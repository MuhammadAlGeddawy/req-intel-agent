from typing import TypedDict, List, Dict, Optional

# ─── STATE DEFINITION ────────────────────────────────────────────────────────
class AgentState(TypedDict):
    # Input
    raw_document: str
    document_name: str
    include_trace: bool                 # Whether to include node_trace in report

    # Extracted
    requirements: List[Dict]           # List of {id, text, domain}

    # Analysis
    classified: List[Dict]             # Requirements with domain + safety flag
    safety_assessments: List[Dict]     # ASIL suggestions for safety reqs
    inconsistencies: List[Dict]        # Detected conflicts between requirements
    gaps: List[Dict]                   # Missing traceability links
    retrieved_context: Dict[str, List[Dict]]  # Historical requirement context retrieved for each requirement

    # Output
    report: Optional[Dict]
    audit_log: List[Dict]              # Every LLM call logged

    json_repair_needed: bool | None
    json_repair_source: str | None
    json_repair_raw: str | None
    json_repair_hint: str | None
    json_repair_attempts: int | None
