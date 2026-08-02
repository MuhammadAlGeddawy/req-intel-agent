import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.nodes.extractor import extract_requirements_node


SAMPLE_DOCUMENT = """# System-Level Requirements

REQ-SYS-001: The adaptive headlight system shall adjust beam direction within 50ms of steering input detection.
REQ-SYS-002: The lighting control unit shall remain operational between -40°C and 125°C ambient temperature.

## Hardware Requirements

REQ-HW-001: The LED driver circuit shall supply a minimum of 1000 lumens per headlight unit.
"""


class ExtractRequirementsNodeTests(unittest.TestCase):
    def setUp(self):
        self.base_state = {
            "raw_document": "",
            "document_name": "test_doc.txt",
            "requirements": [],
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

    def test_extracts_requirements_correctly(self):
        state = {**self.base_state, "raw_document": SAMPLE_DOCUMENT}
        result = extract_requirements_node(state)

        reqs = result["requirements"]
        self.assertEqual(len(reqs), 3)

        # Check REQ-SYS-001
        req1 = reqs[0]
        self.assertEqual(req1["id"], "REQ-SYS-001")
        self.assertEqual(req1["domain"], "SYSTEM")
        self.assertIn("beam direction", req1["text"])

        # Check REQ-SYS-002
        req2 = reqs[1]
        self.assertEqual(req2["id"], "REQ-SYS-002")
        self.assertEqual(req2["domain"], "SYSTEM")

        # Check REQ-HW-001
        req3 = reqs[2]
        self.assertEqual(req3["id"], "REQ-HW-001")
        self.assertEqual(req3["domain"], "HARDWARE")

    def test_audit_log_is_appended(self):
        state = {**self.base_state, "raw_document": SAMPLE_DOCUMENT}
        result = extract_requirements_node(state)

        self.assertTrue(len(result["audit_log"]) > 0)
        last_entry = result["audit_log"][-1]
        self.assertEqual(last_entry["node"], "extract_requirements_regex")
        self.assertIn("Extracted 3 requirements via Regex", last_entry["output"])

    def test_empty_document_yields_no_requirements(self):
        state = {**self.base_state, "raw_document": ""}
        result = extract_requirements_node(state)
        self.assertEqual(len(result["requirements"]), 0)

    def test_document_with_no_matching_patterns(self):
        state = {
            **self.base_state,
            "raw_document": "This is just some random text without any requirement IDs.",
        }
        result = extract_requirements_node(state)
        self.assertEqual(len(result["requirements"]), 0)

    def test_document_with_malformed_ids(self):
        doc = "REQ-UNKNOWN-001: Some requirement without a recognized domain code."
        state = {**self.base_state, "raw_document": doc}
        result = extract_requirements_node(state)
        reqs = result["requirements"]
        self.assertEqual(len(reqs), 1)
        # Unknown domain code "UNKNOWN" should default to "SYSTEM"
        self.assertEqual(reqs[0]["domain"], "SYSTEM")

    def test_multiline_requirement_text(self):
        doc = """REQ-SW-001: The software shall implement a watchdog timer
with a timeout period of 10ms and
automatic system reset capability."""
        state = {**self.base_state, "raw_document": doc}
        result = extract_requirements_node(state)
        reqs = result["requirements"]
        self.assertEqual(len(reqs), 1)
        self.assertIn("watchdog timer", reqs[0]["text"])
        self.assertIn("automatic system reset", reqs[0]["text"])


if __name__ == "__main__":
    unittest.main()

