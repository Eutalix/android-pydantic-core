"""Renders the body of a GitHub Release for a pydantic-core wheel drop.

Deliberately split from CHANGELOG.md (see cliff.toml): changes in
pydantic-core itself are linked, never duplicated. What this module owns
is build provenance — exact Termux `python` package, NDK, API level —
since that is unique to this repo and explains any runtime differences.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UPSTREAM_RELEASES_URL = "https://github.com/pydantic/pydantic/releases"


@dataclass
class WheelBuildInfo:
    android_abi: str
    python_version: str  # e.g. "3.14"
    wheel_filename: str
    termux_python_pkg_version: str  # e.g. "3.14.6-1" — the exact .deb used


@dataclass
class ReleaseContext:
    pydantic_core_version: str
    ndk_version: str
    android_api_level: int
    maturin_version: str
    wheels: list[WheelBuildInfo] = field(default_factory=list)


def render(ctx: ReleaseContext) -> str:
    archs = sorted({w.android_abi for w in ctx.wheels})
    pyvers = sorted({w.python_version for w in ctx.wheels})

    lines = [
        f"### Automated Android build of `pydantic-core` {ctx.pydantic_core_version}",
        "",
        f"Upstream changes: see the [pydantic release notes]({UPSTREAM_RELEASES_URL}) "
        f"for `{ctx.pydantic_core_version}`. This repo only repackages upstream "
        "for Android/Termux, it does not modify pydantic-core's behavior.",
        "",
        "**Build provenance**",
        "",
        f"- NDK: `{ctx.ndk_version}`",
        f"- Minimum Android API level: `{ctx.android_api_level}`",
        f"- maturin: `{ctx.maturin_version}`",
        f"- Architectures: {', '.join(f'`{a}`' for a in archs)}",
        f"- Python versions: {', '.join(f'`{p}`' for p in pyvers)}",
        "- Linked against the real `libpython*.so` extracted from Termux's "
        "own `python` package (no mocked/stub library), per architecture:",
    ]
    for w in sorted(ctx.wheels, key=lambda w: (w.android_abi, w.python_version)):
        lines.append(
            f"  - `{w.android_abi}` / py{w.python_version}: "
            f"Termux `python` package `{w.termux_python_pkg_version}` "
            f"(`{w.wheel_filename}`)"
        )
    lines += [
        "",
        "**Installation**",
        "",
        "```bash",
        "pip install pydantic-core --extra-index-url "
        "https://eutalix.github.io/android-pydantic-core/",
        "```",
        "",
        "**Compatibility note**: officially tested on Termux. The wheel's "
        "RPATH also includes a flat-library-layout search path, which is "
        "expected (but not CI-tested) to work under other Android Python "
        "runtimes using the same Python version "
        f"({', '.join(pyvers)}) that expose a real `libpython*.so` "
        "(e.g. python-for-android/Kivy, Flet).",
    ]
    return "\n".join(lines)
