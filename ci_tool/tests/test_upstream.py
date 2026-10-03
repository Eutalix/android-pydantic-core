from unittest.mock import MagicMock, patch

import pytest

from ci_tool.upstream import (
    UPSTREAM_CARGO_TOML_PATH_DEFAULT,
    UPSTREAM_REPO_DEFAULT,
    check_for_update,
    extract_cargo_version,
    list_stable_pypi_versions,
    release_tag_for_version,
    resolve_commit_for_version,
    version_from_ref,
)

# A trimmed but faithful excerpt of the real pydantic-core/Cargo.toml on
# pydantic/pydantic's main branch, confirmed directly by the user. Used
# as a regression fixture: the [package] version must be found even
# though later sections contain inline tables with their own "version"
# keys for dependencies (pyo3, jiter, pyo3-build-config, ...).
REAL_CARGO_TOML_EXCERPT = """
[package]
name = "pydantic-core"
version = "2.49.0"
edition = "2024"
license = "MIT"
homepage = "https://github.com/pydantic/pydantic"
repository = "https://github.com/pydantic/pydantic.git"
readme = "README.md"
rust-version = "1.88"

[dependencies]
pyo3 = { version = "0.29.2", features = ["num-bigint", "py-clone", "smallvec"] }
regex = "1.12.3"
jiter = { version = "0.16.0", features = ["python"] }

[dev-dependencies]
pyo3 = { version = "0.29", features = ["auto-initialize"] }

[build-dependencies]
version_check = "0.9.5"
pyo3-build-config = { version = "0.29" }
"""


def _fake_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_default_upstream_location_is_pydantic_core_inside_the_monorepo():
    # Pins two user-confirmed facts: pydantic-core's source moved from
    # the dedicated pydantic/pydantic-core repo into pydantic/pydantic,
    # and it lives there at exactly this path.
    assert UPSTREAM_REPO_DEFAULT == "pydantic/pydantic"
    assert UPSTREAM_CARGO_TOML_PATH_DEFAULT == "pydantic-core/Cargo.toml"


def test_release_tag_for_version_adds_v_prefix():
    assert release_tag_for_version("2.49.0") == "v2.49.0"


def test_extract_cargo_version_reads_real_upstream_file_correctly():
    # Regression test built directly from the real file: must not be
    # confused by inline `version = "..."` keys inside [dependencies],
    # [dev-dependencies] or [build-dependencies] appearing after
    # [package].
    assert extract_cargo_version(REAL_CARGO_TOML_EXCERPT) == "2.49.0"


def test_extract_cargo_version_returns_none_without_a_package_section():
    assert extract_cargo_version('[dependencies]\nregex = "1.12.3"\n') is None


def test_list_stable_pypi_versions_requires_a_real_wheel_file():
    payload = {
        "releases": {
            "2.40.0": [{"filename": "pydantic_core-2.40.0-cp312-cp312-x.whl", "yanked": False}],
            "2.41.5": [{"filename": "pydantic_core-2.41.5-cp312-cp312-x.whl", "yanked": False}],
            "2.49.0": [{"filename": "pydantic_core-2.49.0.tar.gz", "yanked": False}],  # sdist only
            "2.49.0b1": [{"filename": "pydantic_core-2.49.0b1-cp312-cp312-x.whl", "yanked": False}],
            "2.50.0.dev1": [{"filename": "pydantic_core-2.50.0.dev1-cp312-cp312-x.whl", "yanked": False}],
            "2.42.0": [{"filename": "pydantic_core-2.42.0-cp312-cp312-x.whl", "yanked": True}],
            "2.43.0": [],
        }
    }
    with patch("ci_tool.upstream.requests.get", return_value=_fake_response(payload)):
        versions = list_stable_pypi_versions("pydantic-core")

    # Also implicitly guards against lexicographic-string sorting bugs
    # (e.g. "2.9.0" > "2.41.5" as plain strings) by using real
    # semantic-version comparison.
    assert versions == ["2.41.5", "2.40.0"]


def test_resolve_commit_for_version_walks_history_until_match():
    commits = [{"sha": "newest"}, {"sha": "middle"}, {"sha": "oldest"}]
    contents_by_sha = {
        "newest": '[package]\nversion = "2.49.0"\n',
        "middle": '[package]\nversion = "2.46.3"\n',
        "oldest": '[package]\nversion = "2.41.5"\n',
    }
    with patch("ci_tool.upstream.iter_path_commits", return_value=commits), patch(
        "ci_tool.upstream.fetch_file_at_commit",
        side_effect=lambda repo, path, ref: contents_by_sha[ref],
    ):
        result = resolve_commit_for_version("pydantic/pydantic", "pydantic-core/Cargo.toml", "2.46.3")

    assert result == "middle"


def test_resolve_commit_for_version_returns_none_when_never_found():
    commits = [{"sha": "a"}]
    with patch("ci_tool.upstream.iter_path_commits", return_value=commits), patch(
        "ci_tool.upstream.fetch_file_at_commit", return_value='[package]\nversion = "1.0.0"\n'
    ):
        result = resolve_commit_for_version("pydantic/pydantic", "pydantic-core/Cargo.toml", "9.9.9")

    assert result is None


def test_resolve_commit_for_version_skips_commits_where_the_file_cannot_be_fetched():
    commits = [{"sha": "deleted-at-this-point"}, {"sha": "good"}]
    with patch("ci_tool.upstream.iter_path_commits", return_value=commits), patch(
        "ci_tool.upstream.fetch_file_at_commit",
        side_effect=[RuntimeError("404"), '[package]\nversion = "2.41.5"\n'],
    ):
        result = resolve_commit_for_version("pydantic/pydantic", "pydantic-core/Cargo.toml", "2.41.5")

    assert result == "good"


def test_check_for_update_falls_through_to_newest_version_with_a_real_commit():
    with patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.49.0", "2.46.3", "2.41.5"]
    ), patch(
        "ci_tool.upstream.resolve_commit_for_version",
        side_effect=lambda repo, path, v: {"2.46.3": "abc123"}.get(v),
    ), patch("ci_tool.upstream.release_exists", return_value=False):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.package_version == "2.46.3"
    assert result.upstream_ref == "abc123"
    assert result.should_build is True


def test_check_for_update_skips_already_released_version():
    with patch("ci_tool.upstream.list_stable_pypi_versions", return_value=["2.41.5"]), patch(
        "ci_tool.upstream.resolve_commit_for_version", return_value="abc123"
    ), patch("ci_tool.upstream.release_exists", return_value=True):
        result = check_for_update("owner/repo", "pydantic-core")

    assert result.should_build is False


def test_check_for_update_reports_nothing_buildable_when_no_commit_matches():
    with patch(
        "ci_tool.upstream.list_stable_pypi_versions", return_value=["2.49.0", "2.46.3"]
    ), patch("ci_tool.upstream.resolve_commit_for_version", return_value=None), patch(
        "ci_tool.upstream.release_exists"
    ) as mock_release_exists:
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
        ("pydantic-core-v2.46.3", "2.46.3"),
        ("main", None),
        ("fix-something", None),
        ("a1b2c3d4", None),
    ],
)
def test_version_from_ref(ref, expected):
    assert version_from_ref(ref) == expected
