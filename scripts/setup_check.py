"""
scripts/setup_check.py

First-run validator for HiveAI Knowledge Refinery.

Checks that all required services, dependencies, and configuration
are in place before running the application.

Usage:
    python scripts/setup_check.py           # Full check
    python scripts/setup_check.py --fix     # Attempt to auto-fix issues
"""

import os
import sys
import subprocess
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"


def check_python_version():
    """Check Python version >= 3.10."""
    v = sys.version_info
    if v >= (3, 10):
        print(f"  {PASS} Python {v.major}.{v.minor}.{v.micro}")
        return True
    print(f"  {FAIL} Python {v.major}.{v.minor} — need >= 3.10")
    return False


def check_env_file():
    """Check .env file exists and has DATABASE_URL."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        example = PROJECT_ROOT / ".env.example"
        if example.exists():
            print(f"  {FAIL} No .env file — copy .env.example to .env and configure it")
        else:
            print(f"  {FAIL} No .env file found")
        return False

    with open(env_path) as f:
        content = f.read()

    has_db = any(
        line.strip().startswith("DATABASE_URL=") and not line.strip().startswith("#")
        for line in content.splitlines()
    )
    if not has_db:
        print(f"  {FAIL} .env exists but DATABASE_URL is not set")
        return False

    print(f"  {PASS} .env file configured")
    return True


def check_dependencies():
    """Check critical Python packages are installed."""
    required = [
        ("flask", "Flask"),
        ("sqlalchemy", "SQLAlchemy"),
        ("requests", "requests"),
        ("sentence_transformers", "sentence-transformers"),
        ("numpy", "numpy"),
        ("dotenv", "python-dotenv"),
    ]
    all_ok = True
    for module, name in required:
        try:
            importlib.import_module(module)
            print(f"  {PASS} {name}")
        except ImportError:
            print(f"  {FAIL} {name} — install with: pip install {name}")
            all_ok = False
    return all_ok


def check_ollama():
    """Check Ollama is running and has models available."""
    try:
        import requests
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code != 200:
            print(f"  {FAIL} Ollama returned status {resp.status_code}")
            return False

        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]
        print(f"  {PASS} Ollama running — {len(models)} model(s) available")

        # Check for recommended models
        has_reasoning = any("qwen3" in m and ("14b" in m or "32b" in m or "35b" in m) for m in model_names)
        has_fast = any("qwen3" in m for m in model_names)

        if has_reasoning:
            print(f"  {PASS} Reasoning model found")
        else:
            print(f"  {WARN} No Qwen3 14B+ model — pull with: ollama pull qwen3:14b")

        if has_fast:
            print(f"  {PASS} Fast model found")
        else:
            print(f"  {WARN} No Qwen3 model — pull with: ollama pull qwen3:8b")

        return True
    except ImportError:
        print(f"  {FAIL} requests library not installed")
        return False
    except Exception as e:
        print(f"  {FAIL} Ollama not reachable at {base_url} — {e}")
        print(f"        Install: https://ollama.com/download")
        return False


def check_database():
    """Check database is accessible."""
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")

        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            print(f"  {FAIL} DATABASE_URL not set")
            return False

        if db_url.startswith("sqlite"):
            db_file = db_url.replace("sqlite:///", "")
            db_path = PROJECT_ROOT / db_file if not os.path.isabs(db_file) else Path(db_file)
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                print(f"  {PASS} SQLite database ({size_mb:.1f} MB)")
            else:
                print(f"  {INFO} SQLite database will be created on first run")
            return True
        else:
            from sqlalchemy import create_engine, text
            engine = create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"  {PASS} PostgreSQL connection successful")
            return True
    except Exception as e:
        print(f"  {FAIL} Database connection failed: {e}")
        return False


def check_gpu():
    """Check GPU availability for embedding model."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  {PASS} GPU: {name} ({vram:.1f} GB VRAM)")
        else:
            print(f"  {WARN} No GPU detected — embedding model will use CPU (slower)")
        return True
    except ImportError:
        print(f"  {WARN} PyTorch not installed — GPU check skipped")
        return True


def check_disk_space():
    """Check available disk space."""
    import shutil
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    free_gb = free / (1024**3)
    if free_gb < 5:
        print(f"  {FAIL} Only {free_gb:.1f} GB free — need at least 5 GB for models and data")
        return False
    elif free_gb < 20:
        print(f"  {WARN} {free_gb:.1f} GB free — recommend 20+ GB for model downloads")
    else:
        print(f"  {PASS} {free_gb:.1f} GB free disk space")
    return True


def check_llama_server():
    """Check llama-server availability (optional, for LoRA models)."""
    try:
        import requests
        base_url = os.environ.get("LLAMA_SERVER_BASE_URL", "http://localhost:11435")
        resp = requests.get(f"{base_url}/health", timeout=3)
        if resp.status_code == 200:
            print(f"  {PASS} llama-server running at {base_url}")
        else:
            print(f"  {INFO} llama-server not running (optional — needed for LoRA models)")
        return True
    except Exception:
        print(f"  {INFO} llama-server not running (optional — needed for LoRA models)")
        return True


def check_lora_adapters():
    """Check for trained LoRA adapters."""
    lora_dir = PROJECT_ROOT / "loras"
    if not lora_dir.exists():
        print(f"  {INFO} No loras/ directory — no LoRA adapters trained yet")
        return True

    versions = list(lora_dir.glob("*/adapter_model.safetensors")) + list(lora_dir.glob("*/*.gguf"))
    if versions:
        for v in versions:
            size_mb = v.stat().st_size / (1024 * 1024)
            print(f"  {PASS} LoRA adapter: {v.parent.name}/{v.name} ({size_mb:.0f} MB)")
    else:
        print(f"  {INFO} No LoRA adapters found — train one with scripts/train_v2.py")
    return True


def main():
    fix_mode = "--fix" in sys.argv

    print("\n" + "=" * 60)
    print("  HiveAI Knowledge Refinery — Setup Validator")
    print("=" * 60)

    sections = [
        ("Python Environment", [check_python_version]),
        ("Configuration", [check_env_file]),
        ("Dependencies", [check_dependencies]),
        ("Database", [check_database]),
        ("LLM Backend (Ollama)", [check_ollama]),
        ("GPU / Hardware", [check_gpu, check_disk_space]),
        ("LoRA / Fine-tuning", [check_llama_server, check_lora_adapters]),
    ]

    total_pass = 0
    total_fail = 0
    total_warn = 0

    for section_name, checks in sections:
        print(f"\n  --- {section_name} ---")
        for check_fn in checks:
            result = check_fn()
            if result:
                total_pass += 1
            else:
                total_fail += 1

    print(f"\n{'=' * 60}")
    if total_fail == 0:
        print("  All checks passed! HiveAI is ready to run.")
        print(f"  Start with: python -m hiveai")
    else:
        print(f"  {total_fail} check(s) failed. Fix the issues above and re-run.")
    print(f"{'=' * 60}\n")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
