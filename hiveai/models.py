import os
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    Float, Boolean, ForeignKey, JSON, Index, event as sa_event
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import text
from hiveai.config import DATABASE_URL, DB_BACKEND, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE, HNSW_EF_SEARCH

logger = logging.getLogger(__name__)

Base = declarative_base()

if DB_BACKEND == "postgresql":
    from pgvector.sqlalchemy import Vector
    _engine_kwargs = {
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_recycle": DB_POOL_RECYCLE,
        "pool_pre_ping": True,
    }
    if os.environ.get("DB_SSL_MODE"):
        _engine_kwargs["connect_args"] = {"sslmode": os.environ.get("DB_SSL_MODE", "require")}
    engine = create_engine(DATABASE_URL, **_engine_kwargs)

    @sa_event.listens_for(engine, "connect")
    def set_hnsw_ef_search(dbapi_conn, connection_record):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("SET hnsw.ef_search = %s", (HNSW_EF_SEARCH,))
            cursor.close()
        except Exception:
            pass
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow():
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    topic = Column(Text, nullable=False)
    status = Column(String(50), default="queued")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    hive_ping_count = Column(Integer, default=0)
    crawl_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    triple_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    golden_book_id = Column(Integer, ForeignKey("golden_books.id"), nullable=True)

    crawled_pages = relationship("CrawledPage", back_populates="job")
    chunks = relationship("Chunk", back_populates="job")
    triples = relationship("GraphTriple", back_populates="job")

    __table_args__ = (
        Index("ix_jobs_status", "status"),
    )


