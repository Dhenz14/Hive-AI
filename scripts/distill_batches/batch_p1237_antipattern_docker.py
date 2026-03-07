"""
Anti-pattern training pairs - Docker anti-patterns
Topics: root user, no .dockerignore, large images, secrets in layers, no health checks
"""

pairs = [
    {
        "instruction": r'''Here's my Dockerfile for a Node.js app. It works fine:

```dockerfile
FROM node:20
WORKDIR /app
COPY . .
RUN npm install
EXPOSE 3000
CMD ["node", "server.js"]
```

My security team flagged it. What's wrong?''',
        "output": r'''<think>
Running as root in the container. The default user in most base images is root. If an attacker exploits the Node.js app, they get root access inside the container, which can be used to escape to the host in some configurations. The fix is to create a non-root user and switch to it. Also missing multi-stage build and npm ci instead of npm install, but root is the primary security issue flagged.
</think>

Your container runs as root. By default, the `node:20` image uses the root user, so your application has full root privileges inside the container. If an attacker exploits a vulnerability in your Node.js app, they get root access -- which in some container runtime configurations can be used to escape to the host.

**The fix -- create and use a non-root user:**

```dockerfile
FROM node:20-slim

WORKDIR /app

# Copy package files first for better layer caching
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Copy application code
COPY . .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 3000
CMD ["node", "server.js"]
```

**What changed:**
1. **`USER appuser`** -- the process runs as a non-root user. Even if the app is compromised, the attacker has limited privileges.
2. **`node:20-slim`** -- smaller base image (200MB vs 1GB), fewer packages that could have vulnerabilities.
3. **`npm ci`** -- deterministic installs from lock file, faster than `npm install`.
4. **Package files copied first** -- Docker caches this layer, so `npm ci` only re-runs when dependencies change, not when you edit source code.

**Note:** The `node` base image actually includes a built-in `node` user, so you can simplify:

```dockerfile
USER node
```

But you must ensure file permissions are correct for that user.

**Why this matters:** Container escape vulnerabilities exist (CVE-2019-5736, for example). Running as non-root is a defense-in-depth measure that limits blast radius.'''
    },
    {
        "instruction": r'''My Docker image keeps getting bigger. The build also seems slow -- it re-installs dependencies even when I only change a comment in my code:

```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

The image is 1.8GB. My app is 50KB of Python.''',
        "output": r'''<think>
Two problems: no .dockerignore (copying everything including .git, node_modules, __pycache__, venv, etc.) and poor layer ordering (COPY . . before pip install breaks caching). The 1.8GB size is from the full python base image plus copied junk. Fix with .dockerignore, multi-stage build, slim base image, and proper layer ordering.
</think>

Two problems are causing both the size and the slow builds.

**Problem 1: No .dockerignore.** `COPY . .` copies EVERYTHING -- your `.git` directory (possibly hundreds of MB), `__pycache__`, `.venv`, test files, IDE config, and any data files. Create a `.dockerignore`:

```
.git
.gitignore
__pycache__
*.pyc
.venv
.env
tests/
*.md
.mypy_cache
.pytest_cache
docker-compose.yml
Dockerfile
```

**Problem 2: Layer caching is broken.** You copy all code BEFORE installing dependencies. Any code change invalidates the `COPY . .` layer, which invalidates the `pip install` layer. Dependencies are re-downloaded on every build.

**The fix -- proper layer ordering and slim image:**

```dockerfile
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies first (cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (only this layer rebuilds on code changes)
COPY . .

CMD ["python", "app.py"]
```

**For even smaller images, use multi-stage builds:**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
USER nobody
CMD ["python", "app.py"]
```

**Size comparison:**
- `python:3.11` -- ~1GB base
- `python:3.11-slim` -- ~150MB base
- With `.dockerignore` -- removes .git and junk
- With `--no-cache-dir` -- removes pip's download cache from the image

Your 1.8GB image should drop to under 200MB.'''
    },
    {
        "instruction": r'''I need my container to access our database and an API. I put the credentials in the Dockerfile so they're always available:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

ENV DATABASE_URL=postgresql://admin:pr0d_p4ss@db.internal:5432/myapp
ENV API_KEY=ak_live_9x7mK2pLqR5nW8vT3jF6
ENV AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```''',
        "output": r'''<think>
Secrets baked into Docker image layers. ENV directives are stored in the image metadata and every layer is visible. Anyone who pulls the image can run "docker inspect" or "docker history" to see all environment variables, including the database password and API keys. These secrets persist even if overridden at runtime. The fix is to pass secrets at runtime via docker run -e or docker secrets.
</think>

Those credentials are permanently baked into the image and visible to anyone with access to it.

**How anyone can see them:**

```bash
# Shows all ENV values in the image
docker inspect your-image | grep -A5 "Env"

# Shows the full Dockerfile history including ENV values
docker history --no-trunc your-image
```

Even if you push this to a private registry, anyone with pull access sees your production database password, API key, and AWS secret. If the image is ever accidentally pushed to a public registry, all credentials are compromised.

**What makes this worse:** Docker image layers are immutable. Even if you build a new image without the ENV lines, the old layers still contain the secrets in the registry's history.

**The fix -- pass secrets at runtime, never at build time:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

Pass credentials when running the container:

```bash
# Option 1: environment variables at runtime
docker run \
    -e DATABASE_URL=postgresql://admin:pr0d_p4ss@db.internal:5432/myapp \
    -e API_KEY=ak_live_... \
    your-image

# Option 2: env file (keep out of version control)
docker run --env-file .env.production your-image

# Option 3: Docker secrets (Swarm/Compose)
echo "pr0d_p4ss" | docker secret create db_password -
```

**For Kubernetes:** Use Secrets objects or a secrets manager like Vault.

**For build-time secrets** (e.g., private pip index): Use Docker BuildKit's `--secret` flag, which mounts the secret temporarily without storing it in any layer:

```bash
docker build --secret id=pip_token,src=./token.txt .
```'''
    },
    {
        "instruction": r'''My container starts and Docker says it's running, but sometimes the app inside hasn't actually started yet. My load balancer sends traffic before it's ready:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000"]
```

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports:
      - "8000:8000"
  worker:
    build: .
    command: celery -A tasks worker
    depends_on:
      - web
```''',
        "output": r'''<think>
No health check defined. Docker reports the container as "running" as soon as the process starts, but the app might still be loading, connecting to databases, or warming up caches. Without a HEALTHCHECK, Docker and orchestrators cannot distinguish between "process started" and "ready to serve traffic." The depends_on only waits for the container to start, not for the app to be healthy. Need HEALTHCHECK instruction and depends_on with condition.
</think>

Docker considers a container "healthy" the moment the process starts, not when your app is ready to serve requests. Gunicorn might take several seconds to load your app, connect to the database, and warm caches.

**The result:** Your load balancer sends traffic to a container that is not ready, causing 502 errors during deployments and restarts.

**The fix -- add a HEALTHCHECK:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000

# Health check hits your app's health endpoint
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000"]
```

Add a health endpoint to your app:

```python
@app.route('/health')
def health():
    # Check that the app is truly ready
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy'}), 200
    except Exception:
        return jsonify({'status': 'unhealthy'}), 503
```

**Update docker-compose to use the health check:**

```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      start_period: 15s
      retries: 3

  worker:
    build: .
    command: celery -A tasks worker
    depends_on:
      web:
        condition: service_healthy
```

**Key parameters:**
- `start_period` -- grace period for app startup before health checks count as failures
- `interval` -- how often to check
- `retries` -- how many consecutive failures before marking unhealthy

Now Docker knows when your app is truly ready, and `depends_on` with `condition: service_healthy` waits for the app to be ready, not just the process to start.'''
    },
    {
        "instruction": r'''I want to install some debug tools in my production image. Here's my Dockerfile:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    vim nano \
    curl wget \
    net-tools iputils-ping telnet \
    htop strace \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY . .

CMD ["python3", "app.py"]
```

I install vim, gcc, and debug tools so I can SSH in and debug if something goes wrong in production.''',
        "output": r'''<think>
Installing unnecessary packages in production image -- especially compilers (gcc), editors (vim/nano), network tools (telnet), and debug tools (strace). This increases attack surface (gcc lets an attacker compile exploits inside the container), bloats the image, and goes against the principle of minimal containers. Debug tools should not be in production images. Use ephemeral debug containers or multi-stage builds instead.
</think>

Every unnecessary package in your production image is an expansion of your attack surface. `gcc` and `make` are especially dangerous -- if an attacker gets a shell, they can compile exploits directly inside your container.

**Problems with this approach:**
- **`gcc g++ make`** -- a compiler toolchain lets attackers build and run any C program inside your container
- **`vim nano`** -- text editors let attackers modify your application code at runtime
- **`strace`** -- lets attackers trace system calls and inspect secrets in memory
- **`telnet net-tools`** -- network tools help attackers pivot to other internal services
- **Ubuntu base** -- 75MB+ base with thousands of packages you don't need

**The fix -- minimal production image, debug separately:**

```dockerfile
# Build stage -- compilers here only
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Production stage -- minimal
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# No editors, no compilers, no debug tools
RUN groupadd -r app && useradd -r -g app app
USER app

CMD ["python", "app.py"]
```

**When you need to debug production:**

```bash
# Option 1: ephemeral debug container (Kubernetes)
kubectl debug pod/my-app -it --image=busybox

# Option 2: docker exec with a debug image
docker run -it --pid=container:my-app --net=container:my-app \
    nicolaka/netshoot

# Option 3: copy logs out
docker cp my-app:/app/logs ./local-logs
```

These approaches give you debug tools when needed without permanently increasing the attack surface of your production image. The debug container is thrown away after use.'''
    },
]
