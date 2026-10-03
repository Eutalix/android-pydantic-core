"""Fetches Termux's own `python` .deb package and extracts the real
libpython*.so from it — no mocked/stub library, no fake SONAME.

pydantic-core's build.rs performs a real link step against this library,
and Android extension modules must link against the real libpython,
unlike glibc Linux where this is typically unnecessary.

Termux's apt repo publishes a single rolling `python` package per
architecture, not parallel per-minor-version packages the way Debian
does. `fetch_libpython_for_arch` therefore requires the caller to state
which major.minor it wants and fails with the list of what's actually
available if Termux doesn't currently serve it, rather than silently
substituting a mismatched library (see `matching_for_arch_and_version`).
`discover.py` is the companion module used to find out what IS currently
served, so the build matrix can be driven by that instead of a hardcoded
guess.
"""
from __future__ import annotations

import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .arches import Arch

TERMUX_PYTHON_POOL_URL = "https://packages.termux.dev/apt/termux-main/pool/main/p/python/"

_DEB_RE = re.compile(r'href="python_([\d.]+-\d+)_(?P<arch>[\w]+)\.deb"')


@dataclass(frozen=True)
class TermuxPythonPackage:
    version: str  # e.g. "3.14.6-1"
    termux_arch: str  # e.g. "aarch64"
    deb_url: str


def list_available_versions(index_html: str) -> list[TermuxPythonPackage]:
    """Parses the Termux apt pool directory listing for python .deb files."""
    packages = []
    for match in _DEB_RE.finditer(index_html):
        version, arch = match.group(1), match.group("arch")
        packages.append(
            TermuxPythonPackage(
                version=version,
                termux_arch=arch,
                deb_url=f"{TERMUX_PYTHON_POOL_URL}python_{version}_{arch}.deb",
            )
        )
    return packages


def major_minor(version: str) -> str:
    """"3.14.6-1" -> "3.14"."""
    base = version.partition("-")[0]
    parts = base.split(".")
    return ".".join(parts[:2])


def _version_sort_key(pkg: TermuxPythonPackage) -> tuple:
    base, _, revision = pkg.version.partition("-")
    parts = tuple(int(p) for p in base.split("."))
    return parts + (int(revision or 0),)


def latest_for_arch(packages: list[TermuxPythonPackage], termux_arch: str) -> TermuxPythonPackage:
    """Newest python package for `termux_arch`, regardless of major.minor.
    Used by discover.py to find out what Termux currently serves."""
    candidates = [p for p in packages if p.termux_arch == termux_arch]
    if not candidates:
        raise ValueError(f"No Termux python package found for arch {termux_arch!r}")
    return max(candidates, key=_version_sort_key)


def matching_for_arch_and_version(
    packages: list[TermuxPythonPackage], termux_arch: str, python_version: str
) -> TermuxPythonPackage:
    """Newest Termux python package for `termux_arch` whose major.minor
    equals `python_version` (e.g. "3.14"); raises with the list of what
    IS available if there is no match, since Termux typically serves only
    one python version at a time."""
    candidates = [
        p
        for p in packages
        if p.termux_arch == termux_arch and major_minor(p.version) == python_version
    ]
    if not candidates:
        available = sorted({major_minor(p.version) for p in packages if p.termux_arch == termux_arch})
        raise ValueError(
            f"Termux's apt pool has no python package matching version "
            f"{python_version!r} for arch {termux_arch!r}. Currently "
            f"available major.minor version(s): {available or ['<none found>']}. "
            "Use `ci_tool discover-python-version` to find the current one "
            "instead of hardcoding python_version."
        )
    return max(candidates, key=_version_sort_key)


def fetch_index() -> str:
    resp = requests.get(TERMUX_PYTHON_POOL_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def download_deb(pkg: TermuxPythonPackage, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"python_{pkg.version}_{pkg.termux_arch}.deb"
    if dest.exists():
        return dest
    resp = requests.get(pkg.deb_url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return dest


def extract_libpython(deb_path: Path, extract_dir: Path) -> Path:
    """Extracts libpython*.so from a Termux .deb.

    .deb files are `ar` archives containing a `data.tar.*` member with the
    actual filesystem tree; we shell out to `ar` rather than reimplementing
    the ar format in Python.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ar", "x", str(deb_path.resolve())],
        cwd=extract_dir,
        check=True,
    )

    data_tar = next(extract_dir.glob("data.tar.*"), None)
    if data_tar is None:
        raise FileNotFoundError(f"No data.tar.* found after extracting {deb_path}")

    with tarfile.open(data_tar) as tar:
        members = [
            m for m in tar.getmembers()
            if re.search(r"libpython3\.\d+\.so$", m.name)
        ]
        if not members:
            raise FileNotFoundError(f"No libpython*.so found inside {data_tar}")
        member = max(members, key=lambda m: len(m.name))
        tar.extract(member, path=extract_dir, filter="data")

    extracted = extract_dir / member.name
    final_path = extract_dir / extracted.name.rsplit("/", 1)[-1]
    if extracted != final_path:
        extracted.rename(final_path)
    return final_path


def fetch_libpython_for_arch(arch: Arch, cache_dir: Path, python_version: str) -> tuple[Path, str]:
    """Returns (path to libpython*.so, package version). `python_version`
    must match what Termux's pool actually serves for `arch`."""
    index = fetch_index()
    packages = list_available_versions(index)
    pkg = matching_for_arch_and_version(packages, arch.termux_arch, python_version)
    deb_path = download_deb(pkg, cache_dir / "debs")
    lib_path = extract_libpython(deb_path, cache_dir / "extracted" / arch.termux_arch / python_version)
    return lib_path, pkg.version
