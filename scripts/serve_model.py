"""
scripts/serve_model.py

Python-based OpenAI-compatible inference server for Qwen3.5-MoE with LoRA.

Loads the model using the same monkey-patched infrastructure as training
(unfused experts + BnB 4-bit + PEFT adapter), then serves /v1/chat/completions
on the specified port. Compatible with run_eval.py --base-url.

Usage:
    python scripts/serve_model.py                           # base model only
    python scripts/serve_model.py --lora loras/v3           # with v3 LoRA
    python scripts/serve_model.py --lora loras/v3 --port 11435
    python scripts/serve_model.py --test                    # quick sanity check
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from threading import Lock

sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BASE_MODEL = os.path.join(PROJECT_ROOT, "models", "qwen3.5-35b-a3b-pruned")

# ---------------------------------------------------------------------------
# Reuse monkey-patches from train_v3.py
# ---------------------------------------------------------------------------
def patch_experts_for_quantization():
    """Monkey-patch Qwen3NextExperts to use nn.Linear instead of fused 3D Parameters."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers.activations import ACT2FN
    from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoeExperts
    from transformers.models.qwen3_next.modeling_qwen3_next import Qwen3NextExperts

    def patched_init(self, config):
        nn.Module.__init__(self)
        self.num_experts = config.num_experts
        self.hidden_dim = config.hidden_size
        self.intermediate_dim = config.moe_intermediate_size
        self.act_fn = ACT2FN[config.hidden_act]
        self.config = config
        self.has_bias = False
        self.is_transposed = False
        self.gate_projs = nn.ModuleList([
            nn.Linear(self.hidden_dim, self.intermediate_dim, bias=False)
            for _ in range(self.num_experts)
        ])
        self.up_projs = nn.ModuleList([
            nn.Linear(self.hidden_dim, self.intermediate_dim, bias=False)
            for _ in range(self.num_experts)
        ])
        self.down_projs = nn.ModuleList([
            nn.Linear(self.intermediate_dim, self.hidden_dim, bias=False)
            for _ in range(self.num_experts)
        ])

    def patched_forward(self, hidden_states, top_k_index, top_k_weights):
        final_hidden_states = torch.zeros_like(hidden_states)
        with torch.no_grad():
            active_experts = top_k_index.unique().tolist()
        for expert_idx in active_experts:
            mask = (top_k_index == expert_idx)
            token_idx, top_k_pos = mask.nonzero(as_tuple=True)
            if token_idx.numel() == 0:
                continue
            current_state = hidden_states[token_idx]
            gate_out = self.gate_projs[expert_idx](current_state)
            up_out = self.up_projs[expert_idx](current_state)
            current_hidden_states = F.silu(gate_out) * up_out
            current_hidden_states = self.down_projs[expert_idx](current_hidden_states)
            current_hidden_states = current_hidden_states * top_k_weights[token_idx, top_k_pos, None]
            final_hidden_states.index_add_(0, token_idx, current_hidden_states.to(final_hidden_states.dtype))
        return final_hidden_states

    Qwen3_5MoeExperts.__init__ = patched_init
    Qwen3_5MoeExperts.forward = patched_forward
    Qwen3NextExperts.__init__ = patched_init
    Qwen3NextExperts.forward = patched_forward

    from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoePreTrainedModel
    original_init_weights = Qwen3_5MoePreTrainedModel._init_weights

    import torch as _torch
    @_torch.no_grad()
    def patched_init_weights(self, module):
        if isinstance(module, (Qwen3_5MoeExperts, Qwen3NextExperts)):
            return
        original_init_weights(self, module)

    Qwen3_5MoePreTrainedModel._init_weights = patched_init_weights
    logger.info("Patched expert classes: fused 3D -> per-expert nn.Linear")


