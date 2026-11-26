# Diagnostyka adaptera (tylko odczyt, PSU nie jest zmieniane).
# Użycie: python test2.py --port COM4

import argparse
import asyncio
import os
import sys

from dali.driver.serial import DriverLubaRs232

DEFAULT_PORT = os.environ.get("DALI_PORT") or (
    "COM4" if sys.platform == "win32" else "/dev/ttyUSB0"
)


async def main(port: str) -> None:

    report = []

    driver = DriverLubaRs232(f"luba232:{port}")

    try:
        # apply_settings=False: nie zmieniamy ustawień sprzętowych adaptera.
        await driver.connect(apply_settings=False)

        report.append("=== CONNECTION ===")
        report.append(f"Connected      : {driver.is_connected}")

        try:
            desc = await driver.query_device_descriptor()
            report.append("")
            report.append("=== DEVICE ===")
            report.append(f"Descriptor     : {desc}")
        except Exception as ex:
            report.append(f"Descriptor ERR : {ex}")

        try:
            status = await driver.read_status()
            report.append("")
            report.append("=== STATUS ===")
            report.append(f"Status         : {status}")
        except Exception as ex:
            report.append(f"Status ERR     : {ex}")

        report.append("")
        report.append("=== DRIVER ===")
        report.append(f"URI            : {driver.uri}")
        report.append(f"Serial Path    : {driver.serial_path}")
        report.append(f"Bus Power (cfg): {driver.bus_power}")

        report.append("")
        report.append("=== PROTOCOL ===")
        proto = driver._protocol
        for name in dir(proto):
            if name.startswith("_"):
                continue
            try:
                value = getattr(proto, name)
            except Exception as ex:
                report.append(f"{name} ERR : {ex}")
                continue
            if callable(value):
                report.append(f"[METHOD] {name}")
            else:
                report.append(f"{name} = {value!r}")

    except Exception as ex:
        report.append(f"FATAL: {ex}")

    finally:
        transport = getattr(driver, "_transport", None)
        if transport is not None:
            transport.close()

    print("\n".join(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raport diagnostyczny adaptera LUBA")
    parser.add_argument("--port", default=DEFAULT_PORT)
    args = parser.parse_args()
    asyncio.run(main(args.port))
