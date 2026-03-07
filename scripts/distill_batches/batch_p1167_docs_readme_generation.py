"""Documentation generation training pairs: README.md sections from project code."""

pairs = [
    {
        "instruction": r'''Write a README "Getting Started" section for this CLI tool. Here's the main entry point:

import click
import yaml
from pathlib import Path

@click.group()
@click.option("--config", "-c", default="taskrunner.yaml", help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config, verbose):
    ctx.ensure_object(dict)
    ctx.obj["config"] = yaml.safe_load(Path(config).read_text())
    ctx.obj["verbose"] = verbose

@cli.command()
@click.argument("task_name")
@click.option("--dry-run", is_flag=True, help="Show what would be executed")
def run(task_name, dry_run):
    """Execute a defined task."""
    ...

@cli.command()
def list():
    """List all available tasks."""
    ...

@cli.command()
@click.argument("task_name")
def validate(task_name):
    """Validate a task definition without running it."""
    ...

# setup.py has: entry_points={"console_scripts": ["taskrunner=taskrunner.cli:cli"]}
# requirements: click>=8.0, pyyaml>=6.0''',
        "output": r'''## Getting Started

### Prerequisites

- Python 3.8 or later
- pip

### Installation

```bash
pip install taskrunner
```

Or install from source:

```bash
git clone https://github.com/yourorg/taskrunner.git
cd taskrunner
pip install -e .
```

### Configuration

Create a `taskrunner.yaml` file in your project root:

```yaml
tasks:
  build:
    command: "make build"
    description: "Compile the project"
  test:
    command: "pytest tests/"
    description: "Run the test suite"
  deploy:
    command: "scripts/deploy.sh"
    description: "Deploy to production"
```

### Basic Usage

List all available tasks:

```bash
taskrunner list
```

Run a task:

```bash
taskrunner run build
```

Preview what a task would do without executing it:

```bash
taskrunner run deploy --dry-run
```

Validate a task definition:

```bash
taskrunner validate build
```

### Options

| Flag             | Short | Description                             |
|------------------|-------|-----------------------------------------|
| --config FILE    | -c    | Path to config file (default: taskrunner.yaml) |
| --verbose        | -v    | Enable debug logging                    |
| --help           |       | Show help and exit                      |

You can use a custom config file with any command:

```bash
taskrunner -c production.yaml run deploy
```'''
    },
    {
        "instruction": r'''Generate a README "Installation" and "Quick Start" section for this Python library based on its setup.py and main module:

# setup.py
setup(
    name="datavalidator",
    version="2.1.0",
    python_requires=">=3.9",
    install_requires=["pydantic>=2.0", "email-validator>=2.0"],
    extras_require={
        "async": ["aiohttp>=3.8"],
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.21"],
    },
)

# datavalidator/core.py
class Validator:
    def __init__(self, rules=None, strict=False):
        self.rules = rules or {}
        self.strict = strict

    def validate(self, data):
        ...
        return ValidationResult(valid=True, data=cleaned)

    def validate_many(self, records):
        return [self.validate(r) for r in records]

    @classmethod
    def from_schema_file(cls, path):
        schema = json.loads(Path(path).read_text())
        return cls(rules=schema.get("rules"), strict=schema.get("strict", False))''',
        "output": r'''<think>
I need to write README sections covering installation (with extras) and a quick start showing the main class. The setup.py tells me: Python 3.9+, two install methods (basic and with extras), and there is a dev extra for contributors. The core.py shows three main usage patterns: direct construction, validate single/many, and from_schema_file.
</think>

## Installation

Install from PyPI:

```bash
pip install datavalidator
```

If you need async support:

```bash
pip install datavalidator[async]
```

For development (includes test dependencies):

```bash
pip install datavalidator[dev]
```

**Requirements:** Python 3.9 or later.

## Quick Start

### Basic validation

```python
from datavalidator import Validator

rules = {
    "email": {"type": "email", "required": True},
    "age": {"type": "int", "min": 0, "max": 150},
    "role": {"type": "string", "choices": ["admin", "user", "guest"]},
}

v = Validator(rules=rules, strict=True)
result = v.validate({"email": "user@example.com", "age": 30, "role": "admin"})

if result.valid:
    print("Clean data:", result.data)
else:
    print("Errors:", result.errors)
```

### Validate multiple records

```python
records = [
    {"email": "a@test.com", "age": 25},
    {"email": "invalid", "age": -1},
]
results = v.validate_many(records)
for r in results:
    print(r.valid, r.errors)
```

### Load rules from a JSON file

```python
v = Validator.from_schema_file("schema.json")
result = v.validate(user_input)
```

Where `schema.json` looks like:

```json
{
    "strict": true,
    "rules": {
        "name": {"type": "string", "required": true},
        "email": {"type": "email", "required": true}
    }
}
```'''
    },
    {
        "instruction": r'''Write a "Configuration" section for this project's README. Here are the relevant config loading bits:

# config.py
import os
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    db_url: str = "sqlite:///app.db"
    db_pool_size: int = 5
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = ""
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list = field(default_factory=lambda: ["http://localhost:3000"])
    max_upload_mb: int = 25
    worker_count: int = 4
    rate_limit_per_minute: int = 60

def load_config():
    return AppConfig(
        db_url=os.getenv("APP_DB_URL", AppConfig.db_url),
        db_pool_size=int(os.getenv("APP_DB_POOL_SIZE", AppConfig.db_pool_size)),
        redis_url=os.getenv("APP_REDIS_URL", AppConfig.redis_url),
        secret_key=os.getenv("APP_SECRET_KEY", ""),
        debug=os.getenv("APP_DEBUG", "").lower() in ("1", "true", "yes"),
        log_level=os.getenv("APP_LOG_LEVEL", AppConfig.log_level),
        cors_origins=os.getenv("APP_CORS_ORIGINS", "http://localhost:3000").split(","),
        max_upload_mb=int(os.getenv("APP_MAX_UPLOAD_MB", AppConfig.max_upload_mb)),
        worker_count=int(os.getenv("APP_WORKER_COUNT", AppConfig.worker_count)),
        rate_limit_per_minute=int(os.getenv("APP_RATE_LIMIT", AppConfig.rate_limit_per_minute)),
    )''',
        "output": r'''## Configuration

The application is configured via environment variables. All variables are optional and have sensible defaults for local development.

### Environment Variables

| Variable             | Type    | Default                  | Description                                      |
|----------------------|---------|--------------------------|--------------------------------------------------|
| APP_DB_URL           | string  | sqlite:///app.db         | Database connection string (SQLAlchemy format)    |
| APP_DB_POOL_SIZE     | int     | 5                        | Max database connections in the pool              |
| APP_REDIS_URL        | string  | redis://localhost:6379/0 | Redis connection URL for caching and sessions     |
| APP_SECRET_KEY       | string  | (empty)                  | Secret key for signing tokens. **Set this in production.** |
| APP_DEBUG            | bool    | false                    | Enable debug mode (accepts "1", "true", or "yes") |
| APP_LOG_LEVEL        | string  | INFO                     | Logging level (DEBUG, INFO, WARNING, ERROR)       |
| APP_CORS_ORIGINS     | string  | http://localhost:3000    | Comma-separated list of allowed CORS origins      |
| APP_MAX_UPLOAD_MB    | int     | 25                       | Maximum file upload size in megabytes             |
| APP_WORKER_COUNT     | int     | 4                        | Number of background worker processes             |
| APP_RATE_LIMIT       | int     | 60                       | Max API requests per user per minute              |

### Example .env file

```bash
APP_DB_URL=postgresql://user:pass@db-host:5432/myapp
APP_DB_POOL_SIZE=20
APP_REDIS_URL=redis://redis-host:6379/0
APP_SECRET_KEY=your-random-secret-key-here
APP_DEBUG=false
APP_LOG_LEVEL=WARNING
APP_CORS_ORIGINS=https://myapp.com,https://admin.myapp.com
APP_MAX_UPLOAD_MB=50
APP_WORKER_COUNT=8
APP_RATE_LIMIT=120
```

### Production Notes

- **APP_SECRET_KEY** must be set to a strong random value. Generate one with: `python -c "import secrets; print(secrets.token_hex(32))"`
- **APP_DEBUG** should always be `false` in production.
- **APP_DB_URL** should point to PostgreSQL (not SQLite) for production workloads.'''
    },
    {
        "instruction": r'''Write a "Usage Examples" README section for this image processing library:

class ImagePipeline:
    def __init__(self, path):
        self.img = Image.open(path)
        self.history = []

    def resize(self, width, height, keep_aspect=True):
        ...
        return self

    def crop(self, left, top, right, bottom):
        ...
        return self

    def rotate(self, degrees, expand=True):
        ...
        return self

    def apply_filter(self, filter_name):
        # supports: "blur", "sharpen", "grayscale", "sepia", "edge_detect"
        ...
        return self

    def watermark(self, text, position="bottom-right", opacity=0.5):
        ...
        return self

    def save(self, output_path, quality=85, format=None):
        ...

    def undo(self, steps=1):
        ...
        return self''',
        "output": r'''<think>
The ImagePipeline uses a fluent/builder pattern where each method returns self. That means I should show chained calls. I need to show several realistic examples: basic resize, chained operations, watermarking, undo, and saving in different formats. I should keep code examples practical and short.
</think>

## Usage Examples

### Basic image resize

```python
from imgpipeline import ImagePipeline

ImagePipeline("photo.jpg").resize(800, 600).save("photo_small.jpg")
```

### Chain multiple operations

Operations can be chained in any order. Each step is recorded in the history for undo support.

```python
(ImagePipeline("input.png")
    .resize(1920, 1080)
    .apply_filter("sharpen")
    .crop(100, 50, 1820, 1030)
    .save("output.png", quality=95))
```

### Apply filters

Supported filters: `blur`, `sharpen`, `grayscale`, `sepia`, `edge_detect`.

```python
pipeline = ImagePipeline("portrait.jpg")
pipeline.apply_filter("grayscale").save("portrait_bw.jpg")
```

### Add a watermark

```python
(ImagePipeline("product.jpg")
    .resize(1200, 900)
    .watermark("(c) 2024 MyBrand", position="bottom-right", opacity=0.3)
    .save("product_watermarked.jpg"))
```

### Undo mistakes

Every operation is tracked. Call `undo()` to step back.

```python
p = ImagePipeline("photo.jpg")
p.apply_filter("blur")
p.apply_filter("sepia")
p.undo(steps=1)         # removes sepia, keeps blur
p.save("photo_blur.jpg")
```

### Save in different formats

```python
p = ImagePipeline("photo.png")
p.save("photo.jpg", quality=90, format="JPEG")
p.save("photo.webp", quality=80, format="WEBP")
```'''
    },
    {
        "instruction": r'''Write a "Contributing" section for a README based on this project structure:

# Project uses:
# - Python 3.11+
# - poetry for dependency management
# - pytest with coverage
# - ruff for linting
# - mypy for type checking
# - pre-commit hooks
# - conventional commits
# - GitHub Actions CI

# Makefile targets:
# make install - poetry install
# make test - pytest --cov
# make lint - ruff check . && mypy .
# make format - ruff format .
# make all - format lint test''',
        "output": r'''## Contributing

Contributions are welcome. Please follow these guidelines to keep the process smooth.

### Setup

1. Fork and clone the repository.

2. Install Python 3.11 or later and [Poetry](https://python-poetry.org/).

3. Install dependencies and set up pre-commit hooks:

```bash
make install
poetry run pre-commit install
```

### Development Workflow

Run all checks (formatting, linting, tests) in one command:

```bash
make all
```

Or run individual steps:

```bash
make format    # auto-format code with ruff
make lint      # run ruff linter + mypy type checks
make test      # run pytest with coverage report
```

### Commit Messages

This project follows [Conventional Commits](https://www.conventionalcommits.org/). Use one of these prefixes:

- `feat:` -- new feature
- `fix:` -- bug fix
- `docs:` -- documentation only
- `refactor:` -- code change that neither fixes a bug nor adds a feature
- `test:` -- adding or updating tests
- `chore:` -- maintenance (deps, CI config, etc.)

Example: `feat: add CSV export support`

### Pull Request Process

1. Create a feature branch from `main` (`git checkout -b feat/my-feature`).
2. Make your changes and ensure `make all` passes.
3. Push to your fork and open a pull request.
4. Fill out the PR template and link any related issues.
5. A maintainer will review your PR. CI must pass before merging.

### Code Standards

- All public functions and classes must have type annotations.
- New features require tests (aim for >90% coverage).
- No linting warnings or type errors in CI.'''
    },
]
