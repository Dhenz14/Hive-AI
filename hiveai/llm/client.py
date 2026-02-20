import logging
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
    EMBEDDING_MODEL_NAME, OLLAMA_BASE_URL,
)

logger = logging.getLogger(__name__)
logging.getLogger("instructor").setLevel(logging.WARNING)
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


def get_client():
    if not hasattr(_thread_local, "client") or _thread_local.client is None:
        backend = get_active_backend()
        if backend == "ollama":
            from hiveai.config import OLLAMA_BASE_URL
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
def llm_call(prompt, system_prompt="You are a knowledge extraction and synthesis AI.", model=None, max_tokens=8192, temperature=0.3):
    if not model:
        model = _get_model_for_backend("reasoning")

    client = get_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM call failed with model {model}: {e}")
        raise


def reason(prompt, max_tokens=8192):
    return llm_call(prompt, model=_get_model_for_backend("reasoning"), max_tokens=max_tokens, temperature=0.2)



def fast(prompt, max_tokens=8192):
    return llm_call(prompt, model=_get_model_for_backend("fast"), max_tokens=max_tokens, temperature=0.2)


def _structured_call(prompt, response_model, model_type="fast", max_tokens=4096):
    try:
        backend = get_active_backend()
        if backend == "ollama":
            from hiveai.config import OLLAMA_BASE_URL
            raw_client = OpenAI(base_url=f"{OLLAMA_BASE_URL}/v1", api_key="ollama")
        else:
            raw_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
        model = _get_model_for_backend(model_type)
        patched_client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
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
                try:
                    _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                    logger.info(f"Embedding model loaded ({_embedding_model.get_sentence_embedding_dimension()} dims)")
                except Exception as e:
                    logger.warning(f"Failed to load embedding model {EMBEDDING_MODEL_NAME}: {e}. Falling back to BAAI/bge-m3")
                    try:
                        _embedding_model = SentenceTransformer("BAAI/bge-m3")
                        logger.info(f"Fallback embedding model loaded ({_embedding_model.get_sentence_embedding_dimension()} dims)")
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

def _cache_key(text):
    return hashlib.md5(text.encode()).hexdigest()

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
        new_embeddings = model.encode(uncached_texts, normalize_embeddings=True, show_progress_bar=False)
        with _embedding_cache_lock:
            for idx, emb in zip(uncached_indices, new_embeddings):
                emb_list = emb.tolist()
                results[idx] = emb_list
                key = _cache_key(texts[idx])
                if len(_embedding_cache) < _CACHE_MAX_SIZE:
                    _embedding_cache[key] = emb_list
    
    return results

def clear_embedding_cache():
    global _embedding_cache
    _embedding_cache = {}


def embed_text(text: str) -> list[float]:
    results = embed_texts([text])
    return results[0]


def clean_llm_response(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<analysis>.*?</analysis>', '', text, flags=re.DOTALL)
    text = re.sub(r'```(?:json|markdown|md)?\s*\n?', '', text)
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
