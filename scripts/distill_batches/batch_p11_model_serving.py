PAIRS = [
    (
        "model-serving/inference-optimization-batching",
        r"""Explain ML model inference optimization techniques including dynamic batching, model quantization for serving, KV-cache management for LLMs, continuous batching strategies, and GPU memory optimization for production deployment.""",
        r"""## ML Model Inference Optimization: Batching, Quantization, and GPU Memory Management

Serving ML models in production requires dramatically different optimization strategies than training. During training, throughput is king — you want maximum GPU utilization over hours. During inference, **latency** and **cost** dominate, **because** users expect sub-second responses and GPU hours are expensive. The **trade-off** between latency, throughput, and cost drives every architectural decision in model serving.

### Dynamic Batching

**Dynamic batching** collects individual requests into batches, amortizing the fixed overhead of GPU kernel launches and memory transfers. **However**, batching increases latency for early-arriving requests that must wait for the batch to fill.

```python
import asyncio
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import deque

@dataclass
class InferenceRequest:
    id: str
    input_data: np.ndarray
    arrived_at: float = field(default_factory=time.monotonic)
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())

class DynamicBatcher:
    # Collects requests into optimal batches
    # Trade-off: larger batches = better throughput but higher latency
    # Best practice: set both max_batch_size AND max_wait_time

    def __init__(
        self,
        model,
        max_batch_size: int = 32,
        max_wait_ms: float = 50.0,
        preferred_batch_sizes: list[int] = None,
    ):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        # Some hardware is more efficient at specific batch sizes (powers of 2)
        self.preferred_batch_sizes = preferred_batch_sizes or [1, 2, 4, 8, 16, 32]
        self._queue: deque[InferenceRequest] = deque()
        self._batch_event = asyncio.Event()
        self._running = False

        # Metrics
        self.total_requests = 0
        self.total_batches = 0
        self.total_padding_waste = 0

    async def submit(self, input_data: np.ndarray) -> Any:
        # Submit a single request, returns when batch completes
        request = InferenceRequest(
            id=f"req_{self.total_requests}",
            input_data=input_data,
        )
        self.total_requests += 1
        self._queue.append(request)
        self._batch_event.set()  # Wake up batcher
        return await request.future

    async def run_batcher(self):
        # Main batching loop — runs as background task
        self._running = True
        while self._running:
            await self._batch_event.wait()
            self._batch_event.clear()

            # Wait for batch to fill or timeout
            deadline = time.monotonic() + self.max_wait_ms / 1000
            while len(self._queue) < self.max_batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        self._wait_for_more(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    break

            if not self._queue:
                continue

            # Extract batch
            batch_size = min(len(self._queue), self.max_batch_size)
            # Snap to preferred batch size for GPU efficiency
            actual_size = self._snap_batch_size(batch_size)
            requests = [self._queue.popleft() for _ in range(batch_size)]

            # Pad batch if needed
            # Common mistake: not padding to preferred sizes wastes GPU efficiency
            inputs = np.stack([r.input_data for r in requests])
            if actual_size > batch_size:
                padding = np.zeros((actual_size - batch_size, *inputs.shape[1:]))
                inputs = np.concatenate([inputs, padding])
                self.total_padding_waste += actual_size - batch_size

            # Run inference
            self.total_batches += 1
            try:
                outputs = await self.model.predict_batch(inputs)
                # Distribute results to individual request futures
                for i, req in enumerate(requests):
                    req.future.set_result(outputs[i])
            except Exception as e:
                for req in requests:
                    req.future.set_exception(e)

    def _snap_batch_size(self, size: int) -> int:
        for ps in self.preferred_batch_sizes:
            if ps >= size:
                return ps
        return size

    async def _wait_for_more(self):
        while len(self._queue) < self.max_batch_size:
            await asyncio.sleep(0.001)
```

### KV-Cache Management for LLM Serving

For **autoregressive LLMs**, the KV-cache stores previous attention key-value pairs to avoid recomputation. **Therefore**, memory management for KV-cache is the primary bottleneck in LLM serving.

```python
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class KVBlock:
    # Fixed-size block of KV cache memory
    # PagedAttention (vLLM) manages KV cache like virtual memory pages
    block_id: int
    block_size: int  # number of tokens per block (typically 16)
    key_data: Optional[np.ndarray] = None   # shape: (block_size, num_heads, head_dim)
    value_data: Optional[np.ndarray] = None
    ref_count: int = 0  # for copy-on-write sharing
    num_filled: int = 0

    @property
    def is_full(self) -> bool:
        return self.num_filled >= self.block_size

    @property
    def is_empty(self) -> bool:
        return self.num_filled == 0

class PagedKVCacheManager:
    # Manages KV cache using paged memory allocation (like OS virtual memory)
    # Best practice: this is the approach used by vLLM and TensorRT-LLM
    # because it eliminates memory fragmentation from variable-length sequences

    def __init__(
        self,
        num_layers: int,
        num_heads: int,
        head_dim: int,
        block_size: int = 16,
        max_blocks: int = 1024,
        dtype=np.float16,
    ):
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.head_dim = head_dim
        self.block_size = block_size
        self.max_blocks = max_blocks
        self.dtype = dtype

        # Pre-allocate all KV cache blocks (GPU memory pool)
        # Pitfall: not pre-allocating leads to fragmentation
        self.free_blocks: list[int] = list(range(max_blocks))
        self.blocks: dict[int, KVBlock] = {
            i: KVBlock(block_id=i, block_size=block_size)
            for i in range(max_blocks)
        }

        # Sequence -> list of block IDs (block table)
        self.block_tables: dict[str, list[int]] = {}

    def allocate_sequence(self, seq_id: str) -> bool:
        # Allocate first block for a new sequence
        if not self.free_blocks:
            return False  # OOM — need to preempt another sequence
        block_id = self.free_blocks.pop()
        self.blocks[block_id].ref_count = 1
        self.block_tables[seq_id] = [block_id]
        return True

    def append_token(self, seq_id: str) -> bool:
        # Add a token to a sequence's KV cache
        # If current block is full, allocate a new one
        table = self.block_tables[seq_id]
        current_block = self.blocks[table[-1]]

        if current_block.is_full:
            if not self.free_blocks:
                return False  # Need to evict or preempt
            new_block_id = self.free_blocks.pop()
            self.blocks[new_block_id].ref_count = 1
            table.append(new_block_id)
            current_block = self.blocks[new_block_id]

        current_block.num_filled += 1
        return True

    def fork_sequence(self, parent_id: str, child_id: str):
        # Copy-on-write fork for beam search / speculative decoding
        # Share blocks between parent and child (just increment ref counts)
        # However, when either sequence writes to a shared block,
        # we must copy it first (copy-on-write)
        # This is critical because beam search creates many branches

        parent_table = self.block_tables[parent_id]
        child_table = list(parent_table)  # copy block ID list

        for block_id in child_table:
            self.blocks[block_id].ref_count += 1

        self.block_tables[child_id] = child_table

    def free_sequence(self, seq_id: str):
        # Release all blocks for a completed/cancelled sequence
        if seq_id not in self.block_tables:
            return
        for block_id in self.block_tables[seq_id]:
            self.blocks[block_id].ref_count -= 1
            if self.blocks[block_id].ref_count == 0:
                self.blocks[block_id].num_filled = 0
                self.free_blocks.append(block_id)
        del self.block_tables[seq_id]

    def get_utilization(self) -> dict:
        used = self.max_blocks - len(self.free_blocks)
        return {
            "total_blocks": self.max_blocks,
            "used_blocks": used,
            "free_blocks": len(self.free_blocks),
            "utilization": used / self.max_blocks,
            "active_sequences": len(self.block_tables),
        }
```

### Continuous Batching and Scheduling

**Continuous batching** (iteration-level scheduling) allows new requests to join a batch at every decode step, rather than waiting for the entire batch to complete. This dramatically improves throughput **because** different sequences finish at different times.

```python
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

class SequenceStatus(Enum):
    WAITING = "waiting"      # in queue, not yet scheduled
    RUNNING = "running"      # actively generating tokens
    PREEMPTED = "preempted"  # evicted from GPU, can be resumed
    FINISHED = "finished"    # hit EOS or max_tokens

@dataclass
class SequenceGroup:
    request_id: str
    prompt_tokens: list[int]
    generated_tokens: list[int] = field(default_factory=list)
    status: SequenceStatus = SequenceStatus.WAITING
    max_tokens: int = 512
    arrival_time: float = 0.0
    first_token_time: Optional[float] = None

    @property
    def num_total_tokens(self) -> int:
        return len(self.prompt_tokens) + len(self.generated_tokens)

    @property
    def is_prefill(self) -> bool:
        return len(self.generated_tokens) == 0

class ContinuousBatchScheduler:
    # Schedules sequences for continuous batching
    # Therefore, GPU is never idle waiting for a batch to complete
    # Common mistake: static batching where short sequences waste GPU cycles
    # waiting for the longest sequence in the batch

    def __init__(
        self,
        kv_cache: PagedKVCacheManager,
        max_running: int = 256,
        max_prefill_tokens: int = 4096,
    ):
        self.kv_cache = kv_cache
        self.max_running = max_running
        self.max_prefill_tokens = max_prefill_tokens
        self.waiting: list[SequenceGroup] = []
        self.running: list[SequenceGroup] = []
        self.preempted: list[SequenceGroup] = []

    def schedule(self) -> dict:
        # Called every iteration to determine what to run
        # Priority: 1) Continue running sequences, 2) Resume preempted, 3) Start new

        scheduled_prefill = []
        scheduled_decode = []
        preempt_list = []

        # Step 1: Try to continue all running sequences
        remaining_running = []
        for seq in self.running:
            can_continue = self.kv_cache.append_token(seq.request_id)
            if can_continue:
                scheduled_decode.append(seq)
                remaining_running.append(seq)
            else:
                # Cannot allocate KV block — must preempt
                # Best practice: preempt most recently arrived (LCFS)
                # because they have used less compute
                preempt_list.append(seq)
        self.running = remaining_running

        # Step 2: Preempt to free memory if needed
        for seq in reversed(preempt_list):
            seq.status = SequenceStatus.PREEMPTED
            self.kv_cache.free_sequence(seq.request_id)
            self.preempted.append(seq)

        # Step 3: Resume preempted sequences (they have priority)
        while self.preempted and len(self.running) < self.max_running:
            seq = self.preempted.pop(0)
            if self.kv_cache.allocate_sequence(seq.request_id):
                seq.status = SequenceStatus.RUNNING
                scheduled_prefill.append(seq)  # Must re-prefill
                self.running.append(seq)
            else:
                self.preempted.insert(0, seq)
                break

        # Step 4: Start new sequences from waiting queue
        prefill_budget = self.max_prefill_tokens
        while self.waiting and len(self.running) < self.max_running:
            seq = self.waiting[0]
            if len(seq.prompt_tokens) > prefill_budget:
                break  # Would exceed prefill budget
            if not self.kv_cache.allocate_sequence(seq.request_id):
                break  # No memory

            self.waiting.pop(0)
            seq.status = SequenceStatus.RUNNING
            scheduled_prefill.append(seq)
            self.running.append(seq)
            prefill_budget -= len(seq.prompt_tokens)

        return {
            "prefill": scheduled_prefill,
            "decode": scheduled_decode,
            "num_running": len(self.running),
            "num_waiting": len(self.waiting),
            "num_preempted": len(self.preempted),
            "kv_utilization": self.kv_cache.get_utilization(),
        }

    def process_outputs(self, outputs: list[tuple[str, int, bool]]):
        # Process generated tokens, mark finished sequences
        finished = set()
        for request_id, token_id, is_eos in outputs:
            seq = next((s for s in self.running if s.request_id == request_id), None)
            if seq is None:
                continue
            seq.generated_tokens.append(token_id)
            if is_eos or len(seq.generated_tokens) >= seq.max_tokens:
                seq.status = SequenceStatus.FINISHED
                finished.add(request_id)

        # Free finished sequences
        for rid in finished:
            self.kv_cache.free_sequence(rid)
        self.running = [s for s in self.running if s.request_id not in finished]
```

### Key Takeaways

- **Dynamic batching** amortizes GPU overhead — the **trade-off** is between throughput (larger batches) and latency (waiting for batch to fill)
- **PagedAttention** manages KV-cache like virtual memory pages — **because** it eliminates fragmentation from variable-length sequences, improving GPU memory utilization by 2-4x
- **Continuous batching** allows new requests every decode step — a **common mistake** is using static batching where completed sequences waste GPU cycles
- **Best practice**: pre-allocate GPU memory pools and use copy-on-write for beam search — **however** this adds implementation complexity
- **Pitfall**: not setting a prefill token budget — long prompts can starve decode steps, spiking latency for in-flight requests
- **Therefore**, production serving requires careful orchestration of batching, memory management, and scheduling — frameworks like vLLM, TensorRT-LLM, and SGLang handle this complexity
"""
    ),
    (
        "model-serving/model-quantization-deployment",
        r"""Explain model quantization techniques for production deployment including post-training quantization, GPTQ, AWQ, quantization-aware training, mixed-precision strategies, and benchmarking quantized model quality versus speed trade-offs.""",
        r"""## Model Quantization for Deployment: PTQ, GPTQ, AWQ, and Mixed-Precision Strategies

**Model quantization** reduces model weights and activations from higher precision (FP32/FP16) to lower precision (INT8/INT4), dramatically reducing memory footprint and increasing inference speed. **However**, quantization is not free — it introduces approximation errors that can degrade model quality. The **trade-off** between compression ratio and accuracy loss drives quantization strategy selection.

### Post-Training Quantization (PTQ) Fundamentals

The simplest approach: quantize a pre-trained model without further training. **Because** PTQ requires no training data or GPU time for fine-tuning, it's the fastest path to deployment.

```python
import numpy as np
from dataclasses import dataclass
from typing import Optional, Literal
from enum import Enum

class QuantType(Enum):
    SYMMETRIC = "symmetric"    # range: [-max, max]
    ASYMMETRIC = "asymmetric"  # range: [min, max]

@dataclass
class QuantConfig:
    bits: int = 8
    group_size: int = 128   # quantize in groups for finer granularity
    quant_type: QuantType = QuantType.SYMMETRIC
    # Per-channel vs per-tensor quantization
    # Best practice: per-channel for weights, per-tensor for activations
    per_channel: bool = True

class Quantizer:
    # Implements basic quantization and dequantization
    # Common mistake: using per-tensor quantization for weights
    # because different channels have vastly different ranges

    def __init__(self, config: QuantConfig):
        self.config = config
        self.qmin = -(2 ** (config.bits - 1))
        self.qmax = 2 ** (config.bits - 1) - 1

    def compute_scale_zero(
        self, tensor: np.ndarray, axis: Optional[int] = None
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.config.quant_type == QuantType.SYMMETRIC:
            # Symmetric: zero_point = 0, scale = max(|tensor|) / qmax
            # Pitfall: outliers in a single channel inflate the scale for all values
            abs_max = np.abs(tensor).max(axis=axis, keepdims=True)
            scale = abs_max / self.qmax
            scale = np.where(scale == 0, 1.0, scale)  # avoid div by zero
            zero_point = np.zeros_like(scale)
        else:
            # Asymmetric: uses full range [qmin, qmax]
            # Therefore captures the actual min/max distribution better
            t_min = tensor.min(axis=axis, keepdims=True)
            t_max = tensor.max(axis=axis, keepdims=True)
            scale = (t_max - t_min) / (self.qmax - self.qmin)
            scale = np.where(scale == 0, 1.0, scale)
            zero_point = np.round(self.qmin - t_min / scale)

        return scale, zero_point

    def quantize(self, tensor: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # Quantize with group-wise granularity
        original_shape = tensor.shape

        if self.config.group_size > 0 and len(tensor.shape) == 2:
            # Reshape into groups along the last dimension
            rows, cols = tensor.shape
            n_groups = cols // self.config.group_size
            if cols % self.config.group_size != 0:
                # Pad to group size
                pad_size = self.config.group_size - (cols % self.config.group_size)
                tensor = np.pad(tensor, ((0, 0), (0, pad_size)))
                cols = tensor.shape[1]
                n_groups = cols // self.config.group_size

            grouped = tensor.reshape(rows, n_groups, self.config.group_size)
            scale, zero_point = self.compute_scale_zero(grouped, axis=2)
            quantized = np.clip(
                np.round(grouped / scale + zero_point),
                self.qmin, self.qmax
            ).astype(np.int8)

            return quantized, scale, zero_point

        axis = 0 if self.config.per_channel else None
        scale, zero_point = self.compute_scale_zero(tensor, axis=axis)
        quantized = np.clip(
            np.round(tensor / scale + zero_point),
            self.qmin, self.qmax
        ).astype(np.int8)

        return quantized, scale, zero_point

    def dequantize(
        self, quantized: np.ndarray, scale: np.ndarray, zero_point: np.ndarray
    ) -> np.ndarray:
        return (quantized.astype(np.float32) - zero_point) * scale
```

### GPTQ: Optimal Weight Quantization

**GPTQ** (Generative Pre-Training Quantization) uses second-order information (Hessian) to find optimal quantized weights that minimize the output error. **Therefore**, it achieves better quality than naive round-to-nearest at the same bit width.

```python
class GPTQQuantizer:
    # GPTQ quantizes one layer at a time using calibration data
    # It minimizes: ||WX - Q(W)X||^2 where Q is the quantization function
    # Key insight: quantize columns sequentially, updating remaining columns
    # to compensate for quantization error (Optimal Brain Quantization)

    def __init__(self, bits: int = 4, group_size: int = 128, damp_percent: float = 0.01):
        self.bits = bits
        self.group_size = group_size
        self.damp_percent = damp_percent  # damping for numerical stability

    def quantize_layer(
        self,
        weight: np.ndarray,       # shape: (out_features, in_features)
        hessian: np.ndarray,      # shape: (in_features, in_features)
        block_size: int = 128,    # process columns in blocks
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # GPTQ algorithm: sequential quantization with error compensation
        # However, processing one column at a time is slow
        # Best practice: use block-wise quantization (block_size columns at once)

        rows, cols = weight.shape
        W = weight.copy().astype(np.float64)

        # Add damping to Hessian diagonal for numerical stability
        # Pitfall: insufficient damping causes NaN/Inf in Cholesky
        damp = self.damp_percent * np.mean(np.diag(hessian))
        hessian_damped = hessian + damp * np.eye(cols)

        # Cholesky decomposition of inverse Hessian
        # H_inv gives us the sensitivity of each weight
        try:
            L = np.linalg.cholesky(hessian_damped)
            H_inv = np.linalg.inv(L).T
        except np.linalg.LinAlgError:
            # Fallback: use diagonal approximation
            # Common mistake: not handling non-PD Hessian
            H_inv = np.diag(1.0 / (np.diag(hessian_damped) + 1e-8))

        quantized = np.zeros_like(W, dtype=np.int8)
        scales = np.zeros((rows, cols // self.group_size), dtype=np.float32)
        zeros = np.zeros_like(scales)

        for block_start in range(0, cols, block_size):
            block_end = min(block_start + block_size, cols)

            for col in range(block_start, block_end):
                group_idx = col // self.group_size
                w_col = W[:, col]

                # Quantize this column
                q_col, s, z = self._quantize_column(w_col, group_idx, scales, zeros, rows)
                quantized[:, col] = q_col

                # Dequantize to get quantization error
                w_hat = (q_col.astype(np.float64) - z) * s
                error = w_col - w_hat

                # Compensate remaining columns using Hessian information
                # This is the key GPTQ insight: spread error to unquantized columns
                if col < cols - 1:
                    h_diag = H_inv[col, col]
                    if h_diag > 0:
                        compensation = np.outer(error, H_inv[col, col+1:]) / h_diag
                        W[:, col+1:] += compensation

        return quantized, scales, zeros

    def _quantize_column(self, col, group_idx, scales, zeros, rows):
        # Round-to-nearest with clipping
        qmax = 2 ** self.bits - 1
        col_max = np.abs(col).max()
        scale = col_max / qmax if col_max > 0 else 1.0
        q = np.clip(np.round(col / scale), 0, qmax).astype(np.int8)
        scales[:, group_idx] = scale
        return q, scale, 0.0

    def collect_hessian(self, model_layer, calibration_data: list[np.ndarray]) -> np.ndarray:
        # Collect Hessian from calibration data
        # H = 2 * X^T X where X is the input activations
        # Trade-off: more calibration samples = better Hessian estimate
        # but diminishing returns after ~128 samples
        n_samples = 0
        H = None
        for batch in calibration_data:
            # batch shape: (seq_len, hidden_dim)
            if H is None:
                H = np.zeros((batch.shape[1], batch.shape[1]))
            H += batch.T @ batch
            n_samples += batch.shape[0]
        return (2.0 / n_samples) * H
```

### AWQ: Activation-Aware Weight Quantization

**AWQ** takes a different approach: instead of using Hessian information, it identifies **salient weight channels** based on activation magnitudes and applies per-channel scaling to protect them before quantization.

```python
class AWQQuantizer:
    # AWQ: Activation-Aware Weight Quantization
    # Key insight: 1% of weight channels are critical (high activation magnitude)
    # Protecting these channels via scaling preserves quality
    # Therefore, AWQ achieves GPTQ-level quality with simpler implementation

    def __init__(self, bits: int = 4, group_size: int = 128):
        self.bits = bits
        self.group_size = group_size

    def find_optimal_scales(
        self,
        weight: np.ndarray,
        activation_stats: np.ndarray,  # mean |activation| per channel
        n_grid: int = 20,
    ) -> np.ndarray:
        # Search for optimal per-channel scales that minimize quantization error
        # Best practice: grid search over scale factors for each channel

        best_scales = np.ones(weight.shape[1])
        best_error = float("inf")

        # Normalize activation magnitudes to [0, 1]
        act_norm = activation_stats / (activation_stats.max() + 1e-8)

        # Grid search: scale = act_norm ^ alpha, where alpha in [0, 1]
        # Higher alpha = more protection for salient channels
        for alpha_idx in range(n_grid + 1):
            alpha = alpha_idx / n_grid
            scales = act_norm ** alpha

            # Apply scales: W_scaled = W * diag(scales)
            # Then quantize W_scaled
            # After dequantization: W_approx = dequant(Q(W_scaled)) / diag(scales)
            scaled_weight = weight * scales[np.newaxis, :]
            quantized = self._round_to_nearest(scaled_weight)
            dequantized = quantized / scales[np.newaxis, :]

            error = np.mean((weight - dequantized) ** 2)
            if error < best_error:
                best_error = error
                best_scales = scales.copy()

        return best_scales

    def quantize_with_scales(
        self,
        weight: np.ndarray,
        scales: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # Apply activation-aware scales before quantization
        # This effectively reduces quantization error on important channels
        # However, scales must be fused into adjacent layers for efficiency
        # Common mistake: applying scales at runtime (adds latency)

        scaled_weight = weight * scales[np.newaxis, :]
        quantized, q_scales, q_zeros = self._group_quantize(scaled_weight)
        return quantized, q_scales, q_zeros, scales

    def _round_to_nearest(self, tensor: np.ndarray) -> np.ndarray:
        qmax = 2 ** self.bits - 1
        scale = tensor.max() / qmax if tensor.max() > 0 else 1.0
        return np.round(np.clip(tensor / scale, 0, qmax)) * scale

    def _group_quantize(self, weight: np.ndarray):
        rows, cols = weight.shape
        qmax = 2 ** self.bits - 1
        n_groups = cols // self.group_size

        quantized = np.zeros_like(weight, dtype=np.int8)
        scales = np.zeros((rows, n_groups))
        zeros = np.zeros_like(scales)

        for g in range(n_groups):
            start = g * self.group_size
            end = start + self.group_size
            group = weight[:, start:end]

            g_min = group.min(axis=1, keepdims=True)
            g_max = group.max(axis=1, keepdims=True)
            scale = (g_max - g_min) / qmax
            scale = np.where(scale == 0, 1.0, scale)
            zero = np.round(-g_min / scale)

            quantized[:, start:end] = np.clip(
                np.round(group / scale + zero), 0, qmax
            ).astype(np.int8)
            scales[:, g] = scale.squeeze()
            zeros[:, g] = zero.squeeze()

        return quantized, scales, zeros

# Benchmarking quantized models
class QuantBenchmark:
    def compare_methods(
        self,
        original_weight: np.ndarray,
        calibration_data: list[np.ndarray],
    ) -> dict:
        # Compare quantization methods on quality and speed
        results = {}

        # PTQ (naive round-to-nearest)
        ptq = Quantizer(QuantConfig(bits=4, group_size=128))
        q, s, z = ptq.quantize(original_weight)
        deq = ptq.dequantize(q, s, z)
        results["ptq"] = {
            "mse": float(np.mean((original_weight - deq) ** 2)),
            "max_error": float(np.max(np.abs(original_weight - deq))),
            "compression": original_weight.nbytes / q.nbytes,
        }

        # GPTQ
        gptq = GPTQQuantizer(bits=4, group_size=128)
        hessian = gptq.collect_hessian(None, calibration_data)
        q_gptq, s_gptq, z_gptq = gptq.quantize_layer(original_weight, hessian)
        # ... compute metrics similarly

        return results
```

### Key Takeaways

- **Post-training quantization** is the simplest path — **however** naive round-to-nearest at 4-bit degrades quality significantly for LLMs
- **GPTQ** uses Hessian information to minimize quantization error — **because** it compensates remaining weights for each quantized column, quality is much better
- **AWQ** protects salient channels via activation-aware scaling — the **trade-off** is simpler implementation vs. slightly less optimal than GPTQ for some models
- **Common mistake**: quantizing without calibration data — always use representative samples for calibration
- **Best practice**: benchmark perplexity/accuracy at each quantization level and choose the most aggressive quantization that stays within your quality budget
- **Pitfall**: assuming quantization speedup is automatic — you need hardware-optimized INT4/INT8 kernels (CUTLASS, Marlin) to actually realize the speed gains
- **Therefore**, production quantization is a pipeline: calibrate → quantize → benchmark quality → benchmark speed → deploy
"""
    ),
    (
        "model-serving/feature-store-patterns",
        r"""Explain feature store architecture for ML systems including online and offline stores, feature computation pipelines, point-in-time correctness, feature serving latency optimization, and integration patterns with training and inference pipelines.""",
        r"""## Feature Store Architecture: Online/Offline Stores, Point-in-Time Correctness, and Serving

A **feature store** is the bridge between data engineering and ML, providing a centralized system for defining, computing, storing, and serving features consistently across training and inference. **However**, the apparent simplicity of "store features, serve them" masks deep challenges around consistency, latency, and the training-serving skew problem. **Because** feature definitions drift between training notebooks and production serving code, models degrade silently — the feature store exists to eliminate this gap.

### Core Architecture: Offline and Online Stores

The **dual-store architecture** is fundamental: an **offline store** for batch access during training (high throughput, high latency) and an **online store** for real-time inference (low latency, point lookups).

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import time

class ValueType(Enum):
    INT64 = "int64"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    FLOAT_ARRAY = "float_array"
    TIMESTAMP = "timestamp"

@dataclass
class FeatureDefinition:
    name: str
    entity_key: str           # e.g., "user_id", "item_id"
    value_type: ValueType
    description: str
    owner: str                # team that owns this feature
    tags: list[str] = field(default_factory=list)
    # TTL for online store — stale features should be treated as missing
    # Best practice: set TTL based on feature freshness requirements
    online_ttl: timedelta = timedelta(hours=24)
    # Computation schedule for batch features
    batch_schedule: Optional[str] = None  # cron expression
    # Streaming source for real-time features
    stream_source: Optional[str] = None  # e.g., Kafka topic

@dataclass
class FeatureView:
    # Groups related features computed from the same source
    # Common mistake: one feature per view — group by entity and source
    name: str
    entity_key: str
    features: list[FeatureDefinition]
    source: str  # table, topic, or transformation
    # Point-in-time join key — critical for training correctness
    timestamp_field: str = "event_timestamp"

class OnlineStore:
    # Low-latency key-value store for serving (Redis, DynamoDB, Bigtable)
    # Trade-off: Redis is fastest (sub-ms) but limited by memory
    # DynamoDB scales better but has higher latency (~5ms)

    def __init__(self, redis_client):
        self.redis = redis_client

    async def write_features(
        self,
        entity_key: str,
        entity_value: str,
        features: dict[str, Any],
        timestamp: datetime,
        ttl_seconds: int = 86400,
    ):
        # Store as hash with timestamp for freshness checking
        key = f"features:{entity_key}:{entity_value}"
        pipe = self.redis.pipeline()
        pipe.hset(key, mapping={
            **{f"f:{k}": self._serialize(v) for k, v in features.items()},
            "_ts": timestamp.isoformat(),
        })
        pipe.expire(key, ttl_seconds)
        await pipe.execute()

    async def get_features(
        self,
        entity_key: str,
        entity_value: str,
        feature_names: list[str],
        max_age: Optional[timedelta] = None,
    ) -> dict[str, Any]:
        key = f"features:{entity_key}:{entity_value}"
        fields = [f"f:{name}" for name in feature_names] + ["_ts"]

        values = await self.redis.hmget(key, fields)

        if all(v is None for v in values):
            return {name: None for name in feature_names}

        # Check freshness
        ts_raw = values[-1]
        if ts_raw and max_age:
            ts = datetime.fromisoformat(ts_raw.decode())
            if datetime.utcnow() - ts > max_age:
                # Pitfall: serving stale features silently
                # Best practice: return None and let model use default
                return {name: None for name in feature_names}

        result = {}
        for i, name in enumerate(feature_names):
            raw = values[i]
            result[name] = self._deserialize(raw) if raw else None

        return result

    def _serialize(self, value: Any) -> bytes:
        import json
        return json.dumps(value).encode()

    def _deserialize(self, raw: bytes) -> Any:
        import json
        return json.loads(raw.decode())
```

### Point-in-Time Correctness

**Point-in-time correctness** prevents data leakage during training by ensuring that features used for each training example only include data available **before** the event timestamp. This is the most critical correctness property of a feature store.

```python
import pandas as pd
from typing import Optional

class PointInTimeJoiner:
    # Joins features to events with temporal correctness
    # Common mistake: simple left join without timestamp filtering
    # because it leaks future data into training examples
    # This is the #1 cause of "model works in training but fails in production"

    def join(
        self,
        events: pd.DataFrame,        # columns: entity_id, event_timestamp, label
        feature_table: pd.DataFrame,  # columns: entity_id, feature_timestamp, features...
        entity_key: str = "entity_id",
        event_ts: str = "event_timestamp",
        feature_ts: str = "feature_timestamp",
        max_age: Optional[timedelta] = None,
    ) -> pd.DataFrame:
        # For each event, find the most recent feature row BEFORE the event
        # Therefore, we never use data from the future

        # Sort both by timestamp
        events = events.sort_values(event_ts)
        feature_table = feature_table.sort_values(feature_ts)

        # Use pd.merge_asof for efficient point-in-time join
        # This is an O(n log n) operation, much better than nested loops
        result = pd.merge_asof(
            events,
            feature_table,
            left_on=event_ts,
            right_on=feature_ts,
            by=entity_key,
            direction="backward",  # only look at past features
            tolerance=max_age,     # None for no max age
        )

        # Check for feature staleness
        if max_age:
            staleness = result[event_ts] - result[feature_ts]
            stale_mask = staleness > max_age
            feature_cols = [c for c in feature_table.columns if c not in [entity_key, feature_ts]]
            result.loc[stale_mask, feature_cols] = None

        return result

    def validate_no_leakage(
        self,
        result: pd.DataFrame,
        event_ts: str = "event_timestamp",
        feature_ts: str = "feature_timestamp",
    ) -> bool:
        # Verify that ALL feature timestamps are before event timestamps
        # Best practice: run this check in CI/CD pipeline for feature changes
        valid_mask = result[feature_ts] <= result[event_ts]
        null_mask = result[feature_ts].isna()  # nulls are OK (missing features)
        return bool((valid_mask | null_mask).all())

class FeatureComputationPipeline:
    # Computes features from raw data with versioning
    # Trade-off: pre-computed features are faster but stale
    # on-demand features are fresh but slow

    def __init__(self, offline_store, online_store):
        self.offline = offline_store
        self.online = online_store

    async def materialize_batch(
        self,
        feature_view: FeatureView,
        start_time: datetime,
        end_time: datetime,
    ):
        # Compute features and write to both stores
        # Offline: append to feature table (for training)
        # Online: upsert latest values (for serving)

        # Step 1: Read raw data for the time window
        raw_data = await self.offline.read_source(
            feature_view.source,
            start_time,
            end_time,
        )

        # Step 2: Compute features using registered transformations
        # However, transformations must be deterministic and idempotent
        features = self._compute_features(raw_data, feature_view)

        # Step 3: Write to offline store (append)
        await self.offline.write_features(feature_view.name, features)

        # Step 4: Write latest values to online store
        # Only the most recent row per entity goes to online store
        latest = features.sort_values(feature_view.timestamp_field).groupby(
            feature_view.entity_key
        ).last()

        for entity_id, row in latest.iterrows():
            await self.online.write_features(
                feature_view.entity_key,
                str(entity_id),
                row.to_dict(),
                timestamp=row[feature_view.timestamp_field],
                ttl_seconds=int(feature_view.features[0].online_ttl.total_seconds()),
            )

    def _compute_features(self, raw_data: pd.DataFrame, view: FeatureView) -> pd.DataFrame:
        # Apply registered transformations
        # Pitfall: non-deterministic transformations (random, current_time)
        # because they create training-serving skew
        return raw_data  # placeholder for actual transformation logic
```

### Feature Serving Optimization

```python
class FeatureServer:
    # Optimized feature serving for low-latency inference
    # Best practice: batch feature lookups and use caching

    def __init__(self, online_store: OnlineStore, cache_ttl: int = 60):
        self.store = online_store
        self.cache = {}  # in-process cache for hot features
        self.cache_ttl = cache_ttl
        self.metrics = {"cache_hits": 0, "cache_misses": 0, "latency_ms": []}

    async def get_features_for_prediction(
        self,
        entity_keys: dict[str, str],  # {"user_id": "123", "item_id": "456"}
        feature_refs: list[str],       # ["user_features:age", "item_features:price"]
    ) -> dict[str, Any]:
        start = time.monotonic()

        # Group features by entity for batched lookups
        # Therefore, we minimize round-trips to the online store
        by_entity = {}
        for ref in feature_refs:
            view_name, feat_name = ref.split(":")
            entity_key = self._get_entity_key(view_name)
            entity_value = entity_keys.get(entity_key)
            if entity_value:
                by_entity.setdefault((entity_key, entity_value), []).append(feat_name)

        # Parallel lookups across entities
        import asyncio
        tasks = []
        for (ek, ev), feat_names in by_entity.items():
            tasks.append(self._get_with_cache(ek, ev, feat_names))

        results_list = await asyncio.gather(*tasks)

        # Merge results
        merged = {}
        for result in results_list:
            merged.update(result)

        latency = (time.monotonic() - start) * 1000
        self.metrics["latency_ms"].append(latency)
        return merged

    async def _get_with_cache(self, entity_key, entity_value, feature_names):
        cache_key = f"{entity_key}:{entity_value}"
        cached = self.cache.get(cache_key)
        if cached and (time.monotonic() - cached["ts"]) < self.cache_ttl:
            self.metrics["cache_hits"] += 1
            return {k: cached["data"].get(k) for k in feature_names}

        self.metrics["cache_misses"] += 1
        data = await self.store.get_features(entity_key, entity_value, feature_names)
        self.cache[cache_key] = {"data": data, "ts": time.monotonic()}
        return data

    def _get_entity_key(self, view_name: str) -> str:
        # Map feature view to entity key
        view_map = {
            "user_features": "user_id",
            "item_features": "item_id",
            "session_features": "session_id",
        }
        return view_map.get(view_name, "entity_id")
```

### Key Takeaways

- **Dual-store architecture** (offline + online) is essential — **because** training needs high-throughput batch access while inference needs low-latency point lookups
- **Point-in-time correctness** prevents data leakage — a **common mistake** is joining features without temporal filtering, which inflates training metrics but fails in production
- **Feature freshness** must be monitored with TTLs — **however** setting TTLs too aggressively causes excessive missing features
- **Best practice**: register all feature transformations centrally to eliminate training-serving skew — the same code must compute features for both training and serving
- **Pitfall**: non-deterministic transformations (random seeds, current timestamps) create subtle skew that's hard to debug
- **Trade-off**: pre-computed features are faster but may be stale; on-demand computation is fresh but adds serving latency — **therefore** choose based on each feature's freshness requirements
"""
    ),
]
