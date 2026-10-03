"""Checks whether pydantic-core has published a new version upstream
that this repo has not yet built, driving the scheduled check_upstream.yml
workflow. Also derives whether a given git ref represents a releasable
version, used by build_wheels.yml to decide automatically whether a run
should publish a GitHub Release.

pydantic-core's source and release process moved from its own dedicated
repo (pydantic/pydantic-core, last tag there: v2.41.5) into the
pydantic/pydantic monorepo, where it now lives as a subdirectory
(confirmed: pydantic-core/Cargo.toml exists on pydantic/pydantic's
default branch). Its pyproject.toml declares `dynamic = ["version"]`
with maturin as the build backend, meaning the actual released version
of the `pydantic_core` package is read directly from
pydantic-core/Cargo.toml's `[package] version` field — not from any git
tag or release name. The monorepo also has its own, *independent*
version-number track for the `pydantic` package itself (its "Prepare
release vX.Y.Z" commits reference pydantic's version, not
pydantic-core's), so there is no reliable tag or commit-message
convention to key off of for pydantic-core specifically. Given that,
this module resolves a PyPI version straight to the exact upstream
commit by walking pydantic-core/Cargo.toml's own commit history and
reading its content at each commit — the only approach that doesn't
depend on guessing a naming convention.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Iterator

import requests
from packaging.version import InvalidVersion, Version

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
UPSTREAM_REPO_DEFAULT = "pydantic/pydantic"
# Confirmed via `gh api repos/pydantic/pydantic/git/trees/main?recursive=1`.
UPSTREAM_CARGO_TOML_PATH_DEFAULT = "pydantic-core/Cargo.toml"

# Matches a (possibly "v"-prefixed) version number anywhere a manually
# supplied ref might end with one, e.g. "v2.49.0" or "pydantic-core-v2.49.0".
# Not used to resolve the *automated* flow's ref (that's always a raw
# commit SHA, which never looks like this) — only as a convenience for a
# human manually dispatching the workflow against a literal version tag.
_VERSION_SUFFIX_RE = re.compile(r"v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)?)$")

_PACKAGE_SECTION_RE = re.compile(r"(?ms)^\[package\]\s*\n(.*?)(?=^\[|\Z)")
_VERSION_LINE_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')


def _has_published_wheel(files: list[dict]) -> bool:
    return any(
        f.get("filename", "").endswith(".whl") and not f.get("yanked", False)
        for f in files
    )


def list_stable_pypi_versions(package_name: str) -> list[str]:
    """Every version of `package_name` on PyPI that is a final (non-
    prerelease, non-dev) release AND has at least one real, non-yanked
    wheel file uploaded — newest first.

    Deliberately does NOT trust the top-level `info.version` field of
    PyPI's JSON API response as "the" latest version, and does NOT
    consider a version "ready" just because *some* file exists for it —
    confirmed in production: pydantic-core 2.49.0 appeared on PyPI with
    info.version pointing at it while only an sdist had been uploaded,
    zero wheels. Requiring a real, non-yanked wheel file is a much
    better proxy for "this release is actually complete".
    """
    resp = requests.get(PYPI_JSON_URL.format(package=package_name), timeout=30)
    resp.raise_for_status()
    releases = resp.json().get("releases", {})

    candidates: list[tuple[Version, str]] = []
    for version_str, files in releases.items():
        if not _has_published_wheel(files):
            continue
        try:
            parsed = Version(version_str)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        candidates.append((parsed, version_str))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [version_str for _, version_str in candidates]


def release_tag_for_version(version: str) -> str:
    """Tag used for *this* repo's own release (not upstream's) — our own
    naming convention, independent of whatever upstream does."""
    return f"v{version}"


def extract_cargo_version(cargo_toml_text: str) -> str | None:
    """Reads the `[package] version` field from a Cargo.toml's text.

    Deliberately scoped to the [package] section only (not a bare
    "^version = ..." search over the whole file): Cargo.toml also
    contains dependency version pins (e.g. `regex = "1.12.3"`) and
    inline tables with their own "version" keys (e.g.
    `pyo3 = { version = "0.29.2", ... }`), though none of those happen
    to collide with a line-anchored "version = ..." pattern in the real
    file at time of writing — scoping to [package] makes that
    non-collision a guarantee rather than a coincidence.
    """
    section_match = _PACKAGE_SECTION_RE.search(cargo_toml_text)
    search_space = section_match.group(1) if section_match else cargo_toml_text
    match = _VERSION_LINE_RE.search(search_space)
    return match.group(1) if match else None


def iter_path_commits(
    upstream_repo: str, path: str, max_pages: int = 10, per_page: int = 100
) -> Iterator[dict]:
    """Yields commits touching `path` in `upstream_repo`, newest first,
    fetched one page at a time so resolve_commit_for_version() can stop
    as soon as it finds a match instead of always paying for the file's
    entire commit history (which, for a long-lived file like Cargo.toml,
    can be hundreds of commits)."""
    for page in range(1, max_pages + 1):
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{upstream_repo}/commits",
                "-f",
                f"path={path}",
                "-f",
                f"per_page={per_page}",
                "-f",
                f"page={page}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gh api failed listing commits for {path} in {upstream_repo}: {result.stderr}"
            )
        batch = json.loads(result.stdout)
        if not batch:
            return
        yield from batch
        if len(batch) < per_page:
            return


def fetch_file_at_commit(upstream_repo: str, path: str, ref: str) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{upstream_repo}/contents/{path}", "-f", f"ref={ref}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh api failed fetching {path}@{ref} in {upstream_repo}: {result.stderr}"
        )
    payload = json.loads(result.stdout)
    return base64.b64decode(payload["content"]).decode("utf-8")


def resolve_commit_for_version(upstream_repo: str, cargo_toml_path: str, version: str) -> str | None:
    """The exact upstream commit SHA at which pydantic-core/Cargo.toml's
    `[package] version` reads `version` — or None if no commit touching
    that file ever set it to exactly that value (within the pages
    scanned). This is a real, checkout-able git ref, unlike a tag name
    that may not exist."""
    for commit in iter_path_commits(upstream_repo, cargo_toml_path):
        sha = commit.get("sha")
        if not sha:
            continue
        try:
            content = fetch_file_at_commit(upstream_repo, cargo_toml_path, sha)
        except RuntimeError:
            continue
        if extract_cargo_version(content) == version:
            return sha
    return None


def version_from_ref(ref: str) -> str | None:
    """Convenience for a human manually dispatching the workflow with a
    literal version-looking ref (e.g. "v2.49.0"). Returns None for
    anything that doesn't end in a version number — in particular, for
    the raw commit SHAs the automated check_upstream.yml flow passes,
    which is why that flow passes the version explicitly instead of
    relying on this function (see build_wheels.yml's `release_version`
    input)."""
    match = _VERSION_SUFFIX_RE.search(ref.strip())
    return match.group(1) if match else None


def release_exists(repo: str, tag: str) -> bool:
    """True if `repo` already has a GitHub release tagged `tag`."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@dataclass(frozen=True)
