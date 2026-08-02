from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes.classifier import classify_requirements_node
from .nodes.extractor import extract_requirements_node
from .nodes.retriever_node import retrieve_context_node
from .nodes.safety import assess_safety_levels_node
from .nodes.validator import detect_inconsistencies_node, detect_gaps_node
from ..llm.client import JSONParsingException
from ..utils.logger import log_entry
from ..utils.normalization import normalize_asil as _normalize_asil


# --- HELPER: FORMAT ANALYSIS RESPONSE --------------------------------------------
def format_analysis_response(pipeline_state, analysis_id: int = 0, include_trace: bool = False) -> dict:
    """
    Transform the pipeline AgentState into the client-facing analysis response schema.
    This keeps the public response concise and removes old duplicate fields.
    """
    from datetime import datetime
    from ..llm.client import MODEL

    # Fallback: if classification pipeline failed, use domain-based heuristic
    classified = pipeline_state.get("classified", [])
    if not classified:
        classified = [
            {
                **r,
                "safety_relevant": r.get("domain", "") == "SAFETY",
                "safety_reason": "Domain: SAFETY" if r.get("domain", "") == "SAFETY" else None,
            }
            for r in pipeline_state.get("requirements", [])
        ]

    safety_assessments = pipeline_state.get("safety_assessments", [])
    inconsistencies = pipeline_state.get("inconsistencies", [])
    gaps = pipeline_state.get("gaps", [])

    safety_lookup = {}
    for a in safety_assessments:
        rid = a.get("id")
        if rid:
            safety_lookup[rid] = a

    req_text_lookup = {}
    for r in classified:
        rid = r.get("id", "")
        if rid:
            req_text_lookup[rid] = r.get("text", "")

    retrieved_context = pipeline_state.get("retrieved_context", {})

    requirements = []
    safety_relevant_count = 0
    domain_counts = {"SYSTEM": 0, "HARDWARE": 0, "SOFTWARE": 0, "SAFETY": 0, "TEST": 0}
    for r in classified:
        rid = r.get("id", "")
        domain = r.get("domain", "SYSTEM")
        if domain in domain_counts:
            domain_counts[domain] += 1

        is_safety_relevant = r.get("safety_relevant", False)
        if is_safety_relevant:
            safety_relevant_count += 1

        sa = safety_lookup.get(rid)
        safety_block = {
            "is_relevant": bool(is_safety_relevant),
            "reason": r.get("safety_reason") if is_safety_relevant else None,
            "assessment": None,
            "retrieved_requirements": [],
        }
        if is_safety_relevant and sa:
            safety_block["assessment"] = {
                "exposure": sa.get("exposure") or "E0",
                "severity": sa.get("severity") or "S0",
                "controllability": sa.get("controllability") or "C0",
                "rationale": sa.get("rationale") or "Not assessed",
                "suggested_asil": _normalize_asil(sa.get("suggested_asil")),
            }

        # Most similar knowledge-base requirements (top 5 by default) with metadata.
        if is_safety_relevant:
            safety_block["retrieved_requirements"] = [
                {
                    "req_id": item.get("req_id"),
                    "req_text": item.get("req_text"),
                    "domain": item.get("domain", "UNKNOWN"),
                    "asil": _normalize_asil(item.get("asil")),
                    "reasoning": item.get("reasoning"),
                    "score": item.get("score"),
                }
                for item in (retrieved_context.get(rid) or [])
            ]

        requirements.append({
            "id": rid,
            "domain": domain,
            "text": r.get("text", ""),
            "safety": safety_block,
        })

    formatted_inconsistencies = []
    for i, inc in enumerate(inconsistencies):
        affected = []
        if inc.get("req_id_1"):
            affected.append(inc["req_id_1"])
        if inc.get("req_id_2"):
            affected.append(inc["req_id_2"])
        formatted_inconsistencies.append({
            "id": inc.get("id", f"INC-{i+1:04d}"),
            "type": inc.get("type", "conflict"),
            "severity": inc.get("severity", "MEDIUM"),
            "affected_ids": affected,
            "description": inc.get("description", ""),
            "suggested_action": inc.get("suggested_action", ""),
        })

    formatted_gaps = []
    for i, g in enumerate(gaps):
        aff_id = g.get("affected_req_id", "")
        formatted_gaps.append({
            "id": g.get("id", f"GAP-{i+1:04d}"),
            "type": g.get("gap_type", "missing_traceability"),
            "priority": g.get("priority", "MEDIUM"),
            "affected_id": aff_id,
            "description": g.get("description", ""),
            "suggested_action": g.get("suggested_action", ""),
        })

    inc_count = len(formatted_inconsistencies)
    gap_count = len(formatted_gaps)
    now_iso = datetime.now().isoformat()

    findings = {
        "inconsistencies": formatted_inconsistencies,
        "gaps": formatted_gaps,
    }

    response = {
        "id": analysis_id,
        "status": "COMPLETED",
        "error_message": pipeline_state.get("error_message", None),
        "document": {
            "id": 0,
            "name": pipeline_state.get("document_name", ""),
            "version": "1.0.0",
            "classification": "Internal",
        },
        "meta": {
            "model": MODEL,
            "agent_version": "1.0.0",
            "created_at": pipeline_state.get("created_at", now_iso),
            "updated_at": now_iso,
            "human_review_required": True,
        },
        "summary": {
            "total_requirements": len(requirements),
            "safety_relevant_count": safety_relevant_count,
            "inconsistencies_count": inc_count,
            "gaps_count": gap_count,
            "domain_breakdown": domain_counts,
        },
        "requirements": requirements,
        "findings": findings,
    }

    if include_trace:
        node_trace = {
            "1_extract_requirements": {"node": "extract_requirements", "output_count": len(pipeline_state.get("requirements", [])), "output": pipeline_state.get("requirements", [])},
            "2_classify_requirements": {"node": "classify_requirements", "output_count": len(pipeline_state.get("classified", [])), "output": pipeline_state.get("classified", [])},
            "3_retrieve_context": {"node": "retrieve_context", "output_summary": {req_id: len(results) for req_id, results in pipeline_state.get("retrieved_context", {}).items()}},
            "4_assess_safety_levels": {"node": "assess_safety_levels", "output_count": len(pipeline_state.get("safety_assessments", [])), "output": pipeline_state.get("safety_assessments", [])},
            "5_detect_inconsistencies": {"node": "detect_inconsistencies", "output_count": len(pipeline_state.get("inconsistencies", [])), "output": pipeline_state.get("inconsistencies", [])},
            "6_detect_gaps": {"node": "detect_gaps", "output_count": len(pipeline_state.get("gaps", [])), "output": pipeline_state.get("gaps", [])},
            "7_repair_json": {"node": "repair_json", "was_invoked": pipeline_state.get("json_repair_source") is not None},
        }
        response["node_trace"] = node_trace

    return response


