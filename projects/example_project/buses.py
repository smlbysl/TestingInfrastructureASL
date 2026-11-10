"""Messages on buses whose PCI travels next to the data: MIL-STD-1553 and CAN.

Each bus is its own project (no shared header with ProjectBase); the PCI comes from the channel's protocol:
- 1553: node + subnet are mandatory when an object is created (bit_report(node=5, subnet=3))
- CAN : the id, here as a class default (_address); it can also be given per object
A signature inside the data still tells messages apart under the same PCI (mode_a / mode_b).
1553 words are big endian, so the 1553 project is a BigEndianStructure.
"""
from ctypes import BigEndianStructure, LittleEndianStructure, c_int16, c_uint8, c_uint16

from asl_testing import BaseMessageStructure, Direction, Signature
from projects.example_project.channels import MyChannels


# ---------------------------------------------------------------- MIL-STD-1553

class Mil1553Base(BaseMessageStructure, BigEndianStructure):
    _channel = MyChannels.BUS_A


class bit_report(Mil1553Base):
    """Built-in test result of a terminal (2 words)."""
    _fields_ = [
        ("status",      c_uint16),
        ("temperature", c_int16),
    ]


class ModeFamily(Mil1553Base):
    """Several messages on one subaddress: the first word says which one."""
    _signature = Signature("kind")


class mode_a(ModeFamily):
    _fields_ = [("kind", c_uint16), ("value", c_uint16)]
    _defaults = {"kind": 1}


class mode_b(ModeFamily):
    _fields_ = [("kind", c_uint16), ("value", c_uint16)]
    _defaults = {"kind": 2}


class motor_demand(Mil1553Base):
    """Sent to a terminal (1 word)."""
    _fields_ = [("speed", c_int16)]
    _direction = Direction.TX


# ---------------------------------------------------------------- CAN

class CanBase(BaseMessageStructure, LittleEndianStructure):
    _channel = MyChannels.CAN0


class wheel_speed(CanBase):
    _address = {"can_id": 0x123}
    _fields_ = [("rpm", c_uint16), ("valid", c_uint8)]


class brake_cmd(CanBase):
    _address = {"can_id": 0x200}
    _fields_ = [("pressure", c_uint16)]
    _direction = Direction.TX
