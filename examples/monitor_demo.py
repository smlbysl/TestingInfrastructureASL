"""Monitor demo: a fake device sends changing values, the test sends periodic messages.

Run from the repository root:   python -m examples.monitor_demo [--seconds 60] [--port 8050]
Open http://127.0.0.1:8050, then Tools > Start measurement and add fields from the tree.
The packets are also written to monitor_demo.csv (CommLogger): open it later with File > Import CSV,
or without a test:
    python -m asl_testing.services.monitor projects.example_project.header:ProjectBase projects.example_project.messages
"""

__author__ = "İsmail Baysal"

import argparse
import math
import threading
import time

from asl_testing import Comm, Direction, FakeUtsClient, Timing, CommLogger, MonitorService
from projects.example_project.header import ProjectBase
from projects.example_project.messages import bambaşka, comut, motor_cmd, request

SRC, DEST = 0x0001, 0x0002


def device(uts: FakeUtsClient, stop: threading.Event) -> None:
    """Plays the device: comut every 50 ms (sine + counter), bambaşka every 200 ms (ramp)."""
    status = comut(DEST, SRC, 0x20, direction=Direction.TX)
    diag = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
    t0 = time.monotonic()
    n = 0
    while not stop.is_set():
        t = time.monotonic() - t0
        status.comut[0] = int(1000 + 800 * math.sin(2 * math.pi * 0.2 * t))
        status.comut[1] = n
        _send(uts, status)
        if n % 4 == 0:
            diag.request[0] = int(t * 10) % 100
            diag.request[1] = 50 if int(t) % 6 < 3 else 10
            _send(uts, diag)
        n += 1
        stop.wait(0.05)


def _send(uts: FakeUtsClient, msg) -> None:
    ch = msg.channel
    uts.inject(ch, ch.framing.envelope.on_send(msg.pack()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--record", action="store_true", help="start measuring at once (no Tools > Start)")
    args = parser.parse_args()

    uts = FakeUtsClient()
    comm = Comm(uts, [ProjectBase])
    history = CommLogger(comm, "monitor_demo.csv")
    monitor = MonitorService(comm, [ProjectBase], port=args.port)

    # messages of the test
    status = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=3))                       # RX
    diag = bambaşka(0x07, SRC, 0x40)                                                    # RX on DIAG
    req = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.1))             # TX periodic
    motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05))       # TX periodic
    start = time.monotonic()
    req.on_send(lambda m: m.request.__setitem__(1, int(abs((time.monotonic() - start) % 4 - 2) * 50)))
    motor.on_send(lambda m: setattr(m, "speed", int(300 * math.sin(2 * math.pi * 0.1 * (time.monotonic() - start)))))

    stop = threading.Event()
    comm.open()
    monitor.start()
    if args.record:
        monitor.listen()
    comm.start(req)
    comm.start(motor)
    threading.Thread(target=device, args=(uts, stop), daemon=True).start()
    print(f"monitor on {monitor.url}  (Tools > Start measurement)  - running {args.seconds:g} s, Ctrl+C to stop")
    try:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            time.sleep(2)
            motor.cmd.startReq = 1                       # a one-shot request every 2 s
    except KeyboardInterrupt:
        pass
    stop.set()
    comm.close()
    monitor.stop()
    history.close()
    print("packets written to monitor_demo.csv")


if __name__ == "__main__":
    main()
