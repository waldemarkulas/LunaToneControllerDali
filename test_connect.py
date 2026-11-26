import asyncio

from dali.driver.serial import DriverLubaRs232

PORT = "COM4"

async def main():

    print("Connecting...")

    driver = DriverLubaRs232(
        uri=f"luba232:{PORT}"
    )

    await driver.connect()

    print("CONNECTED")

    await asyncio.sleep(2)

    print("DONE")

asyncio.run(main())