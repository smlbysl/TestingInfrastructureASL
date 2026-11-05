"""Minimal send / receive on the fake UTS.

The test sends a request. A fake device answers with a status message (request value + 1).
The answer is polled from the fake UTS, dispatched to the status object and the listener runs.

Run from the project root:  python example_send_receive.py
"""
import time

from comm import Comm
from events import MessageSent
from generic.enumerations import Direction
from project.channels import MyChannels
from project.messages import comut, request
from project.project import ProjectBase

SRC, DEST = 0x01, 0x02

comm = Comm.load("setups/fake.toml", ProjectBase, MyChannels)

req = request(SRC, DEST, 0x10, direction=Direction.TX)       # we send this
status = comut(DEST, SRC, 0x20)                                # we receive this


# --- Fake device: answers every request (only for the fake UTS) ----------------------
answer = comut(DEST, SRC, 0x20, direction=Direction.TX)


def device(event: MessageSent) -> None:
    answer.comut[0] = event.snapshot().request[0] + 1
    comm.uts.inject(answer.channel.link, answer.pack())


comm.subscribe(MessageSent, device, where=req)

# --- Test ----------------------------------------------------------------------------
comm.on_receive(status, lambda ev: print(f"listener: status.comut[0] = {ev.snapshot().comut[0]}"))

with comm:
    req.request[0] = 41
    comm.send(req)
    time.sleep(0.1)

print(f"status.comut[0] = {status.comut[0]}, UTS time = {status.rx_state.timestamp:.3f}")
print(f"logs: {comm.run_dir}")
