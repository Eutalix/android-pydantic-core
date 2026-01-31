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
PY_VER_DOT="${PY_MAJOR}.${PY_MINOR}"  # e.g. 3.12
PY_TAG="cp${PY_MAJOR}${PY_MINOR}"     # e.g. cp312

# Check minimum supported version (3.9+)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
  echo -e "${RED}Error: This installer requires Python 3.9 or higher.${NC}"
  echo -e "Current version: $PY_VER_DOT"
  exit 1
fi

echo -e "   - Python: ${GREEN}${PY_VER_DOT}${NC} (${PY_TAG})"

# 2. Architecture Detection
echo -e "${YELLOW}[2/4] Detecting architecture...${NC}"
ARCH=$(uname -m)
case "$ARCH" in
  aarch64)      PLAT_TAG="linux_aarch64" ;;
  armv7l|armv8l) PLAT_TAG="linux_armv7l" ;;
  x86_64)       PLAT_TAG="linux_x86_64" ;;
  i686|i386)    PLAT_TAG="linux_i686" ;;
  *)
    echo -e "${RED}Error: Unsupported architecture ($ARCH).${NC}"
    exit 1
    ;;
esac

echo -e "   - Arch: ${GREEN}${ARCH}${NC} -> Wheels matching: ${PLAT_TAG}"

# 3. Fetch Latest Release URL
echo -e "${YELLOW}[3/4] Finding latest compatible wheel...${NC}"

# We use the GitHub API to get the latest release JSON
API_URL="https://api.github.com/repos/${REPO_USER}/${REPO_NAME}/releases/latest"
echo -e "   - Querying GitHub API..."
JSON_RESPONSE=$(curl -s "$API_URL")

# Use Python to parse the JSON (jq is not installed by default on Termux)
# It finds the asset that contains both the python tag (cp312) and platform tag (linux_aarch64)
READ_PYTHON_SCRIPT="
import sys, json
try:
    data = json.load(sys.stdin)
    if 'assets' not in data: sys.exit(1)
    
    py_tag = '${PY_TAG}'
    plat_tag = '${PLAT_TAG}'
    
    for asset in data['assets']:
        name = asset['name']
        if py_tag in name and plat_tag in name and name.endswith('.whl'):
            print(asset['browser_download_url'])
            print(asset['name'])
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
"

# Capture output (Line 1: URL, Line 2: Filename)
RESULT=$(echo "$JSON_RESPONSE" | python3 -c "$READ_PYTHON_SCRIPT")

if [ -z "$RESULT" ]; then
    echo -e "${RED}Error: No compatible wheel found in the latest release.${NC}"
    echo "Make sure a release exists for Python $PY_VER_DOT on $ARCH."
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
  
  # Install using pip
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