import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.utils.normalization import normalize_asil, ASIL_VALUES
from src.schemas import (
    AnalysisPayloadResponse,
    SafetyAssessment,
    RequirementOutput,
    RequirementSafety,
    RetrievedRequirement,
    InconsistencyOutput,
    GapOutput,
    FindingsOutput,
)
from src.api import _coerce_report_payload
from src.agents.graph import format_analysis_response


class NormalizeAsilTests(unittest.TestCase):
    def test_standard_values_passthrough(self):
        self.assertEqual(normalize_asil("QM"), "QM")
        self.assertEqual(normalize_asil("ASIL_A"), "ASIL_A")
        self.assertEqual(normalize_asil("ASIL_B"), "ASIL_B")
        self.assertEqual(normalize_asil("ASIL_C"), "ASIL_C")
        self.assertEqual(normalize_asil("ASIL_D"), "ASIL_D")

    def test_loose_formats_normalize(self):
        self.assertEqual(normalize_asil("asil-b"), "ASIL_B")
        self.assertEqual(normalize_asil("ASIL B"), "ASIL_B")
        self.assertEqual(normalize_asil("ASILB"), "ASIL_B")
        self.assertEqual(normalize_asil("B"), "ASIL_B")
        self.assertEqual(normalize_asil("D"), "ASIL_D")
        self.assertEqual(normalize_asil("qm"), "QM")

    def test_none_empty_and_unknown_fallback_to_qm(self):
        self.assertEqual(normalize_asil(None), "QM")
        self.assertEqual(normalize_asil(""), "QM")
        self.assertEqual(normalize_asil("   "), "QM")
        self.assertEqual(normalize_asil("not-an-asil"), "QM")

    def test_all_asil_values_are_iso_standard(self):
        for value in ("QM", "A", "B", "C", "D", "ASILA", "ASIL-D", "asil_c"):
            self.assertIn(normalize_asil(value), ASIL_VALUES)


class SafetyAssessmentSchemaTests(unittest.TestCase):
    def test_asil_normalized_in_schema(self):
        assessment = SafetyAssessment(suggested_asil="ASIL-B")
        self.assertEqual(assessment.suggested_asil, "ASIL_B")

    def test_asil_defaults_to_qm(self):
        assessment = SafetyAssessment()
        self.assertEqual(assessment.suggested_asil, "QM")

    def test_asil_lowercase_normalized(self):
        assessment = SafetyAssessment(suggested_asil="c")
        self.assertEqual(assessment.suggested_asil, "ASIL_C")


class AnalysisPayloadSchemaTests(unittest.TestCase):
    def test_accepts_target_schema_payload(self):
        payload = AnalysisPayloadResponse(
            id=1,
            status="COMPLETED",
            error_message=None,
            meta={
                "agent_version": "1.0.0",
                "model": "qwen/qwen-2.5-7b-instruct",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "human_review_required": True,
            },
            document={
                "id": 0,
                "name": "doc.txt",
                "version": "1.0.0",
                "classification": "Internal",
            },
            summary={
                "total_requirements": 3,
                "safety_relevant_count": 2,
                "inconsistencies_count": 1,
                "gaps_count": 1,
                "domain_breakdown": {"SYSTEM": 1, "HARDWARE": 1, "SAFETY": 1},
            },
            requirements=[
                {
                    "id": "REQ-SYS-001",
                    "text": "System req",
                    "domain": "SYSTEM",
                    "safety": {
                        "is_relevant": True,
                        "reason": "reason",
                        "assessment": {
                            "exposure": "E3",
                            "severity": "S2",
                            "controllability": "C2",
                            "suggested_asil": "ASIL_B",
                            "rationale": "test",
                        },
                    },
                }
            ],
            findings={
                "inconsistencies": [
                    {
                        "id": "INC-0001",
                        "type": "conflict",
                        "severity": "HIGH",
                        "description": "desc",
                        "affected_ids": ["REQ-SYS-001", "REQ-HW-001"],
                        "suggested_action": "fix",
                    }
                ],
                "gaps": [
                    {
                        "id": "GAP-0001",
                        "type": "missing_test",
                        "priority": "HIGH",
                        "affected_id": "REQ-SAF-001",
                        "description": "desc",
                        "suggested_action": "add",
                    }
                ],
            },
        )
        self.assertEqual(payload.id, 1)
        self.assertEqual(payload.status, "COMPLETED")
        self.assertIn("created_at", payload.meta.model_dump())
        self.assertEqual(payload.requirements[0].safety.assessment.suggested_asil, "ASIL_B")
        self.assertEqual(payload.findings.inconsistencies[0].affected_ids, ["REQ-SYS-001", "REQ-HW-001"])
        self.assertEqual(payload.findings.gaps[0].affected_id, "REQ-SAF-001")

    def test_missing_optional_fields_get_defaults(self):
        payload = AnalysisPayloadResponse(id=1, status="PENDING")
        self.assertEqual(payload.meta.human_review_required, True)
        self.assertEqual(payload.findings.inconsistencies, [])
        self.assertEqual(payload.findings.gaps, [])
        self.assertEqual(payload.requirements, [])
        self.assertIsNone(payload.node_trace)

    def test_no_findings_safety_and_no_text_duplicates(self):
        """After coercion, findings must not contain safety bucket or affected_req_texts."""
        report = {
            "document": {"id": 0, "name": "doc", "version": "1.0.0", "classification": "Internal"},
            "meta": {"model": "m", "agent_version": "1.0.0", "human_review_required": True},
            "summary": {"total_requirements": 0},
            "requirements": [],
            "findings": {
                "safety": {"count": 0, "items": []},
                "inconsistencies": [
                    {
                        "id": "INC-0001",
                        "type": "conflict",
                        "severity": "HIGH",
                        "description": "d",
                        "affected_ids": ["A", "B"],
                        "affected_req_texts": ["text A", "text B"],
                        "suggested_action": "fix",
                    }
                ],
                "gaps": [
                    {
                        "id": "GAP-0001",
                        "type": "missing_test",
                        "priority": "HIGH",
                        "affected_id": "C",
                        "affected_req_text": "text C",
                        "description": "d",
                        "suggested_action": "add",
                    }
                ],
            },
        }
        coerced = _coerce_report_payload(report)
        self.assertNotIn("safety", coerced["findings"])
        inc = coerced["findings"]["inconsistencies"][0]
        gap = coerced["findings"]["gaps"][0]
        self.assertNotIn("affected_req_texts", inc)
        self.assertNotIn("affected_req_text", gap)

    def test_legacy_issues_block_mapped_to_findings(self):
        """Legacy reports with issues -> traceability_gaps should map to findings.gaps."""
        report = {
            "issues": {
                "inconsistencies": [{"id": "INC-1", "type": "conflict"}],
                "traceability_gaps": [{"id": "GAP-1", "type": "missing_test"}],
            }
        }
        coerced = _coerce_report_payload(report)
        self.assertEqual(coerced["findings"]["inconsistencies"][0]["id"], "INC-1")
        self.assertEqual(coerced["findings"]["gaps"][0]["id"], "GAP-1")


