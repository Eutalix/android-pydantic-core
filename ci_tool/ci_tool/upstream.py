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

# pydantic-core's source and release process moved from its own dedicated
# repo (pydantic/pydantic-core, last tag there: v2.41.5) into the
# pydantic/pydantic monorepo, where it now lives as a subdirectory and is
# released under its own tags *within* that repo — confirmed by finding
# a real GitHub release titled "pydantic-core v2.46.3" on
# pydantic/pydantic. Tags there can't just be bare "v{version}" like the
# old repo used, since the monorepo also tags releases of `pydantic`
# itself (and pydantic-settings, etc.) — so release names must be
# disambiguated by package. See find_matching_release().
UPSTREAM_REPO_DEFAULT = "pydantic/pydantic"

_VERSION_PATTERN = r"\d+\.\d+\.\d+(?:[A-Za-z0-9]*)?"
_VERSION_IN_STRING_RE = re.compile(_VERSION_PATTERN)
# Anchored to the END of the string only (not the whole string): used on
# literal, user/automation-provided git refs (pydantic_core_ref), which
# may now be package-prefixed (e.g. "pydantic-core-v2.46.3") rather than
# a bare version, now that releases live inside a shared monorepo.
_VERSION_SUFFIX_RE = re.compile(r"(" + _VERSION_PATTERN + r")$")

_SEPARATORS_RE = re.compile(r"[-_/\s]+")


def _normalize_for_match(s: str) -> str:
    """Collapses '-', '_', '/', whitespace and lowercases, so tag/release
    names using any separator convention can be compared against a
    package name using a different one (e.g. "pydantic-core",
    "pydantic_core", "pydantic core" all normalize to "pydanticcore")."""
    return _SEPARATORS_RE.sub("", s).lower()


def _repo_is_dedicated_to_package(upstream_repo: str, package_name: str) -> bool:
    """True for a repo whose own name already identifies the package
    (the historical single-package-repo layout, e.g.
    "pydantic/pydantic-core"), where tags are expected to be bare
    versions with no package-name prefix needed. False for a shared
    monorepo (e.g. "pydantic/pydantic" hosting pydantic-core as a
    subdirectory), where releases must mention the package by name to
    disambiguate from sibling packages' own version tags."""
    repo_slug = upstream_repo.rsplit("/", 1)[-1]
    return _normalize_for_match(package_name) in _normalize_for_match(repo_slug)


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
    info.version pointing at it while its publish was still incomplete.
    Requiring a real, non-yanked wheel file is a much better proxy for
    "this release is actually complete".
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


def normalize_tag(tag: str) -> str:
    """Strips an optional leading 'v'/'V' (bare-version tag convention,
    e.g. "v2.41.5" -> "2.41.5")."""
    return tag[1:] if tag[:1] in ("v", "V") else tag


def fetch_upstream_releases(upstream_repo: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{upstream_repo}/releases", "--paginate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed listing releases for {upstream_repo}: {result.stderr}")
    return json.loads(result.stdout)


def find_matching_release(
    releases: list[dict], upstream_repo: str, package_name: str, version: str
) -> str | None:
    """Returns the real tag_name of the upstream release matching
    `version`, or None if none exists (yet, or ever).

    Handles two conventions automatically, based on whether
    `upstream_repo`'s own name identifies `package_name`:
      - dedicated repo: tags are bare versions ("v2.41.5").
      - shared monorepo: releases must mention `package_name` (in
        tag_name and/or the release's display name, any separator
        style) alongside the version number, to disambiguate from
        sibling packages released from the same repo.
    """
    try:
        target = Version(version)
    except InvalidVersion:
        return None

    dedicated = _repo_is_dedicated_to_package(upstream_repo, package_name)
    normalized_package = _normalize_for_match(package_name)

    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag_name = release.get("tag_name")
        if not tag_name:
            continue

        if dedicated:
            candidate_version = normalize_tag(tag_name)
        else:
            haystack = f"{tag_name} {release.get('name') or ''}"
            if normalized_package not in _normalize_for_match(haystack):
                continue
            match = _VERSION_IN_STRING_RE.search(haystack)
            candidate_version = match.group(0) if match else None

        if candidate_version is None:
            continue
        try:
            if Version(candidate_version) == target:
                return tag_name
        except InvalidVersion:
            continue

    return None


def version_from_ref(ref: str) -> str | None:
    """Extracts a trailing version number from a git ref, if present —
    e.g. "v2.46.3" -> "2.46.3", and also "pydantic-core-v2.46.3" ->
    "2.46.3" (since release tags may now be package-prefixed inside the
    pydantic/pydantic monorepo). Returns None for refs with no trailing
    version number at all (branch names like "main", commit SHAs, ...).

    Used by build_wheels.yml to decide, automatically and without a
    second manually-synchronized input, whether a given run should
    publish a GitHub Release.
    """
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
    package_version: str | None
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
    returns the first one upstream has actually released — rather than
    rigidly chasing whatever PyPI's `info.version` claims is "latest"
    even when that version isn't fully published, or assuming a fixed
    tag-naming template that breaks the moment upstream restructures
    its repos (as happened in production with the move to a monorepo).
    """
    releases = fetch_upstream_releases(upstream_repo)

    for version in list_stable_pypi_versions(package_name):
        upstream_ref = find_matching_release(releases, upstream_repo, package_name, version)
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
