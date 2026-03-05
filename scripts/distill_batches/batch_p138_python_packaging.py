"""Python packaging — pyproject.toml, CLI tools, and distribution."""

PAIRS = [
    (
        "python/pyproject-toml",
        "Show modern Python project setup with pyproject.toml: dependencies, build config, tool settings, and optional extras.",
        '''Modern Python project setup with pyproject.toml:

```toml
# --- pyproject.toml ---

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
version = "1.0.0"
description = "A well-structured Python package"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "Alice", email = "alice@example.com" },
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Typing :: Typed",
]

dependencies = [
    "httpx>=0.25",
    "pydantic>=2.0",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov",
    "pytest-asyncio",
    "mypy",
    "ruff",
]
docs = [
    "mkdocs",
    "mkdocs-material",
]
postgres = [
    "asyncpg>=0.28",
    "sqlalchemy[asyncio]>=2.0",
]

# CLI entry points
[project.scripts]
myapp = "mypackage.cli:main"

# Plugin entry points
[project.entry-points."mypackage.plugins"]
default = "mypackage.plugins.default:DefaultPlugin"

[project.urls]
Homepage = "https://github.com/alice/mypackage"
Documentation = "https://mypackage.readthedocs.io"
Repository = "https://github.com/alice/mypackage"
Issues = "https://github.com/alice/mypackage/issues"


# --- Tool configuration ---

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # type-checking imports
]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.lint.isort]
known-first-party = ["mypackage"]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers --tb=short"
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[tool.coverage.run]
source = ["mypackage"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__",
]
fail_under = 80
```

```
# --- Project structure ---

mypackage/
├── pyproject.toml
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── py.typed          # PEP 561 marker for type stubs
│       ├── cli.py
│       ├── core/
│       │   ├── __init__.py
│       │   └── models.py
│       └── plugins/
│           ├── __init__.py
│           └── default.py
├── tests/
│   ├── conftest.py
│   ├── test_core.py
│   └── test_cli.py
└── docs/
```

```bash
# --- Common commands ---

# Install in dev mode with extras
pip install -e ".[dev,postgres]"

# Build distribution
python -m build

# Upload to PyPI
twine upload dist/*

# Run tools
ruff check .           # Lint
ruff format .          # Format
mypy src/              # Type check
pytest --cov           # Test with coverage
```

Python packaging patterns:
1. **`pyproject.toml`** — single config file replaces setup.py, setup.cfg, and tool configs
2. **`[project.scripts]`** — auto-generated CLI entry points installed with the package
3. **`[project.optional-dependencies]`** — `pip install "pkg[dev,postgres]"` for optional groups
4. **`src/` layout** — prevents importing uninstalled package from project root
5. **`py.typed` marker** — PEP 561 signals that package includes inline type annotations'''
    ),
    (
        "python/makefile-tasks",
        "Show Makefile patterns for Python projects: common tasks, virtual environments, and CI shortcuts.",
        '''Makefile patterns for Python projects:

```makefile
# --- Makefile ---

.PHONY: help install dev test lint format check clean build docs serve

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \\
		awk 'BEGIN {FS = ":.*?## "}; {printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}'

# --- Setup ---

PYTHON := python3
VENV := .venv
BIN := $(VENV)/bin

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: $(VENV)/bin/activate ## Install production dependencies
	$(BIN)/pip install -e .

dev: $(VENV)/bin/activate ## Install development dependencies
	$(BIN)/pip install -e ".[dev]"
	$(BIN)/pre-commit install

# --- Testing ---

test: ## Run tests
	$(BIN)/pytest

test-cov: ## Run tests with coverage report
	$(BIN)/pytest --cov --cov-report=html --cov-report=term-missing

test-watch: ## Run tests in watch mode
	$(BIN)/ptw -- --tb=short -q

test-fast: ## Run tests excluding slow markers
	$(BIN)/pytest -m "not slow" -x -q

# --- Code quality ---

lint: ## Run linter
	$(BIN)/ruff check src/ tests/

format: ## Format code
	$(BIN)/ruff format src/ tests/
	$(BIN)/ruff check --fix src/ tests/

typecheck: ## Run type checker
	$(BIN)/mypy src/

check: lint typecheck test ## Run all checks (lint + types + tests)

# --- Build and publish ---

build: clean ## Build distribution packages
	$(BIN)/python -m build

publish-test: build ## Publish to TestPyPI
	$(BIN)/twine upload --repository testpypi dist/*

publish: build ## Publish to PyPI
	$(BIN)/twine upload dist/*

# --- Documentation ---

docs: ## Build documentation
	$(BIN)/mkdocs build

serve: ## Serve documentation locally
	$(BIN)/mkdocs serve

# --- Database ---

db-migrate: ## Run database migrations
	$(BIN)/alembic upgrade head

db-rollback: ## Rollback last migration
	$(BIN)/alembic downgrade -1

db-migration: ## Create new migration (usage: make db-migration msg="add users")
	$(BIN)/alembic revision --autogenerate -m "$(msg)"

# --- Docker ---

docker-build: ## Build Docker image
	docker build -t myapp:latest .

docker-run: ## Run Docker container
	docker run -p 8000:8000 --env-file .env myapp:latest

# --- Cleanup ---

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
```

```bash
# Usage:
make help          # Show all available targets
make dev           # Set up development environment
make check         # Run full CI check locally
make test-fast     # Quick test run
make db-migration msg="add orders table"
```

Makefile patterns:
1. **`help` target** — auto-generated from `## comments` with colored output
2. **Venv as prerequisite** — `$(VENV)/bin/activate` creates venv only if missing
3. **`check` target** — combines lint + typecheck + test for local CI simulation
4. **`$(BIN)` prefix** — all commands use venv Python without manual activation
5. **`.PHONY`** — declare non-file targets to prevent conflicts with filenames'''
    ),
]
"""
