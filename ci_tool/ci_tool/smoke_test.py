"""Smoke-tests a freshly built wheel against the real, official Termux
environment — `termux/termux-docker` — rather than hand-assembling a
bionic rootfs under qemu-user, which would require independently
replicating details (bootstrap `SYMLINKS.txt`, the `aosp-utils`/
`libandroid-stub` packages that provide `/system/bin/linker64`, the
`/system` symlink layout) that termux-docker already maintains and tests.

`termux/termux-docker` image tags are the exact strings "aarch64", "arm",
"x86_64", "i686" — identical to `Arch.termux_arch`.

No QEMU/binfmt setup is used: 32-bit arm/x86 containers run natively in
hardware compat mode on GitHub's arm64/x86_64 runners respectively (see
build_wheels.yml's runner choice per architecture).

The termux-docker image is built `FROM scratch` with only the Termux
rootfs copied in — there is no `/tmp` at the container root (Termux's own
TMPDIR is `$PREFIX/tmp`). All command output inside the container is
therefore captured into shell variables, never redirected to a file path.

The wheel is installed with its real dependency tree resolved from PyPI
(not `--no-deps`): pydantic-core requires `typing_extensions` at import
time, not merely as optional metadata. This cannot substitute a
different pydantic-core, since pip is given a literal local file path for
the package itself — only its pure-Python dependencies are resolved from
the index. Native/ABI correctness is independently verified by
`patch.py`'s NEEDED/RPATH checks at build time.

Termux's apt repo generally carries only the *current* `python` package
version. If the pinned `termux_python_pkg_version` recorded at build time
is no longer installable by the time the smoke test runs, that is a SKIP
(exit code 77), not a failure — a known, explicit coverage gap rather
than a false pass or an unrelated CI failure.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .arches import Arch

SKIP_EXIT_CODE = 77


def docker_image(arch: Arch) -> str:
    return f"termux/termux-docker:{arch.termux_arch}"


def in_container_script(
    *,
    wheel_filename: str,
    termux_python_pkg_version: str,
    expected_pydantic_core_version: str,
) -> str:
    """Builds the shell script run inside the termux-docker container.
    Pure string construction, split out for testability without Docker.
    """
    wheel_path_in_container = f"/mnt/wheel/{wheel_filename}"
    pinned = f"python={shlex.quote(termux_python_pkg_version)}"

    return "\n".join(
        [
            "set -u",
            "apt update -qq",
            f'apt_output=$(apt-get install -y -qq --allow-downgrades {pinned} 2>&1)',
            "apt_status=$?",
            'if [ "$apt_status" -ne 0 ]; then',
            '  if echo "$apt_output" | grep -qiE "unable to locate|no installation candidate|was not found"; then',
            f'    echo "SKIP: Termux apt no longer offers python {termux_python_pkg_version}; cannot smoke-test this wheel today." >&2',
            f"    exit {SKIP_EXIT_CODE}",
            "  fi",
            '  echo "$apt_output" >&2',
            "  exit 1",
            "fi",
            "set -e",
            "python3 -m pip --version >/dev/null 2>&1 || python3 -m ensurepip --upgrade",
            f"python3 -m pip install {shlex.quote(wheel_path_in_container)}",
            "python3 -c \"import pydantic_core; "
            f"assert pydantic_core.__version__ == {expected_pydantic_core_version!r}, pydantic_core.__version__; "
            "print('pydantic_core', pydantic_core.__version__, 'OK')\"",
        ]
    )


def build_docker_run_command(
    *,
    arch: Arch,
    dist_dir: Path,
    wheel_filename: str,
    termux_python_pkg_version: str,
    expected_pydantic_core_version: str,
) -> list[str]:
    script = in_container_script(
        wheel_filename=wheel_filename,
        termux_python_pkg_version=termux_python_pkg_version,
        expected_pydantic_core_version=expected_pydantic_core_version,
    )
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{dist_dir.resolve()}:/mnt/wheel:ro",
        docker_image(arch),
        "bash",
        "-c",
        script,
    ]


class SmokeTestSkipped(Exception):
    """Raised when the pinned Termux python version is no longer
    installable — a known coverage gap, not a build defect."""


def run_smoke_test(
    *,
    arch: Arch,
    dist_dir: Path,
    wheel_filename: str,
    termux_python_pkg_version: str,
    expected_pydantic_core_version: str,
) -> None:
    cmd = build_docker_run_command(
        arch=arch,
        dist_dir=dist_dir,
        wheel_filename=wheel_filename,
        termux_python_pkg_version=termux_python_pkg_version,
        expected_pydantic_core_version=expected_pydantic_core_version,
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == SKIP_EXIT_CODE:
        raise SmokeTestSkipped(result.stderr.strip() or "smoke test skipped")
    if result.returncode != 0:
        raise RuntimeError(
            f"Smoke test failed for {wheel_filename} ({arch.android_abi}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
