"""
Code explanation training pairs - Docker configs, CI/CD pipelines, nginx configs
"""

pairs = [
    {
        "instruction": r'''Walk me through this Dockerfile:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production && \
    cp -R node_modules /prod_modules && \
    npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=builder /prod_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3000/health || exit 1
CMD ["node", "dist/server.js"]
```''',
        "output": r'''This is a multi-stage Docker build optimized for small, secure production images.

**Stage 1 -- builder:**

1. Starts from `node:20-alpine` (Alpine Linux is ~5MB vs ~900MB for full Debian).
2. Copies only `package.json` and `package-lock.json` first. This is a layer caching optimization -- these files change rarely, so npm install is cached unless dependencies change.
3. The `RUN` line does something clever: installs production deps first, copies them aside to `/prod_modules`, then runs a full `npm ci` (including devDependencies like TypeScript, build tools). This way the production node_modules are saved before dev deps pollute them.
4. Copies the full source code and runs the build.

**Stage 2 -- production image:**

1. Starts from a fresh `node:20-alpine` -- nothing from the builder stage carries over except what is explicitly COPYed. Build tools, source code, and dev dependencies are gone.
2. Creates a non-root user (`appuser`) and group. Running as root in containers is a security risk -- if the app is compromised, the attacker gets root in the container.
3. Copies only what is needed: production node_modules, compiled output, and package.json.
4. `USER appuser` switches to the non-root user for all subsequent commands.
5. `HEALTHCHECK` makes Docker (and orchestrators like Kubernetes) aware of the app's health status.

**Result:** The final image contains only the Node.js runtime, production dependencies, and compiled JavaScript. No TypeScript compiler, no source code, no devDependencies. This typically cuts image size by 60-80%.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a GitHub Actions workflow. Let me trace through the jobs and steps.
</think>

Explain this GitHub Actions workflow:

```yaml
name: CI/CD Pipeline
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
      - run: npm ci
      - run: npm test -- --coverage
      - uses: codecov/codecov-action@v3
        if: matrix.node-version == 20

  deploy:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-arn: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - run: aws s3 sync dist/ s3://${{ secrets.S3_BUCKET }} --delete
      - run: aws cloudfront create-invalidation --distribution-id ${{ secrets.CF_DIST_ID }} --paths "/*"
```''',
        "output": r'''<think>
This is a CI/CD pipeline with a test matrix and conditional deployment. I should explain the trigger conditions, matrix strategy, and the deployment flow.
</think>

This pipeline runs tests on every push and PR to main, and deploys to AWS only when code is merged to main.

**Triggers (`on`):** Fires on pushes to main (direct commits or merged PRs) and on pull requests targeting main.

**Test job:**

The `matrix` strategy runs the test job three times in parallel -- once for each Node version (18, 20, 22). This ensures the code works across supported versions.

- `actions/checkout@v4` clones the repo.
- `actions/setup-node@v4` installs the specified Node version. The `cache: 'npm'` option caches the npm cache directory across runs, speeding up `npm ci`.
- Tests run with coverage reporting.
- Coverage is uploaded to Codecov, but only from the Node 20 run (`if: matrix.node-version == 20`). Uploading three identical coverage reports would be wasteful.

**Deploy job:**

- `needs: test` -- waits for ALL three test matrix runs to pass before deploying.
- The `if` condition ensures deployment only happens on pushes to main, not on PRs. This is critical -- you do not want PRs deploying to production.
- `environment: production` enables GitHub's environment protection rules (manual approvals, required reviewers).
- Uses OIDC role assumption (`role-to-arn`) instead of long-lived AWS access keys -- a security best practice.
- `s3 sync --delete` uploads the build and removes files that no longer exist in the build output.
- CloudFront invalidation clears the CDN cache so users get the new version immediately. The `/*` path invalidates everything.'''
    },
    {
        "instruction": r'''Explain this nginx configuration:

```nginx
upstream api_servers {
    least_conn;
    server 10.0.1.10:8080 weight=3;
    server 10.0.1.11:8080 weight=2;
    server 10.0.1.12:8080 backup;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/api.pem;
    ssl_certificate_key /etc/ssl/private/api.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    location /api/ {
        proxy_pass http://api_servers/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }

    location ~* \.(js|css|png|jpg|svg|woff2?)$ {
        root /var/www/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```''',
        "output": r'''This configures nginx as a reverse proxy with load balancing, SSL termination, and static file serving.

**Upstream block (load balancing):**

- `least_conn` -- routes each request to the server with the fewest active connections. Better than the default round-robin for requests with varying processing times.
- `weight=3` and `weight=2` -- server 10 gets roughly 60% of traffic, server 11 gets 40%. Higher weight means more requests.
- `backup` -- server 12 only receives traffic when BOTH primary servers are down. It is a failover node.

**SSL configuration:**

- `listen 443 ssl http2` -- HTTPS on port 443 with HTTP/2 enabled (multiplexed connections, header compression).
- Only TLS 1.2 and 1.3 are allowed -- older versions (1.0, 1.1) have known vulnerabilities.
- The cipher list prioritizes ECDHE (forward secrecy) with AES-GCM (authenticated encryption). This is a restrictive but secure selection.

**API proxy (`location /api/`):**

- `proxy_pass http://api_servers/` -- the trailing slash is important. It strips `/api/` from the path, so `/api/users` becomes `/users` on the backend. Without the slash, the full path would be forwarded.
- The `proxy_set_header` lines pass through the original client information. Without these, backends would see nginx's IP instead of the real client.
- `proxy_connect_timeout 5s` -- fail fast if a backend is unreachable.

**Static files (`location ~*`):**

- The `~*` means case-insensitive regex matching.
- `expires 1y` with `immutable` tells browsers to cache these files for a year without even revalidating. This works when filenames include content hashes (e.g., `app.a1b2c3.js`).'''
    },
    {
        "instruction": r'''What does this docker-compose.yml set up?

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/myapp
      - REDIS_URL=redis://cache:6379
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d myapp"]
      interval: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  pgdata:
```''',
        "output": r'''This sets up a three-service stack: a custom application, PostgreSQL database, and Redis cache.

**The `app` service:**

- Built from the Dockerfile in the current directory.
- Port 3000 is mapped from container to host.
- Connects to the database using the hostname `db` and cache using `cache` -- Docker Compose creates a network where services can reach each other by service name.
- `depends_on` with `condition: service_healthy` means the app will not start until PostgreSQL's healthcheck passes. This prevents the common problem of the app crashing because the database is not ready yet. Redis only needs `service_started` -- a weaker guarantee (container running, not necessarily accepting connections).
- `restart: unless-stopped` -- the container restarts automatically on crashes but stays down if you explicitly stop it with `docker-compose stop`.

**The `db` service:**

- Uses the official PostgreSQL 16 Alpine image.
- `pgdata` named volume persists database data across container restarts. Without this, all data would vanish when the container is recreated.
- The `init.sql` file is mounted into `/docker-entrypoint-initdb.d/` -- PostgreSQL's official image automatically executes SQL files in this directory on first startup only (not on subsequent starts).
- The healthcheck runs `pg_isready` every 5 seconds, up to 5 retries.

**The `cache` service:**

- Redis 7 with a custom command overriding the default config.
- `maxmemory 256mb` caps memory usage.
- `allkeys-lru` eviction policy: when memory is full, Redis removes the least recently used key (regardless of whether it has a TTL). This is appropriate for caching but would be dangerous for a Redis used as a primary data store.

**Security note:** The database password is hardcoded in plain text. For production, use Docker secrets or an external secrets manager.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a Terraform configuration. Let me trace through the resources and explain the infrastructure it creates.
</think>

Explain what infrastructure this Terraform code creates:

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
}
```''',
        "output": r'''<think>
This creates a VPC with public and private subnets across two availability zones, plus a NAT gateway. Classic AWS networking setup.
</think>

This creates a standard AWS VPC network topology with public and private subnets -- the foundation for most production deployments.

**VPC:**
A virtual private network with the CIDR block `10.0.0.0/16`, giving you 65,536 IP addresses. `enable_dns_hostnames` lets EC2 instances get public DNS names.

**Public subnets (2x):**

The `count = 2` creates two subnets, one in each availability zone. `cidrsubnet("10.0.0.0/16", 8, count.index)` generates:
- Subnet 0: `10.0.0.0/24` (256 IPs)
- Subnet 1: `10.0.1.0/24` (256 IPs)

The `8` means "add 8 bits to the prefix length" (16 + 8 = /24). `map_public_ip_on_launch = true` gives instances in these subnets public IPs automatically -- making them reachable from the internet.

**Private subnets (2x):**

Same pattern but offset by 10: `10.0.10.0/24` and `10.0.11.0/24`. No public IP mapping -- instances here are not directly accessible from the internet.

**NAT gateway:**

Placed in the first public subnet. It lets instances in private subnets make outbound internet connections (to download packages, call APIs) without being directly reachable from the internet. The `aws_eip.nat` gives it a static public IP.

**Why two availability zones?** High availability. If one AZ goes down, resources in the other AZ keep running. Most AWS services (ALB, RDS Multi-AZ) require at least two AZs.

**Missing pieces:** This does not show the route tables, internet gateway, or security groups that would complete the setup. The private subnets need a route to the NAT gateway, and the public subnets need a route to an internet gateway.'''
    },
]
