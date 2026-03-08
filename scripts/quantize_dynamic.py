#!/usr/bin/env python3
"""
Dynamic 4-bit quantization with importance matrix (imatrix).

Wraps llama.cpp's llama-imatrix and llama-quantize tools to produce
imatrix-guided GGUF quants. Optionally benchmarks the result via run_eval.py.

Prerequisites:
    - llama.cpp built at /tmp/llama.cpp/ (with llama-imatrix, llama-quantize)
    - Model in GGUF format (or convert first via llama.cpp's convert scripts)
    - Calibration JSONL with instruction/output pairs (training data works well)

Usage:
    # Full pipeline: imatrix + quantize
    python scripts/quantize_dynamic.py --model model-f16.gguf --calibration data.jsonl

    # Generate imatrix only
    python scripts/quantize_dynamic.py --model model-f16.gguf --calibration data.jsonl --imatrix-only

    # Quantize with existing imatrix
    python scripts/quantize_dynamic.py --model model-f16.gguf --imatrix model.imatrix.dat

    # Quantize + benchmark
    python scripts/quantize_dynamic.py --model model-f16.gguf --calibration data.jsonl --benchmark

Note: scripts/quantize_imatrix.py has similar functionality with Windows support and
      auto-calibration from training data. This script is Linux-targeted and adds
      JSONL calibration input, --imatrix-only, and --benchmark integration.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LLAMA_CPP = Path("/tmp/llama.cpp")
LLAMA_IMATRIX = LLAMA_CPP / "llama-imatrix"
LLAMA_QUANTIZE = LLAMA_CPP / "llama-quantize"

QUANT_TYPES = [
    "Q2_K", "Q3_K_S", "Q3_K_M", "Q4_0", "Q4_K_S", "Q4_K_M",
    "Q5_K_S", "Q5_K_M", "Q6_K", "Q8_0",
]


def jsonl_to_calibration_text(jsonl_path: Path, max_samples: int = 500) -> str:
    """Convert JSONL training pairs to plain text for imatrix calibration.

    Extracts instruction + output fields and concatenates them as plain text
    blocks separated by double newlines. llama-imatrix needs raw text, not JSON.
    """
    samples = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text_parts = []
            if row.get("instruction"):
                text_parts.append(row["instruction"])
            if row.get("input"):
                text_parts.append(row["input"])
            if row.get("output"):
                text_parts.append(row["output"])
            combined = "\n".join(text_parts)
            if len(combined) > 50:
                samples.append(combined)
            if len(samples) >= max_samples:
                break

    if not samples:
        log.error(f"No usable samples found in {jsonl_path}")
        sys.exit(1)

    log.info(f"Extracted {len(samples)} calibration samples from {jsonl_path}")
    return "\n\n".join(samples)


def generate_imatrix(model: str, calibration_text: str, output: str,
                     ctx_size: int = 512, ngl: int = 99) -> str:
    """Step 1: Generate importance matrix from calibration data."""
    if not LLAMA_IMATRIX.exists():
        log.error(f"llama-imatrix not found at {LLAMA_IMATRIX}")
        log.error("Build: cd /tmp/llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build")
        sys.exit(1)

    # Write calibration text to temp file
    cal_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                           encoding="utf-8")
    try:
        cal_file.write(calibration_text)
        cal_file.close()

        cmd = [
            str(LLAMA_IMATRIX),
            "-m", model,
            "-f", cal_file.name,
            "-o", output,
            "-c", str(ctx_size),
            "-ngl", str(ngl),
            "--chunks", "100",
        ]
        log.info(f"Generating importance matrix...")
        log.info(f"  Model: {model}")
        log.info(f"  Output: {output}")
        log.info(f"  Command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            log.error(f"llama-imatrix failed (rc={result.returncode}):\n{result.stderr[-2000:]}")
            sys.exit(1)

        log.info(f"Importance matrix saved: {output} ({os.path.getsize(output) / 1024:.0f} KB)")
    finally:
        os.unlink(cal_file.name)

    return output


def quantize_model(model: str, output: str, quant_type: str,
                   imatrix: str = None) -> str:
    """Step 2: Quantize model with optional imatrix guidance."""
    if not LLAMA_QUANTIZE.exists():
        log.error(f"llama-quantize not found at {LLAMA_QUANTIZE}")
        sys.exit(1)

    cmd = [str(LLAMA_QUANTIZE)]
    if imatrix:
        cmd.extend(["--imatrix", imatrix])
    cmd.extend([model, output, quant_type])

    log.info(f"Quantizing: {quant_type} {'(imatrix-guided)' if imatrix else '(standard)'}")
    log.info(f"  Input:  {model}")
    log.info(f"  Output: {output}")
    log.info(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if result.returncode != 0:
        log.error(f"llama-quantize failed (rc={result.returncode}):\n{result.stderr[-2000:]}")
        sys.exit(1)

    size_gb = os.path.getsize(output) / (1024 ** 3)
    log.info(f"Quantized model: {output} ({size_gb:.2f} GB)")
    return output


def run_benchmark(model_gguf: str):
    """Step 3 (optional): Run eval harness on the quantized model."""
    eval_script = PROJECT_ROOT / "scripts" / "run_eval.py"
    if not eval_script.exists():
        log.warning(f"Eval script not found: {eval_script} — skipping benchmark")
        return

    log.info(f"Running benchmark on {model_gguf} ...")
    log.info("  (This requires llama-server running with the quantized model)")
    cmd = [sys.executable, str(eval_script)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        log.warning(f"Benchmark returned non-zero: {result.returncode}")
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-10:]:
            log.info(f"  {line}")


def main():
    parser = argparse.ArgumentParser(
        description="Dynamic 4-bit quantization with importance matrix (imatrix)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", required=True,
                        help="Path to base GGUF model (e.g. model-f16.gguf)")
    parser.add_argument("--calibration", default=None,
                        help="JSONL file with instruction/output pairs for imatrix calibration")
    parser.add_argument("--quant-type", default="Q4_K_M", choices=QUANT_TYPES,
                        help="Quantization type (default: Q4_K_M)")
    parser.add_argument("--output", default=None,
                        help="Output GGUF path (default: auto-named)")
    parser.add_argument("--imatrix", default=None,
                        help="Use existing imatrix file (skip generation)")
    parser.add_argument("--imatrix-only", action="store_true",
                        help="Only generate imatrix, skip quantization")
    parser.add_argument("--benchmark", action="store_true",
                        help="Run eval harness after quantization")
    parser.add_argument("--ctx-size", type=int, default=512,
                        help="Context size for imatrix generation (default: 512)")
    parser.add_argument("--ngl", type=int, default=99,
                        help="GPU layers for imatrix generation (default: 99)")
    args = parser.parse_args()

    model = os.path.abspath(args.model)
    if not os.path.exists(model):
        log.error(f"Model not found: {model}")
        sys.exit(1)

    model_stem = Path(model).stem

    # --- Step 1: Importance matrix ---
    imatrix_path = args.imatrix
    if not imatrix_path:
        if not args.calibration:
            log.error("--calibration or --imatrix is required")
            sys.exit(1)
        cal_path = Path(args.calibration)
        if not cal_path.exists():
            log.error(f"Calibration file not found: {cal_path}")
            sys.exit(1)

        cal_text = jsonl_to_calibration_text(cal_path)
        imatrix_path = str(Path(model).parent / f"{model_stem}.imatrix.dat")
        generate_imatrix(model, cal_text, imatrix_path,
                         ctx_size=args.ctx_size, ngl=args.ngl)

    if args.imatrix_only:
        log.info("imatrix generation complete (--imatrix-only). Done.")
        return

    # --- Step 2: Quantize ---
    if args.output:
        output = args.output
    else:
        output = str(Path(model).parent / f"{model_stem}-imatrix-{args.quant_type}.gguf")

    quantize_model(model, output, args.quant_type, imatrix=imatrix_path)

    # --- Step 3: Benchmark (optional) ---
    if args.benchmark:
        run_benchmark(output)

    log.info("=" * 50)
    log.info("  DONE")
    log.info(f"  Output: {output}")
    log.info(f"  Size: {os.path.getsize(output) / (1024 ** 3):.2f} GB")
    log.info(f"  Quant: {args.quant_type} (imatrix-guided)")
    log.info("=" * 50)


if __name__ == "__main__":
    main()
