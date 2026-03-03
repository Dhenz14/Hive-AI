"""
Train HiveAI LoRA v2 on Qwen3.5-35B-A3B.

One-command training:
    python scripts/train_v2.py

What it does:
    1. Loads premium pairs (quality >= 0.75) from hiveai.db export
    2. Trains LoRA adapter on Qwen3.5-35B-A3B (attention-only, r=16)
       Uses standard PEFT (not Unsloth) — Unsloth's patching conflicts with
       accelerate's device hooks when device_map='auto' CPU offload is needed.
    3. Saves adapter to loras/v2/
    4. Converts adapter to GGUF for llama-server
"""
import faulthandler
import logging
import os
import subprocess
import sys
import time

# Force unbuffered stdout/stderr so log output appears immediately
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

faulthandler.enable(file=sys.stderr, all_threads=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    stream=sys.stderr,  # explicit stderr so 2>&1 captures it
)
# Make sure transformers logger also outputs at INFO level
logging.getLogger("transformers").setLevel(logging.INFO)
logging.getLogger("trl").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINING_JSONL = os.path.join(PROJECT_ROOT, "loras", "training_data", "v1_6.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "loras", "v2")
BASE_MODEL_LOCAL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "hf")
BASE_GGUF = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b", "Qwen3.5-35B-A3B-Q4_K_M.gguf")
CONVERT_SCRIPT = r"C:\Users\theyc\llama.cpp\convert_lora_to_gguf.py"
ADAPTER_GGUF = os.path.join(OUTPUT_DIR, "hiveai-v2-lora.gguf")

# HuggingFace model ID (fallback if local path doesn't exist)
HF_MODEL_ID = "unsloth/Qwen3.5-35B-A3B"


def check_prerequisites():
    """Verify all files and dependencies are ready."""
    errors = []

    if not os.path.exists(TRAINING_JSONL):
        errors.append(f"Training data not found: {TRAINING_JSONL}")

    # Check base model
    model_path = BASE_MODEL_LOCAL if os.path.isdir(BASE_MODEL_LOCAL) else HF_MODEL_ID
    safetensors = [f for f in os.listdir(BASE_MODEL_LOCAL) if f.endswith(".safetensors")] if os.path.isdir(BASE_MODEL_LOCAL) else []
    if os.path.isdir(BASE_MODEL_LOCAL) and len(safetensors) < 14:
        errors.append(f"Base model incomplete: only {len(safetensors)}/14 safetensor shards in {BASE_MODEL_LOCAL}")

    # Check GGUF for post-training conversion
    if not os.path.exists(BASE_GGUF):
        logger.warning(f"Base GGUF not found yet: {BASE_GGUF} (needed for llama-server, not for training)")

    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning(f"LoRA converter not found: {CONVERT_SCRIPT} (will skip GGUF conversion)")

    try:
        import peft  # noqa: F401
    except ImportError:
        errors.append("peft not installed. Run: pip install peft")

    if errors:
        for e in errors:
            logger.error(f"BLOCKER: {e}")
        sys.exit(1)

    # Validate training data quality before committing to a multi-hour run
    if os.path.exists(TRAINING_JSONL):
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from hiveai.lora.exporter import validate_export
            validation = validate_export(TRAINING_JSONL)
            total = validation.get("total", 0)
            valid = validation.get("valid", 0)
            truncated = validation.get("truncated_code", 0)
            dupes = validation.get("duplicates", 0)
            logger.info(
                f"Training data validated: {valid}/{total} valid, "
                f"{truncated} truncated code, {dupes} duplicates"
            )
            if total > 0 and truncated / total > 0.10:
                logger.warning(f"WARNING: {truncated}/{total} ({truncated/total*100:.1f}%) have truncated code blocks!")
            if total > 0 and dupes / total > 0.20:
                logger.warning(f"WARNING: {dupes}/{total} ({dupes/total*100:.1f}%) are duplicates!")
        except Exception as e:
            logger.warning(f"Training data validation skipped: {e}")

    logger.info("All prerequisites OK")
    return model_path


def _fix_meta_weights(model, model_path: str, logger):
    """Post-load fix: materialize any parameters still on meta device.

    Qwen3.5-35B-A3B ships as a VL checkpoint (Qwen3_5MoeForConditionalGeneration)
    with state-dict keys like 'model.language_model.layers.X.*'.
    AutoModelForCausalLM loads Qwen3_5MoeForCausalLM, which expects 'model.layers.X.*'.
    The prefix mismatch leaves ~582 language-model params on meta.
    This function translates the checkpoint keys, looks up the device_map to find the
    target device for each param, and materializes them correctly:
      - GPU modules: quantize to 4-bit NF4 (to fit in 16GB VRAM)
      - CPU modules: keep as bf16 (Linear4bit.forward handles quant_state=None)
    """
    import torch
    import torch.nn as nn
    from safetensors import safe_open
    import bitsandbytes.functional as bnb_F
    from bitsandbytes.nn import Params4bit

    meta_params = [(n, p) for n, p in model.named_parameters() if p.device.type == "meta"]
    meta_buffers = [(n, b) for n, b in model.named_buffers() if b.device.type == "meta"]

    if not meta_params and not meta_buffers:
        logger.info("Post-load check: all weights materialized cleanly.")
        return

    logger.warning(f"Post-load: {len(meta_params)} meta params, {len(meta_buffers)} meta buffers — loading from checkpoint")
    for name, p in meta_params[:6]:
        logger.warning(f"  meta: {name}  shape={tuple(p.shape)}")

    # Key prefix translations: model key → checkpoint key.
    # Qwen3_5MoeForCausalLM uses "model.X" but VL checkpoint has "model.language_model.X".
    PREFIX_TRANSLATIONS = [
        ("model.layers.",       "model.language_model.layers."),
        ("model.embed_tokens.", "model.language_model.embed_tokens."),
        ("model.norm.",         "model.language_model.norm."),
    ]

    def translate_key(model_key):
        """Translate model key to checkpoint key. Returns None if no match."""
        for model_pfx, ckpt_pfx in PREFIX_TRANSLATIONS:
            if model_key.startswith(model_pfx):
                return ckpt_pfx + model_key[len(model_pfx):]
        return model_key  # try as-is

    # Build a TRUE key→shard mapping by scanning all shard file headers.
    # The model.safetensors.index.json is unreliable for this checkpoint
    # (expert weights like gate_up_proj are mapped to wrong shards in the index).
    #
    # We read ONLY the safetensors header (first 8 bytes = header length, then JSON)
    # WITHOUT memory-mapping the full file. safe_open() mmap's the entire shard
    # (~5GB each, 14 shards = 70GB virtual address space), which overflows Windows
    # page file. Reading just the header is ~KB per file.
    import struct
    import json as _json

    def _read_safetensors_keys(path):
        """Read tensor key names from a safetensors header without mmap'ing the file."""
        with open(path, "rb") as fh:
            hlen = struct.unpack("<Q", fh.read(8))[0]
            hdr = _json.loads(fh.read(hlen).decode("utf-8"))
        return [k for k in hdr if k != "__metadata__"]

    shard_files = sorted(
        f for f in os.listdir(model_path)
        if f.endswith(".safetensors") and "index" not in f
    )
    logger.info(f"  Scanning {len(shard_files)} shard headers (header-only, no mmap) ...")
    true_key_map = {}  # ckpt_key → shard_filename
    for shard_file in shard_files:
        shard_path = os.path.join(model_path, shard_file)
        for k in _read_safetensors_keys(shard_path):
            true_key_map[k] = shard_file
    logger.info(f"  Found {len(true_key_map)} checkpoint keys across {len(shard_files)} shards")

    # Build device lookup from hf_device_map (longest-prefix match)
    hf_device_map = getattr(model, "hf_device_map", {})
    sample = list(hf_device_map.items())[:6]
    logger.info(f"  hf_device_map ({len(hf_device_map)} entries) sample: {sample}")

    def _is_gpu(dev):
        return isinstance(dev, int) or str(dev) in ("cuda", "cuda:0", "0")

    def get_target_device(model_key):
        best_prefix, best_device = "", "cpu"
        for key, dev in hf_device_map.items():
            if (model_key == key or model_key.startswith(key + ".")) and len(key) > len(best_prefix):
                best_prefix, best_device = key, dev
        return "cuda:0" if _is_gpu(best_device) else "cpu"

    # Group: shard_file → [(model_key, ckpt_key, target_device), ...]
    shard_groups = {}
    unfixable = []
    for name, _ in meta_params + meta_buffers:
        ckpt_key = translate_key(name)
        if ckpt_key in true_key_map:
            shard = true_key_map[ckpt_key]
            tgt = get_target_device(name)
            shard_groups.setdefault(shard, []).append((name, ckpt_key, tgt))
        else:
            unfixable.append(name)

    if unfixable:
        logger.warning(f"  {len(unfixable)} meta params not in checkpoint (runtime tensors, OK)")
        for u in unfixable[:4]:
            logger.warning(f"    unfixable: {u}")

    gpu_count = sum(1 for triples in shard_groups.values() for _, _, d in triples if d == "cuda:0")
    cpu_count = sum(1 for triples in shard_groups.values() for _, _, d in triples if d == "cpu")
    logger.info(f"  Will load {gpu_count} params to GPU (Params4bit or bf16 nn.Param), {cpu_count} to CPU (bf16)")

    # ── RAM budget: skip large CPU params to avoid OOM ──
    # MoE expert tensors (gate_up_proj/down_proj) are ~1GB each × 40 layers = ~64GB in bf16.
    # With ~54GB available RAM, we can't materialize them all. Instead, register them in the
    # OffloadedWeightsLoader's index for on-demand disk loading by the offloading hooks.
    MAX_CPU_MATERIALIZE_BYTES = 100_000_000  # 100MB threshold per param
    # Build meta param shape lookup: model_key → shape
    _meta_shapes = {}
    for name, p in meta_params:
        _meta_shapes[name] = tuple(p.shape)
    for name, b in meta_buffers:
        _meta_shapes[name] = tuple(b.shape)

    # Collect loaders from AlignDevicesHook for disk-fallback registration
    from accelerate.hooks import AlignDevicesHook, SequentialHook
    from accelerate.utils import PrefixedDataset
    _all_loaders = {}  # id(loader) → loader
    for _, _mod in model.named_modules():
        _hf_hook = getattr(_mod, "_hf_hook", None)
        if _hf_hook is None:
            continue
        _hooks = _hf_hook.hooks if isinstance(_hf_hook, SequentialHook) else [_hf_hook]
        for _h in _hooks:
            if not isinstance(_h, AlignDevicesHook):
                continue
            _wmap = getattr(_h, "weights_map", None)
            if isinstance(_wmap, PrefixedDataset) and hasattr(_wmap.dataset, "index"):
                _all_loaders[id(_wmap.dataset)] = _wmap.dataset

    logger.info(f"  Found {len(_all_loaders)} loader(s) for disk-fallback registration")

    fixed = 0
    deferred = 0  # large params deferred to disk fallback
    deferred_keys = set()  # track deferred model keys (skip in tie resolution)
    for shard_file, triples in shard_groups.items():
        shard_path = os.path.join(model_path, shard_file)
        abs_shard_path = os.path.abspath(shard_path)

        # Split into materialize vs defer (disk fallback)
        to_materialize = []
        to_defer = []
        for model_key, ckpt_key, target_device in triples:
            if target_device == "cpu":
                shape = _meta_shapes.get(model_key, ())
                numel = 1
                for d in shape:
                    numel *= d
                bf16_bytes = numel * 2
                if bf16_bytes > MAX_CPU_MATERIALIZE_BYTES:
                    to_defer.append((model_key, ckpt_key, target_device))
                    continue
            to_materialize.append((model_key, ckpt_key, target_device))

        # Register deferred params in loader index for disk fallback.
        # IMPORTANT: also update loader.all_keys — __iter__ uses this cached list.
        for model_key, ckpt_key, _ in to_defer:
            disk_entry = {
                "safetensors_file": abs_shard_path,
                "weight_name": ckpt_key,
            }
            for loader in _all_loaders.values():
                if hasattr(loader, 'index') and loader.index is not None:
                    loader.index[model_key] = disk_entry
                    if model_key not in loader.all_keys:
                        loader.all_keys.append(model_key)
            deferred_keys.add(model_key)
            if deferred < 5:
                logger.info(f"  [DISK FALLBACK] {model_key} → {shard_file}:{ckpt_key}")
            deferred += 1

        if not to_materialize:
            logger.info(f"  Shard {shard_file}: 0 materialize, {len(to_defer)} deferred to disk")
            continue

        logger.info(f"  Shard {shard_file}: {len(to_materialize)} materialize, {len(to_defer)} deferred ...")
        with safe_open(shard_path, framework="pt", device="cpu") as f:
            for model_key, ckpt_key, target_device in to_materialize:
                try:
                    tensor_bf16 = f.get_tensor(ckpt_key).to(torch.bfloat16)

                    # Navigate model to parent module
                    parts = model_key.split(".")
                    mod = model
                    for part in parts[:-1]:
                        mod = getattr(mod, part)
                    attr = parts[-1]
                    existing = getattr(mod, attr, None)

                    should_quantize = (target_device == "cuda:0"
                                       and tensor_bf16.ndim >= 2
                                       and isinstance(existing, Params4bit))

                    if should_quantize:
                        w_gpu = tensor_bf16.to("cuda:0")
                        w_4bit, quant_state = bnb_F.quantize_4bit(
                            w_gpu, blocksize=64, compress_statistics=True,
                            quant_type="nf4", quant_storage=torch.uint8,
                        )
                        new_param = Params4bit(
                            w_4bit, requires_grad=False,
                            quant_state=quant_state, blocksize=64,
                            compress_statistics=True, quant_type="nf4",
                            quant_storage=torch.uint8, bnb_quantized=True,
                        )
                        if hasattr(mod, "_parameters") and attr in mod._parameters:
                            mod._parameters[attr] = new_param
                        else:
                            setattr(mod, attr, new_param)
                        if hasattr(mod, "quant_state"):
                            mod.quant_state = quant_state
                    elif target_device == "cuda:0":
                        req_grad = existing.requires_grad if isinstance(existing, nn.Parameter) else False
                        new_param = nn.Parameter(tensor_bf16.to("cuda:0"), requires_grad=req_grad)
                        if hasattr(mod, "_parameters") and attr in mod._parameters:
                            mod._parameters[attr] = new_param
                        elif hasattr(mod, "_buffers") and attr in mod._buffers:
                            mod._buffers[attr] = tensor_bf16.to("cuda:0")
                        else:
                            setattr(mod, attr, new_param)
                    else:
                        if tensor_bf16.ndim >= 2 and isinstance(existing, Params4bit):
                            new_param = Params4bit(
                                tensor_bf16.contiguous(), requires_grad=False,
                                blocksize=64, compress_statistics=True,
                                quant_type="nf4", quant_storage=torch.uint8,
                                bnb_quantized=True,
                            )
                        else:
                            req_grad = existing.requires_grad if isinstance(existing, nn.Parameter) else False
                            new_param = nn.Parameter(tensor_bf16, requires_grad=req_grad)

                        if hasattr(mod, "_parameters") and attr in mod._parameters:
                            mod._parameters[attr] = new_param
                        elif hasattr(mod, "_buffers") and attr in mod._buffers:
                            mod._buffers[attr] = tensor_bf16
                        else:
                            setattr(mod, attr, new_param)

                    fixed += 1
                except Exception as e:
                    logger.error(f"    Failed: {model_key} (ckpt={ckpt_key}): {e}")

    total = len(meta_params) + len(meta_buffers)
    logger.info(
        f"Post-load fix: {fixed}/{total - len(unfixable)} materialized, "
        f"{deferred} deferred to disk fallback (>{MAX_CPU_MATERIALIZE_BYTES/1e6:.0f}MB)"
    )

    # Tie resolution: handle expert weights that are in the index but not in any shard.
    # These are weight-tied layers (e.g., layer 12 experts share layer 39's checkpoint tensor).
    # from_pretrained skips tying them because the wrong index claims "both are present."
    # Fix: find another materialized param with the same suffix and shape and share its tensor.
    # NOTE: skip deferred params — they're intentionally on meta with disk fallback registered.
    remaining_meta = [(n, p) for n, p in model.named_parameters()
                      if p.device.type == "meta" and n not in deferred_keys]
    remaining_meta += [(n, b) for n, b in model.named_buffers()
                       if b.device.type == "meta" and n not in deferred_keys]
    if remaining_meta:
        logger.warning(f"  {len(remaining_meta)} params still on meta (excl {len(deferred_keys)} deferred) — attempting tie resolution")
        all_params = {n: p for n, p in model.named_parameters() if p.device.type != "meta"}
        tie_fixed = 0
        for name, param in remaining_meta:
            parts = name.split(".")
            # Suffix after "model.layers.X." (e.g., "mlp.experts.gate_up_proj")
            suffix = ".".join(parts[3:]) if len(parts) > 3 else ""

            # First: try exact shape match
            candidates = [
                (n, p) for n, p in all_params.items()
                if suffix and n.endswith("." + suffix) and p.shape == param.shape
            ]
            # Fallback: suffix-only match (meta shape may be wrong for fused expert tensors)
            if not candidates:
                candidates = [
                    (n, p) for n, p in all_params.items()
                    if suffix and n.endswith("." + suffix)
                ]

            if candidates:
                src_name, src_param = candidates[0]
                logger.info(f"    Tied: {name} (meta_shape={tuple(param.shape)}) <- {src_name} (shape={tuple(src_param.shape)})")
                mod = model
                for part in parts[:-1]:
                    mod = getattr(mod, part)
                attr = parts[-1]
                if hasattr(mod, "_parameters") and attr in mod._parameters:
                    mod._parameters[attr] = src_param
                elif hasattr(mod, "_buffers") and attr in mod._buffers:
                    mod._buffers[attr] = src_param.data
                else:
                    setattr(mod, attr, src_param)
                tie_fixed += 1
            else:
                logger.warning(f"    Unresolvable: {name} shape={tuple(param.shape)} — no matching materialized param found")
                tie_fixed += 0  # still unresolvable
        logger.info(f"  Tie resolution: {tie_fixed}/{len(remaining_meta)} resolved")


