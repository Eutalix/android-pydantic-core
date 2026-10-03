import pytest

from ci_tool.termux import (
    latest_for_arch,
    list_available_versions,
    major_minor,
    matching_for_arch_and_version,
)

SAMPLE_INDEX_HTML = """
<a href="python_3.14.6-1_aarch64.deb">python_3.14.6-1_aarch64.deb</a>
<a href="python_3.14.6-1_arm.deb">python_3.14.6-1_arm.deb</a>
<a href="python_3.14.5-2_aarch64.deb">python_3.14.5-2_aarch64.deb</a>
<a href="python_3.13.0-1_x86_64.deb">python_3.13.0-1_x86_64.deb</a>
"""


def test_major_minor_strips_patch_and_revision():
    assert major_minor("3.14.6-1") == "3.14"
    assert major_minor("3.13.0-1") == "3.13"


def test_list_available_versions_parses_real_index_shape():
    packages = list_available_versions(SAMPLE_INDEX_HTML)
    assert len(packages) == 4
    assert {p.version for p in packages} == {"3.14.6-1", "3.14.5-2", "3.13.0-1"}


def test_latest_for_arch_picks_newest_regardless_of_minor():
    packages = list_available_versions(SAMPLE_INDEX_HTML)
    latest = latest_for_arch(packages, "aarch64")
    assert latest.version == "3.14.6-1"


def test_matching_for_arch_and_version_finds_exact_minor():
    packages = list_available_versions(SAMPLE_INDEX_HTML)
    pkg = matching_for_arch_and_version(packages, "aarch64", "3.14")
    assert pkg.version == "3.14.6-1"


def test_matching_for_arch_and_version_raises_with_available_list_when_absent():
    packages = list_available_versions(SAMPLE_INDEX_HTML)
    with pytest.raises(ValueError, match=r"3\.11.*aarch64"):
        matching_for_arch_and_version(packages, "aarch64", "3.11")


def test_matching_for_arch_and_version_error_lists_whats_actually_available():
    packages = list_available_versions(SAMPLE_INDEX_HTML)
    with pytest.raises(ValueError, match=r"3\.14"):
        matching_for_arch_and_version(packages, "aarch64", "3.11")
