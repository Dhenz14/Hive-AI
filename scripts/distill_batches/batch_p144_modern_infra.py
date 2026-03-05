"""Modern infrastructure 2026 — eBPF, Cilium, Crossplane, Flux CD, and Gateway API."""

PAIRS = [
    (
        "infra/ebpf-observability",
        "Show eBPF patterns for observability: tracing system calls, network monitoring, and performance profiling with bpftrace and Python.",
        '''eBPF observability patterns:

```python
# --- What is eBPF? ---
#
# eBPF (extended Berkeley Packet Filter) runs sandboxed programs
# in the Linux kernel WITHOUT modifying kernel source or loading modules.
#
# Use cases:
#   - Observability: trace syscalls, function calls, network packets
#   - Networking: load balancing, firewalling (Cilium)
#   - Security: runtime enforcement, syscall filtering
#   - Performance: CPU profiling, latency analysis


# --- bpftrace one-liners (the awk of eBPF) ---

"""
# Trace all open() syscalls with filename
bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("%s %s\\n", comm, str(args->filename)); }'

# Histogram of read() sizes
bpftrace -e 'tracepoint:syscalls:sys_exit_read /args->ret > 0/ { @bytes = hist(args->ret); }'

# Count syscalls by process
bpftrace -e 'tracepoint:raw_syscalls:sys_enter { @[comm] = count(); }'

# TCP connection latency histogram
bpftrace -e 'kprobe:tcp_v4_connect { @start[tid] = nsecs; }
             kretprobe:tcp_v4_connect /@start[tid]/ {
               @us = hist((nsecs - @start[tid]) / 1000);
               delete(@start[tid]);
             }'

# Trace DNS queries
bpftrace -e 'tracepoint:net:net_dev_xmit /args->len > 0/ { @[comm] = count(); }'

# Function latency (any kernel function)
bpftrace -e 'kprobe:vfs_read { @start[tid] = nsecs; }
             kretprobe:vfs_read /@start[tid]/ {
               @ns = hist(nsecs - @start[tid]);
               delete(@start[tid]);
             }'

# Page faults by process
bpftrace -e 'software:page-faults:1 { @[comm] = count(); }'
"""


# --- Python BCC (BPF Compiler Collection) ---

from bcc import BPF
import time

# Trace TCP connections with latency
bpf_program = r"""
#include <net/sock.h>
#include <bcc/proto.h>

struct event_t {
    u32 pid;
    u32 daddr;
    u16 dport;
    u64 delta_us;
    char comm[16];
};

BPF_HASH(start, u32);
BPF_PERF_OUTPUT(events);

int trace_connect(struct pt_regs *ctx, struct sock *sk) {
    u32 tid = bpf_get_current_pid_tgid();
    u64 ts = bpf_ktime_get_ns();
    start.update(&tid, &ts);
    return 0;
}

int trace_connect_return(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    u64 *tsp = start.lookup(&tid);
    if (!tsp) return 0;

    u64 delta = (bpf_ktime_get_ns() - *tsp) / 1000;  // microseconds
    start.delete(&tid);

    struct event_t event = {};
    event.pid = tid >> 32;
    event.delta_us = delta;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));

    events.perf_submit(ctx, &event, sizeof(event));
    return 0;
}
"""

def trace_tcp_connections():
    """Monitor TCP connection latencies with eBPF."""
    b = BPF(text=bpf_program)
    b.attach_kprobe(event="tcp_v4_connect", fn_name="trace_connect")
    b.attach_kretprobe(event="tcp_v4_connect", fn_name="trace_connect_return")

    def print_event(cpu, data, size):
        event = b["events"].event(data)
        print(f"PID={event.pid} COMM={event.comm.decode()} "
              f"LATENCY={event.delta_us}us")

    b["events"].open_perf_buffer(print_event)

    print("Tracing TCP connections... Ctrl+C to exit")
    while True:
        try:
            b.perf_buffer_poll()
        except KeyboardInterrupt:
            break


# --- Prometheus metrics from eBPF ---

from prometheus_client import Histogram, Counter, start_http_server

tcp_latency = Histogram(
    "tcp_connect_latency_seconds",
    "TCP connection establishment latency",
    ["destination"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

syscall_count = Counter(
    "syscall_total",
    "System calls by type",
    ["syscall", "process"],
)

def ebpf_to_prometheus():
    """Export eBPF metrics to Prometheus."""
    start_http_server(9090)
    b = BPF(text=bpf_program)
    # ... attach probes and update Prometheus metrics in callbacks


# --- eBPF for HTTP latency (L7 observability without sidecars) ---

"""
# Trace HTTP requests at the kernel level (no sidecar needed)
# This is how Cilium Hubble and Pixie work

# With bpftrace:
bpftrace -e '
  uprobe:/usr/lib/x86_64-linux-gnu/libssl.so.3:SSL_write {
    @start[tid] = nsecs;
  }
  uprobe:/usr/lib/x86_64-linux-gnu/libssl.so.3:SSL_read /@start[tid]/ {
    @latency_us = hist((nsecs - @start[tid]) / 1000);
    delete(@start[tid]);
  }
'
"""
```

eBPF observability patterns:
1. **bpftrace** — one-liner tracing for syscalls, kernel functions, and network events
2. **BCC Python** — attach probes to kernel/user functions with C programs compiled at runtime
3. **Perf events** — stream kernel events to userspace for real-time monitoring
4. **No sidecar** — observe HTTP/TCP at kernel level without proxy overhead (Cilium/Pixie approach)
5. **Prometheus export** — feed eBPF metrics into standard monitoring pipelines'''
    ),
    (
        "infra/crossplane-infrastructure",
        "Show Crossplane patterns: composing cloud resources as Kubernetes custom resources, compositions, and multi-cloud.",
        '''Crossplane infrastructure-as-code patterns:

```yaml
# --- What is Crossplane? ---
#
# Crossplane extends Kubernetes to manage ANY cloud resource
# (AWS, GCP, Azure, etc.) as Kubernetes custom resources.
#
# Instead of Terraform + kubectl, use ONLY kubectl for everything:
#   kubectl apply -f database.yaml  → creates an RDS instance
#   kubectl delete -f database.yaml → deletes it
#
# Benefits:
#   - GitOps-native: ArgoCD/Flux manage infrastructure
#   - Self-service: developers create resources via CRDs
#   - Drift detection: Kubernetes reconciliation loop


# --- Install Crossplane + AWS provider ---

# helm install crossplane crossplane-stable/crossplane -n crossplane-system
# kubectl apply -f provider-aws.yaml


# --- Managed Resource (direct cloud resource) ---

# database.yaml — creates an actual RDS instance
apiVersion: rds.aws.upbound.io/v1beta2
kind: Instance
metadata:
  name: my-postgres
spec:
  forProvider:
    region: us-east-1
    engine: postgres
    engineVersion: "16"
    instanceClass: db.t3.medium
    allocatedStorage: 20
    dbName: myapp
    masterUsername: admin
    masterPasswordSecretRef:
      name: db-password
      namespace: default
      key: password
    publiclyAccessible: false
    vpcSecurityGroupIdRefs:
      - name: db-sg
    dbSubnetGroupNameRef:
      name: db-subnets
  writeConnectionSecretToRef:
    name: db-connection
    namespace: default


---
# --- Composition (reusable infrastructure template) ---

# Composition = "infrastructure module" (like Terraform module)
# Developers request a "Database", Crossplane creates RDS + security group + subnet group

apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: databases.infra.example.com
spec:
  group: infra.example.com
  names:
    kind: Database
    plural: databases
  versions:
    - name: v1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                size:
                  type: string
                  enum: [small, medium, large]
                engine:
                  type: string
                  enum: [postgres, mysql]
                  default: postgres


---
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws
  labels:
    provider: aws
spec:
  compositeTypeRef:
    apiVersion: infra.example.com/v1
    kind: Database
  resources:
    - name: rds-instance
      base:
        apiVersion: rds.aws.upbound.io/v1beta2
        kind: Instance
        spec:
          forProvider:
            region: us-east-1
            engine: postgres
            engineVersion: "16"
            publiclyAccessible: false
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: spec.size
          toFieldPath: spec.forProvider.instanceClass
          transforms:
            - type: map
              map:
                small: db.t3.micro
                medium: db.t3.medium
                large: db.r6g.large

    - name: security-group
      base:
        apiVersion: ec2.aws.upbound.io/v1beta1
        kind: SecurityGroup
        spec:
          forProvider:
            region: us-east-1
            description: Database security group


---
# --- Developer self-service (claim) ---

# Developer just writes this — no AWS knowledge needed
apiVersion: infra.example.com/v1
kind: Database
metadata:
  name: my-app-db
spec:
  size: medium
  engine: postgres

# kubectl apply -f my-db.yaml
# → Crossplane creates: RDS instance + security group + subnet group
# → Connection secret appears in Kubernetes


---
# --- Multi-cloud: same API, different providers ---

# GCP composition for the same Database CRD
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-gcp
  labels:
    provider: gcp
spec:
  compositeTypeRef:
    apiVersion: infra.example.com/v1
    kind: Database
  resources:
    - name: cloudsql-instance
      base:
        apiVersion: sql.gcp.upbound.io/v1beta2
        kind: DatabaseInstance
        spec:
          forProvider:
            databaseVersion: POSTGRES_16
            region: us-central1
            settings:
              - tier: db-custom-2-4096
```

Crossplane patterns:
1. **Managed Resources** — each cloud resource is a Kubernetes CR with reconciliation loop
2. **Compositions** — reusable templates (like Terraform modules) abstracting cloud details
3. **CompositeResourceDefinitions** — define developer-facing APIs (`Database`, `Cache`, `Queue`)
4. **Multi-cloud** — same CRD, different Compositions per cloud provider
5. **GitOps-native** — ArgoCD/Flux manage infrastructure alongside application code'''
    ),
    (
        "infra/kubernetes-gateway-api",
        "Show Kubernetes Gateway API patterns: HTTPRoute, TLS termination, traffic splitting, and migration from Ingress.",
        '''Kubernetes Gateway API patterns:

```yaml
# --- What is Gateway API? ---
#
# Gateway API is the successor to Ingress.
# Key improvements:
#   - Role-oriented: separate Gateway (infra) from HTTPRoute (developer)
#   - Portable: works across implementations (Istio, Cilium, Envoy, NGINX)
#   - Expressive: header matching, traffic splitting, request mirroring
#   - Type-safe: strong schema validation
#
# Install CRDs: kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml


# --- GatewayClass (cluster-level, managed by infra team) ---

apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: istio
spec:
  controllerName: istio.io/gateway-controller


---
# --- Gateway (namespace-level, managed by platform team) ---

apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: main-gateway
  namespace: gateway-system
spec:
  gatewayClassName: istio
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: wildcard-tls
      allowedRoutes:
        namespaces:
          from: All  # Any namespace can attach routes

    - name: http
      protocol: HTTP
      port: 80
      allowedRoutes:
        namespaces:
          from: All


---
# --- HTTPRoute (managed by application developers) ---

apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-routes
  namespace: myapp
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway-system
  hostnames:
    - "api.example.com"
  rules:
    # Route /api/v2/* to v2 service
    - matches:
        - path:
            type: PathPrefix
            value: /api/v2
      backendRefs:
        - name: api-v2
          port: 8080

    # Route /api/v1/* to v1 service (legacy)
    - matches:
        - path:
            type: PathPrefix
            value: /api/v1
      backendRefs:
        - name: api-v1
          port: 8080

    # Default: route to latest
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: api-v2
          port: 8080


---
# --- Canary deployment (traffic splitting) ---

apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: canary-route
  namespace: myapp
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway-system
  hostnames:
    - "app.example.com"
  rules:
    - backendRefs:
        - name: app-stable
          port: 8080
          weight: 90    # 90% to stable
        - name: app-canary
          port: 8080
          weight: 10    # 10% to canary


---
# --- Header-based routing (A/B testing) ---

apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: ab-test-route
  namespace: myapp
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway-system
  hostnames:
    - "app.example.com"
  rules:
    # Beta users (header match)
    - matches:
        - headers:
            - name: X-Beta-User
              value: "true"
      backendRefs:
        - name: app-beta
          port: 8080

    # Default: stable
    - backendRefs:
        - name: app-stable
          port: 8080


---
# --- Request mirroring (shadow traffic) ---

apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: mirror-route
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway-system
  rules:
    - backendRefs:
        - name: api-production
          port: 8080
      filters:
        - type: RequestMirror
          requestMirror:
            backendRef:
              name: api-shadow
              port: 8080
            # Shadow receives copy of all requests
            # Responses from shadow are discarded


---
# --- Migration from Ingress ---

# Old Ingress:
# apiVersion: networking.k8s.io/v1
# kind: Ingress
# metadata:
#   name: myapp
#   annotations:
#     nginx.ingress.kubernetes.io/rewrite-target: /
# spec:
#   rules:
#     - host: app.example.com
#       http:
#         paths:
#           - path: /
#             pathType: Prefix
#             backend:
#               service:
#                 name: myapp
#                 port:
#                   number: 8080

# New Gateway API equivalent:
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: myapp
spec:
  parentRefs:
    - name: main-gateway
      namespace: gateway-system
  hostnames:
    - "app.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: myapp
          port: 8080
      filters:
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: /
```

Gateway API patterns:
1. **Role separation** — GatewayClass (infra) → Gateway (platform) → HTTPRoute (developer)
2. **Traffic splitting** — `weight` field for canary deployments (90/10, 95/5, etc.)
3. **Header matching** — route by headers for A/B testing and beta features
4. **Request mirroring** — shadow traffic to new service without affecting production
5. **Portable** — same HTTPRoute spec works across Istio, Cilium, Envoy Gateway, NGINX'''
    ),
]
