from ...utils.parsers import extract_requirements
from ...utils.logger import log_entry

# ─── NODE 1: REQUIREMENT EXTRACTOR ───────────────────────────────────────────
def extract_requirements_node(state):
    print("\n[Node 1] Extracting requirements via Regex...")

    raw_text = state.get('raw_document', "")
    requirements = extract_requirements(raw_text)

    print(f"   → Extracted {len(requirements)} requirements (Deterministic)")

    # Maintain your existing audit log structure
    audit = state.get("audit_log", [])
    audit.append(log_entry(
        state, 
        "extract_requirements_regex",
        f"Document: {state.get('document_name', 'Unknown')}",
        f"Extracted {len(requirements)} requirements via Regex"
    ))

    return {**state, "requirements": requirements, "audit_log": audit}