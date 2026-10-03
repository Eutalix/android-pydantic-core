from pathlib import Path

from ci_tool.arches import get
from ci_tool.build import BuildConfig, ndk_clang_target, retag_wheel


def test_ndk_clang_target_arm_uses_armv7a():
    assert ndk_clang_target(get("armeabi-v7a"), 24) == "armv7a-linux-androideabi24"


def test_ndk_clang_target_matches_rust_target_otherwise():
    assert ndk_clang_target(get("arm64-v8a"), 24) == "aarch64-linux-android24"


def test_retag_wheel_rewrites_platform_component(tmp_path):
    src = tmp_path / "pydantic_core-2.49.0-cp314-cp314-linux_aarch64.whl"
    src.write_bytes(b"fake")
    cfg = BuildConfig(
        arch=get("arm64-v8a"),
        python_version="3.14",
        android_api_level=24,
        ndk_home=Path("/ndk"),
        libpython_dir=tmp_path,
        manifest_path=tmp_path / "Cargo.toml",
        out_dir=tmp_path,
    )
    out = retag_wheel(src, cfg)
    assert out.name == "pydantic_core-2.49.0-cp314-cp314-android_24_arm64_v8a.whl"


def test_build_config_absolutizes_relative_paths(tmp_path, monkeypatch):
    # cargo runs the linker from the package root, not necessarily this
    # process's cwd — BuildConfig must never hand out a relative path.
    monkeypatch.chdir(tmp_path)
    cfg = BuildConfig(
        arch=get("arm64-v8a"),
        python_version="3.14",
        android_api_level=24,
        ndk_home=Path("relative-ndk"),
        libpython_dir=Path(".ci-cache/extracted/aarch64/3.14"),
        manifest_path=Path("pydantic-core/Cargo.toml"),
        out_dir=Path("dist"),
    )
    assert cfg.ndk_home.is_absolute()
    assert cfg.libpython_dir.is_absolute()
    assert cfg.libpython_dir == (tmp_path / ".ci-cache/extracted/aarch64/3.14")
    assert cfg.manifest_path.is_absolute()
    assert cfg.out_dir.is_absolute()
