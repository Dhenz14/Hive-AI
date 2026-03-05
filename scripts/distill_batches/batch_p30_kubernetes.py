"""Kubernetes — deployments, services, scaling, operators, and production patterns."""

PAIRS = [
    (
        "devops/kubernetes-deployments",
        "Show Kubernetes deployment patterns: rolling updates, canary deployments, resource management, and health checks with practical manifests.",
        '''Kubernetes deployment patterns for production:

```yaml
# --- Production-ready Deployment ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  labels:
    app: api-server
    version: v1.2.0
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1    # At most 1 pod down during update
      maxSurge: 1           # At most 1 extra pod during update
  template:
    metadata:
      labels:
        app: api-server
        version: v1.2.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: api-server
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000

      containers:
        - name: api
          image: registry.example.com/api:v1.2.0
          ports:
            - containerPort: 8080
              name: http
              protocol: TCP

          # Resource management
          resources:
            requests:
              cpu: "250m"      # 0.25 vCPU guaranteed
              memory: "256Mi"  # 256MB guaranteed
            limits:
              cpu: "1000m"     # 1 vCPU max
              memory: "512Mi"  # 512MB max (OOMKilled if exceeded)

          # Startup probe (slow-starting apps)
          startupProbe:
            httpGet:
              path: /health
              port: http
            failureThreshold: 30
            periodSeconds: 10
            # Gives app up to 300s to start

          # Readiness probe (traffic routing)
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
            # Failed = removed from Service endpoints

          # Liveness probe (restart on hang)
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
            # Failed = pod is restarted

          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: api-secrets
                  key: database-url
            - name: LOG_LEVEL
              valueFrom:
                configMapKeyRef:
                  name: api-config
                  key: log-level
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name

          # Graceful shutdown
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
          terminationGracePeriodSeconds: 30

      # Pod topology spread (distribute across nodes/zones)
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api-server

      # Pod disruption budget (maintain availability)
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: api-server
                topologyKey: kubernetes.io/hostname

---
# --- HorizontalPodAutoscaler ---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
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
    # Custom metric (requests per second)
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "1000"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60

---
# --- PodDisruptionBudget ---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server
spec:
  minAvailable: 2  # At least 2 pods must be available
  selector:
    matchLabels:
      app: api-server

---
# --- Service ---
apiVersion: v1
kind: Service
metadata:
  name: api-server
spec:
  selector:
    app: api-server
  ports:
    - port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
```

Key patterns:
1. **Rolling updates** — zero-downtime deploys with maxUnavailable/maxSurge
2. **Three probes** — startup (slow starts), readiness (traffic), liveness (restarts)
3. **Resource requests/limits** — prevent noisy neighbors, enable autoscaling
4. **Pod topology spread** — distribute across zones for HA
5. **PDB** — prevent disruptions from draining too many pods
6. **HPA** — scale based on CPU, memory, or custom metrics
7. **Graceful shutdown** — preStop hook + terminationGracePeriodSeconds'''
    ),
    (
        "devops/kubernetes-networking",
        "Explain Kubernetes networking: Services, Ingress, NetworkPolicies, and service mesh integration with Istio.",
        '''Kubernetes networking from pods to production:

```yaml
# --- Ingress with TLS ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
      secretName: api-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /api/v1
            pathType: Prefix
            backend:
              service:
                name: api-server
                port:
                  number: 80
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: websocket-server
                port:
                  number: 80

---
# --- NetworkPolicy (micro-segmentation) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-server-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow traffic from ingress controller
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - port: 8080
    # Allow traffic from monitoring
    - from:
        - namespaceSelector:
            matchLabels:
              name: monitoring
      ports:
        - port: 8080
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
    # Allow database
    - to:
        - podSelector:
            matchLabels:
              app: postgresql
      ports:
        - port: 5432
    # Allow Redis
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - port: 6379
    # Allow external HTTPS
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - port: 443

---
# --- Default deny all traffic (zero-trust) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}  # Apply to all pods
  policyTypes:
    - Ingress
    - Egress
  # No rules = deny all (except DNS which many CNIs exempt)
```

```python
# --- Service mesh concepts (Istio) ---

# VirtualService — traffic routing
ISTIO_VIRTUAL_SERVICE = """
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: api-server
spec:
  hosts:
    - api-server
  http:
    # Canary: 90% to v1, 10% to v2
    - route:
        - destination:
            host: api-server
            subset: v1
          weight: 90
        - destination:
            host: api-server
            subset: v2
          weight: 10
      # Retry policy
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: 5xx,reset,connect-failure
      # Timeout
      timeout: 10s
      # Fault injection (chaos testing)
      # fault:
      #   delay:
      #     percentage:
      #       value: 5
      #     fixedDelay: 3s
"""

# DestinationRule — circuit breaker + load balancing
ISTIO_DESTINATION_RULE = """
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: api-server
spec:
  host: api-server
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        h2UpgradePolicy: DEFAULT
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
    loadBalancer:
      simple: LEAST_REQUEST
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
"""
```

Networking layers:
1. **Pod-to-Pod** — flat network, every pod can reach every pod (by default)
2. **Service** — stable DNS name + load balancing across pods
3. **Ingress** — HTTP routing, TLS termination, external access
4. **NetworkPolicy** — firewall rules between pods/namespaces
5. **Service mesh** — mTLS, observability, traffic management, circuit breaking'''
    ),
]
