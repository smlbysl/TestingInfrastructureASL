"""UtsControl: direct (vertical) access from the test to UTS management.

Configuration and receive filters of a UTS interface. Synchronous: a call returns the result or
raises (UtsError from the client). Independent of the RX / TX threads and of events; it only
shares the UtsClient with them.

The target is a message object or a Channel; a message gives its channel. The channel's
UTS path + interface select the UTS interface, so channels sharing an address share its
configuration and its filter. Filter positions are on the line: the protocol's header size
(protocol.offset) is added to the signature position.

    comm.control.add_filter(status)                # signature bytes of the message, on the line
    comm.control.remove_filter(status)
    comm.control.clear_filter(MyChannels.CONTROL)
    comm.control.set_config(status, baudRate=115200)
"""
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
        return self.uts.get_config(ch.protocol.path, ch.interface)

    def set_config(self, target: Target, **settings) -> None:
        ch = _channel(target)
        self.uts.set_config(ch.protocol.path, ch.interface, settings)
        self.log.info("%s: config %s", ch, settings)

    # ---------------------------------------------------------------- filters

    def get_filter(self, target: Target) -> tuple[str, FilterGroups]:
        """(kind, groups) of the interface; kind "NONE" means no filter."""
        ch = _channel(target)
        return self.uts.get_filter(ch.protocol.path, ch.interface)

    def set_filter(self, target: Target, groups: FilterGroups, kind: str = "INCLUSIVE") -> None:
        """Writes a whole filter: OR of groups, each an AND of (byte position on the line, value)."""
        ch = _channel(target)
        self.uts.set_filter(ch.protocol.path, ch.interface, kind, groups)
        self.log.info("%s: filter %s %s", ch, kind, groups)

    def clear_filter(self, target: Target) -> None:
        """Removes the filter of the interface: every packet passes again."""
        ch = _channel(target)
        self.uts.set_filter(ch.protocol.path, ch.interface, "NONE", [])
        self.log.info("%s: filter cleared", ch)

    def add_filter(self, msg: BaseMessageStructure) -> None:
        """Adds the message's signature bytes to the interface's filter (read, add, write back).

        The first one switches the interface from "everything passes" to "only the filter passes".
        Adding the same message twice changes nothing.
        """
        ch = msg.channel
        group = signature_filter(msg, ch.protocol.offset)
        kind, groups = self.uts.get_filter(ch.protocol.path, ch.interface)
        if group in groups:
            return
        groups = groups + [group]
        self.uts.set_filter(ch.protocol.path, ch.interface, "INCLUSIVE", groups)
        self.log.info("%s: filter + %s %s", ch, type(msg).__name__, group)

    def remove_filter(self, msg: BaseMessageStructure) -> None:
        """Removes the message's group from the filter; no group left -> no filter."""
        ch = msg.channel
        group = signature_filter(msg, ch.protocol.offset)
        kind, groups = self.uts.get_filter(ch.protocol.path, ch.interface)
        if group not in groups:
            return
        groups = [g for g in groups if g != group]
        self.uts.set_filter(ch.protocol.path, ch.interface, "INCLUSIVE" if groups else "NONE", groups)
        self.log.info("%s: filter - %s", ch, type(msg).__name__)


def _channel(target: Target) -> Channel:
    return target if isinstance(target, Channel) else target.channel
