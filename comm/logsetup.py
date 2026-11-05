"""Logging set-up for a run: one process log file for every layer.

Every module logs with logging.getLogger(__name__); this function only decides where the
records go and at which level. The handler is attached to the root logger, so any new module,
and third party libraries, end up in the same file.
"""
import logging
from pathlib import Path

from comm.config import LoggingConfig

FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s %(message)s"
DATEFMT = "%H:%M:%S"

_handlers: list[logging.Handler] = []           # handlers added by the last setup_logging call


def setup_logging(config: LoggingConfig, run_dir: Path) -> Path:
    """Writes the process log to run_dir/comm.log; returns its path."""
    root = logging.getLogger()
    for handler in _handlers:                   # a second load in the same process replaces the first
        root.removeHandler(handler)
        handler.close()
    _handlers.clear()

    formatter = logging.Formatter(FORMAT, DATEFMT)
    path = run_dir / "comm.log"
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    _handlers.append(file_handler)
    if config.console:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        _handlers.append(console)

    for handler in _handlers:
        root.addHandler(handler)
    root.setLevel(config.level)
    for name, level in config.levels.items():
        logging.getLogger(name).setLevel(level)
    return path
