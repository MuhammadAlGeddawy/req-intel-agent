from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes.extractor import extract_requirements_node
from .nodes.classifier import classify_requirements_node
from .nodes.safety import assess_safety_levels_node
from .nodes.validator import detect_inconsistencies_node, detect_gaps_node

# ─── NODE 6: REPORT GENERATOR ────────────────────────────────────────────────
def generate_report_node(state):
    from datetime import datetime
    from ..llm.client import MODEL

    print("\n[Node 6] Generating traceability report...")

    domains = {}
    for r in state["classified"]:
        d = r.get("domain", "UNKNOWN")
        domains[d] = domains.get(d, 0) + 1

    report = {
        "metadata": {
            "document": state["document_name"],
            "generated_at": datetime.now().isoformat(),
            "model_used": MODEL,
            "agent_version": "1.0.0",
            "human_review_required": True
        },
        "summary": {
            "total_requirements": len(state["classified"]),
            "by_domain": domains,
            "safety_relevant": sum(1 for r in state["classified"] if r.get("safety_relevant")),
            "inconsistencies_found": len(state["inconsistencies"]),
            "gaps_found": len(state["gaps"]),
            "high_severity_issues": sum(1 for i in state["inconsistencies"] if i.get("severity") == "HIGH") +
                                     sum(1 for g in state["gaps"] if g.get("priority") == "HIGH")
        },
        "requirements": state["classified"],
        "safety_assessments": {
            "disclaimer": "SUGGESTIONS ONLY — All ASIL assignments require human expert review per ISO 26262",
            "assessments": state["safety_assessments"]
        },
        "inconsistencies": state["inconsistencies"],
        "traceability_gaps": state["gaps"],
        "audit_log": state["audit_log"]
    }

    print(f"   → Report generated successfully")
    return {**state, "report": report}


# ─── BUILD THE GRAPH ─────────────────────────────────────────────────────────
def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("extract_requirements", extract_requirements_node)
    graph.add_node("classify_requirements", classify_requirements_node)
    graph.add_node("assess_safety_levels", assess_safety_levels_node)
    graph.add_node("detect_inconsistencies", detect_inconsistencies_node)
    graph.add_node("detect_gaps", detect_gaps_node)
    graph.add_node("generate_report", generate_report_node)

    graph.set_entry_point("extract_requirements")
    graph.add_edge("extract_requirements", "classify_requirements")
    graph.add_edge("classify_requirements", "assess_safety_levels")
    graph.add_edge("assess_safety_levels", "detect_inconsistencies")
    graph.add_edge("detect_inconsistencies", "detect_gaps")
    graph.add_edge("detect_gaps", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()