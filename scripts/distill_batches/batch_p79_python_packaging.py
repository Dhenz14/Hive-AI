"""Python — packaging, pyproject.toml, and dependency management."""

PAIRS = [
    (
        "python/pyproject-toml",
        "Show modern Python packaging with pyproject.toml: project metadata, build systems, optional dependencies, and scripts.",
        """Modern Python packaging with pyproject.toml:

```toml
# pyproject.toml — single file for all project configuration

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
version = "1.2.0"
description = "A well-structured Python package"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [
    { name = "Alice Smith", email = "alice@example.com" },
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

# Core dependencies
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.0,<3.0",
    "click>=8.0",
]

# Optional dependency groups
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "mypy>=1.10",
]
docs = [
    "mkdocs>=1.6",
    "mkdocs-material>=9.0",
]

# CLI entry points
[project.scripts]
myapp = "mypackage.cli:main"

# Plugin entry points
[project.entry-points."mypackage.plugins"]
csv = "mypackage.plugins.csv:CSVPlugin"
json = "mypackage.plugins.json:JSONPlugin"

[project.urls]
Homepage = "https://github.com/alice/mypackage"
Documentation = "https://mypackage.readthedocs.io"
Repository = "https://github.com/alice/mypackage"


# --- Tool configuration (all in one file) ---

[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["mypackage"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers"
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[tool.coverage.run]
source = ["mypackage"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__",
]
```

```
# Project layout
mypackage/
├── pyproject.toml
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── cli.py
│       ├── core.py
│       └── plugins/
│           ├── __init__.py
│           ├── csv.py
│           └── json.py
├── tests/
│   ├── __init__.py
│   ├── test_core.py
│   └── conftest.py
└── docs/
```

```bash
# Development workflow
pip install -e ".[dev]"      # Editable install with dev deps
pytest                        # Run tests
ruff check .                  # Lint
ruff format .                 # Format
mypy src/                     # Type check
python -m build               # Build sdist + wheel
twine upload dist/*           # Publish to PyPI
```

Packaging patterns:
1. **`pyproject.toml`** — single config for build, deps, and all tools
2. **`[project.optional-dependencies]`** — group extras like `pip install pkg[dev]`
3. **`[project.scripts]`** — auto-generate CLI entry points
4. **`src/` layout** — prevents accidental imports of uninstalled package
5. **`-e ".[dev]"`** — editable install with dev dependencies for local development"""
    ),
    (
        "python/dependency-management",
        "Show Python dependency management patterns: virtual environments, pip-tools, uv, and lock files.",
        """Python dependency management:

```bash
# --- Virtual environments ---

# Create with venv (stdlib)
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
.venv\\Scripts\\activate       # Windows

# Or with uv (10-100x faster)
uv venv
source .venv/bin/activate


# --- uv (modern, fast package manager) ---

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init myproject
cd myproject

# Add dependencies (auto-creates venv)
uv add httpx pydantic click
uv add --dev pytest ruff mypy

# Lock dependencies (generates uv.lock)
uv lock

# Sync environment from lock file
uv sync

# Run commands in project environment
uv run python main.py
uv run pytest

# Pin Python version
uv python pin 3.12


# --- pip-tools (deterministic installs) ---

# requirements.in (abstract dependencies)
# httpx>=0.27
# pydantic>=2.0,<3.0
# click>=8.0

# Compile to locked requirements.txt
pip-compile requirements.in --output-file requirements.txt
pip-compile requirements-dev.in --output-file requirements-dev.txt

# Install from lock file
pip-sync requirements.txt requirements-dev.txt

# Upgrade a specific package
pip-compile --upgrade-package httpx requirements.in


# --- Dependency groups (PEP 735 / pyproject.toml) ---

# [dependency-groups]
# test = ["pytest>=8", "pytest-cov>=5"]
# lint = ["ruff>=0.4", "mypy>=1.10"]
# dev = [{include-group = "test"}, {include-group = "lint"}]
#
# uv sync --group dev
```

```python
# --- Version constraints best practices ---

# pyproject.toml [project] dependencies

# GOOD: Allow compatible updates
dependencies = [
    "httpx>=0.27,<1.0",       # Minor/patch updates OK
    "pydantic>=2.0,<3.0",     # Within major version
    "click>=8.0",              # Minimum version, flexible
]

# BAD: Overly strict
# "httpx==0.27.0"            # Breaks on any update
# "pydantic"                 # No minimum, anything goes

# Lock files (uv.lock / requirements.txt) pin exact versions
# for reproducible deployments. Source deps stay flexible.


# --- Multi-environment CI example ---

# .github/workflows/test.yml
# jobs:
#   test:
#     strategy:
#       matrix:
#         python-version: ["3.11", "3.12", "3.13"]
#     steps:
#       - uses: actions/checkout@v4
#       - uses: astral-sh/setup-uv@v3
#       - run: uv sync --frozen
#       - run: uv run pytest --cov
```

Dependency management patterns:
1. **`uv`** — fast Rust-based tool: venv + install + lock in one tool
2. **Lock files** — pin exact versions for reproducible CI/production deploys
3. **Flexible source deps** — use `>=X.Y,<Z.0` ranges in pyproject.toml
4. **`pip-compile`** — compile abstract deps to locked concrete versions
5. **Dependency groups** — separate test/lint/docs deps, install what you need"""
    ),
    (
        "database/sql-advanced",
        "Show advanced SQL patterns: CTEs, window functions, recursive queries, lateral joins, and query optimization.",
        """Advanced SQL patterns:

```sql
-- --- Common Table Expressions (CTEs) ---

-- Named subqueries for readability
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', ordered_at) AS month,
        SUM(total) AS revenue,
        COUNT(DISTINCT customer_id) AS customers
    FROM orders
    WHERE ordered_at >= '2024-01-01'
    GROUP BY 1
),
growth AS (
    SELECT
        month,
        revenue,
        customers,
        LAG(revenue) OVER (ORDER BY month) AS prev_revenue,
        revenue - LAG(revenue) OVER (ORDER BY month) AS revenue_change,
        ROUND(
            (revenue - LAG(revenue) OVER (ORDER BY month))
            / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) * 100, 1
        ) AS growth_pct
    FROM monthly_revenue
)
SELECT * FROM growth ORDER BY month;


-- --- Window functions ---

-- Rank customers by spend
SELECT
    customer_id,
    name,
    total_spend,
    RANK() OVER (ORDER BY total_spend DESC) AS spend_rank,
    NTILE(4) OVER (ORDER BY total_spend DESC) AS quartile,
    total_spend / SUM(total_spend) OVER () * 100 AS pct_of_total,
    SUM(total_spend) OVER (ORDER BY total_spend DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_spend
FROM (
    SELECT customer_id, name, SUM(total) AS total_spend
    FROM orders JOIN customers USING (customer_id)
    GROUP BY customer_id, name
) t;

-- Moving average (7-day)
SELECT
    order_date,
    daily_revenue,
    AVG(daily_revenue) OVER (
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM daily_sales;


-- --- Recursive CTEs ---

-- Org chart traversal
WITH RECURSIVE org_tree AS (
    -- Base case: top-level managers
    SELECT id, name, manager_id, 1 AS depth, name::text AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: employees reporting to known managers
    SELECT e.id, e.name, e.manager_id, t.depth + 1,
           t.path || ' > ' || e.name
    FROM employees e
    JOIN org_tree t ON e.manager_id = t.id
    WHERE t.depth < 10  -- Safety limit
)
SELECT * FROM org_tree ORDER BY path;

-- Generate date series
WITH RECURSIVE dates AS (
    SELECT DATE '2024-01-01' AS d
    UNION ALL
    SELECT d + INTERVAL '1 day' FROM dates WHERE d < '2024-12-31'
)
SELECT d AS date FROM dates;


-- --- LATERAL join (correlated subquery as join) ---

-- Top 3 orders per customer
SELECT c.name, t.order_id, t.total, t.ordered_at
FROM customers c
CROSS JOIN LATERAL (
    SELECT order_id, total, ordered_at
    FROM orders
    WHERE customer_id = c.id
    ORDER BY total DESC
    LIMIT 3
) t;


-- --- Upsert (INSERT ... ON CONFLICT) ---

INSERT INTO product_stats (product_id, view_count, last_viewed)
VALUES ('prod-123', 1, NOW())
ON CONFLICT (product_id) DO UPDATE SET
    view_count = product_stats.view_count + 1,
    last_viewed = EXCLUDED.last_viewed;


-- --- FILTER clause (conditional aggregation) ---

SELECT
    DATE_TRUNC('month', ordered_at) AS month,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
    COUNT(*) FILTER (WHERE status = 'refunded') AS refunded,
    SUM(total) FILTER (WHERE status = 'completed') AS net_revenue,
    AVG(total) FILTER (WHERE status = 'completed' AND total > 100) AS avg_large_order
FROM orders
GROUP BY 1
ORDER BY 1;


-- --- Query optimization hints ---

-- Check query plan
EXPLAIN ANALYZE
SELECT * FROM orders WHERE customer_id = 'cust-123' AND ordered_at > '2024-01-01';

-- Partial index (only index what you query)
CREATE INDEX idx_orders_active
    ON orders (customer_id, ordered_at)
    WHERE status = 'active';

-- Covering index (index-only scan)
CREATE INDEX idx_orders_covering
    ON orders (customer_id) INCLUDE (total, ordered_at);

-- Expression index
CREATE INDEX idx_orders_month
    ON orders (DATE_TRUNC('month', ordered_at));
```

Advanced SQL patterns:
1. **CTEs** — named subqueries for readable multi-step transformations
2. **Window functions** — rank, running totals, moving averages without self-joins
3. **Recursive CTEs** — tree traversal, date generation, graph walks
4. **`LATERAL` joins** — correlated subquery as a join (top-N per group)
5. **`FILTER` clause** — conditional aggregation cleaner than CASE WHEN"""
    ),
]
