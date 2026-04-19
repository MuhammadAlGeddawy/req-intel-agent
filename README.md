# Engineering Requirements Intelligence Agent
### Multi-step LangGraph agent for automotive requirements traceability


---

## Project Structure

```
req_intel_agent/
├── src/
│   ├── agents/
│   │   ├── graph.py          # LangGraph orchestration
│   │   ├── state.py          # AgentState TypedDict
│   │   └── nodes/            # Individual node logic
│   │       ├── extractor.py  # (Regex logic)
│   │       ├── classifier.py
│   │       ├── safety.py
│   │       └── validator.py  # Gaps/Inconsistencies
│   ├── llm/
│   │   ├── client.py         # OpenRouter/Anthropic wrappers
│   │   └── prompts.py        # Centralized system prompts (versioned)
│   ├── utils/
│   │   ├── parsers.py        # Regex and JSON cleanup
│   │   └── logger.py         # Custom audit logging
│   └── main.py               # Entry point (FastAPI or CLI)
├── tests/                    # Unit tests for nodes & regex
├── config/                   # .env and yaml configs
├── requirements.txt
└── README.md
```

---

## What It Does

A 6-node LangGraph agent that processes engineering requirement documents and produces a structured traceability report:

```
Document Input
     ↓
[Node 1] Extract Requirements     → Parse all REQ-XXX-NNN items
     ↓
[Node 2] Classify + Flag Safety   → Domain tagging, safety relevance
     ↓
[Node 3] Assess ASIL Levels       → ISO 26262 ASIL suggestions (human review required)
     ↓
[Node 4] Detect Inconsistencies   → Cross-discipline conflicts
     ↓
[Node 5] Detect Gaps              → Missing traceability links (ASPICE)
     ↓
[Node 6] Generate Report          → JSON + console report with audit log
```

---

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenRouter API key in config/.env
# Get your free API key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_key_here

# Run the agent
python run.py
```

## Alternative Run Methods

You can also run directly:

```bash
# From req_intel_agent directory
python -c "import sys; sys.path.insert(0, '.'); import src.main"
```

Or using Python module syntax:

```bash
# From req_intel_agent directory
python -m src.main
```

---

## Sample Output

The agent processes `sample_requirements.txt` (sample lighting system requirements) and outputs:

- **Inconsistency detected**: REQ-SYS-002 (operates -40°C to 125°C) vs REQ-SW-004 (operates 8°C to 120°C) — temperature range conflict
- **Gaps detected**: Missing test requirements for several hardware requirements
- **ASIL suggestions**: For safety requirements (pending human review)
- **Audit log**: Every LLM call timestamped and recorded

Full report saved to `requirements_report.json`

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| Human review gates on ASIL | ISO 26262 requires expert sign-off — AI suggests, human decides |
| Audit log on every LLM call | ASPICE traceability compliance |
| JSON structured outputs | Downstream integration with ALM tools like Codebeamer |
| Graceful JSON parsing fallback | Production robustness |

---

## Extending This Project

- Add a **LangGraph interrupt checkpoint** before report generation for human approval
- Add **Codebeamer API integration** to push suggested links automatically
- Add **FAISS vector search** for semantic requirement similarity (not just keyword)
- Add **Simulink output ingestion** as an additional document type
- Add a **Streamlit UI** for non-technical stakeholders

---

## Tech Stack

- **LangGraph** — agent orchestration and state management
- **Qwen** — LLM reasoning at each node
- **Python / Pydantic** — structured output validation
- **JSON** — audit-trail and report format
