# Engineering Requirements Intelligence Agent

Multi-step LangGraph-based analysis pipeline for engineering requirements, with both a CLI workflow and a FastAPI service for persistent analysis history.

## Overview

This project analyzes requirements documents and produces a structured report covering:

- extracted requirements
- domain classification
- safety relevance
- ASIL suggestions
- inconsistency detection
- traceability gap detection
- audit log output

The repository now supports two usage modes:

1. **CLI mode** — run the sample workflow and save a JSON report locally
2. **API mode** — submit documents over HTTP and persist analyses to a SQLite database

---

## Current Features

- LangGraph-powered multi-step requirement analysis
- Console report generation
- JSON report export to `requirements_report.json`
- FastAPI API for submitting analyses
- SQLite-backed persistence for saved analyses
- Simple request helper script in `request.py`
- Local HTML viewer file: `report_viewer.html`

---

## Project Structure

```text
req_intel_agent/
├── config/
│   └── .env                        # Local environment variables (kept out of git)
├── src/
│   ├── agents/
│   │   ├── graph.py                # LangGraph orchestration
│   │   ├── state.py                # Agent state definition
│   │   └── nodes/
│   │       ├── classifier.py       # Requirement classification
│   │       ├── extractor.py        # Requirement extraction
│   │       ├── safety.py           # Safety / ASIL assessment
│   │       └── validator.py        # Gaps and inconsistencies
│   ├── llm/
│   │   ├── client.py               # LLM client integration
│   │   └── prompts.py              # Prompt definitions
│   ├── utils/
│   │   ├── logger.py               # Audit logging helpers
│   │   └── parsers.py              # Parsing helpers
│   ├── api.py                      # FastAPI application
│   ├── db.py                       # SQLAlchemy models and DB session setup
│   └── main.py                     # CLI entrypoint / sample run flow
├── tests/
├── report_viewer.html              # Local report viewer
├── request.py                      # Example API client script
├── requirements.txt
├── run.py                          # Runs src.main
├── sample.txt
├── sample_requirements.txt
├── requirements_report.json        # Generated sample report
└── README.md
```

---

## What the Agent Produces

The analysis pipeline builds a report with sections such as:

- metadata
- summary
- inconsistencies
- traceability gaps
- safety assessments
- audit log

Typical outputs include:

- conflicting requirement ranges or constraints
- missing traceability or validation links
- suggested ASIL classifications for safety-related items
- timestamped LLM-call audit data

---

## Requirements

- Python 3.10+
- OpenRouter API key or compatible LLM configuration expected by the project
- Internet access for model calls if using hosted LLMs

Python dependencies are listed in `requirements.txt`:

- `langgraph`
- `langchain`
- `langchain-core`
- `pydantic`
- `openai`
- `python-dotenv`
- `sqlalchemy`
- `fastapi`
- `uvicorn[standard]`

---

## Setup

From the `req_intel_agent` directory:

```bash
pip install -r requirements.txt
```

Create `config/.env` with your local settings. At minimum, configure the API key your LLM client expects.

Example:

```env
OPENROUTER_API_KEY=your_key_here
DATABASE_URL=sqlite:///./requirements_agent.db
```

Notes:

- `config/.env` is intentionally ignored by git
- if `DATABASE_URL` is not set, the app defaults to SQLite at:
  `requirements_agent.db`
- that SQLite file is typically created in the `req_intel_agent` directory when the API runs from there

---

## Running the CLI Workflow

The CLI mode uses `sample_requirements.txt`, runs the LangGraph pipeline, prints a formatted report, and writes the full JSON output to `requirements_report.json`.

From the `req_intel_agent` directory:

```bash
python run.py
```

Alternative:

```bash
python -m src.main
```

Generated file:

```text
requirements_report.json
```

---

## Running the API

Start the FastAPI app from the `req_intel_agent` directory:

```bash
uvicorn src.api:app --reload
```

The API initializes the database on startup.

Default local URL:

```text
http://127.0.0.1:8000
```

### Available Endpoints

#### `GET /health`

Basic health check.

Response:

```json
{
  "status": "ok"
}
```

#### `POST /analyze`

Submit a requirements document for analysis and persistence.

Request body:

```json
{
  "document": "REQ-SYS-001 ...",
  "document_name": "my_requirements.txt"
}
```

Response shape:

```json
{
  "analysis_id": 1,
  "report": {}
}
```

#### `GET /analyses`

Returns saved analysis summaries ordered by newest first.

#### `GET /analyses/{analysis_id}`

Returns a single saved analysis, including:

- document name
- raw document
- report
- creation timestamp

---

## Example API Usage

### Using `curl`

```bash
curl -X POST "http://127.0.0.1:8000/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"document\":\"REQ-SYS-001 The system shall...\",\"document_name\":\"example.txt\"}"
```

### Using the included script

The repository includes `request.py`, which reads `sample_requirements.txt` and posts it to the local API:

```bash
python request.py
```

Note: `request.py` uses the `requests` package. If it is not already installed in your environment, install it manually:

```bash
pip install requests
```

---

## Database Storage

The persistence layer is implemented in `src/db.py` using SQLAlchemy.

Stored table:

- `analysis_records`

Stored fields:

- `id`
- `document_name`
- `raw_document`
- `report`
- `created_at`

Default database location:

```text
requirements_agent.db
```

Default connection string:

```text
sqlite:///./requirements_agent.db
```

You can override this by setting `DATABASE_URL` in `config/.env`.

---

## Sample Output

When running the CLI flow against `sample_requirements.txt`, the project can detect issues such as:

- requirement inconsistencies across domains
- traceability gaps
- safety-relevant items requiring human review
- structured audit information for model interactions

The full JSON output is saved to:

```text
requirements_report.json
```

---

## Important Notes

- Safety / ASIL output is advisory and requires human review
- `config/.env` should never be committed
- local cache files and runtime artifacts are ignored by git
- the local SQLite database file is also ignored by git

---

## Tech Stack

- **Python**
- **LangGraph**
- **LangChain**
- **FastAPI**
- **SQLAlchemy**
- **Pydantic**
- **SQLite**
- **python-dotenv**

---

## Next Improvements

Potential next steps for the project:

- add Swagger/OpenAPI usage examples to the README
- add automated tests for API routes and DB persistence
- add Docker support
- add a richer frontend for browsing saved analyses
- add authentication if the API is exposed beyond local development
