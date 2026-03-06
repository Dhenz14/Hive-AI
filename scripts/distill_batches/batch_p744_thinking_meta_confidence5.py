"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 5)

More scenarios covering ambiguous bugs, underdefined requirements,
best practices without consensus, and performance without profiling.
"""

PAIRS = [
    (
        "thinking/meta-confidence-ambiguous-bug-slow",
        r'''Our app suddenly got slow. Average response time went from 50ms to 2 seconds. Nothing was deployed. Help!''',
        r'''<think>
I'm uncertain about the specific cause but can rank hypotheses.

What I'm confident about:
- 50ms → 2 seconds is a 40x regression — this is severe and likely a single root cause
- "Nothing deployed" means environmental change (but people often forget config changes, dependency updates, or infrastructure changes)
- A sudden jump (not gradual) suggests an event, not a leak

What I'm uncertain about:
- Whether ALL endpoints are slow or just some
- Whether it's the app, the database, the network, or an external service
- Whether it started at a specific time (correlatable with events)

Most likely causes (no-deploy scenario):
1. Database issue (HIGH): slow queries, lock contention, dead index, disk I/O
2. External service degradation (HIGH): API calls timing out
3. Infrastructure (MEDIUM): network latency, DNS, disk IOPS saturation
4. Resource exhaustion (MEDIUM): memory pressure causing swapping, CPU stolen by another process
5. Data growth (LOW): table crossed a size threshold where queries become slow
</think>

**I can't identify the cause without diagnostics, but here's a systematic triage — check in this order (fastest to slowest):**

**1. Where is the time spent? (30 seconds)**
```bash
# Check database query time vs app time
# If your app logs request timing:
grep "slow\|timeout\|2[0-9][0-9][0-9]ms" /var/log/app.log | tail -20

# Check database specifically:
psql -c "SELECT * FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - interval '1 second';"
```

**2. Check infrastructure (1 minute)**
```bash
top         # CPU usage — is something eating CPU?
free -m     # Memory — is the system swapping?
iostat -x 1 # Disk I/O — is the disk saturated?
```

**3. Check external dependencies (1 minute)**
```bash
# Are external APIs responding slowly?
time curl -s https://api.stripe.com/v1/charges -H "Authorization: Bearer sk_test"
time redis-cli ping
time psql -c "SELECT 1"
```

**Hypothesis ranking:**

| Hypothesis | Probability | Diagnostic |
|-----------|------------|-----------|
| Database under load/lock contention | High | Check `pg_stat_activity`, slow query log |
| External API slow/timeout | High | `time curl` each external service |
| Disk I/O saturation | Medium | `iostat -x 1` |
| Memory swapping | Medium | `free -m`, check for swap usage |
| DNS resolution slow | Medium | `time dig api.stripe.com` |
| Network latency spike | Lower | `mtr db-host` |
| Data growth threshold | Lower | Check largest table sizes |

**What I'm uncertain about:**
- Whether it's consistent (every request) or intermittent (some requests)
- Whether it correlates with traffic volume
- The exact start time (which would help correlate with events)

The diagnostics above should identify the cause within 5 minutes.'''
    ),
    (
        "thinking/meta-confidence-underdefined-migration",
        r'''We want to migrate our monolith to microservices. How should we approach this?''',
        r'''<think>
This is extremely underdefined. "Migrate to microservices" is a multi-month to multi-year undertaking that depends on dozens of factors I don't know.

What I'm confident about:
- Microservice migrations fail more often than they succeed
- The #1 mistake is trying to split everything at once ("big bang")
- The strangler fig pattern is the proven approach
- Without knowing the codebase, team size, and pain points, specific advice is speculation

What I'm uncertain about:
- Whether they SHOULD migrate at all (what problem are they solving?)
- Which services to extract first
- Their team's operational maturity (can they run distributed systems?)

What I definitely don't know:
- Codebase size and architecture
- Team size and skills
- Current pain points that motivate the migration
- Deployment infrastructure
- Whether they've tried modular monolith first
</think>

**I need a lot more context before recommending an approach.** Microservice migrations are the #1 way engineering teams waste months of work.

**Critical questions before starting:**

1. **Why?** What specific problem are you trying to solve?
   - Deployment speed? → Maybe CI/CD optimization is enough
   - Team scaling? → How many developers? (<15 probably doesn't need microservices)
   - Independent scaling? → Which component actually needs it?
   - Technology diversity? → Genuinely need different languages/frameworks?

2. **Have you tried a modular monolith first?**
   ```
   monolith/
   ├── users/          # Clear module boundary
   ├── orders/         # Could become a service IF needed
   ├── payments/       # Well-defined interface
   └── notifications/  # Loosely coupled
   ```
   This gives you 80% of the benefits with 20% of the complexity.

3. **Team readiness:**
   - Can your team operate distributed systems? (Service mesh, distributed tracing, eventual consistency)
   - Do you have DevOps/platform engineering support?
   - Is your CI/CD mature enough for multi-service deployments?

**What I'm confident about:**
- Never do a "big bang" rewrite → use the strangler fig pattern
- Extract the MOST independent component first
- Don't extract until you have clear service boundaries
- Each extraction should be reversible (you should be able to merge it back)

**What I'm uncertain about:**
- Which component to extract first (depends on your codebase)
- The right service granularity (too many small services is worse than a monolith)
- Whether your specific situation justifies the migration at all

**If you proceed, the pattern that works:**
1. Define clear module boundaries in the monolith
2. Create internal APIs between modules (function calls, not HTTP yet)
3. Extract ONE module as a service
4. Run both for weeks in production
5. If successful, extract the next one
6. If it causes more problems than it solves, merge it back

Most teams should stop at step 2 (modular monolith). That's not a failure — it's engineering maturity.'''
    ),
    (
        "thinking/meta-confidence-no-consensus-monolith-vs-micro",
        r'''What's better: monolith or microservices? We're starting a new project.''',
        r'''<think>
This is a question where the community genuinely has no consensus. I should present both sides honestly.

What I'm confident about:
- There is no universally "better" architecture
- Most successful companies STARTED with a monolith
- Premature microservices is a common and expensive mistake
- The right answer depends on team size, product maturity, and operational capacity

What I'm uncertain about:
- The exact team size threshold where microservices become worthwhile
- Whether the "modular monolith" movement is a lasting trend or temporary
- The long-term cost comparison for any specific scenario
</think>

**There's no consensus.** This is one of the most debated topics in software engineering. Here's an honest comparison:

**What I'm confident about:**

| Factor | Monolith | Microservices |
|--------|---------|--------------|
| Start a new product | Better (ship fast) | Worse (infra overhead) |
| Team of 2-10 | Better | Overkill |
| Team of 50+ | Can be challenging | Often necessary |
| Simple deployment | 1 deploy | N deploys to orchestrate |
| Debugging | Stack trace | Distributed tracing |
| Data consistency | Transactions | Eventual consistency |
| Time to first feature | Days | Weeks (after infra setup) |

**The honest history:**
- **Netflix**: Started monolith → migrated to microservices at scale
- **Amazon**: Started monolith → migrated when teams couldn't work independently
- **Shopify**: STILL a monolith (modular) at massive scale
- **Instagram**: Monolith on Django serving billions of requests
- **Segment**: Went to microservices → went BACK to monolith

**What the different camps say:**

**"Always start monolith"** (Martin Fowler, DHH):
- You don't know the right service boundaries yet
- Premature decomposition creates distributed monoliths (worst of both worlds)
- Modular monolith gives most benefits without distributed systems complexity

**"Microservices from the start"** (some tech leaders):
- Forces clean API boundaries early
- Independent deployment from day one
- Teams can work independently

**My uncertain recommendation:**
For a NEW project, start with a **well-structured monolith** with clear module boundaries. Extract services when:
- A specific module needs independent scaling
- Teams are stepping on each other's toes
- You have the DevOps maturity to operate distributed systems

This is my best judgment, not settled science. Reasonable engineers disagree.'''
    ),
    (
        "thinking/meta-confidence-performance-frontend",
        r'''Our React app's Lighthouse score is 35. How do I get it to 90+?''',
        r'''<think>
I'm somewhat confident about general optimization strategies but uncertain about the specific fixes without seeing the app.

What I'm confident about:
- A score of 35 is very low — there are likely a few major issues, not many small ones
- The top causes of low Lighthouse scores are: large JavaScript bundles, unoptimized images, no lazy loading, render-blocking resources, and missing caching headers
- Getting from 35 to 90 is achievable but the specific fixes depend on what's causing the low score

What I'm uncertain about:
- Which specific metric is pulling the score down (LCP? TBT? CLS?)
- Whether the app uses SSR or is pure client-side
- The bundle size and composition
- Whether images are optimized

What I definitely don't know:
- The app's architecture
- Current bundle size
- Whether they use code splitting
- Image sizes and formats
- Third-party scripts loaded
</think>

**I can give you the likely fixes, but without seeing the Lighthouse report details, I'm guessing at which specific issues matter most.**

**Run Lighthouse and check which metrics are red:**
```
Performance score breakdown:
- LCP (Largest Contentful Paint) — how fast main content appears
- TBT (Total Blocking Time) — how long JS blocks the main thread
- CLS (Cumulative Layout Shift) — visual stability
- FCP (First Contentful Paint) — first visual response
- Speed Index — how quickly content visually populates
```

**Most likely fixes (ordered by typical impact):**

**If LCP is bad (most common):**
```jsx
// 1. Optimize images (usually the #1 fix)
// Before: <img src="hero.jpg" />  (2MB uncompressed JPEG)
// After:
<img
    src="hero.webp"
    loading="lazy"
    width={800}
    height={400}
    alt="Hero"
/>
// Use WebP format, add dimensions, lazy load below-fold images
```

**If TBT is bad:**
```jsx
// 2. Code splitting (reduce initial bundle)
// Before:
import HeavyComponent from './HeavyComponent'

// After:
const HeavyComponent = React.lazy(() => import('./HeavyComponent'))
```

```bash
# Check your bundle size:
npx source-map-explorer build/static/js/*.js
# This shows EXACTLY what's in your bundle
```

**If CLS is bad:**
```css
/* 3. Reserve space for dynamic content */
img, video { width: 100%; height: auto; aspect-ratio: 16/9; }
.ad-slot { min-height: 250px; }
```

**Universal improvements:**
- Remove unused dependencies: `npx depcheck`
- Tree-shake: ensure your bundler eliminates dead code
- Compress: enable gzip/brotli on your server
- Cache: set `Cache-Control: max-age=31536000` for static assets

**What I'm uncertain about:**
- Which of these applies to YOUR app (the Lighthouse report details would tell us)
- Whether third-party scripts (analytics, ads, chat widgets) are the main problem
- Whether SSR/SSG would be appropriate for your use case (Next.js)

**Share your Lighthouse report breakdown** and I can give specific, prioritized fixes.'''
    ),
    (
        "thinking/meta-confidence-security-incomplete-csrf",
        r'''We added CSRF protection to our Django app. Are we safe from CSRF attacks now?''',
        r'''<think>
I'm fairly confident about the general answer but uncertain about the specific implementation.

What I'm confident about:
- Django's CSRF protection ({% csrf_token %}) is well-designed and effective for standard form submissions
- But "safe from CSRF" depends on more than just adding the middleware
- There are common ways to misconfigure CSRF protection even when it's "enabled"

What I'm uncertain about:
- Whether they're using Django's CSRF middleware correctly
- Whether they have API endpoints that bypass CSRF (common with DRF)
- Whether they're using @csrf_exempt anywhere
- Whether their CORS settings are correct
- Whether they handle CSRF for AJAX requests properly

What I definitely don't know:
- Their specific configuration
- Whether they have any @csrf_exempt views
- Whether they use Django REST Framework (which has its own CSRF handling)
- Their CORS settings
- Whether they serve the frontend from a different domain
</think>

**Probably, but I can't be certain without seeing your configuration.** Django's CSRF protection is good, but there are common ways to undermine it.

**What I'm confident about:**
- Django's `CsrfViewMiddleware` + `{% csrf_token %}` protects standard form submissions
- The implementation is well-tested and secure when properly configured

**Things that could make you NOT safe (check these):**

**1. `@csrf_exempt` decorators:**
```python
# BAD: Any view with this bypasses CSRF protection
@csrf_exempt
def transfer_money(request):  # Vulnerable!
    ...

# Check: grep your codebase
# grep -r "csrf_exempt" .
```

**2. Django REST Framework API views:**
```python
# DRF's SessionAuthentication enforces CSRF, but TokenAuthentication doesn't
# If you use token auth from a browser, you need CSRF checks
```

**3. CORS misconfiguration:**
```python
# BAD: allows any origin to make authenticated requests
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
# This effectively bypasses CSRF protection!
```

**4. Subdomains:**
```python
# If attacker controls evil.yourdomain.com, they can set cookies for .yourdomain.com
# Check CSRF_COOKIE_DOMAIN setting
```

**5. AJAX requests:**
```javascript
// Are your AJAX requests sending the CSRF token?
// If using fetch(), you need to include the token manually
fetch('/api/endpoint', {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),  // Must include this
    },
    credentials: 'same-origin',  // Must include this
});
```

**Verification checklist:**
- [ ] `django.middleware.csrf.CsrfViewMiddleware` in MIDDLEWARE
- [ ] No `@csrf_exempt` on sensitive views
- [ ] `grep -r "csrf_exempt" .` shows nothing dangerous
- [ ] CORS settings don't allow all origins with credentials
- [ ] AJAX requests include CSRF token header
- [ ] `CSRF_COOKIE_SECURE = True` in production (HTTPS only)
- [ ] `CSRF_COOKIE_HTTPONLY = True` (prevents JS access to cookie)

**I'm fairly confident Django's CSRF is correct, but I'm uncertain about YOUR configuration.** Run through the checklist above.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