class UpdateCheck:
    package_version: str | None  # None => nothing wheel-complete on PyPI has a matching upstream commit
    release_tag: str | None
    upstream_ref: str | None  # a commit SHA, not a tag
    already_released: bool

    @property
    def should_build(self) -> bool:
        return self.upstream_ref is not None and not self.already_released


def check_for_update(
    repo: str,
    package_name: str,
    upstream_repo: str = UPSTREAM_REPO_DEFAULT,
    cargo_toml_path: str = UPSTREAM_CARGO_TOML_PATH_DEFAULT,
) -> UpdateCheck:
    """Walks PyPI's wheel-complete stable versions newest-first and
    returns the first one for which pydantic-core/Cargo.toml's own
    commit history actually has a matching `version = "..."` — rather
    than trusting PyPI's `info.version` pointer (which can reference an
    incomplete release) or guessing a tag/release naming convention
    (which broke twice already: the dedicated repo's tags stopped at
    v2.41.5, and the monorepo has no pydantic-core-specific tags or
    release-name convention at all).
    """
    for version in list_stable_pypi_versions(package_name):
        upstream_ref = resolve_commit_for_version(upstream_repo, cargo_toml_path, version)
        if upstream_ref is None:
            continue
        tag = release_tag_for_version(version)
        return UpdateCheck(
            package_version=version,
            release_tag=tag,
            upstream_ref=upstream_ref,
            already_released=release_exists(repo, tag),
        )

    return UpdateCheck(package_version=None, release_tag=None, upstream_ref=None, already_released=False)
