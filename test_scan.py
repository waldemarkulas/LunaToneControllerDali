import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort
from dali.gear.general import (
    RecallMaxLevel,
    Off
)

PORT = "COM4"
ADDRESS = 0


async def main():

    driver = DriverLubaRs232(
        f"luba232:{PORT}"
    )

    await driver.connect()

    # PSU ON
    driver._protocol.bus_power = True
    await driver._protocol.send_device_settings()

    print("LIGHT ON")

    await driver.send(
        RecallMaxLevel(
            GearShort(ADDRESS)
        )
    )

    input(
        "Press ENTER for OFF..."
    )

    print("LIGHT OFF")

    await driver.send(
        Off(
            GearShort(ADDRESS)
        )
    )

    input(
        "Press ENTER to EXIT..."
    )


asyncio.run(main())
