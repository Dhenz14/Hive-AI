PAIRS = [
    ("thinking/debugging", r'''Our Kubernetes pod keeps entering CrashLoopBackOff. The pod restarts every 30 seconds and the backoff time keeps increasing:

```
$ kubectl get pods
NAME                        READY   STATUS             RESTARTS   AGE
api-server-7f8d9b6c4-x2k9p 0/1     CrashLoopBackOff   14         12m

$ kubectl describe pod api-server-7f8d9b6c4-x2k9p
...
State:          Waiting
  Reason:       CrashLoopBackOff
Last State:     Terminated
  Reason:       Error
  Exit Code:    1
  Started:      Fri, 06 Mar 2026 10:23:45 +0000
  Finished:     Fri, 06 Mar 2026 10:23:47 +0000

$ kubectl logs api-server-7f8d9b6c4-x2k9p
Traceback (most recent call last):
  File "/app/main.py", line 12, in <module>
    db_url = os.environ["DATABASE_URL"]
KeyError: 'DATABASE_URL'
```

Our deployment YAML references a Secret for this env var:

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: api-secrets
        key: database-url
```

The secret exists:
```
$ kubectl get secret api-secrets
NAME          TYPE     DATA   AGE
api-secrets   Opaque   3      5d
```

But the pod still cannot find the env var.''', r'''<think>
CrashLoopBackOff with KeyError for an environment variable that should come from a Secret. The secret exists, so why is the env var not injected?

Let me think about common causes:
1. Secret key name mismatch -- the secret has the key under a different name
2. Secret is in a different namespace
3. The pod spec references the wrong secret name
4. The secret data has the key with different casing

The user shows `secretKeyRef.key: database-url` -- let me check if the actual secret has that exact key. The secret exists with 3 data entries, but we need to verify the key name.

Most likely: the secret key is named differently (e.g., `DATABASE_URL` instead of `database-url`, or `database_url` with underscores). Secret key names are case-sensitive and the key in the secretKeyRef must match exactly what is in the secret data.

Another possibility: namespace mismatch. If the deployment is in namespace "production" but the secret is in "default", the pod cannot access it.
</think>

The pod crashes because the `DATABASE_URL` environment variable is not being injected, despite the secret existing. This is almost always a **secret key name mismatch**.

**Diagnose the exact key names in the secret:**

```bash
# Show the actual keys in the secret (not the values)
$ kubectl get secret api-secrets -o jsonpath='{.data}' | python3 -c "import sys,json; print(list(json.load(sys.stdin).keys()))"
['DATABASE_URL', 'redis-url', 'api-key']
```

The secret key is `DATABASE_URL` (uppercase with underscores), but your deployment references `database-url` (lowercase with hyphens). Secret key lookups are **case-sensitive and exact-match**.

**Fix the deployment YAML:**

```yaml
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: api-secrets
        key: DATABASE_URL   # Must match the EXACT key in the secret
```

**Alternative: check for namespace mismatch:**

```bash
# Verify pod and secret are in the same namespace
$ kubectl get pod api-server-7f8d9b6c4-x2k9p -o jsonpath='{.metadata.namespace}'
production

$ kubectl get secret api-secrets -n production
# If this fails with "not found", the secret is in a different namespace
```

**Debugging commands for future secret issues:**

```bash
# Decode and view all secret keys (careful -- prints values!)
kubectl get secret api-secrets -o json | jq '.data | keys'

# Check if the secret key exists without printing the value
kubectl get secret api-secrets -o jsonpath='{.data.DATABASE_URL}' | wc -c
# If output is 0, the key does not exist

# View pod events for injection errors
kubectl describe pod <pod-name> | grep -A5 "Events:"
# Look for "secret not found" or "key not found" warnings

# Verify the secret is mounted by exec-ing into a running pod
kubectl exec -it <pod-name> -- env | grep DATABASE
```

**Prevention tips:**
- Use `kubectl describe pod` to check for Warning events about missing secrets before investigating application logs
- Add a `optional: false` (the default) to secretKeyRef to make pod scheduling fail fast if the secret is missing
- Use a naming convention for secret keys that matches your env var names exactly
- Add a pre-deploy check in CI that validates secret keys match deployment references
- Consider using `envFrom` with `secretRef` to inject all keys from a secret as env vars, avoiding key name mismatches'''),

    ("thinking/debugging", r'''A Kubernetes pod is being OOMKilled repeatedly but our application only uses about 200MB of memory according to our metrics:

```
$ kubectl describe pod worker-5c8f7d9b4-m3k2j
...
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137

Containers:
  worker:
    Limits:
      memory: 512Mi
    Requests:
      memory: 256Mi

$ kubectl top pod worker-5c8f7d9b4-m3k2j
NAME                        CPU(cores)   MEMORY(bytes)
worker-5c8f7d9b4-m3k2j     150m         487Mi
```

But our Python application metrics show:
```
import psutil
process = psutil.Process()
print(f"RSS: {process.memory_info().rss / 1024 / 1024:.0f} MB")
# Output: RSS: 195 MB
```

How can the pod use 487Mi when the Python process only uses 195MB?''', r'''<think>
The discrepancy between Python process memory (195MB RSS) and Kubernetes pod memory (487Mi) is a classic debugging puzzle. Let me think about what accounts for the difference.

Kubernetes measures container memory using cgroups, which includes:
1. RSS (Resident Set Size) of all processes in the container
2. Page cache (file-backed memory from disk reads)
3. tmpfs usage (if any tmpfs mounts like /dev/shm)
4. Kernel memory (slab, etc.)

The Python process reports only its own RSS. But the container might have:
- Child processes (forked workers, subprocess calls)
- Shared memory segments
- Memory-mapped files
- The page cache from file I/O

The most common cause: the application does heavy file I/O (reading data files, log files, temp files) and the kernel page cache counts toward the container memory limit. Or the application spawns child processes (e.g., Celery workers, multiprocessing).

Also, Python RSS from psutil measures only the main process. If there are worker threads with native allocations, or subprocess-spawned children, those are separate.

Another common cause: Python memory fragmentation. The Python allocator requests memory from the OS but does not always return it. The OS sees higher RSS than what Python is actively using.
</think>

The 292MB gap between Python's self-reported memory (195MB) and Kubernetes' measurement (487Mi) is caused by Kubernetes counting ALL memory in the cgroup, not just your Python process RSS.

**What Kubernetes counts toward the memory limit:**

```
Container memory (cgroup) = RSS of all processes
                          + page cache (file I/O buffers)
                          + tmpfs usage (/dev/shm, /tmp if tmpfs)
                          + kernel memory (slab allocations)
                          + swap (if enabled)
```

**Diagnose what is consuming the extra memory:**

```bash
# Check memory breakdown inside the container
kubectl exec -it worker-5c8f7d9b4-m3k2j -- cat /sys/fs/cgroup/memory/memory.stat

# Key fields:
# rss          - actual process memory
# cache        - page cache from file I/O
# mapped_file  - memory-mapped files
# swap         - swap usage

# Check for child processes
kubectl exec -it worker-5c8f7d9b4-m3k2j -- ps aux
# Look for forked workers, subprocess calls, etc.

# Check tmpfs usage
kubectl exec -it worker-5c8f7d9b4-m3k2j -- df -h /dev/shm /tmp
```

**Common causes of the gap:**

**1. Page cache from file I/O (most common)**

```python
# This reads a large file and the kernel caches it in memory
with open('/data/large_dataset.csv', 'r') as f:
    data = f.readlines()  # 200MB file -> 200MB page cache

# Even after closing the file, the page cache persists
# and counts toward the container memory limit
```

**2. Child processes not visible to psutil.Process()**

```python
# Celery with prefork pool spawns child processes
# Each child has its own RSS
celery_app.conf.worker_concurrency = 4
# 4 workers x 50MB each = 200MB not shown by parent psutil

# Fix: measure all processes
import psutil
total = sum(p.memory_info().rss for p in psutil.process_iter())
print(f"Total RSS all processes: {total / 1024 / 1024:.0f} MB")
```

**3. Python memory fragmentation**

```python
# Python's memory allocator (pymalloc) holds onto freed memory
# The OS sees it as "in use" even though Python considers it free
import tracemalloc
tracemalloc.start()
# ... your code ...
current, peak = tracemalloc.get_traced_memory()
print(f"Python tracked: {current / 1024 / 1024:.0f} MB")
print(f"Python peak: {peak / 1024 / 1024:.0f} MB")
# Compare with psutil RSS to see fragmentation
```

**Fixes:**

```yaml
# Increase memory limit to account for page cache
resources:
  limits:
    memory: 768Mi   # Give headroom for page cache
  requests:
    memory: 512Mi
```

```python
# Reduce page cache by using streaming I/O
# Instead of reading entire file:
data = open('large.csv').read()  # Entire file in page cache

# Stream it:
import csv
with open('large.csv') as f:
    reader = csv.reader(f)
    for row in reader:
        process(row)  # Only one row in memory at a time

# Or explicitly advise the kernel to drop cache after reading
import os
fd = os.open('large.csv', os.O_RDONLY)
os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
os.close(fd)
```

**Prevention tips:**
- Always set memory limits 2-3x your expected application RSS to account for page cache
- Use `memory.stat` from cgroups, not application-level metrics, for capacity planning
- Monitor `container_memory_working_set_bytes` in Prometheus (excludes inactive page cache)
- Use streaming I/O for large files to minimize page cache pressure
- If using multiprocessing, account for child process memory in your limits'''),

    ("thinking/debugging", r'''Kubernetes service discovery is failing. Pod A cannot reach Pod B via the service name, but can reach it via the pod IP:

```
# From inside Pod A:
$ curl http://backend-service:8080/health
curl: (6) Could not resolve host: backend-service

# But direct pod IP works:
$ curl http://10.244.1.15:8080/health
{"status": "ok"}

# DNS lookup fails:
$ nslookup backend-service
;; connection timed out; no servers could be reached

# The service exists:
$ kubectl get svc backend-service
NAME              TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
backend-service   ClusterIP   10.96.45.123   <none>        8080/TCP   2d

# Endpoints are populated:
$ kubectl get endpoints backend-service
NAME              ENDPOINTS          AGE
backend-service   10.244.1.15:8080   2d
```

The service is correctly configured with endpoints, but DNS resolution from Pod A fails entirely.''', r'''<think>
DNS resolution failing entirely from within a pod -- even nslookup times out. This means the pod cannot reach the cluster DNS service (typically CoreDNS).

Let me think about what could cause this:
1. CoreDNS pods are down or not running
2. The kube-dns service (which fronts CoreDNS) is misconfigured
3. The pod's /etc/resolv.conf is wrong (pointing to wrong nameserver)
4. Network policy blocking DNS traffic (UDP port 53)
5. The pod's DNS policy is set to "Default" instead of "ClusterFirst"

Since nslookup completely times out (not NXDOMAIN, but connection timeout), this means the DNS server is unreachable. That points to either CoreDNS being down, network policies blocking port 53, or the pod having wrong DNS configuration.

Let me check the most common one: pod dnsPolicy. If it is set to "Default", the pod uses the node's DNS, not cluster DNS, and cannot resolve service names.
</think>

The fact that `nslookup` times out entirely (not NXDOMAIN) means the pod cannot reach the cluster DNS server at all. This is a DNS connectivity issue, not a service configuration issue.

**Step 1: Check what DNS server the pod is using:**

```bash
kubectl exec -it <pod-a> -- cat /etc/resolv.conf
```

Expected output for cluster DNS:
```
nameserver 10.96.0.10
search default.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

If the nameserver is NOT 10.96.0.10 (or your cluster DNS IP), the pod is not configured for cluster DNS.

**Step 2: Check if CoreDNS is running:**

```bash
$ kubectl get pods -n kube-system -l k8s-app=kube-dns
NAME                       READY   STATUS    RESTARTS   AGE
coredns-6d4b75cb6d-7x8k2  1/1     Running   0          5d
coredns-6d4b75cb6d-m3j9p  1/1     Running   0          5d

# Check CoreDNS logs for errors
$ kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50
```

**Step 3: Check for network policies blocking DNS:**

```bash
$ kubectl get networkpolicies -A
# Look for policies that might block egress to kube-system namespace on port 53
```

**Most common cause -- incorrect dnsPolicy in the pod spec:**

```yaml
# WRONG: "Default" uses the node's DNS, not cluster DNS
apiVersion: v1
kind: Pod
spec:
  dnsPolicy: Default   # <-- This is the bug!
  containers:
    - name: app
      image: myapp:latest
```

```yaml
# CORRECT: "ClusterFirst" uses cluster DNS for service discovery
apiVersion: v1
kind: Pod
spec:
  dnsPolicy: ClusterFirst   # <-- Default for most workloads
  containers:
    - name: app
      image: myapp:latest
```

**Check the current dnsPolicy:**

```bash
$ kubectl get pod <pod-a> -o jsonpath='{.spec.dnsPolicy}'
Default
# If this shows "Default", that is the problem!
```

**Other causes and fixes:**

```bash
# If CoreDNS pods are in CrashLoopBackOff, check their config
kubectl get configmap coredns -n kube-system -o yaml

# If a NetworkPolicy is blocking DNS, add an egress rule
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to: []
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

**Quick DNS test from inside any pod:**

```bash
# Test cluster DNS directly
kubectl exec -it <pod> -- nslookup kubernetes.default.svc.cluster.local

# Test with explicit DNS server
kubectl exec -it <pod> -- nslookup backend-service 10.96.0.10

# If the explicit server works but default does not,
# the pod resolv.conf is wrong (dnsPolicy issue)
```

**Prevention tips:**
- Never set `dnsPolicy: Default` unless you specifically need node DNS only
- If using `hostNetwork: true`, you must explicitly set `dnsPolicy: ClusterFirstWithHostNet`
- Always include UDP port 53 egress in NetworkPolicies
- Monitor CoreDNS pod health and restart counts
- Use fully qualified names (backend-service.default.svc.cluster.local) to avoid ndots search delays'''),

    ("thinking/debugging", r'''A PersistentVolumeClaim is stuck in Pending state and our pod cannot start because the volume will not mount:

```
$ kubectl get pvc data-volume
NAME          STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
data-volume   Pending                                      gp2            15m

$ kubectl describe pvc data-volume
...
Events:
  Type     Reason              Age                From                         Message
  ----     ------              ----               ----                         -------
  Normal   WaitForFirstConsumer 15m (x4 over 15m) persistentvolume-controller  waiting for first consumer to be created before binding

$ kubectl get pod app-0
NAME    READY   STATUS    RESTARTS   AGE
app-0   0/1     Pending   0          14m

$ kubectl describe pod app-0
...
Events:
  Type     Reason            Age                From               Message
  ----     ------            ----               ----               -------
  Warning  FailedScheduling  2m (x8 over 14m)   default-scheduler  0/3 nodes are available: 3 node(s) had volume node affinity conflict.
```

We have 3 nodes in us-east-1a, us-east-1b, us-east-1c. The StorageClass is gp2 (AWS EBS).''', r'''<think>
The key error is: "0/3 nodes are available: 3 node(s) had volume node affinity conflict."

And the PVC shows: "waiting for first consumer to be created before binding"

This is a classic EBS + availability zone issue. AWS EBS volumes are zone-specific -- a volume in us-east-1a can only be mounted by a node in us-east-1a.

The StorageClass has `volumeBindingMode: WaitForFirstConsumer`, which means the PV is not created until a pod is scheduled. But the scheduler cannot find a node because... there is a conflict between the pod's node affinity/topology and the available zones.

Wait, but with WaitForFirstConsumer, the volume should be created in whatever zone the pod gets scheduled to. So why the conflict?

Possible causes:
1. There is an existing PV (from a previous PVC) that is bound to a specific zone, and the pod has a nodeSelector or affinity that conflicts with that zone
2. The pod is part of a StatefulSet and a previously created PV is in zone us-east-1a, but the node in that zone is full/cordoned
3. The pod has a nodeSelector or nodeAffinity that restricts it to a specific zone, but the PV was provisioned in a different zone

For StatefulSets, PVCs are retained across pod restarts. If the original PV was created in us-east-1a and the node in us-east-1a is unavailable (cordoned, out of capacity), the pod cannot be scheduled anywhere else because the EBS volume cannot move zones.

This is the most common cause of "volume node affinity conflict."
</think>

The error "volume node affinity conflict" with AWS EBS means the PersistentVolume is locked to one availability zone, but no node in that zone can accept the pod. EBS volumes are physically tied to a single AZ and cannot be mounted across zones.

**Diagnose the exact conflict:**

```bash
# Check if there is an existing PV bound to this PVC (from a previous run)
$ kubectl get pv | grep data-volume
pvc-abc123   10Gi   RWO   Retain   Released   default/data-volume   gp2   5d

# Check which zone the PV is in
$ kubectl describe pv pvc-abc123 | grep -A5 "Node Affinity"
Node Affinity:
  Required Terms:
    Term 0:
      topology.ebs.csi.aws.com/zone in [us-east-1a]

# Check which nodes are available in that zone
$ kubectl get nodes -l topology.kubernetes.io/zone=us-east-1a
# If no nodes are available, that is the conflict
```

**Common scenario: StatefulSet with retained PVs**

If this pod is part of a StatefulSet, the PVC is retained when the pod is deleted. The existing PV was provisioned in us-east-1a, but:
- The node in us-east-1a was replaced/cordoned/scaled down
- No node in us-east-1a has sufficient resources
- The new node pool only has nodes in us-east-1b and us-east-1c

**Fix 1: Make a node available in the correct zone**

```bash
# Check node capacity in the PV's zone
kubectl get nodes -l topology.kubernetes.io/zone=us-east-1a \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,CPU:.status.allocatable.cpu,MEM:.status.allocatable.memory

# If no nodes exist in that zone, scale the node group
# AWS EKS example:
aws eks update-nodegroup-config \
  --cluster-name my-cluster \
  --nodegroup-name workers \
  --scaling-config minSize=1,maxSize=5,desiredSize=3
# Ensure the ASG spans the zone where the PV lives
```

**Fix 2: Migrate the PV to a different zone (data migration)**

```bash
# 1. Create a snapshot of the EBS volume
VOLUME_ID=$(kubectl get pv pvc-abc123 -o jsonpath='{.spec.csi.volumeHandle}')
SNAPSHOT_ID=$(aws ec2 create-snapshot --volume-id $VOLUME_ID --query 'SnapshotId' --output text)
aws ec2 wait snapshot-completed --snapshot-ids $SNAPSHOT_ID

# 2. Create a new volume in the target zone
NEW_VOLUME=$(aws ec2 create-volume \
  --snapshot-id $SNAPSHOT_ID \
  --availability-zone us-east-1b \
  --volume-type gp2 \
  --query 'VolumeId' --output text)

# 3. Create a new PV pointing to the new volume
# 4. Update the PVC to bind to the new PV
```

**Fix 3: Prevent this in the future with topology-aware provisioning**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp2-balanced
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer  # Provision in the scheduled zone
allowedTopologies:
  - matchLabelExpressions:
    - key: topology.ebs.csi.aws.com/zone
      values:
        - us-east-1a
        - us-east-1b
        - us-east-1c
parameters:
  type: gp2
```

**Fix 4: Use EFS instead of EBS for cross-zone access**

```yaml
# EFS is not zone-bound -- works across all AZs
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: efs-sc
provisioner: efs.csi.aws.com
```

**Prevention tips:**
- Use `WaitForFirstConsumer` binding mode so volumes are created in the zone where the pod is scheduled
- Ensure your node auto-scaler covers all zones where PVs might exist
- For StatefulSets, use `reclaimPolicy: Delete` if data is not critical, or plan for zone migration
- Consider EFS or cross-zone storage for workloads that need zone flexibility
- Monitor PVC status and alert on Pending PVCs older than 5 minutes'''),

    ("thinking/debugging", r'''Our Kubernetes rolling update is stuck -- the new pods are starting but old pods are not terminating. The deployment shows a mix of old and new pods:

```
$ kubectl rollout status deployment/web-app
Waiting for deployment "web-app" spec update to be observed...
Waiting for deployment "web-app" rollout to finish: 2 out of 4 new replicas have been updated...

$ kubectl get pods -l app=web-app
NAME                       READY   STATUS    RESTARTS   AGE
web-app-6f8d9b7c5-abc12   1/1     Running   0          2d    # old
web-app-6f8d9b7c5-def34   1/1     Running   0          2d    # old
web-app-6f8d9b7c5-ghi56   1/1     Running   0          2d    # old
web-app-6f8d9b7c5-jkl78   1/1     Running   0          2d    # old
web-app-8a2c4e1d3-mn90p   0/1     Running   0          25m   # new (not ready)
web-app-8a2c4e1d3-qr12s   0/1     Running   0          25m   # new (not ready)

$ kubectl describe pod web-app-8a2c4e1d3-mn90p
...
Conditions:
  Type              Status
  Ready             False
  ContainersReady   False
Readiness probe:
  HTTP GET http://:8080/ready
  Delay: 5s, Timeout: 3s, Period: 10s, Success: 1, Failure: 3

Events:
  Type     Reason     Age                 From     Message
  ----     ------     ----                ----     -------
  Warning  Unhealthy  2m (x150 over 25m)  kubelet  Readiness probe failed: HTTP probe failed with statuscode: 503
```

The new pods are running but never become Ready because the readiness probe keeps failing with 503.''', r'''<think>
The rolling update is stuck because new pods are never becoming Ready. The old pods will not be terminated until new pods pass their readiness probe, which is the correct behavior -- Kubernetes will not remove old pods until new pods can serve traffic.

The new pods return 503 from the /ready endpoint. This could be because:
1. The new version has a bug in the readiness endpoint
2. The new version needs a dependency that is not available (database migration not run, config missing, etc.)
3. The new version takes longer to start than the probe allows
4. The readiness endpoint checks a dependency that is failing (e.g., cannot connect to a service, missing env var)

Since the pods are in Running state but not Ready, the container started fine but the application reports it is not ready to serve traffic. This is not a crash -- it is the application itself saying "I am not ready."

The fix depends on why the application returns 503. We need to check the application logs.
</think>

The rolling update is stuck by design -- Kubernetes will not terminate old pods until new pods pass their readiness probe. The new pods are running but returning 503 on the readiness endpoint, so the rollout cannot progress. This is actually Kubernetes protecting you from a bad deployment.

**Step 1: Check why the new pod returns 503:**

```bash
# Check application logs (not just events)
$ kubectl logs web-app-8a2c4e1d3-mn90p
[2026-03-06 10:15:30] INFO: Starting web-app v2.3.0
[2026-03-06 10:15:31] ERROR: Failed to connect to cache service: redis://redis-master:6379
[2026-03-06 10:15:31] WARNING: Readiness check failing - cache unavailable
[2026-03-06 10:15:41] WARNING: Readiness check failing - cache unavailable
...

# Test the readiness endpoint directly
$ kubectl exec web-app-8a2c4e1d3-mn90p -- curl -s localhost:8080/ready
{"status": "not_ready", "reason": "cache_unavailable"}
```

**Common causes of readiness probe failures during rollout:**

**1. New version added a dependency check to the readiness probe:**

```python
# Old version readiness endpoint:
@app.get("/ready")
def ready():
    return {"status": "ok"}

# New version added a cache check that fails:
@app.get("/ready")
def ready():
    if not redis_client.ping():
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ok"}
```

**2. Missing configuration or secret for the new version:**

```bash
# Check if the new version expects env vars that do not exist
kubectl exec web-app-8a2c4e1d3-mn90p -- env | sort
# Compare with old pod:
kubectl exec web-app-6f8d9b7c5-abc12 -- env | sort
```

**3. Database migration not applied:**

```bash
# New code expects a column/table that does not exist yet
kubectl logs web-app-8a2c4e1d3-mn90p | grep -i "migration\|schema\|column"
```

**Immediate actions:**

```bash
# Option A: Roll back to the previous version
kubectl rollout undo deployment/web-app

# Option B: Pause the rollout while you investigate
kubectl rollout pause deployment/web-app

# Check rollout history
kubectl rollout history deployment/web-app
```

**Fix the deployment strategy to prevent stuck rollouts:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    spec:
      containers:
        - name: web-app
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 6
            timeoutSeconds: 3
          # Add a startup probe for slow-starting apps
          startupProbe:
            httpGet:
              path: /ready
              port: 8080
            failureThreshold: 30
            periodSeconds: 5
            # Gives the app 150 seconds to start before failing
      # Set a progress deadline so stuck rollouts are flagged
      progressDeadlineSeconds: 300  # 5 minutes
```

**Add a progressDeadlineSeconds to auto-detect stuck rollouts:**

```bash
# With progressDeadlineSeconds set, after the deadline:
$ kubectl rollout status deployment/web-app
error: deployment "web-app" exceeded its progress deadline

# The deployment condition will show:
$ kubectl get deployment web-app -o jsonpath='{.status.conditions[?(@.type=="Progressing")].message}'
ReplicaSet "web-app-8a2c4e1d3" has timed out progressing.
```

**Prevention tips:**
- Always set `progressDeadlineSeconds` to detect stuck rollouts automatically
- Use startup probes for applications that take a long time to initialize
- Keep readiness probes lightweight -- check only what the pod itself controls
- Do not add new dependency checks to readiness probes without ensuring dependencies are available
- Run database migrations as a separate Job before deploying new application code
- Use `kubectl rollout pause` to investigate before deciding to undo or proceed'''),
]
