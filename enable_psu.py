import asyncio

from dali.driver.serial import DriverLubaRs232

async def main():

    driver = DriverLubaRs232(
        "luba232:COM4"
    )

    await driver.connect()

    print("BEFORE:")
    print("bus_power =", driver._protocol.bus_power)

    status = await driver.read_status()
    print("status =", status)

    print()

    driver._protocol.bus_power = True

    await driver._protocol.send_device_settings()

    print("AFTER:")
    print("bus_power =", driver._protocol.bus_power)

    status = await driver.read_status()
    print("status =", status)

    input("CHECK VOLTAGE NOW AND PRESS ENTER")

asyncio.run(main())