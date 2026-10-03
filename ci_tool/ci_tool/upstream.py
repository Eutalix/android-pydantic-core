"""Checks whether pydantic-core has published a new version upstream
that this repo has not yet built, driving the scheduled check_upstream.yml
workflow. Also derives whether a given git ref represents a releasable
version, used by build_wheels.yml to decide automatically whether a run
should publish a GitHub Release.

Unlike pypi_index.py (which reads *this* repo's own GitHub Releases to
build the PEP 503 index), this module reads PyPI — the project being
repackaged — and cross-references this repo's own releases to decide
whether a new build run should be kicked off.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

import requests
from packaging.version import InvalidVersion, Version

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
UPSTREAM_REPO_DEFAULT = "pydantic/pydantic-core"

# Matches an optional "v" prefix followed by a dotted numeric version,
# with an optional pre-release/build suffix (e.g. "v2.49.0", "2.49.0",
# "v2.49.0rc1") — but NOT branch names ("main"), arbitrary branch
# slugs ("fix-xyz"), or raw commit SHAs (no dots).
_VERSION_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)?)$")


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
    consider a version "ready" just because *some* file exists for it.
    Confirmed in production: pydantic-core 2.49.0 was visible on PyPI
    with info.version pointing at it, yet it had only a source
    distribution (sdist) uploaded — zero wheels — and correspondingly
    no matching git tag existed yet in the upstream repo. pydantic-core
    is a Rust/PyO3 extension built via CI from a tagged commit, so an
    sdist-only release is a strong, directly observable signal that
    upstream's own release pipeline hasn't finished publishing that
    version yet. Requiring a real wheel file is a much better proxy for
    "this release is actually complete" than merely checking
    prerelease/yanked status, and it's cheap to verify directly from
    this same API response.
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
    """Tag used for *this* repo's own release (not upstream's)."""
    return f"v{version}"


def normalize_tag(tag: str) -> str:
    """Strips an optional leading 'v'/'V' so a git tag can be compared
    against a bare PyPI version string (e.g. "v2.49.0" -> "2.49.0")."""
    return tag[1:] if tag[:1] in ("v", "V") else tag


def extract_tag_names(tags_json: list[dict]) -> list[str]:
    """Pure parsing, split out for testability without a real `gh` call."""
    return [t["name"] for t in tags_json if "name" in t]


def find_matching_tag(tag_names: list[str], version: str) -> str | None:
    """Returns the real tag name matching `version`, or None if upstream
    has no such tag (yet, or ever — e.g. a withdrawn/incomplete PyPI
    release, as seen in production — see list_stable_pypi_versions)."""
    for name in tag_names:
        if normalize_tag(name) == version:
            return name
    return None


def fetch_upstream_tags(upstream_repo: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{upstream_repo}/tags", "--paginate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed listing tags for {upstream_repo}: {result.stderr}")
    return json.loads(result.stdout)


def version_from_ref(ref: str) -> str | None:
    """If `ref` looks like a version tag, returns the bare version
    string (without any leading "v"); otherwise returns None.

    Used by build_wheels.yml to decide, automatically and without a
    second manually-synchronized input, whether a given run should
    publish a GitHub Release.
    """
    match = _VERSION_TAG_RE.match(ref.strip())
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
    package_version: str | None  # None => nothing both wheel-complete on PyPI and tagged upstream
    release_tag: str | None
    upstream_ref: str | None
    already_released: bool

    @property
    def should_build(self) -> bool:
        return self.upstream_ref is not None and not self.already_released


def check_for_update(
    repo: str,
    package_name: str,
    upstream_repo: str = UPSTREAM_REPO_DEFAULT,
) -> UpdateCheck:
    """Walks PyPI's wheel-complete stable versions newest-first and
    returns the first one upstream has actually tagged — rather than
    rigidly chasing whatever PyPI's `info.version` claims is "latest"
    even when that specific version isn't fully published yet. This
    makes the scheduled check self-healing: it always finds the newest
    version that is genuinely buildable today.
    """
    tag_names = extract_tag_names(fetch_upstream_tags(upstream_repo))

    for version in list_stable_pypi_versions(package_name):
        upstream_ref = find_matching_tag(tag_names, version)
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
