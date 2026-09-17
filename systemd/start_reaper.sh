#!/usr/bin/env bash
# Fail-closed REAPER and amplifier startup for the custom shield.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "${REPO_DIR}/config/dreammachine.env"

PATTERN="${REPO_DIR}/rp2350/pattern.py"
REAPER_PID=""

shutdown_audio() {
	python3 "${PATTERN}" amp-mute >/dev/null 2>&1 || true
	python3 "${PATTERN}" amp-shutdown >/dev/null 2>&1 || true
	if [ -n "${REAPER_PID}" ] && kill -0 "${REAPER_PID}" 2>/dev/null; then
		kill -TERM "${REAPER_PID}" 2>/dev/null || true
	fi
}
trap shutdown_audio EXIT HUP INT TERM

python3 "${PATTERN}" amp-mute
python3 "${PATTERN}" amp-shutdown
sleep 8

python3 "${PATTERN}" amp-start-muted
/usr/local/bin/reaper "${REAPER_PROJECT_PATH}" &
REAPER_PID=$!

CARD_NUM=$(aplay -l | awk -v name="${ALSA_CARD_NAME}" '$0 ~ name {print $2}' | tr -d ':' | head -n1)
if [ -z "${CARD_NUM}" ]; then
	echo "ERROR: DAC '${ALSA_CARD_NAME}' is unavailable; amplifier remains shut down." >&2
	exit 1
fi

PCM_DEVICE="/dev/snd/pcmC${CARD_NUM}D0p"
for _ in $(seq 1 40); do
	if ! kill -0 "${REAPER_PID}" 2>/dev/null; then
		echo "ERROR: REAPER exited before opening the DAC; amplifier remains shut down." >&2
		exit 1
	fi
	if fuser -s "${PCM_DEVICE}" 2>/dev/null; then
		/usr/local/bin/reaper -nonewinst "${REPO_DIR}/reaper/force_master_mono.lua"
		python3 "${PATTERN}" amp-unmute
		wait "${REAPER_PID}"
		exit $?
	fi
	sleep 0.5
done

echo "ERROR: REAPER did not open ${PCM_DEVICE}; amplifier remains shut down." >&2
exit 1
