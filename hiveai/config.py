import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

DB_BACKEND = "postgresql"
if DATABASE_URL.startswith("sqlite"):
    DB_BACKEND = "sqlite"

HIVE_API_NODES = [
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://hive-api.arcange.eu",
    "https://api.openhive.network",
    "https://rpc.ausbit.dev",
    "https://rpc.ecency.com",
    "https://api.hive.blue",
    "https://techcoderx.com",
    "https://anyx.io",
]

HIVE_PRIMARY_TAG = "archivedcontenthaf"
HIVE_REFINED_TAG = "hiveaiknowledgehaf"

MAX_CRAWL_PAGES = 10
CRAWL_TIMEOUT = 30
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

LLM_MODEL_REASONING = "qwen/qwen3-30b-a3b"
LLM_MODEL_FAST = "microsoft/phi-4"

OPENROUTER_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")

LLM_BACKEND = os.environ.get("LLM_BACKEND", "auto")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_REASONING = os.environ.get("OLLAMA_MODEL_REASONING", "qwen3:14b")
OLLAMA_MODEL_FAST = os.environ.get("OLLAMA_MODEL_FAST", "qwen3:8b")

EXTRACTION_QUALITY = os.environ.get("EXTRACTION_QUALITY", "high").lower()

EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIMENSIONS = 1024
SEMANTIC_SIMILARITY_THRESHOLD = float(os.environ.get("SEMANTIC_SIMILARITY_THRESHOLD", "0.82"))

CORS_PROXIES = [
    "https://corsproxy.io/?",
    "https://api.allorigins.win/raw?url=",
    "https://api.codetabs.com/v1/proxy?quest=",
]

from hiveai.hardware import get_hardware_profile, detect_hardware
_hw_profile = get_hardware_profile()
AVAILABLE_CPUS = _hw_profile["detected"]["cpus"]
HARDWARE_PROFILE = _hw_profile["profile"]
CRAWL_WORKERS = _hw_profile["crawl_workers"]
LLM_WORKERS = _hw_profile["llm_workers"]
EMBEDDING_BATCH_SIZE = _hw_profile["embedding_batch_size"]
MAX_CRAWL_PAGES = _hw_profile.get("max_crawl_pages", MAX_CRAWL_PAGES)
DB_POOL_SIZE = _hw_profile["db_pool_size"]

HNSW_EF_SEARCH = int(os.environ.get("HNSW_EF_SEARCH", "100"))
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))

MAX_RAW_CONTENT_SIZE = int(os.environ.get("MAX_RAW_CONTENT_SIZE", "100000"))
MAX_CHUNK_TEXT_FOR_LLM = int(os.environ.get("MAX_CHUNK_TEXT_FOR_LLM", "15000"))

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
SEMANTIC_CHUNKING = os.environ.get("SEMANTIC_CHUNKING", "").lower() in ("1", "true", "yes")
CRAWL_CACHE_TTL_HOURS = int(os.environ.get("CRAWL_CACHE_TTL_HOURS", "168"))
