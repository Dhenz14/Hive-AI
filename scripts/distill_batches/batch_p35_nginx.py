"""Nginx — reverse proxy, load balancing, caching, and security configuration."""

PAIRS = [
    (
        "devops/nginx-reverse-proxy",
        "Show Nginx reverse proxy patterns: upstream configuration, load balancing, SSL termination, rate limiting, and caching.",
        '''Nginx production reverse proxy configuration:

```nginx
# --- Main configuration ---

# /etc/nginx/nginx.conf
worker_processes auto;           # Match CPU cores
worker_rlimit_nofile 65535;
error_log /var/log/nginx/error.log warn;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    # --- Basic settings ---
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 10m;
    server_tokens off;          # Hide Nginx version

    # --- Logging ---
    log_format json_combined escape=json '{'
        '"time": "$time_iso8601",'
        '"remote_addr": "$remote_addr",'
        '"request": "$request",'
        '"status": $status,'
        '"body_bytes_sent": $body_bytes_sent,'
        '"request_time": $request_time,'
        '"upstream_response_time": "$upstream_response_time",'
        '"http_user_agent": "$http_user_agent",'
        '"request_id": "$request_id"'
    '}';
    access_log /var/log/nginx/access.log json_combined;

    # --- Gzip compression ---
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 5;
    gzip_types
        text/plain text/css text/xml text/javascript
        application/json application/javascript application/xml
        application/rss+xml image/svg+xml;

    # --- Rate limiting zones ---
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    # --- Cache zone ---
    proxy_cache_path /var/cache/nginx levels=1:2
        keys_zone=app_cache:10m max_size=1g
        inactive=60m use_temp_path=off;

    # --- Upstream (load balancing) ---
    upstream api_backend {
        least_conn;                     # Least connections algorithm
        keepalive 32;                   # Connection pooling

        server 10.0.1.1:8000 weight=5;
        server 10.0.1.2:8000 weight=5;
        server 10.0.1.3:8000 weight=3;
        server 10.0.1.4:8000 backup;   # Only used when others fail
    }

    upstream websocket_backend {
        ip_hash;  # Sticky sessions for WebSocket
        server 10.0.2.1:8080;
        server 10.0.2.2:8080;
    }

    # --- Redirect HTTP to HTTPS ---
    server {
        listen 80;
        server_name api.example.com;
        return 301 https://$server_name$request_uri;
    }

    # --- Main HTTPS server ---
    server {
        listen 443 ssl http2;
        server_name api.example.com;

        # --- SSL ---
        ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
        ssl_prefer_server_ciphers off;
        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:10m;
        ssl_session_tickets off;
        ssl_stapling on;
        ssl_stapling_verify on;

        # --- Security headers ---
        add_header X-Frame-Options DENY always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
        add_header Content-Security-Policy "default-src 'self'" always;
        add_header Referrer-Policy strict-origin-when-cross-origin always;

        # --- Request ID ---
        add_header X-Request-ID $request_id always;

        # --- API endpoints ---
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            limit_conn addr 10;

            proxy_pass http://api_backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header Connection "";  # Enable keepalive

            proxy_connect_timeout 5s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;

            # Error handling
            proxy_next_upstream error timeout http_502 http_503;
            proxy_next_upstream_tries 2;
        }

        # --- Cached endpoints ---
        location /api/public/ {
            proxy_pass http://api_backend;
            proxy_cache app_cache;
            proxy_cache_valid 200 10m;
            proxy_cache_valid 404 1m;
            proxy_cache_key "$request_uri";
            proxy_cache_use_stale error timeout updating http_500 http_502;
            add_header X-Cache-Status $upstream_cache_status;
        }

        # --- Login (strict rate limit) ---
        location /api/auth/login {
            limit_req zone=login burst=5 nodelay;
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        # --- WebSocket ---
        location /ws/ {
            proxy_pass http://websocket_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 3600s;  # Keep alive for 1 hour
        }

        # --- Static files (with caching) ---
        location /static/ {
            alias /var/www/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
            access_log off;
        }

        # --- Health check (no logging) ---
        location /health {
            access_log off;
            return 200 "ok";
            add_header Content-Type text/plain;
        }
    }
}
```

Key patterns:
1. **Load balancing** — `least_conn` for APIs, `ip_hash` for WebSockets
2. **Rate limiting** — per-IP limits with burst buffer
3. **Proxy caching** — cache public endpoints, serve stale on errors
4. **SSL hardening** — TLS 1.2+, HSTS, OCSP stapling
5. **Security headers** — CSP, X-Frame-Options, nosniff
6. **WebSocket proxy** — upgrade headers + long read timeout
7. **Request tracing** — `$request_id` propagated to backends'''
    ),
    (
        "devops/nginx-advanced",
        "Show advanced Nginx patterns: geo-based routing, A/B testing, request buffering, and Lua scripting with OpenResty.",
        '''Advanced Nginx patterns for complex routing:

```nginx
# --- Geo-based routing ---

geo $country {
    default         US;
    10.0.0.0/8      INTERNAL;
    192.168.0.0/16  INTERNAL;
}

# Route to regional backends
map $country $backend {
    default     us_backend;
    EU          eu_backend;
    INTERNAL    internal_backend;
}

upstream us_backend { server us.api.internal:8000; }
upstream eu_backend { server eu.api.internal:8000; }

server {
    location /api/ {
        proxy_pass http://$backend;
    }
}


# --- A/B testing with split_clients ---

split_clients "${remote_addr}" $ab_variant {
    10%  variant_b;
    *    variant_a;
}

upstream variant_a { server 10.0.1.1:8000; }
upstream variant_b { server 10.0.1.2:8000; }

server {
    location /api/ {
        proxy_pass http://$ab_variant;
        add_header X-Variant $ab_variant;
    }
}


# --- Canary deployment with map ---

map $cookie_canary $canary_backend {
    "true"  canary_backend;
    default stable_backend;
}

# Or percentage-based:
split_clients "${request_id}" $canary {
    5%  canary_backend;
    *   stable_backend;
}


# --- Request/response buffering ---

location /api/upload {
    client_max_body_size 100m;
    client_body_buffer_size 128k;

    # Buffer request body before proxying (reduces upstream connection time)
    proxy_request_buffering on;

    # Don't buffer response (for streaming)
    proxy_buffering off;

    proxy_pass http://upload_backend;
}

location /api/stream {
    proxy_pass http://api_backend;
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
}


# --- Access control ---

# Allow list for admin endpoints
location /admin/ {
    allow 10.0.0.0/8;
    allow 192.168.1.0/24;
    deny all;
    proxy_pass http://admin_backend;
}

# Block bad bots
map $http_user_agent $bad_bot {
    default         0;
    ~*crawl         1;
    ~*bot           1;
    ~*spider        1;
    ""              1;  # Empty user-agent
}

server {
    if ($bad_bot) {
        return 403;
    }
}


# --- Custom error pages ---

error_page 502 503 504 /50x.html;
location = /50x.html {
    root /usr/share/nginx/html;
    internal;
}

error_page 429 /rate_limited.json;
location = /rate_limited.json {
    internal;
    default_type application/json;
    return 429 '{"error": "rate_limited", "message": "Too many requests"}';
}


# --- Conditional logging ---

# Don't log health checks
map $request_uri $loggable {
    /health     0;
    /metrics    0;
    default     1;
}

access_log /var/log/nginx/access.log combined if=$loggable;


# --- Proxy header manipulation ---

location /api/ {
    proxy_pass http://api_backend;

    # Hide upstream headers
    proxy_hide_header X-Powered-By;
    proxy_hide_header Server;

    # Add CORS for specific origins
    set $cors_origin "";
    if ($http_origin ~* "^https://(app|admin)\\.example\\.com$") {
        set $cors_origin $http_origin;
    }
    add_header Access-Control-Allow-Origin $cors_origin always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;

    if ($request_method = OPTIONS) {
        add_header Access-Control-Max-Age 86400;
        return 204;
    }
}
```

Advanced patterns:
1. **Geo routing** — route to nearest regional backend
2. **A/B testing** — `split_clients` for percentage-based traffic split
3. **Canary deploys** — cookie or percentage-based routing to new version
4. **Access control** — IP allow-lists for admin, bot blocking
5. **Conditional logging** — skip health checks and metrics endpoints
6. **CORS handling** — origin validation at proxy level'''
    ),
]
"""