def _fix_wrong_shape_params(model, model_path, logger):
    """Fix model parameters that were loaded with wrong shapes due to corrupted safetensors index.

    Unlike _fix_meta_weights (which handles meta params), this function handles params that WERE
    loaded but with the WRONG tensor from a shard. For example, input_layernorm.weight may be
    loaded as (32,) because the corrupted safetensors index pointed to the wrong entry in a shard.

    These wrong-shape params don't show up as 'meta' so _fix_meta_weights skips them entirely,
    and _fix_hook_weights_map also skips them (both the model param AND the weights_map entry
    have the same wrong shape, so they appear to 'match').

    Strategy: check all decoder-layer standard norms (input_layernorm.weight,
    post_attention_layernorm.weight) — these ALWAYS have shape (hidden_size,) = (2048,).
    Anything else is a corruption from the bad safetensors index. Reload from the correct
    checkpoint key (using the true shard header scan), or zero-initialize if missing.
    """
    import torch
    import torch.nn as nn
    from safetensors import safe_open
    import struct
    import json as _json

    HIDDEN_SIZE = 2048
    # Submodule attribute names whose weight must always be (HIDDEN_SIZE,)
    TARGET_MODULE_ATTR = {"input_layernorm", "post_attention_layernorm"}

    PREFIX_TRANSLATIONS = [
        ("model.layers.",       "model.language_model.layers."),
        ("model.embed_tokens.", "model.language_model.embed_tokens."),
        ("model.norm.",         "model.language_model.norm."),
    ]

    def translate_key(model_key):
        for model_pfx, ckpt_pfx in PREFIX_TRANSLATIONS:
            if model_key.startswith(model_pfx):
                return ckpt_pfx + model_key[len(model_pfx):]
        return model_key

    hf_device_map = getattr(model, "hf_device_map", {})

    def _is_gpu(dev):
        return isinstance(dev, int) or str(dev) in ("cuda", "cuda:0", "0")

    def get_target_device(model_key):
        best_prefix, best_device = "", "cpu"
        for key, dev in hf_device_map.items():
            if (model_key == key or model_key.startswith(key + ".")) and len(key) > len(best_prefix):
                best_prefix, best_device = key, dev
        return "cuda:0" if _is_gpu(best_device) else "cpu"

    # Build true key→shard map (header-only, no mmap)
    def _read_safetensors_keys(path):
        with open(path, "rb") as fh:
            hlen = struct.unpack("<Q", fh.read(8))[0]
            hdr = _json.loads(fh.read(hlen).decode("utf-8"))
        return [k for k in hdr if k != "__metadata__"]

    shard_files = sorted(f for f in os.listdir(model_path)
                         if f.endswith(".safetensors") and "index" not in f)
    true_key_map = {}
    for sf in shard_files:
        for k in _read_safetensors_keys(os.path.join(model_path, sf)):
            true_key_map[k] = sf

    # Scan: find norm weights with wrong shape
    wrong = []  # list of (full_param_name, current_shape, module, attr)
    for module_path, mod in model.named_modules():
        # e.g., module_path = "model.layers.12.input_layernorm"
        attr = module_path.rsplit(".", 1)[-1] if "." in module_path else module_path
        if attr not in TARGET_MODULE_ATTR:
            continue
        w = getattr(mod, "weight", None)
        if w is None or w.device.type == "meta":
            continue
        if tuple(w.shape) == (HIDDEN_SIZE,):
            continue  # correct
        param_full_name = module_path + ".weight"
        wrong.append((param_full_name, tuple(w.shape), mod))
        logger.warning(f"  Wrong-shape norm: {param_full_name}: {tuple(w.shape)} (expected ({HIDDEN_SIZE},))")

    if not wrong:
        logger.info("_fix_wrong_shape_params: all decoder norm weights have correct shape")
        return

    logger.warning(f"_fix_wrong_shape_params: fixing {len(wrong)} wrongly-loaded norm weights")

    # Group by shard for efficient loading
    to_fix_shards = {}  # shard_file → [(param_full_name, ckpt_key, mod), ...]
    to_zero_init = []   # [(param_full_name, mod), ...]
    for name, _, mod in wrong:
        ckpt_key = translate_key(name)
        if ckpt_key in true_key_map:
            shard = true_key_map[ckpt_key]
            to_fix_shards.setdefault(shard, []).append((name, ckpt_key, mod))
        else:
            to_zero_init.append((name, mod))

    # Load correct weights from checkpoint shards
    for shard_file, triples in to_fix_shards.items():
        shard_path = os.path.join(model_path, shard_file)
        with safe_open(shard_path, framework="pt", device="cpu") as sf_obj:
            for name, ckpt_key, mod in triples:
                try:
                    tensor = sf_obj.get_tensor(ckpt_key).to(torch.bfloat16)
                    if tuple(tensor.shape) != (HIDDEN_SIZE,):
                        logger.warning(f"  {name}: checkpoint has {tuple(tensor.shape)}, using zero init")
                        tensor = torch.zeros(HIDDEN_SIZE, dtype=torch.bfloat16)
                    else:
                        logger.info(f"  {name}: reloaded correct ({HIDDEN_SIZE},) from {shard_file}")
                    tgt = get_target_device(name)
                    mod._parameters["weight"] = nn.Parameter(tensor.to(tgt), requires_grad=False)
                except Exception as e:
                    logger.error(f"  {name}: failed: {e}")

    # Zero-initialize for params not found in any shard
    for name, mod in to_zero_init:
        tgt = get_target_device(name)
        mod._parameters["weight"] = nn.Parameter(
            torch.zeros(HIDDEN_SIZE, dtype=torch.bfloat16).to(tgt), requires_grad=False
        )
        logger.warning(f"  {name}: not in checkpoint, zero-initialized")

    logger.info(f"_fix_wrong_shape_params: done ({len(wrong)} norms corrected)")


