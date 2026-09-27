-- __startup.lua — runs automatically when REAPER starts
-- Launches the DREAMMACHINE POPO sonification monitors and starts playback

local LOOP_LENGTH = 1200  -- 20 minutes (seconds)

reaper.defer(function()
  -- Set loop range before monitors start — they need it for positioning
  reaper.GetSet_LoopTimeRange(true, true, 0, LOOP_LENGTH, false)
end)

reaper.defer(function()
  -- AutoLoop tracks 1-4: loads 4 newest POPO wavs, repositions on each loop
  dofile(reaper.GetResourcePath() .. "/Scripts/DM_Autoloop_Tracks_1-4.lua")
end)

reaper.defer(function()
  -- Sonifications tracks 5-10: replaces media with 6 newest POPO wavs per loop
  dofile(reaper.GetResourcePath() .. "/Scripts/DM_Sonifications_Tracks_5-10.lua")
end)

-- Auto-play: start transport after a short delay (let scripts load first)
reaper.defer(function()
  reaper.Main_OnCommand(1007, 0)  -- Transport: Play
end)
