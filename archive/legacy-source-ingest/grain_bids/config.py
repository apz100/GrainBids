# grain_bids/config.py
"""
Central configuration loader. Reads config.toml from the repo root and
exposes a single `config` object used by all modules.

Usage:
    from grain_bids.config import config

    output_dir = config.output_dir
    db_path    = config.db_path
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# tomllib is stdlib in Python 3.11+; fall back to tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError(
            "tomli is required for Python < 3.11. Install with: pip install tomli"
        )

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.toml"

with open(_CONFIG_PATH, "rb") as _f:
    _raw = tomllib.load(_f)


def _resolve_output_dir(candidates: List[str]) -> Path:
    """Return the first candidate directory that can be created/accessed."""
    last_err = None
    for c in candidates:
        d = Path(c) if Path(c).is_absolute() else _REPO_ROOT / c
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"Could not create any output directory from {candidates}: {last_err}"
    )


class _Config:
    # --- Paths ---
    @property
    def output_dir(self) -> Path:
        return _resolve_output_dir(_raw["paths"]["output_candidates"])

    @property
    def db_path(self) -> Path:
        p = Path(_raw["paths"]["db_path"])
        if not p.is_absolute():
            p = _REPO_ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def posted_bids_dir(self) -> Path:
        d = Path(_raw["paths"]["posted_bids_dir"])
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # network share may not be available; callers handle gracefully
        return d

    # --- Source toggles ---
    @property
    def sources(self) -> dict:
        return dict(_raw.get("sources", {}))

    def source_enabled(self, name: str) -> bool:
        return bool(self.sources.get(name, True))

    # --- US elevator sources ---
    @property
    def us_enabled(self) -> bool:
        return bool(_raw.get("us", {}).get("enabled", False))

    @property
    def us_elevators(self) -> list:
        """List of US elevator dicts from [[us.elevators]] in config.toml."""
        return list(_raw.get("us", {}).get("elevators", []))

    # --- Posted bid params ---
    @property
    def posted_bid(self) -> dict:
        return dict(_raw.get("posted_bid", {}))

    @property
    def exclude_corn(self) -> List[str]:
        return list(_raw.get("posted_bid", {}).get("exclude_corn", []))

    @property
    def exclude_soybeans(self) -> List[str]:
        return list(_raw.get("posted_bid", {}).get("exclude_soybeans", []))

    # --- Notifications ---
    @property
    def notifications(self) -> dict:
        return dict(_raw.get("notifications", {}))

    @property
    def notifications_enabled(self) -> bool:
        return bool(self.notifications.get("enabled", False))


config = _Config()
