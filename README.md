# LunaToneControllerDali

Sterowanie magistralą DALI / DALI DT8 przez interfejs **Lunatone DALI-2 USB 30mA** (nr art. 24138215-30), protokół LUBA, biblioteka `python-dali`.

Na razie działa wiersz poleceń (`dali_lunatonev2.py`). Logika sterowania (`DaliController`) nie drukuje nic na ekran i zwraca dane, więc tę samą klasę użyje później aplikacja webowa.

---

## 1. Wymagania

**Sprzęt**

- Lunatone DALI-2 USB 30mA podłączony kablem USB do komputera.
- Oprawa DALI (do testów) i zasilanie magistrali: wewnętrzny zasilacz adaptera (domyślnie) albo zewnętrzny zasilacz DALI (wtedy użyj `--psu keep`).

**Oprogramowanie**

- Python **3.10 lub nowszy** (projekt rozwijany na 3.14, testy przechodzą na 3.13).
- Zależności z `requirements.txt` (przypięte wersje):
  - `python-dali==0.16`
  - `serialx==1.15.1` (na Windows automatycznie instaluje `pywin32`)
  - `pyserial==3.5`
- Do testów dodatkowo `pytest` (`requirements-dev.txt`).

> Uwaga: `python-dali` zmienia zachowanie połączenia LUBA między wersjami. Od 0.13 `connect()` sam wysyła ustawienia adaptera, więc bez przypięcia wersji skrypty mogą przestać działać. Nie aktualizuj biblioteki bez testu na sprzęcie.

---

## 2. Instalacja – Windows

Otwórz PowerShell w katalogu projektu.

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jeśli PowerShell blokuje aktywację venv, uruchom raz:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Znajdź port COM adaptera:** Menedżer urządzeń → *Porty (COM i LPT)* → wpis z Lunatone (np. `COM4`). Alternatywnie:

```powershell
python -m serial.tools.list_ports -v
```

**Zamknij DALI Cockpit** i inne programy, które używają tego samego portu. Port może być otwarty tylko przez jeden program.

---

