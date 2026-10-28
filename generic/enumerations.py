from enum import Enum, Flag, auto


class ProtocolType(Enum):
    ETHERNET = "ethernet"
    RS422 = "rs422"
    CAN = "can"


class Direction(Flag):
    RX = auto()
    TX = auto()
    BOTH = RX | TX      # bidirectional message


class Endian(Enum):
    LITTLE = "little"
    BIG = "big"
