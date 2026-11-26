"""
Interfejs webowy do sterowania magistralą DALI.

Korzysta z tej samej logiki co CLI (dali_lunatonev2.py), więc komendy i walidacja
są identyczne. Port szeregowy ustawia serwer (DALI_PORT), klient nie może go wybrać.

Uruchomienie lokalne (Windows):
    python -m uvicorn web_app:app --host 127.0.0.1 --port 8000

Uruchomienie na serwerze:
    DALI_WEB_TOKEN=<długi losowy tekst> DALI_PORT=/dev/ttyUSB0 \
        uvicorn web_app:app --host 0.0.0.0 --port 8000

Zmienna DALI_WEB_TOKEN włącza wymóg logowania tokenem. Bez niej API jest otwarte,
więc nie wystawiaj takiej wersji poza własną sieć.
"""

import asyncio
import contextlib
import hmac
import io
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import dali_catalog
import dali_lunatonev2 as dali

WEB_TOKEN = os.environ.get("DALI_WEB_TOKEN", "")
INDEX_HTML = Path(__file__).resolve().parent / "web" / "index.html"

# Komendy widoczne w interfejsie. Muszą odpowiadać podkomendom z build_parser().
COMMANDS = [
    {"id": "status", "label": "Status adaptera", "group": "Magistrala",
     "address": False, "value": False},
    {"id": "psu-on", "label": "Zasilacz magistrali: włącz", "group": "Magistrala",
     "address": False, "value": False},
    {"id": "psu-off", "label": "Zasilacz magistrali: wyłącz", "group": "Magistrala",
     "address": False, "value": False},
    {"id": "scan", "label": "Skan magistrali (szukaj opraw)", "group": "Magistrala",
     "address": False, "value": False},
    {"id": "device-id", "label": "ID: adapter (i oprawa, jeśli podasz adres)",
     "group": "Identyfikacja", "address": "optional", "value": False},
    {"id": "memory-scan", "label": "Skan banków pamięci oprawy", "group": "Identyfikacja",
     "address": True, "value": False},
    {"id": "info", "label": "Informacje o oprawie", "group": "Oprawa",
     "address": True, "value": False},
    {"id": "groups", "label": "Grupy oprawy", "group": "Oprawa",
     "address": True, "value": False},
    {"id": "on", "label": "Oprawa: pełna jasność", "group": "Oprawa",
     "address": True, "value": False},
    {"id": "off", "label": "Oprawa: wyłącz", "group": "Oprawa",
     "address": True, "value": False},
    {"id": "level", "label": "Oprawa: ustaw poziom", "group": "Oprawa",
     "address": True, "value": True, "value_label": "Poziom (0–254)"},
    {"id": "all-on", "label": "Wszystkie oprawy: pełna jasność", "group": "Broadcast",
     "address": False, "value": False},
    {"id": "all-off", "label": "Wszystkie oprawy: wyłącz", "group": "Broadcast",
     "address": False, "value": False},
    {"id": "all-level", "label": "Wszystkie oprawy: ustaw poziom", "group": "Broadcast",
     "address": False, "value": True, "value_label": "Poziom (0–254)"},
]
COMMANDS_BY_ID = {c["id"]: c for c in COMMANDS}

# Serializuje dostęp do portu: jeden port obsługuje jedno połączenie naraz.
_port_lock = asyncio.Lock()


class RunRequest(BaseModel):
    command: str
    address: int | None = None
    value: int | None = None


class SendRequest(BaseModel):
    """Dowolna komenda z katalogu python-dali."""
    id: str
    kind: str | None = None          # short / group / broadcast
    address: int | None = None
    args: list[str | int] = []
    confirm: bool = False


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not WEB_TOKEN:
        return
    expected = f"Bearer {WEB_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Brak lub zły token")


def build_argv(req: RunRequest) -> list[str]:
    spec = COMMANDS_BY_ID.get(req.command)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Nieznana komenda: {req.command}")

    argv = ["--port", dali.DEFAULT_PORT, req.command]
    if spec["address"] is True:
        if req.address is None:
            raise HTTPException(status_code=400, detail="Podaj adres oprawy (0–63)")
        argv += ["--address", str(req.address)]
    elif spec["address"] == "optional" and req.address is not None:
        argv += ["--address", str(req.address)]
    if spec["value"]:
        if req.value is None:
            raise HTTPException(status_code=400, detail="Podaj wartość (0–254)")
        argv += ["--value", str(req.value)]
    return argv


def parse_argv(argv: list[str]):
    """Parsuje argumenty tym samym parserem co CLI. Błąd -> HTTP 400 z opisem."""
    parser = dali.build_parser()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            return parser.parse_args(argv)
    except SystemExit:
        lines = [line.strip() for line in stderr.getvalue().splitlines() if line.strip()]
        raise HTTPException(status_code=400, detail=lines[-1] if lines else "Zły argument")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    if not WEB_TOKEN:
        print("UWAGA: DALI_WEB_TOKEN nie ustawiony - API działa bez logowania.")
    yield


app = FastAPI(title="LunaToneControllerDali", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML.read_text(encoding="utf-8")


@app.get("/api/commands", dependencies=[Depends(require_token)])
async def list_commands():
    return {
        "commands": COMMANDS,
        "catalog": dali_catalog.public_entries(),
        "port": dali.DEFAULT_PORT,
    }


async def _execute(argv: list[str], command: str, request: Request):
    args = parse_argv(argv)
    client = request.client.host if request.client else None

    out_lines: list[str] = []
    err_lines: list[str] = []
    async with _port_lock:
        code = await dali.run(
            args, out=out_lines.append, err=err_lines.append,
            source="web", client=client,
        )

    return {
        "ok": code == 0,
        "command": command,
        "output": out_lines,
        "errors": err_lines,
    }


@app.post("/api/run", dependencies=[Depends(require_token)])
async def run_command(req: RunRequest, request: Request):
    argv = build_argv(req)
    return await _execute(argv, req.command, request)


@app.post("/api/send", dependencies=[Depends(require_token)])
async def send_command(req: SendRequest, request: Request):
    if req.id not in dali_catalog.CATALOG:
        raise HTTPException(status_code=400, detail=f"Nieznana komenda: {req.id}")

    argv = ["--port", dali.DEFAULT_PORT, "cmd", f"--id={req.id}"]
    if req.kind:
        argv.append(f"--kind={req.kind}")
    if req.address is not None:
        argv.append(f"--address={req.address}")
    for value in req.args:
        if str(value).strip() != "":
            argv.append(f"--arg={value}")
    if req.confirm:
        argv.append("--confirm")

    return await _execute(argv, "cmd", request)