## 3. Instalacja – Linux (np. serwer)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Znajdź port:**

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
# albo
python -m serial.tools.list_ports -v
```

Typowo `/dev/ttyUSB0` lub `/dev/ttyACM0`.

**Uprawnienia do portu** (na Debian/Ubuntu port należy do grupy `dialout`):

```bash
sudo usermod -aG dialout $USER
# wyloguj się i zaloguj ponownie (albo: newgrp dialout)
```

---

## 4. Konfiguracja portu (opcjonalnie)

Domyślny port to `COM4` na Windows i `/dev/ttyUSB0` na Linuxie. Można go zmienić zmienną środowiskową `DALI_PORT` albo opcją `--port` przy każdym uruchomieniu.

Windows (PowerShell, tylko bieżąca sesja):

```powershell
$env:DALI_PORT = "COM5"
```

Linux:

```bash
export DALI_PORT=/dev/ttyACM0
```

---

## 5. Uruchamianie (CLI)

Składnia: `python dali_lunatonev2.py [--port PORT] [--psu on|off|keep] KOMENDA ...`

Kody wyjścia: `0` = OK, `1` = błąd (opis na stderr), `2` = zły argument.

| Komenda | Opis |
|---|---|
| `status` | stan adaptera i napięcia na magistrali (tylko odczyt, nie zmienia PSU) |
| `psu-on` | włącza wewnętrzny zasilacz magistrali |
| `psu-off` | wyłącza wewnętrzny zasilacz magistrali |
| `scan` | szuka opraw na adresach 0–63 |
| `info --address N` | typy urządzenia, poziomy, status oprawy |
| `groups --address N` | grupy, do których należy oprawa |
| `on --address N` | pełna jasność |
| `off --address N` | wyłączenie |
| `level --address N --value V` | poziom DAPC, V = 0–254 |
| `all-on` / `all-off` | broadcast |
| `all-level --value V` | broadcast, poziom V = 0–254 |

Przykłady (Windows):

```powershell
python dali_lunatonev2.py --port COM4 status
python dali_lunatonev2.py --port COM4 psu-on
python dali_lunatonev2.py --port COM4 scan
python dali_lunatonev2.py --port COM4 level --address 0 --value 127
```

Przykłady (Linux):

```bash
python dali_lunatonev2.py --port /dev/ttyUSB0 status
python dali_lunatonev2.py --port /dev/ttyUSB0 on --address 0
```

**Zasilacz magistrali (`--psu`):**

- `on` (domyślnie): każde polecenie włącza wewnętrzny zasilacz i czeka, aż pojawi się napięcie na magistrali.
- `off`: wyłącza wewnętrzny zasilacz.
- `keep`: nie zmienia ustawień adaptera. Użyj tego przy zewnętrznym zasilaczu DALI. Nie łącz dwóch zasilaczy na jednej magistrali.

---

## 6. Testy

### 6a. Testy automatyczne (bez sprzętu)

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Oczekiwany wynik: `13 passed`. Testy używają atrapy sterownika, więc działają bez adaptera i bez portu.

### 6b. Test na sprzęcie – kolejność

Wykonuj w tej kolejności. Każdy krok ma przejść, zanim przejdziesz do następnego.

1. **Połączenie i stan**
   ```
   python dali_lunatonev2.py --port COM4 status
   ```
   Oczekiwane: `Bus voltage : OK` (po włączonym PSU) albo `ERROR`, jeśli magistrala nie jest zasilona.

2. **Zasilacz**
   ```
   python dali_lunatonev2.py --port COM4 psu-on
   python dali_lunatonev2.py --port COM4 status
   ```
   Oczekiwane: `PSU ON`, a potem `Bus voltage : OK`. Dodatkowo zmierz napięcie na DA+/DA- (około 16–19 V).

3. **Skan**
   ```
   python dali_lunatonev2.py --port COM4 scan
   ```
   Oczekiwane: `DEVICE FOUND AT ADDRESS ...` dla każdej podłączonej oprawy.

4. **Odczyt danych oprawy** (podstaw adres ze skanu)
   ```
   python dali_lunatonev2.py --port COM4 info --address 0
   python dali_lunatonev2.py --port COM4 groups --address 0
   ```

5. **Sterowanie**
   ```
   python dali_lunatonev2.py --port COM4 on --address 0
   python dali_lunatonev2.py --port COM4 level --address 0 --value 25
   python dali_lunatonev2.py --port COM4 level --address 0 --value 254
   python dali_lunatonev2.py --port COM4 off --address 0
   ```
   Oprawa powinna reagować na każdą komendę.

6. **Wyłączenie zasilacza** (opcjonalnie)
   ```
   python dali_lunatonev2.py --port COM4 psu-off
   ```

Zanotuj wynik każdego kroku. Jeśli któryś nie przejdzie, wklej komendę i pełny wynik (także błąd na stderr).

---

## 7. Rozwiązywanie problemów

| Objaw | Co sprawdzić |
|---|---|
| `Bus voltage : ERROR` | magistrala bez zasilania. Uruchom `psu-on` (przy `--psu on`) albo sprawdź zewnętrzny zasilacz i kable DA+/DA-. |
| `Frame transmission rejected, error code 1` | brak napięcia na magistrali. Sprawdź jak wyżej. |
| `BŁĄD: ... No such file or directory` | zły port. Sprawdź Menedżer urządzeń (Windows) lub `ls /dev/tty*` (Linux). |
| `BŁĄD: ... Permission denied` (Linux) | brak uprawnień do portu. Zrób `usermod -aG dialout`, potem przelogowanie. |
| Port jest zajęty / błąd otwarcia | zamknij DALI Cockpit i inne programy na tym porcie. |
| `connect` nie kończy się | odłącz i podłącz adapter, zamknij inne programy, spróbuj ponownie. |
| Oprawa nie reaguje, a `scan` nic nie znajduje | sprawdź adresowanie oprawy i zasilanie magistrali (`status`). |

---

## 8. Struktura projektu

| Plik | Rola |
|---|---|
| `dali_lunatonev2.py` | **główne CLI** i klasa `DaliController` (warstwa logiki bez wypisywania) |
| `tests/test_dali_cli.py` | testy CLI na atrapie sterownika (bez sprzętu) |
| `pytest.ini` | pytest uruchamia tylko `tests/` |
| `requirements.txt` / `requirements-dev.txt` | zależności z przypiętymi wersjami |
| `test2.py` | raport diagnostyczny adaptera (tylko odczyt) |
| `report.py`, `dali_info.py`, `query_*.py`, `test_*.py`, `power.py`, `odd.py`, `enable_psu.py`, `inspect_driver.py`, `dali_lunatone.py` | **stare skrypty laboratoryjne** z pierwszych testów. Mają zahardkodowane `COM4` i adres `0`. Uruchamiaj je ręcznie. Nie są testami pytest. |
| `readMe.txt` | notatki z pierwszego etapu projektu (protokół, odkrycia dot. PSU) |
| `LUBA_Protocol_EN.pdf` | dokumentacja protokołu LUBA od Lunatone |

Plik `DaliController` zwraca dane i nie drukuje, więc aplikacja webowa może go wywołać bezpośrednio.

---

## 9. Uwagi dla wdrożenia na serwerze (aplikacja webowa)

- Aplikacja webowa będzie miała pełny dostęp do magistrali DALI, więc **musi mieć uwierzytelnianie** przed wystawieniem w sieci. Nie publikuj jej bez logowania.
- Adapter jest podłączony po USB, więc serwer musi fizycznie mieć port (`/dev/ttyUSB0`). Każdy proces z dostępem do tego portu może sterować magistralą, więc ogranicz uprawnienia konta uruchamiającego aplikację.
- Jeden port obsługuje jedno połączenie naraz. Aplikacja webowa i CLI nie mogą równolegle otwierać tego samego portu.
