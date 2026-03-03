"""
hiveai/lora/merge_cycle.py

LoRA Merge Cycling — Train LoRA → merge into base → save new base → repeat.

Each cycle bakes adapter specialization into the core weights, so subsequent
LoRAs learn on an already-improved foundation.  The previous base is never
deleted, enabling rollback if a cycle regresses.

Usage:
    from hiveai.lora.merge_cycle import run_merge_cycle, load_merge_history

    result = run_merge_cycle(
        adapter_dir="loras/v5",
        base_model_dir="models/qwen3.5-9b",
        output_base_dir="models/qwen3.5-9b-cycle1",
    )

Also provides reusable merge / GGUF / Ollama helpers consumed by deploy_v5.py.
"""
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MERGE_HISTORY_FILE = os.path.join(PROJECT_ROOT, "loras", "merge_history.json")
OLLAMA_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class MergeCycleResult:
    success: bool
    cycle_number: int
    input_base: str
    output_base: str
    adapter_dir: str
    eval_score_before: Optional[float] = None
    eval_score_after: Optional[float] = None
    merge_time_s: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Merge history
# ---------------------------------------------------------------------------
def load_merge_history() -> list[dict]:
    if os.path.exists(MERGE_HISTORY_FILE):
        with open(MERGE_HISTORY_FILE) as f:
            return json.load(f)
    return []


