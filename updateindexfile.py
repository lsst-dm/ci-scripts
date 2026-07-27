import json
import os
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

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


def filter_folders() -> str:
    if MINIVER and SPLENV_REF:
        return f"miniconda3-{MINIVER}-{SPLENV_REF}"
    return ""


def list_recursive(prefix: str) -> list[str]:
    """Return every object path under prefix (recursive), relative to the bucket.

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
    except subprocess.CalledProcessError:
        print(f"{target} matched no objects, skipping")
        return []
    strip = f"{GCS_PREFIX}/"
    return [u[len(strip):] for u in result.stdout.splitlines() if u.startswith(strip)]


def group_by_parent(objects: list[str]) -> dict[str, list[str]]:
    """Map each folder prefix to the file names directly inside it."""
    by_parent: dict[str, list[str]] = defaultdict(list)
    for obj in objects:
        cut = obj.rfind("/")
        parent, name = obj[: cut + 1], obj[cut + 1:]
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
        seg = obj[len(base):].split("/", 1)[0]
        if seg:
            folders.add(f"{base}{seg}/")
    return folders


def upload_index(target: str, names: list[str]) -> None:
    """Write the file list as index.json into the target folder."""
    dest = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(names, f)
        tmp = f.name
    try:
        subprocess.run(
            ["gcloud", "storage", "cp", tmp, dest],
            capture_output=True,
            check=True,
            text=True,
        )
        print(f"updated {dest}")
    finally:
        os.remove(tmp)


def target_prefixes(
    root_objects: dict[str, list[str]], existing: set[str]
) -> list[str]:
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
    """Download the existing index.json for a target, or None if absent."""
    src = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    try:
        result = subprocess.run(
            ["gcloud", "storage", "cat", src],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"WARNING: {src} is not valid JSON")
        return None

def compare_index(target: str, names: list[str]) -> dict | None:
    """Compare the generated index against the one currently in prod. Used for testing"""
    dest = f"{GCS_PREFIX}/{target}{INDEX_FILE}"
    current = fetch_current_index(target)

    if current is None:
        return {
            "dest": dest,
            "status": "MISSING",
            "count": len(names),
        }

    names =normalize_index(names)
    current = normalize_index(current)
    if current == names:
        return None  # up-to-date, nothing to report

    cur_set, new_set = set(current), set(names)
    return {
        "dest": dest,
        "status": "DIFFERS",
        "reordered": cur_set == new_set,  # same contents, different order
        "added": sorted(new_set - cur_set),
        "removed": sorted(cur_set - new_set),
    }

def normalize_index(names: list[str]) -> list[str]:
    """Drop blank/whitespace-only entries and index.json for comparison."""
    return [
        n for n in names
        if n and n.strip() and n.strip() != INDEX_FILE
    ]

def main():
    # One recursive listing for src plus one per conda root, run concurrently.
    listing_prefixes = ["stack/src"] + ROOT_FOLDERS
    with ThreadPoolExecutor(max_workers=len(listing_prefixes)) as pool:
        listings = list(pool.map(list_recursive, listing_prefixes))

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
        futures = [
            pool.submit(action, t, sorted(by_parent.get(t, [])))
            for t in targets
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Error: task failed: {e}")
                results.append(None)

    if not DRY_RUN:
        return
    # Recap: only folders whose index would change.
    diffs = [r for r in results if r]
    print("\n" + "=" * 60)
    print(f"[DRY-RUN] RECAP: {len(diffs)} of {len(targets)} indexes differ")
    print("=" * 60)

    for r in diffs:
        if r["status"] == "MISSING":
            print(f"\n{r['dest']}")
            print(f"    MISSING in prod, would create with {r['count']} entries")
            continue

        print(f"\n{r['dest']}  DIFFERS")
        if r["reordered"]:
            print("    (same contents, different order)")
        for name in r["added"]:
            print(f"    + {name}")
        for name in r["removed"]:
            print(f"    - {name}")


if __name__ == "__main__":
    main()
