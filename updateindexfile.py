import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum

DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")

MINIVER = os.getenv("MINIVER")
SPLENV_REF = os.getenv("SPLENV_REF")

BUCKET_NAME = "eups-prod"
GCS_PREFIX = f"gs://{BUCKET_NAME}"
INDEX_FILE = "index.json"

# Subfolders indexed within every conda platform folder.
PLATFORM_SUBFOLDERS = ["manifests/", "env/", "tables/"]
# The src tree has the same subfolders plus these.
SRC_SUBFOLDERS = PLATFORM_SUBFOLDERS + ["products/", "tags/"]

ROOT_FOLDERS = [
    "stack/redhat/el7/conda-system",
    "stack/redhat/el8-arm/conda-system",
    "stack/osx/14-arm/conda-system",
]

MAX_WORKERS = 16


class IndexStatus(StrEnum):
    MISSING = "MISSING"  # no index.json in prod yet
    DIFFERS = "DIFFERS"  # contents or order differs from prod
    UNREADABLE = "UNREADABLE"  # existing index could not be read


@dataclass
class IndexDiff:
    dest: str
    status: IndexStatus
    count: int = 0
    reordered: bool = False
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def filter_folders() -> str:
    if MINIVER and SPLENV_REF:
        return f"miniconda3-{MINIVER}-{SPLENV_REF}"
    return ""


def list_recursive(prefix: str) -> list[str] | None:
    """Return every object path under prefix (recursive), relative to the bucket.
    Returns [] if the prefix matched nothing or None if the listing command itself failed.

    Uses the ``**`` wildcard so gcloud returns a flat list of object URLs
    (no directory placeholders, no per-directory headers), which is cheap to
    group in Python. A prefix that matches nothing yields an empty list.
    """
    target = f"{GCS_PREFIX}/{prefix.rstrip('/')}/**"
    try:
        result = subprocess.run(
            ["gcloud", "storage", "ls", target],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        # error messages taken from gcloud storage ls docs. Could change in the future
        if "matched no objects" in stderr:
            return []
        print(f"ERROR: listing {target} failed: {stderr.strip()}")
        return None
    strip = f"{GCS_PREFIX}/"
    return [u[len(strip) :] for u in result.stdout.splitlines() if u.startswith(strip)]


def group_by_parent(objects: list[str]) -> dict[str, list[str]]:
    """Map each folder prefix to the file names directly inside it."""
    by_parent: dict[str, list[str]] = defaultdict(list)
    for obj in objects:
        cut = obj.rfind("/")
        parent, name = obj[: cut + 1], obj[cut + 1 :]
        if name and name != INDEX_FILE:
            by_parent[parent].append(name)
    return by_parent


def existing_prefixes(objects: list[str]) -> set[str]:
    """Every folder prefix that has at least one object beneath it."""
    prefixes: set[str] = set()
    for obj in objects:
        parts = obj.split("/")
        for i in range(1, len(parts)):
            prefixes.add("/".join(parts[:i]) + "/")
    return prefixes


def platform_folders(root: str, objects: list[str]) -> set[str]:
    """Discover the conda platform folders (one level below a root)."""
    base = f"{root.rstrip('/')}/"
    folders = set()
    for obj in objects:
        if not obj.startswith(base):
            continue
        seg = obj[len(base) :].split("/", 1)[0]
        if seg:
            folders.add(f"{base}{seg}/")
    return folders


def upload_index(target: str, names: list[str]) -> None:
    """Write the file list as index.json into the target folder."""
    dest = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        tmp = f.name
        json.dump(names, f)
    try:
        subprocess.run(
            ["gcloud", "storage", "cp", tmp, dest],
            capture_output=True,
            check=True,
            text=True,
        )
        print(f"updated {dest}")
    # Adding more detail to when an upload fails
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"upload to {dest} failed: {(e.stderr or '').strip()}") from e
    finally:
        os.remove(tmp)


