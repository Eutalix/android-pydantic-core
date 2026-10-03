"""Generates a PEP 503 ("simple repository API") static index from the
repo's GitHub Releases, for publishing via GitHub Pages.

Uses `gh api repos/<repo>/releases` rather than `gh release list`: the
latter does not include `assets`/`browser_download_url`, which this
index depends on.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NORMALIZE_RE = re.compile(r"[-_.]+")


def normalize_package_name(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of -_. collapsed to '-'."""
    return _NORMALIZE_RE.sub("-", name).lower()


@dataclass(frozen=True)
class WheelAsset:
    filename: str
    download_url: str


def extract_wheel_assets(releases: list[dict]) -> list[WheelAsset]:
    """Pulls every .whl asset out of a `gh api .../releases` response,
    skipping draft releases."""
    assets = []
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            url = asset.get("browser_download_url")
            if name.endswith(".whl") and url:
                assets.append(WheelAsset(filename=name, download_url=url))
    return assets


def render_package_index(package_name: str, assets: list[WheelAsset]) -> str:
    normalized = normalize_package_name(package_name)
    links = "\n".join(f'    <a href="{a.download_url}">{a.filename}</a><br>' for a in assets)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<body>\n"
        f"  <h1>Links for {normalized}</h1>\n"
        f"{links}\n"
        "</body>\n"
        "</html>\n"
    )


def render_root_redirect(package_name: str) -> str:
    normalized = normalize_package_name(package_name)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        f'<head><meta http-equiv="refresh" content="0; url={normalized}/" /></head>\n'
        f'<body><a href="{normalized}/">Go to {normalized}</a></body>\n'
        "</html>\n"
    )


def fetch_releases(repo: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases", "--paginate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr}")
    return json.loads(result.stdout)


def write_index(site_dir: Path, package_name: str, assets: list[WheelAsset]) -> None:
    normalized = normalize_package_name(package_name)
    package_dir = site_dir / normalized
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "index.html").write_text(render_package_index(package_name, assets))
    (site_dir / "index.html").write_text(render_root_redirect(package_name))


def build_index(*, repo: str, package_name: str, site_dir: Path) -> int:
    """High-level entry point. Returns the number of wheels indexed."""
    releases = fetch_releases(repo)
    assets = extract_wheel_assets(releases)
    write_index(site_dir, package_name, assets)
    return len(assets)
