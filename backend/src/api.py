import json
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .agents.graph import build_agent
from .agents.state import AgentState
from .db import AnalysisRecord, AnalysisStatus, RequirementEmbedding, RequirementLink, get_db, init_db, session_scope
from .llm.client import get_embeddings
from .schemas import (
    AnalysisPayloadResponse,
    AnalysisSummaryResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    StatusResponse,
)
from .utils.retriever import hybrid_search_and_rerank

agent = build_agent()

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "SYSTEM": ["system", "architecture", "platform", "communication", "latency", "response time"],
    "HARDWARE": ["hardware", "sensor", "actuator", "led", "motor", "circuit", "voltage", "temperature sensor", "battery", "bms", "power relay"],
    "SOFTWARE": ["software", "algorithm", "firmware", "watchdog", "log", "code", "mc/dc"],
    "SAFETY": ["safety", "asil", "iso 26262", "fail-safe", "hazard", "safe state", "diagnostic coverage"],
    "TEST": ["test", "verification", "validation", "coverage", "simulat"],
}

_DOMAIN_ENTITY_MAP: dict[str, str] = {
    "bms": "HARDWARE",
    "battery": "HARDWARE",
    "eps": "HARDWARE",
    "esc": "HARDWARE",
    "adass": "SOFTWARE",
    "v2x": "SYSTEM",
    "hmi": "SOFTWARE",
    "airbag": "HARDWARE",
    "steering": "HARDWARE",
    "braking": "HARDWARE",
    "thermal": "HARDWARE",
    "sensor fusion": "SOFTWARE",
    "perception": "SOFTWARE",
    "chassis": "HARDWARE",
    "powertrain": "HARDWARE",
    "body electronics": "HARDWARE",
    "domain controller": "HARDWARE",
    "centralised compute": "SYSTEM",
    "automated parking": "SOFTWARE",
    "automated valet": "SOFTWARE",
}

def _infer_domain(req_text: str) -> str:
    lowered = req_text.lower()
    for entity, domain in _DOMAIN_ENTITY_MAP.items():
        if entity in lowered:
            return domain
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lowered)
        if score > 0:
            scores[domain] = score
    if scores:
        return max(scores, key=scores.get)
    return "SYSTEM"


def build_initial_state(payload: AnalyzeRequest, include_trace: bool = False) -> AgentState:
    return {
        "raw_document": payload.document,
        "document_name": payload.document_name,
        "include_trace": include_trace,
        "requirements": [],
        "classified": [],
        "safety_assessments": [],
        "inconsistencies": [],
        "gaps": [],
        "retrieved_context": {},
        "report": None,
        "audit_log": [],
        "json_repair_needed": None,
        "json_repair_source": None,
        "json_repair_raw": None,
        "json_repair_hint": None,
        "json_repair_attempts": None,
    }


def ingest_knowledge_base_payload(payload: dict[str, Any]) -> dict[str, int]:
    requirements = payload.get("requirements", [])
    links = payload.get("links", [])
    with session_scope() as db:
        for item in requirements:
            req_id = item.get("req_id")
            if not req_id:
                continue
            existing = db.query(RequirementEmbedding).filter(RequirementEmbedding.req_id == req_id).first()
            embedding_value = item.get("embedding") or [0.0] * 1536
            if existing is None:
                db.add(RequirementEmbedding(req_id=req_id, domain=item.get("domain", "UNKNOWN"), req_text=item.get("req_text", ""), asil=item.get("asil"), reasoning=item.get("reasoning"), embedding=embedding_value))
            else:
                existing.domain = item.get("domain", "UNKNOWN")
                existing.req_text = item.get("req_text", "")
                existing.asil = item.get("asil")
                existing.reasoning = item.get("reasoning")
                existing.embedding = embedding_value
                db.add(existing)
        for link in links:
            source_req_id = link.get("source_req_id")
            target_req_id = link.get("target_req_id")
            link_type = link.get("link_type")
            if not source_req_id or not target_req_id or not link_type:
                continue
            existing = db.query(RequirementLink).filter(RequirementLink.source_req_id == source_req_id, RequirementLink.target_req_id == target_req_id, RequirementLink.link_type == link_type).first()
            if existing is None:
                db.add(RequirementLink(source_req_id=source_req_id, target_req_id=target_req_id, link_type=link_type))
    return {"requirements_ingested": len(requirements), "links_ingested": len(links)}


def _ingest_knowledge_base_worker(payload: dict[str, Any]) -> None:
    ingest_knowledge_base_payload(payload)


