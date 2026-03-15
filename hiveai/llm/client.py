import logging
import os
import re
import threading
import hashlib
import requests
from functools import lru_cache
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from pydantic import BaseModel, Field
from typing import List, Optional
import instructor
from hiveai.config import (
    OPENROUTER_BASE_URL, OPENROUTER_API_KEY, LLM_MODEL_REASONING, LLM_MODEL_FAST,
    EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL, LLAMA_SERVER_BASE_URL, LLAMA_SERVER_MODELS,
    MOLORA_ENABLED,
)

logger = logging.getLogger(__name__)
logging.getLogger("instructor").setLevel(logging.WARNING)

# Connection-pooled session for llama-server / local HTTP backends.
# Reuses TCP connections (Keep-Alive) instead of opening a new socket per request.
_http_session = requests.Session()
_http_session.headers.update({"Content-Type": "application/json"})
logging.getLogger("httpx").setLevel(logging.WARNING)


class ExtractedTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class TripleExtractionResult(BaseModel):
    triples: List[ExtractedTriple]

_thread_local = threading.local()

_active_backend = None

# ---------------------------------------------------------------------------
# MoLoRA — Mixture of LoRA Experts routing (lazy-init, dormant if disabled)
# ---------------------------------------------------------------------------
_molora_router = None
if MOLORA_ENABLED:
    try:
        from hiveai.lora.molora import MoLoRARouter
        _molora_router = MoLoRARouter()
        logger.info("MoLoRA router initialized — domain-based routing enabled")
    except Exception as e:
        logger.warning(f"MoLoRA init failed, falling back to standard routing: {e}")

# ---------------------------------------------------------------------------
# Per-Backend Circuit Breakers — isolate failures so one dead backend
# doesn't block calls to healthy ones.
# ---------------------------------------------------------------------------
class _CircuitBreaker:
    """Per-backend circuit breaker with half-open recovery."""
    __slots__ = ("name", "failures", "open_until", "_lock")

    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.open_until = 0.0
        self._lock = threading.Lock()

    def check(self):
        import time as _time
        from hiveai.config import CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN
        with self._lock:
            now = _time.time()
            if self.open_until > now:
                remaining = int(self.open_until - now)
                raise RuntimeError(
                    f"Circuit breaker [{self.name}] OPEN: {CIRCUIT_BREAKER_THRESHOLD} consecutive "
                    f"failures. Cooling down for {remaining}s."
                )
            if self.failures >= CIRCUIT_BREAKER_THRESHOLD:
                self.failures = 0
                logger.info(f"Circuit breaker [{self.name}]: cooldown expired, resetting")

    def record_success(self):
        with self._lock:
            if self.failures > 0:
                self.failures = 0

    def record_failure(self):
        import time as _time
        from hiveai.config import CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN
        with self._lock:
            self.failures += 1
            if self.failures >= CIRCUIT_BREAKER_THRESHOLD:
                self.open_until = _time.time() + CIRCUIT_BREAKER_COOLDOWN
                logger.error(
                    f"Circuit breaker [{self.name}] OPENED: {self.failures} failures. "
                    f"Pausing for {CIRCUIT_BREAKER_COOLDOWN}s."
                )

_circuit_breakers = {
    "llama": _CircuitBreaker("llama-server"),
    "ollama": _CircuitBreaker("ollama"),
    "openrouter": _CircuitBreaker("openrouter"),
    "embedding": _CircuitBreaker("embedding"),
}

def _get_breaker(model: str = None) -> _CircuitBreaker:
    """Route to the correct circuit breaker based on model/backend."""
    if model and _is_llama_server_model(model):
        return _circuit_breakers["llama"]
    backend = get_active_backend()
    return _circuit_breakers.get(backend, _circuit_breakers["ollama"])

# Legacy API (used throughout the codebase)
def _check_circuit_breaker(model: str = None):
    _get_breaker(model).check()

def _record_circuit_success(model: str = None):
    _get_breaker(model).record_success()

def _record_circuit_failure(model: str = None):
    _get_breaker(model).record_failure()


