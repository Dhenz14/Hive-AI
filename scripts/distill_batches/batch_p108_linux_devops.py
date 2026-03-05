"""Linux/DevOps — systemd services, nginx config, and shell scripting patterns."""

PAIRS = [
    (
        "devops/systemd",
        "Show systemd service patterns: unit files, socket activation, timers, and service management.",
        """systemd service patterns:

```ini
# --- /etc/systemd/system/myapp.service ---

[Unit]
Description=My Application Server
Documentation=https://docs.myapp.com
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=notify
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp

# Environment
EnvironmentFile=/opt/myapp/.env
Environment=PYTHONUNBUFFERED=1

# Execution
ExecStartPre=/opt/myapp/venv/bin/python -m myapp.check_db
ExecStart=/opt/myapp/venv/bin/uvicorn myapp:app --host 0.0.0.0 --port 8000 --workers 4
ExecReload=/bin/kill -HUP $MAINPID

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Timeouts
TimeoutStartSec=30
TimeoutStopSec=30
WatchdogSec=60

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/myapp/data /var/log/myapp
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
RestrictNamespaces=yes
RestrictSUIDSGID=yes
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

# Resource limits
LimitNOFILE=65536
MemoryMax=1G
CPUQuota=200%

[Install]
WantedBy=multi-user.target


# --- /etc/systemd/system/myapp-worker.service ---

[Unit]
Description=My App Background Worker
After=myapp.service
PartOf=myapp.service

[Service]
Type=simple
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp
EnvironmentFile=/opt/myapp/.env
ExecStart=/opt/myapp/venv/bin/python -m myapp.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target


# --- Timer unit (cron replacement) ---
# /etc/systemd/system/myapp-cleanup.timer

[Unit]
Description=Run cleanup every 6 hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target


# /etc/systemd/system/myapp-cleanup.service

[Unit]
Description=Cleanup old data

[Service]
Type=oneshot
User=myapp
ExecStart=/opt/myapp/venv/bin/python -m myapp.cleanup
```

```bash
# --- Service management ---

# Enable and start
sudo systemctl enable --now myapp.service

# Status and logs
systemctl status myapp.service
journalctl -u myapp.service -f          # Follow logs
journalctl -u myapp.service --since "1 hour ago"

# Reload after editing unit file
sudo systemctl daemon-reload
sudo systemctl restart myapp.service

# Timer management
sudo systemctl enable --now myapp-cleanup.timer
systemctl list-timers --all

# Check security hardening score
systemd-analyze security myapp.service

# Resource usage
systemctl show myapp.service --property=MemoryCurrent,CPUUsageNSec
```

systemd patterns:
1. **`Type=notify`** — service signals readiness (uvicorn/gunicorn support sd_notify)
2. **Security hardening** — `ProtectSystem=strict`, `NoNewPrivileges`, capability bounding
3. **`Restart=on-failure`** — auto-restart with rate limiting via `StartLimitBurst`
4. **Timer units** — cron replacement with `OnCalendar`, `Persistent` survives downtime
5. **`PartOf=`** — worker restarts/stops when main service restarts/stops"""
    ),
    (
        "devops/nginx-config",
        "Show nginx configuration patterns: reverse proxy, SSL/TLS, rate limiting, caching, and load balancing.",
        """nginx configuration patterns:

```nginx
# --- /etc/nginx/nginx.conf ---

user nginx;
worker_processes auto;
worker_rlimit_nofile 65535;
error_log /var/log/nginx/error.log warn;
pid /run/nginx.pid;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'rt=$request_time';
    access_log /var/log/nginx/access.log main buffer=32k;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    keepalive_requests 1000;

    # Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml image/svg+xml;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    # Upstream (load balancing)
    upstream app_servers {
        least_conn;  # Or: round_robin, ip_hash, random
        server 127.0.0.1:8001;
        server 127.0.0.1:8002;
        server 127.0.0.1:8003;
        keepalive 32;
    }

    # Cache zone
    proxy_cache_path /var/cache/nginx levels=1:2
                     keys_zone=app_cache:10m max_size=1g
                     inactive=60m use_temp_path=off;

    include /etc/nginx/conf.d/*.conf;
}


# --- /etc/nginx/conf.d/myapp.conf ---

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name myapp.com www.myapp.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name myapp.com www.myapp.com;

    # SSL/TLS
    ssl_certificate     /etc/letsencrypt/live/myapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # Static files (served directly by nginx)
    location /static/ {
        alias /opt/myapp/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # API with rate limiting
    location /api/ {
        limit_req zone=api burst=20 nodelay;

        proxy_pass http://app_servers;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;

        # Caching for GET requests
        proxy_cache app_cache;
        proxy_cache_methods GET HEAD;
        proxy_cache_valid 200 10m;
        proxy_cache_valid 404 1m;
        proxy_cache_bypass $http_cache_control;
        add_header X-Cache-Status $upstream_cache_status;
    }

    # Strict rate limit on login
    location /api/auth/login {
        limit_req zone=login burst=3 nodelay;
        limit_req_status 429;

        proxy_pass http://app_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://app_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }

    # SPA fallback (React/Vue/Angular)
    location / {
        root /opt/myapp/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

nginx patterns:
1. **`upstream` + `least_conn`** — load balancing across app server instances
2. **`limit_req_zone`** — per-IP rate limiting with burst allowance
3. **`proxy_cache`** — response caching with per-status TTLs and bypass headers
4. **`try_files $uri /index.html`** — SPA client-side routing fallback
5. **`ssl_protocols TLSv1.2 TLSv1.3`** — modern TLS only, with OCSP stapling"""
    ),
    (
        "devops/shell-scripting",
        "Show bash shell scripting patterns: safe defaults, argument parsing, logging, and common patterns.",
        """Bash shell scripting patterns:

```bash
#!/usr/bin/env bash

# --- Safe defaults ---

set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$'\\n\\t'       # Safer word splitting

# Trap for cleanup on exit
cleanup() {
    local exit_code=$?
    echo "Cleaning up..."
    rm -rf "${TEMP_DIR:-}"
    exit "$exit_code"
}
trap cleanup EXIT


# --- Logging ---

readonly LOG_FILE="/var/log/myapp/deploy.log"

log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" | tee -a "$LOG_FILE"
}

info()  { log "INFO"  "$@"; }
warn()  { log "WARN"  "$@" >&2; }
error() { log "ERROR" "$@" >&2; }
die()   { error "$@"; exit 1; }


# --- Argument parsing ---

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] <environment>

Deploy application to the specified environment.

Arguments:
  environment    Target environment (staging, production)

Options:
  -t, --tag TAG       Docker image tag (default: latest)
  -n, --dry-run       Show what would be done without executing
  -v, --verbose       Enable verbose output
  -h, --help          Show this help message

Examples:
  $(basename "$0") staging
  $(basename "$0") -t v1.2.3 production
  $(basename "$0") --dry-run production
EOF
}

# Defaults
TAG="latest"
DRY_RUN=false
VERBOSE=false

# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            die "Unknown option: $1"
            ;;
        *)
            break
            ;;
    esac
done

# Require positional argument
ENVIRONMENT="${1:?$(usage; echo; echo "Error: environment is required")}"
shift

# Validate
case "$ENVIRONMENT" in
    staging|production) ;;
    *) die "Invalid environment: $ENVIRONMENT (must be staging or production)" ;;
esac


# --- Confirmation prompt ---

confirm() {
    local prompt="${1:-Are you sure?}"
    read -rp "$prompt [y/N] " response
    [[ "$response" =~ ^[yY]$ ]]
}

if [[ "$ENVIRONMENT" == "production" ]] && ! "$DRY_RUN"; then
    confirm "Deploy $TAG to PRODUCTION?" || die "Aborted"
fi


# --- Run command (with dry-run support) ---

run() {
    if "$DRY_RUN"; then
        info "[DRY RUN] $*"
    else
        "$VERBOSE" && info "Running: $*"
        "$@"
    fi
}


# --- Retry with backoff ---

retry() {
    local max_attempts="$1"
    local delay="$1"
    shift 2
    local attempt=1

    until "$@"; do
        if (( attempt >= max_attempts )); then
            error "Failed after $max_attempts attempts: $*"
            return 1
        fi
        warn "Attempt $attempt failed, retrying in ${delay}s..."
        sleep "$delay"
        delay=$(( delay * 2 ))
        attempt=$(( attempt + 1 ))
    done
}


# --- Parallel execution ---

pids=()
for server in web-1 web-2 web-3; do
    (
        info "Deploying to $server..."
        run ssh "$server" "docker pull myapp:$TAG && docker restart myapp"
    ) &
    pids+=($!)
done

# Wait for all and check exit codes
failed=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failed=$(( failed + 1 ))
    fi
done
(( failed == 0 )) || die "$failed deployments failed"


# --- File operations ---

TEMP_DIR=$(mktemp -d)
readonly TEMP_DIR

# Safe file comparison and update
update_config() {
    local src="$1"
    local dest="$2"

    if [[ ! -f "$dest" ]] || ! diff -q "$src" "$dest" > /dev/null 2>&1; then
        info "Updating $dest"
        run cp "$src" "$dest"
        return 0
    fi
    info "$dest is up to date"
    return 1
}


info "Deployment complete: $TAG -> $ENVIRONMENT"
```

Shell scripting patterns:
1. **`set -euo pipefail`** — fail fast on errors, undefined vars, and broken pipes
2. **`trap cleanup EXIT`** — always clean up temp files, even on error
3. **Argument parsing** — `while/case` loop with `--long` and `-s` short options
4. **`run()` wrapper** — dry-run support by prefixing all side-effect commands
5. **Parallel with `wait`** — background jobs with PID tracking and failure counting"""
    ),
]
