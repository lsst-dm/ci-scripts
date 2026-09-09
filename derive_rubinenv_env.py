#!/usr/bin/env python3
"""Derive the published rubin-env explicit env file from a rubin-env-rsp build.

Builds run in rubin-env-rsp, so `conda list --explicit` of the build env is the
exact build record and is published as ${tag}_rsp.env. ${tag}.env is the subset
of that same solve which a non-RSP consumer needs, and is what `lsstinstall -X`
installs.

The subset has to be computed from the build env itself, by keeping the packages
reachable from rubin-env over `depends`. Taking the package names from a separate
plain rubin-env solve does not work: the two solves can pick different build
variants of the same package, and a variant chosen by the rsp solve may require
packages the rubin-env solve never listed.
"""

import argparse
import glob
import json
import os
import re
import sys
from urllib.parse import urlparse

ARCHIVE_SUFFIXES = (".conda", ".tar.bz2")

# conda explicit files may reference a local channel as well as a remote one;
# the prereleased-rubin-env build path installs from a file channel.
PACKAGE_SCHEMES = ("http", "https", "file")


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def is_package_line(line):
    """Return True if the line is a package URL rather than a comment/@EXPLICIT."""
    return urlparse(line.strip()).scheme in PACKAGE_SCHEMES


def pkgname(line):
    """Return the package name from a conda explicit URL line.

    Package names may contain '-', so trim the trailing '-<version>-<build>'
    fields rather than splitting on '-'.
    """
    fn = os.path.basename(urlparse(line.strip()).path)
    for suffix in ARCHIVE_SUFFIXES:
        if fn.endswith(suffix):
            fn = fn.removesuffix(suffix)
            break
    return fn.rsplit("-", 2)[0]


def depname(spec):
    """Return the bare package name from a conda match spec."""
    return re.split(r"[\s=<>!|,\[]", spec.strip(), maxsplit=1)[0]


def read_rsp_env(path):
    """Return (lines, name -> url line) for a conda explicit file.

    Non-URL lines are kept in `lines` so they can be reproduced in place: the
    conda header, @EXPLICIT, and lsstsw's leading '#environment_name:' line,
    which envconfig greps back out of the derived file.
    """
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError as e:
        die(f"unable to read --rsp-env {path}: {e}")

    urls = {}
    for line in lines:
        if not is_package_line(line):
            continue
        name = pkgname(line)
        if name in urls:
            die(f"{path} lists {name} more than once")
        urls[name] = line
    if not urls:
        die(f"{path} contains no package URLs")
    return lines, urls


def read_conda_meta(path):
    """Return name -> list of dependency specs from a conda-meta directory."""
    files = glob.glob(os.path.join(path, "*.json"))
    if not files:
        die(f"no package metadata found in --conda-meta {path}")

    depends = {}
    for f in files:
        try:
            with open(f) as fh:
                meta = json.load(fh)
        except (OSError, ValueError) as e:
            die(f"unable to read {f}: {e}")
        name = meta.get("name")
        if name:
            depends[name] = meta.get("depends", [])
    return depends


def reachable_from(roots, depends):
    """Return the set of package names reachable from roots over `depends`."""
    seen = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for spec in depends.get(name, []):
            dep = depname(spec)
            # __glibc, __unix, ... are virtual packages with no artifact
            if dep and not dep.startswith("__") and dep not in seen:
                stack.append(dep)
    return seen


def build_argparser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rsp-env",
        required=True,
        help="conda explicit file for the rubin-env-rsp build env (${tag}_rsp.env)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="derived conda explicit file to write (${tag}.env)",
    )
    parser.add_argument(
        "--conda-meta",
        default=None,
        help="conda-meta directory of the build env "
             "(default: $CONDA_PREFIX/conda-meta)",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="metapackage to walk from; repeatable (default: rubin-env)",
    )
    return parser


def derive(rsp_env, out_path, conda_meta, roots):
    """Write the subset of `rsp_env` reachable from `roots` to `out_path`."""
    lines, urls = read_rsp_env(rsp_env)
    depends = read_conda_meta(conda_meta)

    # A package in the build record with no metadata means --conda-meta belongs
    # to a different or stale env; walking it would emit a partial file.
    without_meta = sorted(set(urls) - set(depends))
    if without_meta:
        die(
            f"--conda-meta {conda_meta} has no metadata for "
            f"{len(without_meta)} package(s) listed in {rsp_env}; "
            f"it does not describe the same environment: "
            f"{', '.join(without_meta)}"
        )

    missing_roots = [r for r in roots if r not in urls]
    if missing_roots:
        die(
            f"{rsp_env} does not contain root package(s) "
            f"{', '.join(missing_roots)}; rubin-env-rsp is expected to depend "
            f"on rubin-env"
        )

    reachable = reachable_from(roots, depends)

    # Closure guard: the walk cannot violate this, which is the point -- it pins
    # the invariant so a later change here cannot publish an env that installs
    # and then fails to import.
    violations = {}
    for name in sorted(reachable):
        if name in urls:
            continue
        for parent in sorted(reachable):
            if parent in urls and name in {depname(s) for s in depends.get(parent, [])}:
                violations.setdefault(name, []).append(parent)
    if violations:
        print(
            f"ERROR: derived env is not dependency closed -- "
            f"{len(violations)} package(s) reachable from "
            f"{', '.join(roots)} have no entry in {rsp_env}:",
            file=sys.stderr,
        )
        for name, parents in sorted(violations.items()):
            print(f"    {name} <- required by: {', '.join(parents)}", file=sys.stderr)
        sys.exit(1)

    out = []
    for line in lines:
        if not is_package_line(line):
            out.append(line)
        elif pkgname(line) in reachable:
            out.append(line)

    try:
        with open(out_path, "w") as f:
            f.write("\n".join(out) + "\n")
    except OSError as e:
        die(f"unable to write --out {out_path}: {e}")

    kept = sum(1 for line in out if is_package_line(line))
    print(
        f"derived {out_path}: {kept} of {len(urls)} packages from "
        f"{rsp_env} (reachable from {', '.join(roots)})"
    )


def main():
    args = build_argparser().parse_args()

    conda_meta = args.conda_meta
    if conda_meta is None:
        prefix = os.environ.get("CONDA_PREFIX")
        if not prefix:
            die("--conda-meta not given and CONDA_PREFIX is unset; "
                "is the build environment activated?")
        conda_meta = os.path.join(prefix, "conda-meta")

    derive(args.rsp_env, args.out, conda_meta, args.root or ["rubin-env"])


if __name__ == "__main__":
    main()
