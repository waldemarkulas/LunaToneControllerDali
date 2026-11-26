"""
Sterowanie magistralą DALI przez interfejs Lunatone DALI-2 USB (protokół LUBA).

Dwie warstwy:
  * DaliController  - logika bez wypisywania na ekran. Zwraca dane, więc
                      można jej użyć z CLI, z aplikacji webowej albo z testów.
  * main()/CLI      - parsuje argumenty, wywołuje kontroler i drukuje wynik.

Przykłady:
  python dali_lunatonev2.py --port COM4 status
  python dali_lunatonev2.py --port COM4 device-id
  python dali_lunatonev2.py --port COM4 device-id --address 0
  python dali_lunatonev2.py --port COM4 memory-scan --address 0
  python dali_lunatonev2.py --port COM4 level --address 0 --value 127
  python dali_lunatonev2.py list-cmds --filter DAPC
  python dali_lunatonev2.py --port COM4 cmd --id dali.gear.general.Off --kind short --address 0

Kody wyjścia: 0 = OK, 1 = błąd (opis na stderr), 2 = zły argument.
Każde wykonanie (poza list-cmds) jest zapisywane w logs/dali-RRRR-MM-DD.txt.
"""

import argparse
import asyncio
import os
import sys

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort, GearBroadcast

from dali.gear.general import (
    Off,
    RecallMaxLevel,
    DAPC,
    DTR0,
    DTR1,
    QueryActualLevel,
    QueryMinLevel,
    QueryMaxLevel,
    QueryStatus,
    QueryControlGearPresent,
    QueryGroupsZeroToSeven,
    QueryGroupsEightToFifteen,
    ReadMemoryLocation,
)

from dali.sequences import QueryDeviceTypes
from dali.memory import info

import dali_catalog
from dali_logging import log_event
from dali_version import APP_VERSION


# Numery artykułów Lunatone, z którymi ten projekt jest używany.
# python-dali ostrzega przy każdym numerze spoza swojej listy TESTED_ARTICLE_NUMBERS,
# więc lista jest tu uzupełniana, żeby ostrzeżenie nie pojawiało się przy każdym
# połączeniu. Nieznany numer nadal wywoła ostrzeżenie biblioteki.
SUPPORTED_ARTICLE_NUMBERS = frozenset({24138215, 24138246, 24166096})

DriverLubaRs232.TESTED_ARTICLE_NUMBERS = (
    frozenset(DriverLubaRs232.TESTED_ARTICLE_NUMBERS) | SUPPORTED_ARTICLE_NUMBERS
)

DEFAULT_PORT = os.environ.get("DALI_PORT") or (
    "COM4" if sys.platform == "win32" else "/dev/ttyUSB0"
)

# psu:
#   "on"   - włącz wewnętrzny zasilacz magistrali (bit 7 HardwareSettings)
#   "off"  - wyłącz wewnętrzny zasilacz
#   "keep" - nie zmieniaj ustawień sprzętowych (np. przy zewnętrznym PSU)
PSU_MODES = ("on", "off", "keep")

ADDRESS_MAX = 63
LEVEL_MAX = 254


