from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_registry import ADAPTERS, get_adapter, list_adapters, list_pilot_adapter_keys  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
