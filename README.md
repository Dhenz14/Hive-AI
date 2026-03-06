# HiveAI Knowledge Refinery

## What is it?

HiveAI Knowledge Refinery is an AI-powered research system that autonomously discovers authoritative web sources, extracts structured knowledge into a persistent graph, generates polished "Golden Book" reference documents, and publishes them immutably to the Hive blockchain. It then distills this knowledge into LoRA adapters — compressed skill artifacts that encode the *ability to produce knowledge*, not just stored facts.

It operates fully offline with Ollama — no API keys required — while seamlessly scaling to high-performance configurations with async job queues, automatic hardware tuning, and incremental knowledge graph updates. The system features merge cycling (progressive LoRA training), MoLoRA domain routing, a secure code sandbox, and a Decentralized Brain Collective (DBC) for on-chain knowledge sharing.

---

## Features

### Research Pipeline
- **URL Discovery** — Intelligent source discovery using DuckDuckGo, Brave Search API, and SearXNG with LLM-powered fallback for offline operation
- **Mass Web Crawling** — Asynchronous browser automation via Playwright with JavaScript rendering, page caching (configurable TTL), and automatic retry logic
- **Semantic Chunking** — Intelligent content splitting with embedding-based topic boundary detection (or fast semchunk fallback)
- **Chain-of-Thought Extraction** — Multi-step LLM reasoning: claim identification → atomic facts → confidence assessment → triple generation with full justification

### Knowledge Graph
- **Triples with Attribution** — Subject-predicate-object triples linked to source chunks, crawled pages, and confidence scores
- **Entity Resolution** — Normalizes aliases (JavaScript→JS, Machine Learning→ML) and deduplicates entities using embedding similarity
- **Contradiction Detection** — Identifies opposing predicates and numeric conflicts, resolves by confidence score
- **Community Detection** — Louvain clustering groups related triples into topic communities with LLM-generated summaries for cohesive broad-topic answering
- **GraphRAG Integration** — Persistent, incremental knowledge graph with full traceability and community-based context compression

### Golden Books
- **Multi-Step Generation** — Automated outline creation → prose writing with outline context → coherence review → conditional rewrite for quality
- **Quality Scoring** — Five-dimension automatic evaluation with auto-rewrite for low-quality output
- **Cross-Book Referencing** — Maintains context relationships across multiple generated books
- **Semantic Novelty Filtering** — Detects and excludes redundant content across existing books

### AI Chat ("Ask the Keeper")
- **Multi-Hop RAG** — Three-stage retrieval: semantic vector search → entity extraction for second-hop search → cross-encoder reranking
- **Semantic Vector Search** — HNSW-indexed pgvector (server) or numpy cosine similarity (local) with context-aware embeddings
- **Cross-Encoder Reranking** — ms-marco-MiniLM-L-6-v2 model dramatically improves result relevance after initial retrieval
- **GraphRAG Context** — Leverages community summaries for broader topical questions
- **Auto-Learn** — Detects knowledge gaps and automatically triggers background research jobs, re-answers with new knowledge when available
- **Code Self-Verification** — Code blocks in chat responses are executed in a secure sandbox before returning to the user, catching runtime errors before they reach you
- **MoLoRA Domain Routing** — Automatic domain detection routes queries to specialized models (Python, Hive, JavaScript, Rust, etc.) when enabled

### LoRA Training Pipeline
- **Self-Distillation** — 16 prompt templates generate training pairs from the model's own knowledge (standard + O1-style reasoning)
- **Claude Opus Distillation** — 4,500+ expert-curated training pairs across 560+ batch files covering 80+ technical domains (Python, TypeScript, React, CSS, DevOps, databases, security, ML/AI, system design, compilers, distributed systems, and more). Loaded dynamically via `scripts/claude_distill_v2.py`
- **Thinking-Trace Curriculum** — 1,638 thinking-trace training pairs with `<think>` blocks across 4 cognitive phases: Foundation (434 pairs: debugging, security, performance, architecture, testing, concurrency, data modeling), Advanced (401 pairs: backtracking, adversarial self-testing, analogical reasoning, tradeoffs, uncertainty), Meta-Cognition (403 pairs: reasoning quality, confidence calibration, Socratic method, learning from mistakes, code quality judgment), and Autonomy (400 pairs: training data generation, self-evaluation, curriculum design, meta-learning, autonomous improvement, quality assurance). Target mix: 72% direct-answer + 28% thinking-trace
- **Self-Improvement Pipeline** — Autonomous "get smarter" loop: self-eval → data generation → QLoRA training → GGUF export → validation. Includes LoRA bank, curriculum meta-learning, error-driven learning, and online distillation (p400-p407 batch series)
- **Genetic Expansion** — Mutation operators (rephrase, constrain, generalize, error-inject, multi-step) expand top pairs for data diversity
- **Quality Scoring v5** — Multi-dimensional scoring with code quality cap (0.35), no-code gate, MIN_CODE_BLOCKS requirement, and tiered dedup (exact/paraphrase/near)
- **Merge Cycling** — Train LoRA → merge into base → train new LoRA on improved base → repeat. Each cycle bakes specialization deeper into core weights
- **MoLoRA (Mixture of LoRA Experts)** — Domain-specialized LoRAs with intelligent keyword-based query routing. Each domain gets its own merged Ollama model with graceful fallback to the generalist
- **Eval System** — 115 coding challenges (100 general + 15 Hive-specific) across 4 dimensions: code correctness (30%), test quality (30%), conceptual depth (20%), explanation (20%)
- **Model Benchmark Harness** — 12-task harness across 4 categories (single-shot generation, refactoring, debugging, context retention) measuring tokens/sec, TTFT, VRAM, speculative decoding acceptance rate, and task success. Built-in model comparison mode
- **Multi-Backend Serving** — Ollama for standard models, llama-server for LoRA adapters, OpenRouter for cloud models. Automatic routing via `smart_call()`

