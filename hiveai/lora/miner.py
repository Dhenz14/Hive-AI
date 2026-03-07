"""
hiveai/lora/miner.py

Multi-Source AI Knowledge Miner — mines training pairs from free AI APIs.

Rotates through available providers (Gemini, OpenRouter, Groq, Cerebras,
DeepSeek, Mistral, HuggingFace, Ollama fallback), uses the existing distiller
templates to ask coding questions, scores responses through the quality pipeline,
and stages eligible pairs as training data.

Enable: MULTI_MINER_ENABLED=true + set one or more API keys.
"""

import json
import logging
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

@dataclass
class Provider:
    """Definition of a free AI API provider."""
    name: str
    base_url: str
    api_key_env: str          # env var name, e.g., "GROQ_API_KEY"
    models: list              # available model names
    rpm_limit: int            # requests per minute (0 = unlimited)
    daily_limit: int          # requests per day (0 = unlimited)
    priority: int             # lower = preferred
    requires_thinking: bool = False  # strip <think> blocks (DeepSeek R1)


PROVIDER_REGISTRY = {
    "gemini": Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GEMINI_API_KEY",
        models=["gemini-2.5-flash", "gemini-2.5-pro"],
        rpm_limit=15,
        daily_limit=250,
        priority=1,
    ),
    "openrouter": Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="AI_INTEGRATIONS_OPENROUTER_API_KEY",
        models=[
            "nousresearch/hermes-3-llama-3.1-405b:free",    # 405B — highest quality free
            "qwen/qwen3-coder:free",                         # 480B MoE coder, 262K ctx
            "qwen/qwen3-next-80b-a3b-instruct:free",        # 80B MoE, 262K ctx
            "openai/gpt-oss-120b:free",                      # OpenAI open model, 131K ctx
            "meta-llama/llama-3.3-70b-instruct:free",        # Strong 70B, 128K ctx
            "mistralai/mistral-small-3.1-24b-instruct:free", # Mistral coding, 128K ctx
            "nvidia/nemotron-3-nano-30b-a3b:free",           # NVIDIA MoE, 256K ctx
            "google/gemma-3-27b-it:free",                    # Google 27B, 131K ctx
        ],
        rpm_limit=10,
        daily_limit=200,
        priority=2,
        requires_thinking=True,
    ),
    "groq": Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        rpm_limit=30,
        daily_limit=0,
        priority=3,
    ),
    "cerebras": Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models=["llama3.1-70b"],
        rpm_limit=30,
        daily_limit=0,
        priority=4,
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-reasoner"],
        rpm_limit=10,
        daily_limit=0,
        priority=5,
        requires_thinking=True,
    ),
    "mistral": Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        models=["codestral-latest", "mistral-large-latest"],
        rpm_limit=2,
        daily_limit=0,
        priority=6,
    ),
    "huggingface": Provider(
        name="huggingface",
        base_url="https://api-inference.huggingface.co/v1",
        api_key_env="HF_API_KEY",
        models=["Qwen/Qwen2.5-72B-Instruct"],
        rpm_limit=15,
        daily_limit=900,
        priority=7,
    ),
    "ollama": Provider(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env="",
        models=[],
        rpm_limit=0,
        daily_limit=0,
        priority=99,
    ),
}


# ---------------------------------------------------------------------------
# Per-Provider Runtime State
# ---------------------------------------------------------------------------

