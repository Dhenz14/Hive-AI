#!/usr/bin/env python3
"""Train HiveAI LoRA via GRPO (Group Relative Policy Optimization).

Reward: code validity 30% + concept coverage 20% + test passing 30% + LLM certificate 20%.

Usage: python train_grpo.py --warm-start loras/v8 --output-dir loras/v8_grpo
       python train_grpo.py --warm-start loras/v8 --dry-run --no-cert
"""
import ast
import faulthandler
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None
faulthandler.enable(file=sys.stderr, all_threads=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MAX_SEQ_LENGTH = 2048
LORA_CONFIG = {
    "r": 16, "lora_alpha": 32,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "lora_dropout": 0.0, "bias": "none", "use_dora": False, "use_rslora": True,
}

# Reward dimension weights (must sum to 1.0)
W_CODE_VALIDITY = 0.30
W_CONCEPT_COV   = 0.20
W_TEST_PASS     = 0.30
W_CERTIFICATE   = 0.20

# --- Reward: Code Validity (30%) ---
_STRUCT_CHECKS = [
    (r"(fn |func |def |class |struct |impl |interface )", 0.3),
    (r"(\{[\s\S]*\})", 0.2), (r"(return |->|=>)", 0.2),
    (r"(import |use |#include|package )", 0.15), (r"(if |for |while |match |switch )", 0.15)]


def reward_code_validity(prompts, completions, **kwargs):
    """AST parse for Python, structural heuristics for other languages."""
    rewards = []
    for completion in completions:
        blocks = _extract_code(_get_text(completion))
        if not blocks:
            rewards.append(0.0); continue
        scores = []
        for lang, code in blocks[:4]:
            if lang in ("python", "py", ""):
                try: ast.parse(code); scores.append(1.0)
                except SyntaxError: scores.append(0.2)
            else:
                s = sum(w for pat, w in _STRUCT_CHECKS if re.search(pat, code))
                scores.append(min(s, 1.0))
        rewards.append(sum(scores) / len(scores))
    return rewards


# --- Reward: Concept Coverage (20%) ---
def reward_concept_coverage(prompts, completions, **kwargs):
    """Score how many expected concepts from the prompt appear in the response."""
    concept_meta = kwargs.get("concept_meta", {})
    rewards = []
    for i, completion in enumerate(completions):
        text = _get_text(completion).lower()
        prompt_text = _get_prompt_text(prompts[i]).lower()

        # Use explicit expected_concepts if available (from eval_challenges)
        expected = concept_meta.get(i, [])
        if not expected:
            expected = _extract_implicit_concepts(prompt_text)
        if not expected:
            rewards.append(0.7)  # No concepts to check, partial credit
            continue

        covered = sum(1 for c in expected if c.lower() in text)
        rewards.append(covered / len(expected))
    return rewards


def _extract_implicit_concepts(prompt_text):
    """Extract technical concepts from prompt text via keyword patterns."""
    pats = [r"\b(async|await|promise|future|channel|goroutine|mutex)\b",
            r"\b(recursion|iteration|memoiz|dynamic programming)\b",
            r"\b(tree|graph|hash|stack|queue|heap|linked list|trie)\b",
            r"\b(REST|GraphQL|WebSocket|HTTP|gRPC|API)\b",
            r"\b(test|mock|stub|fixture|assert)\b",
            r"\b(generic|template|trait|interface|abstract)\b",
            r"\b(closure|lambda|higher.order|callback|decorator)\b",
            r"\b(error handling|exception|panic|Result|Option)\b"]
    concepts = set()
    for pat in pats:
        for m in re.findall(pat, prompt_text, re.I):
            concepts.add(m.lower() if isinstance(m, str) else m[0].lower())
    return list(concepts)


# --- Reward: Test Passing (30%) ---
def reward_test_passing(prompts, completions, **kwargs):
    """Execute test_code against generated code. Strongest signal."""
    test_meta = kwargs.get("test_meta", {})
    rewards = []
    for i, completion in enumerate(completions):
        text = _get_text(completion)
        blocks = _extract_code(text)
        if not blocks:
            rewards.append(0.0)
            continue
        py_blocks = [code for lang, code in blocks if lang in ("python", "py", "")]
        test_code = test_meta.get(i, "")
        if py_blocks:
            combined = "\n\n".join(py_blocks) + ("\n\n" + test_code if test_code else "")
            rewards.append(_run_python(combined))
        elif test_code:
            rewards.append(0.3)  # Non-Python with Python test
        else:
            rewards.append(0.5)  # Non-Python, no test — structural credit
    return rewards


def _run_python(code, timeout=10):
    """Execute Python code in subprocess. Returns 1.0 on success, 0.0-0.3 on failure."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        r = subprocess.run([sys.executable, tmp], capture_output=True, timeout=timeout, text=True)
        if r.returncode == 0:
            return 1.0
        elif "AssertionError" in r.stderr or "AssertionError" in r.stdout:
            return 0.2  # Ran but tests failed
        return 0.3  # Other error
    except subprocess.TimeoutExpired:
        return 0.1
    except Exception:
        return 0.0
    finally:
        Path(tmp).unlink(missing_ok=True)


# --- Reward: Certificate Verification (20%) ---
_CERT_TPL = ("You are a code review judge. Rate this response 0.0-1.0 on correctness, "
             "completeness, idiom quality, and safety.\n\nPrompt: {prompt}\n\n"
             "Response:\n{response}\n\nReply ONLY: {{\"score\": 0.0-1.0, \"reason\": \"...\"}}")


def reward_certificate(prompts, completions, **kwargs):
    """LLM-as-judge for non-Python code where execution isn't available."""
    if kwargs.get("no_cert", False):
        return [0.5] * len(completions)
    rewards = []
    for i, completion in enumerate(completions):
        text = _get_text(completion)
        blocks = _extract_code(text)
        if blocks and not any(l not in ("python", "py", "") for l, _ in blocks):
            rewards.append(0.5)  # Pure Python — test_passing covers it
            continue
        rewards.append(_llm_judge(_get_prompt_text(prompts[i]), text))
    return rewards


def _llm_judge(prompt_text, response_text, timeout=30):
    """Call local llama-server for LLM-as-judge scoring. Returns 0.5 on any failure."""
    try:
        import requests
        r = requests.post("http://localhost:11435/v1/chat/completions", timeout=timeout,
                          json={"model": "hiveai", "temperature": 0.0, "max_tokens": 100,
                                "messages": [{"role": "user", "content": _CERT_TPL.format(
                                    prompt=prompt_text[:500], response=response_text[:2000])}]})
        if r.status_code != 200:
            return 0.5
        m = re.search(r'"score"\s*:\s*([\d.]+)', r.json()["choices"][0]["message"]["content"])
        return float(m.group(1)) if m else 0.5
    except Exception:
        return 0.5


# --- Composite Reward ---
def composite_reward(prompts, completions, **kwargs):
    """Single reward function that combines all 4 dimensions with proper weights."""
    r_valid = reward_code_validity(prompts, completions, **kwargs)
    r_concept = reward_concept_coverage(prompts, completions, **kwargs)
    r_test = reward_test_passing(prompts, completions, **kwargs)
    r_cert = reward_certificate(prompts, completions, **kwargs)

    rewards = []
    for i in range(len(completions)):
        score = (W_CODE_VALIDITY * r_valid[i] + W_CONCEPT_COV * r_concept[i] +
                 W_TEST_PASS * r_test[i] + W_CERTIFICATE * r_cert[i])
        rewards.append(score)
    return rewards


# --- Helpers ---
def _get_text(completion):
    if isinstance(completion, list):
        return completion[0]["content"] if completion else ""
    return str(completion)


def _get_prompt_text(prompt):
    if isinstance(prompt, list):
        return prompt[-1]["content"] if prompt else ""
    return str(prompt)


def _extract_code(text):
    """Extract (language, code) tuples from markdown fenced blocks."""
    pattern = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)
    blocks = []
    for m in pattern.finditer(text):
        lang = m.group(1).lower()
        code = m.group(2).strip()
        if code:
            blocks.append((lang, code))
    return blocks


