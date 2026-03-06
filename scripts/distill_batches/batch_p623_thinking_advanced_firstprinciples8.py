"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 8/8)"""

PAIRS = [
    (
        "thinking/firstprinciples-why-dns-exists",
        "Why does DNS exist? Can you explain it from scratch? I know it 'translates domain names to IP addresses' but I want to understand WHY it's designed the way it is.",
        r'''<think>
DNS from first principles. Let me derive it from the root problem.

**Step 1: The fundamental problem**
Computers communicate using IP addresses (e.g., 93.184.216.34). Humans can't remember these. We need a way to map human-friendly names to machine-friendly numbers.

**Step 2: Simplest solution — a local file**
The original solution (before DNS): `/etc/hosts` — a file mapping names to IPs.
```
93.184.216.34    example.com
142.250.80.46    google.com
```
Problem: how does everyone get the same file? In the early internet (1970s), Stanford Research Institute maintained ONE file that everyone downloaded. When you added a server, you called SRI and they updated the file.

This worked for hundreds of hosts. It doesn't work for billions.

**Step 3: Why a central file fails**
- Single point of failure (SRI goes down = no name resolution)
- Doesn't scale (billions of entries in one file)
- Update latency (changes take time to propagate)
- Name conflicts (who owns "mail"?)

**Step 4: The DNS solution — distributed hierarchical database**
Instead of one file, split the data into zones managed by different authorities:
- `.com` is managed by Verisign
- `example.com` is managed by whoever registered it
- `mail.example.com` is managed by example.com's admins

Each level only knows about its direct children. To resolve `www.example.com`:
1. Ask root: "Who knows about .com?" → root says "Ask Verisign"
2. Ask Verisign: "Who knows about example.com?" → Verisign says "Ask ns1.example.com"
3. Ask ns1.example.com: "What's the IP for www.example.com?" → "93.184.216.34"

**Step 5: Caching — make it fast**
Doing 3+ lookups for every request is slow. Solution: cache results with TTL.
First lookup: 50-200ms (full resolution chain)
Cached lookup: 0ms (already known)

This is why DNS has TTL (Time To Live) — cached answers expire after a set time (typically 300-86400 seconds).

**Step 6: Redundancy — make it reliable**
Each zone has multiple nameservers (typically 2-13). If one fails, others answer.
Root DNS has 13 logical servers, each is actually a cluster of hundreds of machines.

So DNS is: hierarchical (splits authority), distributed (no single point of failure), cached (fast after first lookup), and redundant (multiple servers per zone).
</think>

Let me derive DNS from the problem it solves, step by step.

## Step 1: The Root Problem

```
Computers communicate using IP addresses:
  93.184.216.34 = example.com
  142.250.80.46 = google.com

Humans need friendly names.
We need: name → number translation.
```

## Step 2: The First Solution (A Single File)

```
Before DNS existed (1970s-1983):

  /etc/hosts — a text file on every computer:
    93.184.216.34    example.com
    142.250.80.46    google.com
    10.0.0.1         mail-server

  Maintained by Stanford Research Institute (SRI).
  When you added a server to the internet:
    1. Call SRI on the phone
    2. They add your entry to the HOSTS.TXT file
    3. Every computer downloads the updated file periodically

  This worked for ~500 hosts on ARPANET.
```

## Step 3: Why the Single File Fails

```
Scale:
  1983: ~500 hosts    → one file works
  1993: ~2M hosts     → file is massive, downloads take forever
  2024: ~600M domains → impossible in one file

Single point of failure:
  SRI goes down → nobody can resolve names → internet breaks

Update speed:
  Add a new server → call SRI → they update → everyone re-downloads
  Could take DAYS for changes to propagate

Name conflicts:
  You want "mail"? So does everyone else.
  Who decides who gets what name? SRI can't arbitrate billions of claims.
```

## Step 4: The DNS Solution — Hierarchical Distribution

```
KEY INSIGHT: split the namespace into a TREE.
Each branch is managed by a different organization.

                    . (root)
                   / \
              .com    .org    .uk
              / \        \
        google  example   wikipedia
        / \       |
      www mail   www

Each level only knows about its DIRECT CHILDREN:
  Root servers know: who manages .com, .org, .uk, ...
  .com servers know: who manages google.com, example.com, ...
  example.com servers know: the IPs for www, mail, api, ...

No single authority manages everything.
Each domain owner manages their own zone.
```

## Step 5: How Resolution Works (The Lookup Chain)

```
You type: www.example.com
Your computer doesn't know the IP. Here's what happens:

  Step 1: Ask ROOT server
          "Who manages .com?"
          Root: "Ask Verisign at 192.41.162.30"

  Step 2: Ask .COM server (Verisign)
          "Who manages example.com?"
          Verisign: "Ask ns1.example.com at 93.184.216.34"

  Step 3: Ask example.com's nameserver
          "What's the IP for www.example.com?"
          ns1.example.com: "93.184.216.34, TTL 3600"

  Step 4: Your computer connects to 93.184.216.34

  Total: 3 network requests, ~100ms

But wait — this happens for EVERY website visit?
```

## Step 6: Caching — Make It Fast

```
Without caching: 3 lookups per domain × every page load = slow

With caching (TTL = Time To Live):
  First visit to example.com:
    Full resolution: 100ms → cache result for 3600 seconds

  Next 3600 seconds:
    "www.example.com? I already know: 93.184.216.34"
    Resolution time: 0ms (cached)

  After 3600 seconds:
    Cache expires → do full resolution again

Caching happens at multiple levels:
  Your browser:       caches for the TTL
  Your OS:            caches (so all apps benefit)
  Your router:        might cache
  Your ISP's DNS:     caches (so all ISP customers benefit)

  One person at your ISP visits google.com
  → ISP caches the result
  → Next million requests from ISP customers: instant
```

## Step 7: Redundancy — Make It Reliable

```
What if a nameserver goes down?

Every zone has MULTIPLE nameservers:
  example.com:
    ns1.example.com (primary)
    ns2.example.com (secondary, different data center)

  Root DNS:
    13 root servers (a.root-servers.net through m.root-servers.net)
    Each is actually a CLUSTER of hundreds of machines worldwide
    Total: ~1,500+ root server instances globally

  If one fails → query goes to another
  DNS is one of the most resilient systems ever built.
```

## Why DNS Is Designed This Way (Summary)

```
PROBLEM                  DNS SOLUTION              ALTERNATIVE THAT FAILS
──────────────────────────────────────────────────────────────────────────
Humans can't remember     Name → IP mapping         Everyone memorizes IPs
  IP addresses

Billions of domains       Hierarchical tree          One giant file

Single point of failure   Distributed authorities    One central server

Slow lookups              TTL-based caching          Query every time

Name ownership            Zone delegation            Central authority
                          (you manage your domain)   decides everything

Reliability               Multiple nameservers       One server per domain
                          per zone
```

```
DNS works because it's:
  Hierarchical:   splits the problem into manageable pieces
  Distributed:    no single point of failure or control
  Cached:         fast after first lookup
  Redundant:      multiple servers per zone
  Delegated:      each domain owner manages their own records

These same principles appear in many distributed systems:
  File systems (directory trees)
  Package registries (npm, PyPI)
  Certificate authorities (PKI chain of trust)
  CDNs (edge caching with TTL)
```'''
    ),
    (
        "thinking/firstprinciples-why-environment-variables",
        "Why do we use environment variables for configuration? Why not just put everything in a config file? I keep seeing 'use env vars!' but nobody explains why they're better.",
        r'''<think>
Environment variables from first principles. Why not just config files?

**The root problem: configuration changes between environments**
Your app needs to know:
- Database URL (different in dev/staging/prod)
- API keys (different per environment, secret)
- Feature flags (different per deployment)
- Log levels (verbose in dev, minimal in prod)

**Why not config files?**
Config files work but have specific problems:

1. **Secrets in code**: If config.json has your database password, and it's in git, anyone with repo access has your production credentials. Even in a private repo, git history is forever.

2. **Environment coupling**: You need different config files per environment:
   - config.dev.json
   - config.staging.json
   - config.production.json
   Which one does the app load? How does it know which environment it's in?

3. **Deployment complexity**: Config files need to be deployed WITH the code. If config changes, you need to redeploy. Environment variables can be changed without redeployment.

**Why environment variables solve these:**

1. **Separation of config from code**: The Twelve-Factor App principle. Code is the same everywhere; only the configuration changes. Code goes in git; config goes in the environment.

2. **No secrets in code**: `DATABASE_URL` is set in the environment, not in a file that gets committed. The secret never touches git.

3. **Environment detection is implicit**: The app doesn't need to know "am I in production?" It just reads DATABASE_URL and gets whatever URL is set for this environment.

4. **Platform support**: Every platform (Heroku, AWS, Docker, K8s, Vercel) supports setting env vars. Not every platform supports custom config file locations.

**Where env vars fall short:**
- Complex/nested config (env vars are flat key-value strings)
- Many config values (50+ env vars gets unwieldy)
- Type safety (everything is a string)
- Documentation (no schema, no comments)

**The practical answer:**
Use env vars for secrets and environment-specific values.
Use config files (loaded from code, with env var overrides) for complex application settings.
</think>

Let me derive why environment variables exist by starting from the problem they solve.

## The Root Problem: Same Code, Different Environments

```
Your app runs in 3+ places:
  Development:  localhost database, verbose logging, test API keys
  Staging:      staging database, moderate logging, test API keys
  Production:   production database, minimal logging, REAL API keys

The CODE is identical. The CONFIGURATION differs.
Where does the configuration live?
```

## Option 1: Config Files (The Obvious Approach)

```python
# config.json
{
    "database_url": "postgres://prod-server:5432/myapp",
    "api_key": "sk_live_abc123_REAL_MONEY",
    "log_level": "error"
}

# app.py
import json
config = json.load(open("config.json"))
db = connect(config["database_url"])
```

```
Problems:

1. SECRETS IN GIT:
   config.json is in the repo → everyone with repo access
   has your production database password and API keys.
   Git history is forever — even if you delete it later.

2. WHICH CONFIG FILE?
   You need: config.dev.json, config.staging.json, config.prod.json
   How does the app know which to load?
   You need... an environment variable to tell it which config file to use.
   (Circular dependency!)

3. CONFIG CHANGE = REDEPLOY:
   Change log level from "error" to "debug"?
   Edit file → commit → deploy. Just to change one setting.

4. PLATFORM INCOMPATIBILITY:
   Docker: where does config.json go inside the container?
   Heroku: no file system access for config files
   Lambda: read-only file system
   Kubernetes: need to mount ConfigMaps as files (extra complexity)
```

## Option 2: Environment Variables (The Standard)

```python
import os

# App reads config from environment — doesn't care WHERE it's set
db = connect(os.environ["DATABASE_URL"])
api_key = os.environ["API_KEY"]
log_level = os.environ.get("LOG_LEVEL", "info")  # Default if not set
```

```
Each environment sets its own values:

DEVELOPMENT (your laptop):
  export DATABASE_URL="postgres://localhost/myapp_dev"
  export API_KEY="sk_test_fake123"
  export LOG_LEVEL="debug"

PRODUCTION (cloud platform):
  DATABASE_URL="postgres://prod-server/myapp_prod"   # Set in platform dashboard
  API_KEY="sk_live_abc123_REAL_MONEY"                 # Set in secrets manager
  LOG_LEVEL="error"                                   # Set in deployment config

Same code. Different environment. Different config.
The code never needs to know "am I in production?"
```

## Why Environment Variables Won

```
1. SECRETS NEVER TOUCH CODE:
   Git history: clean. No passwords, no API keys.
   Code reviews: no risk of leaking credentials.
   Repository access ≠ production credentials.

2. UNIVERSAL PLATFORM SUPPORT:
   Heroku:      heroku config:set DATABASE_URL=...
   Docker:      docker run -e DATABASE_URL=...
   Kubernetes:  env: [{name: DATABASE_URL, value: ...}]
   AWS Lambda:  Environment variables in function config
   Vercel:      Project settings → Environment Variables
   Linux:       export DATABASE_URL=...

   EVERY platform supports env vars. Not every platform supports
   your custom config file format.

3. NO REDEPLOY FOR CONFIG CHANGES:
   Change log level → update env var → restart service
   No code change, no git commit, no CI/CD pipeline.

4. THE TWELVE-FACTOR APP PRINCIPLE:
   "Store config in the environment"
   Code and config are separate concerns.
   Code goes in git. Config goes in the environment.
```

## Where Env Vars Fall Short (And What to Do)

```python
# PROBLEM: Complex/nested configuration
# Env vars are flat strings — no nesting, no arrays

# ❌ Awkward as env vars:
# APP_DB_PRIMARY_HOST=db1.example.com
# APP_DB_PRIMARY_PORT=5432
# APP_DB_REPLICA_HOST=db2.example.com
# APP_DB_REPLICA_PORT=5432

# ✅ Solution: use env vars for secrets + config files for structure
# config.yaml (safe to commit — no secrets!)
database:
  primary:
    host: ${DATABASE_PRIMARY_HOST}   # Resolved from env var
    port: 5432
  replica:
    host: ${DATABASE_REPLICA_HOST}   # Resolved from env var
    port: 5432

logging:
  level: ${LOG_LEVEL:-info}          # Default: info
  format: json
  output:
    - stdout
    - file: /var/log/app.log


# PROBLEM: Type safety (env vars are always strings)
# "true", "TRUE", "1", "yes" — which is boolean true?

# ✅ Solution: parse and validate at startup
import os

def get_bool(key, default=False):
    return os.environ.get(key, str(default)).lower() in ('true', '1', 'yes')

def get_int(key, default=0):
    return int(os.environ.get(key, default))

DEBUG = get_bool("DEBUG")                # True/False
MAX_RETRIES = get_int("MAX_RETRIES", 3)  # int
```

## The Practical Rule

```
USE ENV VARS FOR:
  ✓ Secrets (passwords, API keys, tokens)
  ✓ Environment-specific values (database URLs, service endpoints)
  ✓ Feature flags that change per deployment
  ✓ Anything that differs between dev/staging/production

USE CONFIG FILES FOR:
  ✓ Complex/nested application settings
  ✓ Default values and documentation
  ✓ Settings that are the SAME across all environments
  ✓ Schema-validated configuration

BEST PRACTICE: Config files with env var overrides
  Config file provides structure + defaults
  Env vars override secrets and environment-specific values
  Config file is safe to commit (no secrets)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
