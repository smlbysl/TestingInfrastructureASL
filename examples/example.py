"""End-to-end example with a fake UTS.

Shows: periodic and one-shot TX, RX dispatch, listeners, unknown / invalid packets,
channels sharing an interface (envelope), line-level events, RX timeout and recovery,
a re-created message replacing the old one, UTS errors and the logs.

Run from the repository root:  python -m examples.example
"""
import ctypes
import logging
import time

from asl_testing import Comm, FakeUtsClient
from asl_testing.events import WireReceived, WireSent
from asl_testing.message.timing import Direction
from asl_testing.message.timing import Timing
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut, diag_log, request
from projects.example_project.header import ProjectBase
from asl_testing.services import CommLogger, ErrorLog

SRC, DEST = 0x0001, 0x0002


def device_sends(uts: FakeUtsClient, msg) -> None:
    """Plays the device: the packet, with the channel's envelope, appears in the UTS receive buffer."""
    ch = msg.channel
    uts.inject(ch.protocol, ch.interface, ch.framing.envelope.on_send(msg.pack()))


def main() -> None:
    # General log: every layer (and the test code) in one file; set once by the test side
    logging.basicConfig(filename="comm.log", filemode="w", level=logging.DEBUG,
                        format="%(asctime)s %(levelname)-7s %(name)-28s %(message)s")
    uts = FakeUtsClient()
    comm = Comm(uts, [ProjectBase], poll_interval=0.01)
    history = CommLogger(comm, "comm_history.csv")
    errors = ErrorLog(comm, "comm_errors.log")

    # --- Message objects (from the ICD) --------------------------------------
    sw_req = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.02))
    status = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=1.5))
    diag = bambaşka(0x07, SRC, 0x40)                                    # Family2 -> DIAG (Ethernet + header)

    seen = []
    comm.on_receive(status, lambda ev: seen.append(hex(ev.snapshot().comut[0])))
    wire_rx, wire_tx = [], []
    comm.subscribe(WireReceived, lambda ev: wire_rx.append((str(ev.channel), ev.wire)))
    comm.subscribe(WireSent, lambda ev: wire_tx.append((str(ev.channel), ev.wire)))
    comm.listen(MyChannels.RAW)        # no RX message on RAW: listen to see its packets

    comm.open()

    # --- TX ---------------------------------------------------------------------
    print("TX")
    comm.start(sw_req)
    time.sleep(0.1)
    comm.stop(sw_req)
    periodic = len(uts.sent)
    comm.send(sw_req)
    print(f"  periodic sends: {periodic}, after one-shot: {len(uts.sent)}, "
          f"counter: {sw_req.messageCounter.val}")

    # --- RX ---------------------------------------------------------------------
    print("\nRX")
    remote = comut(DEST, SRC, 0x20, direction=Direction.TX)          # the device's copy of the message
    for value in (0xCAFE, 0xBEEF):
        remote.comut[0] = value
        device_sends(uts, remote)
        time.sleep(0.03)

    remote_diag = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
    remote_diag.request[0] = 0x1234
    device_sends(uts, remote_diag)

    bad = bytearray(remote.pack())
    bad[comut.checksum.offset] ^= 0xFF                                   # broken CRC
    uts.inject(MyChannels.CONTROL.protocol, 0, bytes(bad))
    uts.inject(MyChannels.CONTROL.protocol, 0, bytes(16))                # matches no message
    uts.inject(MyChannels.RAW.protocol, 1, b"\x01\x02\x03")               # no header on ETHERNET:1 -> RAW
    time.sleep(0.05)

    print(f"  status.comut[0] = 0x{status.comut[0]:X}, uts time = {status.rx_state.timestamp:.3f}")
    print(f"  listener saw: {seen}")
    print(f"  diag.request[0] = 0x{diag.request[0]:X}  (DIAG: header removed)")
    print(f"  status valid={status.rx_state.count} invalid={status.rx_state.errors}, "
          f"unknown frames: {[str(f.channel) for f in comm.unknown]}")
    eth_in = next(w for ch, w in wire_rx if ch == "DIAG")
    print(f"  WireReceived on DIAG: {eth_in[:8].hex(' ')} | ... ({len(eth_in)} bytes, header included)")

    # --- Variable size: the checksum follows the used entries -----------------------
    print("\nVariable size")
    log = diag_log(DEST, SRC, 0x50)
    remote_log = diag_log(DEST, SRC, 0x50, direction=Direction.TX)
    remote_log.count = 3
    for i in range(3):
        remote_log.entries[i] = 0x100 + i
    device_sends(uts, remote_log)
    time.sleep(0.05)
    print(f"  wire size {remote_log.messageLength.val} of max {ctypes.sizeof(log)}, "
          f"count={log.count}, entries={[hex(x) for x in log.entries[:4]]}")

    # --- RX timeout and recovery -------------------------------------------------
    print("\nRX timeout")
    time.sleep(0.15)                                                     # > 0.05 * 1.5
    device_sends(uts, remote)
    time.sleep(0.05)

    # --- Re-creating a message replaces the old object ---------------------------
    print("\nRe-create")
    status2 = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=1.5))     # no conflict error
    remote.comut[0] = 0x5555
    device_sends(uts, remote)
    time.sleep(0.05)
    print(f"  new object: 0x{status2.comut[0]:X}, old object (no longer updated): 0x{status.comut[0]:X}")

    comm.start(sw_req)
    sw_req2 = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.02))   # replaces sw_req
    time.sleep(0.05)
    print(f"  old periodic request still running: {comm.tx.is_running(sw_req)}")

    # --- UTS error ----------------------------------------------------------------
    def unreachable(*args):
        raise ConnectionError("UTS unreachable")

    uts.transfer = unreachable
    print(f"\nUTS error: send returned {comm.send(sw_req2)}")
    del uts.transfer

    comm.close()
    print(f"\nline level: {len(wire_tx)} WireSent, {len(wire_rx)} WireReceived")
    history.close()
    errors.close()

    print("\ncomm_history.csv (first lines)")
    with open("comm_history.csv", encoding="utf-8") as f:
        for line in f.readlines()[:4]:
            print("  " + line.rstrip())
    print("\ncomm_errors.log")
    with open("comm_errors.log", encoding="utf-8") as f:
        for line in f:
            print("  " + line.rstrip())


if __name__ == "__main__":
    main()
