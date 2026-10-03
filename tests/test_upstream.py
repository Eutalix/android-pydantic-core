from unittest.mock import patch

from ci_tool.upstream import (
    check_for_update,
    release_tag_for_version,
    upstream_ref_for_version,
)


def test_release_tag_for_version_adds_v_prefix():
    assert release_tag_for_version("2.49.0") == "v2.49.0"


def test_upstream_ref_for_version_uses_default_template():
    assert upstream_ref_for_version("2.49.0") == "v2.49.0"


def test_upstream_ref_for_version_honors_custom_template():
    assert upstream_ref_for_version("2.49.0", ref_template="release-{version}") == "release-2.49.0"


def test_check_for_update_flags_new_version_as_needing_build():
    with patch("ci_tool.upstream.latest_pypi_version", return_value="2.50.0"), patch(
        "ci_tool.upstream.release_exists", return_value=False
    ):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.package_version == "2.50.0"
    assert result.release_tag == "v2.50.0"
    assert result.should_build is True


def test_check_for_update_skips_already_released_version():
    with patch("ci_tool.upstream.latest_pypi_version", return_value="2.49.0"), patch(
        "ci_tool.upstream.release_exists", return_value=True
    ):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.should_build is False
