# report.py

import asyncio
from dali.driver.serial import DriverLubaRs232

async def main():

    report = []

    try:

        driver = DriverLubaRs232(
            uri="luba232:COM4"
        )

        await driver.connect()

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
        report.append(f"Bus Power      : {driver.bus_power}")
        report.append(f"URI            : {driver.uri}")
        report.append(f"Serial Path    : {driver.serial_path}")

        report.append("")
        report.append("=== PROTOCOL ===")

        proto = driver._protocol

        for name in dir(proto):

            if name.startswith("_"):
                continue

            try:
                value = getattr(proto, name)

                if callable(value):
                    report.append(f"[METHOD] {name}")
                else:
                    report.append