class ProviderState:
    """Tracks rate limits, health, and usage for a single provider."""

    def __init__(self, provider: Provider):
        self.provider = provider
        self.api_key: str = ""
        self.daily_count = 0
        self.daily_reset_at: float = 0.0
        self.minute_timestamps: deque = deque()
        self.consecutive_failures = 0
        self.circuit_open_until: float = 0.0
        self.total_pairs = 0
        self.total_calls = 0
        self.last_error: str = ""
        self._lock = threading.Lock()

    def _load_key(self):
        """Load API key from environment."""
        if self.provider.api_key_env:
            self.api_key = os.environ.get(self.provider.api_key_env, "")
        else:
            # Ollama needs no key
            self.api_key = "ollama"

    def is_available(self) -> bool:
        """True if provider has API key, is not circuit-broken, and under daily limit."""
        if not self.api_key:
            return False
        now = time.time()
        if now < self.circuit_open_until:
            return False
        if self.provider.daily_limit > 0:
            self._maybe_reset_daily(now)
            if self.daily_count >= self.provider.daily_limit:
                return False
        return True

    def can_make_request(self) -> bool:
        """True if RPM and daily limits allow another request right now."""
        if not self.is_available():
            return False
        if self.provider.rpm_limit <= 0:
            return True
        with self._lock:
            now = time.time()
            # Prune old timestamps
            window_start = now - 60
            while self.minute_timestamps and self.minute_timestamps[0] < window_start:
                self.minute_timestamps.popleft()
            return len(self.minute_timestamps) < self.provider.rpm_limit

    def wait_for_rate_limit(self) -> float:
        """Seconds to wait before next request is allowed (0 if ready)."""
        if not self.is_available():
            return 999.0
        if self.provider.rpm_limit <= 0:
            return 0.0
        with self._lock:
            now = time.time()
            window_start = now - 60
            while self.minute_timestamps and self.minute_timestamps[0] < window_start:
                self.minute_timestamps.popleft()
            if len(self.minute_timestamps) < self.provider.rpm_limit:
                return 0.0
            return self.minute_timestamps[0] + 60.0 - now + 0.1

    def record_request(self):
        """Record a request for rate tracking."""
        with self._lock:
            self.minute_timestamps.append(time.time())
            self.daily_count += 1
            self.total_calls += 1

    def record_success(self):
        """Reset failure counter on success."""
        self.consecutive_failures = 0

    def record_failure(self, error: str):
        """Track failure, open circuit breaker after threshold."""
        self.last_error = error
        self.consecutive_failures += 1
        from hiveai.config import CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN
        if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self.circuit_open_until = time.time() + CIRCUIT_BREAKER_COOLDOWN
            logger.warning(f"Miner: {self.provider.name} circuit breaker opened "
                           f"({self.consecutive_failures} failures, cooldown {CIRCUIT_BREAKER_COOLDOWN}s)")

    def _maybe_reset_daily(self, now: float):
        """Reset daily counter at midnight UTC."""
        if now >= self.daily_reset_at:
            self.daily_count = 0
            # Next midnight UTC
            tomorrow = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            from datetime import timedelta
            tomorrow += timedelta(days=1)
            self.daily_reset_at = tomorrow.timestamp()

    def to_dict(self) -> dict:
        """Serialize state for the status API."""
        return {
            "name": self.provider.name,
            "available": self.is_available(),
            "can_request": self.can_make_request(),
            "api_key_set": bool(self.api_key),
            "calls_today": self.daily_count,
            "daily_limit": self.provider.daily_limit,
            "total_calls": self.total_calls,
            "pairs_generated": self.total_pairs,
            "consecutive_failures": self.consecutive_failures,
            "circuit_open": time.time() < self.circuit_open_until,
            "last_error": self.last_error[:100] if self.last_error else "",
            "priority": self.provider.priority,
        }


# ---------------------------------------------------------------------------
# Provider Router
# ---------------------------------------------------------------------------

class ProviderRouter:
    """Selects the next available provider using priority-based round-robin."""

    def __init__(self):
        self.states: dict[str, ProviderState] = {}
        self._index = 0
        self._initialize()

    def _initialize(self):
        """Load API keys, create ProviderState for each provider."""
        for name, provider in PROVIDER_REGISTRY.items():
            state = ProviderState(provider)
            state._load_key()

            # Special: populate Ollama models from config
            if name == "ollama":
                try:
                    from hiveai.config import OLLAMA_MODEL_REASONING
                    state.provider = Provider(
                        name="ollama",
                        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
                        api_key_env="",
                        models=[OLLAMA_MODEL_REASONING],
                        rpm_limit=0,
                        daily_limit=0,
                        priority=99,
                    )
                    state.api_key = "ollama"
                except Exception:
                    pass

            self.states[name] = state

        available = [n for n, s in self.states.items() if s.api_key]
        logger.info(f"Miner router initialized: {len(available)} providers available: "
                    f"{', '.join(available)}")

    def get_available(self) -> list[ProviderState]:
        """Return all available providers, sorted by priority."""
        return sorted(
            [s for s in self.states.values() if s.is_available()],
            key=lambda s: s.provider.priority
        )

    def next_provider(self) -> ProviderState | None:
        """Get the next available provider that can accept a request."""
        available = self.get_available()
        if not available:
            return None

        # Round-robin within available providers
        self._index = self._index % len(available)
        state = available[self._index]
        self._index += 1

        if state.can_make_request():
            return state

        # If preferred is rate-limited, try others
        for s in available:
            if s.can_make_request():
                return s

        return None

    def get_stats(self) -> list[dict]:
        """Return per-provider stats."""
        return [s.to_dict() for s in sorted(
            self.states.values(),
            key=lambda s: s.provider.priority
        )]


