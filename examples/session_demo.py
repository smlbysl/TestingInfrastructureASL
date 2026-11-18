"""Session demo: a test with a fake device writes a session folder (SessionLog), see docs/SESSION_LOG.md.

Run from the repository root:
    python -m examples.session_demo [--seconds 60]        # writes runs/<time>_demo/

The folder can be watched while it is written, or opened afterwards, with the monitor tool (asl_monitor,
separate repository): asl-monitor follow runs / asl-monitor open runs
"""

__author__ = "İsmail Baysal"

import argparse
import math
import threading
import time

from asl_testing import Comm, Direction, FakeUtsAdapter, SessionLog, Timing
from projects.example_project.header import ProjectBase
from projects.example_project.messages import bambaşka, comut, motor_cmd, request

SRC, DEST = 0x0001, 0x0002


def device(adapter: FakeUtsAdapter, stop: threading.Event, silent: threading.Event) -> None:
    """Plays the device: comut every 50 ms (sine + counter), bambaşka every 200 ms (ramp)."""
    status = comut(DEST, SRC, 0x20, direction=Direction.TX)
    diag = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
    t0 = time.monotonic()
    n = 0
    while not stop.is_set():
        t = time.monotonic() - t0
        if not silent.is_set():
            status.comut[0] = int(1000 + 800 * math.sin(2 * math.pi * 0.2 * t))
            status.comut[1] = n
            _send(adapter, status)
        if n % 4 == 0:
            diag.request[0] = int(t * 10) % 100
            diag.request[1] = 50 if int(t) % 6 < 3 else 10
            _send(adapter, diag)
        n += 1
        stop.wait(0.05)


def _send(adapter: FakeUtsAdapter, msg) -> None:
    ch = msg.channel
    adapter.inject(ch, ch.framing.envelope.on_send(msg.pack()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--root", default="runs")
    args = parser.parse_args()

    adapter = FakeUtsAdapter()
    comm = Comm(adapter, [ProjectBase])
    session = SessionLog(comm, args.root, name="demo")

    status = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=3))                       # RX, timeout watched
    bambaşka(0x07, SRC, 0x40)                                                           # RX on DIAG
    req = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.1))             # TX periodic
    motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05))       # TX periodic
    start = time.monotonic()
    req.on_send(lambda m: m.request.__setitem__(1, int(abs((time.monotonic() - start) % 4 - 2) * 50)))
    motor.on_send(lambda m: setattr(m, "speed", int(300 * math.sin(2 * math.pi * 0.1 * (time.monotonic() - start)))))

    stop, silent = threading.Event(), threading.Event()
    comm.open()
    comm.start(req)
    comm.start(motor)
    threading.Thread(target=device, args=(adapter, stop, silent), daemon=True).start()
    print(f"writing {session.folder}  - running {args.seconds:g} s, Ctrl+C to stop")
    try:
        end, step = time.monotonic() + args.seconds, 0
        while time.monotonic() < end:
            time.sleep(2)
            step += 1
            session.mark(f"step {step}: start request")
            motor.cmd.startReq = 1                       # a one-shot request every 2 s
            if step % 5 == 0:                            # the device goes quiet for a moment: RxTimeout
                silent.set()
                time.sleep(0.5)
                silent.clear()
                adapter.inject(status.channel, b"\x99" * 12)     # and an unknown packet
    except KeyboardInterrupt:
        pass
    stop.set()
    comm.close()
    session.close()
    print(f"closed {session.folder}")


if __name__ == "__main__":
    main()
