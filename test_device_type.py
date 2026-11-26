import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort
from dali.sequences import QueryDeviceTypes

PORT = "COM4"
ADDRESS = 0


async def main():

    driver = DriverLubaRs232(
        f"luba232:{PORT}"
    )

    await driver.connect()

    driver._protocol.bus_power = True
    await driver._protocol.send_device_settings()

    result = await driver.run_sequence(
        QueryDeviceTypes(
            GearShort(ADDRESS)
        )
    )

    print()
    print("DEVICE TYPES")
    print(result)

    input("ENTER")


asyncio.run(main())