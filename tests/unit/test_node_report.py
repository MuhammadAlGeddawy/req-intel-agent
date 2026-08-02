import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.graph import generate_report_node


class GenerateReportNodeTests(unittest.TestCase):
    def setUp(self):
        self.classified = [
            {"id": "REQ-SYS-001", "text": "System req 1", "domain": "SYSTEM", "safety_relevant": True, "safety_reason": "Safety"},
            {"id": "REQ-HW-001", "text": "Hardware req 1", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
            {"id": "REQ-SAF-001", "text": "Safety req 1", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "Critical"},
        ]
        self.safety_assessments = [
            {"id": "REQ-SYS-001", "suggested_asil": "ASIL_B", "severity": "S2", "exposure": "E3", "controllability": "C2", "rationale": "test", "human_review_required": True},
        ]
        self.inconsistencies = [
            {"req_id_1": "REQ-SYS-001", "req_id_2": "REQ-HW-001", "type": "conflicting_values", "description": "Conflict", "severity": "HIGH", "suggested_action": "Fix"},
        ]
        self.gaps = [
            {"gap_type": "missing_test", "affected_req_id": "REQ-SAF-001", "description": "Missing test", "priority": "HIGH", "suggested_action": "Create test"},
        ]

        self.base_state = {
            "raw_document": "some doc",
            "document_name": "test_doc.txt",
            "include_trace": False,
            "requirements": [],
            "classified": self.classified,
            "safety_assessments": self.safety_assessments,
            "inconsistencies": self.inconsistencies,
            "gaps": self.gaps,
            "retrieved_context": {},
            "report": None,
            "audit_log": [{"timestamp": "2024-01-01", "node": "test", "input": "in", "output": "out", "model": "qwen"}],
            "json_repair_needed": None,
            "json_repair_source": None,
            "json_repair_raw": None,
            "json_repair_hint": None,
            "json_repair_attempts": None,
        }

    def test_report_matches_target_schema(self):
        report = generate_report_node(self.base_state)["report"]

        self.assertEqual(report["status"], "COMPLETED")
        self.assertIn("id", report)
        self.assertIn("meta", report)
        self.assertIn("document", report)
        self.assertIn("summary", report)
        self.assertIn("requirements", report)
        self.assertIn("findings", report)
        self.assertNotIn("report_status", report)
        self.assertNotIn("pipeline_outputs", report)
        self.assertNotIn("document_name", report)
        self.assertNotIn("issues", report)

    def test_meta_has_consolidated_timestamps(self):
        meta = generate_report_node(self.base_state)["report"]["meta"]

        self.assertIn("agent_version", meta)
        self.assertIn("model", meta)
        self.assertIn("created_at", meta)
        self.assertIn("updated_at", meta)
        self.assertIn("human_review_required", meta)
        self.assertNotIn("processed_at", meta)

    def test_findings_omit_safety_and_text_duplicates(self):
        findings = generate_report_node(self.base_state)["report"]["findings"]

        self.assertIn("inconsistencies", findings)
        self.assertIn("gaps", findings)
        self.assertNotIn("safety", findings)

        inc = findings["inconsistencies"][0]
        gap = findings["gaps"][0]
        self.assertNotIn("affected_req_texts", inc)
        self.assertNotIn("affected_req_text", gap)

    def test_asil_values_are_iso_standard_strings(self):
        req = next(r for r in generate_report_node(self.base_state)["report"]["requirements"] if r["id"] == "REQ-SYS-001")
        self.assertEqual(req["safety"]["assessment"]["suggested_asil"], "ASIL_B")

    def test_root_summary_counts_are_correct(self):
        summary = generate_report_node(self.base_state)["report"]["summary"]

        self.assertEqual(summary["total_requirements"], 3)
        self.assertEqual(summary["safety_relevant_count"], 2)
        self.assertEqual(summary["inconsistencies_count"], 1)
        self.assertEqual(summary["gaps_count"], 1)

    def test_requirements_keep_inline_safety_blocks(self):
        req = generate_report_node(self.base_state)["report"]["requirements"][0]

        self.assertIn("safety", req)
        self.assertIsInstance(req["safety"]["is_relevant"], bool)
        self.assertIn("assessment", req["safety"])


if __name__ == "__main__":
    unittest.main()
