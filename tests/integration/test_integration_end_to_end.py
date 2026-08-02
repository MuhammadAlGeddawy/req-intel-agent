"""
End-to-end integration test running the full agent pipeline with the real LLM.
Processes the sample_requirements.txt document and validates the full report.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.agents.graph import build_agent
from src.agents.state import AgentState


SAMPLE_PATH = ROOT / "sample_requirements.txt"


class EndToEndIntegrationTests(unittest.TestCase):
    """Full pipeline integration test with real LLM calls."""

    @classmethod
    def setUpClass(cls):
        if not SAMPLE_PATH.exists():
            raise FileNotFoundError(f"Sample requirements file not found: {SAMPLE_PATH}")
        cls.document = SAMPLE_PATH.read_text(encoding="utf-8")

    def setUp(self):
        self.initial_state: AgentState = {
            "raw_document": self.document,
            "document_name": "LGT-REQ-001 — Valeo Lighting System Requirements",
            "include_trace": False,
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
        self.agent = build_agent()

    # Patch the retriever to return empty results (no Postgres available locally)
    def _patched_agent_invoke(self, state):
        with patch("src.agents.nodes.retriever_node.hybrid_search_and_rerank", return_value=[]):
            return self.agent.invoke(state)

    def test_full_pipeline_produces_report(self):
        """Complete pipeline: should produce a valid report structure."""
        final_state = self._patched_agent_invoke(self.initial_state)
        report = final_state.get("report")

        self.assertIsNotNone(report, "Agent should produce a report")

        # New schema: status, document, meta
        self.assertIn("status", report)
        self.assertEqual(report["status"], "COMPLETED")
        self.assertIn("document", report)
        self.assertIn("name", report["document"])
        self.assertIn("meta", report)
        self.assertIn("processed_at", report["meta"])
        self.assertTrue(report["meta"]["human_review_required"])

        # Summary
        self.assertIn("summary", report)
        summary = report["summary"]
        self.assertGreater(summary["total_requirements"], 0)
        self.assertIn("domain_breakdown", summary)
        self.assertIn("safety_relevant_count", summary)
        self.assertIn("inconsistencies_count", summary)
        self.assertIn("gaps_count", summary)

        # Requirements with inline safety
        self.assertIn("requirements", report)
        self.assertGreater(len(report["requirements"]), 0)
        for req in report["requirements"]:
            self.assertIn("id", req)
            self.assertIn("text", req)
            self.assertIn("domain", req)
            self.assertIn("safety", req)
            self.assertIn("is_relevant", req["safety"])

        # Issues block (new consolidated format)
        self.assertIn("issues", report)
        self.assertIn("inconsistencies", report["issues"])
        self.assertIn("traceability_gaps", report["issues"])

        # No trace/log leakage by default
        self.assertNotIn("node_trace", report)
        self.assertNotIn("audit_log", report)
        self.assertNotIn("dependency_graph", report)
        self.assertNotIn("safety_assessments", report)

    def test_pipeline_extracts_all_requirements(self):
        """Pipeline should extract requirements from sample file."""
        final_state = self._patched_agent_invoke(self.initial_state)
        total = final_state["report"]["summary"]["total_requirements"]
        self.assertGreater(
            total,
            0,
            "Should extract at least one requirement from sample file",
        )
        self.assertLessEqual(
            total,
            20,
            "Should not extract more requirements than exist in sample file",
        )

    def test_pipeline_detects_safety_relevant(self):
        """Pipeline should flag safety requirements (ASIL, failsafe, etc.)."""
        final_state = self._patched_agent_invoke(self.initial_state)
        safety_count = final_state["report"]["summary"]["safety_relevant_count"]
        self.assertGreater(safety_count, 0, "Should detect safety-relevant requirements")

    def test_pipeline_detects_inconsistencies(self):
        """Pipeline should detect the known temperature range inconsistency."""
        final_state = self._patched_agent_invoke(self.initial_state)
        inconsistencies = final_state["report"]["issues"]["inconsistencies"]
        self.assertGreater(len(inconsistencies), 0)

    def test_pipeline_inline_safety_structure(self):
        """Safety data should be inlined into requirements."""
        final_state = self._patched_agent_invoke(self.initial_state)
        for req in final_state["report"]["requirements"]:
            safety = req["safety"]
            self.assertIn("is_relevant", safety)
            self.assertIn("reason", safety)
            self.assertIn("assessment", safety)
            # Non-safety requirements should have null assessment
            if not safety["is_relevant"]:
                self.assertIsNone(safety["assessment"])
                self.assertIsNone(safety["reason"])

    def test_include_trace_controls_node_trace(self):
        """include_trace=True should include node_trace."""
        trace_state = {**self.initial_state, "include_trace": True}
        final_state = self._patched_agent_invoke(trace_state)
        report = final_state["report"]
        self.assertIn("node_trace", report)
        node_trace = report["node_trace"]
        self.assertIn("1_extract_requirements", node_trace)
        self.assertIn("2_classify_requirements", node_trace)
        self.assertIn("4_assess_safety_levels", node_trace)

    def test_issues_field_mapping(self):
        """Verify inconsistencies have affected_ids array and gaps have affected_id."""
        final_state = self._patched_agent_invoke(self.initial_state)
        issues = final_state["report"]["issues"]

        for inc in issues["inconsistencies"]:
            self.assertIn("affected_ids", inc)
            self.assertIsInstance(inc["affected_ids"], list)
            self.assertIn("id", inc)
            self.assertIn("severity", inc)

        for gap in issues["traceability_gaps"]:
            self.assertIn("affected_id", gap)
            self.assertIsInstance(gap["affected_id"], str)
            self.assertIn("id", gap)
            self.assertIn("priority", gap)


if __name__ == "__main__":
    unittest.main()
