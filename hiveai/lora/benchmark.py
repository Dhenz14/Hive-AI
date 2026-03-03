"""
hiveai/lora/benchmark.py

LoRA benchmark evaluator.

Before a LoRA is marked "ready":
  1. Sample a held-out test set (10% of eligible pairs never used in training)
  2. Run both base Qwen3 and Qwen3+LoRA on the same instructions
  3. Score responses: code quality, reasoning depth, length ratio
  4. Require LoRA to beat base model by >= 5% on held-out set

Currently a functional stub: scoring logic is implemented, Unsloth
model loading requires the same CUDA environment as trainer.py.

Usage:
  from hiveai.lora.benchmark import run_benchmark
  result = run_benchmark(db, adapter_path="loras/coding_v1/", sample_size=50)
"""
import logging
import random
import re

logger = logging.getLogger(__name__)

MIN_IMPROVEMENT = 0.05     # LoRA must beat base by 5%
DEFAULT_SAMPLE_SIZE = 50   # held-out pairs to evaluate


def run_benchmark(db, adapter_path: str, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict:
    """
    Run held-out benchmark comparing base model vs LoRA.

    Returns:
        {
            "base_score": float,
            "lora_score": float,
            "delta": float,
            "passed": bool,
            "sample_size": int,
        }
    """
    held_out = _get_held_out_pairs(db, sample_size)
    if not held_out:
        return {"error": "No held-out pairs available for benchmarking"}

    if not _check_unsloth():
        # Return a dry-run result when Unsloth isn't available
        logger.warning("Unsloth not available — returning placeholder benchmark result")
        return {
            "base_score": None,
            "lora_score": None,
            "delta": None,
            "passed": False,
            "sample_size": len(held_out),
            "note": "Install Unsloth to run actual benchmark inference",
        }

    logger.info(f"Benchmarking LoRA adapter at {adapter_path} on {len(held_out)} held-out pairs")

    base_scores = []
    lora_scores = []

    try:
        base_model, lora_model, tokenizer = _load_models(adapter_path)
    except Exception as e:
        logger.error(f"Failed to load models for benchmarking: {e}")
        return {"error": str(e)}

    for pair in held_out:
        instruction = pair.instruction
        reference = pair.response

        base_response = _generate(base_model, tokenizer, instruction)
        lora_response = _generate(lora_model, tokenizer, instruction)

        base_scores.append(_score_response(base_response, reference))
        lora_scores.append(_score_response(lora_response, reference))

    base_avg = sum(base_scores) / len(base_scores) if base_scores else 0.0
    lora_avg = sum(lora_scores) / len(lora_scores) if lora_scores else 0.0
    delta = lora_avg - base_avg
    passed = delta >= MIN_IMPROVEMENT

    logger.info(f"Benchmark: base={base_avg:.3f}, lora={lora_avg:.3f}, delta={delta:+.3f}, passed={passed}")
    return {
        "base_score": base_avg,
        "lora_score": lora_avg,
        "delta": delta,
        "passed": passed,
        "sample_size": len(held_out),
    }


def _get_held_out_pairs(db, sample_size: int) -> list:
    """
    Return pairs that were NOT used in any training run (lora_version IS NULL).
    These are the true held-out test set.
    """
    from hiveai.models import TrainingPair
    candidates = db.query(TrainingPair).filter(
        TrainingPair.is_eligible == True,
        TrainingPair.lora_version.is_(None),
    ).all()

    if not candidates:
        return []

    n = min(sample_size, len(candidates))
    return random.sample(candidates, n)


def _score_response(response: str, reference: str) -> float:
    """
    Heuristic scoring for a generated response vs reference.

    Dimensions:
      - Code presence (0-0.4): does the response contain code blocks?
      - Length ratio (0-0.3): is response length within 50-200% of reference?
      - Keyword overlap (0-0.3): shared technical terms with reference

    Returns 0.0 – 1.0
    """
    if not response:
        return 0.0

    score = 0.0

    # Code block presence
    code_blocks = len(re.findall(r"```", response))
    ref_code_blocks = len(re.findall(r"```", reference))
    if ref_code_blocks > 0:
        if code_blocks >= ref_code_blocks:
            score += 0.4
        elif code_blocks > 0:
            score += 0.2
    else:
        score += 0.2  # no code expected, give partial credit for any response

    # Length ratio
    resp_words = len(response.split())
    ref_words = len(reference.split())
    if ref_words > 0:
        ratio = resp_words / ref_words
        if 0.5 <= ratio <= 2.0:
            score += 0.3
        elif 0.3 <= ratio <= 3.0:
            score += 0.15

    # Keyword overlap (technical terms: words >= 5 chars)
    ref_keywords = set(w.lower() for w in reference.split() if len(w) >= 5)
    resp_keywords = set(w.lower() for w in response.split() if len(w) >= 5)
    if ref_keywords:
        overlap = len(ref_keywords & resp_keywords) / len(ref_keywords)
        score += overlap * 0.3

    return min(score, 1.0)


def _check_unsloth() -> bool:
    try:
        import unsloth  # noqa: F401
        return True
    except ImportError:
        return False


def _load_models(adapter_path: str):
    """Load base model and LoRA-merged model for comparison."""
    from unsloth import FastLanguageModel
    from hiveai.config import OLLAMA_MODEL_REASONING

    base_model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=OLLAMA_MODEL_REASONING,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(base_model)

    lora_model, _ = FastLanguageModel.from_pretrained(
        model_name=adapter_path,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(lora_model)

    return base_model, lora_model, tokenizer


def _generate(model, tokenizer, instruction: str, max_new_tokens: int = 512) -> str:
    """Generate a response from a model given an instruction."""
    import torch
    prompt = (
        "Below is an instruction that describes a task. "
        "Write a response that appropriately completes the request.\n\n"
        f"### Instruction:\n{instruction}\n\n"
        "### Input:\n\n### Response:\n"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.3,
            do_sample=True,
        )
    generated = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return generated.strip()
