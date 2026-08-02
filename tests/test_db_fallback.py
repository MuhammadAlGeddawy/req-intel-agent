import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class DatabaseFallbackTests(unittest.TestCase):
    def test_init_db_falls_back_to_sqlite_when_postgres_is_unavailable(self):
        import src.db as db_module

        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "fallback.db"
            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql+psycopg://postgres:postgres@postgres:5432/requirements_agent",
                    "DB_FALLBACK_TO_SQLITE": "true",
                    "SQLITE_PATH": str(sqlite_path),
                },
                clear=False,
            ):
                reloaded_module = importlib.reload(db_module)
                reloaded_module.init_db()

                self.assertTrue(str(reloaded_module.engine.url).startswith("sqlite"))
                self.assertTrue(sqlite_path.exists())

                reloaded_module.engine.dispose()


if __name__ == "__main__":
    unittest.main()
