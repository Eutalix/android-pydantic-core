"""Discovers which Python major.minor version Termux's apt repo
*currently* serves, so the build matrix can be driven by that instead of
a hardcoded guess (see termux.py's module docstring for why).

Only one reference architecture (arm64-v8a) is queried, on the
assumption that all architectures track the same Python version in
lockstep, since Termux builds `python` from one source package across
its supported architectures.
"""
from __future__ import annotations

from .arches import Arch
from .termux import fetch_index, latest_for_arch, list_available_versions, major_minor


def discover_python_version(arch: Arch) -> str:
    """Returns the major.minor Python version (e.g. "3.14") Termux's apt
    repo currently serves for `arch`."""
    index = fetch_index()
    packages = list_available_versions(index)
    pkg = latest_for_arch(packages, arch.termux_arch)
    return major_minor(pkg.version)
