# Grandma-Proof Deployment Plan

## The Goal

```
1. Install Docker
2. Run: docker compose up
3. Open http://localhost:5001
4. It works. GPU-accelerated AI with 12,000+ knowledge sections.
```

No WSL. No Python. No pip. No llama-server builds. No model downloads.
One command. Works on any machine with Docker + NVIDIA GPU.

## What We Have (90% done)

| File | Status | What it does |
|------|--------|-------------|
| `Dockerfile` | Exists, needs update | Multi-stage Python build, Flask app |
| `docker-compose.yml` | Exists, needs update | Flask + Ollama, GPU support |
| `.dockerignore` | Done | Excludes bloat |
| `requirements.txt` | Done | 22 production packages |
| `.env.example` | Done | 164 lines, every option documented |
| `hiveai/__main__.py` | Done | Gunicorn in production mode |
| `/ready` + `/health` | Done | Health probes for Docker |

## What's Missing (the 10%)

### 1. llama-server in Docker (the big one)

Current setup uses Ollama as the LLM container. But our model stack is:
- Primary: v5-think GGUF via llama-server (port 11435)
- Fallback: Ollama models

**Solution**: Add a `llama-server` service that loads our GGUF.

```yaml
llama-server:
  image: ghcr.io/ggerganov/llama.cpp:server-cuda
  ports:
    - "11435:11435"
  volumes:
    - ./models:/models
  command: >
    --model /models/current_base.gguf
    --port 11435
    --host 0.0.0.0
    --ctx-size 8192
    --flash-attn auto
    -t 12
    --n-gpu-layers 99
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:11435/health"]
    interval: 15s
    timeout: 5s
    start_period: 30s
```

The official `ghcr.io/ggerganov/llama.cpp:server-cuda` image ships with
a pre-built CUDA llama-server binary. No building from source.

### 2. Model download on first run

The GGUF (9.9GB) and embedding models (4.3GB + 2.2GB) can't ship in the
Docker image (too large). Options:

**Option A (recommended): Bind-mount models directory**
```yaml
volumes:
  - ${HIVEAI_MODELS_DIR:-./models}:/models
  - ${HF_CACHE_DIR:-hf-cache}:/root/.cache/huggingface
```
User downloads the GGUF once, points `HIVEAI_MODELS_DIR` at it.
Embedding models auto-download on first run into the HF cache volume.

**Option B (future): Auto-download script**
Add a `scripts/download_models.sh` that pulls the GGUF from HuggingFace:
```bash
huggingface-cli download Dhenz14/hiveai-v5-think --local-dir ./models
```

### 3. First-run setup script

```bash
#!/bin/bash
# scripts/setup.sh — One-time setup for new users
echo "=== HiveAI Setup ==="

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not installed. Get it at https://docker.com"
    exit 1
fi

# Check NVIDIA
if ! docker info 2>/dev/null | grep -q "nvidia"; then
    echo "WARNING: NVIDIA Container Toolkit not detected."
    echo "  Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/"
fi

# Create .env from example
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from template"
fi

# Create models directory
mkdir -p models

# Check for model
if [ ! -f models/current_base.gguf ]; then
    echo ""
    echo "Model not found. Download it:"
    echo "  huggingface-cli download Dhenz14/hiveai-v5-think --local-dir ./models"
    echo ""
    echo "Or copy your existing GGUF to ./models/current_base.gguf"
fi

echo ""
echo "Ready! Run: docker compose up"
echo "Then open: http://localhost:5001"
```

### 4. Iron wall bypass for Docker

The app.py iron wall blocks Windows startup. Docker runs Linux containers,
so `os.name == 'nt'` is False — no bypass needed. The guard only blocks
bare Windows Python execution, which is exactly what we want.

### 5. Database persistence

SQLite DB must survive container restarts:
```yaml
volumes:
  - hiveai-data:/app/data
environment:
  - DATABASE_URL=sqlite:///data/hiveai.db
```

The `/app/data` volume persists all DB state (telemetry, book sections,
training pairs, solved examples) across container lifecycle.

## Updated docker-compose.yml

```yaml
services:
  hiveai:
    build: .
    ports:
      - "5001:5001"
    env_file:
      - .env
    environment:
      - PORT=5001
      - PRODUCTION=1
      - LLM_BACKEND=llama-server
      - LLAMA_SERVER_BASE_URL=http://llama-server:11435
      - OLLAMA_BASE_URL=http://ollama:11434
      - DATABASE_URL=sqlite:///data/hiveai.db
      - RUNTIME_MODE=chat_rag
      - LLM_CTX_SIZE=8192
    volumes:
      - hiveai-data:/app/data
      - hf-cache:/root/.cache/huggingface
    depends_on:
      llama-server:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/ready"]
      interval: 30s
      timeout: 5s
      start_period: 120s
      retries: 3

  llama-server:
    image: ghcr.io/ggerganov/llama.cpp:server-cuda
    ports:
      - "11435:11435"
    volumes:
      - ${HIVEAI_MODELS_DIR:-./models}:/models:ro
    command: >
      --model /models/current_base.gguf
      --port 11435
      --host 0.0.0.0
      --ctx-size 8192
      --flash-attn auto
      -t 12
      --n-gpu-layers 99
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11435/health"]
      interval: 15s
      timeout: 5s
      start_period: 30s
      retries: 3

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped
    profiles:
      - with-ollama

volumes:
  hiveai-data:
  hf-cache:
  ollama-models:
```

Key changes from existing:
- **llama-server** as primary LLM (not Ollama)
- Ollama moved to optional profile (`docker compose --profile with-ollama up`)
- Model directory bind-mounted (not baked into image)
- HF cache persisted as volume (embedding models download once)
- Flask depends on llama-server health (not just "started")
- start_period=120s for Flask (embedding model first-load takes ~60s)

## User Experience Flow

### New User (grandma)
```bash
git clone https://github.com/Dhenz14/Hive-AI.git
cd Hive-AI
bash scripts/setup.sh          # checks docker, creates .env, prompts for model
# ... downloads model to ./models/ ...
docker compose up               # everything starts
# Open http://localhost:5001    # done
```

### Existing User (developer)
```bash
cd Hive-AI
docker compose up --build       # rebuild after code changes
```

### Pool Mode (HivePoA node)
```bash
docker compose up               # same command
# HivePoA discovers this node via /ready endpoint
# Pool routing happens automatically
```

## Checklist

- [x] Dockerfile (multi-stage, production gunicorn)
- [x] docker-compose.yml (Flask + Ollama)
- [x] .dockerignore (clean)
- [x] .env.example (comprehensive)
- [x] __main__.py (gunicorn entrypoint)
- [x] /ready + /health endpoints
- [x] requirements.txt (22 packages)
- [ ] Add llama-server service to docker-compose.yml
- [ ] Add scripts/setup.sh (first-run wizard)
- [ ] Verify ghcr.io/ggerganov/llama.cpp:server-cuda image works
- [ ] Test full docker compose up from clean state
- [ ] Upload v5-think GGUF to HuggingFace for public download
- [ ] Add models/README.md explaining how to get the model
- [ ] Test on a second machine (Computer B)
```