# ---------------------------------------------------------------------------
# Topic Tracker
# ---------------------------------------------------------------------------

class TopicTracker:
    """Tracks which topics have been used today to maximize diversity."""

    def __init__(self):
        self.used_today: set = set()
        self.last_reset: date = date.min
        self.all_topics: list = []
        self._build_pool()

    def _build_pool(self):
        """Combine all topic lists from the distiller with language tags."""
        try:
            from hiveai.lora.distiller import (
                BUILTIN_TOPICS, HIVE_TOPICS, CPP_TOPICS,
                RUST_TOPICS, GO_TOPICS,
            )
            for t in BUILTIN_TOPICS:
                self.all_topics.append((t, "python"))
            for t in HIVE_TOPICS:
                self.all_topics.append((t, "python"))
            for t in CPP_TOPICS:
                self.all_topics.append((t, "cpp"))
            for t in RUST_TOPICS:
                self.all_topics.append((t, "rust"))
            for t in GO_TOPICS:
                self.all_topics.append((t, "go"))
            random.shuffle(self.all_topics)
            logger.info(f"Miner topic pool: {len(self.all_topics)} topics across 5 languages")
        except Exception as e:
            logger.warning(f"Miner: failed to load topic pool: {e}")
            # Fallback minimal topics
            self.all_topics = [
                ("Python concurrency with asyncio", "python"),
                ("Hash maps and collision resolution", "python"),
                ("Binary search tree implementation", "python"),
                ("REST API design patterns", "python"),
                ("Database connection pooling", "python"),
            ]

    def next_topic(self) -> tuple[str, str]:
        """Return (topic, language) not used today. Resets at midnight."""
        today = date.today()
        if today != self.last_reset:
            self.used_today.clear()
            self.last_reset = today
            random.shuffle(self.all_topics)

        for topic, lang in self.all_topics:
            if topic not in self.used_today:
                self.used_today.add(topic)
                return topic, lang

        # All topics exhausted today — reset and reuse
        self.used_today.clear()
        random.shuffle(self.all_topics)
        topic, lang = self.all_topics[0]
        self.used_today.add(topic)
        return topic, lang


# ---------------------------------------------------------------------------
# Template Tracker
# ---------------------------------------------------------------------------

class TemplateTracker:
    """Cycles through templates for diversity."""

    def __init__(self):
        self._indices: dict[str, int] = {}
        self._templates: dict[str, list] = {}
        self._load_templates()

    def _load_templates(self):
        """Load all template families from the distiller."""
        try:
            from hiveai.lora.distiller import (
                TEMPLATES, O1_TEMPLATES, EXPLAIN_TEMPLATES,
                CPP_TEMPLATES, RUST_TEMPLATES, GO_TEMPLATES, JS_TEMPLATES,
            )
            self._templates["python"] = TEMPLATES + O1_TEMPLATES + EXPLAIN_TEMPLATES
            self._templates["cpp"] = CPP_TEMPLATES
            self._templates["rust"] = RUST_TEMPLATES
            self._templates["go"] = GO_TEMPLATES
            self._templates["javascript"] = JS_TEMPLATES
        except Exception as e:
            logger.warning(f"Miner: failed to load templates: {e}")
            self._templates["python"] = [
                ("implement",
                 "Implement {concept} in Python. Show the complete approach, explain "
                 "the reasoning step by step, cover edge cases, and include at least "
                 "3 working code examples ranging from basic to production-ready."),
            ]

    def next_template(self, language: str) -> tuple[str, str]:
        """Return (template_key, template_text) for the given language."""
        # Fall back to python templates if language not found
        lang = language if language in self._templates else "python"
        templates = self._templates.get(lang, self._templates.get("python", []))

        if not templates:
            return ("implement", "Implement {concept}. Show working code examples.")

        idx = self._indices.get(lang, 0)
        idx = idx % len(templates)
        key, text = templates[idx]
        self._indices[lang] = idx + 1
        return key, text


# ---------------------------------------------------------------------------
# Mining Statistics
# ---------------------------------------------------------------------------

@dataclass
class MinerStats:
    """Aggregate mining statistics."""
    started_at: float = 0.0
    total_generated: int = 0
    total_eligible: int = 0
    total_rejected_quality: int = 0
    total_rejected_dedup: int = 0
    errors: int = 0
    per_provider: dict = field(default_factory=dict)
    per_language: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Miner Worker
