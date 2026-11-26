import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort
from dali.gear.general import DAPC

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

    print("LEVEL 25")
    await driver.send(
        DAPC(
            GearShort(ADDRESS),
            25
        )
    )

    input("ENTER -> LEVEL 127")

    await driver.send(
        DAPC(
            GearShort(ADDRESS),
            127
        )
    )

    input("ENTER -> LEVEL 254")

    await driver.send(
        DAPC(
            GearShort(ADDRESS),
            254
        )
    )

    input("ENTER -> EXIT")

asyncio.run(main())