# --- NODE: REPORT GENERATOR --------------------------------------------------
def generate_report_node(state):
    print("\n[Node 6] Generating traceability report...")
    include_trace = state.get("include_trace", False)
    analysis_id = state.get("analysis_id", 0)
    report = format_analysis_response(state, analysis_id=analysis_id, include_trace=include_trace)
    print(f"   \u2192 Report generated successfully")
    return {**state, "report": report}


def _classify_fallback_from_requirements(requirements):
    """Domain-based safety classification fallback: SAFETY domain items are
    safety-relevant, all others are not."""
    classified = []
    for r in requirements:
        domain = r.get("domain", "")
        is_safety = domain == "SAFETY"
        classified.append({
            **r,
            "safety_relevant": is_safety,
            "safety_reason": "Domain: SAFETY" if is_safety else None,
        })
    return classified


def repair_json_node(state):
    print("\n[Node repair_json] Repairing malformed JSON payload from LLM output...")
    source = state.get("json_repair_source")
    raw = state.get("json_repair_raw", "")
    hint = state.get("json_repair_hint", "expected JSON schema")
    attempt_count = state.get("json_repair_attempts") or 0

    if attempt_count >= 2:
        audit = state.get("audit_log", [])
        audit.append({"node": "repair_json_gave_up", "input": source or "unknown", "output": "Repair failed twice; continuing with degraded defaults."})
        fallback_state = {**state, "json_repair_needed": False, "json_repair_attempts": attempt_count, "audit_log": audit}
        if source == "classify_requirements":
            return {**fallback_state, "classified": _classify_fallback_from_requirements(state.get("requirements", []))}
        if source == "assess_safety_levels":
            return {**fallback_state, "safety_assessments": []}
        if source == "detect_inconsistencies":
            return {**fallback_state, "inconsistencies": []}
        if source == "detect_gaps":
            return {**fallback_state, "gaps": []}
        return fallback_state

    system = "You are a JSON repair assistant for a requirements analysis pipeline. An earlier LLM response failed to parse into valid JSON. Your job is to fix the broken JSON and return only valid JSON matching the expected schema. Do not include markdown, explanations, or any text outside the JSON object."
    user = f"Source node: {source}\nParsing hint: {hint}\nMalformed raw response:\n{raw}\nIf the content cannot be repaired, return the minimal valid JSON structure for the target field."

    from ..llm.client import call_llm_json

    try:
        repaired = call_llm_json(system, user, max_tokens=1200, schema_hint=f"repair for {source}")
    except JSONParsingException as exc:
        print(f"   \u2192 Repair attempt failed (JSON parse): {exc}")
        return repair_json_node({**state, "json_repair_attempts": attempt_count + 1})
    except Exception as exc:
        print(f"   LLM repair call failed: {exc}")
        audit = state.get("audit_log", [])
        audit.append({"node": "repair_json_gave_up", "input": source or "unknown", "output": f"LLM error during repair: {exc}"})
        fallback_state = {**state, "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}
        if source == "classify_requirements":
            return {**fallback_state, "classified": _classify_fallback_from_requirements(state.get("requirements", []))}
        if source == "assess_safety_levels":
            return {**fallback_state, "safety_assessments": []}
        if source == "detect_inconsistencies":
            return {**fallback_state, "inconsistencies": []}
        if source == "detect_gaps":
            return {**fallback_state, "gaps": []}
        return fallback_state

    audit = state.get("audit_log", [])
    audit.append({"node": "repair_json_success", "input": source or "unknown", "output": f"Repaired JSON for {source}."})

    if source == "classify_requirements":
        repaired_classified = repaired.get("classified", [])
        req_dict = {r["id"]: r for r in state.get("requirements", [])}
        merged = []
        for lc in repaired_classified:
            req_id = lc.get("id")
            if req_id in req_dict:
                req = req_dict[req_id].copy()
                req["safety_relevant"] = lc.get("safety_relevant", False)
                req["safety_reason"] = lc.get("safety_reason")
                merged.append(req)
            else:
                merged.append(lc)
        # Fallback unmatched: use domain-based heuristic for any requirements the LLM/repair skipped
        for req_id, req in req_dict.items():
            if req_id not in {lc.get("id") for lc in repaired_classified}:
                domain = req.get("domain", "")
                is_safety = domain == "SAFETY"
                req["safety_relevant"] = is_safety
                req["safety_reason"] = "Domain: SAFETY" if is_safety else None
                merged.append(req)
        if not merged and state.get("requirements"):
            merged = _classify_fallback_from_requirements(state["requirements"])
        return {**state, "classified": merged, "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}
    if source == "assess_safety_levels":
        return {**state, "safety_assessments": repaired.get("assessments", []), "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}
    if source == "detect_inconsistencies":
        return {**state, "inconsistencies": repaired.get("inconsistencies", []), "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}
    if source == "detect_gaps":
        return {**state, "gaps": repaired.get("gaps", []), "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}
    return {**state, "json_repair_needed": False, "json_repair_attempts": attempt_count + 1, "audit_log": audit}


# --- BUILD THE GRAPH ---------------------------------------------------------
def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("extract_requirements", extract_requirements_node)
    graph.add_node("classify_requirements", classify_requirements_node)
    graph.add_node("retrieve_context", retrieve_context_node)
    graph.add_node("assess_safety_levels", assess_safety_levels_node)
    graph.add_node("detect_inconsistencies", detect_inconsistencies_node)
    graph.add_node("detect_gaps", detect_gaps_node)
    graph.add_node("repair_json", repair_json_node)
    graph.add_node("generate_report", generate_report_node)

    graph.set_entry_point("extract_requirements")
    graph.add_edge("extract_requirements", "classify_requirements")
    graph.add_conditional_edges(
        "classify_requirements",
        lambda state: "repair_json" if state.get("json_repair_needed") else "retrieve_context",
    )
    graph.add_edge("retrieve_context", "assess_safety_levels")
    graph.add_conditional_edges(
        "assess_safety_levels",
        lambda state: "repair_json" if state.get("json_repair_needed") else "detect_inconsistencies",
    )
    graph.add_conditional_edges(
        "detect_inconsistencies",
        lambda state: "repair_json" if state.get("json_repair_needed") else "detect_gaps",
    )
    graph.add_conditional_edges(
        "detect_gaps",
        lambda state: "repair_json" if state.get("json_repair_needed") else "generate_report",
    )
    graph.add_conditional_edges(
        "repair_json",
        lambda state: {
            "classify_requirements": "retrieve_context",
            "assess_safety_levels": "detect_inconsistencies",
            "detect_inconsistencies": "detect_gaps",
            "detect_gaps": "generate_report",
        }.get(state.get("json_repair_source"), "generate_report"),
    )
    graph.add_edge("generate_report", END)

    return graph.compile()
