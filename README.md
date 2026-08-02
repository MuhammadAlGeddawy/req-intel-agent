# Engineering Requirements Intelligence Agent

Production-ready automotive requirements analysis service built around a LangGraph pipeline, FastAPI API, and OpenRouter-backed LLM workflows.

## Overview

This project turns raw engineering requirement text into a structured safety and traceability assessment. It:

- extracts requirement statements from a document
- classifies each requirement as safety-relevant or not
- retrieves historical context using hybrid retrieval
- suggests ISO 26262 ASIL values for safety-relevant items
- finds requirement inconsistencies and traceability gaps
- persists analysis records in a relational database
- exposes the workflow via a FastAPI service and Docker deployment

The production pipeline is designed for automotive engineering teams who need a reproducible, auditable way to screen requirement sets for safety-impacting content.

---

## Production Architecture

```text
Document input
   ↓
Extract requirements
   ↓
Classify safety relevance
   ↓
Retrieve historical context
   ↓
Assess ASIL / hazardous event exposure
   ↓
Detect inconsistencies
   ↓
Detect traceability gaps
   ↓
Generate final report
```

The current implementation centers around:

- FastAPI service in backend/src/api.py
- graph orchestration in backend/src/agents/graph.py
- LLM integration in backend/src/llm/client.py
- prompt contracts in backend/src/llm/prompts.py
- persistence in backend/src/db.py
- Docker runtime in docker-compose.yaml and backend/Dockerfile

---

## Core Production Files

- backend/src/api.py — FastAPI endpoints and DB-backed analysis lifecycle
- backend/src/agents/graph.py — final report formatter and LangGraph orchestration
- backend/src/agents/state.py — agent state schema
- backend/src/agents/nodes/extractor.py — requirement extraction node
- backend/src/agents/nodes/classifier.py — safety relevance classification
- backend/src/agents/nodes/retriever_node.py — retrieval and context augmentation
- backend/src/agents/nodes/safety.py — ASIL and risk assessment
- backend/src/agents/nodes/validator.py — inconsistency and gap detection
- backend/src/llm/client.py — OpenRouter client, retry handling, JSON parsing, embedding generation
- backend/src/llm/prompts.py — classification and safety assessment prompt definitions
- backend/src/db.py — SQLite/Postgres session management and models
- backend/src/utils/parsers.py — regex-based document extraction
- backend/src/utils/retriever.py — hybrid retrieval logic
- request.py — example client for local or Docker testing

---

## Runtime Stack

- Python 3.11 in Docker
- FastAPI for API surface
- SQLAlchemy for persistence
- PostgreSQL in Docker for production-style storage, with SQLite fallback support
- LangGraph for stateful orchestration
- OpenRouter + OpenAI-compatible client for LLM execution
- sentence-transformers + transformers for local embeddings fallback

---

## Configuration

Required runtime configuration is driven by environment variables and the Docker env file.

### Local environment

Create a file at backend/config/.env or copy the example template if available.

```env
OPENROUTER_API_KEY=your_key_here
DATABASE_URL=sqlite:///./requirements_agent.db
```

For Docker, the compose setup reads the same env file and passes PostgreSQL connection values for the service container.

---

## Docker Setup

The project is configured to run with Docker Compose from the repository root:

```bash
docker compose up -d --build
```

The services are:

- agent-service: FastAPI backend
- postgres: PostgreSQL database

The app is exposed on:

- http://localhost:8081

Health check:

- GET /health

---

## Running the API

### Local development

```bash
cd backend
uvicorn src.api:app --reload
```

### Docker

```bash
docker compose up -d --build
```

---

## API Contract

### POST /analyze

Creates an analysis job asynchronously.

Request body:

```json
{
  "document": "REQ-SYS-001 The system shall ...",
  "document_name": "example_requirements.txt"
}
```

Response:

```json
{
  "analysis_id": 7,
  "status": "PENDING"
}
```

Status code: 202 Accepted

### GET /analyses/{analysis_id}/status

Returns the job status.

