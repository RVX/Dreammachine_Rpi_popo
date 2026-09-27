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
local fade_len      = 10.0   -- Fade-in/out duration in seconds
local gain_db       = 0.0
local show_console  = true
local min_gap       = 30.0    -- min seconds between items across tracks 5-10
local project_min_time = 5.0  -- no items in first 5s

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

local function insert_file_on_track(track, file_path, pos)
  local source = reaper.PCM_Source_CreateFromFile(file_path)
  if not source then
    log("[ERROR] Failed to load file: " .. file_path)
    return nil, 0
  end
  local item = reaper.AddMediaItemToTrack(track)
  local take = reaper.AddTakeToMediaItem(item)
  reaper.SetMediaItemTake_Source(take, source)
  local length = reaper.GetMediaSourceLength(source)
  reaper.SetMediaItemPosition(item, pos, false)
  reaper.SetMediaItemLength(item, length, false)
  reaper.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_len)
  reaper.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_len)
  local gain = 10 ^ (gain_db / 20)
  reaper.SetMediaItemTakeInfo_Value(take, "D_VOL", gain)
  reaper.UpdateItemInProject(item)
  log("[OK] " .. file_path:match("[^/]+$") .. " at " .. string.format("%.1fs", pos))
  return item, length
end

-- Find a random position that doesn't overlap with existing ranges
local function find_gap_position(item_len, loop_start, loop_end, existing_ranges)
  local tries = 0
  while tries < 100 do
    local avail = loop_end - math.max(loop_start, project_min_time) - item_len
    if avail <= 0 then return nil end
    local pos = math.max(loop_start, project_min_time) + math.random() * avail
    local ok = true
    for _, r in ipairs(existing_ranges) do
      if pos < r[2] + min_gap and pos + item_len > r[1] - min_gap then
        ok = false
        break
      end
    end
    if ok then return pos end
    tries = tries + 1
  end
  return nil  -- give up after 100 tries
end

local function replace_files_on_tracks(files)
  if #files < 1 then
    log("[WARN] No sonification files found in: " .. folder)
    return
  end
  local loop_start, loop_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  -- If no loop set or loop too short, use project length or default 20 min
  if loop_end - loop_start < 60 then
    loop_start = 0
    loop_end = math.max(reaper.GetProjectLength(0), 1200)  -- 20 min default
    log("[INFO] No loop set, using " .. string.format("%.0f", loop_end) .. "s timeline")
  end
  local all_ranges = {}  -- track positions across ALL tracks to avoid stacking
  for i, track_num in ipairs(track_numbers) do
    local track = reaper.GetTrack(0, track_num)
    if track then
      clear_track(track)
      if files[i] then
        -- peek at file length first
        local src = reaper.PCM_Source_CreateFromFile(files[i])
        local flen = src and reaper.GetMediaSourceLength(src) or 30
        local pos = find_gap_position(flen, loop_start, loop_end, all_ranges)
        if pos then
          local item, actual_len = insert_file_on_track(track, files[i], pos)
          if item then
            table.insert(all_ranges, {pos, pos + actual_len})
          end
        else
          -- Even-spread fallback: divide timeline into equal slots per track index
          local slot = (loop_end - loop_start) / #track_numbers
          local spread_pos = loop_start + (i - 1) * slot + math.random() * slot * 0.3
          log("[WARN] Track " .. (track_num + 1) .. ": no gap found, spread to " .. string.format("%.1fs", spread_pos))
          local item, actual_len = insert_file_on_track(track, files[i], spread_pos)
          if item then
            table.insert(all_ranges, {spread_pos, spread_pos + actual_len})
          end
        end
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
