# How GPU Sharing Works — Plain English Guide

## The Expert Plumber

Imagine an expert plumber. He knows HOW to think about plumbing — he can look
at any new design and understand it because he deeply knows the craft. But he
doesn't memorize every pipe size, every bracket, every fitting. He carries a
perfectly organized notebook where he can flip to exactly the right page in seconds.

That's Hive-AI:

- **The Plumber's Brain** = the AI model (v5-think, 14B parameters). Knows how to
  reason about code, debug problems, design systems. Trained once, frozen.
- **The Plumber's Notebook** = the RAG knowledge base (12,000+ verified solutions).
  Always growing — new knowledge flows in like a faucet from every verified
  chat response and training pair. Perfectly indexed, language-routed, reranked.
- **GPU Power** = how fast the plumber can think. More GPU = faster answers,
  longer documents, or an even smarter plumber (bigger model).

## The Big Idea

Spirit Bomb lets multiple computers pool their graphics cards (GPUs)
to run AI models that are too big for any single computer.

Think of it like this: a 32-billion parameter AI model needs ~20GB of
GPU memory. Your single 16GB GPU can't fit it. But your two computers
together have 28GB — more than enough if they split the work.

## Your 2 Computers

**Computer A:** RTX 4070 Ti SUPER (16GB)
**Computer B:** RTX 4070 SUPER (12GB)

### What happens when you run Spirit Bomb:

```
Computer A                        Computer B
┌─────────────────┐              ┌─────────────────┐
│ GPU: 16GB VRAM  │              │ GPU: 12GB VRAM  │
│                 │◄── network ──►│                 │
│ Model layers    │              │ Model layers    │
│ 1-40            │              │ 41-64           │
│                 │              │                 │
│ Also runs:      │              │ Also runs:      │
│ - Ollama (local)│              │ - vLLM worker   │
│ - HivePoA server│              │ - Inference svc │
│ - Coordinator   │              │ - Ping server   │
└─────────────────┘              └─────────────────┘
```

1. Both computers run `python scripts/start_spiritbomb.py`
2. They register with HivePoA and discover each other
3. The coordinator forms a 2-GPU cluster
4. When you ask a question in "Cluster" mode:
   - Your prompt goes to Computer A (layers 1-40)
   - The partial result passes over your network to Computer B (layers 41-64)
   - Computer B finishes and sends the response back
   - You see one seamless answer, powered by both GPUs

### What you experience:

- **Local mode (Medium):** Uses only your local GPU. Runs a smaller model (14B).
  Works offline. Free. Private. Fast for simple questions.

- **Cluster mode (High-Intel):** Uses BOTH your GPUs together. Runs a bigger
  model (32B). Needs both computers online. Better answers for complex questions.

## 100 GPU Cluster

Same idea, bigger:

```
US-East Cluster (20 GPUs)     EU-West Cluster (15 GPUs)
┌──────────────────────┐     ┌──────────────────────┐
│ User1: RTX 4090 24GB │     │ User6: RTX 3090 24GB │
│ User2: RTX 4080 16GB │     │ User7: RTX 4070 12GB │
│ User3: RTX 4070 12GB │     │ User8: RTX 3080 10GB │
│ ...17 more GPUs      │     │ ...12 more GPUs      │
│                      │     │                      │
│ Total: 320GB VRAM    │     │ Total: 200GB VRAM    │
│ Running: Qwen3-80B   │     │ Running: Qwen3-32B   │
└──────────────────────┘     └──────────────────────┘
         ▲                            ▲
         │                            │
    ┌────┴────────────────────────────┴────┐
    │         HivePoA Coordinator          │
    │  (routes requests to nearest cluster)│
    └──────────────────────────────────────┘
```

- Each person runs the Spirit Bomb script on their computer
- The coordinator groups nearby GPUs (<50ms latency)
- Each group collectively runs a model none of them could run alone
- When you ask a question, it goes to the nearest group
- **Nothing runs "in the cloud."** Every computation happens on someone's real computer.

## Where Does Everything Live?

| Component | Where it runs | What it does |
|-----------|--------------|--------------|
| **Your AI model** | Split across community GPUs | Each GPU holds some layers |
| **HivePoA server** | Your server (or any host) | Coordinates who does what |
| **Coordinator** | Runs alongside HivePoA | Polls GPUs, publishes tier |
| **Worker** | Each community member's PC | Hosts model layers, serves requests |
| **Your data/history** | YOUR computer only | Never leaves your machine |

## How Do GPUs Talk to Each Other?

1. **Discovery:** Each worker registers with HivePoA and says "I'm online, I have X GPU"
2. **Latency probing:** Workers ping each other to measure speed (need <50ms)
3. **Cluster formation:** Coordinator groups nearby workers into teams
4. **Model distribution:** Each worker downloads only its assigned layers from IPFS
5. **Inference pipeline:** Request flows through the pipeline: GPU1 → GPU2 → GPU3 → response

## Your Setup Right Now

To try the 2-computer setup:

**Computer A (main):**
```bash
# Start HivePoA server
cd HivePoA
NODE_ENV=production PORT=5000 npx tsx server/index.ts

# In another terminal:
cd Hive-AI
python scripts/start_spiritbomb.py
```

**Computer B (helper):**
```bash
cd Hive-AI
python scripts/start_spiritbomb.py \
    --hivepoa-url http://COMPUTER_A_IP:5000
```

Both computers will register, form a cluster, and you can use the
combined GPU power from Computer A's browser at http://localhost:5000/inference.

## What "Tier" Means

Using the plumber analogy — the tiers control how smart and fast the plumber is:

| Tier | GPUs | The Plumber | In Practice |
|------|------|-------------|-------------|
| **Tier 1** | 0-14 | Expert plumber working solo with his notebook | 14B model on your local GPU. Fast, private, offline-capable. |
| **Tier 2** | 15-39 | Same plumber but now he has a photographic memory (bigger brain) | 32B model across community GPUs. 10-15% smarter answers. |
| **Tier 3** | 40+ | Master plumber with encyclopedic knowledge and a team of specialists | 80B MoE model on 40+ GPUs. Near GPT-4 quality, fully decentralized. |

The notebook (RAG) stays the same across all tiers — it's always local, always fast.
What changes is the brain powering the reasoning. More GPU = bigger brain = better
at solving problems it's never seen before. The notebook handles everything it HAS
seen before.

More GPUs = smarter AI. That's the Spirit Bomb.
