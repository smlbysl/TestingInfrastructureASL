from enum import Enum, Flag, auto


class Direction(Flag):
    RX = auto()
    TX = auto()
    BOTH = RX | TX      # bidirectional message


class Endian(Enum):
    LITTLE = "little"
    BIG = "big"
