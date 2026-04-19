import json
from ...llm.client import call_llm_json
from ...llm.prompts import CLASSIFY_SYSTEM_PROMPT
from ...utils.logger import log_entry

# ─── NODE 2: DOMAIN CLASSIFIER + SAFETY FLAGGER ──────────────────────────────
def classify_requirements_node(state):
    print("\n[Node 2] Classifying requirements and flagging safety-relevant ones...")

    system = CLASSIFY_SYSTEM_PROMPT

    req_list = json.dumps(state["requirements"], indent=2)
    user = f"Requirements:\n{req_list}"
    result = call_llm_json(system, user, max_tokens=2000)

    classified = result.get("classified", state["requirements"])
    safety_count = sum(1 for r in classified if r.get("safety_relevant"))
    print(f"   → {safety_count} safety-relevant requirements identified")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "classify_requirements",
                           f"{len(classified)} requirements",
                           f"{safety_count} flagged as safety-relevant"))

    return {**state, "classified": classified, "audit_log": audit}