# GPU Clustering — Your Options

## Option A: vLLM + Ray (Docker)
**Best for:** Production, large clusters, expert parallel (MoE models)

```bash
# Computer A (head):
cd Hive-AI
docker compose -f docker-compose.spiritbomb.yml up vllm

# Computer B (worker):
RAY_HEAD_ADDRESS=192.168.0.101:6379 docker compose -f docker-compose.spiritbomb.yml --profile multi-machine up vllm-worker
```

- Requires: Docker + NVIDIA Container Toolkit on both machines
- Supports: PP (pipeline parallel), TP (tensor parallel), EP (expert parallel)
- Models: downloaded from HuggingFace on first run
- Status: Docker image pulling (~15GB)

## Option B: Exo (Native, no Docker)
**Best for:** Quick setup, 2-4 consumer devices, auto-discovery

```bash
# Both computers:
pip install exo
exo run qwen3-14b
```

- No Docker needed
- Auto-discovers peers on LAN
- Ring topology (each device gets a model shard)
- 2.2x scaling measured on 3 devices
- Supports: Qwen, Llama, DeepSeek, Mistral

## Option C: Ollama + load balancing (simplest)
**Best for:** Independent GPUs serving separate requests

```bash
# Computer A: ollama serve (port 11434)
# Computer B: ollama serve (port 11434)
# Load balancer routes requests round-robin
```

- No model splitting — each GPU runs full model independently
- Doubles throughput for multiple concurrent users
- Simplest setup, works today

## Which to choose?

| Need | Best option |
|------|-------------|
| Quick test with 2 PCs | Option C (already works) |
| Split a 32B model across 2 GPUs | Option A (vLLM) or B (Exo) |
| 4+ consumer devices | Option B (Exo) |
| Production cluster | Option A (vLLM + Ray) |
