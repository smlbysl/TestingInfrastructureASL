"""Channels of the project. Links (ETH1, SER1) are defined in the setup file."""
from generic.channel import Channel, ChannelSet
from project.framing import EthHeader


class MyChannels(ChannelSet):
    CONTROL = Channel("SER1")                           # RS-422 control messages
    DIAG = Channel("ETH1", envelope=EthHeader())        # Ethernet, with the 8-byte header
    RAW = Channel("ETH1")                               # Ethernet, same interface, no header
