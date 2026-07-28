#!/usr/bin/env bash
# 02_install_reaper.sh — download and install REAPER (Linux aarch64, evaluation).
# Run on the Pi: bash setup/02_install_reaper.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REAPER_VERSION="778"
REAPER_URL="https://www.reaper.fm/files/7.x/reaper${REAPER_VERSION}_linux_aarch64.tar.xz"
TMP_DIR="$(mktemp -d)"

echo "==> downloading REAPER ${REAPER_VERSION} (aarch64) from reaper.fm"
curl -fL "${REAPER_URL}" -o "${TMP_DIR}/reaper.tar.xz"

echo "==> extracting"
tar -xf "${TMP_DIR}/reaper.tar.xz" -C "${TMP_DIR}"

echo "==> installing to /opt/REAPER (system-wide, integrates desktop entry)"
sudo "${TMP_DIR}"/reaper_linux_aarch64/install-reaper.sh \
    --install /opt \
    --integrate-desktop \
    --usr-local-bin-symlink

rm -rf "${TMP_DIR}"

echo "==> REAPER installed: $(readlink -f /opt/REAPER/reaper || echo '/opt/REAPER/reaper')"
echo "This is a 60-day full-featured evaluation. Enter a license later via"
echo "REAPER > Help > About REAPER > Enter license key (or per-machine later)."
echo ""
echo "NEXT STEP (manual, one-time, via VNC/HDMI on this Pi only):"
echo "  1. Launch REAPER once from the desktop menu (creates ~/.config/REAPER/reaper.ini)."
echo "  2. Follow reaper/OSC_SETUP.md to add the OSC (ReaOSC) control surface."
echo "  3. Create/import the '${REAPER_PROJECT_NAME:-Dreammachine_popo_01}' project."
echo "02_install_reaper.sh done."
