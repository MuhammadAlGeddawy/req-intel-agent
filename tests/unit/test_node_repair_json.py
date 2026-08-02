import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.llm.client import JSONParsingException
from src.agents.graph import repair_json_node


class RepairJsonNodeTests(unittest.TestCase):
    def setUp(self):
        self.base_state = {
            "raw_document": "some doc",
            "document_name": "test.txt",
            "requirements": [{"id": "REQ-SYS-001", "text": "System req", "domain": "SYSTEM"}],
            "classified": [],
            "safety_assessments": [],
            "inconsistencies": [],
            "gaps": [],
            "retrieved_context": {},
            "report": None,
            "audit_log": [],
            "json_repair_needed": True,
            "json_repair_source": "classify_requirements",
            "json_repair_raw": '{"broken json}',
            "json_repair_hint": "classification output",
            "json_repair_attempts": 0,
        }

    @patch("src.llm.client.call_llm_json")
    def test_repair_classify_requirements_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "classified": [
                {"id": "REQ-SYS-001", "safety_relevant": True, "safety_reason": "Fixed reason"},
            ]
        }

        result = repair_json_node(self.base_state)
        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(len(result["classified"]), 1)
        self.assertEqual(result["classified"][0]["id"], "REQ-SYS-001")
        self.assertTrue(result["classified"][0]["safety_relevant"])

    @patch("src.llm.client.call_llm_json")
    def test_repair_classify_empty_fallback(self, mock_call_llm_json):
        """If repaired classified is empty but state has requirements, fallback to defaults."""
        mock_call_llm_json.return_value = {"classified": []}

        result = repair_json_node(self.base_state)
        self.assertFalse(result["json_repair_needed"])
        classified = result["classified"]
        self.assertEqual(len(classified), 1)
        # Should fallback to requirements with safety_relevant=False
        self.assertEqual(classified[0]["id"], "REQ-SYS-001")
        self.assertFalse(classified[0]["safety_relevant"])
        self.assertIsNone(classified[0]["safety_reason"])

    @patch("src.llm.client.call_llm_json")
    def test_repair_safety_assessments_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "assessments": [{"id": "REQ-SAF-001", "suggested_asil": "C"}]
        }

        state = {**self.base_state, "json_repair_source": "assess_safety_levels"}
        result = repair_json_node(state)

        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(len(result["safety_assessments"]), 1)
        self.assertEqual(result["safety_assessments"][0]["suggested_asil"], "C")

    @patch("src.llm.client.call_llm_json")
    def test_repair_inconsistencies_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "inconsistencies": [{"req_id_1": "A", "req_id_2": "B", "type": "conflict", "description": "test", "severity": "HIGH", "suggested_action": "fix"}]
        }

        state = {**self.base_state, "json_repair_source": "detect_inconsistencies"}
        result = repair_json_node(state)

        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(len(result["inconsistencies"]), 1)

    @patch("src.llm.client.call_llm_json")
    def test_repair_gaps_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "gaps": [{"gap_type": "missing_test", "affected_req_id": "REQ-001", "description": "test", "priority": "HIGH", "suggested_action": "fix"}]
        }

        state = {**self.base_state, "json_repair_source": "detect_gaps"}
        result = repair_json_node(state)

        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(len(result["gaps"]), 1)

    @patch("src.llm.client.call_llm_json")
    def test_max_attempts_gives_up(self, mock_call_llm_json):
        """After 2 attempts, should give up and fallback to non-safety defaults."""
        state = {**self.base_state, "json_repair_attempts": 2}

        result = repair_json_node(state)

        mock_call_llm_json.assert_not_called()
        self.assertFalse(result["json_repair_needed"])
        # classify_requirements source: fallback with non-safety defaults from requirements
        self.assertEqual(len(result["classified"]), 1)
        self.assertFalse(result["classified"][0]["safety_relevant"])
        self.assertIsNone(result["classified"][0]["safety_reason"])

    @patch("src.llm.client.call_llm_json")
    def test_give_up_for_safety_assessments(self, mock_call_llm_json):
        state = {
            **self.base_state,
            "json_repair_attempts": 2,
            "json_repair_source": "assess_safety_levels",
        }
        result = repair_json_node(state)
        self.assertEqual(result["safety_assessments"], [])

    @patch("src.llm.client.call_llm_json")
    def test_give_up_for_inconsistencies(self, mock_call_llm_json):
        state = {
            **self.base_state,
            "json_repair_attempts": 2,
            "json_repair_source": "detect_inconsistencies",
        }
        result = repair_json_node(state)
        self.assertEqual(result["inconsistencies"], [])

    @patch("src.llm.client.call_llm_json")
    def test_give_up_for_gaps(self, mock_call_llm_json):
        state = {
            **self.base_state,
            "json_repair_attempts": 2,
            "json_repair_source": "detect_gaps",
        }
        result = repair_json_node(state)
        self.assertEqual(result["gaps"], [])

    @patch("src.llm.client.call_llm_json")
    def test_repair_json_parse_exception_retries(self, mock_call_llm_json):
        """If JSONParsingException occurs during repair, should retry up to 2 attempts then give up."""
        mock_call_llm_json.side_effect = JSONParsingException(
            raw='{still broken}',
            schema_hint="repair for classify_requirements"
        )

        result = repair_json_node(self.base_state)

        # repair_json_node calls itself recursively — after 2 failed attempts it gives up
        # The final propagated result has json_repair_needed=False and attempts=2
        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(result["json_repair_attempts"], 2)

    @patch("src.llm.client.call_llm_json")
    def test_repair_llm_exception_gives_up(self, mock_call_llm_json):
        """A general Exception during LLM repair call should fallback immediately."""
        mock_call_llm_json.side_effect = RuntimeError("LLM crash")

        result = repair_json_node(self.base_state)

        # Should give up and return classified from requirements with non-safety defaults
        self.assertFalse(result["json_repair_needed"])
        self.assertEqual(len(result["classified"]), 1)
        self.assertFalse(result["classified"][0]["safety_relevant"])
        self.assertIsNone(result["classified"][0]["safety_reason"])

    @patch("src.llm.client.call_llm_json")
    def test_audit_log_on_successful_repair(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "classified": [{"id": "REQ-SYS-001", "safety_relevant": True, "safety_reason": "Fixed"}]
        }

        result = repair_json_node(self.base_state)
        last_entry = result["audit_log"][-1]
        self.assertEqual(last_entry["node"], "repair_json_success")

    @patch("src.llm.client.call_llm_json")
    def test_audit_log_on_give_up(self, mock_call_llm_json):
        state = {**self.base_state, "json_repair_attempts": 2}
        result = repair_json_node(state)
        last_entry = result["audit_log"][-1]
        self.assertEqual(last_entry["node"], "repair_json_gave_up")


if __name__ == "__main__":
    unittest.main()