def _fix_hook_weights_map(model, logger):
    """Fix ALL stale/wrong-shape entries in AlignDevicesHook weights_map (OffloadedWeightsLoader).

    CRITICAL: Keys in OffloadedWeightsLoader are PRE-PEFT module paths (set by dispatch_model
    before PEFT wrapping). The hook's pre_forward calls:
        weights_map[local_param_name]
        → PrefixedDataset.__getitem__(local_param_name)
        → loader[prefix + local_param_name]
    where `prefix = module_name + "."` and `module_name` is the path from BEFORE PEFT wrapping.

    After get_peft_model(), model.named_modules() returns PEFT paths like:
        "base_model.model.model.layers.0.self_attn.q_proj.base_layer"
    But the hook's weights_map.prefix is still the pre-PEFT path:
        "model.layers.0.self_attn.q_proj."

    Old approach (BROKEN): built current_tensors using named_modules() → wrong PEFT paths
        → loader.state_dict["base_model.model.model.layers.0.self_attn.q_proj.base_layer.weight"]
        → hook looks for "model.layers.0.self_attn.q_proj.weight" → KEY MISMATCH → disk fallback

    New approach (CORRECT): for each hooked module, use hook.weights_map.prefix + param_name
        → loader.state_dict["model.layers.0.self_attn.q_proj.weight"] = correct_tensor
        → hook looks for "model.layers.0.self_attn.q_proj.weight" → found in state_dict ✓
    """
    import torch
    import bitsandbytes.functional as bnb_F
    from accelerate.hooks import AlignDevicesHook, SequentialHook
    from accelerate.utils import PrefixedDataset

    def _get_align_hooks(module):
        hook = getattr(module, "_hf_hook", None)
        if hook is None:
            return []
        hooks = hook.hooks if isinstance(hook, SequentialHook) else [hook]
        return [h for h in hooks if isinstance(h, AlignDevicesHook)]

    def _to_cpu_bf16(param):
        """Convert param to CPU bf16 for storage in the weights_map."""
        if hasattr(param, "quant_state") and param.quant_state is not None:
            bf16 = bnb_F.dequantize_4bit(
                param.data, param.quant_state,
                quant_type=getattr(param, "quant_type", "nf4"),
            ).to("cpu", dtype=torch.bfloat16)
        else:
            bf16 = param.data.to("cpu", dtype=torch.bfloat16)
        return bf16

    def _expected_shape(param):
        """Return the shape a correctly-stored weights_map entry should have."""
        if hasattr(param, "quant_state") and param.quant_state is not None:
            return tuple(param.quant_state.shape)
        return tuple(param.shape)

    # Collect all unique loaders AND all (module, hook) pairs with their prefixes.
    # The prefix is the PRE-PEFT module path set by dispatch_model — the EXACT key prefix
    # the hook uses when calling loader[prefix + param_name].
    all_loaders = {}    # id(loader) → loader object
    hooked_modules = [] # [(module, hook, prefix_str)]

    for _, mod in model.named_modules():
        for h in _get_align_hooks(mod):
            wmap = getattr(h, "weights_map", None)
            if isinstance(wmap, PrefixedDataset) and hasattr(wmap.dataset, "state_dict"):
                loader = wmap.dataset
                all_loaders[id(loader)] = loader
                hooked_modules.append((mod, h, wmap.prefix))

    if not all_loaders:
        logger.info("_fix_hook_weights_map: no OffloadedWeightsLoader found — nothing to do")
        return

    logger.info(
        f"_fix_hook_weights_map: found {len(all_loaders)} unique loader(s), "
        f"{len(hooked_modules)} hooked modules"
    )

    # Log sample keys so we can see what path format the loader uses (diagnostic)
    first_loader = next(iter(all_loaders.values()))
    sample_mem  = list(first_loader.state_dict.keys())[:5]
    sample_disk = [k for k in (first_loader.index or {}) if k not in first_loader.state_dict][:5]
    logger.info(f"  Loader sample mem keys:  {sample_mem}")
    logger.info(f"  Loader sample disk keys: {sample_disk}")
    # Log index entry format (to see if it uses safetensors_file / weight_name)
    if first_loader.index:
        sample_idx = {k: v for k, v in list(first_loader.index.items())[:3]}
        logger.info(f"  Loader index sample entries: {sample_idx}")
    # Check a few expected attention-weight keys
    attn_check_keys = [
        f"model.layers.{i}.self_attn.q_proj.weight" for i in [0, 3, 35, 39]
    ]
    for ck in attn_check_keys:
        in_sd = ck in first_loader.state_dict
        in_idx = ck in (first_loader.index or {})
        if in_sd:
            v = first_loader.state_dict[ck]
            logger.info(f"  Key {ck}: IN state_dict shape={tuple(v.shape)}")
        elif in_idx:
            logger.info(f"  Key {ck}: ONLY in index (disk fallback) — {first_loader.index[ck]}")
        else:
            logger.warning(f"  Key {ck}: NOT in state_dict OR index — will KeyError!")

    n_added = 0       # keys that were NOT in state_dict (disk-backed) and are now added
    n_fixed_meta = 0  # keys that were in state_dict as meta tensors, now fixed
    n_fixed_shape = 0 # keys that were in state_dict with wrong shape, now fixed
    n_ok = 0          # keys that were already correct, verified and re-confirmed
    n_error = 0       # keys that failed to convert

    for mod, hook, prefix in hooked_modules:
        loader = hook.weights_map.dataset
        recurse = getattr(hook, 'place_submodules', False)

        # Fix parameters (recurse to match hook's pre_forward which uses named_module_tensors)
        for param_name, param in mod.named_parameters(recurse=recurse):
            if param is None or param.device.type == "meta":
                continue
            # CRITICAL: use prefix + param_name (pre-PEFT path) as the loader key
            key = prefix + param_name
            try:
                exp_shape = _expected_shape(param)

                if key in loader.state_dict:
                    val = loader.state_dict[key]
                    if isinstance(val, torch.Tensor):
                        is_meta = val.device.type == "meta"
                        shape_ok = tuple(val.shape) == exp_shape
                        if not is_meta and shape_ok:
                            n_ok += 1
                            continue  # already correct
                        if is_meta:
                            n_fixed_meta += 1
                            logger.info(f"  wmap fix meta  {key}: {tuple(val.shape)} → {exp_shape}")
                        else:
                            n_fixed_shape += 1
                            logger.warning(f"  wmap fix shape {key}: {tuple(val.shape)} → {exp_shape}")
                else:
                    n_added += 1
                    if n_added <= 20:
                        logger.info(f"  wmap add (disk-backed) {key}: {exp_shape}")

                loader.state_dict[key] = _to_cpu_bf16(param)

            except Exception as e:
                n_error += 1
                logger.error(f"  wmap FAILED {key}: {e}")

        # Fix buffers (recurse to catch sub-module buffers like linear_attn.dt_bias)
        for buf_name, buf in mod.named_buffers(recurse=recurse):
            if buf is None or buf.device.type == "meta":
                continue
            key = prefix + buf_name
            try:
                exp_shape = tuple(buf.shape)

                if key in loader.state_dict:
                    val = loader.state_dict[key]
                    if isinstance(val, torch.Tensor):
                        is_meta = val.device.type == "meta"
                        shape_ok = tuple(val.shape) == exp_shape
                        if not is_meta and shape_ok:
                            n_ok += 1
                            continue
                        if is_meta:
                            n_fixed_meta += 1
                        else:
                            n_fixed_shape += 1
                            logger.warning(f"  wmap fix shape buf {key}: {tuple(val.shape)} → {exp_shape}")
                else:
                    n_added += 1
                    if n_added <= 20:
                        logger.info(f"  wmap add buf (disk-backed) {key}: {exp_shape}")

                loader.state_dict[key] = buf.to("cpu", dtype=torch.bfloat16)

            except Exception as e:
                n_error += 1
                logger.error(f"  wmap FAILED buf {key}: {e}")

    total_entries = sum(len(l.state_dict) for l in all_loaders.values())
    logger.info(
        f"_fix_hook_weights_map: {n_added} added (disk-backed disabled), "
        f"{n_fixed_meta} meta fixed, {n_fixed_shape} shape fixed, "
        f"{n_ok} already ok, {n_error} errors. "
        f"Total in-memory entries: {total_entries} across {len(all_loaders)} loader(s)"
    )

    # ── SHAPE GUARD ──────────────────────────────────────────────────────────
    # Build a registry mapping every loader key that a hook will ever request
    # to its expected shape.  We then patch __getitem__ so that if the loader
    # returns a tensor with the WRONG shape (e.g. (32,) key-collision from GDN
    # dt_bias/A_log), we silently return the saved correct tensor (or zeros)
    # instead.  This intercepts the corruption before it reaches any module,
    # covering ALL parameter types: Linear4bit weight, gate_up_proj, down_proj,
    # router weight, etc. — without needing per-module _old_forward wrappers.
    #
    # Key iteration mirrors exactly what AlignDevicesHook.pre_forward does:
    #   for name, _ in named_module_tensors(module, include_buffers=offload_buffers,
    #                                        recurse=place_submodules):
    #       weights = weights_map[name]   ← this is what we guard
    #
    import bitsandbytes.nn.modules as _bnb_mod_sg

    def _correct_shape_for(mod, param_name, param):
        """Return expected (non-corrupted) shape.
        For a Linear4bit module's 'weight', use out/in_features (stable even if
        _fix_meta_weights corrupted the param tensor).  For everything else, use
        the tensor's own shape — non-Linear4bit params are not touched by
        _fix_meta_weights so their meta shapes are reliable."""
        # Navigate to owner module for nested names like 'gate_up_proj.weight'
        parts = param_name.split('.')
        owner = mod
        leaf  = parts[-1]
        for part in parts[:-1]:
            owner = getattr(owner, part, None)
            if owner is None:
                return tuple(param.shape)
        if leaf == 'weight' and isinstance(owner, _bnb_mod_sg.Linear4bit):
            ei = getattr(owner, 'in_features', None)
            eo = getattr(owner, 'out_features', None)
            if ei is not None and eo is not None:
                return (eo, ei)
        return tuple(param.shape)

    # _shape_guard: full_loader_key → (expected_shape, Optional[correct_cpu_bf16])
    # 'correct_cpu_bf16' is the tensor to return when shape is wrong; None → zeros.
    _shape_guard = {}   # {str: (tuple, Optional[Tensor])}
    n_guard = 0

    for mod, hook, prefix in hooked_modules:
        loader = hook.weights_map.dataset
        recurse = getattr(hook, 'place_submodules', False)

        # Parameters (including 1D — GDN dt_bias/A_log shape corruption is a known issue)
        for pname, param in mod.named_parameters(recurse=recurse):
            if param is None:
                continue
            exp_shape = _correct_shape_for(mod, pname, param)
            full_key = prefix + pname
            correct_cpu = None
            if full_key in loader.state_dict:
                t = loader.state_dict[full_key]
                if tuple(t.shape) == exp_shape:
                    correct_cpu = t.detach().clone().cpu().to(torch.bfloat16)
                else:
                    # Fix the loader state_dict entry too
                    zero = torch.zeros(exp_shape, dtype=torch.bfloat16)
                    loader.state_dict[full_key] = zero
                    correct_cpu = zero.clone()
            _shape_guard[full_key] = (exp_shape, correct_cpu)
            n_guard += 1

        # Buffers (e.g., dt_bias, A_log in GDN — ALWAYS guard, regardless of offload_buffers.
        # During gradient-checkpoint recompute, hooks reload buffers from the loader which
        # can return wrong-shape tensors from the corrupted safetensors index.)
        for bname, buf in mod.named_buffers(recurse=recurse):
            if buf is None:
                continue
            exp_shape = tuple(buf.shape)
            full_key = prefix + bname
            if full_key not in _shape_guard:
                correct_buf_cpu = None
                if full_key in loader.state_dict:
                    t = loader.state_dict[full_key]
                    if isinstance(t, torch.Tensor) and tuple(t.shape) == exp_shape:
                        correct_buf_cpu = t.detach().clone().cpu().to(torch.bfloat16)
                elif buf.device.type != 'meta':
                    correct_buf_cpu = buf.detach().clone().cpu().to(torch.bfloat16)
                _shape_guard[full_key] = (exp_shape, correct_buf_cpu)
                n_guard += 1

    logger.info(f"Shape guard: {n_guard} keys registered across {len(all_loaders)} loader(s)")

    dt_bias_guard_keys = [k for k in _shape_guard if "dt_bias" in k or "A_log" in k]
    logger.info(f"Shape guard: {len(dt_bias_guard_keys)} dt_bias/A_log keys registered")

    # ── DIAGNOSTIC + SHAPE-GUARD __getitem__ patch ───────────────────────────
    _logged_once = set()
    for ldr in all_loaders.values():
        orig_cls_getitem = ldr.__class__.__getitem__

        def _make_logged_getitem(orig_fn, _logger, _logged, _guard):
            def _logged_getitem(self, key):
                # ── Shape guard: validate and fix before returning ──
                if key in _guard:
                    exp_shape, correct_cpu = _guard[key]
                    try:
                        result = orig_fn(self, key)
                    except KeyError:
                        _logger.warning(f"[SHAPE GUARD MISSING] {key}: not in loader → zeros{exp_shape}")
                        return torch.zeros(exp_shape, dtype=torch.bfloat16)
                    actual = tuple(result.shape)
                    if actual != exp_shape:
                        _logger.warning(
                            f"[SHAPE GUARD FIX] {key}: {actual} → "
                            f"{'correct' if correct_cpu is not None else 'zeros'}{exp_shape}"
                        )
                        if correct_cpu is not None:
                            return correct_cpu.to(result.device if result.device.type != 'meta' else 'cpu')
                        return torch.zeros(exp_shape, dtype=result.dtype,
                                           device=result.device if result.device.type != 'meta' else 'cpu')
                    return result

                return orig_fn(self, key)
            return _logged_getitem

        ldr.__class__.__getitem__ = _make_logged_getitem(orig_cls_getitem, logger, _logged_once, _shape_guard)
    logger.info("Shape guard + access-logging __getitem__ patch installed")

    # ── MMAP-FREE SAFETENSORS READER ──────────────────────────────────────────
    # CRITICAL: safe_open() uses memory-mapped I/O. On Windows, repeated mmap
    # access to large safetensors files (expert weights, 500MB-1GB each) causes
    # intermittent SIGSEGV during gradient checkpointing's backward recompute.
    # Fix: monkey-patch the OffloadedWeightsLoader to read tensor bytes via
    # regular file I/O (open/seek/read) instead of mmap. Slower but crash-proof.
    import json as _json
    import struct

    _st_header_cache = {}  # filename → {tensor_name: {"dtype": str, "shape": list, "data_offsets": [start, end]}}

    def _parse_safetensors_header(filepath):
        """Parse the safetensors file header to get tensor metadata without mmap."""
        if filepath in _st_header_cache:
            return _st_header_cache[filepath]
        with open(filepath, "rb") as f:
            header_size = struct.unpack("<Q", f.read(8))[0]
            header_bytes = f.read(header_size)
        header = _json.loads(header_bytes)
        # Remove __metadata__ if present
        header.pop("__metadata__", None)
        _st_header_cache[filepath] = header
        return header

    _DTYPE_MAP = {
        "F16": (torch.float16, 2),
        "BF16": (torch.bfloat16, 2),
        "F32": (torch.float32, 4),
        "F64": (torch.float64, 8),
        "I32": (torch.int32, 4),
        "I64": (torch.int64, 8),
        "U8": (torch.uint8, 1),
        "I8": (torch.int8, 1),
        "BOOL": (torch.bool, 1),
    }

    def _read_tensor_no_mmap(filepath, tensor_name):
        """Read a single tensor from a safetensors file using regular file I/O."""
        header = _parse_safetensors_header(filepath)
        if tensor_name not in header:
            raise KeyError(f"Tensor {tensor_name!r} not found in {filepath}")
        meta = header[tensor_name]
        dtype_str = meta["dtype"]
        shape = meta["shape"]
        start, end = meta["data_offsets"]

        torch_dtype, elem_size = _DTYPE_MAP[dtype_str]

        # Data starts after 8 bytes (header_size field) + header
        with open(filepath, "rb") as f:
            header_size = struct.unpack("<Q", f.read(8))[0]
            data_offset = 8 + header_size + start
            data_length = end - start
            f.seek(data_offset)
            raw_bytes = f.read(data_length)

        # Convert bytes → torch tensor
        tensor = torch.frombuffer(bytearray(raw_bytes), dtype=torch_dtype).reshape(shape)
        return tensor

    # Monkey-patch OffloadedWeightsLoader.__getitem__ to use mmap-free reader
    for ldr in all_loaders.values():
        _prev_getitem = ldr.__class__.__getitem__

        def _make_no_mmap_getitem(prev_fn, _logger):
            def _no_mmap_getitem(self, key):
                # State dict first (fast path)
                if key in self.state_dict:
                    return self.state_dict[key]

                # Check for safetensors disk-backed tensor
                weight_info = self.index.get(key)
                if weight_info is not None and weight_info.get("safetensors_file") is not None:
                    sf_file = weight_info["safetensors_file"]
                    weight_name = weight_info.get("weight_name", key)
                    tensor = _read_tensor_no_mmap(sf_file, weight_name)
                    if "dtype" in weight_info:
                        tensor = tensor.to(getattr(torch, weight_info["dtype"]))
                    return tensor

                # Fall back to previous __getitem__ for non-safetensors
                return prev_fn(self, key)
            return _no_mmap_getitem

        ldr.__class__.__getitem__ = _make_no_mmap_getitem(_prev_getitem, logger)

    logger.info("mmap-free safetensors reader installed (bypasses safe_open entirely)")


