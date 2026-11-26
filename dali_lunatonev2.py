"""
Sterowanie magistralą DALI przez interfejs Lunatone DALI-2 USB (protokół LUBA).

Dwie warstwy:
  * DaliController  - logika bez wypisywania na ekran. Zwraca dane, więc
                      można jej użyć z CLI, z aplikacji webowej albo z testów.
  * main()/CLI      - parsuje argumenty, wywołuje kontroler i drukuje wynik.

Przykłady:
  python dali_lunatonev2.py --port COM4 status
  python dali_lunatonev2.py --port COM4 psu-on
  python dali_lunatonev2.py --port /dev/ttyUSB0 scan
  python dali_lunatonev2.py --port COM4 level --address 0 --value 127

Kody wyjścia: 0 = OK, 1 = błąd (opis na stderr).
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
    QueryActualLevel,
    QueryMinLevel,
    QueryMaxLevel,
    QueryStatus,
    QueryControlGearPresent,
    QueryGroupsZeroToSeven,
    QueryGroupsEightToFifteen,
)

from dali.sequences import QueryDeviceTypes


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

    async def close(self) -> None:
        transport = getattr(self.driver, "_transport", None)
        if transport is not None:
            transport.close()
        self.driver = None

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
            result["device_types"] = await self.driver.run_sequence(
                QueryDeviceTypes(addr)
            )
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


# --- walidacja argumentów -------------------------------------------------

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
        description="Sterowanie magistralą DALI (Lunatone DALI-2 USB)."
    )
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

    return parser


# --- wykonanie komend -----------------------------------------------------

async def run(args, out=print) -> int:
    """Wykonuje komendę. `out` pozwala podmienić wypisywanie (testy, web)."""
    psu = args.psu
    if args.command == "psu-on":
        psu = "on"
    elif args.command == "psu-off":
        psu = "off"

    ctrl = DaliController(args.port, psu=psu)
    read_only = args.command == "status"

    try:
        await ctrl.connect(apply_settings=False if read_only else None)

        if args.command == "status":
            status = await ctrl.line_status()
            out("=== STATUS ADAPTERA ===")
            out(f"Port           : {ctrl.port}")
            if status is None:
                out("Bus voltage    : BRAK ODPOWIEDZI ADAPTERA")
            else:
                out("Bus voltage    : " + ("ERROR" if status.bus_voltage_error else "OK"))

        elif args.command in ("psu-on", "psu-off"):
            # Ustawienie PSU zostało wykonane w connect().
            out("PSU ON" if psu == "on" else "PSU OFF")

        elif args.command == "scan":
            found = await ctrl.scan()
            if not found:
                out("NO DEVICES FOUND")
            for address in found:
                out(f"DEVICE FOUND AT ADDRESS {address}")

        elif args.command == "info":
            data = await ctrl.info(args.address)
            out("=== DEVICE INFO ===")
            out(f"Address      : {data['address']}")
            out(f"Device Types : {data['device_types']}")
            out(f"Actual Level : {data['actual_level']}")
            out(f"Min Level    : {data['min_level']}")
            out(f"Max Level    : {data['max_level']}")
            out(f"Status       : {data['status']}")

        elif args.command == "groups":
            groups = await ctrl.groups(args.address)
            out(f"ADDRESS {args.address} GROUPS: {groups if groups else 'brak'}")

        elif args.command == "on":
            await ctrl.on(args.address)
            out(f"ADDRESS {args.address} ON")

        elif args.command == "off":
            await ctrl.off(args.address)
            out(f"ADDRESS {args.address} OFF")

        elif args.command == "level":
            await ctrl.level(args.address, args.value)
            out(f"ADDRESS {args.address} LEVEL {args.value}")

        elif args.command == "all-on":
            await ctrl.all_on()
            out("BROADCAST ON")

        elif args.command == "all-off":
            await ctrl.all_off()
            out("BROADCAST OFF")

        elif args.command == "all-level":
            await ctrl.all_level(args.value)
            out(f"BROADCAST LEVEL {args.value}")

        return 0

    except Exception as ex:
        print(f"BŁĄD: {ex}", file=sys.stderr)
        return 1

    finally:
        await ctrl.close()


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
