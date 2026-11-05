"""End-to-end example on the fake UTS.

Shows: periodic and one-shot TX, RX dispatch, a channel with an envelope, raw rules,
unknown / invalid packets, RX timeout, baseline and reset, UTS functions and the log files.

Run from the project root:  python example.py
"""
import time

from comm import Comm
from generic.enumerations import Direction
from generic.timing import Timing
from project.channels import MyChannels
from project.messages import bambaşka, comut, diag_log, request
from project.project import ProjectBase
from project.testing import device_send

SRC, DEST = 0x01, 0x02


def main() -> None:
    comm = Comm.load("setups/fake.toml", ProjectBase, MyChannels)

    sw_req = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.02))
    status = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=1.5))
    diag = bambaşka(0x07, SRC, 0x40)                       # Family2 -> DIAG channel (Ethernet + header)
    log = diag_log(DEST, SRC, 0x50)                        # variable size

    with comm:
        # --- baseline: what must run in every test ---------------------------------
        comm.start(sw_req)
        comm.mark_baseline()

        # --- TX ------------------------------------------------------------------------
        time.sleep(0.1)
        print(f"TX  periodic request sent {sw_req.tx_state.count} times on {sw_req.channel}")

        # --- RX ------------------------------------------------------------------------
        remote = comut(DEST, SRC, 0x20, direction=Direction.TX)
        remote.comut[0] = 0xCAFE
        device_send(comm, remote)
        remote_diag = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
        remote_diag.request[0] = 0x1234
        wire = device_send(comm, remote_diag)
        remote_log = diag_log(DEST, SRC, 0x50, direction=Direction.TX)
        remote_log.count = 2
        remote_log.entries[0], remote_log.entries[1] = 0x100, 0x101
        device_send(comm, remote_log)
        time.sleep(0.05)
        print(f"RX  status.comut[0] = 0x{status.comut[0]:X} (CONTROL)")
        print(f"RX  diag.request[0] = 0x{diag.request[0]:X} (DIAG, header {wire[:8].hex(' ')} removed)")
        print(f"RX  diag_log count={log.count} entries={[hex(x) for x in log.entries[:3]]}")

        # --- raw rule: drop packets on a channel ------------------------------------
        MyChannels.CONTROL.on_receive_raw(lambda data: None)
        remote.comut[0] = 0xBEEF
        device_send(comm, remote)
        time.sleep(0.05)
        print(f"RAW rule dropped the packet: status.comut[0] still 0x{status.comut[0]:X}")

        # --- unknown / invalid ------------------------------------------------------
        comm.uts.inject(MyChannels.DIAG.link, b"\x01\x02\x03")          # no header -> RAW channel
        time.sleep(0.05)
        print(f"RX  unknown: {[(f.link.name, f.channel.name) for f in comm.unknown]}")

        # --- RX timeout (status is periodic: 50 ms, tolerance 1.5) --------------------
        time.sleep(0.1)

        # --- reset back to the baseline ----------------------------------------------
        comm.stop(sw_req)
        comm.reset()
        print(f"RESET periodic request running again: {comm.is_running(sw_req)}, "
              f"raw rules on CONTROL: {len(MyChannels.CONTROL._rx_rules)}")

        # --- UTS functions -------------------------------------------------------------
        comm.set_filter(MyChannels.DIAG, [[(0, 0x55), (1, 0xAA)]])
        comm.clear(MyChannels.CONTROL)
        comm.configure(MyChannels.CONTROL, baud_rate=115200)

    print(f"\nlogs in {comm.run_dir}")
    print("comm.log (warnings):")
    with open(comm.log_file, encoding="utf-8") as f:
        for line in f:
            if "WARNING" in line:
                print("  " + line.rstrip())


if __name__ == "__main__":
    main()
