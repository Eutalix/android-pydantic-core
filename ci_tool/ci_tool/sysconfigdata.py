"""Generates a real `_sysconfigdata__android_<arch>.py` file.

Read by both maturin's `cross_compile::parse_sysconfigdata` (wheel
metadata/tag decisions) and pyo3-build-config's
`InterpreterConfig::from_sysconfigdata` (via PYO3_CROSS_LIB_DIR). Using
one real file for both avoids maturin and the actual `cargo build`
disagreeing about the target Python's version/ABI.
"""
from __future__ import annotations

from pathlib import Path

from .arches import Arch

TERMUX_PREFIX = "/data/data/com.termux/files/usr"


def render(
    *,
    python_version: str,  # "3.14"
    arch: Arch,
    android_api_level: int,
    pointer_width_bits: int = 64,
) -> str:
    major, minor = python_version.split(".")
    soabi = f"cpython-{major}{minor}"
    ldlibrary = f"libpython{python_version}.so"
    libdir = f"{TERMUX_PREFIX}/lib"

    fields = {
        "SOABI": soabi,
        "VERSION": python_version,
        "Py_ENABLE_SHARED": 1,
        "LIBDIR": libdir,
        "LDLIBRARY": ldlibrary,
        "LDVERSION": python_version,
        "SIZEOF_VOID_P": pointer_width_bits // 8,
        "ANDROID_API_LEVEL": android_api_level,
        "Py_GIL_DISABLED": 0,
        "Py_DEBUG": 0,
        # Must use the NDK/autoconf-style triple (arch.ndk_lib_arch), not
        # rustc's own target name (arch.rust_target) — these differ for
        # armeabi-v7a ("arm-linux-androideabi" vs "armv7-linux-androideabi"),
        # and the real interpreter's import machinery only looks for the
        # former.
        "EXT_SUFFIX": f".{soabi}-{arch.ndk_lib_arch}.so",
        "PYTHONFRAMEWORK": "",
    }

    lines = ["build_time_vars = {"]
    for key, value in fields.items():
        lines.append(f"    {key!r}: {value!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write(
    dest_dir: Path,
    *,
    python_version: str,
    arch: Arch,
    android_api_level: int,
    pointer_width_bits: int = 64,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Keyed by rust_target purely as a lookup name for PYO3_CROSS_LIB_DIR;
    # unrelated to EXT_SUFFIX's own triple requirement above.
    filename = f"_sysconfigdata__android_{arch.rust_target}.py"
    path = dest_dir / filename
    path.write_text(
        render(
            python_version=python_version,
            arch=arch,
            android_api_level=android_api_level,
            pointer_width_bits=pointer_width_bits,
        )
    )
    return path
