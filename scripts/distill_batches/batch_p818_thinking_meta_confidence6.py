"""Phase 3C: Metacognition — Detecting Guessing vs Knowing (Part 6)

Training the model to distinguish between responses grounded in solid
knowledge versus responses that are educated guesses or extrapolations.
"""

PAIRS = [
    (
        "thinking/meta-confidence-guess-vs-know-gc",
        r'''What's the default garbage collection algorithm in Java 21? How does it compare to Go's GC in terms of pause times for a 50GB heap?''',
        r'''<think>
Let me carefully separate what I know from what I'd be guessing about.

KNOW with high certainty:
- Java 21 uses G1GC as the default garbage collector
- ZGC and Shenandoah are available as alternatives for low-pause requirements
- Go uses a concurrent, tri-color mark-and-sweep GC
- Go's GC prioritizes low pause times over throughput
- Java's G1GC targets pause time goals (default ~200ms)
- ZGC targets sub-millisecond pauses regardless of heap size

KNOW with medium certainty:
- Java 21 (LTS release) made ZGC generational by default when selected
- Go's GC pauses are typically under 1ms for most workloads
- G1GC with a 50GB heap would likely have pauses in the 100-500ms range
- ZGC with 50GB heap should keep pauses under 1-2ms

GUESSING / EXTRAPOLATING:
- Exact pause time numbers for specific heap sizes — these depend heavily on allocation rate, live object graph complexity, and hardware
- Whether the specific Java 21 G1GC improvements significantly changed 50GB heap behavior
- Go's exact behavior with 50GB heap — Go programs typically don't use heaps this large, and I'm uncertain about GC behavior at that scale

I should present what I know confidently, flag the comparison numbers as approximate, and be clear that real benchmarks are the only way to get accurate numbers.
</think>

I can answer this with varying confidence levels. Let me be explicit about where I'm on solid ground versus extrapolating.

**Java 21 default GC (HIGH confidence):**

G1GC is the default. For a 50GB heap:
```
G1GC: ~100-500ms pauses (depends on allocation rate, live set size)
      Targets -XX:MaxGCPauseMillis=200 by default
      Mixed collections on 50GB heap can exceed this target
```

If pause times matter, Java 21 offers:
```bash
# ZGC (generational by default in Java 21)
java -XX:+UseZGC -Xmx50g MyApp
# Target: sub-millisecond pauses regardless of heap size

# Shenandoah
java -XX:+UseShenandoahGC -Xmx50g MyApp
# Target: pauses proportional to root set, not heap size
```

**Go GC comparison (MEDIUM confidence — I'm partly extrapolating):**

Go's GC typically achieves sub-millisecond pauses, but:
- Go programs rarely use 50GB heaps (the runtime is designed differently)
- At 50GB, Go's GC would consume significant CPU for concurrent marking
- GOGC tuning becomes critical at this scale
- I'm **not confident** about exact Go GC behavior at 50GB — this is outside typical Go usage patterns

**Approximate comparison (flagged as estimates):**

| GC | 50GB Heap Pause | Throughput | My Confidence |
|----|----------------|------------|---------------|
| Java G1GC | 100-500ms | High | Medium-High |
| Java ZGC | <1-2ms | Slightly lower | Medium |
| Go GC | <1ms (typical) | Lower at this heap size | Low-Medium |

**What you should actually do:** Benchmark with your workload. GC behavior depends on allocation rate, object lifetimes, and live set size — not just heap size.'''
    ),
    (
        "thinking/meta-confidence-guess-vs-know-config",
        r'''What's the maximum number of file descriptors a Linux process can open? I'm hitting "too many open files" with our WebSocket server handling 50K connections.''',
        r'''<think>
Let me separate facts from fuzzy knowledge here.

KNOW for certain:
- The "too many open files" error is EMFILE or ENFILE
- Linux has both per-process (soft/hard) and system-wide limits
- The default soft limit is typically 1024 for user processes
- ulimit -n shows/sets the per-process limit
- Each WebSocket connection uses at least one file descriptor
- /proc/sys/fs/file-max controls the system-wide limit

KNOW with high confidence:
- The hard limit can be set in /etc/security/limits.conf
- systemd services use LimitNOFILE in the unit file
- The system-wide maximum depends on RAM (kernel auto-calculates)
- For 50K WebSocket connections, you need at least 50K+ FDs per process
- You also need to tune net.core.somaxconn and TCP settings

MIGHT BE SLIGHTLY OFF on:
- The exact default hard limit (varies by distro — typically 4096 or 65536)
- Whether modern distros have changed the default 1024 soft limit
- Exact systemd defaults for LimitNOFILE (some distros override)

This is a well-trodden ops problem. I'm confident in the solution approach.
</think>

This is squarely in my wheelhouse. I'm confident about the diagnosis and fix.

**The defaults (HIGH confidence):**
```bash
# Per-process soft limit (usually the culprit)
ulimit -Sn    # Typically 1024 (way too low for 50K connections)

# Per-process hard limit
ulimit -Hn    # Typically 4096-65536 depending on distro

# System-wide limit
cat /proc/sys/fs/file-max    # Usually very high (hundreds of thousands)
```

**The fix for 50K WebSocket connections:**

**Step 1: Increase per-process limits**
```bash
# /etc/security/limits.conf (for non-systemd processes)
websocket-user    soft    nofile    100000
websocket-user    hard    nofile    100000
```

```ini
# For systemd services: /etc/systemd/system/websocket.service.d/override.conf
[Service]
LimitNOFILE=100000
```

**Step 2: Increase system-wide limits if needed**
```bash
# /etc/sysctl.d/99-websocket.conf
fs.file-max = 200000
fs.nr_open = 200000

# Network tuning for 50K connections
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.netdev_max_backlog = 65535
```

**Step 3: Verify at runtime**
```bash
# Check current process FD usage
ls /proc/$(pidof your-server)/fd | wc -l

# Check system-wide
cat /proc/sys/fs/file-nr    # allocated  free  maximum
```

**Step 4: Application-level considerations**
```bash
# Also tune your WebSocket server
# - Use epoll (not select/poll) — most modern frameworks do this
# - Ensure connection cleanup on disconnect
# - Monitor for FD leaks: count should correlate with active connections
```

The 1024 default is a historical artifact. For any server handling significant connections, bumping to 100K+ is standard practice.'''
    ),
    (
        "thinking/meta-confidence-guess-vs-know-k8s-limits",
        r'''What happens if I don't set resource limits on my Kubernetes pods? Someone told me the OOMKiller will target them first — is that true?''',
        r'''<think>
Let me check what I actually know vs what might be slightly imprecise.

KNOW for certain:
- Kubernetes has resource requests and limits (CPU and memory)
- Requests affect scheduling — the scheduler places pods on nodes with enough capacity
- Limits enforce caps — a pod exceeding memory limit gets OOM killed
- Without requests, the pod gets "best effort" QoS class
- Without limits, the pod can consume all available node resources

KNOW with high confidence:
- Kubernetes has three QoS classes: Guaranteed, Burstable, BestEffort
- BestEffort pods (no requests or limits set) are evicted first under pressure
- The OOMKiller scores processes — BestEffort pods get higher oom_score_adj
- Guaranteed pods (requests == limits) are the last to be evicted
- The oom_score_adj values: BestEffort=1000, Burstable=2-999, Guaranteed=-997

LESS CERTAIN about:
- The exact oom_score_adj values (I believe BestEffort is 1000 and Guaranteed is -997, but I should flag this as approximate)
- Whether the kubelet eviction manager kicks in before the kernel OOMKiller in all cases
- Exact eviction ordering when multiple Burstable pods compete

The person's claim is essentially correct but slightly simplified. Let me explain the full picture.
</think>

Your colleague is essentially correct, but the full picture is more nuanced. I'm confident in the Kubernetes QoS model here.

**The short answer: Yes, pods without resource settings are targeted first.**

Kubernetes assigns a QoS class based on your resource configuration:

```yaml
# QoS: Guaranteed (LAST to be killed)
# requests == limits for ALL containers
resources:
  requests:
    memory: "256Mi"
    cpu: "500m"
  limits:
    memory: "256Mi"
    cpu: "500m"

# QoS: Burstable (middle priority)
# requests set but != limits, or only partially set
resources:
  requests:
    memory: "128Mi"
  limits:
    memory: "256Mi"

# QoS: BestEffort (FIRST to be killed)
# No requests or limits set at all
# (just omit the resources section entirely)
```

**What actually happens under memory pressure (HIGH confidence):**

```
Node memory pressure detected
        |
        v
Kubelet eviction manager activates
        |
        v
Eviction order:
  1. BestEffort pods exceeding requests (they have none, so always "exceeding")
  2. Burstable pods exceeding their requests
  3. Burstable pods within requests (by priority)
  4. Guaranteed pods (only if node is critically low)
```

**The OOM killer angle (HIGH confidence on concept, MEDIUM on exact values):**

```bash
# Kubernetes sets oom_score_adj on containers:
# BestEffort:  1000  (highest — killed first by kernel OOM killer)
# Burstable:   2-999 (scaled based on request/limit ratio)
# Guaranteed:  -997  (lowest — killed last)
```

**My recommendation:**

Always set at least requests. Limits are debatable for CPU (throttling vs no limit), but memory limits prevent runaway consumption:

```yaml
resources:
  requests:
    memory: "256Mi"    # Scheduling guarantee
    cpu: "100m"        # Scheduling guarantee
  limits:
    memory: "512Mi"    # Hard cap — OOM kill if exceeded
    # cpu: omitted     # Many teams skip CPU limits to avoid throttling
```

**One thing I'm less certain about:** The exact interaction between kubelet eviction (graceful, respects termination grace period) and kernel OOM kill (immediate SIGKILL). In practice, the kubelet usually acts first, but under rapid memory spikes the kernel OOM killer may act directly.'''
    ),
    (
        "thinking/meta-confidence-guess-vs-know-encryption",
        r'''Is AES-256-GCM sufficient for encrypting data at rest in our healthcare application? Our compliance team says we need FIPS 140-2 validation.''',
        r'''<think>
Let me be very careful here — this involves security compliance where being wrong has real consequences.

KNOW with high certainty:
- AES-256-GCM is a strong, widely-used authenticated encryption algorithm
- It provides both confidentiality and integrity
- AES-256 is approved by NIST for protecting classified information
- FIPS 140-2 is a US government standard for cryptographic modules
- FIPS 140-2 validation is about the IMPLEMENTATION, not just the algorithm
- Using AES-256-GCM doesn't mean you're FIPS-validated
- Healthcare = HIPAA, which requires encryption but references NIST guidance

KNOW with high confidence:
- FIPS 140-2 has been superseded by FIPS 140-3 (but 140-2 certs remain valid)
- OpenSSL has a FIPS-validated module (but you must use it in FIPS mode)
- Cloud providers (AWS, Azure, GCP) offer FIPS-validated encryption services
- FIPS validation requires testing by an accredited lab — you can't self-certify
- AES-256-GCM is among the FIPS-approved algorithms

UNCERTAIN about:
- Whether FIPS 140-3 has fully replaced 140-2 in all compliance contexts
- Specific FIPS-validated library version numbers
- Whether your specific compliance requirement is FIPS 140-2 Level 1, 2, 3, or 4
- The exact current state of OpenSSL's FIPS certification

This is a case where I should give solid guidance but strongly recommend involving a compliance specialist. Getting this wrong in healthcare has legal consequences.
</think>

**Important caveat:** This involves regulatory compliance in healthcare. I'm confident in the technical cryptography, but you should verify compliance specifics with a qualified auditor. Getting this wrong has legal and financial consequences.

**AES-256-GCM — technically excellent (HIGH confidence):**

Yes, AES-256-GCM is a strong choice:
- 256-bit key = quantum-resistant for foreseeable future
- GCM mode provides authenticated encryption (confidentiality + integrity)
- NIST-approved, widely reviewed, no known practical attacks
- Suitable for data at rest and in transit

**But FIPS 140-2 is about MORE than the algorithm (HIGH confidence):**

This is the critical distinction:
```
Using AES-256-GCM         ≠  FIPS 140-2 compliant
Using a FIPS-validated    =  FIPS 140-2 compliant
module that implements
AES-256-GCM
```

FIPS 140-2 validates the **cryptographic module** (the software/hardware implementation), not just the algorithm choice. You need:

1. **A FIPS-validated cryptographic library:**
   - OpenSSL FIPS module (check NIST CMVP for current cert status)
   - AWS CloudHSM (FIPS 140-2 Level 3)
   - Azure Key Vault (FIPS 140-2 Level 2)
   - BouncyCastle FIPS (Java)

2. **The module must run in FIPS mode:**
```bash
# OpenSSL FIPS mode — must be explicitly enabled
# Simply linking against OpenSSL is NOT sufficient
```

3. **FIPS 140-2 Level matters:**
   - Level 1: Software module, tested
   - Level 2: Tamper-evidence, role-based auth
   - Level 3: Tamper-resistant, identity-based auth
   - Level 4: Physical security envelope

**For healthcare specifically (MEDIUM confidence — verify with compliance):**

HIPAA doesn't explicitly mandate FIPS 140-2, but:
- The HIPAA Security Rule requires encryption for ePHI
- NIST SP 800-111 recommends FIPS-validated modules for data at rest
- Many healthcare organizations adopt FIPS 140-2 as a safe harbor
- Your compliance team's requirement is reasonable and common

**Actionable steps:**
1. Use a FIPS-validated module (check NIST CMVP list: csrc.nist.gov)
2. Confirm the required FIPS level with your compliance team
3. Document your encryption approach for audit trails
4. Consider cloud KMS services — they handle FIPS validation for you

**I strongly recommend** engaging a compliance specialist to validate your specific regulatory requirements rather than relying solely on technical guidance.'''
    ),
    (
        "thinking/meta-confidence-guess-vs-know-caching",
        r'''We're seeing 2-second response times on our product listing API. Someone suggested adding Redis caching. Before I do that, how can I tell if caching is actually the right solution versus the query being slow?''',
        r'''<think>
This is a great diagnostic question and I'm confident in the methodology here.

KNOW for certain:
- 2-second API response time is almost certainly too slow for a product listing
- The cause could be: slow DB query, missing index, N+1 queries, network latency, serialization, or application code
- Adding caching without understanding the root cause often masks problems
- You should profile before optimizing

KNOW with high confidence:
- Tools for diagnosing: EXPLAIN ANALYZE for SQL, APM tools, request timing breakdown
- Common causes for slow product listings: missing indexes, N+1 queries (fetching related data), large result sets without pagination
- Redis caching is appropriate when: data is read-heavy, changes infrequently, and the underlying query is inherently expensive
- Redis caching is NOT appropriate when: the query should be fast but isn't (fix the query instead), data changes frequently, or cache invalidation complexity outweighs benefits

This is bread-and-butter backend performance work. I can give a strong, structured diagnostic approach.
</think>

Excellent instinct to diagnose before reaching for caching. I'm very confident in this diagnostic approach — it's fundamental backend performance work.

**Step 1: Identify WHERE the 2 seconds is spent (5 minutes)**

Add timing to your request lifecycle:
```python
import time

@app.get("/products")
async def list_products():
    t0 = time.perf_counter()

    # Database query
    t1 = time.perf_counter()
    products = await db.fetch_products(filters)
    t2 = time.perf_counter()

    # Serialization
    result = serialize(products)
    t3 = time.perf_counter()

    print(f"DB: {t2-t1:.3f}s | Serialize: {t3-t2:.3f}s | Total: {t3-t0:.3f}s")
    return result
```

Possible results and what they mean:
```
DB: 1.8s | Serialize: 0.2s → Fix the query (not caching)
DB: 0.1s | Serialize: 1.9s → Fix serialization (not caching)
DB: 0.05s | Serialize: 0.05s | Total: 2.0s → N+1 queries or middleware issue
```

**Step 2: If the database is slow, diagnose WHY**

```sql
-- Run your query with EXPLAIN ANALYZE
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT p.*, c.name as category_name
FROM products p
JOIN categories c ON p.category_id = c.id
WHERE p.active = true
ORDER BY p.created_at DESC
LIMIT 50;

-- Look for:
-- Seq Scan on products → Missing index
-- Nested Loop with high row counts → N+1 or bad join
-- Sort with high cost → Missing index on ORDER BY column
```

**Step 3: Decision tree — cache or fix?**

```
Is the query slow because of a missing index?
  → Add the index (5 minutes, no caching needed)

Is it N+1 queries (many small queries)?
  → Add eager loading / JOIN (fix the code)

Is the query inherently expensive (complex aggregation, full-text search)?
  → Caching IS appropriate here

Is the data set huge and pagination is missing?
  → Add pagination (LIMIT/OFFSET or cursor-based)

Is the query fast but called 100x per page load?
  → Caching OR batching is appropriate
```

**When Redis caching IS the right answer:**
- Read-to-write ratio is 100:1 or higher
- The query is inherently expensive even with proper indexes
- Data staleness of 30-300 seconds is acceptable
- You have a clear cache invalidation strategy

**When caching is a bandaid:**
- Missing database index (fix takes 1 minute)
- N+1 queries (fix takes 30 minutes)
- No pagination on a 100K row table
- Slow serialization of unnecessary fields

Fix the root cause first. Add caching for genuinely expensive operations.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
