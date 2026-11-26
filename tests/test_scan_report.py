"""
Testy pełnego skanu urządzenia: dekodowanie banków, raport, zapis do pliku
z CLI i endpoint web. Na symulowanej oprawie (bez sprzętu).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dali_lunatonev2 as app  # noqa: E402
import dali_memory  # noqa: E402
import web_app  # noqa: E402
from test_memory import SimBus, make_bank0  # noqa: E402


class SimDriver(SimBus):
    """Symulowany DriverLubaRs232: banki 0, 1 i 2."""

    def __init__(self, uri, bus_power=False):
        super().__init__({
            0: make_bank0(),
            1: [0x03, 0xAA, 0xBB, 0xCC],
            2: [0x02, 0x10, 0x20],
        })
        self._transport = None
        self._protocol = SimpleNamespace(device_info=SimpleNamespace(
            gtin=1234, id=99, pcb_ver=1, assembly_ver=2, article_num=24138215,
        ))

    async def connect(self, apply_settings=True):
        return None


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setattr(app, "DriverLubaRs232", SimDriver)
    monkeypatch.setattr(web_app, "WEB_TOKEN", "")
    return SimDriver


def test_bank0_is_decoded_with_library_names():
    banks = dali_memory.analyse_scan({"last_bank": 0, "banks": {0: make_bank0()}})
    bank0 = banks[0]

    names = {r["name"]: r for r in bank0["rows"]}
    assert "GTIN" in names and names["GTIN"]["value"] is not None
    assert "IdentificationNumber" in names
    assert "FirmwareVersion" in names


def test_missing_bank_is_marked_as_not_existing():
    banks = dali_memory.analyse_scan({"last_bank": 1, "banks": {0: make_bank0(), 1: None}})

    assert banks[1]["exists"] is False
    assert banks[1]["rows"] == []


def test_report_contains_version_identity_and_banks():
    from dali_version import APP_VERSION

    banks = dali_memory.analyse_scan({"last_bank": 1, "banks": {0: make_bank0(), 1: [0x01, 0xAA]}})
    report = dali_memory.format_report(
        0, {"gtin": 1, "serial": 42, "firmware": "1.7"},
        {"gtin": 1234, "id": 99, "article_num": 24138215}, banks, 1,
    )
    text = "\n".join(report)

    assert APP_VERSION in text
    assert "BANK 0:" in text and "BANK 1:" in text
    assert "Numer seryjny         : 42" in text
    assert "24138215" in text


def test_cli_device_scan_writes_txt(sim, tmp_path, capsys):
    out = tmp_path / "raport.txt"
    args = app.build_parser().parse_args(
        ["--port", "COM4", "device-scan", "--address", "0", "--out", str(out)]
    )
    import asyncio
    code = asyncio.run(app.run(args))

    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "SKAN URZĄDZENIA DALI" in text
    assert "BANK 2:" in text
    assert "Zapisano raport" in capsys.readouterr().out


def test_web_scan_endpoint_returns_banks_and_report(sim):
    with TestClient(web_app.app) as client:
        res = client.post("/api/scan-device", json={"address": 0})

    body = res.json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["last_bank"] == 2
    assert [b["number"] for b in body["banks"]] == [0, 1, 2]
    assert any("BANK 1:" in line for line in body["report"])


def test_web_scan_rejects_bad_address(sim):
    with TestClient(web_app.app) as client:
        res = client.post("/api/scan-device", json={"address": 99})

    assert res.status_code == 400


def test_report_skips_unimplemented_values_but_counts_them():
    banks = dali_memory.analyse_scan({"last_bank": 0, "banks": {0: make_bank0()}})
    text = "\n".join(dali_memory.format_report(0, {}, None, banks, 0))

    assert "HardwareVersion" not in text
    assert "pominięto" in text
