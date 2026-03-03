import os
import sys

if __name__ == "__main__":
    from hiveai.models import init_db
    init_db()

    port = int(os.environ.get("PORT", "5001"))
    if os.environ.get("PRODUCTION") == "1":
        workers = int(os.environ.get("WEB_WORKERS", "2"))
        os.execvp("gunicorn", [
            "gunicorn",
            f"--workers={workers}",
            f"--bind=0.0.0.0:{port}",
            "--timeout=120",
            "--reuse-port",
            "hiveai.app:app"
        ])
    else:
        from hiveai.app import app
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
