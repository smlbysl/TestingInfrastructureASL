"""Walks the PDU layers with four buses. Run from the repository root:

    python -m prototypes.pdu_layers.demo
"""
from ctypes import c_int16, c_uint8, c_uint16

from .channel import Channel
from .gateway import FakeUts, Gateway
from .message import BeMessage, LeMessage
from .protocols import Can, DeviceHeader, Ethernet, Mil1553, Rs422


# ---------------------------------------------------------------- channels (project definition)

class Ch:
    CAM   = Channel("CAM",   1, Ethernet(DeviceHeader()))     # ethernet 1, packets with a device header
    RAW   = Channel("RAW",   1, Ethernet())                   # ethernet 1, plain payload
    SER   = Channel("SER",   0, Rs422())
    BUS_A = Channel("BUS_A", 1, Mil1553())
    CAN0  = Channel("CAN0",  0, Can())


# ---------------------------------------------------------------- messages (project definition)

class status(LeMessage):                     # plain Ethernet: told apart by the msgId field (signature)
    _channel = Ch.RAW
    _signature = {"msgId": 0x20}
    _fields_ = [("msgId", c_uint8), ("speed", c_int16)]


class diag(LeMessage):
    _channel = Ch.RAW
    _signature = {"msgId": 0x40}
    _fields_ = [("msgId", c_uint8), ("code", c_uint16)]


class cam_info(LeMessage):                   # Ethernet with a header: the device number is the PCI
    _channel = Ch.CAM
    _fields_ = [("exposure", c_uint16)]


class ser_report(LeMessage):                 # plain RS422, the only message of the channel: no signature
    _channel = Ch.SER
    _fields_ = [("count", c_uint16), ("value", c_uint16)]


class bit_report(BeMessage):                 # 1553: node + subnet are the PCI
    _channel = Ch.BUS_A
    _fields_ = [("status", c_uint16), ("temp", c_int16)]


class mode_a(BeMessage):                     # two messages on one subaddress: a signature in the data
    _channel = Ch.BUS_A
    _signature = {"kind": 1}
    _fields_ = [("kind", c_uint16), ("value", c_uint16)]


class mode_b(BeMessage):
    _channel = Ch.BUS_A
    _signature = {"kind": 2}
    _fields_ = [("kind", c_uint16), ("value", c_uint16)]


class motor_cmd(BeMessage):                  # 1553 TX
    _channel = Ch.BUS_A
    _fields_ = [("speed", c_int16)]


class wheel_speed(LeMessage):                # CAN: the id is the PCI
    _channel = Ch.CAN0
    _fields_ = [("rpm", c_uint16), ("valid", c_uint8)]


def title(text: str) -> None:
    print(f"\n=== {text}")


def main() -> None:
    uts = FakeUts()
    gw = Gateway(uts, [Ch.CAM, Ch.RAW, Ch.SER, Ch.BUS_A, Ch.CAN0])

    # RX messages: created by the test, registered on their channel
    st, dg = status(), diag()
    cam = cam_info(device=7)
    rep = ser_report()
    bit = bit_report(node=5, subnet=3)
    ma, mb = mode_a(node=6, subnet=1), mode_b(node=6, subnet=1)
    whl = wheel_speed(can_id=0x123)

    title("TX: message -> SDU -> PDU (PCI added) -> UTS JSON")
    print("1553     ", gw.send(motor_cmd(direction="tx", node=5, subnet=1, speed=-300)))
    print("Ethernet ", gw.send(status(direction="tx", speed=1200)))
    print("eth+hdr  ", gw.send(cam_info(direction="tx", device=7, exposure=500)))
    print("CAN      ", gw.send(wheel_speed(direction="tx", can_id=0x200, rpm=900, valid=1)))

    title("RX: UTS JSON -> adapter -> PDU -> channel (PCI, then signature) -> message")
    device = [
        ("ethernet", 1, {"message": [0x20, 0xB0, 0x04], "timestamp": 1_000_000}),          # status
        ("ethernet", 1, {"message": [0x40, 0x07, 0x00], "timestamp": 1_000_100}),          # diag
        ("ethernet", 1, {"message": [0xA5, 7, 2, 0xF4, 0x01], "timestamp": 1_000_200}),    # header, device 7
        ("ethernet", 1, {"message": [0xA5, 9, 2, 0x00, 0x00], "timestamp": 1_000_300}),    # device 9: not registered
        ("ethernet", 1, {"message": [0x99, 0x00, 0x00], "timestamp": 1_000_400}),          # msgId 0x99: no signature match
        ("serials",  0, {"message": [2, 0, 0x34, 0x12], "timestamp": 1_000_500}),          # ser_report
        ("1553",     1, {"message": [5, 3, 2, 0x0001, 0xFFF6], "timestamp": 1_000_600}),   # bit_report
        ("1553",     1, {"message": [6, 1, 2, 1, 111], "timestamp": 1_000_700}),           # mode_a
        ("1553",     1, {"message": [6, 1, 2, 2, 222], "timestamp": 1_000_800}),           # mode_b
        ("1553",     1, {"message": [6, 1, 2, 3, 333], "timestamp": 1_000_900}),           # kind 3: unknown
        ("1553",     1, {"message": [5, 3, 3, 1, 2], "timestamp": 1_001_000}),             # count 3, 2 words
        ("1553",     1, {"message": [5, 3, 1, 7], "timestamp": 1_001_100}),                # 1 word: invalid size
        ("can",      0, {"id": 0x123, "message": [0x84, 0x03, 1], "timestamp": 1_001_200}),
    ]
    for path, interface, item in device:
        uts.device_sends(path, interface, item)
    for r in gw.poll():
        name = type(r.message).__name__ if r.message is not None else ""
        values = r.message.values() if r.kind == "received" else ""
        print(f"{r.kind:14s} {str(r.channel):6s} {name:12s} {values} {r.detail}")

    title("Rules checked at definition time")
    for text, make in [
        ("1553 message without subnet", lambda: bit_report(node=5)),
        ("1553 node 33", lambda: bit_report(node=33, subnet=1)),
        ("CAN message without id", lambda: wheel_speed()),
        ("second message without signature on node 5 / subnet 3",
         lambda: motor_cmd(node=5, subnet=3)),
        ("mode_a created again (replaces the old one)", lambda: mode_a(node=6, subnet=1)),
    ]:
        try:
            make()
            print(f"ok      {text}")
        except (TypeError, ValueError) as error:
            print(f"error   {text}: {error}")


if __name__ == "__main__":
    main()
