"""
Logi wykonanych komend do plików tekstowych.

Pliki: logs/dali-RRRR-MM-DD.txt (jeden plik na dzień, dopisywany).
Katalog można zmienić zmienną DALI_LOG_DIR.

Zapis logów nigdy nie przerywa wykonania komendy: błąd zapisu tylko
wypisuje ostrzeżenie na stderr.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(os.environ.get("DALI_LOG_DIR") or Path(__file__).resolve().parent / "logs")


def log_event(source, command, details, ok, lines, errors, client=None, log_dir=None):
    """
    Dopisuje jedną komendę do dziennego pliku logu.

    source  - "cli" albo "web"
    command - nazwa komendy, np. "level" albo "cmd"
    details - krótki opis argumentów (tekst)
    lines   - linie wyjścia
    errors  - linie błędów
    client  - adres klienta (dla web), opcjonalnie
    """
    now = datetime.now()
    directory = Path(log_dir) if log_dir else LOG_DIR

    origin = source if not client else f"{source} {client}"
    status = "OK" if ok else "BŁĄD"
    head = f"{now:%Y-%m-%d %H:%M:%S} | {origin} | {command} {details}".rstrip() + f" | {status}"

    body = [f"    {line}" for line in lines]
    body += [f"    ERR: {line}" for line in errors]

    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"dali-{now:%Y-%m-%d}.txt"
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join([head, *body, ""]))
    except OSError as ex:
        print(f"UWAGA: nie udało się zapisać logu: {ex}", file=sys.stderr)
