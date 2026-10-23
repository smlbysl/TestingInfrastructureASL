
from enum import Enum

class ProtocolType(Enum):
    ETHERNET = "ethernet"
    RS422 = "rs422"
    CAN = "can"

class Direction(Enum):
    RX = "rx"
    TX = "tx"

class Endian(Enum):
    LITTLE = "little"
    BIG = "big"
