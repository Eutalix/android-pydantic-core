import pytest

from ci_tool.arches import ARCHES, all_abis, get


def test_all_abis_have_unique_rust_targets():
    targets = [a.rust_target for a in ARCHES.values()]
    assert len(targets) == len(set(targets))


def test_unknown_arch_raises():
    with pytest.raises(ValueError):
        get("mips-fantasy")


@pytest.mark.parametrize("abi", all_abis())
def test_arch_fields_nonempty(abi):
    arch = get(abi)
    assert arch.rust_target
    assert arch.termux_arch
    assert arch.ndk_lib_arch
    assert arch.ndk_clang_triple
    assert arch.android_abi == abi
