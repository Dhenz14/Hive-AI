"""
scripts/preflight.py

Pre-training quality control system for HiveAI LoRA training.
Catches data, config, and model problems in ~15 minutes instead of 15 hours.

Four gates:
  Gate 1: Data Audit        (~30s)  — JSONL integrity, format, quality, coverage
  Gate 2: Config Sanity     (~10s)  — LoRA targets, VRAM budget, format alignment
  Gate 3: Micro-Train       (~15m)  — 10-step smoke test: loss, grads, accuracy
  Gate 4: In-Flight Monitor (async) — checkpoint eval, early stopping, plateau detection

Usage:
  python scripts/preflight.py audit  <jsonl_path>              # Gate 1 only
  python scripts/preflight.py config <jsonl_path> <model_path> # Gate 2 only
  python scripts/preflight.py smoke  <jsonl_path> <model_path> # Gate 3 only
  python scripts/preflight.py full   <jsonl_path> <model_path> # Gates 1+2+3
  python scripts/preflight.py monitor <log_path>               # Gate 4 (attach to running)

Exit codes:
  0 = all gates passed
  1 = gate failed (do NOT proceed to training)
  2 = warnings (proceed with caution)
"""
import json
import logging
import os
import re
import sys
import time
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("preflight")

# ── Thresholds ──────────────────────────────────────────────────────────────
MAX_DUPLICATE_RATIO = 0.15        # >15% near-dupes → fail (excluding intentional oversampling)
MAX_TRUNCATION_RATIO = 0.40       # >40% pairs exceed max_seq_length → fail (trainer truncates gracefully)
MIN_PAIRS = 100                   # Fewer than 100 pairs → fail
MIN_QUALITY_MEAN = 0.65           # Average quality below this → fail
MIN_CODE_BLOCK_RATIO = 0.40       # <40% pairs have code blocks → warning
MAX_SINGLE_SOURCE_RATIO = 0.90    # >90% from one source → warning
MICRO_TRAIN_STEPS = 10            # Smoke test steps
LOSS_DECREASE_THRESHOLD = 0.05    # Loss must drop at least 5% in 10 steps
GRAD_NORM_MAX = 5.0               # Gradient explosion threshold
GRAD_NORM_MIN = 1e-6              # Gradient vanishing threshold
ACCURACY_IMPROVEMENT_MIN = 0.01   # Token accuracy must improve at least 1%

# ── ANSI colors ─────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _pass(msg):
    log.info(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg):
    log.info(f"  {RED}FAIL{RESET}  {msg}")


def _warn(msg):
    log.info(f"  {YELLOW}WARN{RESET}  {msg}")


def _info(msg):
    log.info(f"  {CYAN}INFO{RESET}  {msg}")


# ════════════════════════════════════════════════════════════════════════════
# GATE 1: DATA AUDIT
# ════════════════════════════════════════════════════════════════════════════

