"""Tests for derive_rubinenv_env.py."""

import importlib.util
import json
import os
import subprocess
import sys
from urllib.parse import urlparse

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(TESTS_DIR), "derive_rubinenv_env.py")

CHANNEL = "https://conda.anaconda.org/conda-forge/linux-64"


def _load_script():
    """Import the script so its parsers can be exercised without subprocess."""
    spec = importlib.util.spec_from_file_location("derive_rubinenv_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


derive = _load_script()

RSP_ENV_HEADER = """\
# This file may be used to create an environment using:
# $ conda create --name <env> --file <this file>
# platform: linux-64
# created-by: conda 26.5.3
@EXPLICIT
"""

# (name, version, build, [depends]) in the order conda would list them.
#
# Only the qt6_* build of libopencv depends on qt6-main, so qt6-main is reachable
# from rubin-env solely through a build variant the rsp solve chose.
PACKAGES = [
    ("python", "3.13.7", "hf636f53_0", ["__glibc >=2.17"]),
    ("libstdcxx", "14.3.0", "h8f9b012_0", []),
    ("double-conversion", "3.3.1", "h5888daf_0", []),
    ("xcb-util-cursor", "0.1.5", "hb9d3cd8_0", []),
    ("qt6-main", "6.11.1", "pl5321h16c4a6b_1", ["xcb-util-cursor", "double-conversion"]),
    ("libopencv", "5.0.0", "qt6_h91fa782_601", ["qt6-main >=6.11.1,<6.12.0a0", "libstdcxx >=14"]),
    ("py-opencv", "5.0.0", "qt6_h6945e2d_601", ["libopencv 5.0.0 qt6_h91fa782_601", "python >=3.13"]),
    ("opencv", "5.0.0", "qt6_h12f39d8_601", ["libopencv 5.0.0 qt6_h91fa782_601", "py-opencv"]),
    ("numpy", "2.4.0", "py313h5d7c261_0", ["python >=3.13"]),
    ("rubin-env", "13.1.0", "py313h87b86d6_2", ["opencv", "numpy", "python >=3.13,<3.14.0a0"]),
    # RSP-only: reachable from rubin-env-rsp but not from rubin-env.
    ("notebook-shim", "0.2.5", "pyhd8ed1ab_0", []),
    ("jupyterlab", "4.5.0", "pyhd8ed1ab_0", ["notebook-shim"]),
    ("rubin-env-rsp", "13.1.0", "py313h4f54f2c_2", ["rubin-env 13.1.0 py313h87b86d6_2", "jupyterlab"]),
]

RUBIN_ENV_REACHABLE = {
    "python",
    "libstdcxx",
    "double-conversion",
    "xcb-util-cursor",
    "qt6-main",
    "libopencv",
    "py-opencv",
    "opencv",
    "numpy",
    "rubin-env",
}

RSP_ONLY = {"notebook-shim", "jupyterlab", "rubin-env-rsp"}


def url_line(name, version, build, channel=CHANNEL):
    return f"{channel}/{name}-{version}-{build}.conda#{'a' * 32}"


def write_env(path, packages, header=RSP_ENV_HEADER, channels=None):
    """Write a conda explicit file, optionally overriding a package's channel."""
    channels = channels or {}
    with open(path, "w") as f:
        f.write(header)
        for name, version, build, _ in packages:
            f.write(url_line(name, version, build, channels.get(name, CHANNEL)) + "\n")


def write_conda_meta(path, packages):
    os.makedirs(path, exist_ok=True)
    for name, version, build, depends in packages:
        with open(os.path.join(path, f"{name}-{version}-{build}.json"), "w") as f:
            json.dump(
                {
                    "name": name,
                    "version": version,
                    "build": build,
                    "depends": depends,
                },
                f,
            )


@pytest.fixture
def env(tmp_path):
    """A complete, self-consistent rubin-env-rsp build env."""
    rsp_env = tmp_path / "w_2026_36_rsp.env"
    conda_meta = tmp_path / "conda-meta"
    write_env(rsp_env, PACKAGES)
    write_conda_meta(conda_meta, PACKAGES)
    return {
        "rsp_env": str(rsp_env),
        "conda_meta": str(conda_meta),
        "out": str(tmp_path / "w_2026_36.env"),
    }


def run(env, *extra):
    return subprocess.run(
        [
            sys.executable,
            SCRIPT,
            "--rsp-env",
            env["rsp_env"],
            "--conda-meta",
            env["conda_meta"],
            "--out",
            env["out"],
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def is_url(line):
    return urlparse(line.strip()).scheme in ("http", "https", "file")


def urls_of(path):
    with open(path) as f:
        return [ln.rstrip("\n") for ln in f if is_url(ln)]


def names_of(path):
    names = []
    for line in urls_of(path):
        base = os.path.basename(urlparse(line).path).removesuffix(".conda")
        names.append(base.rsplit("-", 2)[0])
    return names


def test_qt6_variant_dependency_is_kept(env):
    """qt6-main is reachable only via the rsp solve's qt6_* libopencv build."""
    result = run(env)
    assert result.returncode == 0, result.stderr
    names = names_of(env["out"])
    assert "qt6-main" in names
    assert "libopencv" in names
    # qt6-main's own transitive deps come along too.
    assert "xcb-util-cursor" in names
    assert "double-conversion" in names


def test_output_is_exactly_the_rubin_env_closure(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert set(names_of(env["out"])) == RUBIN_ENV_REACHABLE


def test_rsp_only_packages_are_excluded(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    names = set(names_of(env["out"]))
    assert not (names & RSP_ONLY)


def test_output_is_dependency_closed(env):
    """Every dependency of every emitted package resolves within the output."""
    result = run(env)
    assert result.returncode == 0, result.stderr
    emitted = set(names_of(env["out"]))
    depends = {name: deps for name, _, _, deps in PACKAGES}
    for name in emitted:
        for spec in depends[name]:
            dep = spec.split()[0]
            if dep.startswith("__"):
                continue
            assert dep in emitted, f"{dep} required by {name} is missing"


def test_header_order_and_md5_are_preserved(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    with open(env["out"]) as f:
        out_lines = f.read().splitlines()
    with open(env["rsp_env"]) as f:
        rsp_lines = f.read().splitlines()

    assert out_lines[: len(RSP_ENV_HEADER.splitlines())] == RSP_ENV_HEADER.splitlines()
    # emitted URL lines are byte-identical to their rsp counterparts, in order
    out_urls = [ln for ln in out_lines if is_url(ln)]
    rsp_urls = [ln for ln in rsp_lines if is_url(ln)]
    assert out_urls == [ln for ln in rsp_urls if ln in set(out_urls)]
    assert all(ln.endswith("#" + "a" * 32) for ln in out_urls)


def test_environment_name_header_is_passed_through(tmp_path):
    """envconfig greps '#environment_name:' back out of the derived file."""
    rsp_env = tmp_path / "rsp.env"
    conda_meta = tmp_path / "conda-meta"
    header = "#environment_name: lsst-scipipe-13.1.0-rsp\n" + RSP_ENV_HEADER
    write_env(rsp_env, PACKAGES, header=header)
    write_conda_meta(conda_meta, PACKAGES)
    env = {
        "rsp_env": str(rsp_env),
        "conda_meta": str(conda_meta),
        "out": str(tmp_path / "out.env"),
    }
    result = run(env)
    assert result.returncode == 0, result.stderr
    with open(env["out"]) as f:
        assert f.readline().rstrip("\n") == "#environment_name: lsst-scipipe-13.1.0-rsp"


def test_file_channel_packages_are_treated_as_packages(tmp_path):
    """The prereleased-rubin-env path installs from a local file channel.

    A file:// root must satisfy the missing-root check, and a file:// RSP-only
    package must be filtered rather than copied through as a header line.
    """
    rsp_env = tmp_path / "rsp.env"
    conda_meta = tmp_path / "conda-meta"
    local = "file:///tmp/rubinenv-feedstock/build_artifacts/linux-64"
    write_env(
        rsp_env,
        PACKAGES,
        channels={"rubin-env": local, "rubin-env-rsp": local, "jupyterlab": local},
    )
    write_conda_meta(conda_meta, PACKAGES)
    env = {
        "rsp_env": str(rsp_env),
        "conda_meta": str(conda_meta),
        "out": str(tmp_path / "out.env"),
    }
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert set(names_of(env["out"])) == RUBIN_ENV_REACHABLE
    urls = urls_of(env["out"])
    assert any(ln.startswith(local) for ln in urls)
    # the file:// RSP-only packages are gone, not passed through verbatim
    with open(env["out"]) as f:
        out_text = f.read()
    assert "jupyterlab" not in out_text
    assert "rubin-env-rsp" not in out_text


def test_missing_root_fails(env):
    result = run(env, "--root", "rubin-env-nonesuch")
    assert result.returncode != 0
    assert "rubin-env-nonesuch" in result.stderr
    assert not os.path.exists(env["out"])


def test_conda_meta_missing_metadata_fails(tmp_path):
    """A stale or wrong active env must not silently produce a partial file."""
    rsp_env = tmp_path / "rsp.env"
    conda_meta = tmp_path / "conda-meta"
    write_env(rsp_env, PACKAGES)
    write_conda_meta(conda_meta, [p for p in PACKAGES if p[0] != "qt6-main"])
    env = {
        "rsp_env": str(rsp_env),
        "conda_meta": str(conda_meta),
        "out": str(tmp_path / "out.env"),
    }
    result = run(env)
    assert result.returncode != 0
    assert "qt6-main" in result.stderr
    assert not os.path.exists(env["out"])


def test_closure_violation_is_reported(tmp_path):
    """A reachable package with no URL in the rsp list must fail the build."""
    rsp_env = tmp_path / "rsp.env"
    conda_meta = tmp_path / "conda-meta"
    write_env(rsp_env, [p for p in PACKAGES if p[0] != "qt6-main"])
    write_conda_meta(conda_meta, PACKAGES)
    env = {
        "rsp_env": str(rsp_env),
        "conda_meta": str(conda_meta),
        "out": str(tmp_path / "out.env"),
    }
    result = run(env)
    assert result.returncode != 0
    assert "qt6-main" in result.stderr
    assert "libopencv" in result.stderr
    assert not os.path.exists(env["out"])


# --- real published artifacts -------------------------------------------------
#
# tests/data holds the w_2026_36 pair from https://eups.lsst.cloud/stack/src/env:
# the rubin-env-rsp build record, and the ${tag}.env the old two-solve derivation
# produced from it. Vendored rather than fetched so the suite stays offline.

DATA = os.path.join(TESTS_DIR, "data")
REAL_RSP_ENV = os.path.join(DATA, "w_2026_36_rsp.env")
REAL_ENV = os.path.join(DATA, "w_2026_36.env")

REAL_HEADER = [
    "#environment_name: lsst-scipipe-13.1.0-rsp",
    "# This file may be used to create an environment using:",
    "# $ conda create --name <env> --file <this file>",
    "# platform: linux-64",
    "# created-by: conda 26.5.3",
    "@EXPLICIT",
]


def real_urls_by_name(path):
    """Return name -> url line for a real published env file."""
    with open(path) as f:
        lines = f.read().splitlines()
    return {derive.pkgname(ln): ln for ln in lines if derive.is_package_line(ln)}


def test_real_env_file_lines_are_classified():
    """Every line of a real file is a package URL or a reproducible header."""
    with open(REAL_RSP_ENV) as f:
        lines = f.read().splitlines()
    packages = [ln for ln in lines if derive.is_package_line(ln)]
    assert [ln for ln in lines if not derive.is_package_line(ln)] == REAL_HEADER
    assert len(packages) == 1030
    # published files omit the '#md5' that `conda list --explicit` emits
    assert not any("#" in ln for ln in packages)


def test_real_env_package_names_parse():
    names = real_urls_by_name(REAL_RSP_ENV)
    assert len(names) == 1030, "names must be unique within one solve"
    assert {"rubin-env", "rubin-env-rsp", "rubin-env-nosysroot"} <= set(names)
    # '_x86_64-microarch-level-4-3_icelake.conda' and a '.tar.bz2' entry
    assert "_x86_64-microarch-level" in names
    assert "font-ttf-dejavu-sans-mono" in names
    assert not any(n.endswith(derive.ARCHIVE_SUFFIXES) or "/" in n for n in names)


def test_published_pair_shares_byte_identical_urls():
    """The subset must carry the build record's exact versions and builds."""
    rsp = real_urls_by_name(REAL_RSP_ENV)
    published = real_urls_by_name(REAL_ENV)
    shared = set(rsp) & set(published)
    assert len(shared) == 780
    assert all(rsp[name] == published[name] for name in shared)


def test_published_env_shows_the_two_solve_bug():
    """Real-data shape of what this script replaces.

    w_2026_36.env keeps the qt6_* libopencv build but drops qt6-main, and lists
    six packages the build env never contained -- both impossible when the
    subset is a closure of the build record.
    """
    rsp = real_urls_by_name(REAL_RSP_ENV)
    published = real_urls_by_name(REAL_ENV)
    assert "qt6_" in published["libopencv"]
    assert "qt6-main" in rsp
    assert "qt6-main" not in published
    assert set(published) - set(rsp) == {
        "flatbuffers",
        "libdovi",
        "libplacebo",
        "onednn",
        "onednn-cpu-threadpool",
        "pybind11-abi",
    }