class CrawledPage(Base):
    __tablename__ = "crawled_pages"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    url = Column(String(2000), nullable=False)
    title = Column(String(500), nullable=True)
    raw_content = Column(Text, nullable=True)
    cleaned_markdown = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    source_type = Column(String(50), default="web")
    crawled_at = Column(DateTime, default=utcnow)
    from_hive = Column(Boolean, default=False)

    job = relationship("Job", back_populates="crawled_pages")
    chunks = relationship("Chunk", back_populates="page")

    __table_args__ = (
        Index("ix_crawled_pages_url", "url"),
        Index("ix_crawled_pages_hash", "content_hash"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    page_id = Column(Integer, ForeignKey("crawled_pages.id"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    embedding = Column(JSON, nullable=True)

    job = relationship("Job", back_populates="chunks")
    page = relationship("CrawledPage", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_job_id", "job_id"),
        Index("ix_chunks_page_id", "page_id"),
    )


class GraphTriple(Base):
    __tablename__ = "graph_triples"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    subject = Column(String(500), nullable=False)
    predicate = Column(String(200), nullable=False)
    obj = Column(String(500), nullable=False)
    confidence = Column(Float, default=1.0)
    source_chunk_id = Column(Integer, ForeignKey("chunks.id"), nullable=True)
    source_url = Column(String(2000), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    job = relationship("Job", back_populates="triples")

    __table_args__ = (
        Index("ix_triples_subject", "subject"),
        Index("ix_triples_predicate", "predicate"),
        Index("ix_triples_job_id", "job_id"),
    )


class GoldenBook(Base):
    __tablename__ = "golden_books"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    source_count = Column(Integer, default=0)
    source_urls = Column(JSON, default=lambda: [])
    triple_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=utcnow)
    published_at = Column(DateTime, nullable=True)
    hive_permlink = Column(String(255), nullable=True)
    hive_author = Column(String(50), nullable=True)
    hive_tx_id = Column(String(64), nullable=True)
    quality_score = Column(Float, nullable=True)
    quality_details = Column(JSON, nullable=True)
    needs_rewrite = Column(Boolean, default=False)
    compressed_content = Column(Text, nullable=True)

    sections = relationship("BookSection", back_populates="book", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_golden_books_status", "status"),
        Index("ix_golden_books_quality", "quality_score"),
    )


class BookReference(Base):
    __tablename__ = "book_references"

    id = Column(Integer, primary_key=True)
    from_book_id = Column(Integer, ForeignKey("golden_books.id", ondelete="CASCADE"), nullable=False)
    to_book_id = Column(Integer, ForeignKey("golden_books.id", ondelete="CASCADE"), nullable=False)
    reference_context = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    from_book = relationship("GoldenBook", foreign_keys=[from_book_id])
    to_book = relationship("GoldenBook", foreign_keys=[to_book_id])

    __table_args__ = (
        Index("ix_book_refs_from", "from_book_id"),
        Index("ix_book_refs_to", "to_book_id"),
    )


class Community(Base):
    __tablename__ = "communities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    entities = Column(JSON, default=lambda: [])
    triple_count = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_communities_job_id", "job_id"),
    )


class HiveKnown(Base):
    __tablename__ = "hive_known"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    url = Column(String(2000), nullable=False)
    permlink = Column(String(255), nullable=True)
    author = Column(String(50), nullable=True)
    title = Column(String(500), nullable=True)
    content_hash = Column(String(64), nullable=True)
    tags = Column(JSON, default=lambda: [])
    discovered_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_hive_known_url", "url"),
    )


if DB_BACKEND == "postgresql":
    class BookSection(Base):
        __tablename__ = "book_sections"

        id = Column(Integer, primary_key=True)
        book_id = Column(Integer, ForeignKey("golden_books.id", ondelete="CASCADE"), nullable=False)
        header = Column(String(500), nullable=False)
        content = Column(Text, nullable=False)
        token_count = Column(Integer, default=0)
        embedding = Column(Vector(1024), nullable=True)
        keywords_json = Column(Text, nullable=True)  # JSON array of extracted keywords
        created_at = Column(DateTime, default=utcnow)

        book = relationship("GoldenBook", back_populates="sections")

        __table_args__ = (
            Index("ix_book_sections_book_id", "book_id"),
            Index("ix_book_sections_embedding_hnsw", "embedding",
                  postgresql_using="hnsw",
                  postgresql_with={"m": 16, "ef_construction": 64},
                  postgresql_ops={"embedding": "vector_cosine_ops"}),
        )

        @property
        def keywords(self):
            if self.keywords_json:
                return json.loads(self.keywords_json)
            return []
else:
    class BookSection(Base):
        __tablename__ = "book_sections"

        id = Column(Integer, primary_key=True)
        book_id = Column(Integer, ForeignKey("golden_books.id", ondelete="CASCADE"), nullable=False)
        header = Column(String(500), nullable=False)
        content = Column(Text, nullable=False)
        token_count = Column(Integer, default=0)
        embedding_json = Column(Text, nullable=True)
        keywords_json = Column(Text, nullable=True)  # JSON array of extracted keywords
        created_at = Column(DateTime, default=utcnow)

        book = relationship("GoldenBook", back_populates="sections")

        __table_args__ = (
            Index("ix_book_sections_book_id", "book_id"),
        )

        @property
        def embedding(self):
            if self.embedding_json is None:
                return None
            try:
                return json.loads(self.embedding_json)
            except (json.JSONDecodeError, TypeError):
                return None

        @embedding.setter
        def embedding(self, value):
            if value is None:
                self.embedding_json = None
            elif isinstance(value, (list, tuple)):
                self.embedding_json = json.dumps([float(v) for v in value])
            elif hasattr(value, 'tolist'):
                self.embedding_json = json.dumps(value.tolist())
            else:
                self.embedding_json = json.dumps(value)

        @property
        def keywords(self):
            if self.keywords_json:
                return json.loads(self.keywords_json)
            return []


class TrainingPair(Base):
    __tablename__ = "training_pairs"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)     # "self_distill" | "web_crawl" | "human_verified" | "auto_verified"
    topic = Column(String(500), nullable=True)
    instruction = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)    # 1024-dim floats, JSON-serialized
    quality = Column(Float, default=0.0)
    is_eligible = Column(Boolean, default=False)
    lora_version = Column(Integer, nullable=True)   # set when used in a training run
    metadata_json = Column(Text, nullable=True)     # JSON blob for refinement trajectories, DPO data, etc.
    created_at = Column(DateTime, default=utcnow)

    # Recurrence tracking (v1 skill buffer)
    recurrence_count = Column(Integer, default=1)     # how many times similar question seen
    last_seen_at = Column(DateTime, nullable=True)    # last time a similar question was asked

    __table_args__ = (
        Index("ix_training_pairs_source", "source"),
        Index("ix_training_pairs_eligible", "is_eligible"),
        Index("ix_training_pairs_topic", "topic"),
    )

    @property
    def embedding(self):
        if self.embedding_json is None:
            return None
        try:
            return json.loads(self.embedding_json)
        except (json.JSONDecodeError, TypeError):
            return None

    @embedding.setter
    def embedding(self, value):
        if value is None:
            self.embedding_json = None
        elif isinstance(value, (list, tuple)):
            self.embedding_json = json.dumps([float(v) for v in value])
        elif hasattr(value, "tolist"):
            self.embedding_json = json.dumps(value.tolist())
        else:
            self.embedding_json = json.dumps(value)


