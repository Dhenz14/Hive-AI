"""
hiveai/lora/molora.py

MoLoRA — Mixture of LoRA Experts.

Routes user queries to domain-specialized Ollama models based on keyword
classification.  Each domain has its own merged model (base + domain LoRA),
and the router picks the best one for the query.

When no domain model is available, falls back to the general model.

Enable with MOLORA_ENABLED=true in .env.

Usage:
    from hiveai.lora.molora import MoLoRARouter, classify_domain

    router = MoLoRARouter()
    domain, model = router.route("Write a Python flask endpoint")
    # → ("python", "hiveai-v5-python")
"""
import logging
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain registry
# ---------------------------------------------------------------------------
DOMAINS = {
    "python": {
        "keywords": [
            "python", "pip", "django", "flask", "fastapi", "pandas", "numpy",
            "pytest", "asyncio", "pydantic", "sqlalchemy", "celery", "uvicorn",
            "poetry", "virtualenv", "conda", "matplotlib", "scipy", "torch",
            "tensorflow", "keras", "scrapy", "beautifulsoup",
        ],
        "extensions": [".py"],
        "ollama_model": "hiveai-v5-python",
        "adapter_path": "loras/domains/python/",
        "weight": 1.0,
    },
    "hive": {
        "keywords": [
            "hive", "hivemind", "hbd", "hp", "rc", "beem", "dhive", "hivesigner",
            "steemit", "appbase", "condenser", "custom_json", "broadcast",
            "posting_key", "active_key", "witness", "proposal", "dapp",
            "hivesql", "hive-engine", "splinterlands", "hive api",
        ],
        "extensions": [],
        "ollama_model": "hiveai-v5-hive",
        "adapter_path": "loras/domains/hive/",
        "weight": 1.5,  # boost — Hive is our core specialty
    },
    "javascript": {
        "keywords": [
            "javascript", "typescript", "node", "nodejs", "react", "vue",
            "angular", "npm", "yarn", "webpack", "vite", "express", "nextjs",
            "deno", "bun", "svelte", "jquery", "dom", "fetch api",
        ],
        "extensions": [".js", ".ts", ".tsx", ".jsx"],
        "ollama_model": "hiveai-v5-js",
        "adapter_path": "loras/domains/js/",
        "weight": 1.0,
    },
    "rust": {
        "keywords": [
            "rust", "cargo", "tokio", "serde", "axum", "wasm", "actix",
            "reqwest", "clap", "diesel", "rocket", "async-std", "rayon",
        ],
        "extensions": [".rs"],
        "ollama_model": "hiveai-v5-rust",
        "adapter_path": "loras/domains/rust/",
        "weight": 1.0,
    },
    "cpp": {
        "keywords": [
            "c++", "cpp", "cmake", "make", "gcc", "clang", "stl",
            "boost", "qt", "opencv", "cuda", "openmp",
        ],
        "extensions": [".cpp", ".hpp", ".c", ".h"],
        "ollama_model": "hiveai-v5-cpp",
        "adapter_path": "loras/domains/cpp/",
        "weight": 1.0,
    },
    "go": {
        "keywords": [
            "golang", "go ", "goroutine", "channel", "gin", "echo",
            "cobra", "viper", "gorm",
        ],
        "extensions": [".go"],
        "ollama_model": "hiveai-v5-go",
        "adapter_path": "loras/domains/go/",
        "weight": 1.0,
    },
    "general": {
        "keywords": [],
        "extensions": [],
        "ollama_model": "hiveai-v5",
        "adapter_path": "loras/v5/",
        "weight": 0.0,  # fallback only
    },
}

# Minimum score to classify as a specific domain (prevents weak matches)
MIN_DOMAIN_SCORE = 2.0


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------
def classify_domain(query: str) -> str:
    """
    Rule-based domain classification from query text.

    Scores each domain by counting keyword matches (weighted),
    returns the highest-scoring domain or "general" if below threshold.
    """
    q = query.lower()
    scores: dict[str, float] = {}

    for domain, config in DOMAINS.items():
        if domain == "general":
            continue
        score = 0.0
        for keyword in config["keywords"]:
            if keyword in q:
                score += config.get("weight", 1.0)
        # Extension mentions (e.g., ".py file", ".rs")
        for ext in config.get("extensions", []):
            if ext in q:
                score += 0.5
        if score > 0:
            scores[domain] = score

    if not scores:
        return "general"

    best_domain = max(scores, key=scores.get)
    if scores[best_domain] < MIN_DOMAIN_SCORE:
        return "general"

    return best_domain


def get_model_for_domain(domain: str) -> str:
    """Returns the Ollama model name for a given domain."""
    if domain in DOMAINS:
        return DOMAINS[domain]["ollama_model"]
    return DOMAINS["general"]["ollama_model"]


def get_available_domains() -> list[str]:
    """Returns domains that have adapter directories with files."""
    import os
    available = ["general"]
    for domain, config in DOMAINS.items():
        if domain == "general":
            continue
        adapter_path = config["adapter_path"]
        if os.path.isdir(adapter_path) and os.path.exists(
            os.path.join(adapter_path, "adapter_config.json")
        ):
            available.append(domain)
    return available


# ---------------------------------------------------------------------------
# MoLoRA Router
# ---------------------------------------------------------------------------
class MoLoRARouter:
    """Routes queries to domain-specialized Ollama models."""

    def __init__(self):
        self.domains = DOMAINS
        self._available_models: Optional[set[str]] = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 60.0  # refresh every 60s

    def route(self, query: str) -> tuple[str, str]:
        """
        Classify query and return (domain, ollama_model_name).

        Falls back to general if domain model isn't available in Ollama.
        """
        domain = classify_domain(query)
        model = self.domains[domain]["ollama_model"]

        if domain == "general":
            return (domain, model)

        if self._is_model_available(model):
            return (domain, model)

        logger.debug(f"MoLoRA: domain={domain} but model {model} not available, falling back to general")
        return ("general", self.domains["general"]["ollama_model"])

    def _is_model_available(self, model: str) -> bool:
        """Check if an Ollama model exists (cached)."""
        now = time.time()
        if self._available_models is None or (now - self._cache_time) > self._cache_ttl:
            self._refresh_available_models()
            self._cache_time = now

        return model in (self._available_models or set())

    def _refresh_available_models(self):
        """Query ollama list to get available models."""
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # Parse model names from ollama list output
                models = set()
                for line in result.stdout.strip().split("\n")[1:]:  # skip header
                    if line.strip():
                        # First column is model name (e.g., "hiveai-v5:latest")
                        name = line.split()[0].split(":")[0]
                        models.add(name)
                self._available_models = models
                logger.debug(f"MoLoRA: {len(models)} models available in Ollama")
            else:
                logger.warning("MoLoRA: ollama list failed")
                self._available_models = set()
        except Exception as e:
            logger.warning(f"MoLoRA: could not query Ollama: {e}")
            self._available_models = set()

    def get_status(self) -> dict:
        """Return router status for dashboard/debugging."""
        self._refresh_available_models()
        domain_status = {}
        for domain, config in self.domains.items():
            model = config["ollama_model"]
            domain_status[domain] = {
                "model": model,
                "available": model in (self._available_models or set()),
                "keywords": len(config.get("keywords", [])),
            }
        return {
            "enabled": True,
            "domains": domain_status,
            "total_models": len(self._available_models or set()),
        }
