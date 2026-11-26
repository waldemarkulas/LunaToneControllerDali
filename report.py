import asyncio
from dali.driver.serial import DriverLubaRs232

async def main():

    driver = DriverLubaRs232(
        "luba232:COM4"
    )

    await driver.connect()

    print("before:", driver.bus_power)

    driver._protocol.bus_power = True

    await driver._protocol.send_device_settings()

    print("settings sent")

    status = await driver.read_status()

    print(status)

asyncio.run(main())