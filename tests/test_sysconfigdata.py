from ci_tool.arches import get
from ci_tool.sysconfigdata import render, write


def test_render_contains_confirmed_fields():
    out = render(python_version="3.14", arch=get("arm64-v8a"), android_api_level=24)
    assert "'SOABI': 'cpython-314'" in out
    assert "'VERSION': '3.14'" in out
    assert "'Py_ENABLE_SHARED': 1" in out
    assert "'LIBDIR': '/data/data/com.termux/files/usr/lib'" in out
    assert "'LDLIBRARY': 'libpython3.14.so'" in out
    assert "'SIZEOF_VOID_P': 8" in out
    assert "'ANDROID_API_LEVEL': 24" in out


def test_render_is_valid_python_syntax():
    out = render(python_version="3.14", arch=get("x86"), android_api_level=24, pointer_width_bits=32)
    namespace: dict = {}
    exec(out, namespace)  # noqa: S102 — trusted, generated in-process
    assert namespace["build_time_vars"]["SIZEOF_VOID_P"] == 4


def test_write_creates_expected_filename(tmp_path):
    path = write(tmp_path, python_version="3.14", arch=get("arm64-v8a"), android_api_level=24)
    assert path.name == "_sysconfigdata__android_aarch64-linux-android.py"
    assert path.exists()


def test_ext_suffix_uses_ndk_triple_not_rustc_triple_for_armeabi_v7a():
    # armeabi-v7a is the one ABI where rust_target ("armv7-linux-androideabi")
    # and ndk_lib_arch ("arm-linux-androideabi") differ; EXT_SUFFIX must use
    # the latter to match what the real interpreter's import machinery expects.
    out = render(python_version="3.14", arch=get("armeabi-v7a"), android_api_level=24, pointer_width_bits=32)
    assert "'EXT_SUFFIX': '.cpython-314-arm-linux-androideabi.so'" in out
    assert "armv7" not in out


def test_ext_suffix_matches_rust_target_for_archs_where_they_coincide():
    for abi, expected_triple in [
        ("arm64-v8a", "aarch64-linux-android"),
        ("x86_64", "x86_64-linux-android"),
        ("x86", "i686-linux-android"),
    ]:
        arch = get(abi)
        assert arch.rust_target == arch.ndk_lib_arch == expected_triple
        out = render(python_version="3.14", arch=arch, android_api_level=24)
        assert f"'EXT_SUFFIX': '.cpython-314-{expected_triple}.so'" in out