def _patch_rms_norm_old_forwards(model, logger):
    """Wrap _old_forward on all Qwen3_5MoeRMSNorm instances to auto-correct wrong-shape weights.

    Root cause of the (32,) shape crash during gradient-checkpointing recompute:
    AlignDevicesHook.pre_forward loads from weights_map which may have a stale or
    corrupted (32,) tensor for 'weight' (the corrupted safetensors index maps some
    keys to tensors from wrong shards; in this model linear_num_value_heads=32, so
    dt_bias / A_log params have shape (32,) — one of these ends up stored under the
    input_layernorm.weight key in the disk-backed weights_map).

    The hook's new_forward runs this sequence:
        1. pre_forward() → loads weights_map["weight"] = wrong (32,) tensor → sets module.weight
        2. module._old_forward(*args) → calls Qwen3_5MoeRMSNorm.forward (our wrapper)
        3. post_forward() → moves weight back to meta

    By wrapping _old_forward we intercept BETWEEN the hook's load (step 1) and the
    actual computation (step 2), detect the wrong shape, and swap in the saved correct
    weight before proceeding.
    """
    import torch
    import torch.nn as nn

    try:
        from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoeRMSNorm
    except ImportError:
        logger.warning("_patch_rms_norm_old_forwards: cannot import Qwen3_5MoeRMSNorm")
        return

    # Save correct weights NOW (post _fix_meta_weights, all norms are materialized).
    # This dict maps module_path → (expected_dim, cpu bf16 tensor).
    correct_weights = {}
    for module_path, mod in model.named_modules():
        if not isinstance(mod, Qwen3_5MoeRMSNorm):
            continue
        if not hasattr(mod, '_old_forward'):
            continue  # no AlignDevicesHook on this module — params won't be swapped
        w = mod._parameters.get('weight')
        if w is None or w.device.type == 'meta':
            continue
        correct_weights[module_path] = (w.shape[0], w.data.detach().cpu().clone())

    if not correct_weights:
        logger.warning("_patch_rms_norm_old_forwards: no RMSNorm modules with _old_forward found")
        return

    logger.info(f"_patch_rms_norm_old_forwards: saving correct weights for {len(correct_weights)} modules")

    # Patch _old_forward on each found module
    patched = 0
    for module_path, (expected_dim, correct_w_cpu) in correct_weights.items():
        mod = model
        for part in module_path.split('.'):
            mod = getattr(mod, part, None)
            if mod is None:
                break
        if mod is None:
            continue

        orig_old_forward = mod._old_forward

        def make_wrapper(m, edim, cw_cpu, orig):
            """Return a forward wrapper that corrects wrong-shape weights before running."""
            def shape_correcting_forward(*args, **kwargs):
                w = m._parameters.get('weight')
                if w is not None and w.device.type != 'meta' and w.shape[0] != edim:
                    logger.warning(
                        f"[RMSNorm] weight shape {tuple(w.shape)} → ({edim},) corrected"
                        f" (hook loaded stale tensor from corrupted weights_map)"
                    )
                    m._parameters['weight'] = nn.Parameter(
                        cw_cpu.to(device=w.device, dtype=w.dtype),
                        requires_grad=False,
                    )
                return orig(*args, **kwargs)
            return shape_correcting_forward

        mod._old_forward = make_wrapper(mod, expected_dim, correct_w_cpu, orig_old_forward)
        patched += 1

    logger.info(f"_patch_rms_norm_old_forwards: wrapped _old_forward on {patched} RMSNorm modules")


