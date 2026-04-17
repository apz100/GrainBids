from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

if hasattr(__import__('sys'), 'version_info') and __import__('sys').version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class SourceConfig:
    enabled_sources: dict[str, bool]
    us_enabled: bool
    us_elevators: list[dict[str, Any]]


def load_source_config(config_path: str | Path) -> SourceConfig:
    path = Path(config_path)
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return SourceConfig(
        enabled_sources=dict(data.get("sources", {})),
        us_enabled=bool(data.get("us", {}).get("enabled", False)),
        us_elevators=list(data.get("us", {}).get("elevators", [])),
    )
