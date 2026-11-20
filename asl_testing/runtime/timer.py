"""Timer resolution on Windows: 1 ms while a Comm is open.

Windows wakes sleeping threads (Event.wait, time.sleep before 3.11) on its system timer, 15.6 ms by
default; a 5 ms period then runs at ~64 Hz. timeBeginPeriod(1) lowers it to 1 ms for this process
until timeEndPeriod(1). Other systems: nothing to do.
"""

__author__ = "İsmail Baysal"

import sys
import threading

_lock = threading.Lock()
_users = 0


def _winmm():
    import ctypes
    return ctypes.WinDLL("winmm")


def begin() -> None:
    """Asks for 1 ms timer resolution (counted: the first caller sets it)."""
    global _users
    if sys.platform != "win32":
        return
    with _lock:
        if _users == 0:
            _winmm().timeBeginPeriod(1)
        _users += 1


def end() -> None:
    """Gives the resolution back (the last caller restores it)."""
    global _users
    if sys.platform != "win32":
        return
    with _lock:
        if _users == 0:
            return
        _users -= 1
        if _users == 0:
            _winmm().timeEndPeriod(1)
