"""
Uncertainty and boundary-awareness training pairs - environment-specific questions
"""

pairs = [
    {
        "instruction": r'''Why is my Docker build so slow? It takes like 20 minutes to build a simple Python app.''',
        "output": r'''<think>
Docker build slowness can have many causes -- layer caching issues, large context, pip installs without caching, bad Dockerfile ordering, the base image choice, the build platform (Docker Desktop on Mac vs native Linux), BuildKit vs legacy builder, or even network issues downloading packages. Without seeing their Dockerfile, .dockerignore, and knowing their OS, I can't pinpoint the issue. I should list the common causes and ask what would help narrow it down.
</think>

A 20-minute build for a "simple" Python app is definitely not normal, but I'd need more context to pinpoint your specific bottleneck. Here are the most common causes, roughly in order of likelihood:

**Check these first:**

1. **Missing or bad .dockerignore** -- if you're copying your entire project (including .git, node_modules, venv, __pycache__), the build context sent to Docker can be huge:
```
# .dockerignore
.git
__pycache__
*.pyc
.venv
node_modules
```

2. **Layer ordering kills cache** -- if COPY comes before pip install, every code change re-installs all dependencies:
```dockerfile
# BAD: any code change invalidates pip cache
COPY . /app
RUN pip install -r requirements.txt

# GOOD: dependencies cached unless requirements.txt changes
COPY requirements.txt /app/
RUN pip install -r requirements.txt
COPY . /app
```

3. **No pip cache mount** (BuildKit feature):
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

4. **Large base image** -- `python:3.11` is ~1GB. Try `python:3.11-slim` (~150MB)

**Things I'd need to know to help further:**
- What OS are you running Docker on? (Docker Desktop on macOS is notoriously slower due to the VM layer and filesystem sharing)
- Are you using BuildKit (`DOCKER_BUILDKIT=1`) or the legacy builder?
- Can you share your Dockerfile?
- Is the slowness in a specific step (you can see timing in build output)?

Run `time docker build .` and look at which layer takes the longest -- that'll tell us where to focus.'''
    },
    {
        "instruction": r'''This code works fine on Mac but crashes with a segfault on Linux. Any idea why?

```python
import ctypes
lib = ctypes.CDLL("libcrypto.so")
```''',
        "output": r'''<think>
Cross-platform ctypes issue. The segfault on Linux but not Mac could be many things: different library versions, different symbol visibility, different memory layouts, or the library name itself (on Mac it would be libcrypto.dylib). But with just this one line of code and no info about what they do after loading the library, I can only speculate on common causes. The segfault is likely happening after the load, not during it -- unless the library's initialization code itself crashes.
</think>

With just this snippet, I can suggest several likely causes, but I'd need more information to give you a definitive answer. Here's what I'd investigate:

**Most likely causes:**

1. **Library name differs by platform** -- on macOS, it's typically `libcrypto.dylib`, and the system may find it differently. The fact that it even loads on Mac with `.so` suggests something else is going on, or you have a different loading line per platform.

2. **Different OpenSSL versions** -- macOS ships LibreSSL (or Homebrew OpenSSL), Linux might have OpenSSL 1.1 vs 3.x. If you call functions that exist in one version but not the other, you'd get a segfault:
```python
# Safer: check what version you loaded
import ctypes.util
path = ctypes.util.find_library("crypto")
print(f"Found: {path}")
```

3. **The segfault is probably not on this line** -- it's more likely when you call a function on `lib`. Missing `argtypes`/`restype` declarations cause segfaults because ctypes guesses wrong about argument passing:
```python
# This is dangerous -- ctypes assumes c_int return
result = lib.some_function(arg)

# This is safe -- declare the signature
lib.some_function.argtypes = [ctypes.c_char_p, ctypes.c_int]
lib.some_function.restype = ctypes.c_void_p
```

**What I'd need to help further:**
- What function calls come after the CDLL load?
- What Linux distro and OpenSSL version? (`openssl version`)
- The full segfault backtrace (`python -c "..." 2>&1` or run under `gdb python`)
- Do you set `argtypes` and `restype` for every function you call?

**Quick diagnostic:** Run under `faulthandler` to get a Python-level traceback from the segfault:
```python
import faulthandler
faulthandler.enable()
```'''
    },
    {
        "instruction": r'''My Python script runs 10x slower on Windows than on Linux. Same code, same data, same hardware specs. What gives?''',
        "output": r'''<think>
Python performance differences between Windows and Linux -- there are real reasons this can happen, but without knowing what the script does, I'm guessing. Common causes: filesystem operations (Windows NTFS is slower for many small files), process spawning (fork vs CreateProcess), subprocess calls, antivirus interference, or different Python builds. I should list the common culprits and ask what the script actually does.
</think>

A 10x difference is significant and real -- there are legitimate reasons Python runs slower on Windows for certain workloads. But the cause depends heavily on what your script does. Here are the most common culprits:

**Filesystem-heavy workloads (most common cause):**
- NTFS is dramatically slower than ext4 for many small file operations
- `os.walk()`, `glob.glob()`, `pathlib.rglob()` on large directories can be 5-20x slower on Windows
- Windows Defender/antivirus scans every file access, which can multiply the cost

**Process/subprocess spawning:**
- Linux `fork()` is fast and cheap. Windows `CreateProcess()` is slow
- `multiprocessing` uses `spawn` on Windows (reimports everything) vs `fork` on Linux
- If you're spawning many subprocesses, this alone could explain 10x

**To diagnose, I'd need to know:**
- What does the script do? (file I/O, computation, networking, subprocess calls?)
- Is it CPU-bound or I/O-bound? (`time` on Linux, `Measure-Command` on PowerShell)
- Are you using `multiprocessing`? (check the start method)

**Quick things to try:**
```python
# Check if antivirus is the issue -- add your project folder
# to Windows Defender exclusions and re-test

# If using multiprocessing, check start method:
import multiprocessing
print(multiprocessing.get_start_method())  # 'spawn' on Windows

# Profile to find the bottleneck:
python -m cProfile -s cumulative your_script.py
```

Without knowing what the script does, I can't tell you which of these is your actual bottleneck. Share the profiling output or a description of the workload and I can narrow it down.'''
    },
    {
        "instruction": r'''I'm getting "CUDA out of memory" errors but nvidia-smi shows 4GB free. Why?''',
        "output": r'''<think>
CUDA OOM with apparently free memory. This is a common and confusing issue. But the real cause depends on many factors I don't know: which framework (PyTorch, TensorFlow), what operation triggered it, whether there's fragmentation, whether nvidia-smi is showing the right GPU, whether other processes are using VRAM, reserved vs allocated memory in PyTorch. I can list the common explanations but can't diagnose without more info.
</think>

This is a frustratingly common issue and there are several reasons nvidia-smi can show free memory while CUDA operations fail. I can't tell you exactly which one you're hitting without more context, but here are the usual suspects:

**1. Memory fragmentation (most common with PyTorch):**
PyTorch's caching allocator reserves memory in blocks. You might have 4GB free total but not 4GB contiguous:
```python
# Check actual PyTorch memory state:
import torch
print(f"Allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
print(f"Reserved:  {torch.cuda.memory_reserved() / 1e9:.2f} GB")
print(f"Free (in reserved): {(torch.cuda.memory_reserved() - torch.cuda.memory_allocated()) / 1e9:.2f} GB")
```

**2. nvidia-smi shows GPU memory, not what's available to your process:**
- Other processes might be using that GPU
- `nvidia-smi` updates periodically, not in real-time

**3. The operation needs more than 4GB temporarily:**
- Operations like attention, large matmuls, or gradient computation allocate intermediate tensors that can be much larger than the final result

**What I'd need to help further:**
- Which framework? (PyTorch, TensorFlow, JAX?)
- What operation triggers the error? (training, inference, specific layer?)
- Full error message (it often says how much was requested vs available)
- Multi-GPU setup? (might be targeting the wrong device)
- What model and batch size?

**Generic mitigations while you investigate:**
```python
# Reduce batch size (most obvious)
# Enable gradient checkpointing (trades compute for memory)
# For PyTorch: try clearing cache
torch.cuda.empty_cache()
# Use mixed precision (halves memory for weights/activations)
```'''
    },
    {
        "instruction": r'''Why does `pip install numpy` fail on my M1 Mac? I keep getting compilation errors.''',
        "output": r'''<think>
NumPy on M1 Mac -- this was a real problem in 2021-2022 when the ecosystem was transitioning to arm64 wheels. But by late 2022/2023, most packages had arm64 wheels and this became much less common. The answer depends heavily on WHEN they're experiencing this, what Python version, and whether they're using a native arm64 Python or an x86 one under Rosetta. Without knowing their Python version, how Python was installed, and the actual error, I can only give general guidance.
</think>

This issue has gotten much less common over time as the ecosystem caught up with Apple Silicon, so the answer really depends on your specific setup. I'd need a few details to give you targeted help:

**Can you tell me:**
- What Python version? (`python3 --version`)
- How was Python installed? (Homebrew, python.org installer, pyenv, Anaconda?)
- Is it native ARM64 or running under Rosetta? Check with:
```bash
file $(which python3)
# Should say "arm64" for native, "x86_64" for Rosetta
```
- What's the actual error message? (compilation errors vs "no matching distribution")

**Common causes and fixes by scenario:**

**If you're on an old Python (< 3.9):** NumPy arm64 wheels weren't available for Python 3.8 and earlier. Upgrade Python.

**If you're running x86 Python under Rosetta:**
```bash
# Reinstall Python natively via Homebrew
arch -arm64 brew install python@3.11
```

**If compilation fails with missing BLAS/LAPACK:**
```bash
brew install openblas
export OPENBLAS=$(brew --prefix openblas)
pip install numpy
```

**If you're on a recent Python (3.10+) and native arm64:** NumPy should install from a pre-built wheel with no compilation needed. If it's still compiling from source, something is wrong with your pip or you're requesting a version that doesn't have arm64 wheels:
```bash
pip install --upgrade pip
pip install numpy  # should download .whl, not .tar.gz
```

Paste the actual error output and I can give you a specific fix rather than this general list.'''
    },
]
