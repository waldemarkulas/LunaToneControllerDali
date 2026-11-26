"""
Testy CLI bez sprzętu. Prawdziwy adapter zastępuje atrapa FakeDriver.

Uruchomienie (z katalogu głównego repo):
    python -m pytest -v
"""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dali_lunatonev2 as app  # noqa: E402
from dali.gear.general import DAPC, RecallMaxLevel  # noqa: E402


class FakeLineStatus:
    def __init__(self, bus_voltage_error=False):
        self.bus_voltage_error = bus_voltage_error


class FakeResponse:
    def __init__(self, value):
        self.value = value


class FakeDriver:
    """Zachowuje się jak DriverLubaRs232 na tyle, na ile potrzebuje CLI."""

    instances = []
    bus_voltage_error = False
    connect_error = None

    def __init__(self, uri, bus_power=False):
        self.uri = uri
        self.bus_power = bus_power
        self.connect_kwargs = None
        self.sent = []
        self._transport = None
        FakeDriver.instances.append(self)

    async def connect(self, apply_settings=True):
        if FakeDriver.connect_error:
            raise FakeDriver.connect_error
        self.connect_kwargs = {"apply_settings": apply_settings}

    async def read_status(self):
        return FakeLineStatus(FakeDriver.bus_voltage_error)

    async def send(self, cmd):
        self.sent.append(cmd)
        return FakeResponse(0)


@pytest.fixture(autouse=True)
def fake_driver(monkeypatch):
    FakeDriver.instances = []
    FakeDriver.bus_voltage_error = False
    FakeDriver.connect_error = None
    monkeypatch.setattr(app, "DriverLubaRs232", FakeDriver)
    return FakeDriver


def run_cli(*argv):
    """Uruchamia komendę tak jak CLI i zwraca (kod wyjścia, linie wyjścia)."""
    lines = []
    args = app.build_parser().parse_args(list(argv))
    code = asyncio.run(app.run(args, out=lines.append))
    return code, lines


def test_import_prints_nothing():
    result = subprocess.run(
        [sys.executable, "-c", "import dali_lunatonev2"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_psu_on_passes_bus_power_to_driver_and_applies_settings(fake_driver):
    code, lines = run_cli("--port", "COM4", "psu-on")

    assert code == 0
    drv = fake_driver.instances[0]
    assert drv.uri == "luba232:COM4"
    assert drv.bus_power is True
    assert drv.connect_kwargs == {"apply_settings": True}
    assert lines == ["PSU ON"]


def test_psu_off_turns_bus_power_off(fake_driver):
    code, lines = run_cli("--port", "COM4", "psu-off")

    assert code == 0
    drv = fake_driver.instances[0]
    assert drv.bus_power is False
    assert drv.connect_kwargs == {"apply_settings": True}
    assert lines == ["PSU OFF"]


def test_status_is_read_only_and_reports_bus_voltage(fake_driver):
    code, lines = run_cli("--port", "COM4", "status")

    assert code == 0
    assert fake_driver.instances[0].connect_kwargs == {"apply_settings": False}
    assert any("Bus voltage    : OK" in line for line in lines)


def test_status_reports_bus_voltage_error(fake_driver):
    fake_driver.bus_voltage_error = True

    code, lines = run_cli("--port", "COM4", "status")

    assert code == 0
    assert any("Bus voltage    : ERROR" in line for line in lines)


def test_psu_keep_does_not_apply_settings(fake_driver):
    code, _ = run_cli("--port", "COM4", "--psu", "keep", "on", "--address", "0")

    assert code == 0
    drv = fake_driver.instances[0]
    assert drv.connect_kwargs == {"apply_settings": False}
    assert any(isinstance(cmd, RecallMaxLevel) for cmd in drv.sent)


def test_default_psu_mode_is_on(fake_driver):
    run_cli("--port", "COM4", "on", "--address", "1")

    drv = fake_driver.instances[0]
    assert drv.bus_power is True
    assert drv.connect_kwargs == {"apply_settings": True}


def test_level_sends_dapc_with_value(fake_driver):
    code, lines = run_cli("--port", "COM4", "level", "--address", "5", "--value", "127")

    assert code == 0
    sent = fake_driver.instances[0].sent
    assert len(sent) == 1 and isinstance(sent[0], DAPC)
    assert lines == ["ADDRESS 5 LEVEL 127"]


def test_address_out_of_range_is_rejected():
    with pytest.raises(SystemExit):
        app.build_parser().parse_args(["on", "--address", "64"])


def test_level_out_of_range_is_rejected():
    with pytest.raises(SystemExit):
        app.build_parser().parse_args(["level", "--address", "0", "--value", "255"])


def test_all_level_accepts_upper_bound():
    args = app.build_parser().parse_args(["all-level", "--value", "254"])
    assert args.value == 254


def test_connection_error_returns_exit_code_1(fake_driver, capsys):
    fake_driver.connect_error = IOError("port not found")

    code, _ = run_cli("--port", "COM99", "status")

    assert code == 1
    assert "port not found" in capsys.readouterr().err


def test_supported_article_numbers_are_whitelisted_in_driver():
    from dali.driver.serial import DriverLubaRs232

    for article in (24138215, 24138246, 24166096):
        assert article in DriverLubaRs232.TESTED_ARTICLE_NUMBERS


def test_invalid_psu_mode_is_rejected():
    with pytest.raises(ValueError):
        app.DaliController("COM4", psu="maybe")
