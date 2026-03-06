"""Phase 3E: Metacognition — Learning From Mistakes (Part 7)

Additional pairs for scenario 10 (config bugs) + scenarios 11-13 (encoding, deployment, monitoring).
"""

PAIRS = [
    (
        "thinking/meta-mistakes-config-env-mismatch",
        r'''Our staging environment works perfectly but production keeps connecting to the wrong database:

```python
# config.py
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/myapp_dev")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
API_KEY = os.getenv("API_KEY", "dev-key-12345")
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-dev-key")
```

In production, someone forgot to set DATABASE_URL, so it silently fell back to the dev default. We had production data going to the dev database for 3 hours.''',
        r'''<think>
I made an error: providing dev defaults for production-critical config values. When the environment variable isn't set, the app silently uses the dev database instead of crashing.

The mistake was: making it "convenient" to run without environment variables by providing defaults. This means a missing env var in production doesn't cause a loud failure — it causes silent data corruption.

The root cause was: optimizing for developer convenience (easy local setup) at the cost of production safety. Dev defaults are fine for non-critical settings (log level, page size) but dangerous for infrastructure URLs and secrets.

Generalizable lesson: Critical config (database URLs, API keys, secrets) should NEVER have defaults. Missing critical config should crash the app at startup with a clear error message. Dev convenience should come from .env files, not from default values in code.

Checklist item: For every config value with a default, ask: "If this default is used in production, what's the worst case?" If the answer involves data loss, security breach, or connecting to wrong infrastructure — remove the default.

Similar situations where this lesson applies:
1. Default API keys that work in dev but are invalid in production
2. Default log levels that suppress errors in production
3. Default feature flags that enable debug features in production
</think>

**Dev defaults in config are a production disaster waiting to happen.** Missing DATABASE_URL should crash, not silently use localhost.

**Fix — fail loud on missing critical config:**
```python
import os
import sys

def require_env(name):
    value = os.getenv(name)
    if value is None:
        print(f"FATAL: Required environment variable {name} is not set", file=sys.stderr)
        sys.exit(1)
    return value

# Critical config — NO defaults, crash if missing
DATABASE_URL = require_env("DATABASE_URL")
REDIS_URL = require_env("REDIS_URL")
SECRET_KEY = require_env("SECRET_KEY")
API_KEY = require_env("API_KEY")

# Non-critical config — defaults are fine
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "20"))
```

**For dev convenience, use .env files (not code defaults):**
```bash
# .env (gitignored)
DATABASE_URL=postgresql://localhost:5432/myapp_dev
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret
API_KEY=dev-key
```

```python
# Load .env only in development
from dotenv import load_dotenv
load_dotenv()  # Loads .env if present, no-op in production
```

**The lesson: critical config should crash on missing, not silently default.** Dev convenience comes from .env files, not from dangerous defaults in code.'''
    ),
    (
        "thinking/meta-mistakes-config-typo-late-failure",
        r'''Our app started fine but crashed 2 hours later when a user triggered a specific feature:

```python
# settings.py
STRIPE_PUBLSHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")  # Typo!
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

# payment.py (used hours later when someone makes a purchase)
from settings import STRIPE_PUBLSHABLE_KEY
stripe.api_key = STRIPE_PUBLSHABLE_KEY  # None! Typo in settings.py
```

The typo in the variable name meant `STRIPE_PUBLISHABLE_KEY` env var was read correctly but stored in a misspelled variable. The code in payment.py imported the misspelled name and got the right value... but the real env var name in `os.getenv` had a typo.''',
        r'''<think>
I made an error: a typo in the settings variable name (`PUBLSHABLE` instead of `PUBLISHABLE`) meant the env var was read but the code using it also had to use the typo. Wait — actually looking more carefully, the os.getenv reads `STRIPE_PUBLISHABLE_KEY` (correct), but stores it in `STRIPE_PUBLSHABLE_KEY` (typo). And payment.py imports the typo. So actually the env var IS read correctly but the Python variable has a typo. This would work... unless payment.py tried to import `STRIPE_PUBLISHABLE_KEY` (the correctly-spelled version that doesn't exist).

Actually let me re-read. The issue is: `STRIPE_PUBLSHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")` — the env var read is correct, the Python variable name has a typo. If payment.py imports `STRIPE_PUBLSHABLE_KEY`, it actually works. The real issue would be if someone tries to import `STRIPE_PUBLISHABLE_KEY` (correct spelling) — ImportError.

The real lesson here is about validating config at startup regardless of the specific bug mechanics.

The root cause was: config is loaded at import time but only validated when first used (hours later). If we validated all config at startup, we'd catch None values, typos, and missing keys immediately.

Generalizable lesson: Validate ALL configuration at application startup, not at first use. Load config, check that required values are present and valid, and fail fast. Don't wait until a user triggers a code path that reads the config.

Checklist item: Does the app have a config validation step at startup that checks all required config values are present, non-None, and the right format?

Similar situations where this lesson applies:
1. Database connection strings checked only when the first query runs
2. API keys validated only when the first API call is made
3. File paths checked only when the first file operation runs
</think>

**The real problem: config isn't validated at startup.** Whether it's a typo, a missing env var, or an invalid format — you shouldn't find out hours later when a user hits the code path.

**Fix — validate all config at startup:**
```python
# config.py
import os
import sys
from dataclasses import dataclass

@dataclass
class Config:
    stripe_publishable_key: str
    stripe_secret_key: str
    database_url: str

    @classmethod
    def from_env(cls):
        """Load and validate ALL config at startup."""
        errors = []

        stripe_pub = os.getenv("STRIPE_PUBLISHABLE_KEY")
        if not stripe_pub:
            errors.append("STRIPE_PUBLISHABLE_KEY is not set")
        elif not stripe_pub.startswith("pk_"):
            errors.append(f"STRIPE_PUBLISHABLE_KEY should start with 'pk_', got '{stripe_pub[:10]}'")

        stripe_secret = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_secret:
            errors.append("STRIPE_SECRET_KEY is not set")

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            errors.append("DATABASE_URL is not set")

        if errors:
            for e in errors:
                print(f"CONFIG ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        return cls(
            stripe_publishable_key=stripe_pub,
            stripe_secret_key=stripe_secret,
            database_url=db_url,
        )

# App startup:
config = Config.from_env()  # Fails immediately if anything is wrong
```

**Benefits:**
- Typos in env var names → caught at startup
- Missing config → caught at startup, ALL missing values reported at once
- Invalid format → caught at startup (Stripe keys should start with `pk_`)
- No chance of `None` leaking into business logic hours later

**The lesson: validate config at startup, not at first use.** Fail in the first second, not after 2 hours of serving traffic.'''
    ),
    (
        "thinking/meta-mistakes-config-secret-in-code",
        r'''I accidentally committed API keys to our public GitHub repo:

```python
# config.py (committed to git)
STRIPE_SECRET_KEY = "sk_live_51H7..."
SENDGRID_API_KEY = "SG.abc123..."
DATABASE_URL = "postgresql://admin:realpassword@prod-db.us-east-1.rds.amazonaws.com/myapp"
```

I noticed after 2 days. I've deleted the file and pushed a new commit. Is the secret safe now?''',
        r'''<think>
I made an error: committing secrets to a git repository. And no, deleting in a new commit does NOT remove the secret — git history preserves every version of every file. Anyone can see the secret in the old commit.

The mistake was: hardcoding secrets in source code instead of using environment variables, and not having safeguards (pre-commit hooks, .gitignore) to prevent this.

The root cause was: two failures — (1) no separation between configuration and code, and (2) not understanding that git history is permanent. Deleting a file doesn't remove it from history.

Generalizable lesson: Secrets must NEVER be in source code. Use environment variables or secret managers. If a secret is accidentally committed, treat it as compromised immediately — rotate it. Git history deletion (filter-branch, BFG) is unreliable because forks, caches, and local clones may have already captured the secret.

Checklist item: Before every commit: does `git diff --cached` show any keys, passwords, or tokens? Set up pre-commit hooks to scan for secrets automatically.

Similar situations where this lesson applies:
1. Hardcoded database passwords in docker-compose.yml
2. API keys in frontend JavaScript (visible to users)
3. Private keys committed to repos
</think>

**No — the secret is NOT safe.** Deleting a file in a new commit doesn't remove it from git history. Anyone can run:

```bash
git log --all --full-history -- config.py
git show <old-commit>:config.py  # Secret is right there
```

**Immediate actions required:**

1. **Rotate ALL exposed secrets NOW:**
   - Stripe: Generate new API keys in Stripe dashboard, revoke old ones
   - SendGrid: Generate new API key, delete old one
   - Database: Change the password immediately

2. **Check for unauthorized access:**
   - Stripe dashboard → Developers → Logs (check for unknown API calls)
   - Database → Check for unknown connections in `pg_stat_activity`

3. **Prevent future leaks:**
```bash
# .gitignore
.env
*.pem
*.key

# Pre-commit hook (install trufflehog or gitleaks):
pip install pre-commit
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

4. **Use environment variables, never hardcoded secrets:**
```python
# config.py
import os
STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]  # No default!
```

**The lesson: committed secrets are compromised secrets — rotate immediately.** Git history is permanent. Prevention (pre-commit hooks, .gitignore, env vars) is the only real solution.'''
    ),
    (
        "thinking/meta-mistakes-encoding-emoji-truncation",
        r'''Our database stores user bios as VARCHAR(255) and some users report their bios being corrupted. The bio looks fine in the form but garbled after saving:

```python
# User submits: "I love coding! 🚀✨ Building cool stuff"
# Database stores: "I love coding! 🚀✨ Building cool st"
# Displayed as: "I love coding! 🚀✨ Building cool st" (truncated mid-character sometimes)
```

Some users see garbled characters at the end of their bio.''',
        r'''<think>
I made an error: VARCHAR(255) counts characters in some databases but bytes in others. Emojis are 4 bytes in UTF-8. If the database counts bytes, a 255-byte limit truncates multi-byte characters mid-sequence, producing garbled output.

The mistake was: assuming VARCHAR(N) means N characters universally. In MySQL with utf8 (not utf8mb4), it's 3 bytes per character max — emojis (4 bytes) get corrupted. Even with utf8mb4, VARCHAR(255) might truncate at 255 characters, cutting off content with emojis unexpectedly because emojis are 4 bytes.

The root cause was: not choosing an encoding and enforcing it at every boundary. The form accepts Unicode (including emojis), but the database column may not support 4-byte UTF-8 characters, or the byte limit may truncate mid-character.

Generalizable lesson: Choose one encoding (UTF-8 everywhere), enforce it at every boundary (form validation, API, database column type), and understand the difference between character count and byte count. Specifically: MySQL's `utf8` is NOT real UTF-8 — use `utf8mb4`.

Checklist item: For any text field: (1) Is the database column using utf8mb4 (not utf8)? (2) Is the length limit in characters or bytes? (3) Does validation count the same way the database does?

Similar situations where this lesson applies:
1. CSV export truncating Unicode characters
2. API payload size limits cutting multi-byte characters
3. Filename handling with non-ASCII characters
</think>

**Two problems: encoding and length calculation.**

**Problem 1: MySQL `utf8` is NOT real UTF-8:**
```sql
-- utf8 in MySQL = max 3 bytes per char. Emojis need 4 bytes.
-- This CORRUPTS emojis:
CREATE TABLE users (bio VARCHAR(255) CHARACTER SET utf8);

-- Fix: use utf8mb4 (real UTF-8, supports 4-byte chars):
ALTER TABLE users MODIFY bio VARCHAR(255) CHARACTER SET utf8mb4;
```

**Problem 2: Length validation mismatch:**
```python
# Frontend counts characters: "Hello 🚀" = 7 characters ✓ (fits in 255)
# But in UTF-8 bytes: "Hello 🚀" = 10 bytes (🚀 = 4 bytes)

# Validate consistently:
def validate_bio(text, max_chars=255):
    if len(text) > max_chars:  # Python counts Unicode codepoints
        raise ValueError(f"Bio must be {max_chars} characters or fewer")
    return text
```

**Problem 3: Truncation at byte boundary corrupts:**
```python
# WRONG: truncating bytes can split a multi-byte character
bio_bytes = bio.encode('utf-8')[:255]  # Might cut emoji in half

# RIGHT: truncate at character level
bio_truncated = bio[:255]  # Python handles Unicode correctly
```

**The full fix:**
1. Database: `utf8mb4` charset (not `utf8`)
2. Validation: count characters, not bytes
3. Truncation: never truncate encoded bytes — truncate the string first, then encode

**The lesson: choose UTF-8 everywhere and enforce it at every boundary.** Database charset, application validation, and truncation logic must all agree on encoding.'''
    ),
    (
        "thinking/meta-mistakes-encoding-csv-bom",
        r'''Some users report that our CSV export is garbled when opened in Excel. Others say it works fine. The garbled output shows Chinese characters at the beginning of the file:

```python
def export_csv(data):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Amount"])
    for row in data:
        writer.writerow(row)
    return output.getvalue().encode('utf-8')
```

The CSV opens fine in Google Sheets but shows `Name` as `锘縉ame` in Excel on Windows.''',
        r'''<think>
I made an error: Excel on Windows expects a BOM (Byte Order Mark) at the beginning of UTF-8 CSV files. Without it, Excel assumes the file is in the local encoding (often Windows-1252 or GBK on Chinese Windows), causing garbled text.

The mistake was: assuming that "UTF-8" is universally understood. It is — except by Excel on Windows, which needs a BOM to recognize UTF-8.

The root cause was: not understanding that CSV encoding has a platform-specific quirk. Google Sheets, macOS Numbers, and most modern software handle UTF-8 correctly. But Excel on Windows (still the most common CSV consumer) needs the UTF-8 BOM (`\xef\xbb\xbf`) prepended to the file.

Generalizable lesson: When generating files for external consumption, test with the most common consumer (Excel on Windows for CSV). Encoding assumptions that work in your dev environment may fail for users on different platforms. The UTF-8 BOM is a pragmatic fix for Excel compatibility.

Checklist item: For any CSV export feature: does it include a UTF-8 BOM? Is the Content-Type header correct? Test by opening in Excel on Windows.

Similar situations where this lesson applies:
1. JSON with non-ASCII characters not rendered correctly in some clients
2. PDF generation with Unicode characters requiring embedded fonts
3. Email content with special characters requiring proper MIME encoding
</think>

**Excel on Windows doesn't auto-detect UTF-8 CSV. It needs a BOM (Byte Order Mark).**

**Fix — add UTF-8 BOM:**
```python
def export_csv(data):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Amount"])
    for row in data:
        writer.writerow(row)

    # Add UTF-8 BOM for Excel compatibility
    csv_bytes = output.getvalue().encode('utf-8-sig')  # utf-8-sig adds BOM
    return csv_bytes
```

The key change: `encode('utf-8-sig')` instead of `encode('utf-8')`. This prepends `\xef\xbb\xbf` (the UTF-8 BOM) which tells Excel "this file is UTF-8."

**If serving as HTTP response:**
```python
@app.get("/export")
def export():
    csv_bytes = export_csv(data)
    return Response(
        csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=export.csv"}
    )
```

**Why this only affects Excel on Windows:**
- Google Sheets: detects UTF-8 automatically
- macOS Numbers: detects UTF-8 automatically
- Excel on Windows: assumes local encoding unless BOM present

**The lesson: test file exports with the most common consumer.** For CSV, that's Excel on Windows. The UTF-8 BOM is ugly but pragmatic — it solves the #1 CSV encoding complaint.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
