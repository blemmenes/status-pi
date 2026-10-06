# Busy light: Unicorn HAT Mini status display

A Raspberry Pi Zero W with a Pimoroni Unicorn HAT Mini that shows:

- **Solid red** while any Mac app is recording from an audio input (any mic: USB interface, Bluetooth headset, built-in). Playing audio doesn't count. Hammerspoon detects this and POSTs it to the Pi.
- Otherwise, for each [Bambuddy](https://github.com/maziggy/bambuddy) printer that is printing, a **countdown of the time remaining** (`H:MM`) and a **progress bar**. With more than one printer printing, the display cycles every 5 s.
- **Pulsing green** (success) or **pulsing amber** (failed/cancelled) when a print is waiting for its plate to be cleared. Holding **button A for 1 s** calls Bambuddy `clear-plate` for the printer on screen, which lets Bambuddy start the next queued job.
- While a print's countdown is on screen, holding **button X** (top right) **for 1 s** sets that printer's print speed to **sport**, and holding **button Y** (bottom right) **for 1 s** sets it back to **standard**. These are the button labels printed on the board, so `rotation` doesn't change which one is which.

```
hammerspoon/busylight.lua   Mac side: POST /api/mic when an app records audio
hammerspoon/micwatch.swift  Mac side: input-capture detector run by busylight.lua
pi/busylight/               Pi service (stdlib only + unicornhatmini on the Pi)
pi/deploy/                  systemd unit + install script
```

## Screen legend

| Display | Meaning |
| --- | --- |
| Solid red | In a meeting (mic in use) |
| Digits `H:MM` | Print time remaining (hours:minutes, capped at `99:59`), in the printer's configured color. In the row just above the bottom, a dot on the left marks which printer (leftmost = printer 1, two pixels right = printer 2, …). The bottom row is progress. `- - - -` means Bambuddy has no estimate yet. Blinking digits mean the print is paused. Hold X for 1 s for sport speed, Y for standard. |
| Pulsing green / amber | Print finished / failed or cancelled. Clear the plate, then hold A for 1 s. With several printers, a dark cut-out digit shows which one. |
| White flash | Plate cleared, or print speed changed |
| Purple flash | Clear-plate or speed change failed (see `journalctl -u busylight`) |
| Single dim pixel, bottom right | Idle. Grey = Bambuddy reachable, purple = can't reach Bambuddy |

## Bambuddy setup

Bambuddy runs at `http://sinkhole.local:8000/` and manages one printer: **P2S** (Office), id `1`. `config.example.toml` already points at both.

1. In Bambuddy, create an API key with **Read Status** and **Control Printer** permissions. Put it only in `/etc/busylight/config.toml` on the Pi (and the gitignored `pi/config.toml` for Mac dev runs), never in the repo.
2. Turn on **Require plate clear** in Bambuddy's queue settings. Without it, the queue does not wait for the button.
3. If you add a printer, find its numeric id with `GET /api/v1/printers/` and add a `[[printers]]` block.

Check the API from any machine:

```sh
BB=http://sinkhole.local:8000/api/v1 KEY=<key>
curl -s -H "X-API-Key: $KEY" $BB/printers/ | python3 -m json.tool          # ids and names
curl -s -H "X-API-Key: $KEY" $BB/printers/1/status | python3 -m json.tool
```

The status output includes `state`, `progress`, `remaining_time` (minutes), and `awaiting_plate_clear`.

## Pi install

Requires Pi OS Bookworm or newer (Python ≥ 3.11), with the HAT attached.

```sh
sudo apt-get install -y git
git clone <this repo> ~/busylight
cd ~/busylight
sudo pi/deploy/install.sh
sudoedit /etc/busylight/config.toml
sudo systemctl restart busylight
journalctl -u busylight -f
```

The script enables SPI, installs the apt packages, creates a `busylight` system user in the `spi` and `gpio` groups, installs into `/opt/busylight/venv`, and enables `busylight.service`. It's idempotent: to update, `git pull` then rerun `sudo pi/deploy/install.sh`. An existing `/etc/busylight/config.toml` is never overwritten.

### config.toml

See [`pi/config.example.toml`](pi/config.example.toml). Fields:

- `brightness` (0–1) and `rotation` (0/90/180/270). Use `rotation = 180` if the image is upside down for how the Pi is mounted.
- `[http] token`: shared secret; the same value goes in the Mac's `.secrets.json`.
- `[mic] ttl_seconds`: mic-on expires unless Hammerspoon refreshes it (it does every 30 s), so red clears even if the Mac disappears.
- `[bambuddy]`: `base_url` (`http://sinkhole.local:8000/api/v1`), `api_key` (replace `replace-me` with the real key), poll interval, request timeout. The Pi resolves `sinkhole.local` over mDNS (avahi is installed by default on Pi OS); if it can't, use Bambuddy's IP instead.
- `[[printers]]`: one block per printer, in display order, with Bambuddy `id` and the RGB `color` used for its digits.

## Hammerspoon install (Mac)

Requires macOS 14.4+ and the Xcode command line tools (`xcode-select --install`).

```sh
swiftc -O -o hammerspoon/micwatch hammerspoon/micwatch.swift
ln -s "$PWD/hammerspoon/busylight.lua" ~/.hammerspoon/busylight.lua
```

`micwatch` asks CoreAudio once a second whether any process is capturing audio input, so playback through a device that also has a mic (Scarlett, AirPods, …) doesn't turn the light red. `busylight.lua` runs it from next to the symlink's target and restarts it if it exits. Rebuild it after pulling changes to `micwatch.swift`, then reload Hammerspoon.

Add to `~/.hammerspoon/.secrets.json`:

```json
"busylight": { "url": "http://<pi-host>:8080", "token": "<same as http.token>" }
```

In `~/.hammerspoon/init.lua`, right after `secrets.start('.secrets.json')`:

```lua
BusyLight = require('busylight')
BusyLight.start({ ignore = {} })
```

`BusyLight` must be a global so its watchers aren't garbage collected. If an always-on virtual input (Krisp, Loopback, BlackHole, …) keeps the light red, add its exact device name to `ignore`: recording then only counts while some non-ignored input device is running. List names with `hs.inspect(hs.fnutils.map(hs.audiodevice.allInputDevices(), function(d) return d:name() end))` in the Hammerspoon console.

### Moving to a new Mac

Nothing changes on the Pi; it only sees `POST /api/mic` from whichever Mac has the token.

1. **Bring the repo.** This checkout has no git remote, so either push it somewhere first (`git remote add origin …; git push -u origin main`) or let Migration Assistant copy `~/github/status-pi`.
2. **Install the tools**: [Hammerspoon](https://www.hammerspoon.org/) and `xcode-select --install`. macOS 14.4+ is required; any new MacBook qualifies.
3. **Bring `~/.hammerspoon`**: `init.lua` (with the two `BusyLight` lines), `secrets.lua`, and `.secrets.json`. If you start fresh, `.secrets.json` needs the `busylight` entry above; the token is `[http] token` in `/etc/busylight/config.toml` on the Pi.
4. **Rebuild the helper and recreate the symlink** from the repo root, even after Migration Assistant (the binary is gitignored, and the symlink is an absolute path that breaks if the home folder path changes):
   ```sh
   swiftc -O -o hammerspoon/micwatch hammerspoon/micwatch.swift
   ln -sf "$PWD/hammerspoon/busylight.lua" ~/.hammerspoon/busylight.lua
   ```
5. **Launch Hammerspoon and grant Local Network access** when macOS asks (System Settings → Privacy & Security → Local Network → Hammerspoon). Without it every POST fails with `Could not connect to the server`. Privacy permissions don't migrate, so expect the prompt again.
6. **Stop the old Mac.** Quit Hammerspoon there or remove its `BusyLight` lines; otherwise its 30 s heartbeats of `active: false` keep clearing the new Mac's red.
7. **Verify.** The Hammerspoon console should show no `busylight:` errors. Join a test call and the light goes red within about a second; play music with no call and it stays off. Check from the terminal with `curl -s -H 'Authorization: Bearer <token>' status-pi.local:8080/api/state` (`mic_active`).
8. **Optional, Mac dev runs:** set up as in [Development](#development-mac); copy `pi/config.toml` (gitignored, holds the Bambuddy key) or recreate it.

## HTTP API (Pi, port 8080)

All `/api/*` routes require `Authorization: Bearer <token>`.

| Route | Description |
| --- | --- |
| `GET /healthz` | `ok` (no auth) |
| `POST /api/mic` | Body `{"active": true\|false}` → 204 |
| `GET /api/state` | Current screen, mic state, Bambuddy health, last printer snapshots |

```sh
curl -s -XPOST -H 'Authorization: Bearer change-me' -d '{"active":true}' <pi-host>:8080/api/mic
curl -s -H 'Authorization: Bearer change-me' <pi-host>:8080/api/state
```

## Development (Mac)

```sh
cd pi
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
cp config.example.toml config.toml   # gitignored; set api_key
.venv/bin/python -m busylight --config config.toml --fake-display
```

`--fake-display` draws the panel in the terminal with ANSI colors (logs go to stderr). Typing `a`, `x`, or `y` + Enter acts as holding that button.

## Troubleshooting

- **Button never fires but the display works**: pin-factory conflict on GPIO 7/8. Add `Environment=GPIOZERO_PIN_FACTORY=rpigpio` to `pi/deploy/busylight.service` and rerun the install script.
- **Purple idle pixel**: the Pi can't reach Bambuddy. Check `base_url`/`api_key` and `journalctl -u busylight`.
