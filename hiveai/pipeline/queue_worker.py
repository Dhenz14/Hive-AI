import logging
import threading
import time
from hiveai.models import SessionLocal, Job, SystemConfig

logger = logging.getLogger(__name__)

_worker_thread = None
_shutdown_event = threading.Event()
_worker_lock = threading.Lock()

def is_queue_paused(db):
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == "queue_paused").first()
        return row and row.value == "true"
    except:
        return False

def set_queue_paused(paused: bool):
    db = SessionLocal()
    try:
        from hiveai.pipeline.reembed import _ensure_system_config_table
        _ensure_system_config_table()
        row = db.query(SystemConfig).filter(SystemConfig.key == "queue_paused").first()
        if row:
            row.value = "true" if paused else "false"
        else:
            db.add(SystemConfig(key="queue_paused", value="true" if paused else "false"))
        db.commit()
    finally:
        db.close()

def get_queue_status():
    db = SessionLocal()
    try:
        paused = is_queue_paused(db)
        running = db.query(Job).filter(Job.status.in_(["generating_urls", "crawling", "chunking", "reasoning", "writing", "review", "compressing"])).first()
        queued_count = db.query(Job).filter(Job.status == "queued").count()
        return {
            "paused": paused,
            "running_job": {"id": running.id, "topic": running.topic, "status": running.status} if running else None,
            "queued_count": queued_count,
            "worker_alive": _worker_thread is not None and _worker_thread.is_alive(),
        }
    finally:
        db.close()

def cancel_job(job_id):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return {"error": "Job not found"}
        if job.status == "queued":
            job.status = "cancelled"
            db.commit()
            return {"status": "cancelled", "id": job_id}
        elif job.status in ("generating_urls", "crawling", "chunking", "reasoning", "writing", "review", "compressing"):
            row = db.query(SystemConfig).filter(SystemConfig.key == f"cancel_job_{job_id}").first()
            if row:
                row.value = "true"
            else:
                db.add(SystemConfig(key=f"cancel_job_{job_id}", value="true"))
            db.commit()
            return {"status": "cancel_requested", "id": job_id}
        else:
            return {"error": f"Job is already {job.status}"}
    finally:
        db.close()

def is_job_cancelled(job_id, db):
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == f"cancel_job_{job_id}").first()
        return row and row.value == "true"
    except:
        return False

def _clear_cancel_flag(job_id, db):
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == f"cancel_job_{job_id}").first()
        if row:
            db.delete(row)
            db.commit()
    except:
        pass

def _claim_next_job(db):
    job = db.query(Job).filter(Job.status == "queued").order_by(Job.created_at.asc()).first()
    if job:
        job.status = "generating_urls"
        db.commit()
        return job
    return None

def _worker_loop():
    logger.info("Queue worker started")
    while not _shutdown_event.is_set():
        db = SessionLocal()
        try:
            if is_queue_paused(db):
                db.close()
                _shutdown_event.wait(timeout=5)
                continue
            
            job = _claim_next_job(db)
            db.close()
            
            if job:
                logger.info(f"Queue worker: processing job {job.id} - '{job.topic}'")
                try:
                    from hiveai.pipeline.orchestrator import run_pipeline
                    run_pipeline(job.id)
                except Exception as e:
                    logger.error(f"Queue worker: job {job.id} failed: {e}")
                    error_db = SessionLocal()
                    try:
                        failed_job = error_db.get(Job, job.id)
                        if failed_job and failed_job.status not in ("completed", "published", "cancelled"):
                            failed_job.status = "error"
                        error_db.commit()
                    finally:
                        error_db.close()
                finally:
                    clean_db = SessionLocal()
                    try:
                        _clear_cancel_flag(job.id, clean_db)
                    finally:
                        clean_db.close()
            else:
                _shutdown_event.wait(timeout=3)
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            try:
                db.close()
            except:
                pass
            _shutdown_event.wait(timeout=5)

    logger.info("Queue worker stopped")

def start_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            logger.info("Queue worker already running")
            return
        _shutdown_event.clear()
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="queue-worker")
        _worker_thread.start()
        logger.info("Queue worker thread started")

def stop_worker():
    global _worker_thread
    _shutdown_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)
        _worker_thread = None
    logger.info("Queue worker stopped")

def ensure_worker_running():
    """Check if worker is alive and restart if needed."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        logger.warning("Queue worker died — restarting")
        start_worker()
