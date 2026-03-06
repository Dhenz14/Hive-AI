r'''Phase 4A: Self-Improvement — Training Data Generation (Part 5)

Generate and evaluate training pairs for DevOps and infrastructure topics.
Each answer creates 3 graded training pairs with quality analysis.
'''

PAIRS = [
    (
        "thinking/auto-datagen-docker-containerization",
        r'''Generate 3 high-quality training pairs that teach Docker containerization. For each pair, explain why it's effective training data.''',
        r'''<think>
To create effective training data for Docker containerization, I need to consider:
1. Common misconceptions: confusing images vs containers, not understanding layers, ignoring multi-stage builds, running as root
2. Real scenarios: writing Dockerfiles for production apps, debugging container networking, optimizing image size
3. Difficulty progression: basic Dockerfile writing -> optimization -> production patterns

I should cover the fundamentals first, then move to optimization, then production-grade patterns. Each pair should demonstrate a concrete task rather than abstract theory.
</think>

Here are 3 training pairs for Docker containerization:

**Pair 1 (Beginner):**
```
Q: I have a Python Flask app with a requirements.txt. Write a Dockerfile for it and explain each line.

A: Here is a production-ready Dockerfile for a Flask application:

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]

Line-by-line explanation:
- FROM python:3.11-slim: Uses the slim variant to reduce image size (~150MB vs ~900MB for the full image). Always pin a specific Python version.
- WORKDIR /app: Sets the working directory inside the container. All subsequent commands run from here.
- COPY requirements.txt .: Copies only requirements.txt first. This is intentional — Docker caches each layer, so dependencies are only reinstalled when requirements.txt changes.
- RUN pip install --no-cache-dir: The --no-cache-dir flag prevents pip from storing download caches, reducing image size.
- COPY . .: Copies the rest of the application code. Because this comes after pip install, code changes do not trigger a full dependency reinstall.
- EXPOSE 5000: Documents which port the app listens on. This does not actually publish the port — you still need -p 5000:5000 when running.
- CMD: Uses gunicorn instead of Flask's dev server, which is not suitable for production.
```
**Why this works:** It teaches layer caching strategy (the most important Docker optimization concept) through a practical example. The explanation of why requirements.txt is copied separately is the key insight that separates beginners from competent Docker users.

**Pair 2 (Intermediate):**
```
Q: My Docker image for a Node.js app is 1.2GB. Here is my Dockerfile. How can I reduce its size?

FROM node:18
WORKDIR /app
COPY . .
RUN npm install
RUN npm run build
EXPOSE 3000
CMD ["node", "dist/index.js"]

A: Several optimizations can reduce this dramatically — often to under 200MB:

1. Use a multi-stage build to separate build-time and runtime dependencies:

FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production && cp -R node_modules prod_modules
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/prod_modules ./node_modules
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/index.js"]

Key changes:
- node:18-alpine instead of node:18 saves ~700MB (Alpine is ~5MB base vs ~350MB for Debian)
- Multi-stage build: the builder stage has devDependencies for compilation, but the final image only has production node_modules and compiled output
- npm ci instead of npm install ensures reproducible installs from package-lock.json
- package*.json copied first to leverage layer caching

2. Add a .dockerignore file to prevent copying unnecessary files:
   node_modules, .git, *.md, .env, tests/
```
**Why this works:** It starts from a realistic bad Dockerfile and transforms it, teaching multi-stage builds in context. Showing the size impact motivates the learner. The .dockerignore addition teaches defense-in-depth.

**Pair 3 (Advanced):**
```
Q: How should I handle secrets in Docker containers? Our team currently passes database passwords via environment variables in docker-compose.yml and sometimes bakes them into images.

A: Both practices are insecure. Here is the correct approach at each level:

**Never do this** — secrets in image layers:
ENV DB_PASSWORD=hunter2  # Visible in docker history, persists in layer cache

**Acceptable for dev** — runtime environment variables:
docker run -e DB_PASSWORD="$(vault read -field=password secret/db)" myapp
# Better: use an env file excluded from version control
docker run --env-file .env.production myapp

**Production approach** — Docker secrets (Swarm) or mounted volumes:
# docker-compose.yml with secrets
services:
  app:
    image: myapp
    secrets:
      - db_password
secrets:
  db_password:
    external: true  # Managed by docker secret create

In the application, read from /run/secrets/db_password instead of environment variables. Secrets are mounted as tmpfs (never written to disk) and only available to services that declare them.

**Kubernetes approach** — use Sealed Secrets or external-secrets-operator to sync from Vault/AWS Secrets Manager into Kubernetes Secrets, then mount as volumes (not env vars, since env vars appear in pod specs and logs).

Key principle: secrets should be injected at runtime, never at build time, and should be readable only by the process that needs them.
```
**Why this works:** It addresses a real security anti-pattern that many teams have. It provides a progression from worst to best practice and covers both Docker Swarm and Kubernetes, which reflects real-world tool diversity.

**Quality assessment:**
- Concept coverage: Dockerfile basics, layer caching, multi-stage builds, image optimization, secrets management
- Realism: All three scenarios come from common developer pain points — writing a first Dockerfile, dealing with bloated images, and handling secrets
- Difficulty curve: Writing a Dockerfile -> optimizing an existing one -> security architecture decisions'''
    ),
    (
        "thinking/auto-datagen-cicd-pipeline",
        r'''Generate 3 high-quality training pairs that teach CI/CD pipeline design. For each pair, explain why it's effective training data.''',
        r'''<think>
For CI/CD pipeline design, I need to think about:
1. Common misconceptions: treating CI/CD as just "run tests on push," not understanding pipeline stages, ignoring caching and parallelism
2. Real scenarios: setting up a pipeline from scratch, debugging slow pipelines, implementing deployment strategies
3. Difficulty progression: basic pipeline structure -> optimization and caching -> advanced deployment strategies

The pairs should use concrete CI/CD tooling (GitHub Actions is most universal) rather than abstract concepts.
</think>

Here are 3 training pairs for CI/CD pipeline design:

**Pair 1 (Beginner):**
```
Q: I have a Python project with pytest tests and I want to set up GitHub Actions to run tests on every pull request. How do I structure the workflow file?

A: Create .github/workflows/ci.yml:

name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: pytest --tb=short -q

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: 'pip'
      - run: pip install ruff
      - run: ruff check .

Key design decisions:
- Tests and linting are separate jobs so they run in parallel
- Matrix strategy tests across Python versions to catch compatibility issues
- cache: 'pip' avoids re-downloading packages on every run
- Triggers on both PR and push to main — PR for pre-merge checks, push for post-merge verification
```
**Why this works:** It covers the complete setup from zero, uses the most popular CI platform, and introduces matrix builds and parallelism early. The "key design decisions" section teaches the reasoning behind structural choices.

**Pair 2 (Intermediate):**
```
Q: Our CI pipeline takes 25 minutes. The main bottleneck is installing dependencies (4 min), running unit tests (8 min), running integration tests (10 min), and building a Docker image (3 min). How can we speed this up?

A: Here is a multi-pronged optimization strategy:

1. **Aggressive caching** — cache both pip packages and Docker layers:
   - uses: actions/cache@v4
     with:
       path: ~/.cache/pip
       key: pip-${{ hashFiles('requirements*.txt') }}

2. **Parallelize test suites** — split tests across multiple runners:
   jobs:
     unit-tests:
       strategy:
         matrix:
           shard: [1, 2, 3, 4]
       steps:
         - run: pytest tests/unit --shard-id=${{ matrix.shard }} --num-shards=4
   This splits 8 minutes of unit tests into ~2 minutes across 4 runners.

3. **Run integration tests conditionally** — only when relevant code changes:
   - uses: dorny/paths-filter@v3
     id: changes
     with:
       filters: |
         backend:
           - 'src/**'
           - 'tests/integration/**'
   - run: pytest tests/integration
     if: steps.changes.outputs.backend == 'true'

4. **Docker build caching** with BuildKit:
   - uses: docker/build-push-action@v5
     with:
       cache-from: type=gha
       cache-to: type=gha,mode=max

5. **Fail fast** — put lint and type checks first since they take seconds and catch obvious errors before expensive test runs.

Expected result: pipeline drops from 25 minutes to ~6-8 minutes for most PRs.
```
**Why this works:** It starts from a quantified problem (25 minutes with specific breakdowns), which mirrors how real optimization work begins. Each technique is shown with actual configuration syntax, not just theory.

**Pair 3 (Advanced):**
```
Q: We need to implement a deployment pipeline for a microservices application that supports canary deployments, automatic rollback, and promotion across staging and production environments. What does this look like?

A: Here is a deployment pipeline architecture using GitHub Actions with ArgoCD:

**Pipeline stages:**
1. CI (on PR): lint, test, build image, push to registry with PR tag
2. Merge to main: build final image tagged with git SHA, deploy to staging automatically
3. Canary promotion: deploy to 10% of production traffic, monitor error rates
4. Full rollout: if canary metrics pass, promote to 100%

**Implementation sketch:**

deploy-staging:
  needs: [build]
  steps:
    - run: |
        yq e ".spec.source.targetRevision = \"$SHA\"" \
          argocd/staging/app.yaml | kubectl apply -f -
    - run: argocd app wait myapp-staging --health

deploy-canary:
  needs: [deploy-staging]
  environment: production-canary  # requires manual approval
  steps:
    - run: |
        kubectl set image deployment/myapp myapp=registry/myapp:$SHA
        kubectl patch deployment/myapp -p \
          '{"spec":{"strategy":{"rollingUpdate":{"maxSurge":"10%","maxUnavailable":"0%"}}}}'

verify-canary:
  needs: [deploy-canary]
  steps:
    - run: |
        # Query Prometheus for error rate over 10 minutes
        ERROR_RATE=$(curl -s "$PROM_URL/api/v1/query?query=rate(http_errors[10m])")
        if (( $(echo "$ERROR_RATE > 0.01" | bc -l) )); then
          echo "Error rate too high, rolling back"
          kubectl rollout undo deployment/myapp
          exit 1
        fi

promote-production:
  needs: [verify-canary]
  environment: production  # requires manual approval
  steps:
    - run: argocd app set myapp-prod --revision $SHA
    - run: argocd app sync myapp-prod

**Automatic rollback:** ArgoCD monitors health. If pods crash-loop after deployment, it automatically reverts to the last healthy revision. The verify-canary job adds application-level health checks beyond pod liveness.

**Key principle:** Every stage must be independently retriable. If canary verification fails, the pipeline rolls back without affecting the staging environment.
```
**Why this works:** It teaches the full deployment lifecycle with concrete tooling choices. The canary pattern with automatic rollback is a real production requirement. The combination of GitHub Actions for orchestration and ArgoCD for GitOps reflects current industry best practices.

**Quality assessment:**
- Concept coverage: Pipeline structure, caching, parallelism, conditional execution, canary deployments, automated rollback, environment promotion
- Realism: Progresses from "set up CI for my project" to "optimize a slow pipeline" to "build a production deployment strategy" — a natural career progression
- Difficulty curve: Configuration basics -> performance optimization -> distributed deployment architecture'''
    ),
    (
        "thinking/auto-datagen-infrastructure-as-code",
        r'''Generate 3 high-quality training pairs that teach infrastructure as code with Terraform. For each pair, explain why it's effective training data.''',
        r'''<think>
For Terraform/IaC training data, I should consider:
1. Common misconceptions: not understanding state, ignoring modules, hardcoding values, not planning before apply
2. Real scenarios: provisioning cloud resources, managing state across teams, structuring large projects
3. Difficulty progression: basic resource creation -> modules and state management -> advanced patterns (workspaces, imports, drift detection)

I should use AWS as the cloud provider since it is most widely used, but keep concepts transferable.
</think>

Here are 3 training pairs for infrastructure as code (Terraform):

**Pair 1 (Beginner):**
```
Q: I need to create an AWS EC2 instance with a security group that allows SSH and HTTP access using Terraform. Walk me through the configuration.

A: Here is a complete Terraform configuration:

# providers.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5"
}

provider "aws" {
  region = var.aws_region
}

# variables.tf
variable "aws_region" {
  default = "us-east-1"
}
variable "instance_type" {
  default = "t3.micro"
}

# main.tf
resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "Allow SSH and HTTP"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]  # Never use 0.0.0.0/0
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.web.id]
  tags = { Name = "web-server" }
}

# outputs.tf
output "public_ip" {
  value = aws_instance.web.public_ip
}

Workflow: run terraform init, then terraform plan to preview changes, then terraform apply to create resources. Always review the plan before applying.
```
**Why this works:** It shows proper file organization (separate files for providers, variables, main, outputs), demonstrates resource references between security group and instance, and includes a security note about SSH CIDR blocks. The workflow explanation teaches the plan-before-apply discipline.

**Pair 2 (Intermediate):**
```
Q: Our Terraform project has grown to 50+ resources all in one directory. How should we restructure it using modules, and how do we manage state safely across a team?

A: Restructure into reusable modules with remote state:

**Directory structure:**
infrastructure/
  modules/
    networking/    # VPC, subnets, NAT gateway
      main.tf
      variables.tf
      outputs.tf
    compute/       # EC2, ASG, launch templates
    database/      # RDS, ElastiCache
    monitoring/    # CloudWatch, SNS alerts
  environments/
    staging/
      main.tf      # Calls modules with staging values
      backend.tf   # S3 state for staging
    production/
      main.tf      # Calls modules with prod values
      backend.tf   # S3 state for production

**Remote state with locking:**
# backend.tf
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

The DynamoDB table provides distributed locking — if two engineers run terraform apply simultaneously, the second one blocks until the first finishes. Without this, concurrent applies corrupt state.

**Module usage:**
module "networking" {
  source       = "../../modules/networking"
  environment  = "production"
  vpc_cidr     = "10.0.0.0/16"
  az_count     = 3
}

module "database" {
  source     = "../../modules/database"
  subnet_ids = module.networking.private_subnet_ids
  vpc_id     = module.networking.vpc_id
}

**Key rules:** Never edit terraform.tfstate manually. Use terraform import to bring existing resources under management. Use terraform state mv to reorganize without destroying resources.
```
**Why this works:** It addresses the real pain point of scaling Terraform projects, teaches module design with clear boundaries, and emphasizes state locking as a team collaboration necessity. The directory structure is immediately actionable.

**Pair 3 (Advanced):**
```
Q: We have infrastructure deployed manually in AWS that we need to bring under Terraform management without downtime. We also need to detect and remediate configuration drift. What is the strategy?

A: This is a brownfield adoption problem. Here is a phased approach:

**Phase 1: Import existing resources**
Use terraform import to map existing cloud resources to Terraform state:

terraform import aws_instance.web i-0abc123def456
terraform import aws_rds_cluster.main my-cluster-id

After import, run terraform plan. It will show differences between the real resource and your .tf code. Adjust your configuration until plan shows "No changes" — this means your code accurately describes reality.

**Tip:** Use terraformer or aztfexport to auto-generate .tf files from existing infrastructure. Review and refactor the output — auto-generated code is ugly but correct.

**Phase 2: Detect drift**
Configuration drift occurs when someone modifies resources outside Terraform (console clicks, CLI commands, other tools).

Detection approach:
1. Scheduled CI job runs terraform plan every 4 hours
2. If plan shows changes, it means reality has drifted from code
3. Alert the team via Slack webhook:

   # In CI pipeline
   PLAN_OUTPUT=$(terraform plan -detailed-exitcode 2>&1)
   if [ $? -eq 2 ]; then
     curl -X POST "$SLACK_WEBHOOK" \
       -d "{\"text\": \"Drift detected in production infrastructure\"}"
   fi

**Phase 3: Enforce code-only changes**
- Remove console write access for non-emergency use (SCPs or IAM policies)
- All changes go through PR -> plan -> review -> apply
- Use Atlantis or Spacelift to run terraform plan automatically on PRs and post the output as a comment
- Require approval from infrastructure team before apply

**Phase 4: Handle emergency changes**
Sometimes you must fix things via console (outage response). After the emergency:
1. Run terraform plan to see what drifted
2. Update .tf code to match the emergency fix
3. Apply so state is consistent again
4. Document in post-incident review

This preserves the principle that Terraform code is the source of truth, even when reality temporarily diverges.
```
**Why this works:** Most Terraform tutorials assume greenfield projects, but real teams usually adopt IaC on existing infrastructure. This pair teaches the import workflow, drift detection as a continuous process, and organizational policies — bridging technical and process concerns.

**Quality assessment:**
- Concept coverage: Resource creation, file organization, modules, remote state, locking, brownfield adoption, drift detection, organizational governance
- Realism: Progresses from "create my first resource" to "scale my project" to "adopt IaC across an organization" — real growth trajectory
- Difficulty curve: Individual resources -> project structure and team workflows -> organizational adoption strategy'''
    ),
    (
        "thinking/auto-datagen-log-aggregation",
        r'''Generate 3 high-quality training pairs that teach log aggregation and analysis. For each pair, explain why it's effective training data.''',
        r'''<think>
For log aggregation and analysis, I need to consider:
1. Common misconceptions: unstructured logging, logging too much or too little, not correlating logs across services, ignoring log levels
2. Real scenarios: setting up centralized logging, debugging production issues with logs, structured logging implementation
3. Difficulty progression: structured logging basics -> centralized aggregation -> advanced querying and alerting

I should cover the application side (how to log) and the infrastructure side (how to collect and query).
</think>

Here are 3 training pairs for log aggregation and analysis:

**Pair 1 (Beginner):**
```
Q: Our Python application uses print() statements for logging. What should we use instead, and what does good structured logging look like?

A: Replace print() with Python's structlog or the standard logging module with JSON output. Here is why and how:

**Problems with print():**
- No log levels (cannot filter debug vs error)
- No timestamps (when did it happen?)
- No structured fields (hard to parse and search)
- No context propagation (which request caused this?)

**Structured logging with structlog:**
import structlog

logger = structlog.get_logger()

# Bad: print(f"User {user_id} placed order {order_id}")
# Good:
logger.info("order_placed",
    user_id=user_id,
    order_id=order_id,
    total_amount=amount,
    item_count=len(items))

This outputs JSON:
{"event": "order_placed", "user_id": "u-123", "order_id": "ord-456",
 "total_amount": 59.99, "item_count": 3, "timestamp": "2025-01-15T10:30:00Z",
 "level": "info"}

**Key rules for effective logging:**
- Use log levels correctly: DEBUG for dev, INFO for business events, WARNING for recoverable issues, ERROR for failures needing attention
- Include correlation IDs: attach a request_id to every log line so you can trace a request across services
- Log events, not messages: "order_placed" is searchable; "User placed an order" is not
- Never log sensitive data: passwords, tokens, PII, credit card numbers
```
**Why this works:** It starts from the most common bad practice (print statements) and shows the concrete replacement. The JSON output example makes the benefit immediately visible. The rules at the end are memorable and actionable.

**Pair 2 (Intermediate):**
```
Q: We have 12 microservices each writing logs to their own files. How do we set up centralized log aggregation so we can search across all services?

A: Use the ELK stack (Elasticsearch, Logstash/Fluentd, Kibana) or a managed alternative like Grafana Loki. Here is a practical setup with Fluentd and Elasticsearch:

**Architecture:**
App containers -> stdout (JSON) -> Fluentd (DaemonSet) -> Elasticsearch -> Kibana

**Step 1:** Applications log JSON to stdout (never to files in containers):
# Docker best practice: log to stdout, let the runtime handle collection

**Step 2:** Deploy Fluentd as a DaemonSet in Kubernetes:
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
spec:
  template:
    spec:
      containers:
      - name: fluentd
        image: fluent/fluentd-kubernetes-daemonset:v1-debian-elasticsearch
        env:
        - name: FLUENT_ELASTICSEARCH_HOST
          value: "elasticsearch.logging.svc"
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: dockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true

Fluentd automatically collects stdout from all containers on each node, enriches logs with Kubernetes metadata (pod name, namespace, labels), and forwards to Elasticsearch.

**Step 3:** Create Kibana index pattern and dashboards:
- Index pattern: fluentd-* to match all incoming log indices
- Key dashboards: error rate by service, slow request logs, deployment markers

**Lightweight alternative** — Grafana Loki:
If Elasticsearch is too resource-heavy, Loki stores logs as compressed chunks indexed only by labels (service, level, namespace). It uses far less storage but requires you to know which labels to query. Use Loki when cost matters and you can filter by known dimensions.
```
**Why this works:** It presents a complete architecture with concrete deployment configuration, not just abstract diagrams. The Loki alternative acknowledges that not every team can run Elasticsearch, which reflects real-world constraints.

**Pair 3 (Advanced):**
```
Q: We have centralized logging set up, but our team struggles to debug issues across microservices. A user reports a failed checkout, and we have to manually search multiple services. How do we improve this?

A: Implement distributed tracing correlation across your log pipeline:

**1. Propagate trace context:**
Every incoming request gets a trace_id (or inherits one from the caller). Pass it via headers:

from uuid import uuid4
import structlog

def middleware(request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid4()))
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    response = call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

Now every log line from this request includes trace_id. When service A calls service B, it passes X-Trace-ID in the HTTP header. Service B binds the same trace_id.

**2. Build a trace view in Kibana:**
Query: trace_id: "abc-123" sorted by timestamp. This shows the entire request journey:
10:30:00.001 [api-gateway]   INFO  request_received  path=/checkout
10:30:00.050 [order-service]  INFO  order_created     order_id=ord-789
10:30:00.120 [payment-svc]    ERROR payment_failed    reason="card_declined"
10:30:00.125 [order-service]  WARN  order_rolled_back order_id=ord-789
10:30:00.130 [api-gateway]    INFO  request_completed status=402 duration=129ms

**3. Add alerting on patterns:**
Use Elasticsearch Watcher or Grafana alerting:
- Alert when error_rate > 5% for any service over 5 minutes
- Alert when a specific error message appears more than N times
- Alert when p99 latency (logged as duration_ms) exceeds SLA threshold

**4. Integrate with OpenTelemetry:**
For full observability, connect logs to traces and metrics. OpenTelemetry auto-injects trace_id and span_id into log records, letting you jump from a log line directly to its distributed trace in Jaeger or Tempo.

The result: when a user reports "checkout failed," support looks up their request by user_id, finds the trace_id, and sees the complete cross-service journey in seconds rather than hours.
```
**Why this works:** It addresses the real gap between "we have centralized logs" and "we can actually debug with them." The trace correlation example with concrete log output makes the concept tangible. The integration with OpenTelemetry points toward the modern observability stack.

**Quality assessment:**
- Concept coverage: Structured logging, centralized aggregation, log collection architecture, distributed tracing, correlation IDs, alerting
- Realism: The progression from "our app uses print()" to "we cannot debug across services" matches how logging maturity actually evolves in organizations
- Difficulty curve: Application-level logging -> infrastructure-level collection -> cross-service debugging and alerting'''
    ),
    (
        "thinking/auto-datagen-secrets-management",
        r'''Generate 3 high-quality training pairs that teach secrets management. For each pair, explain why it's effective training data.''',
        r'''<think>
For secrets management training data, I need to consider:
1. Common misconceptions: storing secrets in code/env files, not rotating secrets, sharing credentials via Slack/email, using the same secret across environments
2. Real scenarios: removing hardcoded secrets, setting up a secrets manager, implementing rotation
3. Difficulty progression: basic secret hygiene -> using a secrets manager -> automated rotation and zero-trust patterns

Security topics need to be especially concrete because vague advice leads to insecure implementations.
</think>

Here are 3 training pairs for secrets management:

**Pair 1 (Beginner):**
```
Q: I just realized our Django settings.py has database credentials hardcoded and committed to Git. How do I fix this properly?

A: This is a critical security issue. Here is the remediation plan:

**Step 1: Rotate the exposed credentials immediately.**
The credentials in Git history are compromised. Even if you delete them from the current code, they remain in Git history forever. Change the database password NOW before doing anything else.

**Step 2: Remove secrets from code and use environment variables:**
# settings.py — BEFORE (insecure)
DATABASES = {
    'default': {
        'PASSWORD': 'super_secret_password',  # Never do this
    }
}

# settings.py — AFTER
import os
DATABASES = {
    'default': {
        'PASSWORD': os.environ['DB_PASSWORD'],  # Read from environment
    }
}

**Step 3: Set environment variables securely:**
- Local development: use a .env file with python-dotenv, add .env to .gitignore
- Production: set via your deployment platform (Heroku config vars, AWS Parameter Store, Kubernetes secrets)

**Step 4: Prevent future leaks:**
- Add pre-commit hooks that scan for secrets:
  pip install detect-secrets
  detect-secrets scan > .secrets.baseline
  # Add to .pre-commit-config.yaml

- Add .env, *.pem, *.key to .gitignore immediately

**Step 5: Scrub Git history (optional but recommended):**
  git filter-repo --invert-paths --path settings.py
  # Or use BFG Repo-Cleaner for simpler cases

Force-push and notify all contributors to re-clone.
```
**Why this works:** It starts from a common real mistake and provides a complete remediation plan, not just "use environment variables." The emphasis on rotating credentials first (before code cleanup) teaches the correct security mindset: stop the bleeding, then fix the root cause.

**Pair 2 (Intermediate):**
```
Q: Our team uses .env files for secrets locally and environment variables in production. This works but we have 15 services and managing secrets across environments is becoming painful. What should we use instead?

A: Adopt a centralized secrets manager. Here is a comparison and implementation guide:

**Options:**
- HashiCorp Vault: Most powerful, self-hosted or HCP, steep learning curve
- AWS Secrets Manager: Managed, integrates natively with AWS services, $0.40/secret/month
- AWS SSM Parameter Store: Free tier for standard params, good for config + secrets
- Azure Key Vault / GCP Secret Manager: Cloud-native options for those platforms

**Recommended setup with AWS Secrets Manager:**

1. Store secrets with clear naming convention:
   aws secretsmanager create-secret \
     --name "production/order-service/database" \
     --secret-string '{"host":"db.example.com","password":"rotated_pw_123"}'

   Naming: {environment}/{service}/{secret-type}

2. Access from application code:
   import boto3
   import json

   def get_secret(name):
       client = boto3.client('secretsmanager')
       response = client.get_secret_value(SecretId=name)
       return json.loads(response['SecretString'])

   db_config = get_secret(f"{ENV}/order-service/database")

3. Use IAM policies to restrict access — each service's IAM role can only read its own secrets:
   {
     "Effect": "Allow",
     "Action": "secretsmanager:GetSecretValue",
     "Resource": "arn:aws:secretsmanager:*:*:secret:production/order-service/*"
   }

4. Cache secrets in memory (refresh every 5 minutes) to avoid API rate limits and reduce latency.

**Migration path:** Replace .env files one service at a time. Keep .env as fallback during transition:
   password = os.environ.get('DB_PASSWORD') or get_secret(...)
```
**Why this works:** It compares real options with honest tradeoffs instead of just recommending one tool. The naming convention, IAM scoping, and migration path are practical details that tutorials often skip but teams always need.

**Pair 3 (Advanced):**
```
Q: We use AWS Secrets Manager for storing database credentials. Our security team requires automated credential rotation with zero downtime. How do we implement this?

A: Implement a dual-credential rotation strategy:

**The problem with naive rotation:**
If you change the DB password while the app is using it, all connections fail until the app reads the new password. This causes downtime.

**Solution: Two-user rotation (AWS recommended pattern)**

Create two database users (e.g., app_user_a and app_user_b). The secret stores the currently active user. Rotation alternates between them:

1. ACTIVE: app_user_a (current password in Secrets Manager)
2. Rotation triggers: create new password for app_user_b, update it in the database
3. Update Secrets Manager with app_user_b credentials
4. ACTIVE: app_user_b (app_user_a still works until next rotation)

**Implementation with AWS Lambda rotation function:**

aws secretsmanager rotate-secret \
  --secret-id production/order-service/database \
  --rotation-lambda-arn arn:aws:lambda:...:rotate-db-creds \
  --rotation-rules AutomaticallyAfterDays=30

The Lambda function implements four steps:
- createSecret: Generate new credentials, store as AWSPENDING
- setSecret: Update the database user's password
- testSecret: Connect to the database with new credentials to verify
- finishSecret: Mark AWSPENDING as AWSCURRENT

**Application-side handling:**
import botocore

def get_db_connection():
    creds = get_secret("production/order-service/database")
    try:
        return connect(password=creds['password'])
    except AuthenticationError:
        # Secret may have just rotated — force refresh from Secrets Manager
        creds = get_secret("production/order-service/database", force_refresh=True)
        return connect(password=creds['password'])

**Key points:**
- The application caches credentials but must handle auth failures by refreshing
- Two-user rotation ensures the old credentials remain valid during the transition window
- Test the rotation in staging first — a broken rotation Lambda can lock you out of your database
- Monitor rotation via CloudWatch: alert if rotation fails or if a secret has not been rotated in > 35 days
```
**Why this works:** Zero-downtime secret rotation is a real production requirement that most developers have never implemented. The dual-user pattern is non-obvious but essential. Including the application-side retry logic makes this immediately implementable rather than theoretical.

**Quality assessment:**
- Concept coverage: Removing hardcoded secrets, Git history remediation, centralized secrets management, access control, automated rotation, zero-downtime patterns
- Realism: The progression from "oops I committed a password" to "manage secrets across 15 services" to "automate rotation" reflects actual organizational maturity
- Difficulty curve: Emergency remediation -> centralized management adoption -> automated rotation with zero downtime'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
