"""Fetches Termux's `termux-app` bootstrap zip — the minimal base rootfs
(bash, dpkg, linker config, CA certs) used as the foundation for the
smoke-test rootfs (see smoke_test.py).

Release/asset naming confirmed against a live `GET
/repos/termux/termux-packages/releases` response (not guessed from docs):
tags look like `bootstrap-2026.04.12-r1+apt.android-7`, and each such
release carries exactly four assets — `bootstrap-aarch64.zip`,
`bootstrap-arm.zip`, `bootstrap-i686.zip`, `bootstrap-x86_64.zip` — whose
arch component matches `Arch.termux_arch` verbatim, so no extra mapping
table is needed here beyond the asset filename template below.

The bootstrap zip does NOT include Termux's `python` package (there is no
python-related asset here, and the default package set pulled by
`generate-bootstraps.sh`/`build-bootstraps.sh` per the maintainer docs
never mentions it) — so overlaying the `python` .deb from termux.py on
top of an extracted bootstrap in smoke_test.py cannot collide with a
bootstrap-provided python installation; there isn't one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import requests

RELEASES_URL = "https://api.github.com/repos/termux/termux-packages/releases"

# Confirmed exact format via a live API response, e.g.:
#   "bootstrap-2026.04.12-r1+apt.android-7"
_BOOTSTRAP_TAG_RE = re.compile(r"^bootstrap-\d{4}\.\d{2}\.\d{2}-r\d+\+apt\.android-\d+$")

_ASSET_NAME = {
    "aarch64": "bootstrap-aarch64.zip",
    "arm": "bootstrap-arm.zip",
    "x86_64": "bootstrap-x86_64.zip",
    "i686": "bootstrap-i686.zip",
}


@dataclass(frozen=True)
class BootstrapRelease:
    tag_name: str
    published_at: str  # ISO 8601, used only for max()/sort, never parsed as a date
    assets: dict[str, str]  # asset filename -> browser_download_url


def parse_releases(payload: list[dict]) -> list[BootstrapRelease]:
    """Pure parsing function, split out so it's unit-testable against a
    static JSON fixture without a network call.

    Filters out any non-bootstrap releases that might share the same repo
    (the termux-packages repo also tags ordinary package releases).
    """
    releases = []
    for item in payload:
        tag = item.get("tag_name", "")
        if not _BOOTSTRAP_TAG_RE.match(tag):
            continue
        assets = {a["name"]: a["browser_download_url"] for a in item.get("assets", [])}
        releases.append(
            BootstrapRelease(
                tag_name=tag,
                published_at=item.get("published_at") or item.get("created_at") or "",
                assets=assets,
            )
        )
    return releases


def latest_release(releases: list[BootstrapRelease]) -> BootstrapRelease:
    """GitHub's `/releases` endpoint returns newest-first, so releases[0]
    would normally suffice — but we sort explicitly on `published_at`
    (ISO 8601 strings sort correctly lexically) so this doesn't silently
    break if the API's ordering guarantee ever changes or the list is
    pre-filtered/reordered upstream of this function.
    """
    if not releases:
        raise ValueError("No bootstrap releases found")
    return max(releases, key=lambda r: r.published_at)


def asset_url_for_termux_arch(release: BootstrapRelease, termux_arch: str) -> str:
    try:
        asset_name = _ASSET_NAME[termux_arch]
    except KeyError as exc:
        raise ValueError(f"Unknown termux_arch {termux_arch!r}. Known: {sorted(_ASSET_NAME)}") from exc
    try:
        return release.assets[asset_name]
    except KeyError as exc:
        raise ValueError(
            f"Release {release.tag_name!r} has no {asset_name!r} asset. "
            f"Found: {sorted(release.assets)}"
        ) from exc


def fetch_latest_release() -> BootstrapRelease:
    resp = requests.get(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "android-pydantic-core-ci"},
        timeout=30,
    )
    resp.raise_for_status()
    releases = parse_releases(resp.json())
    return latest_release(releases)


def download_bootstrap(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    dest = dest_dir / filename
    if dest.exists():
        return dest
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return dest


def fetch_bootstrap_for_arch(termux_arch: str, cache_dir: Path) -> Path:
    """High-level entry point used by the smoke-test CLI command."""
    release = fetch_latest_release()
    url = asset_url_for_termux_arch(release, termux_arch)
    return download_bootstrap(url, cache_dir / "bootstrap")
