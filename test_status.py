import asyncio

from dali.driver.serial import DriverLubaRs232

async def main():

    driver = DriverLubaRs232(
        uri="luba232:COM4"
    )

    await driver.connect()

    print("CONNECTED")

    print("bus_power:")
    print(driver.bus_power)

    print()

    print("status:")

    status = await driver.read_status()

    print(status)

    print()

    print("device info:")

    info = await driver.query_device_descriptor()

    print(info)

asyncio.run(main())