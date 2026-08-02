import json
from ...llm.client import call_llm_json, JSONParsingException
from ...llm.prompts import SAFETY_ASSESS_SYSTEM_PROMPT
from ...utils.logger import log_entry


def _build_historical_context_block(state, requirement):
    context_items = state.get("retrieved_context", {}).get(requirement.get("id"), [])
    if not context_items:
        return "No historical context available."

    lines = []
    for item in context_items:
        lines.append(
            f"- {item.get('req_id')} | {item.get('domain', 'UNKNOWN')} | {item.get('req_text')} | score={item.get('score', 0)}"
        )
    return "Historical context for this requirement:\n" + "\n".join(lines)

# ─── NODE 3: SAFETY LEVEL ASSESSOR ───────────────────────────────────────────
def assess_safety_levels_node(state):
    print("\n[Node 3] Assessing ASIL levels for safety-relevant requirements...")

    safety_reqs = [r for r in state["classified"] if r.get("safety_relevant")]

    if not safety_reqs:
        print("   → No safety-relevant requirements found, skipping")
        return {**state, "safety_assessments": []}

    assessments = []
    for requirement in safety_reqs:
        historical_context_block = _build_historical_context_block(state, requirement)
        system = SAFETY_ASSESS_SYSTEM_PROMPT.format(historical_context_block=historical_context_block)
        user = f"Assess this safety requirement:\n{json.dumps(requirement, indent=2)}"
        try:
            result = call_llm_json(system, user, max_tokens=800, schema_hint="safety assessment output")
        except JSONParsingException as exc:
            audit = state.get("audit_log", [])
            audit.append(log_entry(state, "assess_safety_levels_parse_error", requirement.get("id", "unknown"), str(exc)))
            return {
                **state,
                "safety_assessments": [],
                "json_repair_needed": True,
                "json_repair_source": "assess_safety_levels",
                "json_repair_raw": exc.raw,
                "json_repair_hint": exc.schema_hint,
                "json_repair_attempts": state.get("json_repair_attempts", 0),
                "audit_log": audit,
            }
        except Exception as exc:
            print(f"   ⚠️  LLM call failed for safety assessment: {exc}")
            audit = state.get("audit_log", [])
            audit.append(log_entry(state, "assess_safety_levels_fallback", requirement.get("id", "unknown"), str(exc)))
            return {**state, "safety_assessments": [], "audit_log": audit}

        assessment = result.get("assessments", [{}])[0] if result.get("assessments") else {}
        assessment["id"] = requirement.get("id")
        assessments.append(assessment)

    print(f"   → ASIL suggestions generated for {len(assessments)} requirements")
    for a in assessments:
        print(f"      {a.get('id')}: Suggested ASIL-{a.get('suggested_asil')} ⚠️ Human review required")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "assess_safety_levels",
                           f"{len(safety_reqs)} safety requirements",
                           f"{len(assessments)} ASIL suggestions (all pending human review)"))

    return {**state, "safety_assessments": assessments, "audit_log": audit}
