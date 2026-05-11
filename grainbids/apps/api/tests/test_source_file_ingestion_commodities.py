from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_file_ingestion import _display_commodity_name  # noqa: E402


class SourceFileIngestionCommodityTests(unittest.TestCase):
    def test_display_commodity_name_aliases(self) -> None:
        self.assertEqual(_display_commodity_name("corn"), "Corn")
        self.assertEqual(_display_commodity_name("soybean"), "Soybeans")
        self.assertEqual(_display_commodity_name("SOYBEANS"), "Soybeans")
        self.assertEqual(_display_commodity_name("wheat"), "Wheat")

    def test_display_commodity_name_fallback_title_case(self) -> None:
        self.assertEqual(_display_commodity_name("canola"), "Canola")
        self.assertEqual(_display_commodity_name("  "), "")


if __name__ == "__main__":
    unittest.main()

