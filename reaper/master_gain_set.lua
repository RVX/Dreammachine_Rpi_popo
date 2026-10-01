-- Set REAPER's master track output to an absolute dB offset (per-unit volume leveling).
-- Idempotent: sets an absolute value, safe to re-run. Edit TARGET_DB before running on a
-- different unit -- this is NOT a relative adjustment, each run overwrites the master fader.
-- Invoke against the running instance: reaper -nonewinst reaper/master_gain_set.lua

local master = reaper.GetMasterTrack(0)
local TARGET_DB = -2.0

local gain = 10 ^ (TARGET_DB / 20)
reaper.SetMediaTrackInfo_Value(master, "D_VOL", gain)
reaper.UpdateArrange()

local state = io.open("/tmp/dreammachine-gain-state.txt", "w")
if state then
	state:write(string.format("D_VOL=%.4f (%.1fdB)\n", reaper.GetMediaTrackInfo_Value(master, "D_VOL"), TARGET_DB))
	state:close()
end