### Blockchain Publishing
- **Hive Blockchain Integration** — Publishes Golden Books to Hive with configurable multipart splitting for large content
- **Tagged Organization** — Namespace-based tagging (archivedcontenthaf, hiveaiknowledgehaf) for discoverability
- **Immutable Timestamping** — Permanent, verifiable record on distributed ledger with full source attribution

### Decentralized Brain Collective (DBC)
- **On-Chain Knowledge Sharing** — Nodes propose and vote on training pairs via Hive custom_json operations
- **HP-Weighted Consensus** — Hive Power-weighted voting prevents sybil attacks; epoch-based timeout ensures liveness
- **Pair Encoding** — Gzip + base64 encoding fits training pairs into Hive's custom_json size limits
- **Secrets Scanner** — 10-pattern scanner prevents accidental credential leaks in training data
- **RC Hysteresis** — Automatically pauses operations when Resource Credits drop below floor, resumes when recovered
- **HivePoA Storage** — IPFS + GitHub Releases fallback for large adapter files with resume-capable downloads

### Local-First Operation
- **Ollama Support** — Fully offline operation using Ollama with Qwen3, Phi-4, or any compatible model
- **Hardware Auto-Detection** — Automatic profile selection (low/medium/high) based on CPU and RAM
- **Configurable Embedding Models** — BAAI/bge-m3, Qwen3-Embedding, or any sentence-transformers model with single-command re-embedding
- **Confidence Routing** — `smart_call()` classifies query difficulty → routes trivial/simple queries to fast model, complex ones to reasoning model. 60-70% of queries use the fast model.
- **Zero External Dependencies** — Optional search APIs (Serper.dev, Brave) but fully functional without them

### Secure Code Sandbox
- **Safe Execution** — Python and JavaScript code runs in isolated subprocesses with timeouts, resource limits, and restricted imports
- **Chat Verification** — When enabled (`CHAT_VERIFY_CODE=true`), all code in chat responses is executed before delivery, catching syntax and runtime errors

### Job Queue & Scaling
- **Async Background Processing** — SQLAlchemy-based queue with automatic worker threads
- **Batch Job Creation** — Create hundreds of research jobs in a single request
- **Pause/Resume** — Pause entire queue without losing progress, resume seamlessly
- **Per-Job Cancellation** — Cancel individual jobs mid-pipeline with cleanup
- **Progress Tracking** — Real-time status, stage transitions, and error logging per job

---

## Quick Start (Windows)

### 1. Install Prerequisites