def _patch_linear_attn_old_forwards(model, logger):
    """Patch _old_forward on linear_attn modules to validate dt_bias/A_log shapes.

    This is the definitive fix for the dt_bias (32,)→(2048,) corruption during
    gradient-checkpointing recompute.  The accelerate AlignDevicesHook's pre_forward
    calls set_module_tensor_to_device(module, name, device, value=value,
    tied_params_map=self.tied_params_map).  The tied_params_map can silently replace
    the correct value with a wrong-shape tensor if data pointers collide.

    By patching _old_forward, we intercept AFTER the hook has set all params/buffers
    and BEFORE the actual computation.  If dt_bias or A_log have wrong shapes, we
    restore from saved correct copies.
    """
    import torch
    import torch.nn as nn

    # Find linear_attn modules that have _old_forward (= have an accelerate hook)
    saved_tensors = {}  # module_path → {"dt_bias": (shape, cpu_tensor), "A_log": (shape, cpu_tensor)}

    for module_path, mod in model.named_modules():
        if not hasattr(mod, 'dt_bias') or not hasattr(mod, '_old_forward'):
            continue

        tensors = {}
        for attr in ('dt_bias', 'A_log'):
            p = getattr(mod, attr, None)
            if p is None:
                continue
            shape = tuple(p.shape)
            if p.device.type != 'meta':
                tensors[attr] = (shape, p.data.detach().cpu().clone())
            else:
                # Meta tensor — get correct value from the hook's weights_map
                hook = getattr(mod, '_hf_hook', None)
                if hook is not None:
                    wmap = getattr(hook, 'weights_map', None)
                    if wmap is not None:
                        try:
                            val = wmap[attr]
                            if isinstance(val, torch.Tensor) and tuple(val.shape) == shape:
                                tensors[attr] = (shape, val.detach().cpu().clone())
                            else:
                                tensors[attr] = (shape, None)  # will use zeros
                        except (KeyError, Exception):
                            tensors[attr] = (shape, None)
                else:
                    tensors[attr] = (shape, None)

        if tensors:
            saved_tensors[module_path] = tensors

    if not saved_tensors:
        logger.warning("_patch_linear_attn_old_forwards: no linear_attn modules found")
        return

    logger.info(f"_patch_linear_attn_old_forwards: saving tensors for {len(saved_tensors)} modules")
    for mp, t in list(saved_tensors.items())[:3]:
        for attr, (sh, cpu_t) in t.items():
            logger.info(f"  {mp}.{attr}: shape={sh}, has_data={'yes' if cpu_t is not None else 'NO'}")

    # Patch _old_forward
    patched = 0
    for module_path, tensors in saved_tensors.items():
        # Navigate to module
        mod = model
        for part in module_path.split('.'):
            mod = getattr(mod, part, None)
            if mod is None:
                break
        if mod is None:
            continue

        orig_old_forward = mod._old_forward

        def make_wrapper(m, m_path, tdict, orig, _log):
            _fix_count = [0]  # mutable counter in closure

            def shape_correcting_forward(*args, **kwargs):
                for attr_name, (exp_shape, cpu_tensor) in tdict.items():
                    p = getattr(m, attr_name, None)
                    if p is None:
                        continue
                    actual = tuple(p.shape)
                    if actual != exp_shape:
                        if _fix_count[0] < 3:  # limit logging
                            _log.warning(
                                f"[LINEAR_ATTN FIX] {m_path}.{attr_name}: "
                                f"{actual} → {exp_shape}"
                            )
                        _fix_count[0] += 1
                        if cpu_tensor is not None:
                            new_val = cpu_tensor.to(device=p.device, dtype=p.dtype)
                        else:
                            new_val = torch.zeros(exp_shape, dtype=p.dtype, device=p.device)
                        # Use _parameters directly to bypass Parameter wrapping issues
                        if attr_name in m._parameters:
                            m._parameters[attr_name] = nn.Parameter(new_val, requires_grad=p.requires_grad)
                        elif hasattr(m, '_buffers') and attr_name in m._buffers:
                            m._buffers[attr_name] = new_val
                        else:
                            setattr(m, attr_name, new_val)
                return orig(*args, **kwargs)
            return shape_correcting_forward

        mod._old_forward = make_wrapper(mod, module_path, tensors, orig_old_forward, logger)
        patched += 1

    logger.info(f"_patch_linear_attn_old_forwards: wrapped _old_forward on {patched} linear_attn modules")


def _patch_expert_old_forwards(model, logger):
    """Patch _old_forward on Qwen3_5MoeExperts to validate gate_up_proj/down_proj shapes.

    During forward, AlignDevicesHook's pre_forward loads expert weights from the disk
    fallback (safetensors index).  The index is corrupted for several layers, causing
    down_proj to load with shape (256, 1024, 2048) instead of (256, 2048, 512).
    The tied_params_map in set_module_tensor_to_device can also bypass the loader's
    shape guard.

    This patches _old_forward to validate shapes AFTER the hook and BEFORE computation.
    If wrong, replaces with zeros of correct shape (experts are frozen, won't affect gradients).
    """
    import torch
    import torch.nn as nn

    try:
        from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoeExperts
    except ImportError:
        try:
            from transformers.integrations.moe import MoeLayer as Qwen3_5MoeExperts
        except ImportError:
            logger.warning("_patch_expert_old_forwards: cannot import expert module class")
            return

    # Get expected shapes — try first correct expert module, then fall back to config
    expected_gup_shape = None
    expected_dn_shape = None
    for _, mod in model.named_modules():
        gup = getattr(mod, "gate_up_proj", None)
        dn = getattr(mod, "down_proj", None)
        if (gup is not None and isinstance(gup, torch.Tensor) and gup.ndim == 3
                and dn is not None and isinstance(dn, torch.Tensor) and dn.ndim == 3):
            expected_gup_shape = tuple(gup.shape)
            expected_dn_shape = tuple(dn.shape)
            logger.info(f"_patch_expert_old_forwards: reference shapes: "
                        f"gate_up_proj={expected_gup_shape}, down_proj={expected_dn_shape}")
            break

    if expected_gup_shape is None:
        # Derive from config
        try:
            cfg = model.config
            text_cfg = cfg.text_config if hasattr(cfg, 'text_config') else cfg
            ne = text_cfg.num_experts            # 256
            mi = text_cfg.moe_intermediate_size  # 512
            hs = text_cfg.hidden_size            # 2048
            expected_gup_shape = (ne, 2 * mi, hs)
            expected_dn_shape = (ne, hs, mi)
            logger.info(f"_patch_expert_old_forwards: shapes from config: "
                        f"gate_up_proj={expected_gup_shape}, down_proj={expected_dn_shape}")
        except AttributeError:
            logger.warning("_patch_expert_old_forwards: cannot determine expected shapes")
            return

    patched = 0
    for module_path, mod in model.named_modules():
        if not hasattr(mod, 'gate_up_proj') or not hasattr(mod, 'down_proj'):
            continue
        if not hasattr(mod, '_old_forward'):
            continue

        orig_old_forward = mod._old_forward

        def make_wrapper(m, m_path, gup_shape, dn_shape, orig, _log):
            _fix_count = [0]

            def shape_correcting_forward(*args, **kwargs):
                for attr_name, exp_shape in [("gate_up_proj", gup_shape), ("down_proj", dn_shape)]:
                    p = getattr(m, attr_name, None)
                    if p is None:
                        continue
                    actual = tuple(p.shape)
                    if actual != exp_shape:
                        if _fix_count[0] < 5:
                            _log.warning(
                                f"[EXPERT FIX] {m_path}.{attr_name}: "
                                f"{actual} → zeros{exp_shape}"
                            )
                        _fix_count[0] += 1
                        new_val = torch.zeros(exp_shape, dtype=p.dtype, device=p.device)
                        if attr_name in m._parameters:
                            m._parameters[attr_name] = nn.Parameter(new_val, requires_grad=False)
                        else:
                            setattr(m, attr_name, new_val)
                return orig(*args, **kwargs)
            return shape_correcting_forward

        mod._old_forward = make_wrapper(
            mod, module_path, expected_gup_shape, expected_dn_shape, orig_old_forward, logger
        )
        patched += 1

    logger.info(f"_patch_expert_old_forwards: wrapped _old_forward on {patched} expert modules")


def _fix_expert_shapes(model, logger):
    """Validate and repair MoE expert weight shapes across all decoder layers.

    Layers 12, 18, 29, 30, 31 are missing from the checkpoint shards.
    - Layer 12: was still 'meta' after _fix_meta_weights (caught by tie resolution)
    - Layers 18/29/30/31: transformers may have left them as random-init with wrong shape
      (e.g., 1D tensor of shape (32,)) due to corrupted safetensors index.

    _grouped_linear calls weight.transpose(-2, -1) which fails on 1D tensors.
    Fix: find the expected shape from a known-good layer, then replace any
    wrong-shaped gate_up_proj / down_proj with a tied reference.
    """
    import torch

    # Find the first layer with a correct 3D gate_up_proj
    ref_layer_idx = None
    ref_gate_up = None
    ref_down = None

    for i, layer in enumerate(model.model.layers):
        try:
            experts = layer.mlp.experts
        except AttributeError:
            continue  # shared/non-MoE layer
        gup = getattr(experts, "gate_up_proj", None)
        dn  = getattr(experts, "down_proj", None)
        if gup is not None and gup.ndim == 3 and dn is not None and dn.ndim == 3:
            ref_layer_idx = i
            ref_gate_up = gup
            ref_down = dn
            break

    if ref_gate_up is None:
        logger.warning("_fix_expert_shapes: no reference layer found — all expert weights may be broken")
        return

    expected_gup_shape = tuple(ref_gate_up.shape)
    expected_dn_shape  = tuple(ref_down.shape)
    logger.info(
        f"_fix_expert_shapes: reference layer {ref_layer_idx} "
        f"gate_up_proj={expected_gup_shape}  down_proj={expected_dn_shape}"
    )

    n_fixed = 0
    for i, layer in enumerate(model.model.layers):
        try:
            experts = layer.mlp.experts
        except AttributeError:
            continue

        for attr_name, ref_param, expected_shape in [
            ("gate_up_proj", ref_gate_up, expected_gup_shape),
            ("down_proj",    ref_down,    expected_dn_shape),
        ]:
            param = getattr(experts, attr_name, None)
            if param is None:
                continue

            pshape = tuple(param.shape)
            dev = param.device.type

            # Skip correctly-formed weights:
            # - CPU bf16 Params4bit (our bypass): ndim==3, shape == expected → OK
            # - GPU 4-bit quantized Params4bit: ndim==2 (packed), quant_state set → OK
            # - Meta with correct shape: deferred to disk fallback → OK (do NOT tie!)
            # Only fix: 1D tensors or tensors with wrong shape
            is_gpu_quantized = (dev == "cuda" and
                                hasattr(param, "quant_state") and
                                param.quant_state is not None)
            if param.ndim >= 2 and (is_gpu_quantized or pshape == expected_shape):
                continue  # looks correct (may be meta = disk-deferred), skip

            # Wrong shape (1D) or meta — tie to reference CPU layer
            logger.warning(
                f"  Layer {i} experts.{attr_name}: shape={pshape} dev={dev} "
                f"→ tying to layer {ref_layer_idx} {expected_shape}"
            )
            if hasattr(experts, "_parameters") and attr_name in experts._parameters:
                experts._parameters[attr_name] = (
                    ref_param if isinstance(ref_param, torch.nn.Parameter)
                    else torch.nn.Parameter(ref_param.data, requires_grad=False)
                )
            else:
                setattr(experts, attr_name, ref_param)
            n_fixed += 1

    if n_fixed:
        logger.info(f"_fix_expert_shapes: repaired {n_fixed} expert weight tensors")
    else:
        logger.info("_fix_expert_shapes: all expert weights have correct shapes")


