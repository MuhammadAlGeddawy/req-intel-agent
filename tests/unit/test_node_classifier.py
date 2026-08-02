import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.llm.client import JSONParsingException
from src.llm.prompts import CLASSIFY_SYSTEM_PROMPT
from src.agents.nodes.classifier import classify_requirements_node


class ClassifyRequirementsNodeTests(unittest.TestCase):
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

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_classifies_safety_relevant_requirements(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "classified": [
                {"id": "REQ-SYS-001", "safety_relevant": True, "safety_reason": "Detection of faults is safety-related"},
                {"id": "REQ-HW-001", "safety_relevant": False, "safety_reason": None},
                {"id": "REQ-SAF-001", "safety_relevant": True, "safety_reason": "Actuator failure requires safe state"},
            ]
        }

        result = classify_requirements_node(self.base_state)
        classified = result["classified"]

        self.assertEqual(len(classified), 3)
        self.assertTrue(classified[0]["safety_relevant"])  # REQ-SYS-001
        self.assertFalse(classified[1]["safety_relevant"])  # REQ-HW-001
        self.assertTrue(classified[2]["safety_relevant"])   # REQ-SAF-001

        # Domains should be preserved from regex
        self.assertEqual(classified[0]["domain"], "SYSTEM")
        self.assertEqual(classified[1]["domain"], "HARDWARE")
        self.assertEqual(classified[2]["domain"], "SAFETY")

    def test_classifier_prompt_requires_all_requirements_to_be_evaluated(self):
        """The model prompt must explicitly require a full per-requirement classification."""
        self.assertIn("Evaluate every requirement in the list", CLASSIFY_SYSTEM_PROMPT)
        self.assertIn("Return one output element for each input requirement", CLASSIFY_SYSTEM_PROMPT)

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_fallback_for_unmatched_llm_ids(self, mock_call_llm_json):
        """If LLM returns fewer items than input, unmatched ones get domain-based defaults."""
        mock_call_llm_json.return_value = {
            "classified": [
                {"id": "REQ-SYS-001", "safety_relevant": True, "safety_reason": "reason"},
            ]
        }

        result = classify_requirements_node(self.base_state)
        classified = result["classified"]

        self.assertEqual(len(classified), 3)
        # REQ-HW-001 (HARDWARE domain) should have safety_relevant=False as fallback
        hw = next(r for r in classified if r["id"] == "REQ-HW-001")
        # REQ-SAF-001 (SAFETY domain) should have safety_relevant=True via domain heuristic
        saf = next(r for r in classified if r["id"] == "REQ-SAF-001")
        self.assertFalse(hw["safety_relevant"])
        self.assertIsNone(hw["safety_reason"])
        self.assertTrue(saf["safety_relevant"])
        self.assertEqual(saf["safety_reason"], "Domain: SAFETY")

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_json_parse_error_triggers_repair(self, mock_call_llm_json):
        """When call_llm_json raises JSONParsingException, set json_repair_needed."""
        mock_call_llm_json.side_effect = JSONParsingException(
            raw='{"broken json"}',
            schema_hint="classification output",
        )

        result = classify_requirements_node(self.base_state)

        self.assertTrue(result["json_repair_needed"])
        self.assertEqual(result["json_repair_source"], "classify_requirements")
        self.assertIn("broken", result["json_repair_raw"])
        self.assertEqual(len(result["classified"]), 0)

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_llm_call_general_exception_fallback(self, mock_call_llm_json):
        """Any non-JSON exception should fallback with domain-based safety defaults."""
        mock_call_llm_json.side_effect = RuntimeError("Network error")

        result = classify_requirements_node(self.base_state)

        classified = result["classified"]
        self.assertEqual(len(classified), 3)
        # SAFETY domain items should still be marked safety-relevant
        for r in classified:
            if r["domain"] == "SAFETY":
                self.assertTrue(r["safety_relevant"])
                self.assertEqual(r["safety_reason"], "Domain: SAFETY")
            else:
                self.assertFalse(r["safety_relevant"])
                self.assertIsNone(r["safety_reason"])

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_empty_requirements_list(self, mock_call_llm_json):
        state = {**self.base_state, "requirements": []}
        mock_call_llm_json.return_value = {"classified": []}

        result = classify_requirements_node(state)
        self.assertEqual(len(result["classified"]), 0)

    @patch("src.agents.nodes.classifier.call_llm_json")
    def test_audit_log_on_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "classified": [
                {"id": "REQ-SYS-001", "safety_relevant": True, "safety_reason": "reason"},
                {"id": "REQ-HW-001", "safety_relevant": False, "safety_reason": None},
                {"id": "REQ-SAF-001", "safety_relevant": True, "safety_reason": "reason2"},
            ]
        }

        result = classify_requirements_node(self.base_state)
        audit = result["audit_log"]
        self.assertTrue(len(audit) > 0)
        last_entry = audit[-1]
        self.assertEqual(last_entry["node"], "classify_requirements_safety_only")
        self.assertIn("2 flagged as safety-relevant", last_entry["output"])


if __name__ == "__main__":
    unittest.main()
