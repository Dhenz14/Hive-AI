"""Code translation pairs: Between YAML, JSON, TOML, INI, and env files."""

PAIRS = [
    (
        "code-translation/config-formats",
        r'''Convert this docker-compose.yml to equivalent environment variables and a .env file:

version: "3.8"
services:
  web:
    image: myapp:latest
    ports:
      - "8080:3000"
    environment:
      NODE_ENV: production
      DATABASE_URL: postgres://user:pass@db:5432/myapp
      REDIS_URL: redis://cache:6379
      JWT_SECRET: supersecret123
      LOG_LEVEL: info
      MAX_UPLOAD_MB: 50
    depends_on:
      - db
      - cache
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: "0.5"
          memory: 512M

  db:
    image: postgres:15
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: myapp
    volumes:
      - pgdata:/var/lib/postgresql/data

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb

volumes:
  pgdata:''',
        r'''<think>
Converting docker-compose YAML to .env file. I need to:

1. Extract all environment variables from all services
2. Handle the fact that different services might have conflicting variable names (POSTGRES_USER vs the web app's DATABASE_URL)
3. Add prefixes for service-specific variables
4. Some compose settings (ports, replicas, resource limits) don't directly map to env vars but could be useful as comments

The tricky part: the DATABASE_URL contains the db credentials inline. In a .env file, you'd typically reference other variables or keep them consistent. Also, secrets like JWT_SECRET should be marked as needing replacement in production.

I should also show the docker-compose.yml modified to use the .env file via env_file or variable substitution (${}), since that's the practical use case.
</think>

```ini
# .env file
# Application settings
NODE_ENV=production
LOG_LEVEL=info
MAX_UPLOAD_MB=50
JWT_SECRET=supersecret123

# Database
POSTGRES_USER=user
POSTGRES_PASSWORD=pass
POSTGRES_DB=myapp
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# Redis
REDIS_HOST=cache
REDIS_PORT=6379
REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}
REDIS_MAXMEMORY=256mb

# Deployment
WEB_PORT=8080
WEB_INTERNAL_PORT=3000
WEB_REPLICAS=3
WEB_CPU_LIMIT=0.5
WEB_MEMORY_LIMIT=512M
```

```yaml
# Updated docker-compose.yml using .env file
version: "3.8"
services:
  web:
    image: myapp:latest
    ports:
      - "${WEB_PORT}:${WEB_INTERNAL_PORT}"
    env_file: .env
    depends_on:
      - db
      - cache
    deploy:
      replicas: ${WEB_REPLICAS}
      resources:
        limits:
          cpus: "${WEB_CPU_LIMIT}"
          memory: ${WEB_MEMORY_LIMIT}

  db:
    image: postgres:15
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory ${REDIS_MAXMEMORY}

volumes:
  pgdata:
```

Key translation notes:

- YAML nested structure flattens to KEY=VALUE lines
- Service-specific settings get prefixed (WEB_PORT, WEB_REPLICAS)
- Inline credentials in DATABASE_URL are split into separate vars and composed with ${} substitution
- Docker Compose auto-reads .env in the same directory
- `env_file: .env` passes all vars to the container; `environment:` with `${}` only passes selected vars
- Secrets (JWT_SECRET, POSTGRES_PASSWORD) should use Docker secrets or a vault in production, not .env files
- Comments with # work in .env files but not in all parsers (python-dotenv supports them, Docker Compose supports them)''',
    ),
    (
        "code-translation/config-formats",
        r'''Convert this pyproject.toml configuration to the equivalent setup.cfg and setup.py:

[project]
name = "mypackage"
version = "2.1.0"
description = "A useful Python package"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.9"
authors = [
    {name = "Alice Smith", email = "alice@example.com"},
]
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
]
dependencies = [
    "requests>=2.28",
    "click>=8.0",
    "pydantic>=2.0,<3.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "black", "mypy"]
docs = ["sphinx>=5.0", "sphinx-rtd-theme"]

[project.scripts]
mycommand = "mypackage.cli:main"

[project.urls]
Homepage = "https://github.com/alice/mypackage"
Issues = "https://github.com/alice/mypackage/issues"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.black]
line-length = 88
target-version = ["py39"]

[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"''',
        r'''```ini
# setup.cfg -- declarative configuration equivalent

[metadata]
name = mypackage
version = 2.1.0
description = A useful Python package
long_description = file: README.md
long_description_content_type = text/markdown
license = MIT
author = Alice Smith
author_email = alice@example.com
url = https://github.com/alice/mypackage
project_urls =
    Issues = https://github.com/alice/mypackage/issues
classifiers =
    Programming Language :: Python :: 3
    License :: OSI Approved :: MIT License
    Operating System :: OS Independent

[options]
python_requires = >=3.9
packages = find:
install_requires =
    requests>=2.28
    click>=8.0
    pydantic>=2.0,<3.0

[options.extras_require]
dev =
    pytest>=7.0
    black
    mypy
docs =
    sphinx>=5.0
    sphinx-rtd-theme

[options.entry_points]
console_scripts =
    mycommand = mypackage.cli:main

[tool:pytest]
testpaths = tests
addopts = -v --tb=short
```

```python
# setup.py -- minimal shim (needed for editable installs with older pip)
from setuptools import setup
setup()
```

Key differences between formats:

- TOML uses `[sections]` with typed values (arrays, inline tables); setup.cfg uses INI-style `key = value` with multi-line lists
- `dependencies = ["requests>=2.28"]` (TOML array) -> `install_requires = \n    requests>=2.28` (indented continuation lines)
- `authors = [{name = "Alice", email = "..."}]` (TOML inline table) -> separate `author` and `author_email` fields
- `[project.scripts]` -> `[options.entry_points] / console_scripts`
- `readme = "README.md"` -> `long_description = file: README.md` with explicit content type
- `[tool.pytest.ini_options]` -> `[tool:pytest]` (colon instead of dot in setup.cfg)
- `[tool.black]` has no setup.cfg equivalent -- Black reads from pyproject.toml only
- pyproject.toml is the modern standard (PEP 621); setup.cfg is legacy but still widely supported''',
    ),
    (
        "code-translation/config-formats",
        r'''Convert this Kubernetes YAML deployment to a Helm values.yaml with a template:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-api
  labels:
    app: web-api
    env: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web-api
  template:
    metadata:
      labels:
        app: web-api
    spec:
      containers:
        - name: web-api
          image: registry.example.com/web-api:v1.4.2
          ports:
            - containerPort: 8080
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-secret
                  key: url
            - name: LOG_LEVEL
              value: "info"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: web-api
spec:
  selector:
    app: web-api
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP''',
        r'''```yaml
# values.yaml -- parameterized configuration

replicaCount: 3

image:
  repository: registry.example.com/web-api
  tag: v1.4.2
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

containerPort: 8080

env:
  LOG_LEVEL: info

secrets:
  dbSecretName: db-secret
  dbSecretKey: url

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

readinessProbe:
  path: /health
  initialDelaySeconds: 5
  periodSeconds: 10

livenessProbe:
  path: /health
  initialDelaySeconds: 15
  periodSeconds: 20

labels:
  env: production
```

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "chart.fullname" . }}
  labels:
    app: {{ include "chart.fullname" . }}
    env: {{ .Values.labels.env }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ include "chart.fullname" . }}
  template:
    metadata:
      labels:
        app: {{ include "chart.fullname" . }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.containerPort }}
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.secrets.dbSecretName }}
                  key: {{ .Values.secrets.dbSecretKey }}
            - name: LOG_LEVEL
              value: {{ .Values.env.LOG_LEVEL | quote }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: {{ .Values.readinessProbe.path }}
              port: {{ .Values.containerPort }}
            initialDelaySeconds: {{ .Values.readinessProbe.initialDelaySeconds }}
            periodSeconds: {{ .Values.readinessProbe.periodSeconds }}
          livenessProbe:
            httpGet:
              path: {{ .Values.livenessProbe.path }}
              port: {{ .Values.containerPort }}
            initialDelaySeconds: {{ .Values.livenessProbe.initialDelaySeconds }}
            periodSeconds: {{ .Values.livenessProbe.periodSeconds }}
```

```yaml
# templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "chart.fullname" . }}
spec:
  selector:
    app: {{ include "chart.fullname" . }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
  type: {{ .Values.service.type }}
```

Key translation notes:

- Hard-coded values extracted into `values.yaml` as parameterized defaults
- Image tag separated from repository so you can override just the tag during deploys
- `resources` block uses `toYaml` helper to pass through as-is (keeps values.yaml flexible)
- `{{ include "chart.fullname" . }}` replaces hard-coded "web-api" name for reusability
- Override for staging: `helm install --set replicaCount=1,image.tag=v1.5.0,labels.env=staging`''',
    ),
    (
        "code-translation/config-formats",
        r'''Convert this JSON configuration to TOML and YAML, preserving all structure:

{
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "myapp",
    "pool": {
      "min": 2,
      "max": 20,
      "idle_timeout": 300
    },
    "ssl": {
      "enabled": true,
      "ca_file": "/etc/ssl/certs/db-ca.pem"
    }
  },
  "cache": {
    "backend": "redis",
    "url": "redis://localhost:6379/0",
    "ttl": 3600,
    "prefix": "myapp:"
  },
  "logging": {
    "level": "info",
    "format": "json",
    "outputs": ["stdout", "file"],
    "file": {
      "path": "/var/log/myapp/app.log",
      "max_size_mb": 100,
      "rotate": 5
    }
  },
  "features": {
    "enable_signup": true,
    "enable_oauth": false,
    "rate_limit": {
      "requests_per_minute": 60,
      "burst": 10
    },
    "allowed_origins": [
      "https://myapp.com",
      "https://staging.myapp.com"
    ]
  }
}''',
        r'''```toml
# config.toml

[database]
host = "localhost"
port = 5432
name = "myapp"

[database.pool]
min = 2
max = 20
idle_timeout = 300

[database.ssl]
enabled = true
ca_file = "/etc/ssl/certs/db-ca.pem"

[cache]
backend = "redis"
url = "redis://localhost:6379/0"
ttl = 3600
prefix = "myapp:"

[logging]
level = "info"
format = "json"
outputs = ["stdout", "file"]

[logging.file]
path = "/var/log/myapp/app.log"
max_size_mb = 100
rotate = 5

[features]
enable_signup = true
enable_oauth = false
allowed_origins = [
    "https://myapp.com",
    "https://staging.myapp.com",
]

[features.rate_limit]
requests_per_minute = 60
burst = 10
```

```yaml
# config.yaml

database:
  host: localhost
  port: 5432
  name: myapp
  pool:
    min: 2
    max: 20
    idle_timeout: 300
  ssl:
    enabled: true
    ca_file: /etc/ssl/certs/db-ca.pem

cache:
  backend: redis
  url: redis://localhost:6379/0
  ttl: 3600
  prefix: "myapp:"

logging:
  level: info
  format: json
  outputs:
    - stdout
    - file
  file:
    path: /var/log/myapp/app.log
    max_size_mb: 100
    rotate: 5

features:
  enable_signup: true
  enable_oauth: false
  rate_limit:
    requests_per_minute: 60
    burst: 10
  allowed_origins:
    - https://myapp.com
    - https://staging.myapp.com
```

Key differences between the three formats:

- JSON: no comments, strict syntax (trailing commas forbidden), all strings quoted, verbose for nested config
- TOML: uses `[section.subsection]` headers to flatten nesting. Supports comments. More readable for flat/shallow config. Arrays can be inline `[a, b]` or multi-line
- YAML: uses indentation for nesting (no braces). Most compact for deeply nested structures. Supports comments. Arrays use `- item` syntax. Gotcha: unquoted strings like `yes`, `no`, `on`, `off` are parsed as booleans in YAML 1.1
- TOML has no null type; JSON and YAML do. If a key can be null, TOML needs a sentinel value or the key must be absent
- YAML `prefix: "myapp:"` needs quotes because the colon could be ambiguous; TOML always quotes strings; JSON always quotes strings''',
    ),
    (
        "code-translation/config-formats",
        r'''Convert this Nginx configuration to a Caddy equivalent:

server {
    listen 80;
    server_name myapp.com www.myapp.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name myapp.com www.myapp.com;

    ssl_certificate /etc/letsencrypt/live/myapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.com/privkey.pem;

    root /var/www/myapp/public;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location ~* \.(js|css|png|jpg|gif|ico|svg|woff2?)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    gzip_min_length 256;
}''',
        r'''<think>
Nginx to Caddy translation. Caddy's Caddyfile format is much more concise and handles several things automatically:

1. HTTPS/TLS: Caddy auto-provisions Let's Encrypt certificates. No need to specify cert paths or the HTTP->HTTPS redirect -- it's automatic.

2. HTTP/2: Enabled by default in Caddy.

3. Gzip: Caddy calls it "encode" and supports gzip and zstd.

4. Proxy headers: Caddy's reverse_proxy automatically sets X-Forwarded-For, X-Forwarded-Proto, X-Real-IP, and Host.

5. WebSocket proxying: Caddy's reverse_proxy handles WebSocket upgrade automatically -- no special config needed.

6. try_files: Caddy has `try_files` as a directive too.

7. Static file caching with regex location matching: Caddy uses `@matcher` syntax or `path` matchers with wildcards.

The Caddy config will be significantly shorter because of all the automatic behavior.
</think>

```
# Caddyfile

myapp.com, www.myapp.com {
    # TLS is automatic -- Caddy provisions Let's Encrypt certs
    # HTTP -> HTTPS redirect is automatic
    # HTTP/2 is on by default

    # Gzip and zstd compression
    encode gzip zstd

    # API reverse proxy
    handle /api/* {
        reverse_proxy localhost:3000
        # Headers like X-Forwarded-For are set automatically
    }

    # WebSocket -- no special config needed, reverse_proxy handles it
    handle /ws {
        reverse_proxy localhost:3000
    }

    # Static file caching
    @static path *.js *.css *.png *.jpg *.gif *.ico *.svg *.woff *.woff2
    header @static Cache-Control "public, immutable, max-age=2592000"

    # SPA fallback: serve files, fall back to index.html
    root * /var/www/myapp/public
    try_files {path} {path}/ /index.html
    file_server
}
```

What Caddy handles automatically (no config needed):

- **HTTPS**: Auto-provisions Let's Encrypt certificates, no `ssl_certificate` paths
- **HTTP redirect**: `listen 80` + `return 301 https://` block is unnecessary
- **HTTP/2**: Enabled by default, no `http2` flag needed
- **Proxy headers**: `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Real-IP`, `Host` are set automatically by `reverse_proxy`
- **WebSocket upgrade**: `reverse_proxy` detects and handles Upgrade/Connection headers automatically

Key syntax differences:

- Nginx `server {}` blocks -> Caddy site address at top
- Nginx `location /path {}` -> Caddy `handle /path/* {}` (note the `*` wildcard)
- Nginx regex locations `~*` -> Caddy `@matcher path` with glob patterns
- Nginx `expires 30d` -> Caddy `header Cache-Control "max-age=2592000"`
- Nginx `gzip on; gzip_types ...` -> Caddy `encode gzip zstd` (auto-detects content types)
- Nginx: ~50 lines, Caddy: ~20 lines for identical functionality''',
    ),
]
