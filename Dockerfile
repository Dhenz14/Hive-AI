# =============================================================================
# HiveAI Knowledge Refinery — Dockerfile
# =============================================================================
# Multi-stage build: slim Python image with only production dependencies.
#
# Build:   docker build -t hiveai .
# Run:     docker compose up (recommended — includes llama-server)
#
# For GPU support, ensure NVIDIA Container Toolkit is installed:
#   https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/
# =============================================================================

# Stage 1: Builder — install Python deps in a venv
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for building native extensions (psycopg2, numpy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime — slim image with venv from builder
FROM python:3.12-slim

WORKDIR /app

# Runtime deps only (libpq for psycopg2, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY hiveai/ ./hiveai/
COPY scripts/ ./scripts/
COPY skills/ ./skills/
COPY evals/ ./evals/
COPY loras/ ./loras/
COPY requirements.txt pyproject.toml ./
COPY .env.example ./

# Create data directory for SQLite persistence
RUN mkdir -p /app/data

# Default environment
ENV PORT=5001
ENV PRODUCTION=1
ENV WEB_WORKERS=2
ENV PYTHONUNBUFFERED=1
ENV HIVEAI_ALLOW_WINDOWS=1

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:5001/ready || exit 1

# Run with gunicorn in production mode
CMD ["python", "-m", "hiveai"]
