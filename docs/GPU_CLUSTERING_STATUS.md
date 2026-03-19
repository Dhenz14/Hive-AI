# GPU Clustering — Honest Status (2026-03-19)

## What Works RIGHT NOW

### Level 1: GPU Pool (both GPUs serve independently)
- Computer A runs Ollama with qwen3:14b → serves requests
- Computer B runs Ollama with qwen3:14b → serves requests
- HivePoA tracks both, load-balances between them
- **Each handles separate requests — doubles throughput for multiple users**
- **Status: WORKS TODAY. No Docker needed.**

### Level 2: Model Splitting (one big model across both GPUs)
- Requires vLLM in Docker — **downloading now (~15GB image)**
- Or Exo — **not available on Windows yet** (needs Linux/macOS)
- **Status: BLOCKED ON VLLM DOWNLOAD**

## The Three Paths to Model Splitting

### Path 1: vLLM + Docker (downloading now)
- ✅ Docker Desktop installed and GPU-enabled
- ⏳ vLLM image downloading (~15GB)
- Once downloaded: `docker compose -f docker-compose.spiritbomb.yml up`
- Computer B joins via Ray: `RAY_HEAD_ADDRESS=192.168.0.101:6379`

### Path 2: Exo (not available on Windows)
- ❌ Requires Rust bindings not compiled for Windows
- ✅ Works great on macOS/Linux
- Best option if either machine runs Linux

### Path 3: llama.cpp RPC (simplest, needs manual build)
- Download llama.cpp from GitHub
- Build with RPC support: `cmake -DGGML_RPC=ON`
- Run rpc-server on Computer B
- Run llama-server on Computer A with `--rpc Computer_B_IP:50052`
- **Lightest weight option but requires building from source**

## Recommended Next Steps

1. Let vLLM download finish (check: `docker images | grep vllm`)
2. Test single-machine vLLM: `docker compose -f docker-compose.spiritbomb.yml up`
3. When Computer B is ready: join the Ray cluster
4. Verify with: open localhost:8100/health

## Meanwhile: Level 1 is Production-Ready

Both GPUs serving independently is already valuable:
- 2x throughput for concurrent users
- Redundancy (one goes down, other keeps serving)
- Both earn HBD rewards
- Dashboard shows both in the community pool
