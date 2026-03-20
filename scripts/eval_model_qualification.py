#!/usr/bin/env python3
"""
scripts/eval_model_qualification.py

Run qualification eval for Spirit Bomb tier models.

Tests a model against 10 prompts covering knowledge, code, math, reasoning.
Must score 60%+ to qualify for a tier slot.

Usage:
    # Eval the Claude distill against stock:
    python scripts/eval_model_qualification.py

    # Eval a specific model:
    python scripts/eval_model_qualification.py --model qwen3:14b

    # Eval and qualify (updates the model stack):
    python scripts/eval_model_qualification.py --model claude-distill-14b --qualify
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hiveai.compute.model_manager import ModelManager, EVAL_PROMPTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval")


async def run_eval(model_name: str, ollama_name: str = ""):
    """Run eval for a single model."""
    mgr = ModelManager()
    target = ollama_name or model_name

    logger.info(f"\n{'='*60}")
    logger.info(f"  EVALUATING: {model_name}")
    logger.info(f"  Ollama target: {target}")
    logger.info(f"  Prompts: {len(EVAL_PROMPTS)}")
    logger.info(f"{'='*60}\n")

    result = await mgr.eval_model(model_name, target)

    logger.info(f"\n{'='*60}")
    logger.info(f"  RESULTS: {model_name}")
    logger.info(f"  Score: {result.score}% ({result.correct}/{result.eval_prompts})")
    logger.info(f"  Avg latency: {result.avg_latency_ms:.0f}ms")
    logger.info(f"  Avg tokens: {result.avg_tokens:.0f}")
    logger.info(f"  Qualified: {'YES' if result.score >= 60 else 'NO'} (threshold: 60%)")
    logger.info(f"{'='*60}\n")

    # Save results
    results_dir = PROJECT_ROOT / "evidence" / "model-evals"
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_name = model_name.replace("/", "_").replace(":", "_")
    results_path = results_dir / f"{safe_name}-eval.json"
    with open(results_path, "w") as f:
        json.dump({
            "model": model_name,
            "ollama_name": target,
            "score": result.score,
            "correct": result.correct,
            "total": result.eval_prompts,
            "avg_latency_ms": result.avg_latency_ms,
            "avg_tokens": result.avg_tokens,
            "timestamp": result.timestamp,
            "details": result.details,
        }, f, indent=2)
    logger.info(f"Results saved to: {results_path}")

    return result


async def compare_models():
    """Compare stock qwen3:14b vs Claude distill."""
    logger.info("\n" + "=" * 60)
    logger.info("  SPIRIT BOMB MODEL QUALIFICATION")
    logger.info("  Comparing: qwen3:14b vs Claude-Opus-Distill")
    logger.info("=" * 60 + "\n")

    # Test stock model
    stock = await run_eval("qwen3:14b")

    # Test Claude distill (if downloaded)
    distill_name = "hf.co/Otakadelic/Qwen3-14B-Claude-4.5-Opus-High-Reasoning-Distill-Q6_K-GGUF"
    try:
        distill = await run_eval("claude-distill-14b", distill_name)
    except Exception as e:
        logger.warning(f"Claude distill not available yet: {e}")
        logger.info("Download it with: ollama pull " + distill_name)
        distill = None

    # Compare
    logger.info("\n" + "=" * 60)
    logger.info("  COMPARISON SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  qwen3:14b (stock):    {stock.score}% | {stock.avg_latency_ms:.0f}ms avg")
    if distill:
        logger.info(f"  Claude distill (Q6K): {distill.score}% | {distill.avg_latency_ms:.0f}ms avg")
        if distill.score > stock.score:
            logger.info(f"\n  WINNER: Claude distill (+{distill.score - stock.score:.1f}%)")
        elif stock.score > distill.score:
            logger.info(f"\n  WINNER: Stock qwen3:14b (+{stock.score - distill.score:.1f}%)")
        else:
            logger.info(f"\n  TIE — keeping stock (faster)")
    else:
        logger.info(f"  Claude distill: NOT YET DOWNLOADED")
    logger.info("=" * 60)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Spirit Bomb Model Qualification Eval")
    parser.add_argument("--model", default="", help="Specific model to eval")
    parser.add_argument("--ollama-name", default="", help="Ollama model identifier")
    parser.add_argument("--compare", action="store_true", help="Compare stock vs distill")
    args = parser.parse_args()

    if args.model:
        await run_eval(args.model, args.ollama_name)
    else:
        await compare_models()


if __name__ == "__main__":
    asyncio.run(main())
