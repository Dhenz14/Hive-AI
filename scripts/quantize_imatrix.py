"""
Dynamic 4-bit quantization with importance matrix (imatrix).

Standard Q4_K_M quantizes all layers equally. imatrix-guided quantization
keeps attention layers at higher precision while aggressively quantizing
less important FFN weights, enabling larger models on 16GB VRAM.

Prerequisites:
    - llama.cpp built with CUDA (~/llama.cpp/bin/)
    - Base model in GGUF format or HuggingFace safetensors
    - Calibration text (training data or representative prompts)

Usage:
    # Step 1: Generate importance matrix
    python scripts/quantize_imatrix.py --generate-imatrix --model models/model.gguf

    # Step 2: Quantize with imatrix
    python scripts/quantize_imatrix.py --quantize --model models/model.gguf --quant Q4_K_M

    # One-shot: generate imatrix + quantize
    python scripts/quantize_imatrix.py --model models/model.gguf --quant Q4_K_M

    # Custom calibration data
    python scripts/quantize_imatrix.py --model models/model.gguf --calibration-data my_data.txt

Target: Run Qwen2.5-Coder-32B on 16GB VRAM (currently impossible with standard Q4_K_M).
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default paths — adjust for your system
LLAMA_CPP_DIR = Path.home() / "llama.cpp" / "bin"
LLAMA_IMATRIX = LLAMA_CPP_DIR / "llama-imatrix"
LLAMA_QUANTIZE = LLAMA_CPP_DIR / "llama-quantize"

# Windows executables
if sys.platform == "win32":
    LLAMA_IMATRIX = LLAMA_IMATRIX.with_suffix(".exe")
    LLAMA_QUANTIZE = LLAMA_QUANTIZE.with_suffix(".exe")

# Supported quantization types (ordered by size, smallest first)
QUANT_TYPES = {
    "Q2_K":    {"bits": 2.5, "desc": "Smallest, significant quality loss"},
    "Q3_K_S":  {"bits": 3.0, "desc": "Small, noticeable quality loss"},
    "Q3_K_M":  {"bits": 3.5, "desc": "Medium-small, moderate quality loss"},
    "Q4_0":    {"bits": 4.0, "desc": "Legacy 4-bit, uniform quantization"},
    "Q4_K_S":  {"bits": 4.0, "desc": "Small 4-bit, good balance"},
    "Q4_K_M":  {"bits": 4.5, "desc": "Medium 4-bit, recommended default"},
    "Q5_K_S":  {"bits": 5.0, "desc": "Small 5-bit, near-lossless"},
    "Q5_K_M":  {"bits": 5.5, "desc": "Medium 5-bit, high quality"},
    "Q6_K":    {"bits": 6.5, "desc": "6-bit, minimal quality loss"},
    "Q8_0":    {"bits": 8.0, "desc": "8-bit, virtually lossless"},
}

# VRAM estimates for common model sizes at different quant levels
VRAM_ESTIMATES = {
    # (param_billions, quant_type) -> approximate VRAM in GB (with KV cache for ctx=4096)
    (7,  "Q4_K_M"): 5.5,
    (7,  "Q5_K_M"): 6.5,
    (14, "Q4_K_M"): 9.5,
    (14, "Q5_K_M"): 11.0,
    (32, "Q4_K_M"): 20.0,
    (32, "Q3_K_M"): 16.5,
    (32, "Q2_K"):   13.0,
    (70, "Q4_K_M"): 42.0,
    (70, "Q2_K"):   28.0,
}


def generate_calibration_data(output_path: Path, max_lines: int = 500):
    """Generate calibration text from training data.

    Good calibration data should be representative of actual model usage.
    We use a mix of training pair outputs (code + explanations).
    """
    training_files = [
        PROJECT_ROOT / "loras" / "training_data" / "v8.jsonl",
        PROJECT_ROOT / "loras" / "training_data" / "v7.jsonl",
    ]

    lines = []
    for tf in training_files:
        if not tf.exists():
            continue
        with open(tf, "r", encoding="utf-8") as f:
            for line_str in f:
                if not line_str.strip():
                    continue
                try:
                    row = json.loads(line_str)
                    # Use the output (response) as calibration — it's what the model generates
                    output = row.get("output", "")
                    if len(output) > 100:
                        lines.append(output)
                except json.JSONDecodeError:
                    continue
                if len(lines) >= max_lines:
                    break
        if len(lines) >= max_lines:
            break

    if not lines:
        logger.error("No training data found for calibration. Need v7.jsonl or v8.jsonl.")
        sys.exit(1)

    # Write as plain text (one response per block, separated by newlines)
    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines[:max_lines]:
            f.write(line + "\n\n")

    logger.info(f"Generated calibration data: {len(lines[:max_lines])} samples -> {output_path}")
    return output_path


def run_imatrix(model_path: str, calibration_path: str, output_path: str,
                ctx_size: int = 512, n_gpu_layers: int = 99):
    """Generate importance matrix using llama-imatrix."""
    if not LLAMA_IMATRIX.exists():
        logger.error(f"llama-imatrix not found at {LLAMA_IMATRIX}")
        logger.error("Build llama.cpp: cd ~/llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build")
        sys.exit(1)

    cmd = [
        str(LLAMA_IMATRIX),
        "-m", model_path,
        "-f", calibration_path,
        "-o", output_path,
        "-c", str(ctx_size),
        "-ngl", str(n_gpu_layers),
        "--chunks", "100",        # Process 100 chunks of calibration data
    ]

    logger.info(f"Generating importance matrix...")
    logger.info(f"  Model: {model_path}")
    logger.info(f"  Calibration: {calibration_path}")
    logger.info(f"  Output: {output_path}")
    logger.info(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        logger.error(f"llama-imatrix failed:\n{result.stderr}")
        sys.exit(1)

    logger.info(f"Importance matrix generated: {output_path}")
    if result.stdout:
        # Log last few lines of output
        for line in result.stdout.strip().split("\n")[-5:]:
            logger.info(f"  {line}")


def run_quantize(model_path: str, output_path: str, quant_type: str,
                 imatrix_path: str = None):
    """Quantize model using llama-quantize with optional imatrix."""
    if not LLAMA_QUANTIZE.exists():
        logger.error(f"llama-quantize not found at {LLAMA_QUANTIZE}")
        sys.exit(1)

    cmd = [
        str(LLAMA_QUANTIZE),
    ]
    if imatrix_path:
        cmd.extend(["--imatrix", imatrix_path])
    cmd.extend([model_path, output_path, quant_type])

    logger.info(f"Quantizing model...")
    logger.info(f"  Input: {model_path}")
    logger.info(f"  Output: {output_path}")
    logger.info(f"  Type: {quant_type} ({QUANT_TYPES.get(quant_type, {}).get('desc', 'unknown')})")
    logger.info(f"  imatrix: {imatrix_path or 'NONE (standard quantization)'}")
    logger.info(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if result.returncode != 0:
        logger.error(f"llama-quantize failed:\n{result.stderr}")
        sys.exit(1)

    # Report output file size
    out_size = os.path.getsize(output_path) / (1024**3)
    logger.info(f"Quantized model: {output_path} ({out_size:.1f} GB)")

    return output_path


def estimate_vram(model_params_b: float, quant_type: str, ctx_size: int = 4096):
    """Estimate VRAM usage for a quantized model."""
    quant_info = QUANT_TYPES.get(quant_type)
    if not quant_info:
        return None

    # Rough formula: params * bits_per_param / 8 + KV cache
    model_size_gb = model_params_b * quant_info["bits"] / 8
    # KV cache estimate: 2 * n_layers * d_model * ctx_size * 2 bytes (kv)
    # Simplified: ~0.5GB per 4096 ctx for 14B, scales linearly
    kv_cache_gb = (model_params_b / 14.0) * (ctx_size / 4096.0) * 0.5
    overhead_gb = 0.5  # CUDA overhead

    total = model_size_gb + kv_cache_gb + overhead_gb
    return round(total, 1)


def main():
    parser = argparse.ArgumentParser(
        description="Dynamic 4-bit quantization with importance matrix",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard quantization (no imatrix)
  python scripts/quantize_imatrix.py --model model.gguf --quant Q4_K_M --no-imatrix

  # imatrix-guided quantization (recommended)
  python scripts/quantize_imatrix.py --model model.gguf --quant Q4_K_M

  # Generate imatrix only (for later use)
  python scripts/quantize_imatrix.py --generate-imatrix --model model.gguf

  # Aggressive quant for 16GB VRAM
  python scripts/quantize_imatrix.py --model model.gguf --quant Q3_K_M

  # List quant types and VRAM estimates
  python scripts/quantize_imatrix.py --list-quants --model-params 32
        """,
    )
    parser.add_argument("--model", type=str, required=False,
                        help="Path to base GGUF model")
    parser.add_argument("--quant", type=str, default="Q4_K_M",
                        choices=list(QUANT_TYPES.keys()),
                        help="Quantization type (default: Q4_K_M)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output GGUF path (default: auto-named)")
    parser.add_argument("--calibration-data", type=str, default=None,
                        help="Path to calibration text file (default: auto-generated from training data)")
    parser.add_argument("--generate-imatrix", action="store_true",
                        help="Only generate importance matrix (skip quantization)")
    parser.add_argument("--no-imatrix", action="store_true",
                        help="Skip imatrix, use standard quantization")
    parser.add_argument("--imatrix", type=str, default=None,
                        help="Use existing imatrix file")
    parser.add_argument("--ctx-size", type=int, default=512,
                        help="Context size for imatrix generation (default: 512)")
    parser.add_argument("--list-quants", action="store_true",
                        help="List available quantization types with VRAM estimates")
    parser.add_argument("--model-params", type=float, default=14,
                        help="Model size in billions of parameters (for VRAM estimates)")
    args = parser.parse_args()

    if args.list_quants:
        print(f"\nQuantization types for {args.model_params:.0f}B model (ctx=4096):\n")
        print(f"  {'Type':<10} {'Bits':>5} {'~VRAM':>7}  Description")
        print(f"  {'─'*10} {'─'*5} {'─'*7}  {'─'*40}")
        for qtype, info in QUANT_TYPES.items():
            vram = estimate_vram(args.model_params, qtype)
            vram_str = f"{vram:.1f}GB" if vram else "?"
            fits = " ✓" if vram and vram <= 16 else " ✗" if vram and vram > 16 else ""
            print(f"  {qtype:<10} {info['bits']:>5.1f} {vram_str:>7}{fits}  {info['desc']}")
        print(f"\n  ✓ = fits 16GB VRAM, ✗ = exceeds 16GB VRAM")
        return

    if not args.model:
        parser.error("--model is required (unless using --list-quants)")

    model_path = os.path.abspath(args.model)
    if not os.path.exists(model_path):
        logger.error(f"Model not found: {model_path}")
        sys.exit(1)

    # --- Calibration data ---
    if args.calibration_data:
        cal_path = args.calibration_data
    else:
        cal_path = str(PROJECT_ROOT / "scripts" / "calibration_data.txt")
        if not os.path.exists(cal_path):
            generate_calibration_data(Path(cal_path))

    # --- imatrix ---
    imatrix_path = args.imatrix
    model_stem = Path(model_path).stem

    if not args.no_imatrix and not imatrix_path:
        imatrix_path = str(PROJECT_ROOT / "models" / f"{model_stem}.imatrix.dat")
        if not os.path.exists(imatrix_path):
            run_imatrix(model_path, cal_path, imatrix_path, ctx_size=args.ctx_size)
        else:
            logger.info(f"Using existing imatrix: {imatrix_path}")

    if args.generate_imatrix:
        logger.info("imatrix generation complete. Use --quantize to create quantized model.")
        return

    # --- Quantize ---
    if args.output:
        output_path = args.output
    else:
        suffix = f"-imatrix-{args.quant}" if imatrix_path else f"-{args.quant}"
        output_path = str(PROJECT_ROOT / "models" / f"{model_stem}{suffix}.gguf")

    run_quantize(model_path, output_path, args.quant,
                 imatrix_path=imatrix_path if not args.no_imatrix else None)

    # --- Summary ---
    vram = estimate_vram(14, args.quant)  # Default to 14B
    logger.info("=" * 60)
    logger.info("  QUANTIZATION COMPLETE")
    logger.info(f"  Output: {output_path}")
    logger.info(f"  Size: {os.path.getsize(output_path) / (1024**3):.1f} GB")
    if vram:
        logger.info(f"  Est. VRAM: ~{vram} GB (14B @ ctx=4096)")
    logger.info(f"  imatrix: {'YES' if imatrix_path else 'NO (standard)'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
