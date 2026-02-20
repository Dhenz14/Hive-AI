import os
import re
import json
import logging
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from sqlalchemy import func
from hiveai.models import init_db, SessionLocal, Job, GoldenBook, GraphTriple, CrawledPage, Chunk, BookSection, SystemConfig, utcnow
from hiveai.llm.client import reason, fast, embed_text, clean_llm_response
from sqlalchemy import text as sa_text
from hiveai.llm.prompts import CHAT_SYSTEM_PROMPT, KNOWLEDGE_GAP_PROMPT, ANSWER_CHECK_PROMPT
from hiveai.chat import search_knowledge_sections, build_conversation_context, clean_topic, trigger_auto_learn, get_compressed_knowledge

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
        }
        return render_template("dashboard.html", jobs=jobs, books=books, stats=stats)
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

        knowledge_context = ""
        for section in top_sections:
            knowledge_context += f"\n\n--- From '{section['book_title']}' > {section['header']} ---\n{section['content'][:3000]}\n"

        book_ids = list(set(s.get("book_id") for s in top_sections if s.get("book_id")))
        compressed = get_compressed_knowledge(book_ids, db)
        if compressed:
            knowledge_context = f"=== Dense Knowledge Map ===\n{compressed}\n\n=== Detailed Sections ===\n{knowledge_context}"

        conversation_context = build_conversation_context(history)

        prompt = f"""{CHAT_SYSTEM_PROMPT}

Your knowledge sections (from verified Golden Books):
{knowledge_context}
{conversation_context}

User's question: {message}

Answer using ONLY the knowledge sections above. If you lack knowledge, respond with KNOWLEDGE_GAP: <topic>"""

        response = reason(prompt, max_tokens=4096)
        response = clean_llm_response(response)

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

        return jsonify({
            "reply": response,
            "sources": source_books,
            "learning": learning_info
        })
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
