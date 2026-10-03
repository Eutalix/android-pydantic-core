from pathlib import Path

from ci_tool.arches import all_abis, get
from ci_tool.smoke_test import (
    SKIP_EXIT_CODE,
    build_docker_run_command,
    docker_image,
    in_container_script,
)


def test_docker_image_matches_confirmed_readme_tags():
    expected = {
        "arm64-v8a": "termux/termux-docker:aarch64",
        "armeabi-v7a": "termux/termux-docker:arm",
        "x86_64": "termux/termux-docker:x86_64",
        "x86": "termux/termux-docker:i686",
    }
    for abi in all_abis():
        assert docker_image(get(abi)) == expected[abi]


def test_in_container_script_pins_exact_termux_python_version():
    script = in_container_script(
        wheel_filename="pydantic_core-2.49.0-cp314-cp314-android_24_arm64_v8a.whl",
        termux_python_pkg_version="3.14.7-1",
        expected_pydantic_core_version="2.49.0",
    )
    assert "python=3.14.7-1" in script
    assert "/mnt/wheel/pydantic_core-2.49.0-cp314-cp314-android_24_arm64_v8a.whl" in script
    assert "2.49.0" in script
    assert str(SKIP_EXIT_CODE) in script


def test_in_container_script_does_not_use_no_deps():
    # pydantic-core requires typing_extensions at import time, so
    # dependencies must be resolved from PyPI normally.
    script = in_container_script(
        wheel_filename="x.whl",
        termux_python_pkg_version="3.14.7-1",
        expected_pydantic_core_version="1.0.0",
    )
    assert "--no-deps" not in script
    assert "--no-index" not in script


def test_in_container_script_has_skip_path_on_missing_apt_version():
    script = in_container_script(
        wheel_filename="x.whl",
        termux_python_pkg_version="9.9.9-1",
        expected_pydantic_core_version="1.0.0",
    )
    assert "SKIP:" in script
    assert f"exit {SKIP_EXIT_CODE}" in script


def test_in_container_script_never_redirects_to_a_file():
    # termux-docker is built FROM scratch with no /tmp at the container
    # root; output must be captured into a shell variable instead.
    script = in_container_script(
        wheel_filename="x.whl",
        termux_python_pkg_version="3.14.7-1",
        expected_pydantic_core_version="1.0.0",
    )
    assert "/tmp/" not in script
    assert "apt_output=$(" in script


def test_build_docker_run_command_mounts_dist_dir_readonly(tmp_path):
    cmd = build_docker_run_command(
        arch=get("x86_64"),
        dist_dir=tmp_path,
        wheel_filename="x.whl",
        termux_python_pkg_version="3.14.7-1",
        expected_pydantic_core_version="1.0.0",
    )
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert f"{Path(tmp_path).resolve()}:/mnt/wheel:ro" in cmd
    assert "termux/termux-docker:x86_64" in cmd
