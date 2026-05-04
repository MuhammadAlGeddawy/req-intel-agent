import json
from ...llm.client import call_llm_json
from ...llm.prompts import SAFETY_ASSESS_SYSTEM_PROMPT
from ...utils.logger import log_entry

# ─── NODE 3: SAFETY LEVEL ASSESSOR ───────────────────────────────────────────
def assess_safety_levels_node(state):
    print("\n[Node 3] Assessing ASIL levels for safety-relevant requirements...")

    safety_reqs = [r for r in state["classified"] if r.get("safety_relevant")]

    if not safety_reqs:
        print("   → No safety-relevant requirements found, skipping")
        return {**state, "safety_assessments": []}

    system = SAFETY_ASSESS_SYSTEM_PROMPT

    user = f"Safety requirements to assess:\n{json.dumps(safety_reqs, indent=2)}"
    result = call_llm_json(system, user, max_tokens=2000)
    assessments = result.get("assessments", [])

    print(f"   → ASIL suggestions generated for {len(assessments)} requirements")
    for a in assessments:
        print(f"      {a.get('id')}: Suggested ASIL-{a.get('suggested_asil')} ⚠️ Human review required")

    audit = state.get("audit_log", [])
    audit.append(log_entry(state, "assess_safety_levels",
                           f"{len(safety_reqs)} safety requirements",
                           f"{len(assessments)} ASIL suggestions (all pending human review)"))

    return {**state, "safety_assessments": assessments, "audit_log": audit}