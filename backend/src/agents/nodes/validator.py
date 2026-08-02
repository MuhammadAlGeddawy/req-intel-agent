import json
from ...llm.client import call_llm_json, JSONParsingException
from ...llm.prompts import INCONSISTENCY_SYSTEM_PROMPT, GAP_SYSTEM_PROMPT
from ...utils.logger import log_entry

# ─── NODE 4: INCONSISTENCY DETECTOR ──────────────────────────────────────────
def detect_inconsistencies_node(state):
    print("\n[Node 4] Detecting cross-discipline inconsistencies...")

    system = INCONSISTENCY_SYSTEM_PROMPT

    req_list = json.dumps(state["classified"], indent=2)
    user = f"Full requirement set:\n{req_list}"
    try:
        result = call_llm_json(system, user, max_tokens=800, schema_hint="inconsistency output")
    except JSONParsingException as exc:
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "detect_inconsistencies_parse_error", "inconsistency output", str(exc)))
        return {
            **state,
            "inconsistencies": [],
            "json_repair_needed": True,
            "json_repair_source": "detect_inconsistencies",
            "json_repair_raw": exc.raw,
            "json_repair_hint": exc.schema_hint,
            "json_repair_attempts": state.get("json_repair_attempts", 0),
            "audit_log": audit,
        }
    except Exception as exc:
        print(f"   ⚠️  LLM call failed for detect_inconsistencies: {exc}")
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "detect_inconsistencies_fallback", "inconsistency output", str(exc)))
        return {**state, "inconsistencies": [], "audit_log": audit}

    inconsistencies = result.get("inconsistencies", [])

    print(f"   → {len(inconsistencies)} inconsistencies detected")
    for inc in inconsistencies:
        print(f"      [{inc.get('severity')}] {inc.get('req_id_1')} \u2194 {inc.get('req_id_2')}: {inc.get('description')[:80]}...")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "detect_inconsistencies",
                           f"{len(state['classified'])} requirements",
                           f"{len(inconsistencies)} conflicts found"))

    return {**state, "inconsistencies": inconsistencies, "audit_log": audit}


# ─── NODE 5: GAP DETECTOR ────────────────────────────────────────────────────
def detect_gaps_node(state):
    print("\n[Node 5] Detecting traceability gaps...")

    system = GAP_SYSTEM_PROMPT

    req_list = json.dumps(state["classified"], indent=2)
    user = f"Full requirement set:\n{req_list}"
    try:
        result = call_llm_json(system, user, max_tokens=800, schema_hint="gap output")
    except JSONParsingException as exc:
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "detect_gaps_parse_error", "gap output", str(exc)))
        return {
            **state,
            "gaps": [],
            "json_repair_needed": True,
            "json_repair_source": "detect_gaps",
            "json_repair_raw": exc.raw,
            "json_repair_hint": exc.schema_hint,
            "json_repair_attempts": state.get("json_repair_attempts", 0),
            "audit_log": audit,
        }
    except Exception as exc:
        print(f"   ⚠️  LLM call failed for detect_gaps: {exc}")
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "detect_gaps_fallback", "gap output", str(exc)))
        return {**state, "gaps": [], "audit_log": audit}

    gaps = result.get("gaps", [])

    print(f"   → {len(gaps)} traceability gaps identified")
    for g in gaps:
        print(f"      [{g.get('priority')}] {g.get('gap_type')}: {g.get('affected_req_id')}")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "detect_gaps",
                           f"{len(state['classified'])} requirements",
                           f"{len(gaps)} gaps found"))

    return {**state, "gaps": gaps, "audit_log": audit}
