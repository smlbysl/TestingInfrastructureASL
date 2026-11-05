"""Setup file (TOML): everything that depends on the test bench, not on the project.

    [uts]       base_url, timeout, fake, config_mode ("auto" / "manual")
    [comm]      poll_interval
    [logging]   dir, level, console, [logging.levels]
    [links.X]   bus, interface, settings of the UTS interface
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UtsConfig:
    base_url: str = "http://localhost:8000"
    timeout: float = 2.0
    fake: bool = False
    config_mode: str = "auto"


@dataclass
class CommConfig:
    poll_interval: float = 0.01


@dataclass
class LoggingConfig:
    dir: str = "logs"                           # every run writes into its own sub folder
    level: str = "INFO"
    console: bool = False
    levels: dict[str, str] = field(default_factory=dict)


@dataclass
class SetupConfig:
    path: Path
    uts: UtsConfig
    comm: CommConfig
    logging: LoggingConfig
    links: dict[str, dict[str, Any]]


def load_config(path: str | Path) -> SetupConfig:
    path = Path(path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - {"uts", "comm", "logging", "links"}
    if unknown:
        raise ValueError(f"{path}: unknown sections {', '.join(sorted(unknown))}")
    return SetupConfig(
        path=path,
        uts=UtsConfig(**data.get("uts", {})),
        comm=CommConfig(**data.get("comm", {})),
        logging=LoggingConfig(**data.get("logging", {})),
        links=data.get("links", {}),
    )
