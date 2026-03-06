PAIRS = [
    ("thinking/debugging", r'''My Docker build is not using cache even though I haven't changed anything:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
RUN python setup.py build
CMD ["python", "app.py"]
```

Every build reinstalls all pip dependencies (takes 3 minutes) even when I only changed a single Python file. Docker output shows:

```
Step 3/6 : COPY . .
 ---> abc123def456
Step 4/6 : RUN pip install -r requirements.txt
 ---> Running in 789xyz...
```

Step 4 should be cached since requirements.txt hasn't changed. Why isn't it?''', r'''<think>
The issue is the order of COPY and RUN instructions. Docker's layer caching works by comparing the instruction and its inputs (for COPY, the file checksums). If any layer is invalidated, ALL subsequent layers are also invalidated.

`COPY . .` copies the ENTIRE directory. If ANY file changes (even a single .py file), this layer is invalidated. Since `RUN pip install` comes AFTER the COPY, it is also invalidated even though requirements.txt itself hasn't changed.

The fix is to copy requirements.txt first, install dependencies, THEN copy the rest of the code. This way, pip install is only re-run when requirements.txt actually changes.
</think>

Docker's layer cache invalidation is cascading: when a layer changes, ALL subsequent layers are rebuilt. Your `COPY . .` copies the entire project directory. When any file changes (even a single `.py` file), this COPY layer is invalidated, which forces the `RUN pip install` layer to rebuild too.

**The fix: Copy dependencies file first, install, then copy code**

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Layer 1: Copy ONLY the requirements file
COPY requirements.txt .

# Layer 2: Install dependencies (cached unless requirements.txt changes)
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3: Copy the rest of the application code
COPY . .

# Layer 4: Build step
RUN python setup.py build

CMD ["python", "app.py"]
```

**How this works:**

When you change a Python file:
- Layer 1 (COPY requirements.txt): requirements.txt has not changed, so this layer is cached
- Layer 2 (pip install): depends on Layer 1 which is cached, so this is also cached
- Layer 3 (COPY . .): a file changed, so this is rebuilt
- Layer 4 (setup.py build): depends on Layer 3, so this is rebuilt

Result: pip install is skipped entirely. Build time drops from 3+ minutes to seconds.

**Further optimizations:**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app

# Use BuildKit cache mount for pip cache
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .
RUN python setup.py build

# Multi-stage: smaller final image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app .
CMD ["python", "app.py"]
```

**Add .dockerignore to prevent unnecessary cache busts:**

```
# .dockerignore
.git
__pycache__
*.pyc
.env
.venv
node_modules
tests/
docs/
*.md
```

Without `.dockerignore`, COPY includes `.git/` (which changes with every commit), `__pycache__/` (which changes with every run), and other files that unnecessarily bust the cache.

**Prevention tips:**
- Always copy dependency manifests before source code in Dockerfiles
- Use `.dockerignore` to exclude files that trigger unnecessary rebuilds
- Use BuildKit (`DOCKER_BUILDKIT=1`) for advanced caching features
- Order Dockerfile instructions from least-frequently-changed to most-frequently-changed
- Use multi-stage builds to keep final images small'''),

    ("thinking/debugging", r'''My multi-stage Docker build fails because a binary compiled in the build stage doesn't work in the runtime stage:

```dockerfile
FROM python:3.11 AS builder
RUN pip install --user numpy pandas scikit-learn
RUN pip install --user my-c-extension-package

FROM python:3.11-alpine
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "app.py"]
```

Error at runtime:
```
ImportError: Error loading shared library libstdc++.so.6: No such file or directory
```

The packages install fine in the build stage but crash in the runtime stage.''', r'''<think>
The build stage uses `python:3.11` (based on Debian) and the runtime stage uses `python:3.11-alpine` (based on Alpine Linux). These use different C libraries:

- Debian uses glibc
- Alpine uses musl libc

Binary packages (wheels) compiled against glibc will not work on musl, and vice versa. Additionally, Alpine may not have shared libraries (libstdc++, libgomp, etc.) that the compiled packages depend on.

The fix: use the same base image for both stages, or use Alpine for both, or use slim instead of Alpine.
</think>

The build stage uses `python:3.11` (Debian-based, uses glibc) but the runtime stage uses `python:3.11-alpine` (Alpine Linux, uses musl libc). These are fundamentally incompatible:

1. **C library mismatch**: Binary packages compiled against glibc cannot run on musl libc
2. **Missing shared libraries**: Alpine is minimal and lacks libstdc++, libgomp, and other libraries that numpy/sklearn need
3. **Different wheel formats**: pip downloads `manylinux` wheels for Debian but needs `musllinux` wheels for Alpine (many packages lack Alpine wheels)

**Fix 1: Use the same base for both stages (recommended)**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

CMD ["python", "app.py"]
```

Using `python:3.11-slim` for both stages ensures binary compatibility. The slim variant is only ~50MB larger than Alpine.

**Fix 2: If you must use Alpine, install build dependencies**

```dockerfile
FROM python:3.11-alpine AS builder
RUN apk add --no-cache gcc g++ musl-dev linux-headers gfortran openblas-dev
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-alpine
# Install runtime dependencies (but not build tools)
RUN apk add --no-cache libstdc++ libgomp openblas
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . /app
WORKDIR /app
CMD ["python", "app.py"]
```

Note: Building numpy/pandas from source on Alpine takes 10-30 minutes because there are no pre-built musl wheels for most scientific Python packages.

**Fix 3: Use distroless for minimal images (best security)**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt
COPY . .

FROM gcr.io/distroless/python3
WORKDIR /app
COPY --from=builder /app /app
ENV PYTHONPATH=/app/deps
CMD ["app.py"]
```

Distroless images have no shell or package manager, reducing the attack surface.

**Image size comparison:**
```
python:3.11          ~920 MB
python:3.11-slim     ~150 MB
python:3.11-alpine   ~60 MB
distroless/python3   ~50 MB
```

**Prevention tips:**
- Use the same base image (or same Linux distro family) for build and runtime stages
- Avoid Alpine for Python projects with C extensions -- the build time and compatibility issues are not worth the size savings
- Use `python:3.11-slim` as the default choice -- good balance of size and compatibility
- Test your runtime image with `docker run --rm image python -c "import numpy; print(numpy.__version__)"` before deploying
- List shared library dependencies with `ldd /usr/local/lib/python3.11/site-packages/numpy/*.so`'''),

    ("thinking/debugging", r'''Containers on the same Docker network can't communicate by service name:

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: ./web
    ports:
      - "8080:8080"
    environment:
      - API_URL=http://localhost:3000/api
  api:
    build: ./api
    ports:
      - "3000:3000"
```

The web container tries to call the API at http://localhost:3000/api but gets connection refused. Both containers are running and accessible from the host.''', r'''<think>
The issue is that the web container uses `localhost` to connect to the API. Inside a Docker container, `localhost` refers to the container itself, not the host or other containers. Each container has its own network namespace with its own localhost.

In Docker Compose, services can reach each other using the service name as the hostname. So the web container should use `http://api:3000/api` instead of `http://localhost:3000/api`.

The `ports` mapping (3000:3000) makes the API accessible from the HOST at localhost:3000, but not from other containers at localhost:3000.
</think>

Inside a Docker container, `localhost` refers to the container itself, not the host machine or other containers. Each container has its own isolated network namespace. The web container is trying to connect to port 3000 on itself, where nothing is listening.

**How Docker Compose networking works:**

Docker Compose automatically creates a network for your services. Each service is reachable by its service name as the hostname. The `ports` mapping only exposes ports to the host, not between containers.

```
Host machine:
  localhost:8080 -> web container:8080
  localhost:3000 -> api container:3000

Inside web container:
  localhost -> web container itself (not the api!)
  api:3000 -> api container:3000 (via Docker DNS)
```

**Fix: Use the service name as hostname**

```yaml
version: '3.8'
services:
  web:
    build: ./web
    ports:
      - "8080:8080"
    environment:
      - API_URL=http://api:3000/api   # 'api' is the service name
    depends_on:
      - api
  api:
    build: ./api
    ports:
      - "3000:3000"
```

The Docker-embedded DNS server resolves `api` to the API container's IP address on the Compose network.

**You can also remove the `ports` mapping for internal-only services:**

```yaml
services:
  web:
    build: ./web
    ports:
      - "8080:8080"    # exposed to host (for user access)
    environment:
      - API_URL=http://api:3000/api
  api:
    build: ./api
    expose:
      - "3000"          # only accessible within Docker network, not from host
```

Using `expose` instead of `ports` is more secure for internal services.

**Debugging network connectivity between containers:**

```bash
# Exec into the web container and test connectivity
docker compose exec web sh

# Inside the container:
ping api                    # test DNS resolution
curl http://api:3000/api    # test HTTP connectivity
nslookup api                # check DNS resolution details

# From the host, inspect the network:
docker network ls
docker network inspect <project>_default
```

**Common gotcha: depends_on does not wait for the service to be ready**

```yaml
services:
  web:
    depends_on:
      api:
        condition: service_healthy   # wait for health check to pass
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 5s
      timeout: 3s
      retries: 5
```

`depends_on` only controls startup order, not readiness. Use health checks to ensure the API is actually accepting connections before the web service starts.

**Prevention tips:**
- Never use `localhost` to reference other containers -- always use service names
- Use `expose` instead of `ports` for services that only need internal access
- Add health checks to all services
- Use `depends_on` with `condition: service_healthy` for proper startup ordering
- Test inter-service connectivity with `docker compose exec <service> curl <other_service>:<port>`'''),

    ("thinking/debugging", r'''My Docker container fails to write to a mounted volume:

```
PermissionError: [Errno 13] Permission denied: '/data/output/results.csv'
```

Docker Compose config:
```yaml
services:
  worker:
    build: .
    volumes:
      - ./output:/data/output
    user: "1000:1000"
```

Dockerfile:
```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 appuser
USER appuser
WORKDIR /app
COPY . .
CMD ["python", "worker.py"]
```

The ./output directory exists on the host and is owned by my user (uid 1000). The container runs as uid 1000. Why can't it write?''', r'''<think>
Let me think about what could cause this permission issue despite matching UIDs.

Possible causes:
1. The host directory might have restrictive permissions (no write for the group or others, and the container user might not match exactly)
2. SELinux or AppArmor might be blocking access
3. The directory might be owned by uid 1000 but with mode 755 (owner-writable) -- but the container user IS uid 1000 so this should work
4. Docker might create the volume mount as root before the user directive takes effect
5. On macOS/Windows with Docker Desktop, the file ownership mapping works differently

Wait, actually the most common cause: if the `./output` directory does NOT exist when docker-compose starts, Docker creates it as root. Then the container user (1000) cannot write to a root-owned directory.

Another common cause: on Linux with rootless Docker, UID mapping can shift UIDs.

Let me also consider: maybe the directory exists but is owned by a different user, or has restrictive permissions.
</think>

There are several possible causes for this permission denied error, even with matching UIDs. Let me go through the most likely ones:

**Cause 1: Docker auto-creates the directory as root**

If `./output` does not exist when you run `docker compose up`, Docker creates it automatically -- but as root (uid 0), not as your user. The container process running as uid 1000 then cannot write to a root-owned directory.

Fix:
```bash
# Create the directory before starting containers
mkdir -p ./output
# Verify ownership
ls -la ./output
```

Or in the Dockerfile:
```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 appuser
RUN mkdir -p /data/output && chown appuser:appuser /data/output
USER appuser
WORKDIR /app
COPY . .
CMD ["python", "worker.py"]
```

**Cause 2: SELinux is blocking access (RHEL/CentOS/Fedora)**

On systems with SELinux enabled, Docker volume mounts need the `:z` or `:Z` label:

```yaml
volumes:
  - ./output:/data/output:z     # shared label
  # or
  - ./output:/data/output:Z     # private label (only this container)
```

Check if SELinux is the issue:
```bash
# Check SELinux status
getenforce
# Temporarily test with SELinux permissive
sudo setenforce 0
docker compose up  # if this works, SELinux was blocking
sudo setenforce 1  # re-enable after testing
```

**Cause 3: Host directory permissions are wrong**

```bash
# Check the actual permissions
ls -la ./output
# drwxr-xr-x 2 root root 4096 Mar 15 10:00 output
#              ^^^^ owned by root, not your user!

# Fix:
sudo chown 1000:1000 ./output
chmod 755 ./output
```

**Cause 4: Subdirectories created by root**

If a previous run created files as root inside the volume:

```bash
ls -la ./output/
# -rw-r--r-- 1 root root 12345 results_old.csv
# The directory is writable, but existing files are owned by root
```

Fix:
```bash
sudo chown -R 1000:1000 ./output/
```

**Cause 5: Named volumes vs bind mounts behave differently**

```yaml
# Bind mount (your case) - uses host filesystem permissions
volumes:
  - ./output:/data/output

# Named volume - Docker manages permissions
volumes:
  - output_data:/data/output

volumes:
  output_data:
```

Named volumes are initialized with the container directory's ownership and permissions, making them more reliable.

**Best practice Dockerfile pattern:**

```dockerfile
FROM python:3.11-slim

# Create user and directories with proper ownership
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m appuser && \
    mkdir -p /data/output && \
    chown -R appuser:appgroup /data/output

USER appuser
WORKDIR /app
COPY --chown=appuser:appgroup . .
CMD ["python", "worker.py"]
```

**Prevention tips:**
- Always pre-create host directories before starting containers
- Use `chown` in the Dockerfile for directories the app needs to write to
- Add a startup script that checks write permissions and fails with a clear error
- Prefer named volumes over bind mounts for data that Docker manages
- On SELinux systems, always use the `:z` or `:Z` suffix on volume mounts'''),

    ("thinking/debugging", r'''My Docker container health check keeps failing even though the application is running:

```yaml
services:
  web:
    build: .
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

```
$ docker ps
CONTAINER ID   STATUS
abc123         Up 2 minutes (unhealthy)
```

But from the host:
```
$ curl http://localhost:8080/health
{"status": "ok"}
```

The health check fails but the endpoint works fine from outside.''', r'''<think>
The health check runs INSIDE the container, not from the host. The issue is likely that `curl` is not installed in the container image. If the image is based on a slim or Alpine base, curl might not be present.

When the health check command fails (because curl is not found), Docker marks the container as unhealthy.

Let me also consider: maybe curl is installed but the health endpoint is not accessible on localhost inside the container (maybe the app binds to 0.0.0.0 vs 127.0.0.1). Or maybe the container has a different network configuration.

The most common cause is simply curl not being installed in slim/minimal images.
</think>

The health check runs INSIDE the container, not from the host. The most common cause of this issue is that `curl` is not installed in the container image. Slim and Alpine images do not include curl by default.

**Diagnose the issue:**

```bash
# Check health check logs
docker inspect --format='{{json .State.Health}}' abc123 | python -m json.tool

# You will likely see:
# "Output": "OCI runtime exec failed: exec failed: unable to start container process:
#  exec: \"curl\": executable file not found in $PATH"
```

**Fix 1: Install curl in the Dockerfile**

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
```

**Fix 2: Use wget instead (often pre-installed in Alpine)**

```yaml
healthcheck:
  test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Fix 3: Use Python for the health check (no extra dependencies)**

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
```

This uses Python's built-in urllib -- no need to install curl or wget.

**Fix 4: Use a custom health check script**

```python
#!/usr/bin/env python3
# healthcheck.py
import sys
import urllib.request

try:
    response = urllib.request.urlopen('http://localhost:8080/health', timeout=5)
    if response.status == 200:
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
```

```dockerfile
COPY healthcheck.py /healthcheck.py
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["python", "/healthcheck.py"]
```

**Other common health check failures:**

1. **App binds to 0.0.0.0 vs 127.0.0.1**: If your app binds to `0.0.0.0`, localhost works. If it binds to a specific interface, localhost might not reach it.

2. **Wrong port**: The health check uses the container's internal port, not the mapped host port. If your app listens on 8080 inside, use 8080 in the health check regardless of the port mapping.

3. **SSL/TLS**: If your app uses HTTPS internally, use `https://` and add `--insecure` or `-k` to curl.

4. **start_period too short**: If your app takes longer than `start_period` to start, health checks begin failing before the app is ready.

**Prevention tips:**
- Always test health checks by exec-ing into the container: `docker exec abc123 curl http://localhost:8080/health`
- Use `docker inspect` to view health check output and error messages
- Keep health check endpoints lightweight -- no database queries or heavy computation
- Set `start_period` to accommodate your application's startup time
- Return a JSON body with component status for observability'''),
]
