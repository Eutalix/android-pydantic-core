from unittest.mock import MagicMock, patch

import pytest

from ci_tool.upstream import (
    check_for_update,
    extract_tag_names,
    find_matching_tag,
    list_stable_pypi_versions,
    normalize_tag,
    release_tag_for_version,
    version_from_ref,
)


def _fake_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


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


def test_extract_tag_names_pulls_name_field():
    assert extract_tag_names([{"name": "v2.41.5"}, {"name": "v2.40.0"}]) == ["v2.41.5", "v2.40.0"]


def test_find_matching_tag_returns_real_tag_name():
    tags = ["v2.48.0", "v2.49.0", "v2.50.0-beta"]
    assert find_matching_tag(tags, "2.49.0") == "v2.49.0"


def test_find_matching_tag_works_without_v_prefix():
    assert find_matching_tag(["2.48.0", "2.49.0"], "2.49.0") == "2.49.0"


def test_find_matching_tag_returns_none_when_absent():
    assert find_matching_tag(["v2.40.0", "v2.41.5"], "2.49.0") is None


def test_list_stable_pypi_versions_requires_a_real_wheel_file():
    # Regression test for a confirmed-real production case: pydantic-core
    # 2.49.0 existed on PyPI with only an sdist uploaded (no .whl files
    # at all) — not yanked, not a prerelease, just incomplete. This must
    # be excluded even though nothing about it is formally "yanked".
    payload = {
        "releases": {
            "2.40.0": [{"filename": "pydantic_core-2.40.0-cp312-cp312-x.whl", "yanked": False}],
            "2.41.5": [{"filename": "pydantic_core-2.41.5-cp312-cp312-x.whl", "yanked": False}],
            "2.49.0": [{"filename": "pydantic_core-2.49.0.tar.gz", "yanked": False}],  # sdist only
            "2.49.0b1": [{"filename": "pydantic_core-2.49.0b1-cp312-cp312-x.whl", "yanked": False}],  # prerelease
            "2.50.0.dev1": [{"filename": "pydantic_core-2.50.0.dev1-cp312-cp312-x.whl", "yanked": False}],
            "2.42.0": [{"filename": "pydantic_core-2.42.0-cp312-cp312-x.whl", "yanked": True}],  # wheel yanked
            "2.43.0": [],  # registered, nothing ever uploaded
        }
    }
    with patch("ci_tool.upstream.requests.get", return_value=_fake_response(payload)):
        versions = list_stable_pypi_versions("pydantic-core")

    assert versions == ["2.41.5", "2.40.0"]


def test_check_for_update_falls_through_to_newest_wheel_complete_tagged_version():
    # End-to-end version of the same production scenario: 2.49.0 is
    # PyPI's "latest" by version number, but it's the sdist-only release
    # above (so list_stable_pypi_versions already excludes it) — this
    # just confirms check_for_update() correctly uses whatever
    # list_stable_pypi_versions returns and keeps walking until it finds
    # a version upstream actually tagged.
    fake_tags = [{"name": "v2.41.5"}, {"name": "v2.40.0"}]
    with patch("ci_tool.upstream.fetch_upstream_tags", return_value=fake_tags), patch(
        "ci_tool.upstream.list_stable_pypi_versions",
        return_value=["2.41.5", "2.40.0"],
    ), patch("ci_tool.upstream.release_exists", return_value=False):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.package_version == "2.41.5"
    assert result.upstream_ref == "v2.41.5"
    assert result.should_build is True


def test_check_for_update_skips_already_released_version():
    fake_tags = [{"name": "v2.41.5"}]
    with patch("ci_tool.upstream.fetch_upstream_tags", return_value=fake_tags), patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.41.5"]
    ), patch("ci_tool.upstream.release_exists", return_value=True):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.should_build is False


def test_check_for_update_reports_nothing_buildable_when_no_version_is_tagged():
    fake_tags = [{"name": "v1.0.0"}]
    with patch("ci_tool.upstream.fetch_upstream_tags", return_value=fake_tags), patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.49.0", "2.41.5"]
    ), patch("ci_tool.upstream.release_exists") as mock_release_exists:
        result = check_for_update("owner/repo", "pydantic-core")

    mock_release_exists.assert_not_called()
    assert result.should_build is False
    assert result.package_version is None


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
