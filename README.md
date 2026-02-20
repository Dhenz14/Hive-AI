# HiveAI Knowledge Refinery

## What is it?

HiveAI Knowledge Refinery is an AI-powered research system that autonomously discovers authoritative web sources, extracts structured knowledge into a persistent graph, generates polished "Golden Book" reference documents, and publishes them immutably to the Hive blockchain. It operates fully offline with Ollama—no API keys required—while seamlessly scaling to high-performance configurations with async job queues, automatic hardware tuning, and incremental knowledge graph updates.

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

### Blockchain Publishing
- **Hive Blockchain Integration** — Publishes Golden Books to Hive with configurable multipart splitting for large content
- **Tagged Organization** — Namespace-based tagging (archivedcontenthaf, hiveaiknowledgehaf) for discoverability
- **Immutable Timestamping** — Permanent, verifiable record on distributed ledger with full source attribution

### Local-First Operation
- **Ollama Support** — Fully offline operation using Ollama with Qwen3, Phi-4, or any compatible model
- **Hardware Auto-Detection** — Automatic profile selection (low/medium/high) based on CPU and RAM
- **Configurable Embedding Models** — BAAI/bge-m3, Qwen3-Embedding, or any sentence-transformers model with single-command re-embedding
- **Zero External Dependencies** — Optional search APIs (Serper.dev, Brave) but fully functional without them

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

Open your browser to **http://localhost:5000** — that's it! Fully local, no API keys, no cloud dependencies.

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

Open your browser to **http://localhost:5000**

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

### Embedding & Semantics

| Variable | Purpose | Default |
|----------|---------|---------|
| `EMBEDDING_MODEL` | Embedding model | `BAAI/bge-m3` |
| `SEMANTIC_SIMILARITY_THRESHOLD` | Duplicate detection (0.0-1.0) | `0.82` |
| `HNSW_EF_SEARCH` | pgvector search accuracy | `100` |
| `SEMANTIC_CHUNKING` | Embedding-based chunking | `false` |

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
- **Storage**: 10 GB
- **Database**: SQLite (automatic, no setup)
- **LLM**: Ollama with qwen3:8b
- **Profile**: `medium` or `high` (auto-detected)

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
Blockchain Publishing
    ↓ (Hive with multipart splitting)
Immutable Record
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | Flask | REST API and dashboard UI |
| **Database** | SQLite or PostgreSQL + pgvector | Triples, embeddings, content storage |
| **LLM** | Ollama or OpenRouter | Reasoning, extraction, writing, chat |
| **Embeddings** | sentence-transformers | Vector search, semantic similarity |
| **Web Scraping** | crawl4ai (Playwright) | JavaScript-aware page extraction |
| **Graph Analysis** | NetworkX, Louvain | Community detection and summaries |
| **Job Queue** | SQLAlchemy + threading | Async pipeline orchestration |
| **Blockchain** | Hive RPC | Immutable publishing |

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Language** | Python 3.11+ |
| **Web Framework** | Flask |
| **Database** | SQLite (local) or PostgreSQL 13+ with pgvector (production) |
| **LLM Backends** | Ollama, OpenRouter (Claude, Qwen3, Phi-4, etc.) |
| **Embeddings** | sentence-transformers (BAAI/bge-m3, Qwen3-Embedding) |
| **Web Scraping** | crawl4ai (Playwright) |
| **Graph Computing** | NetworkX, Louvain (community detection) |
| **Chunking** | semchunk (fast) or embedding-based (precise) |
| **Structured LLM** | instructor (JSON schema validation) |
| **Vector Search** | pgvector HNSW (PostgreSQL) or numpy cosine (SQLite) |
| **Job Queue** | SQLAlchemy ORM + threading |
| **Blockchain** | Hive RPC nodes |

---

## File Structure

```
hiveai-knowledge-refinery/
├── hiveai/
│   ├── app.py                 # Flask web server
│   ├── config.py              # Configuration and hardware detection
│   ├── hardware.py            # Hardware profile logic
│   ├── models.py              # SQLAlchemy ORM models
│   ├── chat.py                # Multi-hop RAG chat pipeline
│   ├── llm/
│   │   ├── client.py          # LLM backend abstraction (Ollama/OpenRouter)
│   │   └── prompts.py         # System and reasoning prompts
│   ├── pipeline/
│   │   ├── url_discovery.py   # Source discovery (DuckDuckGo, Brave, SearXNG)
│   │   ├── crawler.py         # Web crawling with caching
│   │   ├── cleaner.py         # Text cleaning and normalization
│   │   ├── reasoner.py        # Chain-of-thought triple extraction
│   │   ├── entity_resolver.py # Alias normalization and deduplication
│   │   ├── contradiction.py   # Contradiction detection
│   │   ├── communities.py     # Louvain clustering and summaries
│   │   ├── writer.py          # Golden Book generation pipeline
│   │   ├── scorer.py          # Quality scoring
│   │   ├── publisher.py       # Hive blockchain publishing
│   │   ├── queue_worker.py    # Async job orchestration
│   │   └── orchestrator.py    # High-level pipeline coordinator
│   ├── storage/
│   │   └── graph_store.py     # Knowledge graph persistence
│   ├── templates/             # Jinja2 HTML templates
│   │   ├── dashboard.html
│   │   ├── chat.html
│   │   ├── graph_explorer.html
│   │   ├── job_detail.html
│   │   └── book_review.html
│   └── static/                # CSS, JS, images for UI
├── docs/
│   ├── CONTRIBUTING.md        # Contribution guidelines
│   ├── README.md              # Documentation
│   └── CODE_OF_CONDUCT.md
├── .env.example               # Configuration template
├── setup.sh                   # Linux/macOS setup script
├── setup.bat                  # Windows setup script
├── run.sh                     # Linux/macOS launcher
├── run.bat                    # Windows launcher
├── pyproject.toml             # Python project metadata
├── requirements.txt           # Python dependencies
├── LICENSE                    # MIT License
└── README.md                  # This file
```

---

## Usage Examples

### Create a Research Job

```bash
curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"topic": "Quantum Machine Learning 2025"}'
```

### Batch Create Jobs

```bash
curl -X POST http://localhost:5000/api/jobs/batch \
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
curl http://localhost:5000/api/queue/status
```

### Chat with Knowledge Base

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest advances in quantum computing?",
    "history": []
  }'
```

### Check System Status

```bash
# Hardware profile
curl http://localhost:5000/api/hardware

# LLM backend
curl http://localhost:5000/api/llm-status

# Embedding model
curl http://localhost:5000/api/embedding-status
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

- [ ] Multi-document summarization across book collections
- [ ] Fine-tuning embedding models on domain-specific data
- [ ] Real-time collaborative knowledge graph editing
- [ ] Advanced visualization of community structures
- [ ] Integration with external knowledge bases (Wikipedia, Wikidata)
- [ ] Multilingual support and cross-lingual entity resolution
- [ ] IPFS integration for distributed storage
- [ ] Mobile companion app for Hive authentication

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
- [Hive Blockchain](https://hive.io) — Decentralized publishing
