# Requirements Intelligence Agent — Detailed Repository Documentation

## Purpose

This repository implements an automotive requirements intelligence service focused on functional safety screening, risk assessment, and traceability review. The production flow is built around a deterministic extraction step, a LangGraph orchestration layer, and LLM-based classification and assessment nodes.

The service is designed to:

- extract requirement statements from raw documents
- preserve requirement metadata such as IDs and domains
- classify items as safety-relevant or non-safety-relevant
- retrieve relevant historical context when available
- suggest ISO 26262 ASIL values for safety-related requirements
- detect cross-requirement inconsistencies
- find traceability and validation gaps
- persist the results through a FastAPI API
- provide a stable JSON contract for downstream tooling

---

## High-Level Architecture

The core application lives under backend/src.

Production-critical subsystems:

- backend/src/api.py — FastAPI HTTP layer and persistence workflow
- backend/src/agents/graph.py — orchestration and final report shaping
- backend/src/db.py — SQLAlchemy models and DB initialization
- backend/src/llm/client.py — OpenRouter / OpenAI-compatible client, JSON parsing, embedding logic
- backend/src/llm/prompts.py — system prompts for classification and safety assessment
- backend/src/agents/nodes — extraction, classification, retrieval, safety, and validation nodes
- backend/src/utils — parsers and hybrid retrieval helpers

The execution model is stateful and graph-based via StateGraph from LangGraph. The service is not just a data transform; it is a persistent analysis workflow with model calls guarded by repair logic and a durable database-backed result store.

---

## Production Runtime Flow

1. Client submits a raw document through the API.
2. The analysis is saved as a PENDING record in the database.
3. A background task invokes the agent graph.
4. Requirements are extracted from the source text.
5. Each requirement is classified for safety relevance.
6. Relevant requirements receive ASIL-style safety assessment.
7. Inconsistencies and traceability gaps are detected.
8. The final report is formatted into a stable client-facing JSON payload.
9. The completed result is stored and retrievable via the analysis ID.

---

## Production-critical Files

### backend/src/api.py

This is the production HTTP interface.

Responsibilities:

- POST /analyze accepts a document and document name, creates an analysis record, and returns a job ID
- GET /analyses/{analysis_id}/status polls status transitions
- GET /analyses/{analysis_id} returns the final saved payload
- GET /analyses lists recent analyses
- POST /knowledge-base/upload ingests JSON or JSONL payloads into the knowledge base
- GET /health provides a readiness check

Important contract details:

- AnalyzeRequest requires a non-empty document and optional document_name
- AnalyzeResponse returns analysis_id and status
- AnalysisPayloadResponse exposes the canonical payload with summary, requirements, findings, and compatibility fields such as pipeline_outputs

### backend/src/agents/graph.py

This file contains both graph assembly and final response shaping.

The final report formatter is the most important production output contract. It consolidates:

- summary
- requirements
- findings with grouped safety, inconsistencies, and gaps
- pipeline_outputs retained for backward compatibility
- node_trace optional debugging data when requested

This file intentionally keeps the schema clear for clients while preserving older fields already used elsewhere in the repo.

### backend/src/db.py

This layer is responsible for database initialization and persistence.

Key points:

- SQLite is used by default for local dev
- PostgreSQL is used in the Docker stack
- fallback logic exists for SQLite when Postgres is unavailable or not configured
- tables include analysis_records, requirement_embeddings, and requirement_links
- session_scope ensures atomic DB transactions for analysis writes

### backend/src/llm/client.py

This file acts as the system boundary for LLM access.

Responsibilities:

- loads OPENROUTER_API_KEY from the env file
- creates the OpenAI-compatible client
- retries transient failures via tenacity
- parses JSON responses and raises JSONParsingException on malformed output
- falls back to a secondary model when needed
- provides local embedding generation using transformers as a fallback path

The critical design choice here is that the app prefers strict schema compliance over loose parsing. Broken LLM output is repaired, not silently accepted.

### backend/src/llm/prompts.py

This file centralizes the prompt contracts. It is essential for keeping the LLM aligned to the project’s real requirements.

The classifier prompt explicitly enforces:

- evaluate every requirement
- preserve IDs and list order
- return a result for each requirement
- do not omit safety-relevant items

This is the key guard against zero-safety-classification in production.

---

## Agent Graph and Execution Model

The graph is constructed in backend/src/agents/graph.py using stateful node execution.

The operational flow is:

1. extract_requirements_node
2. classify_requirements_node
3. retrieve_context_node
4. assess_safety_levels_node
5. detect_inconsistencies_node
6. detect_gaps_node
7. generate_report_node

