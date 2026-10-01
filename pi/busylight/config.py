"""TOML configuration loading and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Any

MAX_PRINTERS = 8
ROTATIONS = (0, 90, 180, 270)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class HttpConfig:
    bind: str
    port: int
    token: str


@dataclass(frozen=True)
class MicConfig:
    ttl_seconds: float


@dataclass(frozen=True)
class BambuddyConfig:
    base_url: str
    api_key: str
    poll_interval_seconds: float
    timeout_seconds: float


@dataclass(frozen=True)
class PrinterConfig:
    id: int
    index: int  # 1-based position in the config list
    color: tuple[int, int, int]


@dataclass(frozen=True)
class Config:
    brightness: float
    rotation: int
    http: HttpConfig
    mic: MicConfig
    bambuddy: BambuddyConfig
    printers: tuple[PrinterConfig, ...]


def _get(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"missing {where}{key}")
    return table[key]


def _table(table: dict[str, Any], key: str) -> dict[str, Any]:
    value = _get(table, key, "")
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    return float(value)


def _positive(value: Any, name: str) -> float:
    number = _number(value, name)
    if number <= 0:
        raise ConfigError(f"{name} must be > 0")
    return number


def _nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _color(value: Any, name: str) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise ConfigError(f"{name} must be a list of 3 integers")
    channels = tuple(_int(c, name) for c in value)
    if any(c < 0 or c > 255 for c in channels):
        raise ConfigError(f"{name} values must be in 0..255")
    return channels  # type: ignore[return-value]


def parse_config(data: dict[str, Any]) -> Config:
    brightness = _number(_get(data, "brightness", ""), "brightness")
    if not 0.0 <= brightness <= 1.0:
        raise ConfigError("brightness must be in [0, 1]")
    rotation = _int(_get(data, "rotation", ""), "rotation")
    if rotation not in ROTATIONS:
        raise ConfigError(f"rotation must be one of {ROTATIONS}")

    http_t = _table(data, "http")
    port = _int(_get(http_t, "port", "http."), "http.port")
    if not 0 <= port <= 65535:
        raise ConfigError("http.port must be in 0..65535")
    http = HttpConfig(
        bind=_nonempty_str(_get(http_t, "bind", "http."), "http.bind"),
        port=port,
        token=_nonempty_str(_get(http_t, "token", "http."), "http.token"),
    )

    mic_t = _table(data, "mic")
    mic = MicConfig(ttl_seconds=_positive(_get(mic_t, "ttl_seconds", "mic."), "mic.ttl_seconds"))

    bb_t = _table(data, "bambuddy")
    base_url = _nonempty_str(_get(bb_t, "base_url", "bambuddy."), "bambuddy.base_url")
    if base_url.endswith("/"):
        base_url = base_url[:-1]
    bambuddy = BambuddyConfig(
        base_url=base_url,
        api_key=_nonempty_str(_get(bb_t, "api_key", "bambuddy."), "bambuddy.api_key"),
        poll_interval_seconds=_positive(
            _get(bb_t, "poll_interval_seconds", "bambuddy."), "bambuddy.poll_interval_seconds"
        ),
        timeout_seconds=_positive(_get(bb_t, "timeout_seconds", "bambuddy."), "bambuddy.timeout_seconds"),
    )

    raw_printers = _get(data, "printers", "")
    if not isinstance(raw_printers, list) or not 1 <= len(raw_printers) <= MAX_PRINTERS:
        raise ConfigError(f"[[printers]] must have 1 to {MAX_PRINTERS} entries")
    printers: list[PrinterConfig] = []
    seen: set[int] = set()
    for index, entry in enumerate(raw_printers, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"printers[{index}] must be a table")
        pid = _int(_get(entry, "id", f"printers[{index}]."), f"printers[{index}].id")
        if pid in seen:
            raise ConfigError(f"duplicate printer id {pid}")
        seen.add(pid)
        color = _color(_get(entry, "color", f"printers[{index}]."), f"printers[{index}].color")
        printers.append(PrinterConfig(id=pid, index=index, color=color))

    return Config(
        brightness=brightness,
        rotation=rotation,
        http=http,
        mic=mic,
        bambuddy=bambuddy,
        printers=tuple(printers),
    )


def load_config(path: str) -> Config:
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    return parse_config(data)