class DaliController:
    """Kontroler magistrali DALI. Metody zwracają wyniki, nie drukują."""

    def __init__(self, port: str = DEFAULT_PORT, psu: str = "on"):
        if psu not in PSU_MODES:
            raise ValueError(f"psu musi być jednym z {PSU_MODES}, jest: {psu!r}")

        self.port = port
        self.psu = psu
        self.driver = None
        self.article_number = None

    async def connect(self, apply_settings: bool | None = None) -> None:
        """
        Łączy się z adapterem.

        Ustawienia PSU przekazujemy do konstruktora, a nie ustawiamy ręcznie
        po connect(). Dzięki temu python-dali czeka, aż napięcie na magistrali
        się pojawi, zanim wyśle pierwsze ramki DALI.

        apply_settings=False: połączenie tylko do odczytu, ustawienia sprzętowe
        adaptera (w tym PSU) zostają nietknięte.
        """
        if apply_settings is None:
            apply_settings = self.psu != "keep"

        self.driver = DriverLubaRs232(
            f"luba232:{self.port}",
            bus_power=(self.psu == "on"),
        )
        await self.driver.connect(apply_settings=apply_settings)

        info_ = self.adapter_info()
        self.article_number = info_["article_num"] if info_ else None

    def unsupported_article(self) -> bool:
        """True, gdy adapter ma numer artykułu spoza SUPPORTED_ARTICLE_NUMBERS."""
        return (
            self.article_number is not None
            and self.article_number not in SUPPORTED_ARTICLE_NUMBERS
        )

    async def close(self) -> None:
        transport = getattr(self.driver, "_transport", None)
        if transport is not None:
            transport.close()
        self.driver = None

    # --- identyfikacja ------------------------------------------------------

    def adapter_info(self) -> dict | None:
        """Dane identyfikacyjne samego adaptera LUBA (z połączenia)."""
        device_info = getattr(self.driver._protocol, "device_info", None)
        if device_info is None:
            return None
        return {
            "gtin": getattr(device_info, "gtin", None),
            "id": getattr(device_info, "id", None),
            "pcb_ver": getattr(device_info, "pcb_ver", None),
            "assembly_ver": getattr(device_info, "assembly_ver", None),
            "article_num": getattr(device_info, "article_num", None),
        }

    async def gear_identity(self, address: int) -> dict:
        """ID oprawy z banku 0 pamięci (GTIN, numer seryjny, firmware)."""
        return await self.driver.send(identity_sequence(GearShort(address)))

    async def memory_scan(self, address: int) -> dict:
        """Odczyt wszystkich banków pamięci oprawy (od 0 do ostatniego)."""
        return await self.driver.send(memory_scan_sequence(GearShort(address)))

    # --- ogólne wysłanie komendy --------------------------------------------

    async def send_command(self, command_obj):
        """Wysyła dowolny obiekt komendy python-dali i zwraca odpowiedź (lub None)."""
        return await self.driver.send(command_obj)

    # --- odczyt -----------------------------------------------------------

    async def line_status(self):
        """Zwraca LubaLineStatus albo None, gdy adapter nie odpowiedział."""
        return await self.driver.read_status()

    async def scan(self) -> list[int]:
        """Zwraca listę adresów (0..63), pod którymi odpowiada oprawa."""
        found = []
        for address in range(ADDRESS_MAX + 1):
            try:
                response = await self.driver.send(
                    QueryControlGearPresent(GearShort(address))
                )
            except Exception:
                continue
            if response is not None and response.value:
                found.append(address)
        return found

    async def info(self, address: int) -> dict:
        """Zwraca słownik z danymi oprawy. Błąd pojedynczego zapytania
        trafia jako tekst 'ERROR (...)', nie przerywa pozostałych."""
        addr = GearShort(address)
        result = {"address": address}

        try:
            result["device_types"] = await self.driver.send(QueryDeviceTypes(addr))
        except Exception as ex:
            result["device_types"] = f"ERROR ({ex})"

        queries = [
            ("actual_level", QueryActualLevel),
            ("min_level", QueryMinLevel),
            ("max_level", QueryMaxLevel),
            ("status", QueryStatus),
        ]
        for key, cmd in queries:
            try:
                response = await self.driver.send(cmd(addr))
                result[key] = response.value
            except Exception as ex:
                result[key] = f"ERROR ({ex})"

        return result

    async def groups(self, address: int) -> list[int]:
        """Zwraca listę grup (0..15), do których należy oprawa."""
        addr = GearShort(address)
        low = await self.driver.send(QueryGroupsZeroToSeven(addr))
        high = await self.driver.send(QueryGroupsEightToFifteen(addr))
        if low is None or high is None:
            raise IOError("brak odpowiedzi na zapytanie o grupy")

        groups = [g for g in range(8) if low.value & (1 << g)]
        groups += [g + 8 for g in range(8) if high.value & (1 << g)]
        return groups

    # --- sterowanie -------------------------------------------------------

    async def on(self, address: int) -> None:
        await self.driver.send(RecallMaxLevel(GearShort(address)))

    async def off(self, address: int) -> None:
        await self.driver.send(Off(GearShort(address)))

    async def level(self, address: int, value: int) -> None:
        await self.driver.send(DAPC(GearShort(address), value))

    async def all_on(self) -> None:
        await self.driver.send(RecallMaxLevel(GearBroadcast()))

    async def all_off(self) -> None:
        await self.driver.send(Off(GearBroadcast()))

    async def all_level(self, value: int) -> None:
        await self.driver.send(DAPC(GearBroadcast(), value))


# --- sekwencje odczytu pamięci -----------------------------------------------