def target_prefixes(root_objects: dict[str, list[str]], existing: set[str]) -> list[str]:
    """Build the ordered, de-duplicated list of folders needing an index."""
    sub = filter_folders()
    targets = [f"stack/src/{f}" for f in SRC_SUBFOLDERS]
    for root, objects in root_objects.items():
        for folder in sorted(platform_folders(root, objects)):
            if sub and sub not in folder:
                continue
            targets.append(folder)
            targets.extend(f"{folder}{f}" for f in PLATFORM_SUBFOLDERS)
    targets = [t for t in targets if t in existing]
    return list(dict.fromkeys(targets))


def fetch_current_index(target: str) -> list[str] | None:
    """Download the existing index.json for a target, or None if absent. Raise RuntimeError if the read itself failed"""
    src = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    try:
        result = subprocess.run(
            ["gcloud", "storage", "cat", src],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if "does not exist" in stderr or "matched no objects" in stderr:
            return None
        raise RuntimeError(f"could not read {src}: {stderr.strip()}") from e
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"WARNING: {src} is not valid JSON")
        return None


def compare_index(target: str, names: list[str]) -> IndexDiff | None:
    """Compare the generated index against the one currently in prod. Used for testing"""
    dest = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    try:
        current = fetch_current_index(target)
    except RuntimeError as e:
        print(f"WARNING: {e}")
        return IndexDiff(dest=dest, status=IndexStatus.UNREADABLE)

    if current is None:
        return IndexDiff(dest=dest, status=IndexStatus.MISSING, count=len(names))

    names = normalize_index(names)
    current = normalize_index(current)
    if current == names:
        return None  # up-to-date, nothing to report

    cur_set, new_set = set(current), set(names)
    return IndexDiff(
        dest=dest,
        status=IndexStatus.DIFFERS,
        reordered=cur_set == new_set,  # same contents, different order
        added=sorted(new_set - cur_set),
        removed=sorted(cur_set - new_set),
    )


def normalize_index(names: list[str]) -> list[str]:
    """Drop blank/whitespace-only entries and index.json for comparison."""
    return [n for n in names if n and n.strip() and n.strip() != INDEX_FILE]


def main() -> int:
    # One recursive listing for src plus one per conda root, run concurrently.
    listing_prefixes = ["stack/src"] + ROOT_FOLDERS
    with ThreadPoolExecutor(max_workers=len(listing_prefixes)) as pool:
        listings = list(pool.map(list_recursive, listing_prefixes))
    if any(objs is None for objs in listings):
        print("Error: one or more listings failed; aborting and not uploading")
        return 1

    # Narrow the type: after the guard above, no entry is None.
    listings = [objs for objs in listings if objs is not None]

    src_objects = listings[0]
    root_objects = dict(zip(ROOT_FOLDERS, listings[1:]))

    all_objects = list(src_objects)
    for objects in root_objects.values():
        all_objects.extend(objects)

    by_parent = group_by_parent(all_objects)
    existing = existing_prefixes(all_objects)
    targets = target_prefixes(root_objects, existing)

    action = compare_index if DRY_RUN else upload_index
    if DRY_RUN:
        print("[DRY-RUN] no objects will be uploaded")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(action, t, sorted(by_parent.get(t, []))): t for t in targets}
        results = []
        failures = 0
        for future in as_completed(futures):
            target = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error: {target} failed: {e}")
                failures += 1

    if not DRY_RUN:
        if failures:
            print(f"ERROR: {failures} of {len(targets)} uploads failed")
            return 1
        return 0
    # Recap: only folders whose index would change.
    diffs = [r for r in results if r]
    print("\n" + "=" * 60)
    print(f"[DRY-RUN] RECAP: {len(diffs)} of {len(targets)} indexes differ")
    print("=" * 60)

    for r in diffs:
        if r.status is IndexStatus.MISSING:
            print(f"\n{r.dest}")
            print(f"    MISSING in prod, would create with {r.count} entries")
            continue
        if r.status is IndexStatus.UNREADABLE:
            print(f"\n{r.dest} UNREADABLE (could not compare)")
            continue

        print(f"\n{r.dest}  DIFFERS")
        if r.reordered:
            print("    (same contents, different order)")
        for name in r.added:
            print(f"    + {name}")
        for name in r.removed:
            print(f"    - {name}")
    if failures:
        print(f"WARNING: {failures} comparisons errored")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
