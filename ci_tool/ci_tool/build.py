"""Orchestrates `maturin build` for a single (arch, python_version) cell
of the CI build matrix.

All architecture-specific values are read from `arches.py`; this module
combines them with build-time parameters (API level, lib dir) and wires
the result into the environment maturin/cargo/pyo3-build-config expect.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .arches import Arch
from .wheel_tags import wheel_platform_tag


@dataclass(frozen=True)
class BuildConfig:
    arch: Arch
    python_version: str  # "3.14"
    android_api_level: int
    ndk_home: Path
    libpython_dir: Path  # dir with real libpython*.so + generated sysconfigdata
    manifest_path: Path  # pydantic-core's Cargo.toml
    out_dir: Path

    def __post_init__(self) -> None:
        # cargo invokes the rustc/linker subprocess with its cwd set to
        # the package root (the directory containing the manifest being
        # built), not necessarily this process's own cwd. Every path is
        # therefore absolutized exactly once, here, so no downstream code
        # has to reason about whose cwd a relative path resolves against.
        object.__setattr__(self, "ndk_home", Path(self.ndk_home).resolve())
        object.__setattr__(self, "libpython_dir", Path(self.libpython_dir).resolve())
        object.__setattr__(self, "manifest_path", Path(self.manifest_path).resolve())
        object.__setattr__(self, "out_dir", Path(self.out_dir).resolve())


def ndk_host_tag() -> str:
    """Host-OS subdir under <ndk>/toolchains/llvm/prebuilt/. Hardcoded
    since this tool only ever runs on GitHub's Linux x86_64 runners."""
    return "linux-x86_64"


def ndk_clang_target(arch: Arch, android_api_level: int) -> str:
    """Full NDK clang wrapper triple, e.g. "aarch64-linux-android24"."""
    return f"{arch.ndk_clang_triple}{android_api_level}"


def toolchain_bin_dir(ndk_home: Path) -> Path:
    return ndk_home / "toolchains" / "llvm" / "prebuilt" / ndk_host_tag() / "bin"


def build_env(cfg: BuildConfig) -> dict[str, str]:
    """Environment for the `maturin build` subprocess: CC/AR/linker point
    at the NDK's clang instead of the host's, and PYO3_CROSS_LIB_DIR/
    PYO3_CROSS_PYTHON_VERSION point pyo3-build-config at our generated
    sysconfigdata instead of trying to execute a target-arch interpreter,
    which cannot run on the Linux build host.
    """
    bin_dir = toolchain_bin_dir(cfg.ndk_home)
    clang_target = ndk_clang_target(cfg.arch, cfg.android_api_level)
    cc = bin_dir / f"{clang_target}-clang"
    cxx = bin_dir / f"{clang_target}-clang++"
    ar = bin_dir / "llvm-ar"

    target_underscored = cfg.arch.rust_target.replace("-", "_")
    target_upper = target_underscored.upper()

    env = dict(os.environ)
    env.update(
        {
            "CC": str(cc),
            "CXX": str(cxx),
            "AR": str(ar),
            f"CC_{target_underscored}": str(cc),
            f"AR_{target_underscored}": str(ar),
            f"CARGO_TARGET_{target_upper}_LINKER": str(cc),
            "PYO3_CROSS_LIB_DIR": str(cfg.libpython_dir),
            "PYO3_CROSS_PYTHON_VERSION": cfg.python_version,
            "PYO3_CROSS": "1",
        }
    )
    return env


def maturin_command(cfg: BuildConfig) -> list[str]:
    return [
        "maturin",
        "build",
        "--release",
        "--target",
        cfg.arch.rust_target,
        "--manifest-path",
        str(cfg.manifest_path),
        "--out",
        str(cfg.out_dir),
        # auditwheel has no Android policy; patch.py runs our own
        # NEEDED/RPATH checks instead.
        "--skip-auditwheel",
    ]


def run_maturin_build(cfg: BuildConfig) -> Path:
    """Runs maturin, returns the path to the single wheel it produced."""
    if shutil.which("maturin") is None:
        raise RuntimeError("maturin not found on PATH")

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(maturin_command(cfg), env=build_env(cfg), check=True)

    produced = sorted(cfg.out_dir.glob("*.whl"))
    if len(produced) != 1:
        raise RuntimeError(f"Expected exactly one wheel in {cfg.out_dir}, found {produced}")
    return produced[0]


def retag_wheel(wheel_path: Path, cfg: BuildConfig) -> Path:
    """Rewrites the maturin-produced filename's platform component to our
    Android tag (see wheel_tags.py), since maturin has no notion of PEP
    738 Android tags for a foreign --target."""
    stem_parts = wheel_path.stem.split("-")
    if len(stem_parts) < 4:
        raise ValueError(f"Unexpected wheel filename shape: {wheel_path.name}")
    *head, _old_platform = stem_parts
    new_platform = wheel_platform_tag(cfg.arch, cfg.android_api_level)
    new_path = wheel_path.with_name("-".join([*head, new_platform]) + ".whl")
    wheel_path.rename(new_path)
    return new_path
