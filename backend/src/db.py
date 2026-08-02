import os
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import JSON, Column, DateTime, Enum as SQLEnum, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

# pgvector is optional at import-time (tests/local may run without Postgres)
try:  # pragma: no cover
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover
    Vector = None


try:
    from sqlalchemy.engine import reflection
except ImportError:  # pragma: no cover
    reflection = None

ENV_PATH = Path(__file__).resolve().parents[1] / "config" / ".env"
load_dotenv(dotenv_path=ENV_PATH)

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_URL = os.getenv("DATABASE_URL")
FALLBACK_TO_SQLITE = os.getenv("DB_FALLBACK_TO_SQLITE", "false").lower() in {"1", "true", "yes", "on"}

if not DATABASE_URL:
    if POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_DB:
        DATABASE_URL = (
            f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
            f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )
    else:
        DATABASE_URL = "sqlite:///./requirements_agent.db"


def _build_engine(url: str):
    # For SQLite on Windows, pooled connections can keep the DB file locked.
    # Use NullPool to avoid background connections and allow temp DB cleanup.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}

    engine_kwargs = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }

    if url.startswith("sqlite"):
        try:
            from sqlalchemy.pool import NullPool

            engine_kwargs["poolclass"] = NullPool
        except Exception:
            # Fallback: still use sqlite connect args.
            pass
    else:
        engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

    return create_engine(url, **engine_kwargs)



engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _dispose_engine() -> None:
    """Dispose SQLAlchemy engine to release file handles (important on Windows)."""
    global engine, SessionLocal
    try:
        engine.dispose()
    except Exception:
        pass
    # Re-bind SessionLocal to the current engine instance.
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



# ─── Knowledge Base Tables (Postgres + pgvector) ─────────────────────────────
# These models are required for RAG retrieval and historical context.
# If pgvector is not available (local/dev), Vector will be None and the models
# can still be imported; migrations/DB creation will be skipped for vector-specific parts.


class RequirementEmbedding(Base):
    __tablename__ = "requirement_embeddings"

    id = Column(Integer, primary_key=True, index=True)

    analysis_record_id = Column(
        Integer,
        # Nullable to support standalone synthetic data injections.
        nullable=True,
    )


    req_id = Column(String(50), unique=True, index=True, nullable=False)
    domain = Column(String(20), nullable=False)
    req_text = Column(Text, nullable=False)
    asil = Column(String(5), nullable=True)
    reasoning = Column(Text, nullable=True)

    if Vector is not None and DATABASE_URL.startswith("postgres"):
        embedding = Column(Vector(1536), nullable=False)
    else:  # pragma: no cover
        embedding = Column(JSON, nullable=False)


class RequirementLink(Base):
    __tablename__ = "requirement_links"

    id = Column(Integer, primary_key=True, index=True)

    source_req_id = Column(String(50), index=True, nullable=False)
    target_req_id = Column(String(50), index=True, nullable=False)
    link_type = Column(String(30), nullable=False)

    # Prevent duplicate edges
    from sqlalchemy import UniqueConstraint

    __table_args__ = (
        UniqueConstraint("source_req_id", "target_req_id", "link_type", name="uq_requirement_links_edge"),
    )


class AnalysisStatus(str, Enum):

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    document_name = Column(String(255), nullable=False, index=True)
    raw_document = Column(Text, nullable=False)
    report_type = JSONB().with_variant(JSON, "sqlite") if DATABASE_URL.startswith("postgresql") else JSON
    report = Column(report_type, nullable=True)
    status = Column(SQLEnum(AnalysisStatus, name="analysis_status"), nullable=False, server_default=AnalysisStatus.PENDING.value)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


def _ensure_sqlite_schema() -> None:
    if not str(engine.url).startswith("sqlite"):
        return

    sqlite_path = Path(engine.url.database or ":memory:")
    if str(sqlite_path) == ":memory:":
        Base.metadata.create_all(bind=engine)
        return

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if not sqlite_path.exists():
        Base.metadata.create_all(bind=engine)
        return

    inspector = reflection.Inspector.from_engine(engine)
    existing_columns = {col["name"] for col in inspector.get_columns("analysis_records")}
    if "status" in existing_columns:
        Base.metadata.create_all(bind=engine)
        return

    with engine.begin() as connection:
        if "status" not in existing_columns:
            connection.execute(text("ALTER TABLE analysis_records ADD COLUMN status VARCHAR(20)"))
        if "error_message" not in existing_columns:
            connection.execute(text("ALTER TABLE analysis_records ADD COLUMN error_message TEXT"))
        if "updated_at" not in existing_columns:
            connection.execute(text("ALTER TABLE analysis_records ADD COLUMN updated_at DATETIME"))

    Base.metadata.create_all(bind=engine)


def init_db() -> None:
    global DATABASE_URL, engine, SessionLocal

    # Tests often patch DATABASE_URL to a temporary sqlite file.
    # Re-create the engine for the patched DATABASE_URL to avoid Windows file locking.

    # Release any previous engine connections before re-creating.
    try:
        _dispose_engine()
    except Exception:
        pass

    engine = _build_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    if DATABASE_URL.startswith("postgres") and FALLBACK_TO_SQLITE:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except OperationalError:
            sqlite_path = os.getenv(
                "SQLITE_PATH",
                str(Path(__file__).resolve().parents[1] / "requirements_agent.db"),
            )
            DATABASE_URL = f"sqlite:///{sqlite_path}"
            engine = _build_engine(DATABASE_URL)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


    # Postgres-only: initialize pgvector extension before table creation.
    if DATABASE_URL.startswith("postgres"):
        try:
            with engine.connect() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                connection.commit()
        except Exception:
            # If pgvector extension or vector types are unavailable, we still create non-vector tables.
            pass

    # If pgvector is available, ensure HNSW/cosine indexes are created via metadata.
    # (pgvector's Vector + index should be declared in the model. We add the index
    # in the next iteration when Vector is fully available.)


    _ensure_sqlite_schema()
    Base.metadata.create_all(bind=engine)



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
