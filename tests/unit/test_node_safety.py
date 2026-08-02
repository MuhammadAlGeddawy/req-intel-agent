import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.llm.client import JSONParsingException
from src.agents.nodes.safety import assess_safety_levels_node


class AssessSafetyLevelsNodeTests(unittest.TestCase):
    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "The system shall detect fault within 100ms.", "domain": "SYSTEM", "safety_relevant": True, "safety_reason": "Fault detection"},
            {"id": "REQ-HW-001", "text": "The LED driver circuit shall supply 1000 lumens.", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SAF-001", "text": "In case of actuator failure, system shall default to safe position.", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Actuator failure"},
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
                "REQ-SAF-001": [{"req_id": "REQ-HIST-001", "req_text": "Historical safe state", "domain": "SAFETY", "asil": "C", "reasoning": "Historical", "score": 0.9}],
            },
            "report": None,
            "audit_log": [],
            "json_repair_needed": None,
            "json_repair_source": None,
            "json_repair_raw": None,
            "json_repair_hint": None,
            "json_repair_attempts": None,
        }

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_assesses_safety_relevant_requirements(self, mock_call_llm_json):
        # side_effect returns fresh dicts each time to avoid mutation by id injection
        mock_call_llm_json.side_effect = [
            {
                "assessments": [
                    {
                        "suggested_asil": "B",
                        "severity": "S2",
                        "exposure": "E3",
                        "controllability": "C2",
                        "rationale": "Fault detection is moderately severe",
                    },
                ]
            },
            {
                "assessments": [
                    {
                        "suggested_asil": "C",
                        "severity": "S3",
                        "exposure": "E4",
                        "controllability": "C2",
                        "rationale": "Actuator failure is critical",
                    },
                ]
            },
        ]

        result = assess_safety_levels_node(self.base_state)
        assessments = result["safety_assessments"]

        # Should assess both REQ-SYS-001 and REQ-SAF-001 (2 safety-relevant reqs)
        self.assertEqual(len(assessments), 2)

        # Check that the id was injected correctly for each requirement
        self.assertEqual(assessments[0]["id"], "REQ-SYS-001")
        self.assertEqual(assessments[1]["id"], "REQ-SAF-001")

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_no_safety_relevant_requirements(self, mock_call_llm_json):
        """If no requirements are safety_relevant, should return empty assessments."""
        state = {
            **self.base_state,
            "classified": [
                {"id": "REQ-HW-001", "text": "LED driver circuit", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
            ],
        }

        result = assess_safety_levels_node(state)
        self.assertEqual(result["safety_assessments"], [])
        mock_call_llm_json.assert_not_called()

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_json_parse_error_triggers_repair(self, mock_call_llm_json):
        """JSONParsingException should set json_repair_needed."""
        mock_call_llm_json.side_effect = JSONParsingException(
            raw='{"bad json"}',
            schema_hint="safety assessment output",
        )

        result = assess_safety_levels_node(self.base_state)

        self.assertTrue(result["json_repair_needed"])
        self.assertEqual(result["json_repair_source"], "assess_safety_levels")
        self.assertEqual(len(result["safety_assessments"]), 0)

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_llm_call_general_exception_fallback(self, mock_call_llm_json):
        """General exception should return empty assessments with audit log."""
        mock_call_llm_json.side_effect = RuntimeError("LLM unavailable")

        result = assess_safety_levels_node(self.base_state)

        self.assertEqual(len(result["safety_assessments"]), 0)
        audit = result["audit_log"]
        last_entry = audit[-1]
        self.assertEqual(last_entry["node"], "assess_safety_levels_fallback")

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_audit_log_on_success(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            "assessments": [{"suggested_asil": "B", "severity": "S2", "exposure": "E3", "controllability": "C2", "rationale": "test"}],
        }

        result = assess_safety_levels_node(self.base_state)
        audit = result["audit_log"]
        last_entry = audit[-1]
        self.assertEqual(last_entry["node"], "assess_safety_levels")
        self.assertIn("ASIL suggestions", last_entry["output"])

    @patch("src.agents.nodes.safety.call_llm_json")
    def test_empty_safety_assessments_in_response(self, mock_call_llm_json):
        """If LLM returns assessments list that is empty, should still create entry with defaults."""
        mock_call_llm_json.return_value = {"assessments": []}

        result = assess_safety_levels_node(self.base_state)
        assessments = result["safety_assessments"]

        # Each requirement gets an empty assessment dict merged with its id
        self.assertEqual(len(assessments), 2)


if __name__ == "__main__":
    unittest.main()

