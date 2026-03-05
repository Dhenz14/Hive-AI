"""Cilium eBPF networking and TiDB distributed SQL."""

PAIRS = [
    (
        "devops/cilium-networking",
        "Show Cilium eBPF-based Kubernetes networking: network policies, service mesh, observability with Hubble, and cluster mesh.",
        '''Cilium eBPF networking for Kubernetes:

```yaml
# --- Install Cilium (Helm) ---
# helm repo add cilium https://helm.cilium.io/
# helm install cilium cilium/cilium --namespace kube-system \
#   --set kubeProxyReplacement=true \
#   --set hubble.enabled=true \
#   --set hubble.relay.enabled=true \
#   --set hubble.ui.enabled=true


# === Network Policies (L3/L4 + L7) ===

# --- L3/L4: Allow frontend -> API on port 8080 ---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: api-ingress
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: api-server
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: frontend
        - matchLabels:
            app: mobile-gateway
      toPorts:
        - ports:
            - port: "8080"
              protocol: TCP
    - fromEndpoints:
        - matchLabels:
            app: prometheus
      toPorts:
        - ports:
            - port: "9090"
              protocol: TCP

---
# --- L7: HTTP-aware policy (filter by path/method) ---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: api-l7-policy
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: api-server
  ingress:
    - fromEndpoints:
        - matchLabels:
            app: frontend
      toPorts:
        - ports:
            - port: "8080"
              protocol: TCP
          rules:
            http:
              - method: GET
                path: "/api/v1/products.*"
              - method: POST
                path: "/api/v1/orders"
                headers:
                  - 'Content-Type: application/json'
              # Deny everything else (DELETE, PUT to /admin, etc.)

---
# --- DNS-based egress policy ---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: allow-external-apis
  namespace: production
spec:
  endpointSelector:
    matchLabels:
      app: payment-service
  egress:
    - toFQDNs:
        - matchName: "api.stripe.com"
        - matchName: "api.paypal.com"
      toPorts:
        - ports:
            - port: "443"
              protocol: TCP
    - toEndpoints:
        - matchLabels:
            "k8s:io.kubernetes.pod.namespace": kube-system
            "k8s:k8s-app": kube-dns
      toPorts:
        - ports:
            - port: "53"
              protocol: ANY
          rules:
            dns:
              - matchPattern: "*.stripe.com"
              - matchPattern: "*.paypal.com"

---
# --- Cluster-wide default deny ---
apiVersion: cilium.io/v2
kind: CiliumClusterwideNetworkPolicy
metadata:
  name: default-deny
spec:
  endpointSelector: {}
  ingress:
    - fromEndpoints:
        - {}  # Allow intra-cluster only, deny external by default
  egress:
    - toEndpoints:
        - {}
    - toEntities:
        - kube-apiserver  # Always allow API server access


# === Hubble Observability ===

# --- View flows ---
# hubble observe --namespace production --protocol http
# hubble observe --to-label app=api-server --verdict DROPPED
# hubble observe --from-pod production/frontend-abc123 -f

# --- Hubble metrics (Prometheus) ---
# cilium_forward_count_total
# cilium_drop_count_total
# cilium_policy_verdict
# hubble_flows_processed_total


# === Service Mesh (sidecar-free) ===

---
# Mutual TLS without sidecars — eBPF handles encryption in-kernel
apiVersion: cilium.io/v2alpha1
kind: CiliumL2AnnouncementPolicy
metadata:
  name: l2-policy
spec:
  interfaces:
    - eth0
  loadBalancerIPs: true

---
# Traffic management: weighted routing
apiVersion: cilium.io/v2
kind: CiliumEnvoyConfig
metadata:
  name: api-traffic-split
  namespace: production
spec:
  services:
    - name: api-server
      namespace: production
  resources:
    - "@type": type.googleapis.com/envoy.config.route.v3.RouteConfiguration
      name: api-routes
      virtual_hosts:
        - name: api
          domains: ["*"]
          routes:
            - match:
                prefix: "/"
              route:
                weighted_clusters:
                  clusters:
                    - name: "production/api-server-v1"
                      weight: 90
                    - name: "production/api-server-v2"
                      weight: 10


# === Cluster Mesh (multi-cluster) ===

---
# Enable cluster mesh on both clusters:
# cilium clustermesh enable --context cluster1
# cilium clustermesh enable --context cluster2
# cilium clustermesh connect --context cluster1 --destination-context cluster2

# Global service: accessible from any cluster
apiVersion: v1
kind: Service
metadata:
  name: shared-cache
  namespace: production
  annotations:
    io.cilium/global-service: "true"        # Available across clusters
    io.cilium/shared-service: "true"        # Load-balance across clusters
    io.cilium/service-affinity: "local"     # Prefer local cluster
spec:
  selector:
    app: redis
  ports:
    - port: 6379
```

Cilium advantages over traditional CNI:
1. **L7 policies** — HTTP/gRPC-aware filtering (path, method, headers) without sidecars
2. **DNS-based egress** — allow traffic to specific FQDNs, not just IPs (handles dynamic DNS)
3. **No kube-proxy** — eBPF replaces iptables for service routing (faster, scalable)
4. **Hubble observability** — real-time flow visibility with dropped packet tracing
5. **Cluster mesh** — multi-cluster service discovery and load balancing with locality awareness'''
    ),
    (
        "database/tidb-distributed-sql",
        "Show TiDB distributed SQL patterns: cluster architecture, horizontal scaling, placement rules, and migration from MySQL.",
        '''TiDB distributed SQL database patterns:

```sql
-- === TiDB Architecture ===
-- TiDB = MySQL-compatible distributed SQL
-- Components: TiDB (SQL layer) + TiKV (storage) + PD (placement driver)
--
-- TiDB Server (stateless, scales horizontally)
--   ↓ SQL parsing, optimization, execution
-- TiKV (distributed key-value, Raft consensus)
--   ↓ MVCC, transactions, data storage
-- PD (Placement Driver)
--   ↓ Metadata, scheduling, timestamp oracle


-- === Horizontal Scaling ===

-- TiDB auto-shards data into ~96MB "Regions"
-- Each Region has 3 replicas via Raft consensus
-- PD automatically rebalances Regions across TiKV nodes

-- Check cluster topology
SELECT * FROM information_schema.tikv_store_status;

-- Check Region distribution for a table
SELECT
    region_id,
    start_key,
    end_key,
    leader_store_id,
    peer_store_ids
FROM information_schema.tikv_region_status
WHERE db_name = 'myapp' AND table_name = 'orders'
LIMIT 10;


-- === Table Design for Distribution ===

-- AUTO_RANDOM: prevent write hotspot on auto-increment PKs
-- (auto-increment causes all inserts to hit the same Region)
CREATE TABLE orders (
    id BIGINT PRIMARY KEY AUTO_RANDOM(5),  -- 5 shard bits
    user_id BIGINT NOT NULL,
    status ENUM('pending', 'paid', 'shipped', 'delivered') NOT NULL,
    total_cents BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_status (user_id, status),
    INDEX idx_created (created_at)
);

-- Clustered index: store row data with PK (faster point lookups)
CREATE TABLE users (
    id BIGINT PRIMARY KEY CLUSTERED AUTO_RANDOM,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Hash-partitioned table: explicit distribution control
CREATE TABLE events (
    id BIGINT NOT NULL AUTO_RANDOM,
    event_type VARCHAR(50) NOT NULL,
    payload JSON,
    created_at DATE NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE COLUMNS(created_at) (
    PARTITION p2024 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax  VALUES LESS THAN MAXVALUE
);


-- === Placement Rules (data locality) ===

-- Create placement policy: keep data in specific regions
CREATE PLACEMENT POLICY us_west
    PRIMARY_REGION = "us-west-2"
    REGIONS = "us-west-2,us-east-1"
    FOLLOWERS = 2
    LEADER_CONSTRAINTS = "[+region=us-west-2]";

CREATE PLACEMENT POLICY eu_gdpr
    PRIMARY_REGION = "eu-west-1"
    REGIONS = "eu-west-1,eu-central-1"
    CONSTRAINTS = "[+region=eu-]"  -- Data stays in EU
    FOLLOWERS = 2;

-- Apply placement to tables (GDPR compliance)
ALTER TABLE eu_users PLACEMENT POLICY = eu_gdpr;
ALTER TABLE us_orders PLACEMENT POLICY = us_west;

-- Database-level placement
ALTER DATABASE eu_data PLACEMENT POLICY = eu_gdpr;


-- === TiFlash (columnar analytics) ===

-- Add TiFlash replica for OLAP queries (same data, columnar format)
ALTER TABLE orders SET TIFLASH REPLICA 2;

-- TiDB optimizer automatically routes:
-- - Point queries / OLTP → TiKV (row store)
-- - Analytics / scans → TiFlash (columnar)

-- Force TiFlash for specific query
SELECT /*+ READ_FROM_STORAGE(TIFLASH[orders]) */
    DATE(created_at) AS day,
    COUNT(*) AS order_count,
    SUM(total_cents) / 100.0 AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY day
ORDER BY day;


-- === Migration from MySQL ===

-- TiDB is wire-compatible with MySQL 8.0
-- Most apps work without code changes

-- Check compatibility before migration
-- tidb-ctl compatibility-check --host mysql-source --port 3306

-- Use TiDB Data Migration (DM) for online migration:
-- 1. Full data export + import
-- 2. Continuous binlog replication
-- 3. Cutover when caught up
```

```yaml
# --- TiDB Data Migration task ---
# dm-task.yaml

name: mysql-to-tidb
task-mode: all                    # full + incremental
target-database:
  host: "tidb.example.com"
  port: 4000
  user: "root"
  password: "${DM_TIDB_PASSWORD}"

mysql-instances:
  - source-id: "mysql-01"
    block-allow-list: "migrate-rules"
    mydumper-config-name: "global"

block-allow-list:
  migrate-rules:
    do-dbs: ["myapp"]
    do-tables:
      - db-name: "myapp"
        tbl-name: "~^(?!_migrations).*$"   # Skip migration table

mydumpers:
  global:
    threads: 8
    chunk-filesize: 256
```

```python
# --- Python application with TiDB ---

import sqlalchemy
from sqlalchemy import create_engine, text


def create_tidb_engine(
    host: str = "tidb.example.com",
    port: int = 4000,
    database: str = "myapp",
    user: str = "root",
    password: str = "",
    pool_size: int = 20,
):
    """Create SQLAlchemy engine for TiDB.

    TiDB uses MySQL protocol — use mysql+pymysql driver.
    Key difference: use optimistic transactions by default.
    """
    engine = create_engine(
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
        pool_size=pool_size,
        pool_recycle=3600,
        connect_args={
            "ssl": {"ca": "/path/to/ca.pem"},
        },
        # TiDB-specific: optimistic transaction mode
        execution_options={
            "isolation_level": "REPEATABLE READ",
        },
    )
    return engine


def retry_on_conflict(func, max_retries: int = 3):
    """Retry decorator for TiDB optimistic transaction conflicts.

    TiDB uses optimistic locking by default — concurrent writes
    to the same row may conflict. Retry with backoff.
    """
    import time
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except sqlalchemy.exc.OperationalError as e:
                if "Write conflict" in str(e) and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                raise
    return wrapper
```

TiDB patterns:
1. **AUTO_RANDOM** — shard bits in primary key prevent write hotspots (vs auto-increment hitting one Region)
2. **Placement policies** — control data locality per table/database for compliance (GDPR, data residency)
3. **TiFlash** — add columnar replicas for analytics; optimizer auto-routes OLTP to TiKV, OLAP to TiFlash
4. **MySQL compatibility** — wire-compatible with MySQL 8.0; use same drivers, ORMs, and tools
5. **Optimistic transactions** — default in TiDB; retry on write conflicts instead of acquiring locks upfront'''
    ),
]
