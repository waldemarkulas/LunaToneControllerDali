"""
Testy interfejsu webowego na atrapie sterownika (bez sprzętu).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dali_lunatonev2 as dali  # noqa: E402
import web_app  # noqa: E402


class FakeResponse:
    def __init__(self, value):
        self.value = value


class FakeDriver:
    instances = []
    connect_error = None

    def __init__(self, uri, bus_power=False):
        self.uri = uri
        self.bus_power = bus_power
        self._transport = None
        self._protocol = SimpleNamespace(device_info=SimpleNamespace(article_num=24138215))
        FakeDriver.instances.append(self)

    async def connect(self, apply_settings=True):
        if FakeDriver.connect_error:
            raise FakeDriver.connect_error

    async def read_status(self):
        return SimpleNamespace(bus_voltage_error=False)

    async def send(self, cmd):
        return FakeResponse(0)


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeDriver.instances = []
    FakeDriver.connect_error = None
    monkeypatch.setattr(dali, "DriverLubaRs232", FakeDriver)
    monkeypatch.setattr(web_app, "WEB_TOKEN", "")
    return FakeDriver


@pytest.fixture
def client():
    with TestClient(web_app.app) as c:
        yield c


def test_index_serves_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Sterowanie DALI" in res.text


def test_commands_catalog_matches_cli_parser(client):
    res = client.get("/api/commands")
    assert res.status_code == 200
    ids = {c["id"] for c in res.json()["commands"]}

    parser = dali.build_parser()
    cli_commands = set(parser._subparsers._group_actions[0].choices)
    # cmd i list-cmds są obsługiwane przez katalog, nie przez przyciski
    assert ids == cli_commands - {"cmd", "list-cmds"}


def test_status_runs_and_returns_output(client, fake):
    res = client.post("/api/run", json={"command": "status"})

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert any("Bus voltage" in line for line in body["output"])
    assert fake.instances[0].uri == f"luba232:{dali.DEFAULT_PORT}"


def test_level_sends_value(client):
    res = client.post("/api/run", json={"command": "level", "address": 3, "value": 127})

    assert res.status_code == 200
    assert res.json()["output"] == ["ADDRESS 3 LEVEL 127"]


def test_level_without_value_is_400(client):
    res = client.post("/api/run", json={"command": "level", "address": 3})
    assert res.status_code == 400


def test_value_out_of_range_is_400(client):
    res = client.post("/api/run", json={"command": "all-level", "value": 300})
    assert res.status_code == 400


def test_address_out_of_range_is_400(client):
    res = client.post("/api/run", json={"command": "on", "address": 64})
    assert res.status_code == 400


def test_unknown_command_is_400(client):
    res = client.post("/api/run", json={"command": "format-disk"})
    assert res.status_code == 400


def test_client_cannot_choose_port(client, fake):
    res = client.post(
        "/api/run",
        json={"command": "status", "port": "/dev/sda"},
    )

    assert res.status_code == 200
    assert fake.instances[0].uri == f"luba232:{dali.DEFAULT_PORT}"


def test_driver_error_is_reported_not_raised(client, fake):
    fake.connect_error = IOError("port not found")

    res = client.post("/api/run", json={"command": "status"})

    body = res.json()
    assert res.status_code == 200
    assert body["ok"] is False
    assert any("port not found" in line for line in body["errors"])


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(web_app, "WEB_TOKEN", "secret-token")

    assert client.get("/api/commands").status_code == 401
    assert client.post("/api/run", json={"command": "status"}).status_code == 401
    assert client.get(
        "/api/commands", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401
    assert client.get(
        "/api/commands", headers={"Authorization": "Bearer secret-token"}
    ).status_code == 200