class RetrievedRequirementsTests(unittest.TestCase):
    def test_retrieved_requirement_asil_normalized(self):
        item = RetrievedRequirement(req_id="KB-1", req_text="...", domain="SAFETY", asil="ASIL-B", score=0.87)
        self.assertEqual(item.asil, "ASIL_B")

    def test_safety_schema_accepts_retrieved_requirements(self):
        safety = RequirementSafety(
            is_relevant=True,
            assessment={"suggested_asil": "C", "exposure": "E3", "severity": "S2", "controllability": "C2", "rationale": "r"},
            retrieved_requirements=[
                {"req_id": "KB-1", "req_text": "similar 1", "domain": "SAFETY", "asil": "B", "reasoning": "hist", "score": 0.9},
                {"req_id": "KB-2", "req_text": "similar 2", "domain": "SOFTWARE", "asil": "ASIL-C", "reasoning": "hist2", "score": 0.7},
            ],
        )
        self.assertEqual(len(safety.retrieved_requirements), 2)
        self.assertEqual(safety.retrieved_requirements[0].asil, "ASIL_B")
        self.assertEqual(safety.retrieved_requirements[1].asil, "ASIL_C")

    def test_report_includes_retrieved_requirements_for_safety_reqs(self):
        """format_analysis_response should surface retrieved_requirements for safety reqs."""
        state = {
            "requirements": [],
            "classified": [
                {"id": "REQ-SAF-001", "text": "safe state", "domain": "SAFETY", "safety_relevant": True, "safety_reason": "reason"},
                {"id": "REQ-HW-001", "text": "led", "domain": "HARDWARE", "safety_relevant": False, "safety_reason": None},
            ],
            "safety_assessments": [
                {"id": "REQ-SAF-001", "suggested_asil": "C", "exposure": "E3", "severity": "S2", "controllability": "C2", "rationale": "r"},
            ],
            "inconsistencies": [],
            "gaps": [],
            "retrieved_context": {
                "REQ-SAF-001": [
                    {"req_id": "KB-1", "req_text": "similar", "domain": "SAFETY", "asil": "B", "reasoning": "h", "score": 0.9},
                ],
                "REQ-HW-001": [],
            },
            "error_message": None,
            "document_name": "doc.txt",
        }
        report = format_analysis_response(state, analysis_id=7)
        saf_req = next(r for r in report["requirements"] if r["id"] == "REQ-SAF-001")
        hw_req = next(r for r in report["requirements"] if r["id"] == "REQ-HW-001")
        self.assertEqual(len(saf_req["safety"]["retrieved_requirements"]), 1)
        self.assertEqual(saf_req["safety"]["retrieved_requirements"][0]["req_id"], "KB-1")
        self.assertEqual(saf_req["safety"]["retrieved_requirements"][0]["asil"], "ASIL_B")
        # Non-safety requirement should have empty retrieved_requirements
        self.assertEqual(hw_req["safety"]["retrieved_requirements"], [])

    def test_full_payload_validates_retrieved_requirements(self):
        payload = AnalysisPayloadResponse(
            id=1,
            status="COMPLETED",
            requirements=[
                {
                    "id": "REQ-SAF-001",
                    "text": "safe state",
                    "domain": "SAFETY",
                    "safety": {
                        "is_relevant": True,
                        "reason": "r",
                        "assessment": {"suggested_asil": "C"},
                        "retrieved_requirements": [
                            {"req_id": "KB-1", "req_text": "similar", "domain": "SAFETY", "asil": "ASIL-C", "score": 0.85},
                        ],
                    },
                }
            ],
        )
        req = payload.requirements[0]
        self.assertEqual(len(req.safety.retrieved_requirements), 1)
        self.assertEqual(req.safety.retrieved_requirements[0].asil, "ASIL_C")


if __name__ == "__main__":
    unittest.main()

