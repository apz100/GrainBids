"""Market source ingestion module.

This package hosts migrated grain-price pullers and orchestration helpers that were
previously in legacy root scripts. Keep new integration work under app/platform.
"""
from pathlib import Path
import sys

_sources_path = Path(__file__).resolve().parent
if str(_sources_path) not in sys.path:
    # Legacy source adapters import siblings like "processing" as top-level modules.
    sys.path.insert(0, str(_sources_path))