```json
{
  "analysis_id": 7,
  "status": "COMPLETED",
  "error_message": null
}
```

### GET /analyses/{analysis_id}

Returns the stored analysis payload.

The canonical response body contains these sections:

- document
- meta
- summary
- requirements
- findings
- pipeline_outputs
- optional node_trace

Example structure:

```json
{
  "id": 7,
  "status": "COMPLETED",
  "report_status": "COMPLETED",
  "document": {
    "id": 7,
    "name": "Demo",
    "version": "1.0.0",
    "classification": "Internal"
  },
  "meta": {
    "model": "qwen/qwen-2.5-7b-instruct",
    "agent_version": "1.0.0",
    "processed_at": "2026-08-01T00:00:00",
    "human_review_required": true
  },
  "summary": {
    "total_requirements": 2,
    "safety_relevant_count": 1,
    "inconsistencies_count": 1,
    "gaps_count": 1,
    "domain_breakdown": {
      "SYSTEM": 1,
      "HARDWARE": 0,
      "SOFTWARE": 0,
      "SAFETY": 1,
      "TEST": 0
    }
  },
  "requirements": [
    {
      "id": "REQ-1",
      "domain": "SAFETY",
      "text": "Brake shall enter fail-safe state if CAN bus is lost.",
      "safety": {
        "is_relevant": true,
        "reason": "Handles safe state",
        "assessment": {
          "exposure": "E1",
          "severity": "S2",
          "controllability": "C2",
          "rationale": "Loss of braking is hazardous",
          "suggested_asil": "ASIL-B"
        }
      }
    }
  ],
  "findings": {
    "safety": {
      "count": 1,
      "items": [
        {
          "id": "REQ-1",
          "is_relevant": true,
          "reason": "Handles safe state",
          "assessment": {
            "exposure": "E1",
            "severity": "S2",
            "controllability": "C2",
            "rationale": "Loss of braking is hazardous",
            "suggested_asil": "ASIL-B"
          }
        }
      ]
    },
    "inconsistencies": [
      {
        "id": "INC-1",
        "type": "conflict",
        "severity": "HIGH",
        "affected_ids": ["REQ-1", "REQ-2"],
        "description": "Safety and non-safety requirements conflict by priority"
      }
    ],
    "gaps": [
      {
        "id": "GAP-1",
        "type": "missing_traceability",
        "priority": "HIGH",
        "affected_id": "REQ-1",
        "description": "No verification trace for brake fail-safe path"
      }
    ]
  },
  "pipeline_outputs": {
    "1_extraction_and_classification": {},
    "2_safety_assessment": {},
    "3_inconsistency_detection": {},
    "4_traceability_gap_analysis": {}
  },
  "error_message": null
}
```

This contract is designed to be clear for API consumers while keeping the legacy pipeline output fields intact for compatibility.

---

## Database Model

The persistence layer stores analysis metadata and retrieval knowledge. The key production patterns are:

- AnalysisRecord stores document input and the final report JSON
- RequirementEmbedding stores retrieval artifacts and domain metadata
- RequirementLink stores relationship edges between requirements

This supports analysis persistence and future retrieval quality improvements.

---

## Reliability Notes

The production code avoids heuristic shortcuts for safety classification. The classifier prompt requires full evaluation of each requirement, preserving IDs and order, so the model cannot silently drop safety-relevant items.

The graph includes JSON repair fallback paths for malformed LLM responses, but the primary design remains prompt-accurate and contract-driven rather than heuristic-driven.

---

## Validation

Run the unit checks for the classifier and core nodes:

```bash
python -m pytest tests/unit -q
```

The service can also be exercised with the example client:

```bash
python request.py
```

---

## Summary

This repository is a production-oriented requirements intelligence pipeline for engineering and safety review. It combines:

- deterministic extraction
- LLM classification and safety reasoning
- retrieval-supported context enrichment
- validation for inconsistencies and gaps
- persistent analysis storage
- a service API with a clear report-oriented JSON contract

The most important production artifact is not just the model output, but the stable API payload that downstream systems can trust.
