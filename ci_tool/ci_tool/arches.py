"""Single source of truth for every architecture-specific value.

Every other module (wheel tagging, sysconfigdata generation, Termux
package fetching, maturin invocation, smoke testing) reads from this
table instead of re-deriving architecture-specific values inline.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Arch:
    # Android NDK ABI name; also the identifier used in the GitHub
    # Actions build matrix.
    android_abi: str
    # rustc/cargo target triple for this ABI.
    rust_target: str
    # Termux's own architecture identifier: used in .deb filenames and as
    # the exact `termux/termux-docker:<termux_arch>` image tag.
    termux_arch: str
    # NDK/autoconf-style architecture triple. Used for the sysroot lib
    # subdirectory AND for the compiled extension's EXT_SUFFIX — these
    # must match what the real Android/CPython interpreter expects, which
    # is not always the same string as `rust_target` (see armeabi-v7a).
    ndk_lib_arch: str
    # NDK clang wrapper triple without the trailing API-level number
    # (e.g. "aarch64-linux-android", or "armv7a-linux-androideabi" for
    # armeabi-v7a — note this differs from both `rust_target` and
    # `ndk_lib_arch`).
    ndk_clang_triple: str


ARCHES: dict[str, Arch] = {
    "arm64-v8a": Arch(
        android_abi="arm64-v8a",
        rust_target="aarch64-linux-android",
        termux_arch="aarch64",
        ndk_lib_arch="aarch64-linux-android",
        ndk_clang_triple="aarch64-linux-android",
    ),
    "armeabi-v7a": Arch(
        android_abi="armeabi-v7a",
        rust_target="armv7-linux-androideabi",
        termux_arch="arm",
        ndk_lib_arch="arm-linux-androideabi",
        ndk_clang_triple="armv7a-linux-androideabi",
    ),
    "x86_64": Arch(
        android_abi="x86_64",
        rust_target="x86_64-linux-android",
        termux_arch="x86_64",
        ndk_lib_arch="x86_64-linux-android",
        ndk_clang_triple="x86_64-linux-android",
    ),
    "x86": Arch(
        android_abi="x86",
        rust_target="i686-linux-android",
        termux_arch="i686",
        ndk_lib_arch="i686-linux-android",
        ndk_clang_triple="i686-linux-android",
    ),
}


def get(android_abi: str) -> Arch:
    try:
        return ARCHES[android_abi]
    except KeyError as exc:
        raise ValueError(
            f"Unknown architecture {android_abi!r}. Known: {sorted(ARCHES)}"
        ) from exc


def all_abis() -> list[str]:
    return list(ARCHES)