def run_analysis_task(analysis_id: int, include_trace: bool = False) -> None:
    with session_scope() as db:
        record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()
        if record is None:
            return
        record.status = AnalysisStatus.PROCESSING
        db.add(record)
        raw_document = record.raw_document
        document_name = record.document_name
    try:
        payload = AnalyzeRequest(document=raw_document, document_name=document_name)
        initial_state = build_initial_state(payload, include_trace=include_trace)
        initial_state["analysis_id"] = analysis_id
        final_state = agent.invoke(initial_state)
        report = final_state.get("report")
        with session_scope() as db:
            record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()
            if record is None:
                return
            record.report = report
            record.status = AnalysisStatus.COMPLETED if report is not None else AnalysisStatus.FAILED
            if report is None:
                record.error_message = "Agent did not produce a report."
            else:
                record.error_message = None
            db.add(record)
    except Exception as exc:
        with session_scope() as db:
            record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()
            if record is None:
                return
            record.status = AnalysisStatus.FAILED
            record.error_message = str(exc)
            db.add(record)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Requirements Intelligence Agent API", description="FastAPI service for engineering requirements analysis and report persistence.", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def analyze_document(payload: AnalyzeRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> AnalyzeResponse:
    record = AnalysisRecord(document_name=payload.document_name, raw_document=payload.document, status=AnalysisStatus.PENDING)
    db.add(record)
    db.commit()
    db.refresh(record)
    background_tasks.add_task(run_analysis_task, record.id)
    return AnalyzeResponse(analysis_id=record.id, status=record.status)


def _parse_chatml_jsonl_line(line: str, index: int) -> dict[str, Any] | None:
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None
    messages = item.get("messages", [])
    if len(messages) < 3:
        return None
    user_msg = None
    for m in messages:
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break
    if not user_msg:
        return None
    req_text = user_msg.split("Analyze this safety requirement:")[-1].strip()
    if not req_text:
        return None
    assistant_msg = None
    for m in messages:
        if m.get("role") == "assistant":
            assistant_msg = m.get("content", "")
            break
    asil = None
    reasoning = None
    if assistant_msg:
        try:
            analysis = json.loads(assistant_msg)
            asil = analysis.get("asil", "QM")
            if asil and asil.startswith("ASIL "):
                asil = asil.replace("ASIL ", "")
            reasoning = analysis.get("reasoning", "")
        except json.JSONDecodeError:
            pass
    req_id = f"REQ-GEN-{index:04d}"
    domain = _infer_domain(req_text)
    return {"req_id": req_id, "domain": domain, "req_text": req_text, "asil": asil, "reasoning": reasoning}


