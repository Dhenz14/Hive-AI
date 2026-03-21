# HiveAI Models

Place your GGUF model file here as `current_base.gguf`.

## Download

```bash
# Option A: HuggingFace CLI
pip install huggingface-hub
huggingface-cli download Dhenz14/hiveai-v5-think --local-dir .

# Option B: Manual
# Copy your GGUF file here and rename to current_base.gguf
```

## Current Model

**v5-think** (Q5_K_M, ~9.9GB)
- Base: Qwen2.5-Coder-14B-Instruct
- Fine-tuned with 5 LoRA merges (golden chain)
- 94.65% on 60-probe eval across 6 domains
- Optimized for code generation, debugging, architecture

## Requirements

- Minimum 10GB VRAM (RTX 3080 or better)
- Recommended: RTX 4070 Ti Super (16GB) or better
