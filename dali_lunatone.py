import asyncio
import argparse

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort

from dali.gear.general import (
    Off,
    RecallMaxLevel,
    DAPC,
    QueryActualLevel,
    QueryMinLevel,
    QueryMaxLevel,
    QueryStatus,
    QueryControlGearPresent,
)

from dali.sequences import QueryDeviceTypes


DEFAULT_PORT = "COM4"


class DaliController:

    def __init__(self, port):

        self.port = port

        self.driver = DriverLubaRs232(
            f"luba232:{port}"
        )

    async def connect(self):

        await self.driver.connect()

    async def psu_on(self):

        self.driver._protocol.bus_power = True

        await self.driver._protocol.send_device_settings()

        print("PSU ON")

    async def psu_off(self):

        self.driver._protocol.bus_power = False

        await self.driver._protocol.send_device_settings()

        print("PSU OFF")

    async def status(self):

        line_status = await self.driver.read_status()

        print()
        print("=== INTERFACE STATUS ===")
        print(f"Port         : {self.port}")
        print(f"Bus Power    : {self.driver._protocol.bus_power}")
        print(f"Line Status  : {line_status}")
        print()

    async def scan(self):

        print()
        print("=== SCAN ===")
        print()

        found = False

        for addr in range(64):

            try:

                response = await self.driver.send(
                    QueryControlGearPresent(
                        GearShort(addr)
                    )
                )

                if response.value:

                    found = True

                    print(
                        f"DEVICE FOUND AT ADDRESS {addr}"
                    )

            except Exception:
                pass

        if not found:

            print("NO DEVICES FOUND")

        print()

    async def info(self, address):

        addr = GearShort(address)

        print()
        print("=== DEVICE INFO ===")
        print()

        print(f"Address      : {address}")

        try:

            device_types = await self.driver.run_sequence(
                QueryDeviceTypes(addr)
            )

            print(f"Device Types : {device_types}")

        except Exception as ex:

            print(f"Device Types : ERROR ({ex})")

        try:

            actual = await self.driver.send(
                QueryActualLevel(addr)
            )

            print(
                f"Actual Level : {actual.value}"
            )

        except Exception as ex:

            print(
                f"Actual Level : ERROR ({ex})"
            )

        try:

            minimum = await self.driver.send(
                QueryMinLevel(addr)
            )

            print(
                f"Min Level    : {minimum.value}"
            )

        except Exception as ex:

            print(
                f"Min Level    : ERROR ({ex})"
            )

        try:

            maximum = await self.driver.send(
                QueryMaxLevel(addr)
            )

            print(
                f"Max Level    : {maximum.value}"
            )

        except Exception as ex:

            print(
                f"Max Level    : ERROR ({ex})"
            )

        try:

            status = await self.driver.send(
                QueryStatus(addr)
            )

            print(
                f"Status       : {status}"
            )

        except Exception as ex:

            print(
                f"Status       : ERROR ({ex})"
            )

        print()

    async def on(self, address):

        await self.driver.send(
            RecallMaxLevel(
                GearShort(address)
            )
        )

        print(
            f"ON ADDRESS {address}"
        )

    async def off(self, address):

        await self.driver.send(
            Off(
                GearShort(address)
            )
        )

        print(
            f"OFF ADDRESS {address}"
        )

    async def level(self, address, level):

        if level < 0:
            level = 0

        if level > 254:
            level = 254

        await self.driver.send(
            DAPC(
                GearShort(address),
                level
            )
        )

        print(
            f"ADDRESS {address} LEVEL {level}"
        )


async def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        default=DEFAULT_PORT
    )

    sub = parser.add_subparsers(
        dest="command"
    )

    sub.add_parser("psu-on")
    sub.add_parser("psu-off")
    sub.add_parser("status")
    sub.add_parser("scan")

    info = sub.add_parser("info")
    info.add_argument(
        "--address",
        type=int,
        required=True
    )

    on = sub.add_parser("on")
    on.add_argument(
        "--address",
        type=int,
        required=True
    )

    off = sub.add_parser("off")
    off.add_argument(
        "--address",
        type=int,
        required=True
    )

    level = sub.add_parser("level")
    level.add_argument(
        "--address",
        type=int,
        required=True
    )
    level.add_argument(
        "--value",
        type=int,
        required=True
    )

    args = parser.parse_args()

    controller = DaliController(
        args.port
    )

    await controller.connect()

    if args.command == "psu-on":

        await controller.psu_on()

    elif args.command == "psu-off":

        await controller.psu_off()

    elif args.command == "status":

        await controller.status()

    elif args.command == "scan":

        await controller.psu_on()
        await controller.scan()

    elif args.command == "info":

        await controller.psu_on()
        await controller.info(args.address)

    elif args.command == "on":

        await controller.psu_on()
        await controller.on(args.address)

    elif args.command == "off":

        await controller.psu_on()
        await controller.off(args.address)

    elif args.command == "level":

        await controller.psu_on()
        await controller.level(
            args.address,
            args.value
        )

    else:

        parser.print_help()


if __name__ == "__main__":

    asyncio.run(main())