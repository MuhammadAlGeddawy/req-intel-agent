from datetime import datetime
from typing import Dict
from ..llm.client import MODEL

# ─── HELPER: LOG LLM CALLS ───────────────────────────────────────────────────
def log_entry(state, node: str, input_summary: str, output_summary: str) -> Dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "node": node,
        "input": input_summary,
        "output": output_summary,
        "model": MODEL
    }