On malformed JSON output from any LLM-backed node, the graph can route to a repair node to recover the contract. This was intentionally added to improve reliability without hiding the root cause from the product team.

---

## Report Response Contract

The API response contract is intentionally structured to be clear for clients while remaining compatible with the older report keys.

### Canonical response fields

- id
- status
- report_status
- document
- meta
- summary
- requirements
- findings
- pipeline_outputs
- error_message
- created_at
- updated_at

### findings section

The unified findings payload is the client-friendly summary layer:

```json
"findings": {
  "inconsistencies": [
    { "id": "INC-1", "type": "conflict", "severity": "HIGH", "affected_ids": ["REQ-A", "REQ-B"], "description": "...", "suggested_action": "..." }
  ],
  "gaps": [
    { "id": "GAP-1", "type": "missing_traceability", "priority": "MEDIUM", "affected_id": "REQ-C", "description": "...", "suggested_action": "..." }
  ]
}
```

Safety details are strictly inline per requirement (`requirements[].safety`). The `findings.safety` bucket and per-finding `affected_req_text`/`affected_req_texts` duplicates are intentionally omitted.

### Per-requirement safety metadata with similar requirements

Each safety-relevant requirement carries an assessment plus the top-N most similar knowledge-base requirements (default 5) with their metadata:

```json
"requirements": [
  {
    "id": "REQ-SAF-001",
    "text": "...",
    "domain": "SAFETY",
    "safety": {
      "is_relevant": true,
      "reason": "...",
      "assessment": {
        "exposure": "E4",
        "severity": "S3",
        "controllability": "C2",
        "suggested_asil": "ASIL_C",
        "rationale": "..."
      },
      "retrieved_requirements": [
        {
          "req_id": "KB-0123",
          "req_text": "...",
          "domain": "SAFETY",
          "asil": "ASIL_C",
          "reasoning": "...",
          "score": 0.91
        }
      ]
    }
  }
]
```

The `retrieved_requirements` list is populated from the knowledge-base retriever (`retrieve_context_node`), which uses hybrid BM25 + dense search over the ingested `iso26262-automotive-safety-requirements` style datasets. ASIL values are normalized to ISO 26262 standard strings (`QM`, `ASIL_A`–`ASIL_D`).

### Backward-compatible fields

The response schema is defined by typed Pydantic models in `backend/src/schemas.py` (`AnalysisPayloadResponse`). `ConfigDict(extra="allow")` preserves any additional fields for older consumers during migration.

---

## API examples

### POST /analyze

Request:

```json
{
  "document": "REQ-SYS-001 The system shall ...",
  "document_name": "my_requirements.txt"
}
```

Response:

```json
{
  "analysis_id": 7,
  "status": "PENDING"
}
```

### GET /analyses/{analysis_id}

Response includes the full normalized report, including grouped findings and per-requirement safety metadata.

---

## Docker deployment

The root Docker Compose file defines a production-style deployment with:

- PostgreSQL service
- backend service with port mapping 8081:8000
- env file for secrets
- health checks
- named volumes for persistence

Runtime entrypoint:

```bash
docker compose up -d --build
```

The app is then available at:

```text
http://localhost:8081
```

---

## Database design

The app stores analysis metadata, safety outputs, and retrieval knowledge. The key production patterns are:

- AnalysisRecord stores document input and the final report JSON
- RequirementEmbedding stores retrieval artifacts and domain metadata
- RequirementLink stores relationship edges between requirements

This supports both analysis persistence and future retrieval quality improvements.

---

## Reliability assumptions and constraints

The implementation is intentionally built around product correctness rather than heuristics.

- The classifier prompt requires full coverage of all requirements.
- The LLM output is parsed strictly and repaired when malformed.
- Safety findings are not synthesized from weak rules; they come from the model contract and the requirement set.
- Output structure is normalized before being saved and exposed via the API.

This is a deliberate tradeoff: slightly more prompt discipline, but far more trustworthy safety reporting.

---

## Local testing and verification

Typical validation flow:

```bash
python -m pytest tests/unit -q
```

Example API submission:

```bash
python request.py
```

This exercises the actual analysis lifecycle against the running service, including polling the status endpoint and retrieving the final result.

---

## Summary

The repository is best understood as a production-facing automotive requirements intelligence platform. It combines:

- deterministic extraction
- LLM classification and safety reasoning
- retrieval-supported context enrichment
- validation for inconsistencies and gaps
- persistent analysis storage
- a service API with a clean, report-oriented JSON contract

The most important production artifact is not just the model output, but the stable API payload that downstream systems can trust.
