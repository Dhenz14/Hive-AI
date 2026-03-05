"""Kubernetes — deployments, services, config, autoscaling, and operational patterns."""

PAIRS = [
    (
        "k8s/deployment-patterns",
        "Show Kubernetes deployment patterns: Deployment, Service, ConfigMap, HPA, PDB, and health checks.",
        """Kubernetes deployment patterns:

```yaml
# --- Deployment with best practices ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
  labels:
    app: api
    version: v2.1.0
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # Zero-downtime
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
        version: v2.1.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: api
      terminationGracePeriodSeconds: 60
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api

      containers:
        - name: api
          image: registry.example.com/api:v2.1.0
          ports:
            - containerPort: 8080
              name: http

          # Resource limits
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi

          # Environment from ConfigMap and Secret
          envFrom:
            - configMapRef:
                name: api-config
            - secretRef:
                name: api-secrets

          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName

          # Health checks
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            failureThreshold: 30
            periodSeconds: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 15
            timeoutSeconds: 3
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2

          # Graceful shutdown
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}

      # Security context
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault


---
# --- Service ---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: api
  ports:
    - port: 80
      targetPort: http
      protocol: TCP


---
# --- HPA (Horizontal Pod Autoscaler) ---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 20
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
          value: 25
          periodSeconds: 120
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


---
# --- PodDisruptionBudget ---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api
  namespace: production
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: api


---
# --- ConfigMap ---
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
  namespace: production
data:
  LOG_LEVEL: "info"
  DATABASE_POOL_SIZE: "20"
  CACHE_TTL: "300"
  CORS_ORIGIN: "https://app.example.com"
```

Kubernetes patterns:
1. **`maxUnavailable: 0`** — zero-downtime rolling updates
2. **Three probes** — startup (slow init), liveness (restart if stuck), readiness (traffic routing)
3. **`preStop` hook** — delay shutdown so in-flight requests complete
4. **`topologySpreadConstraints`** — spread pods across zones for HA
5. **PDB** — prevent disruptions from taking below minimum during upgrades"""
    ),
    (
        "k8s/ingress-networking",
        "Show Kubernetes networking patterns: Ingress, NetworkPolicy, and service mesh basics.",
        """Kubernetes networking patterns:

```yaml
# --- Ingress with TLS and path routing ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: production
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/use-regex: "true"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
        - app.example.com
      secretName: app-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /v1
            pathType: Prefix
            backend:
              service:
                name: api-v1
                port:
                  number: 80
          - path: /v2
            pathType: Prefix
            backend:
              service:
                name: api-v2
                port:
                  number: 80

    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 80


---
# --- NetworkPolicy (micro-segmentation) ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-network-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow from ingress controller
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - port: 8080
          protocol: TCP

    # Allow from other services in same namespace
    - from:
        - podSelector:
            matchLabels:
              role: backend
      ports:
        - port: 8080
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP

    # Allow database
    - to:
        - podSelector:
            matchLabels:
              app: postgres
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
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - port: 443


---
# --- Default deny all traffic in namespace ---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress


---
# --- ExternalSecret (from AWS Secrets Manager) ---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-secrets
  namespace: production
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets
    kind: ClusterSecretStore
  target:
    name: api-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: production/api/database-url
    - secretKey: API_KEY
      remoteRef:
        key: production/api/api-key
```

Networking patterns:
1. **Default deny** — start with deny-all, then whitelist needed traffic
2. **NetworkPolicy** — microsegmentation at pod level (API can only reach DB, Redis)
3. **Ingress** — TLS termination, rate limiting, path-based routing
4. **ExternalSecrets** — sync secrets from vault/cloud provider to k8s
5. **Egress control** — restrict outbound to only needed destinations"""
    ),
    (
        "k8s/helm-kustomize",
        "Show Kubernetes templating with Helm charts and Kustomize overlays for multi-environment deployments.",
        """Helm and Kustomize patterns:

```yaml
# --- Helm chart values ---
# charts/api/values.yaml (defaults)

replicaCount: 2
image:
  repository: registry.example.com/api
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
    cpu: "1"
    memory: 512Mi

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilization: 70

env: {}
secrets: {}

# --- Environment-specific values ---
# values-production.yaml
replicaCount: 3
image:
  tag: v2.1.0
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: "2"
    memory: 1Gi
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
env:
  LOG_LEVEL: info
  CACHE_TTL: "300"


# --- Helm template ---
# charts/api/templates/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "api.fullname" . }}
  labels:
    {{- include "api.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "api.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "api.selectorLabels" . | nindent 8 }}
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          ports:
            - containerPort: 8080
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          {{- if .Values.env }}
          envFrom:
            - configMapRef:
                name: {{ include "api.fullname" . }}
          {{- end }}
```

```yaml
# --- Kustomize base ---
# base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - hpa.yaml
commonLabels:
  app: api

# --- Kustomize overlay ---
# overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
namespace: production
namePrefix: prod-

# Patch replicas and resources
patches:
  - target:
      kind: Deployment
      name: api
    patch: |
      - op: replace
        path: /spec/replicas
        value: 3
      - op: replace
        path: /spec/template/spec/containers/0/resources/requests/cpu
        value: 500m
      - op: replace
        path: /spec/template/spec/containers/0/resources/requests/memory
        value: 512Mi

# Environment-specific config
configMapGenerator:
  - name: api-config
    literals:
      - LOG_LEVEL=info
      - DATABASE_POOL_SIZE=20
    options:
      disableNameSuffixHash: true

images:
  - name: registry.example.com/api
    newTag: v2.1.0

# Apply: kubectl apply -k overlays/production/
```

Templating patterns:
1. **Helm** — full templating engine with values files per environment
2. **Kustomize** — patch-based overlays without templates (built into kubectl)
3. **Config checksums** — annotation hash triggers rollout when ConfigMap changes
4. **`configMapGenerator`** — Kustomize auto-generates ConfigMaps from literals/files
5. **Image tags** — override in overlay, never use `latest` in production"""
    ),
]
