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

# Deploy Lua scripts to REAPER's Scripts dir (REAPER may wipe it on config reset)
REAPER_SCRIPTS="/home/sjc/.config/REAPER/Scripts"
mkdir -p "${REAPER_SCRIPTS}"
for script in DM_Autoloop_Tracks_1-4.lua DM_Sonifications_Tracks_5-10.lua __startup.lua; do
    if [ -f "${REPO_DIR}/reaper/${script}" ]; then
        cp "${REPO_DIR}/reaper/${script}" "${REAPER_SCRIPTS}/"
    fi
done

# Ensure ALSA audio config exists in reaper.ini (survives config wipes)
bash "${REPO_DIR}/reaper/ensure_reaper_audio.sh"

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

		# Amp watchdog: unconditionally re-send amp-unmute every cycle, not just
		# when the DAC closes. The RP2350's amp_unmute() only retry-polls FAULTZ
		# for 300ms and then gives up permanently with no further attempts ever
		# initiated from its side; if that single window is missed (observed in
		# the field, not just on the bench), the DAC stays open the whole time
		# and this watchdog would otherwise never fire again. 0x22 is a no-op
		# when already unmuted, so resending it on a timer is always safe.
		(
			while kill -0 "${REAPER_PID}" 2>/dev/null; do
				sleep 15
				if ! fuser -s "${PCM_DEVICE}" 2>/dev/null; then
					echo "WATCHDOG: DAC closed unexpectedly, re-unmuting amp" >&2
				fi
				python3 "${PATTERN}" amp-unmute >/dev/null 2>&1 || true
			done
		) &
		WATCHDOG_PID=$!

		wait "${REAPER_PID}"
		EXIT_CODE=$?
		kill "${WATCHDOG_PID}" 2>/dev/null || true
		exit "${EXIT_CODE}"
	fi
	sleep 0.5
done

echo "ERROR: REAPER did not open ${PCM_DEVICE}; amplifier remains shut down." >&2
exit 1