def save_merge_history(history: list[dict]):
    os.makedirs(os.path.dirname(MERGE_HISTORY_FILE), exist_ok=True)
    with open(MERGE_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    logger.info(f"Merge history saved ({len(history)} cycles)")


def get_next_cycle_number() -> int:
    history = load_merge_history()
    if not history:
        return 1
    return max(h.get("cycle", 0) for h in history) + 1


def get_current_base() -> Optional[str]:
    """Return the most recent merged base path, or None if no cycles yet."""
    history = load_merge_history()
    if not history:
        return None
    return history[-1].get("base_out")


# ---------------------------------------------------------------------------
# Adapter verification
# ---------------------------------------------------------------------------
def verify_adapter_files(adapter_dir: str) -> bool:
    """Check that required adapter files exist."""
    required = ["adapter_config.json", "adapter_model.safetensors"]
    missing = [f for f in required if not os.path.exists(os.path.join(adapter_dir, f))]
    if missing:
        logger.error(f"Missing adapter files in {adapter_dir}: {missing}")
        return False
    for f in required:
        path = os.path.join(adapter_dir, f)
        size_mb = os.path.getsize(path) / 1024 / 1024
        logger.info(f"  {f}: {size_mb:.1f} MB")
    return True


# ---------------------------------------------------------------------------
# Model merge (CPU subprocess)
# ---------------------------------------------------------------------------
def merge_model(
    base_model_dir: str,
    adapter_dir: str,
    output_dir: str,
    timeout: int = 1800,
) -> bool:
    """
    Merge a LoRA adapter into base model weights using PEFT.

    Runs in a subprocess with CUDA disabled to avoid GPU contention.
    Requires ~20-40GB RAM depending on model size.
    """
    if os.path.exists(os.path.join(output_dir, "config.json")):
        logger.info(f"Merged model already exists at {output_dir} — skipping merge")
        return True

    logger.info("Merging LoRA adapter into base model weights...")
    logger.info(f"  Base:    {base_model_dir}")
    logger.info(f"  Adapter: {adapter_dir}")
    logger.info(f"  Output:  {output_dir}")

    merge_script = f"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os, sys, time

base_path = {repr(base_model_dir)}
adapter_path = {repr(adapter_dir)}
output_path = {repr(output_dir)}

print("Loading base model (bf16, CPU)...")
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(
    base_path,
    torch_dtype=torch.bfloat16,
    device_map="cpu",
    trust_remote_code=True,
)
print(f"  Base loaded in {{time.time()-t0:.0f}}s")

print("Loading LoRA adapter...")
model = PeftModel.from_pretrained(model, adapter_path)
print("  Adapter loaded")

print("Merging and unloading...")
model = model.merge_and_unload()
print("  Merged")

os.makedirs(output_path, exist_ok=True)
print(f"Saving merged model to {{output_path}}...")
model.save_pretrained(output_path, safe_serialization=True)

print("Saving tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(base_path, trust_remote_code=True)
tokenizer.save_pretrained(output_path)
print("MERGE COMPLETE")
"""
    merge_py = os.path.join(adapter_dir, "_merge_tmp.py")
    with open(merge_py, "w") as f:
        f.write(merge_script)

    logger.info("Running merge subprocess (CPU only)...")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, merge_py],
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
    )

    try:
        os.remove(merge_py)
    except OSError:
        pass

    if result.returncode != 0:
        logger.error(f"Merge failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[-2000:])
        if result.stdout:
            logger.info(result.stdout[-1000:])
        return False

    elapsed = time.time() - t0
    if "MERGE COMPLETE" in result.stdout:
        logger.info(f"Merge complete in {elapsed:.0f}s")
        return True

    logger.error("Merge subprocess finished but no completion marker found")
    logger.info(result.stdout[-500:])
    return False


def verify_merged_model(merged_dir: str) -> bool:
    """Verify a merged model directory has required files."""
    if not os.path.exists(os.path.join(merged_dir, "config.json")):
        logger.error(f"No config.json in {merged_dir}")
        return False

    # Check for safetensors files
    safetensors = [f for f in os.listdir(merged_dir) if f.endswith(".safetensors")]
    if not safetensors:
        logger.error(f"No .safetensors files in {merged_dir}")
        return False

    total_size = sum(os.path.getsize(os.path.join(merged_dir, f)) for f in safetensors)
    logger.info(f"Merged model verified: {len(safetensors)} shards, {total_size / 1e9:.1f} GB")
    return True


# ---------------------------------------------------------------------------
# GGUF export
# ---------------------------------------------------------------------------
def export_gguf(
    merged_dir: str,
    gguf_path: str,
    quant: str = "Q8_0",
    timeout: int = 1800,
) -> bool:
    """Export a merged HF model to GGUF format."""
    if os.path.exists(gguf_path):
        size_gb = os.path.getsize(gguf_path) / 1024**3
        logger.info(f"GGUF already exists: {gguf_path} ({size_gb:.1f} GB) — skipping")
        return True

    convert_script = None
    for candidate in [
        r"C:\Users\theyc\llama.cpp\convert_hf_to_gguf.py",
        os.path.expanduser("~/llama.cpp/convert_hf_to_gguf.py"),
        "/opt/llama.cpp/convert_hf_to_gguf.py",
    ]:
        if os.path.exists(candidate):
            convert_script = candidate
            break

    if not convert_script:
        logger.warning("convert_hf_to_gguf.py not found")
        logger.warning(f"Manual: python convert_hf_to_gguf.py {merged_dir} --outfile {gguf_path} --outtype {quant.lower()}")
        return False

    os.makedirs(os.path.dirname(gguf_path), exist_ok=True)
    logger.info(f"Converting merged model to GGUF ({quant})...")
    cmd = [sys.executable, convert_script, merged_dir, "--outfile", gguf_path, "--outtype", quant.lower()]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        logger.error(f"GGUF export failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[-2000:])
        return False

    if os.path.exists(gguf_path):
        size_gb = os.path.getsize(gguf_path) / 1024**3
        logger.info(f"GGUF created: {gguf_path} ({size_gb:.1f} GB)")
        return True

    # Check for file with different name
    parent = os.path.dirname(gguf_path)
    if os.path.isdir(parent):
        for f in os.listdir(parent):
            if f.endswith(".gguf") and os.path.join(parent, f) != gguf_path:
                src = os.path.join(parent, f)
                os.rename(src, gguf_path)
                size_gb = os.path.getsize(gguf_path) / 1024**3
                logger.info(f"GGUF created (renamed): {gguf_path} ({size_gb:.1f} GB)")
                return True

    logger.error("GGUF conversion finished but no .gguf file found")
    return False


# ---------------------------------------------------------------------------
# Ollama model creation
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are HiveAI, an expert coding assistant specialized in Python, JavaScript, "
    "blockchain development (especially Hive), and software engineering best practices. "
    "Write clean, correct, well-documented code. Include practical examples with "
    "complete, runnable code. Explain your reasoning and trade-offs."
)


def create_ollama_model(
    gguf_path: str,
    model_name: str,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    timeout: int = 600,
) -> bool:
    """Create an Ollama model from a GGUF file with ChatML template."""
    modelfile_content = f"""FROM {gguf_path}

SYSTEM \"\"\"{system_prompt}\"\"\"

TEMPLATE \"\"\"{{{{- if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{- end }}}}
<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
<|im_start|>assistant
{{{{ .Response }}}}<|im_end|>\"\"\"

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 16384
"""
    modelfile_path = os.path.join(os.path.dirname(gguf_path), f"Modelfile.{model_name}")
    os.makedirs(os.path.dirname(modelfile_path), exist_ok=True)
    with open(modelfile_path, "w") as f:
        f.write(modelfile_content)
    logger.info(f"Modelfile written: {modelfile_path}")

    logger.info(f"Creating Ollama model '{model_name}'...")
    result = subprocess.run(
        ["ollama", "create", model_name, "-f", modelfile_path],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        logger.error(f"ollama create failed (exit {result.returncode})")
        if result.stderr:
            logger.error(result.stderr[:1000])
        return False

    logger.info(f"Ollama model '{model_name}' created successfully!")

    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if model_name in result.stdout:
        logger.info(f"  Verified: {model_name} in ollama list")
        return True

    logger.warning(f"  {model_name} not found in ollama list after creation")
    return False


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------
def run_eval(model_name: str, timeout: int = 7200) -> Optional[float]:
    """Run eval harness and return the overall score, or None on failure."""
    eval_script = os.path.join(PROJECT_ROOT, "scripts", "run_eval.py")
    if not os.path.exists(eval_script):
        logger.warning("run_eval.py not found — skipping eval")
        return None

    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"eval_{model_name}.log")

    logger.info(f"Running eval for {model_name}...")
    cmd = [sys.executable, eval_script, "--model", model_name]
    with open(log_path, "w") as log_f:
        result = subprocess.run(cmd, stdout=log_f, stderr=log_f, timeout=timeout)

    if result.returncode != 0:
        logger.warning(f"Eval exited with code {result.returncode}")
        return None

    with open(log_path) as f:
        eval_out = f.read()
    score_match = re.search(r"Overall.*?(0\.\d+)", eval_out)
    if score_match:
        score = float(score_match.group(1))
        logger.info(f"Eval score for {model_name}: {score:.3f}")
        return score

    logger.warning("Could not parse eval score from output")
    return None


# ---------------------------------------------------------------------------
# Main: run_merge_cycle
# ---------------------------------------------------------------------------
def run_merge_cycle(
    adapter_dir: str,
    base_model_dir: str,
    output_base_dir: str,
    min_eval_score: float = 0.0,
    eval_model_name: Optional[str] = None,
    deploy_to_ollama: bool = False,
    ollama_model_name: Optional[str] = None,
    gguf_quant: str = "Q8_0",
    dry_run: bool = False,
) -> MergeCycleResult:
    """
    Execute one merge cycle: verify → eval gate → merge → verify → record.

    Args:
        adapter_dir: Path to LoRA adapter directory (e.g., "loras/v5")
        base_model_dir: Path to current base model weights
        output_base_dir: Where to save the merged model
        min_eval_score: Minimum eval score to proceed with merge (0 = skip gate)
        eval_model_name: Ollama model name for pre-merge eval
        deploy_to_ollama: Also export GGUF and register in Ollama
        ollama_model_name: Name for the Ollama model
        gguf_quant: GGUF quantization type
        dry_run: Show what would happen without doing it

    Returns:
        MergeCycleResult with success status and metadata
    """
    cycle_num = get_next_cycle_number()
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting merge cycle {cycle_num}")
    logger.info(f"  Base:    {base_model_dir}")
    logger.info(f"  Adapter: {adapter_dir}")
    logger.info(f"  Output:  {output_base_dir}")

    result = MergeCycleResult(
        success=False,
        cycle_number=cycle_num,
        input_base=base_model_dir,
        output_base=output_base_dir,
        adapter_dir=adapter_dir,
    )

    # 1. Verify adapter
    if not verify_adapter_files(adapter_dir):
        result.error = "Adapter verification failed"
        return result

    # 2. Eval gate (optional)
    if min_eval_score > 0 and eval_model_name:
        logger.info(f"Running eval gate (min score: {min_eval_score})...")
        if dry_run:
            logger.info(f"  [DRY RUN] Would eval {eval_model_name}")
        else:
            score = run_eval(eval_model_name)
            result.eval_score_before = score
            if score is not None and score < min_eval_score:
                result.error = f"Eval score {score:.3f} below minimum {min_eval_score}"
                logger.warning(result.error)
                return result

    # 3. Merge
    if dry_run:
        logger.info(f"  [DRY RUN] Would merge {adapter_dir} into {base_model_dir}")
        logger.info(f"  [DRY RUN] Output: {output_base_dir}")
        result.success = True
        return result

    t0 = time.time()
    merge_ok = merge_model(base_model_dir, adapter_dir, output_base_dir)
    result.merge_time_s = time.time() - t0

    if not merge_ok:
        result.error = "Merge failed"
        return result

    # 4. Verify merged model
    if not verify_merged_model(output_base_dir):
        result.error = "Merged model verification failed"
        return result

    # 5. Optional: deploy to Ollama
    if deploy_to_ollama and ollama_model_name:
        gguf_path = os.path.join(output_base_dir, f"{ollama_model_name}.gguf")
        if export_gguf(output_base_dir, gguf_path, quant=gguf_quant):
            create_ollama_model(gguf_path, ollama_model_name)

            # Post-deploy eval
            post_score = run_eval(ollama_model_name)
            result.eval_score_after = post_score

    # 6. Record cycle
    history = load_merge_history()
    history.append({
        "cycle": cycle_num,
        "base_in": base_model_dir,
        "base_out": output_base_dir,
        "adapter": adapter_dir,
        "eval_before": result.eval_score_before,
        "eval_after": result.eval_score_after,
        "merge_time_s": result.merge_time_s,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    save_merge_history(history)

    result.success = True
    logger.info(f"Merge cycle {cycle_num} complete in {result.merge_time_s:.0f}s")
    return result
