"""
Testy odczytu ID i skanu banków pamięci na symulowanej magistrali.

Symulator zachowuje się jak oprawa: obsługuje DTR0, DTR1 i ReadMemoryLocation
z auto-inkrementacją DTR0 (tak jak w IEC 62386). Nie zastępuje testu na sprzęcie.
"""

import asyncio
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dali_lunatonev2 as app  # noqa: E402
from dali.gear.general import DTR0, DTR1, ReadMemoryLocation  # noqa: E402


class SimBus:
    """Symulowana oprawa z bankami pamięci: {numer banku: [bajty albo None]}."""

    def __init__(self, banks):
        self.banks = banks
        self.dtr0 = 0
        self.dtr1 = 0
        self.log = []

    def _handle(self, cmd):
        name = type(cmd).__name__
        if isinstance(cmd, DTR0):
            self.dtr0 = cmd.param
            return None
        if isinstance(cmd, DTR1):
            self.dtr1 = cmd.param
            return None
        if isinstance(cmd, ReadMemoryLocation):
            self.log.append((self.dtr1, self.dtr0))
            bank = self.banks.get(self.dtr1)
            value = None
            if bank is not None and self.dtr0 < len(bank):
                value = bank[self.dtr0]
            self.dtr0 = min(self.dtr0 + 1, 255)
            if value is None:
                return SimpleNamespace(raw_value=None)
            return SimpleNamespace(
                raw_value=SimpleNamespace(as_integer=value, error=False)
            )
        raise AssertionError(f"nieoczekiwana komenda: {name}")

    async def send(self, msg):
        if inspect.isgenerator(msg):
            try:
                cmd = next(msg)
                while True:
                    cmd = msg.send(self._handle(cmd))
            except StopIteration as stop:
                return stop.value
        return self._handle(msg)


def make_bank0():
    # loc 0: ostatni adres, loc 2: ostatni bank, loc 3-8: GTIN, loc 9-10: firmware,
    # loc 0x0B-0x12: numer seryjny
    gtin = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05]
    firmware = [0x01, 0x07]
    serial = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2A]
    return [0x12, 0x00, 0x02] + gtin + firmware + serial


def test_identity_reads_gtin_serial_and_firmware():
    bus = SimBus({0: make_bank0()})
    ctrl = app.DaliController()
    ctrl.driver = bus

    result = asyncio.run(ctrl.gear_identity(0))

    assert result["gtin"] == int.from_bytes(bytes([0, 1, 2, 3, 4, 5]), "big")
    assert result["serial"] == 0x2A
    assert "ERROR" not in str(result["firmware"])


def test_memory_scan_reads_all_banks_until_last():
    bank1 = [0x03, 0xAA, 0xBB, 0xCC]  # ostatni adres 3 -> 4 bajty (0..3)
    bank2 = [0x02, 0x10, 0x20]  # ostatni adres 2 -> 3 bajty
    bus = SimBus({0: make_bank0(), 1: bank1, 2: bank2})  # bank 3 nie istnieje
    ctrl = app.DaliController()
    ctrl.driver = bus

    result = asyncio.run(ctrl.memory_scan(0))

    assert result["last_bank"] == 2
    assert result["banks"][1] == bank1
    assert result["banks"][2] == bank2
    assert result["banks"][0][:3] == [0x12, 0x00, 0x02]


def test_memory_scan_marks_missing_locations_as_none():
    bank1 = [0x03, 0xAA, None, 0xCC]
    bus = SimBus({0: [0x02, 0x00, 0x01], 1: bank1})  # ostatni bank = 1
    ctrl = app.DaliController()
    ctrl.driver = bus

    result = asyncio.run(ctrl.memory_scan(0))

    assert result["banks"][1] == bank1


def test_hexdump_formats_rows_and_gaps():
    lines = app.hexdump([0x0A, None, 0xFF] + list(range(16)), width=16)

    assert lines[0].startswith("  00: 0A -- FF 00 01")
    assert len(lines) == 2
    assert lines[1].startswith("  10:")
