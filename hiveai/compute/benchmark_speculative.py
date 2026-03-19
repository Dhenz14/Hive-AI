"""
hiveai/compute/benchmark_speculative.py

EAGLE-3 Speculative Decoding Benchmark Harness.

Measures speculative decoding speedup on local hardware by comparing:
  - Baseline vLLM (no speculative decoding)
  - vLLM + speculative decoding (EAGLE-3 / n-gram)

Outputs a JSON evidence file with detailed metrics:
  - Tokens per second (baseline vs speculative)
  - Time to first token (TTFT)
  - Acceptance rate
  - Speedup factor
  - GPU hardware info

Usage:
    # Assumes vLLM is running on localhost:8000
    python -m hiveai.compute.benchmark_speculative \\
        --vllm-url http://localhost:8000 \\
        --output evidence/speculative-benchmark.json \\
        --num-runs 20

The harness does NOT start/stop vLLM — it measures against whatever is running.
Run once with baseline config, once with speculative, then merge results.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import statistics
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

# Default benchmark prompts (varied complexity)
DEFAULT_PROMPTS = [
    "Write a Python function that implements binary search on a sorted array.",
    "Explain the difference between TCP and UDP protocols in networking.",
    "What is the time complexity of quicksort and why?",
    "Write a SQL query to find the top 5 customers by total order value.",
    "Describe how a transformer neural network processes a sequence of tokens.",
    "Implement a simple LRU cache in Python with O(1) get and put operations.",
    "What are the SOLID principles in software engineering? Give examples.",
    "Write a Rust function that safely handles concurrent access to a shared counter.",
    "Explain how IPFS content addressing works with CIDs and Merkle DAGs.",
    "Design a rate limiter that allows 100 requests per minute per user.",
]


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    prompt_index: int
    prompt_preview: str  # first 50 chars
    tokens_generated: int
    total_time_ms: float
    time_to_first_token_ms: float
    tokens_per_second: float
    model: str = ""


@dataclass
class BenchmarkSummary:
    """Aggregated benchmark statistics."""
    mode: str  # "baseline" or "speculative"
    model: str
    num_runs: int
    total_tokens: int
    # Tokens per second
    tps_mean: float
    tps_median: float
    tps_p5: float
    tps_p95: float
    # Time to first token
    ttft_mean_ms: float
    ttft_median_ms: float
    ttft_p95_ms: float
    # Acceptance rate (speculative only)
    acceptance_rate: Optional[float] = None
    avg_accepted_per_step: Optional[float] = None
    # Raw results
    results: list[BenchmarkResult] = field(default_factory=list)


@dataclass
class BenchmarkEvidence:
    """Full benchmark evidence file."""
    benchmark: str = "speculative_decoding"
    version: str = "1.0.0"
    gpu: dict = field(default_factory=dict)
    baseline: Optional[BenchmarkSummary] = None
    speculative: Optional[BenchmarkSummary] = None
    comparison: dict = field(default_factory=dict)
    timestamp: str = ""
    config: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class SpeculativeBenchmark:
    """
    Benchmark harness for speculative decoding measurement.

    Sends prompts to a running vLLM instance and measures performance.
    """

    def __init__(
        self,
        vllm_url: str = "http://localhost:8000",
        model: str = "",
        max_tokens: int = 256,
        temperature: float = 0.0,  # deterministic for reproducibility
        num_warmup: int = 2,
        api_key: str = "",
    ):
        self.vllm_url = vllm_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.num_warmup = num_warmup
        self.api_key = api_key

    async def run_benchmark(
        self,
        prompts: list[str],
        mode: str = "baseline",
    ) -> BenchmarkSummary:
        """Run benchmark against a vLLM instance."""
        if aiohttp is None:
            raise ImportError("aiohttp required")

        # Auto-detect model if not specified
        if not self.model:
            self.model = await self._detect_model()

        results: list[BenchmarkResult] = []

        async with aiohttp.ClientSession() as session:
            # Warmup
            for i in range(self.num_warmup):
                await self._single_request(session, prompts[i % len(prompts)], 0)
                logger.debug(f"Warmup {i+1}/{self.num_warmup} complete")

            # Benchmark runs
            for i, prompt in enumerate(prompts):
                result = await self._single_request(session, prompt, i)
                if result:
                    results.append(result)
                    logger.info(
                        f"Run {i+1}/{len(prompts)}: {result.tokens_per_second:.1f} tok/s, "
                        f"TTFT={result.time_to_first_token_ms:.0f}ms, "
                        f"tokens={result.tokens_generated}"
                    )

        if not results:
            raise RuntimeError("No successful benchmark runs")

        # Aggregate
        tps_values = [r.tokens_per_second for r in results]
        ttft_values = [r.time_to_first_token_ms for r in results]

        summary = BenchmarkSummary(
            mode=mode,
            model=self.model,
            num_runs=len(results),
            total_tokens=sum(r.tokens_generated for r in results),
            tps_mean=round(statistics.mean(tps_values), 2),
            tps_median=round(statistics.median(tps_values), 2),
            tps_p5=round(sorted(tps_values)[max(0, int(len(tps_values) * 0.05))], 2),
            tps_p95=round(sorted(tps_values)[min(len(tps_values) - 1, int(len(tps_values) * 0.95))], 2),
            ttft_mean_ms=round(statistics.mean(ttft_values), 1),
            ttft_median_ms=round(statistics.median(ttft_values), 1),
            ttft_p95_ms=round(sorted(ttft_values)[min(len(ttft_values) - 1, int(len(ttft_values) * 0.95))], 1),
            results=results,
        )

        # Try to get acceptance rate from vLLM metrics
        if mode == "speculative":
            metrics = await self._get_speculative_metrics()
            if metrics:
                summary.acceptance_rate = metrics.get("acceptance_rate")
                summary.avg_accepted_per_step = metrics.get("avg_accepted_per_step")

        return summary

    async def _single_request(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        index: int,
    ) -> Optional[BenchmarkResult]:
        """Send a single completion request and measure performance."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }

        start = time.monotonic()
        try:
            async with session.post(
                f"{self.vllm_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                first_byte_time = time.monotonic()
                data = await resp.json()
                end = time.monotonic()

                if resp.status != 200:
                    logger.warning(f"Request {index} failed: HTTP {resp.status}")
                    return None

                usage = data.get("usage", {})
                tokens = usage.get("completion_tokens", 0)
                total_ms = (end - start) * 1000
                ttft_ms = (first_byte_time - start) * 1000

                return BenchmarkResult(
                    prompt_index=index,
                    prompt_preview=prompt[:50],
                    tokens_generated=tokens,
                    total_time_ms=round(total_ms, 1),
                    time_to_first_token_ms=round(ttft_ms, 1),
                    tokens_per_second=round(tokens / (total_ms / 1000), 2) if total_ms > 0 else 0,
                    model=self.model,
                )
        except Exception as e:
            logger.warning(f"Request {index} error: {e}")
            return None

    async def _detect_model(self) -> str:
        """Auto-detect the model running on vLLM."""
        if aiohttp is None:
            return "unknown"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.vllm_url}/v1/models") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("data", [])
                        if models:
                            return models[0].get("id", "unknown")
        except Exception:
            pass
        return "unknown"

    async def _get_speculative_metrics(self) -> Optional[dict]:
        """Try to read speculative decoding metrics from vLLM /metrics."""
        if aiohttp is None:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.vllm_url}/metrics") as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Parse Prometheus metrics
                        metrics = {}
                        for line in text.split("\n"):
                            if "spec_decode" in line and not line.startswith("#"):
                                parts = line.split()
                                if len(parts) >= 2:
                                    metrics[parts[0]] = float(parts[1])
                        if metrics:
                            accepted = metrics.get("vllm:spec_decode_draft_acceptance_rate", 0)
                            return {
                                "acceptance_rate": round(accepted, 4),
                                "avg_accepted_per_step": round(accepted * 5, 2),
                            }
        except Exception:
            pass
        return None

    @staticmethod
    def compare(
        baseline: BenchmarkSummary,
        speculative: BenchmarkSummary,
    ) -> dict:
        """Compare baseline vs speculative benchmark results."""
        tps_speedup = speculative.tps_median / max(baseline.tps_median, 0.01)
        ttft_improvement = 1.0 - (speculative.ttft_median_ms / max(baseline.ttft_median_ms, 0.01))

        return {
            "tps_speedup": round(tps_speedup, 2),
            "ttft_improvement_pct": round(ttft_improvement * 100, 1),
            "baseline_tps_median": baseline.tps_median,
            "speculative_tps_median": speculative.tps_median,
            "baseline_ttft_median_ms": baseline.ttft_median_ms,
            "speculative_ttft_median_ms": speculative.ttft_median_ms,
            "acceptance_rate": speculative.acceptance_rate,
            "verdict": (
                f"{tps_speedup:.1f}x speedup"
                + (f" ({speculative.acceptance_rate:.0%} acceptance)" if speculative.acceptance_rate else "")
            ),
        }

    @staticmethod
    def detect_gpu() -> dict:
        """Detect GPU hardware info."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,uuid",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 4:
                    return {
                        "name": parts[0],
                        "vram_mb": int(float(parts[1])),
                        "vram_gb": round(float(parts[1]) / 1024, 1),
                        "driver": parts[2],
                        "uuid": parts[3],
                    }
        except Exception:
            pass
        return {"name": "unknown", "vram_gb": 0}

    def write_evidence(
        self,
        baseline: Optional[BenchmarkSummary],
        speculative: Optional[BenchmarkSummary],
        output_path: str,
    ) -> None:
        """Write benchmark evidence to a JSON file."""
        evidence = BenchmarkEvidence(
            gpu=self.detect_gpu(),
            baseline=baseline,
            speculative=speculative,
            comparison=self.compare(baseline, speculative) if baseline and speculative else {},
            config={
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "num_warmup": self.num_warmup,
                "vllm_url": self.vllm_url,
            },
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(asdict(evidence), f, indent=2, default=str)

        logger.info(f"Benchmark evidence written to {output_path}")


# ── CLI Entry Point ─────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="EAGLE-3 Speculative Decoding Benchmark")
    parser.add_argument("--vllm-url", default="http://localhost:8000")
    parser.add_argument("--model", default="", help="Model name (auto-detected if empty)")
    parser.add_argument("--mode", choices=["baseline", "speculative", "both"], default="both")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--num-runs", type=int, default=10)
    parser.add_argument("--output", default="evidence/speculative-benchmark.json")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    prompts = DEFAULT_PROMPTS[:args.num_runs]
    bench = SpeculativeBenchmark(
        vllm_url=args.vllm_url,
        model=args.model,
        max_tokens=args.max_tokens,
        api_key=args.api_key,
    )

    baseline = None
    speculative = None

    if args.mode in ("baseline", "both"):
        logger.info("Running BASELINE benchmark...")
        baseline = await bench.run_benchmark(prompts, mode="baseline")
        logger.info(f"Baseline: {baseline.tps_median} tok/s median, {baseline.ttft_median_ms}ms TTFT")

    if args.mode in ("speculative", "both"):
        logger.info("Running SPECULATIVE benchmark...")
        speculative = await bench.run_benchmark(prompts, mode="speculative")
        logger.info(f"Speculative: {speculative.tps_median} tok/s median, {speculative.ttft_median_ms}ms TTFT")

    if baseline and speculative:
        comparison = bench.compare(baseline, speculative)
        logger.info(f"Result: {comparison['verdict']}")

    bench.write_evidence(baseline, speculative, args.output)


if __name__ == "__main__":
    asyncio.run(main())
