from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402


class RuntimeConfigTests(unittest.TestCase):
    def test_production_requires_database_url(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                database_url="",
                allow_implicit_org=False,
                api_cors_origins="https://grainbids.com",
            )

    def test_production_requires_explicit_org(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                database_url="postgresql+psycopg://test:test@localhost:5432/test",
                allow_implicit_org=True,
                api_cors_origins="https://grainbids.com",
            )

    def test_production_accepts_valid_settings(self) -> None:
        settings = Settings(
            app_env="production",
            database_url="postgresql+psycopg://test:test@localhost:5432/test",
            allow_implicit_org=False,
            api_cors_origins="https://grainbids.com,https://www.grainbids.com",
        )
        self.assertEqual(
            settings.api_cors_origins_list,
            ["https://grainbids.com", "https://www.grainbids.com"],
        )


if __name__ == "__main__":
    unittest.main()
