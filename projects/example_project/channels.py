"""Channels of the project: one per UTS interface. Messages get them as class defaults (_channel)."""

__author__ = "İsmail Baysal"

from asl_testing import ChannelSet, EthernetChannel, Rs422Channel, Framing
from projects.example_project.framing import EthHeader


class MyChannels(ChannelSet):
    CONTROL = Rs422Channel(0)                                   # RS-422 control messages
    DIAG = EthernetChannel(1, Framing(envelope=EthHeader()))    # Ethernet, with the 8-byte header
    SER2 = Rs422Channel(2)                                      # RS-422, messages identified by the channel
