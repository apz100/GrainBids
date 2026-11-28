from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_file_ingestion import (  # noqa: E402
    _display_commodity_name,
    _read_source_url,
    _source_identifier,
)


class SourceFileIngestionCommodityTests(unittest.TestCase):
    def test_display_commodity_name_aliases(self) -> None:
        self.assertEqual(_display_commodity_name("corn"), "Corn")
        self.assertEqual(_display_commodity_name("soybean"), "Soybeans")
        self.assertEqual(_display_commodity_name("SOYBEANS"), "Soybeans")
        self.assertEqual(_display_commodity_name("wheat"), "Wheat")

    def test_display_commodity_name_fallback_title_case(self) -> None:
        self.assertEqual(_display_commodity_name("canola"), "Canola")
        self.assertEqual(_display_commodity_name("  "), "")

    def test_source_identifier_preserves_https_url_for_reprocessing(self) -> None:
        url = "https://example.test/ontario-bids.csv?as_of=2026-11-28"
        self.assertEqual(_source_identifier(url), url)

    @patch("app.services.source_file_ingestion.requests.get")
    def test_read_source_url_parses_https_csv_without_filesystem_access(self, get: Mock) -> None:
        response = Mock()
        response.content = b"location,commodity\nChesterville,Corn\n"
        get.return_value = response

        rows, headers = _read_source_url("https://example.test/ontario-bids.csv")

        response.raise_for_status.assert_called_once_with()
        get.assert_called_once_with("https://example.test/ontario-bids.csv", timeout=120)
        self.assertEqual(headers, ["location", "commodity"])
        self.assertEqual(rows, [{"location": "Chesterville", "commodity": "Corn"}])


    @patch("app.services.source_file_ingestion._read_multi_sheet_workbook_from_dataframes")
    @patch("app.services.source_file_ingestion.pd.read_excel")
    @patch("app.services.source_file_ingestion.requests.get")
    def test_read_source_url_parses_https_xlsx_via_in_memory_stream(
        self,
        get: Mock,
        read_excel: Mock,
        normalize_workbook: Mock,
    ) -> None:
        response = Mock()
        response.content = b"mock-xlsx-payload"
        get.return_value = response
        workbook = {"Corn": Mock()}
        read_excel.return_value = workbook
        expected = ([{"location": "Chesterville", "commodity": "Corn"}], ["location", "commodity"])
        normalize_workbook.return_value = expected

        rows, headers = _read_source_url("https://example.test/ontario-bids.xlsx")

        response.raise_for_status.assert_called_once_with()
        get.assert_called_once_with("https://example.test/ontario-bids.xlsx", timeout=120)
        buffer = read_excel.call_args.args[0]
        self.assertEqual(buffer.read(), b"mock-xlsx-payload")
        self.assertEqual(read_excel.call_args.kwargs, {"sheet_name": None})
        normalize_workbook.assert_called_once_with(workbook, source_label="https://example.test/ontario-bids.xlsx")
        self.assertEqual((rows, headers), expected)

if __name__ == "__main__":
    unittest.main()

