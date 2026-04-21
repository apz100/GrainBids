from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_registry import ADAPTERS, get_adapter, list_adapters  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
