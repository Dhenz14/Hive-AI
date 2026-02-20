import os
import sys

if __name__ == "__main__":
    from hiveai.models import init_db
    init_db()

    if os.environ.get("PRODUCTION") == "1":
        workers = int(os.environ.get("WEB_WORKERS", "2"))
        os.execvp("gunicorn", [
            "gunicorn",
            f"--workers={workers}",
            "--bind=0.0.0.0:5000",
            "--timeout=120",
            "--reuse-port",
            "hiveai.app:app"
        ])
    else:
        from hiveai.app import app
        app.run(host="0.0.0.0", port=5000, debug=True)
