"""Phase 4B: Self-Improvement -- Self-Evaluation (Part 12)

Evaluating own DevOps advice for practicality and appropriateness.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-devops-kubernetes-recommendation",
        r'''A solo developer asks how to deploy their Django application. I am about to recommend Kubernetes. Let me evaluate whether that is appropriate:

My draft: "Use Kubernetes for deployment. It provides auto-scaling, self-healing, and rolling updates. Set up a 3-node cluster with Helm charts for your Django app, PostgreSQL, Redis, and Nginx ingress controller."''',
        r'''<think>
Let me evaluate my DevOps recommendation:

**The context:**
- Solo developer
- Django application
- No mention of scale requirements

**My recommendation:** Kubernetes with 3-node cluster, Helm charts, multiple components.

**Is this appropriate? ABSOLUTELY NOT.**

**Problem 1: Massive overkill**
- Kubernetes is designed for teams of 10+ managing dozens of services
- A solo developer managing K8s is spending 80% of time on infrastructure
- A 3-node K8s cluster costs $150-300/month minimum
- A Django app for one developer can run on a $10/month server

**Problem 2: Operational complexity**
- K8s requires knowledge of: pods, deployments, services, ingress, ConfigMaps, secrets, namespaces, PVCs, RBAC, network policies
- Debugging requires: kubectl, container logs, pod descriptions, event streams
- Upgrades: cluster version upgrades, node draining, addon compatibility
- This is a full-time job, not a side task for a solo developer

**Problem 3: I did not ask about requirements**
- How many users?
- How much traffic?
- What is the budget?
- What is the developer's DevOps experience?

**What a solo developer actually needs:**
- `git push` to deploy
- Automatic HTTPS
- Managed database
- Zero infrastructure management

**Verdict:** I recommended enterprise infrastructure for a solo developer. This would waste weeks of setup time and hundreds of dollars monthly. Rating: 1/10.
</think>

**Self-evaluation: Kubernetes for a solo developer is like recommending a semi truck for grocery shopping. Rating: 1/10.**

**What I should recommend instead:**

"For a solo developer with a Django app, use managed hosting:

**Option 1: Railway or Render (simplest)**
```
Setup time: 15 minutes
Cost: $7-25/month
Deploy: git push (automatic)
Database: Managed PostgreSQL included
HTTPS: Automatic
Scaling: Click a button if needed
```

**Option 2: DigitalOcean App Platform**
```
Setup time: 20 minutes
Cost: $12-25/month
Deploy: git push or Docker
Database: Managed PostgreSQL add-on
HTTPS: Automatic
```

**Option 3: VPS with Docker Compose (more control)**
```
Setup time: 1-2 hours
Cost: $6-12/month
Deploy: docker compose up -d

# docker-compose.yml -- the ENTIRE infrastructure:
services:
  web:
    build: .
    ports: ['8000:8000']
    env_file: .env
  db:
    image: postgres:16
    volumes: ['pgdata:/var/lib/postgresql/data']
  nginx:
    image: nginx
    ports: ['80:80', '443:443']
volumes:
  pgdata:
```

**When to ACTUALLY consider Kubernetes:**
- 10+ developers deploying multiple services independently
- Need auto-scaling for variable traffic (Black Friday spikes)
- Running 10+ microservices that need service discovery
- Have a dedicated DevOps/platform team

**None of these apply to a solo developer.**"

**Self-evaluation lesson:** Match the infrastructure to the team and scale. The best infrastructure is the one that lets you focus on building your product, not managing servers.'''
    ),
    (
        "thinking/auto-selfeval-devops-cicd-overcomplicated",
        r'''A small team asks me to help set up CI/CD. I am about to recommend a complex pipeline. Let me evaluate my draft:

My draft: "Set up a CI/CD pipeline with: GitHub Actions for CI, ArgoCD for GitOps deployment, Terraform for infrastructure, HashiCorp Vault for secrets, SonarQube for code quality, Trivy for container scanning, and Grafana/Prometheus for monitoring. Use blue-green deployments with automatic rollback."''',
        r'''<think>
Let me evaluate my CI/CD recommendation:

**The context:** A small team asking for CI/CD help.

**My recommendation:** 7 different tools, GitOps, blue-green deployments.

**Is this appropriate? FAR TOO COMPLEX.**

**Problem 1: Too many tools**
- GitHub Actions, ArgoCD, Terraform, Vault, SonarQube, Trivy, Grafana, Prometheus
- That is 8 tools to learn, configure, maintain, and troubleshoot
- Each tool has its own documentation, upgrade cycle, and failure modes
- A small team will spend weeks just setting this up

**Problem 2: I did not ask what they need**
- How many developers?
- What is their current deployment process?
- What problems are they trying to solve?
- What is their experience with DevOps tools?
- "CI/CD" for a 3-person team is very different from a 50-person team

**Problem 3: Some of these tools solve problems they probably do not have**
- ArgoCD: GitOps for Kubernetes (do they even use K8s?)
- Vault: Enterprise secret management (GitHub secrets is probably enough)
- SonarQube: Code quality server (linters in CI are simpler)
- Trivy: Container security scanning (do they ship containers?)

**What a small team actually needs:**
- Run tests automatically on PRs
- Deploy automatically when merging to main
- Basic linting and formatting checks
- Environment variables for secrets

**Verdict:** I recommended an enterprise DevOps stack for what is probably a small team needing basic automation. Rating: 2/10.
</think>

**Self-evaluation: I recommended 8 tools when 1 would do. This is resume-driven DevOps, not practical engineering. Rating: 2/10.**

**What I should recommend instead:**

"Start simple and add complexity only when you hit real problems:

**Phase 1: Basic CI/CD (week 1, GitHub Actions only)**
```yaml
# .github/workflows/ci.yml -- This is your ENTIRE CI/CD pipeline:
name: CI/CD

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
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest
      - run: ruff check .  # Linting

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          # Deploy to your hosting platform
          # Railway: railway up
          # Render: triggers automatically on push
          # VPS: ssh user@server 'cd app && git pull && docker compose up -d'
```

**That is it. One file. No additional tools.**

**Phase 2: Add when you need it (not before)**
| When you notice... | Then add... |
|-------------------|------------|
| Tests pass but app breaks in production | Staging environment |
| Secrets scattered in code/env files | GitHub Secrets (built-in, free) |
| Security vulnerabilities in dependencies | `pip-audit` step in CI |
| Deployments cause downtime | Zero-downtime deploy (rolling update) |
| Need to roll back frequently | Tag releases, deploy by tag |
| Multiple environments (dev/staging/prod) | Environment-specific workflows |

**The principle:** Start with the simplest pipeline that catches bugs before production. Add complexity only when you experience a real problem that justifies it."

**Self-evaluation lesson:** DevOps tools exist to solve problems. If you do not have the problem, you do not need the tool. Start simple, add incrementally.'''
    ),
    (
        "thinking/auto-selfeval-devops-docker-configuration",
        r'''A developer shows me their Dockerfile that takes 10 minutes to build and produces a 2GB image. I am about to suggest using Alpine Linux as the base image. Let me evaluate whether that is the best first recommendation:

My draft: "Switch from Ubuntu to Alpine Linux as your base image. Alpine images are only 5MB compared to Ubuntu's 72MB. This will dramatically reduce your image size."''',
        r'''<think>
Let me evaluate my Docker recommendation:

**The problem:** 10-minute build time, 2GB image.

**My recommendation:** Switch to Alpine Linux base image.

**Is this the right first recommendation? NO. It addresses the wrong thing first.**

**Problem 1: Alpine is not the main issue**
- Base image: Ubuntu 72MB vs Alpine 5MB
- Savings: 67MB
- Total image: 2GB
- 67MB out of 2GB is only 3.3% of the problem
- The other 1.93GB is dependencies, build artifacts, or application code

**Problem 2: Alpine can cause problems**
- Alpine uses musl libc instead of glibc
- Many Python packages (NumPy, pandas, Pillow) need compilation on Alpine
- This can add 5-10 minutes to build time (the opposite of what we want)
- Some packages have subtle bugs on musl
- Python slim-based images are usually better

**Problem 3: The real causes of 2GB images**
1. Build dependencies left in the final image
2. No multi-stage build (compiler, dev headers in production image)
3. Not using .dockerignore (copying node_modules, .git, etc.)
4. Package manager cache not cleaned
5. Entire repo with test data and docs copied into image

**What I should investigate first:**
1. What is in the 2GB? (`docker history` or `dive`)
2. Is there a .dockerignore file?
3. Is it using multi-stage builds?
4. Are build tools being installed in the final image?

**Verdict:** Alpine is a micro-optimization when the real problem is almost certainly poor Dockerfile practices. Rating: 3/10.
</think>

**Self-evaluation: Suggesting Alpine for a 2GB image is like suggesting a lighter paint color to reduce the weight of a truck. Rating: 3/10.**

**What I should recommend instead:**

"Let's find out WHERE the 2GB is coming from, then fix the biggest problems first:

**Step 1: Analyze the image**
```bash
# See layer sizes:
docker history myapp:latest

# Or use dive for interactive analysis:
dive myapp:latest
```

**Step 2: Fix the biggest issues first**

**Fix 1: Multi-stage build (biggest impact)**
```dockerfile
# BAD: Everything in one stage (2GB)
FROM python:3.12
RUN apt-get install -y gcc libpq-dev  # Build tools in final image!
COPY . .
RUN pip install -r requirements.txt

# GOOD: Multi-stage build (~200MB)
# Stage 1: Build
FROM python:3.12 AS builder
RUN apt-get update && apt-get install -y gcc libpq-dev
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Runtime (no build tools)
FROM python:3.12-slim
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ['gunicorn', 'app:app']
```

**Fix 2: Add .dockerignore**
```
# .dockerignore
.git
__pycache__
*.pyc
node_modules
.env
tests/
docs/
*.md
.vscode/
```

**Fix 3: Optimize layer caching (fixes build time)**
```dockerfile
# BAD: Any code change invalidates pip install cache
COPY . .
RUN pip install -r requirements.txt

# GOOD: Dependencies cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .                              # Code changes don't re-install deps
```

**Expected results:**
| Fix | Image size impact | Build time impact |
|-----|------------------|------------------|
| Multi-stage build | 2GB -> 200-400MB | Minimal |
| .dockerignore | -100-500MB | Faster COPY |
| Layer caching | No change | 10min -> 30s (cached) |
| python:3.12-slim base | -600MB | Minimal |

**Apply these fixes BEFORE considering Alpine.** After these, your image should be 150-300MB and builds should take under a minute."

**Self-evaluation lesson:** When optimizing, find the biggest bottleneck first. A 67MB base image savings is irrelevant when the real problem is 1.9GB of build artifacts in the final image.'''
    ),
    (
        "thinking/auto-selfeval-devops-monitoring-setup",
        r'''A developer asks what monitoring to set up for their new production application. I am about to recommend a comprehensive observability stack. Let me evaluate my draft:

My draft: "Set up the full observability stack: Prometheus for metrics, Grafana for dashboards, Jaeger for distributed tracing, ELK stack (Elasticsearch, Logstash, Kibana) for logging, PagerDuty for alerting, and custom dashboards for business metrics."''',
        r'''<think>
Let me evaluate my monitoring recommendation:

**The context:** New production application, developer asking about monitoring.

**My recommendation:** 6+ tools for full observability.

**Is this appropriate? PROBABLY NOT for a new application.**

**Problem 1: Too much too soon**
- Prometheus + Grafana + Jaeger + ELK + PagerDuty = 5 systems to maintain
- Each requires configuration, storage, and ongoing maintenance
- ELK stack alone needs significant resources (Elasticsearch is memory-hungry)
- This is weeks of setup work before monitoring a single request

**Problem 2: I did not ask about the application**
- Is it a monolith or microservices? (Jaeger is useless for monoliths)
- How many users? (Determines if self-hosted or managed makes sense)
- What is the budget? (Self-hosted is cheap but high maintenance)
- What hosting? (Many platforms include basic monitoring)

**Problem 3: New applications need LESS monitoring**
- A new app has few users and simple architecture
- Start with basics: is it up? Is it fast? Are there errors?
- Add sophisticated monitoring as the system grows

**What a new application actually needs:**
1. Health check endpoint
2. Error tracking (Sentry or similar)
3. Uptime monitoring
4. Application logs (structured)
5. Basic performance metrics

**Verdict:** I recommended a monitoring architecture suited for a large-scale distributed system, not a new application. Rating: 2/10.
</think>

**Self-evaluation: I recommended a monitoring platform that is itself harder to run than the application being monitored. Rating: 2/10.**

**What I should recommend instead:**

"Start with the monitoring essentials and grow from there:

**Level 1: The bare minimum (set up on day 1)**
```python
# 1. Health check endpoint
@app.route('/health')
def health():
    try:
        db.execute('SELECT 1')  # Check database
        return {'status': 'healthy'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 503

# 2. Error tracking (Sentry -- 5 minutes to set up)
import sentry_sdk
sentry_sdk.init(dsn='your-sentry-dsn')
# Now all unhandled exceptions are captured with stack traces,
# user context, and request details. Free tier is generous.

# 3. Structured logging
import logging, json
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 4. Uptime monitoring
# Use UptimeRobot (free) or Better Uptime
# Pings /health every 5 minutes, alerts if down
```

**Level 2: When you have real users (week 2-4)**
```python
# 5. Request timing middleware
import time

@app.before_request
def start_timer():
    g.start_time = time.perf_counter()

@app.after_request
def log_request(response):
    duration = time.perf_counter() - g.start_time
    logger.info(json.dumps({
        'method': request.method,
        'path': request.path,
        'status': response.status_code,
        'duration_ms': round(duration * 1000, 1),
    }))
    return response
```

**Level 3: When you need dashboards (month 2+)**
```
Option A (managed, easy): Datadog, New Relic, or Grafana Cloud
  - No infrastructure to manage
  - Built-in dashboards and alerting
  - $0-25/month for small apps

Option B (self-hosted, cheap): Prometheus + Grafana
  - Only set this up if you have specific needs managed tools do not cover
  - Requires maintenance and storage
```

**Monitoring maturity path:**
| Stage | What to monitor | Tools |
|-------|----------------|-------|
| Launch | Is it up? Any errors? | Health check + Sentry + UptimeRobot |
| First users | Response times, error rates | Request logging + Sentry |
| Growing | Performance trends, capacity | Managed APM (Datadog/New Relic) |
| At scale | Custom metrics, tracing | Prometheus + Grafana + Jaeger |"

**Self-evaluation lesson:** Monitoring should grow with your application. Day-one monitoring should take 30 minutes to set up, not 3 weeks.'''
    ),
    (
        "thinking/auto-selfeval-devops-security-hardening",
        r'''A developer asks me to review their deployment security. I notice they are running their application as root. I am about to only mention running as non-root. Let me evaluate whether my review is thorough enough:

My draft: "Don't run your application as root. Create a non-root user in your Dockerfile and switch to it with the USER directive."''',
        r'''<think>
Let me evaluate my security review:

**The problem:** Application running as root, developer asks for security review.

**My recommendation:** Switch to non-root user.

**Is this correct? Yes, but woefully incomplete for a "security review."**

**What I got right:**
- Running as root is a significant security risk
- Non-root user is an important best practice

**What I completely missed:**

1. **Environment variables / Secrets management**
   - Are secrets hardcoded in the code?
   - Are they in the Docker image?
   - Are they in plain text environment variables?

2. **Network security**
   - Is the database exposed to the internet?
   - Is there a firewall?
   - Is HTTPS configured?

3. **Dependency vulnerabilities**
   - Are there known CVEs in dependencies?
   - Is there a process for updating them?

4. **Application security**
   - SQL injection protection?
   - CSRF protection?
   - Input validation?
   - Authentication/authorization?

5. **Docker security beyond non-root**
   - Using specific image tags (not :latest)?
   - Minimal base image?
   - Read-only filesystem?
   - No unnecessary capabilities?

**Verdict:** I identified one security issue and ignored at least 10 others. A security review that only mentions "don't run as root" gives false confidence. Rating: 3/10.
</think>

**Self-evaluation: Mentioning only non-root is like a home security review that only checks whether the front door is locked. Rating: 3/10.**

**What I should recommend instead:**

"Here is a practical deployment security checklist:

**Category 1: Container security**
```dockerfile
# Run as non-root (you identified this, good):
RUN adduser --disabled-password --gecos '' appuser
USER appuser

# Pin base image version (not :latest):
FROM python:3.12.2-slim  # Specific version, not python:latest

# Read-only filesystem:
# docker run --read-only --tmpfs /tmp myapp

# Drop all Linux capabilities:
# docker run --cap-drop ALL myapp

# No new privileges:
# docker run --security-opt no-new-privileges myapp
```

**Category 2: Secrets management**
```bash
# NEVER do this:
ENV DATABASE_URL=postgresql://user:password@host/db  # In Dockerfile = baked into image!
ENV API_KEY=sk-12345                                  # Anyone with image access sees this

# DO this:
# Pass secrets at runtime, never build time
docker run -e DATABASE_URL='...' myapp
# Or use Docker secrets / cloud provider secret managers
```

**Category 3: Network security**
```
- Database: Only accessible from application server (not internet)
- Redis: Bind to localhost or private network only
- HTTPS: Mandatory for all public endpoints
- CORS: Configure allowed origins explicitly
- Rate limiting: Prevent abuse
```

**Category 4: Dependency security**
```bash
# Scan for known vulnerabilities:
pip-audit                    # Python dependencies
npm audit                    # Node dependencies
docker scout cves myapp      # Container image
trivy image myapp            # Alternative scanner
```

**Category 5: Application security (quick wins)**
```python
# SQL injection: Use parameterized queries (NEVER string formatting)
# CSRF: Enable Django/Flask CSRF protection
# Headers: Set security headers
response.headers['X-Content-Type-Options'] = 'nosniff'
response.headers['X-Frame-Options'] = 'DENY'
response.headers['Strict-Transport-Security'] = 'max-age=31536000'
```

**Priority order:**
1. Secrets not in code or images (most common breach cause)
2. Database not exposed to internet
3. HTTPS everywhere
4. Non-root container
5. Dependency scanning
6. Application security headers

Fix #1-3 immediately. The rest can be addressed over the next sprint."

**Self-evaluation lesson:** A security review must be comprehensive. Identifying one issue and missing ten others is worse than identifying all issues with basic recommendations, because it creates a false sense of security.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
