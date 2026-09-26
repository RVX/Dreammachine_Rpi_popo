--[[
  DM_Sonifications_Tracks_5-10.lua
  Adapted from Mazon_StoneSpeakers_Sonifications_5-10.lua
  for DREAMMACHINE Pi units running POPO sonification.

  Replace media items on tracks 5-10 with the 6 most recent POPO sonification
  files and apply +12dB gain, on every loop cycle, but only if there are new files.
]]

local folder        = "/home/sjc/popo/datasets/ground/sonifications"
local valid_exts    = {".wav"}
local track_numbers = {4, 5, 6, 7, 8, 9} -- Tracks 5-10 (0-indexed)
local insert_time   = 0.0
local fade_len      = 0.05
local gain_db       = 12.0
local show_console  = true

local function log(msg)
  if show_console then reaper.ShowConsoleMsg(tostring(msg) .. "\n") end
end

local function has_valid_ext(filename)
  for _, ext in ipairs(valid_exts) do
    if filename:lower():sub(-#ext) == ext then return true end
  end
  return false
end

-- Match POPO filename pattern: popo_live_YYYYMMDDTHHMMSS_*.wav
local function is_popo_file(filename)
  return filename:match("^popo_live_%d+T%d+_.+%.wav$") ~= nil
end

local function get_newest_files()
  local files = {}
  local i = 0
  while true do
    local file = reaper.EnumerateFiles(folder, i)
    if not file then break end
    if has_valid_ext(file) and is_popo_file(file) then
      local full_path = folder .. "/" .. file
      local f = io.popen('stat -c "%Y" "' .. full_path .. '"')
      local mod_time = f and tonumber(f:read("*a")) or 0
      if f then f:close() end
      table.insert(files, {path = full_path, time = mod_time})
    end
    i = i + 1
  end
  table.sort(files, function(a, b) return a.time > b.time end)
  local result = {}
  for j = 1, math.min(6, #files) do
    table.insert(result, files[j].path)
  end
  return result
end

local function clear_track(track)
  for i = reaper.CountTrackMediaItems(track) - 1, 0, -1 do
    reaper.DeleteTrackMediaItem(track, reaper.GetTrackMediaItem(track, i))
  end
end

local function insert_file_on_track(track, file_path)
  local source = reaper.PCM_Source_CreateFromFile(file_path)
  if not source then
    log("[ERROR] Failed to load file: " .. file_path)
    return
  end
  local item = reaper.AddMediaItemToTrack(track)
  local take = reaper.AddTakeToMediaItem(item)
  reaper.SetMediaItemTake_Source(take, source)
  local length = reaper.GetMediaSourceLength(source)
  reaper.SetMediaItemPosition(item, insert_time, false)
  reaper.SetMediaItemLength(item, length, false)
  reaper.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_len)
  reaper.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_len)
  local gain = 10 ^ (gain_db / 20)
  reaper.SetMediaItemTakeInfo_Value(take, "D_VOL", gain)
  reaper.UpdateItemInProject(item)
  log("[OK] Inserted: " .. file_path:match("[^/]+$") .. " (+" .. gain_db .. "dB)")
end

local function replace_files_on_tracks(files)
  if #files < 1 then
    log("[WARN] No sonification files found in: " .. folder)
    return
  end
  for i, track_num in ipairs(track_numbers) do
    local track = reaper.GetTrack(0, track_num)
    if track then
      clear_track(track)
      if files[i] then
        insert_file_on_track(track, files[i])
      else
        log("[WARN] Not enough files for track " .. (track_num + 1))
      end
    else
      log("[WARN] Track " .. (track_num + 1) .. " not found.")
    end
  end
end

local function files_changed(new_files, old_files)
  if #new_files ~= #old_files then return true end
  for i = 1, #new_files do
    if new_files[i] ~= old_files[i] then return true end
  end
  return false
end

-- Loop state
local _, loop_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
local last_play_pos = reaper.GetPlayPosition()
local last_files = {}

local function log_header()
  if show_console then
    reaper.ShowConsoleMsg("\n=== POPO Sonifications - Tracks 5-10 Monitor ===\n")
    reaper.ShowConsoleMsg("Folder: " .. folder .. "\n")
  end
end

local function monitor_loop()
  local play_pos = reaper.GetPlayPosition()
  local playing  = reaper.GetPlayState() & 1 == 1
  if playing and last_play_pos < loop_end and play_pos < last_play_pos then
    local files = get_newest_files()
    reaper.ClearConsole()
    log_header()
    if files_changed(files, last_files) then
      log("New files detected - replacing tracks 5-10 (+" .. gain_db .. "dB)...\n")
      reaper.Undo_BeginBlock()
      reaper.PreventUIRefresh(1)
      replace_files_on_tracks(files)
      reaper.PreventUIRefresh(-1)
      reaper.Undo_EndBlock("Replace POPO sonification files", -1)
      last_files = files
    else
      log("No new files since last loop. Nothing replaced.\n")
      for _, f in ipairs(last_files) do
        log("  " .. f:match("[^/]+$"))
      end
    end
  end

  last_play_pos = play_pos
  reaper.defer(monitor_loop)
end

-- INIT
math.randomseed(os.time())
log_header()
monitor_loop()
