local master = reaper.GetMasterTrack(0)

reaper.SetMediaTrackInfo_Value(master, "D_PAN", 0.0)
reaper.SetMediaTrackInfo_Value(master, "D_WIDTH", 0.0)
reaper.UpdateArrange()

local state = io.open("/tmp/dreammachine-mono-state.txt", "w")
if state then
	state:write(string.format(
		"pan=%.1f\nwidth=%.1f\n",
		reaper.GetMediaTrackInfo_Value(master, "D_PAN"),
		reaper.GetMediaTrackInfo_Value(master, "D_WIDTH")
	))
	state:close()
end

reaper.ShowConsoleMsg("DREAMMACHINE: master output forced to centered mono\n")