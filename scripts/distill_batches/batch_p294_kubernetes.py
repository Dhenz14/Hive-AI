"""Kubernetes patterns — deployments, services, HPA, operators."""

PAIRS = [
    (
        "devops/k8s-deployment",
        "Show Kubernetes deployment patterns: rolling updates, readiness probes, resource management, and HPA autoscaling.",
        '''Kubernetes deployment with autoscaling:

```yaml
# Deployment with rolling updates and probes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  labels:
    app: api-server
    version: v2.3.1
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1          # 1 extra pod during update
      maxUnavailable: 0    # Zero downtime
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
        version: v2.3.1
    spec:
      containers:
        - name: api
          image: myregistry/api-server:v2.3.1
          ports:
            - containerPort: 8000
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 20
          startupProbe:
            httpGet:
              path: /health/startup
              port: 8000
            failureThreshold: 30
            periodSeconds: 2
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
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api-server
---
# Horizontal Pod Autoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
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
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "100"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
---
# Service
apiVersion: v1
kind: Service
metadata:
  name: api-server
spec:
  selector:
    app: api-server
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

Key patterns:
1. **Three probes** — startup (slow init), readiness (can serve), liveness (not hung)
2. **Zero-downtime deploy** — maxSurge=1, maxUnavailable=0; new pods ready before old terminate
3. **Topology spread** — distribute pods across nodes; survive node failure
4. **HPA with custom metrics** — scale on CPU, memory, and business metrics (RPS)
5. **Scale-down stabilization** — 5-minute window prevents flapping; scale up faster than down'''
    ),
    (
        "devops/k8s-networking",
        "Show Kubernetes networking: Ingress, NetworkPolicy, service mesh basics, and TLS termination.",
        '''Kubernetes networking patterns:

```yaml
# Ingress with TLS and path-based routing
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
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
          - path: /api/v2
            pathType: Prefix
            backend:
              service:
                name: api-server-v2
                port:
                  number: 80
          - path: /api/v1
            pathType: Prefix
            backend:
              service:
                name: api-server-v1
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
# NetworkPolicy: restrict pod communication
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-server-policy
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
        - podSelector:
            matchLabels:
              app: monitoring
      ports:
        - port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - port: 6379
    - to:  # Allow DNS
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
```

Key patterns:
1. **Path-based routing** — different services behind same domain; version-based routing
2. **TLS termination** — cert-manager auto-provisions Let's Encrypt certificates
3. **Rate limiting** — nginx annotations for per-IP rate limits at ingress level
4. **NetworkPolicy** — whitelist ingress/egress; default-deny for zero trust
5. **DNS egress** — always allow port 53 UDP; pods need DNS resolution'''
    ),
]
"""
