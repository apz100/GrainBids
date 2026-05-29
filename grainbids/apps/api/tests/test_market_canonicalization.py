from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.market_canonicalization import (  # noqa: E402
    canonical_commodity_name,
    canonical_location_name,
    canonical_source_name,
    region_source_names,
    source_scope,
)


class MarketCanonicalizationTests(unittest.TestCase):
    def test_source_aliases(self) -> None:
        self.assertEqual(canonical_source_name("glg"), "Great Lakes Grain")
        self.assertEqual(canonical_source_name("LAC"), "London Agricultural Commodities")
        self.assertEqual(canonical_source_name("Hensall HDC"), "Hensall Co-operative")
        self.assertEqual(canonical_source_name("Snobelen"), "Snobelen Farms")
        self.assertEqual(canonical_source_name("The Andersons"), "The Andersons")
        self.assertEqual(canonical_source_name("Ontario Daily File"), "Ontario Cash Bids")
        self.assertEqual(canonical_source_name("Eastern Ontario Daily File"), "Eastern Ontario Cash Bids")

    def test_location_normalizes_any_branch(self) -> None:
        self.assertEqual(canonical_location_name("Any Wanstead Branch"), "Wanstead Branch")
        self.assertEqual(canonical_location_name("Any   Wanstead   Branch"), "Wanstead Branch")

    def test_location_strips_trailing_commodity(self) -> None:
        self.assertEqual(canonical_location_name("Blenheim Corn"), "Blenheim")
        self.assertEqual(canonical_location_name("Brinston Soybeans"), "Brinston")

    def test_commodity_aliases(self) -> None:
        self.assertEqual(canonical_commodity_name("soybean"), "Soybeans")
        self.assertEqual(canonical_commodity_name("corn"), "Corn")

    def test_source_scope_region_vs_company(self) -> None:
        self.assertEqual(source_scope("Ontario Cash Bids"), ("region", "Ontario"))
        self.assertEqual(source_scope("Ontario Daily File"), ("region", "Ontario"))
        self.assertEqual(source_scope("Eastern Ontario Daily File"), ("region", "Eastern Ontario"))
        self.assertEqual(source_scope("GLG"), ("company", "Great Lakes Grain"))

    def test_region_source_names(self) -> None:
        self.assertEqual(region_source_names("Ontario"), ("Ontario Cash Bids",))
        self.assertEqual(region_source_names("Eastern Ontario"), ("Eastern Ontario Cash Bids",))
        self.assertEqual(region_source_names("Unknown Region"), ())


if __name__ == "__main__":
    unittest.main()
