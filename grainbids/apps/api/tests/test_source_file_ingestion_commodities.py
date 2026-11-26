from __future__ import annotations

import sys
import unittest
from unittest.mock import Mock, patch
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_file_ingestion import _display_commodity_name, _read_source_url  # noqa: E402


class SourceFileIngestionCommodityTests(unittest.TestCase):
    def test_display_commodity_name_aliases(self) -> None:
        self.assertEqual(_display_commodity_name("corn"), "Corn")
        self.assertEqual(_display_commodity_name("soybean"), "Soybeans")
        self.assertEqual(_display_commodity_name("SOYBEANS"), "Soybeans")
        self.assertEqual(_display_commodity_name("wheat"), "Wheat")

    def test_display_commodity_name_fallback_title_case(self) -> None:
        self.assertEqual(_display_commodity_name("canola"), "Canola")
        self.assertEqual(_display_commodity_name("  "), "")


    @patch("app.services.source_file_ingestion.requests.get")
    def test_read_source_url_parses_https_csv_without_filesystem_access(self, get: Mock) -> None:
        response = Mock()
        response.content = b"location,commodity\\nChesterville,Corn\\n"
        get.return_value = response

        rows, headers = _read_source_url("https://example.test/ontario-bids.csv")

        response.raise_for_status.assert_called_once_with()
        get.assert_called_once_with("https://example.test/ontario-bids.csv", timeout=120)
        self.assertEqual(headers, ["location", "commodity"])
        self.assertEqual(rows, [{"location": "Chesterville", "commodity": "Corn"}])


if __name__ == "__main__":
    unittest.main()

