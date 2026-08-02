"""
Integration test for assess_safety_levels_node using the real LLM.
Tests that the LLM produces valid ASIL assessments for safety-relevant requirements.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.nodes.safety import assess_safety_levels_node


class SafetyIntegrationTests(unittest.TestCase):
    """Integration tests that call the real LLM for ASIL assessment."""

    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "The system shall detect fault within 100ms.", "domain": "SYSTEM", "safety_relevant": True, "safety_reason": "Fault detection is critical for safe operation"},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, the system shall default to a fixed straight-ahead beam position within 100ms.", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Actuator failure requires safe state"},
        ]
        self.base_state = {
            "raw_document": "some doc",
            "document_name": "test.txt",
            "requirements": [],
            "classified": self.classified,
            "safety_assessments": [],
            "inconsistencies": [],
            "gaps": [],
            "retrieved_context": {
                "REQ-SYS-001": [],
                "REQ-SAF-001": [],
            },
            "report": None,
            "audit_log": [],
            "json_repair_needed": None,
            "json_repair_source": None,
            "json_repair_raw": None,
            "json_repair_hint": None,
            "json_repair_attempts": None,
        }

    def test_llm_returns_asil_assessments(self):
        """Real LLM call: should return ASIL suggestions for safety-relevant reqs."""
        result = assess_safety_levels_node(self.base_state)
        assessments = result["safety_assessments"]

        self.assertEqual(len(assessments), 2)

        for assessment in assessments:
            self.assertIn("id", assessment)
            self.assertIn("suggested_asil", assessment)
            self.assertIn(assessment["suggested_asil"], {"QM", "A", "B", "C", "D"})
            self.assertIn("severity", assessment)
            self.assertIn("exposure", assessment)
            self.assertIn("controllability", assessment)
            self.assertIn("rationale", assessment)
            # human_review_required is a suggestion from the LLM; accept either value
            self.assertIn("human_review_required", assessment)

    def test_llm_no_safety_relevant_requirements(self):
        """Real LLM call with no safety reqs: should return empty."""
        state = {
            **self.base_state,
            "classified": [
                {"id": "REQ-HW-001", "text": "LED driver circuit", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
            ],
        }
        result = assess_safety_levels_node(state)
        self.assertEqual(result["safety_assessments"], [])

    def test_llm_returns_audit_log(self):
        """Real LLM call should produce an audit log entry."""
        result = assess_safety_levels_node(self.base_state)
        self.assertTrue(len(result["audit_log"]) > 0)
        self.assertEqual(result["audit_log"][-1]["node"], "assess_safety_levels")


if __name__ == "__main__":
    unittest.main()

