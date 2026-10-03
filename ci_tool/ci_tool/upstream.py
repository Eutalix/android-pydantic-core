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

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
UPSTREAM_REPO_DEFAULT = "pydantic/pydantic-core"

# Matches an optional "v" prefix followed by a dotted numeric version,
# with an optional pre-release/build suffix (e.g. "v2.49.0", "2.49.0",
# "v2.49.0rc1") — but NOT branch names ("main"), arbitrary branch
# slugs ("fix-xyz"), or raw commit SHAs (no dots).
_VERSION_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)?)$")


def latest_pypi_version(package_name: str) -> str:
    resp = requests.get(PYPI_JSON_URL.format(package=package_name), timeout=30)
    resp.raise_for_status()
    return resp.json()["info"]["version"]


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


def find_matching_tag(tag_names: list[str], version: str) -> str:
    """Returns the real tag name matching `version`, or raises with a
    preview of what *is* tagged — mirrors termux.matching_for_arch_and_version:
    fail loudly with the actual available data rather than silently
    handing a guessed, possibly-nonexistent ref to `actions/checkout`."""
    for name in tag_names:
        if normalize_tag(name) == version:
            return name
    preview = tag_names[:15]
    raise ValueError(
        f"No tag matching version {version!r} found among "
        f"{len(tag_names)} upstream tag(s). First few seen: {preview}. "
        "If the upstream naming convention isn't a bare or "
        "'v'-prefixed version number, update normalize_tag() in "
        "ci_tool/upstream.py."
    )


def fetch_upstream_tags(upstream_repo: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{upstream_repo}/tags", "--paginate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed listing tags for {upstream_repo}: {result.stderr}")
    return json.loads(result.stdout)


def resolve_upstream_ref(upstream_repo: str, version: str) -> str:
    """High-level entry point: the real, confirmed git ref in
    `upstream_repo` for PyPI version `version` — resolved by querying
    the repo's actual tags instead of guessing a naming template."""
    tag_names = extract_tag_names(fetch_upstream_tags(upstream_repo))
    return find_matching_tag(tag_names, version)


def version_from_ref(ref: str) -> str | None:
    """If `ref` looks like a version tag, returns the bare version
    string (without any leading "v"); otherwise returns None.

    Used by build_wheels.yml to decide, automatically and without a
    second manually-synchronized input, whether a given run should
    publish a GitHub Release: building `pydantic_core_ref: main` or some
    feature branch never releases, building a tag like `v2.49.0` or
    `2.49.0` always does (unless overridden by the workflow's `dry_run`
    input).
    """
    match = _VERSION_TAG_RE.match(ref.strip())
    return match.group(1) if match else None


def release_exists(repo: str, tag: str) -> bool:
    """True if `repo` already has a GitHub release tagged `tag`. Shells
    out to `gh` (already authenticated via GITHUB_TOKEN in Actions),
    consistent with pypi_index.fetch_releases."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@dataclass(frozen=True)
class UpdateCheck:
    package_version: str  # e.g. "2.49.0", from PyPI
    release_tag: str  # e.g. "v2.49.0", this repo's tag
    upstream_ref: str  # the real tag found in upstream_repo
    already_released: bool

    @property
    def should_build(self) -> bool:
        return not self.already_released


def check_for_update(
    repo: str,
    package_name: str,
    upstream_repo: str = UPSTREAM_REPO_DEFAULT,
) -> UpdateCheck:
    version = latest_pypi_version(package_name)
    tag = release_tag_for_version(version)
    upstream_ref = resolve_upstream_ref(upstream_repo, version)
    return UpdateCheck(
        package_version=version,
        release_tag=tag,
        upstream_ref=upstream_ref,
        already_released=release_exists(repo, tag),
    )
