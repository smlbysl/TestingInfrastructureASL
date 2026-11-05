"""Builds a Comm from a setup file. Used by Comm.load; independent of any test framework.

1. read the setup file
2. create the run folder and set up logging
3. create the links from the setup file and check them
4. bind the project's channels to the links and check them
5. create the UTS client (fake or HTTP), the Comm and the message history log
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Sequence

from comm.comm import Comm
from comm.config import load_config
from comm.link import CONFIG_MODES, Link
from comm.logsetup import setup_logging
from comm.uts import FakeUtsClient, HttpUtsClient
from generic.basemessage import BaseMessageStructure
from generic.channel import ChannelSet
from services.commlogger import CommLogger

log = logging.getLogger(__name__)


def build(setup_file, projects: Sequence[type[BaseMessageStructure]], channels: type[ChannelSet]) -> Comm:
    config = load_config(setup_file)
    run_dir = Path(config.logging.dir) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    run_dir.mkdir(parents=True, exist_ok=True)
    log_file = setup_logging(config.logging, run_dir)
    log.info("setup %s, run folder %s", config.path, run_dir)

    if config.uts.config_mode not in CONFIG_MODES:
        raise ValueError(f"[uts] config_mode must be one of {CONFIG_MODES}")
    links = {name: Link.from_config(name, section, config.uts.config_mode)
             for name, section in config.links.items()}
    _check_links(links)
    channels.bind(links)

    if config.uts.fake:
        uts = FakeUtsClient()
        log.info("UTS: fake client")
    else:
        uts = HttpUtsClient(config.uts.base_url, config.uts.timeout)
        log.info("UTS: %s", config.uts.base_url)

    comm = Comm(uts, projects, links, channels, config.comm.poll_interval)
    comm.config = config
    comm.run_dir = run_dir
    comm.log_file = log_file
    comm.add_service(CommLogger(comm, run_dir / "comm_history.csv"))
    log.info("%d link(s): %s; %d channel(s): %s", len(links), ", ".join(map(str, links.values())),
             len(list(channels.all())), ", ".join(ch.name for ch in channels.all()))
    return comm


def _check_links(links: dict[str, Link]) -> None:
    used: dict[tuple[str, int], str] = {}
    for link in links.values():
        key = (link.bus, link.interface)
        if key in used:
            raise ValueError(f"links {used[key]} and {link.name} both use {link.bus}/{link.interface}")
        used[key] = link.name
