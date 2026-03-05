"""Infrastructure as Code — Terraform patterns, modules, state management, drift detection."""

PAIRS = [
    (
        "devops/terraform-patterns",
        "Show Terraform best practices: module design, state management, workspaces, and handling sensitive values.",
        '''Terraform patterns for production infrastructure:

```hcl
# --- Module structure ---
# modules/
#   vpc/
#     main.tf
#     variables.tf
#     outputs.tf
#   ecs-service/
#     main.tf
#     variables.tf
#     outputs.tf
#     versions.tf

# modules/ecs-service/variables.tf
variable "service_name" {
  type        = string
  description = "Name of the ECS service"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,28}$", var.service_name))
    error_message = "Service name must be lowercase alphanumeric, 3-29 chars."
  }
}

variable "container_image" {
  type = string
}

variable "cpu" {
  type    = number
  default = 256
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.cpu)
    error_message = "CPU must be a valid Fargate value."
  }
}

variable "memory" {
  type    = number
  default = 512
}

variable "environment" {
  type = map(string)
  default = {}
}

variable "secrets" {
  type = map(string)  # ARN references to SSM/Secrets Manager
  default = {}
  sensitive = true
}

# modules/ecs-service/main.tf
resource "aws_ecs_task_definition" "this" {
  family                   = var.service_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = var.service_name
    image = var.container_image

    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
    }]

    environment = [
      for k, v in var.environment : { name = k, value = v }
    ]

    secrets = [
      for k, v in var.secrets : { name = k, valueFrom = v }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.service_name
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_ecs_service" "this" {
  name            = var.service_name
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.service.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = var.service_name
    container_port   = 8080
  }
}

# --- Root module usage ---
# environments/production/main.tf

terraform {
  required_version = ">= 1.7"

  backend "s3" {
    bucket         = "company-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

module "api_service" {
  source = "../../modules/ecs-service"

  service_name    = "api"
  container_image = "123456789.dkr.ecr.us-east-1.amazonaws.com/api:${var.image_tag}"
  cpu             = 1024
  memory          = 2048
  desired_count   = 3
  cluster_id      = module.ecs_cluster.id
  private_subnet_ids = module.vpc.private_subnet_ids

  environment = {
    LOG_LEVEL    = "info"
    DB_HOST      = module.rds.endpoint
    REDIS_URL    = module.elasticache.endpoint
  }

  secrets = {
    DB_PASSWORD  = aws_ssm_parameter.db_password.arn
    API_KEY      = aws_secretsmanager_secret.api_key.arn
  }
}
```

State management:
```bash
# Remote state with locking
# S3 + DynamoDB prevents concurrent modifications

# Import existing resources
terraform import aws_s3_bucket.logs my-log-bucket

# State manipulation (use carefully)
terraform state list
terraform state show aws_ecs_service.api
terraform state mv aws_ecs_service.old aws_ecs_service.new
terraform state rm aws_ecs_service.deprecated

# Plan with targeting (emergency fixes only)
terraform plan -target=module.api_service
```

Key patterns:
- **Module composition** — small, focused modules composed in root
- **Environment separation** — `environments/{dev,staging,prod}/` with shared modules
- **State locking** — DynamoDB + S3 prevents concurrent applies
- **Sensitive values** — SSM/Secrets Manager ARNs, never plaintext
- **Lifecycle rules** — `create_before_destroy` for zero-downtime
- **Validation** — input validation catches errors before apply'''
    ),
    (
        "devops/infrastructure-testing",
        "Show how to test infrastructure code with Terratest, policy-as-code with OPA/Conftest, and drift detection.",
        '''Testing infrastructure code for correctness and compliance:

```python
# --- Policy-as-code with Conftest/OPA ---
# policy/terraform.rego

package main

# Deny public S3 buckets
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_s3_bucket"
    resource.change.after.acl == "public-read"
    msg := sprintf("S3 bucket '%s' must not be public", [resource.name])
}

# Require encryption on EBS volumes
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_ebs_volume"
    not resource.change.after.encrypted
    msg := sprintf("EBS volume '%s' must be encrypted", [resource.name])
}

# Enforce tagging
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_instance"
    tags := resource.change.after.tags
    required := {"Environment", "Team", "CostCenter"}
    missing := required - {key | tags[key]}
    count(missing) > 0
    msg := sprintf("Instance '%s' missing tags: %v", [resource.name, missing])
}

# Limit instance sizes
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_instance"
    not valid_instance_type(resource.change.after.instance_type)
    msg := sprintf("Instance type '%s' not allowed", [resource.change.after.instance_type])
}

valid_instance_type(t) {
    allowed := {"t3.micro", "t3.small", "t3.medium", "m5.large", "m5.xlarge"}
    allowed[t]
}
```

```python
# --- Drift detection ---
# scripts/drift_detector.py

import subprocess
import json
import sys
from datetime import datetime

def detect_drift(workspace: str) -> dict:
    """Run terraform plan and detect resource drift."""

    # Refresh state without applying
    result = subprocess.run(
        ["terraform", "plan", "-detailed-exitcode", "-json",
         "-refresh-only", "-no-color"],
        capture_output=True, text=True,
        cwd=f"environments/{workspace}",
    )

    # Exit code 2 = changes detected (drift)
    if result.returncode == 0:
        return {"drifted": False, "changes": []}

    if result.returncode == 2:
        changes = parse_plan_output(result.stdout)
        return {
            "drifted": True,
            "workspace": workspace,
            "detected_at": datetime.utcnow().isoformat(),
            "changes": changes,
        }

    # Exit code 1 = error
    return {"error": result.stderr}

def parse_plan_output(json_output: str) -> list[dict]:
    """Parse terraform JSON plan output for drift details."""
    changes = []
    for line in json_output.strip().split("\\n"):
        try:
            entry = json.loads(line)
            if entry.get("type") == "resource_drift":
                change = entry.get("change", {})
                changes.append({
                    "resource": change.get("resource", {}).get("addr"),
                    "action": change.get("action"),
                    "attributes_changed": list(
                        change.get("change", {}).get("after_unknown", {}).keys()
                    ),
                })
        except json.JSONDecodeError:
            continue
    return changes

def notify_drift(drift_report: dict):
    """Send drift alert to Slack/PagerDuty."""
    if not drift_report["drifted"]:
        return

    message = (
        f"Infrastructure drift detected in {drift_report['workspace']}\\n"
        f"Changed resources: {len(drift_report['changes'])}\\n"
    )
    for change in drift_report["changes"]:
        message += f"  - {change['resource']}: {change['action']}\\n"

    # Send to alerting system
    print(message)

# Run drift detection on schedule (cron/CI)
if __name__ == "__main__":
    for env in ["production", "staging"]:
        report = detect_drift(env)
        notify_drift(report)
        if report.get("drifted"):
            sys.exit(1)  # Fail CI on drift
```

```go
// --- Terratest (Go) for infrastructure validation ---
// test/vpc_test.go

package test

import (
    "testing"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/gruntwork-io/terratest/modules/aws"
    "github.com/stretchr/testify/assert"
)

func TestVpcModule(t *testing.T) {
    t.Parallel()

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../modules/vpc",
        Vars: map[string]interface{}{
            "cidr_block":     "10.99.0.0/16",
            "environment":    "test",
            "azs":           []string{"us-east-1a", "us-east-1b"},
        },
    })

    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)

    // Validate outputs
    vpcId := terraform.Output(t, terraformOptions, "vpc_id")
    assert.NotEmpty(t, vpcId)

    // Verify VPC exists and has correct CIDR
    vpc := aws.GetVpcById(t, vpcId, "us-east-1")
    assert.Equal(t, "10.99.0.0/16", vpc.CidrBlock)

    // Verify subnets created
    subnets := terraform.OutputList(t, terraformOptions, "private_subnet_ids")
    assert.Equal(t, 2, len(subnets))
}
```

CI pipeline integration:
```bash
# 1. Format check
terraform fmt -check -recursive

# 2. Validate
terraform init -backend=false
terraform validate

# 3. Security scan (tfsec)
tfsec . --minimum-severity HIGH

# 4. Policy check (Conftest)
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
conftest test plan.json --policy policy/

# 5. Cost estimation (Infracost)
infracost diff --path . --compare-to infracost-base.json

# 6. Apply (with approval gate)
terraform apply -auto-approve  # Only in CI after all checks pass
```'''
    ),
]