def gate_data_audit(jsonl_path: str, max_seq_length: int = 4096) -> dict:
    """
    Validate training JSONL file integrity, quality, and coverage.
    Returns dict with 'passed', 'warnings', 'errors', and 'stats'.
    """
    log.info(f"\n{BOLD}{'='*60}")
    log.info(f"GATE 1: DATA AUDIT")
    log.info(f"{'='*60}{RESET}")
    log.info(f"File: {jsonl_path}")

    errors = []
    warnings = []
    stats = {}

    # ── 1a. File exists and parses ──────────────────────────────────────
    if not os.path.exists(jsonl_path):
        _fail(f"File not found: {jsonl_path}")
        return {"passed": False, "errors": ["File not found"], "warnings": [], "stats": {}}

    pairs = []
    parse_errors = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                obj["_line"] = i
                pairs.append(obj)
            except json.JSONDecodeError as e:
                parse_errors += 1
                if parse_errors <= 3:
                    _fail(f"JSON parse error on line {i}: {e}")

    if parse_errors > 0:
        errors.append(f"{parse_errors} JSON parse errors")
        _fail(f"{parse_errors} lines failed to parse")
    else:
        _pass(f"All {len(pairs)} lines parse as valid JSON")

    if len(pairs) < MIN_PAIRS:
        _fail(f"Only {len(pairs)} pairs (minimum: {MIN_PAIRS})")
        errors.append(f"Too few pairs: {len(pairs)}")
    else:
        _pass(f"{len(pairs)} pairs (>= {MIN_PAIRS} minimum)")
    stats["total_pairs"] = len(pairs)

    if not pairs:
        return {"passed": False, "errors": errors, "warnings": warnings, "stats": stats}

    # ── 1b. Required fields ─────────────────────────────────────────────
    missing_fields = 0
    for p in pairs:
        if "instruction" not in p or "output" not in p:
            missing_fields += 1
    if missing_fields > 0:
        _fail(f"{missing_fields} pairs missing 'instruction' or 'output' field")
        errors.append(f"{missing_fields} pairs with missing fields")
    else:
        _pass("All pairs have 'instruction' and 'output' fields")

    # ── 1c. Empty content check ─────────────────────────────────────────
    empty_instructions = sum(1 for p in pairs if not p.get("instruction", "").strip())
    empty_outputs = sum(1 for p in pairs if not p.get("output", "").strip())
    if empty_instructions > 0:
        _fail(f"{empty_instructions} pairs have empty instructions")
        errors.append(f"{empty_instructions} empty instructions")
    if empty_outputs > 0:
        _fail(f"{empty_outputs} pairs have empty outputs")
        errors.append(f"{empty_outputs} empty outputs")
    if empty_instructions == 0 and empty_outputs == 0:
        _pass("No empty instructions or outputs")

    # ── 1d. Quality distribution ────────────────────────────────────────
    has_metadata = any("metadata" in p for p in pairs)
    qualities = []
    if has_metadata:
        for p in pairs:
            q = p.get("metadata", {}).get("quality", None)
            if q is not None:
                qualities.append(float(q))
    # Also check top-level quality field (some exporters put it there)
    if not qualities:
        for p in pairs:
            q = p.get("quality", None)
            if q is not None:
                qualities.append(float(q))

    if qualities:
        avg_q = statistics.mean(qualities)
        med_q = statistics.median(qualities)
        min_q = min(qualities)
        max_q = max(qualities)
        stats["quality"] = {
            "mean": round(avg_q, 3),
            "median": round(med_q, 3),
            "min": round(min_q, 3),
            "max": round(max_q, 3),
            "count_with_quality": len(qualities),
        }

        # Histogram
        buckets = Counter()
        for q in qualities:
            bucket = f"{int(q*10)/10:.1f}-{int(q*10)/10 + 0.1:.1f}"
            buckets[bucket] += 1

        _info("Quality distribution:")
        for bucket in sorted(buckets.keys()):
            bar = "#" * min(buckets[bucket] // max(1, len(pairs) // 50), 40)
            log.info(f"         {bucket}: {buckets[bucket]:>5}  {bar}")

        if avg_q < MIN_QUALITY_MEAN:
            _fail(f"Average quality {avg_q:.3f} < {MIN_QUALITY_MEAN} threshold")
            errors.append(f"Low average quality: {avg_q:.3f}")
        else:
            _pass(f"Average quality: {avg_q:.3f} (threshold: {MIN_QUALITY_MEAN})")

        low_quality = sum(1 for q in qualities if q < 0.5)
        if low_quality > len(qualities) * 0.1:
            _warn(f"{low_quality} pairs ({low_quality/len(qualities)*100:.1f}%) below 0.5 quality")
            warnings.append(f"{low_quality} low-quality pairs")
    else:
        _warn("No quality scores found in data — cannot validate quality distribution")
        warnings.append("No quality metadata")

    # ── 1e. Token length estimation ─────────────────────────────────────
    # Rough estimate: 1 token ≈ 4 chars for English
    CHARS_PER_TOKEN = 3.5
    lengths = []
    truncated = 0
    for p in pairs:
        instruction = p.get("instruction", "")
        inp = p.get("input", "")
        output = p.get("output", "")
        # ChatML overhead: ~30 tokens for system + formatting
        total_chars = len(instruction) + len(inp) + len(output) + 200
        est_tokens = int(total_chars / CHARS_PER_TOKEN)
        lengths.append(est_tokens)
        if est_tokens > max_seq_length:
            truncated += 1

    stats["token_lengths"] = {
        "mean": int(statistics.mean(lengths)),
        "median": int(statistics.median(lengths)),
        "max": max(lengths),
        "p95": int(sorted(lengths)[int(len(lengths) * 0.95)]),
        "truncated_count": truncated,
        "truncated_pct": round(truncated / len(pairs) * 100, 1),
    }

    trunc_ratio = truncated / len(pairs)
    if trunc_ratio > MAX_TRUNCATION_RATIO:
        _fail(f"{truncated} pairs ({trunc_ratio*100:.1f}%) exceed {max_seq_length} tokens (est.)")
        errors.append(f"{truncated} pairs would be truncated")
    elif truncated > 0:
        _warn(f"{truncated} pairs ({trunc_ratio*100:.1f}%) may be truncated at {max_seq_length} tokens")
        warnings.append(f"{truncated} pairs near truncation limit")
    else:
        _pass(f"All pairs fit within {max_seq_length} token limit")

    _info(f"Token lengths: mean={stats['token_lengths']['mean']}, "
          f"median={stats['token_lengths']['median']}, "
          f"p95={stats['token_lengths']['p95']}, "
          f"max={stats['token_lengths']['max']}")

    # ── 1f. Code block coverage ─────────────────────────────────────────
    code_block_count = 0
    for p in pairs:
        output = p.get("output", "")
        if "```" in output:
            code_block_count += 1

    code_ratio = code_block_count / len(pairs) if pairs else 0
    stats["code_blocks"] = {
        "pairs_with_code": code_block_count,
        "ratio": round(code_ratio, 3),
    }

    if code_ratio < MIN_CODE_BLOCK_RATIO:
        _warn(f"Only {code_ratio*100:.1f}% of pairs contain code blocks (threshold: {MIN_CODE_BLOCK_RATIO*100}%)")
        warnings.append(f"Low code coverage: {code_ratio*100:.1f}%")
    else:
        _pass(f"{code_ratio*100:.1f}% of pairs contain code blocks")

    # ── 1g. Source diversity ────────────────────────────────────────────
    sources = Counter()
    for p in pairs:
        src = p.get("metadata", {}).get("source", p.get("source", "unknown"))
        sources[src] += 1

    stats["sources"] = dict(sources)
    if sources:
        top_source, top_count = sources.most_common(1)[0]
        top_ratio = top_count / len(pairs)
        _info(f"Source distribution: {dict(sources)}")
        if top_ratio > MAX_SINGLE_SOURCE_RATIO:
            _warn(f"Source '{top_source}' is {top_ratio*100:.1f}% of data — low diversity")
            warnings.append(f"Single source dominates: {top_source} ({top_ratio*100:.1f}%)")
        else:
            _pass(f"No single source exceeds {MAX_SINGLE_SOURCE_RATIO*100}% of data")

    # ── 1h. Domain coverage ─────────────────────────────────────────────
    hive_terms = {"hive", "vests", "hive power", "hbd", "resource credits", "dpos",
                  "custom_json", "dhive", "beem", "lighthive", "haf", "hivemind",
                  "condenser_api", "delegate_vesting_shares", "rc_api"}
    hive_count = 0
    for p in pairs:
        text = (p.get("instruction", "") + " " + p.get("output", "")).lower()
        if any(term in text for term in hive_terms):
            hive_count += 1

    hive_ratio = hive_count / len(pairs) if pairs else 0
    stats["domain"] = {
        "hive_pairs": hive_count,
        "general_pairs": len(pairs) - hive_count,
        "hive_ratio": round(hive_ratio, 3),
    }
    _info(f"Domain: {hive_count} Hive ({hive_ratio*100:.1f}%) / "
          f"{len(pairs) - hive_count} general ({(1-hive_ratio)*100:.1f}%)")

    # ── 1i. Near-duplicate detection (fast, instruction-only) ───────────
    _info("Running fast dedup check (exact instruction match)...")
    instruction_counts = Counter(p.get("instruction", "").strip() for p in pairs)
    exact_dupes = sum(c - 1 for c in instruction_counts.values() if c > 1)
    dupe_ratio = exact_dupes / len(pairs) if pairs else 0
    stats["duplicates"] = {
        "exact_instruction_dupes": exact_dupes,
        "dupe_ratio": round(dupe_ratio, 3),
    }

    if dupe_ratio > MAX_DUPLICATE_RATIO:
        _fail(f"{exact_dupes} exact instruction duplicates ({dupe_ratio*100:.1f}%)")
        errors.append(f"Too many duplicates: {exact_dupes}")
    elif exact_dupes > 0:
        _warn(f"{exact_dupes} exact instruction duplicates ({dupe_ratio*100:.1f}%)")
        warnings.append(f"{exact_dupes} exact duplicates")
    else:
        _pass("No exact instruction duplicates")

    # ── 1j. Difficulty distribution ─────────────────────────────────────
    difficulties = Counter()
    for p in pairs:
        diff = p.get("metadata", {}).get("difficulty", p.get("difficulty", "unknown"))
        difficulties[diff] += 1
    stats["difficulties"] = dict(difficulties)
    if difficulties and "unknown" not in difficulties:
        _info(f"Difficulty distribution: {dict(difficulties)}")
    elif "unknown" in difficulties and difficulties["unknown"] == len(pairs):
        _warn("No difficulty metadata — curriculum ordering won't work")
        warnings.append("No difficulty metadata")

    # ── 1k. Sample pairs for human review ───────────────────────────────
    _info("Random sample for eyeball review:")
    sample = random.sample(pairs, min(3, len(pairs)))
    for i, p in enumerate(sample, 1):
        instr = p.get("instruction", "")[:100]
        output = p.get("output", "")[:80]
        q = p.get("metadata", {}).get("quality", p.get("quality", "?"))
        log.info(f"         Sample {i}: Q={q} | {instr}...")
        log.info(f"                    → {output}...")

    # ── Summary ─────────────────────────────────────────────────────────
    passed = len(errors) == 0
    log.info(f"\n  Gate 1 {'PASSED' if passed else 'FAILED'}: "
             f"{len(errors)} errors, {len(warnings)} warnings")

    return {"passed": passed, "errors": errors, "warnings": warnings, "stats": stats}


# ════════════════════════════════════════════════════════════════════════════
# GATE 2: CONFIG SANITY
# ════════════════════════════════════════════════════════════════════════════

def gate_config_sanity(jsonl_path: str, model_path: str, config: dict = None) -> dict:
    """
    Validate training config against model architecture and inference setup.
    """
    log.info(f"\n{BOLD}{'='*60}")
    log.info(f"GATE 2: CONFIG SANITY")
    log.info(f"{'='*60}{RESET}")

    errors = []
    warnings = []

    if config is None:
        from hiveai.lora.trainer import LORA_CONFIG, TRAINING_CONFIG, MAX_SEQ_LENGTH
        config = {
            "lora": LORA_CONFIG,
            "training": TRAINING_CONFIG,
            "max_seq_length": MAX_SEQ_LENGTH,
        }

    lora_cfg = config.get("lora", {})
    train_cfg = config.get("training", {})
    max_seq = config.get("max_seq_length", 2048)

    # ── 2a. Model exists ────────────────────────────────────────────────
    if not os.path.exists(model_path):
        _fail(f"Model path not found: {model_path}")
        errors.append("Model path not found")
        return {"passed": False, "errors": errors, "warnings": warnings}

    # Check for config.json in model dir
    model_config_path = os.path.join(model_path, "config.json")
    model_config = {}
    if os.path.exists(model_config_path):
        with open(model_config_path, "r") as f:
            model_config = json.load(f)
        _pass(f"Model config found: {model_config.get('model_type', 'unknown')} architecture")
    else:
        _warn("No config.json in model directory — skipping architecture checks")
        warnings.append("No model config.json")

    # ── 2b. LoRA target modules exist in model ──────────────────────────
    target_modules = lora_cfg.get("target_modules", [])
    if model_config:
        # For Qwen-family models, check expected module names
        model_type = model_config.get("model_type", "")
        expected_modules = {"q_proj", "k_proj", "v_proj", "o_proj",
                           "gate_proj", "up_proj", "down_proj"}

        valid_targets = all(m in expected_modules for m in target_modules)
        if valid_targets:
            _pass(f"LoRA targets {target_modules} are valid for {model_type}")
        else:
            unknown = [m for m in target_modules if m not in expected_modules]
            _warn(f"Unknown LoRA targets: {unknown}")
            warnings.append(f"Unknown LoRA targets: {unknown}")

        # MoE check: warn if targeting MLP modules on MoE model
        num_experts = model_config.get("num_experts", model_config.get("num_local_experts", 0))
        mlp_targets = [m for m in target_modules if m in {"gate_proj", "up_proj", "down_proj"}]
        if num_experts > 1 and mlp_targets:
            _fail(f"MoE model with {num_experts} experts but LoRA targets include "
                  f"MLP modules {mlp_targets} — this creates {num_experts}x adapters!")
            errors.append(f"MLP LoRA on MoE model ({num_experts} experts)")
        elif num_experts > 1:
            _pass(f"MoE model ({num_experts} experts): correctly targeting attention-only")

    # ── 2c. EOS token alignment ─────────────────────────────────────────
    eos_id = model_config.get("eos_token_id")
    if isinstance(eos_id, list):
        _info(f"Model EOS token IDs: {eos_id}")
    elif eos_id:
        _info(f"Model EOS token ID: {eos_id}")

    # ── 2d. System prompt alignment ─────────────────────────────────────
    try:
        from hiveai.lora.trainer import CHATML_SYSTEM
        from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

        if CHATML_SYSTEM == CODING_SYSTEM_PROMPT:
            _pass("Training system prompt matches inference CODING_SYSTEM_PROMPT")
        elif "helpful" in CHATML_SYSTEM.lower() and "assistant" in CHATML_SYSTEM.lower():
            _fail("Training uses generic 'helpful assistant' prompt — mismatches inference!")
            errors.append("System prompt mismatch (generic vs CODING_SYSTEM_PROMPT)")
        else:
            _warn(f"Training system prompt: '{CHATML_SYSTEM[:60]}...'")
            _warn("Verify this matches what llama-server sends at inference")
            warnings.append("System prompt may not match inference")
    except ImportError:
        _warn("Could not import trainer/prompts — skipping system prompt check")
        warnings.append("System prompt check skipped (import error)")

    # ── 2e. VRAM budget estimate ────────────────────────────────────────
    try:
        import torch
        if torch.cuda.is_available():
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            _info(f"GPU: {torch.cuda.get_device_name(0)}, VRAM: {vram_gb:.1f}GB")

            # Rough VRAM estimate for 4-bit training
            num_params = model_config.get("num_parameters", 0)
            if not num_params:
                # Estimate from hidden_size and num_layers
                hidden = model_config.get("hidden_size", 2048)
                layers = model_config.get("num_hidden_layers", 40)
                num_params = hidden * hidden * 4 * layers  # very rough

            # 4-bit model: ~0.5 bytes/param, LoRA + optimizer: ~2-4GB overhead
            model_vram = num_params * 0.5 / (1024**3) if num_params else 0
            batch_size = train_cfg.get("per_device_train_batch_size", 2)
            # Activation memory: batch_size * seq_len * hidden_size * 2 bytes
            hidden = model_config.get("hidden_size", 2048)
            activation_vram = batch_size * max_seq * hidden * 2 / (1024**3)
            lora_overhead = 3.0  # LoRA params + optimizer states + gradients

            total_est = model_vram + activation_vram + lora_overhead
            if total_est > 0 and model_vram > 0:
                _info(f"VRAM estimate: model={model_vram:.1f}GB + "
                      f"activations={activation_vram:.1f}GB + overhead={lora_overhead:.1f}GB "
                      f"= {total_est:.1f}GB")

                if total_est > vram_gb * 0.95:
                    _fail(f"Estimated VRAM ({total_est:.1f}GB) exceeds GPU ({vram_gb:.1f}GB)")
                    errors.append(f"VRAM overflow: {total_est:.1f}GB > {vram_gb:.1f}GB")
                elif total_est > vram_gb * 0.85:
                    _warn(f"Tight VRAM fit: {total_est:.1f}GB / {vram_gb:.1f}GB (>{85}%)")
                    warnings.append("Tight VRAM fit")
                else:
                    _pass(f"VRAM budget OK: {total_est:.1f}GB / {vram_gb:.1f}GB")
        else:
            _fail("No CUDA GPU detected!")
            errors.append("No GPU")
    except ImportError:
        _warn("PyTorch not available — skipping VRAM check")
        warnings.append("VRAM check skipped")

    # ── 2f. Training config sanity ──────────────────────────────────────
    lr = train_cfg.get("learning_rate", 0)
    if lr > 1e-3:
        _fail(f"Learning rate {lr} is dangerously high for fine-tuning (>1e-3)")
        errors.append(f"LR too high: {lr}")
    elif lr > 5e-4:
        _warn(f"Learning rate {lr} is high — typical range: 1e-4 to 3e-4")
        warnings.append(f"High LR: {lr}")
    elif lr > 0:
        _pass(f"Learning rate: {lr}")

    epochs = train_cfg.get("num_train_epochs", 0)
    if epochs > 5:
        _warn(f"{epochs} epochs is high — risk of overfitting")
        warnings.append(f"High epoch count: {epochs}")
    elif epochs > 0:
        _pass(f"Epochs: {epochs}")

    batch = train_cfg.get("per_device_train_batch_size", 1)
    grad_acc = train_cfg.get("gradient_accumulation_steps", 1)
    effective_batch = batch * grad_acc
    _info(f"Effective batch size: {batch} x {grad_acc} = {effective_batch}")
    if effective_batch < 4:
        _warn(f"Effective batch size {effective_batch} is small — noisy gradients")
        warnings.append(f"Small effective batch: {effective_batch}")

    # ── 2g. Format alignment check ──────────────────────────────────────
    # Check if training data format matches ChatML
    with open(jsonl_path, "r", encoding="utf-8") as f:
        first_line = json.loads(f.readline().strip())

    has_text_field = "text" in first_line
    has_alpaca_fields = "instruction" in first_line and "output" in first_line

    if has_text_field:
        text = first_line["text"]
        if "<|im_start|>" in text:
            _pass("Training data is pre-formatted ChatML (matches inference)")
        elif "### Instruction:" in text:
            _fail("Training data uses Alpaca format but inference uses ChatML!")
            errors.append("Format mismatch: Alpaca training vs ChatML inference")
        else:
            _warn(f"Unknown pre-formatted text: '{text[:60]}...'")
            warnings.append("Unknown training format")
    elif has_alpaca_fields:
        _info("Training data is Alpaca JSONL — will be formatted by trainer's format_prompt()")
        _pass("Alpaca format compatible with ChatML conversion in format_prompt()")
    else:
        _fail(f"Unrecognized JSONL format. Keys: {list(first_line.keys())}")
        errors.append("Unrecognized data format")

    # ── 2h. Time estimate ───────────────────────────────────────────────
    # Count pairs
    pair_count = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pair_count += 1

    steps = (pair_count * epochs) // effective_batch if effective_batch > 0 else 0
    _info(f"Estimated steps: {pair_count} pairs x {epochs} epochs / {effective_batch} batch = {steps}")

    # Use v2's known timing if available (~7.5 min/step for Qwen3.5, ~21s for Qwen3-14B)
    num_experts = model_config.get("num_experts", model_config.get("num_local_experts", 0))
    if num_experts > 100:
        secs_per_step = 450  # ~7.5 min for large MoE
        _info(f"MoE model — estimated {secs_per_step/60:.1f} min/step (from v2 calibration)")
    else:
        secs_per_step = 21  # ~21s for dense 14B
        _info(f"Dense model — estimated {secs_per_step}s/step (from v1 calibration)")

    total_hours = (steps * secs_per_step) / 3600
    _info(f"Estimated total training time: {total_hours:.1f} hours ({steps} steps)")

    stats = {
        "steps": steps,
        "estimated_hours": round(total_hours, 1),
        "effective_batch_size": effective_batch,
    }

    # ── Summary ─────────────────────────────────────────────────────────
    passed = len(errors) == 0
    log.info(f"\n  Gate 2 {'PASSED' if passed else 'FAILED'}: "
             f"{len(errors)} errors, {len(warnings)} warnings")

    return {"passed": passed, "errors": errors, "warnings": warnings, "stats": stats}


# ════════════════════════════════════════════════════════════════════════════
# GATE 3: MICRO-TRAIN (10-step smoke test)
# ════════════════════════════════════════════════════════════════════════════

def gate_micro_train(jsonl_path: str, model_path: str, steps: int = MICRO_TRAIN_STEPS) -> dict:
    """
    Run a 10-step training smoke test. Checks:
    - Loss decreases
    - Gradient norms are stable
    - Token accuracy improves
    """
    log.info(f"\n{BOLD}{'='*60}")
    log.info(f"GATE 3: MICRO-TRAIN ({steps}-step smoke test)")
    log.info(f"{'='*60}{RESET}")

    errors = []
    warnings = []
    metrics = {"losses": [], "grad_norms": [], "accuracies": []}

    try:
        import torch
        from datasets import load_dataset
        from transformers import AutoTokenizer

        if not torch.cuda.is_available():
            _fail("No CUDA GPU — cannot run micro-train")
            return {"passed": False, "errors": ["No GPU"], "warnings": [], "metrics": {}}

        _info(f"Loading tokenizer from {model_path}...")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

        _info(f"Loading dataset from {jsonl_path}...")
        dataset = load_dataset("json", data_files=jsonl_path, split="train")

        # Subsample for speed: use first 50 pairs
        if len(dataset) > 50:
            dataset = dataset.select(range(50))
            _info(f"Using first 50 pairs for smoke test")

        # Import trainer's format_prompt to use same formatting
        from hiveai.lora.trainer import CHATML_SYSTEM, EOS_TOKEN

        def format_for_smoke(examples):
            texts = []
            for instruction, inp, output in zip(
                examples["instruction"], examples["input"], examples["output"]
            ):
                user_content = instruction
                if inp:
                    user_content += "\n" + inp
                messages = [
                    {"role": "system", "content": CHATML_SYSTEM},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": output},
                ]
                try:
                    text = tokenizer.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=False
                    )
                except Exception:
                    text = (
                        f"<|im_start|>system\n{CHATML_SYSTEM}<|im_end|>\n"
                        f"<|im_start|>user\n{user_content}<|im_end|>\n"
                        f"<|im_start|>assistant\n{output}<|im_end|>"
                    )
                texts.append(text)
            return {"text": texts}

        _info("Formatting dataset...")
        # Ensure 'input' field exists
        if "input" not in dataset.column_names:
            dataset = dataset.map(lambda x: {"input": ""})
        dataset = dataset.map(format_for_smoke, batched=True, remove_columns=dataset.column_names)

        _info(f"Loading model (4-bit) from {model_path}...")
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        from transformers import AutoModelForCausalLM
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        _info("Applying LoRA...")
        from peft import get_peft_model, LoraConfig
        from hiveai.lora.trainer import LORA_CONFIG

        peft_config = LoraConfig(**LORA_CONFIG)
        model = get_peft_model(model, peft_config)

        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        _info(f"Trainable: {trainable:,} / {total:,} ({trainable/total*100:.2f}%)")

        _info(f"Running {steps}-step smoke test...")
        from trl import SFTConfig, SFTTrainer

        smoke_config = SFTConfig(
            output_dir=os.path.join(PROJECT_ROOT, "loras", "_smoke_test"),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
            max_steps=steps,
            learning_rate=2e-4,
            bf16=True,
            logging_steps=1,
            save_strategy="no",
            report_to="none",
            max_seq_length=1024,  # Short for speed
            dataset_text_field="text",
        )

        # Custom callback to capture metrics
        from transformers import TrainerCallback

        class MetricsCapture(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs:
                    if "loss" in logs:
                        metrics["losses"].append(float(logs["loss"]))
                    if "grad_norm" in logs:
                        metrics["grad_norms"].append(float(logs["grad_norm"]))
                    if "mean_token_accuracy" in logs:
                        metrics["accuracies"].append(float(logs["mean_token_accuracy"]))

        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset,
            processing_class=tokenizer,
            args=smoke_config,
            callbacks=[MetricsCapture()],
        )

        train_result = trainer.train()
        _pass(f"Smoke test completed: {steps} steps")

        # ── Analyze metrics ─────────────────────────────────────────────
        losses = metrics["losses"]
        grads = metrics["grad_norms"]
        accs = metrics["accuracies"]

        if len(losses) >= 2:
            first_loss = losses[0]
            last_loss = losses[-1]
            loss_change = (first_loss - last_loss) / first_loss if first_loss > 0 else 0

            _info(f"Loss: {first_loss:.4f} → {last_loss:.4f} (change: {loss_change*100:+.1f}%)")

            if loss_change < -0.20:
                _fail(f"Loss INCREASED by {abs(loss_change)*100:.1f}% — something is wrong")
                errors.append(f"Loss increased: {first_loss:.4f} → {last_loss:.4f}")
            elif loss_change < LOSS_DECREASE_THRESHOLD:
                _warn(f"Loss barely decreased ({loss_change*100:.1f}%) — may be stuck")
                warnings.append("Loss not decreasing strongly")
            else:
                _pass(f"Loss decreasing: {loss_change*100:.1f}% over {steps} steps")

        if grads:
            max_grad = max(grads)
            min_grad = min(grads)
            avg_grad = statistics.mean(grads)
            _info(f"Grad norms: min={min_grad:.4f}, avg={avg_grad:.4f}, max={max_grad:.4f}")

            if max_grad > GRAD_NORM_MAX:
                _fail(f"Gradient explosion detected: max norm = {max_grad:.4f}")
                errors.append(f"Gradient explosion: {max_grad:.4f}")
            elif min_grad < GRAD_NORM_MIN:
                _fail(f"Gradient vanishing detected: min norm = {min_grad:.6f}")
                errors.append(f"Gradient vanishing: {min_grad:.6f}")
            else:
                _pass(f"Gradient norms stable (range: {min_grad:.4f} - {max_grad:.4f})")

        if len(accs) >= 2:
            first_acc = accs[0]
            last_acc = accs[-1]
            acc_change = last_acc - first_acc
            _info(f"Token accuracy: {first_acc:.4f} → {last_acc:.4f} (change: {acc_change:+.4f})")

            if acc_change < -0.05:
                _fail(f"Token accuracy DECREASED — model is getting worse")
                errors.append(f"Accuracy decreased: {first_acc:.4f} → {last_acc:.4f}")
            elif acc_change < ACCURACY_IMPROVEMENT_MIN:
                _warn(f"Token accuracy barely improved ({acc_change:+.4f})")
                warnings.append("Accuracy stagnant")
            else:
                _pass(f"Token accuracy improving: {acc_change:+.4f}")

        # Cleanup smoke test artifacts
        smoke_dir = os.path.join(PROJECT_ROOT, "loras", "_smoke_test")
        if os.path.exists(smoke_dir):
            import shutil
            shutil.rmtree(smoke_dir, ignore_errors=True)
            _info("Cleaned up smoke test artifacts")

        # Free GPU memory
        del model, trainer
        torch.cuda.empty_cache()
        _info("GPU memory freed")

    except Exception as e:
        _fail(f"Micro-train crashed: {e}")
        errors.append(f"Smoke test crash: {e}")
        import traceback
        log.error(traceback.format_exc())

    passed = len(errors) == 0
    log.info(f"\n  Gate 3 {'PASSED' if passed else 'FAILED'}: "
             f"{len(errors)} errors, {len(warnings)} warnings")

    return {"passed": passed, "errors": errors, "warnings": warnings, "metrics": metrics}


