"""
Response variety training pairs - Progressive disclosure (simple answer, then depth)
Opens with a 1-2 sentence TL;DR, then progressively adds detail.
"""

pairs = [
    {
        "instruction": r'''How do I handle environment variables in a Node.js project?''',
        "output": r'''Short answer: use a `.env` file with the `dotenv` package for local development, and real environment variables in production. Here's how to set it up properly.

Install dotenv:

```bash
npm install dotenv
```

Create a `.env` file in your project root:

```
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
API_KEY=sk-abc123
PORT=3000
NODE_ENV=development
```

Load it at the very top of your entry point:

```javascript
// src/index.js -- this MUST be the first line
require('dotenv').config();

// Now process.env.DATABASE_URL is available
console.log(process.env.PORT); // "3000"
```

Going deeper -- you'll want validation so your app fails fast if a required variable is missing:

```javascript
// src/config.js
require('dotenv').config();

function requireEnv(name) {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Missing required environment variable: ${name}`);
    }
    return value;
}

const config = {
    port: parseInt(process.env.PORT || '3000', 10),
    databaseUrl: requireEnv('DATABASE_URL'),
    apiKey: requireEnv('API_KEY'),
    isProduction: process.env.NODE_ENV === 'production',
    logLevel: process.env.LOG_LEVEL || 'info',
};

module.exports = config;
```

Then import `config` everywhere instead of accessing `process.env` directly:

```javascript
const config = require('./config');
app.listen(config.port);
```

Important: add `.env` to your `.gitignore` immediately. Commit a `.env.example` with placeholder values so other developers know which variables they need:

```
# .env.example -- copy to .env and fill in values
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
API_KEY=your-api-key-here
PORT=3000
```

For production (Docker, Heroku, AWS), set real environment variables through the platform's UI or deployment config -- never deploy a `.env` file to production.'''
    },
    {
        "instruction": r'''Should I use async/await or threads in Python?''',
        "output": r'''Short answer: use async/await for I/O-heavy workloads (web servers, API calls, database queries) and threads for legacy blocking code you can't rewrite. Here's the reasoning and when each one shines.

Async/await is cooperative multitasking -- your code voluntarily yields control when waiting on I/O:

```python
import asyncio
import httpx

async def fetch_all(urls):
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.json() for r in responses]

# Fetches 100 URLs concurrently in ~1 second instead of ~100 seconds
urls = [f"https://api.example.com/item/{i}" for i in range(100)]
results = asyncio.run(fetch_all(urls))
```

Threads use OS-level preemptive switching. They work with existing blocking libraries but have the GIL limitation:

```python
from concurrent.futures import ThreadPoolExecutor
import requests

def fetch(url):
    return requests.get(url).json()

with ThreadPoolExecutor(max_workers=20) as pool:
    results = list(pool.map(fetch, urls))
```

When to use which:

- **Async/await**: new projects, web servers (FastAPI, aiohttp), anything with native async library support. Lower memory per connection, handles thousands of concurrent connections easily.
- **Threads**: calling blocking libraries that don't have async versions (some database drivers, file operations, subprocess calls). Also fine for moderate concurrency (tens of threads, not thousands).
- **Multiprocessing**: CPU-bound work (number crunching, image processing). Neither async nor threads help here because of the GIL.

```python
# Mixing both -- run blocking code in an async context
import asyncio

async def process_data():
    loop = asyncio.get_event_loop()
    # Run blocking function in a thread pool
    result = await loop.run_in_executor(None, blocking_database_call, params)
    return result
```

The key insight: async/await is not faster than threads for a single operation. The advantage is efficiency at scale -- an async server can handle 10,000 concurrent connections with minimal memory, while 10,000 threads would consume gigabytes of stack space.'''
    },
    {
        "instruction": r'''What's the best way to handle errors in a REST API?''',
        "output": r'''Short answer: return consistent JSON error responses with appropriate HTTP status codes, and never expose internal details to clients. Here's how to build that properly.

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from typing import Any

class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details

app = FastAPI()

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    import logging
    logging.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )

# Usage in routes
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    if not user:
        raise AppError("NOT_FOUND", f"User {user_id} not found", status=404)
    return user

@app.post("/users")
async def create_user(data: UserCreate):
    if await db.get_user_by_email(data.email):
        raise AppError("DUPLICATE_EMAIL", "Email already exists", status=409)
    return await db.create_user(data)
```

Going deeper -- use the right status codes:

- 400: bad input (validation errors, malformed JSON)
- 401: not authenticated (missing/invalid token)
- 403: authenticated but not authorized
- 404: resource not found
- 409: conflict (duplicate, version mismatch)
- 429: rate limited
- 500: server bug, never the client's fault

The `code` field (like "DUPLICATE_EMAIL") is machine-readable so frontends can show specific UI per error type. Never include stack traces, SQL queries, or file paths in production responses.'''
    },
    {
        "instruction": r'''How do I set up CI/CD for a Python project?''',
        "output": r'''Short answer: use GitHub Actions with a workflow that runs linting, tests, and deploys on merge to main. Here's a setup that covers the essentials.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('pyproject.toml') }}

      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/
      - run: pytest tests/ -v --cov=src

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - run: echo "Your deploy commands here"
```

Your `pyproject.toml` should define dev dependencies:

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov", "ruff", "mypy"]
```

Going deeper -- the `deploy` job uses `needs: test` so it only runs after tests pass, and the `if` condition ensures it only deploys from main, not from PRs.

For secrets (API keys, deploy credentials), add them in GitHub Settings -> Secrets, then reference as `${{ secrets.DEPLOY_KEY }}`.

Add a branch protection rule requiring CI to pass before merging. That's the "CD" part -- every merge to main auto-deploys, and broken code can't get merged.'''
    },
    {
        "instruction": r'''What's the best way to structure a Python package?''',
        "output": r'''Short answer: use a `src/` layout with `pyproject.toml` as the single config file. Here's what that looks like and why each piece matters.

The recommended structure:

```
my-package/
  src/
    my_package/
      __init__.py
      core.py
      utils.py
      models/
        __init__.py
        user.py
  tests/
    __init__.py
    test_core.py
    test_utils.py
    conftest.py
  pyproject.toml
  README.md
  LICENSE
```

The `pyproject.toml` replaces setup.py, setup.cfg, and most other config files:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-package"
version = "0.1.0"
description = "A useful package"
requires-python = ">=3.10"
dependencies = [
    "httpx>=0.25",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]

[project.scripts]
my-cli = "my_package.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]

[tool.mypy]
strict = true
```

Why the `src/` layout? It forces you to install your package before testing it (`pip install -e .`), which catches packaging bugs early. Without `src/`, Python can import your code directly from the project root, masking issues like missing `__init__.py` files or forgotten package data.

Going deeper -- common patterns inside the package:

```python
# src/my_package/__init__.py -- public API
from my_package.core import process_data
from my_package.models.user import User

__all__ = ["process_data", "User"]
__version__ = "0.1.0"
```

```python
# src/my_package/core.py -- keep modules focused
from my_package.utils import validate_input
from my_package.models.user import User

def process_data(raw: dict) -> User:
    validated = validate_input(raw)
    return User(**validated)
```

```python
# tests/conftest.py -- shared fixtures
import pytest
from my_package import User

@pytest.fixture
def sample_user():
    return User(name="Alice", email="alice@example.com")
```

Install for development with `pip install -e ".[dev]"`. The `-e` flag means editable mode -- code changes take effect immediately without reinstalling. The `[dev]` installs the optional dev dependencies (pytest, ruff, etc.).'''
    },
]
