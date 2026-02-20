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
            cursor.execute(f"SET hnsw.ef_search = {HNSW_EF_SEARCH}")
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
    source_urls = Column(JSON, default=list)
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
    entities = Column(JSON, default=list)
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
    tags = Column(JSON, default=list)
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
        created_at = Column(DateTime, default=utcnow)

        book = relationship("GoldenBook", back_populates="sections")

        __table_args__ = (
            Index("ix_book_sections_book_id", "book_id"),
            Index("ix_book_sections_embedding_hnsw", "embedding",
                  postgresql_using="hnsw",
                  postgresql_with={"m": 16, "ef_construction": 64},
                  postgresql_ops={"embedding": "vector_cosine_ops"}),
        )
else:
    class BookSection(Base):
        __tablename__ = "book_sections"

        id = Column(Integer, primary_key=True)
        book_id = Column(Integer, ForeignKey("golden_books.id", ondelete="CASCADE"), nullable=False)
        header = Column(String(500), nullable=False)
        content = Column(Text, nullable=False)
        token_count = Column(Integer, default=0)
        embedding_json = Column(Text, nullable=True)
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
