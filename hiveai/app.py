import os
import re
import json
import logging
import threading
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response
from sqlalchemy import func
from hiveai.models import init_db, SessionLocal, Job, GoldenBook, GraphTriple, CrawledPage, Chunk, BookSection, SystemConfig, TrainingPair, LoraVersion, ChatFeedback, Community, HiveKnown, TelemetryEvent, utcnow
from hiveai.llm.client import reason, fast, smart_call, embed_text, clean_llm_response, stream_llm_call
from sqlalchemy import text as sa_text
from hiveai.llm.prompts import CHAT_SYSTEM_PROMPT, KNOWLEDGE_GAP_PROMPT, ANSWER_CHECK_PROMPT, EXECUTABLE_CODE_INSTRUCTION, EXECUTABLE_REPAIR_PROMPT
from hiveai.chat import search_knowledge_sections, build_conversation_context, build_message_array, clean_topic, trigger_auto_learn, get_compressed_knowledge, budget_context
from skills.skill_loader import load_skills_for_query
from hiveai.orchestrator import classify_request, should_retry_verification, build_revision_prompt

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

        _ce_start = _t.time()
        from hiveai.llm.client import _get_cross_encoder
        _get_cross_encoder()
        _log.info(f"Cross-encoder warmed up ({_t.time() - _ce_start:.0f}s)")

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
        MIN_TRAINING_QUALITY, LORA_EXPORT_QUALITY, CHAT_VERIFY_CODE,
        RUNTIME_MODE, LLM_CTX_SIZE, OLLAMA_BASE_URL, LLAMA_SERVER_BASE_URL,
    )
    checks["config"] = {
        "hardware_profile": HARDWARE_PROFILE,
        "db_backend": DB_BACKEND,
        "llm_backend": LLM_BACKEND,
        "min_training_quality": MIN_TRAINING_QUALITY,
        "lora_export_quality": LORA_EXPORT_QUALITY,
        "chat_verify_code": CHAT_VERIFY_CODE,
    }

    # --- Runtime mode (what the process is actually doing) ---
    try:
        from hiveai.llm.client import get_active_backend
        _resolved_backend = get_active_backend()
    except Exception:
        _resolved_backend = "unknown"
    checks["runtime"] = {
        "mode": RUNTIME_MODE,
        "ctx_size": LLM_CTX_SIZE,
        "configured_backend": LLM_BACKEND,
        "resolved_backend": _resolved_backend,
        "ollama_endpoint": OLLAMA_BASE_URL,
        "llama_server_endpoint": LLAMA_SERVER_BASE_URL,
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
        try:
            from hiveai.chat import get_compaction_metrics
            cm = get_compaction_metrics()
            stats["compaction"] = {
                "compression_ratio": cm.get("avg_compression_ratio", 0),
                "cache_hit_rate": cm.get("cache_hit_rate", 0),
                "total_compactions": cm.get("compactions", 0),
            }
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
    from hiveai.config import LLM_BACKEND, OPENROUTER_API_KEY, OLLAMA_BASE_URL, LLAMA_SERVER_BASE_URL
    backend = get_active_backend()
    # Check llama-server connectivity for health bar
    import requests as _req
    llm_online = False
    try:
        r = _req.get(f"{LLAMA_SERVER_BASE_URL}/health", timeout=3)
        llm_online = r.status_code == 200
    except Exception:
        pass
    return jsonify({
        "online": llm_online,
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
            "online": match and embedding_count > 0,
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
    import time as _time
    t_start = _time.perf_counter()

    data = request.get_json()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # --- Step 1: Classify request (zero GPU cost, <1ms) ---
    classify = classify_request(message, history)
    t_classify = _time.perf_counter()

    # --- Telemetry: 3-arm assignment ---
    from hiveai.config import TELEMETRY_ENABLED, TELEMETRY_HOLDOUT_SURFACE_PCT, TELEMETRY_NO_INJECTION_PCT
    from hiveai.telemetry import (
        assign_experiment_group, generate_answer_id, generate_request_id, generate_attempt_id,
        classify_workflow, detect_language, best_confidence_band,
        log_telemetry_event, is_internal_traffic,
        should_inject_memory, should_show_surface,
    )
    _telem_session_id = data.get("session_id") or str(uuid.uuid4())
    _telem_request_id = generate_request_id()
    _telem_answer_id = generate_answer_id()
    _telem_attempt_id = generate_attempt_id()
    _telem_group = assign_experiment_group(_telem_session_id, TELEMETRY_HOLDOUT_SURFACE_PCT, TELEMETRY_NO_INJECTION_PCT) if TELEMETRY_ENABLED else "treatment"
    _telem_inject_memory = should_inject_memory(_telem_group)
    _telem_user_agent = request.headers.get("User-Agent", "")
    _telem_is_internal = is_internal_traffic(_telem_session_id, _telem_user_agent)
    _telem_frontend_build = data.get("frontend_build") or request.headers.get("X-Frontend-Build")

    db = SessionLocal()
    try:
        from hiveai.llm.client import LLMProviderUnavailable
        books = db.query(GoldenBook).all()

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

        # --- Step 2: Retrieval (if needed) ---
        top_sections = []
        source_books = []
        knowledge_context = ""
        _entity_sections = []
        _retrieval_trace = {}

        _crag_verdict = "correct"
        _retrieval_confidence = {"band": "none", "score": 0.0, "section_count": 0, "crag_verdict": "correct"}

        if classify.needs_retrieval:
            top_sections, source_books, all_books = search_knowledge_sections(
                message, db, history=history, retrieval_mode=classify.retrieval_mode,
                trace=_retrieval_trace)

            # Shadow reranker: score all retrieved sections (log only, no enforcement)
            from hiveai.config import RERANKER_SHADOW_ENABLED
            if RERANKER_SHADOW_ENABLED and top_sections:
                try:
                    from hiveai.llm.client import compute_shadow_reranker_scores
                    import time as _shadow_time
                    _shadow_t0 = _shadow_time.perf_counter()
                    _shadow_result = compute_shadow_reranker_scores(message, top_sections)
                    _shadow_t1 = _shadow_time.perf_counter()
                    _shadow_result["reranker_shadow_latency_ms"] = round((_shadow_t1 - _shadow_t0) * 1000, 1)
                    _retrieval_trace.update(_shadow_result)
                except Exception as _shadow_err:
                    logging.getLogger(__name__).debug(f"Shadow reranker skipped: {_shadow_err}")
                    _retrieval_trace["reranker_shadow_applied"] = False
                    _retrieval_trace["reranker_shadow_reason"] = str(_shadow_err)[:200]

            # --- Phase 3: CRAG retrieval judge ---
            from hiveai.config import ENABLE_CRAG
            if ENABLE_CRAG and top_sections:
                try:
                    from hiveai.rag.retrieval_judge import judge_retrieval, INCORRECT, AMBIGUOUS
                    _crag_verdict = judge_retrieval(message, top_sections)
                    if _crag_verdict == INCORRECT:
                        top_sections = []
                        knowledge_context = ""
                        source_books = []
                    elif _crag_verdict == AMBIGUOUS:
                        try:
                            from hiveai.config import ENABLE_HYDE
                            if ENABLE_HYDE:
                                from hiveai.rag.hyde import generate_hyde_embedding
                                from hiveai.rag.fusion import rrf_merge
                                from hiveai.vectorstore import hybrid_search as _hs
                                hyde_emb = generate_hyde_embedding(message)
                                if hyde_emb:
                                    hyde_sections = _hs(db, message, hyde_emb, limit=8)
                                    if hyde_sections:
                                        top_sections = rrf_merge([top_sections, hyde_sections], limit=12)
                        except Exception:
                            pass
                except Exception as e:
                    logging.getLogger(__name__).warning(f"CRAG judge failed: {e}")

            # Split entity lane before main context budgeting
            _entity_sections = [s for s in top_sections if s.get("is_entity")]
            # 3-arm experiment: no_injection strips solved examples from context
            _ctx_sections = [s for s in top_sections if not s.get("is_entity")]
            if not _telem_inject_memory:
                _ctx_sections = [s for s in _ctx_sections if not s.get("is_solved_example")]

            # --- Phase 3: Contextual compression for tight-budget mode ---
            _is_exec = classify.response_contract == "executable_code"
            if _is_exec and _ctx_sections:
                try:
                    from hiveai.rag.compressor import compress_sections
                    _ctx_sections = compress_sections(message, _ctx_sections, max_compress=3)
                except Exception:
                    pass  # compression is best-effort

            _ctx_budget = 1200 if _is_exec else 4000
            knowledge_context = budget_context(_ctx_sections, message, max_tokens=_ctx_budget, executable_mode=_is_exec)

            # Suppression gate: don't inject noise when all retrieved sections are low-confidence
            _suppression_reason = None
            if knowledge_context and _ctx_sections:
                from hiveai.config import RETRIEVAL_SUPPRESS_THRESHOLD
                _ret_best = max((s.get("relevance_score", 0) for s in _ctx_sections), default=0.0)
                if _ret_best < RETRIEVAL_SUPPRESS_THRESHOLD:
                    logging.getLogger(__name__).info(f"Retrieval suppressed (preinject): best_score={_ret_best:.3f} below threshold")
                    knowledge_context = ""
                    _suppression_reason = "below_threshold"

            _compressed_used = False
            if knowledge_context:
                book_ids = list(set(s.get("book_id") for s in top_sections if s.get("book_id")))
                compressed = get_compressed_knowledge(book_ids, db)
                if compressed:
                    knowledge_context = f"=== Dense Knowledge Map ===\n{compressed}\n\n=== Detailed Sections ===\n{knowledge_context}"
                    _compressed_used = True

            # Finalize retrieval trace
            _retrieval_trace.update({
                "trace_schema_version": 3,
                "retrieval_suppressed": _suppression_reason is not None,
                "suppression_reason": _suppression_reason,
                "final_best_score": round(
                    max((s.get("relevance_score", 0) for s in _ctx_sections), default=0.0), 4),
                "hard_section_count": len(_ctx_sections),
                "hard_context_present": bool(knowledge_context),
                "top_section_books": list(dict.fromkeys(
                    s.get("book_title", "") for s in _ctx_sections[:3] if s.get("book_title")))[:3],
                "hard_section_refs": [
                    {"id": s.get("id"), "header": (s.get("header") or "")[:80]}
                    for s in _ctx_sections[:5] if s.get("id")
                ],
                "entities_retrieved": len(_entity_sections),
                "entity_ids": [s.get("id") for s in _entity_sections if s.get("id")],
                "soft_entity_lane_used": bool(_entity_sections),
                "compressed_knowledge_used": _compressed_used,
            })

            # --- Phase 3: Compute retrieval confidence ---
            try:
                from hiveai.rag.confidence import compute_confidence
                _retrieval_confidence = compute_confidence(top_sections, _crag_verdict)
            except Exception:
                pass

        t_retrieval = _time.perf_counter()

        # --- Solved-example reuse detection ---
        _solved_sections_retrieved = [
            s for s in top_sections if s.get("is_solved_example")
        ]

        # --- Step 3: Build prompt ---
        skill_context = load_skills_for_query(message)
        skill_block = f"\n\n{skill_context}" if skill_context else ""

        # Build entity context block (soft background, separate from authoritative sections)
        _entity_context = ""
        if _entity_sections:
            _ent_blocks = []
            for _es in _entity_sections[:3]:
                _ent_blocks.append(
                    f"[{_es.get('entity_type', 'concept')}] {_es.get('header', '')}: {_es.get('content', '')}"
                )
            _entity_context = "\n".join(_ent_blocks)

        if knowledge_context:
            system_prompt = f"""{CHAT_SYSTEM_PROMPT}
{skill_block}

Your knowledge sections (from verified Golden Books):
{knowledge_context}

Answer using ONLY the knowledge sections above. If you lack knowledge, respond with KNOWLEDGE_GAP: <topic>"""
        else:
            system_prompt = f"""{CHAT_SYSTEM_PROMPT}
{skill_block}

Answer the question directly and helpfully."""

        if _entity_context:
            system_prompt += f"\n\nProject context (background patterns, not authoritative):\n{_entity_context}"

        # Inject executable output contract if needed
        if classify.response_contract == "executable_code":
            system_prompt += EXECUTABLE_CODE_INSTRUCTION

        chat_messages = build_message_array(system_prompt, history, user_message=message)

        # --- Step 4: Generate ---
        response = smart_call("", question=message,
                             messages=chat_messages,
                             num_sections=len(top_sections), max_tokens=4096)
        response = clean_llm_response(response)

        # --- Step 4b: One-shot repair for truncated executable JSON ---
        _parse_status = "none"
        if classify.response_contract == "executable_code" and '"code"' in response:
            from hiveai.sandbox import _try_json_code_contract
            _json_blocks, _ps = _try_json_code_contract(response)
            _parse_status = _ps
            if _ps == "truncated":
                _repair_logger = logging.getLogger("hiveai.repair")
                _repair_logger.info("Truncated JSON detected — attempting one-shot repair")
                repair_messages = chat_messages + [
                    {"role": "assistant", "content": response},
                    {"role": "user", "content": EXECUTABLE_REPAIR_PROMPT},
                ]
                repaired = smart_call("", messages=repair_messages, max_tokens=2048)
                repaired = clean_llm_response(repaired)
                _repaired_blocks, _rps = _try_json_code_contract(repaired)
                if _repaired_blocks and _rps == "complete":
                    response = repaired
                    _parse_status = "repaired"
                    _repair_logger.info("Repair successful — using repaired response")
                else:
                    _repair_logger.info(f"Repair failed (status={_rps}) — keeping original")

        t_generation = _time.perf_counter()

        # --- Step 5: Verify + bounded revision ---
        verified_meta = None
        was_revised = False
        _contract_mode = "none"
        _verifier_mode = "generated_assertions"
        _harness_result = None
        try:
            from hiveai.config import CHAT_VERIFY_CODE
            _verify_logger = logging.getLogger("hiveai.verify")
            _verify_logger.info(f"Verify gate: CHAT_VERIFY_CODE={CHAT_VERIFY_CODE}, needs_verification={classify.needs_verification}, response_len={len(response)}, has_fences={'```' in response}")
            if CHAT_VERIFY_CODE and classify.needs_verification:
                from hiveai.sandbox import verify_response_code, extract_code_blocks
                from hiveai.canonical_harness import match_harness, run_harness

                # Check for canonical harness FIRST — try detected language, fall back to python
                blocks = extract_code_blocks(response)
                _block_lang = blocks[0].get("language", "python") if blocks else "python"
                _harness_match = match_harness(message, language=_block_lang)
                if not _harness_match and _block_lang != "python":
                    _harness_match = match_harness(message, language="python")
                if _harness_match:
                    _verifier_mode = _harness_match.mode
                    if _harness_match.mode == "no_verdict":
                        _verify_logger.info(f"Harness {_harness_match.harness_id}: no_verdict ({_harness_match.reason})")
                        _contract_mode = "none"
                        _harness_result = {"passed": None, "mode": "no_verdict", "harness_id": _harness_match.harness_id, "reason": _harness_match.reason}
                    else:
                        _contract_mode = blocks[0].get("contract", "fenced") if blocks else "none"
                        if blocks:
                            solution_code = blocks[0].get("code_only", blocks[0]["code"])
                            _harness_result = run_harness(solution_code, _harness_match, timeout=15)
                            _verify_logger.info(f"Harness {_harness_match.harness_id}: passed={_harness_result['passed']}, mode={_harness_result['mode']}")

                # Fall back to model-authored verification if no harness or harness is no_verdict
                if _harness_match and _harness_match.mode not in ("no_verdict",) and _harness_result:
                    # Use harness result instead of model-authored verification
                    verification = {
                        "total_blocks": 1 if _harness_result.get("passed") is not None else 0,
                        "passed": 1 if _harness_result.get("passed") else 0,
                        "failed": 0 if _harness_result.get("passed") else 1,
                        "contract_mode": _contract_mode,
                    }
                else:
                    verification = verify_response_code(response, timeout=15)
                    _contract_mode = verification.get("contract_mode", _contract_mode)

                _verify_logger.info(f"Verification result: blocks={verification['total_blocks']}, passed={verification['passed']}, failed={verification['failed']}, verifier_mode={_verifier_mode}")
                if verification["total_blocks"] > 0:
                    verified_meta = {
                        "blocks": verification["total_blocks"],
                        "passed": verification["passed"],
                        "failed": verification["failed"],
                    }

                    # Bounded revision: retry once for fixable errors
                    if verification["failed"] > 0 and should_retry_verification(verification):
                        revision_prompt = build_revision_prompt(verification)
                        revision_messages = chat_messages + [
                            {"role": "assistant", "content": response},
                            {"role": "user", "content": revision_prompt},
                        ]
                        revised = smart_call("", messages=revision_messages, max_tokens=4096)
                        revised = clean_llm_response(revised)
                        reverify = verify_response_code(revised, timeout=15)  # clean no longer strips code fences

                        # Accept revision only if it's actually better
                        if reverify.get("failed", 999) < verification["failed"]:
                            response = revised
                            verification = reverify
                            was_revised = True
                            verified_meta = {
                                "blocks": reverify["total_blocks"],
                                "passed": reverify["passed"],
                                "failed": reverify["failed"],
                                "revised": True,
                            }
                            logging.getLogger(__name__).info(
                                f"Revision improved: {verification['failed']}→{reverify['failed']} failures"
                            )

                    # Warn if still failing after revision attempt
                    if verified_meta.get("failed", 0) > 0 and verified_meta.get("passed", 0) == 0:
                        response += (
                            "\n\n> **Note:** Automated code verification detected potential issues. "
                            "Please test the code carefully before using in production."
                        )
        except Exception as e:
            logging.getLogger(__name__).error(f"Code verification failed: {type(e).__name__}: {e}", exc_info=True)

        t_verify = _time.perf_counter()

        # --- Step 6: Auto-stage verified pairs ---
        auto_staged = None
        if verified_meta and verified_meta.get("failed", 1) == 0 and verified_meta.get("passed", 0) > 0:
            try:
                auto_staged = _auto_stage_verified_pair(message, response, verification, db)
            except Exception as e:
                logging.getLogger(__name__).error(f"Auto-stage failed: {type(e).__name__}: {e}", exc_info=True)

        # --- Track solved-example reuse ---
        if _solved_sections_retrieved:
            try:
                _reuse_logger = logging.getLogger("hiveai.reuse")
                _verified_pass = bool(verified_meta and verified_meta.get("passed", 0) > 0
                                      and verified_meta.get("failed", 0) == 0)
                for _s in _solved_sections_retrieved:
                    _sid = _s.get("id")
                    if not _sid:
                        continue
                    _sec = db.query(BookSection).filter(BookSection.id == _sid).first()
                    if not _sec or not _sec.keywords_json:
                        continue
                    _meta = json.loads(_sec.keywords_json) if isinstance(_sec.keywords_json, str) else {}
                    _meta.setdefault("reuse", {"retrieved": 0, "verified_pass": 0, "verified_fail": 0, "no_verdict": 0})
                    _meta["reuse"]["retrieved"] += 1
                    # Only count pass/fail when verification actually ran assertions
                    _had_verdict = verified_meta and (verified_meta.get("passed", 0) > 0 or verified_meta.get("failed", 0) > 0)
                    if _had_verdict:
                        if _verified_pass:
                            _meta["reuse"]["verified_pass"] += 1
                        else:
                            _meta["reuse"]["verified_fail"] += 1
                    elif verified_meta:
                        _meta["reuse"]["no_verdict"] = _meta["reuse"].get("no_verdict", 0) + 1
                    _rank = next((i + 1 for i, s in enumerate(top_sections) if s.get("id") == _sid), None)
                    _meta["reuse"].setdefault("ranks", [])
                    if _rank:
                        _meta["reuse"]["ranks"].append(_rank)
                        # Keep last 20 ranks
                        _meta["reuse"]["ranks"] = _meta["reuse"]["ranks"][-20:]
                    _sec.keywords_json = json.dumps(_meta)
                db.commit()
                _reuse_logger.info(
                    f"Reuse tracked: {len(_solved_sections_retrieved)} solved example(s), "
                    f"verified_pass={_verified_pass}, had_verdict={_had_verdict}"
                )
            except Exception as _e:
                logging.getLogger(__name__).warning(f"Reuse tracking failed (non-critical): {_e}")

        # --- Step 7: Knowledge gap detection ---
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

        t_end = _time.perf_counter()

        # --- Build response with trace ---
        result = {
            "reply": response,
            "sources": source_books,
            "learning": learning_info,
        }
        if verified_meta:
            result["verified"] = verified_meta
        if auto_staged:
            result["auto_staged"] = auto_staged

        # Request trace (for observability — visible in API response)
        result["retrieval_confidence"] = _retrieval_confidence
        result["trace"] = {
            "classification": classify.to_dict(),
            "chunks_considered": len(top_sections),
            "crag_verdict": _crag_verdict,
            "retrieval_confidence": _retrieval_confidence.get("band", "none"),
            "solved_example_retrieved": len(_solved_sections_retrieved) > 0,
            "solved_example_count": len(_solved_sections_retrieved),
            "solved_example_ids": [s.get("id") for s in _solved_sections_retrieved if s.get("id")],
            "retrieval_trace": _retrieval_trace,
            "revised": was_revised,
            "response_contract": classify.response_contract,
            "contract_mode": _contract_mode,
            "verifier_mode": _verifier_mode,
            "harness_id": _harness_result.get("harness_id") if _harness_result else None,
            "parse_status": _parse_status,
            "latency_ms": {
                "classify": round((t_classify - t_start) * 1000, 1),
                "retrieval": round((t_retrieval - t_classify) * 1000, 1),
                "generation": round((t_generation - t_retrieval) * 1000, 1),
                "verification": round((t_verify - t_generation) * 1000, 1),
                "total": round((t_end - t_start) * 1000, 1),
            },
        }

        # MoLoRA domain info (if enabled)
        try:
            from hiveai.config import MOLORA_ENABLED
            if MOLORA_ENABLED:
                from hiveai.lora.molora import classify_domain
                result["domain"] = classify_domain(message)
        except Exception:
            pass

        # --- Telemetry: log event (async, never blocks chat) ---
        if TELEMETRY_ENABLED:
            _has_memory = len(_solved_sections_retrieved) > 0
            log_telemetry_event(
                request_id=_telem_request_id,
                answer_id=_telem_answer_id,
                attempt_id=_telem_attempt_id,
                session_id=_telem_session_id,
                experiment_group=_telem_group,
                memory_available=_has_memory,
                memory_context_injected=(_has_memory and _telem_inject_memory),
                memory_surface_emitted=_has_memory,  # non-streaming always returns inline
                solved_example_count=len(_solved_sections_retrieved),
                solved_example_ids=[s.get("id") for s in _solved_sections_retrieved if s.get("id")] or None,
                workflow_class=classify_workflow(message),
                language_detected=detect_language(message),
                retrieval_mode=classify.retrieval_mode,
                response_contract=classify.response_contract,
                verification_passed=verified_meta.get("passed") if verified_meta else None,
                verification_failed=verified_meta.get("failed") if verified_meta else None,
                verification_total=verified_meta.get("blocks") if verified_meta else None,
                was_revised=was_revised,
                auto_staged=bool(auto_staged),
                auto_promoted=bool(auto_staged and auto_staged.get("promoted")),
                latency_retrieval_ms=round((t_retrieval - t_classify) * 1000, 1),
                latency_generation_ms=round((t_generation - t_retrieval) * 1000, 1),
                latency_verification_ms=round((t_verify - t_generation) * 1000, 1),
                latency_total_ms=round((t_end - t_start) * 1000, 1),
                is_internal=_telem_is_internal,
                verifier_mode=_verifier_mode,
                frontend_build=_telem_frontend_build,
                retrieval_trace=_retrieval_trace or None,
                crag_verdict=_crag_verdict,
                retrieval_confidence_band=_retrieval_confidence.get("band"),
                retrieval_confidence_score=_retrieval_confidence.get("score"),
            )

        result["trace"]["request_id"] = _telem_request_id
        result["trace"]["answer_id"] = _telem_answer_id
        result["trace"]["experiment_group"] = _telem_group
        return jsonify(result)
    except LLMProviderUnavailable as e:
        logging.getLogger(__name__).warning(f"LLM provider unavailable: {e}")
        return jsonify({
            "error": "llm_provider_unavailable",
            "message": f"No LLM provider is currently available ({e.detail}). "
                       f"Please check that Ollama is running or that your API key has credits.",
            "provider": e.provider,
            "detail": e.detail,
        }), 503
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Streaming Chat API (SSE)
# ---------------------------------------------------------------------------

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    Server-Sent Events streaming chat endpoint.

    Orchestrated flow:
      1. Classify request (rule-based, <1ms)
      2. Route: agent mode OR preinject/hybrid
      3. RAG search + context building (if needed)
      4. Stream LLM response
      5. Verify + bounded revision (if needed)
      6. Auto-stage verified pairs

    SSE events:
      event: classify  — classification result (sent first)
      event: sources   — book sources metadata
      data: {"token"}  — each streamed token
      event: verification — code verification results
      event: revision  — revision attempt info
      event: auto_staged — training pair staged
      event: done      — {"full_response": "...", "trace": {...}}
      event: error     — on failure
    """
    data = request.get_json()
    message = (data.get("message") or "").strip()
    history = data.get("history", [])
    # Allow client to force agent mode, but classifier can also trigger it
    force_agent = data.get("agent_mode", False)
    workspace = data.get("workspace", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Classify BEFORE entering the generator (sync, <1ms)
    classify = classify_request(message, history)
    use_agent = force_agent or classify.retrieval_mode == "agent"

    # --- Telemetry: 3-arm assignment (session-level) ---
    from hiveai.config import TELEMETRY_ENABLED, TELEMETRY_HOLDOUT_SURFACE_PCT, TELEMETRY_NO_INJECTION_PCT
    from hiveai.telemetry import (
        assign_experiment_group, generate_answer_id, generate_request_id, generate_attempt_id,
        classify_workflow, detect_language, best_confidence_band,
        log_telemetry_event, is_internal_traffic,
        should_inject_memory, should_show_surface,
    )
    _telem_session_id = data.get("session_id") or str(uuid.uuid4())
    _telem_request_id = generate_request_id()
    _telem_answer_id = generate_answer_id()
    _telem_attempt_id = generate_attempt_id()
    _telem_group = assign_experiment_group(_telem_session_id, TELEMETRY_HOLDOUT_SURFACE_PCT, TELEMETRY_NO_INJECTION_PCT) if TELEMETRY_ENABLED else "treatment"
    _telem_inject_memory = should_inject_memory(_telem_group)
    _telem_show_surface = should_show_surface(_telem_group)
    _telem_user_agent = request.headers.get("User-Agent", "")
    _telem_is_internal = is_internal_traffic(_telem_session_id, _telem_user_agent)
    _telem_frontend_build = data.get("frontend_build") or request.headers.get("X-Frontend-Build")

    def generate():
        import time as _time
        from hiveai.llm.client import LLMProviderUnavailable
        t_start = _time.perf_counter()

        db = SessionLocal()
        try:
            # Send classification as first event
            yield f"event: classify\ndata: {json.dumps(classify.to_dict())}\n\n"

            books = db.query(GoldenBook).all()

            rich_system_prompt = CHAT_SYSTEM_PROMPT  # default; overridden when books exist
            top_sections = []
            _entity_sections = []
            _retrieval_trace = {}
            if not books:
                # No Golden Books yet — stream direct response without RAG
                yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
                no_rag_system = "You are HiveAI, a helpful coding knowledge assistant.\n\nAnswer the question directly and helpfully. Note: The knowledge library is still being built, so this response comes from the base model without RAG context."
                chat_messages = build_message_array(no_rag_system, history, user_message=message)
            else:
                # Retrieval phase (if classifier says we need it)
                source_books = []
                _crag_verdict_s = "correct"
                _retrieval_confidence_s = {"band": "none", "score": 0.0, "section_count": 0, "crag_verdict": "correct"}

                if classify.needs_retrieval:
                    top_sections, source_books, all_books = search_knowledge_sections(
                        message, db, history=history, retrieval_mode=classify.retrieval_mode,
                        trace=_retrieval_trace)
                    yield f"event: sources\ndata: {json.dumps({'sources': source_books})}\n\n"

                    # Shadow reranker: score all retrieved sections (log only)
                    from hiveai.config import RERANKER_SHADOW_ENABLED
                    if RERANKER_SHADOW_ENABLED and top_sections:
                        try:
                            from hiveai.llm.client import compute_shadow_reranker_scores
                            import time as _shadow_time
                            _shadow_t0 = _shadow_time.perf_counter()
                            _shadow_result = compute_shadow_reranker_scores(message, top_sections)
                            _shadow_t1 = _shadow_time.perf_counter()
                            _shadow_result["reranker_shadow_latency_ms"] = round((_shadow_t1 - _shadow_t0) * 1000, 1)
                            _retrieval_trace.update(_shadow_result)
                        except Exception as _shadow_err:
                            logging.getLogger(__name__).debug(f"Shadow reranker skipped: {_shadow_err}")
                            _retrieval_trace["reranker_shadow_applied"] = False
                            _retrieval_trace["reranker_shadow_reason"] = str(_shadow_err)[:200]

                    # --- Phase 3: CRAG retrieval judge ---
                    from hiveai.config import ENABLE_CRAG
                    if ENABLE_CRAG and top_sections:
                        try:
                            from hiveai.rag.retrieval_judge import judge_retrieval, INCORRECT, AMBIGUOUS
                            _crag_verdict_s = judge_retrieval(message, top_sections)
                            if _crag_verdict_s == INCORRECT:
                                top_sections = []
                                knowledge_context = ""
                                source_books = []
                            elif _crag_verdict_s == AMBIGUOUS:
                                try:
                                    from hiveai.config import ENABLE_HYDE
                                    if ENABLE_HYDE:
                                        from hiveai.rag.hyde import generate_hyde_embedding
                                        from hiveai.rag.fusion import rrf_merge
                                        from hiveai.vectorstore import hybrid_search as _hs
                                        hyde_emb = generate_hyde_embedding(message)
                                        if hyde_emb:
                                            hyde_sections = _hs(db, message, hyde_emb, limit=8)
                                            if hyde_sections:
                                                top_sections = rrf_merge([top_sections, hyde_sections], limit=12)
                                except Exception:
                                    pass
                        except Exception as e:
                            logging.getLogger(__name__).warning(f"CRAG judge failed (stream): {e}")

                    # Split entity lane before main context budgeting
                    _entity_sections = [s for s in top_sections if s.get("is_entity")]
                    # 3-arm experiment: no_injection strips solved examples from context
                    # (still retrieves them for latent logging, but withholds from LLM prompt)
                    _ctx_sections = [s for s in top_sections if not s.get("is_entity")]
                    if not _telem_inject_memory:
                        _ctx_sections = [s for s in _ctx_sections if not s.get("is_solved_example")]

                    # --- Phase 3: Contextual compression for tight-budget mode ---
                    _is_exec_s = classify.response_contract == "executable_code"
                    if _is_exec_s and _ctx_sections:
                        try:
                            from hiveai.rag.compressor import compress_sections
                            _ctx_sections = compress_sections(message, _ctx_sections, max_compress=3)
                        except Exception:
                            pass

                    _ctx_budget = 1200 if _is_exec_s else 4000
                    knowledge_context = budget_context(_ctx_sections, message, max_tokens=_ctx_budget, executable_mode=_is_exec_s)

                    # Suppression gate: don't inject noise when all retrieved sections are low-confidence
                    _suppression_reason = None
                    if knowledge_context and _ctx_sections:
                        from hiveai.config import RETRIEVAL_SUPPRESS_THRESHOLD
                        _ret_best = max((s.get("relevance_score", 0) for s in _ctx_sections), default=0.0)
                        if _ret_best < RETRIEVAL_SUPPRESS_THRESHOLD:
                            logging.getLogger(__name__).info(f"Retrieval suppressed (retry): best_score={_ret_best:.3f} below threshold")
                            knowledge_context = ""
                            _suppression_reason = "below_threshold"

                    _compressed_used = False
                    if knowledge_context:
                        book_ids = list(set(s.get("book_id") for s in top_sections if s.get("book_id")))
                        compressed = get_compressed_knowledge(book_ids, db)
                        if compressed:
                            knowledge_context = f"=== Dense Knowledge Map ===\n{compressed}\n\n=== Detailed Sections ===\n{knowledge_context}"
                            _compressed_used = True

                    # Finalize retrieval trace (freeze here — same object snapshot emitted twice)
                    _retrieval_trace.update({
                        "trace_schema_version": 3,
                        "retrieval_suppressed": _suppression_reason is not None,
                        "suppression_reason": _suppression_reason,
                        "final_best_score": round(
                            max((s.get("relevance_score", 0) for s in _ctx_sections), default=0.0), 4),
                        "hard_section_count": len(_ctx_sections),
                        "hard_context_present": bool(knowledge_context),
                        "top_section_books": list(dict.fromkeys(
                            s.get("book_title", "") for s in _ctx_sections[:3] if s.get("book_title")))[:3],
                        "hard_section_refs": [
                            {"id": s.get("id"), "header": (s.get("header") or "")[:80]}
                            for s in _ctx_sections[:5] if s.get("id")
                        ],
                        "entities_retrieved": len(_entity_sections),
                        "entity_ids": [s.get("id") for s in _entity_sections if s.get("id")],
                        "soft_entity_lane_used": bool(_entity_sections),
                        "compressed_knowledge_used": _compressed_used,
                    })
                    # Emit early so retrieval path is observable even if generation later fails
                    yield f"event: retrieval_trace\ndata: {json.dumps(_retrieval_trace)}\n\n"

                    # --- Phase 3: Compute retrieval confidence ---
                    try:
                        from hiveai.rag.confidence import compute_confidence
                        _retrieval_confidence_s = compute_confidence(top_sections, _crag_verdict_s)
                        yield f"event: confidence\ndata: {json.dumps(_retrieval_confidence_s)}\n\n"
                    except Exception:
                        pass

                    skill_context = load_skills_for_query(message)
                    skill_block = f"\n\n{skill_context}" if skill_context else ""

                    rich_system_prompt = f"""{CHAT_SYSTEM_PROMPT}
{skill_block}

Your knowledge sections (from verified Golden Books):
{knowledge_context}

Answer using ONLY the knowledge sections above. If you lack knowledge, respond with KNOWLEDGE_GAP: <topic>"""
                else:
                    yield f"event: sources\ndata: {json.dumps({'sources': []})}\n\n"
                    skill_context = load_skills_for_query(message)
                    skill_block = f"\n\n{skill_context}" if skill_context else ""
                    rich_system_prompt = f"{CHAT_SYSTEM_PROMPT}{skill_block}\n\nAnswer the question directly and helpfully."

                # Entity context block (background patterns, softer framing than main sections)
                if _entity_sections:
                    _ent_blocks = []
                    for _es in _entity_sections[:3]:
                        _ent_blocks.append(
                            f"[{_es.get('entity_type', 'concept')}] {_es.get('header', '')}: {_es.get('content', '')}"
                        )
                    rich_system_prompt += "\n\nProject context (background patterns, not authoritative):\n" + "\n".join(_ent_blocks)

                # Inject executable output contract if needed
                if classify.response_contract == "executable_code":
                    rich_system_prompt += EXECUTABLE_CODE_INSTRUCTION

                chat_messages = build_message_array(rich_system_prompt, history, user_message=message)

            t_retrieval = _time.perf_counter()

            # Solved-example reuse detection
            _solved_sections_retrieved = [
                s for s in top_sections if s.get("is_solved_example")
            ]
            _telem_se_details = []  # initialized for telemetry; populated below if examples found
            if _solved_sections_retrieved:
                _se_ids = [s.get("id") for s in _solved_sections_retrieved if s.get("id")]
                # Enrich with reuse stats for UX surfacing
                _se_details = []
                for _s in _solved_sections_retrieved:
                    _sid = _s.get("id")
                    if not _sid:
                        continue
                    _sec = db.query(BookSection).get(_sid) if _sid else None
                    if _sec and _sec.keywords_json:
                        _meta = json.loads(_sec.keywords_json) if isinstance(_sec.keywords_json, str) else _sec.keywords_json
                        _reuse = _meta.get("reuse", {})
                        _vp = _reuse.get("verified_pass", 0)
                        _vf = _reuse.get("verified_fail", 0)
                        _total = _vp + _vf
                        _pass_rate = round(_vp / max(_total, 1) * 100)
                        _confidence = "high" if _pass_rate >= 85 else "good" if _pass_rate >= 70 else "mixed" if _pass_rate >= 50 else "low"
                        # Extract short label from header
                        _header = _sec.header or ""
                        _label = _header.replace("Solved: ", "").replace("Write a Python function ", "").replace("Write a ", "")[:60]
                        _se_details.append({
                            "id": _sid,
                            "label": _label,
                            "language": _meta.get("language", "python"),
                            "times_verified": _total,
                            "pass_rate": _pass_rate,
                            "confidence": _confidence,
                            "times_retrieved": _reuse.get("retrieved", 0),
                        })
                # Telemetry: capture latent match data before deciding whether to display
                _telem_se_details = list(_se_details)  # saved for telemetry logging
                if _telem_show_surface:
                    yield f"event: solved_examples\ndata: {json.dumps({'retrieved': True, 'count': len(_solved_sections_retrieved), 'ids': _se_ids, 'details': _se_details})}\n\n"

            # ---- Agent mode: tool-use loop ----
            if use_agent:
                from hiveai.agent.runner import run_agent_stream
                for event in run_agent_stream(chat_messages, workspace, base_system=rich_system_prompt):
                    if "token" in event:
                        yield f"data: {json.dumps({'token': event['token']})}\n\n"
                    elif "tool_call" in event:
                        yield f"event: tool_call\ndata: {json.dumps(event['tool_call'])}\n\n"
                    elif "tool_result" in event:
                        yield f"event: tool_result\ndata: {json.dumps(event['tool_result'], default=str)}\n\n"
                    elif "iteration" in event:
                        yield f"event: iteration\ndata: {json.dumps(event)}\n\n"
                    elif "error" in event:
                        yield f"event: error\ndata: {json.dumps({'error': event['error']})}\n\n"
                        return
                    elif event.get("done"):
                        full = clean_llm_response(event.get("full_response", ""))
                        t_end = _time.perf_counter()
                        done_data = {
                            "full_response": full,
                            "trace": {
                                "classification": classify.to_dict(),
                                "mode": "agent",
                                "latency_ms": {"total": round((t_end - t_start) * 1000, 1)},
                            },
                        }
                        yield f"event: done\ndata: {json.dumps(done_data)}\n\n"
                return

            # ---- Normal mode: single-shot stream ----
            for chunk in stream_llm_call("", messages=chat_messages, max_tokens=4096):
                if "error" in chunk:
                    _err_payload = {"error": chunk["error"]}
                    if chunk.get("error_type") == "provider_unavailable":
                        _err_payload["error"] = "llm_provider_unavailable"
                        _err_payload["message"] = f"No LLM provider is currently available. Please check that Ollama is running or that your API key has credits."
                        _err_payload["detail"] = chunk["error"]
                    yield f"event: error\ndata: {json.dumps(_err_payload)}\n\n"
                    return
                if "token" in chunk:
                    yield f"data: {json.dumps({'token': chunk['token']})}\n\n"
                if chunk.get("done"):
                    full = clean_llm_response(chunk.get("full_response", ""))
                    t_generation = _time.perf_counter()

                    # One-shot repair for truncated JSON (streaming path)
                    _parse_status = "none"
                    if classify.response_contract == "executable_code" and '"code"' in full:
                        from hiveai.sandbox import _try_json_code_contract
                        _jb, _ps = _try_json_code_contract(full)
                        _parse_status = _ps
                        if _ps == "truncated":
                            repair_msgs = chat_messages + [
                                {"role": "assistant", "content": full},
                                {"role": "user", "content": EXECUTABLE_REPAIR_PROMPT},
                            ]
                            repaired = smart_call("", messages=repair_msgs, max_tokens=2048)
                            repaired = clean_llm_response(repaired)
                            _rb, _rps = _try_json_code_contract(repaired)
                            if _rb and _rps == "complete":
                                full = repaired
                                _parse_status = "repaired"

                    # Self-verify + bounded revision
                    was_revised = False
                    staged = None
                    _contract_mode = "none"
                    _verifier_mode = "generated_assertions"
                    _harness_result = None
                    verification = None
                    try:
                        from hiveai.config import CHAT_VERIFY_CODE
                        if CHAT_VERIFY_CODE and classify.needs_verification:
                            from hiveai.sandbox import verify_response_code, extract_code_blocks
                            from hiveai.canonical_harness import match_harness, run_harness

                            blocks = extract_code_blocks(full)
                            _block_lang = blocks[0].get("language", "python") if blocks else "python"
                            _harness_match = match_harness(message, language=_block_lang)
                            if not _harness_match and _block_lang != "python":
                                _harness_match = match_harness(message, language="python")
                            if _harness_match:
                                _verifier_mode = _harness_match.mode
                                if _harness_match.mode == "no_verdict":
                                    _contract_mode = "none"
                                    _harness_result = {"passed": None, "mode": "no_verdict", "harness_id": _harness_match.harness_id, "reason": _harness_match.reason}
                                else:
                                    _contract_mode = blocks[0].get("contract", "fenced") if blocks else "none"
                                    if blocks:
                                        solution_code = blocks[0].get("code_only", blocks[0]["code"])
                                        _harness_result = run_harness(solution_code, _harness_match, timeout=15)

                            if _harness_match and _harness_match.mode not in ("no_verdict",) and _harness_result:
                                verification = {
                                    "total_blocks": 1 if _harness_result.get("passed") is not None else 0,
                                    "passed": 1 if _harness_result.get("passed") else 0,
                                    "failed": 0 if _harness_result.get("passed") else 1,
                                    "contract_mode": _contract_mode,
                                }
                            else:
                                verification = verify_response_code(full, timeout=15)
                                _contract_mode = verification.get("contract_mode", _contract_mode)
                            if verification["total_blocks"] > 0:
                                v_data = {
                                    "blocks": verification["total_blocks"],
                                    "passed": verification["passed"],
                                    "failed": verification["failed"],
                                }
                                yield f"event: verification\ndata: {json.dumps(v_data)}\n\n"

                                # Bounded revision: retry once for fixable errors
                                if verification["failed"] > 0 and should_retry_verification(verification):
                                    yield f"event: revision\ndata: {json.dumps({'status': 'retrying', 'fixable_errors': verification['failed']})}\n\n"
                                    revision_prompt = build_revision_prompt(verification)
                                    revision_messages = chat_messages + [
                                        {"role": "assistant", "content": full},
                                        {"role": "user", "content": revision_prompt},
                                    ]
                                    # Stream the revision
                                    revised_parts = []
                                    for rev_chunk in stream_llm_call("", messages=revision_messages, max_tokens=4096):
                                        if "token" in rev_chunk:
                                            revised_parts.append(rev_chunk["token"])
                                            # Don't stream revision tokens — replace full response at done
                                        if rev_chunk.get("done"):
                                            revised = clean_llm_response(rev_chunk.get("full_response", ""))
                                            reverify = verify_response_code(revised, timeout=15)
                                            if reverify.get("failed", 999) < verification["failed"]:
                                                full = revised
                                                verification = reverify
                                                was_revised = True
                                                v_data = {
                                                    "blocks": reverify["total_blocks"],
                                                    "passed": reverify["passed"],
                                                    "failed": reverify["failed"],
                                                    "revised": True,
                                                }
                                                yield f"event: verification\ndata: {json.dumps(v_data)}\n\n"
                                                yield f"event: revision\ndata: {json.dumps({'status': 'improved', 'new_failures': reverify['failed']})}\n\n"
                                            else:
                                                yield f"event: revision\ndata: {json.dumps({'status': 'no_improvement'})}\n\n"

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

                    t_verify = _time.perf_counter()

                    # Track solved-example reuse (streaming path)
                    if _solved_sections_retrieved:
                        try:
                            _v_pass = bool(
                                verification
                                and verification.get("passed", 0) > 0
                                and verification.get("failed", 0) == 0
                            )
                            for _s in _solved_sections_retrieved:
                                _sid = _s.get("id")
                                if not _sid:
                                    continue
                                _sec = db.query(BookSection).filter(BookSection.id == _sid).first()
                                if not _sec or not _sec.keywords_json:
                                    continue
                                _meta = json.loads(_sec.keywords_json) if isinstance(_sec.keywords_json, str) else {}
                                _meta.setdefault("reuse", {"retrieved": 0, "verified_pass": 0, "verified_fail": 0, "no_verdict": 0})
                                _meta["reuse"]["retrieved"] += 1
                                _had_verdict = verification and (verification.get("passed", 0) > 0 or verification.get("failed", 0) > 0)
                                if _had_verdict:
                                    if _v_pass:
                                        _meta["reuse"]["verified_pass"] += 1
                                    else:
                                        _meta["reuse"]["verified_fail"] += 1
                                elif verification:
                                    _meta["reuse"]["no_verdict"] = _meta["reuse"].get("no_verdict", 0) + 1
                                _rank = next((i + 1 for i, s in enumerate(top_sections) if s.get("id") == _sid), None)
                                _meta["reuse"].setdefault("ranks", [])
                                if _rank:
                                    _meta["reuse"]["ranks"].append(_rank)
                                    _meta["reuse"]["ranks"] = _meta["reuse"]["ranks"][-20:]
                                _sec.keywords_json = json.dumps(_meta)
                            db.commit()
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

                    t_end = _time.perf_counter()

                    # --- Telemetry: log event (async, never blocks chat) ---
                    if TELEMETRY_ENABLED:
                        _telem_staged = staged  # may be None or dict
                        _has_memory = len(_solved_sections_retrieved) > 0
                        log_telemetry_event(
                            request_id=_telem_request_id,
                            answer_id=_telem_answer_id,
                            attempt_id=_telem_attempt_id,
                            session_id=_telem_session_id,
                            experiment_group=_telem_group,
                            memory_available=_has_memory,
                            memory_context_injected=(_has_memory and _telem_inject_memory),
                            memory_surface_emitted=(_has_memory and _telem_show_surface),
                            solved_example_count=len(_solved_sections_retrieved),
                            solved_example_ids=[s.get("id") for s in _solved_sections_retrieved if s.get("id")] or None,
                            confidence_band=best_confidence_band(_telem_se_details) if _telem_se_details else None,
                            workflow_class=classify_workflow(message),
                            language_detected=detect_language(message),
                            retrieval_mode=classify.retrieval_mode,
                            response_contract=classify.response_contract,
                            verification_passed=verification.get("passed") if verification else None,
                            verification_failed=verification.get("failed") if verification else None,
                            verification_total=verification.get("total_blocks") if verification else None,
                            was_revised=was_revised,
                            auto_staged=bool(_telem_staged),
                            auto_promoted=bool(_telem_staged and _telem_staged.get("promoted")),
                            latency_retrieval_ms=round((t_retrieval - t_start) * 1000, 1),
                            latency_generation_ms=round((t_generation - t_retrieval) * 1000, 1),
                            latency_verification_ms=round((t_verify - t_generation) * 1000, 1),
                            latency_total_ms=round((t_end - t_start) * 1000, 1),
                            matched_pattern_pass_rates=[d.get("pass_rate") for d in _telem_se_details] if _telem_se_details else None,
                            is_internal=_telem_is_internal,
                            verifier_mode=_verifier_mode,
                            frontend_build=_telem_frontend_build,
                            retrieval_trace=_retrieval_trace or None,
                            crag_verdict=_crag_verdict_s,
                            retrieval_confidence_band=_retrieval_confidence_s.get("band"),
                            retrieval_confidence_score=_retrieval_confidence_s.get("score"),
                        )

                    done_data = {
                        "full_response": full,
                        "retrieval_confidence": _retrieval_confidence_s,
                        "trace": {
                            "classification": classify.to_dict(),
                            "mode": "agent" if use_agent else classify.retrieval_mode,
                            "chunks_considered": len(top_sections),
                            "crag_verdict": _crag_verdict_s,
                            "retrieval_confidence": _retrieval_confidence_s.get("band", "none"),
                            "solved_example_retrieved": len(_solved_sections_retrieved) > 0,
                            "solved_example_count": len(_solved_sections_retrieved),
                            "solved_example_ids": [s.get("id") for s in _solved_sections_retrieved if s.get("id")],
                            "retrieval_trace": _retrieval_trace,
                            "revised": was_revised,
                            "response_contract": classify.response_contract,
                            "contract_mode": _contract_mode,
                            "verifier_mode": _verifier_mode,
                            "harness_id": _harness_result.get("harness_id") if _harness_result else None,
                            "parse_status": _parse_status,
                            "request_id": _telem_request_id,
                            "answer_id": _telem_answer_id,
                            "experiment_group": _telem_group,
                            "latency_ms": {
                                "retrieval": round((t_retrieval - t_start) * 1000, 1),
                                "generation": round((t_generation - t_retrieval) * 1000, 1),
                                "verification": round((t_verify - t_generation) * 1000, 1),
                                "total": round((t_end - t_start) * 1000, 1),
                            },
                        },
                    }
                    yield f"event: done\ndata: {json.dumps(done_data)}\n\n"
        except LLMProviderUnavailable as e:
            logging.getLogger(__name__).warning(f"LLM provider unavailable (stream): {e}")
            yield f"event: error\ndata: {json.dumps({'error': 'llm_provider_unavailable', 'message': f'No LLM provider is currently available ({e.detail}). Please check that Ollama is running or that your API key has credits.', 'provider': e.provider, 'detail': e.detail})}\n\n"
        except Exception as e:
            logging.getLogger(__name__).error(f"Stream chat error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.close()

    return Response(generate(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Solved Example Promotion — verified candidates → retrievable knowledge
# ---------------------------------------------------------------------------

_SOLVED_EXAMPLES_BOOK_TITLE = "Solved Examples :: Verified Code"
_SOLVED_EXAMPLES_JOB_ID = -1  # Synthetic book, no real crawl job


def _extract_and_store_entities(user_message, ai_response, pair_id, primary_lang, quality, db):
    """Extract 1-3 reusable entities from a verified Q&A pair, store as source_type='entity'."""
    import urllib.request
    import json as _json
    import re as _re
    from hiveai.config import (
        ENTITY_MEMORY_ENABLED, ENTITY_MEMORY_MIN_QUALITY, ENTITY_MEMORY_MAX_PER_BOOK,
        LLAMA_SERVER_BASE_URL,
    )
    logger = logging.getLogger("hiveai.promote")

    if not ENTITY_MEMORY_ENABLED or quality < ENTITY_MEMORY_MIN_QUALITY:
        return

    try:
        # Cap total entities per book to prevent noise explosion
        book = _get_or_create_solved_examples_book(db)
        entity_count = db.query(BookSection).filter(
            BookSection.book_id == book.id,
            BookSection.keywords_json.contains('"source_type": "entity"'),
        ).count()
        if entity_count >= ENTITY_MEMORY_MAX_PER_BOOK:
            logger.debug(f"Entity extraction skipped: cap {ENTITY_MEMORY_MAX_PER_BOOK} reached")
            return

        prompt = (
            'Extract 1-3 reusable technical entities from this Q&A. Return JSON array only.\n'
            'Each entity: {"type": "procedure|preference|concept", "name": "<5-10 word label>", '
            '"content": "<50-150 word distillation>", "triggers": ["kw1","kw2","kw3"]}\n'
            'If no clear entities exist, return [].\n\n'
            f'Q: {user_message[:300]}\n'
            f'A: {ai_response[:500]}\n'
            f'Language: {primary_lang}'
        )
        body = _json.dumps({
            "model": "hiveai",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.1,
        }).encode()
        req = urllib.request.Request(
            f"{LLAMA_SERVER_BASE_URL}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = _json.loads(resp.read())
        content_str = raw["choices"][0]["message"]["content"].strip()
        m = _re.search(r'\[.*\]', content_str, _re.DOTALL)
        if not m:
            return
        entities = _json.loads(m.group())
    except Exception as e:
        logger.debug(f"Entity extraction skipped: {e}")
        return  # Never fail promotion because of entity extraction

    stored = 0
    for ent in entities[:3]:
        if not all(k in ent for k in ("type", "name", "content", "triggers")):
            continue
        ent_type = ent["type"] if ent["type"] in ("procedure", "preference", "concept") else "concept"
        try:
            embedding = embed_text(ent["name"] + " " + ent["content"])
            section = BookSection(
                book_id=book.id,
                header=f"[{ent_type}] {ent['name']}",
                content=ent["content"],
                token_count=len(ent["content"].split()),
                keywords_json=_json.dumps({
                    "source_type": "entity",
                    "entity_type": ent_type,
                    "keywords": ent.get("triggers", []),
                    "extracted_from_pair_id": pair_id,
                    "language": primary_lang,
                }),
            )
            section.embedding = embedding
            db.add(section)
            stored += 1
        except Exception as e:
            logger.debug(f"Entity store skipped: {e}")
            continue
    if stored:
        db.flush()
        logger.info(f"Stored {stored} entities from pair_id={pair_id} lang={primary_lang}")


def _get_or_create_solved_examples_book(db):
    """Get or create the synthetic 'Solved Examples' GoldenBook for promoted candidates."""
    book = db.query(GoldenBook).filter(
        GoldenBook.title == _SOLVED_EXAMPLES_BOOK_TITLE,
    ).first()
    if book:
        return book

    import hashlib
    book = GoldenBook(
        job_id=_SOLVED_EXAMPLES_JOB_ID,
        title=_SOLVED_EXAMPLES_BOOK_TITLE,
        content="Automatically promoted solved examples from verified chat responses.",
        content_hash=hashlib.sha256(_SOLVED_EXAMPLES_BOOK_TITLE.encode()).hexdigest(),
        source_count=0,
        word_count=0,
        status="published",
    )
    db.add(book)
    db.flush()
    logging.getLogger("hiveai.promote").info(
        f"Created synthetic book '{_SOLVED_EXAMPLES_BOOK_TITLE}' id={book.id}"
    )
    return book


def promote_candidate_to_knowledge(
    user_message: str,
    ai_response: str,
    pair_id: int,
    quality: float,
    verification: dict,
    code_complexity: dict,
    content_hash: str,
    db,
):
    """
    Promote a verified training candidate into a retrievable BookSection.

    Creates a distilled solved-example record in the synthetic 'Solved Examples'
    book, embedded in the same BGE-M3 space as golden book sections so the RAG
    pipeline can retrieve it for similar future queries.

    Returns the BookSection id on success, or None if promotion was skipped/failed.
    """
    from hiveai.config import AUTO_PROMOTE_VERIFIED, AUTO_PROMOTE_MIN_QUALITY, AUTO_PROMOTE_MIN_CODE_LINES
    logger = logging.getLogger("hiveai.promote")

    if not AUTO_PROMOTE_VERIFIED:
        return None

    # Stricter gate than staging
    if quality < AUTO_PROMOTE_MIN_QUALITY:
        logger.debug(f"Promotion skipped: quality {quality:.3f} < {AUTO_PROMOTE_MIN_QUALITY}")
        return None

    if code_complexity.get("lines", 0) < AUTO_PROMOTE_MIN_CODE_LINES:
        logger.debug(f"Promotion skipped: {code_complexity.get('lines', 0)} lines < {AUTO_PROMOTE_MIN_CODE_LINES}")
        return None

    try:
        import re as _re

        # --- Distill into structured solved-example format ---
        # Extract code blocks from response
        code_fences = _re.findall(r'```(\w*)\n(.*?)```', ai_response, _re.DOTALL)

        # Detect primary language
        languages = [lang for lang, _ in code_fences if lang]
        primary_lang = languages[0] if languages else "python"

        # Build code section (all blocks concatenated)
        code_parts = []
        for lang, code in code_fences:
            code_parts.append(code.strip())
        code_body = "\n\n".join(code_parts)

        # Verifier result summary
        v_passed = verification.get("passed", 0)
        v_total = verification.get("total_blocks", 0)
        has_asserts = code_complexity.get("has_assertions", False)
        verifier_type = "assertions pass" if has_asserts else "execution pass"

        # Distilled content — structured for good retrieval
        header = f"Solved: {user_message[:200]}"
        content = f"""Problem:
{user_message}

Verified solution ({primary_lang}):
```{primary_lang}
{code_body}
```

Verification: {verifier_type} ({v_passed}/{v_total} blocks)
Quality: {quality:.2f} | Lines: {code_complexity.get('lines', 0)} | Branches: {code_complexity.get('branches', 0)}"""

        # Keywords for BM25 hybrid search
        # Extract meaningful terms from the problem + code
        problem_terms = set()
        for word in user_message.lower().split():
            cleaned = _re.sub(r'[^a-z0-9_]', '', word)
            if len(cleaned) > 2:
                problem_terms.add(cleaned)
        # Add language
        problem_terms.add(primary_lang.lower())
        keywords = list(problem_terms)[:20]

        # Embed using same model as knowledge base
        try:
            embedding = embed_text(user_message + " " + header)
        except Exception:
            logger.warning("Promotion skipped: embedding failed")
            return None

        # Get or create the synthetic book
        book = _get_or_create_solved_examples_book(db)

        # Create BookSection
        section = BookSection(
            book_id=book.id,
            header=header,
            content=content,
            token_count=len(content.split()),
            keywords_json=json.dumps({
                "keywords": keywords,
                "source_type": "solved_example",
                "training_pair_id": pair_id,
                "content_hash": content_hash,
                "verification_status": verifier_type,
                "language": primary_lang,
                "quality_score": quality,
            }),
        )
        section.embedding = embedding

        db.add(section)
        db.flush()

        # Update book stats
        book.source_count = (book.source_count or 0) + 1
        book.word_count = (book.word_count or 0) + len(content.split())

        db.commit()

        logger.info(
            f"Promoted candidate pair_id={pair_id} → BookSection id={section.id} "
            f"book='{_SOLVED_EXAMPLES_BOOK_TITLE}' lang={primary_lang} "
            f"quality={quality:.3f} verifier={verifier_type}"
        )

        # Extract and store cross-session entities (never blocks promotion)
        try:
            _extract_and_store_entities(user_message, ai_response, pair_id, primary_lang, quality, db)
            db.commit()
        except Exception as _ent_err:
            logger.debug(f"Entity extraction post-commit skipped: {_ent_err}")
            try:
                db.rollback()
            except Exception:
                pass

        return section.id

    except Exception as e:
        logger.error(f"Promotion failed: {type(e).__name__}: {e}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None


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
        base_quality = _score_quality(user_message, ai_response)

        # Sandbox-verified code gets a quality floor: passing all assertions IS quality
        # The text-based scorer penalizes short responses, but verified code doesn't need
        # verbose explanations to be high quality training data.
        #
        # Guards against garbage:
        #   1. Code complexity — trivial one-liners don't get the floor
        #   2. Verifier strength — compile-only < tests-pass < multi-assert
        #   3. Prompt complexity — "hello world" prompts rejected
        pass_count = verification.get("passed", 0)

        # --- Guard 1: Code complexity ---
        # Count nontrivial code lines across all passed blocks
        total_code_lines = 0
        total_branches = 0
        has_assertions = False
        for res in verification.get("results", []):
            code = res.get("code_preview", "")
            exec_info = res.get("execution", {})
            if exec_info and exec_info.get("success"):
                # Use full code from response if available, else preview
                preview = code
                total_code_lines += max(1, preview.count(" ") + 1)  # rough proxy from preview
                if "assert" in preview.lower():
                    has_assertions = True

        # Use sandbox's extract_code_blocks (handles unclosed fences)
        import re as _re
        from hiveai.sandbox import extract_code_blocks as _extract_blocks
        _extracted = _extract_blocks(ai_response)
        total_code_lines = 0
        total_branches = 0
        has_assertions = False
        _code_fences = [b["code"] for b in _extracted]  # for content-hash dedupe
        for block_info in _extracted:
            code = block_info["code"]
            lines = [ln for ln in code.strip().splitlines() if ln.strip() and not ln.strip().startswith('#')]
            total_code_lines += len(lines)
            for ln in lines:
                if _re.search(r'\b(if|for|while|match|try|except|catch)\b', ln):
                    total_branches += 1
                if 'assert' in ln.lower():
                    has_assertions = True

        # --- Guard 2: Verifier strength weighting ---
        # compile-only (no assertions, no real test): +0.00
        # execution pass (runs without error): +0.02
        # has assertions: +0.04
        # multiple blocks pass: +0.02 per additional block (max +0.08)
        verifier_bonus = 0.0
        if has_assertions:
            verifier_bonus += 0.04
        else:
            verifier_bonus += 0.02  # execution-only pass
        if pass_count > 1:
            verifier_bonus += min((pass_count - 1) * 0.02, 0.08)

        # --- Guard 3: Prompt complexity ---
        prompt_words = len(user_message.split())
        prompt_complex = prompt_words >= 8  # "hello world" type prompts are < 8 words

        # --- Apply guards ---
        # Minimum 5 nontrivial code lines AND 8+ word prompt to earn the floor
        if total_code_lines >= 5 and prompt_complex:
            verified_floor = 0.78 + verifier_bonus  # 0.80-0.90 depending on strength
        elif total_code_lines >= 3:
            verified_floor = 0.75 + verifier_bonus * 0.5  # reduced floor for simple code
        else:
            verified_floor = 0.0  # trivial code gets no floor — rely on base scorer

        quality = max(base_quality + AUTO_IMPROVE_QUALITY_BONUS, verified_floor)
        quality = min(quality, 1.0)

        logger.info(
            f"Auto-stage quality: base={base_quality:.3f}, verified_floor={verified_floor:.3f}, "
            f"final={quality:.3f} (lines={total_code_lines}, branches={total_branches}, "
            f"assertions={has_assertions}, verifier_bonus={verifier_bonus:.2f}, prompt_words={prompt_words})"
        )

        if quality < MIN_TRAINING_QUALITY:
            logger.info(f"Auto-stage skipped: quality {quality:.3f} < {MIN_TRAINING_QUALITY}")
            return None

        # --- Content-hash exact dedupe ---
        # Normalized hash over instruction + code body + language to catch exact duplicates
        # before the more expensive embedding-based similarity check
        _code_body = "\n".join(sorted(_code_fences))  # reuse fences extracted above
        _content_hash = hashlib.sha256(
            (user_message.strip().lower() + "\n" + _code_body.strip()).encode()
        ).hexdigest()

        existing_hash = db.query(TrainingPair).filter(
            TrainingPair.metadata_json.contains(_content_hash),
        ).first()
        if existing_hash:
            logger.debug(f"Auto-stage skipped: exact content hash duplicate {_content_hash[:12]}")
            return None

        # Embed instruction for dedup + recurrence detection
        try:
            embedding = embed_text(user_message)
        except Exception:
            embedding = None

        # Recurrence-aware dedup: if similar pair exists, bump recurrence instead of creating new
        if embedding is not None:
            from hiveai.vectorstore import cosine_distance
            existing_pairs = db.query(TrainingPair).filter(
                TrainingPair.source.in_(["auto_verified", "human_verified"]),
                TrainingPair.embedding_json.isnot(None),
            ).order_by(TrainingPair.created_at.desc()).limit(200).all()

            for existing in existing_pairs:
                if existing.embedding is not None:
                    dist = cosine_distance(embedding, existing.embedding)
                    if dist < 0.10:  # >0.90 similarity = same question
                        existing.recurrence_count = (existing.recurrence_count or 1) + 1
                        existing.last_seen_at = utcnow()
                        # Update response if new answer is better quality
                        if quality > (existing.quality or 0):
                            existing.response = ai_response
                            existing.quality = quality
                        db.commit()
                        logger.info(
                            f"Recurrence bump: pair id={existing.id} "
                            f"count={existing.recurrence_count} quality={existing.quality:.3f}"
                        )
                        return {
                            "action": "recurrence_bump",
                            "pair_id": existing.id,
                            "recurrence_count": existing.recurrence_count,
                            "quality": round(existing.quality, 3),
                        }

        # No existing match — check broader dedup and create new pair
        from hiveai.lora.dedup import is_duplicate, add_to_cache
        if is_duplicate(user_message, db, quality=quality):
            logger.debug("Auto-stage skipped: duplicate detected")
            return None

        # Create training pair
        _contract_fmt = verification.get("contract_mode")
        _exec_langs = json.dumps(sorted(set(
            b["language"]
            for b in verification.get("results", [])
            if b.get("language")
        )))

        pair = TrainingPair(
            source="auto_verified",
            topic="chat_auto_improve",
            instruction=user_message,
            response=ai_response,
            quality=quality,
            is_eligible=True,
            recurrence_count=1,
            last_seen_at=utcnow(),
            contract_format=_contract_fmt,
            execution_languages=_exec_langs,
            metadata_json=json.dumps({
                "verification": {
                    "total_blocks": verification["total_blocks"],
                    "passed": verification["passed"],
                    "pass_rate": verification.get("overall_pass_rate", 1.0),
                },
                "source_type": "chat_auto_improve",
                "content_hash": _content_hash,
                "code_complexity": {
                    "lines": total_code_lines,
                    "branches": total_branches,
                    "has_assertions": has_assertions,
                },
            }),
        )
        if embedding is not None:
            pair.embedding = embedding

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
        if embedding is not None:
            add_to_cache(embedding, quality=quality)

        logger.info(f"Auto-staged training pair id={pair.id} quality={quality:.3f} "
                     f"blocks={verification['total_blocks']} passed={verification['passed']}")

        # --- Promote to retrievable knowledge (if gates pass) ---
        section_id = promote_candidate_to_knowledge(
            user_message=user_message,
            ai_response=ai_response,
            pair_id=pair.id,
            quality=quality,
            verification=verification,
            code_complexity={
                "lines": total_code_lines,
                "branches": total_branches,
                "has_assertions": has_assertions,
            },
            content_hash=_content_hash,
            db=db,
        )

        result = {"pair_id": pair.id, "quality": round(quality, 3)}
        if section_id:
            result["promoted"] = True
            result["section_id"] = section_id
        return result

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
# Chat Session Persistence & Search API
# ---------------------------------------------------------------------------

@app.route("/api/chat/sessions", methods=["POST"])
def create_chat_session():
    """Create a new chat session. Returns session_id."""
    import uuid
    from hiveai.models import ChatSession
    db = SessionLocal()
    try:
        session = ChatSession(id=str(uuid.uuid4()))
        db.add(session)
        db.commit()
        return jsonify({"session_id": session.id})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/chat/sessions", methods=["GET"])
def list_chat_sessions():
    """List recent chat sessions with titles."""
    from hiveai.models import ChatSession
    db = SessionLocal()
    try:
        sessions = db.query(ChatSession).order_by(
            ChatSession.updated_at.desc()
        ).limit(50).all()
        return jsonify([{
            "id": s.id,
            "title": s.title or "Untitled",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "message_count": len(s.messages),
        } for s in sessions])
    finally:
        db.close()


@app.route("/api/chat/sessions/<session_id>/messages", methods=["POST"])
def save_chat_message(session_id):
    """Save a message to a session. Body: {role, content}."""
    from hiveai.models import ChatSession, ChatMessage
    body = request.get_json(silent=True) or {}
    role = (body.get("role") or "").strip()
    content = (body.get("content") or "").strip()
    if not role or not content:
        return jsonify({"error": "role and content required"}), 400

    db = SessionLocal()
    try:
        session = db.query(ChatSession).get(session_id)
        if not session:
            return jsonify({"error": "session not found"}), 404

        msg = ChatMessage(session_id=session_id, role=role, content=content)
        db.add(msg)

        # Auto-title from first user message
        if not session.title and role == "user":
            session.title = content[:100]

        db.commit()

        # Update FTS index
        try:
            db.execute(
                text("INSERT INTO chat_messages_fts(rowid, content) VALUES (:id, :content)"),
                {"id": msg.id, "content": content}
            )
            db.commit()
        except Exception:
            pass  # FTS table may not exist yet

        return jsonify({"ok": True, "message_id": msg.id})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/chat/sessions/<session_id>/messages", methods=["GET"])
def get_chat_messages(session_id):
    """Get all messages for a session."""
    from hiveai.models import ChatMessage
    db = SessionLocal()
    try:
        messages = db.query(ChatMessage).filter_by(
            session_id=session_id
        ).order_by(ChatMessage.id).all()
        return jsonify([{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in messages])
    finally:
        db.close()


@app.route("/api/chat/search", methods=["GET"])
def search_chat_history():
    """Full-text search across all chat sessions.
    Query param: q=<search terms>
    Returns matching messages grouped by session.
    """
    from hiveai.models import ChatMessage, ChatSession
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"error": "query too short (min 2 chars)"}), 400

    db = SessionLocal()
    try:
        # Try FTS5 search first
        try:
            fts_results = db.execute(
                text("""
                    SELECT cm.id, cm.session_id, cm.role, cm.content, cm.created_at
                    FROM chat_messages_fts fts
                    JOIN chat_messages cm ON cm.id = fts.rowid
                    WHERE chat_messages_fts MATCH :query
                    ORDER BY rank
                    LIMIT 30
                """),
                {"query": query}
            ).fetchall()
        except Exception:
            # FTS table doesn't exist, fall back to LIKE search
            fts_results = db.execute(
                text("""
                    SELECT id, session_id, role, content, created_at
                    FROM chat_messages
                    WHERE content LIKE :pattern
                    ORDER BY id DESC
                    LIMIT 30
                """),
                {"pattern": f"%{query}%"}
            ).fetchall()

        # Group by session
        sessions = {}
        for row in fts_results:
            sid = row[1]
            if sid not in sessions:
                sess = db.query(ChatSession).get(sid)
                sessions[sid] = {
                    "session_id": sid,
                    "title": sess.title if sess else "Untitled",
                    "matches": [],
                }
            sessions[sid]["matches"].append({
                "id": row[0],
                "role": row[2],
                "content": row[3][:300],  # Truncate for preview
                "created_at": row[4].isoformat() if row[4] else None,
            })

        return jsonify(list(sessions.values()))
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


@app.route("/api/compaction/metrics", methods=["GET"])
def compaction_metrics_api():
    """Conversation compaction & context budgeting quality metrics."""
    try:
        from hiveai.chat import get_compaction_metrics
        return jsonify(get_compaction_metrics())
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
# Training Pipeline API (micro-training flywheel)
# ---------------------------------------------------------------------------

@app.route('/api/preflight', methods=['POST'])
def run_preflight():
    """Run pre-flight checks before training"""
    import subprocess
    data = request.json or {}
    cmd = ['python3', 'scripts/preflight_check.py', '--quiet']
    if data.get('data_path'):
        cmd.extend(['--data', data['data_path']])
    if data.get('base_model'):
        cmd.extend(['--base-model', data['base_model']])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return jsonify({
            'exit_code': result.returncode,
            'output': result.stdout,
            'errors': result.stderr,
            'status': 'pass' if result.returncode == 0 else 'warn' if result.returncode == 2 else 'fail'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route("/api/lora/micro-train", methods=["POST"])
def lora_micro_train():
    """Launch a micro-training cycle via WSL in a tmux session."""
    import subprocess as sp
    import shlex
    data = request.get_json() or {}
    domain = data.get("domain", "general")
    data_path = data.get("data_path", "")
    version = data.get("version", "")
    prev_version = data.get("prev_version", "")

    if not data_path or not version:
        return jsonify({"error": "data_path and version are required"}), 400

    # Sanitize inputs (prevent command injection)
    for val in [domain, data_path, version, prev_version]:
        if any(c in val for c in [";", "&", "|", "$", "`", "\n", "'"]):
            return jsonify({"error": "Invalid characters in parameters"}), 400

    # Build the run_full_cycle command
    cycle_cmd = f"bash /opt/hiveai/project/scripts/run_full_cycle.sh {shlex.quote(domain)} {shlex.quote(data_path)} {shlex.quote(version)}"
    if prev_version:
        cycle_cmd += f" {shlex.quote(prev_version)}"

    # Launch in tmux so it survives session closure
    tmux_cmd = f"tmux new-session -d -s hiveai_train '{cycle_cmd}' 2>/dev/null || echo 'tmux session already exists'"
    wsl_cmd = ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", tmux_cmd]

    try:
        sp.Popen(wsl_cmd)
        logging.getLogger(__name__).info(f"Micro-train launched: {version} ({domain})")
        return jsonify({
            "status": "launched",
            "version": version,
            "domain": domain,
            "data_path": data_path,
            "tmux_session": "hiveai_train",
        })
    except Exception as e:
        return jsonify({"error": f"Failed to launch training: {e}"}), 500


@app.route("/api/lora/training-status")
def lora_training_status():
    """Poll training progress from WSL tmux session."""
    import subprocess as sp
    result = {"active": False, "stage": None, "step": None, "total_steps": None,
              "loss": None, "eta": None, "summary": None, "log_tail": []}
    try:
        # Check if any training tmux session exists
        # Training runs under various session names: hiveai_train, v5resume, auto_queue, etc.
        check = sp.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "tmux list-sessions 2>/dev/null | grep -qiE 'train|v[0-9]|auto_queue' && echo ACTIVE || echo INACTIVE"],
            capture_output=True, text=True, timeout=5,
        )
        if "ACTIVE" not in check.stdout:
            return jsonify(result)

        result["active"] = True

        # Read latest log — find most recently modified log file
        log_result = sp.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "ls -t /opt/hiveai/project/logs/auto_queue_*/*.log /opt/hiveai/project/logs/*.log "
             "/opt/hiveai/project/logs/*/train.log 2>/dev/null | head -1 | xargs tail -30 2>/dev/null || echo 'no logs'"],
            capture_output=True, text=True, timeout=5,
        )
        log_lines = [l.strip() for l in log_result.stdout.strip().split("\n") if l.strip()]
        result["log_tail"] = log_lines[-20:]

        # Parse step/loss from log
        for line in reversed(log_lines):
            if "step" in line.lower() and "/" in line:
                import re
                step_match = re.search(r'(\d+)/(\d+)', line)
                if step_match:
                    result["step"] = int(step_match.group(1))
                    result["total_steps"] = int(step_match.group(2))
            if "loss" in line.lower() and "=" in line:
                import re
                loss_match = re.search(r'loss[=:\s]+([0-9.]+)', line, re.IGNORECASE)
                if loss_match:
                    result["loss"] = float(loss_match.group(1))

        # Check checkpoint for pipeline stage
        # Checkpoint files are logs/{version}_checkpoint.txt with format: step=N\nversion=...
        chk_result = sp.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "cat /opt/hiveai/project/logs/*_checkpoint.txt 2>/dev/null | head -5"],
            capture_output=True, text=True, timeout=5,
        )
        checkpoint = chk_result.stdout.strip()
        if checkpoint:
            # Parse step=N from checkpoint file
            import re as _re
            step_match = _re.search(r'step=(\d+)', checkpoint)
            version_match = _re.search(r'version=(\S+)', checkpoint)
            if step_match:
                pipeline_step = int(step_match.group(1))
                # Map checkpoint step (1-7) to human-readable stage name
                stage_names = {
                    0: 'preflight', 1: 'replay', 2: 'training', 3: 'converting',
                    4: 'merging', 5: 'consolidating', 6: 'evaluating', 7: 'complete'
                }
                result["stage"] = stage_names.get(pipeline_step, str(pipeline_step))
                result["pipeline_step"] = pipeline_step
            if version_match:
                result["version"] = version_match.group(1)

        # Build summary
        if result["step"] and result["total_steps"]:
            pct = int(100 * result["step"] / result["total_steps"])
            result["summary"] = f"Step {result['step']}/{result['total_steps']} ({pct}%)"
        elif result["stage"]:
            result["summary"] = result["stage"]
        else:
            result["summary"] = "running"

    except Exception as e:
        result["error"] = str(e)

    return jsonify(result)


@app.route("/api/lora/stop-training", methods=["POST"])
def lora_stop_training():
    """Stop the running training tmux session."""
    import subprocess as sp
    try:
        sp.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
             "tmux kill-session -t hiveai_train 2>/dev/null"],
            capture_output=True, timeout=5,
        )
        return jsonify({"status": "stopped"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/lora/list-batches", methods=["GET"])
def lora_list_batches():
    """List available training batch files in datasets/ directory."""
    datasets_dir = os.path.join(WORKSPACE, "datasets")
    batches = []
    if os.path.isdir(datasets_dir):
        for fname in sorted(os.listdir(datasets_dir)):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(datasets_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    pair_count = sum(1 for _ in f)
            except Exception:
                pair_count = 0
            batches.append({
                "filename": fname,
                "path": fpath,
                "pair_count": pair_count,
                "size_kb": round(os.path.getsize(fpath) / 1024, 1),
            })
    return jsonify({"batches": batches})


@app.route("/api/lora/prepare-batches", methods=["POST"])
def lora_prepare_batches():
    """Split a JSONL file into micro-training batches."""
    import subprocess as sp
    data = request.get_json() or {}
    input_path = data.get("input_path", "")
    batch_size = data.get("batch_size", 500)

    if not input_path:
        return jsonify({"error": "input_path is required"}), 400

    script = os.path.join(WORKSPACE, "scripts", "batch_splitter.py")
    if not os.path.exists(script):
        return jsonify({"error": "batch_splitter.py not found"}), 500

    try:
        result = sp.run(
            ["python", script, input_path, "--batch-size", str(batch_size)],
            capture_output=True, text=True, timeout=60,
            cwd=WORKSPACE,
        )
        if result.returncode == 0:
            return jsonify({"status": "ok", "output": result.stdout})
        else:
            return jsonify({"error": result.stderr or result.stdout}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/eval/ledger")
def eval_ledger():
    """Return the score ledger (historical domain scores across versions)."""
    ledger_path = os.path.join(WORKSPACE, "score_ledger.json")
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})


logging.getLogger(__name__).info("Training pipeline routes registered: /api/lora/micro-train, /api/lora/training-status, /api/eval/ledger")


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


# ---------------------------------------------------------------------------
# Critique Pattern Memory — GEM 1 Phase 2 (read-only inspection endpoints)
# ---------------------------------------------------------------------------

@app.route("/api/eval/critique-patterns")
def api_critique_patterns():
    """All critique patterns with outcomes, filterable by domain/probe/status."""
    from hiveai.config import CRITIQUE_MEMORY_ENABLED
    if not CRITIQUE_MEMORY_ENABLED:
        return jsonify({"error": "Critique memory disabled"}), 404
    try:
        from scripts.critique_memory import retrieve_critique_patterns, abandon_stale_critiques
        db = SessionLocal()
        try:
            # Auto-abandon stale critiques on read
            abandon_stale_critiques(db)
            db.commit()

            domain = request.args.get("domain")
            probe_id = request.args.get("probe_id")
            status = request.args.get("status")
            limit = int(request.args.get("limit", "50"))
            patterns = retrieve_critique_patterns(db, domain=domain, probe_id=probe_id,
                                                   status=status, limit=limit)
            return jsonify(patterns)
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"Critique patterns error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/eval/critique-stats")
def api_critique_stats():
    """Summary statistics for critique pattern memory."""
    from hiveai.config import CRITIQUE_MEMORY_ENABLED
    if not CRITIQUE_MEMORY_ENABLED:
        return jsonify({"error": "Critique memory disabled"}), 404
    try:
        from scripts.critique_memory import get_critique_stats
        db = SessionLocal()
        try:
            stats = get_critique_stats(db)
            return jsonify(stats)
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"Critique stats error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/eval/effective-templates")
def api_effective_templates():
    """Template success rates per domain from closed critique patterns."""
    from hiveai.config import CRITIQUE_MEMORY_ENABLED
    if not CRITIQUE_MEMORY_ENABLED:
        return jsonify({"error": "Critique memory disabled"}), 404
    try:
        from scripts.critique_memory import get_effective_templates
        domain = request.args.get("domain")
        if not domain:
            return jsonify({"error": "domain parameter required"}), 400
        db = SessionLocal()
        try:
            templates = get_effective_templates(db, domain)
            return jsonify(templates)
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"Effective templates error: {e}")
        return jsonify({"error": str(e)}), 500


logging.getLogger(__name__).info("Critique memory routes registered: /api/eval/critique-patterns, /api/eval/critique-stats, /api/eval/effective-templates")


# ---------------------------------------------------------------------------
# Bayesian Confidence Calibration — GEM 2 Phase 3 (read-only inspection)
# ---------------------------------------------------------------------------

@app.route("/api/eval/confidence")
def api_confidence_ledger():
    """Full calibration ledger with posteriors, intervals, versioning. Read-only."""
    from hiveai.config import BAYESIAN_CALIBRATION_ENABLED
    if not BAYESIAN_CALIBRATION_ENABLED:
        return jsonify({"error": "Bayesian calibration disabled", "hint": "Set BAYESIAN_CALIBRATION_ENABLED=true"}), 404
    try:
        from scripts.confidence_calibrator import compute_ledger_from_db
        db = SessionLocal()
        try:
            ledger = compute_ledger_from_db(db)
            # Filter by domain if requested
            domain = request.args.get("domain")
            if domain and ledger.get("buckets"):
                ledger["buckets"] = {
                    k: v for k, v in ledger["buckets"].items()
                    if v.get("domain") == domain
                }
                ledger["total_buckets"] = len(ledger["buckets"])
            return jsonify(ledger)
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"Confidence ledger error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/eval/confidence/reliability")
def api_confidence_reliability():
    """Reliability diagram data for calibration validation. Read-only."""
    from hiveai.config import BAYESIAN_CALIBRATION_ENABLED
    if not BAYESIAN_CALIBRATION_ENABLED:
        return jsonify({"error": "Bayesian calibration disabled"}), 404
    try:
        from scripts.confidence_calibrator import validate_from_db
        from datetime import datetime, timezone
        db = SessionLocal()
        try:
            # Use current time as cutoff (fit on all data, no holdout)
            # For real validation, pass a proper cutoff
            cutoff_str = request.args.get("fit_cutoff")
            if cutoff_str:
                cutoff = datetime.fromisoformat(cutoff_str)
                if cutoff.tzinfo is None:
                    cutoff = cutoff.replace(tzinfo=timezone.utc)
            else:
                cutoff = datetime.now(timezone.utc)
            result = validate_from_db(db, fit_cutoff=cutoff)
            return jsonify(result)
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"Confidence reliability error: {e}")
        return jsonify({"error": str(e)}), 500


logging.getLogger(__name__).info("Confidence calibration routes registered: /api/eval/confidence, /api/eval/confidence/reliability")


@app.route("/eval")
def eval_page():
    """Evaluation dashboard — run evals, view results, compare models."""
    return render_template("eval.html")


# ---------------------------------------------------------------------------
# Skill Candidates — review, approve, reject, export staged training pairs
# ---------------------------------------------------------------------------

@app.route("/candidates")
def candidates_page():
    return render_template("candidates.html")


@app.route("/api/candidates")
def list_candidates():
    """List staged training pair candidates with filters."""
    db = SessionLocal()
    try:
        source = request.args.get("source", "")
        sort = request.args.get("sort", "recurrence")
        min_rec = request.args.get("min_recurrence", 1, type=int)

        q = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.source.in_(["auto_verified", "human_verified", "human_correction"]),
        )
        if source:
            q = q.filter(TrainingPair.source == source)
        if min_rec > 1:
            q = q.filter(TrainingPair.recurrence_count >= min_rec)

        if sort == "recurrence":
            q = q.order_by(TrainingPair.recurrence_count.desc(), TrainingPair.quality.desc())
        elif sort == "quality":
            q = q.order_by(TrainingPair.quality.desc())
        else:
            q = q.order_by(TrainingPair.created_at.desc())

        pairs = q.limit(100).all()

        # Stats
        total = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.source.in_(["auto_verified", "human_verified", "human_correction"]),
        ).count()
        high_rec = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.recurrence_count >= 3,
        ).count()

        return jsonify({
            "candidates": [{
                "id": p.id,
                "source": p.source,
                "instruction": p.instruction[:500],
                "response": p.response[:800],
                "quality": round(p.quality or 0, 3),
                "recurrence_count": p.recurrence_count or 1,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
            } for p in pairs],
            "total": total,
            "high_recurrence": high_rec,
        })
    finally:
        db.close()


@app.route("/api/candidates/<int:pair_id>/approve", methods=["POST"])
def approve_candidate(pair_id):
    db = SessionLocal()
    try:
        pair = db.query(TrainingPair).get(pair_id)
        if not pair:
            return jsonify({"error": "Not found"}), 404
        pair.source = "human_verified"
        pair.is_eligible = True
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@app.route("/api/candidates/<int:pair_id>/reject", methods=["POST"])
def reject_candidate(pair_id):
    db = SessionLocal()
    try:
        pair = db.query(TrainingPair).get(pair_id)
        if not pair:
            return jsonify({"error": "Not found"}), 404
        pair.is_eligible = False
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@app.route("/api/candidates/export", methods=["POST"])
def export_candidates():
    """Export approved candidates as JSONL for training."""
    db = SessionLocal()
    try:
        data = request.get_json() or {}
        min_rec = data.get("min_recurrence", 1)
        min_quality = data.get("min_quality", 0.8)

        pairs = db.query(TrainingPair).filter(
            TrainingPair.is_eligible == True,
            TrainingPair.quality >= min_quality,
            TrainingPair.recurrence_count >= min_rec,
        ).order_by(TrainingPair.quality.desc()).all()

        lines = []
        for p in pairs:
            lines.append(json.dumps({
                "instruction": p.instruction,
                "input": "",
                "output": p.response,
            }, ensure_ascii=False))

        content = "\n".join(lines)
        return Response(
            content,
            mimetype="application/jsonl",
            headers={"Content-Disposition": f"attachment; filename=candidates_{len(pairs)}_pairs.jsonl"},
        )
    finally:
        db.close()


@app.route("/api/browse/communities")
def browse_communities():
    """Browse community detection results."""
    db = SessionLocal()
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, request.args.get("per_page", 50, type=int))
        total = db.query(Community).count()
        communities = (db.query(Community)
                       .order_by(Community.created_at.desc())
                       .offset((page - 1) * per_page)
                       .limit(per_page)
                       .all())
        return jsonify({
            "total": total, "page": page, "per_page": per_page,
            "items": [{
                "id": c.id, "job_id": c.job_id,
                "entities": c.entities, "triple_count": c.triple_count,
                "summary": c.summary,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            } for c in communities]
        })
    finally:
        db.close()


@app.route("/api/browse/hive-known")
def browse_hive_known():
    """Browse known Hive blockchain content."""
    db = SessionLocal()
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, request.args.get("per_page", 50, type=int))
        search = request.args.get("q", "").strip()
        query = db.query(HiveKnown)
        if search:
            query = query.filter(
                HiveKnown.title.ilike(f"%{search}%") |
                HiveKnown.author.ilike(f"%{search}%") |
                HiveKnown.permlink.ilike(f"%{search}%")
            )
        total = query.count()
        items = (query.order_by(HiveKnown.discovered_at.desc())
                 .offset((page - 1) * per_page)
                 .limit(per_page)
                 .all())
        return jsonify({
            "total": total, "page": page, "per_page": per_page,
            "items": [{
                "id": h.id, "job_id": h.job_id, "url": h.url,
                "permlink": h.permlink, "author": h.author,
                "title": h.title, "tags": h.tags,
                "discovered_at": h.discovered_at.isoformat() if h.discovered_at else None,
            } for h in items]
        })
    finally:
        db.close()


logging.getLogger(__name__).info("Browse routes registered: /api/browse/communities, /api/browse/hive-known")


# ---------------------------------------------------------------------------
# Memory Scoreboard API
# ---------------------------------------------------------------------------

@app.route("/api/memory/scoreboard")
def memory_scoreboard():
    """Return reuse stats for all promoted solved examples."""
    db = SessionLocal()
    try:
        # Find all sections in the Solved Examples book
        book = db.query(GoldenBook).filter(
            GoldenBook.title == "Solved Examples :: Verified Code"
        ).first()
        if not book:
            return jsonify({"examples": [], "total": 0})

        sections = db.query(BookSection).filter(
            BookSection.book_id == book.id
        ).order_by(BookSection.created_at.desc()).all()

        examples = []
        for s in sections:
            meta = json.loads(s.keywords_json) if s.keywords_json else {}
            reuse = meta.get("reuse", {"retrieved": 0, "verified_pass": 0, "verified_fail": 0})
            ranks = reuse.get("ranks", [])
            examples.append({
                "section_id": s.id,
                "header": s.header,
                "language": meta.get("language", "unknown"),
                "quality_score": meta.get("quality_score"),
                "training_pair_id": meta.get("training_pair_id"),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "times_retrieved": reuse.get("retrieved", 0),
                "verified_pass": reuse.get("verified_pass", 0),
                "verified_fail": reuse.get("verified_fail", 0),
                "avg_rank": round(sum(ranks) / len(ranks), 1) if ranks else None,
                "best_rank": min(ranks) if ranks else None,
            })

        total_retrieved = sum(e["times_retrieved"] for e in examples)
        total_pass = sum(e["verified_pass"] for e in examples)
        total_fail = sum(e["verified_fail"] for e in examples)

        # Telemetry summary (if any events exist)
        telemetry_summary = None
        try:
            telem_count = db.query(TelemetryEvent).count()
            if telem_count > 0:
                treatment_count = db.query(TelemetryEvent).filter(TelemetryEvent.experiment_group == "treatment").count()
                holdout_count = db.query(TelemetryEvent).filter(TelemetryEvent.experiment_group == "holdout").count()
                memory_emitted = db.query(TelemetryEvent).filter(TelemetryEvent.memory_surface_emitted == True).count()  # noqa: E712
                memory_injected = db.query(TelemetryEvent).filter(TelemetryEvent.memory_context_injected == True).count()  # noqa: E712
                memory_avail = db.query(TelemetryEvent).filter(TelemetryEvent.memory_available == True).count()  # noqa: E712
                telemetry_summary = {
                    "total_events": telem_count,
                    "treatment": treatment_count,
                    "holdout": holdout_count,
                    "memory_available": memory_avail,
                    "memory_context_injected": memory_injected,
                    "memory_surface_emitted": memory_emitted,
                    "experiment_active": holdout_count > 0,
                }
        except Exception:
            pass

        return jsonify({
            "examples": examples,
            "total": len(examples),
            "aggregate": {
                "total_retrievals": total_retrieved,
                "total_verified_pass": total_pass,
                "total_verified_fail": total_fail,
                "hit_rate": round(sum(1 for e in examples if e["times_retrieved"] > 0) / max(len(examples), 1), 2),
            },
            "telemetry": telemetry_summary,
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Product Telemetry API
# ---------------------------------------------------------------------------

@app.route("/api/telemetry/product-review")
def telemetry_product_review():
    """Aggregate product telemetry into the A/B review scorecard.

    Returns treatment vs holdout stats across all dimensions:
    confidence band, workflow class, language, verification outcomes.
    """
    from hiveai.telemetry import aggregate_product_review
    db = SessionLocal()
    try:
        return jsonify(aggregate_product_review(db))
    finally:
        db.close()


@app.route("/api/telemetry/snapshot", methods=["POST"])
def telemetry_snapshot():
    """Append current review to product_telemetry_ledger.json (timestamped, append-only)."""
    import os as _os
    from hiveai.telemetry import aggregate_product_review
    db = SessionLocal()
    try:
        review = aggregate_product_review(db)
        if review.get("total_events", 0) == 0:
            return jsonify({"error": "No telemetry data to snapshot"}), 400

        ledger_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "product_telemetry_ledger.json",
        )
        # Load existing ledger or start fresh
        ledger = []
        if _os.path.exists(ledger_path):
            try:
                with open(ledger_path, "r") as f:
                    ledger = json.load(f)
            except (json.JSONDecodeError, IOError):
                ledger = []

        # Add notes if provided
        body = request.get_json(silent=True) or {}
        if body.get("notes"):
            review["notes"] = body["notes"]

        ledger.append(review)

        with open(ledger_path, "w") as f:
            json.dump(ledger, f, indent=2)

        return jsonify({"status": "ok", "snapshots": len(ledger), "path": ledger_path})
    finally:
        db.close()


@app.route("/api/telemetry/events")
def telemetry_events():
    """Return raw telemetry events (paginated). For debugging and export."""
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))
    group = request.args.get("group")  # optional filter: "treatment" or "holdout"

    db = SessionLocal()
    try:
        q = db.query(TelemetryEvent).order_by(TelemetryEvent.created_at.desc())
        if group:
            q = q.filter(TelemetryEvent.experiment_group == group)
        total = q.count()
        events = q.offset(offset).limit(limit).all()

        return jsonify({
            "total": total,
            "offset": offset,
            "limit": limit,
            "events": [
                {
                    "id": e.id,
                    "answer_id": e.answer_id,
                    "session_id": e.session_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "experiment_group": e.experiment_group,
                    "request_id": e.request_id,
                    "attempt_id": e.attempt_id,
                    "parent_answer_id": e.parent_answer_id,
                    "final_answer_id": e.final_answer_id,
                    "is_terminal_attempt": e.is_terminal_attempt,
                    "memory_available": e.memory_available,
                    "memory_context_injected": e.memory_context_injected,
                    "memory_surface_emitted": e.memory_surface_emitted,
                    "solved_example_count": e.solved_example_count,
                    "confidence_band": e.confidence_band,
                    "workflow_class": e.workflow_class,
                    "language_detected": e.language_detected,
                    "retrieval_mode": e.retrieval_mode,
                    "response_contract": e.response_contract,
                    "model_id": e.model_id,
                    "git_sha": e.git_sha,
                    "verifier_mode": e.verifier_mode,
                    "frontend_build": e.frontend_build,
                    "workflow_classifier_version": e.workflow_classifier_version,
                    "language_detector_version": e.language_detector_version,
                    "verification_passed": e.verification_passed,
                    "verification_failed": e.verification_failed,
                    "verification_total": e.verification_total,
                    "was_revised": e.was_revised,
                    "auto_staged": e.auto_staged,
                    "auto_promoted": e.auto_promoted,
                    "details_expanded": e.details_expanded,
                    "pattern_clicked": e.pattern_clicked,
                    "explicit_accept": e.explicit_accept,
                    "implicit_accept_proxy": e.implicit_accept_proxy,
                    "user_retried": e.user_retried,
                    "latency_total_ms": e.latency_total_ms,
                    "is_internal": e.is_internal,
                }
                for e in events
            ],
        })
    finally:
        db.close()


@app.route("/api/telemetry/client-event", methods=["POST"])
def telemetry_client_event():
    """Record a client-side user interaction signal (idempotent).

    Body (JSON):
      answer_id    str  -- the answer_id from the trace (server-issued UUID)
      event_type   str  -- one of the valid client event types (see below)

    Event types:
      Engagement:  details_expand, pattern_click
      Explicit:    explicit_accept, thumbs_up, explicit_reject, thumbs_down, retry, reformulation
      Implicit:    implicit_accept_no_followup, copy_code

    Idempotent: each (answer_id, event_type) recorded at most once.
    """
    from hiveai.telemetry import record_client_event, ALL_CLIENT_EVENTS

    body = request.get_json(silent=True) or {}
    answer_id = (body.get("answer_id") or "").strip()
    event_type = (body.get("event_type") or "").strip()

    if not answer_id or not event_type:
        return jsonify({"error": "answer_id and event_type are required"}), 400

    if event_type not in ALL_CLIENT_EVENTS:
        return jsonify({
            "error": f"Invalid event_type. Must be one of: {', '.join(sorted(ALL_CLIENT_EVENTS))}",
        }), 400

    db = SessionLocal()
    try:
        result = record_client_event(db, answer_id, event_type)
        status_code = {"ok": 200, "already_recorded": 200, "not_found": 404,
                       "invalid_event_type": 400, "error": 500}.get(result["status"], 200)
        return jsonify({"answer_id": answer_id, "event_type": event_type, **result}), status_code
    finally:
        db.close()


if __name__ == "__main__":
    from hiveai.models import init_db
    init_db()
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
