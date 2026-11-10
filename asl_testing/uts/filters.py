"""Filter calculations: message objects -> UTS filter groups (pure functions).

A group is a list of (byte position on the line, value); a filter is a list of groups (OR).
Positions are on the line, so the protocol header in front of the message is added (offset).
"""


def signature_filter(msg, offset: int = 0) -> list[tuple[int, int]]:
    """The signature bytes of a message object as one filter group.

    offset: bytes in front of the message on the line (the channel protocol's offset).
    Only bytes covered by the signature mask are used. A byte only partly covered (bit field)
    is given with its masked value; whether UTS accepts that is an open point.
    """
    sig = msg._signature
    if sig is None or sig.mask is None:
        raise ValueError(f"{type(msg).__name__} has no signature: no filter bytes")
    data = bytes(msg)[sig.offset:sig.offset + len(sig.mask)]
    return [(offset + sig.offset + i, b & m) for i, (b, m) in enumerate(zip(data, sig.mask)) if m]
