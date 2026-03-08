import os
import re
import json
import logging
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response
from sqlalchemy import func
from hiveai.models import init_db, SessionLocal, Job, GoldenBook, GraphTriple, CrawledPage, Chunk, BookSection, SystemConfig, TrainingPair, LoraVersion, ChatFeedback, utcnow
from hiveai.llm.client import reason, fast, smart_call, embed_text, clean_llm_response, stream_llm_call
from sqlalchemy import text as sa_text
from hiveai.llm.prompts import CHAT_SYSTEM_PROMPT, KNOWLEDGE_GAP_PROMPT, ANSWER_CHECK_PROMPT
from hiveai.chat import search_knowledge_sections, build_conversation_context, clean_topic, trigger_auto_learn, get_compressed_knowledge, budget_context
from skills.skill_loader import load_skills_for_query

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))


@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route("/archive")
def archive_index():
    return send_from_directory(WORKSPACE, 'index.html')


@app.route("/archive/hash-explorer.html")
def archive_hash_explorer():
    return send_from_directory(WORKSPACE, 'hash-explorer.html')


@app.route("/archive/static/<path:path>")
def archive_static(path):
    return send_from_directory(os.path.join(WORKSPACE, 'static'), path)

init_db()

# Validate configuration on startup
try:
    from hiveai.config import validate_config
    validate_config()
except Exception as _cfg_err:
    logging.getLogger(__name__).error(f"Config validation failed: {_cfg_err}")

try:
    from hiveai.pipeline.reembed import check_embedding_model_match, get_stored_embedding_model
    from hiveai.config import EMBEDDING_MODEL_NAME
    if not check_embedding_model_match():
        _stored = get_stored_embedding_model()
        logging.getLogger(__name__).warning(
            f"Embedding model mismatch: stored='{_stored}', configured='{EMBEDDING_MODEL_NAME}'. "
            f"Run POST /api/reembed to update."
        )
except Exception as _check_err:
    logging.getLogger(__name__).warning(f"Could not check embedding model match: {_check_err}")

from hiveai.pipeline.queue_worker import start_worker

# --- Warm embedding + dedup caches on startup (NON-BLOCKING) ---
# bge-m3 takes 5+ minutes to load on CPU — run in background thread
# so the Flask app starts serving immediately.
def _background_warmup():
    _log = logging.getLogger(__name__)
    try:
        import time as _t
        _start = _t.time()
        from hiveai.llm.client import embed_text as _warm_embed
        _warm_embed("warmup")
        _log.info(f"Embedding model warmed up ({_t.time() - _start:.0f}s)")

        from hiveai.lora.dedup import _get_cached_embeddings
        _warm_db = SessionLocal()
        _embs, _quals = _get_cached_embeddings(_warm_db)
        _warm_db.close()
        _log.info(f"Dedup cache warmed: {len(_embs)} embeddings preloaded")
    except Exception as e:
        _log.warning(f"Cache warmup failed: {e}")

import threading
_warmup_thread = threading.Thread(target=_background_warmup, daemon=True)
_warmup_thread.start()

start_worker()


def backfill_embeddings(db):
    from hiveai.pipeline.writer import embed_book_sections
    from sqlalchemy import func as sqla_func

    books_with_sections = db.query(BookSection.book_id).distinct().subquery()
    books_to_embed = db.query(GoldenBook).filter(
        ~GoldenBook.id.in_(db.query(books_with_sections.c.book_id))
    ).all()

    if not books_to_embed:
        return 0

    total_sections = 0
    for book in books_to_embed:
        try:
            count = embed_book_sections(book, db)
            total_sections += count
            logging.getLogger(__name__).info(f"Backfilled {count} sections for book '{book.title}'")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to backfill book {book.id}: {e}")

    return total_sections



def backfill_quality_scores(db):
    from hiveai.pipeline.scorer import score_book
    unscored = db.query(GoldenBook).filter(GoldenBook.quality_score == None).all()
    if not unscored:
        return 0
    scored = 0
    for book in unscored:
        try:
            result = score_book(book)
            book.quality_score = result["score"]
            book.quality_details = result["details"]
            if result["score"] < 0.5:
                book.needs_rewrite = True
            db.commit()
            scored += 1
            logging.getLogger(__name__).info(f"Backfill scored book '{book.title}': {result['score']}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to score book {book.id}: {e}")
    return scored


def _background_backfill():
    import time
    time.sleep(3)
    try:
        _db = SessionLocal()
        _backfill_count = backfill_embeddings(_db)
        if _backfill_count > 0:
            logging.getLogger(__name__).info(f"Backfilled {_backfill_count} book sections in background")
        _score_count = backfill_quality_scores(_db)
        if _score_count > 0:
            logging.getLogger(__name__).info(f"Backfill scored {_score_count} books in background")
        _db.close()
    except Exception as _e:
        logging.getLogger(__name__).warning(f"Background backfill failed: {_e}")

_backfill_thread = threading.Thread(target=_background_backfill, daemon=True)
_backfill_thread.start()


def _auto_improve_worker():
    """Background worker: periodically check for accumulated auto-verified pairs
    and trigger micro-training when enough are available."""
    import time as _time
    _time.sleep(30)  # Wait for app startup

    _logger = logging.getLogger("hiveai.auto_improve")

    while True:
        try:
            from hiveai.config import AUTO_IMPROVE_ENABLED, AUTO_IMPROVE_CHECK_INTERVAL, AUTO_IMPROVE_MIN_PAIRS
            if not AUTO_IMPROVE_ENABLED:
                _time.sleep(AUTO_IMPROVE_CHECK_INTERVAL)
                continue

            _db = SessionLocal()
            try:
                auto_count = _db.query(TrainingPair).filter(
                    TrainingPair.source == "auto_verified",
                    TrainingPair.is_eligible == True,
                    TrainingPair.lora_version == None,
                ).count()

                if auto_count >= AUTO_IMPROVE_MIN_PAIRS:
                    _logger.info(f"Auto-improve: {auto_count} verified pairs ready, triggering micro-training")

                    from hiveai.lora.trainer import train_lora, MIN_PAIRS_MICRO

                    output_dir = os.path.join(WORKSPACE, "loras", "training_data")
                    os.makedirs(output_dir, exist_ok=True)
                    ts = int(_time.time())
                    micro_path = os.path.join(output_dir, f"auto_improve_{ts}.jsonl")

                    # Export eligible unused pairs as Alpaca-format JSONL
                    pairs = _db.query(TrainingPair).filter(
                        TrainingPair.is_eligible == True,
                        TrainingPair.quality >= 0.70,
                        TrainingPair.lora_version == None,
                    ).order_by(TrainingPair.quality.desc()).all()

                    if len(pairs) >= MIN_PAIRS_MICRO:
                        with open(micro_path, "w", encoding="utf-8") as f:
                            for p in pairs:
                                f.write(json.dumps({
                                    "instruction": p.instruction,
                                    "output": p.response,
                                }, ensure_ascii=False) + "\n")

                        adapter_dir = os.path.join(WORKSPACE, "loras", f"auto_improve_{ts}")

                        def _run_micro():
                            tdb = SessionLocal()
                            try:
                                train_lora(micro_path, adapter_dir, f"auto-{ts}",
                                           db=tdb, force_micro=True)
                            except Exception as exc:
                                logging.getLogger("hiveai.auto_improve").error(f"Auto micro-training failed: {exc}")
                            finally:
                                tdb.close()

                        threading.Thread(target=_run_micro, daemon=True).start()
                        _logger.info(f"Auto-improve: micro-training started ({len(pairs)} pairs)")
                    else:
                        _logger.debug(f"Auto-improve: only {len(pairs)} eligible pairs, need {MIN_PAIRS_MICRO}")
                else:
                    _logger.debug(f"Auto-improve: {auto_count} auto-verified pairs, need {AUTO_IMPROVE_MIN_PAIRS}")

            finally:
                _db.close()

        except Exception as exc:
            logging.getLogger("hiveai.auto_improve").error(f"Auto-improve worker error: {exc}")

        _time.sleep(AUTO_IMPROVE_CHECK_INTERVAL)


