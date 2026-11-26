import asyncio

from dali.driver.serial import DriverLubaRs232

async def main():

    driver = DriverLubaRs232(
        uri="luba232:COM4"
    )

    await driver.connect()

    print("Connected")

    proto = driver._protocol

    print()
    print("DEVICE INFO")
    print(proto.device_info)

    print()
    print("BUS POWER")
    print(proto.bus_power)

    print()
    print("SETTINGS CLASS")
    print(driver.LubaDeviceSettings)

asyncio.run(main())