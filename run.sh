#!/bin/bash

# Load environment variables from .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)
fi

# Check if we should run in production mode
if [ "${PRODUCTION:-0}" = "1" ]; then
    WORKERS=${WEB_WORKERS:-2}
    echo "Starting HiveAI in production mode (${WORKERS} workers)..."
    exec gunicorn --bind=0.0.0.0:5000 --workers=$WORKERS --reuse-port "hiveai.app:app"
else
    echo "Starting HiveAI in development mode..."
    exec python -m hiveai.app
fi
