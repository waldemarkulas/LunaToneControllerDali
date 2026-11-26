import asyncio
import argparse

from dali.driver.serial import DriverLubaRs232
from dali.address import GearShort, GearBroadcast

from dali.gear.general import (
    Off,
    RecallMaxLevel,
    DAPC,
    QueryActualLevel,
    QueryMinLevel,
    QueryMaxLevel,
    QueryStatus,
    QueryControlGearPresent,
    QueryGroupsZeroToSeven,
    QueryGroupsEightToFifteen,
)

from dali.sequences import QueryDeviceTypes


DEFAULT_PORT = "COM4"


class DaliController:

    def __init__(self, port: str):

        self.port = port

        self.driver = DriverLubaRs232(
            f"luba232:{port}"
        )

    async def connect(self):

        await self.driver.connect()

    async def enable_psu(self):

        self.driver._protocol.bus_power = True

        await self.driver._protocol.send_device_settings()

        print("PSU ON")

    async def disable_psu(self):

        self.driver._protocol.bus_power = False 

        await self.driver._protocol.send_device_settings()

    print("PSU OFF")

    async def show_status(self):

        status = await self.driver.read_status()

        print()
        print("================================")
        print("INTERFACE STATUS")
        print("================================")
        print(f"PORT       : {self.port}")
        print(f"BUS POWER  : {self.driver._protocol.bus_power}")
        print(f"STATUS     : {status}")
        print()

    async def scan(self):

        print()
        print("================================")
        print("SCAN")
        print("================================")

        found = False

        for address in range(64):

            try:

                response = await self.driver.send(
                    QueryControlGearPresent(
                        GearShort(address)
                    )
                )

                if response.value:

                    found = True

                    print(
                        f"DEVICE FOUND AT ADDRESS {address}"
                    )

            except Exception:
                pass

        if not found:
            print("NO DEVICES FOUND")

        print()

    async def info(self, address):

        addr = GearShort(address)

        print()
        print("================================")
        print("DEVICE INFO")
        print("================================")

        print(f"ADDRESS      : {address}")

        try:

            device_types = await self.driver.run_sequence(
                QueryDeviceTypes(addr)
            )

            print(
                f"DEVICE TYPES : {device_types}"
            )

        except Exception as ex:

            print(
                f"DEVICE TYPES : ERROR ({ex})"
            )

        try:

            actual = await self.driver.send(
                QueryActualLevel(addr)
            )

            print(
                f"ACTUAL LEVEL : {actual.value}"
            )

        except Exception as ex:

            print(
                f"ACTUAL LEVEL : ERROR ({ex})"
            )

        try:

            minimum = await self.driver.send(
                QueryMinLevel(addr)
            )

            print(
                f"MIN LEVEL    : {minimum.value}"
            )

        except Exception as ex:

            print(
                f"MIN LEVEL    : ERROR ({ex})"
            )

        try:

            maximum = await self.driver.send(
                QueryMaxLevel(addr)
            )

            print(
                f"MAX LEVEL    : {maximum.value}"
            )

        except Exception as ex:

            print(
                f"MAX LEVEL    : ERROR ({ex})"
            )

        try:

            status = await self.driver.send(
                QueryStatus(addr)
            )

            print(
                f"STATUS       : {status}"
            )

        except Exception as ex:

            print(
                f"STATUS       : ERROR ({ex})"
            )

        print()

    async def groups(self, address):

        addr = GearShort(address)

        print()
        print("================================")
        print("GROUP MEMBERSHIP")
        print("================================")

        try:

            low = await self.driver.send(
                QueryGroupsZeroToSeven(addr)
            )

            high = await self.driver.send(
                QueryGroupsEightToFifteen(addr)
            )

            low_mask = low.value
            high_mask = high.value

            for group in range(8):

                member = bool(
                    low_mask & (1 << group)
                )

                print(
                    f"GROUP {group:02d} : {member}"
                )

            for group in range(8):

                member = bool(
                    high_mask & (1 << group)
                )

                print(
                    f"GROUP {group + 8:02d} : {member}"
                )

        except Exception as ex:

            print(
                f"GROUP QUERY ERROR : {ex}"
            )

        print()

    async def on(self, address):

        await self.driver.send(
            RecallMaxLevel(
                GearShort(address)
            )
        )

        print(
            f"ADDRESS {address} ON"
        )

    async def off(self, address):

        await self.driver.send(
            Off(
                GearShort(address)
            )
        )

        print(
            f"ADDRESS {address} OFF"
        )

    async def level(self, address, value):

        value = max(
            0,
            min(254, value)
        )

        await self.driver.send(
            DAPC(
                GearShort(address),
                value
            )
        )

        print(
            f"ADDRESS {address} LEVEL {value}"
        )

    async def all_on(self):

        await self.driver.send(
            RecallMaxLevel(
                GearBroadcast()
            )
        )

        print("BROADCAST ON")

    async def all_off(self):

        await self.driver.send(
            Off(
                GearBroadcast()
            )
        )

        print("BROADCAST OFF")

    async def all_level(self, value):

        value = max(
            0,
            min(254, value)
        )

        await self.driver.send(
            DAPC(
                GearBroadcast(),
                value
            )
        )

        print(
            f"BROADCAST LEVEL {value}"
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

    sub.add_parser("all-on")
    sub.add_parser("all-off")

    all_level = sub.add_parser(
        "all-level"
    )

    all_level.add_argument(
        "--value",
        type=int,
        required=True
    )

    info = sub.add_parser("info")

    info.add_argument(
        "--address",
        type=int,
        required=True
    )

    groups = sub.add_parser(
        "groups"
    )

    groups.add_argument(
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

    level = sub.add_parser(
        "level"
    )

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

        await controller.enable_psu()

    elif args.command == "psu-off":

        await controller.disable_psu()

    elif args.command == "status":

        await controller.show_status()

    elif args.command == "scan":

        await controller.enable_psu()
        await controller.scan()

    elif args.command == "info":

        await controller.enable_psu()
        await controller.info(
            args.address
        )

    elif args.command == "groups":

        await controller.enable_psu()
        await controller.groups(
            args.address
        )

    elif args.command == "on":

        await controller.enable_psu()
        await controller.on(
            args.address
        )

    elif args.command == "off":

        await controller.enable_psu()
        await controller.off(
            args.address
        )

    elif args.command == "level":

        await controller.enable_psu()
        await controller.level(
            args.address,
            args.value
        )

    elif args.command == "all-on":

        await controller.enable_psu()
        await controller.all_on()

    elif args.command == "all-off":

        await controller.enable_psu()
        await controller.all_off()

    elif args.command == "all-level":

        await controller.enable_psu()
        await controller.all_level(
            args.value
        )

    else:

        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())