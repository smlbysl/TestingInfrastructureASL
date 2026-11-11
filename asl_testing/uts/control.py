"""UtsControl: configuration and receive filters of a UTS interface, called directly from the test.

Calls are synchronous (result or UtsError) and independent of the RX / TX threads.
The target is a channel or a message (its channel); the channel selects protocol + interface.

    comm.control.add_filter(status)
    comm.control.remove_filter(status)
    comm.control.clear_filter(MyChannels.CONTROL)
    comm.control.set_config(status, baudRate=115200)
"""

__author__ = "İsmail Baysal"
import logging
from typing import Any, Union

from asl_testing.channel.channel import Channel
from asl_testing.message.base import BaseMessageStructure
from asl_testing.uts.client import FilterGroups, UtsClient
from asl_testing.uts.filters import signature_filter

Target = Union[Channel, BaseMessageStructure]


class UtsControl:
    def __init__(self, uts: UtsClient, log=None):
        self.uts = uts
        self.log = log or logging.getLogger(__name__)

    # ---------------------------------------------------------------- configuration

    def get_config(self, target: Target) -> dict[str, Any]:
        ch = _channel(target)
        return self.uts.get_config(ch.protocol, ch.interface)

    def set_config(self, target: Target, **settings) -> None:
        ch = _channel(target)
        self.uts.set_config(ch.protocol, ch.interface, settings)
        self.log.info("%s: config %s", ch, settings)

    # ---------------------------------------------------------------- filters

    def get_filter(self, target: Target) -> tuple[str, FilterGroups]:
        """(kind, groups) of the interface; kind "NONE" means no filter."""
        ch = _channel(target)
        return self.uts.get_filter(ch.protocol, ch.interface)

    def set_filter(self, target: Target, groups: FilterGroups, kind: str = "INCLUSIVE") -> None:
        """Writes the whole filter."""
        ch = _channel(target)
        self.uts.set_filter(ch.protocol, ch.interface, kind, groups)
        self.log.info("%s: filter %s %s", ch, kind, groups)

    def clear_filter(self, target: Target) -> None:
        """Removes the filter; every packet passes."""
        ch = _channel(target)
        self.uts.set_filter(ch.protocol, ch.interface, "NONE", [])
        self.log.info("%s: filter cleared", ch)

    def add_filter(self, msg: BaseMessageStructure) -> None:
        """Adds the message's signature bytes to the filter (read, add, write). Adding twice changes nothing."""
        ch = msg.channel
        group = signature_filter(msg, ch.framing.envelope.offset)
        kind, groups = self.uts.get_filter(ch.protocol, ch.interface)
        if group in groups:
            return
        groups = groups + [group]
        self.uts.set_filter(ch.protocol, ch.interface, "INCLUSIVE", groups)
        self.log.info("%s: filter + %s %s", ch, type(msg).__name__, group)

    def remove_filter(self, msg: BaseMessageStructure) -> None:
        """Removes the message's group; with no group left the filter is removed."""
        ch = msg.channel
        group = signature_filter(msg, ch.framing.envelope.offset)
        kind, groups = self.uts.get_filter(ch.protocol, ch.interface)
        if group not in groups:
            return
        groups = [g for g in groups if g != group]
        self.uts.set_filter(ch.protocol, ch.interface, "INCLUSIVE" if groups else "NONE", groups)
        self.log.info("%s: filter - %s", ch, type(msg).__name__)


def _channel(target: Target) -> Channel:
    return target if isinstance(target, Channel) else target.channel
