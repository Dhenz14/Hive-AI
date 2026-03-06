"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 12)"""

PAIRS = [
    (
        "thinking/meta-reasoning-pre-commit-vs-ci-linting",
        r'''Should code linting and formatting run in pre-commit hooks or in CI?

Approach A — Pre-commit hooks:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.0
    hooks:
      - id: black
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.2.0
    hooks:
      - id: ruff
        args: [--fix]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
```

Approach B — CI-only linting:
```yaml
# .github/workflows/lint.yml
name: Lint
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install black ruff mypy
      - run: black --check .
      - run: ruff check .
      - run: mypy src/
```

Which approach is better for a team of 5?''',
        r'''<think>
Comparing pre-commit hooks vs CI-only linting...

Approach A — Pre-commit hooks:
- Catches issues BEFORE commit — instant feedback
- Formats code automatically (black, ruff --fix)
- No "fix formatting" commits cluttering history
- BUT: requires every developer to install hooks (`pre-commit install`)
- New developers might skip setup
- Can slow down commits (especially mypy on large codebases)
- Can be bypassed with --no-verify
- hooks run on staged files only — may miss project-wide issues

Approach B — CI-only:
- Enforced — can't bypass (PR won't merge if CI fails)
- No developer setup required
- Runs on full codebase, not just staged files
- BUT: feedback loop is slow (push → wait for CI → fix → push again)
- Creates "fix lint" commits
- Developer might commit broken formatting and not know until CI runs minutes later

Multi-axis evaluation:

Feedback speed: Pre-commit wins. Instant feedback before commit vs minutes waiting for CI.

Enforcement: CI wins. Pre-commit can be bypassed (--no-verify) or not installed. CI blocks merging.

Developer experience: Pre-commit wins for auto-fixing (black formats, ruff fixes). CI can only report failures.

Setup cost: CI wins. No per-developer setup. Pre-commit requires each dev to run `pre-commit install`.

Reliability: CI wins for full-codebase checks. Pre-commit only checks staged files — can miss cross-file issues.

Hmm wait — this is a false dichotomy. The best teams do BOTH. Pre-commit for fast feedback and auto-fixing, CI as the enforcement backstop.

The critical factor: they're complementary, not competing. Pre-commit catches 95% of issues instantly. CI catches the remaining 5% (bypassed hooks, full-codebase checks) and blocks merging.

Winner: BOTH — pre-commit for fast feedback + CI as enforcement.
If forced to choose one: CI, because enforcement > convenience.
</think>

**Use both.** They're complementary, not competing.

**The right setup:**
```
Pre-commit (fast feedback) → CI (enforcement backstop)
```

- Pre-commit catches issues instantly, auto-fixes formatting
- CI catches everything pre-commit misses and blocks merging

**If forced to choose ONE:** CI-only, because enforcement matters more than convenience. A developer can bypass `--no-verify` or forget to install hooks. CI blocks the merge.

**Why pre-commit alone isn't enough:**
- Developers must run `pre-commit install` (someone will forget)
- `git commit --no-verify` bypasses everything
- Only checks staged files — misses cross-file type errors
- Different developer environments may produce different results

**Why CI alone isn't ideal:**
- Slow feedback loop: commit → push → wait 2 min → "black would reformat 3 files" → fix → push again
- Creates noise "fix formatting" commits
- No auto-fixing — CI only reports, doesn't fix

**Recommended hybrid:**

```yaml
# .pre-commit-config.yaml (fast checks only)
repos:
  - repo: https://github.com/psf/black
    hooks:
      - id: black        # Auto-formats (fast)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff
        args: [--fix]    # Auto-fixes (fast)
  # NOTE: skip mypy in pre-commit — too slow
```

```yaml
# CI: full enforcement including slow checks
- run: black --check .
- run: ruff check .
- run: mypy src/       # Full project type checking (slow but thorough)
```

| Concern | Pre-commit | CI |
|---------|-----------|-----|
| Speed | Instant | Minutes |
| Auto-fix | Yes (black, ruff --fix) | Report only |
| Enforcement | Bypassable | Blocks merge |
| Setup | Per-developer | Automatic |
| Scope | Staged files | Full codebase |

**For a team of 5**: pre-commit for black + ruff (fast auto-fixers), CI for everything including mypy.'''
    ),
    (
        "thinking/meta-reasoning-pytest-fixtures-vs-setup",
        r'''For test setup in Python, compare pytest fixtures vs setUp/tearDown:

Approach A — pytest fixtures:
```python
import pytest
from app.db import create_engine, Session

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def sample_user(db_session):
    user = User(name="Alice", email="alice@test.com")
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def api_client(db_session):
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_get_user(api_client, sample_user):
    response = api_client.get(f"/users/{sample_user.id}")
    assert response.status_code == 200
    assert response.json["name"] == "Alice"
```

Approach B — unittest setUp/tearDown:
```python
import unittest

class TestUserAPI(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(bind=self.engine)
        self.user = User(name="Alice", email="alice@test.com")
        self.session.add(self.user)
        self.session.commit()
        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def test_get_user(self):
        response = self.client.get(f"/users/{self.user.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["name"], "Alice")
```

Which pattern is better?''',
        r'''<think>
Comparing pytest fixtures vs unittest setUp/tearDown...

Approach A — pytest fixtures:
- Composable: fixtures can depend on other fixtures (sample_user depends on db_session)
- Reusable: define once in conftest.py, use across all test files
- Explicit dependency injection: test function declares exactly what it needs
- yield for setup/teardown — cleanup is right next to setup
- Can be scoped: function, class, module, session
- Parametrize fixtures for data-driven tests

Approach B — unittest setUp/tearDown:
- Everything in setUp — ALL setup runs for EVERY test, even if not needed
- self.everything — test_get_user sets up DB + user + client even if a test only needs the DB
- setUp is monolithic — can't compose pieces
- Can't share setup across test classes easily
- More familiar to Java/C# developers
- Works without any framework dependency (stdlib)

Multi-axis evaluation:

Composability: pytest wins. `sample_user(db_session)` — fixtures compose like functions. setUp is a monolithic block.

Reusability: pytest wins. conftest.py fixtures are available to all tests automatically. setUp must be inherited or duplicated.

Performance: pytest wins. Tests only set up what they declare. setUp runs everything for every test. A test that only needs db_session shouldn't create a sample_user.

Readability: pytest wins. `def test_get_user(api_client, sample_user)` — the signature tells you exactly what this test needs. setUp requires reading the method to understand what's available.

Cleanup: pytest wins slightly. `yield session` keeps setup and teardown together. tearDown is separated from setUp.

Scoping: pytest wins. `@pytest.fixture(scope="session")` for expensive one-time setup (create DB). setUp runs per test method always.

stdlib dependency: unittest wins — no pip install needed. But pytest is a de facto standard in Python.

The critical factor: composability and explicit dependencies make tests clearer, faster, and more maintainable. pytest fixtures are simply the better abstraction.

Winner: pytest fixtures for any non-trivial test suite.
BUT: unittest is fine for tiny projects or when you can't add dependencies.
</think>

**pytest fixtures are better** for any project beyond trivial scripts. The composability advantage is decisive.

**Why pytest fixtures win:**

1. **Explicit dependencies** — the test signature IS the documentation:
```python
# What does this test need? Read the signature:
def test_get_user(api_client, sample_user):  # Needs API client + a user
    ...

# unittest: read all of setUp to understand what's available
def test_get_user(self):  # Needs... self.something? Read setUp.
    ...
```

2. **Composability** — fixtures depend on fixtures:
```python
db_session → sample_user → test  # Only set up what's needed
db_session → api_client → test   # Different composition
```

3. **No wasted setup** — unittest setUp creates EVERYTHING for EVERY test:
```python
# unittest: test_health_check creates DB, user, client (only needs client)
# pytest: def test_health_check(api_client): — only creates client + db
```

4. **Reusability via conftest.py:**
```
tests/
├── conftest.py          # db_session, sample_user available everywhere
├── test_users.py        # Just uses them
├── test_orders.py       # Just uses them
└── api/
    └── conftest.py      # api_client available in api/ tests
```

5. **Scoping** — expensive setup runs once:
```python
@pytest.fixture(scope="session")
def db_engine():           # Create engine ONCE for all tests
    return create_engine(...)

@pytest.fixture(scope="function")
def db_session(db_engine):  # Fresh session per test
    ...
```

| Axis | pytest fixtures | unittest setUp |
|------|----------------|---------------|
| Composability | Fixture depends on fixture | Monolithic block |
| Reusability | conftest.py, automatic | Inheritance or duplication |
| Performance | Only setup what's needed | Everything, every test |
| Readability | Signature = dependencies | Read setUp to understand |
| Scoping | function/class/module/session | Per-test only |
| Stdlib | Needs pip install | Built-in |

**Use unittest only when:** zero external dependencies required, or maintaining legacy test suite not worth migrating.'''
    ),
    (
        "thinking/meta-reasoning-nginx-vs-caddy",
        r'''For reverse proxying a Python web application, compare Nginx vs Caddy:

Approach A — Nginx:
```nginx
server {
    listen 80;
    server_name myapp.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name myapp.com;

    ssl_certificate /etc/letsencrypt/live/myapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/myapp/static/;
        expires 30d;
    }
}
# Plus: certbot setup, cron renewal, separate config for each site
```

Approach B — Caddy:
```
myapp.com {
    reverse_proxy 127.0.0.1:8000
    file_server /static/* {
        root /var/www/myapp
    }
}
```

Which is better for a small Python web app?''',
        r'''<think>
Comparing Nginx vs Caddy for reverse proxying a Python web app...

Approach A — Nginx:
- Industry standard, battle-tested at massive scale
- Extremely performant, low memory footprint
- Extensive documentation and community knowledge
- BUT: verbose configuration
- TLS requires separate certbot setup + cron renewal
- HTTP→HTTPS redirect requires separate server block
- Proxy headers must be explicitly configured
- Config errors are easy to make, hard to debug

Approach B — Caddy:
- Automatic HTTPS — obtains and renews Let's Encrypt certs automatically
- Minimal configuration — the entire config is 5 lines
- Secure defaults (HTTPS, modern TLS, HSTS)
- HTTP→HTTPS redirect is automatic
- Proxy headers (X-Forwarded-For, etc.) set automatically
- Slightly higher memory usage than Nginx
- Smaller community, fewer Stack Overflow answers
- Written in Go, single binary deployment

Multi-axis evaluation:

Configuration simplicity: Caddy wins massively. 5 lines vs 25+ lines. No separate TLS setup, no header config, no redirect block.

TLS management: Caddy wins. Automatic cert provisioning and renewal. Nginx needs certbot, cron job, and manual initial setup.

Performance: Nginx wins at extreme scale (millions of connections). For a typical Python app (not the bottleneck), negligible difference.

Security defaults: Caddy wins. HTTPS by default, modern TLS config, HSTS. Nginx requires you to configure these correctly.

Community: Nginx wins. Decades of documentation, blog posts, Stack Overflow answers. Every hosting tutorial uses Nginx.

Flexibility: Nginx wins for complex configurations — load balancing algorithms, rate limiting, caching, streaming. Caddy handles most use cases but Nginx has more knobs.

Operational: Caddy wins for small teams. One binary, no certbot dependency, no cron jobs. Nginx requires managing more moving parts.

The critical factor: "small Python web app" — simplicity and automatic TLS matter more than extreme performance tuning. Caddy eliminates entire categories of mistakes.

Winner: Caddy for small Python web apps.
BUT: Nginx for high-traffic production systems, complex routing, or when you need specific Nginx modules.
</think>

**Caddy is better for a small Python web app.** The automatic HTTPS and minimal config eliminate entire categories of operational work.

**The config comparison speaks for itself:**

Caddy (5 lines, done):
```
myapp.com {
    reverse_proxy 127.0.0.1:8000
    file_server /static/* {
        root /var/www/myapp
    }
}
```

Nginx (25+ lines + certbot + cron):
```nginx
# HTTP→HTTPS redirect block
# HTTPS server block
# SSL certificate paths
# Proxy headers (4 lines)
# Static file serving
# Plus: certbot setup, cron renewal
```

**What Caddy handles automatically:**
- Obtains Let's Encrypt certificate on first request
- Renews certificates before expiry
- Redirects HTTP → HTTPS
- Sets proxy headers (X-Forwarded-For, X-Real-IP)
- Configures modern TLS (TLS 1.3, secure ciphers)
- Enables HSTS

**What you must manually configure with Nginx:**
- Install certbot, run initial cert generation
- Add cron job for renewal
- Write HTTP→HTTPS redirect server block
- Configure SSL paths and parameters
- Set proxy headers explicitly
- Add security headers manually

**When Nginx is the right choice:**
- High-traffic systems (millions of req/s)
- Complex load balancing (upstream groups, health checks)
- Specific modules needed (RTMP, Lua scripting)
- Team already has Nginx expertise and configs
- Corporate environment where Nginx is standard

| Axis | Nginx | Caddy |
|------|-------|-------|
| Config complexity | 25+ lines | 5 lines |
| TLS management | Manual (certbot) | Automatic |
| Performance ceiling | Higher | Sufficient |
| Security defaults | Manual | Automatic |
| Community | Massive | Growing |
| Learning curve | Steep | Gentle |

**For a small Python app**: Caddy saves hours of config and eliminates cert renewal failures.'''
    ),
    (
        "thinking/meta-reasoning-click-vs-argparse",
        r'''For building a Python CLI tool, compare Click vs argparse:

Approach A — argparse:
```python
import argparse

def main():
    parser = argparse.ArgumentParser(description='Deploy application')
    parser.add_argument('environment', choices=['staging', 'production'])
    parser.add_argument('--version', required=True, help='Version to deploy')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('-v', '--verbose', action='count', default=0)

    subparsers = parser.add_subparsers(dest='command')
    rollback = subparsers.add_parser('rollback', help='Rollback deployment')
    rollback.add_argument('--to-version', required=True)

    args = parser.parse_args()

    if args.command == 'rollback':
        do_rollback(args.environment, args.to_version, args.dry_run)
    else:
        do_deploy(args.environment, args.version, args.dry_run, args.verbose)
```

Approach B — Click:
```python
import click

@click.group()
@click.argument('environment', type=click.Choice(['staging', 'production']))
@click.option('--dry-run', is_flag=True, help='Preview only')
@click.option('-v', '--verbose', count=True)
@click.pass_context
def cli(ctx, environment, dry_run, verbose):
    ctx.ensure_object(dict)
    ctx.obj.update(environment=environment, dry_run=dry_run, verbose=verbose)

@cli.command()
@click.option('--version', required=True, help='Version to deploy')
@click.pass_context
def deploy(ctx, version):
    do_deploy(ctx.obj['environment'], version, ctx.obj['dry_run'], ctx.obj['verbose'])

@cli.command()
@click.option('--to-version', required=True)
@click.pass_context
def rollback(ctx, to_version):
    do_rollback(ctx.obj['environment'], to_version, ctx.obj['dry_run'])
```

Which is better for a deployment CLI tool?''',
        r'''<think>
Comparing Click vs argparse for a CLI deployment tool...

Approach A — argparse:
- Standard library — zero dependencies
- Procedural style — define parser, parse args, use args dict
- Subcommands via subparsers (somewhat awkward API)
- Manual dispatch: `if args.command == 'rollback'`
- No input prompting, no progress bars, no color output
- Familiar to all Python developers

Approach B — Click:
- Decorator-based — functions become commands automatically
- Subcommands are natural (group + command decorators)
- Automatic dispatch — no if/else for subcommands
- Built-in prompting, progress bars, color output, file handling
- Context passing for shared options
- External dependency (but very stable, used by Flask)
- More boilerplate for context passing

Multi-axis evaluation:

Simple CLIs: argparse wins. For a script with 3 flags, argparse is 5 lines. Click is more ceremony.

Complex CLIs (subcommands, groups): Click wins. Subcommands are just decorated functions. argparse subparsers + manual dispatch gets messy.

UX features: Click wins. Progress bars, colored output, confirmation prompts, file path completion — all built in. argparse is args-only.

Dependencies: argparse wins — stdlib. But Click is a single pip install with no transitive deps.

Testing: Click wins with CliRunner — invoke commands programmatically and check output. argparse requires mocking sys.argv.

Composability: Click wins. Groups can be nested, commands can be reused across CLIs. argparse subparsers don't compose well.

Type safety: Click's decorators provide validation at parse time. argparse requires manual validation after parsing (except for choices and type converters).

For THIS specific case: a deployment tool benefits from Click's confirmation prompts (`click.confirm("Deploy to production?")`), progress bars for deploy steps, colored output for success/failure, and clean subcommand structure.

The critical factor: deployment tools need subcommands, interactive prompts, and good UX. Click is purpose-built for this.

Winner: Click for a deployment CLI tool.
BUT: argparse is fine for simple scripts with a few flags and no subcommands.
</think>

**Click is better for a deployment CLI tool.** The subcommand structure, UX features, and testability justify the dependency.

**Why Click wins for deployment tools:**

1. **Natural subcommands**: Functions = commands, no manual dispatch
2. **Interactive prompts** (critical for deployment):
```python
@cli.command()
def deploy(ctx, version):
    if ctx.obj['environment'] == 'production':
        click.confirm("Deploy to PRODUCTION?", abort=True)
```
3. **Progress bars** for deployment steps:
```python
with click.progressbar(steps, label='Deploying') as bar:
    for step in bar:
        execute_step(step)
```
4. **Colored output**:
```python
click.secho("Deployed successfully!", fg='green', bold=True)
click.secho("Rollback failed!", fg='red', err=True)
```
5. **Testability** with CliRunner:
```python
def test_deploy():
    runner = CliRunner()
    result = runner.invoke(cli, ['staging', 'deploy', '--version', '1.2.3'])
    assert result.exit_code == 0
    assert 'Deployed' in result.output
```

**When argparse is better:**
- Simple scripts with 2-3 flags, no subcommands
- Zero-dependency requirement (embedded scripts, containers)
- Quick one-off automation scripts

| Axis | argparse | Click |
|------|---------|-------|
| Dependencies | stdlib | pip install click |
| Subcommands | Awkward subparsers | Natural decorators |
| Prompts/progress | None | Built-in |
| Testing | Mock sys.argv | CliRunner |
| Colored output | None | Built-in |
| Learning curve | Lower | Moderate |
| Complex CLIs | Gets messy | Stays clean |

**Rule of thumb**: argparse for scripts, Click for tools.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
