import os
from dotenv import load_dotenv

load_dotenv()

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
OLLAMA_MODEL_FAST = os.environ.get("OLLAMA_MODEL_FAST", "qwen3.5:9b")

# llama-server — serves the merged GGUF model (merge-then-freeze, no LoRA at runtime).
# Any model name in LLAMA_SERVER_MODELS routes to llama-server instead of Ollama.
LLAMA_SERVER_BASE_URL = os.environ.get("LLAMA_SERVER_BASE_URL", "http://localhost:11435")
LLAMA_SERVER_MODELS: set = {
    m.strip()
    for m in os.environ.get("LLAMA_SERVER_MODELS", "hiveai").split(",")
    if m.strip()
}
# The currently-active llama-server model name (used for routing)
LLAMA_SERVER_MODEL = os.environ.get("LLAMA_SERVER_MODEL", "hiveai")

EXTRACTION_QUALITY = os.environ.get("EXTRACTION_QUALITY", "high").lower()

EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIMENSIONS = 1024
SEMANTIC_SIMILARITY_THRESHOLD = float(os.environ.get("SEMANTIC_SIMILARITY_THRESHOLD", "0.82"))
MIN_TRAINING_QUALITY = float(os.environ.get("MIN_TRAINING_QUALITY", "0.80"))
LORA_EXPORT_QUALITY = float(os.environ.get("LORA_EXPORT_QUALITY", "0.75"))
# Hard gate: pairs with fewer code blocks than this are never eligible (coding model must code)
MIN_CODE_BLOCKS = int(os.environ.get("MIN_CODE_BLOCKS", "1"))

# --- Deduplication thresholds (tiered system) ---
# Above EXACT: always reject (true duplicate)
DEDUP_EXACT_THRESHOLD = float(os.environ.get("DEDUP_EXACT_THRESHOLD", "0.95"))
# Above PARAPHRASE: reject unless new pair has significantly better quality
DEDUP_PARAPHRASE_THRESHOLD = float(os.environ.get("DEDUP_PARAPHRASE_THRESHOLD", "0.85"))
# Above NEAR: allow if responses cover different angles (diversity preserved)
DEDUP_NEAR_THRESHOLD = float(os.environ.get("DEDUP_NEAR_THRESHOLD", "0.75"))
# Quality improvement margin for paraphrase tier
DEDUP_QUALITY_MARGIN = float(os.environ.get("DEDUP_QUALITY_MARGIN", "0.10"))

# --- Entity resolution ---
ENTITY_SIMILARITY_THRESHOLD = float(os.environ.get("ENTITY_SIMILARITY_THRESHOLD", "0.92"))

# --- LLM circuit breaker ---
CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_COOLDOWN = int(os.environ.get("CIRCUIT_BREAKER_COOLDOWN", "60"))

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

# --- Chat self-verification ---
# When enabled, code blocks in chat responses are executed in the sandbox
# before returning to the user. Adds 0-15s latency but catches runtime errors.
CHAT_VERIFY_CODE = os.environ.get("CHAT_VERIFY_CODE", "true").lower() in ("1", "true", "yes")

# --- Retrieval tuning ---
ENABLE_MULTI_HOP_RAG = os.environ.get("ENABLE_MULTI_HOP_RAG", "true").lower() in ("1", "true", "yes")

# --- MoLoRA (Mixture of LoRA Experts) ---
MOLORA_ENABLED = os.environ.get("MOLORA_ENABLED", "false").lower() in ("1", "true", "yes")
MOLORA_DEFAULT_DOMAIN = os.environ.get("MOLORA_DEFAULT_DOMAIN", "general")

# --- Auto-Improvement (self-learning from verified chat responses) ---
AUTO_IMPROVE_ENABLED = os.environ.get("AUTO_IMPROVE_ENABLED", "true").lower() in ("1", "true", "yes")
AUTO_IMPROVE_MIN_BLOCKS = int(os.environ.get("AUTO_IMPROVE_MIN_BLOCKS", "1"))
AUTO_IMPROVE_QUALITY_BONUS = float(os.environ.get("AUTO_IMPROVE_QUALITY_BONUS", "0.05"))
AUTO_IMPROVE_CHECK_INTERVAL = int(os.environ.get("AUTO_IMPROVE_CHECK_INTERVAL", "300"))
AUTO_IMPROVE_MIN_PAIRS = int(os.environ.get("AUTO_IMPROVE_MIN_PAIRS", "20"))