def identity_sequence(addr):
    """Sekwencja DALI: GTIN, numer seryjny i wersja firmware z banku 0."""
    result = {}
    for key, value_cls in (
        ("gtin", info.GTIN),
        ("serial", info.IdentificationNumber),
        ("firmware", info.FirmwareVersion),
    ):
        try:
            result[key] = yield from value_cls.read(addr)
        except Exception as ex:
            result[key] = f"ERROR ({ex})"
    return result


def _read_bank(addr, bank: int):
    """
    Sekwencja DALI: czyta cały bank. Lokalizacja 0 zawiera ostatni adres banku.
    Zwraca listę bajtów (None = lokalizacja niezaimplementowana) albo None,
    gdy bank nie istnieje.

    DTR0 jest zwiększany po każdym ReadMemoryLocation, więc kolejne lokalizacje
    czytamy bez ponownego ustawiania DTR0 (tak samo robi python-dali).
    """
    yield DTR1(bank)
    yield DTR0(0)
    response = yield ReadMemoryLocation(addr)
    if response is None or response.raw_value is None:
        return None
    last = response.raw_value.as_integer

    data = [last]
    for _ in range(last):
        response = yield ReadMemoryLocation(addr)
        if response is None or response.raw_value is None:
            data.append(None)
        else:
            data.append(response.raw_value.as_integer)
    return data


def memory_scan_sequence(addr):
    """Sekwencja DALI: skanuje wszystkie banki pamięci oprawy."""
    try:
        last_bank = yield from info.LastMemoryBank.read(addr)
    except Exception:
        last_bank = yield from info.LastMemoryBank_legacy.read(addr)

    banks = {}
    for bank in range(last_bank + 1):
        try:
            banks[bank] = yield from _read_bank(addr, bank)
        except Exception as ex:
            banks[bank] = f"ERROR ({ex})"
    return {"last_bank": last_bank, "banks": banks}


def hexdump(data: list, width: int = 16) -> list[str]:
    """Zamienia listę bajtów na linie: adres + bajty heksadecymalnie."""
    lines = []
    for start in range(0, len(data), width):
        chunk = data[start:start + width]
        cells = " ".join("--" if b is None else f"{b:02X}" for b in chunk)
        lines.append(f"  {start:02X}: {cells}")
    return lines


def format_response(response) -> str:
    if response is None:
        return "brak odpowiedzi (komenda bez odpowiedzi lub brak zwrotu)"
    value = getattr(response, "value", None)
    if value is not None:
        return f"{type(response).__name__}: {value}"
    return repr(response)


# --- argumenty --------------------------------------------------------------

def _address(text: str) -> int:
    value = int(text)
    if not 0 <= value <= ADDRESS_MAX:
        raise argparse.ArgumentTypeError(f"adres musi być w zakresie 0..{ADDRESS_MAX}")
    return value


