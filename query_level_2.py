import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort
from dali.gear.general import (
    DAPC,
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

    for level in [25, 127, 254]:

        print()
        print(f"SET {level}")

        await driver.send(
            DAPC(
                GearShort(ADDRESS),
                level
            )
        )

        await asyncio.sleep(2)

        response = await driver.send(
            QueryActualLevel(
                GearShort(ADDRESS)
            )
        )

        print(
            f"QUERY = {response.value}"
        )

        input("ENTER")

asyncio.run(main())