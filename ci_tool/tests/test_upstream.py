from unittest.mock import MagicMock, patch

import pytest

from ci_tool.upstream import (
    UPSTREAM_REPO_DEFAULT,
    check_for_update,
    find_matching_release,
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


def test_default_upstream_repo_is_the_monorepo():
    # Pins a user-confirmed fact: pydantic-core's source/releases moved
    # from the dedicated pydantic/pydantic-core repo (last tag v2.41.5)
    # into the pydantic/pydantic monorepo.
    assert UPSTREAM_REPO_DEFAULT == "pydantic/pydantic"


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


def test_find_matching_release_dedicated_repo_uses_bare_version():
    releases = [{"tag_name": "v2.41.5", "draft": False}]
    result = find_matching_release(releases, "pydantic/pydantic-core", "pydantic-core", "2.41.5")
    assert result == "v2.41.5"


def test_find_matching_release_monorepo_requires_package_name_in_tag():
    releases = [
        {"tag_name": "pydantic-core-v2.46.3", "name": "pydantic-core v2.46.3", "draft": False},
    ]
    result = find_matching_release(releases, "pydantic/pydantic", "pydantic-core", "2.46.3")
    assert result == "pydantic-core-v2.46.3"


def test_find_matching_release_monorepo_ignores_sibling_packages_bare_tag():
    # Regression test for the real production scenario: in a monorepo, a
    # bare "v2.46.3" tag most likely belongs to the main `pydantic`
    # package itself, not pydantic-core — must not be matched just
    # because the version number happens to coincide.
    releases = [{"tag_name": "v2.46.3", "name": None, "draft": False}]
    result = find_matching_release(releases, "pydantic/pydantic", "pydantic-core", "2.46.3")
    assert result is None


def test_find_matching_release_ignores_drafts_and_prereleases():
    releases = [
        {"tag_name": "pydantic-core-v2.46.3", "name": "pydantic-core v2.46.3", "draft": True},
        {"tag_name": "pydantic-core-v2.46.3", "name": "pydantic-core v2.46.3", "prerelease": True},
    ]
    result = find_matching_release(releases, "pydantic/pydantic", "pydantic-core", "2.46.3")
    assert result is None


def test_find_matching_release_returns_none_when_absent():
    releases = [{"tag_name": "pydantic-core-v2.40.0", "name": "pydantic-core v2.40.0", "draft": False}]
    result = find_matching_release(releases, "pydantic/pydantic", "pydantic-core", "2.46.3")
    assert result is None


def test_list_stable_pypi_versions_requires_a_real_wheel_file():
    payload = {
        "releases": {
            "2.40.0": [{"filename": "pydantic_core-2.40.0-cp312-cp312-x.whl", "yanked": False}],
            "2.46.3": [{"filename": "pydantic_core-2.46.3-cp312-cp312-x.whl", "yanked": False}],
            "2.49.0": [{"filename": "pydantic_core-2.49.0.tar.gz", "yanked": False}],  # sdist only
            "2.49.0b1": [{"filename": "pydantic_core-2.49.0b1-cp312-cp312-x.whl", "yanked": False}],
            "2.50.0.dev1": [{"filename": "pydantic_core-2.50.0.dev1-cp312-cp312-x.whl", "yanked": False}],
            "2.42.0": [{"filename": "pydantic_core-2.42.0-cp312-cp312-x.whl", "yanked": True}],
            "2.43.0": [],
        }
    }
    with patch("ci_tool.upstream.requests.get", return_value=_fake_response(payload)):
        versions = list_stable_pypi_versions("pydantic-core")

    assert versions == ["2.46.3", "2.40.0"]


def test_check_for_update_falls_through_to_newest_released_version():
    fake_releases = [
        {"tag_name": "pydantic-core-v2.46.3", "name": "pydantic-core v2.46.3", "draft": False},
    ]
    with patch("ci_tool.upstream.fetch_upstream_releases", return_value=fake_releases), patch(
        "ci_tool.upstream.list_stable_pypi_versions",
        return_value=["2.49.0", "2.46.3", "2.41.5"],
    ), patch("ci_tool.upstream.release_exists", return_value=False):
        result = check_for_update("owner/repo", "pydantic-core", upstream_repo="pydantic/pydantic")

    assert result.package_version == "2.46.3"
    assert result.upstream_ref == "pydantic-core-v2.46.3"
    assert result.should_build is True


def test_check_for_update_skips_already_released_version():
    fake_releases = [{"tag_name": "pydantic-core-v2.46.3", "name": "pydantic-core v2.46.3", "draft": False}]
    with patch("ci_tool.upstream.fetch_upstream_releases", return_value=fake_releases), patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.46.3"]
    ), patch("ci_tool.upstream.release_exists", return_value=True):
        result = check_for_update("owner/repo", "pydantic-core", upstream_repo="pydantic/pydantic")

    assert result.should_build is False


def test_check_for_update_reports_nothing_buildable_when_no_version_is_released():
    fake_releases = [{"tag_name": "v1.0.0", "name": None, "draft": False}]
    with patch("ci_tool.upstream.fetch_upstream_releases", return_value=fake_releases), patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.49.0", "2.46.3"]
    ), patch("ci_tool.upstream.release_exists") as mock_release_exists:
        result = check_for_update("owner/repo", "pydantic-core", upstream_repo="pydantic/pydantic")

    mock_release_exists.assert_not_called()
    assert result.should_build is False
    assert result.package_version is None


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("v2.49.0", "2.49.0"),
        ("2.49.0", "2.49.0"),
        ("v2.49.0rc1", "2.49.0rc1"),
        ("pydantic-core-v2.46.3", "2.46.3"),  # monorepo-prefixed tag
        ("main", None),
        ("fix-something", None),
        ("a1b2c3d4", None),
    ],
)
def test_version_from_ref(ref, expected):
    assert version_from_ref(ref) == expected
