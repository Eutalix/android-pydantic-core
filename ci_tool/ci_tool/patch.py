"""Post-processes the raw cargo/maturin `.so` before it ships inside the
wheel: sets a dual RPATH and verifies the resulting NEEDED list.

RPATH has two entries:
  1. `$ORIGIN` — for runtimes that bundle `libpython*.so` next to the
     extension in a flat directory (e.g. python-for-android/Kivy, Flet).
  2. The real Termux prefix — where Termux actually installs libpython.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

TERMUX_LIB_DIR = "/data/data/com.termux/files/usr/lib"
RPATH_ENTRIES = ["$ORIGIN", TERMUX_LIB_DIR]

# Our substitute for auditwheel's manylinux policy — there is no Android
# equivalent, so we hand-maintain this allow-list of what bionic + the
# NDK sysroot are known to provide on every API level we target.
_ALLOWED_NEEDED_RE = re.compile(
    r"^(libpython3\.\d+\.so|libc\.so|libm\.so|libdl\.so|liblog\.so|libz\.so)$"
)


def set_rpath(so_path: Path, rpaths: list[str] = RPATH_ENTRIES) -> None:
    if shutil.which("patchelf") is None:
        raise RuntimeError("patchelf not found on PATH")
    subprocess.run(
        ["patchelf", "--set-rpath", ":".join(rpaths), str(so_path)],
        check=True,
    )


_NEEDED_RE = re.compile(r"\(NEEDED\)\s+Shared library: \[(.+?)\]")


def parse_needed(readelf_output: str) -> list[str]:
    """Pure parsing, split out for testability without a real ELF file."""
    return _NEEDED_RE.findall(readelf_output)


def needed_libraries(so_path: Path) -> list[str]:
    result = subprocess.run(
        ["readelf", "-d", str(so_path)], check=True, capture_output=True, text=True
    )
    return parse_needed(result.stdout)


def check_needed(needed: list[str]) -> list[str]:
    """Returns the disallowed NEEDED entries (empty list means OK)."""
    return [lib for lib in needed if not _ALLOWED_NEEDED_RE.match(lib)]


def verify_needed(so_path: Path) -> None:
    needed = needed_libraries(so_path)
    bad = check_needed(needed)
    if bad:
        raise RuntimeError(f"{so_path} links against unexpected libraries: {bad}. Full NEEDED: {needed}")
    if not any(lib.startswith("libpython3.") for lib in needed):
        raise RuntimeError(f"{so_path} does not link against libpython3.*, found: {needed}")


def patch_extension_in_wheel(wheel_path: Path, *, verify: bool = True) -> None:
    """Rewrites the wheel in place: sets RPATH on its `.so`, verifies
    NEEDED, re-zips. Uses a temp dir since patchelf needs a real file on
    disk, not a zip member."""
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
            zf.extractall(tmp_path)

        so_files = list(tmp_path.rglob("*.so"))
        if not so_files:
            raise FileNotFoundError(f"No .so found inside {wheel_path}")

        for so_path in so_files:
            set_rpath(so_path)
            if verify:
                verify_needed(so_path)

        wheel_path.unlink()
        with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in names:
                zf.write(tmp_path / name, arcname=name)
