"""Python packaging — pyproject.toml, distribution, virtual environments, and dependency management."""

PAIRS = [
    (
        "python/modern-packaging",
        "Show modern Python packaging with pyproject.toml: project configuration, build systems, entry points, and publishing to PyPI.",
        '''Modern Python packaging with pyproject.toml:

```toml
# pyproject.toml — Single source of truth for project config

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "myapp"
version = "1.2.0"
description = "A production-ready Python application"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Alice Smith", email = "alice@example.com"},
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
    "httpx>=0.24",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "mypy>=1.0",
    "ruff>=0.1",
    "pre-commit>=3.0",
]
docs = [
    "mkdocs>=1.5",
    "mkdocs-material>=9.0",
]

[project.scripts]
# CLI entry points
myapp = "myapp.cli:main"
myapp-worker = "myapp.worker:main"

[project.urls]
Homepage = "https://github.com/alice/myapp"
Documentation = "https://myapp.readthedocs.io"
Repository = "https://github.com/alice/myapp"
Issues = "https://github.com/alice/myapp/issues"

# --- Tool configuration ---

[tool.ruff]
target-version = "py310"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TCH"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["myapp"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: marks tests as slow",
    "integration: integration tests",
]

[tool.coverage.run]
source = ["myapp"]
branch = true

[tool.coverage.report]
show_missing = true
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__",
]
```

```python
# --- Project structure ---

# myapp/
# ├── pyproject.toml
# ├── src/
# │   └── myapp/
# │       ├── __init__.py
# │       ├── cli.py
# │       ├── main.py
# │       └── models.py
# ├── tests/
# │   ├── conftest.py
# │   └── test_main.py
# └── .github/
#     └── workflows/
#         └── publish.yml

# src/myapp/__init__.py
__version__ = "1.2.0"

# src/myapp/cli.py
import argparse

def main():
    parser = argparse.ArgumentParser(description="MyApp CLI")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    # Start app...
```

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # Trusted publishing
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        # No API key needed with trusted publishing!
```

```bash
# Development workflow
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # Editable install with dev deps
pytest                             # Run tests
ruff check . && ruff format .      # Lint and format
mypy src/                          # Type check
python -m build                    # Build wheel and sdist
twine check dist/*                 # Validate package
```

Key decisions:
1. **`hatchling`** — modern, fast build backend (alternatives: setuptools, flit)
2. **`src/` layout** — prevents importing uninstalled package
3. **Editable install** — `pip install -e .` for development
4. **Trusted publishing** — PyPI OIDC, no API keys needed
5. **Single `pyproject.toml`** — replaces setup.py, setup.cfg, MANIFEST.in'''
    ),
    (
        "python/dependency-management",
        "Show Python dependency management patterns: pip-tools, uv, lock files, virtual environments, and reproducible builds.",
        '''Python dependency management for reproducible builds:

```bash
# --- uv: Fast Python package manager ---

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project with uv
uv init myproject
cd myproject

# Add dependencies
uv add fastapi uvicorn sqlalchemy
uv add --dev pytest ruff mypy

# Lock dependencies (creates uv.lock)
uv lock

# Sync environment from lock file
uv sync

# Run commands in the virtual env
uv run python -m pytest
uv run myapp serve

# Update a specific dependency
uv lock --upgrade-package fastapi

# Show dependency tree
uv tree
```

```toml
# pyproject.toml with uv
[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.100",
    "sqlalchemy>=2.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=7.0",
    "ruff>=0.1",
]
```

```bash
# --- pip-tools: Pinned requirements ---

# Install pip-tools
pip install pip-tools

# requirements.in — top-level dependencies (unpinned)
cat > requirements.in << 'EOF'
fastapi>=0.100
uvicorn[standard]
sqlalchemy>=2.0
httpx
EOF

# Compile to pinned requirements.txt
pip-compile requirements.in -o requirements.txt --strip-extras

# Output: requirements.txt with exact versions + hashes
# fastapi==0.110.0
# uvicorn[standard]==0.27.1
# sqlalchemy==2.0.28
# ...all transitive deps pinned

# Compile dev requirements
pip-compile requirements-dev.in -o requirements-dev.txt

# Sync environment to match lock file exactly
pip-sync requirements.txt requirements-dev.txt

# Update all dependencies
pip-compile --upgrade requirements.in

# Update single package
pip-compile --upgrade-package fastapi requirements.in
```

```python
# --- Virtual environment best practices ---

import subprocess
import sys
from pathlib import Path

def setup_project():
    """Automated project setup."""
    venv_dir = Path(".venv")

    # Create venv if not exists
    if not venv_dir.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)])

    # Determine pip path
    pip = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"

    # Install from lock file
    subprocess.run([str(pip), "install", "-r", "requirements.txt"])
    subprocess.run([str(pip), "install", "-r", "requirements-dev.txt"])
    subprocess.run([str(pip), "install", "-e", "."])

    print("Environment ready! Activate with:")
    if sys.platform == "win32":
        print("  .venv\\\\Scripts\\\\activate")
    else:
        print("  source .venv/bin/activate")
```

```dockerfile
# --- Reproducible Docker builds ---
FROM python:3.12-slim

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install dependencies from lock file (cached layer)
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

Tool comparison:
- **uv** — fastest, all-in-one (venv + install + lock), Rust-based
- **pip-tools** — simple compile/sync workflow, generates requirements.txt
- **poetry** — all-in-one with own lock format, slower than uv
- **pdm** — PEP 582 support, modern resolver

Best practices:
1. **Always lock** — pinned versions for reproducible builds
2. **Separate dev deps** — don't ship test tools in production
3. **Hash checking** — `--require-hashes` for supply chain security
4. **CI uses lock file** — never `pip install` without pinned versions'''
    ),
]
