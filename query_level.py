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

    print("SET LEVEL 127")

    await driver.send(
        DAPC(
            GearShort(ADDRESS),
            127
        )
    )

    await asyncio.sleep(1)

    response = await driver.send(
        QueryActualLevel(
            GearShort(ADDRESS)
        )
    )

    print()
    print("TYPE:")
    print(type(response))

    print()
    print("RESPONSE:")
    print(response)

    try:
        print()
        print("VALUE:")
        print(response.value)
    except Exception:
        pass

    input("ENTER")


asyncio.run(main())