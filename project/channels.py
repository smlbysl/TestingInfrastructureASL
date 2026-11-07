"""Channels of the project. Messages get them as class defaults (_channel)."""
from generic.channel import ChannelSet, EthernetChannel, Rs422Channel
from generic.framing import Framing
from project.framing import EthHeader


class MyChannels(ChannelSet):
    CONTROL = Rs422Channel(0)                                   # RS-422 control messages
    DIAG = EthernetChannel(1, Framing(envelope=EthHeader()))    # Ethernet, with the 8-byte header
    RAW = EthernetChannel(1)                                    # Ethernet, same interface, no header
