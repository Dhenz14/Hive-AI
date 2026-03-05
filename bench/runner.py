"""Model runner for benchmarking. Supports Ollama, llama-server, and speculative decoding."""

import json
import subprocess
import time
import requests
from dataclasses import dataclass, field


@dataclass
class GenerationResult:
    text: str = ""
    tokens_generated: int = 0
    prompt_tokens: int = 0
    time_to_first_token_ms: float = 0.0
    total_time_ms: float = 0.0
    tokens_per_sec: float = 0.0
    # Speculative decoding stats (only from llama-server)
    draft_tokens: int = 0
    accepted_tokens: int = 0
    acceptance_rate: float = 0.0
    error: str = ""


@dataclass
class ModelConfig:
    name: str
    backend: str = "ollama"  # "ollama" or "llama-server"
    base_url: str = "http://localhost:11434"
    draft_model: str = ""  # for speculative decoding
    context_size: int = 8192
    temperature: float = 0.2
    max_tokens: int = 2048


def get_vram_usage_mb() -> float:
    """Query nvidia-smi for current GPU VRAM usage."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip().split("\n")[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0.0


def generate_ollama(config: ModelConfig, prompt: str, system: str = "") -> GenerationResult:
    """Generate via Ollama's /api/chat endpoint, streaming to measure TTFT."""
    result = GenerationResult()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.name,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {
            "num_predict": config.max_tokens,
            "temperature": config.temperature,
            "num_ctx": config.context_size,
        },
    }

    start = time.perf_counter()
    first_token_time = None
    chunks = []

    try:
        resp = requests.post(
            f"{config.base_url}/api/chat",
            json=payload, stream=True, timeout=300,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            content = data.get("message", {}).get("content", "")
            if content:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                chunks.append(content)
            if data.get("done"):
                result.prompt_tokens = data.get("prompt_eval_count", 0)
                result.tokens_generated = data.get("eval_count", 0)
                break

    except Exception as e:
        result.error = str(e)
        return result

    end = time.perf_counter()
    result.text = "".join(chunks)
    result.total_time_ms = (end - start) * 1000
    if first_token_time is not None:
        result.time_to_first_token_ms = (first_token_time - start) * 1000
    if result.tokens_generated and result.total_time_ms > 0:
        # Exclude prompt processing time for generation speed
        gen_time = (end - (first_token_time or start))
        result.tokens_per_sec = result.tokens_generated / gen_time if gen_time > 0 else 0

    return result


def generate_llama_server(config: ModelConfig, prompt: str, system: str = "") -> GenerationResult:
    """Generate via llama-server's OpenAI-compatible /v1/chat/completions endpoint."""
    result = GenerationResult()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.name,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "stream": True,
    }

    start = time.perf_counter()
    first_token_time = None
    chunks = []
    token_count = 0

    try:
        resp = requests.post(
            f"{config.base_url}/v1/chat/completions",
            json=payload, stream=True, timeout=300,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    chunks.append(content)
                    token_count += 1

                # Extract usage stats if present (final chunk)
                usage = data.get("usage", {})
                if usage:
                    result.prompt_tokens = usage.get("prompt_tokens", 0)
                    result.tokens_generated = usage.get("completion_tokens", token_count)
            except (ValueError, KeyError):
                continue

    except Exception as e:
        result.error = str(e)
        return result

    end = time.perf_counter()
    result.text = "".join(chunks)
    if not result.tokens_generated:
        result.tokens_generated = token_count
    result.total_time_ms = (end - start) * 1000
    if first_token_time is not None:
        result.time_to_first_token_ms = (first_token_time - start) * 1000
    gen_time = end - (first_token_time or start)
    if result.tokens_generated and gen_time > 0:
        result.tokens_per_sec = result.tokens_generated / gen_time

    # Try to get speculative decoding stats from /health or /metrics
    result.draft_tokens, result.accepted_tokens, result.acceptance_rate = (
        _get_spec_decode_stats(config.base_url)
    )

    return result


def _get_spec_decode_stats(base_url: str) -> tuple[int, int, float]:
    """Try to extract speculative decoding stats from llama-server metrics."""
    try:
        resp = requests.get(f"{base_url}/metrics", timeout=2)
        if resp.status_code != 200:
            return 0, 0, 0.0
        text = resp.text
        draft = 0
        accepted = 0
        for line in text.split("\n"):
            if "speculative_decoding_tokens_drafted" in line and not line.startswith("#"):
                draft = int(float(line.split()[-1]))
            elif "speculative_decoding_tokens_accepted" in line and not line.startswith("#"):
                accepted = int(float(line.split()[-1]))
        rate = accepted / draft if draft > 0 else 0.0
        return draft, accepted, rate
    except Exception:
        return 0, 0, 0.0


def generate(config: ModelConfig, prompt: str, system: str = "") -> GenerationResult:
    """Route to the correct backend."""
    if config.backend == "llama-server":
        return generate_llama_server(config, prompt, system)
    return generate_ollama(config, prompt, system)