def _detect_ollama():
    """Check if Ollama is running locally."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            logger.info(f"Ollama detected with models: {model_names}")
            return True
        return False
    except Exception:
        return False


def get_active_backend():
    """Determine which LLM backend to use."""
    global _active_backend
    if _active_backend is not None:
        return _active_backend

    from hiveai.config import LLM_BACKEND, OPENROUTER_API_KEY

    if LLM_BACKEND == "ollama":
        _active_backend = "ollama"
    elif LLM_BACKEND == "openrouter":
        _active_backend = "openrouter"
    else:
        if _detect_ollama():
            _active_backend = "ollama"
            logger.info("Auto-detected Ollama — using local LLM")
        elif OPENROUTER_API_KEY:
            _active_backend = "openrouter"
            logger.info("Using OpenRouter API")
        else:
            _active_backend = "ollama"
            logger.info("No API key and no Ollama — defaulting to Ollama (may fail)")

    return _active_backend


def _get_model_for_backend(model_type="reasoning"):
    """Get the appropriate model name for the active backend."""
    backend = get_active_backend()
    if backend == "ollama":
        from hiveai.config import OLLAMA_MODEL_REASONING, OLLAMA_MODEL_FAST
        return OLLAMA_MODEL_REASONING if model_type == "reasoning" else OLLAMA_MODEL_FAST
    else:
        return LLM_MODEL_REASONING if model_type == "reasoning" else LLM_MODEL_FAST


def is_retryable_error(exception):
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or "Expecting value" in error_msg
        or "500" in error_msg
        or "502" in error_msg
        or "503" in error_msg
        or "connection" in error_msg.lower()
        or (hasattr(exception, "status_code") and exception.status_code in (429, 500, 502, 503))
    )


def _is_llama_server_model(model: str) -> bool:
    """Return True if this model should route to llama-server instead of Ollama."""
    return model in LLAMA_SERVER_MODELS


def get_client(model: str | None = None):
    """Return an OpenAI-compatible client.

    If *model* is a llama-server model (e.g. hiveai-v1), returns a client
    pointed at the llama-server endpoint.  Otherwise uses the normal Ollama/
    OpenRouter client cached on the thread-local.
    """
    if model and _is_llama_server_model(model):
        # llama-server speaks OpenAI format — no caching needed (lightweight)
        return OpenAI(base_url=f"{LLAMA_SERVER_BASE_URL}/v1", api_key="llama")

    if not hasattr(_thread_local, "client") or _thread_local.client is None:
        backend = get_active_backend()
        if backend == "ollama":
            _thread_local.client = OpenAI(
                base_url=f"{OLLAMA_BASE_URL}/v1",
                api_key="ollama",
            )
        else:
            _thread_local.client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=OPENROUTER_API_KEY,
            )
    return _thread_local.client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(is_retryable_error),
    reraise=True,
)
def llm_call(prompt, system_prompt="You are a knowledge extraction and synthesis AI.", model=None, max_tokens=8192, temperature=0.3, use_cache=True, messages=None):
    """Call the LLM with either a prompt string or a pre-built messages array.

    When *messages* is provided, it is sent directly to the chat completions API
    (system_prompt and prompt are ignored).  This enables proper multi-turn
    ChatML conversations instead of flattening history into a single string.
    """
    if not model:
        model = _get_model_for_backend("reasoning")
    _check_circuit_breaker(model)

    # Build the messages payload
    if messages is not None:
        chat_messages = messages
        cache_key_str = str(messages)
    else:
        chat_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        cache_key_str = prompt

    # Check LLM response cache (only for deterministic temperature <= 0.3)
    if use_cache and temperature <= 0.3:
        cached = get_cached_response(cache_key_str, model)
        if cached is not None:
            return cached

    client = get_client(model)
    try:
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if _is_llama_server_model(model) else {}
        response = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            extra_body=extra or None,
        )
        _record_circuit_success(model)
        content = response.choices[0].message.content

        # Cache the response for future identical queries
        if use_cache and temperature <= 0.3 and content:
            set_cached_response(cache_key_str, content, model)

        return content
    except Exception as e:
        _record_circuit_failure(model)
        logger.error(f"LLM call failed with model {model}: {e}")
        raise


def stream_llm_call(prompt, system_prompt="You are a knowledge extraction and synthesis AI.",
                    model=None, max_tokens=4096, temperature=0.3, messages=None):
    """
    Stream tokens from Ollama (/api/chat NDJSON) or llama-server (/v1/chat/completions SSE).

    Yields dicts: {"token": "..."} for each token, {"done": True, "full_response": "..."} at end.
    Routing is automatic — llama-server models (e.g. hiveai-v1) use SSE format.

    When *messages* is provided, it is sent directly as the messages array
    (system_prompt and prompt are ignored).  This enables proper multi-turn
    ChatML conversations.
    """
    if not model:
        model = _get_model_for_backend("reasoning")
    _check_circuit_breaker(model)

    # Build messages payload
    if messages is not None:
        chat_messages = messages
    else:
        chat_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

    # ---- llama-server path (OpenAI SSE) ----
    if _is_llama_server_model(model):
        try:
            import json as _json
            resp = _http_session.post(
                f"{LLAMA_SERVER_BASE_URL}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": chat_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=600,
                stream=True,
            )
            resp.raise_for_status()

            full_response = []
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data: "):
                    payload = line_str[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        data = _json.loads(payload)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_response.append(content)
                            yield {"token": content}
                    except (ValueError, KeyError):
                        continue

            _record_circuit_success(model)
            full = "".join(full_response)
            # Strip thinking blocks from visible response
            if "</think>" in full:
                full = full.split("</think>", 1)[1].strip()
            yield {"done": True, "full_response": full}

        except Exception as e:
            _record_circuit_failure(model)
            logger.error(f"llama-server streaming failed: {e}")
            yield {"error": str(e), "done": True}
        return

    # ---- Ollama native path (/api/chat NDJSON) ----
    try:
        import json as _json
        resp = _http_session.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": chat_messages,
                "stream": True,
                "think": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                },
            },
            timeout=600,
            stream=True,
        )
        resp.raise_for_status()

        full_response = []
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = _json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    full_response.append(content)
                    yield {"token": content}
                if data.get("done"):
                    _record_circuit_success(model)
                    yield {"done": True, "full_response": "".join(full_response)}
                    return
            except (ValueError, KeyError):
                continue

        _record_circuit_success(model)
        yield {"done": True, "full_response": "".join(full_response)}

    except Exception as e:
        _record_circuit_failure(model)
        logger.error(f"Streaming LLM call failed: {e}")
        yield {"error": str(e), "done": True}


def reason(prompt, max_tokens=8192, system_prompt=None, messages=None):
    kwargs = {"model": _get_model_for_backend("reasoning"), "max_tokens": max_tokens, "temperature": 0.2}
    if messages is not None:
        kwargs["messages"] = messages
    elif system_prompt:
        kwargs["system_prompt"] = system_prompt
    return llm_call(prompt, **kwargs)



def fast(prompt, max_tokens=8192, system_prompt=None, messages=None):
    kwargs = {"model": _get_model_for_backend("fast"), "max_tokens": max_tokens, "temperature": 0.2}
    if messages is not None:
        kwargs["messages"] = messages
    elif system_prompt:
        kwargs["system_prompt"] = system_prompt
    return llm_call(prompt, **kwargs)


def estimate_query_difficulty(question: str, num_sections: int = 0) -> str:
    """
    Classify query difficulty to route to fast() or reason().

    Returns: "trivial", "simple", "moderate", "complex"

    Routing logic:
      trivial/simple → fast() model (instant, low VRAM)
      moderate/complex → reason() model (full MoE power)
    """
    q = question.lower().strip()
    words = q.split()
    word_count = len(words)

    # Complex signals (need full reasoning model)
    complex_signals = 0
    if any(w in q for w in ["compare", "trade-off", "tradeoff", "versus", "vs"]):
        complex_signals += 2
    if any(w in q for w in ["design", "architect", "implement", "build", "create"]):
        complex_signals += 1
    if any(w in q for w in ["debug", "fix", "error", "bug", "crash"]):
        complex_signals += 1
    if any(w in q for w in ["optimize", "performance", "benchmark", "scale"]):
        complex_signals += 1
    if any(w in q for w in ["why does", "how does", "explain how"]):
        complex_signals += 1
    if word_count > 30:
        complex_signals += 1  # long questions tend to be complex

    # Simple signals (fast model can handle)
    simple_signals = 0
    if word_count < 8:
        simple_signals += 1
    if any(w in q for w in ["what is", "define", "list", "name"]):
        simple_signals += 1
    if num_sections >= 5:
        simple_signals += 1  # lots of context = easy retrieval

    if complex_signals >= 3:
        return "complex"
    elif complex_signals >= 2:
        return "moderate"
    elif simple_signals >= 2:
        return "trivial"
    elif simple_signals >= 1 and complex_signals == 0:
        return "simple"
    return "moderate"


def smart_call(prompt: str, question: str = "", num_sections: int = 0,
               max_tokens: int = 4096, system_prompt: str = None,
               messages: list = None) -> str:
    """
    Confidence-based model routing: routes easy queries to fast model,
    complex queries to full reasoning model.

    When *messages* is provided, it is forwarded directly to llm_call as a
    pre-built ChatML message array (prompt and system_prompt are ignored).

    When MoLoRA is enabled, domain-specialized models are tried first.

    This saves significant VRAM and latency for 60-70% of typical queries
    while preserving quality for the hard ones.
    """
    # MoLoRA domain routing (if enabled and initialized)
    if _molora_router is not None:
        try:
            query_text = question or prompt[:200]
            domain, domain_model = _molora_router.route(query_text)
            if domain != "general":
                logger.info(f"MoLoRA routing: {domain} → {domain_model}")
                kwargs = {"model": domain_model, "max_tokens": max_tokens, "temperature": 0.2}
                if messages is not None:
                    kwargs["messages"] = messages
                elif system_prompt:
                    kwargs["system_prompt"] = system_prompt
                return llm_call(prompt, **kwargs)
        except Exception as e:
            logger.warning(f"MoLoRA routing failed, falling back to standard: {e}")

    # Standard difficulty-based routing
    difficulty = estimate_query_difficulty(question or prompt[:200], num_sections)

    if difficulty in ("trivial", "simple"):
        logger.info(f"Smart routing: {difficulty} → fast model")
        return fast(prompt, max_tokens=min(max_tokens, 2048), system_prompt=system_prompt, messages=messages)
    else:
        logger.info(f"Smart routing: {difficulty} → reason model")
        return reason(prompt, max_tokens=max_tokens, system_prompt=system_prompt, messages=messages)


_instructor_clients = {}  # Cache instructor-wrapped clients per backend key

def _structured_call(prompt, response_model, model_type="fast", max_tokens=4096):
    try:
        model = _get_model_for_backend(model_type)
        if _is_llama_server_model(model):
            backend_key = "llama"
        elif get_active_backend() == "ollama":
            backend_key = "ollama"
        else:
            backend_key = "openrouter"

        if backend_key not in _instructor_clients:
            if backend_key == "llama":
                raw_client = OpenAI(base_url=f"{LLAMA_SERVER_BASE_URL}/v1", api_key="llama")
            elif backend_key == "ollama":
                raw_client = OpenAI(base_url=f"{OLLAMA_BASE_URL}/v1", api_key="ollama")
            else:
                raw_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
            _instructor_clients[backend_key] = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
        patched_client = _instructor_clients[backend_key]
        result = patched_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a knowledge extraction and synthesis AI."},
                {"role": "user", "content": prompt},
            ],
            response_model=response_model,
            max_tokens=max_tokens,
            temperature=0.2,
            max_retries=2,
        )
        return result
    except Exception as e:
        logger.warning(f"Instructor structured call failed ({model_type}): {e}")
        return None


def fast_structured(prompt, response_model, max_tokens=4096):
    return _structured_call(prompt, response_model, model_type="fast", max_tokens=max_tokens)


def reason_structured(prompt, response_model, max_tokens=4096):
    return _structured_call(prompt, response_model, model_type="reasoning", max_tokens=max_tokens)


_embedding_model = None
_embedding_lock = threading.Lock()

_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
                # Use CPU for embeddings to keep GPU free for LLM inference
                embed_device = os.environ.get("EMBEDDING_DEVICE", "cpu")
                try:
                    _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=embed_device)
                    logger.info(f"Embedding model loaded on {embed_device} ({_embedding_model.get_sentence_embedding_dimension()} dims)")
                except Exception as e:
                    logger.warning(f"Failed to load embedding model {EMBEDDING_MODEL_NAME}: {e}. Falling back to BAAI/bge-m3")
                    try:
                        _embedding_model = SentenceTransformer("BAAI/bge-m3", device=embed_device)
                        logger.info(f"Fallback embedding model loaded on {embed_device} ({_embedding_model.get_sentence_embedding_dimension()} dims)")
                    except Exception as fallback_error:
                        logger.error(f"Failed to load fallback embedding model: {fallback_error}")
                        raise
    return _embedding_model


def _get_cross_encoder():
    global _cross_encoder_model
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                from sentence_transformers import CrossEncoder
                logger.info("Loading cross-encoder model: cross-encoder/ms-marco-MiniLM-L-6-v2")
                _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                logger.info("Cross-encoder model loaded")
    return _cross_encoder_model


def rerank_sections(query: str, sections: list[dict], top_k: int = 8) -> list[dict]:
    if not sections:
        return sections
    try:
        model = _get_cross_encoder()
        pairs = [(query, s.get("content", "") or s.get("header", "")) for s in sections]
        scores = model.predict(pairs)
        scored = list(zip(sections, scores))
        scored.sort(key=lambda x: float(x[1]), reverse=True)
        return [s[0] for s in scored[:top_k]]
    except Exception as e:
        logger.warning(f"Cross-encoder reranking failed, returning original sections: {e}")
        return sections[:top_k]


_embedding_cache = {}
_embedding_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 10000
_EMBEDDING_CACHE_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "embedding_cache.db")
_embedding_cache_dirty = 0  # count of unsaved entries since last flush

def _cache_key(text):
    return hashlib.md5(text.encode()).hexdigest()

def _load_embedding_cache_from_disk():
    """Load embedding cache from SQLite on startup. Fast: ~1-2s for 10K entries."""
    global _embedding_cache
    try:
        if not os.path.exists(_EMBEDDING_CACHE_DB):
            return 0
        import sqlite3, json as _json
        con = sqlite3.connect(_EMBEDDING_CACHE_DB, timeout=5)
        rows = con.execute("SELECT key, embedding FROM embeddings ORDER BY rowid DESC LIMIT ?",
                           (_CACHE_MAX_SIZE,)).fetchall()
        con.close()
        loaded = 0
        with _embedding_cache_lock:
            for key, emb_json in rows:
                if key not in _embedding_cache:
                    _embedding_cache[key] = _json.loads(emb_json)
                    loaded += 1
        if loaded:
            logger.info(f"Embedding cache: loaded {loaded} entries from disk")
        return loaded
    except Exception as e:
        logger.warning(f"Failed to load embedding cache from disk: {e}")
        return 0

def _flush_embedding_cache_to_disk():
    """Persist current embedding cache to SQLite. Called periodically."""
    global _embedding_cache_dirty
    try:
        import sqlite3, json as _json
        con = sqlite3.connect(_EMBEDDING_CACHE_DB, timeout=10)
        con.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, embedding TEXT)")
        with _embedding_cache_lock:
            items = list(_embedding_cache.items())
            _embedding_cache_dirty = 0
        # Batch insert with upsert
        con.executemany(
            "INSERT OR REPLACE INTO embeddings (key, embedding) VALUES (?, ?)",
            [(k, _json.dumps(v)) for k, v in items]
        )
        con.commit()
        con.close()
        logger.debug(f"Embedding cache: flushed {len(items)} entries to disk")
    except Exception as e:
        logger.warning(f"Failed to flush embedding cache to disk: {e}")

# Load cache from disk on module import
_load_embedding_cache_from_disk()

def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    
    model = _get_embedding_model()
    
    results = [None] * len(texts)
    uncached_indices = []
    uncached_texts = []
    
    with _embedding_cache_lock:
        for i, text in enumerate(texts):
            key = _cache_key(text)
            if key in _embedding_cache:
                results[i] = _embedding_cache[key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
    
    if uncached_texts:
        global _embedding_cache_dirty
        # Batch encode in chunks to prevent OOM on large batches
        _EMBED_BATCH = 256
        if len(uncached_texts) <= _EMBED_BATCH:
            new_embeddings = model.encode(uncached_texts, normalize_embeddings=True, show_progress_bar=False)
        else:
            import numpy as np
            chunks = [uncached_texts[i:i+_EMBED_BATCH] for i in range(0, len(uncached_texts), _EMBED_BATCH)]
            new_embeddings = np.vstack([model.encode(c, normalize_embeddings=True, show_progress_bar=False) for c in chunks])
        with _embedding_cache_lock:
            for idx, emb in zip(uncached_indices, new_embeddings):
                emb_list = emb.tolist()
                results[idx] = emb_list
                key = _cache_key(texts[idx])
                if len(_embedding_cache) >= _CACHE_MAX_SIZE:
                    # Evict oldest 10% (FIFO via dict insertion order)
                    evict_count = _CACHE_MAX_SIZE // 10
                    for k in list(_embedding_cache.keys())[:evict_count]:
                        del _embedding_cache[k]
                _embedding_cache[key] = emb_list
                _embedding_cache_dirty += 1
        # Flush to disk every 100 new embeddings
        if _embedding_cache_dirty >= 100:
            _flush_embedding_cache_to_disk()

    return results

def clear_embedding_cache():
    global _embedding_cache
    # Flush to disk before clearing
    if _embedding_cache:
        _flush_embedding_cache_to_disk()
    _embedding_cache = {}


def embed_text(text: str) -> list[float]:
    results = embed_texts([text])
    if not results or results[0] is None:
        raise ValueError(f"Failed to embed text (length={len(text)})")
    return results[0]


# ---------------------------------------------------------------------------
# LLM Response Cache — avoids re-calling the LLM for semantically identical queries.
# Uses prompt hash + model name as key. TTL prevents stale responses.
# ---------------------------------------------------------------------------
import time as _time

_llm_response_cache = {}
_llm_response_cache_lock = threading.Lock()
_LLM_CACHE_MAX_SIZE = 500
_LLM_CACHE_TTL = 3600  # 1 hour default


def _llm_cache_key(prompt: str, model: str = "") -> str:
    """Hash the full prompt + model for cache lookup."""
    content = f"{model}|{prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def get_cached_response(prompt: str, model: str = "") -> str | None:
    """Check if a cached LLM response exists for this prompt."""
    key = _llm_cache_key(prompt, model)
    with _llm_response_cache_lock:
        entry = _llm_response_cache.get(key)
        if entry and _time.time() < entry["expires"]:
            logger.debug(f"LLM cache HIT: {key}")
            return entry["response"]
        elif entry:
            del _llm_response_cache[key]  # expired
    return None


def set_cached_response(prompt: str, response: str, model: str = "",
                        ttl: int = _LLM_CACHE_TTL) -> None:
    """Cache an LLM response for future identical queries."""
    key = _llm_cache_key(prompt, model)
    now = _time.time()
    with _llm_response_cache_lock:
        # Prune all expired entries first (prevents memory leak)
        expired = [k for k, v in _llm_response_cache.items() if now >= v["expires"]]
        for k in expired:
            del _llm_response_cache[k]
        # If still at capacity, evict oldest 10%
        if len(_llm_response_cache) >= _LLM_CACHE_MAX_SIZE:
            evict_count = max(_LLM_CACHE_MAX_SIZE // 10, 1)
            by_age = sorted(_llm_response_cache, key=lambda k: _llm_response_cache[k]["expires"])
            for k in by_age[:evict_count]:
                del _llm_response_cache[k]
        _llm_response_cache[key] = {
            "response": response,
            "expires": now + ttl,
        }


def clear_llm_cache():
    """Clear the LLM response cache."""
    global _llm_response_cache
    with _llm_response_cache_lock:
        _llm_response_cache = {}


def clean_llm_response(text):
    """Clean LLM response: strip thinking tags and wrapper fences (not code fences)."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<analysis>.*?</analysis>', '', text, flags=re.DOTALL)
    # Only strip json/markdown wrapper fences — preserve code fences (```python, ```cpp, etc.)
    text = re.sub(r'```(?:json|markdown|md)\s*\n?', '', text)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


def repair_json(text):
    """Attempt to repair malformed JSON from LLM output."""
    text = clean_llm_response(text)
    bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
    if bracket_match:
        return bracket_match.group()
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        return '[' + brace_match.group() + ']'
    return text
