"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 13)"""

PAIRS = [
    (
        "thinking/meta-reasoning-makefile-vs-taskpy",
        r'''For automating Python project tasks (test, lint, build, deploy), compare Makefile vs a Python task runner:

Approach A — Makefile:
```makefile
.PHONY: test lint format build deploy

test:
	pytest tests/ -v --cov=src

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

build: test lint
	docker build -t myapp .

deploy: build
	docker push myapp:latest
	kubectl apply -f k8s/
```

Approach B — Python task runner (invoke):
```python
from invoke import task

@task
def test(c):
    c.run("pytest tests/ -v --cov=src")

@task
def lint(c):
    c.run("ruff check src/ tests/")
    c.run("mypy src/")

@task
def format(c):
    c.run("black src/ tests/")
    c.run("ruff check --fix src/ tests/")

@task(pre=[test, lint])
def build(c):
    c.run("docker build -t myapp .")

@task(pre=[build])
def deploy(c):
    c.run("docker push myapp:latest")
    c.run("kubectl apply -f k8s/")
```

Which is better for a Python project?''',
        r'''<think>
Comparing Makefile vs Python task runner (invoke) for project automation...

Approach A — Makefile:
- Universal — available on every Unix system, no pip install
- Well-understood by most developers
- Dependency chaining built in (build: test lint)
- Tab-indentation requirement is a classic gotcha
- Not Python-specific — works for any project type
- No conditional logic beyond shell commands
- make is not available by default on Windows

Approach B — invoke:
- Python-native — team already knows Python
- Real programming language for complex logic (conditionals, loops, imports)
- Cross-platform (works on Windows)
- Requires pip install invoke
- pre= for task dependencies
- Can import project code for tasks (e.g., read version from __init__.py)

Multi-axis evaluation:

Simplicity: Makefile wins for simple task lists. It's just commands with labels. invoke adds a dependency and boilerplate (`from invoke import task`, `@task`, `c.run()`).

Complex logic: invoke wins. Need conditional deployment based on branch? Read config files? Parameterized tasks? Python is natural. Make requires shell scripting.

Cross-platform: invoke wins. Makefile assumes Unix. Windows needs WSL, Git Bash, or mingw. invoke runs anywhere Python runs.

Dependencies: Makefile wins — no pip install. invoke is another dependency to manage.

Discoverability: Roughly equal. `make <tab>` shows targets. `invoke --list` shows tasks.

Team familiarity: For a Python team, invoke's Python syntax may be more approachable than Make syntax. But Make is ubiquitous in open source.

Ecosystem: Makefile is used by almost every open-source project. Contributors expect it. invoke is niche.

The critical factor: for a Python project with simple tasks (test, lint, build), Makefile is simpler and has zero dependencies. For complex automation with conditional logic, invoke is more capable. Most Python projects have simple enough tasks that Makefile suffices.

Winner: Makefile for typical Python project automation.
BUT: invoke if you need complex conditional logic, Windows support, or prefer Python over shell.
</think>

**Makefile is better for typical Python project tasks.** It's simpler, dependency-free, and universally understood.

**Why Makefile wins:**
- Zero dependencies — available on every Unix system
- Universally recognized by contributors and CI systems
- Task dependency chaining is built in: `build: test lint`
- Less boilerplate than invoke for simple commands
- Open source standard — contributors expect it

**Why invoke is overkill here:**
```makefile
# Makefile: 2 lines per task
test:
	pytest tests/ -v --cov=src
```
```python
# invoke: 4 lines per task + import + pip install
@task
def test(c):
    c.run("pytest tests/ -v --cov=src")
```

**When invoke IS better:**
- **Complex conditional logic**: Deploy differently based on branch/environment
- **Windows support**: Makefile needs WSL/Git Bash on Windows
- **Project introspection**: Read version from Python code, generate dynamic configs
- **Parameterized tasks**: `invoke deploy --env=staging --version=1.2.3`

**Makefile gotchas to avoid:**
```makefile
# MUST use tabs, not spaces (classic mistake)
# Add .PHONY for non-file targets
# Use $(MAKE) for recursive make, not make
```

| Axis | Makefile | invoke |
|------|---------|--------|
| Dependencies | None (Unix) | pip install |
| Syntax | Shell commands | Python |
| Complex logic | Awkward | Natural |
| Windows | Needs WSL/Git Bash | Cross-platform |
| Boilerplate | Minimal | More ceremony |
| Community | Universal | Niche |
| Learning curve | Tab gotcha, shell | Python (familiar) |

**Rule**: Makefile for command lists, invoke for programmatic automation.'''
    ),
    (
        "thinking/meta-reasoning-poetry-vs-pip",
        r'''For Python dependency management, compare pip + requirements.txt vs Poetry:

Approach A — pip + requirements.txt:
```
# requirements.txt
flask==3.0.0
sqlalchemy==2.0.25
redis==5.0.1
pytest==8.0.0

# requirements-dev.txt
-r requirements.txt
black==24.1.0
ruff==0.2.0
mypy==1.8.0
```

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for development
pip freeze > requirements-lock.txt   # lock versions
```

Approach B — Poetry:
```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"
flask = "^3.0"
sqlalchemy = "^2.0"
redis = "^5.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
black = "^24.1"
ruff = "^0.2"
mypy = "^1.8"
```

```bash
poetry install              # creates venv + installs + locks
poetry add requests         # add dependency
poetry lock                 # regenerate lock file
poetry run pytest           # run in venv
```

Which is better for a team project?''',
        r'''<think>
Comparing pip + requirements.txt vs Poetry for dependency management...

Approach A — pip + requirements.txt:
- Simple, universal, everyone knows it
- No extra tool to install
- BUT: no dependency resolution — requirements.txt is just a flat list
- pip freeze captures EVERYTHING including transitive deps, making upgrades hard
- No distinction between direct and transitive dependencies
- Multiple requirements files (dev, prod) are messy
- No lock file by default — `pip freeze` is a poor substitute
- Virtual environment management is separate (venv, virtualenv)

Approach B — Poetry:
- Proper dependency resolver (like npm/yarn for Python)
- Lock file (poetry.lock) with exact versions for ALL transitive deps
- Clear separation: direct deps in pyproject.toml, full graph in poetry.lock
- Dev dependencies built in (`[tool.poetry.group.dev.dependencies]`)
- Creates and manages virtual environments automatically
- `poetry add/remove` manages pyproject.toml
- BUT: another tool to install and learn
- Occasional resolver conflicts on complex dependency trees (improved in recent versions)
- pyproject.toml is the PEP 621 standard format

Multi-axis evaluation:

Reproducibility: Poetry wins. poetry.lock pins every transitive dependency with hashes. requirements.txt either pins too much (pip freeze) or too little (just direct deps).

Dependency resolution: Poetry wins. It resolves version conflicts before installing. pip installs in order and may produce broken environments.

Simplicity: pip wins for quick scripts. `pip install flask` is simpler than `poetry add flask`.

Onboarding: pip wins — already installed with Python. Poetry requires `curl` or `pipx install poetry`.

Dev/prod separation: Poetry wins. Built-in groups. pip needs multiple requirements files.

Upgrade safety: Poetry wins. `poetry update flask` respects constraints and updates lock file. With pip, upgrading one package can break others silently.

CI/CD: Poetry works well but adds `poetry install` to CI. pip is already there.

Standards: Poetry uses pyproject.toml (PEP 621). requirements.txt has no standard format for constraints.

The critical factor: for a "team project," reproducible builds across all developer machines and CI is essential. Poetry's lock file guarantees this. requirements.txt doesn't.

Winner: Poetry for team projects.
BUT: pip + requirements.txt for simple scripts, one-off tools, or minimal-dependency projects.
</think>

**Poetry is better for team projects.** The lock file and dependency resolution prevent "works on my machine" problems.

**Why Poetry wins for teams:**
- **Reproducible builds**: `poetry.lock` pins every transitive dependency — all machines get identical environments
- **Dependency resolution**: Detects conflicts BEFORE installing (pip installs and hopes)
- **Clean separation**: Direct deps in pyproject.toml, full graph in poetry.lock
- **Dev groups**: No juggling multiple requirements files

**Why pip + requirements.txt breaks down:**

```
# The pip freeze problem:
pip freeze > requirements.txt
# Now you have 47 lines including transitive deps
# Which ones are YOUR dependencies? No way to tell
# Upgrading flask means manually figuring out which
# of the 47 packages are flask's dependencies
```

```toml
# Poetry: crystal clear
[tool.poetry.dependencies]  # YOUR 3 packages
flask = "^3.0"
sqlalchemy = "^2.0"
redis = "^5.0"

# poetry.lock: automatically tracks all 47 transitive deps
```

**Poetry workflow for teams:**
```bash
# Developer 1 adds a package:
poetry add celery          # Updates pyproject.toml + poetry.lock
git commit pyproject.toml poetry.lock

# Developer 2 pulls and syncs:
git pull
poetry install             # Gets exact same versions

# CI:
poetry install --no-interaction
poetry run pytest
```

**Use pip + requirements.txt when:**
- Quick scripts or one-off tools
- Docker images where you pin everything in `pip freeze` output
- Can't install Poetry in the environment
- Single-developer project with few dependencies

| Axis | pip + requirements.txt | Poetry |
|------|----------------------|--------|
| Reproducibility | Poor (no real lock) | Excellent (poetry.lock) |
| Resolution | Install-order dependent | Full resolver |
| Direct vs transitive | Mixed together | Clearly separated |
| Dev dependencies | Extra files | Built-in groups |
| Onboarding | Pre-installed | Requires install |
| Standards | No formal spec | pyproject.toml (PEP 621) |

**For teams**: Poetry. For scripts: pip.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
