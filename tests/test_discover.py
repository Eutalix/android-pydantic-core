from unittest.mock import patch

from ci_tool.arches import get
from ci_tool.discover import discover_python_version
from ci_tool.termux import TermuxPythonPackage

SAMPLE_PACKAGES = [
    TermuxPythonPackage(version="3.14.6-1", termux_arch="aarch64", deb_url="https://x/a.deb"),
    TermuxPythonPackage(version="3.14.5-2", termux_arch="aarch64", deb_url="https://x/b.deb"),
]


def test_discover_python_version_returns_major_minor_of_latest():
    with patch("ci_tool.discover.fetch_index", return_value="<html></html>"), patch(
        "ci_tool.discover.list_available_versions", return_value=SAMPLE_PACKAGES
    ):
        version = discover_python_version(get("arm64-v8a"))
    assert version == "3.14"
