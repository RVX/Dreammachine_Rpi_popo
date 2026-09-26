-- __startup.lua — runs automatically when REAPER starts
-- Launches the DREAMMACHINE POPO sonification monitors

reaper.defer(function()
  -- AutoLoop tracks 1-4: loads 4 newest POPO wavs, repositions on each loop
  dofile(reaper.GetResourcePath() .. "/Scripts/DM_Autoloop_Tracks_1-4.lua")
end)

reaper.defer(function()
  -- Sonifications tracks 5-10: replaces media with 6 newest POPO wavs per loop
  dofile(reaper.GetResourcePath() .. "/Scripts/DM_Sonifications_Tracks_5-10.lua")
end)
