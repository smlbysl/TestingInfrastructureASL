"""Minimal send / receive over the fake UTS.

The test sends a request. A fake device answers with a status message (request value + 1).
The answer is polled from the fake UTS, dispatched to the status object and the listener runs.

Run from the repository root:  python -m examples.example_send_receive
"""
import time

from asl_testing import Comm, FakeUtsClient, MessageReceived, MessageSent, Direction
from projects.example_project.messages import comut, request
from projects.example_project.header import ProjectBase

SRC, DEST = 0x01, 0x02

uts = FakeUtsClient()
comm = Comm(uts, [ProjectBase], poll_interval=0.01)

# --- Message objects -------------------------------------------------------------
req = request(SRC, DEST, 0x10, direction=Direction.TX)      # we send this
status = comut(DEST, SRC, 0x20)                               # we receive this (default direction RX)


# --- Fake device: answers every request ----------------------------------------------
device_answer = comut(DEST, SRC, 0x20, direction=Direction.TX)   # the device's copy of the status message


def device(event: MessageSent) -> None:
    device_answer.comut[0] = event.snapshot().request[0] + 1
    uts.device_sends(device_answer)                               # appears in the UTS receive buffer


comm.subscribe(MessageSent, device, where=req)


# --- Trace: prints every sent / received message (like a trace window) ------------------
def trace(event) -> None:
    if isinstance(event, (MessageSent, MessageReceived)):
        direction = "TX" if isinstance(event, MessageSent) else "RX"
        print(f"  trace {direction} {type(event.message).__name__:8} {event.channel}  {event.raw.hex(' ')}")


comm.subscribe(object, trace)

# --- Listener of the test ------------------------------------------------------------
comm.on_receive(status, lambda ev: print(f"  listener: status.comut[0] = {ev.snapshot().comut[0]}"))

# --- Test -----------------------------------------------------------------------------
with comm:                                        # open(): RX poller + TX scheduler start
    req.request[0] = 41
    comm.send(req)
    time.sleep(0.1)                               # give the poller time to fetch the answer

print(f"\nsent to UTS     : {len(uts.sent)} packet(s), first on {uts.sent[0][0]}:{uts.sent[0][1]}")
print(f"status.comut[0] : {status.comut[0]}")
print(f"status rx_state : count={status.rx_state.count}, uts time={status.rx_state.timestamp:.3f}")
