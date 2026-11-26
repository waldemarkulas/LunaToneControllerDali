"""
Interpretacja skanu pamięci oprawy: opisy banków i wartości z python-dali
oraz raport tekstowy (ten sam tekst w przeglądarce, w CLI i w pliku .txt).

Wejście: wynik memory_scan_sequence z dali_lunatonev2:
    {"last_bank": int, "banks": {numer: [bajty] | None | "ERROR (...)"}}
Lista bajtów ma indeks = adres lokalizacji (0 = ostatni adres banku).
"""

from datetime import datetime

import dali.memory.diagnostics as _diagnostics
import dali.memory.emergency as _emergency
import dali.memory.energy as _energy
import dali.memory.info as _info
import dali.memory.maintenance as _maintenance
import dali.memory.oem as _oem
from dali.memory.location import FlagValue, MemoryBank, MemoryLocationNotImplemented

from dali_version import APP_VERSION

# Opisy modułów biblioteki (nazwa modułu -> czytelny tytuł banku).
MODULE_TITLES = {
    "info": "Informacje o urządzeniu (IEC 62386-102)",
    "oem": "Dane producenta (OEM)",
    "energy": "Energia",
    "diagnostics": "Diagnostyka",
    "emergency": "Oprawy awaryjne",
    "maintenance": "Konserwacja",
}

_MODULES = [_info, _oem, _energy, _diagnostics, _emergency, _maintenance]

_registry_cache = None


def _registry() -> dict:
    """Numer banku -> (tytuł, lista MemoryBank). Pomija warianty *_legacy."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    registry = {}
    for mod in _MODULES:
        title = MODULE_TITLES.get(mod.__name__.rsplit(".", 1)[-1], "Bank")
        for name, obj in vars(mod).items():
            if not isinstance(obj, MemoryBank) or name.endswith("_legacy"):
                continue
            entry = registry.setdefault(obj.address, {"title": title, "banks": []})
            entry["banks"].append(obj)
    _registry_cache = registry
    return registry


def _doc(value_cls) -> str:
    doc = (value_cls.__doc__ or "").strip()
    return doc.splitlines()[0] if doc else ""


def decode_bank(number: int, raw: list) -> list[dict]:
    """
    Dekoduje wartości zdefiniowane w bibliotece dla danego banku.
    Zwraca wiersze: name, value (tekst), doc, status.
    """
    rows = []
    entry = _registry().get(number)
    if not entry:
        return rows

    for bank in entry["banks"]:
        for value_cls in bank.values:
            row = {"name": value_cls.name, "doc": _doc(value_cls), "value": None, "status": "ok"}
            try:
                value = value_cls.from_list(raw)
                if isinstance(value, FlagValue):
                    row["status"] = value.value
                else:
                    row["value"] = str(value)
            except MemoryLocationNotImplemented:
                row["status"] = "nie zaimplementowane"
            except Exception as ex:  # nieprawidłowe dane w pamięci
                row["status"] = f"błąd dekodowania: {ex}"
            rows.append(row)
    return rows


def analyse_scan(scan: dict) -> list[dict]:
    """Zamienia surowy skan na listę banków z opisami i dekodowanymi wartościami."""
    banks = []
    for number, data in sorted(scan["banks"].items()):
        entry = _registry().get(number)
        title = entry["title"] if entry else "Bank nieznany w bibliotece"
        if data is None:
            banks.append({"number": number, "title": title, "exists": False,
                          "last": None, "data": None, "rows": []})
        elif isinstance(data, str):
            banks.append({"number": number, "title": title, "exists": True,
                          "last": None, "data": data, "rows": []})
        else:
            banks.append({"number": number, "title": title, "exists": True,
                          "last": data[0], "data": data, "rows": decode_bank(number, data)})
    return banks


def _hexdump(data: list, width: int = 16) -> list[str]:
    lines = []
    for start in range(0, len(data), width):
        chunk = data[start:start + width]
        cells = " ".join("--" if b is None else f"{b:02X}" for b in chunk)
        lines.append(f"    {start:02X}: {cells}")
    return lines


def format_report(address: int, identity: dict, adapter: dict | None, banks: list[dict],
                  last_bank, when: datetime | None = None) -> list[str]:
    """Raport tekstowy: linie gotowe do wypisania albo zapisania do pliku."""
    when = when or datetime.now()
    out = [
        "=" * 64,
        "SKAN URZĄDZENIA DALI",
        "=" * 64,
        f"Wersja oprogramowania : {APP_VERSION}",
        f"Data skanu            : {when:%Y-%m-%d %H:%M:%S}",
        f"Adres oprawy          : {address}",
        "",
        "--- ID ADAPTERA (LUBA) ---",
    ]
    if adapter:
        out += [
            f"GTIN                  : {adapter.get('gtin')}",
            f"ID                    : {adapter.get('id')}",
            f"Numer artykułu        : {adapter.get('article_num')}",
        ]
    else:
        out.append("brak danych")

    out += [
        "",
        "--- ID OPRAWY (bank 0) ---",
        f"GTIN                  : {identity.get('gtin')}",
        f"Numer seryjny         : {identity.get('serial')}",
        f"Firmware              : {identity.get('firmware')}",
        "",
        f"--- BANKI PAMIĘCI (ostatni bank: {last_bank}, banków: {len(banks)}) ---",
    ]

    for bank in banks:
        out.append("")
        if not bank["exists"]:
            out.append(f"BANK {bank['number']}: nie istnieje")
            continue
        if bank["data"] is None or isinstance(bank["data"], str):
            out.append(f"BANK {bank['number']}: {bank['title']} - błąd odczytu: {bank['data']}")
            continue
        out.append(f"BANK {bank['number']}: {bank['title']}  (ostatni adres 0x{bank['last']:02X})")
        out += _hexdump(bank["data"])
        present = [r for r in bank["rows"] if r["status"] != "nie zaimplementowane"]
        skipped = len(bank["rows"]) - len(present)
        if present:
            out.append("  Wartości:")
            width = max(len(r["name"]) for r in present)
            for row in present:
                value = row["value"] if row["value"] is not None else f"<{row['status']}>"
                doc = f"  # {row['doc']}" if row["doc"] else ""
                out.append(f"    {row['name']:<{width}} = {value}{doc}")
        if skipped:
            out.append(f"  (pominięto {skipped} wartości niezaimplementowanych w tym banku)")
    out.append("")
    out.append("=" * 64)
    return out