try:
    from hiveai.config import AUTO_IMPROVE_ENABLED as _ai_enabled
    if _ai_enabled:
        _auto_improve_thread = threading.Thread(target=_auto_improve_worker, daemon=True)
        _auto_improve_thread.start()
        logging.getLogger(__name__).info("Auto-improve background worker started")
except Exception:
    pass

# --- Multi-Source Miner Background Worker ---
try:
    from hiveai.config import MULTI_MINER_ENABLED
    if MULTI_MINER_ENABLED:
        from hiveai.lora.miner import start_miner
        _miner_worker = start_miner()
        logging.getLogger(__name__).info("Multi-source miner background worker started")
except Exception as _miner_err:
    logging.getLogger(__name__).warning(f"Multi-source miner failed to start: {_miner_err}")


@app.route("/health")
def health_check():
    """Detailed health check endpoint for monitoring and diagnostics."""
    import time
    import shutil
    checks = {"status": "ok", "timestamp": time.time()}

    # --- Database ---
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "training_pairs": db.query(TrainingPair).count(),
            "lora_versions": db.query(LoraVersion).count(),
            "golden_books": db.query(GoldenBook).count(),
            "active_jobs": db.query(Job).filter(
                Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing"])
            ).count(),
        }
        db.close()
    except Exception as e:
        checks["database"] = {"status": f"error: {e}"}
        checks["status"] = "degraded"

    # --- Ollama ---
    try:
        import requests as _req
        from hiveai.config import OLLAMA_BASE_URL
        r = _req.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            checks["ollama"] = {"status": "ok", "models": models}
        else:
            checks["ollama"] = {"status": f"http {r.status_code}"}
            checks["status"] = "degraded"
    except Exception:
        checks["ollama"] = {"status": "unavailable"}
        checks["status"] = "degraded"

    # --- llama-server ---
    try:
        import requests as _req
        from hiveai.config import LLAMA_SERVER_BASE_URL, LLAMA_SERVER_MODEL
        r = _req.get(f"{LLAMA_SERVER_BASE_URL}/health", timeout=3)
        checks["llama_server"] = {
            "status": "ok" if r.status_code == 200 else f"http {r.status_code}",
            "model": LLAMA_SERVER_MODEL,
        }
    except Exception:
        checks["llama_server"] = {"status": "unavailable"}

    # --- Embedding model ---
    try:
        from hiveai.llm.client import _embedding_model
        checks["embedding"] = {
            "status": "loaded" if _embedding_model is not None else "not_loaded",
            "model": str(getattr(_embedding_model, "model_name", "unknown")) if _embedding_model else None,
        }
    except Exception:
        checks["embedding"] = {"status": "unknown"}

    # --- Disk space ---
    try:
        usage = shutil.disk_usage(WORKSPACE)
        free_gb = usage.free / (1024 ** 3)
        checks["disk"] = {
            "free_gb": round(free_gb, 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "warning": free_gb < 10,
        }
        if free_gb < 5:
            checks["status"] = "degraded"
    except Exception:
        checks["disk"] = {"status": "unknown"}

    # --- Config summary ---
    from hiveai.config import (
        HARDWARE_PROFILE, DB_BACKEND, LLM_BACKEND,
        MIN_TRAINING_QUALITY, LORA_EXPORT_QUALITY, CHAT_VERIFY_CODE
    )
    checks["config"] = {
        "hardware_profile": HARDWARE_PROFILE,
        "db_backend": DB_BACKEND,
        "llm_backend": LLM_BACKEND,
        "min_training_quality": MIN_TRAINING_QUALITY,
        "lora_export_quality": LORA_EXPORT_QUALITY,
        "chat_verify_code": CHAT_VERIFY_CODE,
    }

    code = 200 if checks["status"] == "ok" else 503
    return jsonify(checks), code


@app.route("/")
def dashboard():
    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(20).all()
        books = db.query(GoldenBook).filter(GoldenBook.status == "draft").order_by(GoldenBook.created_at.desc()).limit(10).all()
        stats = {
            "total_jobs": db.query(Job).count(),
            "active_jobs": db.query(Job).filter(Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing"])).count(),
            "total_books": db.query(GoldenBook).count(),
            "published_books": db.query(GoldenBook).filter(GoldenBook.status == "published").count(),
            "total_triples": db.query(GraphTriple).count(),
            "total_pages": db.query(CrawledPage).count(),
            "eligible_teachings": db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count(),
            "lora_crystals": db.query(LoraVersion).count(),
        }
        # Merge cycle and MoLoRA stats
        extra = {}
        try:
            from hiveai.lora.merge_cycle import load_merge_history
            history = load_merge_history()
            extra["merge_cycles"] = len(history)
        except Exception:
            pass
        try:
            from hiveai.config import MOLORA_ENABLED
            if MOLORA_ENABLED:
                from hiveai.lora.molora import get_available_domains
                extra["molora_domains"] = get_available_domains()
        except Exception:
            pass
        try:
            from hiveai.config import MULTI_MINER_ENABLED
            if MULTI_MINER_ENABLED:
                from hiveai.lora.miner import get_miner_status
                extra["miner_status"] = get_miner_status()
        except Exception:
            pass

        return render_template("dashboard.html", jobs=jobs, books=books, stats=stats, **extra)
    finally:
        db.close()


@app.route("/api/stats")
def api_stats():
    """Lightweight stats endpoint for dashboard polling (no heavy queries)."""
    db = SessionLocal()
    try:
        stats = {
            "total_jobs": db.query(Job).count(),
            "active_jobs": db.query(Job).filter(Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing"])).count(),
            "total_books": db.query(GoldenBook).count(),
            "published_books": db.query(GoldenBook).filter(GoldenBook.status == "published").count(),
            "total_triples": db.query(GraphTriple).count(),
            "total_pages": db.query(CrawledPage).count(),
            "eligible_teachings": db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count(),
            "lora_crystals": db.query(LoraVersion).count(),
        }
        try:
            from hiveai.config import MULTI_MINER_ENABLED
            if MULTI_MINER_ENABLED:
                from hiveai.lora.miner import get_miner_status
                ms = get_miner_status()
                stats["mined_today"] = ms.get("stats", {}).get("mined_today", 0)
        except Exception:
            pass
        return jsonify(stats)
    finally:
        db.close()


@app.route("/api/jobs", methods=["POST"])
def create_job():
    data = request.get_json()
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    db = SessionLocal()
    try:
        job = Job(topic=topic, status="queued")
        db.add(job)
        db.commit()
        db.refresh(job)

        return jsonify({"id": job.id, "topic": job.topic, "status": job.status}), 201
    finally:
        db.close()


@app.route("/api/jobs/batch", methods=["POST"])
def create_batch_jobs():
    data = request.get_json()
    topics = data.get("topics", [])
    if not topics or not isinstance(topics, list):
        return jsonify({"error": "List of topics required"}), 400

    db = SessionLocal()
    try:
        created = []
        for topic in topics:
            topic = topic.strip()
            if topic:
                job = Job(topic=topic, status="queued")
                db.add(job)
                db.flush()
                created.append({"id": job.id, "topic": job.topic, "status": job.status})
        db.commit()
        return jsonify({"jobs": created, "count": len(created)}), 201
    finally:
        db.close()


@app.route("/api/queue/status")
def queue_status():
    from hiveai.pipeline.queue_worker import get_queue_status, ensure_worker_running
    ensure_worker_running()
    return jsonify(get_queue_status())


@app.route("/api/queue/pause", methods=["POST"])
def pause_queue():
    from hiveai.pipeline.queue_worker import set_queue_paused
    set_queue_paused(True)
    return jsonify({"status": "paused"})


@app.route("/api/queue/resume", methods=["POST"])
def resume_queue():
    from hiveai.pipeline.queue_worker import set_queue_paused
    set_queue_paused(False)
    return jsonify({"status": "resumed"})


@app.route("/api/jobs/<int:job_id>/cancel", methods=["POST"])
def cancel_job_route(job_id):
    from hiveai.pipeline.queue_worker import cancel_job
    result = cancel_job(job_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/jobs/<int:job_id>")
def get_job(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({
            "id": job.id,
            "topic": job.topic,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "hive_ping_count": job.hive_ping_count,
            "crawl_count": job.crawl_count,
            "chunk_count": job.chunk_count,
            "triple_count": job.triple_count,
            "error_message": job.error_message,
            "golden_book_id": job.golden_book_id,
        })
    finally:
        db.close()


@app.route("/api/jobs/<int:job_id>/stream")
def job_stream(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        chunks = db.query(Chunk).filter(Chunk.job_id == job_id).order_by(Chunk.id).limit(10).all()
        chunks_preview = "\n\n---\n\n".join([c.content[:500] for c in chunks]) if chunks else None

        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).order_by(GraphTriple.confidence.desc()).limit(20).all()
        triples_data = [{"subject": t.subject, "predicate": t.predicate, "object": t.obj, "confidence": t.confidence} for t in triples]

        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
        sources = [{"url": p.url, "title": p.title or "Untitled"} for p in pages]

        book_data = None
        if job.golden_book_id:
            book = db.get(GoldenBook, job.golden_book_id)
            if book:
                book_data = {
                    "id": book.id,
                    "title": book.title,
                    "content": book.content,
                    "word_count": book.word_count,
                    "source_count": book.source_count,
                    "content_hash": book.content_hash,
                }

        stage_map = {
            "queued": "Waiting in the mine queue...",
            "generating_urls": "Mapping source locations...",
            "crawling": "Mining ore from the web...",
            "crawled": "Ore mined and ready for crushing.",
            "chunking": "Crushing ore into manageable pieces...",
            "chunked": "Ore crushed into chunks.",
            "reasoning": "Smelting - extracting pure facts from raw ore...",
            "reasoned": "Smelting complete! Gold nuggets extracted.",
            "writing": "Forging the Golden Tome...",
            "review": "Pure gold! Tome ready for inspection.",
            "published": "Treasured! Inscribed on the blockchain.",
            "error": "Cave-in! Something went wrong.",
        }

        return jsonify({
            "status": job.status,
            "stage": stage_map.get(job.status, job.status),
            "topic": job.topic,
            "chunks_preview": chunks_preview,
            "chunks_count": job.chunk_count,
            "facts_count": job.triple_count,
            "triples": triples_data,
            "golden_book": book_data,
            "sources": sources,
            "error": job.error_message,
        })
    finally:
        db.close()


@app.route("/api/jobs")
def list_jobs():
    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(50).all()
        return jsonify([{
            "id": j.id,
            "topic": j.topic,
            "status": j.status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "crawl_count": j.crawl_count,
            "triple_count": j.triple_count,
        } for j in jobs])
    finally:
        db.close()


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return redirect(url_for("dashboard"))
        pages = db.query(CrawledPage).filter(CrawledPage.job_id == job_id).all()
        triples = db.query(GraphTriple).filter(GraphTriple.job_id == job_id).limit(100).all()
        book = None
        if job.golden_book_id:
            book = db.get(GoldenBook, job.golden_book_id)
        return render_template("job_detail.html", job=job, pages=pages, triples=triples, book=book)
    finally:
        db.close()


@app.route("/book/<int:book_id>")
def book_review(book_id):
    db = SessionLocal()
    try:
        book = db.get(GoldenBook, book_id)
        if not book:
            return redirect(url_for("dashboard"))
        return render_template("book_review.html", book=book)
    finally:
        db.close()


@app.route("/api/books/<int:book_id>/publish", methods=["POST"])
def publish_book(book_id):
    db = SessionLocal()
    try:
        book = db.get(GoldenBook, book_id)
        if not book:
            return jsonify({"error": "Book not found"}), 404
        if book.status == "published":
            return jsonify({"error": "Already published"}), 400

        data = request.get_json() or {}
        author = data.get("author", "")
        if not author:
            return jsonify({"error": "Hive author username required"}), 400

        from hiveai.pipeline.publisher import publish_to_hive
        result = publish_to_hive(book, author, db)
        return jsonify(result)
    finally:
        db.close()


@app.route("/api/books/<int:book_id>/rewrite", methods=["POST"])
def rewrite_book_api(book_id):
    try:
        from hiveai.pipeline.writer import rewrite_book
        book = rewrite_book(book_id)
        if book:
            return jsonify({"status": "ok", "quality_score": book.quality_score})
        return jsonify({"error": "Rewrite failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/graph")
def graph_explorer():
    db = SessionLocal()
    try:
        job_id = request.args.get("job_id", type=int)
        search = request.args.get("search", "").strip()
        min_conf = request.args.get("min_conf", type=float, default=0.0)

        query = db.query(GraphTriple)
        if job_id:
            query = query.filter(GraphTriple.job_id == job_id)
        if min_conf > 0:
            query = query.filter(GraphTriple.confidence >= min_conf)
        if search:
            like = f"%{search}%"
            query = query.filter(
                (GraphTriple.subject.ilike(like)) |
                (GraphTriple.predicate.ilike(like)) |
                (GraphTriple.obj.ilike(like))
            )

        triples = query.order_by(GraphTriple.confidence.desc()).limit(300).all()

        jobs = db.query(Job).filter(Job.triple_count > 0).order_by(Job.created_at.desc()).all()

        subjects = set()
        predicates = set()
        for t in triples:
            subjects.add(t.subject)
            predicates.add(t.predicate)

        stats = {
            "total": len(triples),
            "unique_subjects": len(subjects),
            "unique_predicates": len(predicates),
            "avg_confidence": sum(t.confidence for t in triples if t.confidence) / max(sum(1 for t in triples if t.confidence), 1),
        }

        return render_template("graph_explorer.html",
            triples=triples,
            jobs=jobs,
            stats=stats,
            current_job_id=job_id,
            current_search=search or "",
            current_min_conf=min_conf,
        )
    finally:
        db.close()


@app.route("/api/admin/backfill-embeddings", methods=["POST"])
def backfill_embeddings_api():
    db = SessionLocal()
    try:
        count = backfill_embeddings(db)
        return jsonify({"status": "ok", "sections_created": count})
    finally:
        db.close()


@app.route("/api/admin/score-books", methods=["POST"])
def score_books_api():
    db = SessionLocal()
    try:
        count = backfill_quality_scores(db)
        return jsonify({"status": "ok", "books_scored": count})
    finally:
        db.close()


@app.route("/api/admin/compaction-quality")
def compaction_quality_api():
    """Measure information retention quality of compressed books.

    Query params:
        ?book_id=5          — single book analysis
        ?threshold=0.5      — flag books below this quality
        ?with_embeddings=1  — include semantic similarity (slower)
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.compaction_quality import measure_quality
    db = SessionLocal()
    try:
        from hiveai.models import GoldenBook
        book_id = request.args.get("book_id", type=int)
        threshold = request.args.get("threshold", type=float, default=0.0)
        use_embed = request.args.get("with_embeddings", "").lower() in ("1", "true")

        query = db.query(GoldenBook).filter(
            GoldenBook.compressed_content.isnot(None),
            GoldenBook.compressed_content != "",
        )
        if book_id:
            query = query.filter(GoldenBook.id == book_id)

        books = query.all()
        if not books:
            return jsonify({"status": "ok", "total_books": 0, "books": []})

        results = []
        for book in books:
            q = measure_quality(
                book.content or "", book.compressed_content or "",
                with_embeddings=use_embed,
            )
            q["book_id"] = book.id
            q["title"] = (book.title or "Untitled")[:60]
            results.append(q)

        results.sort(key=lambda r: r["overall_quality"])
        avg_quality = sum(r["overall_quality"] for r in results) / len(results)
        flagged = [r for r in results if r["overall_quality"] < threshold] if threshold > 0 else []

        return jsonify({
            "status": "ok",
            "total_books": len(results),
            "avg_quality": round(avg_quality, 3),
            "threshold": threshold if threshold > 0 else None,
            "flagged_count": len(flagged),
            "books": results,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/reembed", methods=["POST"])
def reembed_api():
    from hiveai.pipeline.reembed import check_embedding_model_match, reembed_all_sections
    db = SessionLocal()
    try:
        if check_embedding_model_match(db):
            return jsonify({"status": "up_to_date", "message": "Embeddings are already up to date"})
        result = reembed_all_sections(db)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/graph")
def graph_stats():
    from hiveai.pipeline.communities import get_global_graph_stats
    return jsonify(get_global_graph_stats())


@app.route("/api/graph/rebuild", methods=["POST"])
def rebuild_graph():
    from hiveai.pipeline.communities import rebuild_global_graph
    result = rebuild_global_graph()
    return jsonify(result)


@app.route("/api/hardware")
def hardware_status():
    from hiveai.hardware import get_hardware_profile
    return jsonify(get_hardware_profile())


@app.route("/api/llm-status")
def llm_status():
    from hiveai.llm.client import get_active_backend, _detect_ollama
    from hiveai.config import LLM_BACKEND, OPENROUTER_API_KEY, OLLAMA_BASE_URL
    backend = get_active_backend()
    return jsonify({
        "active_backend": backend,
        "configured_backend": LLM_BACKEND,
        "ollama_available": _detect_ollama(),
        "ollama_url": OLLAMA_BASE_URL,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
    })


@app.route("/api/embedding-status")
def embedding_status_api():
    from hiveai.pipeline.reembed import get_stored_embedding_model, check_embedding_model_match
    from hiveai.config import EMBEDDING_MODEL_NAME as _configured_model
    db = SessionLocal()
    try:
        stored = get_stored_embedding_model(db)
        match = check_embedding_model_match(db)
        from hiveai.config import DB_BACKEND
        if DB_BACKEND == "sqlite":
            embedding_count = db.query(BookSection).filter(BookSection.embedding_json.isnot(None)).count()
        else:
            embedding_count = db.query(BookSection).filter(BookSection.embedding.isnot(None)).count()
        return jsonify({
            "configured_model": _configured_model,
            "stored_model": stored,
            "match": match,
            "sections_with_embeddings": embedding_count,
        })
    finally:
        db.close()


@app.route("/chat")
def chat_page():
    db = SessionLocal()
    try:
        books = db.query(GoldenBook).order_by(GoldenBook.created_at.desc()).all()
        book_count = len(books)
        topic_list = list(set(
            b.title.replace("Knowledge: ", "").strip()
            for b in books if b.title
        ))
        return render_template("chat.html", books=books, book_count=book_count, topic_list=topic_list)
    finally:
        db.close()


@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message is required"}), 400

    db = SessionLocal()
    try:
        books = db.query(GoldenBook).all()
        topic_list = [
            b.title.replace("Knowledge: ", "").strip()
            for b in books if b.title
        ]

        if not books:
            active_jobs = db.query(Job).filter(
                Job.status.in_(["queued", "generating_urls", "crawling", "chunking", "reasoning", "writing"])
            ).all()

            if active_jobs:
                return jsonify({
                    "reply": "The gnomes are still out mining knowledge! I don't have any Golden Books to draw from yet. Please wait for the current research to finish.",
                    "sources": [],
                    "learning": {"active": True, "topic": active_jobs[0].topic, "job_id": active_jobs[0].id}
                })

            gap_check = fast(
                KNOWLEDGE_GAP_PROMPT.format(question=message, topics="(empty library)"),
                max_tokens=100
            )
            gap_check = clean_llm_response(gap_check)

            research_topic = clean_topic(gap_check) if gap_check != "SUFFICIENT" else clean_topic(message)
            if not research_topic:
                research_topic = message[:100]
            learning_info, _ = trigger_auto_learn(research_topic, db)

            return jsonify({
                "reply": f"My library is empty! I've dispatched the gnomes to research **{research_topic}**. Once they return with knowledge, I'll be able to answer your question.",
                "sources": [],
                "learning": learning_info
            })

        top_sections, source_books, all_books = search_knowledge_sections(message, db, history=history)

        # RLM-inspired context budgeting: prioritize relevant content, drop noise
        knowledge_context = budget_context(top_sections, message, max_tokens=4000)

        book_ids = list(set(s.get("book_id") for s in top_sections if s.get("book_id")))
        compressed = get_compressed_knowledge(book_ids, db)
        if compressed:
            knowledge_context = f"=== Dense Knowledge Map ===\n{compressed}\n\n=== Detailed Sections ===\n{knowledge_context}"

        conversation_context = build_conversation_context(history)

        # Inject domain skills for Hive-related queries
        skill_context = load_skills_for_query(message)
        skill_block = f"\n\n{skill_context}" if skill_context else ""

        # Virtual Memory pattern: knowledge in system position for stronger attention
        system_prompt = f"""{CHAT_SYSTEM_PROMPT}
{skill_block}

Your knowledge sections (from verified Golden Books):
{knowledge_context}

Answer using ONLY the knowledge sections above. If you lack knowledge, respond with KNOWLEDGE_GAP: <topic>"""

        user_prompt = f"""{conversation_context}

User's question: {message}"""

        response = smart_call(user_prompt, question=message,
                             system_prompt=system_prompt,
                             num_sections=len(top_sections), max_tokens=4096)
        response = clean_llm_response(response)

        # Self-verify: run code blocks in sandbox before returning to user
        verified_meta = None
        try:
            from hiveai.config import CHAT_VERIFY_CODE
            if CHAT_VERIFY_CODE:
                from hiveai.sandbox import verify_response_code
                verification = verify_response_code(response, timeout=15)
                if verification["total_blocks"] > 0:
                    verified_meta = {
                        "blocks": verification["total_blocks"],
                        "passed": verification["passed"],
                        "failed": verification["failed"],
                    }
                    if verification["failed"] > 0 and verification["passed"] == 0:
                        response += (
                            "\n\n> **Note:** Automated code verification detected potential issues. "
                            "Please test the code carefully before using in production."
                        )
        except Exception as e:
            logging.getLogger(__name__).debug(f"Code verification skipped: {e}")

        # Auto-improve: stage verified-working responses as training pairs
        auto_staged = None
        if verified_meta and verified_meta.get("failed", 1) == 0 and verified_meta.get("passed", 0) > 0:
            try:
                auto_staged = _auto_stage_verified_pair(message, response, verification, db)
            except Exception:
                pass

        learning_info = {"active": False, "topic": None, "job_id": None}

        if "KNOWLEDGE_GAP:" in response:
            gap_topic_raw = response.split("KNOWLEDGE_GAP:")[-1].strip().strip("*").strip()
            gap_topic = clean_topic(gap_topic_raw) if gap_topic_raw else None
            if gap_topic:
                learning_info, already_exists = trigger_auto_learn(gap_topic, db)
                if already_exists:
                    response = f"I don't have enough knowledge about **{gap_topic}** yet, but the gnomes are already researching it! I'll have an answer once they return."
                else:
                    response = f"I don't have knowledge about **{gap_topic}** in my library yet. I've dispatched the gnomes to research this topic! Once they return with a new Golden Book, I'll be able to answer properly."
        else:
            try:
                sections_summary = ", ".join(
                    f"{s['book_title']} > {s['header']}"
                    for s in top_sections[:8]
                )
                check_result = fast(
                    ANSWER_CHECK_PROMPT.format(
                        question=message,
                        answer=response[:2000],
                        sections_summary=sections_summary
                    ),
                    max_tokens=200
                )
                check_result = clean_llm_response(check_result)

                if "WEAK" in check_result and "GAPS:" in check_result:
                    gap_line = check_result.split("GAPS:")[-1].strip().split("\n")[0].strip()
                    if gap_line and gap_line.lower() != "none" and len(gap_line) < 200:
                        learning_info, _ = trigger_auto_learn(gap_line, db)
                        response += f"\n\n*Note: My coverage on this topic could be stronger. I've dispatched gnomes to research **{gap_line}** for a more thorough answer next time.*"
            except Exception:
                pass

        result = {
            "reply": response,
            "sources": source_books,
            "learning": learning_info,
        }
        if verified_meta:
            result["verified"] = verified_meta
        if auto_staged:
            result["auto_staged"] = auto_staged

        # MoLoRA domain info (if enabled)
        try:
            from hiveai.config import MOLORA_ENABLED
            if MOLORA_ENABLED:
                from hiveai.lora.molora import classify_domain
                result["domain"] = classify_domain(message)
        except Exception:
            pass

        return jsonify(result)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Streaming Chat API (SSE)
# ---------------------------------------------------------------------------

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    Server-Sent Events streaming chat endpoint.

    Phase 1 (sync): RAG search + context building (same as /api/chat)
    Phase 2 (stream): Token-by-token Ollama response via SSE

    SSE events:
      event: sources   — book sources metadata (sent first)
      data: {"token"}  — each streamed token
      event: done      — {"full_response": "..."} for gap detection
      event: error     — on failure
    """
    data = request.get_json()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message is required"}), 400

    def generate():
        db = SessionLocal()
        try:
            books = db.query(GoldenBook).all()
            topic_list = [
                b.title.replace("Knowledge: ", "").strip()
                for b in books if b.title
            ]

            rich_system_prompt = CHAT_SYSTEM_PROMPT  # default; overridden when books exist
            if not books:
                # No Golden Books yet — stream direct Ollama response without RAG
                yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
                conversation_context = build_conversation_context(history)
                prompt = f"""You are HiveAI, a helpful coding knowledge assistant.
{conversation_context}

User's question: {message}

Answer the question directly and helpfully. Note: The knowledge library is still being built, so this response comes from the base model without RAG context."""
            else:
                # Phase 1: RAG search (sync)
                top_sections, source_books, all_books = search_knowledge_sections(message, db, history=history)

                # Send sources first
                yield f"event: sources\ndata: {json.dumps({'sources': source_books})}\n\n"

                # RLM-inspired context budgeting: prioritize relevant content, drop noise
                knowledge_context = budget_context(top_sections, message, max_tokens=4000)

                book_ids = list(set(s.get("book_id") for s in top_sections if s.get("book_id")))
                compressed = get_compressed_knowledge(book_ids, db)
                if compressed:
                    knowledge_context = f"=== Dense Knowledge Map ===\n{compressed}\n\n=== Detailed Sections ===\n{knowledge_context}"

                conversation_context = build_conversation_context(history)

                # Inject domain skills for Hive-related queries
                skill_context = load_skills_for_query(message)
                skill_block = f"\n\n{skill_context}" if skill_context else ""

                # Virtual Memory pattern: knowledge in system position for stronger attention
                rich_system_prompt = f"""{CHAT_SYSTEM_PROMPT}
{skill_block}

Your knowledge sections (from verified Golden Books):
{knowledge_context}

Answer using ONLY the knowledge sections above. If you lack knowledge, respond with KNOWLEDGE_GAP: <topic>"""

                prompt = f"""{conversation_context}

User's question: {message}"""

            # Phase 2: Stream tokens from Ollama
            for chunk in stream_llm_call(prompt, system_prompt=rich_system_prompt, max_tokens=4096):
                if "error" in chunk:
                    yield f"event: error\ndata: {json.dumps({'error': chunk['error']})}\n\n"
                    return
                if "token" in chunk:
                    yield f"data: {json.dumps({'token': chunk['token']})}\n\n"
                if chunk.get("done"):
                    full = clean_llm_response(chunk.get("full_response", ""))
                    # Self-verify code blocks before sending done event
                    try:
                        from hiveai.config import CHAT_VERIFY_CODE
                        if CHAT_VERIFY_CODE:
                            from hiveai.sandbox import verify_response_code
                            verification = verify_response_code(full, timeout=15)
                            if verification["total_blocks"] > 0:
                                v_data = {
                                    "blocks": verification["total_blocks"],
                                    "passed": verification["passed"],
                                    "failed": verification["failed"],
                                }
                                yield f"event: verification\ndata: {json.dumps(v_data)}\n\n"
                                # Auto-improve: stage verified pairs
                                if verification["failed"] == 0 and verification["passed"] > 0:
                                    try:
                                        staged = _auto_stage_verified_pair(message, full, verification, db)
                                        if staged:
                                            yield f"event: auto_staged\ndata: {json.dumps(staged)}\n\n"
                                    except Exception:
                                        pass
                    except Exception:
                        pass

                    # MoLoRA domain info
                    try:
                        from hiveai.config import MOLORA_ENABLED
                        if MOLORA_ENABLED:
                            from hiveai.lora.molora import classify_domain
                            domain = classify_domain(message)
                            if domain != "general":
                                yield f"event: domain\ndata: {json.dumps({'domain': domain})}\n\n"
                    except Exception:
                        pass

                    yield f"event: done\ndata: {json.dumps({'full_response': full})}\n\n"
        except Exception as e:
            logging.getLogger(__name__).error(f"Stream chat error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.close()

    return Response(generate(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Auto-Improvement — stage verified chat responses as training pairs
# ---------------------------------------------------------------------------

def _auto_stage_verified_pair(user_message, ai_response, verification, db):
    """
    Auto-stage a chat response as a training pair if ALL code blocks pass verification.

    Returns dict with pair_id and quality, or None if not staged.
    """
    import hashlib
    from hiveai.config import (
        AUTO_IMPROVE_ENABLED, AUTO_IMPROVE_MIN_BLOCKS,
        AUTO_IMPROVE_QUALITY_BONUS, MIN_TRAINING_QUALITY,
    )

    if not AUTO_IMPROVE_ENABLED:
        return None

    if not verification or verification.get("total_blocks", 0) < AUTO_IMPROVE_MIN_BLOCKS:
        return None

    # Strict: ALL blocks must pass — no partial credit
    if verification.get("failed", 1) > 0 or verification.get("timed_out", 1) > 0:
        return None
    if verification.get("passed", 0) == 0:
        return None

    logger = logging.getLogger("hiveai.auto_improve")
    try:
        from hiveai.lora.distiller import _score_quality
        quality = _score_quality(user_message, ai_response)

        # Execution bonus: all code blocks passed sandbox verification
        quality = min(quality + AUTO_IMPROVE_QUALITY_BONUS, 1.0)

        if quality < MIN_TRAINING_QUALITY:
            logger.debug(f"Auto-stage skipped: quality {quality:.3f} < {MIN_TRAINING_QUALITY}")
            return None

        # Dedup check
        from hiveai.lora.dedup import is_duplicate, add_to_cache
        if is_duplicate(user_message, db, quality=quality):
            logger.debug("Auto-stage skipped: duplicate detected")
            return None

        # Create training pair
        pair = TrainingPair(
            source="auto_verified",
            topic="chat_auto_improve",
            instruction=user_message,
            response=ai_response,
            quality=quality,
            is_eligible=True,
            metadata_json=json.dumps({
                "verification": {
                    "total_blocks": verification["total_blocks"],
                    "passed": verification["passed"],
                    "pass_rate": verification.get("overall_pass_rate", 1.0),
                },
                "source_type": "chat_auto_improve",
            }),
        )
        # Embed instruction for dedup cache
        try:
            embedding = embed_text(user_message)
            pair.embedding = embedding
        except Exception:
            embedding = None

        db.add(pair)
        db.flush()

        # Create ChatFeedback record for lineage tracking
        msg_hash = hashlib.sha256(user_message.encode()).hexdigest()
        feedback = ChatFeedback(
            message_hash=msg_hash,
            user_message=user_message,
            ai_response=ai_response,
            rating="auto",
            staged_pair_id=pair.id,
            auto_staged=True,
            verification_json=json.dumps({
                "total_blocks": verification["total_blocks"],
                "passed": verification["passed"],
                "failed": verification["failed"],
                "timed_out": verification.get("timed_out", 0),
                "overall_pass_rate": verification.get("overall_pass_rate", 1.0),
            }),
        )
        db.add(feedback)
        db.commit()

        # Update dedup cache
        if embedding:
            add_to_cache(embedding, quality=quality)

        logger.info(f"Auto-staged training pair id={pair.id} quality={quality:.3f} "
                     f"blocks={verification['total_blocks']} passed={verification['passed']}")

        return {"pair_id": pair.id, "quality": round(quality, 3)}

    except Exception as e:
        logger.debug(f"Auto-staging skipped: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Chat Feedback API — corrections become training pairs
# ---------------------------------------------------------------------------

@app.route("/api/chat/feedback", methods=["POST"])
def chat_feedback():
    """
    Record thumbs up/down on a chat response. Corrections auto-stage as training pairs.

    Body (JSON):
      user_message   str  -- the original user question
      ai_response    str  -- the AI response being rated
      rating         str  -- "up" or "down"
      correction     str  -- (optional) corrected answer for "down" ratings
    """
    import hashlib
    from hiveai.models import ChatFeedback

    body = request.get_json(silent=True) or {}
    user_message = (body.get("user_message") or "").strip()
    ai_response = (body.get("ai_response") or "").strip()
    rating = (body.get("rating") or "").strip().lower()
    correction = (body.get("correction") or "").strip() or None

    if not user_message or not ai_response or rating not in ("up", "down"):
        return jsonify({"error": "user_message, ai_response, and rating (up/down) required"}), 400

    msg_hash = hashlib.sha256(user_message.encode()).hexdigest()

    db = SessionLocal()
    try:
        staged_pair_id = None
        quality = None

        if rating == "down" and correction:
            # Score the correction and stage as training pair
            try:
                from hiveai.lora.distiller import _score_quality
                quality = _score_quality(user_message, correction)
                quality = min(quality + 0.10, 1.0)  # Human correction bonus

                pair = TrainingPair(
                    source="human_correction",
                    topic="chat_feedback",
                    instruction=user_message,
                    response=correction,
                    quality=quality,
                    is_eligible=quality >= 0.55,
                )
                db.add(pair)
                db.flush()
                staged_pair_id = pair.id
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to stage correction pair: {e}")

        elif rating == "up":
            # High-quality AI responses can be staged as verified pairs
            try:
                from hiveai.lora.distiller import _score_quality
                quality = _score_quality(user_message, ai_response)
                if quality >= 0.75:
                    pair = TrainingPair(
                        source="human_verified",
                        topic="chat_feedback",
                        instruction=user_message,
                        response=ai_response,
                        quality=quality,
                        is_eligible=True,
                    )
                    db.add(pair)
                    db.flush()
                    staged_pair_id = pair.id
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to stage verified pair: {e}")

        feedback = ChatFeedback(
            message_hash=msg_hash,
            user_message=user_message,
            ai_response=ai_response,
            rating=rating,
            correction=correction,
            staged_pair_id=staged_pair_id,
        )
        db.add(feedback)
        db.commit()

        result = {"ok": True, "rating": rating, "feedback_id": feedback.id}
        if staged_pair_id:
            result["staged_pair_id"] = staged_pair_id
            result["quality"] = round(quality, 3) if quality else None
        return jsonify(result)

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auto-Improvement status API
# ---------------------------------------------------------------------------

@app.route("/api/auto-improve/status", methods=["GET"])
def auto_improve_status():
    """Return auto-improvement pipeline status."""
    from hiveai.config import AUTO_IMPROVE_ENABLED, AUTO_IMPROVE_MIN_PAIRS

    db = SessionLocal()
    try:
        auto_pending = db.query(TrainingPair).filter(
            TrainingPair.source == "auto_verified",
            TrainingPair.is_eligible == True,
            TrainingPair.lora_version == None,
        ).count()

        total_auto = db.query(TrainingPair).filter(
            TrainingPair.source == "auto_verified",
        ).count()

        used_auto = db.query(TrainingPair).filter(
            TrainingPair.source == "auto_verified",
            TrainingPair.lora_version != None,
        ).count()

        recent = db.query(ChatFeedback).filter(
            ChatFeedback.auto_staged == True,
        ).order_by(ChatFeedback.created_at.desc()).limit(10).all()

        return jsonify({
            "enabled": AUTO_IMPROVE_ENABLED,
            "pending_pairs": auto_pending,
            "total_auto_pairs": total_auto,
            "used_in_training": used_auto,
            "threshold": AUTO_IMPROVE_MIN_PAIRS,
            "ready_for_training": auto_pending >= AUTO_IMPROVE_MIN_PAIRS,
            "recent_stagings": [
                {
                    "id": r.id,
                    "user_message_preview": r.user_message[:100] if r.user_message else "",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "pair_id": r.staged_pair_id,
                }
                for r in recent
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Multi-Source Miner API
# ---------------------------------------------------------------------------

@app.route("/api/miner/status", methods=["GET"])
def miner_status():
    """Multi-source miner status — per-provider stats, rates, health."""
    try:
        from hiveai.lora.miner import get_miner_status
        return jsonify(get_miner_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/miner/toggle", methods=["POST"])
def miner_toggle():
    """Pause/resume the multi-source miner."""
    try:
        from hiveai.lora.miner import toggle_miner
        body = request.get_json(silent=True) or {}
        paused = body.get("paused", True)
        result = toggle_miner(paused)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# LoRA pipeline API
# ---------------------------------------------------------------------------

@app.route("/api/lora/distill", methods=["POST"])
def lora_distill():
    """
    Trigger self-distillation: use Qwen3 to generate training pairs from prompts.

    Body (JSON):
      topics          list[str]  — coding topics to distill (optional, defaults to built-ins)
      pairs_per_topic int        — pairs per topic (default 3, max 6)
      builtin         bool       — if true, run over full built-in topic list
      language        str        — "python" (default), "cpp", or "javascript"
    """
    db = SessionLocal()
    try:
        body = request.get_json(silent=True) or {}
        topics = body.get("topics", [])
        pairs_per_topic = min(int(body.get("pairs_per_topic", 3)), 6)
        use_builtin = body.get("builtin", False)
        language = body.get("language", "python").lower()
        if language not in ("python", "cpp", "rust", "go", "javascript"):
            return jsonify({"error": f"Unsupported language '{language}'. Use: python, cpp, rust, go, javascript"}), 400

        from hiveai.lora.distiller import (
            distill_batch, distill_builtin, distill_hive,
            distill_cpp, distill_rust, distill_go, distill_javascript,
        )

        use_hive = body.get("hive", False)
        use_cpp = body.get("cpp", False) or language == "cpp"
        use_rust = body.get("rust", False) or language == "rust"
        use_go = body.get("go", False) or language == "go"
        use_js = body.get("javascript", False) or language == "javascript"

        if use_cpp:
            results = distill_cpp(pairs_per_topic=pairs_per_topic, db=db)
        elif use_rust:
            results = distill_rust(pairs_per_topic=pairs_per_topic, db=db)
        elif use_go:
            results = distill_go(pairs_per_topic=pairs_per_topic, db=db)
        elif use_js:
            results = distill_javascript(pairs_per_topic=pairs_per_topic, db=db)
        elif use_hive:
            results = distill_hive(pairs_per_topic=pairs_per_topic, db=db)
        elif use_builtin:
            results = distill_builtin(pairs_per_topic=pairs_per_topic, db=db)
        elif topics:
            results = distill_batch(topics, pairs_per_topic=pairs_per_topic, db=db, language=language)
        else:
            return jsonify({"error": "Provide 'topics' list, set 'builtin': true, 'hive': true, 'cpp': true, 'rust': true, 'go': true, or 'javascript': true"}), 400

        eligible = sum(1 for r in results if r.get("is_eligible"))
        return jsonify({
            "generated": len(results),
            "eligible": eligible,
            "pairs": results[:10],  # preview first 10 in response
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/lora/pairs", methods=["GET"])
def lora_pairs():
    """Return counts and recent training pairs from the staging table."""
    db = SessionLocal()
    try:
        from hiveai.models import TrainingPair

        total = db.query(TrainingPair).count()
        eligible = db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count()
        unused = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.lora_version.is_(None)
        ).count()

        # Recent 20 pairs preview
        recent = db.query(TrainingPair).order_by(TrainingPair.created_at.desc()).limit(20).all()
        preview = [
            {
                "id": p.id,
                "source": p.source,
                "topic": p.topic,
                "instruction": p.instruction[:120] + "..." if len(p.instruction) > 120 else p.instruction,
                "quality": round(p.quality, 3),
                "is_eligible": p.is_eligible,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in recent
        ]

        return jsonify({
            "total": total,
            "eligible": eligible,
            "unused_eligible": unused,
            "ready_to_train": unused >= 500,
            "recent": preview,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/lora/export", methods=["POST"])
def lora_export():
    """
    Export eligible training pairs to Alpaca JSONL for LoRA fine-tuning.

    Body (JSON):
      version         str    — version label (default "v1")
      include_books   bool   — also derive pairs from golden books (default true)
      min_quality     float  — minimum quality threshold (default 0.70)
    """
    db = SessionLocal()
    try:
        body = request.get_json(silent=True) or {}
        version = body.get("version", "v1")
        include_books = body.get("include_books", True)
        from hiveai.config import MIN_TRAINING_QUALITY
        min_quality = float(body.get("min_quality", MIN_TRAINING_QUALITY))

        output_dir = os.path.join(WORKSPACE, "loras", "training_data")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"coding_{version}.jsonl")

        from hiveai.lora.exporter import export_training_pairs, derive_and_stage_from_books, export_with_sampling

        use_smart = body.get("smart", False)
        target_count = int(body.get("target_count", 500))

        if include_books:
            staged_from_books = derive_and_stage_from_books(db, min_quality=min_quality)
        else:
            staged_from_books = 0

        if use_smart:
            count = export_with_sampling(db, output_path, target_count=target_count, min_quality=min_quality)
        else:
            count = export_training_pairs(db, output_path, min_quality=min_quality)

        return jsonify({
            "exported": count,
            "staged_from_books": staged_from_books,
            "output_path": output_path,
            "version": version,
            "smart_sampling": use_smart,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/lora/teach", methods=["POST"])
def lora_teach():
    """
    Teach the model new knowledge from pasted text.
    Creates a GoldenBook, distills training pairs, optionally triggers micro-training.

    Body (JSON):
      title       str   -- title/topic of the knowledge
      content     str   -- full text content (markdown, code, plaintext)
      auto_train  bool  -- if true and enough pairs, trigger micro-training
    """
    import hashlib

    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()
    auto_train = body.get("auto_train", False)

    if not title or not content:
        return jsonify({"error": "title and content required"}), 400
    if len(content) < 100:
        return jsonify({"error": "Content too short (minimum 100 characters)"}), 400

    db = SessionLocal()
    try:
        # Create a teaching GoldenBook
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        book = GoldenBook(
            job_id=0,  # no job — direct teaching
            title=title,
            content=content,
            content_hash=content_hash,
            word_count=len(content.split()),
            status="teaching",
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        # Distill training pairs from the text
        from hiveai.lora.distiller import distill_from_text
        pairs = distill_from_text(content, title, db=db)

        eligible = [p for p in pairs if p.get("is_eligible")]
        micro_triggered = False

        # Optionally trigger micro-training
        if auto_train and len(eligible) >= 20:
            try:
                from hiveai.lora.trainer import MIN_PAIRS_MICRO
                from hiveai.lora.exporter import export_training_pairs

                # Export only unused eligible pairs
                output_dir = os.path.join(WORKSPACE, "loras", "training_data")
                os.makedirs(output_dir, exist_ok=True)
                micro_path = os.path.join(output_dir, f"micro_{title[:30].replace(' ', '_')}.jsonl")
                count = export_training_pairs(db, micro_path, min_quality=0.55)

                if count >= MIN_PAIRS_MICRO:
                    # Start micro-training in background thread
                    def _micro_train():
                        from hiveai.lora.trainer import train_lora
                        from hiveai.models import SessionLocal as SL
                        tdb = SL()
                        try:
                            adapter_dir = os.path.join(WORKSPACE, "loras", f"micro_{book.id}")
                            train_lora(micro_path, adapter_dir, f"micro-{book.id}",
                                       db=tdb, force_micro=True)
                        except Exception as e:
                            logging.getLogger(__name__).error(f"Micro-training failed: {e}")
                        finally:
                            tdb.close()

                    threading.Thread(target=_micro_train, daemon=True).start()
                    micro_triggered = True
            except Exception as e:
                logging.getLogger(__name__).warning(f"Auto micro-train failed: {e}")

        return jsonify({
            "book_id": book.id,
            "pairs_generated": len(pairs),
            "pairs_eligible": len(eligible),
            "micro_training_triggered": micro_triggered,
            "pairs_preview": [
                {"instruction": p["instruction"][:120], "quality": p["quality"]}
                for p in pairs[:5]
            ],
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/lora/versions", methods=["GET"])
def lora_versions():
    """Return all LoRA training runs and current pipeline status."""
    db = SessionLocal()
    try:
        from hiveai.lora.trainer import get_training_status
        status = get_training_status(db)
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Adapter Management API — multi-LoRA hot-swap via llama-server
# ---------------------------------------------------------------------------

@app.route("/api/lora/adapters", methods=["GET"])
def lora_adapters_list():
    """List currently loaded LoRA adapters on llama-server."""
    from hiveai.lora.adapter_manager import get_loaded_adapters, get_server_status
    status = get_server_status()
    adapters = get_loaded_adapters() if status["online"] else []
    return jsonify({"server": status, "adapters": adapters})


@app.route("/api/lora/adapters", methods=["POST"])
def lora_adapters_swap():
    """
    Hot-swap LoRA adapters on llama-server.

    Body (JSON):
      adapters  list  -- [{"path": "...", "scale": 1.0}] or [] for base model only
    """
    from hiveai.lora.adapter_manager import set_adapters
    body = request.get_json(silent=True) or {}
    adapters = body.get("adapters", [])
    ok = set_adapters(adapters)
    return jsonify({"success": ok, "active": adapters})


# ---------------------------------------------------------------------------
# Brain Export API — IPFS + Hive publishing
# ---------------------------------------------------------------------------

@app.route("/api/lora/export-brain", methods=["POST"])
def lora_export_brain():
    """
    Export a trained adapter to IPFS.

    Body (JSON):
      version_id  int  -- ID of the LoraVersion to export
    """
    body = request.get_json(silent=True) or {}
    version_id = body.get("version_id")
    if not version_id:
        return jsonify({"error": "version_id required"}), 400

    db = SessionLocal()
    try:
        from hiveai.lora.brain_export import export_brain
        result = export_brain(version_id, db)
        return jsonify(result)
    except ImportError as e:
        return jsonify({"error": f"IPFS not available: {e}. Install ipfshttpclient and start IPFS daemon."}), 503
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/lora/publish-brain", methods=["POST"])
def lora_publish_brain():
    """
    Publish brain export metadata to Hive blockchain.

    Body (JSON):
      version_id  int  -- ID of the LoraVersion
      author      str  -- Hive account to publish from
    """
    body = request.get_json(silent=True) or {}
    version_id = body.get("version_id")
    author = body.get("author")
    if not version_id or not author:
        return jsonify({"error": "version_id and author required"}), 400

    db = SessionLocal()
    try:
        from hiveai.lora.brain_export import publish_brain_to_hive
        result = publish_brain_to_hive(version_id, author, db)
        return jsonify(result)
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/forge")
def forge_mind():
    """The Gnome's Mind Forge — LoRA training pipeline UI."""
    db = SessionLocal()
    try:
        total_pairs = db.query(TrainingPair).count()
        eligible_pairs = db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count()
        unused_pairs = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.lora_version.is_(None)
        ).count()
        lora_count = db.query(LoraVersion).count()
        versions = db.query(LoraVersion).order_by(LoraVersion.created_at.desc()).limit(10).all()
        from hiveai.lora.trainer import MIN_PAIRS_MICRO, MIN_PAIRS_STANDARD
        return render_template("forge.html",
            total_pairs=total_pairs,
            eligible_pairs=eligible_pairs,
            unused_pairs=unused_pairs,
            lora_count=lora_count,
            versions=versions,
            min_pairs_micro=MIN_PAIRS_MICRO,
            min_pairs_standard=MIN_PAIRS_STANDARD,
        )
    finally:
        db.close()


@app.route("/api/lora/mining-status")
def lora_mining_status():
    """Live brain mining status — reads log tail + DB counts for the Forge UI."""
    db = SessionLocal()
    try:
        total = db.query(TrainingPair).count()
        eligible = db.query(TrainingPair).filter(TrainingPair.is_eligible == True).count()

        # Distinct topics mined
        topics_mined = db.query(TrainingPair.topic).distinct().count()

        # Per-topic counts
        from sqlalchemy import func as sqla_func
        topic_rows = db.query(
            TrainingPair.topic,
            sqla_func.count(TrainingPair.id),
            sqla_func.max(TrainingPair.quality),
        ).group_by(TrainingPair.topic).order_by(sqla_func.max(TrainingPair.created_at).desc()).limit(20).all()
        recent_topics = [
            {"topic": t, "pairs": c, "best_quality": round(q, 2) if q else 0}
            for t, c, q in topic_rows
        ]

        # Read last 30 lines of brain_mine.log for live status
        log_lines = []
        log_path = os.path.join(WORKSPACE, "logs", "brain_mine.log")
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                log_lines = [l.rstrip() for l in all_lines[-30:]]
        except FileNotFoundError:
            log_lines = ["No brain_mine.log found — mining not started yet"]

        # Parse current topic from log
        current_topic = None
        phase = None
        for line in reversed(log_lines):
            if "Mining:" in line and current_topic is None:
                current_topic = line.split("Mining:")[-1].strip()
            if "Deep mining:" in line and current_topic is None:
                current_topic = line.split("Deep mining:")[-1].strip()
                phase = "Phase 2 (deep review)"
            if "FAST MODE" in line and phase is None:
                phase = "Phase 1 (fast breadth)"
            if "Phase 2" in line and "Review" in line and phase is None:
                phase = "Phase 2 (deep review)"

        return jsonify({
            "total_pairs": total,
            "eligible_pairs": eligible,
            "topics_mined": topics_mined,
            "total_topics": 187,
            "current_topic": current_topic,
            "phase": phase or "Unknown",
            "recent_topics": recent_topics,
            "log_tail": log_lines[-15:],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


logging.getLogger(__name__).info("LoRA pipeline routes registered: /api/lora/distill, /api/lora/pairs, /api/lora/export, /api/lora/versions, /api/lora/mining-status")


# ---------------------------------------------------------------------------
# Sandbox API
# ---------------------------------------------------------------------------

@app.route("/api/sandbox/run", methods=["POST"])
def sandbox_run():
    """Execute Python code in a sandboxed subprocess."""
    data = request.get_json()
    code = (data.get("code") or "").strip()
    timeout = min(max(int(data.get("timeout", 30)), 1), 60)

    if not code:
        return jsonify({"error": "code is required"}), 400

    from hiveai.sandbox import execute_python
    result = execute_python(code, timeout=timeout)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Evaluation API
# ---------------------------------------------------------------------------

_eval_state = {"running": False, "results": None, "progress": None, "error": None}
_eval_lock = threading.Lock()


def _run_eval_background(model, category, limit):
    """Background eval runner."""
    import json as _json
    from pathlib import Path

    try:
        # Import eval runner functions
        sys_path_added = False
        eval_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if eval_root not in __import__('sys').path:
            __import__('sys').path.insert(0, eval_root)
            sys_path_added = True

        from scripts.run_eval import load_challenges, evaluate_challenge, generate_report, save_report
        import time as _time

        challenges = load_challenges()
        if category:
            challenges = [c for c in challenges if c["category"] == category]
        if limit:
            challenges = challenges[:limit]

        with _eval_lock:
            _eval_state["progress"] = {"total": len(challenges), "completed": 0, "current": None}

        t_start = _time.time()
        results = []
        for i, challenge in enumerate(challenges):
            with _eval_lock:
                _eval_state["progress"]["current"] = challenge["id"]
                _eval_state["progress"]["completed"] = i

            result = evaluate_challenge(challenge, model)
            results.append(result)

        elapsed = _time.time() - t_start
        report = generate_report(results, model, elapsed)
        report_path = save_report(report)

        with _eval_lock:
            _eval_state["running"] = False
            _eval_state["results"] = report
            _eval_state["progress"]["completed"] = len(challenges)
            _eval_state["progress"]["current"] = None
            _eval_state["progress"]["report_path"] = str(report_path)

    except Exception as e:
        logging.getLogger(__name__).error(f"Eval failed: {e}")
        with _eval_lock:
            _eval_state["running"] = False
            _eval_state["error"] = str(e)


@app.route("/api/eval/run", methods=["POST"])
def eval_run():
    """Trigger an evaluation run in a background thread."""
    with _eval_lock:
        if _eval_state["running"]:
            return jsonify({"error": "Evaluation already running"}), 409

    data = request.get_json() or {}
    model = data.get("model")
    if not model:
        from hiveai.config import OLLAMA_MODEL_FAST
        model = OLLAMA_MODEL_FAST

    category = data.get("category")
    limit = data.get("limit")

    with _eval_lock:
        _eval_state["running"] = True
        _eval_state["results"] = None
        _eval_state["error"] = None
        _eval_state["progress"] = {"total": 0, "completed": 0, "current": None}

    t = threading.Thread(target=_run_eval_background, args=(model, category, limit), daemon=True)
    t.start()

    return jsonify({"status": "started", "model": model, "category": category, "limit": limit})


@app.route("/api/eval/status")
def eval_status():
    """Get current evaluation status."""
    with _eval_lock:
        return jsonify({
            "running": _eval_state["running"],
            "progress": _eval_state["progress"],
            "error": _eval_state["error"],
            "has_results": _eval_state["results"] is not None,
        })


@app.route("/api/eval/results")
def eval_results():
    """Get the latest evaluation results."""
    with _eval_lock:
        if _eval_state["results"]:
            return jsonify(_eval_state["results"])
    return jsonify({"error": "No results available"}), 404


@app.route("/api/eval/reports")
def eval_reports():
    """List saved evaluation reports."""
    evals_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals")
    if not os.path.exists(evals_dir):
        return jsonify([])

    reports = []
    for f in sorted(os.listdir(evals_dir), reverse=True):
        if f.endswith(".json"):
            fpath = os.path.join(evals_dir, f)
            try:
                import json as _json
                with open(fpath, "r") as fp:
                    data = _json.load(fp)
                reports.append({
                    "filename": f,
                    "model": data.get("model"),
                    "overall_score": data.get("overall_score"),
                    "total_challenges": data.get("total_challenges"),
                    "timestamp": data.get("timestamp"),
                })
            except Exception:
                reports.append({"filename": f, "error": "Could not parse"})
    return jsonify(reports)


logging.getLogger(__name__).info("Sandbox + Eval routes registered: /api/sandbox/run, /api/eval/run, /api/eval/status, /api/eval/results, /api/eval/reports")


@app.route("/eval")
def eval_page():
    """Evaluation dashboard — run evals, view results, compare models."""
    return render_template("eval.html")


if __name__ == "__main__":
    from hiveai.models import init_db
    init_db()
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
