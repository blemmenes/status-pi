# Busy light: Unicorn HAT Mini status display

A Raspberry Pi Zero W with a Pimoroni Unicorn HAT Mini that shows:

- **Solid red** while any MacBook audio input is in use. Hammerspoon detects this and POSTs it to the Pi.
- Otherwise, for each [Bambuddy](https://github.com/maziggy/bambuddy) printer that is printing, the **12-hour completion time** and a **progress bar**. With more than one printer printing, the display cycles every 5 s.
- **Pulsing green** (success) or **pulsing amber** (failed/cancelled) when a print is waiting for its plate to be cleared. Holding **button A for 1 s** calls Bambuddy `clear-plate` for the printer on screen, which lets Bambuddy start the next queued job.

```
hammerspoon/busylight.lua   Mac side: mic watcher -> POST /api/mic
pi/busylight/               Pi service (stdlib only + unicornhatmini on the Pi)
pi/deploy/                  systemd unit + install script
```

## Screen legend

| Display | Meaning |
| --- | --- |
| Solid red | In a meeting (mic in use) |
| Digits `H:MM` | Print completion time, in the printer's configured color. In the row just above the bottom: a dot on the left marks which printer (leftmost = printer 1, two pixels right = printer 2, …) and a white dot at the far right means PM. The bottom row is progress. `- - - -` means Bambuddy has no estimate yet. Blinking digits mean the print is paused. |
| Pulsing green / amber | Print finished / failed or cancelled. Clear the plate, then hold A for 1 s. With several printers, a dark cut-out digit shows which one. |
| White flash | Plate cleared |
| Purple flash | Clear-plate failed (see `journalctl -u busylight`) |
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

The ETA uses the Pi's timezone: `sudo timedatectl set-timezone America/Detroit`.

### config.toml

See [`pi/config.example.toml`](pi/config.example.toml). Fields:

- `brightness` (0–1) and `rotation` (0/90/180/270). Use `rotation = 180` if the image is upside down for how the Pi is mounted.
- `[http] token`: shared secret; the same value goes in the Mac's `.secrets.json`.
- `[mic] ttl_seconds`: mic-on expires unless Hammerspoon refreshes it (it does every 30 s), so red clears even if the Mac disappears.
- `[bambuddy]`: `base_url` (`http://sinkhole.local:8000/api/v1`), `api_key` (replace `replace-me` with the real key), poll interval, request timeout. The Pi resolves `sinkhole.local` over mDNS (avahi is installed by default on Pi OS); if it can't, use Bambuddy's IP instead.
- `[[printers]]`: one block per printer, in display order, with Bambuddy `id` and the RGB `color` used for its digits.

## Hammerspoon install (Mac)

```sh
ln -s "$PWD/hammerspoon/busylight.lua" ~/.hammerspoon/busylight.lua
```

Add to `~/.hammerspoon/.secrets.json`:

```json
"busylight": { "url": "http://<pi-host>:8080", "token": "<same as http.token>" }
```

In `~/.hammerspoon/init.lua`, right after `secrets.start('.secrets.json')`:

```lua
BusyLight = require('busylight')
BusyLight.start({ ignore = {} })
```

`BusyLight` must be a global so its watchers aren't garbage collected. If an always-on virtual input (Krisp, Loopback, BlackHole, …) keeps the light red, add its exact device name to `ignore`. List names with `hs.inspect(hs.fnutils.map(hs.audiodevice.allInputDevices(), function(d) return d:name() end))` in the Hammerspoon console.

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

`--fake-display` draws the panel in the terminal with ANSI colors (logs go to stderr), and typing `a` + Enter acts as holding button A.

## Troubleshooting

- **Button never fires but the display works**: pin-factory conflict on GPIO 7/8. Add `Environment=GPIOZERO_PIN_FACTORY=rpigpio` to `pi/deploy/busylight.service` and rerun the install script.
- **Purple idle pixel**: the Pi can't reach Bambuddy. Check `base_url`/`api_key` and `journalctl -u busylight`.