- **Python 3.11+** — Download from [python.org](https://www.python.org/downloads/). During install, check "Add Python to PATH".
- **Git** — Download from [git-scm.com](https://git-scm.com/download/win)
- **Ollama** — Download from [ollama.com](https://ollama.com/download/windows). This runs AI models locally on your PC.

### 2. Clone & Install

```cmd
git clone https://github.com/YOUR-USERNAME/hiveai-knowledge-refinery.git
cd hiveai-knowledge-refinery
setup.bat
```

### 3. Pull AI Models

Open a separate terminal and pull the models Ollama will use:

```cmd
ollama pull qwen3:14b
ollama pull qwen3:8b
```

These are the sweet spot defaults (32GB RAM). For 16GB RAM PCs, use smaller models:
```cmd
ollama pull qwen3:8b
ollama pull qwen3:4b
```
Then update `.env`:
```
OLLAMA_MODEL_REASONING=qwen3:8b
OLLAMA_MODEL_FAST=qwen3:4b
```

### 4. Run

```cmd
run.bat
```

Open your browser to **http://localhost:5001** — that's it! Fully local, no API keys, no cloud dependencies.

---

## Quick Start (Linux / macOS)

### Prerequisites
- Python 3.11+
- Git
- Ollama (recommended) or OpenRouter API key

### Installation

```bash
git clone https://github.com/YOUR-USERNAME/hiveai-knowledge-refinery.git
cd hiveai-knowledge-refinery
chmod +x setup.sh && ./setup.sh
```

### Configuration

```bash
cp .env.example .env
nano .env
```

### Run

```bash
./run.sh
```

Open your browser to **http://localhost:5001**

---

## Local-First Mode (No API Keys — Recommended)

HiveAI is designed to run fully locally on your own hardware. No cloud accounts, no API keys, no subscriptions.

### Setup Ollama

1. **Install Ollama**
   - **Windows**: Download from [ollama.com/download/windows](https://ollama.com/download/windows)
   - **macOS**: `brew install ollama` or download from [ollama.com](https://ollama.com)
   - **Linux**: `curl -fsSL https://ollama.com/install.sh | sh`

2. **Pull Models** (adjust based on your RAM — see sweet spot table below)
   ```bash
   ollama pull qwen3:14b   # Reasoning model — sweet spot (32GB RAM)
   ollama pull qwen3:8b    # Fast model
   ```

3. **Configure HiveAI** (`.env`)
   ```ini
   DATABASE_URL=sqlite:///hiveai.db
   LLM_BACKEND=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL_REASONING=qwen3:14b
   OLLAMA_MODEL_FAST=qwen3:8b
   ```

4. **Start HiveAI**
   ```bash
   python -m hiveai.app
   ```

That's it — fully offline operation with zero API keys, zero cloud dependencies, and all data stays on your machine.

### Recommended Models by Hardware (Sweet Spot Guide)

The system uses two model tiers. The **reasoning model** does the heavy lifting — knowledge extraction (the actual gold mining) and book writing. The **fast model** handles lighter tasks like outlines, reviews, and summaries.

| RAM | Reasoning Model | Fast Model | Quality | Notes |
|-----|----------------|------------|---------|-------|
| 8 GB | `qwen3:4b` | `qwen3:1.7b` | Basic | Works but slower, less accurate extraction |
| 16 GB | `qwen3:8b` | `qwen3:4b` | Good | Solid quality for most topics |
| **32 GB** | **`qwen3:14b`** | **`qwen3:8b`** | **Sweet spot** | **Best quality-per-compute ratio (default)** |
| 64 GB+ | `qwen3:32b` | `qwen3:14b` | Diminishing returns | Marginally better, significantly slower |

Going beyond 32GB/14b is like panning for gold and getting mostly pebbles — the quality improvement per extra compute drops off sharply.

### Extraction Quality

By default, HiveAI uses the reasoning model for knowledge extraction (`EXTRACTION_QUALITY=high`). This means your strongest model does the actual fact-mining, which is where quality matters most. Set `EXTRACTION_QUALITY=standard` if you prefer faster processing with the lighter model.

### GPU Acceleration

Ollama automatically uses your GPU if available. NVIDIA GPUs with 8GB+ VRAM significantly speed up inference. No extra configuration needed — Ollama handles it automatically.

---

## Cloud Mode (OpenRouter — Optional)

For access to cutting-edge models like Qwen3-30B, Phi-4, Claude, etc. without local GPU:

### Setup OpenRouter

1. **Get API Key** — Create account and get key at [openrouter.ai/keys](https://openrouter.ai/keys)

2. **Configure HiveAI** (`.env`)
   ```ini
   LLM_BACKEND=openrouter
   AI_INTEGRATIONS_OPENROUTER_API_KEY=sk-or-v1-your-key-here
   AI_INTEGRATIONS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   ```

3. **Optional Search APIs**
   ```ini
   SERPER_API_KEY=your-key-here
   BRAVE_API_KEY=your-key-here
   ```

---

## LoRA Training

HiveAI trains LoRA adapters that compress coding knowledge into lightweight model extensions. The pipeline supports multiple training versions, merge cycling, and domain-specialized models.

### Training in WSL2

LoRA training requires GPU access. On Windows, use WSL2 with an Ubuntu distro:

```bash
# Enter WSL2
wsl -d Ubuntu-24.04

# Activate training environment
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project

# Prepare training data (the bridge)
python scripts/prepare_v5_data.py --export --stats

# Train (Qwen 2.5 Coder LoRA)
python scripts/train_v5.py 2>&1 | tee logs/train_v5.log
```

### Merge Cycling

After training, merge the LoRA into the base model to create an improved foundation for the next training cycle:

```bash
# Merge v5 adapter into base (creates models/qwen2.5-coder-7b-cycle1)
python scripts/auto_cycle.py --adapter loras/v5 --deploy --eval

# View merge history
python scripts/auto_cycle.py --history
```

### Domain-Specialized Training

Train domain experts from filtered training data:

```bash
# See available domains
python scripts/train_domain.py --list

# Train Python specialist
python scripts/train_domain.py --domain python --dry-run

# Deploy domain model to Ollama
python scripts/deploy_domain.py --domain python
```

### MoLoRA Routing

Enable domain-based routing to automatically send queries to specialized models:

```ini
# In .env
MOLORA_ENABLED=true
MOLORA_DEFAULT_DOMAIN=general
```

When enabled, `smart_call()` classifies each query's domain (Python, Hive, JavaScript, Rust, etc.) and routes it to the matching specialized model. Falls back to the generalist model if a domain model isn't available.

### Eval System

Evaluate model quality with 115 coding challenges:

```bash
# Eval against Ollama model
python scripts/run_eval.py --model qwen3:14b

# Eval against llama-server (LoRA adapter)
python scripts/run_eval.py --base-url http://localhost:11435

# Compare with baseline
python scripts/run_eval.py --model hiveai-v5 --compare qwen3:14b
```

### Model Benchmark Harness

Benchmark coding models across 4 task categories with detailed performance metrics:

```bash
# Benchmark a single model
python -m bench.run_bench --model qwen2.5-coder:14b-q5_K_M

# Head-to-head comparison
python -m bench.run_bench --model qwen3.5:9b --compare qwen2.5-coder:14b-q5_K_M

# Speculative decoding via llama-server
python -m bench.run_bench --model qwen2.5-coder-14b --backend llama-server --draft qwen2.5-coder-1.5b

# Run specific category only
python -m bench.run_bench --model qwen3.5:9b --category single_shot debug
```

**Categories**: single-shot generation (5 tasks), refactoring (2), debugging (3), context retention (2)
**Metrics**: score, pass rate, tokens/sec, time-to-first-token, VRAM peak, speculative decoding acceptance rate

Results are saved as timestamped JSON in `bench/results/` for tracking improvements across training cycles.

### LoRA Version History

| Version | Base Model | Status | Pairs | Eval Score | Notes |
|---------|-----------|--------|-------|------------|-------|
| v1 | Qwen3-14B | Ready | 1,104 | 0.853 (+15%) | First successful training, proven |
| v1.5 | Qwen3-14B | Cancelled | — | — | Superseded by v2 |
| v2 | Qwen3.5-35B-A3B | Killed | — | — | Superseded by v3 |
| v3 | Qwen3.5-35B-A3B (pruned) | Failed | 2,385 | — | Gate-expert alignment bug |
| v4 | Qwen3.5-35B-A3B (pruned) | Blocked | 2,414 | — | MoE-aware ESFT + KL-anchored SFT |
| v5 | Qwen2.5-Coder-7B | Ready to Train | 6,176 | — | 5,596 unique pairs + Hive 2x oversample, thinking curriculum, DoRA r=16, KL-anchored SFT |

#### Claude Opus Distillation Corpus

The project includes 4,500+ expert-curated training pairs distilled from Claude Opus 4.6, organized across 560+ batch files in `scripts/distill_batches/`. These break into two categories:

**Direct-Answer Pairs (~2,900 pairs):** Cover 80+ domains including Python stdlib, async patterns, TypeScript, React, CSS, DevOps, databases, authentication, AI/ML (GRPO, DPO, RAG, multi-agent systems, speculative decoding, federated learning), system design, compilers, distributed systems, security, and an autonomous self-improvement pipeline (p400-p407: self-training loops, QLoRA, self-eval/reward, GGUF optimization, meta-learning, error-driven learning, online distillation, and the "get smarter" orchestrator).

**Thinking-Trace Pairs (1,638 pairs):** A 4-phase cognitive curriculum teaching step-by-step reasoning via `<think>` blocks:
- **Phase 1 — Foundation (434 pairs):** Systematic debugging, security analysis, performance optimization, architecture design, code review, testing strategy, concurrency/distributed systems, data modeling/DevOps
- **Phase 2 — Advanced (401 pairs):** Backtracking & dead-end recovery, adversarial self-testing, analogical reasoning, multi-perspective analysis, first-principles reasoning, tradeoff analysis, uncertainty reasoning
- **Phase 3 — Meta-Cognition (403 pairs):** Reasoning quality evaluation, confidence calibration, Socratic method, context switching, learning from mistakes, code quality judgment
- **Phase 4 — Autonomy (400 pairs):** Training data generation, self-evaluation, curriculum design, meta-learning, autonomous improvement, quality assurance, integration

Target training mix: 72% direct-answer + 28% thinking-trace. The data bridge (`scripts/prepare_v5_data.py`) loads all sources, deduplicates, quality-filters, enforces the mix ratio, orders thinking pairs by curriculum phase (Foundation first, Autonomy last), interleaves them throughout direct-answer pairs, and exports as `v5.jsonl` ready for `train_v5.py`. See `scripts/distill_batches/THINKING_CURRICULUM.md` for the full curriculum plan.

---

## Configuration Reference

### Required Settings

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | Database connection (PostgreSQL or SQLite) | `postgresql://user:pass@localhost:5432/hiveai` or `sqlite:///hiveai.db` |

### LLM Backend

| Variable | Options | Default |
|----------|---------|---------|
| `LLM_BACKEND` | `auto`, `ollama`, `openrouter` | `auto` |
| `OLLAMA_BASE_URL` | Local Ollama URL | `http://localhost:11434` |
| `OLLAMA_MODEL_REASONING` | Reasoning model name | `qwen3:14b` |
| `OLLAMA_MODEL_FAST` | Fast model name | `qwen3:8b` |
| `EXTRACTION_QUALITY` | `high` or `standard` | `high` |
| `AI_INTEGRATIONS_OPENROUTER_API_KEY` | OpenRouter key | (blank) |

### llama-server (LoRA Adapter Serving)

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLAMA_SERVER_BASE_URL` | llama-server endpoint | `http://localhost:11435` |
| `LLAMA_SERVER_MODELS` | Comma-separated model names routed to llama-server | `hiveai-v1,hiveai-v1.5,hiveai-v2` |
| `LLAMA_SERVER_MODEL` | Currently active llama-server model | `hiveai-v1` |

### MoLoRA (Domain Routing)

| Variable | Purpose | Default |
|----------|---------|---------|
| `MOLORA_ENABLED` | Enable domain-based model routing | `false` |
| `MOLORA_DEFAULT_DOMAIN` | Default domain when no match | `general` |

### Embedding & Semantics

| Variable | Purpose | Default |
|----------|---------|---------|
| `EMBEDDING_MODEL` | Embedding model | `BAAI/bge-m3` |
| `SEMANTIC_SIMILARITY_THRESHOLD` | Duplicate detection (0.0-1.0) | `0.82` |
| `HNSW_EF_SEARCH` | pgvector search accuracy | `100` |
| `SEMANTIC_CHUNKING` | Embedding-based chunking | `false` |

### Quality Gates

| Variable | Purpose | Default |
|----------|---------|---------|
| `MIN_TRAINING_QUALITY` | Minimum quality for training pairs | `0.80` |
| `LORA_EXPORT_QUALITY` | Minimum quality for LoRA export | `0.75` |
| `MIN_CODE_BLOCKS` | Minimum code blocks required per pair | `1` |
| `DEDUP_EXACT_THRESHOLD` | Exact duplicate threshold | `0.95` |
| `DEDUP_PARAPHRASE_THRESHOLD` | Paraphrase duplicate threshold | `0.85` |
| `DEDUP_NEAR_THRESHOLD` | Near-duplicate threshold | `0.75` |

### Chat & Sandbox

| Variable | Purpose | Default |
|----------|---------|---------|
| `CHAT_VERIFY_CODE` | Execute code blocks before returning to user | `true` |

### DBC (Decentralized Brain Collective)

| Variable | Purpose | Default |
|----------|---------|---------|
| `DBC_ENABLED` | Enable on-chain knowledge sharing | `false` |
| `DBC_ACCOUNT` | Hive account for broadcasting | (blank) |
| `DBC_POSTING_KEY` | Hive posting key | (blank) |
| `DBC_MIN_ONCHAIN_QUALITY` | Minimum quality for on-chain pairs | `0.85` |
| `DBC_EPOCH_TIMEOUT_HOURS` | Voting epoch timeout | `24` |
| `DBC_RC_FLOOR_PERCENT` | RC floor for hysteresis pause | `20` |
| `DBC_RC_RESUME_PERCENT` | RC level to resume operations | `50` |

### Hardware Profile

| Variable | Options | Auto-Detection |
|----------|---------|-----------------|
| `HARDWARE_PROFILE` | `auto`, `low`, `medium`, `high` | ≥12GB RAM + ≥6 CPU → `high`; ≥6GB RAM + ≥3 CPU → `medium`; else → `low` |

### Performance Tuning

| Variable | Purpose | Low | Medium | High |
|----------|---------|-----|--------|------|
| `CRAWL_WORKERS` | Concurrent crawl threads | 2 | 4 | 8 |
| `LLM_WORKERS` | Concurrent extraction threads | 1 | 2 | 4 |
| `EMBEDDING_BATCH_SIZE` | Batch size for embeddings | 8 | 16 | 32 |
| `MAX_CRAWL_PAGES` | URLs per research job | 5 | 10 | 20 |
| `DB_POOL_SIZE` | DB connection pool | 3 | 5 | 8 |

### Search APIs (Optional)

| Variable | Purpose | Get Key |
|----------|---------|---------|
| `SERPER_API_KEY` | Real web search URL discovery | [serper.dev](https://serper.dev) |
| `BRAVE_API_KEY` | Brave Search (2000/month free) | [brave.com/search/api](https://brave.com/search/api/) |

### Caching & Limits

| Variable | Purpose | Default |
|----------|---------|---------|
| `CRAWL_CACHE_TTL_HOURS` | Cached page expiry | `168` (7 days) |
| `MAX_RAW_CONTENT_SIZE` | Max chars per page | `100000` |
| `MAX_CHUNK_TEXT_FOR_LLM` | Max chars per LLM batch | `15000` |

See `.env.example` for complete reference.

---

## Hardware Requirements

### Local Desktop (Recommended for Personal Use)
- **CPU**: 4+ cores
- **RAM**: 16 GB (8 GB minimum)
- **GPU**: Optional — NVIDIA with 8GB+ VRAM for faster LLM inference
- **Storage**: 10 GB (+ model weights)
- **Database**: SQLite (automatic, no setup)
- **LLM**: Ollama with qwen3:8b
- **Profile**: `medium` or `high` (auto-detected)

### LoRA Training (WSL2 on Windows)
- **GPU**: NVIDIA with 16GB+ VRAM (RTX 4070 Ti SUPER or better)
- **RAM**: 32GB+ system RAM
- **WSL2**: Ubuntu 24.04 with CUDA support
- **Python**: 3.11+ with PyTorch, transformers, peft, trl, bitsandbytes
- **Storage**: 50GB+ for model weights and training data

### Cloud / Server (Production)
- **CPU**: 2+ vCPU
- **RAM**: 2+ GB
- **Storage**: 50+ GB
- **Database**: PostgreSQL 13+ with pgvector
- **LLM**: OpenRouter API
- **Profile**: `medium` or `high` (auto-detected)

### Hardware Profile Auto-Detection

| Profile | CPU | RAM | Crawl Workers | LLM Workers |
|---------|-----|-----|---------------|-------------|
| `low` | 1-2 | < 6 GB | 2 | 1 |
| `medium` | 3-5 | 6-12 GB | 4 | 2 |
| `high` | 6+ | 12+ GB | 8 | 4 |

Override with `HARDWARE_PROFILE` environment variable.

---

## API Endpoints

### Job Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/jobs` | Create single research job |
| `POST` | `/api/jobs/batch` | Batch create multiple research jobs |
| `GET` | `/api/jobs` | List all jobs (last 50) |
| `GET` | `/api/jobs/<id>` | Get job details and stats |
| `GET` | `/api/jobs/<id>/stream` | Stream job progress (chunks, triples, book) |
| `POST` | `/api/jobs/<id>/cancel` | Cancel a running job |

### Queue Control

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/queue/status` | Queue status and worker health |
| `POST` | `/api/queue/pause` | Pause all processing |
| `POST` | `/api/queue/resume` | Resume all processing |

### Chat & RAG

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/chat` | Chat with knowledge base (multi-hop RAG) |

### Knowledge Graph

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/graph` | Global knowledge graph statistics |
| `POST` | `/api/graph/rebuild` | Rebuild communities and summaries |

### System Info

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/hardware` | Hardware profile and detected resources |
| `GET` | `/api/llm-status` | Active LLM backend, Ollama availability |
| `GET` | `/api/embedding-status` | Current embedding model, mismatch detection |
| `POST` | `/api/reembed` | Re-embed all content after model switch |

### Book Publishing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/books/<id>/publish` | Publish Golden Book to Hive |
| `POST` | `/api/books/<id>/rewrite` | Force quality rewrite |

---

## Architecture

### Data Flow

```
URL Discovery
    ↓ (DuckDuckGo, Brave, SearXNG, LLM)
Mass Web Crawl
    ↓ (Playwright with caching)
Chunk & Clean
    ↓ (Semantic or fast chunking)
Triple Extraction
    ↓ (Chain-of-thought LLM reasoning)
Entity Resolution & Contradiction Detection
    ↓
Knowledge Graph
    ↓
Golden Book Generation
    ↓ (Outline → Write → Review → Rewrite)
Quality Scoring
    ↓
Training Pair Generation
    ↓ (Self-distillation + genetic expansion)
LoRA Training
    ↓ (Merge cycling: train → merge → repeat)
Model Deployment
    ↓ (Ollama / llama-server)
Blockchain Publishing
    ↓ (Hive + IPFS for LoRA weights)
Immutable Record
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | Flask | REST API and dashboard UI |
| **Database** | SQLite or PostgreSQL + pgvector | Triples, embeddings, content storage |
| **LLM** | Ollama / llama-server / OpenRouter | Reasoning, extraction, writing, chat |
| **Embeddings** | sentence-transformers | Vector search, semantic similarity |
| **Web Scraping** | crawl4ai (Playwright) | JavaScript-aware page extraction |
| **Graph Analysis** | NetworkX, Louvain | Community detection and summaries |
| **Job Queue** | SQLAlchemy + threading | Async pipeline orchestration |
| **LoRA Training** | PEFT, transformers, trl | Fine-tuning with merge cycling |
| **Code Sandbox** | subprocess (isolated) | Safe Python/JS execution |
| **Blockchain** | Hive RPC (beem) | Immutable publishing + DBC |
| **Domain Router** | MoLoRA | Keyword-based query→model routing |

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Language** | Python 3.11+ |
| **Web Framework** | Flask |
| **Database** | SQLite (local) or PostgreSQL 13+ with pgvector (production) |
| **LLM Backends** | Ollama, llama-server (LoRA), OpenRouter (Claude, Qwen3, Phi-4) |
| **Embeddings** | sentence-transformers (BAAI/bge-m3, Qwen3-Embedding) |
| **Web Scraping** | crawl4ai (Playwright) |
| **Graph Computing** | NetworkX, Louvain (community detection) |
| **Chunking** | semchunk (fast) or embedding-based (precise) |
| **Structured LLM** | instructor (JSON schema validation) |
| **Vector Search** | pgvector HNSW (PostgreSQL) or numpy cosine (SQLite) |
| **LoRA Training** | PEFT, transformers, trl, bitsandbytes (WSL2 + CUDA) |
| **Job Queue** | SQLAlchemy ORM + threading |
| **Blockchain** | Hive RPC nodes (beem, direct RPC, lighthive) |
| **Model Serving** | Ollama, llama.cpp (llama-server) |

---

## File Structure

```
hiveai-knowledge-refinery/
├── hiveai/
│   ├── app.py                 # Flask web server + dashboard
│   ├── config.py              # Configuration, hardware detection, quality gates
│   ├── hardware.py            # Hardware profile auto-detection
│   ├── models.py              # SQLAlchemy ORM (TrainingPair, LoraVersion, ChatFeedback, etc.)
│   ├── chat.py                # Multi-hop RAG chat pipeline with auto-learn
│   ├── sandbox.py             # Secure code execution sandbox (Python + JS)
│   ├── vectorstore.py         # Vector search (pgvector / numpy cosine)
│   ├── llm/
│   │   ├── client.py          # LLM routing (Ollama/llama-server/OpenRouter), smart_call(), MoLoRA
│   │   └── prompts.py         # System prompts, Golden Book templates, CODING_SYSTEM_PROMPT
│   ├── lora/
│   │   ├── distiller.py       # 16 prompt templates, scorer v5, self-refinement, genetic expansion
│   │   ├── trainer.py         # LoRA training wrapper (r=32 standard / r=8 micro, DoRA)
│   │   ├── adapter_manager.py # Runtime multi-LoRA hot-swap
│   │   ├── merge_cycle.py     # Merge cycling orchestrator (train → merge → repeat)
│   │   ├── molora.py          # MoLoRA domain router (7 domains, keyword scoring)
│   │   ├── brain_export.py    # IPFS pinning + Hive LoRA publication
│   │   ├── exporter.py        # Golden Books → JSONL training pairs
│   │   ├── dedup.py           # Embedding-based deduplication gate
│   │   ├── benchmark.py       # Held-out evaluation harness
│   │   └── miner.py           # Multi-source training pair miner
│   ├── dbc/
│   │   ├── chain.py           # Hive blockchain abstraction, pair encoding, protocol logic
│   │   ├── node.py            # DBC node daemon with MockChain for testing
│   │   └── hivepoa.py         # IPFS/GitHub adapter storage client
│   ├── pipeline/
│   │   ├── url_discovery.py   # Source discovery (DuckDuckGo, Brave, SearXNG)
│   │   ├── crawler.py         # Web crawling with caching
│   │   ├── cleaner.py         # Text cleaning and normalization
│   │   ├── reasoner.py        # Chain-of-thought triple extraction
│   │   ├── entity_resolver.py # Alias normalization and deduplication
│   │   ├── contradiction.py   # Contradiction detection
│   │   ├── communities.py     # Louvain clustering and summaries
│   │   ├── writer.py          # Golden Book generation pipeline
│   │   ├── scorer.py          # Quality scoring (v5)
│   │   ├── publisher.py       # Hive blockchain publishing
│   │   ├── queue_worker.py    # Async job orchestration
│   │   └── orchestrator.py    # High-level pipeline coordinator
│   ├── storage/
│   │   └── graph_store.py     # Knowledge graph persistence
│   ├── hive_templates/        # Ready-to-use Hive app scaffolding
│   │   ├── social_app/        # Blog/social app (JS + Python)
│   │   ├── voting_bot/        # Automated curation bot
│   │   ├── token_app/         # Hive Engine token operations
│   │   ├── haf_indexer/       # HAF blockchain indexer
│   │   └── keychain_auth/     # Hive Keychain authentication
│   └── templates/             # Jinja2 HTML templates
│       ├── dashboard.html     # System dashboard with merge cycle stats
│       ├── chat.html          # Chat UI with domain badges
│       ├── forge.html         # Training management
│       ├── eval.html          # Eval results viewer
│       ├── graph_explorer.html
│       ├── job_detail.html
│       └── book_review.html
├── scripts/
│   ├── run_eval.py            # 115-challenge eval harness
│   ├── train_v5.py            # LoRA v5 training (dense Qwen3.5-9B)
│   ├── deploy_v5.py           # Post-training deployment (merge → GGUF → Ollama)
│   ├── auto_cycle.py          # Merge cycling CLI
│   ├── train_domain.py        # Domain-filtered training wrapper
│   ├── deploy_domain.py       # Domain adapter deployment
│   ├── download_model.sh      # Reliable model download (XET-safe)
│   ├── prepare_v5_data.py     # v5 data preparation
│   ├── calibrate_eval.py      # Eval anchor calibration
│   ├── claude_distill.py      # Claude distillation pipeline (v1)
│   ├── claude_distill_v2.py   # Claude Opus distillation v2 (batch loader for all pairs)
│   ├── distill_batches/       # 560+ batch files: 2,900 direct-answer + 1,638 thinking-trace pairs
│   ├── fix_broken_batches.py  # Batch file repair utility (triple-quote conflict resolution)
│   ├── distill_multilang.py   # Multi-language distillation support
│   ├── mine_hive_knowledge.py # Hive-specific pair mining
│   ├── distill_supervisor.py  # Continuous distillation manager
│   └── setup_check.py         # First-run environment validator
├── bench/
│   ├── run_bench.py           # Model benchmark CLI (compare models, track regressions)
│   ├── runner.py              # Ollama + llama-server backends, VRAM monitoring, spec decode
│   ├── tasks.py               # 12 tasks across 4 categories with automatic evaluators
│   └── results/               # Timestamped JSON benchmark results
├── evals/
│   └── anchors/               # 18 domain-specific eval anchor sets
├── loras/
│   ├── training_data/         # JSONL training datasets (v1-v5, DBC, MoE)
│   ├── v1/                    # LoRA v1 adapter (Qwen3-14B) — proven
│   ├── v2/                    # LoRA v2 adapter (Qwen3.5-35B-A3B) — killed
│   └── domains/               # Domain-specialized adapters (MoLoRA)
├── models/                    # Local model weights
├── Dockerfile                 # Multi-stage container build
├── docker-compose.yml         # Full stack (app + Ollama + GPU)
├── BLUEPRINT.md               # LoRA pipeline architecture plan
├── .env.example               # Configuration template
├── pyproject.toml             # Python project metadata
├── requirements.txt           # Python dependencies
├── LICENSE                    # MIT License
└── README.md                  # This file
```

---

## Usage Examples

### Create a Research Job

```bash
curl -X POST http://localhost:5001/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"topic": "Quantum Machine Learning 2025"}'
```

### Batch Create Jobs

```bash
curl -X POST http://localhost:5001/api/jobs/batch \
  -H "Content-Type: application/json" \
  -d '{
    "topics": [
      "Artificial General Intelligence",
      "Quantum Computing",
      "Biological Neural Networks"
    ]
  }'
```

### Monitor Queue

```bash
curl http://localhost:5001/api/queue/status
```

### Chat with Knowledge Base

```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest advances in quantum computing?",
    "history": []
  }'
```

### Check System Status

```bash
# Hardware profile
curl http://localhost:5001/api/hardware

# LLM backend
curl http://localhost:5001/api/llm-status

# Embedding model
curl http://localhost:5001/api/embedding-status
```

---

## Deployment

### Windows Desktop

```cmd
run.bat
```

### Linux / macOS

```bash
./run.sh
```

### Production with Gunicorn (Linux)

```bash
export PRODUCTION=1
export WEB_WORKERS=4
python -m hiveai.app
```

### Docker

```bash
docker-compose up -d
```

### Database Setup

HiveAI supports both PostgreSQL and SQLite:

#### SQLite (Recommended for Desktop/Local)

SQLite is ideal for local development and desktop deployments with no server setup needed:

```bash
# Simply set the DATABASE_URL environment variable
export DATABASE_URL=sqlite:///hiveai.db
python -m hiveai.app
```

The database file (`hiveai.db`) is created automatically in the current directory.

#### PostgreSQL (Recommended for Production)

For production deployments, use PostgreSQL with pgvector extension:

```bash
# Create database
createdb hiveai

# Enable pgvector
psql -d hiveai -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Set `DATABASE_URL` to your PostgreSQL connection string:
- Local: `postgresql://user:pass@localhost:5432/hiveai`
- Neon: `postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/hiveai?sslmode=require`
- Supabase: `postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres`

---

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines on:
- Setting up development environment
- Code style and conventions
- Testing and validation
- Submitting pull requests
- Community standards

---

## Roadmap

### Phase 1 — Information Compression (complete)

The refinery: raw web pages → extracted triples → knowledge graph → Golden Books → Hive blockchain.

- [x] Web crawl → triple extraction → knowledge graph
- [x] Golden Book generation with quality scoring
- [x] Hive blockchain publishing with multipart splitting
- [x] Multi-hop RAG chat ("Ask the Keeper")
- [x] Secure code sandbox with chat self-verification

### Phase 2 — Skill Compression (current)

The trainer: accumulated knowledge → LoRA adapters that encode the *ability to produce knowledge*.

- [x] Self-distillation (16 templates, genetic expansion, scorer v5)
- [x] LoRA v1 training + eval harness (115 challenges, +15% over baseline)
- [x] Multi-backend LLM routing (Ollama + llama-server + OpenRouter)
- [x] Confidence routing via `smart_call()` (60-70% fast model usage)
- [x] Merge cycling (train → merge → repeat)
- [x] MoLoRA domain routing (Python, Hive, JS, Rust, C++, Go)
- [x] Claude Opus distillation corpus (4,500+ pairs across 560+ batch files, 80+ domains)
- [x] Thinking-trace curriculum (1,638 pairs, 4-phase cognitive training: foundation → advanced → meta → autonomy)
- [x] Self-improvement pipeline (p400-p407: autonomous "get smarter" training loop)
- [x] Model benchmark harness (12 tasks, 4 categories, speculative decoding metrics)
- [x] Training data bridge (prepare_v5_data.py: 6,176 curriculum-ordered pairs for Qwen 2.5 Coder)
- [ ] LoRA v5 training (Qwen 2.5 Coder, DoRA r=16, KL-anchored SFT)
- [ ] Domain specialist training (per-domain LoRAs)
- [ ] GRPO+ reinforcement learning via rLLM

### Phase 3 — On-Chain Skill Storage (in progress)

Decentralized Brain Collective: knowledge and skills stored on Hive, reconstructible by anyone.

- [x] DBC protocol (on-chain pair proposals, HP-weighted voting, epoch consensus)
- [x] 3-backend chain abstraction (beem → direct RPC → lighthive)
- [x] Pair encoding (gzip + base64), secrets scanner, RC hysteresis
- [x] HivePoA adapter storage (IPFS + GitHub Releases fallback)
- [ ] Live deployment and testing on Hive testnet
- [ ] Multi-node federation and peer discovery

---

## Support

- **Documentation** — [docs/](docs/)
- **Issues** — GitHub Issues
- **Chat** — Use the built-in "Ask the Keeper" chat interface
- **Config Help** — Run `python -m hiveai.app --help` for options

---

## Acknowledgments

Built with:
- [crawl4ai](https://github.com/unclecode/crawl4ai) — Web scraping
- [sentence-transformers](https://huggingface.co/sentence-transformers/) — Embeddings
- [instructor](https://github.com/jxnl/instructor) — Structured LLM outputs
- [NetworkX](https://networkx.org/) — Graph analysis
- [PEFT](https://github.com/huggingface/peft) — Parameter-efficient fine-tuning
- [Hive Blockchain](https://hive.io) — Decentralized publishing
- [Ollama](https://ollama.com) — Local LLM serving
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — GGUF model serving
