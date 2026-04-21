"""Compatibility package for legacy imports.

Grain price source pullers now live in:
`app.platform.market_data.sources`

This package keeps older imports working during migration.
"""
from pathlib import Path

_legacy_path = Path(__file__).resolve().parents[2] / "platform" / "market_data" / "sources"
if _legacy_path.exists():
    __path__.append(str(_legacy_path))  # type: ignore[name-defined]
