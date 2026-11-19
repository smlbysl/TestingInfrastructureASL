"""Simulated node built from subscribers (like a CAPL node): reacts to received messages, sends its status.

NodeSimulator plays the motor drive (address SIM) against the unit under test (DUT):
- on every `request` from the DUT it takes the commanded mode; when the mode changes it answers at once
- it sends `comut` every 50 ms as its status: comut[0] = mode, comut[1] = heartbeat
- if the DUT's requests stop (RX timeout) it goes to SAFE_MODE; the next request takes it out again

Every handler runs in its own subscriber thread; the status fields are filled in an on_send hook,
which runs under the lock of the message just before each send (periodic or one-shot).

With FakeUtsAdapter there is no real DUT, so a small "fake DUT" thread injects its requests.
On the real setup leave out the fake DUT and use your UtsAdapter.

Run from the repository root:  python -m examples.simulation
"""

__author__ = "İsmail Baysal"

import threading
import time

from asl_testing import Comm, Direction, FakeUtsAdapter, MessageSent, RxRestored, RxTimeout, Timing
from projects.example_project.header import ProjectBase
from projects.example_project.messages import comut, request

SIM, DUT = 0x02, 0x01
SAFE_MODE = 0xFF
T0 = time.monotonic()


def elapsed() -> float:
    return time.monotonic() - T0


class NodeSimulator:
    """Simulated motor drive: listens to the DUT's requests and sends its status."""

    def __init__(self, comm: Comm, period: float = 0.05):
        self.comm = comm
        self.mode = 0
        self.heartbeat = 0
        # RX: the DUT sends a request every 20 ms; 5 missing periods give RxTimeout
        self.command = request(DUT, SIM, 0x10, rx=Timing(0.02, tolerance=5))
        # TX: our status, sent periodically
        self.status = comut(SIM, DUT, 0x20, direction=Direction.TX, tx=Timing(period))
        self.status.on_send(self._fill_status)
        self._subs = [
            comm.on_receive(self.command, self._on_command),
            comm.subscribe(RxTimeout, self._on_timeout, where=self.command),
            comm.subscribe(RxRestored, self._on_restored, where=self.command),
        ]

    def start(self) -> None:
        self.comm.start(self.status)

    def stop(self) -> None:
        self.comm.stop(self.status)
        for sub in self._subs:
            self.comm.bus.unsubscribe(sub)

    # ---------------------------------------------------------------- handlers (subscriber threads)

    def _on_command(self, event) -> None:
        mode = event.snapshot().request[0]          # values of this packet, not of a later one
        if mode != self.mode:
            self.mode = mode
            self.comm.send(self.status)             # answer at once, not only at the next period

    def _on_timeout(self, event) -> None:
        print(f"{elapsed():5.2f} s  DUT requests stopped ({event.age:.2f} s): SAFE_MODE")
        self.mode = SAFE_MODE
        self.comm.send(self.status)

    def _on_restored(self, event) -> None:
        print(f"{elapsed():5.2f} s  DUT requests are back")

    # ---------------------------------------------------------------- hook (TX side, under the message lock)

    def _fill_status(self, msg) -> None:
        self.heartbeat += 1
        msg.comut[0] = self.mode
        msg.comut[1] = self.heartbeat


def fake_dut(adapter: FakeUtsAdapter, stop: threading.Event) -> None:
    """Stand-in for the unit under test: a request every 20 ms; pauses once to cause an RX timeout."""
    plan = [(0.3, 1), (0.6, 2), (0.9, None), (1.2, 3)]     # (until second, mode); None = silent
    cmd = request(DUT, SIM, 0x10, direction=Direction.TX)
    start = time.monotonic()
    while not stop.is_set():
        t = time.monotonic() - start
        step = next((mode for end, mode in plan if t < end), "end")
        if step == "end":
            return
        if step is not None:
            cmd.request[0] = step
            adapter.inject(cmd.channel, cmd.channel.framing.envelope.on_send(cmd.pack()))
        stop.wait(0.02)


def main() -> None:
    adapter = FakeUtsAdapter()
    comm = Comm(adapter, [ProjectBase])
    sim = NodeSimulator(comm)

    last = {"mode": None}

    def show(event) -> None:                       # trace: prints the status when its mode changes
        values = event.snapshot()
        if values.comut[0] != last["mode"]:
            last["mode"] = values.comut[0]
            print(f"{elapsed():5.2f} s  status sent: mode={values.comut[0]:#x} heartbeat={values.comut[1]}")

    comm.subscribe(MessageSent, show, where=sim.status)

    with comm:                                     # open(): RX / TX threads start
        sim.start()
        stop = threading.Event()
        dut = threading.Thread(target=fake_dut, args=(adapter, stop), name="FakeDUT", daemon=True)
        dut.start()
        dut.join()
        time.sleep(0.05)                           # last status out; shorter than the RX timeout
        sim.stop()

    print(f"\nstatus sent {sim.status.tx_state.count} times, requests received {sim.command.rx_state.count}")


if __name__ == "__main__":
    main()
