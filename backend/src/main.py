import json
from .agents.graph import build_agent
from .agents.state import AgentState

# ─── PRETTY PRINT REPORT ─────────────────────────────────────────────────────
def print_report(report: dict):
    print("\n" + "="*70)
    print("  ENGINEERING REQUIREMENTS INTELLIGENCE REPORT")
    print("="*70)

    meta = report["metadata"]
    print(f"\n  Document : {meta['document']}")
    print(f"  Generated: {meta['generated_at']}")
    print(f"  ⚠️  {meta['model_used']} — HUMAN REVIEW REQUIRED FOR ALL SAFETY ITEMS")

    summary = report["summary"]
    print(f"\n{'─'*70}")
    print("  SUMMARY")
    print(f"{'─'*70}")
    print(f"  Total requirements : {summary['total_requirements']}")
    print(f"  By domain          : {summary['by_domain']}")
    print(f"  Safety-relevant    : {summary['safety_relevant']}")
    print(f"  Inconsistencies    : {summary['inconsistencies_found']}")
    print(f"  Traceability gaps  : {summary['gaps_found']}")
    print(f"  High severity      : {summary['high_severity_issues']} ← Immediate attention required")

    if report["inconsistencies"]:
        print(f"\n{'─'*70}")
        print("  INCONSISTENCIES DETECTED")
        print(f"{'─'*70}")
        for inc in report["inconsistencies"]:
            sev = inc.get("severity", "?")
            marker = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "🟢"
            print(f"\n  {marker} [{sev}] {inc.get('req_id_1')} ↔ {inc.get('req_id_2')}")
            print(f"     Issue  : {inc.get('description')}")
            print(f"     Action : {inc.get('suggested_action')}")

    if report["traceability_gaps"]:
        print(f"\n{'─'*70}")
        print("  TRACEABILITY GAPS")
        print(f"{'─'*70}")
        for gap in report["traceability_gaps"]:
            pri = gap.get("priority", "?")
            marker = "🔴" if pri == "HIGH" else "🟡" if pri == "MEDIUM" else "🟢"
            print(f"\n  {marker} [{pri}] {gap.get('gap_type')} → {gap.get('affected_req_id')}")
            print(f"     Issue  : {gap.get('description')}")
            print(f"     Action : {gap.get('suggested_action')}")

    if report["safety_assessments"]["assessments"]:
        print(f"\n{'─'*70}")
        print("  SAFETY ASSESSMENTS (SUGGESTIONS — PENDING HUMAN REVIEW)")
        print(f"{'─'*70}")
        for a in report["safety_assessments"]["assessments"]:
            print(f"\n  ⚠️  {a.get('id')} → Suggested ASIL-{a.get('suggested_asil')}")
            print(f"     Severity/Exposure/Controllability: {a.get('severity')}/{a.get('exposure')}/{a.get('controllability')}")
            print(f"     Rationale: {a.get('rationale')}")
            print(f"     ✋ Human review required: {a.get('human_review_required')}")

    print(f"\n{'─'*70}")
    print(f"  Audit log: {len(report['audit_log'])} LLM calls recorded")
    print("="*70 + "\n")


# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os

    src_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(src_dir, ".."))
    sample_path = os.path.join(project_root, "sample_requirements.txt")
    report_path = os.path.join(project_root, "requirements_report.json")

    # Load sample document
    with open(sample_path, "r", encoding="utf-8") as f:
        document = f.read()

    print("\n" + "="*70)
    print("  ENGINEERING REQUIREMENTS INTELLIGENCE AGENT")
    print("  Powered by LangGraph + Qwen")
    print("="*70)
    print(f"\n  Processing: {sample_path}")
    print(f"  Characters: {len(document)}")

    # Initialize state
    initial_state: AgentState = {
        "raw_document": document,
        "document_name": "LGT-REQ-001 — Valeo Lighting System Requirements",
        "requirements": [],
        "classified": [],
        "safety_assessments": [],
        "inconsistencies": [],
        "gaps": [],
        "report": None,
        "audit_log": []
    }

    # Run the agent
    agent = build_agent()
    final_state = agent.invoke(initial_state)

    # Print the report
    print_report(final_state["report"])

    # Save full JSON report
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_state["report"], f, indent=2)
    print(f"  Full report saved to: {report_path}")