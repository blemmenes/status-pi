-- BUSY LIGHT
--
-- Reports "some app is recording audio input" to the Raspberry Pi busy light.
-- Playback never counts, even on devices with both input and output (USB
-- interfaces, Bluetooth headsets). Detection runs in the `micwatch` helper next
-- to this file's real path; build it with:
--   swiftc -O -o hammerspoon/micwatch hammerspoon/micwatch.swift
-- Needs `busylight = { url = "http://<pi-host>:8080", token = "<http.token>" }`
-- in ~/.hammerspoon/.secrets.json (loaded by secrets.lua into hs.settings "secrets").
--
-- Usage (keep the global so watchers are not garbage collected):
--   BusyLight = require('busylight')
--   BusyLight.start({ ignore = { "BlackHole 2ch" } })

local M = {}

M.devices = {}   -- UID -> hs.audiodevice; must stay referenced, watcher state lives on the object
M.lastSent = nil
M.ignore = {}
M.inputActive = false   -- latest micwatch report: some process is capturing audio input
M.helper = nil          -- running micwatch hs.task

local HEARTBEAT_SECONDS = 30
local HELPER_RESTART_SECONDS = 5

local url, token

-- Real path (follows the ~/.hammerspoon symlink) so the helper is found in the repo.
local helperPath = hs.fs.pathToAbsolute(debug.getinfo(1, "S").source:sub(2)):match("^(.*)/") .. "/micwatch"

local function anyInUse()
  if not M.inputActive then
    return false
  end
  if next(M.ignore) == nil then
    return true
  end
  -- Capture is process-wide; only count it if a non-ignored input device is running.
  for _, dev in pairs(M.devices) do
    if not M.ignore[dev:name()] and dev:inUse() then
      return true
    end
  end
  return false
end

local function send(active)
  M.lastSent = active
  hs.http.asyncPost(
    url .. "/api/mic",
    hs.json.encode({ active = active }),
    { ["Authorization"] = "Bearer " .. token, ["Content-Type"] = "application/json" },
    function(status, body)
      if status ~= 204 then
        print("busylight: POST /api/mic -> " .. tostring(status) .. " " .. tostring(body))
      end
    end
  )
end

function M.evaluate()
  local a = anyInUse()
  if a ~= M.lastSent then
    send(a)
  end
end

local function rebuild()
  for _, dev in pairs(M.devices) do
    pcall(function() dev:watcherStop() end)
    dev:watcherCallback(nil)
  end
  M.devices = {}
  for _, dev in ipairs(hs.audiodevice.allInputDevices()) do
    dev:watcherCallback(function(_, event)
      if event == "gone" then M.evaluate() end
    end)
    dev:watcherStart()
    M.devices[dev:uid()] = dev
  end
end

local function startHelper()
  local task
  task = hs.task.new(helperPath, function(code, _, stderr)
    if M.helper ~= task then
      return
    end
    M.helper = nil
    print("busylight: micwatch exited (" .. tostring(code) .. ") " .. tostring(stderr)
      .. "; restarting in " .. HELPER_RESTART_SECONDS .. " s")
    M.inputActive = false
    M.evaluate()
    M.helperRestart = hs.timer.doAfter(HELPER_RESTART_SECONDS, startHelper)
  end, function(_, stdout)
    local last = stdout and stdout:match("([01])%s*$")
    if last then
      M.inputActive = last == "1"
      M.evaluate()
    end
    return true
  end)
  M.helper = task
  task:start()
end

function M.start(opts)
  opts = opts or {}
  local secrets = hs.settings.get("secrets")
  local cfg = secrets and secrets.busylight
  if not (cfg and cfg.url and cfg.token) then
    print("busylight: add busylight.url/token to .secrets.json")
    return
  end
  url = cfg.url:gsub("/+$", "")
  token = cfg.token
  if not hs.fs.attributes(helperPath) then
    print("busylight: missing " .. helperPath .. "; build it: swiftc -O -o " .. helperPath .. " " .. helperPath .. ".swift")
    return
  end

  M.ignore = {}
  for _, name in ipairs(opts.ignore or {}) do
    M.ignore[name] = true
  end

  hs.audiodevice.watcher.setCallback(function(ev)
    if ev == "dev#" then
      rebuild()
      M.evaluate()
    end
  end)
  hs.audiodevice.watcher.start()

  -- Always send: refreshes the Pi's TTL and repairs any missed event.
  M.timer = hs.timer.doEvery(HEARTBEAT_SECONDS, function() send(anyInUse()) end)

  M.sleep = hs.caffeinate.watcher.new(function(ev)
    if ev == hs.caffeinate.watcher.systemWillSleep then
      send(false)
    elseif ev == hs.caffeinate.watcher.systemDidWake then
      rebuild()
      M.lastSent = nil
      M.evaluate()
    end
  end):start()

  rebuild()
  startHelper()
  send(anyInUse())
end

return M
