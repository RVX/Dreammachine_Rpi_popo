#!/usr/bin/env bash
# ensure_reaper_audio.sh — inject ALSA/HifiBerry audio config into reaper.ini
# Idempotent: only adds missing lines, never overwrites existing user config.

REAPER_INI="${HOME}/.config/REAPER/reaper.ini"

# Wait for REAPER to create the ini on first launch
if [ ! -f "${REAPER_INI}" ]; then
    exit 0
fi

# Only inject if not already present
if ! grep -q '^alsa_outdev=' "${REAPER_INI}" 2>/dev/null; then
    sed -i '/^\[audioconfig\]/a alsa_outdev=hw:sndrpihifiberry' "${REAPER_INI}" 2>/dev/null || true
fi

if ! grep -q '^alsa_indev=' "${REAPER_INI}" 2>/dev/null; then
    sed -i '/^\[audioconfig\]/a alsa_indev=' "${REAPER_INI}" 2>/dev/null || true
fi

exit 0
