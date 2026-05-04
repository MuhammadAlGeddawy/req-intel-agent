from typing import TypedDict, List, Dict, Optional

# ─── STATE DEFINITION ────────────────────────────────────────────────────────
class AgentState(TypedDict):
    # Input
    raw_document: str
    document_name: str

    # Extracted
    requirements: List[Dict]           # List of {id, text, domain}

    # Analysis
    classified: List[Dict]             # Requirements with domain + safety flag
    safety_assessments: List[Dict]     # ASIL suggestions for safety reqs
    inconsistencies: List[Dict]        # Detected conflicts between requirements
    gaps: List[Dict]                   # Missing traceability links

    # Output
    report: Optional[Dict]
    audit_log: List[Dict]              # Every LLM call logged