"""UTS filter groups from message signatures.

A group is a list of (byte position on the line, value); a filter is a list of groups (OR).
"""

__author__ = "İsmail Baysal"


def signature_filter(msg, offset: int = 0) -> list[tuple[int, int]]:
    """Signature bytes of a message as one filter group.

    offset: header size in front of the message (envelope.offset). A byte only partly covered by
    the mask (bit field) is given with its masked value; whether UTS accepts that is open.
    """
    sig = msg._signature
    if sig is None or sig.mask is None:
        raise ValueError(f"{type(msg).__name__} has no signature: no filter bytes")
    data = bytes(msg)[sig.offset:sig.offset + len(sig.mask)]
    return [(offset + sig.offset + i, b & m) for i, (b, m) in enumerate(zip(data, sig.mask)) if m]