class LoraVersion(Base):
    __tablename__ = "lora_versions"

    id = Column(Integer, primary_key=True)
    version = Column(String(50), nullable=False)    # "v1.0", "v1.1", etc.
    base_model = Column(String(100), nullable=False)
    pair_count = Column(Integer, default=0)
    benchmark_score = Column(Float, nullable=True)
    adapter_path = Column(String(500), nullable=True)
    status = Column(String(50), default="pending")  # "training"|"benchmarking"|"ready"|"published"
    hive_tx_id = Column(String(64), nullable=True)
    ipfs_cid = Column(String(128), nullable=True)   # IPFS Content ID for adapter GGUF
    export_metadata = Column(JSON, nullable=True)    # {file_size, sha256, base_model, ...}
    merge_cycle = Column(Integer, default=0)          # which merge cycle this adapter was used in
    merged_base_path = Column(String(500), nullable=True)  # path to merged output base
    parent_version_id = Column(Integer, ForeignKey("lora_versions.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_lora_versions_status", "status"),
    )


class ChatFeedback(Base):
    """User feedback on chat responses — corrections become training pairs."""
    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True)
    message_hash = Column(String(64), nullable=False)   # SHA-256 of user question
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    rating = Column(String(10), nullable=False)         # "up", "down", or "auto"
    correction = Column(Text, nullable=True)            # user's corrected answer
    staged_pair_id = Column(Integer, ForeignKey("training_pairs.id"), nullable=True)
    verification_json = Column(Text, nullable=True)    # sandbox execution results JSON
    auto_staged = Column(Boolean, default=False)       # True if auto-staged (not user feedback)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_chat_feedback_rating", "rating"),
        Index("ix_chat_feedback_hash", "message_hash"),
    )


class ChatSession(Base):
    """Persistent chat session for history search."""
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(200), nullable=True)  # Auto-generated from first message
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual chat message within a session."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(10), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_session", "session_id"),
    )


