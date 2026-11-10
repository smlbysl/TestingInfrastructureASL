"""Several buses through one fake UTS: Ethernet, RS422, MIL-STD-1553 and CAN.

Shows the PDU layers: the protocol of each channel adds its PCI (1553 node / subnet, CAN id, an
Ethernet header), the gateway adapter writes it in the UTS JSON, and an incoming item is matched by
PCI first, then by signature. Also: history (every packet of a poll), wait_for, unknown packets and
a malformed UTS item.

Run from the repository root:  python -m examples.multi_bus
"""
import time

from asl_testing import Comm, Direction, FakeUtsClient, LinkError, UnknownReceived
from projects.example_project.buses import (CanBase, Mil1553Base, bit_report, brake_cmd, mode_a, mode_b,
                                            motor_demand, wheel_speed)
from projects.example_project.header import ProjectBase
from projects.example_project.messages import bambaşka, comut

SRC, DEST = 0x0001, 0x0002


def main() -> None:
    uts = FakeUtsClient()
    comm = Comm(uts, [ProjectBase, Mil1553Base, CanBase])
    unknown, errors = [], []
    comm.subscribe(UnknownReceived, unknown.append)
    comm.subscribe(LinkError, errors.append)

    # RX objects: the PCI is given where the protocol needs one
    status = comut(DEST, SRC, 0x20)                         # RS422 (CONTROL): no PCI, signature in the header fields
    diag = bambaşka(0x07, SRC, 0x40)                        # Ethernet with header (DIAG)
    report = bit_report(node=5, subnet=3)                   # 1553
    ma, mb = mode_a(node=6, subnet=1), mode_b(node=6, subnet=1)
    wheel = wheel_speed()                                   # CAN, id from the class (_address)

    comm.open()

    print("TX: one message per bus, as UTS gets it")
    for msg in (comut(SRC, DEST, 0x21, direction=Direction.TX), motor_demand(node=5, subnet=1, speed=-300),
                brake_cmd(pressure=258)):
        comm.send(msg)
        path, interface, body = uts.sent[-1]
        print(f"  {type(msg).__name__:12s} -> POST /{path}/{interface}  {body}")

    print("\nRX: the device sends")
    mark = report.rx_history.mark()
    uts.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(0xCAFE, 1)))
    uts.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(0x1234, 0, 0, 0)))
    for temp in (20, 85, 21):                               # three packets of one terminal in one poll
        uts.inject("1553", 1, {"message": [5, 3, 2, 0x0001, temp]})
    uts.inject("1553", 1, {"message": [6, 1, 2, 1, 111]})   # mode_a (kind 1)
    uts.inject("1553", 1, {"message": [6, 1, 2, 2, 222]})   # mode_b (kind 2)
    uts.inject("1553", 1, {"message": [6, 1, 2, 3, 333]})   # kind 3: no message -> unknown
    uts.inject("1553", 1, {"message": [9, 9, 1, 7]})        # node 9: nobody -> unknown
    uts.inject("1553", 1, {"message": [5, 3, 3, 1, 2]})     # word count 3, 2 words: malformed
    uts.inject("can", 0, {"id": 0x123, "message": [0x84, 0x03, 1]})

    hot = comm.wait_for(report, lambda s: s.temperature > 80, timeout=1.0, after=mark)
    time.sleep(0.05)
    print(f"  RS422     status.comut[0] = 0x{status.comut[0]:X}")
    print(f"  Ethernet  diag.request[0] = 0x{diag.request[0]:X} (header removed)")
    print(f"  1553      report now: temperature={report.temperature}; history: "
          f"{[r.snapshot().temperature for r in report.rx_history.since(mark)]}")
    print(f"            wait_for(temperature > 80) found {hot.snapshot().temperature if hot else None} "
          f"in the middle of the poll")
    print(f"            mode_a.value={ma.value}  mode_b.value={mb.value}")
    print(f"  CAN       wheel.rpm={wheel.rpm} valid={wheel.valid}")
    print(f"  unknown   {[f'{ev.channel} {ev.pci}' for ev in unknown]}")
    print(f"  UTS error {[str(ev.error) for ev in errors]}")

    print("\nRules at definition time")
    for text, make in [("1553 without subnet", lambda: bit_report(node=5)),
                       ("1553 node 33", lambda: bit_report(node=33, subnet=1)),
                       ("CAN id out of 11 bits", lambda: wheel_speed(can_id=0x800))]:
        try:
            make()
        except (TypeError, ValueError) as error:
            print(f"  {text:22s} -> {type(error).__name__}: {error}")
    comm.close()


if __name__ == "__main__":
    main()
