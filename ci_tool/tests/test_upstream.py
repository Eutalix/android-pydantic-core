from unittest.mock import patch

import pytest

from ci_tool.upstream import (
    check_for_update,
    find_matching_tag,
    normalize_tag,
    release_tag_for_version,
    resolve_upstream_ref,
    version_from_ref,
)


def test_release_tag_for_version_adds_v_prefix():
    assert release_tag_for_version("2.49.0") == "v2.49.0"


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v2.49.0", "2.49.0"),
        ("V2.49.0", "2.49.0"),
        ("2.49.0", "2.49.0"),
    ],
)
def test_normalize_tag_strips_leading_v(tag, expected):
    assert normalize_tag(tag) == expected


def test_find_matching_tag_returns_real_tag_name():
    tags = ["v2.48.0", "v2.49.0", "v2.50.0-beta"]
    assert find_matching_tag(tags, "2.49.0") == "v2.49.0"


def test_find_matching_tag_works_without_v_prefix():
    tags = ["2.48.0", "2.49.0"]
    assert find_matching_tag(tags, "2.49.0") == "2.49.0"


def test_find_matching_tag_raises_with_preview_when_absent():
    with pytest.raises(ValueError, match=r"2\.99\.0"):
        find_matching_tag(["v2.48.0", "v2.49.0"], "2.99.0")


def test_resolve_upstream_ref_queries_real_tags_not_a_guessed_template():
    # Regression test: a previous version of this module built the ref
    # from a hardcoded "v{version}" template without ever checking it
    # existed, which caused `actions/checkout` to fail in production
    # against a tag that didn't exist on the real pydantic-core repo.
    fake_tags_json = [{"name": "v2.48.0"}, {"name": "v2.49.0"}]
    with patch("ci_tool.upstream.fetch_upstream_tags", return_value=fake_tags_json):
        assert resolve_upstream_ref("pydantic/pydantic-core", "2.49.0") == "v2.49.0"


def test_check_for_update_flags_new_version_as_needing_build():
    with patch("ci_tool.upstream.latest_pypi_version", return_value="2.50.0"), patch(
        "ci_tool.upstream.resolve_upstream_ref", return_value="v2.50.0"
    ), patch("ci_tool.upstream.release_exists", return_value=False):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.package_version == "2.50.0"
    assert result.release_tag == "v2.50.0"
    assert result.upstream_ref == "v2.50.0"
    assert result.should_build is True


def test_check_for_update_skips_already_released_version():
    with patch("ci_tool.upstream.latest_pypi_version", return_value="2.49.0"), patch(
        "ci_tool.upstream.resolve_upstream_ref", return_value="v2.49.0"
    ), patch("ci_tool.upstream.release_exists", return_value=True):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.should_build is False


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("v2.49.0", "2.49.0"),
        ("2.49.0", "2.49.0"),
        ("v2.49.0rc1", "2.49.0rc1"),
        ("main", None),
        ("fix-something", None),
        ("a1b2c3d4", None),
    ],
)
def test_version_from_ref(ref, expected):
    assert version_from_ref(ref) == expected