# ---------------------------------------------------------------------------

class MinerWorker:
    """Background daemon that continuously mines training pairs from multiple providers."""

    def __init__(self):
        self.router = ProviderRouter()
        self.topics = TopicTracker()
        self.templates = TemplateTracker()
        self._shutdown = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self.stats = MinerStats()

    def start(self):
        """Start the mining worker as a daemon thread."""
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info("Multi-source miner worker started")

    def stop(self):
        """Signal the worker to stop gracefully."""
        self._shutdown.set()

    def pause(self):
        """Pause mining."""
        self._paused.set()
        logger.info("Miner paused")

    def resume(self):
        """Resume mining."""
        self._paused.clear()
        logger.info("Miner resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    def _worker_loop(self):
        """Main loop: pick provider -> topic -> template -> generate -> score -> persist."""
        from hiveai.config import MINER_STARTUP_DELAY, MINER_INTERVAL_SECONDS, MINER_DAILY_TARGET

        time.sleep(MINER_STARTUP_DELAY)
        self.stats.started_at = time.time()
        logger.info(f"Miner worker active after {MINER_STARTUP_DELAY}s startup delay")

        while not self._shutdown.is_set():
            try:
                # Check pause
                if self._paused.is_set():
                    time.sleep(5)
                    continue

                # Check daily target
                if self.stats.total_eligible >= MINER_DAILY_TARGET:
                    logger.info(f"Miner: daily target reached ({self.stats.total_eligible} pairs)")
                    time.sleep(60)
                    continue

                # Get next provider
                provider_state = self.router.next_provider()
                if not provider_state:
                    logger.debug("Miner: no providers available, sleeping 60s")
                    time.sleep(60)
                    continue

                # Wait for rate limit
                wait = provider_state.wait_for_rate_limit()
                if wait > 0:
                    time.sleep(min(wait, 30))
                    continue

                # Pick topic and template
                topic, language = self.topics.next_topic()
                template_key, template_text = self.templates.next_template(language)

                # Generate one pair
                result = self._generate_one_pair(
                    provider_state, topic, template_key, template_text, language
                )

                if result:
                    self.stats.total_generated += 1
                    pname = provider_state.provider.name
                    self.stats.per_provider[pname] = self.stats.per_provider.get(pname, 0) + 1
                    self.stats.per_language[language] = self.stats.per_language.get(language, 0) + 1

                    if result.get("eligible"):
                        self.stats.total_eligible += 1
                        provider_state.total_pairs += 1
                    elif result.get("dedup"):
                        self.stats.total_rejected_dedup += 1
                    else:
                        self.stats.total_rejected_quality += 1

                    # Log progress every 25 pairs
                    if self.stats.total_generated % 25 == 0:
                        elapsed_h = max((time.time() - self.stats.started_at) / 3600, 0.01)
                        rate = self.stats.total_generated / elapsed_h
                        logger.info(
                            f"Miner progress: {self.stats.total_generated} generated, "
                            f"{self.stats.total_eligible} eligible, "
                            f"{rate:.0f}/hr, errors={self.stats.errors}"
                        )

            except Exception as e:
                self.stats.errors += 1
                logger.error(f"Miner worker error: {e}")
                time.sleep(10)

            time.sleep(MINER_INTERVAL_SECONDS)

    def _generate_one_pair(self, provider_state: ProviderState,
                           topic: str, template_key: str,
                           template_text: str, language: str) -> dict | None:
        """Generate a single training pair using a specific provider."""
        from hiveai.llm.prompts import (
            CODING_SYSTEM_PROMPT, CPP_SYSTEM_PROMPT,
            RUST_SYSTEM_PROMPT, GO_SYSTEM_PROMPT, JAVASCRIPT_SYSTEM_PROMPT,
        )
        from hiveai.config import MIN_TRAINING_QUALITY

        # Select system prompt for language
        system_prompts = {
            "python": CODING_SYSTEM_PROMPT,
            "cpp": CPP_SYSTEM_PROMPT,
            "rust": RUST_SYSTEM_PROMPT,
            "go": GO_SYSTEM_PROMPT,
            "javascript": JAVASCRIPT_SYSTEM_PROMPT,
        }
        system_prompt = system_prompts.get(language, CODING_SYSTEM_PROMPT)

        # Build instruction from template
        instruction = template_text.format(concept=topic)

        # Call provider
        response = self._provider_call(instruction, provider_state, system_prompt)
        if not response:
            return None

        # Clean response
        try:
            from hiveai.lora.distiller import _clean_response, _score_quality
            response = _clean_response(response)
        except Exception:
            pass

        # Score quality
        try:
            from hiveai.lora.distiller import _score_quality
            quality = _score_quality(instruction, response)
        except Exception as e:
            logger.debug(f"Miner: scoring failed: {e}")
            return {"eligible": False}

        if quality < MIN_TRAINING_QUALITY:
            logger.debug(f"Miner: {provider_state.provider.name} pair quality "
                         f"{quality:.3f} < {MIN_TRAINING_QUALITY} (topic: {topic[:50]})")
            return {"eligible": False}

        # Persist via the distiller's persist function
        try:
            from hiveai.models import SessionLocal
            db = SessionLocal()
            try:
                from hiveai.lora.distiller import _persist_pair
                pair_dict = {
                    "source": f"multi_mine_{provider_state.provider.name}",
                    "topic": topic,
                    "instruction": instruction,
                    "response": response,
                    "quality": quality,
                    "is_eligible": True,
                    "metadata": {
                        "provider": provider_state.provider.name,
                        "model": random.choice(provider_state.provider.models),
                        "template_key": template_key,
                        "language": language,
                    },
                }
                _persist_pair(db, pair_dict)
                db.commit()
                logger.debug(f"Miner: {provider_state.provider.name} pair persisted "
                             f"quality={quality:.3f} topic={topic[:50]}")
                return {"eligible": True}
            except Exception as e:
                if "duplicate" in str(e).lower() or "dedup" in str(e).lower():
                    return {"eligible": False, "dedup": True}
                db.rollback()
                logger.debug(f"Miner: persist failed: {e}")
                return {"eligible": False, "dedup": True}
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Miner: DB error: {e}")
            return {"eligible": False}

    def _provider_call(self, prompt: str, provider_state: ProviderState,
                       system_prompt: str, max_tokens: int = 4096) -> str | None:
        """Make an LLM call to a specific external provider."""
        provider = provider_state.provider

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=provider_state.api_key or "none",
                base_url=provider.base_url,
            )

            model = random.choice(provider.models) if provider.models else "default"

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )

            content = response.choices[0].message.content or ""

            # Strip thinking blocks (DeepSeek R1, etc.)
            if provider.requires_thinking and "</think>" in content:
                content = content.split("</think>", 1)[1].strip()

            provider_state.record_request()
            provider_state.record_success()

            return content if content.strip() else None

        except Exception as e:
            provider_state.record_request()
            provider_state.record_failure(str(e))
            logger.warning(f"Miner: {provider.name} call failed: {e}")
            return None

    def get_status(self) -> dict:
        """Return current miner status for the API."""
        elapsed_h = max((time.time() - self.stats.started_at) / 3600, 0.01) if self.stats.started_at else 0
        return {
            "enabled": True,
            "paused": self.is_paused,
            "stats": {
                "started_at": self.stats.started_at,
                "total_generated": self.stats.total_generated,
                "total_eligible": self.stats.total_eligible,
                "rejected_quality": self.stats.total_rejected_quality,
                "rejected_dedup": self.stats.total_rejected_dedup,
                "errors": self.stats.errors,
                "pairs_per_hour": round(self.stats.total_generated / elapsed_h, 1) if elapsed_h else 0,
                "per_provider": self.stats.per_provider,
                "per_language": self.stats.per_language,
            },
            "providers": self.router.get_stats(),
        }


# ---------------------------------------------------------------------------
# Module-level singleton and API
# ---------------------------------------------------------------------------

_miner_instance: MinerWorker | None = None


def start_miner():
    """Initialize and start the miner singleton."""
    global _miner_instance
    if _miner_instance is not None:
        return _miner_instance
    _miner_instance = MinerWorker()
    _miner_instance.start()
    return _miner_instance


def get_miner_status() -> dict:
    """Return miner status for the API endpoint."""
    if _miner_instance is None:
        return {"enabled": False, "message": "Set MULTI_MINER_ENABLED=true to activate"}
    return _miner_instance.get_status()


def toggle_miner(paused: bool) -> dict:
    """Pause or resume the miner."""
    if _miner_instance is None:
        return {"error": "Miner not initialized", "paused": True}
    if paused:
        _miner_instance.pause()
    else:
        _miner_instance.resume()
    return {"paused": paused, "ok": True}
