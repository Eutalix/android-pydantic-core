#!/usr/bin/env bash
# install_pydantic_core.sh
# Automated installer for pre-compiled pydantic-core wheels on Android/Termux.
# Repository: https://github.com/Eutalix/android-pydantic-core

set -e

# --- CONFIGURATION ---
REPO_USER="Eutalix"
REPO_NAME="android-pydantic-core"
BRANCH="main"

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

PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_VER_DOT="${PY_MAJOR}.${PY_MINOR}"  # e.g. 3.12
PY_TAG="cp${PY_MAJOR}${PY_MINOR}"     # e.g. cp312

# Check minimum supported version (3.9+)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
  echo -e "${RED}Error: This installer requires Python 3.9 or higher.${NC}"
  echo -e "Current version: $PY_VER_DOT"
  exit 1
fi

echo -e "   - Python: ${GREEN}${PY_VER_DOT}${NC}"

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

echo -e "   - Arch: ${GREEN}${ARCH}${NC} (${PLAT_TAG})"

# 3. Version Resolution
# We query the GitHub API to list folders inside python/{version}/pydantic-core/
echo -e "${YELLOW}[3/4] Resolving latest version...${NC}"

API_URL="https://api.github.com/repos/${REPO_USER}/${REPO_NAME}/contents/python/${PY_VER_DOT}/pydantic-core?ref=${BRANCH}"

# Fetch folder list, extract "name", sort by version, take the last one
PKG_VER=$(curl -s "$API_URL" | grep '"name":' | cut -d'"' -f4 | sort -V | tail -n 1)

if [ -z "$PKG_VER" ] || [ "$PKG_VER" == "null" ]; then
  echo -e "${RED}Error: Could not find any compatible wheels in the repository.${NC}"
  echo "   Checked path: python/${PY_VER_DOT}/pydantic-core/"
  echo "   API Response: $(curl -s "$API_URL" | head -n 1)"
  exit 1
fi

echo -e "   - Latest Available: ${GREEN}${PKG_VER}${NC}"

# 4. Download and Install
echo -e "${YELLOW}[4/4] Downloading and installing...${NC}"

# Construct the exact URL based on the repo structure
WHEEL_NAME="pydantic_core-${PKG_VER}-${PY_TAG}-${PY_TAG}-${PLAT_TAG}.whl"
REMOTE_PATH="python/${PY_VER_DOT}/pydantic-core/${PKG_VER}/${WHEEL_NAME}"
FULL_URL="https://raw.githubusercontent.com/${REPO_USER}/${REPO_NAME}/${BRANCH}/${REMOTE_PATH}"

echo -e "   - Source: ${CYAN}${WHEEL_NAME}${NC}"

TMP_WHL="pydantic_core_opt.whl"

if curl -fL -o "$TMP_WHL" "$FULL_URL" --progress-bar; then
  echo ""
  pip install "./$TMP_WHL"
  rm -f "$TMP_WHL"
  echo ""
  echo -e "${GREEN}✅ Success! pydantic-core ${PKG_VER} installed.${NC}"
else
  echo ""
  echo -e "${RED}❌ Download failed.${NC}"
  echo "   URL: $FULL_URL"
  rm -f "$TMP_WHL"
  exit 1
fi