# --- Solved Example Promotion (verified candidates → retrievable knowledge) ---
# When enabled, verified candidates that pass complexity gates are also stored as
# BookSection records in a synthetic "Solved Examples" book, making them retrievable
# by the RAG pipeline for future similar queries.
AUTO_PROMOTE_VERIFIED = os.environ.get("AUTO_PROMOTE_VERIFIED", "true").lower() in ("1", "true", "yes")
# Minimum verified_floor to promote (stricter than staging gate)
AUTO_PROMOTE_MIN_QUALITY = float(os.environ.get("AUTO_PROMOTE_MIN_QUALITY", "0.82"))
# Minimum code lines to promote (prevents trivial solutions entering knowledge base)
AUTO_PROMOTE_MIN_CODE_LINES = int(os.environ.get("AUTO_PROMOTE_MIN_CODE_LINES", "5"))

# --- Multi-Source Miner (mine training pairs from free AI APIs) ---
MULTI_MINER_ENABLED = os.environ.get("MULTI_MINER_ENABLED", "false").lower() in ("1", "true", "yes")
MINER_INTERVAL_SECONDS = int(os.environ.get("MINER_INTERVAL_SECONDS", "5"))
MINER_DAILY_TARGET = int(os.environ.get("MINER_DAILY_TARGET", "1000"))
MINER_STARTUP_DELAY = int(os.environ.get("MINER_STARTUP_DELAY", "30"))
MINER_REFINE_ENABLED = os.environ.get("MINER_REFINE_ENABLED", "false").lower() in ("1", "true", "yes")
MINER_PARALLEL_BATCH = int(os.environ.get("MINER_PARALLEL_BATCH", "4"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
HF_API_KEY = os.environ.get("HF_API_KEY", "")

# --- DBC (Decentralized Brain Collective) ---
DBC_ENABLED = os.environ.get("DBC_ENABLED", "false").lower() in ("1", "true", "yes")
DBC_ACCOUNT = os.environ.get("DBC_ACCOUNT", "")
DBC_POSTING_KEY = os.environ.get("DBC_POSTING_KEY", "")
DBC_CUSTOM_JSON_ID = "hiveai"
DBC_MIN_ONCHAIN_QUALITY = float(os.environ.get("DBC_MIN_ONCHAIN_QUALITY", "0.85"))
DBC_EPOCH_TIMEOUT_HOURS = int(os.environ.get("DBC_EPOCH_TIMEOUT_HOURS", "24"))
DBC_RC_FLOOR_PERCENT = float(os.environ.get("DBC_RC_FLOOR_PERCENT", "20"))
DBC_RC_RESUME_PERCENT = float(os.environ.get("DBC_RC_RESUME_PERCENT", "50"))


def validate_config():
    """
    Validate configuration on startup. Returns list of warnings.
    Raises RuntimeError for fatal misconfigurations.
    """
    import logging
    logger = logging.getLogger("hiveai.config")
    warnings = []

    # Fatal checks
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")

    if DB_BACKEND == "postgresql" and "postgresql" not in DATABASE_URL:
        raise RuntimeError(f"DATABASE_URL doesn't look like PostgreSQL: {DATABASE_URL[:30]}...")

    # Quality gate sanity
    if MIN_TRAINING_QUALITY >= LORA_EXPORT_QUALITY:
        warnings.append(
            f"MIN_TRAINING_QUALITY ({MIN_TRAINING_QUALITY}) >= LORA_EXPORT_QUALITY ({LORA_EXPORT_QUALITY}). "
            "Export threshold should be higher than training minimum."
        )

    if MIN_TRAINING_QUALITY < 0.5 or MIN_TRAINING_QUALITY > 1.0:
        warnings.append(f"MIN_TRAINING_QUALITY={MIN_TRAINING_QUALITY} looks out of range (expected 0.5-1.0)")

    if LORA_EXPORT_QUALITY < 0.5 or LORA_EXPORT_QUALITY > 1.0:
        warnings.append(f"LORA_EXPORT_QUALITY={LORA_EXPORT_QUALITY} looks out of range (expected 0.5-1.0)")

    # Dedup threshold ordering
    if not (DEDUP_EXACT_THRESHOLD > DEDUP_PARAPHRASE_THRESHOLD > DEDUP_NEAR_THRESHOLD):
        warnings.append(
            f"Dedup thresholds not ordered: exact={DEDUP_EXACT_THRESHOLD} > "
            f"paraphrase={DEDUP_PARAPHRASE_THRESHOLD} > near={DEDUP_NEAR_THRESHOLD}"
        )

    # LLM backend availability
    if LLM_BACKEND == "openrouter" and not OPENROUTER_API_KEY:
        warnings.append("LLM_BACKEND=openrouter but OPENROUTER_API_KEY is not set")

    # llama-server model should be in the models set
    if LLAMA_SERVER_MODEL and LLAMA_SERVER_MODEL not in LLAMA_SERVER_MODELS:
        warnings.append(
            f"LLAMA_SERVER_MODEL='{LLAMA_SERVER_MODEL}' not in LLAMA_SERVER_MODELS={LLAMA_SERVER_MODELS}. "
            "Requests to this model won't route to llama-server."
        )

    # Embedding dimensions
    if EMBEDDING_DIMENSIONS not in (384, 512, 768, 1024, 1536, 3072, 4096):
        warnings.append(f"EMBEDDING_DIMENSIONS={EMBEDDING_DIMENSIONS} — unusual dimension, verify model compatibility")

    # Chunk size vs overlap sanity
    if CHUNK_OVERLAP >= CHUNK_SIZE:
        warnings.append(f"CHUNK_OVERLAP ({CHUNK_OVERLAP}) >= CHUNK_SIZE ({CHUNK_SIZE}). Chunks will repeat content.")

    # Check for known-bad OLLAMA_MODEL_FAST setting
    if OLLAMA_MODEL_FAST in LLAMA_SERVER_MODELS:
        warnings.append(
            f"OLLAMA_MODEL_FAST='{OLLAMA_MODEL_FAST}' is a llama-server model. "
            "Ollama can't serve LoRA models — fast model calls will fail."
        )

    # Auto-improve config checks
    if AUTO_IMPROVE_ENABLED and not CHAT_VERIFY_CODE:
        warnings.append("AUTO_IMPROVE_ENABLED=true but CHAT_VERIFY_CODE=false — auto-improve requires code verification")

    # Multi-miner config checks
    if MULTI_MINER_ENABLED:
        _miner_keys = sum(1 for env in [
            "GEMINI_API_KEY", "AI_INTEGRATIONS_OPENROUTER_API_KEY",
            "GROQ_API_KEY", "CEREBRAS_API_KEY", "DEEPSEEK_API_KEY",
            "MISTRAL_API_KEY", "HF_API_KEY"
        ] if os.environ.get(env))
        if _miner_keys == 0:
            warnings.append(
                "MULTI_MINER_ENABLED=true but no provider API keys are set. "
                "The miner will only use local Ollama as fallback."
            )
        else:
            logger.info(f"[CONFIG] Multi-miner: {_miner_keys} provider(s) configured")

    # DBC config checks
    if DBC_ENABLED:
        if not DBC_ACCOUNT:
            warnings.append("DBC_ENABLED=true but DBC_ACCOUNT is not set")
        if DBC_RC_FLOOR_PERCENT >= DBC_RC_RESUME_PERCENT:
            warnings.append(
                f"DBC_RC_FLOOR_PERCENT ({DBC_RC_FLOOR_PERCENT}) >= DBC_RC_RESUME_PERCENT ({DBC_RC_RESUME_PERCENT}). "
                "Hysteresis requires floor < resume."
            )

    # Log results
    for w in warnings:
        logger.warning(f"[CONFIG] {w}")

    if not warnings:
        logger.info(f"[CONFIG] Validated OK — backend={LLM_BACKEND}, db={DB_BACKEND}, "
                     f"profile={HARDWARE_PROFILE}, verify_code={CHAT_VERIFY_CODE}, "
                     f"auto_improve={AUTO_IMPROVE_ENABLED}")

    return warnings
