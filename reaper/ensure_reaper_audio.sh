#!/bin/bash
# ensure_reaper_audio.sh — inject ALSA/HifiBerry audio config into reaper.ini
# if it's missing (e.g. after config wipe, fresh install, or accidental move).
# Called from start_reaper.sh before launching REAPER.

INI="/home/sjc/.config/REAPER/reaper.ini"

# Skip if audio is already configured
if grep -q "alsa_outdev=hw:sndrpihifiberry" "$INI" 2>/dev/null; then
    exit 0
fi

mkdir -p "$(dirname "$INI")"

# Inject audio config — REAPER reads [REAPER] section for linux_audio_* keys
# and alsa_* keys at top level
if [ -f "$INI" ]; then
    # Remove any existing audio keys to avoid duplicates
    sed -i '/^alsa_indev=/d;/^alsa_outdev=/d;/^alsa_rtprio=/d;/^jack_launchcmd=/d;/^jack_rtprio=/d;/^linux_audio_/d' "$INI"
fi

# Append to [REAPER] section if it exists, otherwise append at end
if grep -q '^\[REAPER\]' "$INI" 2>/dev/null; then
    sed -i '/^\[REAPER\]/a alsa_indev=\nalsa_outdev=hw:sndrpihifiberry\nalsa_rtprio=0\njack_launchcmd=\njack_rtprio=-1\nlinux_audio_bits=32\nlinux_audio_bsize=512\nlinux_audio_bufs=3\nlinux_audio_mode=1\nlinux_audio_nch_in=2\nlinux_audio_nch_out=2\nlinux_audio_srate=44100\nlinux_audio_srateor=1' "$INI"
else
    cat >> "$INI" << 'EOF'
[REAPER]
alsa_indev=
alsa_outdev=hw:sndrpihifiberry
alsa_rtprio=0
jack_launchcmd=
jack_rtprio=-1
linux_audio_bits=32
linux_audio_bsize=512
linux_audio_bufs=3
linux_audio_mode=1
linux_audio_nch_in=2
linux_audio_nch_out=2
linux_audio_srate=44100
linux_audio_srateor=1
EOF
fi

echo "Audio config injected into $INI"
