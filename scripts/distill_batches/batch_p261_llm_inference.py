"""LLM inference optimization — batching, caching, quantization, serving."""

PAIRS = [
    (
        "ai/llm-serving",
        "Show LLM serving patterns: vLLM setup, continuous batching, streaming, and API server configuration for production.",
        '''LLM serving with vLLM:

```python
from vllm import LLM, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import uvicorn
import json
from dataclasses import dataclass


@dataclass
class InferenceConfig:
    model: str = "meta-llama/Llama-3.1-8B-Instruct"
    tensor_parallel_size: int = 1
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.9
    quantization: str = None  # "awq", "gptq", "squeezellm"
    dtype: str = "auto"       # "float16", "bfloat16", "auto"


def create_offline_engine(config: InferenceConfig) -> LLM:
    """Create vLLM engine for batch inference."""
    return LLM(
        model=config.model,
        tensor_parallel_size=config.tensor_parallel_size,
        max_model_len=config.max_model_len,
        gpu_memory_utilization=config.gpu_memory_utilization,
        quantization=config.quantization,
        dtype=config.dtype,
    )


def batch_generate(engine: LLM, prompts: list[str],
                    temperature: float = 0.7, max_tokens: int = 512) -> list[str]:
    """Batch inference with continuous batching."""
    params = SamplingParams(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=0.9,
        repetition_penalty=1.1,
    )

    outputs = engine.generate(prompts, params)
    return [output.outputs[0].text for output in outputs]


# === Async API Server ===

app = FastAPI()

async def create_async_engine(config: InferenceConfig):
    args = AsyncEngineArgs(
        model=config.model,
        tensor_parallel_size=config.tensor_parallel_size,
        max_model_len=config.max_model_len,
    )
    return AsyncLLMEngine.from_engine_args(args)


@app.post("/v1/completions")
async def completions(request: dict):
    """OpenAI-compatible completions endpoint."""
    prompt = request["prompt"]
    params = SamplingParams(
        temperature=request.get("temperature", 0.7),
        max_tokens=request.get("max_tokens", 256),
        top_p=request.get("top_p", 1.0),
    )

    request_id = f"req-{id(request)}"
    results = []

    async for output in engine.generate(prompt, params, request_id):
        if output.finished:
            results.append(output.outputs[0].text)

    return {"choices": [{"text": results[0]}]}


@app.post("/v1/completions/stream")
async def stream_completions(request: dict):
    """Streaming completions with SSE."""
    prompt = request["prompt"]
    params = SamplingParams(
        temperature=request.get("temperature", 0.7),
        max_tokens=request.get("max_tokens", 256),
    )

    async def generate_stream():
        request_id = f"req-{id(request)}"
        previous_text = ""
        async for output in engine.generate(prompt, params, request_id):
            new_text = output.outputs[0].text[len(previous_text):]
            previous_text = output.outputs[0].text
            if new_text:
                yield f"data: {json.dumps({'text': new_text})}\\n\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
```

Serving framework comparison:

| Framework | Batching | Quantization | Speed |
|-----------|---------|-------------|-------|
| **vLLM** | Continuous + PagedAttention | AWQ, GPTQ | Fastest |
| **TGI** | Continuous | GPTQ, EETQ | Fast |
| **llama.cpp** | N/A (single) | GGUF (many quants) | Good (CPU) |
| **Ollama** | Queue-based | GGUF | Good (ease of use) |

Key patterns:
1. **Continuous batching** — new requests join mid-batch; maximizes GPU utilization
2. **PagedAttention** — vLLM's paged KV cache; eliminates memory waste from fragmentation
3. **Streaming** — SSE for token-by-token delivery; critical for user experience
4. **GPU memory util** — 0.9 = use 90% of VRAM for KV cache; balance throughput vs headroom
5. **Tensor parallelism** — split model across GPUs; enables serving larger models'''
    ),
    (
        "ai/inference-optimization",
        "Show inference optimization techniques: operator fusion, kernel optimization, torch.compile, and ONNX export for deployment.",
        '''Inference optimization for production:

```python
import torch
import torch.nn as nn
import time
from contextlib import contextmanager


@contextmanager
def benchmark(name: str, warmup: int = 3, runs: int = 10):
    """Benchmark inference latency."""
    # Warmup
    yield
    torch.cuda.synchronize()

    times = []
    for _ in range(runs):
        start = time.perf_counter()
        yield
        torch.cuda.synchronize()
        times.append(time.perf_counter() - start)

    avg = sum(times) / len(times)
    print(f"{name}: {avg*1000:.1f}ms avg ({min(times)*1000:.1f}-{max(times)*1000:.1f}ms)")


def optimize_with_compile(model: nn.Module, example_input: torch.Tensor) -> nn.Module:
    """torch.compile: JIT compile model for faster inference.

    Modes:
    - default: balance compile time and speedup
    - reduce-overhead: minimize CPU overhead (good for small models)
    - max-autotune: try all optimizations (slow compile, fastest run)
    """
    compiled = torch.compile(
        model,
        mode="max-autotune",
        fullgraph=True,
    )

    # Warmup compilation
    with torch.no_grad():
        _ = compiled(example_input)

    return compiled


def export_to_onnx(model: nn.Module, example_input: torch.Tensor,
                    output_path: str, opset_version: int = 17):
    """Export model to ONNX for cross-platform deployment."""
    model.eval()

    torch.onnx.export(
        model,
        example_input,
        output_path,
        opset_version=opset_version,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "sequence_length"},
            "output": {0: "batch_size"},
        },
    )

    # Verify
    import onnx
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    print(f"Exported to {output_path}")


def optimize_onnx(model_path: str, output_path: str):
    """Optimize ONNX model with ONNX Runtime."""
    import onnxruntime as ort
    from onnxruntime.transformers import optimizer

    opt_model = optimizer.optimize_model(
        model_path,
        model_type="bert",
        opt_level=2,  # Extended optimizations
        use_gpu=True,
    )
    opt_model.save_model_to_file(output_path)


class ONNXInference:
    """Run inference with ONNX Runtime."""

    def __init__(self, model_path: str, device: str = "cuda"):
        providers = ["CUDAExecutionProvider"] if device == "cuda" else ["CPUExecutionProvider"]
        self.session = __import__("onnxruntime").InferenceSession(
            model_path, providers=providers,
        )

    def __call__(self, **inputs) -> dict:
        input_feed = {k: v.numpy() for k, v in inputs.items()}
        outputs = self.session.run(None, input_feed)
        return {name.name: torch.from_numpy(out)
                for name, out in zip(self.session.get_outputs(), outputs)}


def apply_static_quantization(model: nn.Module, calibration_data):
    """Post-training static quantization for CPU inference."""
    model.eval()
    model.qconfig = torch.ao.quantization.get_default_qconfig("x86")
    prepared = torch.ao.quantization.prepare(model)

    # Calibrate with representative data
    with torch.no_grad():
        for batch in calibration_data:
            prepared(batch)

    quantized = torch.ao.quantization.convert(prepared)
    return quantized
```

Optimization comparison:

| Technique | Speedup | Quality loss | Effort |
|-----------|---------|-------------|--------|
| **torch.compile** | 1.5-3x | None | Low |
| **ONNX Runtime** | 1.5-2x | None | Medium |
| **TensorRT** | 2-5x | None | High |
| **INT8 quantization** | 2-4x | Minimal | Medium |
| **Operator fusion** | 1.2-1.5x | None | Auto |

Key patterns:
1. **torch.compile** — JIT compilation with Triton; drop-in speedup for PyTorch models
2. **ONNX export** — cross-platform format; supports dynamic batch/sequence dimensions
3. **Static quantization** — INT8 weights + activations; requires calibration data
4. **Warmup** — first inference compiles/optimizes; benchmark after warmup
5. **Dynamic axes** — ONNX dynamic dimensions for variable batch size and sequence length'''
    ),
    (
        "ai/model-compression",
        "Show model compression for edge deployment: pruning + quantization, knowledge distillation to small models, and TensorRT optimization.",
        '''Model compression for edge deployment:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class DistillationTrainer:
    """Knowledge distillation: transfer knowledge from large to small model.

    Teacher (large, slow) → Student (small, fast)
    Student learns from both ground truth labels AND teacher's soft predictions.
    """

    def __init__(self, teacher: nn.Module, student: nn.Module,
                 temperature: float = 4.0, alpha: float = 0.7):
        self.teacher = teacher
        self.student = student
        self.temperature = temperature
        self.alpha = alpha  # Weight for distillation vs hard label loss
        self.teacher.eval()

    def distillation_loss(self, student_logits, teacher_logits, labels):
        """Combined loss: soft labels from teacher + hard labels from data."""
        T = self.temperature

        # Soft loss: KL divergence between student and teacher distributions
        soft_student = F.log_softmax(student_logits / T, dim=-1)
        soft_teacher = F.softmax(teacher_logits / T, dim=-1)
        soft_loss = F.kl_div(soft_student, soft_teacher, reduction="batchmean") * (T ** 2)

        # Hard loss: standard cross-entropy with ground truth
        hard_loss = F.cross_entropy(student_logits, labels)

        return self.alpha * soft_loss + (1 - self.alpha) * hard_loss

    def train_step(self, inputs, labels, optimizer):
        self.student.train()

        with torch.no_grad():
            teacher_logits = self.teacher(inputs)

        student_logits = self.student(inputs)
        loss = self.distillation_loss(student_logits, teacher_logits, labels)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        return loss.item()


def prune_and_quantize(model: nn.Module, sparsity: float = 0.5):
    """Combined pruning + quantization for maximum compression."""
    import torch.nn.utils.prune as prune

    # Step 1: Structured pruning
    for name, module in model.named_modules():
        if isinstance(module, nn.Linear):
            prune.l1_unstructured(module, name="weight", amount=sparsity)
            prune.remove(module, "weight")

    # Step 2: Dynamic quantization (no calibration needed)
    quantized = torch.ao.quantization.quantize_dynamic(
        model,
        {nn.Linear},
        dtype=torch.qint8,
    )

    # Report compression
    def count_params(m):
        return sum(p.numel() for p in m.parameters())

    def count_nonzero(m):
        return sum((p != 0).sum().item() for p in m.parameters())

    total = count_params(model)
    nonzero = count_nonzero(model)
    print(f"Sparsity: {1 - nonzero/total:.1%}")
    print(f"Parameters: {total:,} -> {nonzero:,} nonzero")

    return quantized


def export_for_mobile(model: nn.Module, example: torch.Tensor, output_path: str):
    """Export model for mobile/edge deployment."""
    model.eval()

    # TorchScript for mobile
    scripted = torch.jit.trace(model, example)
    scripted_optimized = torch.utils.mobile_optimizer.optimize_for_mobile(scripted)
    scripted_optimized._save_for_lite_interpreter(output_path)
    print(f"Saved mobile model to {output_path}")
```

Compression pipeline:

| Step | Technique | Size reduction | Accuracy impact |
|------|-----------|---------------|-----------------|
| 1 | Knowledge distillation | 4-10x fewer params | -1-3% |
| 2 | Pruning (50%) | 2x less storage | -0.5-1% |
| 3 | INT8 quantization | 4x less storage | -0.1-0.5% |
| **Total** | Combined | 32-160x smaller | -2-5% |

Key patterns:
1. **Temperature scaling** — higher T softens probabilities; reveals teacher's dark knowledge
2. **Alpha blending** — balance soft (teacher) and hard (ground truth) losses; typically α=0.7
3. **Prune then quantize** — pruning first, then quantize remaining weights; maximum compression
4. **Dynamic quantization** — INT8 linear layers without calibration data; easy to apply
5. **Mobile export** — TorchScript + mobile optimizer for on-device inference'''
    ),
]
