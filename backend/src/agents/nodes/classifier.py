import json
from ...llm.client import call_llm_json, JSONParsingException
from ...llm.prompts import CLASSIFY_SYSTEM_PROMPT
from ...utils.logger import log_entry

# ─── NODE 2: SAFETY FLAGGER (DOMAINS FROM REGEX EXTRACTOR) ────────────────────
def classify_requirements_node(state):
    print("\n[Node 2] Flagging safety-relevant requirements (domains from regex)...")

    system = CLASSIFY_SYSTEM_PROMPT

    req_list = json.dumps(state["requirements"], indent=2)
    user = f"""Requirements (domains already extracted via regex):\n{req_list}

Classify ONLY safety relevance. Preserve existing domains. Return ONLY safety_relevant and safety_reason."""
    try:
        result = call_llm_json(system, user, max_tokens=800, schema_hint="classification output")
    except JSONParsingException as exc:
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "classify_requirements_parse_error", "classification output", str(exc)))
        return {
            **state,
            "classified": [],
            "json_repair_needed": True,
            "json_repair_source": "classify_requirements",
            "json_repair_raw": exc.raw,
            "json_repair_hint": exc.schema_hint,
            "json_repair_attempts": state.get("json_repair_attempts", 0),
            "audit_log": audit,
        }
    except Exception as exc:
        print(f"   ⚠️  LLM call failed for classify_requirements: {exc}")
        audit = state.get("audit_log", [])
        audit.append(log_entry(state, "classify_requirements_fallback", "classification output", str(exc)))
        # Domain-based fallback: SAFETY domain items are flagged as safety-relevant
        classified = []
        for r in state["requirements"]:
            domain = r.get("domain", "")
            is_safety = domain == "SAFETY"
            classified.append({
                **r,
                "safety_relevant": is_safety,
                "safety_reason": "Domain: SAFETY" if is_safety else None,
            })
        return {**state, "classified": classified, "audit_log": audit}

    # Merge regex domains with LLM safety flags
    req_dict = {r["id"]: r for r in state["requirements"]}  # id -> {id, text, domain}
    llm_classified = result.get("classified", [])

    classified = []
    for lc in llm_classified:
        req_id = lc.get("id")
        if req_id in req_dict:
            req = req_dict[req_id].copy()
            req["safety_relevant"] = lc.get("safety_relevant", False)
            req["safety_reason"] = lc.get("safety_reason")
            classified.append(req)
        else:
            print(f"   → Warning: LLM classified unknown req ID: {req_id}")

    # Fallback unmatched: use domain-based heuristic for any requirements the LLM skipped
    for req_id, req in req_dict.items():
        if req_id not in {lc.get("id") for lc in llm_classified}:
            domain = req.get("domain", "")
            is_safety = domain == "SAFETY"
            req["safety_relevant"] = is_safety
            req["safety_reason"] = "Domain: SAFETY" if is_safety else None
            classified.append(req)

    safety_count = sum(1 for r in classified if r.get("safety_relevant"))
    print(f"   → {safety_count} safety-relevant requirements identified")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "classify_requirements_safety_only",
                           f"{len(classified)} requirements",
                           f"{safety_count} flagged as safety-relevant (domains preserved from regex)"))

    return {**state, "classified": classified, "audit_log": audit}
