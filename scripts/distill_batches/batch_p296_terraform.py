"""Infrastructure as Code — Terraform, Pulumi, resource management."""

PAIRS = [
    (
        "devops/terraform-patterns",
        "Show Terraform patterns: module composition, state management, workspaces, and drift detection.",
        '''Terraform infrastructure patterns:

```hcl
# modules/api-service/main.tf — reusable module
variable "service_name" { type = string }
variable "environment" { type = string }
variable "container_image" { type = string }
variable "replicas" { type = number, default = 2 }
variable "cpu" { type = string, default = "256" }
variable "memory" { type = string, default = "512" }

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.service_name}-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode            = "awsvpc"
  cpu                     = var.cpu
  memory                  = var.memory
  execution_role_arn      = aws_iam_role.execution.arn
  task_role_arn           = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = var.service_name
    image = var.container_image
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.service_name
      }
    }
    environment = [
      { name = "ENVIRONMENT", value = var.environment },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_ssm_parameter.db_url.arn },
    ]
  }])
}

resource "aws_ecs_service" "api" {
  name            = var.service_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.replicas
  launch_type     = "FARGATE"

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }

  network_configuration {
    subnets         = var.private_subnets
    security_groups = [aws_security_group.api.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = var.service_name
    container_port   = 8000
  }
}

output "service_url" {
  value = "https://${aws_lb.main.dns_name}"
}

# environments/production/main.tf — use the module
module "api" {
  source = "../../modules/api-service"

  service_name    = "api-server"
  environment     = "production"
  container_image = "ghcr.io/myorg/api:v2.3.1"
  replicas        = 4
  cpu             = "512"
  memory          = "1024"
}

# State management
terraform {
  backend "s3" {
    bucket         = "myorg-terraform-state"
    key            = "production/api.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

Key patterns:
1. **Module composition** — reusable infrastructure modules; DRY across environments
2. **Remote state** — S3 backend with DynamoDB locking; team collaboration
3. **Secrets via SSM** — never hardcode secrets; reference from AWS SSM Parameter Store
4. **Environment separation** — per-environment directories with shared modules
5. **Rolling deploy** — min 100% healthy during deploy; zero downtime ECS updates'''
    ),
    (
        "devops/iac-testing",
        "Show Infrastructure as Code testing: plan validation, policy checks, and integration testing for infrastructure.",
        '''IaC testing and validation:

```python
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlanChange:
    resource: str
    action: str  # create, update, delete
    attributes_changed: list[str]


class TerraformTester:
    """Test Terraform plans before apply."""

    def __init__(self, working_dir: str):
        self.dir = working_dir

    def plan(self, var_file: str = None) -> dict:
        """Generate and parse Terraform plan."""
        cmd = ["terraform", "plan", "-out=tfplan", "-no-color"]
        if var_file:
            cmd.extend(["-var-file", var_file])
        subprocess.run(cmd, cwd=self.dir, check=True)

        # Export plan as JSON for analysis
        result = subprocess.run(
            ["terraform", "show", "-json", "tfplan"],
            capture_output=True, text=True, cwd=self.dir,
        )
        return json.loads(result.stdout)

    def get_changes(self, plan: dict) -> list[PlanChange]:
        """Extract resource changes from plan."""
        changes = []
        for rc in plan.get("resource_changes", []):
            actions = rc["change"]["actions"]
            if actions == ["no-op"]:
                continue
            changes.append(PlanChange(
                resource=rc["address"],
                action="+".join(actions),
                attributes_changed=list(
                    rc["change"].get("after_unknown", {}).keys()
                ),
            ))
        return changes

    def assert_no_destroys(self, plan: dict):
        """Safety check: no resources destroyed."""
        changes = self.get_changes(plan)
        destroys = [c for c in changes if "delete" in c.action]
        if destroys:
            resources = [d.resource for d in destroys]
            raise AssertionError(f"Plan would destroy: {resources}")

    def assert_no_drift(self):
        """Check for configuration drift."""
        result = subprocess.run(
            ["terraform", "plan", "-detailed-exitcode", "-no-color"],
            cwd=self.dir, capture_output=True,
        )
        if result.returncode == 2:
            raise AssertionError(f"Drift detected:\\n{result.stdout.decode()}")

    def validate(self) -> bool:
        """Validate Terraform configuration syntax."""
        result = subprocess.run(
            ["terraform", "validate", "-json"],
            capture_output=True, text=True, cwd=self.dir,
        )
        output = json.loads(result.stdout)
        return output["valid"]


# Policy checks (OPA/Conftest style)
class InfraPolicy:
    """Enforce infrastructure policies on Terraform plans."""

    def __init__(self):
        self.violations: list[str] = []

    def check(self, plan: dict) -> list[str]:
        self.violations = []
        for rc in plan.get("resource_changes", []):
            self._check_resource(rc)
        return self.violations

    def _check_resource(self, rc: dict):
        resource_type = rc.get("type", "")
        after = rc["change"].get("after", {}) or {}

        # No public S3 buckets
        if resource_type == "aws_s3_bucket":
            acl = after.get("acl", "private")
            if acl in ("public-read", "public-read-write"):
                self.violations.append(
                    f"{rc['address']}: Public S3 bucket not allowed"
                )

        # Enforce encryption
        if resource_type == "aws_db_instance":
            if not after.get("storage_encrypted"):
                self.violations.append(
                    f"{rc['address']}: RDS must have encryption enabled"
                )

        # Enforce tagging
        tags = after.get("tags", {}) or {}
        required_tags = {"environment", "team", "cost-center"}
        missing = required_tags - set(tags.keys())
        if missing and resource_type.startswith("aws_"):
            self.violations.append(
                f"{rc['address']}: Missing required tags: {missing}"
            )
```

Key patterns:
1. **Plan analysis** — parse plan JSON to verify expected changes before apply
2. **No-destroy check** — prevent accidental resource deletion in CI
3. **Drift detection** — `detailed-exitcode` returns 2 if real state differs from config
4. **Policy enforcement** — check plans against organization rules (encryption, tagging, access)
5. **Validate first** — syntax validation catches errors before expensive plan operations'''
    ),
]
"""
