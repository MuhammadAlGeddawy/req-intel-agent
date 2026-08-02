"""
Integration test for classify_requirements_node using the real LLM.
Tests that the LLM actually produces valid JSON with proper classifications.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.nodes.classifier import classify_requirements_node


class ClassifierIntegrationTests(unittest.TestCase):
    """Integration tests that call the real LLM to classify requirements."""

    def setUp(self):
        self.requirements = [
            {"id": "REQ-SYS-001", "text": "The system shall detect fault within 100ms.", "domain": "SYSTEM"},
            {"id": "REQ-HW-001", "text": "The LED driver circuit shall supply 1000 lumens.", "domain": "HARDWARE"},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, system shall default to safe position.", "domain": "SAFETY"},
        ]
        self.base_state = {
            "raw_document": "some doc",
            "document_name": "test.txt",
            "requirements": self.requirements,
            "classified": [],
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

    def test_llm_returns_valid_classifications(self):
        """Real LLM call: should return classified requirements with safety flags."""
        result = classify_requirements_node(self.base_state)

        classified = result["classified"]
        self.assertGreater(len(classified), 0)

        for req in classified:
            self.assertIn("id", req)
            self.assertIn("safety_relevant", req)
            self.assertIn("safety_reason", req)
            self.assertIn(req["id"], {r["id"] for r in self.requirements})

        # Safety requirements should be flagged
        saf_req = next(r for r in classified if r["id"] == "REQ-SAF-001")
        self.assertTrue(saf_req["safety_relevant"])
        self.assertIsNotNone(saf_req["safety_reason"])

        # Domains preserved from regex
        self.assertEqual(classified[0]["domain"], "SYSTEM")

    def test_llm_handles_empty_requirements(self):
        """Real LLM call with empty requirements: should return empty classified."""
        state = {**self.base_state, "requirements": []}
        result = classify_requirements_node(state)
        self.assertEqual(len(result["classified"]), 0)

    def test_llm_handles_non_safety_requirements(self):
        """Real LLM call: HW req without safety keywords should not be flagged."""
        reqs = [
            {"id": "REQ-HW-001", "text": "The LED driver circuit shall supply 1000 lumens.", "domain": "HARDWARE"},
            {"id": "REQ-HW-002", "text": "The actuator motor shall achieve beam adjustment with a positional accuracy of ±0.1 degrees.", "domain": "HARDWARE"},
        ]
        state = {**self.base_state, "requirements": reqs}
        result = classify_requirements_node(state)

        for r in result["classified"]:
            self.assertFalse(r["safety_relevant"])

    def test_llm_returns_audit_log(self):
        """Real LLM call should produce an audit log entry."""
        result = classify_requirements_node(self.base_state)
        self.assertTrue(len(result["audit_log"]) > 0)
        self.assertEqual(result["audit_log"][-1]["node"], "classify_requirements_safety_only")


if __name__ == "__main__":
    unittest.main()

