#!/usr/bin/env bash
# Install GitHub CLI (gh) to a user-local directory without sudo.
#
# Usage:
#   ./server/install_gh_user_local.sh [--install-dir <path>] [--version <tag>]
#
# Defaults:
#   install_dir = ~/.local/bin
#   version     = latest (fetched from GitHub API)
#
# Do NOT run this script without reviewer/controller authorization.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-${HOME}/.local/bin}"
GH_VERSION="${GH_VERSION:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        --version)     GH_VERSION="$2";  shift 2 ;;
        *) echo "[error] unknown argument: $1" >&2; exit 1 ;;
    esac
done

# Resolve latest version if not pinned
if [[ -z "${GH_VERSION}" ]]; then
    echo "[install_gh] fetching latest gh version from GitHub API"
    if command -v curl &>/dev/null; then
        GH_VERSION="$(curl -fsSL "https://api.github.com/repos/cli/cli/releases/latest" \
            | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])")"
    else
        echo "[error] curl not available; pass --version explicitly" >&2
        exit 1
    fi
fi
GH_VERSION="${GH_VERSION#v}"
echo "[install_gh] target version: ${GH_VERSION}"

# Detect OS and arch
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64)  ARCH_TAG="amd64" ;;
    aarch64|arm64) ARCH_TAG="arm64" ;;
    *) echo "[error] unsupported architecture: ${ARCH}" >&2; exit 1 ;;
esac

case "${OS}" in
    linux)  PKG_EXT="tar.gz";  PKG_OS="linux" ;;
    darwin) PKG_EXT="zip";     PKG_OS="macOS" ;;
    *) echo "[error] unsupported OS: ${OS}" >&2; exit 1 ;;
esac

PKG_NAME="gh_${GH_VERSION}_${PKG_OS}_${ARCH_TAG}"
DOWNLOAD_URL="https://github.com/cli/cli/releases/download/v${GH_VERSION}/${PKG_NAME}.${PKG_EXT}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

echo "[install_gh] downloading ${DOWNLOAD_URL}"
curl --fail --location --retry 3 --progress-bar \
    -o "${TMPDIR}/gh_pkg.${PKG_EXT}" "${DOWNLOAD_URL}"

echo "[install_gh] extracting"
if [[ "${PKG_EXT}" == "tar.gz" ]]; then
    tar -xzf "${TMPDIR}/gh_pkg.${PKG_EXT}" -C "${TMPDIR}"
else
    unzip -q "${TMPDIR}/gh_pkg.${PKG_EXT}" -d "${TMPDIR}"
fi

GH_BIN="$(find "${TMPDIR}" -name "gh" -type f | head -1)"
if [[ -z "${GH_BIN}" ]]; then
    echo "[error] gh binary not found in extracted package" >&2
    exit 1
fi

mkdir -p "${INSTALL_DIR}"
cp "${GH_BIN}" "${INSTALL_DIR}/gh"
chmod 755 "${INSTALL_DIR}/gh"

echo "[install_gh] installed: ${INSTALL_DIR}/gh"
"${INSTALL_DIR}/gh" --version

# Remind user to add to PATH if needed
if ! command -v gh &>/dev/null; then
    echo ""
    echo "[install_gh] NOTE: ${INSTALL_DIR} may not be in PATH."
    echo "Add to ~/.bashrc or ~/.profile:"
    echo "  export PATH=\"${INSTALL_DIR}:\${PATH}\""
fi
