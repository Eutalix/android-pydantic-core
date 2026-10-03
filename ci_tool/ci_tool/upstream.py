"""Checks whether pydantic-core has published a new version upstream
that this repo has not yet built, driving the scheduled check_upstream.yml
workflow.

Unlike pypi_index.py (which reads *this* repo's own GitHub Releases to
build the PEP 503 index), this module reads PyPI — the project being
repackaged — and cross-references this repo's own releases to decide
whether a new build run should be kicked off.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

import requests

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"

# ASSUMPTION, not yet verified against the live pydantic-core repo: that
# its GitHub release tags are named "v{version}" (e.g. "v2.49.0"), which
# is what `pydantic_core_ref` is built from before being checked out by
# build_wheels.yml. Override via --ref-template if this doesn't match.
DEFAULT_UPSTREAM_REF_TEMPLATE = "v{version}"


def latest_pypi_version(package_name: str) -> str:
    resp = requests.get(PYPI_JSON_URL.format(package=package_name), timeout=30)
    resp.raise_for_status()
    return resp.json()["info"]["version"]


def release_tag_for_version(version: str) -> str:
    """Tag used for *this* repo's own release (not upstream's)."""
    return f"v{version}"


def upstream_ref_for_version(
    version: str, ref_template: str = DEFAULT_UPSTREAM_REF_TEMPLATE
) -> str:
    return ref_template.format(version=version)


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
    upstream_ref: str  # e.g. "v2.49.0", git ref to build in pydantic-core
    already_released: bool

    @property
    def should_build(self) -> bool:
        return not self.already_released


def check_for_update(
    repo: str,
    package_name: str,
    ref_template: str = DEFAULT_UPSTREAM_REF_TEMPLATE,
) -> UpdateCheck:
    version = latest_pypi_version(package_name)
    tag = release_tag_for_version(version)
    return UpdateCheck(
        package_version=version,
        release_tag=tag,
        upstream_ref=upstream_ref_for_version(version, ref_template),
        already_released=release_exists(repo, tag),
    )
