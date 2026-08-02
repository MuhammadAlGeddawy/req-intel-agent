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


class RetrieverAndUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sqlite_path = Path(self.tmpdir.name) / "test.db"
        self.env = {
            "DATABASE_URL": f"sqlite:///{self.sqlite_path}",
            "DB_FALLBACK_TO_SQLITE": "true",
            "SQLITE_PATH": str(self.sqlite_path),
            "OPENROUTER_API_KEY": "test-key",
        }
        self._patch = patch.dict(os.environ, self.env, clear=False)
        self._patch.start()

        import src.db as db_module
        importlib.reload(db_module)
        db_module.init_db()

    def tearDown(self):
        self._patch.stop()
        self.tmpdir.cleanup()

    def test_hybrid_search_and_rerank_returns_ingested_requirements(self):
        from src.db import RequirementEmbedding, session_scope
        from src.utils.retriever import hybrid_search_and_rerank

        with session_scope() as db:
            db.add(
                RequirementEmbedding(
                    req_id="REQ-001",
                    domain="SW",
                    req_text="The system shall detect a fault within 100 ms.",
                    asil="B",
                    reasoning="Safety detection",
                    embedding=[0.1] * 1536,
                )
            )
            db.add(
                RequirementEmbedding(
                    req_id="REQ-002",
                    domain="HW",
                    req_text="The sensor shall monitor battery voltage.",
                    asil="A",
                    reasoning="Voltage monitoring",
                    embedding=[0.2] * 1536,
                )
            )

        results = hybrid_search_and_rerank("detect fault", limit=3)

        self.assertTrue(any(item["req_id"] == "REQ-001" for item in results))
        self.assertLessEqual(len(results), 3)

    def test_ingest_knowledge_base_payload_persists_rows_and_links(self):
        from src.api import ingest_knowledge_base_payload
        from src.db import RequirementEmbedding, RequirementLink, session_scope

        payload = {
            "requirements": [
                {
                    "req_id": "REQ-100",
                    "domain": "SW",
                    "req_text": "The software shall enter a safe state on fault detection.",
                    "asil": "C",
                    "reasoning": "Safe state",
                },
                {
                    "req_id": "REQ-101",
                    "domain": "HW",
                    "req_text": "The hardware shall detect over-temperature.",
                    "asil": "B",
                    "reasoning": "Temperature monitoring",
                },
            ],
            "links": [
                {"source_req_id": "REQ-100", "target_req_id": "REQ-101", "link_type": "derived_from"}
            ],
        }

        result = ingest_knowledge_base_payload(payload)

        self.assertEqual(result["requirements_ingested"], 2)
        self.assertEqual(result["links_ingested"], 1)

        with session_scope() as db:
            rows = db.query(RequirementEmbedding).all()
            links = db.query(RequirementLink).all()

        self.assertEqual(len(rows), 2)
        self.assertEqual(len(links), 1)


if __name__ == "__main__":
    unittest.main()
