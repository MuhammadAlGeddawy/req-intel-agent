import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.nodes.retriever_node import retrieve_context_node


class RetrieveContextNodeTests(unittest.TestCase):
    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "The system shall detect fault within 100ms.", "domain": "SYSTEM", "safety_relevant": True, "safety_reason": "reason"},
            {"id": "REQ-HW-001", "text": "The LED driver circuit shall supply 1000 lumens.", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
        ]
        self.base_state = {
            "raw_document": "some doc",
            "document_name": "test.txt",
            "requirements": [],
            "classified": self.classified,
            "safety_assessments": [],
            "inconsistencies": [],
            "gaps": [],
            "retrieved_context": {},
            "report": None,
            "audit_log": [],
            "json_repair_needed": None,
            "json_repair_source": None,
            "json_repair_raw": None,
            "json_repair_hint": None,
            "json_repair_attempts": None,
        }

    @patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank")
    def test_retrieves_context_for_each_requirement(self, mock_search):
        def side_effect(query, limit=3):
            if "fault" in query.lower():
                return [
                    {"req_id": "REQ-HIST-001", "req_text": "Previous fault detection", "domain": "SOFTWARE", "asil": "B", "reasoning": "Historical", "score": 0.85},
                ]
            return [
                {"req_id": "REQ-HIST-002", "req_text": "Previous LED driver spec", "domain": "HARDWARE", "asil": "A", "reasoning": "Historical", "score": 0.75},
            ]

        mock_search.side_effect = side_effect

        result = retrieve_context_node(self.base_state)
        context = result["retrieved_context"]

        self.assertIn("REQ-SYS-001", context)
        self.assertIn("REQ-HW-001", context)
        self.assertEqual(len(context["REQ-SYS-001"]), 1)
        self.assertEqual(len(context["REQ-HW-001"]), 1)
        self.assertEqual(context["REQ-SYS-001"][0]["req_id"], "REQ-HIST-001")

    @patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank")
    def test_empty_context_when_no_results(self, mock_search):
        mock_search.return_value = []

        result = retrieve_context_node(self.base_state)
        context = result["retrieved_context"]

        self.assertIn("REQ-SYS-001", context)
        self.assertIn("REQ-HW-001", context)
        self.assertEqual(len(context["REQ-SYS-001"]), 0)
        self.assertEqual(len(context["REQ-HW-001"]), 0)

    @patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank")
    def test_self_reference_excluded(self, mock_search):
        mock_search.return_value = [
            {"req_id": "REQ-SYS-001", "req_text": "Self reference", "domain": "SYSTEM", "asil": None, "reasoning": None, "score": 0.95},
            {"req_id": "REQ-HIST-001", "req_text": "Historical", "domain": "SOFTWARE", "asil": "B", "reasoning": "Historical", "score": 0.80},
        ]

        result = retrieve_context_node(self.base_state)
        context = result["retrieved_context"]["REQ-SYS-001"]

        # REQ-SYS-001 should be filtered out (same id)
        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]["req_id"], "REQ-HIST-001")

    @patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank")
    def test_requirement_with_no_id_is_skipped(self, mock_search):
        """If requirement has no 'id', it should be skipped gracefully and not crash."""
        state = {**self.base_state, "classified": [{"id": None, "text": "some text", "domain": "SYSTEM"}]}
        mock_search.return_value = [{"req_id": "REQ-HIST-001", "req_text": "test", "domain": "SW", "asil": None, "reasoning": None, "score": 0.5}]

        result = retrieve_context_node(state)
        # Should not crash; the None-id item should be skipped and not added to context
        self.assertEqual(len(result["retrieved_context"]), 0)

    @patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank")
    def test_no_classified_requirements(self, mock_search):
        state = {**self.base_state, "classified": []}
        result = retrieve_context_node(state)
        self.assertEqual(result["retrieved_context"], {})


if __name__ == "__main__":
    unittest.main()

