# Computer B Setup — Spirit Bomb GPU Worker

## What This Does
This computer will share its GPU with Computer A to create a combined AI brain.
Computer A runs the server. This computer (B) joins as a GPU worker.

## Prerequisites
- NVIDIA GPU with 8+ GB VRAM
- Python 3.10+ installed
- Git installed
- Network connection to Computer A (192.168.0.101)

## Step 1: Allow Network Access (one-time, admin PowerShell)

```powershell
# Allow incoming ping (for latency measurement)
netsh advfirewall firewall add rule name="Allow Ping" protocol=icmpv4 dir=in action=allow

# Allow incoming on port 8101 (for latency probing between nodes)
netsh advfirewall firewall add rule name="SpiritBomb Ping" protocol=tcp dir=in localport=8101 action=allow
```

## Step 2: Clone the Repo (one-time)

```bash
cd C:\Users\%USERNAME%
git clone https://github.com/Dhenz14/Hive-AI.git
cd Hive-AI
pip install aiohttp
```

## Step 3: Verify Connection to Computer A

```bash
ping 192.168.0.101
# Should respond with <1ms RTT
```

If ping fails, Computer A needs to open port 5000:
```powershell
# Run on Computer A (admin PowerShell):
netsh advfirewall firewall add rule name="HivePoA" protocol=tcp dir=in localport=5000 action=allow
```

## Step 4: Start Spirit Bomb Worker

```bash
cd C:\Users\%USERNAME%\Hive-AI
python scripts/start_spiritbomb.py --hivepoa-url http://192.168.0.101:5000
```

This will:
1. Auto-detect your GPU (model, VRAM, UUID)
2. Bootstrap an API key from Computer A's HivePoA server
3. Register as a community GPU node
4. Start the inference worker (shares your GPU)
5. Start the coordinator (monitors community tier)

## Step 5: Verify It's Working

On Computer A, open: http://localhost:5000/community-cloud

You should see:
- Total GPUs: 2 (was 0 or 1)
- A new cluster formed
- Your GPU listed as a contributor

## What Happens Next

- Your GPU serves inference requests from the community
- Computer A's browser at /inference can use "Cluster" mode
- Together, both GPUs can run Qwen3-32B (too big for either alone)
- You earn HBD rewards based on tokens processed

## Troubleshooting

**"Connection refused" to 192.168.0.101:5000**
→ Computer A needs to open port 5000 in firewall (see Step 3)

**"No API key" or bootstrap fails**
→ HivePoA server on Computer A might need restart with new build:
```bash
# On Computer A:
cd "C:\Users\theyc\Hive AI\HivePoA"
npm run build
NODE_ENV=production PORT=5000 node dist/index.cjs
```

**GPU not detected**
→ Make sure NVIDIA drivers are installed: `nvidia-smi` should show your GPU

**Python not found**
→ Install Python 3.10+: https://www.python.org/downloads/
