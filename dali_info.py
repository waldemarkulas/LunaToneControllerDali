import asyncio

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort

from dali.gear.general import (
    QueryActualLevel,
    QueryMinLevel,
    QueryMaxLevel,
    QueryStatus
)

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

    addr = GearShort(ADDRESS)

    print()
    print("===================================")
    print("DALI DEVICE INFO")
    print("===================================")

    try:
        device_types = await driver.run_sequence(
            QueryDeviceTypes(addr)
        )

        print("Device Types :", device_types)

    except Exception as ex:

        print("Device Types :", ex)

    try:

        actual = await driver.send(
            QueryActualLevel(addr)
        )

        print("Actual Level :", actual.value)

    except Exception as ex:

        print("Actual Level :", ex)

    try:

        min_level = await driver.send(
            QueryMinLevel(addr)
        )

        print("Min Level    :", min_level.value)

    except Exception as ex:

        print("Min Level    :", ex)

    try:

        max_level = await driver.send(
            QueryMaxLevel(addr)
        )

        print("Max Level    :", max_level.value)

    except Exception as ex:

        print("Max Level    :", ex)

    try:

        status = await driver.send(
            QueryStatus(addr)
        )

        print("Status       :", status)

    except Exception as ex:

        print("Status       :", ex)

    print()
    print("Bus Power    :", driver._protocol.bus_power)

    try:

        line_status = await driver.read_status()

        print("Line Status  :", line_status)

    except Exception as ex:

        print("Line Status  :", ex)

    print()
    input("ENTER")


asyncio.run(main())