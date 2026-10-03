from ci_tool.pypi_index import (
    WheelAsset,
    extract_wheel_assets,
    normalize_package_name,
    render_package_index,
    render_root_redirect,
    write_index,
)

SAMPLE_RELEASES = [
    {
        "draft": False,
        "assets": [
            {
                "name": "pydantic_core-2.41.5-cp314-cp314-android_24_arm64_v8a.whl",
                "browser_download_url": "https://example/a.whl",
            },
            {"name": "pydantic_core-2.41.5.tar.gz", "browser_download_url": "https://example/a.tar.gz"},
        ],
    },
    {
        "draft": True,
        "assets": [
            {
                "name": "pydantic_core-9.9.9-cp314-cp314-android_24_arm64_v8a.whl",
                "browser_download_url": "https://example/draft.whl",
            },
        ],
    },
]


def test_normalize_package_name_collapses_separators():
    assert normalize_package_name("pydantic_core") == "pydantic-core"
    assert normalize_package_name("Pydantic..Core__Test") == "pydantic-core-test"


def test_extract_wheel_assets_skips_drafts_and_non_wheels():
    assets = extract_wheel_assets(SAMPLE_RELEASES)
    assert len(assets) == 1
    assert assets[0].filename == "pydantic_core-2.41.5-cp314-cp314-android_24_arm64_v8a.whl"


def test_render_package_index_includes_links():
    assets = [WheelAsset(filename="x.whl", download_url="https://example/x.whl")]
    html = render_package_index("pydantic-core", assets)
    assert "https://example/x.whl" in html
    assert "x.whl" in html
    assert "Links for pydantic-core" in html


def test_render_root_redirect_points_to_normalized_name():
    html = render_root_redirect("pydantic_core")
    assert "pydantic-core/" in html


def test_write_index_creates_expected_files(tmp_path):
    assets = [WheelAsset(filename="x.whl", download_url="https://example/x.whl")]
    write_index(tmp_path, "pydantic_core", assets)
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "pydantic-core" / "index.html").exists()
    assert "x.whl" in (tmp_path / "pydantic-core" / "index.html").read_text()