def _level(text: str) -> int:
    value = int(text)
    if not 0 <= value <= LEVEL_MAX:
        raise argparse.ArgumentTypeError(f"poziom musi być w zakresie 0..{LEVEL_MAX}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Sterowanie magistralą DALI (Lunatone DALI-2 USB). Wersja: {APP_VERSION}"
    )
    parser.add_argument("--version", action="version", version=APP_VERSION)
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help="port szeregowy: COM4 (Windows) lub /dev/ttyUSB0 (Linux). "
             "Domyślnie zmienna DALI_PORT albo COM4/ttyUSB0.",
    )
    parser.add_argument(
        "--psu",
        choices=PSU_MODES,
        default="on",
        help="zasilacz magistrali: on (domyślnie), off, keep (zewnętrzny PSU)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="stan adaptera i magistrali (tylko odczyt)")
    sub.add_parser("psu-on", help="włącz wewnętrzny zasilacz magistrali")
    sub.add_parser("psu-off", help="wyłącz wewnętrzny zasilacz magistrali")
    sub.add_parser("scan", help="wyszukaj oprawy na magistrali")

    p = sub.add_parser("device-id", help="ID adaptera; z --address także ID oprawy (bank 0)")
    p.add_argument("--address", type=_address, default=None)

    p = sub.add_parser("memory-scan", help="odczyt wszystkich banków pamięci oprawy")
    p.add_argument("--address", type=_address, required=True)

    p = sub.add_parser("info", help="dane oprawy")
    p.add_argument("--address", type=_address, required=True)

    p = sub.add_parser("groups", help="grupy, do których należy oprawa")
    p.add_argument("--address", type=_address, required=True)

    p = sub.add_parser("on", help="pełna jasność oprawy")
    p.add_argument("--address", type=_address, required=True)

    p = sub.add_parser("off", help="wyłącz oprawę")
    p.add_argument("--address", type=_address, required=True)

    p = sub.add_parser("level", help="ustaw poziom oprawy (DAPC)")
    p.add_argument("--address", type=_address, required=True)
    p.add_argument("--value", type=_level, required=True)

    sub.add_parser("all-on", help="broadcast: pełna jasność wszystkich opraw")
    sub.add_parser("all-off", help="broadcast: wyłącz wszystkie oprawy")

    p = sub.add_parser("all-level", help="broadcast: ustaw poziom wszystkich opraw")
    p.add_argument("--value", type=_level, required=True)

    p = sub.add_parser(
        "cmd",
        help="dowolna komenda python-dali (katalog: list-cmds)",
    )
    p.add_argument("--id", required=True, help="identyfikator komendy z list-cmds")
    p.add_argument("--kind", choices=dali_catalog.ADDRESS_KINDS,
                   help="adresat: short, group, broadcast (tylko dla komend z adresem)")
    p.add_argument("--address", type=int, default=None,
                   help="numer adresu lub grupy (dla short / group)")
    p.add_argument("--arg", action="append", default=[],
                   help="argument komendy; można podać wiele razy")
    p.add_argument("--confirm", action="store_true",
                   help="wymagane dla komend zmieniających trwale stan lub pamięć")

    p = sub.add_parser("list-cmds", help="lista komend python-dali (bez połączenia)")
    p.add_argument("--filter", default="", help="fragment nazwy, np. DAPC, Query, Reset")

    return parser


def _details(args) -> str:
    skip = {"command", "port", "psu"}
    parts = []
    for key, value in vars(args).items():
        if key in skip or value in (None, False, []):
            continue
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        parts.append(f"{key}={value}")
    return " ".join(parts)


# --- wykonanie komend -----------------------------------------------------

async def _execute(ctrl: DaliController, args, emit, fail) -> int:
    """Wykonuje komendę na połączonym kontrolerze. Zwraca kod wyjścia."""
    if args.command == "status":
        status = await ctrl.line_status()
        emit(f"=== STATUS ADAPTERA ({APP_VERSION}) ===")
        emit(f"Port           : {ctrl.port}")
        emit(f"Article nr     : {ctrl.article_number}")
        if status is None:
            emit("Bus voltage    : BRAK ODPOWIEDZI ADAPTERA")
        else:
            emit("Bus voltage    : " + ("ERROR" if status.bus_voltage_error else "OK"))

    elif args.command in ("psu-on", "psu-off"):
        # Ustawienie PSU zostało wykonane w connect().
        emit("PSU ON" if ctrl.psu == "on" else "PSU OFF")

    elif args.command == "device-id":
        adapter = ctrl.adapter_info() or {}
        emit("=== ID ADAPTERA (LUBA) ===")
        emit(f"GTIN           : {adapter.get('gtin')}")
        emit(f"ID             : {adapter.get('id')}")
        emit(f"Article nr     : {adapter.get('article_num')}")
        emit(f"PCB ver        : {adapter.get('pcb_ver')}")
        emit(f"Assembly ver   : {adapter.get('assembly_ver')}")
        if args.address is not None:
            ident = await ctrl.gear_identity(args.address)
            emit(f"=== ID OPRAWY {args.address} (bank 0) ===")
            emit(f"GTIN           : {ident['gtin']}")
            emit(f"Nr seryjny     : {ident['serial']}")
            emit(f"Firmware       : {ident['firmware']}")

    elif args.command == "memory-scan":
        result = await ctrl.memory_scan(args.address)
        emit(f"=== SKAN BANKÓW PAMIĘCI, oprawa {args.address} ===")
        emit(f"Ostatni bank   : {result['last_bank']}")
        for bank, data in result["banks"].items():
            if data is None:
                emit(f"BANK {bank}: brak (nie istnieje)")
            elif isinstance(data, str):
                emit(f"BANK {bank}: {data}")
            else:
                emit(f"BANK {bank}: ostatni adres 0x{data[0]:02X}")
                for line in hexdump(data):
                    emit(line)

    elif args.command == "scan":
        found = await ctrl.scan()
        if not found:
            emit("NO DEVICES FOUND")
        for address in found:
            emit(f"DEVICE FOUND AT ADDRESS {address}")

    elif args.command == "info":
        data = await ctrl.info(args.address)
        emit("=== DEVICE INFO ===")
        emit(f"Address      : {data['address']}")
        emit(f"Device Types : {data['device_types']}")
        emit(f"Actual Level : {data['actual_level']}")
        emit(f"Min Level    : {data['min_level']}")
        emit(f"Max Level    : {data['max_level']}")
        emit(f"Status       : {data['status']}")

    elif args.command == "groups":
        groups = await ctrl.groups(args.address)
        emit(f"ADDRESS {args.address} GROUPS: {groups if groups else 'brak'}")

    elif args.command == "on":
        await ctrl.on(args.address)
        emit(f"ADDRESS {args.address} ON")

    elif args.command == "off":
        await ctrl.off(args.address)
        emit(f"ADDRESS {args.address} OFF")

    elif args.command == "level":
        await ctrl.level(args.address, args.value)
        emit(f"ADDRESS {args.address} LEVEL {args.value}")

    elif args.command == "all-on":
        await ctrl.all_on()
        emit("BROADCAST ON")

    elif args.command == "all-off":
        await ctrl.all_off()
        emit("BROADCAST OFF")

    elif args.command == "all-level":
        await ctrl.all_level(args.value)
        emit(f"BROADCAST LEVEL {args.value}")

    elif args.command == "cmd":
        command_obj, entry = dali_catalog.build_command(
            args.id, args.kind, args.address, args.arg
        )
        response = await ctrl.send_command(command_obj)
        emit(f"{entry.name} -> {format_response(response)}")

    return 0


async def run(args, out=print, err=None, source="cli", client=None) -> int:
    """
    Wykonuje komendę i zapisuje ją w logu.

    `out` i `err` pozwalają przekierować wynik i błędy (CLI wypisuje na
    stdout/stderr, web zbiera linie do odpowiedzi). `source` i `client`
    trafiają do logu.
    """
    if args.command == "list-cmds":
        needle = args.filter.lower()
        shown = 0
        for entry in dali_catalog.public_entries():
            if needle and needle not in entry["name"].lower() and needle not in entry["id"].lower():
                continue
            flags = []
            if entry["dangerous"]:
                flags.append("WYMAGA --confirm")
            if entry["address"]:
                flags.append("adresat")
            if entry["varargs"]:
                flags.append("argumenty dowolne")
            params = ", ".join(p["name"] for p in entry["params"])
            out(f"{entry['id']}  ({params})  {' | '.join(flags)}")
            shown += 1
        out(f"Pozycji: {shown}")
        return 0

    lines, errors = [], []

    def emit(message):
        lines.append(message)
        out(message)

    def fail(message):
        errors.append(message)
        if err is not None:
            err(f"BŁĄD: {message}")
        else:
            print(f"BŁĄD: {message}", file=sys.stderr)

    if args.command == "cmd":
        try:
            entry = dali_catalog.CATALOG.get(args.id)
            if entry is None:
                raise ValueError(f"Nieznana komenda: {args.id}")
            if entry.dangerous and not args.confirm:
                raise ValueError(
                    f"{entry.name} zmienia trwale stan lub pamięć. "
                    "Dodaj potwierdzenie (--confirm), aby ją wykonać."
                )
            # Walidacja przed połączeniem z adapterem.
            dali_catalog.build_command(args.id, args.kind, args.address, args.arg)
        except ValueError as ex:
            errors.append(str(ex))
            if err is not None:
                err(f"BŁĄD: {ex}")
            else:
                print(f"BŁĄD: {ex}", file=sys.stderr)
            log_event(source, args.command, f"port={args.port} {_details(args)}",
                      False, lines, errors, client)
            return 1

    psu = args.psu
    if args.command == "psu-on":
        psu = "on"
    elif args.command == "psu-off":
        psu = "off"

    ctrl = DaliController(args.port, psu=psu)
    read_only = args.command == "status"

    code = 1
    try:
        await ctrl.connect(apply_settings=False if read_only else None)

        if ctrl.unsupported_article():
            emit(
                f"UWAGA: nieznany numer artykułu {ctrl.article_number}. "
                f"Znane: {', '.join(str(n) for n in sorted(SUPPORTED_ARTICLE_NUMBERS))}. "
                "Sterowanie nie zostało sprawdzone na tym adapterze."
            )

        code = await _execute(ctrl, args, emit, fail)

    except Exception as ex:
        fail(str(ex))
        code = 1

    finally:
        await ctrl.close()

    details = f"port={args.port} {_details(args)}".strip()
    log_event(source, args.command, details, code == 0, lines, errors, client)
    return code


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
