from ci_tool.arches import all_abis, get
from ci_tool.wheel_tags import android_abi_tag, normalize, wheel_platform_tag


def test_normalize():
    assert normalize("arm64-v8a") == "arm64_v8a"
    assert normalize("a.b c") == "a_b_c"


def test_android_abi_tag_matches_confirmed_device_value():
    arch = get("arm64-v8a")
    assert android_abi_tag(arch) == "arm64_v8a"


def test_wheel_platform_tag_matches_device_confirmed_format():
    arch = get("arm64-v8a")
    assert wheel_platform_tag(arch, 24) == "android_24_arm64_v8a"


def test_all_arches_produce_lowercase_valid_tags():
    for abi in all_abis():
        tag = wheel_platform_tag(get(abi), 24)
        assert tag.startswith("android_24_")
        assert " " not in tag
        assert tag == tag.lower()
