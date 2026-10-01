import http.client
import json
import time

import pytest

from busylight.config import parse_config
from busylight.http_api import start_http_server
from busylight.state import AppState

TOKEN = "s3cret"


@pytest.fixture
def server_state():
    cfg = parse_config(
        {
            "brightness": 0.5,
            "rotation": 0,
            "http": {"bind": "127.0.0.1", "port": 0, "token": TOKEN},
            "mic": {"ttl_seconds": 90},
            "bambuddy": {
                "base_url": "http://127.0.0.1:9/api/v1",
                "api_key": "k",
                "poll_interval_seconds": 10,
                "timeout_seconds": 1,
            },
            "printers": [{"id": 1, "color": [1, 2, 3]}],
        }
    )
    state = AppState(cfg.bambuddy.poll_interval_seconds)
    server = start_http_server(cfg, state)
    yield server, state
    server.shutdown()
    server.server_close()


def request(server, method, path, body=None, token=TOKEN):
    host, port = server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_mic_requires_token(server_state):
    server, state = server_state
    assert request(server, "POST", "/api/mic", b'{"active":true}', token=None)[0] == 401
    assert request(server, "POST", "/api/mic", b'{"active":true}', token="wrong")[0] == 401
    assert not state.view(time.monotonic()).mic_active


def test_mic_rejects_non_bool(server_state):
    server, _ = server_state
    status, body = request(server, "POST", "/api/mic", b'{"active":"yes"}')
    assert status == 400
    assert json.loads(body) == {"error": 'expected {"active": bool}'}


def test_mic_rejects_oversized_body(server_state):
    server, _ = server_state
    assert request(server, "POST", "/api/mic", b"x" * 2000)[0] == 413


def test_mic_sets_state(server_state):
    server, state = server_state
    assert request(server, "POST", "/api/mic", b'{"active":true}')[0] == 204
    assert state.view(time.monotonic()).mic_active
    assert request(server, "POST", "/api/mic", b'{"active":false}')[0] == 204
    assert not state.view(time.monotonic()).mic_active


def test_healthz_without_auth(server_state):
    server, _ = server_state
    assert request(server, "GET", "/healthz", token=None) == (200, b"ok")


def test_state_reports_configured_printers(server_state):
    server, _ = server_state
    status, body = request(server, "GET", "/api/state")
    assert status == 200
    payload = json.loads(body)
    assert payload["screen"] == "idle"
    assert [p["id"] for p in payload["printers"]] == [1]
