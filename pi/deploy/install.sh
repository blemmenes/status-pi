#!/usr/bin/env bash
# Install or update the busy light service. Run as root from the repo checkout on the Pi:
#   sudo pi/deploy/install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

PI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX=/opt/busylight
CONF_DIR=/etc/busylight
CONF="$CONF_DIR/config.toml"

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3,11))'; then
  echo "Pi OS Bookworm or newer required (Python >= 3.11)" >&2
  exit 1
fi

raspi-config nonint do_spi 0

GPIO_PKG=python3-rpi.gpio
if apt-cache policy python3-rpi.gpio | grep -q 'Candidate: (none)' \
  || [[ -z "$(apt-cache policy python3-rpi.gpio)" ]]; then
  GPIO_PKG=python3-rpi-lgpio
fi
apt-get install -y python3-venv python3-spidev python3-gpiozero "$GPIO_PKG" rsync

id busylight >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin busylight
usermod -aG spi,gpio busylight

mkdir -p "$PREFIX"
rsync -a --delete --exclude .venv --exclude config.toml "$PI_DIR/" "$PREFIX/src/"
python3 -m venv --system-site-packages "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install "$PREFIX/src[pi]"
# Same version number on update: force the package itself (not its deps) to refresh.
"$PREFIX/venv/bin/pip" install --force-reinstall --no-deps "$PREFIX/src"

mkdir -p "$CONF_DIR"
if [[ ! -f "$CONF" ]]; then
  cp "$PI_DIR/config.example.toml" "$CONF"
  NEW_CONFIG=1
else
  NEW_CONFIG=0
fi
chown root:busylight "$CONF"
chmod 640 "$CONF"

install -m 644 "$PI_DIR/deploy/busylight.service" /etc/systemd/system/busylight.service
systemctl daemon-reload
systemctl enable busylight
systemctl restart busylight

if [[ $NEW_CONFIG -eq 1 ]]; then
  echo "edit $CONF then: systemctl restart busylight"
fi
