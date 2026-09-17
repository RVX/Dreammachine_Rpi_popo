#!/usr/bin/env bash
# Configure and test the custom PCM5102A I2S DAC shield.
set -euo pipefail
cd "$(dirname "$0")/.."
source config/dreammachine.env

STOP_REAPER=0
PROBE_MODE=0
PROBE_LONG=0
for argument in "$@"; do
    case "${argument}" in
        --stop-reaper) STOP_REAPER=1 ;;
        --probe) PROBE_MODE=1 ;;
        --probe-long)
            PROBE_MODE=1
            PROBE_LONG=1
            ;;
        *)
            echo "Usage: $0 [--stop-reaper] [--probe|--probe-long]" >&2
            exit 2
            ;;
    esac
done

CONFIG_TXT=/boot/firmware/config.txt
if [ ! -f "${CONFIG_TXT}" ]; then
    CONFIG_TXT=/boot/config.txt
fi

if [ ! -f "${CONFIG_TXT}" ]; then
    echo "ERROR: Raspberry Pi boot config was not found." >&2
    exit 1
fi

echo "==> configuring PCM5102A I2S overlay in ${CONFIG_TXT}"
CONFIG_CHANGED=0
if ! grep -q '^dtparam=audio=off$' "${CONFIG_TXT}"; then
    printf '\n%s\n' '# DREAMMACHINE: disable built-in audio for the custom PCM5102A shield' \
        'dtparam=audio=off' | sudo tee -a "${CONFIG_TXT}" >/dev/null
    CONFIG_CHANGED=1
fi

if ! grep -q '^dtoverlay=hifiberry-dac$' "${CONFIG_TXT}"; then
    printf '%s\n' '# DREAMMACHINE custom PCM5102A: GPIO18 BCK, GPIO19 LRCK, GPIO21 DATA' \
        'dtoverlay=hifiberry-dac' | sudo tee -a "${CONFIG_TXT}" >/dev/null
    CONFIG_CHANGED=1
fi

if [ "${CONFIG_CHANGED}" -eq 1 ]; then
    echo "Overlay added. Reboot, then run this script again to verify the DAC."
    exit 0
fi

CARD_NUM=$(aplay -l 2>/dev/null | awk -v name="${ALSA_CARD_NAME}" '$0 ~ name {print $2}' | tr -d ':' | head -n1)
if [ -z "${CARD_NUM}" ]; then
    echo "ERROR: '${ALSA_CARD_NAME}' is not present in aplay -l." >&2
    echo "Reboot if the overlay was just installed, then check: dmesg | grep -i hifiberry" >&2
    exit 1
fi

sudo tee /etc/asound.conf >/dev/null <<EOF
pcm.!default {
    type plug
    slave.pcm "hw:${CARD_NUM},0"
}
ctl.!default {
    type hw
    card ${CARD_NUM}
}
EOF

echo "==> detected PCM5102A as ALSA card ${CARD_NUM}"
aplay -l

PCM_DEVICE="/dev/snd/pcmC${CARD_NUM}D0p"
if fuser -s "${PCM_DEVICE}" 2>/dev/null; then
    if [ "${STOP_REAPER}" -eq 1 ]; then
        echo "==> stopping REAPER to release ${PCM_DEVICE}"
        pkill -TERM -u "$(id -u)" -x reaper 2>/dev/null || true
    fi
    if fuser -s "${PCM_DEVICE}" 2>/dev/null; then
        echo "ERROR: ${PCM_DEVICE} is busy." >&2
        fuser -v "${PCM_DEVICE}" >&2 || true
        echo "Close its audio application or rerun with --stop-reaper." >&2
        exit 1
    fi
fi

if [ "${PROBE_LONG}" -eq 1 ]; then
    echo "==> playing long probe: 30 s left, then 30 s right, repeated twice"
elif [ "${PROBE_MODE}" -eq 1 ]; then
    echo "==> playing a probe-level 1 kHz test: 5 s left, then 5 s right, repeated 3 times"
else
    echo "==> playing a quiet 1 kHz channel-identification test"
fi

TEST_WAV=$(mktemp --suffix=.wav)
trap 'rm -f "${TEST_WAV}"' EXIT
python3 - "${TEST_WAV}" "${PROBE_MODE}" "${PROBE_LONG}" <<'PY'
import math
import struct
import sys
import wave

sample_rate = 48_000
probe_mode = sys.argv[2] == "1"
probe_long = sys.argv[3] == "1"
level_dbfs = -12 if probe_mode else -30
duration = 30.0 if probe_long else (5.0 if probe_mode else 0.5)
repetitions = 2 if probe_long else (3 if probe_mode else 2)
amplitude = int(32767 * (10 ** (level_dbfs / 20)))
segments = ((0, duration), (1, duration)) * repetitions

with wave.open(sys.argv[1], "wb") as output:
    output.setnchannels(2)
    output.setsampwidth(2)
    output.setframerate(sample_rate)
    for channel, duration in segments:
        for sample in range(int(sample_rate * duration)):
            value = int(amplitude * math.sin(2 * math.pi * 1000 * sample / sample_rate))
            frame = (value, 0) if channel == 0 else (0, value)
            output.writeframesraw(struct.pack("<hh", *frame))
PY

aplay -D default "${TEST_WAV}"
if [ "${PROBE_LONG}" -eq 1 ]; then
    echo "DAC long probe completed: 30 s left/right x2 at -12 dBFS."
elif [ "${PROBE_MODE}" -eq 1 ]; then
    echo "DAC probe test completed: 5 s left/right x3 at -12 dBFS."
else
    echo "DAC test completed: left, right, left, right at -30 dBFS."
fi