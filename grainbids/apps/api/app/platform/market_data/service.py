"""Shared GrainBids market-data service entry points.

These helpers expose neutral APIs for GrainBids product modules
to consume market pricing data without importing source pullers directly.
"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

SOURCES_PATH = Path(__file__).resolve().parent / "sources"


def get_sources_path() -> Path:
    """Return the filesystem path containing source pullers and configs."""
    return SOURCES_PATH


def load_source_module(module_name: str) -> Any:
    """Load a source adapter module by short name.

    Example: ``load_source_module("agricharts_source")``.
    """
    return import_module(f"app.platform.market_data.sources.{module_name}")