def train(model_path: str, max_steps: int = 0):
    """Run LoRA training via standard PEFT (no Unsloth patching — Unsloth's
    aggressive model surgery conflicts with accelerate's device hooks when
    device_map='auto' is needed for CPU offloading on 16GB VRAM)."""
    logger.info(f"Loading base model: {model_path}")
    logger.info(f"Training data: {TRAINING_JSONL}")

    # Count pairs
    with open(TRAINING_JSONL, "r", encoding="utf-8") as f:
        pair_count = sum(1 for line in f if line.strip())
    logger.info(f"Training pairs: {pair_count}")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, TaskType, get_peft_model

    # MoE 35B @ 4-bit NF4 with double quant ≈ 17GB > 16GB VRAM.
    # device_map="auto" + llm_int8_enable_fp32_cpu_offload spills ~1.5GB to CPU RAM.
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,  # required when device_map="auto" spills layers to CPU
    )

    # Load model with standard transformers (no Unsloth patching)
    start = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    # 35B @ 4-bit NF4 ≈ 17-18 GB. VRAM = 16 GB.
    # device_map="auto" with max_memory: put 14 GB on GPU, overflow to CPU RAM.
    # Loading bf16→4bit requires the bf16 shards in CPU RAM (~67GB total),
    # but transformers processes shard-by-shard so peak CPU RAM is ~5-8 GB per shard.
    #
    # NOTE: bitsandbytes' _process_model_before_weight_loading only adds CPU-offloaded
    # modules to modules_to_not_convert when device_map is a dict (not the "auto" string).
    # We work around this by patching Params4bit._quantize to skip CPU quantization —
    # keeping CPU-offloaded Params4bit in their original bf16 dtype. Linear4bit.forward
    # detects quant_state=None and falls back to standard F.linear (no 4-bit on CPU).
    max_memory = {0: "14GiB", "cpu": "55GiB"}
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
        max_memory=max_memory,
        dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    load_time = time.time() - start
    logger.info(f"Model loaded in {load_time:.0f}s")

    # Post-load diagnostic: find any parameters still on meta device and fix them.
    # This is a safety net for parameters not properly initialized from checkpoint.
    _fix_meta_weights(model, model_path, logger)

    # Fix params loaded with WRONG SHAPES due to corrupted safetensors index.
    # Unlike meta params, these were loaded from checkpoint but with the wrong tensor
    # (e.g., input_layernorm.weight loaded as (32,) instead of (2048,)). Check all
    # standard decoder-layer norm weights and reload from correct checkpoint data.
    _fix_wrong_shape_params(model, model_path, logger)

    # Validate and repair MoE expert weight shapes.
    # Layers 12, 18, 29, 30, 31 gate_up_proj / down_proj are absent from all checkpoint
    # shards — after _fix_meta_weights they may still have wrong shapes (e.g., 1D tensors
    # from corrupted index). _grouped_linear calls weight.transpose(-2, -1) which fails on
    # non-3D tensors. Tie broken layers to a known-good reference layer's tensors.
    _fix_expert_shapes(model, logger)

    # Manual equivalent of prepare_model_for_kbit_training.
    # We skip the function's "cast all bf16 params to fp32" step because
    # expert weight tensors (256, 1024, 2048) = 2GB in float32 → CPU OOM.
    # That cast is intended for LayerNorm stability but is unnecessary here:
    # - Expert weights are frozen (requires_grad=False), never receive gradients
    # - Only LoRA adapter params are trained
    # The three things we DO need: freeze base params, enable grad checkpointing,
    # and register enable_input_require_grads so gradients flow through embeddings.
    import torch.nn as nn
    logger.info("Freezing base model params (skipping fp32 cast to avoid expert-weight OOM)...")
    n_frozen = 0
    for name, param in model.named_parameters():
        param.requires_grad = False
        n_frozen += 1
    logger.info(f"  Frozen {n_frozen} base model params")

    # enable_input_require_grads allows gradient flow through frozen input embeddings
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    else:
        def _make_inputs_require_grad(module, input, output):
            output.requires_grad_(True)
        model.get_input_embeddings().register_forward_hook(_make_inputs_require_grad)

    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    logger.info("Gradient checkpointing enabled (use_reentrant=False)")

    # Apply LoRA — attention-only for MoE (skip 256 expert MLPs)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.0,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    logger.info("LoRA applied (attention-only, r=16, alpha=32)")

    # IMPORTANT: Call these AFTER get_peft_model, not before.
    # get_peft_model may call dispatch_to_device / init_hook on LoRA wrapper modules,
    # which can create a NEW OffloadedWeightsLoader (wiping our earlier fixes) or
    # re-run init_hook (which snapshots current param state — potentially stale).
    # By running these after PEFT wrapping, we fix the final hook configuration.

    # Repair AlignDevicesHook weights_map (OffloadedWeightsLoader).
    # Writes ALL current model params to the loader's in-memory state_dict, disabling
    # the disk-backed fallback that serves wrong tensors from the corrupted safetensors index.
    _fix_hook_weights_map(model, logger)

    # NUCLEAR FIX: disable tied_params_map on ALL hooks.
    # The model has tie_word_embeddings=False — no actual weight tying exists.
    # But ALL meta tensors share data_ptr=0, so tied_params_map caches the FIRST
    # loaded tensor and reuses it for ALL subsequent parameters, causing catastrophic
    # cross-contamination (expert 3D weights → norm 1D weights, etc.).
    # Disabling tied_params_map forces set_module_tensor_to_device to always use
    # the value from the loader directly, without caching/reusing.
    n_tpm_cleared = 0
    for _name, _mod in model.named_modules():
        _hook = getattr(_mod, '_hf_hook', None)
        if _hook is None:
            continue
        if hasattr(_hook, 'hooks'):  # SequentialHook
            for _h in _hook.hooks:
                if hasattr(_h, 'tied_params_map') and _h.tied_params_map is not None:
                    _h.tied_params_map = None
                    _h.tied_params_names = set()
                    n_tpm_cleared += 1
        elif hasattr(_hook, 'tied_params_map') and _hook.tied_params_map is not None:
            _hook.tied_params_map = None
            _hook.tied_params_names = set()
            n_tpm_cleared += 1
    logger.info(f"Cleared tied_params_map on {n_tpm_cleared} hooks (no weight tying in this model)")

    # Wrap _old_forward on all Qwen3_5MoeRMSNorm instances to auto-correct wrong-shape weights.
    # Safety net: even if a hook loads wrong (32,) weight for input_layernorm, this wrapper
    # detects and corrects it before the norm computation runs.
    _patch_rms_norm_old_forwards(model, logger)

    # Wrap _old_forward on all linear_attn modules to fix dt_bias/A_log shape corruption.
    # This is the definitive fix: intercepts AFTER AlignDevicesHook sets params, BEFORE computation.
    _patch_linear_attn_old_forwards(model, logger)

    # NOTE: _patch_expert_old_forwards is called AFTER the corrective scan below,
    # because the corrective scan's _diag wrapper requires _old_forward to be a bound method.

    # CORRECTIVE SCAN + FORWARD-TIME RESTORE for Linear4bit modules.
    #
    # ROOT CAUSE (confirmed Run #25):
    #   - layers.39.self_attn.q_proj.base_layer has in=2048, out=8192
    #   - Loader state_dict has correct (8192,2048) → first forward OK (LOADER ACCESS logged)
    #   - During gradient-checkpointing RECOMPUTE (backward), module.weight = (32,)
    #   - _logged_once masks second LOADER ACCESS; root cause of (32,) at recompute is unclear
    #     but may relate to set_module_tensor_to_device behavior with non-Params4bit meta params
    #
    # FIX STRATEGY:
    #   Phase 1: Scan loader state_dict for ALL Linear4bit modules (incl. meta-weight/offloaded).
    #            Save correct (eo,ei) tensors for use in forward-time restore.
    #            Fix wrong-shape entries in the loader state_dict.
    #   Phase 2: For non-meta weights, also check and fix the module param directly.
    #   Phase 3: Wrap _old_forward on each instance (bypasses class-level patch issue).
    #            CORRECTIVE: if weight is wrong-shape at forward time, restore saved tensor.
    #            DIAGNOSTIC: log [L4BIT CRASH] with full context if exception fires.
    #
    # CRITICAL: AlignDevicesHook saves module._old_forward as a BOUND METHOD before any
    # class-level patch can be applied. Must wrap _old_forward per-instance.
    try:
        import bitsandbytes.nn.modules as bnb_mod
        import torch.nn as nn
        from accelerate.hooks import AlignDevicesHook, SequentialHook
        from accelerate.utils import PrefixedDataset

        # Build registry: id(module) → full PEFT-wrapped path (after get_peft_model).
        _l4bit_registry = {}
        for _reg_name, _reg_mod in model.named_modules():
            if isinstance(_reg_mod, bnb_mod.Linear4bit):
                _l4bit_registry[id(_reg_mod)] = _reg_name
        logger.info(f"Linear4bit registry: {len(_l4bit_registry)} modules")

        # ── Phase 1: loader state_dict scan (covers meta-weight / CPU-offloaded modules) ──
        # For each hooked Linear4bit, check if loader.state_dict[prefix+'weight'] has
        # the correct (eo,ei) shape.  Save correct tensors; replace wrong ones with zeros.
        _l4bit_correct = {}   # id(mod) → cpu bf16 tensor of shape (eo, ei)
        n_loader_ok   = 0
        n_loader_bad  = 0
        for _reg_name, _reg_mod in model.named_modules():
            if not isinstance(_reg_mod, bnb_mod.Linear4bit):
                continue
            ei = getattr(_reg_mod, 'in_features', None)
            eo = getattr(_reg_mod, 'out_features', None)
            if ei is None or eo is None:
                continue
            _hook = getattr(_reg_mod, '_hf_hook', None)
            if _hook is None:
                continue
            _hooks_list = _hook.hooks if isinstance(_hook, SequentialHook) else [_hook]
            for _h in _hooks_list:
                if not isinstance(_h, AlignDevicesHook):
                    continue
                _wmap = getattr(_h, 'weights_map', None)
                if not isinstance(_wmap, PrefixedDataset):
                    continue
                if not hasattr(_wmap.dataset, 'state_dict'):
                    continue
                _ldr = _wmap.dataset
                _key = _wmap.prefix + 'weight'
                if _key not in _ldr.state_dict:
                    break   # disk-only — loader will read from safetensors every time
                _t = _ldr.state_dict[_key]
                _ts = tuple(_t.shape)
                if _ts == (eo, ei):
                    # Correct — save a CPU copy for forward-time restore
                    _l4bit_correct[id(_reg_mod)] = _t.detach().clone().cpu().to(torch.bfloat16)
                    n_loader_ok += 1
                else:
                    # Wrong shape (e.g. (32,) from dt_bias/A_log key collision)
                    logger.warning(
                        f"[L4BIT BAD LOADER] {_reg_name}: key={_key!r} "
                        f"loader_shape={_ts} expected=({eo},{ei}) — replacing with zeros"
                    )
                    _zero = torch.zeros(eo, ei, dtype=torch.bfloat16)
                    _ldr.state_dict[_key] = _zero
                    _l4bit_correct[id(_reg_mod)] = _zero.clone()
                    n_loader_bad += 1
                break   # only first AlignDevicesHook matters

        logger.info(
            f"Linear4bit loader scan: {n_loader_ok} correct, {n_loader_bad} fixed. "
            f"{len(_l4bit_correct)} modules have saved correct tensors."
        )

        # ── Phase 1b: scan ALL other hooked modules for ALL wrong-shape params ──
        # Catches non-Linear4bit modules: Qwen3_5MoeTopKRouter (weight=(256,2048)),
        # Qwen3_5MoeExperts (gate_up_proj=(256,1024,2048), down_proj=(256,2048,512)),
        # and any other module with multi-dimensional offloaded parameters.
        #
        # KEY CHANGE vs prior version: now iterates ALL _parameters (not just 'weight'),
        # stores corrections by (id(mod), pname) so multi-param modules are fully covered.
        _gen_correct = {}   # {(id(mod), pname): cpu_bf16_tensor}  (replaces id-keyed _l4bit_correct for non-L4bit)
        n_gen_ok = 0
        n_gen_bad = 0
        for _reg_name, _reg_mod in model.named_modules():
            if isinstance(_reg_mod, bnb_mod.Linear4bit):
                continue  # handled by Phase 1 above
            _hook = getattr(_reg_mod, '_hf_hook', None)
            if _hook is None:
                continue
            _hooks_list = _hook.hooks if isinstance(_hook, SequentialHook) else [_hook]
            for _h in _hooks_list:
                if not isinstance(_h, AlignDevicesHook):
                    continue
                _wmap = getattr(_h, 'weights_map', None)
                if not isinstance(_wmap, PrefixedDataset):
                    continue
                if not hasattr(_wmap.dataset, 'state_dict'):
                    continue
                _ldr = _wmap.dataset
                # Check ALL direct parameters of this module
                for _pname, _pw in list(_reg_mod._parameters.items()):
                    if _pw is None:
                        continue
                    _exp_shape = tuple(_pw.shape)
                    if len(_exp_shape) < 2:
                        continue  # 1D params can't be meaningfully guarded
                    _key = _wmap.prefix + _pname
                    if _key not in _ldr.state_dict:
                        # Not in memory — will fall through to disk (safetensors) during recompute.
                        # We can't save a correct tensor now, but Phase 3b will zero-fill if shape is wrong.
                        logger.warning(
                            f"[GEN NOT IN SD] {_reg_name}.{_pname}: key {_key!r} missing from state_dict"
                        )
                        continue
                    _t = _ldr.state_dict[_key]
                    _ts = tuple(_t.shape)
                    if _ts == _exp_shape:
                        _gen_correct[(id(_reg_mod), _pname)] = _t.detach().clone().cpu().to(torch.bfloat16)
                        n_gen_ok += 1
                    else:
                        logger.warning(
                            f"[GEN BAD LOADER] {_reg_name} ({type(_reg_mod).__name__}) "
                            f".{_pname}: key={_key!r} loader_shape={_ts} expected={_exp_shape} — fixing"
                        )
                        _zero = torch.zeros(_exp_shape, dtype=torch.bfloat16)
                        _ldr.state_dict[_key] = _zero
                        _gen_correct[(id(_reg_mod), _pname)] = _zero.clone()
                        n_gen_bad += 1
                    # Also keep legacy id-keyed _l4bit_correct entry for backward compat with Phase 3b old code
                    if _pname == 'weight':
                        _l4bit_correct[id(_reg_mod)] = _gen_correct[(id(_reg_mod), _pname)]
                break  # only first AlignDevicesHook with PrefixedDataset

        logger.info(
            f"General module loader scan: {n_gen_ok} correct, {n_gen_bad} fixed. "
            f"{len(_gen_correct)} (mod,param) correction entries saved."
        )

        # ── Phase 2: direct module weight check (non-meta, non-offloaded) ────
        n_module_bad = 0
        for _reg_name, _reg_mod in model.named_modules():
            if not isinstance(_reg_mod, bnb_mod.Linear4bit):
                continue
            w = _reg_mod.weight
            if w is None or w.device.type == 'meta':
                continue
            ei = getattr(_reg_mod, 'in_features', None)
            eo = getattr(_reg_mod, 'out_features', None)
            if ei is None or eo is None:
                continue
            qs = getattr(w, 'quant_state', None)
            actual = tuple(qs.shape) if qs is not None else tuple(w.shape)
            if len(actual) == 2 and actual == (eo, ei):
                continue
            logger.warning(
                f"[L4BIT BAD MODULE] {_reg_name}: weight_shape={actual} "
                f"expected=({eo},{ei}) — fixing"
            )
            _dev = w.device
            if id(_reg_mod) in _l4bit_correct:
                _fixed = _l4bit_correct[id(_reg_mod)].to(_dev)
            else:
                _fixed = torch.zeros(eo, ei, dtype=torch.bfloat16, device=_dev)
            _reg_mod._parameters['weight'] = nn.Parameter(_fixed, requires_grad=False)
            n_module_bad += 1
        if n_module_bad:
            logger.warning(f"Phase 2: fixed {n_module_bad} Linear4bit modules with wrong direct weights")

        # ── Phase 3: _old_forward wrapper with forward-time correction ────────
        # CORRECTIVE: if the hook loads a wrong-shape weight (e.g., during
        # gradient-checkpointing recompute), restore the saved correct tensor.
        # DIAGNOSTIC: log the crash context if Linear4bit.forward throws.
        n_patched = 0
        for _reg_name, _reg_mod in model.named_modules():
            if not isinstance(_reg_mod, bnb_mod.Linear4bit):
                continue
            if not hasattr(_reg_mod, '_old_forward'):
                continue

            _orig_bound   = _reg_mod._old_forward
            _mod_path     = _l4bit_registry.get(id(_reg_mod), _reg_name)
            _ei           = getattr(_reg_mod, 'in_features', None)
            _eo           = getattr(_reg_mod, 'out_features', None)
            _correct_cpu  = _l4bit_correct.get(id(_reg_mod))  # cpu bf16 or None

            def _make_diag(orig_fn, path, ei, eo, correct_cpu):
                def _diag(*args, **kwargs):
                    x = args[0] if args else kwargs.get('x')
                    self_m = orig_fn.__self__
                    w = self_m.weight
                    if w is not None and w.device.type != 'meta' and x is not None and ei is not None:
                        ws = (tuple(w.quant_state.shape)
                              if (hasattr(w, 'quant_state') and w.quant_state is not None)
                              else tuple(w.shape))
                        # ── check weight shape ──
                        if len(ws) < 2 or ws[1] != ei:
                            logger.error(
                                f"[L4BIT WEIGHT BAD] {path} in={ei} out={eo} wshape={ws}"
                            )
                            # Restore correct weight to prevent crash
                            _dev = w.device
                            if correct_cpu is not None:
                                logger.error(f"[L4BIT RESTORING] {path} → ({eo},{ei}) on {_dev}")
                                self_m._parameters['weight'] = nn.Parameter(
                                    correct_cpu.to(_dev, dtype=torch.bfloat16),
                                    requires_grad=False
                                )
                            else:
                                logger.error(f"[L4BIT ZEROING] {path} — no saved weight")
                                self_m._parameters['weight'] = nn.Parameter(
                                    torch.zeros(eo, ei, dtype=torch.bfloat16, device=_dev),
                                    requires_grad=False
                                )
                        # ── check input shape ──
                        if x.shape[-1] != ei:
                            logger.error(
                                f"[L4BIT INPUT MISMATCH] {path} x.shape={tuple(x.shape)} in={ei}"
                            )
                    try:
                        return orig_fn(*args, **kwargs)
                    except Exception as _e:
                        _w2 = orig_fn.__self__.weight
                        _ws2 = (tuple(_w2.quant_state.shape)
                                if (_w2 is not None and hasattr(_w2, 'quant_state') and _w2.quant_state is not None)
                                else (tuple(_w2.shape) if _w2 is not None else None))
                        logger.error(
                            f"[L4BIT CRASH] {path} "
                            f"x.shape={tuple(x.shape) if x is not None else None} "
                            f"weight_shape={_ws2} error={_e}"
                        )
                        raise
                return _diag

            _reg_mod._old_forward = _make_diag(
                _orig_bound, _mod_path, _ei, _eo, _correct_cpu
            )
            n_patched += 1

        logger.info(f"Linear4bit corrective+diagnostic: {n_patched} _old_forward patches installed (Linear4bit)")

        # ── Phase 3b: _old_forward wrapping for non-Linear4bit hooked modules ──
        # Handles Qwen3_5MoeTopKRouter (gate/weight), Qwen3_5MoeExperts (gate_up_proj,
        # down_proj), and any other non-L4bit module with offloaded multi-dim params.
        #
        # Uses _gen_correct: {(id(mod), pname): correct_cpu_tensor} — supports MULTIPLE
        # params per module (unlike the old id-keyed approach which only handled 'weight').
        #
        # Groups _gen_correct entries by module id, then patches _old_forward once per module.

        # Build per-module correction maps: {id(mod): {pname: correct_cpu}}
        _gen_by_mod = {}
        for (_mid, _pname), _cpu_t in _gen_correct.items():
            if _mid not in _gen_by_mod:
                _gen_by_mod[_mid] = {}
            _gen_by_mod[_mid][_pname] = _cpu_t

        n_gen_patched = 0
        for _reg_name, _reg_mod in model.named_modules():
            if isinstance(_reg_mod, bnb_mod.Linear4bit):
                continue  # already done in Phase 3
            if id(_reg_mod) not in _gen_by_mod:
                continue  # no correction saved for this module
            if not hasattr(_reg_mod, '_old_forward'):
                logger.warning(
                    f"[GEN NO OLD_FORWARD] {_reg_name} ({type(_reg_mod).__name__}): "
                    f"no _old_forward — cannot wrap; will use register_forward_pre_hook fallback"
                )
                # Fallback: register a forward_pre_hook to fix params before every call.
                # This works even when AlignDevicesHook hasn't set _old_forward.
                _corrections_for_hook = _gen_by_mod[id(_reg_mod)]
                _mod_path_h = _reg_name
                def _make_pre_hook(path, corrections):
                    def _pre(module, args):
                        for pname, correct_cpu in corrections.items():
                            p = module._parameters.get(pname)
                            if p is None or p.device.type == 'meta':
                                continue
                            _exp = tuple(correct_cpu.shape)
                            _act = tuple(p.shape)
                            if _act != _exp:
                                logger.error(
                                    f"[GEN HOOK BAD] {path}.{pname}: {_act} → {_exp}"
                                )
                                module._parameters[pname] = nn.Parameter(
                                    correct_cpu.to(p.device, dtype=torch.bfloat16),
                                    requires_grad=False
                                )
                    return _pre
                _reg_mod.register_forward_pre_hook(
                    _make_pre_hook(_mod_path_h, _corrections_for_hook)
                )
                n_gen_patched += 1
                continue

            _orig_bound   = _reg_mod._old_forward
            _mod_path     = _reg_name
            _corrections  = _gen_by_mod[id(_reg_mod)]  # {pname: correct_cpu}

            def _make_gen_diag(orig_fn, path, corrections):
                def _diag(*args, **kwargs):
                    self_m = orig_fn.__self__
                    for _pn, _ccpu in corrections.items():
                        _p = self_m._parameters.get(_pn)
                        if _p is None or _p.device.type == 'meta':
                            continue
                        _exp = tuple(_ccpu.shape)
                        _act = tuple(_p.shape)
                        if _act != _exp:
                            logger.error(
                                f"[GEN WEIGHT BAD] {path} ({type(self_m).__name__}) "
                                f".{_pn}: {_act} expected {_exp}"
                            )
                            self_m._parameters[_pn] = nn.Parameter(
                                _ccpu.to(_p.device, dtype=torch.bfloat16),
                                requires_grad=False
                            )
                    try:
                        return orig_fn(*args, **kwargs)
                    except Exception as _e:
                        _shapes = {_pn: tuple(self_m._parameters[_pn].shape)
                                   for _pn in corrections if self_m._parameters.get(_pn) is not None}
                        logger.error(
                            f"[GEN CRASH] {path} ({type(self_m).__name__}) "
                            f"param_shapes={_shapes} error={_e}"
                        )
                        raise
                return _diag

            _reg_mod._old_forward = _make_gen_diag(
                _orig_bound, _mod_path, _corrections
            )
            n_gen_patched += 1

        logger.info(f"General module corrective: {n_gen_patched} _old_forward patches installed")

    except Exception as e:
        import traceback
        logger.warning(f"Could not install Linear4bit corrective patches: {e}")
        logger.warning(traceback.format_exc())

    # Wrap _old_forward on MoE expert modules to fix gate_up_proj/down_proj shape corruption.
    # Must run AFTER the corrective scan above so our wrapper is the outermost layer.
    _patch_expert_old_forwards(model, logger)

    # Cast LoRA adapter weights to bf16 to match training dtype.
    # PEFT creates adapters in float32 by default; bf16 training (SFTConfig bf16=True)
    # enables autocast which bypasses PEFT's _cast_input_dtype, leaving a bf16 vs float32
    # mismatch in the lora_A matmul.
    n_cast = 0
    for name, param in model.named_parameters():
        if param.requires_grad and param.dtype == torch.float32:
            param.data = param.data.to(torch.bfloat16)
            n_cast += 1
    logger.info(f"Cast {n_cast} LoRA adapter params from float32 → bf16")

    # Load dataset
    from datasets import load_dataset
    dataset = load_dataset("json", data_files=TRAINING_JSONL, split="train")

    # EOS token: Qwen3.5 uses <|im_end|> (token 248046), NOT <|endoftext|>
    logger.info(f"EOS token: '{tokenizer.eos_token}' (id={tokenizer.eos_token_id})")

    # Format training data as ChatML — matches the model's native format and
    # what llama-server sends at inference time via chat_template.
    # apply_chat_template automatically adds empty <think></think> tags for
    # the assistant response, matching the enable_thinking=False inference format.
    #
    # IMPORTANT: We truncate the assistant's output content (not the whole
    # sequence) so the final <|im_end|> EOS token is always present. Without
    # this, 77% of examples get blindly truncated at max_length and the model
    # never sees the stop signal.
    MAX_SEQ = 2048  # must match SFTConfig.max_length

    def format_prompt(examples):
        texts = []
        n_truncated = 0
        for inst, inp, out in zip(examples["instruction"], examples["input"], examples["output"]):
            user_content = inst
            if inp:
                user_content += "\n" + inp

            # Build the full ChatML text first
            messages = [
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": out},
            ]
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            n_tokens = len(tokenizer.encode(text))

            # If too long, progressively shorten the assistant output
            if n_tokens > MAX_SEQ:
                # Measure overhead (everything except the output)
                overhead_messages = [
                    {"role": "system", "content": "You are a helpful AI assistant."},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": ""},
                ]
                overhead_text = tokenizer.apply_chat_template(
                    overhead_messages, tokenize=False, add_generation_prompt=False
                )
                overhead_tokens = len(tokenizer.encode(overhead_text))
                budget = MAX_SEQ - overhead_tokens - 1  # -1 safety margin

                # Truncate output in token space, then decode back
                out_tokens = tokenizer.encode(out, add_special_tokens=False)
                out_tokens = out_tokens[:budget]
                truncated_out = tokenizer.decode(out_tokens, skip_special_tokens=False)

                messages[-1]["content"] = truncated_out
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
                n_truncated += 1

            texts.append(text)
        if n_truncated > 0:
            logger.info(f"  [format_prompt batch] truncated {n_truncated}/{len(texts)} examples to fit {MAX_SEQ} tokens")
        return {"text": texts}

    dataset = dataset.map(format_prompt, batched=True)
    logger.info(f"Dataset ready: {len(dataset)} examples")

    # Validate: every example must end with EOS and fit in MAX_SEQ
    n_valid = 0
    n_over = 0
    for i in range(min(50, len(dataset))):
        text = dataset[i]["text"]
        toks = len(tokenizer.encode(text))
        if toks > MAX_SEQ:
            n_over += 1
        if text.rstrip().endswith("<|im_end|>"):
            n_valid += 1
    logger.info(f"Validation (first 50): {n_valid}/50 end with EOS, {n_over}/50 over {MAX_SEQ} tokens")

    # Log a sample to verify format
    sample = dataset[0]["text"]
    logger.info(f"Sample training text ({len(tokenizer.encode(sample))} tokens, first 500 chars):\n{sample[:500]}")

    # Training — SFTConfig replaces TrainingArguments for SFTTrainer (trl 0.24+)
    from trl import SFTTrainer, SFTConfig
    from transformers import TrainerCallback
    import threading
    import psutil

    # ── Custom callback: logs loss through OUR logger (proven to work) ──────
    class HiveLoggingCallback(TrainerCallback):
        """Logs training metrics via our logger.info() — bypasses HF's print()."""
        def __init__(self):
            self._start_time = time.time()

        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs is None:
                return
            step = state.global_step
            total = state.max_steps
            loss = logs.get("loss", logs.get("train_loss", None))
            lr = logs.get("learning_rate", None)
            elapsed = time.time() - self._start_time
            eta_s = (elapsed / max(step, 1)) * (total - step) if step > 0 else 0
            eta_h = eta_s / 3600
            parts = [f"Step {step}/{total}"]
            if loss is not None:
                parts.append(f"loss={loss:.4f}")
            if lr is not None:
                parts.append(f"lr={lr:.2e}")
            parts.append(f"elapsed={elapsed/3600:.1f}h")
            parts.append(f"ETA={eta_h:.1f}h")
            logger.info(" | ".join(parts))
            sys.stdout.flush()
            sys.stderr.flush()

        def on_step_end(self, args, state, control, **kwargs):
            # Log memory every 50 steps
            if state.global_step % 50 == 0 and state.global_step > 0:
                self._log_memory(state.global_step)

        def on_train_begin(self, args, state, control, **kwargs):
            self._start_time = time.time()
            self._log_memory(0)
            logger.info(f"Training started: {state.max_steps} total steps")
            sys.stdout.flush()

        def _log_memory(self, step):
            try:
                proc = psutil.Process()
                ram_gb = proc.memory_info().rss / (1024**3)
                ram_avail = psutil.virtual_memory().available / (1024**3)
                gpu_line = ""
                try:
                    import subprocess as sp
                    out = sp.check_output(
                        ["nvidia-smi", "--query-gpu=memory.used,memory.free",
                         "--format=csv,noheader,nounits"],
                        text=True, timeout=5
                    ).strip()
                    gpu_used, gpu_free = out.split(", ")
                    gpu_line = f" | GPU={gpu_used}MB used, {gpu_free}MB free"
                except Exception:
                    pass
                logger.info(
                    f"[MEM step={step}] RAM={ram_gb:.1f}GB used, "
                    f"{ram_avail:.1f}GB avail{gpu_line}"
                )
            except Exception as e:
                logger.warning(f"[MEM] failed: {e}")

    # ── Heartbeat thread: confirms process is alive every 5 min ────────────
    _heartbeat_stop = threading.Event()
    def _heartbeat():
        n = 0
        while not _heartbeat_stop.wait(300):  # every 5 minutes
            n += 1
            try:
                proc = psutil.Process()
                ram_gb = proc.memory_info().rss / (1024**3)
                logger.info(f"[HEARTBEAT #{n}] alive, RAM={ram_gb:.1f}GB")
                sys.stdout.flush()
            except Exception:
                pass
    _hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    _hb_thread.start()

    sft_kwargs = dict(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=1,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=1,
        logging_strategy="steps",
        save_steps=50,
        weight_decay=0.01,
        max_grad_norm=1.0,
        seed=42,
        report_to="none",
        disable_tqdm=True,
        gradient_checkpointing=True,
        # SFT-specific params (moved from SFTTrainer constructor)
        dataset_text_field="text",
        max_length=2048,
    )
    if max_steps > 0:
        sft_kwargs["max_steps"] = max_steps
        sft_kwargs["save_steps"] = max_steps + 1  # don't save during test
        logger.info(f"Test mode: max_steps={max_steps}")
    sft_config = SFTConfig(**sft_kwargs)

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=sft_config,
        callbacks=[HiveLoggingCallback()],
    )

    logger.info("Starting training...")
    sys.stdout.flush()
    sys.stderr.flush()
    start = time.time()
    try:
        stats = trainer.train()
    except Exception as e:
        logger.error(f"Training FAILED with exception: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        _heartbeat_stop.set()
        raise
    finally:
        _heartbeat_stop.set()
    elapsed = time.time() - start
    loss = stats.metrics.get("train_loss", "N/A")
    logger.info(f"Training complete: loss={loss}, time={elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Save adapter
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.info(f"Adapter saved to {OUTPUT_DIR}")

    # Save training metadata
    import json
    meta = {
        "version": "v2.0",
        "base_model": model_path,
        "pair_count": pair_count,
        "loss": loss,
        "training_time_s": round(elapsed),
        "lora_config": {"r": 16, "alpha": 32, "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"]},
        "training_config": {"batch": 1, "grad_accum": 8, "epochs": 1, "lr": 2e-4, "seq_len": 2048},
        "eos_token": tokenizer.eos_token,
        "eos_token_id": tokenizer.eos_token_id,
    }
    with open(os.path.join(OUTPUT_DIR, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    return loss


def convert_to_gguf():
    """Convert the saved LoRA adapter to GGUF format."""
    if not os.path.exists(CONVERT_SCRIPT):
        logger.warning("convert_lora_to_gguf.py not found, skipping GGUF conversion")
        logger.warning("Manual conversion: python convert_lora_to_gguf.py --base-model-id unsloth/Qwen3.5-35B-A3B loras/v2/")
        return False

    logger.info("Converting adapter to GGUF...")
    # Use local model path if available, otherwise HuggingFace ID
    base_id = BASE_MODEL_LOCAL if os.path.isdir(BASE_MODEL_LOCAL) else HF_MODEL_ID
    cmd = [
        sys.executable, CONVERT_SCRIPT,
        "--base-model-id", base_id,
        OUTPUT_DIR,
    ]
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode == 0:
        # Find the generated GGUF
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith(".gguf"):
                src = os.path.join(OUTPUT_DIR, f)
                if src != ADAPTER_GGUF:
                    os.rename(src, ADAPTER_GGUF)
                size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
                logger.info(f"GGUF adapter: {ADAPTER_GGUF} ({size_mb:.0f} MB)")
                return True
        logger.error("Conversion succeeded but no .gguf file found in output")
        return False
    else:
        logger.error(f"GGUF conversion failed (exit {result.returncode})")
        if result.stderr:
            logger.error(f"stderr: {result.stderr[:500]}")
        if result.stdout:
            logger.info(f"stdout: {result.stdout[:500]}")
        return False


def print_next_steps():
    """Print what to do after training."""
    print("\n" + "=" * 60)
    print("  HiveAI v2 Training Complete!")
    print("=" * 60)
    print(f"\n  Adapter: {OUTPUT_DIR}")
    if os.path.exists(ADAPTER_GGUF):
        size_mb = os.path.getsize(ADAPTER_GGUF) / 1024 / 1024
        print(f"  GGUF:    {ADAPTER_GGUF} ({size_mb:.0f} MB)")
    print(f"\n  Start llama-server:")
    print(f"    llama-server.exe \\")
    print(f"      -m \"{BASE_GGUF}\" \\")
    print(f"      --lora \"{ADAPTER_GGUF}\" \\")
    print(f"      --port 11435 --ctx-size 8192 --n-gpu-layers 999 --threads 8")
    print(f"\n  Then start Flask:")
    print(f"    python -m hiveai.app")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, default=0,
                        help="Test mode: run N steps then stop (0=full training)")
    args = parser.parse_args()

    logger.info("HiveAI LoRA v2 Training Pipeline")
    logger.info("Base: Qwen3.5-35B-A3B (MoE, 256 experts, 3B active)")
    logger.info("Data: 2210 high-quality pairs (quality >= 0.75)")
    if args.test:
        logger.info(f"TEST MODE: will stop after {args.test} steps")

    model_path = check_prerequisites()
    loss = train(model_path, max_steps=args.test if args.test else 0)
    if not args.test:
        convert_to_gguf()
        print_next_steps()
    else:
        logger.info(f"Test complete (loss={loss}). Ready for full run.")
