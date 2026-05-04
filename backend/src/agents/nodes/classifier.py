import json
from ...llm.client import call_llm_json
from ...llm.prompts import CLASSIFY_SYSTEM_PROMPT
from ...utils.logger import log_entry

# ─── NODE 2: SAFETY FLAGGER (DOMAINS FROM REGEX EXTRACTOR) ────────────────────
def classify_requirements_node(state):
    print("\n[Node 2] Flagging safety-relevant requirements (domains from regex)...")

    system = CLASSIFY_SYSTEM_PROMPT

    req_list = json.dumps(state["requirements"], indent=2)
    user = f"""Requirements (domains already extracted via regex):\n{req_list}

Classify ONLY safety relevance. Preserve existing domains. Return ONLY safety_relevant and safety_reason."""
    result = call_llm_json(system, user, max_tokens=2000)

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

    # Fallback unmatched
    for req_id, req in req_dict.items():
        if req_id not in {lc.get("id") for lc in llm_classified}:
            req["safety_relevant"] = False
            req["safety_reason"] = None
            classified.append(req)

    safety_count = sum(1 for r in classified if r.get("safety_relevant"))
    print(f"   → {safety_count} safety-relevant requirements identified")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "classify_requirements_safety_only",
                           f"{len(classified)} requirements",
                           f"{safety_count} flagged as safety-relevant (domains preserved from regex)"))

    return {**state, "classified": classified, "audit_log": audit}
