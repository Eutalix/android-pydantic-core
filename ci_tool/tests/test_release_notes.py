from ci_tool.release_notes import ReleaseContext, WheelBuildInfo, render


def test_render_includes_key_sections():
    ctx = ReleaseContext(
        pydantic_core_version="2.49.0",
        ndk_version="26.3.11579264",
        android_api_level=24,
        maturin_version="1.15.0",
        wheels=[
            WheelBuildInfo(
                android_abi="arm64-v8a",
                python_version="3.14",
                wheel_filename="pydantic_core-2.49.0-cp314-cp314-android_24_arm64_v8a.whl",
                termux_python_pkg_version="3.14.6-1",
            ),
        ],
    )
    body = render(ctx)
    assert "2.49.0" in body
    assert "arm64-v8a" in body
    assert "Termux `python` package `3.14.6-1`" in body
    assert "pydantic/pydantic/releases" in body
    assert "android_24_arm64_v8a.whl" in body
