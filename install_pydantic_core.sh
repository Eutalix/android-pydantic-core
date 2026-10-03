
#!/usr/bin/env bash
# install_pydantic_core.sh
# Automated installer for pydantic-core on Android/Termux via GitHub Releases.
# Repo: https://github.com/Eutalix/android-pydantic-core

set -e

# --- CONFIGURATION ---
REPO_USER="Eutalix"
REPO_NAME="android-pydantic-core"

# --- COLORS ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}>>> Android Pydantic-Core Installer <<<${NC}"

# 1. Environment Check
echo -e "${YELLOW}[1/4] Checking Python environment...${NC}"
if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}Error: Python 3 is not installed.${NC}"
  echo "Please run: pkg install python"
  exit 1
fi

# Extract version info using Python itself for reliability
eval $(python3 -c "import sys; v=sys.version_info; print(f'PY_MAJOR={v.major} PY_MINOR={v.minor}')")
PY_VER_DOT="${PY_MAJOR}.${PY_MINOR}"  # e.g. 3.14
PY_TAG="cp${PY_MAJOR}${PY_MINOR}"     # e.g. cp314

echo -e "   - Python: ${GREEN}${PY_VER_DOT}${NC} (${PY_TAG})"

# 2. Architecture Detection
#
# This repo publishes wheels tagged with the PEP 738 Android platform
# tag (`android_<api>_<abi>`), where `<abi>` is the Android NDK ABI name
# normalized by replacing "-" with "_" (e.g. "arm64-v8a" -> "arm64_v8a").
# This mirrors ci_tool/arches.py and ci_tool/wheel_tags.py in the build
# pipeline itself — keep this table in sync with that one.
echo -e "${YELLOW}[2/4] Detecting architecture...${NC}"
ARCH=$(uname -m)
case "$ARCH" in
  aarch64)        ABI_TAG="arm64_v8a" ;;
  arm|armv7l|armv8l) ABI_TAG="armeabi_v7a" ;;
  x86_64)         ABI_TAG="x86_64" ;;
  i686|i386)      ABI_TAG="x86" ;;
  *)
    echo -e "${RED}Error: Unsupported architecture ($ARCH).${NC}"
    exit 1
    ;;
esac

echo -e "   - Arch: ${GREEN}${ARCH}${NC} -> Wheels matching ABI tag: ${ABI_TAG}"

# 3. Fetch Latest Release URL
echo -e "${YELLOW}[3/4] Finding latest compatible wheel...${NC}"

API_URL="https://api.github.com/repos/${REPO_USER}/${REPO_NAME}/releases/latest"
echo -e "   - Querying GitHub API..."
JSON_RESPONSE=$(curl -s "$API_URL")

# Use Python to parse the JSON (jq is not installed by default on Termux).
# Matches assets whose filename contains the interpreter tag (cp314) and
# ends with "_<abi_tag>.whl" — an exact suffix match, not a substring
# check, so e.g. ABI tag "x86" never falsely matches "..._x86_64.whl".
READ_PYTHON_SCRIPT="
import sys, json
try:
    data = json.load(sys.stdin)
    if 'assets' not in data: sys.exit(1)

    py_tag = '${PY_TAG}'
    abi_suffix = '_${ABI_TAG}.whl'

    for asset in data['assets']:
        name = asset['name']
        if py_tag in name and name.endswith(abi_suffix):
            print(asset['browser_download_url'])
            print(asset['name'])
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
"

RESULT=$(echo "$JSON_RESPONSE" | python3 -c "$READ_PYTHON_SCRIPT")

if [ -z "$RESULT" ]; then
    echo -e "${RED}Error: No compatible wheel found in the latest release.${NC}"
    echo "This repo only builds against whichever Python version Termux's"
    echo "apt repo currently serves. If you're on Python $PY_VER_DOT and"
    echo "none of the published wheels match, either:"
    echo "  - run 'pkg upgrade python' to match the currently tracked version, or"
    echo "  - check an older release at:"
    echo "    https://github.com/${REPO_USER}/${REPO_NAME}/releases"
    exit 1
fi

DOWNLOAD_URL=$(echo "$RESULT" | head -n 1)
FILENAME=$(echo "$RESULT" | tail -n 1)

echo -e "   - Found: ${GREEN}${FILENAME}${NC}"

# 4. Download and Install
echo -e "${YELLOW}[4/4] Downloading and installing...${NC}"

echo -e "   - Downloading..."
if curl -fL -o "$FILENAME" "$DOWNLOAD_URL" --progress-bar; then
  echo ""
  echo -e "${YELLOW}Installing wheel...${NC}"

  if pip install "./$FILENAME"; then
      rm -f "$FILENAME"
      echo ""
      echo -e "${GREEN}✅ Success! Installed: ${FILENAME}${NC}"
  else
      echo -e "${RED}❌ Pip install failed.${NC}"
      exit 1
  fi
else
  echo ""
  echo -e "${RED}❌ Download failed.${NC}"
  rm -f "$FILENAME"
  exit 1
fi
