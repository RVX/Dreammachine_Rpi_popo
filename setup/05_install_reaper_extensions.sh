#!/usr/bin/env bash
# 05_install_reaper_extensions.sh — install SWS + ReaPack REAPER extensions.
# Run on the Pi: bash setup/05_install_reaper_extensions.sh
# REAPER must be closed and reopened afterwards to load the new extensions.
set -euo pipefail

USERPLUGINS="${HOME}/.config/REAPER/UserPlugins"
mkdir -p "${USERPLUGINS}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# --- ReaPack (package manager) ---
# Official build from cfillion/reapack releases (v1.2.6, linux-aarch64).
# NOTE: keep the "-aarch64" suffix in the installed filename. ReaPack checks
# it was loaded from the standard arch-suffixed path (needed for its own
# self-update mechanism to find the right asset); renaming it to a generic
# reaper_reapack.so triggers a "not loaded from the standard extension path"
# warning on startup.
REAPACK_URL="https://github.com/cfillion/reapack/releases/download/v1.2.6/reaper_reapack-aarch64.so"
echo "==> downloading ReaPack (aarch64)"
rm -f "${USERPLUGINS}/reaper_reapack.so"
curl -fL "${REAPACK_URL}" -o "${USERPLUGINS}/reaper_reapack-aarch64.so"
echo "ReaPack installed: ${USERPLUGINS}/reaper_reapack-aarch64.so"

# --- SWS/S&M extension ---
# Official bleeding-edge build from sws-extension.org (no separate stable
# aarch64 build is published; the pre-release build is what SWS itself
# recommends downloading for Linux/aarch64). The tarball mirrors REAPER's
# resource directory layout (UserPlugins/, Scripts/, Data/), so it's
# extracted straight into ~/.config/REAPER/ to land everything correctly.
SWS_URL="https://sws-extension.org/download/pre-release/sws-2.14.0.7-Linux-aarch64-9daba634.tar.xz"
REAPER_RESOURCE_DIR="${HOME}/.config/REAPER"
echo "==> downloading SWS extension (aarch64)"
curl -fL "${SWS_URL}" -o "${TMP_DIR}/sws.tar.xz"
mkdir -p "${REAPER_RESOURCE_DIR}"
tar -xf "${TMP_DIR}/sws.tar.xz" -C "${REAPER_RESOURCE_DIR}"

echo ""
echo "Installed extensions in ${USERPLUGINS}:"
ls -la "${USERPLUGINS}"
echo ""
echo "05_install_reaper_extensions.sh done. Close and reopen REAPER to load them"
echo "(Extensions menu should then show SWS/S&M and ReaPack after restart)."
