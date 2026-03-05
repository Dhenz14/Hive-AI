"""GGUF optimization — llama.cpp conversion, quantization, and inference tuning for 15GB VRAM."""

PAIRS = [
    (
        "local-ai/gguf-conversion-pipeline",
        "Show the complete pipeline for converting a HuggingFace model to GGUF format with optimal quantization for 15GB VRAM inference.",
        """GGUF conversion and quantization pipeline:

```python
import subprocess
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GGUFConfig:
    \"\"\"Configuration for GGUF conversion and quantization.\"\"\"
    hf_model_path: str          # Path to HuggingFace model directory
    output_dir: str             # Where to save GGUF files
    model_name: str             # Base name for output files
    quant_type: str = "Q4_K_M"  # Quantization type
    context_length: int = 4096  # Context window size
    vocab_only: bool = False
    # VRAM budget breakdown for 15GB:
    # Model weights: ~10-12GB (Q4_K_M for 7-14B params)
    # KV cache: ~1-2GB (depends on context length)
    # Compute buffer: ~1GB
    # Overhead: ~0.5GB


@dataclass
class QuantProfile:
    \"\"\"Predefined quantization profiles for different VRAM budgets.\"\"\"
    name: str
    quant_type: str
    bits_per_weight: float
    max_params_15gb: float  # Billions of params that fit in 15GB
    quality_retention: float  # Approximate quality vs FP16

    @staticmethod
    def profiles_for_15gb() -> list:
        return [
            QuantProfile("ultra-compressed", "Q2_K", 2.5, 35.0, 0.82),
            QuantProfile("compressed", "Q3_K_M", 3.4, 26.0, 0.89),
            QuantProfile("balanced", "Q4_K_M", 4.8, 18.0, 0.94),
            QuantProfile("quality", "Q5_K_M", 5.5, 16.0, 0.96),
            QuantProfile("high-quality", "Q6_K", 6.6, 13.0, 0.98),
            QuantProfile("near-lossless", "Q8_0", 8.5, 10.0, 0.99),
        ]


class GGUFConverter:
    \"\"\"Convert HuggingFace models to GGUF with optimal settings.\"\"\"

    def __init__(self, llama_cpp_path: str = "llama.cpp"):
        self.llama_cpp = Path(llama_cpp_path)
        self.convert_script = self.llama_cpp / "convert_hf_to_gguf.py"
        self.quantize_bin = self.llama_cpp / "build" / "bin" / "llama-quantize"

    def convert_hf_to_gguf(self, config: GGUFConfig) -> Path:
        \"\"\"Step 1: Convert HF safetensors to GGUF FP16.\"\"\"
        output_fp16 = Path(config.output_dir) / f"{config.model_name}-f16.gguf"
        os.makedirs(config.output_dir, exist_ok=True)

        cmd = [
            "python", str(self.convert_script),
            config.hf_model_path,
            "--outfile", str(output_fp16),
            "--outtype", "f16",
        ]
        if config.context_length:
            cmd.extend(["--ctx", str(config.context_length)])

        print(f"Converting {config.hf_model_path} -> {output_fp16}")
        subprocess.run(cmd, check=True)
        return output_fp16

    def quantize(self, fp16_path: Path, config: GGUFConfig) -> Path:
        \"\"\"Step 2: Quantize FP16 GGUF to target quant type.\"\"\"
        output_quant = (
            Path(config.output_dir)
            / f"{config.model_name}-{config.quant_type}.gguf"
        )

        cmd = [
            str(self.quantize_bin),
            str(fp16_path),
            str(output_quant),
            config.quant_type,
        ]

        print(f"Quantizing {fp16_path} -> {output_quant} ({config.quant_type})")
        subprocess.run(cmd, check=True)

        # Clean up FP16 intermediate (saves disk space)
        size_fp16 = fp16_path.stat().st_size / (1024**3)
        size_quant = output_quant.stat().st_size / (1024**3)
        print(f"Size: {size_fp16:.1f}GB (FP16) -> {size_quant:.1f}GB ({config.quant_type})")
        print(f"Compression ratio: {size_fp16/size_quant:.1f}x")

        return output_quant

    def full_pipeline(self, config: GGUFConfig) -> Path:
        \"\"\"Run complete conversion pipeline.\"\"\"
        fp16_path = self.convert_hf_to_gguf(config)
        quant_path = self.quantize(fp16_path, config)
        # Delete FP16 intermediate to save disk
        fp16_path.unlink(missing_ok=True)
        return quant_path

    def select_optimal_quant(self, param_count_b: float,
                              vram_budget_gb: float = 15.0) -> QuantProfile:
        \"\"\"Select best quantization that fits VRAM budget.

        Reserve ~3GB for KV cache + compute buffers.
        \"\"\"
        available_for_weights = vram_budget_gb - 3.0  # GB for weights
        profiles = QuantProfile.profiles_for_15gb()

        best = None
        for profile in reversed(profiles):  # Start from highest quality
            weight_size = param_count_b * profile.bits_per_weight / 8
            if weight_size <= available_for_weights:
                best = profile
                break

        if best is None:
            best = profiles[0]  # Fall back to most compressed
            print(f"Warning: {param_count_b}B params tight even at {best.quant_type}")

        print(f"Selected {best.quant_type} for {param_count_b}B params")
        print(f"  Est. weight size: {param_count_b * best.bits_per_weight / 8:.1f}GB")
        print(f"  Quality retention: {best.quality_retention:.0%}")
        return best


# Usage: convert a merged LoRA model to GGUF
converter = GGUFConverter("/opt/llama.cpp")
config = GGUFConfig(
    hf_model_path="/opt/models/my-finetuned-7b",
    output_dir="/opt/models/gguf",
    model_name="my-finetuned-7b",
    quant_type="Q4_K_M",
)
gguf_path = converter.full_pipeline(config)
```

Key patterns:
1. **Two-step pipeline** -- HF safetensors to FP16 GGUF, then quantize to target type
2. **Quant selection** -- Q4_K_M is the sweet spot for 7-14B models on 15GB VRAM (94% quality retention)
3. **VRAM budget** -- reserve 3GB for KV cache and compute; rest goes to model weights
4. **Disk cleanup** -- delete FP16 intermediate after quantizing to save disk space
5. **Profile matching** -- automatically select best quant type given model size and VRAM budget"""
    ),
    (
        "local-ai/llama-server-optimization",
        "Show llama.cpp server optimization: KV cache tuning, batch sizing, speculative decoding, and GPU layer offloading for maximum throughput on 15GB VRAM.",
        """llama.cpp server optimization for 15GB VRAM:

```python
import subprocess
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class LlamaServerConfig:
    \"\"\"Optimized llama-server configuration for 15GB VRAM.\"\"\"
    model_path: str
    host: str = "127.0.0.1"
    port: int = 8080

    # GPU offloading
    n_gpu_layers: int = -1      # -1 = all layers on GPU
    main_gpu: int = 0           # Primary GPU index

    # Context and batching
    context_size: int = 4096    # Context window
    batch_size: int = 512       # Prompt processing batch
    ubatch_size: int = 256      # Micro-batch for CUDA kernels

    # KV cache optimization
    cache_type_k: str = "q4_0"  # Quantize KV cache keys
    cache_type_v: str = "q4_0"  # Quantize KV cache values
    # q4_0 KV cache: ~4x less VRAM than f16 KV cache
    # For ctx=4096, 7B model: ~200MB vs ~800MB

    # Performance tuning
    n_threads: int = 4          # CPU threads for non-GPU work
    flash_attention: bool = True  # Use flash attention if available
    mlock: bool = True          # Lock model in RAM (prevent swapping)
    no_mmap: bool = False       # Memory-map model file

    # Parallelism
    parallel: int = 1           # Concurrent request slots
    cont_batching: bool = True  # Continuous batching

    # Speculative decoding (draft model for faster generation)
    draft_model: Optional[str] = None
    draft_n: int = 8            # Tokens to draft per step
    draft_p_min: float = 0.5    # Min probability for draft acceptance

    def build_command(self) -> list[str]:
        cmd = [
            "llama-server",
            "--model", self.model_path,
            "--host", self.host,
            "--port", str(self.port),
            "--n-gpu-layers", str(self.n_gpu_layers),
            "--ctx-size", str(self.context_size),
            "--batch-size", str(self.batch_size),
            "--ubatch-size", str(self.ubatch_size),
            "--cache-type-k", self.cache_type_k,
            "--cache-type-v", self.cache_type_v,
            "--threads", str(self.n_threads),
            "--parallel", str(self.parallel),
        ]

        if self.flash_attention:
            cmd.append("--flash-attn")
        if self.mlock:
            cmd.append("--mlock")
        if self.cont_batching:
            cmd.append("--cont-batching")
        if self.draft_model:
            cmd.extend([
                "--model-draft", self.draft_model,
                "--draft", str(self.draft_n),
                "--draft-p-min", str(self.draft_p_min),
            ])

        return cmd


def optimize_for_vram(model_size_gb: float,
                       vram_gb: float = 15.0) -> LlamaServerConfig:
    \"\"\"Auto-configure server settings for available VRAM.

    VRAM breakdown:
    - Model weights: model_size_gb
    - KV cache (q4_0): ~50MB per 1K context for 7B model
    - Compute buffers: ~500MB
    - CUDA overhead: ~300MB
    \"\"\"
    available = vram_gb - model_size_gb - 0.8  # Subtract model + overhead

    # Size KV cache to fit available VRAM
    # q4_0 KV cache: ~50MB per 1K context (7B), ~100MB per 1K (14B)
    kv_per_1k = 0.05 * (model_size_gb / 4)  # Scale with model size
    max_ctx = int(available / kv_per_1k * 1000)
    max_ctx = min(max_ctx, 8192)  # Cap at 8K for sanity
    max_ctx = max(max_ctx, 2048)  # Floor at 2K

    # Parallel slots: each slot needs its own KV cache
    kv_total = kv_per_1k * (max_ctx / 1000)
    max_parallel = max(1, int(available / kv_total))
    max_parallel = min(max_parallel, 4)  # Cap at 4 slots

    config = LlamaServerConfig(
        model_path="",  # Set by caller
        context_size=max_ctx,
        parallel=max_parallel,
        cache_type_k="q4_0",
        cache_type_v="q4_0",
        flash_attention=True,
    )

    print(f"VRAM budget: {vram_gb}GB")
    print(f"  Model: {model_size_gb:.1f}GB")
    print(f"  KV cache ({max_ctx} ctx x {max_parallel} slots): "
          f"{kv_total * max_parallel:.1f}GB")
    print(f"  Overhead: ~0.8GB")
    print(f"  Context: {max_ctx}, Parallel: {max_parallel}")

    return config


# Example: optimize for a Q4_K_M 7B model (~4.5GB)
config = optimize_for_vram(model_size_gb=4.5, vram_gb=15.0)
config.model_path = "/opt/models/my-7b-Q4_K_M.gguf"
print(" ".join(config.build_command()))
```

Key patterns:
1. **Quantized KV cache** -- q4_0 keys/values use 4x less VRAM than f16; enables longer context
2. **Flash attention** -- fused kernel reduces memory and improves speed; always enable if supported
3. **Speculative decoding** -- small draft model proposes tokens, main model verifies; 2-3x speedup
4. **Context/parallel tradeoff** -- more parallel slots = less context per slot; tune for workload
5. **Auto-configuration** -- calculate optimal settings from model size and VRAM budget automatically"""
    ),
    (
        "local-ai/gguf-after-lora-merge",
        "Show the complete workflow for merging a LoRA adapter back into a base model and re-quantizing to GGUF for local inference.",
        """LoRA merge and GGUF re-export workflow:

```python
import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class MergeConfig:
    base_model: str          # HF model path or directory
    lora_path: str           # Path to LoRA adapter
    output_dir: str          # Where to save merged model
    merge_ratio: float = 1.0  # LoRA scaling factor (0.0-1.0)
    quant_type: str = "Q4_K_M"
    llama_cpp_path: str = "llama.cpp"
    delete_intermediates: bool = True  # Clean up FP16 files


class LoRAMergeToGGUF:
    \"\"\"Merge LoRA into base model and export optimized GGUF.

    Full pipeline: load base + LoRA -> merge weights -> save HF ->
    convert to GGUF FP16 -> quantize -> clean up intermediates.
    \"\"\"

    def __init__(self, config: MergeConfig):
        self.config = config
        self.merged_hf_path = os.path.join(config.output_dir, "merged_hf")
        self.gguf_fp16_path = os.path.join(config.output_dir, "merged-f16.gguf")
        self.gguf_final_path = os.path.join(
            config.output_dir,
            f"merged-{config.quant_type}.gguf"
        )

    def step1_merge_lora(self):
        \"\"\"Merge LoRA weights into base model using PEFT.\"\"\"
        from peft import PeftModel, PeftConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        print(f"Loading base model: {self.config.base_model}")
        base = AutoModelForCausalLM.from_pretrained(
            self.config.base_model,
            torch_dtype=torch.float16,
            device_map="cpu",  # Merge on CPU to save VRAM
            low_cpu_mem_usage=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(self.config.base_model)

        print(f"Loading LoRA: {self.config.lora_path}")
        model = PeftModel.from_pretrained(base, self.config.lora_path)

        if self.config.merge_ratio < 1.0:
            # Scale LoRA weights before merge
            for name, param in model.named_parameters():
                if "lora_" in name:
                    param.data *= self.config.merge_ratio

        print("Merging LoRA into base model...")
        merged = model.merge_and_unload()

        print(f"Saving merged model to {self.merged_hf_path}")
        os.makedirs(self.merged_hf_path, exist_ok=True)
        merged.save_pretrained(self.merged_hf_path, safe_serialization=True)
        tokenizer.save_pretrained(self.merged_hf_path)

        # Free memory
        del merged, model, base
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def step2_convert_to_gguf(self):
        \"\"\"Convert merged HF model to GGUF FP16.\"\"\"
        convert_script = os.path.join(
            self.config.llama_cpp_path, "convert_hf_to_gguf.py"
        )
        cmd = [
            "python", convert_script,
            self.merged_hf_path,
            "--outfile", self.gguf_fp16_path,
            "--outtype", "f16",
        ]
        print(f"Converting to GGUF FP16...")
        subprocess.run(cmd, check=True)

    def step3_quantize(self):
        \"\"\"Quantize GGUF FP16 to target type.\"\"\"
        quantize_bin = os.path.join(
            self.config.llama_cpp_path, "build", "bin", "llama-quantize"
        )
        cmd = [
            quantize_bin,
            self.gguf_fp16_path,
            self.gguf_final_path,
            self.config.quant_type,
        ]
        print(f"Quantizing to {self.config.quant_type}...")
        subprocess.run(cmd, check=True)

    def step4_cleanup(self):
        \"\"\"Remove intermediate files to save disk.\"\"\"
        if self.config.delete_intermediates:
            if os.path.exists(self.gguf_fp16_path):
                os.unlink(self.gguf_fp16_path)
                print(f"Deleted FP16 intermediate: {self.gguf_fp16_path}")
            if os.path.exists(self.merged_hf_path):
                shutil.rmtree(self.merged_hf_path)
                print(f"Deleted merged HF dir: {self.merged_hf_path}")

    def step5_validate(self) -> dict:
        \"\"\"Quick validation: load GGUF and run test prompt.\"\"\"
        import requests

        # Assumes llama-server is running or we start it briefly
        test_prompt = "Write a Python function that"
        response = requests.post(
            "http://127.0.0.1:8080/completion",
            json={
                "prompt": test_prompt,
                "n_predict": 50,
                "temperature": 0.1,
            },
            timeout=30,
        )
        result = response.json()
        generated = result.get("content", "")

        stats = {
            "gguf_path": self.gguf_final_path,
            "file_size_gb": os.path.getsize(self.gguf_final_path) / (1024**3),
            "quant_type": self.config.quant_type,
            "test_output_length": len(generated),
            "generates_code": "def " in generated or "return" in generated,
        }
        print(f"Validation: {stats}")
        return stats

    def run_full_pipeline(self) -> str:
        \"\"\"Execute complete merge -> GGUF pipeline.\"\"\"
        self.step1_merge_lora()
        self.step2_convert_to_gguf()
        self.step3_quantize()
        self.step4_cleanup()
        print(f"Final GGUF: {self.gguf_final_path}")
        return self.gguf_final_path


# Usage after a training cycle
config = MergeConfig(
    base_model="/opt/models/qwen3.5-7b",
    lora_path="/opt/training/cycle_3/lora_adapter",
    output_dir="/opt/models/cycle_3_merged",
    merge_ratio=0.85,  # Scale LoRA to prevent catastrophic forgetting
    quant_type="Q4_K_M",
)
pipeline = LoRAMergeToGGUF(config)
final_gguf = pipeline.run_full_pipeline()
```

Key patterns:
1. **CPU merge** -- merge LoRA on CPU to avoid VRAM pressure; only need VRAM for inference
2. **Merge ratio** -- scale LoRA weights (0.85) to prevent overwriting base knowledge
3. **Pipeline stages** -- merge -> FP16 GGUF -> quantize -> cleanup; each stage independent
4. **Disk hygiene** -- delete FP16 intermediate and merged HF dir immediately after quantizing
5. **Validation** -- test generation after merge to catch catastrophic failures before deploying"""
    ),
]