# ════════════════════════════════════════════════════════════════════════════
# GATE 4: IN-FLIGHT MONITOR (attach to running training)
# ════════════════════════════════════════════════════════════════════════════

def gate_inflight_monitor(log_path: str, check_interval: int = 60,
                          patience: int = 30, min_checkpoint_eval: float = 0.0) -> dict:
    """
    Monitor a running training log for anomalies. Runs continuously.

    Checks:
    - Loss trend (plateau detection)
    - Gradient norm stability
    - Token accuracy progression
    - Checkpoint quality (if eval scores appear in log)

    Args:
        log_path: Path to the training log file
        check_interval: Seconds between checks
        patience: Number of steps with no improvement before alerting
        min_checkpoint_eval: Minimum acceptable checkpoint eval score (0 = disabled)
    """
    log.info(f"\n{BOLD}{'='*60}")
    log.info(f"GATE 4: IN-FLIGHT MONITOR")
    log.info(f"{'='*60}{RESET}")
    log.info(f"Monitoring: {log_path}")
    log.info(f"Check interval: {check_interval}s, Patience: {patience} steps")
    log.info(f"Press Ctrl+C to stop monitoring\n")

    if not os.path.exists(log_path):
        _fail(f"Log file not found: {log_path}")
        return {"passed": False, "errors": ["Log not found"]}

    # Regex patterns for metric extraction
    step_pattern = re.compile(r"Step\s+(\d+)/(\d+)\s*\|\s*loss=([\d.]+)")
    loss_pattern = re.compile(r"'loss':\s*'([\d.]+)'")
    grad_pattern = re.compile(r"'grad_norm':\s*'([\d.]+)'")
    acc_pattern = re.compile(r"'mean_token_accuracy':\s*'([\d.]+)'")

    all_losses = []
    all_grads = []
    all_accs = []
    best_loss = float("inf")
    steps_without_improvement = 0
    last_line_count = 0
    alerts = []

    try:
        while True:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            new_lines = lines[last_line_count:]
            last_line_count = len(lines)

            for line in new_lines:
                # Extract step-level metrics
                step_match = step_pattern.search(line)
                loss_match = loss_pattern.search(line)
                grad_match = grad_pattern.search(line)
                acc_match = acc_pattern.search(line)

                if loss_match:
                    loss = float(loss_match.group(1))
                    all_losses.append(loss)

                    if loss < best_loss - 0.01:
                        best_loss = loss
                        steps_without_improvement = 0
                    else:
                        steps_without_improvement += 1

                if grad_match:
                    grad = float(grad_match.group(1))
                    all_grads.append(grad)

                    if grad > GRAD_NORM_MAX:
                        alert = f"GRADIENT EXPLOSION at step ~{len(all_grads)}: norm={grad:.4f}"
                        _fail(alert)
                        alerts.append(alert)

                if acc_match:
                    acc = float(acc_match.group(1))
                    all_accs.append(acc)

            # Periodic status report
            if all_losses:
                recent_loss = statistics.mean(all_losses[-5:]) if len(all_losses) >= 5 else all_losses[-1]
                recent_acc = statistics.mean(all_accs[-5:]) if len(all_accs) >= 5 else (all_accs[-1] if all_accs else 0)
                recent_grad = statistics.mean(all_grads[-5:]) if len(all_grads) >= 5 else (all_grads[-1] if all_grads else 0)

                status = (f"  Steps: {len(all_losses)} | "
                         f"Loss: {recent_loss:.4f} (best: {best_loss:.4f}) | "
                         f"Acc: {recent_acc:.4f} | "
                         f"Grad: {recent_grad:.4f} | "
                         f"Plateau: {steps_without_improvement}/{patience}")
                log.info(status)

                # Plateau detection
                if steps_without_improvement >= patience:
                    alert = (f"PLATEAU DETECTED: Loss hasn't improved for "
                            f"{steps_without_improvement} steps (best: {best_loss:.4f})")
                    _warn(alert)
                    alerts.append(alert)
                    _info("Consider early stopping — the model may have learned all it can from this data")

                # Accuracy regression
                if len(all_accs) >= 20:
                    early_acc = statistics.mean(all_accs[:10])
                    recent_acc_avg = statistics.mean(all_accs[-10:])
                    if recent_acc_avg < early_acc - 0.02:
                        alert = (f"ACCURACY REGRESSION: early avg={early_acc:.4f} → "
                                f"recent avg={recent_acc_avg:.4f}")
                        _warn(alert)
                        alerts.append(alert)

                # Gradient instability
                if len(all_grads) >= 10:
                    grad_std = statistics.stdev(all_grads[-10:])
                    grad_mean = statistics.mean(all_grads[-10:])
                    if grad_std > grad_mean * 0.5:
                        _warn(f"Gradient instability: std/mean = {grad_std/grad_mean:.2f}")

            time.sleep(check_interval)

    except KeyboardInterrupt:
        log.info("\n\nMonitoring stopped by user.")

    # Final summary
    summary = {
        "total_steps_monitored": len(all_losses),
        "final_loss": all_losses[-1] if all_losses else None,
        "best_loss": best_loss if best_loss < float("inf") else None,
        "final_accuracy": all_accs[-1] if all_accs else None,
        "alerts": alerts,
    }

    if all_losses:
        _info(f"\nFinal summary:")
        _info(f"  Steps monitored: {len(all_losses)}")
        _info(f"  Loss: {all_losses[0]:.4f} → {all_losses[-1]:.4f} (best: {best_loss:.4f})")
        if all_accs:
            _info(f"  Accuracy: {all_accs[0]:.4f} → {all_accs[-1]:.4f}")
        _info(f"  Alerts: {len(alerts)}")

    return {"passed": len(alerts) == 0, "alerts": alerts, "summary": summary}


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def print_usage():
    print(f"""
{BOLD}HiveAI Training Preflight System{RESET}

Usage:
  python scripts/preflight.py audit  <jsonl_path>                    Gate 1: Data audit
  python scripts/preflight.py config <jsonl_path> <model_path>       Gate 2: Config check
  python scripts/preflight.py smoke  <jsonl_path> <model_path>       Gate 3: 10-step test
  python scripts/preflight.py full   <jsonl_path> <model_path>       Gates 1+2+3
  python scripts/preflight.py monitor <log_path> [--patience N]      Gate 4: Live monitor

Examples:
  python scripts/preflight.py full loras/training_data/v1_6.jsonl models/qwen3.5-35b-a3b/hf
  python scripts/preflight.py audit loras/training_data/v1_6.jsonl
  python scripts/preflight.py monitor logs/train_v2_full.log --patience 40
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "audit":
        if len(sys.argv) < 3:
            print("Usage: python scripts/preflight.py audit <jsonl_path>")
            sys.exit(1)
        result = gate_data_audit(sys.argv[2])
        sys.exit(0 if result["passed"] else 1)

    elif command == "config":
        if len(sys.argv) < 4:
            print("Usage: python scripts/preflight.py config <jsonl_path> <model_path>")
            sys.exit(1)
        result = gate_config_sanity(sys.argv[2], sys.argv[3])
        sys.exit(0 if result["passed"] else 1)

    elif command == "smoke":
        if len(sys.argv) < 4:
            print("Usage: python scripts/preflight.py smoke <jsonl_path> <model_path>")
            sys.exit(1)
        result = gate_micro_train(sys.argv[2], sys.argv[3])
        sys.exit(0 if result["passed"] else 1)

    elif command == "full":
        if len(sys.argv) < 4:
            print("Usage: python scripts/preflight.py full <jsonl_path> <model_path>")
            sys.exit(1)

        jsonl_path = sys.argv[2]
        model_path = sys.argv[3]
        all_passed = True
        all_warnings = []

        log.info(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗")
        log.info(f"║  HiveAI TRAINING PREFLIGHT — FULL CHECK                  ║")
        log.info(f"╚══════════════════════════════════════════════════════════╝{RESET}\n")

        # Gate 1
        r1 = gate_data_audit(jsonl_path)
        all_passed = all_passed and r1["passed"]
        all_warnings.extend(r1.get("warnings", []))

        if not r1["passed"]:
            log.info(f"\n{RED}Gate 1 FAILED — stopping preflight. Fix data issues first.{RESET}")
            sys.exit(1)

        # Gate 2
        r2 = gate_config_sanity(jsonl_path, model_path)
        all_passed = all_passed and r2["passed"]
        all_warnings.extend(r2.get("warnings", []))

        if not r2["passed"]:
            log.info(f"\n{RED}Gate 2 FAILED — stopping preflight. Fix config issues first.{RESET}")
            sys.exit(1)

        # Gate 3
        log.info(f"\n{YELLOW}Gate 3 requires loading the model onto GPU. "
                 f"Ensure no other model is loaded.{RESET}")
        r3 = gate_micro_train(jsonl_path, model_path)
        all_passed = all_passed and r3["passed"]
        all_warnings.extend(r3.get("warnings", []))

        # Final verdict
        log.info(f"\n{BOLD}{'='*60}")
        log.info(f"PREFLIGHT VERDICT")
        log.info(f"{'='*60}{RESET}")

        if all_passed and not all_warnings:
            log.info(f"\n  {GREEN}{BOLD}ALL GATES PASSED — CLEAR FOR TRAINING{RESET}")
            sys.exit(0)
        elif all_passed:
            log.info(f"\n  {YELLOW}{BOLD}ALL GATES PASSED WITH WARNINGS:{RESET}")
            for w in all_warnings:
                _warn(w)
            log.info(f"\n  Proceed with caution.")
            sys.exit(2)
        else:
            log.info(f"\n  {RED}{BOLD}PREFLIGHT FAILED — DO NOT TRAIN{RESET}")
            sys.exit(1)

    elif command == "monitor":
        if len(sys.argv) < 3:
            print("Usage: python scripts/preflight.py monitor <log_path> [--patience N]")
            sys.exit(1)
        log_path = sys.argv[2]
        patience = 30
        for i, arg in enumerate(sys.argv):
            if arg == "--patience" and i + 1 < len(sys.argv):
                patience = int(sys.argv[i + 1])
        gate_inflight_monitor(log_path, patience=patience)

    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
