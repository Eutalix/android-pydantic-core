"""Computes the PEP 738 Android wheel platform tag.

Mirrors `packaging.tags.android_platforms()`'s normalization, but
reimplemented here because we need to compute the tag for an arbitrary
*target* arch/API level on a plain Linux CI host — `packaging.tags` can
only describe the machine it's currently running on.
"""
from __future__ import annotations

import re

from .arches import Arch

_NORMALIZE_RE = re.compile(r"[.\- ]")


def normalize(value: str) -> str:
    """Equivalent to packaging.tags._normalize_string(): replaces
    ".", "-", " " with "_"."""
    return _NORMALIZE_RE.sub("_", value)


def android_abi_tag(arch: Arch) -> str:
    """The `{abi}` component of an `android_{api}_{abi}` platform tag."""
    return normalize(arch.android_abi)


def android_platform_tags(arch: Arch, min_api_level: int) -> list[str]:
    """Every platform tag a wheel built for `arch`/`min_api_level` satisfies."""
    abi = android_abi_tag(arch)
    return [f"android_{abi}", f"android_{min_api_level}_{abi}"]


def wheel_platform_tag(arch: Arch, min_api_level: int) -> str:
    """The single platform tag baked into the wheel filename. The
    API-qualified form is used (not the bare `android_{abi}` form) to be
    unambiguous about the minimum OS version supported."""
    return f"android_{min_api_level}_{android_abi_tag(arch)}"