def disable_expert_fusing_converter():
    """Disable transformers conversion_mapping that re-fuses per-expert tensors."""
    try:
        import transformers.conversion_mapping as cm
        for key in list(cm._MODEL_TO_CONVERSION_PATTERN.keys()):
            if "qwen3" in key or "qwen2_moe" in key:
                del cm._MODEL_TO_CONVERSION_PATTERN[key]
        logger.info("Disabled qwen2_moe conversion mapping")
    except Exception as e:
        logger.warning(f"Could not disable conversion mapping: {e}")


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def load_model(model_path: str, lora_path: str | None = None, merge: bool = False):
    """Load model with BnB 4-bit + optional PEFT LoRA adapter."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    # Apply patches BEFORE loading
    patch_experts_for_quantization()
    disable_expert_fusing_converter()

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    logger.info(f"Loading tokenizer from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    logger.info(f"Loading model with BnB 4-bit (all on GPU)...")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    logger.info(f"Model loaded in {time.time() - t0:.0f}s")

    vram = torch.cuda.memory_allocated() / 1e9
    logger.info(f"VRAM after base load: {vram:.1f}GB")

    # Apply LoRA adapter if provided
    if lora_path:
        from peft import PeftModel
        logger.info(f"Loading LoRA adapter from {lora_path}...")
        model = PeftModel.from_pretrained(model, lora_path)
        if merge:
            logger.info("Merging LoRA into base weights...")
            model = model.merge_and_unload()
            logger.info("LoRA merged and unloaded")
        else:
            logger.info("Keeping LoRA as active PEFT adapter (no merge)")
        vram = torch.cuda.memory_allocated() / 1e9
        logger.info(f"VRAM with LoRA: {vram:.1f}GB")

    model.eval()
    return model, tokenizer


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
_generate_lock = Lock()


def generate_response(model, tokenizer, messages: list[dict],
                      max_tokens: int = 4096, temperature: float = 0.3) -> dict:
    """Generate a chat completion from messages."""
    import torch

    # Apply chat template — same as training
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    with _generate_lock:
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        input_len = inputs["input_ids"].shape[1]

        t0 = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=max(temperature, 0.01),  # avoid 0.0
                do_sample=temperature > 0.01,
                top_p=0.9 if temperature > 0.01 else 1.0,
                repetition_penalty=1.05,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.time() - t0

        # Decode only the new tokens
        new_tokens = outputs[0][input_len:]
        completion_tokens = len(new_tokens)
        content = tokenizer.decode(new_tokens, skip_special_tokens=True)

        # Strip any residual think tags
        if "</think>" in content:
            content = content.split("</think>", 1)[1]
        content = content.strip()

        # Separate reasoning_content if present
        reasoning = ""
        if "<think>" in content:
            parts = content.split("<think>", 1)
            if "</think>" in parts[1]:
                reasoning = parts[1].split("</think>", 1)[0].strip()
                content = parts[1].split("</think>", 1)[1].strip()

        tokens_per_sec = completion_tokens / elapsed if elapsed > 0 else 0
        logger.info(f"Generated {completion_tokens} tokens in {elapsed:.1f}s ({tokens_per_sec:.1f} tok/s)")

    return {
        "content": content,
        "reasoning_content": reasoning if reasoning else None,
        "completion_tokens": completion_tokens,
        "prompt_tokens": input_len,
        "elapsed_s": elapsed,
    }


# ---------------------------------------------------------------------------
# Flask API (OpenAI-compatible)
# ---------------------------------------------------------------------------
def create_app(model, tokenizer, model_name: str = "hiveai-v3"):
    """Create Flask app with /v1/chat/completions endpoint."""
    from flask import Flask, request, jsonify

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "model": model_name})

    @app.route("/v1/models", methods=["GET"])
    def models():
        return jsonify({
            "data": [{"id": model_name, "object": "model", "owned_by": "hiveai"}]
        })

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        data = request.get_json()
        messages = data.get("messages", [])
        max_tokens = data.get("max_tokens", 4096)
        temperature = data.get("temperature", 0.3)

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        try:
            result = generate_response(model, tokenizer, messages, max_tokens, temperature)
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

        # Build OpenAI-compatible response
        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["content"],
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["prompt_tokens"] + result["completion_tokens"],
            },
        }

        # Include reasoning_content if present (llama-server style)
        if result.get("reasoning_content"):
            response["choices"][0]["message"]["reasoning_content"] = result["reasoning_content"]

        return jsonify(response)

    return app


# ---------------------------------------------------------------------------
# Quick sanity test
# ---------------------------------------------------------------------------
def run_test(model, tokenizer):
    """Quick generation test to verify model works."""
    from hiveai.llm.prompts import CODING_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": CODING_SYSTEM_PROMPT},
        {"role": "user", "content": "Write a Python function that checks if a number is prime. Include type hints and a docstring."},
    ]

    logger.info("Running sanity test...")
    result = generate_response(model, tokenizer, messages, max_tokens=512, temperature=0.3)

    print("\n" + "=" * 60)
    print("SANITY TEST RESULT")
    print("=" * 60)
    print(f"Tokens: {result['completion_tokens']} in {result['elapsed_s']:.1f}s")
    print(f"Speed: {result['completion_tokens'] / result['elapsed_s']:.1f} tok/s")
    print("-" * 60)
    print(result["content"][:2000])
    print("=" * 60)

    if len(result["content"]) < 20:
        logger.error("FAIL: Response too short — model may be broken")
        return False
    if "def " in result["content"] or "prime" in result["content"].lower():
        logger.info("PASS: Response contains expected code/content")
        return True
    else:
        logger.warning("WARN: Response doesn't contain expected keywords")
        print(f"Full response:\n{result['content']}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Serve Qwen3.5-MoE + LoRA via OpenAI API")
    parser.add_argument("--model", default=BASE_MODEL, help="Base model path")
    parser.add_argument("--lora", default=None, help="LoRA adapter directory")
    parser.add_argument("--port", type=int, default=11435, help="Server port")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--name", default="hiveai-v3", help="Model name for API")
    parser.add_argument("--merge", action="store_true", help="Merge LoRA into base (risky with BnB 4-bit + DoRA)")
    parser.add_argument("--test", action="store_true", help="Run sanity test only")
    args = parser.parse_args()

    # Unload Ollama to free VRAM
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": "qwen3:14b", "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Unloaded Ollama model to free VRAM")
    except Exception:
        pass

    # Load model
    model, tokenizer = load_model(args.model, args.lora, merge=args.merge)

    if args.test:
        success = run_test(model, tokenizer)
        sys.exit(0 if success else 1)

    # Start server
    app = create_app(model, tokenizer, args.name)
    logger.info(f"Starting inference server on {args.host}:{args.port}")
    logger.info(f"  Model: {args.model}")
    logger.info(f"  LoRA: {args.lora or 'none'}")
    logger.info(f"  API: http://{args.host}:{args.port}/v1/chat/completions")

    # Use waitress for production-quality serving on Windows
    try:
        from waitress import serve
        logger.info("Using waitress WSGI server")
        serve(app, host=args.host, port=args.port, threads=1)
    except ImportError:
        logger.warning("waitress not installed, using Flask dev server (single-threaded)")
        app.run(host=args.host, port=args.port, threaded=False)


if __name__ == "__main__":
    main()
