import json
from .agents.graph import build_agent
from .agents.state import AgentState

# ─── PRETTY PRINT REPORT ─────────────────────────────────────────────────────
def print_report(report: dict):
    print("\n" + "="*70)
    print("  ENGINEERING REQUIREMENTS INTELLIGENCE REPORT")
    print("="*70)

    meta = report.get("meta", report.get("metadata", {}))
    print(f"\n  Document : {report.get('document', {}).get('name', meta.get('document', 'N/A'))}")
    print(f"  Generated: {meta.get('processed_at', meta.get('generated_at', 'N/A'))}")
    print(f"  ⚠️  {meta.get('model', 'N/A')} — HUMAN REVIEW REQUIRED FOR ALL SAFETY ITEMS")

    summary = report.get("summary", {})
    print(f"\n{'─'*70}")
    print("  SUMMARY")
    print(f"{'─'*70}")
    print(f"  Total requirements : {summary.get('total_requirements', 0)}")
    print(f"  By domain          : {summary.get('domain_breakdown', summary.get('by_domain', {}))}")
    print(f"  Safety-relevant    : {summary.get('safety_relevant_count', summary.get('safety_relevant', 0))}")
    print(f"  Inconsistencies    : {summary.get('inconsistencies_count', summary.get('inconsistencies_found', 0))}")
    print(f"  Traceability gaps  : {summary.get('gaps_count', summary.get('gaps_found', 0))}")

    # Issues block (new schema)
    issues = report.get("issues", {})
    inconsistencies = issues.get("inconsistencies", report.get("inconsistencies", []))
    traceability_gaps = issues.get("traceability_gaps", report.get("traceability_gaps", []))

    if inconsistencies:
        print(f"\n{'─'*70}")
        print("  INCONSISTENCIES DETECTED")
        print(f"{'─'*70}")
        for inc in inconsistencies:
            sev = inc.get("severity", "?")
            marker = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "🟢"
            affected = inc.get("affected_ids", [])
            affected_str = " ↔ ".join(affected) if affected else f"{inc.get('req_id_1', '?')} ↔ {inc.get('req_id_2', '?')}"
            print(f"\n  {marker} [{sev}] {affected_str}")
            print(f"     Issue  : {inc.get('description')}")
            print(f"     Action : {inc.get('suggested_action')}")

    if traceability_gaps:
        print(f"\n{'─'*70}")
        print("  TRACEABILITY GAPS")
        print(f"{'─'*70}")
        for gap in traceability_gaps:
            pri = gap.get("priority", "?")
            marker = "🔴" if pri == "HIGH" else "🟡" if pri == "MEDIUM" else "🟢"
            print(f"\n  {marker} [{pri}] {gap.get('type', gap.get('gap_type', '?'))} → {gap.get('affected_id', gap.get('affected_req_id', '?'))}")
            print(f"     Issue  : {gap.get('description')}")
            print(f"     Action : {gap.get('suggested_action')}")

    # Safety assessments (now inline in requirements)
    safety_reqs = [r for r in report.get("requirements", []) if r.get("safety", {}).get("is_relevant")]
    if safety_reqs:
        print(f"\n{'─'*70}")
        print("  SAFETY ASSESSMENTS (SUGGESTIONS — PENDING HUMAN REVIEW)")
        print(f"{'─'*70}")
        for req in safety_reqs:
            safety = req.get("safety", {})
            assessment = safety.get("assessment")
            if assessment:
                print(f"\n  ⚠️  {req.get('id')} → Suggested ASIL-{assessment.get('suggested_asil')}")
                print(f"     Severity/Exposure/Controllability: {assessment.get('severity')}/{assessment.get('exposure')}/{assessment.get('controllability')}")
                print(f"     Rationale: {assessment.get('rationale')}")
                print(f"     ✋ Human review required")
            else:
                print(f"\n  ⚠️  {req.get('id')} → Safety-relevant (pending assessment)")

    # Audit log (if present via legacy or trace mode)
    if "audit_log" in report:
        print(f"\n{'─'*70}")
        print(f"  Audit log: {len(report['audit_log'])} LLM calls recorded")
        print("="*70 + "\n")
    else:
        print(f"\n{'─'*70}")
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

    # Initialize state with include_trace=True for local debugging
    initial_state: AgentState = {
        "raw_document": document,
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

    # Run the agent
    agent = build_agent()
    final_state = agent.invoke(initial_state)

    # Print the report
    print_report(final_state["report"])

    # Save full JSON report
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(final_state["report"], f, indent=2)
    print(f"  Full report saved to: {report_path}")
