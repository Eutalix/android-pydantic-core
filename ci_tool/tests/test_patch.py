from ci_tool.patch import check_needed, parse_needed

SAMPLE_READELF = """
Dynamic section at offset 0x1000 contains 20 entries:
 0x0000000000000001 (NEEDED)             Shared library: [libpython3.14.so]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so]
 0x0000000000000001 (NEEDED)             Shared library: [liblog.so]
"""


def test_parse_needed_extracts_shared_libs():
    assert parse_needed(SAMPLE_READELF) == ["libpython3.14.so", "libc.so", "liblog.so"]


def test_check_needed_flags_unexpected_lib():
    bad = check_needed(["libpython3.14.so", "libssl.so"])
    assert bad == ["libssl.so"]


def test_check_needed_allows_known_set():
    assert check_needed(
        ["libpython3.14.so", "libc.so", "libm.so", "libdl.so", "liblog.so", "libz.so"]
    ) == []
