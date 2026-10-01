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
		AMP_LOG=/tmp/dreammachine-amp-watchdog.log
		echo "$(date '+%Y-%m-%d %H:%M:%S') startup: sending amp-unmute" >>"${AMP_LOG}"
		python3 "${PATTERN}" amp-unmute

		# Amp watchdog: unconditionally re-send amp-unmute every cycle, not just
		# when the DAC closes. The RP2350's amp_unmute() only retry-polls FAULTZ
		# for 300ms and then gives up permanently with no further attempts ever
		# initiated from its side; if that single window is missed (observed in
		# the field, not just on the bench), the DAC stays open the whole time
		# and this watchdog would otherwise never fire again. 0x22 is a no-op
		# when already unmuted, so resending it on a timer is always safe.
		#
		# Startup is the single riskiest window for missing that 300ms FAULTZ
		# poll (power rails/DAC XSMT still settling), so retry fast (every 2s)
		# for the first ~2 minutes, then fall back to a slow steady-state poll.
		#
		# Plain amp-unmute (0x22) can NEVER clear a *latched* FAULTZ fault (TPA3118
		# over-current/over-temp/UVLO) because it never toggles the shutdown pin —
		# only a full amp-shutdown -> amp-start-muted -> amp-unmute cycle resets
		# that latch (confirmed in the field 2026-09-30: amp stayed silently muted
		# through ~40 plain-unmute retries, only cleared by a manual full cycle).
		# A full cycle audibly interrupts playback for ~0.4s though, so it is only
		# attempted ONCE per boot, at the 30s mark of the startup window (by then a
		# latched fault from power-up transients has had time to manifest but a
		# human watching the opening of the piece is least likely to notice one
		# brief blip) -- never repeated in steady state, to avoid disrupting an
		# already-fine show.
		(
			attempt=0
			full_reset_done=0
			while kill -0 "${REAPER_PID}" 2>/dev/null; do
				if [ "${attempt}" -lt 60 ]; then
					sleep 2
					attempt=$((attempt + 1))
				else
					sleep 15
				fi
				if ! fuser -s "${PCM_DEVICE}" 2>/dev/null; then
					echo "$(date '+%Y-%m-%d %H:%M:%S') WATCHDOG: DAC closed unexpectedly, re-unmuting amp" >>"${AMP_LOG}"
				fi
				if [ "${full_reset_done}" -eq 0 ] && [ "${attempt}" -eq 15 ]; then
					full_reset_done=1
					echo "$(date '+%Y-%m-%d %H:%M:%S') WATCHDOG: one-time full amp reset cycle (clears a latched FAULTZ that plain unmute cannot)" >>"${AMP_LOG}"
					python3 "${PATTERN}" amp-shutdown >>"${AMP_LOG}" 2>&1 || true
					python3 "${PATTERN}" amp-start-muted >>"${AMP_LOG}" 2>&1 || true
				fi
				python3 "${PATTERN}" amp-unmute >>"${AMP_LOG}" 2>&1 || true
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
