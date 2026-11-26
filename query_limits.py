import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort

from dali.gear.general import (
    QueryMinLevel,
    QueryMaxLevel,
    QueryActualLevel
)

PORT = "COM4"
ADDRESS = 0


async def main():

    driver = DriverLubaRs232(
        f"luba232:{PORT}"
    )

    await driver.connect()

    driver._protocol.bus_power = True
    await driver._protocol.send_device_settings()

    minlevel = await driver.send(
        QueryMinLevel(
            GearShort(ADDRESS)
        )
    )

    maxlevel = await driver.send(
        QueryMaxLevel(
            GearShort(ADDRESS)
        )
    )

    actual = await driver.send(
        QueryActualLevel(
            GearShort(ADDRESS)
        )
    )

    print("MIN   =", minlevel.value)
    print("MAX   =", maxlevel.value)
    print("ACTUAL=", actual.value)

    input("ENTER")


asyncio.run(main())