"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 8)"""

PAIRS = [
    (
        "thinking/meta-confidence-ambiguous-encoding",
        r'''Our API returns garbled text for some users. Instead of "naïve résumé", they see "naÃ¯ve rÃ©sumÃ©". It works fine for most users. What's the issue?''',
        r'''<think>
I'm quite confident about the category of bug here.

What I'm confident about:
- "naÃ¯ve rÃ©sumÃ©" is the classic symptom of UTF-8 bytes being interpreted as Latin-1 (ISO-8859-1)
- The original text "naïve résumé" contains non-ASCII characters (ï, é)
- In UTF-8: ï = 0xC3 0xAF. In Latin-1: 0xC3 = Ã, 0xAF = ¯. Hence "Ã¯" = ï decoded as Latin-1
- This is a charset/encoding mismatch somewhere in the chain

What I'm uncertain about:
- WHERE in the chain the mismatch occurs (database, API, client, CDN?)
- Whether the data is stored correctly but served with wrong Content-Type
- Whether it's a database connection charset issue
- Why it only affects "some users" (different browsers? different API clients?)

Possible locations of the bug:
1. API response missing charset: Content-Type: application/json (no charset=utf-8)
2. Database connection not using UTF-8
3. Data stored in wrong encoding in DB
4. Proxy/CDN re-encoding the response
5. Client-side decoding issue
</think>

**I'm quite confident this is a UTF-8/Latin-1 encoding mismatch.** The garbled characters are the classic symptom:

```
"naïve" in UTF-8 bytes: 6E 61 C3 AF 76 65
Same bytes read as Latin-1: n a Ã ¯ v e → "naÃ¯ve"
```

**Where to check (most to least likely):**

**1. API Content-Type header (most common):**
```python
# Check if your response includes charset:
# BAD: Content-Type: application/json
# GOOD: Content-Type: application/json; charset=utf-8

# Flask fix:
app.config['JSON_AS_ASCII'] = False
# Or explicitly:
return Response(json.dumps(data, ensure_ascii=False),
                content_type='application/json; charset=utf-8')
```

**2. Database connection encoding:**
```python
# SQLAlchemy — ensure UTF-8 connection:
engine = create_engine('postgresql://...?client_encoding=utf8')

# Or in PostgreSQL:
SHOW client_encoding;  -- Should be 'UTF8'
```

**3. Data stored in wrong encoding:**
```sql
-- Check database encoding:
SELECT character_set_name FROM information_schema.columns
WHERE table_name = 'your_table' AND column_name = 'your_column';
```

**Why "some users" see it and others don't:**
- Modern browsers auto-detect UTF-8 even without explicit charset → works
- Older browsers or API clients follow the header strictly → broken
- Some clients (Postman, curl) may display raw bytes differently

**I'm uncertain about:**
- Whether the issue is in response encoding or data storage (need to check both)
- Whether a CDN or reverse proxy is altering the Content-Type header

**Quick diagnostic:**
```bash
# Check the raw response headers:
curl -sI https://api.yourapp.com/endpoint | grep -i content-type
# If it says "application/json" without charset=utf-8, that's likely the issue
```'''
    ),
    (
        "thinking/meta-confidence-no-consensus-rest-conventions",
        r'''Our team is arguing about REST API naming conventions. Should endpoints be plural (/users) or singular (/user)? Should we use camelCase or snake_case for JSON fields?''',
        r'''<think>
These are convention questions with no objectively correct answer. I should present the dominant conventions while acknowledging they're conventions, not rules.

What I'm confident about:
- Plural nouns (/users) is the MAJORITY convention in REST APIs
- snake_case vs camelCase for JSON depends on your client ecosystem
- Consistency within YOUR API matters far more than which convention you pick
- There is no RFC or standard that mandates either choice

What I'm uncertain about:
- Whether the "majority convention" should override team preference
- The exact percentage split in the industry
</think>

**These are conventions, not rules.** The community doesn't fully agree, but there ARE majority preferences:

**Endpoint naming — plural is the dominant convention:**

| Style | Examples | Who uses it |
|-------|---------|-------------|
| Plural (majority) | `/users`, `/users/123` | GitHub, Stripe, Twilio, most APIs |
| Singular (minority) | `/user`, `/user/123` | Some APIs, often feels odd |

The argument for plural: `/users` = the collection, `/users/123` = one user from the collection. This reads naturally.

**JSON field naming — depends on your ecosystem:**

| Style | Example | When to use |
|-------|---------|-------------|
| camelCase | `{"firstName": "Alice"}` | JavaScript-heavy (React, Node.js) |
| snake_case | `{"first_name": "Alice"}` | Python-heavy (Django, Flask) |

- GitHub API: snake_case
- Stripe API: snake_case
- Google APIs: camelCase
- AWS APIs: PascalCase (unusual)

**What I'm confident about:**
- **Consistency matters more than the specific choice.** Pick one, enforce it, move on.
- Don't let this debate block actual work — it's bikeshedding.

**My uncertain recommendation:**
```
Endpoints:  /users (plural) — aligns with majority convention
JSON:       snake_case — works well with Python backends
            OR camelCase — if your primary consumers are JavaScript

Just pick one and document it. Enforce it with a linter.
```

**The conversation to end the argument:**
"We'll use plural endpoints and snake_case JSON because [majority convention / matches our stack]. This is now our standard. Let's move on to building features."

**What actually matters in API design** (more than naming):
- Consistent error format
- Proper HTTP status codes
- Good documentation
- Versioning strategy
- Pagination approach'''
    ),
    (
        "thinking/meta-confidence-performance-no-profile-cache",
        r'''Adding Redis caching should make our app 10x faster, right?''',
        r'''<think>
I can't make this prediction without knowing what's slow and why.

What I'm confident about:
- Caching CAN provide dramatic speedups IF the bottleneck is repeated expensive computations or database queries
- Caching provides ZERO speedup if the bottleneck is elsewhere (network, frontend rendering, CPU computation)
- "10x faster" is a specific claim I can't validate without profiling data
- Caching has costs (cache invalidation, stale data, additional infrastructure)

What I'm uncertain about:
- What's actually slow in their app
- Whether the slow operations are cacheable (are they repeated queries with the same inputs?)
- Whether the cache hit rate would be high enough to matter
</think>

**I can't predict "10x faster" without knowing what's slow.** Caching could give you 100x improvement or 0x improvement depending on the bottleneck.

**When caching gives big speedups:**
```
Scenario: Same expensive query runs 100x per minute
Without cache: 100 × 200ms DB query = high latency
With cache:    1 × 200ms + 99 × 1ms cache hit = 10-100x faster ✓
```

**When caching gives zero speedup:**
```
Scenario: Each request has unique parameters
Without cache: 100 unique queries × 200ms
With cache:    100 cache misses × 200ms + Redis overhead = SLOWER ✗

Scenario: Bottleneck is frontend rendering
Without cache: 50ms API + 3000ms render = 3050ms
With cache:    5ms API + 3000ms render = 3005ms = 1.5% faster ✗
```

**What determines caching benefit:**

| Factor | Good for caching | Bad for caching |
|--------|-----------------|-----------------|
| Cache hit rate | >80% same queries | Mostly unique queries |
| Query cost | >50ms per query | <5ms per query |
| Data freshness | Tolerant (minutes-hours) | Must be real-time |
| Read/write ratio | Read-heavy (>90% reads) | Write-heavy |

**Before adding Redis, check:**
1. **What's actually slow?** Profile with Django Debug Toolbar / Flask-DebugToolbar
2. **Is it the same query repeating?** Check query logs for duplicates
3. **Would an index fix it?** Sometimes a $0 index beats a $20/mo Redis server

**I'm confident about:** Caching is not a magic "10x faster" button. It's a specific optimization for specific patterns.

**I'm uncertain about:** Whether YOUR app would benefit from caching — that requires seeing your actual performance profile.'''
    ),
    (
        "thinking/meta-confidence-security-cors",
        r'''I configured CORS on my API. Am I protected from cross-origin attacks?

```python
from flask_cors import CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})
```''',
        r'''<think>
I'm quite confident this CORS configuration has issues.

What I'm confident about:
- `origins: "*"` means ANY website can make requests to your API
- This essentially disables CORS protection — any malicious site can call your API
- CORS with wildcard origin cannot send credentials (cookies, auth headers) — this is a browser security restriction
- If the API uses cookies for auth, wildcard CORS breaks authentication
- If the API uses Bearer tokens, wildcard CORS allows any site to make requests IF they have the token

What I'm uncertain about:
- Whether this API is public (meant to be called from anywhere) — then wildcard might be intentional
- Whether authentication is cookie-based or token-based
- Whether there are sensitive endpoints that shouldn't be exposed
</think>

**`origins: "*"` essentially disables CORS protection.** Any website in the world can make requests to your API.

**I'm confident this is wrong if:**
- Your API uses cookies for authentication
- Your API has any endpoints that shouldn't be called from arbitrary websites
- Your API returns user-specific data

**I'm uncertain whether it's wrong if:**
- This is a truly public API (like a weather API) with no authentication
- All authentication uses API keys that third-party websites legitimately have

**What `origins: "*"` actually means:**
```
evil-website.com → fetch('https://your-api.com/api/user/profile')
                 → Browser allows the request ← BAD if your API has auth cookies
```

**Fix — whitelist your actual frontend origins:**
```python
CORS(app, resources={r"/api/*": {
    "origins": [
        "https://yourfrontend.com",
        "https://www.yourfrontend.com",
        "http://localhost:3000",  # Development only
    ],
    "supports_credentials": True,  # If using cookies
}})
```

**CORS common misconceptions:**
- CORS does NOT prevent server-to-server requests (only browser-enforced)
- CORS does NOT replace authentication — it's an additional layer
- `origins: "*"` with `supports_credentials: True` is rejected by browsers (security feature)

**What CORS actually protects against:**
A user is logged into your-api.com. They visit evil-site.com. Without CORS, evil-site.com's JavaScript could make authenticated requests to your API using the user's cookies. CORS prevents this by requiring your API to explicitly whitelist which origins are allowed.

**With `origins: "*"`, this protection is removed.**

**I'm uncertain about your specific case** — if this is a public API with no auth, wildcard origins might be fine. But for any API with user authentication, whitelist specific origins.'''
    ),
    (
        "thinking/meta-confidence-debug-no-repro-timezone",
        r'''Our scheduled job runs at 9 AM but users in different timezones see different results. Some users see yesterday's report, others see today's. The cron job runs at "9:00 AM" and generates a report for "today." What's going on?''',
        r'''<think>
I'm fairly confident about this — it's a classic timezone issue with scheduled jobs.

What I'm confident about:
- "9:00 AM" in a cron job runs in the SERVER's timezone
- "Today" in the code depends on the server's timezone when the job runs
- Users in different timezones have different "todays" — a user in UTC+12 is already "tomorrow" when the server runs at 9 AM UTC
- The report generated for "today" is actually generated for the server's "today," which may be "yesterday" or "tomorrow" for users in different timezones

What I'm uncertain about:
- What timezone the server is in
- Whether the "today" calculation uses UTC or local time
- Whether users have timezone settings in their profiles
- Whether the report should be per-user-timezone or a single global report
</think>

**I'm fairly confident this is a timezone mismatch.** Here's the issue:

```
Server timezone: UTC (9:00 AM UTC)

User in New York (UTC-5):  It's 4:00 AM → "today" is correct
User in Tokyo (UTC+9):     It's 6:00 PM → they're already in "tomorrow"
User in Sydney (UTC+11):   It's 8:00 PM → definitely "tomorrow"

The report says "today's data" but "today" is different for each timezone.
```

**The fix depends on what the report should represent:**

**Option A: Report is for a specific business day (e.g., UTC day):**
```python
from datetime import datetime, timezone

def generate_report():
    # Always use UTC — consistent regardless of server timezone
    today = datetime.now(timezone.utc).date()
    data = get_data_for_date(today)
    # Label the report with the explicit date
    return {"date": str(today), "data": data}
    # Users see "Report for 2024-03-05" — no ambiguity
```

**Option B: Report is per-user timezone:**
```python
def generate_report_for_user(user):
    user_tz = ZoneInfo(user.timezone)  # e.g., "America/New_York"
    user_today = datetime.now(user_tz).date()
    data = get_data_for_date(user_today)
    return {"date": str(user_today), "data": data}
```

**Key fix — never use ambiguous "today":**
```python
# BAD: ambiguous — what timezone is "today"?
today = datetime.now().date()

# GOOD: explicit timezone
today = datetime.now(timezone.utc).date()
# Or
today = datetime.now(ZoneInfo("America/New_York")).date()
```

**What I'm uncertain about:**
- Whether your report should be a single global report or per-user
- Whether changing the report date will affect downstream systems
- Whether the cron schedule itself should change (run at midnight UTC?)

**The general rule:** Use explicit UTC everywhere internally. Convert to user timezone only for display.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
