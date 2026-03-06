"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 9)

Final 3D pairs to reach 50 total.
"""

PAIRS = [
    (
        "thinking/meta-confidence-underdefined-database-choice",
        r'''What database should I use for my project?''',
        r'''<think>
This is the most underdefined question possible for database selection. I have zero information about the project.

What I'm confident about:
- PostgreSQL is the safest default for most web applications
- The right database depends entirely on the use case
- Without knowing what they're building, any specific recommendation is a guess

What I definitely don't know:
- What they're building
- Data model (relational? document? graph? time-series?)
- Scale expectations
- Team expertise
- Budget constraints
- Hosting environment
</think>

**I can't recommend a database without knowing what you're building.** But here's a decision framework:

**If you tell me nothing else:** PostgreSQL. It handles 90% of use cases, is free, battle-tested, and has excellent tooling.

**If you tell me more:**

| Your use case | Best fit | Why |
|--------------|---------|-----|
| Web app (CRUD, users, orders) | PostgreSQL | Relational data, ACID transactions |
| Document storage (varying schemas) | MongoDB | Flexible schema, nested objects |
| Key-value cache | Redis | Sub-ms reads, in-memory |
| Search | Elasticsearch / Meilisearch | Full-text, fuzzy matching |
| Time-series (metrics, IoT) | TimescaleDB / InfluxDB | Optimized for time-ordered data |
| Graph relationships | Neo4j | Relationship traversal queries |
| Simple embedded | SQLite | Zero config, single file |

**Questions that would help me recommend:**
1. What kind of data? (Users/orders? Documents? Metrics? Relationships?)
2. How much data? (MBs? GBs? TBs?)
3. Read-heavy or write-heavy?
4. Need transactions? (Financial data: yes. Logs: probably not)
5. Team experience? (Go with what the team knows)

**My honest default:** If you're unsure, start with PostgreSQL. You can always add Redis for caching or Elasticsearch for search later. Starting with PostgreSQL is almost never wrong.'''
    ),
    (
        "thinking/meta-confidence-compatibility-docker",
        r'''Will my Docker container built on my Mac M1 work on our Linux production servers?''',
        r'''<think>
I'm fairly confident about the general answer — this is a well-known issue.

What I'm confident about:
- Mac M1/M2/M3 uses ARM architecture (aarch64)
- Most Linux production servers use x86_64 (AMD64) architecture
- Docker images are architecture-specific by default
- An ARM image will NOT run on x86_64 without emulation (and vice versa)
- Docker buildx supports multi-architecture builds

What I'm uncertain about:
- Whether their production servers are actually x86_64 (they might be ARM — AWS Graviton, for example)
- Whether their Docker build process already handles multi-arch
- Whether all their dependencies have both ARM and x86_64 variants
- Performance of QEMU emulation for development
</think>

**Probably not out of the box.** I'm fairly confident about this:

- Mac M1/M2/M3 = ARM architecture (aarch64)
- Most Linux servers = x86_64 (AMD64)
- Docker images built on M1 are ARM images → won't run on x86_64

**Fix — build for the target platform:**
```bash
# Build specifically for x86_64 (Linux servers)
docker buildx build --platform linux/amd64 -t myapp .

# Or build multi-architecture:
docker buildx build --platform linux/amd64,linux/arm64 -t myapp .
```

**In your Dockerfile or CI/CD:**
```yaml
# GitHub Actions example:
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    platforms: linux/amd64
    push: true
    tags: myapp:latest
```

**What I'm uncertain about:**
- Whether your production servers might actually be ARM (AWS Graviton instances are ARM and increasingly popular)
- Whether all your dependencies have x86_64 packages (some Python packages with C extensions might need special handling)
- Whether `--platform linux/amd64` on M1 will build successfully for all your dependencies

**Potential issues with cross-platform builds on M1:**
- Builds are slower (uses QEMU emulation)
- Some packages may fail to compile for x86_64 on ARM
- Native ARM packages won't be used → need x86_64 variants

**Verification:**
```bash
# Check what platform your image is built for:
docker inspect myapp | grep Architecture
# Should show "amd64" for x86_64 servers

# Test locally with platform emulation:
docker run --platform linux/amd64 myapp
```

Check your production server architecture first: `uname -m` on the server will tell you if it's `x86_64` or `aarch64`.'''
    ),
    (
        "thinking/meta-confidence-ambiguous-bug-intermittent-db",
        r'''We get occasional "connection refused" errors from our PostgreSQL database. It happens maybe 5 times a day out of 100,000 requests. The database seems healthy otherwise. What's wrong?''',
        r'''<think>
I'm fairly confident about the category of issue but uncertain about the specific cause.

What I'm confident about:
- "Connection refused" means the TCP connection to PostgreSQL was rejected
- 5/100K (0.005%) is a very low error rate — suggests a transient issue, not a fundamental misconfiguration
- Common causes: connection pool exhaustion, max_connections limit hit, brief network blips, PostgreSQL restarting for autovacuum

What I'm uncertain about:
- Whether they're using connection pooling (PgBouncer, SQLAlchemy pool)
- The PostgreSQL max_connections setting vs actual usage
- Whether it correlates with traffic spikes
- Whether it's actually "connection refused" or "connection timed out" (different causes)
</think>

**I'm fairly confident this is connection pool/limit related, but need diagnostics to confirm.**

**Most likely causes (ranked):**

| Cause | Probability | Check |
|-------|------------|-------|
| Connection pool exhaustion | High | Check pool size vs peak usage |
| PostgreSQL max_connections hit | High | `SHOW max_connections` vs active |
| Brief network blips | Medium | Check network logs/monitoring |
| PostgreSQL maintenance restart | Low | Check PostgreSQL logs |

**Diagnostic steps:**

```sql
-- 1. Check max connections vs current usage
SHOW max_connections;  -- Default is 100
SELECT count(*) FROM pg_stat_activity;  -- Active connections

-- 2. Check connection history at peak times
SELECT count(*), state
FROM pg_stat_activity
GROUP BY state;
-- If 'idle' connections are near max_connections, that's the issue
```

```python
# 3. Check your connection pool settings
# SQLAlchemy default pool_size = 5, max_overflow = 10
engine = create_engine(DATABASE_URL,
    pool_size=5,       # Is this enough?
    max_overflow=10,   # Total max = 15 connections
    pool_timeout=30,   # How long to wait for a connection
    pool_recycle=1800  # Recycle connections every 30 min
)
```

**Most common fix — adjust pool settings:**
```python
# If you have 4 gunicorn workers × 5 pool_size = 20 connections
# Plus 4 × 10 max_overflow = 60 connections at peak
# If max_connections = 100, this uses up to 60, leaving headroom

# If pool is too small, increase:
engine = create_engine(DATABASE_URL,
    pool_size=10,        # More persistent connections
    max_overflow=20,     # More burst capacity
    pool_pre_ping=True,  # Check if connection is alive before using
)
```

**If max_connections is the bottleneck:**
```bash
# Consider PgBouncer for connection pooling
# PgBouncer sits between app and PostgreSQL
# Manages a pool of connections efficiently
```

**What I'm uncertain about:**
- Whether it's your app's pool, PostgreSQL's max_connections, or the network
- Whether the errors correlate with specific times of day (traffic patterns)
- Whether other services also connect to the same PostgreSQL instance

Start with the `pg_stat_activity` check — it'll immediately show if you're near the connection limit.'''
    ),
    (
        "thinking/meta-confidence-scale-without-numbers-api",
        r'''Is REST good enough for our API, or do we need GraphQL or gRPC for better performance?''',
        r'''<think>
I can't answer this without understanding the actual performance requirements and bottlenecks.

What I'm confident about:
- REST, GraphQL, and gRPC are all capable of handling very high traffic
- The protocol itself is rarely the performance bottleneck
- The choice between them is about developer experience and use case, not raw speed
- gRPC IS faster than REST for high-throughput service-to-service communication

What I'm uncertain about:
- Their actual traffic volume and latency requirements
- Whether they're experiencing performance issues now
- The communication pattern (client→server? service→service?)
</think>

**I can't determine if REST is "good enough" without knowing your traffic and requirements.** But I'm fairly confident: **REST is not your performance bottleneck.**

**What I'm confident about:**

REST handles massive scale:
- Twitter API: REST, millions of requests/second
- GitHub API: REST, serves the entire developer ecosystem
- Stripe API: REST, processes billions of dollars

**Performance comparison (rough):**

| Protocol | Latency overhead | Best for |
|----------|-----------------|---------|
| REST (JSON) | ~1-5ms serialization | Public APIs, web clients |
| GraphQL | ~2-10ms query parsing | Mobile apps, flexible data needs |
| gRPC (protobuf) | ~0.1-1ms serialization | Service-to-service, low latency |

**When each protocol matters:**

REST is fine when:
- Client-server communication (web/mobile → backend)
- Traffic < 10,000 req/s per server (most applications)
- Human-readable debugging matters

gRPC is better when:
- Service-to-service communication (microservices)
- Need streaming (bidirectional)
- Latency-critical (every millisecond matters)
- Schema enforcement is important (protobuf contracts)

GraphQL is better when:
- Multiple clients need different data shapes
- Mobile bandwidth is a concern (fetch only needed fields)
- Complex nested data relationships

**What I'm uncertain about:**
- Your specific performance requirements
- Your current bottleneck (it's almost certainly not the REST protocol)
- Whether you've actually measured REST being too slow

**My recommendation:** Keep REST unless you can identify a specific problem it causes. If you find REST is a bottleneck (unlikely), profile first. The fix is usually optimizing database queries, adding caching, or scaling infrastructure — not changing protocols.'''
    ),
    (
        "thinking/meta-confidence-emerging-wasm",
        r'''Should I write my next backend in Rust compiled to WebAssembly for maximum performance?''',
        r'''<think>
I'm fairly confident this is misguided but should explain why without being dismissive.

What I'm confident about:
- WebAssembly (WASM) is designed for running in BROWSERS, not as a backend runtime
- Rust IS very fast for backends, but you'd run it natively, not through WASM
- WASM on the server (via WASI/Wasmtime) exists but is immature for production backends
- The performance benefit of WASM over native code is negative (WASM adds overhead)

What I'm uncertain about:
- Whether WASI ecosystem has matured enough for specific use cases
- Whether the user means edge computing (Cloudflare Workers use WASM) — that's a legitimate use case
- Whether future WASM developments will make server-side WASM competitive
</think>

**This mixes up two things.** Let me clarify what I'm confident about:

**WASM for backends doesn't make sense** (in most cases):
```
Native Rust binary: Fast
Rust → WASM → WASM runtime: Slower (WASM adds overhead, doesn't remove it)
```

WebAssembly adds a layer of indirection. For backends, running Rust natively is FASTER than running Rust through WASM.

**If you want maximum backend performance:**
```
Just compile Rust to a native binary:
cargo build --release
./my-server  # Runs natively, maximum speed
```

**When server-side WASM IS legitimate:**
- **Edge computing**: Cloudflare Workers, Fastly Compute use WASM for sandboxed edge functions — this is a valid use case
- **Plugin systems**: Safely run untrusted code (WASM provides sandboxing)
- **Portability**: Deploy same binary across different architectures

**What I'm uncertain about:**
- Whether WASI (WebAssembly System Interface) will mature to make server-side WASM competitive in the future
- Whether edge computing (Cloudflare Workers) is what you actually need
- The current state of WASM server frameworks (Spin, Fermyon) — they exist but I'm unsure about production readiness

**My confident recommendation:**
- Want fast backend? → Rust (native), Go, or optimize your Python/Node
- Want browser interop? → WASM is perfect (run Rust/C++ in the browser)
- Want edge computing? → WASM on Cloudflare Workers is legitimate
- Want a general backend? → Don't use WASM — run native code

The performance hierarchy for backends:
```
Rust/C++ (native) > Go > Java/C# > Node.js > Python
Rust via WASM < Rust native (WASM adds overhead)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
