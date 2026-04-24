from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform.market_data.service import get_sources_path  # noqa: E402
from app.services.source_registry import get_adapter, list_pilot_adapter_keys  # noqa: E402


class PilotAdapterRuntimeTests(unittest.TestCase):
    def test_required_runtime_dependencies_import(self) -> None:
        requests = importlib.import_module("requests")
        bs4 = importlib.import_module("bs4")
        self.assertIsNotNone(requests)
        self.assertIsNotNone(bs4)

    def test_pilot_adapter_modules_and_functions_exist(self) -> None:
        sources_path = str(get_sources_path())
        if sources_path not in sys.path:
            sys.path.insert(0, sources_path)

        for key in list_pilot_adapter_keys():
            adapter = get_adapter(key)
            module = importlib.import_module(f"app.platform.market_data.sources.{adapter.module}")
            self.assertTrue(hasattr(module, adapter.function), f"{key} missing function {adapter.function}")
            self.assertTrue(callable(getattr(module, adapter.function)))


if __name__ == "__main__":
    unittest.main()