# --- Seed Prompt Loading ---
def load_seed_prompts(seed_path=None, max_prompts=0):
    """Load seed prompts from JSONL, eval_challenges.json, and/or training data."""
    try:
        from hiveai.llm.prompts import CODING_SYSTEM_PROMPT as SYS
    except ImportError:
        SYS = "You are HiveAI, an expert coding assistant."

    prompts, concept_meta, test_meta, seen = [], {}, {}, set()
    cap = max_prompts or 9999

    def _add(instruction, concepts=None, test_code=None):
        key = instruction[:100]
        if key in seen or len(instruction) < 20 or len(prompts) >= cap:
            return
        seen.add(key)
        idx = len(prompts)
        prompts.append([{"role": "system", "content": SYS}, {"role": "user", "content": instruction}])
        if concepts:
            concept_meta[idx] = concepts
        if test_code:
            test_meta[idx] = test_code

    # Source 1: explicit seed prompts JSONL
    if seed_path and os.path.exists(seed_path):
        for line in open(seed_path, "r", encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                _add(r["instruction"], r.get("expected_concepts"), r.get("test_code"))

    # Source 2: eval_challenges.json
    for name in ("eval_challenges.json", "eval_challenges_hard.json"):
        ep = os.path.join(PROJECT_ROOT, "scripts", name)
        if os.path.exists(ep):
            for ch in json.load(open(ep, "r", encoding="utf-8")):
                _add(ch["instruction"], ch.get("expected_concepts"), ch.get("test_code"))

    # Source 3: training data (first available)
    for jn in ("v8.jsonl", "v7.jsonl"):
        dp = os.path.join(PROJECT_ROOT, "loras", "training_data", jn)
        if os.path.exists(dp):
            for line in open(dp, "r", encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                inst = r.get("instruction", "")
                inp = r.get("input", "")
                _add(f"{inst}\n\n{inp}" if inp else inst)
                if len(prompts) >= (max_prompts or 500):
                    break
            break

    if max_prompts > 0:
        prompts = prompts[:max_prompts]
    logger.info(f"Loaded {len(prompts)} seed prompts ({len(concept_meta)} concepts, {len(test_meta)} tests)")
    return prompts, concept_meta, test_meta


def optimize_system():
    """Free VRAM (unload Ollama), set CUDA env vars."""
    try:
        import psutil, urllib.request
        logger.info(f"RAM: {psutil.virtual_memory().available / 1e9:.1f}GB avail")
        resp = urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/ps", method="GET"), timeout=3)
        for m in json.loads(resp.read().decode()).get("models", []):
            if m.get("name"):
                urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate",
                    data=json.dumps({"model": m["name"], "keep_alive": 0}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST"), timeout=5)
    except Exception:
        pass
    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:False,garbage_collection_threshold:0.6")


# --- GRPO Training ---
def train_grpo(args):
    """Main GRPO training loop."""
    import torch
    from datasets import Dataset

    warm_start = args.warm_start
    output_dir = args.output_dir
    candidates = args.candidates
    kl_coeff = args.kl_coeff
    epochs = args.epochs
    dry_run = args.dry_run
    no_cert = args.no_cert

    # Load seed prompts
    prompts, concept_meta, test_meta = load_seed_prompts(args.seed_prompts, max_prompts=args.max_prompts)
    if not prompts:
        logger.error("No seed prompts found. Run generate_seed_prompts.py first.")
        sys.exit(1)

    if dry_run:
        sample = prompts[:10]
        fake = ["```python\ndef hello():\n    return 'world'\n```\nExplanation."] * len(sample)
        scores = composite_reward(sample, fake, concept_meta=concept_meta, test_meta=test_meta, no_cert=no_cert)
        for i, s in enumerate(scores):
            logger.info(f"  Prompt {i}: reward={s:.3f}")
        logger.info(f"  DRY RUN mean reward: {sum(scores)/len(scores):.3f}")
        return

    # --- Load model ---
    FastLanguageModel = None
    try:
        from unsloth import FastLanguageModel as _FLM
        FastLanguageModel = _FLM
        logger.info("Unsloth imported")
    except ImportError:
        logger.warning("Unsloth not available, using standard path")

    load_start = time.time()
    if FastLanguageModel is not None:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=warm_start if os.path.isdir(warm_start) else "unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit",
            max_seq_length=MAX_SEQ_LENGTH, dtype=None, load_in_4bit=True,
        )
        model = FastLanguageModel.get_peft_model(model, **{k: v for k, v in LORA_CONFIG.items() if k != "use_dora"})
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, TaskType, get_peft_model
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
        base = warm_start if os.path.isdir(warm_start) else "Qwen/Qwen2.5-Coder-14B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(base, quantization_config=bnb,
                                                     device_map={"": 0}, torch_dtype=torch.bfloat16,
                                                     trust_remote_code=True)
        lora_cfg = LoraConfig(r=LORA_CONFIG["r"], lora_alpha=LORA_CONFIG["lora_alpha"],
                              target_modules=LORA_CONFIG["target_modules"],
                              lora_dropout=LORA_CONFIG["lora_dropout"], bias=LORA_CONFIG["bias"],
                              use_rslora=LORA_CONFIG["use_rslora"], task_type=TaskType.CAUSAL_LM)
        model = get_peft_model(model, lora_cfg)

    logger.info(f"Model loaded in {time.time() - load_start:.0f}s")
    if torch.cuda.is_available():
        logger.info(f"VRAM: {torch.cuda.memory_allocated() / 1e9:.1f}GB")

    # --- Build dataset ---
    dataset = Dataset.from_list([{"prompt": p} for p in prompts])

    # --- Build reward with metadata closure ---
    def reward_fn(prompts_batch, completions_batch, **kw):
        return composite_reward(prompts_batch, completions_batch,
                                concept_meta=concept_meta, test_meta=test_meta, no_cert=no_cert, **kw)

    # --- Configure and run GRPO ---
    from trl import GRPOConfig, GRPOTrainer

    grpo_args = GRPOConfig(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        num_train_epochs=epochs,
        learning_rate=args.lr if args.lr > 0 else 5e-5,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=1,
        save_steps=50,
        weight_decay=0.01,
        max_grad_norm=0.5,
        seed=42,
        num_generations=candidates,
        max_completion_length=1024,
        beta=kl_coeff,
        temperature=0.7,
        report_to="none",
    )

    logger.info(f"GRPO: {len(prompts)} prompts, K={candidates}, KL={kl_coeff}, "
                f"epochs={epochs}, cert={'OFF' if no_cert else 'ON'}, out={output_dir}")

    trainer = GRPOTrainer(
        model=model, processing_class=tokenizer,
        reward_funcs=[reward_fn], args=grpo_args, train_dataset=dataset,
    )

    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    logger.info(f"GRPO training complete in {elapsed / 3600:.1f}h")

    # --- Save ---
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    meta = {
        "training_type": "GRPO", "warm_start": warm_start,
        "num_prompts": len(prompts), "candidates": candidates,
        "kl_coeff": kl_coeff, "epochs": epochs, "no_cert": no_cert,
        "elapsed_hours": round(elapsed / 3600, 2),
        "reward_weights": {"code_validity": W_CODE_VALIDITY, "concept_coverage": W_CONCEPT_COV,
                           "test_passing": W_TEST_PASS, "certificate": W_CERTIFICATE},
        "lora_config": LORA_CONFIG,
    }
    with open(os.path.join(output_dir, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Adapter saved to {output_dir}")


# --- CLI ---
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Train HiveAI via GRPO (reinforcement learning from rewards)")
    p.add_argument("--warm-start", required=True, help="SFT adapter to start from (e.g. loras/v8)")
    p.add_argument("--output-dir", default=os.path.join(PROJECT_ROOT, "loras", "v8_grpo"),
                   help="Output directory for GRPO adapter")
    p.add_argument("--seed-prompts", default=None, help="Path to seed prompts JSONL")
    p.add_argument("--candidates", type=int, default=4, help="K candidates per prompt (default: 4)")
    p.add_argument("--epochs", type=int, default=1, help="Training epochs (default: 1)")
    p.add_argument("--kl-coeff", type=float, default=0.1, help="KL divergence penalty (default: 0.1)")
    p.add_argument("--max-prompts", type=int, default=0, help="Limit prompt count (0=all)")
    p.add_argument("--dry-run", action="store_true", help="Generate candidates + score without training")
    p.add_argument("--no-cert", action="store_true", help="Disable certificate verification in reward")
    p.add_argument("--rank", type=int, default=0,
                   help="Override LoRA rank (default: 16)")
    p.add_argument("--lr", type=float, default=0.0,
                   help="Override learning rate (default: 5e-5)")
    args = p.parse_args()

    if args.rank > 0:
        LORA_CONFIG["r"] = args.rank
        LORA_CONFIG["lora_alpha"] = args.rank * 2

    optimize_system()
    train_grpo(args)
