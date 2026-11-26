import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearBroadcast
from dali.gear.general import Off


async def main():

    driver = DriverLubaRs232(
        "luba232:COM4"
    )

    await driver.connect()

    # WŁĄCZENIE PSU
    driver._protocol.bus_power = True
    await driver._protocol.send_device_settings()

    print("BUS READY")

    response = await driver.send(
        Off(
            GearBroadcast()
        )
    )

    print("RESPONSE =", response)

    input("ENTER")

asyncio.run(main())