import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.llm.client import JSONParsingException
from src.agents.nodes.validator import detect_inconsistencies_node, detect_gaps_node


class BaseValidatorTestMixin:
    """Shared test data for both validator nodes."""

    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "The system shall operate between -40°C and 125°C.", "domain": "SYSTEM", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SW-004", "text": "The software shall operate within 8°C to 120°C.", "domain": "SOFTWARE", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, system shall default to safe position.", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Actuator failure requires safe state"},
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


class DetectInconsistenciesNodeTests(BaseValidatorTestMixin, unittest.TestCase):

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_detects_inconsistencies(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "inconsistencies": [
                {
                    "req_id_1": "REQ-SYS-001",
                    "req_id_2": "REQ-SW-004",
                    "type": "conflicting_values",
                    "description": "Temperature ranges conflict: REQ-SYS-001 says -40°C to 125°C but REQ-SW-004 says 8°C to 120°C",
                    "severity": "HIGH",
                    "suggested_action": "Align software temperature range with system specification",
                },
            ]
        }

        result = detect_inconsistencies_node(self.base_state)
        inconsistencies = result["inconsistencies"]

        self.assertEqual(len(inconsistencies), 1)
        self.assertEqual(inconsistencies[0]["req_id_1"], "REQ-SYS-001")
        self.assertEqual(inconsistencies[0]["req_id_2"], "REQ-SW-004")
        self.assertEqual(inconsistencies[0]["severity"], "HIGH")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_no_inconsistencies_found(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {"inconsistencies": []}

        result = detect_inconsistencies_node(self.base_state)
        self.assertEqual(len(result["inconsistencies"]), 0)

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_json_parse_error_triggers_repair(self, mock_call_llm_json):
        mock_call_llm_json.side_effect = JSONParsingException(
            raw="{bad json}",
            schema_hint="inconsistency output",
        )

        result = detect_inconsistencies_node(self.base_state)
        self.assertTrue(result["json_repair_needed"])
        self.assertEqual(result["json_repair_source"], "detect_inconsistencies")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_llm_call_general_exception_fallback(self, mock_call_llm_json):
        mock_call_llm_json.side_effect = RuntimeError("API error")

        result = detect_inconsistencies_node(self.base_state)
        self.assertEqual(len(result["inconsistencies"]), 0)
        audit = result["audit_log"]
        self.assertEqual(audit[-1]["node"], "detect_inconsistencies_fallback")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_audit_log_on_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "inconsistencies": [
                {"req_id_1": "REQ-SYS-001", "req_id_2": "REQ-SW-004", "type": "conflicting_values", "description": "Conflict", "severity": "MEDIUM", "suggested_action": "Fix"},
            ]
        }

        result = detect_inconsistencies_node(self.base_state)
        audit = result["audit_log"]
        last_entry = audit[-1]
        self.assertEqual(last_entry["node"], "detect_inconsistencies")
        self.assertIn("1 conflicts found", last_entry["output"])


class DetectGapsNodeTests(BaseValidatorTestMixin, unittest.TestCase):

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_detects_traceability_gaps(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "gaps": [
                {
                    "gap_type": "missing_test",
                    "affected_req_id": "REQ-SAF-001",
                    "description": "No test requirement linked to safety requirement REQ-SAF-001",
                    "priority": "HIGH",
                    "suggested_action": "Create a test requirement for safe state on actuator failure",
                },
            ]
        }

        result = detect_gaps_node(self.base_state)
        gaps = result["gaps"]

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["gap_type"], "missing_test")
        self.assertEqual(gaps[0]["affected_req_id"], "REQ-SAF-001")
        self.assertEqual(gaps[0]["priority"], "HIGH")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_no_gaps_found(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {"gaps": []}

        result = detect_gaps_node(self.base_state)
        self.assertEqual(len(result["gaps"]), 0)

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_json_parse_error_triggers_repair(self, mock_call_llm_json):
        mock_call_llm_json.side_effect = JSONParsingException(
            raw="{bad json}",
            schema_hint="gap output",
        )

        result = detect_gaps_node(self.base_state)
        self.assertTrue(result["json_repair_needed"])
        self.assertEqual(result["json_repair_source"], "detect_gaps")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_llm_call_general_exception_fallback(self, mock_call_llm_json):
        mock_call_llm_json.side_effect = RuntimeError("API error")

        result = detect_gaps_node(self.base_state)
        self.assertEqual(len(result["gaps"]), 0)
        audit = result["audit_log"]
        self.assertEqual(audit[-1]["node"], "detect_gaps_fallback")

    @patch("src.agents.nodes.validator.call_llm_json")
    def test_audit_log_on_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "gaps": [
                {"gap_type": "missing_sw", "affected_req_id": "REQ-SYS-001", "description": "Missing SW req", "priority": "MEDIUM", "suggested_action": "Create"},
            ]
        }

        result = detect_gaps_node(self.base_state)
        audit = result["audit_log"]
        last_entry = audit[-1]
        self.assertEqual(last_entry["node"], "detect_gaps")
        self.assertIn("1 gaps found", last_entry["output"])


if __name__ == "__main__":
    unittest.main()

