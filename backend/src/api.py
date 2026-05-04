from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .agents.graph import build_agent
from .agents.state import AgentState
from .db import AnalysisRecord, get_db, init_db

agent = build_agent()


class AnalyzeRequest(BaseModel):
    document: str = Field(..., min_length=1, description="Raw requirements document content")
    document_name: str = Field(
        default="Untitled Requirements Document",
        min_length=1,
        description="Human-readable document name",
    )


class AnalyzeResponse(BaseModel):
    analysis_id: int
    report: dict[str, Any]


class AnalysisSummaryResponse(BaseModel):
    id: int
    document_name: str
    created_at: Any


def build_initial_state(payload: AnalyzeRequest) -> AgentState:
    return {
        "raw_document": payload.document,
        "document_name": payload.document_name,
        "requirements": [],
        "classified": [],
        "safety_assessments": [],
        "inconsistencies": [],
        "gaps": [],
        "report": None,
        "audit_log": [],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Requirements Intelligence Agent API",
    description="FastAPI service for engineering requirements analysis and report persistence.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_document(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    final_state = agent.invoke(build_initial_state(payload))
    report = final_state.get("report")

    if report is None:
        raise HTTPException(status_code=500, detail="Agent did not produce a report.")

    record = AnalysisRecord(
        document_name=payload.document_name,
        raw_document=payload.document,
        report=report,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return AnalyzeResponse(analysis_id=record.id, report=report)


@app.get("/analyses", response_model=list[AnalysisSummaryResponse])
def list_analyses(db: Session = Depends(get_db)) -> list[AnalysisSummaryResponse]:
    records = (
        db.query(AnalysisRecord)
        .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
        .all()
    )

    return [
        AnalysisSummaryResponse(
            id=record.id,
            document_name=record.document_name,
            created_at=record.created_at,
        )
        for record in records
    ]


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == analysis_id).first()

    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    return {
        "id": record.id,
        "document_name": record.document_name,
        "raw_document": record.raw_document,
        "report": record.report,
        "created_at": record.created_at,
    }
