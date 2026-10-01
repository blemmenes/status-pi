-- BUSY LIGHT
--
-- Reports "any audio input device in use" to the Raspberry Pi busy light.
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

local HEARTBEAT_SECONDS = 30

local url, token

local function anyInUse()
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
  send(anyInUse())
end

return M
