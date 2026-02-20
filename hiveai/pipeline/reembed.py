import logging
from hiveai.config import EMBEDDING_MODEL_NAME
from hiveai.models import SessionLocal, SystemConfig, BookSection, Base, engine

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32


def _ensure_system_config_table():
    Base.metadata.create_all(engine, tables=[SystemConfig.__table__], checkfirst=True)


def get_stored_embedding_model(db=None):
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        _ensure_system_config_table()
        row = db.query(SystemConfig).filter(SystemConfig.key == "embedding_model").first()
        return row.value if row else DEFAULT_MODEL
    except Exception as e:
        logger.warning(f"Could not read stored embedding model: {e}")
        return DEFAULT_MODEL
    finally:
        if close_db:
            db.close()


def check_embedding_model_match(db=None):
    stored = get_stored_embedding_model(db)
    return stored == EMBEDDING_MODEL_NAME


def reembed_all_sections(db):
    from hiveai.llm.client import embed_texts

    _ensure_system_config_table()

    stored_model = get_stored_embedding_model(db)
    configured_model = EMBEDDING_MODEL_NAME

    if stored_model == configured_model:
        logger.info("Embeddings are up to date")
        return {"status": "up_to_date", "count": 0, "old_model": stored_model, "new_model": configured_model}

    logger.info(f"Re-embedding: {stored_model} -> {configured_model}")

    sections = db.query(BookSection).filter(BookSection.content != None, BookSection.content != "").all()
    total = len(sections)

    if total == 0:
        logger.info("No sections to re-embed")
        row = db.query(SystemConfig).filter(SystemConfig.key == "embedding_model").first()
        if row:
            row.value = configured_model
        else:
            db.add(SystemConfig(key="embedding_model", value=configured_model))
        db.commit()
        return {"status": "ok", "count": 0, "old_model": stored_model, "new_model": configured_model}

    embedded_count = 0
    for i in range(0, total, BATCH_SIZE):
        batch = sections[i:i + BATCH_SIZE]
        texts = [s.content for s in batch]
        try:
            embeddings = embed_texts(texts)
            for section, embedding in zip(batch, embeddings):
                section.embedding = embedding
            db.flush()
            embedded_count += len(batch)
            logger.info(f"Re-embedded {embedded_count}/{total} sections...")
        except Exception as e:
            logger.error(f"Failed to embed batch starting at index {i}: {e}")
            raise

    row = db.query(SystemConfig).filter(SystemConfig.key == "embedding_model").first()
    if row:
        row.value = configured_model
    else:
        db.add(SystemConfig(key="embedding_model", value=configured_model))

    db.commit()
    logger.info(f"Re-embedding complete: {embedded_count} sections updated from {stored_model} to {configured_model}")

    return {"status": "ok", "count": embedded_count, "old_model": stored_model, "new_model": configured_model}