def _process_jsonl_upload(content: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    skipped = 0
    for idx, line in enumerate(lines):
        record = _parse_chatml_jsonl_line(line, idx)
        if record is None:
            skipped += 1
        else:
            records.append(record)
    if skipped:
        print(f"  Skipped {skipped} unparseable lines in JSONL file.")
    return records


def _generate_embeddings_for_records(records: list[dict[str, Any]]) -> None:
    texts_to_embed = []
    texts_indices = []
    for idx, record in enumerate(records):
        if not record.get("embedding"):
            texts_to_embed.append(record["req_text"])
            texts_indices.append(idx)
    if texts_to_embed:
        try:
            embeddings = get_embeddings(texts_to_embed)
            for i, idx in enumerate(texts_indices):
                if i < len(embeddings) and embeddings[i]:
                    records[idx]["embedding"] = [float(v) for v in embeddings[i]]
        except Exception as exc:
            print(f"  Embedding generation failed for some records: {exc}")
            for idx in texts_indices:
                records[idx]["embedding"] = [0.0] * 1536


@app.post("/knowledge-base/upload", status_code=202)
def upload_knowledge_base(uploaded_file: UploadFile = File(...), background_tasks: BackgroundTasks = None) -> dict[str, Any]:
    if not uploaded_file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    ext = uploaded_file.filename.lower().rsplit(".", 1)[-1] if "." in uploaded_file.filename else ""
    if ext not in {"json", "jsonl"}:
        raise HTTPException(status_code=400, detail="Expected a .json or .jsonl file upload.")
    try:
        content = uploaded_file.file.read().decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc
    if ext == "jsonl":
        records = _process_jsonl_upload(content)
        if not records:
            raise HTTPException(status_code=400, detail="Could not parse any valid requirement from the JSONL file.")
        _generate_embeddings_for_records(records)
        payload = {"requirements": records, "links": []}
        def _jsonl_worker(p: dict[str, Any]) -> None:
            print(f"  Ingesting {len(p['requirements'])} requirements from JSONL dataset...")
            ingest_knowledge_base_payload(p)
        if background_tasks is not None:
            background_tasks.add_task(_jsonl_worker, payload)
        else:
            _jsonl_worker(payload)
        return {"status": "accepted", "filename": uploaded_file.filename, "format": "jsonl_chatml", "requirements_parsed": len(records)}
    try:
        payload = json.loads(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc
    if background_tasks is not None:
        background_tasks.add_task(_ingest_knowledge_base_worker, payload)
    else:
        _ingest_knowledge_base_worker(payload)
    return {"status": "accepted", "filename": uploaded_file.filename, "format": "json", "requirements": len(payload.get("requirements", []))}


@app.get("/analyses", response_model=list[AnalysisSummaryResponse])
def list_analyses(db: Session = Depends(get_db)) -> list[AnalysisSummaryResponse]:
    records = db.query(AnalysisRecord).order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc()).all()
    return [AnalysisSummaryResponse(id=r.id, document_name=r.document_name, status=r.status, created_at=r.created_at) for r in records]


@app.get("/analyses/{analysis_id}/status", response_model=StatusResponse)
def analysis_status(analysis_id: int, db: Session = Depends(get_db)) -> StatusResponse:
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return StatusResponse(analysis_id=record.id, status=record.status, error_message=record.error_message)


def _coerce_report_payload(report: dict[str, Any] | None) -> dict[str, Any]:
    """Map a stored report (new or legacy) to the canonical analysis payload.

    Legacy reports used ``issues`` with ``inconsistencies`` and
    ``traceability_gaps``. New reports use ``findings`` with ``inconsistencies``
    and ``gaps``. This helper normalizes both into the target schema so older
    persisted records remain consumable.
    """
    if not report:
        return {}

    # Normalize findings: prefer new structure, fall back to legacy issues block.
    findings = report.get("findings")
    if not isinstance(findings, dict):
        issues = report.get("issues") or {}
        findings = {
            "inconsistencies": issues.get("inconsistencies", []),
            "gaps": issues.get("traceability_gaps", []),
        }

    # Strip any duplicate safety bucket from findings (safety belongs in requirements).
    if isinstance(findings, dict):
        findings = {k: v for k, v in findings.items() if k != "safety"}

    # Strip redundant per-finding requirement text payloads (frontend resolves via IDs).
    inconsistencies = [
        {k: v for k, v in inc.items() if k != "affected_req_texts"}
        for inc in (findings.get("inconsistencies") or [])
        if isinstance(inc, dict)
    ]
    gaps = [
        {k: v for k, v in g.items() if k != "affected_req_text"}
        for g in (findings.get("gaps") or [])
        if isinstance(g, dict)
    ]
    findings = {"inconsistencies": inconsistencies, "gaps": gaps}

    payload = {
        "document": report.get("document"),
        "meta": report.get("meta"),
        "summary": report.get("summary"),
        "requirements": report.get("requirements"),
        "findings": findings,
        "node_trace": report.get("node_trace"),
    }
    return payload


@app.get("/analyses/{analysis_id}", response_model=AnalysisPayloadResponse)
def get_analysis(
    analysis_id: int,
    include_trace: bool = False,
    include_raw: bool = False,
    db: Session = Depends(get_db),
) -> AnalysisPayloadResponse:
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    report = record.report if record.status == AnalysisStatus.COMPLETED else None
    payload = _coerce_report_payload(report)

    meta = dict(payload.get("meta") or {})
    if getattr(record, "created_at", None) is not None:
        meta["created_at"] = record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else record.created_at
    if getattr(record, "updated_at", None) is not None:
        meta["updated_at"] = record.updated_at.isoformat() if hasattr(record.updated_at, "isoformat") else record.updated_at
    if "processed_at" in meta:
        del meta["processed_at"]
    payload["meta"] = meta

    return AnalysisPayloadResponse(
        id=record.id,
        status=record.status,
        error_message=record.error_message,
        document=payload.get("document") or {},
        meta=payload.get("meta") or {},
        summary=payload.get("summary") or {},
        requirements=payload.get("requirements") or [],
        findings=payload.get("findings") or {"inconsistencies": [], "gaps": []},
        node_trace=payload.get("node_trace") if report and include_trace else None,
    )
