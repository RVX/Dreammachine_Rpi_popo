--[[
  DM_Autoloop_Tracks_1-4.lua
  Adapted from Mazon_StoneSpeakers_Autollop_Media_Repossition_1-4.lua
  for DREAMMACHINE Pi units running POPO sonification.

  On each loop cycle:
    - Loads the 4 most recent POPO sonification .wav files onto tracks 1-4.
    - Only replaces if new files have appeared since last cycle.
    - Randomly repositions each item within the loop (avoiding first 10s, min 60s gap).
    - Applies fade-in/out of 1s and +12dB gain.
    - Headless — no popup windows.
]]

local folder           = "/home/sjc/popo/datasets/ground/sonifications"
local valid_exts       = {".wav"}
local num_tracks       = 4       -- tracks 1-4 (0-indexed 0-3)
local fade_time        = 10.0   -- Fade-in/out duration in seconds
local gain_db          = 0.0
local min_gap          = 60.0
local project_min_time = 10.0
local show_console     = true

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

local function get_newest_files(n)
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
  for j = 1, math.min(n, #files) do
    table.insert(result, files[j].path)
  end
  return result
end

local function clear_track(track)
  for i = reaper.CountTrackMediaItems(track) - 1, 0, -1 do
    reaper.DeleteTrackMediaItem(track, reaper.GetTrackMediaItem(track, i))
  end
end

local function load_file_on_track(track, file_path)
  local source = reaper.PCM_Source_CreateFromFile(file_path)
  if not source then
    log("[ERROR] Failed to load: " .. file_path)
    return false
  end
  local item = reaper.AddMediaItemToTrack(track)
  local take = reaper.AddTakeToMediaItem(item)
  reaper.SetMediaItemTake_Source(take, source)
  local length = reaper.GetMediaSourceLength(source)
  reaper.SetMediaItemPosition(item, 0.0, false)
  reaper.SetMediaItemLength(item, length, false)
  reaper.SetMediaItemInfo_Value(item, "D_FADEINLEN", fade_time)
  reaper.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", fade_time)
  local gain = 10 ^ (gain_db / 20)
  reaper.SetMediaItemTakeInfo_Value(take, "D_VOL", gain)
  reaper.UpdateItemInProject(item)
  log("[LOAD] " .. file_path:match("[^/]+$") .. " (+" .. gain_db .. "dB)")
  return true
end

local function reposition_all_tracks()
  local loop_start, loop_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  -- If no loop set or loop too short, use project length or default 20 min
  if loop_end - loop_start < 60 then
    loop_start = 0
    loop_end = math.max(reaper.GetProjectLength(0), 1200)  -- 20 min default
    log("[INFO] No loop set, using " .. string.format("%.0f", loop_end) .. "s timeline")
  end
  for t = 0, num_tracks - 1 do
    local track = reaper.GetTrack(0, t)
    if track then
      local item_ranges = {}
      for i = 0, reaper.CountTrackMediaItems(track) - 1 do
        local item = reaper.GetTrackMediaItem(track, i)
        if item then
          local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
          local safe_fade = math.min(fade_time, item_len / 2)
          reaper.SetMediaItemInfo_Value(item, "D_FADEINLEN", safe_fade)
          reaper.SetMediaItemInfo_Value(item, "D_FADEOUTLEN", safe_fade)

          local tries, max_tries = 0, 100
          local pos_ok, new_pos = false, nil
          while tries < max_tries and not pos_ok do
            local adjusted_start = math.max(loop_start, project_min_time)
            local avail = loop_end - adjusted_start - item_len
            if avail <= 0 then break end
            new_pos = adjusted_start + math.random() * avail
            pos_ok = true
            for _, r in ipairs(item_ranges) do
              if new_pos < r[2] + min_gap and new_pos + item_len > r[1] - min_gap then
                pos_ok = false
                break
              end
            end
            tries = tries + 1
          end

          if pos_ok then
            reaper.SetMediaItemInfo_Value(item, "D_POSITION", new_pos)
            table.insert(item_ranges, {new_pos, new_pos + item_len})
            log("[POS]  Track " .. (t+1) .. " -> " .. string.format("%.1fs", new_pos))
          else
            log("[WARN] Track " .. (t+1) .. ": no gap-safe position after " .. max_tries .. " tries")
          end
        end
      end
    end
  end
  reaper.UpdateArrange()
end

local function files_changed(new_files, old_files)
  if #new_files ~= #old_files then return true end
  for i = 1, #new_files do
    if new_files[i] ~= old_files[i] then return true end
  end
  return false
end

local function tracks_are_empty()
  for t = 0, num_tracks - 1 do
    local track = reaper.GetTrack(0, t)
    if track and reaper.CountTrackMediaItems(track) == 0 then
      return true
    end
  end
  return false
end

local function do_load_and_reposition(files)
  if #files == 0 then
    log("[WARN] No sonification files found in: " .. folder)
    return
  end
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  for i = 1, num_tracks do
    local track = reaper.GetTrack(0, i - 1)
    if track then
      clear_track(track)
      if files[i] then load_file_on_track(track, files[i]) end
    end
  end
  reaper.PreventUIRefresh(-1)
  reaper.Undo_EndBlock("Load POPO files", -1)
  reposition_all_tracks()
end

-- Loop state
local last_play_pos = reaper.GetPlayPosition()
local last_files = {}

local function monitor_loop()
  local play_pos = reaper.GetPlayPosition()
  local playing  = reaper.GetPlayState() & 1 == 1
  local _, loop_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)

  if playing and last_play_pos < loop_end and play_pos < last_play_pos then
    local files = get_newest_files(num_tracks)
    if show_console then
      reaper.ClearConsole()
      reaper.ShowConsoleMsg("\n=== POPO AutoLoop Tracks 1-4 ===\n")
      reaper.ShowConsoleMsg("Folder: " .. folder .. "\n\n")
    end

    if files_changed(files, last_files) or tracks_are_empty() then
      log("New files or empty tracks - loading...\n")
      do_load_and_reposition(files)
      last_files = files
    else
      log("No new files - repositioning existing items.\n")
      reposition_all_tracks()
    end
  end

  last_play_pos = play_pos
  reaper.defer(monitor_loop)
end

-- INIT
math.randomseed(os.time())
if show_console then
  reaper.ClearConsole()
  reaper.ShowConsoleMsg("\n=== POPO AutoLoop Tracks 1-4 ===\n")
  reaper.ShowConsoleMsg("Folder: " .. folder .. "\n\n")
end
local init_files = get_newest_files(num_tracks)
log("Initial load on startup...\n")
do_load_and_reposition(init_files)
last_files = init_files
monitor_loop()
