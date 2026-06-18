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

The repository supports three usage modes:

1. **CLI mode** — run the sample workflow and save a JSON report locally
2. **API mode** — submit documents over HTTP and persist analyses to a SQLite database
3. **Docker mode** — run the API as a containerized service with Docker Compose

---

## Current Features

- LangGraph-powered multi-step requirement analysis
- Console report generation
- JSON report export to `requirements_report.json`
- FastAPI API for submitting analyses
- SQLite-backed persistence for saved analyses (with Docker volume support)
- Simple request helper script in `request.py`
- Local HTML viewer file: `report_viewer.html`
- Docker and Docker Compose support with persistent named volumes
- Non-root container user for security
- Healthcheck endpoint for container orchestration
- **ISO 26262 Synthetic Dataset Generation Pipeline**
  - ASIL validation and correction against ISO 26262 Table 4
  - EARS grammar normalization and cleanup
  - Fingerprint-based deduplication
  - Strategic data re-balancing (quality over quantity)
  - Stratified train/eval splits with ChatML format
  - Ready for LLM fine-tuning

---

## Project Structure

```text
req_intel_agent/
├── backend/                        # Main application directory
│   ├── config/
│   │   ├── .env                    # Local environment variables (kept out of git)
│   │   └── .env.example            # Example environment file
│   ├── data/                       # Persistent volume for SQLite in Docker
│   ├── src/
│   │   ├── agents/
│   │   │   ├── graph.py            # LangGraph orchestration
│   │   │   ├── state.py            # Agent state definition
│   │   │   └── nodes/
│   │   │       ├── classifier.py   # Requirement classification
│   │   │       ├── extractor.py    # Requirement extraction
│   │   │       ├── safety.py       # Safety / ASIL assessment
│   │   │       └── validator.py    # Gaps and inconsistencies
│   │   ├── llm/
│   │   │   ├── client.py           # LLM client integration
│   │   │   └── prompts.py          # Prompt definitions
│   │   ├── utils/
│   │   │   ├── logger.py           # Audit logging helpers
│   │   │   └── parsers.py          # Parsing helpers
│   │   ├── api.py                  # FastAPI application
│   │   ├── db.py                   # SQLAlchemy models and DB session setup
│   │   ├── main.py                 # CLI entrypoint / sample run flow
│   │   └── __init__.py
│   ├── run.py                      # Entrypoint: runs src.main or API
│   ├── requirements.txt            # Python dependencies
│   ├── Dockerfile                  # Docker image definition
│   └── .dockerignore               # Docker build exclusions
├── Notebooks/                      # Jupyter notebooks & datasets
│   ├── SynRequirements.ipynb       # Dataset generation & re-balancing pipeline
│   ├── iso26262_train.jsonl        # Stratified training set (859 samples)
│   ├── iso26262_eval.jsonl         # Stratified evaluation set (96 samples)
│   ├── asil_train_final.jsonl      # Cleaned training data
│   ├── ASIL_levels_dataset_v*.jsonl# Intermediate processing datasets
│   └── ASIL_levels_dataset_*_*.jsonl # Dataset variants & splits
├── reports/                        # Generated reports & analysis outputs
│   ├── requirements_report.json    # Sample analysis report
│   ├── ASIL_Report.pdf             # PDF safety report
│   ├── MIGRATION_REPORT.md         # Data migration notes
│   ├── CHANGELOG.md                # Version history
│   ├── TODO.md                     # Task tracking
│   └── *.json                      # Intermediate analysis files
├── tests/                          # Test directory
├── docker-compose.yaml             # Docker Compose orchestration
├── request.py                      # Example API client script
├── sample_requirements.txt         # Sample requirements document
├── ASIL_levels_dataset_v2.jsonl    # Root dataset file
├── requirements_agent.db           # SQLite database (local dev, git-ignored)
├── README.md                       # This file
├── .gitignore                      # Git exclusions
└── .git/                           # Git repository
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

- Python 3.10+ (for local development)
- OpenRouter API key or compatible LLM configuration expected by the project
- Internet access for model calls if using hosted LLMs
- Docker & Docker Compose (optional, for containerized deployment)

Python dependencies are listed in `backend/requirements.txt`:

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

### Local Development

From the `backend/` directory:

```bash
pip install -r requirements.txt
```

Create `config/.env` with your local settings. At minimum, configure the API key your LLM client expects. You can copy the example file:

```bash
cp config/.env.example config/.env
```

Example:

```env
OPENROUTER_API_KEY=your_key_here
DATABASE_URL=sqlite:///./requirements_agent.db
```

Notes:

- `backend/config/.env` is intentionally ignored by git
- if `DATABASE_URL` is not set, the app defaults to SQLite at:
  `requirements_agent.db`
- that SQLite file is typically created in the project root when the API runs locally from `backend/`

### Docker Setup

Ensure Docker and Docker Compose are installed. The provided `docker-compose.yaml` expects a `backend/config/.env` file:

```bash
cp backend/config/.env.example backend/config/.env
# Edit backend/config/.env and add your OPENROUTER_API_KEY
```

Then build and run from the project root:

```bash
docker compose up --build
```

The Docker service will be available at `http://localhost:3001`.

---

## Running the CLI Workflow

The CLI mode uses `sample_requirements.txt`, runs the LangGraph pipeline, prints a formatted report, and writes the full JSON output to `requirements_report.json`.

From the `backend/` directory:

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

### Locally

Start the FastAPI app from the `backend/` directory:

