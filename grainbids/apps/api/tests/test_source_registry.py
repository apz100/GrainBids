from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_registry import (  # noqa: E402
    ADAPTERS,
    SourceFetchTarget,
    fetch_with_adapter,
    get_adapter,
    list_adapters,
    list_pilot_adapter_keys,
)


class SourceRegistryTests(unittest.TestCase):
    def test_list_adapters_not_empty(self) -> None:
        rows = list_adapters()
        self.assertGreater(len(rows), 0)

    def test_get_adapter_known(self) -> None:
        key = next(iter(ADAPTERS.keys()))
        adapter = get_adapter(key)
        self.assertEqual(adapter.key, key)

    def test_get_adapter_unknown_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_adapter("missing-source-key")

    def test_pilot_keys_are_supported(self) -> None:
        pilot_keys = list_pilot_adapter_keys()
        self.assertGreaterEqual(len(pilot_keys), 3)
        self.assertTrue({"agricharts", "glg", "hensall", "snobelen", "andersons"}.issubset(set(pilot_keys)))
        for key in pilot_keys:
            self.assertIn(key, ADAPTERS)

    def test_us_adapters_require_per_source_target(self) -> None:
        self.assertTrue(get_adapter("us_agricharts").requires_target)
        self.assertTrue(get_adapter("us_dtn").requires_target)

    def test_targeted_direct_adapter_receives_url_and_name(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_fetch(url: str, name: str) -> pd.DataFrame:
            calls.append((url, name))
            return pd.DataFrame([{"Location": name, "Commodity": "Corn"}])

        module = SimpleNamespace(fetch_us_agricharts=fake_fetch)
        target = SourceFetchTarget(name="Example Elevator", url="https://example.test/cash-bids")
        with patch("app.services.source_registry.import_module", return_value=module):
            result = fetch_with_adapter(get_adapter("us_agricharts"), target=target)

        self.assertEqual(calls, [(target.url, target.name)])
        self.assertEqual(len(result.index), 1)

    def test_targeted_adapter_rejects_missing_url(self) -> None:
        module = SimpleNamespace(fetch_us_agricharts=lambda _url, _name: pd.DataFrame())
        with patch("app.services.source_registry.import_module", return_value=module):
            with self.assertRaisesRegex(ValueError, "requires a source name and URL"):
                fetch_with_adapter(get_adapter("us_agricharts"))


if __name__ == "__main__":
    unittest.main()
