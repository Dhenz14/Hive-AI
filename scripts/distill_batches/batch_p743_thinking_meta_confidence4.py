"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 4)

Scenarios: Debugging without reproduction, ambiguous bug reports,
security assessment, compatibility questions, underdefined requirements.
"""

PAIRS = [
    (
        "thinking/meta-confidence-debug-no-repro-memory",
        r'''Our production app crashes every 3-7 days with "Killed" in the logs. We can't reproduce it in staging. What's causing it?''',
        r'''<think>
I'm fairly confident about the category of problem but uncertain about the specific cause.

What I'm confident about:
- "Killed" (capital K, no other message) is almost always the Linux OOM Killer
- The OOM killer terminates the process using the most memory when the system runs out
- The 3-7 day cycle suggests a SLOW memory leak — memory grows gradually until OOM
- Not reproducible in staging = staging has different traffic patterns, data volumes, or uptime

What I'm uncertain about:
- WHERE the memory leak is (application code? library? database connections? file handles?)
- Whether it's actually a memory leak or just a legitimately growing memory need (caching, session storage)
- Whether the staging environment has enough memory headroom to mask the leak
- Whether it's the app process or another process on the same machine that's consuming memory

What I definitely don't know:
- Server memory size and current usage patterns
- Whether `dmesg` confirms OOM kills
- Application memory profile over time
- Whether monitoring shows gradual memory growth
</think>

**"Killed" without other context is almost certainly the Linux OOM (Out of Memory) Killer.** I'm fairly confident about this.

**To confirm:**
```bash
# Check kernel logs for OOM kill confirmation
dmesg | grep -i "oom\|killed"
# Look for: "Out of memory: Killed process XXXX (python)"

# Check if it was the OOM killer specifically
journalctl -k | grep -i oom
```

**Why it's not reproducible in staging:**
- Staging restarts more frequently (deploys) → leak never reaches critical point
- Staging has less traffic → slower memory growth
- Staging might have more memory headroom

**Diagnosing the memory leak:**

```bash
# 1. Monitor memory growth over days
# Add this as a cron job:
*/5 * * * * ps -o pid,rss,command -p $(pgrep -f gunicorn) >> /var/log/memory_tracking.log

# 2. Check if memory grows linearly
# Plot RSS over time — if it slopes upward: leak confirmed
```

```python
# 3. In-app memory profiling
import tracemalloc
tracemalloc.start()

@app.route('/debug/memory')
def memory_debug():
    snapshot = tracemalloc.take_snapshot()
    top = snapshot.statistics('lineno')[:10]
    return jsonify([{
        'file': str(s.traceback),
        'size_mb': round(s.size / 1024 / 1024, 2)
    } for s in top])
```

**Most common Python memory leak causes:**

| Cause | Likelihood | How to check |
|-------|-----------|-------------|
| Growing global dict/list | High | Check module-level collections |
| Unbounded cache | High | Check lru_cache, custom caches |
| DB session/connection leak | Medium | Check connection pool stats |
| File handles not closed | Medium | `ls /proc/<pid>/fd \| wc -l` |
| Circular references | Low | `gc.garbage` list |

**Immediate mitigation while debugging:**
```bash
# Gunicorn: auto-restart workers after N requests
gunicorn --max-requests 1000 --max-requests-jitter 100 app:app
# Workers restart before leak reaches critical size
```

I'm confident this is a memory leak + OOM, but the specific leaking code requires profiling to identify.'''
    ),
    (
        "thinking/meta-confidence-security-jwt",
        r'''Is our JWT implementation secure? Here's how we generate tokens:

```python
import jwt
from datetime import datetime, timedelta

def create_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
```

We store the SECRET_KEY in an environment variable.''',
        r'''<think>
I can assess the visible code, but I need more information for a full security assessment.

What I'm confident about:
- The basic structure is reasonable — payload with user_id and expiration
- HS256 is a valid signing algorithm for JWTs
- Storing SECRET_KEY in an environment variable is good practice
- 24-hour expiration is reasonable for many use cases

What I'm uncertain about:
- How SECRET_KEY is generated (is it cryptographically random and long enough?)
- How the token is VERIFIED (this code only shows creation, not validation)
- Whether the token validation checks the algorithm (algorithm confusion attacks)
- Whether there's token refresh/rotation
- How the token is transmitted and stored on the client

What I definitely don't know:
- The SECRET_KEY value (is it "secret123" or a proper random key?)
- The verification code
- Whether there's token revocation capability
- Client-side storage (localStorage? HttpOnly cookie?)
- Whether the API validates expired tokens correctly

I can flag what's visible as good or bad, but a full security assessment requires seeing the verification code and understanding the full flow.
</think>

**The token creation looks reasonable, but I can't fully assess security without seeing the verification side.** Here's what I can evaluate:

**What looks correct:**
- Expiration claim (`exp`) set ✓
- Secret in environment variable ✓
- HS256 algorithm specified explicitly ✓

**What I need to verify (and you should check):**

**1. Is SECRET_KEY strong enough?**
```python
# BAD (guessable):
SECRET_KEY = "mysecret"

# GOOD (cryptographically random):
# python -c "import secrets; print(secrets.token_hex(32))"
# Should be 256+ bits of randomness
```

**2. Does your verification prevent algorithm confusion?**
```python
# DANGEROUS — allows attacker to set alg=none:
decoded = jwt.decode(token, SECRET_KEY)

# SAFE — explicitly requires HS256:
decoded = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
```

**3. Client-side storage (I don't know your setup):**

| Storage | Security |
|---------|----------|
| HttpOnly cookie | Best — not accessible to JS (XSS-safe) |
| localStorage | Vulnerable to XSS |
| sessionStorage | Better than localStorage, still XSS-vulnerable |
| URL parameters | Terrible — logged everywhere |

**4. Can you revoke tokens?**
- With JWTs alone: no (valid until expired)
- Need: token blacklist in Redis, or short expiry + refresh tokens

**Things I'm confident are missing from your implementation:**
```python
# Consider adding these claims:
payload = {
    'user_id': user_id,
    'exp': datetime.utcnow() + timedelta(hours=24),
    'iat': datetime.utcnow(),         # Issued at — useful for rotation
    'jti': str(uuid.uuid4()),          # Unique ID — needed for revocation
}
```

**To complete the security assessment, I'd need to see:**
1. Token verification code (critical)
2. How the token is sent to and stored on the client
3. Whether there's a refresh token flow
4. How `SECRET_KEY` is generated'''
    ),
    (
        "thinking/meta-confidence-compatibility-python-upgrade",
        r'''We're upgrading from Python 3.8 to 3.12. Our app uses Django, Celery, pandas, numpy, and about 30 other packages. Will everything work?''',
        r'''<think>
I'm uncertain about specific package compatibility. This is a concrete question where guessing could cause real problems.

What I'm confident about:
- Python 3.8 → 3.12 spans several versions with breaking changes
- Django, pandas, numpy, and Celery all support Python 3.12 in their LATEST versions
- But their CURRENTLY INSTALLED versions may not support Python 3.12
- There are known breaking changes between 3.8 and 3.12 that could affect app code

What I'm uncertain about:
- Which specific versions of each package you have installed
- Whether any of the "30 other packages" have Python 3.12 support
- Whether your code uses any deprecated Python features removed in 3.9-3.12
- Whether C extension packages need recompilation for 3.12

What I definitely don't know:
- Your current package versions (requirements.txt / poetry.lock)
- Whether you use any abandoned/unmaintained packages
- Whether you use typing features that changed (3.9 removed some 3.8 patterns)
- Whether you have C extensions or use ctypes

I should NOT say "yes, it'll work" or "no, it won't" — I should give them a verification process.
</think>

**I can't tell you "yes" or "no" without seeing your dependency versions.** Python 3.8 → 3.12 has breaking changes that could affect your app in non-obvious ways.

**What I'm confident about:**
- Django 4.2+, pandas 2.0+, numpy 1.24+, Celery 5.3+ all support Python 3.12
- But your CURRENT versions may be older and incompatible

**What I'm uncertain about:**
- Whether your 30+ other packages have Python 3.12 support
- Whether any package uses deprecated C API (removed in 3.12)
- Whether your own code uses removed features

**Known breaking changes (3.8 → 3.12) to check:**

| Change | Affected code |
|--------|--------------|
| `collections.Mapping` removed (use `collections.abc`) | Old libraries, custom code |
| `distutils` removed | Build scripts, some packages |
| `imp` module removed | Very old code |
| `typing.Dict`, `typing.List` → `dict`, `list` | Not breaking, but FYI |
| `asyncio.coroutine` removed | Old async code |
| Various C API changes | C extension packages |

**Safe upgrade process:**

```bash
# Step 1: Check which packages need updating
pip list --outdated

# Step 2: Check Python 3.12 compatibility
# For each package, check PyPI or GitHub for 3.12 support
pip install vermin  # Checks minimum Python version needed
vermin --target=3.12 src/

# Step 3: Test in an isolated environment
python3.12 -m venv test312
source test312/bin/activate
pip install -r requirements.txt 2>&1 | tee install_log.txt
# Check for any installation failures

# Step 4: Run your test suite
pytest --tb=long 2>&1 | tee test_log.txt

# Step 5: Check for deprecation warnings
python -W all manage.py test 2>&1 | grep -i deprecat
```

**Common gotchas:**
1. **C extensions** may need to be recompiled — `pip install --no-binary :all: package_name`
2. **Abandoned packages** with no 3.12 support — check `pip show <package>` for last update date
3. **Django version** — Django 3.x doesn't support Python 3.12, need Django 4.2+

**Don't upgrade production directly.** Test in CI first, then staging, then production.'''
    ),
    (
        "thinking/meta-confidence-underdefined-api-rate",
        r'''What rate limit should I set for my API?''',
        r'''<think>
I have almost no information to give a specific answer. This is a case where I must express maximum uncertainty.

What I'm confident about:
- Rate limits exist to prevent abuse, ensure fair usage, and protect infrastructure
- The right rate limit depends entirely on the use case, which I don't know

What I'm uncertain about:
- Everything, because I don't know:
  - What the API does
  - Who the consumers are (public API? internal? mobile app?)
  - What "expensive" means for this API (DB-heavy? CPU-heavy? calls external APIs?)
  - Current usage patterns
  - Infrastructure capacity

I should state my uncertainty and provide a framework for deciding rather than guessing.
</think>

**I can't give a specific number without understanding your API.** Rate limits depend entirely on context.

**Questions I need answered:**

1. **Who uses the API?**
   - Public developer API → need strict, per-key limits
   - Your own frontend → more generous limits
   - Internal service-to-service → maybe no limit needed

2. **What do the endpoints do?**
   - Read from cache → can handle 1000s req/s
   - Complex DB query → maybe 10-50 req/s per user
   - Calls external API → limited by external API's rate

3. **What are you protecting against?**
   - Abuse/scraping → aggressive limits
   - Accidental client bugs → gentle limits with good error messages
   - Infrastructure protection → based on actual capacity

**Framework for deciding:**

| API type | Typical limit | Reasoning |
|----------|--------------|-----------|
| Public API (free tier) | 60-100 req/min | Prevent abuse, encourage paid |
| Public API (paid) | 1,000-10,000 req/min | Based on plan tier |
| Own frontend | 200-500 req/min per IP | Prevent bots, allow normal browsing |
| Internal service | No limit or very high | Trust internal services |
| Authentication endpoints | 5-10 req/min | Prevent brute force |
| File upload | 5-10 req/hour | Expensive operations |

**If you have no data, start here and adjust:**
```python
# Conservative defaults for a public API:
default_limits = [
    "100 per minute",      # General endpoints
    "10 per minute",       # Authentication
    "5 per minute",        # Expensive operations (search, export)
]
```

**Then: monitor actual usage**, find what's too strict (legitimate users hitting limits) and what's too loose (abuse not caught). Rate limits should be data-driven, not guessed.'''
    ),
    (
        "thinking/meta-confidence-emerging-tech-ai-coding",
        r'''Should I use AI-generated code in production? My company is considering using GitHub Copilot for all our development.''',
        r'''<think>
I have strong opinions but should be calibrated about uncertainty here, since this is an evolving field.

What I'm confident about:
- AI coding assistants (Copilot, etc.) can significantly boost productivity for boilerplate and common patterns
- AI-generated code requires the same review scrutiny as human code — it can have bugs, security issues, and bad patterns
- AI assistants don't understand the full codebase context, business requirements, or security implications
- The code review process, not the code generation method, determines production quality

What I'm uncertain about:
- How quickly AI coding tools are improving (my knowledge has a cutoff)
- Whether AI-generated code has different bug patterns than human code
- The long-term impact on code quality and developer skill development
- Legal implications of AI-generated code (copyright, licensing) — this is unsettled law

What I definitely don't know:
- Your company's specific codebase, security requirements, and compliance needs
- Whether your team has the experience to effectively review AI-generated suggestions
- How Copilot performs on your specific tech stack
</think>

**Yes, with caveats.** AI-generated code is neither magic nor dangerous — it's a tool that needs the same scrutiny as any code.

**What I'm confident about:**

**Use AI assistants for:**
- Boilerplate code (CRUD endpoints, test scaffolding)
- Common patterns (auth middleware, error handling)
- Documentation and comments
- Exploring unfamiliar APIs/libraries
- Writing tests for existing code

**Be cautious with AI for:**
- Security-critical code (auth, crypto, input validation)
- Complex business logic
- Performance-critical paths
- Anything requiring deep codebase context

**What I'm uncertain about:**
- Long-term impact on developer skills (does reliance on AI reduce deep understanding?)
- Legal landscape (AI-generated code and licensing is unsettled law)
- How quickly AI tools improve (my assessment may age quickly)

**Practical guidelines:**

| Practice | Rationale |
|----------|-----------|
| Review AI code like any PR | AI makes subtle bugs too |
| Don't accept suggestions blindly | Understand what the code does before committing |
| Test AI-generated code thoroughly | It may work for happy path but miss edge cases |
| Don't use AI for crypto/security | Too easy to introduce vulnerabilities |
| Use AI for boilerplate, not architecture | AI doesn't understand your system's context |

**The right mental model:** AI coding assistants are like a very fast junior developer — they produce plausible code quickly but need senior review. The code review process, not the generation method, determines production quality.

**My honest assessment:** Companies using AI assistants with proper code review see real productivity gains. Companies using AI assistants without proper code review see more bugs. The tool isn't the variable — the process is.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