```bash
uvicorn src.api:app --reload
```

The API initializes the database on startup.

Default local URL:

```text
http://127.0.0.1:8000
```

### With Docker Compose

```bash
docker compose up --build
```

This mounts a persistent volume (`agent-data`) for the SQLite database and exposes host port `3001` mapped to container port `8000`.

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

## Running the Dataset Pipeline

The training dataset preparation is handled in the Jupyter notebook `Notebooks/SynRequirements.ipynb`.

### Prerequisites

```bash
pip install jupyter scikit-learn pandas numpy
```

### Execution

From the project root directory:

```bash
jupyter notebook Notebooks/SynRequirements.ipynb
```

Or using JupyterLab:

```bash
jupyter lab Notebooks/SynRequirements.ipynb
```

### Output

The notebook generates:

- `Notebooks/iso26262_train.jsonl` — Training dataset (ChatML format, stratified)
- `Notebooks/iso26262_eval.jsonl` — Evaluation dataset (ChatML format, stratified)

These files are ready for fine-tuning language models on ISO 26262 safety analysis tasks.

---

## Example API Usage

### Using `curl`

```bash
curl -X POST "http://localhost:3001/analyze" \
  -H "Content-Type: application/json" \
  -d '{"document":"REQ-SYS-001 The system shall...","document_name":"example.txt"}'
```

### Using the included script

From the project root, the repository includes `request.py`, which reads `sample_requirements.txt` and posts it to the API:

```bash
python request.py
```

Note: `request.py` uses the `requests` package, which is included in `backend/requirements.txt`.

---

## Database Storage

The persistence layer is implemented in `backend/src/db.py` using SQLAlchemy.

Stored table:

- `analysis_records`

Stored fields:

- `id`
- `document_name`
- `raw_document`
- `report`
- `created_at`

Default database location (local development):

```text
requirements_agent.db
```

Default connection string:

```text
sqlite:///./requirements_agent.db
```

When running with Docker Compose, the database is persisted in a named volume at:

```text
/app/data/requirements_agent.db
```

You can override this by setting `DATABASE_URL` in `backend/config/.env`.

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

## Dataset Preparation & Training

### Synthetic Safety Dataset Generation

The `Notebooks/SynRequirements.ipynb` notebook implements a multi-stage pipeline for generating and preparing ISO 26262 safety datasets:

#### Pipeline Stages

1. **Validation & Correction**
   - ASIL level verification against ISO 26262 Table 4
   - Automatic correction of mismatched factor combinations
   - JSON schema validation

2. **Grammar & Syntax Cleanup**
   - EARS requirement text normalization
   - Removal of "When The" syntax stutters
   - Standardization of shall-statements

3. **Deduplication**
   - Fingerprint-based duplicate detection
   - Preservation of unique requirement variations

4. **Data Re-balancing (Strategic Undersampling)**
   - **Heavy Weights** (S3+E4+C3): Reduced from 179 to 53 samples (30% retention)
   - **Mid Weights** (≥2 max factors): Reduced from 489 to 293 samples (60% retention)
   - **Rarity** (low factors): Preserved at 100% (430 samples)
   - **Overall reduction**: 1,277 → 955 samples (25% reduction for improved signal-to-noise ratio)

5. **Stratified Train/Eval Split**
   - 90% training set: `iso26262_train.jsonl` (859 samples)
   - 10% evaluation set: `iso26262_eval.jsonl` (96 samples)
   - Stratification by ASIL level ensures balanced class distribution

#### Generated Datasets

- `Notebooks/iso26262_train.jsonl` — Training set with ChatML format
- `Notebooks/iso26262_eval.jsonl` — Evaluation set with ChatML format
- Both datasets use stratified splits to maintain ASIL distribution

#### Design Philosophy

The re-balancing prioritizes **quality over quantity**, reducing over-represented "High Risk" combinations (S3/E4/C3) to force the model to:
- Learn meaningful patterns in requirement text
- Distinguish subtle safety factors
- Avoid defaulting to highest ASIL for all ambiguous cases

---

## Docker Persistence

### Volume Configuration

The Docker Compose setup includes a named volume for persistent data storage:

```yaml
volumes:
  agent-data:
    driver: local
```

This volume mounts to `/app/data` inside the container and survives:
- Container restarts
- Container destruction and rebuild cycles
- Complete stack teardown and recreation

### Verification

To verify persistence:

```bash
# Start the service
docker compose up -d

# Submit a request
curl -X POST "http://localhost:3001/analyze" \
  -H "Content-Type: application/json" \
  -d '{"document":"REQ-SYS-001 ...","document_name":"test.txt"}'

# Destroy and rebuild
docker compose down
docker compose up -d --build

# Verify data persists
curl http://localhost:3001/analyses
```

The database file at `/app/data/requirements_agent.db` will persist through the entire lifecycle.

---

## Important Notes

- Safety / ASIL output is advisory and requires human review
- `backend/config/.env` should never be committed
- local cache files and runtime artifacts are ignored by git
- the local SQLite database file is also ignored by git
- the Docker image runs as a non-root user (`appuser`) for security
- Generated training datasets are saved in `Notebooks/` for LLM fine-tuning

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
- **Docker**
- **Docker Compose**

---

## Next Improvements

Potential next steps for the project:

- add Swagger/OpenAPI usage examples to the README
- add automated tests for API routes and DB persistence
- add a richer frontend for browsing saved analyses
- add authentication if the API is exposed beyond local development
- add CI/CD pipeline for automated testing and image publishing

