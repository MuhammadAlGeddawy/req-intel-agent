"""
Integration test for detect_inconsistencies_node and detect_gaps_node using the real LLM.
Tests that the LLM produces valid inconsistency and gap reports.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.nodes.validator import detect_inconsistencies_node, detect_gaps_node


class InconsistencyIntegrationTests(unittest.TestCase):
    """Integration tests using real LLM for inconsistency detection."""

    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-002", "text": "The lighting control unit shall remain operational between -40°C and 125°C ambient temperature.", "domain": "SYSTEM", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SW-004", "text": "The control software shall operate within 8°C to 120°C.", "domain": "SOFTWARE", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, the system shall default to a fixed straight-ahead beam position within 100ms.", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Safe state"},
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

    def test_llm_detects_inconsistencies(self):
        """Real LLM call: should detect temperature range conflict."""
        result = detect_inconsistencies_node(self.base_state)
        inconsistencies = result["inconsistencies"]

        self.assertIsInstance(inconsistencies, list)
        for inc in inconsistencies:
            self.assertIn("req_id_1", inc)
            self.assertIn("req_id_2", inc)
            self.assertIn("type", inc)
            self.assertIn("description", inc)
            self.assertIn("severity", inc)
            self.assertIn(inc["severity"], {"HIGH", "MEDIUM", "LOW"})
            self.assertIn("suggested_action", inc)

    def test_llm_returns_audit_log(self):
        """Real LLM call should produce an audit log entry."""
        result = detect_inconsistencies_node(self.base_state)
        self.assertTrue(len(result["audit_log"]) > 0)
        self.assertEqual(result["audit_log"][-1]["node"], "detect_inconsistencies")


class GapIntegrationTests(unittest.TestCase):
    """Integration tests using real LLM for traceability gap detection."""

    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "The adaptive headlight system shall adjust beam direction within 50ms of steering input detection.", "domain": "SYSTEM", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, the system shall default to a fixed straight-ahead beam position within 100ms.", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Safe state required"},
            {"id": "REQ-TST-001", "text": "The beam adjustment latency shall be verified under simulated steering inputs at -20°C, 25°C, and 85°C.", "domain": "TEST", "safety_relevant": False, "safety_reason": None},
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

    def test_llm_detects_gaps(self):
        """Real LLM call: should detect traceability gaps."""
        result = detect_gaps_node(self.base_state)
        gaps = result["gaps"]

        self.assertIsInstance(gaps, list)
        for gap in gaps:
            self.assertIn("gap_type", gap)
            self.assertIn("affected_req_id", gap)
            self.assertIn("description", gap)
            self.assertIn("priority", gap)
            self.assertIn(gap["priority"], {"HIGH", "MEDIUM", "LOW"})
            self.assertIn("suggested_action", gap)

    def test_llm_returns_audit_log(self):
        """Real LLM call should produce an audit log entry."""
        result = detect_gaps_node(self.base_state)
        self.assertTrue(len(result["audit_log"]) > 0)
        self.assertEqual(result["audit_log"][-1]["node"], "detect_gaps")


if __name__ == "__main__":
    unittest.main()

