"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 9)"""

PAIRS = [
    (
        "thinking/abstraction-environment-variables-to-configuration-management",
        "We have 50+ environment variables across our services and it's getting unmanageable. How do I organize configuration better?",
        r'''<think>
50+ env vars getting unwieldy. Let me ladder from concrete to abstract.

**Concrete: the immediate mess**
50+ env vars spread across .env files, CI secrets, deployment configs. Hard to track, easy to misconfigure, no validation.

**Pattern: structured configuration**
Group env vars into logical categories. Validate at startup. Use typed config objects instead of raw string lookups.

**Principle: configuration as a first-class concern**
Configuration should be: validated, documented, typed, hierarchical, and environment-aware. Treat config like code — it needs tests, reviews, and documentation.

**Policy: configuration management strategy**
Define WHERE config lives (secrets manager, env vars, config files), HOW it's validated, and WHO can change it.
</think>

Let me build from your immediate problem to a proper configuration strategy.

## Level 1: Concrete — Organize What You Have

```python
# ❌ Current: 50+ raw env var lookups scattered across code
db_url = os.environ["DATABASE_URL"]
redis_host = os.environ.get("REDIS_HOST", "localhost")
stripe_key = os.environ["STRIPE_SECRET_KEY"]
# ... scattered across 20 files, no validation, no documentation

# ✅ Step 1: centralize into a typed config object
from pydantic_settings import BaseSettings
from pydantic import Field

class DatabaseConfig(BaseSettings):
    url: str = Field(..., alias="DATABASE_URL")
    pool_size: int = Field(20, alias="DB_POOL_SIZE")
    pool_timeout: int = Field(30, alias="DB_POOL_TIMEOUT")

class CacheConfig(BaseSettings):
    host: str = Field("localhost", alias="REDIS_HOST")
    port: int = Field(6379, alias="REDIS_PORT")
    ttl_default: int = Field(300, alias="CACHE_TTL_DEFAULT")

class PaymentConfig(BaseSettings):
    stripe_key: str = Field(..., alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(..., alias="STRIPE_WEBHOOK_SECRET")
    currency: str = Field("usd", alias="PAYMENT_CURRENCY")

class AppConfig(BaseSettings):
    debug: bool = Field(False, alias="DEBUG")
    log_level: str = Field("info", alias="LOG_LEVEL")
    environment: str = Field("development", alias="ENVIRONMENT")
    database: DatabaseConfig = DatabaseConfig()
    cache: CacheConfig = CacheConfig()
    payment: PaymentConfig = PaymentConfig()

# Load once at startup — validates everything immediately
config = AppConfig()
# If STRIPE_SECRET_KEY is missing → clear error at startup, not at runtime

# Use throughout code:
engine = create_engine(config.database.url, pool_size=config.database.pool_size)
```

## Level 2: Pattern — Validate Early, Fail Fast

```python
# The worst config bugs: app starts, runs for hours,
# then crashes when it first tries to use a missing config value.

# ✅ Validate ALL config at startup
def validate_config(config: AppConfig):
    errors = []

    # Check required values exist
    if not config.database.url:
        errors.append("DATABASE_URL is required")

    # Check values make sense
    if config.database.pool_size < 1 or config.database.pool_size > 100:
        errors.append(f"DB_POOL_SIZE must be 1-100, got {config.database.pool_size}")

    # Check connectivity (optional but valuable)
    try:
        engine = create_engine(config.database.url)
        engine.connect().close()
    except Exception as e:
        errors.append(f"Cannot connect to database: {e}")

    if errors:
        for e in errors:
            print(f"CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Config validated: {config.environment} environment, "
          f"{config.database.pool_size} DB connections")


# Call at startup:
config = AppConfig()
validate_config(config)
# App either starts correctly or fails immediately with clear errors.
```

## Level 3: Principle — Configuration Hierarchy

```
Not all configuration is equal. Organize by source and sensitivity:

LAYER 1: DEFAULTS (in code)
  pool_size = 20
  log_level = "info"
  timeout = 30
  → Safe defaults that work for development
  → Committed to git (no secrets here)

LAYER 2: CONFIG FILES (per environment)
  config/development.yaml
  config/production.yaml
  → Non-sensitive environment-specific values
  → Committed to git (no secrets here either)

LAYER 3: ENVIRONMENT VARIABLES
  DATABASE_URL, REDIS_HOST, LOG_LEVEL
  → Environment-specific overrides
  → Set in deployment platform (Heroku, K8s, CI)
  → Override file-based config

LAYER 4: SECRETS MANAGER
  STRIPE_SECRET_KEY, DATABASE_PASSWORD, JWT_SECRET
  → Sensitive values ONLY
  → AWS Secrets Manager, Vault, GCP Secret Manager
  → Never in git, never in env files

RESOLUTION ORDER:
  Secrets Manager > Environment Variables > Config Files > Defaults
  (higher layers override lower layers)
```

## Level 4: Policy — Configuration Management Rules

```
FOR A TEAM:

1. CATEGORIZE every config value:
   □ Is it a secret? → Secrets Manager (never in git)
   □ Is it environment-specific? → Environment variable
   □ Is it the same everywhere? → Config file or code default

2. VALIDATE at startup:
   □ All required values present
   □ Values are the correct type and range
   □ Connections to external services work
   □ App fails FAST with clear errors, not hours later

3. DOCUMENT:
   □ .env.example with every variable and description
   □ README section on required configuration
   □ Default values documented in the config class

4. REVIEW config changes:
   □ Config file changes go through PR review
   □ Secret rotations are logged and auditable
   □ Environment variable changes are tracked (who changed what, when)

5. TEST:
   □ Unit tests for config validation logic
   □ Integration test that starts the app with minimum valid config
   □ CI catches missing or invalid config before deploy
```

```bash
# .env.example — documentation + template
# Database
DATABASE_URL=postgresql://localhost:5432/myapp    # Required
DB_POOL_SIZE=20                                   # Default: 20
DB_POOL_TIMEOUT=30                                # Default: 30 seconds

# Cache
REDIS_HOST=localhost                              # Default: localhost
REDIS_PORT=6379                                   # Default: 6379

# Payment (get test keys from Stripe dashboard)
STRIPE_SECRET_KEY=sk_test_...                     # Required
STRIPE_WEBHOOK_SECRET=whsec_...                   # Required

# Application
DEBUG=false                                       # Default: false
LOG_LEVEL=info                                    # Default: info
ENVIRONMENT=development                           # development/staging/production
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
