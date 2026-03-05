"""Kubernetes — deployments, services, ConfigMaps, secrets, and HPA patterns."""

PAIRS = [
    (
        "devops/k8s-deployments",
        "Show Kubernetes deployment patterns: rolling updates, health probes, resource limits, and pod disruption budgets.",
        """Kubernetes deployment patterns:

```yaml
# --- Deployment with best practices ---

apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  labels:
    app: myapp
    version: v2.1.0
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1          # Max extra pods during update
      maxUnavailable: 0    # Zero downtime

  selector:
    matchLabels:
      app: myapp

  template:
    metadata:
      labels:
        app: myapp
        version: v2.1.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"

    spec:
      terminationGracePeriodSeconds: 60
      serviceAccountName: myapp

      # Anti-affinity: spread across nodes
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: myapp
                topologyKey: kubernetes.io/hostname

      containers:
        - name: myapp
          image: ghcr.io/myorg/myapp:v2.1.0
          imagePullPolicy: IfNotPresent

          ports:
            - containerPort: 8080
              name: http

          # Environment from ConfigMap and Secret
          envFrom:
            - configMapRef:
                name: myapp-config
            - secretRef:
                name: myapp-secrets

          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName

          # Resource limits
          resources:
            requests:
              cpu: 250m         # 0.25 CPU core
              memory: 256Mi
            limits:
              cpu: 1000m        # 1 CPU core
              memory: 512Mi

          # Health probes
          startupProbe:
            httpGet:
              path: /health
              port: http
            failureThreshold: 30
            periodSeconds: 2     # Max 60s to start

          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3

          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3

          # Graceful shutdown
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]

          # Security context
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}

---
# --- Service ---

apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: http
      protocol: TCP

---
# --- HPA (autoscaling) ---

apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # Wait 5 min before scaling down
      policies:
        - type: Percent
          value: 25
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15

---
# --- PodDisruptionBudget ---

apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
```

Kubernetes patterns:
1. **`maxUnavailable: 0`** — zero-downtime rolling updates
2. **Three probes** — startup (slow init), readiness (traffic), liveness (restart)
3. **`preStop` sleep** — delay shutdown for in-flight requests to drain
4. **Pod anti-affinity** — spread replicas across nodes for HA
5. **HPA stabilization** — prevent flapping with scale-down cooldown"""
    ),
    (
        "devops/k8s-config",
        "Show Kubernetes configuration patterns: ConfigMaps, Secrets, Kustomize overlays, and Helm charts.",
        """Kubernetes configuration management:

```yaml
# --- ConfigMap ---

apiVersion: v1
kind: ConfigMap
metadata:
  name: myapp-config
data:
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"
  FEATURE_NEW_UI: "true"

  # File-based config
  config.yaml: |
    server:
      port: 8080
      cors_origins:
        - https://myapp.com
    cache:
      ttl: 300
      max_size: 1000

---
# --- Secret (base64 encoded) ---

apiVersion: v1
kind: Secret
metadata:
  name: myapp-secrets
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXNxbDovL3VzZXI6cGFzc0Bsb2NhbGhvc3QvbXlkYg==
  JWT_SECRET: c3VwZXItc2VjcmV0LWtleS1oZXJl

# Or use stringData (plain text, auto-encoded):
# stringData:
#   DATABASE_URL: "postgresql://user:pass@localhost/mydb"


# --- Kustomize overlays ---

# base/kustomization.yaml
# resources:
#   - deployment.yaml
#   - service.yaml
#   - configmap.yaml

# overlays/staging/kustomization.yaml
# resources:
#   - ../../base
# patches:
#   - patch-replicas.yaml
# configMapGenerator:
#   - name: myapp-config
#     behavior: merge
#     literals:
#       - LOG_LEVEL=debug
#       - FEATURE_NEW_UI=true

# overlays/production/kustomization.yaml
# resources:
#   - ../../base
# replicas:
#   - name: myapp
#     count: 5
# images:
#   - name: ghcr.io/myorg/myapp
#     newTag: v2.1.0
# configMapGenerator:
#   - name: myapp-config
#     behavior: merge
#     literals:
#       - LOG_LEVEL=warn


# --- Helm chart values ---

# values.yaml (defaults)
replicaCount: 3
image:
  repository: ghcr.io/myorg/myapp
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPU: 70

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: myapp.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: myapp-tls
      hosts:
        - myapp.example.com

env:
  LOG_LEVEL: info
  MAX_CONNECTIONS: "100"

secrets:
  DATABASE_URL: ""  # Set via --set-string at deploy time


# values-production.yaml (override per env)
# replicaCount: 5
# resources:
#   requests:
#     cpu: 500m
#     memory: 512Mi
# env:
#   LOG_LEVEL: warn

# Deploy: helm upgrade --install myapp ./chart -f values.yaml -f values-production.yaml
```

```yaml
# --- Ingress with TLS ---

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  ingressClassName: nginx
  tls:
    - hosts: [myapp.example.com]
      secretName: myapp-tls
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp
                port:
                  number: 80
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: myapp-api
                port:
                  number: 80
```

K8s config patterns:
1. **ConfigMap** — non-secret config as env vars or mounted files
2. **Kustomize overlays** — base + per-environment patches (no templating)
3. **Helm values** — `values.yaml` defaults + `values-production.yaml` overrides
4. **Ingress + cert-manager** — auto-provisioned TLS certificates
5. **`configMapGenerator`** — auto-hash suffix ensures pod restart on config change"""
    ),
    (
        "devops/k8s-jobs-cronjobs",
        "Show Kubernetes Job and CronJob patterns: batch processing, parallelism, and completion tracking.",
        """Kubernetes Jobs and CronJobs:

```yaml
# --- One-time Job ---

apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
spec:
  backoffLimit: 3            # Retry up to 3 times
  activeDeadlineSeconds: 300 # Timeout after 5 minutes
  ttlSecondsAfterFinished: 3600  # Cleanup after 1 hour

  template:
    spec:
      restartPolicy: Never   # Don't restart on failure (use backoffLimit)
      containers:
        - name: migrate
          image: ghcr.io/myorg/myapp:v2.1.0
          command: ["python", "-m", "alembic", "upgrade", "head"]
          envFrom:
            - secretRef:
                name: myapp-secrets
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi


---
# --- Parallel Job ---

apiVersion: batch/v1
kind: Job
metadata:
  name: data-processing
spec:
  parallelism: 5        # 5 pods running at once
  completions: 20       # Total tasks to complete
  backoffLimit: 5

  template:
    spec:
      restartPolicy: Never
      containers:
        - name: processor
          image: ghcr.io/myorg/processor:latest
          command: ["python", "process.py"]
          env:
            - name: JOB_COMPLETION_INDEX
              valueFrom:
                fieldRef:
                  fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']


---
# --- CronJob ---

apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
spec:
  schedule: "0 6 * * *"        # Daily at 6 AM UTC
  timeZone: "America/New_York" # K8s 1.27+
  concurrencyPolicy: Forbid    # Skip if previous still running
  startingDeadlineSeconds: 300 # Must start within 5 min of schedule
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3

  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600  # Max 1 hour

      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: report
              image: ghcr.io/myorg/reporter:latest
              command: ["python", "generate_report.py", "--type", "daily"]
              envFrom:
                - configMapRef:
                    name: reporter-config
                - secretRef:
                    name: reporter-secrets
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: 2000m
                  memory: 2Gi


---
# --- CronJob: cleanup old data ---

apiVersion: batch/v1
kind: CronJob
metadata:
  name: cleanup-expired
spec:
  schedule: "0 */6 * * *"     # Every 6 hours
  concurrencyPolicy: Replace  # Kill old job if still running

  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: cleanup
              image: ghcr.io/myorg/myapp:latest
              command:
                - python
                - -c
                - |
                  from myapp.tasks import cleanup_expired_sessions
                  cleanup_expired_sessions(max_age_hours=24)
              envFrom:
                - secretRef:
                    name: myapp-secrets
```

K8s Job patterns:
1. **`backoffLimit`** — retry count before marking job as failed
2. **`parallelism` + `completions`** — run N pods concurrently for M total tasks
3. **`concurrencyPolicy: Forbid`** — skip scheduled run if previous still active
4. **`activeDeadlineSeconds`** — hard timeout prevents hung jobs
5. **`ttlSecondsAfterFinished`** — auto-cleanup completed job pods"""
    ),
]
