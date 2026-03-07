"""
Shell/CLI training pairs - Cron jobs, watch, entr, makefiles, task automation.
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''I want to automatically re-run my tests whenever I save a file. What are my options in the terminal?''',
        "output": r'''<think>
File-watching options:
1. `entr` -- simple, Unix philosophy, watches specific files
2. `inotifywait` -- Linux-specific, watches directories
3. `watchman` (Facebook) -- heavy but powerful
4. `fswatch` -- cross-platform
5. `nodemon` -- Node.js-focused but works for anything
6. `watch` -- not file-based, just re-runs on a timer

For "re-run tests on save," entr is the best fit. It is simple, reliable, and handles the common workflow perfectly. I should also show inotifywait as it comes pre-installed on many systems.
</think>

Best option: `entr` (install: `apt install entr` or `brew install entr`)

```bash
# Re-run tests when any Python file changes
find . -name '*.py' | entr -c python -m pytest

# -c clears the screen before each run
# -r restarts long-running processes (like a dev server)
find . -name '*.py' | entr -r python app.py

# Watch specific files
echo "src/main.py tests/test_main.py" | tr ' ' '\n' | entr -c pytest tests/

# Re-run on new files too (restart entr when directory changes)
while true; do
    find . -name '*.py' | entr -d pytest
    # -d exits when a new file is added to a watched directory
done
```

Alternative: `inotifywait` (comes with `inotify-tools`):

```bash
# Watch for file modifications and run tests
inotifywait -m -r -e modify --include '\.py$' ./src ./tests | while read path action file; do
    echo "Changed: $path$file"
    python -m pytest --tb=short -q
done
```

Simple timer-based approach with `watch`:

```bash
# Re-run every 2 seconds (not file-triggered, just polling)
watch -n 2 'python -m pytest --tb=line -q 2>&1 | tail -5'
```

For a Makefile-based workflow:

```bash
# In Makefile:
# .PHONY: watch-test
# watch-test:
#     find . -name '*.py' | entr -c make test
make watch-test
```'''
    },
    {
        "instruction": r'''Show me a practical Makefile for a Python project with common development tasks.''',
        "output": r'''```makefile
# Makefile for Python project
.PHONY: help install dev test lint format clean build deploy

PYTHON := python3
VENV := .venv
BIN := $(VENV)/bin

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: $(VENV)/bin/activate ## Install production dependencies

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	touch $(VENV)/bin/activate

dev: install ## Install dev dependencies
	$(BIN)/pip install -r requirements-dev.txt
	$(BIN)/pre-commit install

test: ## Run tests with coverage
	$(BIN)/pytest tests/ -v --tb=short --cov=src --cov-report=term-missing

test-fast: ## Run tests without coverage (faster)
	$(BIN)/pytest tests/ -x -q --tb=line

lint: ## Run linters
	$(BIN)/ruff check src/ tests/
	$(BIN)/mypy src/

format: ## Auto-format code
	$(BIN)/ruff format src/ tests/
	$(BIN)/ruff check --fix src/ tests/

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

build: clean ## Build distribution packages
	$(BIN)/python -m build

deploy: build ## Deploy to PyPI
	$(BIN)/twine upload dist/*

db-migrate: ## Run database migrations
	$(BIN)/alembic upgrade head

db-rollback: ## Rollback last migration
	$(BIN)/alembic downgrade -1

run: ## Run the development server
	$(BIN)/uvicorn src.main:app --reload --port 8000

watch-test: ## Re-run tests on file changes
	find src tests -name '*.py' | entr -c $(BIN)/pytest tests/ -x -q
```

Usage:

```bash
make help       # see all available commands
make dev        # set up dev environment
make test       # run tests
make format     # auto-format code
```'''
    },
    {
        "instruction": r'''How do I set up a cron job that monitors disk usage and alerts me when it goes above 90%?''',
        "output": r'''```bash
cat > /opt/scripts/disk-monitor.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

THRESHOLD=90
MAILTO="admin@example.com"
HOSTNAME=$(hostname)
ALERT_FILE="/tmp/.disk-alert-sent"

# Check each mounted filesystem
ALERTS=""
while IFS= read -r line; do
    usage=$(echo "$line" | awk '{print $5}' | tr -d '%')
    mount=$(echo "$line" | awk '{print $6}')
    filesystem=$(echo "$line" | awk '{print $1}')

    if [ "$usage" -gt "$THRESHOLD" ]; then
        ALERTS="${ALERTS}WARNING: ${mount} is ${usage}% full (${filesystem})\n"
    fi
done < <(df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs | tail -n +2)

if [ -n "$ALERTS" ]; then
    # Only send one alert per hour (avoid spam)
    if [ ! -f "$ALERT_FILE" ] || [ $(( $(date +%s) - $(stat -c %Y "$ALERT_FILE") )) -gt 3600 ]; then
        echo -e "Disk space alert on ${HOSTNAME}:\n\n${ALERTS}\nFull output:\n$(df -h)" \
            | mail -s "DISK ALERT: ${HOSTNAME}" "$MAILTO"
        touch "$ALERT_FILE"
        echo "Alert sent at $(date)"
    fi
else
    # Clear the alert flag when everything is ok
    rm -f "$ALERT_FILE"
fi
SCRIPT

chmod +x /opt/scripts/disk-monitor.sh
```

Add to cron (check every 15 minutes):

```bash
crontab -e
# Add this line:
*/15 * * * * /opt/scripts/disk-monitor.sh >> /var/log/disk-monitor.log 2>&1
```

Test it:

```bash
# Run manually to verify
/opt/scripts/disk-monitor.sh

# Test with a lower threshold
THRESHOLD=10 /opt/scripts/disk-monitor.sh
```'''
    },
    {
        "instruction": r'''What's a good pattern for writing a deploy script that handles rolling back if something goes wrong?''',
        "output": r'''<think>
A deploy script with rollback needs:
1. Pre-deploy validation (is the build good? are dependencies met?)
2. Backup the current state before deploying
3. Deploy the new version
4. Health check after deploy
5. Automatic rollback if the health check fails

I should use a symlink-based deployment (like Capistrano style) where each deploy is a directory and "current" is a symlink. This makes rollback instant -- just change the symlink.
</think>

```bash
#!/bin/bash
set -euo pipefail

APP_DIR="/opt/myapp"
RELEASES_DIR="$APP_DIR/releases"
SHARED_DIR="$APP_DIR/shared"
CURRENT_LINK="$APP_DIR/current"
KEEP_RELEASES=5

RELEASE="$(date +%Y%m%d%H%M%S)"
RELEASE_DIR="$RELEASES_DIR/$RELEASE"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "FATAL: $*" >&2; exit 1; }

# Pre-flight checks
log "Starting deploy: release $RELEASE"
[ -f "build/app.tar.gz" ] || die "Build artifact not found"

# Record current release for rollback
PREVIOUS=""
if [ -L "$CURRENT_LINK" ]; then
    PREVIOUS=$(readlink "$CURRENT_LINK")
    log "Previous release: $PREVIOUS"
fi

# Deploy new release
log "Deploying to $RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
tar xzf build/app.tar.gz -C "$RELEASE_DIR"

# Link shared resources (logs, uploads, .env)
ln -sfn "$SHARED_DIR/.env" "$RELEASE_DIR/.env"
ln -sfn "$SHARED_DIR/logs" "$RELEASE_DIR/logs"

# Install dependencies
cd "$RELEASE_DIR"
pip install -r requirements.txt --quiet

# Switch the symlink (atomic operation)
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

# Restart the service
sudo systemctl restart myapp

# Health check (retry for 30 seconds)
log "Running health check..."
for i in $(seq 1 6); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log "Health check passed"
        break
    fi
    if [ "$i" -eq 6 ]; then
        log "Health check FAILED -- rolling back"
        if [ -n "$PREVIOUS" ]; then
            ln -sfn "$PREVIOUS" "$CURRENT_LINK"
            sudo systemctl restart myapp
            log "Rolled back to $PREVIOUS"
        fi
        exit 1
    fi
    sleep 5
done

# Cleanup old releases
cd "$RELEASES_DIR"
ls -1d */ | head -n -${KEEP_RELEASES} | xargs rm -rf || true

log "Deploy complete: $RELEASE"
```'''
    },
    {
        "instruction": r'''Show me how to use GNU Make with phony targets and automatic variables to build a multi-language project.''',
        "output": r'''```makefile
# Build C library + Python bindings + Go CLI
.PHONY: all clean test install

# Directories
SRC_DIR := src
BUILD_DIR := build
BIN_DIR := bin

# Compiler settings
CC := gcc
CFLAGS := -Wall -Wextra -O2 -fPIC
LDFLAGS := -shared

# Find all source files automatically
C_SRCS := $(wildcard $(SRC_DIR)/lib/*.c)
C_OBJS := $(patsubst $(SRC_DIR)/lib/%.c,$(BUILD_DIR)/%.o,$(C_SRCS))

# Default target
all: $(BIN_DIR)/libcore.so python-bindings go-cli

# Pattern rule: compile .c -> .o
# $< = first prerequisite, $@ = target
$(BUILD_DIR)/%.o: $(SRC_DIR)/lib/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Link shared library
# $^ = all prerequisites
$(BIN_DIR)/libcore.so: $(C_OBJS) | $(BIN_DIR)
	$(CC) $(LDFLAGS) $^ -o $@

# Create directories on demand
$(BUILD_DIR) $(BIN_DIR):
	mkdir -p $@

# Python bindings (depends on the C library)
.PHONY: python-bindings
python-bindings: $(BIN_DIR)/libcore.so
	cd bindings/python && pip install -e . --quiet

# Go CLI
.PHONY: go-cli
go-cli:
	cd cmd/cli && go build -o ../../$(BIN_DIR)/mycli .

# Tests for each component
test: test-c test-python test-go

test-c: $(BIN_DIR)/libcore.so
	cd tests/c && $(CC) -o test_core test_core.c -L../../$(BIN_DIR) -lcore && ./test_core

test-python: python-bindings
	cd bindings/python && pytest tests/ -q

test-go: go-cli
	cd cmd/cli && go test ./...

clean:
	rm -rf $(BUILD_DIR) $(BIN_DIR)

# Show variables (useful for debugging the Makefile)
debug:
	@echo "C_SRCS: $(C_SRCS)"
	@echo "C_OBJS: $(C_OBJS)"
```

Key concepts:
- `$@` = target name, `$<` = first dependency, `$^` = all dependencies
- `$(wildcard ...)` finds files matching a pattern
- `$(patsubst ...)` transforms file paths
- `| $(BUILD_DIR)` = order-only prerequisite (create dir but do not rebuild if dir changes)
- `.PHONY` marks targets that are not actual files'''
    },
]