class TelemetryEvent(Base):
    """Product telemetry for 3-arm memory experiment.

    Arms:
      - treatment       — memory injected + surface shown
      - holdout_surface — memory injected + surface hidden
      - no_injection    — memory NOT injected + surface hidden

    Identity graph:
      - request_id  — one per HTTP request
      - answer_id   — one per response (may differ from request if revised)
      - attempt_id  — one per generation attempt (revised answers get new attempt)

    Design invariants:
      - memory_context_injected != memory_surface_emitted (independent)
      - Writes happen async via background queue (fail-open, never blocks chat)
      - Stack versions stamped on every event (model, git SHA, classifiers, frontend)
      - Client outcome events use state-machine transitions, not blind first-write-wins
      - Explicit acceptance separated from implicit proxies

    Naming honesty:
      - "no_injection" means retrieval still runs (for latent logging) but results
        are stripped from the LLM prompt. It does NOT eliminate retrieval-side
        effects (latency, cache warming, reranker load). This arm isolates
        prompt-level injection effect, not full memory subsystem cost.
    """
    __tablename__ = "telemetry_events"

    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), nullable=False)     # one per HTTP request
    answer_id = Column(String(36), nullable=False)      # one per response
    attempt_id = Column(String(36), nullable=True)      # one per generation attempt
    session_id = Column(String(36), nullable=True)      # chat session if available
    created_at = Column(DateTime, default=utcnow)

    # 3-arm assignment (deterministic per session)
    experiment_group = Column(String(30), nullable=False)  # treatment|holdout_surface|no_injection

    # Revision lineage
    parent_answer_id = Column(String(36), nullable=True)  # answer_id of pre-revision response
    final_answer_id = Column(String(36), nullable=True)   # answer_id of terminal response
    is_terminal_attempt = Column(Boolean, default=True)    # False if a revision superseded this

    # Retrieval layer — logged even when context/surface is suppressed
    memory_available = Column(Boolean, default=False)       # pattern match existed
    memory_context_injected = Column(Boolean, default=False)  # memory data in LLM prompt
    memory_surface_emitted = Column(Boolean, default=False)   # SSE event sent to client
    solved_example_count = Column(Integer, default=0)
    solved_example_ids_json = Column(Text, nullable=True)
    confidence_band = Column(String(20), nullable=True)     # high/good/mixed/low

    # Classification (with version tags)
    workflow_class = Column(String(50), nullable=True)
    language_detected = Column(String(20), nullable=True)
    retrieval_mode = Column(String(30), nullable=True)
    response_contract = Column(String(30), nullable=True)
    workflow_classifier_version = Column(String(10), nullable=True)
    language_detector_version = Column(String(10), nullable=True)

    # Stack versions
    model_id = Column(String(50), nullable=True)
    git_sha = Column(String(12), nullable=True)
    verifier_mode = Column(String(30), nullable=True)  # generated_assertions|harness|no_verdict
    frontend_build = Column(String(50), nullable=True)  # client-reported build/version

    # System outcome layer
    verification_passed = Column(Integer, nullable=True)
    verification_failed = Column(Integer, nullable=True)
    verification_total = Column(Integer, nullable=True)
    was_revised = Column(Boolean, default=False)
    auto_staged = Column(Boolean, default=False)
    auto_promoted = Column(Boolean, default=False)

    # User outcome signals — explicit vs implicit (updated via client events)
    # State machine: transitions allowed (retry→accept, accept→reject, etc.)
    details_expanded = Column(Boolean, default=False)        # user opened memory details
    pattern_clicked = Column(Boolean, default=False)         # user clicked matched pattern
    explicit_accept = Column(Boolean, nullable=True)         # True=accept, False=reject, None=no signal
    implicit_accept_proxy = Column(Boolean, nullable=True)   # True=no_followup/copy, None=no signal
    user_retried = Column(Boolean, default=False)            # user retried or reformulated
    outcome_sequence_json = Column(Text, nullable=True)      # ordered list of all outcome events with timestamps

    # Latency (ms) — measured BEFORE telemetry write
    latency_retrieval_ms = Column(Float, nullable=True)
    latency_generation_ms = Column(Float, nullable=True)
    latency_verification_ms = Column(Float, nullable=True)
    latency_total_ms = Column(Float, nullable=True)

    # Matched pattern details (latent — for holdout analysis)
    matched_pattern_pass_rates_json = Column(Text, nullable=True)

    # Traffic hygiene
    is_internal = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_telemetry_group", "experiment_group"),
        Index("ix_telemetry_session", "session_id"),
        Index("ix_telemetry_created", "created_at"),
        Index("ix_telemetry_workflow", "workflow_class"),
        Index("ix_telemetry_answer", "answer_id"),
        Index("ix_telemetry_request", "request_id"),
        Index("ix_telemetry_band", "confidence_band"),
        Index("ix_telemetry_lang", "language_detected"),
        Index("ix_telemetry_group_band", "experiment_group", "confidence_band"),
        Index("ix_telemetry_group_workflow", "experiment_group", "workflow_class"),
    )


class SystemConfig(Base):
    __tablename__ = "system_config"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


def init_db():
    if DB_BACKEND == "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not create pgvector extension: {e}")
    Base.metadata.create_all(engine)

    # Lightweight column migrations — add columns that create_all can't add to existing tables
    _migrate_add_columns(engine)

    # Create FTS5 virtual table for chat search (SQLite only)
    if DB_BACKEND != "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts "
                    "USING fts5(content, content_rowid='rowid')"
                ))
                conn.commit()
                logger.info("FTS5 chat search table ready")
        except Exception as e:
            logger.warning(f"Could not create FTS5 table: {e}")


def _migrate_add_columns(engine):
    """Add columns to existing tables that create_all() can't handle.

    Each migration is idempotent — safe to run on every startup.
    """
    migrations = [
        ("training_pairs", "metadata_json", "TEXT"),
        ("lora_versions", "merge_cycle", "INTEGER DEFAULT 0"),
        ("lora_versions", "merged_base_path", "VARCHAR(500)"),
        ("lora_versions", "parent_version_id", "INTEGER"),
        ("chat_feedback", "verification_json", "TEXT"),
        ("chat_feedback", "auto_staged", "BOOLEAN DEFAULT 0"),
        ("book_sections", "keywords_json", "TEXT"),
        # v1 recurrence tracking for skill buffer
        ("training_pairs", "recurrence_count", "INTEGER DEFAULT 1"),
        ("training_pairs", "last_seen_at", "DATETIME"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                # Safe: table/column/col_type are hardcoded constants above, not user input.
                # DDL identifiers can't be parameterized in SQL.
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
                logger.info(f"Migration: added {table}.{column}")
            except Exception:
                # Column already exists — expected on subsequent startups
                conn.rollback()
