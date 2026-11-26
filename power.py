import asyncio

from dali.driver.serial import DriverLubaRs232

async def main():

    driver = DriverLubaRs232(
        uri="luba232:COM4"
    )

    await driver.connect()

    proto = driver._protocol

    for x in sorted(dir(proto)):
        print(x)

asyncio.run(main())