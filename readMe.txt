Projekt: Python DALI Controller dla Lunatone DALI-2 USB 24138215-30
Status projektu - Etap 1 (Komunikacja i aktywacja magistrali)
Cel projektu

Stworzenie aplikacji Python umożliwiającej sterowanie urządzeniami DALI i DALI DT8 poprzez interfejs Lunatone DALI-2 USB 30mA (nr art. 24138215-30) z wykorzystaniem biblioteki python-dali oraz protokołu LUBA.

Środowisko testowe
Hardware
Plain Text
Interfejs:
Lunatone DALI-2 USB 30mA
 
Article Number:
24138215-30
 
Połączenie:
USB -> COM4
Software
Plain Text
Python 3.14
 
python-dali
pyserial
serialx
Odkryte zachowanie adaptera

Podczas pierwszych testów:

Python
await driver.connect()

połączenie było poprawnie zestawiane:

Plain Text
CONNECTED
 

natomiast wszystkie komendy DALI kończyły się:

Plain Text
Frame transmission rejected, error code 1
Diagnoza

Odczyt statusu adaptera:

Python
status = await driver.read_status()

zwracał:

Plain Text
LubaLineStatus(bus_voltage_error=True)
 

oraz:

Python
driver.bus_power

zwracał:

Plain Text
False

Oznaczało to, że magistrala DALI nie była zasilona.

Weryfikacja sprzętowa

W programie DALI Cockpit po włączeniu PSU:

Plain Text
DA+ / DA-
≈ 16V - 19V

Po zamknięciu programu napięcie znikało.

Odkrycie kluczowej funkcji

Analiza kodu sterownika LUBA wykazała:

Python
hardware_settings = (
0b10000000
if self.bus_power
else 0b00000000
)

oraz komentarz:

Python
# 7: 1 = turn on bus power supply

co oznacza, że:

Plain Text
HardwareSettings Bit7

steruje wewnętrznym PSU magistrali DALI.

Dokumentacja protokołu LUBA również opisuje bit 7 pola HardwareSettings jako przełącznik zasilacza magistrali.

Opracowane rozwiązanie

Po połączeniu należy wykonać:

Python
driver._protocol.bus_power = True
 
await driver._protocol.send_device_settings()
Obowiązkowa sekwencja inicjalizacji

Każdy nowy program musi rozpoczynać komunikację od:

Python
driver = DriverLubaRs232(
"luba232:COM4"
)
 
await driver.connect()
 
driver._protocol.bus_power = True
 
await driver._protocol.send_device_settings()
Potwierdzenie działania

Po wykonaniu:

Python
driver._protocol.bus_power = True
await driver._protocol.send_device_settings()

zmierzono:

Plain Text
19V na magistrali DALI

oraz komenda:

Python
await driver.send(
Off(
GearBroadcast()
)
)

została wysłana poprawnie:

Plain Text
RESPONSE = None

bez błędu transmisji.

Aktualny stan projektu
Zweryfikowane

✅ Otwarcie COM4

✅ Połączenie z adapterem

✅ Odczyt Device Descriptor

✅ Odczyt Device Info

✅ Odczyt Status

✅ Programowe włączanie PSU

✅ Wysyłanie rozkazów DALI

✅ Odbieranie odpowiedzi DALI

✅ Skanowanie magistrali

Niewykonane jeszcze

⬜ Test z rzeczywistą oprawą

⬜ ON/OFF oprawy

⬜ DAPC (0-254)

⬜ Query Actual Level

⬜ Query Status

⬜ DT8 Tunable White

⬜ DT8 Temperature Query

⬜ GUI

⬜ CLI produkcyjne

Nowe wymaganie funkcjonalne
Sterowanie PSU

Aplikacja musi umożliwiać użytkownikowi włączenie lub wyłączenie magistrali DALI.

Wymaganie FW-001

Użytkownik musi mieć możliwość ręcznego sterowania zasilaczem magistrali.

CLI
Shell
python dali.py psu-on
 
python dali.py psu-off
GUI

Przycisk:

Plain Text
[ PSU ON ]
 
[ PSU OFF ]
Implementacja
Python
# PSU ON
 
driver._protocol.bus_power = True
await driver._protocol.send_device_settings()
 
 
# PSU OFF
 
driver._protocol.bus_power = False
await driver._protocol.send_device_settings()
Uzasadnienie

Nie wszystkie interfejsy DALI posiadają własny zasilacz magistrali.

Projekt musi umożliwiać:

Plain Text
✔ użycie wewnętrznego PSU
✔ pracę z zewnętrznym PSU
✔ diagnostykę magistrali
Następny etap

Po podłączeniu pierwszej oprawy:

Scan urządzeń
Odczyt adresu Short Address
ON/OFF
Direct Arc Power Control
DT8 Temperature Control
GUI + CLI final version

Status projektu: Etap 1 zakończony sukcesem. ✅

Ważna aktualizacja do specyfikacji

Dotychczas mieliśmy wymaganie:

Plain Text
FW-001
Możliwość ręcznego sterowania PSU.

Po dzisiejszych testach dopisałbym:

Plain Text
FW-002
Aplikacja musi umożliwiać pracę zarówno z:
- wewnętrznym PSU adaptera Lunatone
- zewnętrznym PSU DALI

oraz:

Plain Text
FW-003
Stan magistrali musi być prezentowany użytkownikowi:
 
BUS Voltage OK / ERROR
PSU ON / OFF