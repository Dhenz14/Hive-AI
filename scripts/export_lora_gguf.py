"""
Export LoRA v1 adapter to GGUF format for Ollama integration.

Workflow:
  1. Load base model (Qwen3-14B 4-bit)
  2. Load LoRA adapter from loras/v1/
  3. Merge LoRA weights into base model
  4. Export as GGUF Q4_K_M quantization
  5. Create Ollama Modelfile
  6. Import into Ollama as 'hiveai-v1'

Usage:
  python scripts/export_lora_gguf.py
  python scripts/export_lora_gguf.py --adapter loras/v1 --name hiveai-v1
"""
import argparse
import logging
import os
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def export_gguf(adapter_path: str, output_dir: str, quant: str = "q4_k_m"):
    """Merge LoRA adapter into base model and export as GGUF."""
    from unsloth import FastLanguageModel

    logger.info(f"Loading base model + LoRA adapter from {adapter_path}")
    t0 = time.time()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter_path,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    logger.info(f"Model loaded in {time.time() - t0:.1f}s")
    logger.info(f"Exporting GGUF ({quant}) to {output_dir}")

    os.makedirs(output_dir, exist_ok=True)

    t1 = time.time()
    model.save_pretrained_gguf(
        output_dir,
        tokenizer,
        quantization_method=quant,
    )
    logger.info(f"GGUF export complete in {time.time() - t1:.1f}s")

    # Find the generated GGUF file
    gguf_files = [f for f in os.listdir(output_dir) if f.endswith(".gguf")]
    if gguf_files:
        gguf_path = os.path.join(output_dir, gguf_files[0])
        logger.info(f"GGUF file: {gguf_path} ({os.path.getsize(gguf_path) / 1e9:.2f} GB)")
        return gguf_path
    else:
        logger.error("No GGUF file found after export!")
        return None


def create_ollama_model(gguf_path: str, model_name: str):
    """Create an Ollama model from the GGUF file."""
    modelfile_path = os.path.join(os.path.dirname(gguf_path), "Modelfile")

    # Write Ollama Modelfile
    modelfile_content = f"""FROM {gguf_path}

TEMPLATE \"\"\"{{{{- if .System }}}}{{{{ .System }}}}{{{{- end }}}}
{{{{- range .Messages }}}}
{{{{- if eq .Role "user" }}}}
### Instruction:
{{{{ .Content }}}}

### Response:
{{{{- else if eq .Role "assistant" }}}}
{{{{ .Content }}}}
{{{{- end }}}}
{{{{- end }}}}\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop "### Instruction:"
PARAMETER stop "### Input:"
PARAMETER num_ctx 2048
"""

    with open(modelfile_path, "w") as f:
        f.write(modelfile_content)
    logger.info(f"Modelfile written to {modelfile_path}")

    # Create Ollama model
    logger.info(f"Creating Ollama model: {model_name}")
    result = subprocess.run(
        ["ollama", "create", model_name, "-f", modelfile_path],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        logger.info(f"Ollama model '{model_name}' created successfully!")
        logger.info(result.stdout)
    else:
        logger.error(f"Failed to create Ollama model: {result.stderr}")
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Export LoRA to GGUF for Ollama")
    parser.add_argument("--adapter", default=os.path.join(PROJECT_ROOT, "loras", "v1"),
                        help="Path to LoRA adapter directory")
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "loras", "v1", "gguf"),
                        help="Output directory for GGUF")
    parser.add_argument("--quant", default="q4_k_m",
                        help="Quantization method (default: q4_k_m)")
    parser.add_argument("--name", default="hiveai-v1",
                        help="Ollama model name (default: hiveai-v1)")
    parser.add_argument("--skip-ollama", action="store_true",
                        help="Only export GGUF, don't create Ollama model")
    args = parser.parse_args()

    logger.info(f"=== HiveAI LoRA -> GGUF Export ===")
    logger.info(f"Adapter: {args.adapter}")
    logger.info(f"Output:  {args.output}")
    logger.info(f"Quant:   {args.quant}")

    # Step 1: Export GGUF
    gguf_path = export_gguf(args.adapter, args.output, args.quant)
    if not gguf_path:
        logger.error("GGUF export failed!")
        sys.exit(1)

    # Step 2: Create Ollama model
    if not args.skip_ollama:
        success = create_ollama_model(gguf_path, args.name)
        if success:
            logger.info(f"\nDone! Run: ollama run {args.name}")
            logger.info(f"Or benchmark: python scripts/run_eval.py --model {args.name}")
        else:
            logger.warning("Ollama model creation failed, but GGUF is available at:")
            logger.warning(f"  {gguf_path}")
    else:
        logger.info(f"GGUF exported to: {gguf_path}")
        logger.info(f"To create Ollama model manually:")
        logger.info(f"  ollama create {args.name} -f {os.path.join(args.output, 'Modelfile')}")


if __name__ == "__main__":
    main()
