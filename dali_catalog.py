"""
Katalog wszystkich komend python-dali (gear i device).

Lista jest budowana z introspekcji klas biblioteki, więc nowe komendy z nowszej
wersji python-dali pojawiają się same. Każda komenda ma:
  * id         - np. "dali.gear.general.DAPC" (unikalne)
  * family     - "gear" (oprawy) albo "device" (urządzenia sterujące)
  * address    - True, gdy komenda przyjmuje adresata (short / grupa / broadcast)
  * params     - nazwy argumentów (bez adresata), z informacją czy wymagane
  * varargs    - True, gdy sygnatura nie określa liczby argumentów (*args);
                 wtedy użytkownik podaje je jako listę, a python-dali waliduje
  * dangerous  - True, gdy komenda zmienia trwale stan oprawy/pamięci i wymaga
                 potwierdzenia (reset, zapis pamięci, adres, power-on level...)

Argumenty podane jako tekst: liczby zamieniane są na int, pozostałe zostają
tekstem (np. "OFF" albo "MASK" dla DAPC), a walidację wykonuje python-dali.
"""

import inspect
from dataclasses import dataclass, field

from dali.address import (
    DeviceBroadcast,
    DeviceGroup,
    DeviceShort,
    GearBroadcast,
    GearGroup,
    GearShort,
)
from dali.command import Command

import dali.device.general
import dali.device.general_sensor
import dali.device.light
import dali.device.occupancy
import dali.device.pushbutton
import dali.gear.colour
import dali.gear.converter
import dali.gear.emergency
import dali.gear.general
import dali.gear.incandescent
import dali.gear.led

FAMILY_MODULES = {
    "gear": [
        dali.gear.general,
        dali.gear.led,
        dali.gear.colour,
        dali.gear.emergency,
        dali.gear.converter,
        dali.gear.incandescent,
    ],
    "device": [
        dali.device.general,
        dali.device.general_sensor,
        dali.device.light,
        dali.device.occupancy,
        dali.device.pushbutton,
    ],
}

# Parametry, które oznaczają adresata komendy.
ADDRESS_PARAMS = {"destination", "device"}

# Komendy zmieniające trwale stan oprawy/urządzenia lub pamięć.
DANGEROUS_PREFIXES = (
    "Reset",
    "Initialise",
    "Randomise",
    "Terminate",
    "WriteMemory",
    "Store",
    "SetPowerOnLevel",
    "SetSystemFailureLevel",
    "SetShortAddress",
)

ADDRESS_KINDS = ("short", "group", "broadcast")

_ADDRESS_CLASSES = {
    "gear": (GearShort, GearGroup, GearBroadcast),
    "device": (DeviceShort, DeviceGroup, DeviceBroadcast),
}


@dataclass
class Param:
    name: str
    required: bool
    default: object = None


@dataclass
class Entry:
    id: str
    family: str
    name: str
    module: str
    cls: type
    label: str
    address: bool
    params: list = field(default_factory=list)
    varargs: bool = False
    dangerous: bool = False


def _short_module(module_name: str) -> str:
    return module_name.replace("dali.", "", 1)


def _build_catalog() -> dict:
    catalog = {}
    for family, modules in FAMILY_MODULES.items():
        for mod in modules:
            for name, cls in vars(mod).items():
                if name.startswith("_") or name.startswith("Unknown"):
                    continue
                if not (inspect.isclass(cls) and issubclass(cls, Command)):
                    continue
                if cls.__module__ != mod.__name__:
                    continue

                try:
                    sig = inspect.signature(cls.__init__)
                except (TypeError, ValueError):
                    continue
                names = list(sig.parameters.values())[1:]  # bez self
                # Komendy z argumentami nazwanymi (**kwargs) nie da się
                # poprawnie zbudować z formularza, więc są pomijane.
                if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in names):
                    continue

                address = bool(names) and names[0].name in ADDRESS_PARAMS
                if address:
                    names = names[1:]

                params, varargs = [], False
                for p in names:
                    if p.kind == inspect.Parameter.VAR_POSITIONAL:
                        varargs = True
                    elif p.kind == inspect.Parameter.VAR_KEYWORD:
                        continue
                    else:
                        params.append(Param(
                            name=p.name,
                            required=p.default is inspect.Parameter.empty,
                            default=None if p.default is inspect.Parameter.empty else p.default,
                        ))

                doc = (inspect.getdoc(cls) or name).splitlines()[0]
                short = _short_module(mod.__name__)
                cmd_id = f"{mod.__name__}.{name}"
                catalog[cmd_id] = Entry(
                    id=cmd_id,
                    family=family,
                    name=name,
                    module=short,
                    cls=cls,
                    label=doc,
                    address=address,
                    params=params,
                    varargs=varargs,
                    dangerous=name.startswith(DANGEROUS_PREFIXES),
                )
    return catalog


CATALOG = _build_catalog()


def public_entries() -> list[dict]:
    """Katalog w formie do wysłania do przeglądarki (JSON)."""
    out = []
    for entry in sorted(CATALOG.values(), key=lambda e: (e.family, e.name, e.module)):
        out.append({
            "id": entry.id,
            "name": entry.name,
            "family": entry.family,
            "module": entry.module,
            "label": entry.label,
            "address": entry.address,
            "params": [
                {"name": p.name, "required": p.required, "default": p.default}
                for p in entry.params
            ],
            "varargs": entry.varargs,
            "dangerous": entry.dangerous,
        })
    return out


def parse_value(text):
    """Liczby zamienia na int, resztę zostawia jako tekst."""
    if isinstance(text, int):
        return text
    s = str(text).strip()
    try:
        return int(s)
    except ValueError:
        return s


def make_address(family: str, kind: str, value=None):
    short, group, broadcast = _ADDRESS_CLASSES[family]
    if kind == "short":
        if value is None:
            raise ValueError("Podaj adres krótki")
        return short(int(value))
    if kind == "group":
        if value is None:
            raise ValueError("Podaj numer grupy")
        return group(int(value))
    if kind == "broadcast":
        return broadcast()
    raise ValueError(f"Nieznany rodzaj adresata: {kind}")


def build_command(cmd_id: str, kind=None, address=None, args=None) -> tuple[Command, Entry]:
    """
    Tworzy obiekt komendy python-dali.
    Zwraca (komenda, wpis katalogu). Błędne argumenty -> ValueError.
    """
    entry = CATALOG.get(cmd_id)
    if entry is None:
        raise ValueError(f"Nieznana komenda: {cmd_id}")

    values = [parse_value(v) for v in (args or [])]
    call_args = []

    if entry.address:
        if kind not in ADDRESS_KINDS:
            raise ValueError(f"Komenda {entry.name} wymaga adresata (short / group / broadcast)")
        call_args.append(make_address(entry.family, kind, address))
    elif kind is not None:
        raise ValueError(f"Komenda {entry.name} nie przyjmuje adresata")

    if not entry.varargs:
        required = [p for p in entry.params if p.required]
        if not (len(required) <= len(values) <= len(entry.params)):
            raise ValueError(
                f"Komenda {entry.name}: oczekiwano {len(required)}-{len(entry.params)} "
                f"wartości, podano {len(values)}"
            )

    call_args.extend(values)
    try:
        return entry.cls(*call_args), entry
    except Exception as ex:  # błędne argumenty zgłasza python-dali
        raise ValueError(f"Komenda {entry.name}: {ex}") from None
