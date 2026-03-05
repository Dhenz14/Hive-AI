"""Compliance automation."""

PAIRS = [
    (
        "compliance/policy-as-code-opa-rego",
        "Implement policy-as-code using Open Policy Agent (OPA) and Rego for Kubernetes admission control, Terraform plan validation, and API authorization.",
        '''Policy-as-code with OPA and Rego:

```rego
# --- Kubernetes admission control policies ---

# policy/k8s/deployment.rego
package kubernetes.admission

import rego.v1

# Deny deployments without resource limits
deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    not container.resources.limits.memory
    msg := sprintf(
        "Container '%s' in Deployment '%s' must have memory limits",
        [container.name, input.request.object.metadata.name]
    )
}

deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    not container.resources.limits.cpu
    msg := sprintf(
        "Container '%s' in Deployment '%s' must have CPU limits",
        [container.name, input.request.object.metadata.name]
    )
}

# Deny containers running as root
deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    container.securityContext.runAsUser == 0
    msg := sprintf(
        "Container '%s' must not run as root (UID 0)",
        [container.name]
    )
}

deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    not container.securityContext.runAsNonRoot
    msg := sprintf(
        "Container '%s' must set securityContext.runAsNonRoot=true",
        [container.name]
    )
}

# Deny images from untrusted registries
deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    not startswith(container.image, "ghcr.io/acme-corp/")
    not startswith(container.image, "gcr.io/distroless/")
    not startswith(container.image, "cgr.dev/chainguard/")
    msg := sprintf(
        "Container '%s' uses untrusted registry: '%s'. Allowed: ghcr.io/acme-corp/, gcr.io/distroless/, cgr.dev/chainguard/",
        [container.name, container.image]
    )
}

# Deny images with :latest tag
deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    endswith(container.image, ":latest")
    msg := sprintf(
        "Container '%s' must not use :latest tag. Pin to specific version.",
        [container.name]
    )
}

# Require mandatory labels
required_labels := {"app", "team", "environment"}

deny contains msg if {
    input.request.kind.kind == "Deployment"
    labels := input.request.object.metadata.labels
    missing := required_labels - {key | labels[key]}
    count(missing) > 0
    msg := sprintf(
        "Deployment '%s' missing required labels: %v",
        [input.request.object.metadata.name, missing]
    )
}

# Deny privilege escalation
deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    container.securityContext.privileged == true
    msg := sprintf(
        "Privileged containers are not allowed: '%s'",
        [container.name]
    )
}

deny contains msg if {
    input.request.kind.kind == "Deployment"
    container := input.request.object.spec.template.spec.containers[_]
    container.securityContext.allowPrivilegeEscalation == true
    msg := sprintf(
        "Privilege escalation not allowed: '%s'",
        [container.name]
    )
}
```

```rego
# --- Terraform plan validation policies ---

# policy/terraform/aws.rego
package terraform.aws

import rego.v1

# Parse Terraform plan JSON
resources := input.resource_changes

# Deny unencrypted S3 buckets
deny contains msg if {
    resource := resources[_]
    resource.type == "aws_s3_bucket"
    resource.change.after.server_side_encryption_configuration == null
    msg := sprintf(
        "S3 bucket '%s' must have server-side encryption enabled",
        [resource.address]
    )
}

# Deny public S3 buckets
deny contains msg if {
    resource := resources[_]
    resource.type == "aws_s3_bucket_public_access_block"
    config := resource.change.after
    not config.block_public_acls
    msg := sprintf(
        "S3 bucket '%s' must block public ACLs",
        [resource.address]
    )
}

# Deny unencrypted RDS instances
deny contains msg if {
    resource := resources[_]
    resource.type == "aws_db_instance"
    not resource.change.after.storage_encrypted
    msg := sprintf(
        "RDS instance '%s' must have storage encryption enabled",
        [resource.address]
    )
}

# Require multi-AZ for production RDS
deny contains msg if {
    resource := resources[_]
    resource.type == "aws_db_instance"
    tags := resource.change.after.tags
    tags.Environment == "production"
    not resource.change.after.multi_az
    msg := sprintf(
        "Production RDS '%s' must be multi-AZ",
        [resource.address]
    )
}

# Deny overly permissive security groups
deny contains msg if {
    resource := resources[_]
    resource.type == "aws_security_group_rule"
    resource.change.after.type == "ingress"
    resource.change.after.cidr_blocks[_] == "0.0.0.0/0"
    resource.change.after.from_port != 443
    resource.change.after.from_port != 80
    msg := sprintf(
        "Security group rule '%s' allows 0.0.0.0/0 on port %d (only 80/443 allowed)",
        [resource.address, resource.change.after.from_port]
    )
}

# Require mandatory tags on all taggable resources
required_tags := {"Team", "Environment", "ManagedBy"}

deny contains msg if {
    resource := resources[_]
    resource.change.after.tags != null
    tags := resource.change.after.tags
    missing := required_tags - {key | tags[key]}
    count(missing) > 0
    resource.change.actions[_] != "delete"
    msg := sprintf(
        "Resource '%s' missing required tags: %v",
        [resource.address, missing]
    )
}

# Cost guardrails: deny expensive instance types
expensive_instances := {
    "m6i.4xlarge", "m6i.8xlarge", "m6i.12xlarge",
    "r6i.4xlarge", "r6i.8xlarge",
    "p4d.24xlarge", "p5.48xlarge",
}

deny contains msg if {
    resource := resources[_]
    resource.type == "aws_instance"
    resource.change.after.instance_type in expensive_instances
    msg := sprintf(
        "Instance type '%s' requires FinOps approval: '%s'",
        [resource.change.after.instance_type, resource.address]
    )
}
```

```python
# --- OPA integration for CI/CD and API authorization ---

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OPAEvaluator:
    """Evaluates policies using OPA (local binary or server)."""

    opa_url: str | None = None  # If None, use local binary
    policy_dir: Path = Path("policies")

    async def evaluate_terraform_plan(
        self, plan_json_path: str
    ) -> dict[str, Any]:
        """Evaluate Terraform plan against OPA policies."""
        with open(plan_json_path) as f:
            plan_data = json.load(f)

        if self.opa_url:
            return await self._evaluate_remote(
                "terraform/aws", plan_data
            )
        return self._evaluate_local(
            "terraform/aws", plan_data
        )

    async def evaluate_k8s_admission(
        self, admission_review: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate Kubernetes admission request."""
        if self.opa_url:
            return await self._evaluate_remote(
                "kubernetes/admission", admission_review
            )
        return self._evaluate_local(
            "kubernetes/admission", admission_review
        )

    async def evaluate_api_authz(
        self, request_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate API authorization request."""
        if self.opa_url:
            return await self._evaluate_remote(
                "authz/api", request_context
            )
        return self._evaluate_local(
            "authz/api", request_context
        )

    async def _evaluate_remote(
        self, policy_path: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate policy against OPA server."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.opa_url}/v1/data/{policy_path}",
                json={"input": input_data},
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})

            denials = result.get("deny", [])
            warnings = result.get("warn", [])

            return {
                "allowed": len(denials) == 0,
                "denials": list(denials),
                "warnings": list(warnings),
            }

    def _evaluate_local(
        self, policy_path: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate policy using local OPA binary."""
        input_file = "/tmp/opa-input.json"
        with open(input_file, "w") as f:
            json.dump(input_data, f)

        result = subprocess.run(
            [
                "opa", "eval",
                "--data", str(self.policy_dir),
                "--input", input_file,
                "--format", "json",
                f"data.{policy_path.replace('/', '.')}.deny",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"OPA eval failed: {result.stderr}")
            return {"allowed": False, "denials": ["OPA evaluation error"]}

        output = json.loads(result.stdout)
        denials = output.get("result", [{}])[0].get("expressions", [{}])[0].get("value", [])

        return {
            "allowed": len(denials) == 0,
            "denials": list(denials),
        }


@dataclass
class PolicyTestRunner:
    """Runs OPA policy unit tests."""

    policy_dir: Path = Path("policies")
    test_dir: Path = Path("policies/tests")

    def run_tests(self) -> dict[str, Any]:
        """Run all OPA policy tests."""
        result = subprocess.run(
            [
                "opa", "test",
                str(self.policy_dir),
                str(self.test_dir),
                "--verbose",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
        )

        output = json.loads(result.stdout) if result.stdout else []
        passed = sum(1 for t in output if t.get("pass"))
        failed = sum(1 for t in output if not t.get("pass"))

        return {
            "total": len(output),
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0,
            "results": output,
        }
```

| Policy Domain | OPA Package | Enforcement Point | Examples |
|---|---|---|---|
| K8s admission | kubernetes.admission | Gatekeeper/OPA sidecar | Image registry, resource limits, labels |
| Terraform | terraform.aws | CI pipeline (conftest) | Encryption, tags, security groups |
| API authorization | authz.api | OPA sidecar / envoy ext_authz | RBAC, ABAC, data filtering |
| CI/CD | cicd.pipeline | Pipeline gates | Branch protection, approvals |
| Network | network.policy | Admission controller | Allowed CIDRs, protocols |
| Data | data.classification | API middleware | PII access, data residency |

Key patterns:

1. **Policy-as-code in version control** — store all Rego policies in Git alongside infrastructure code; review policies in PRs like any other code change
2. **Unit test policies** — write OPA test cases for every policy rule to prevent regressions; run tests in CI before deploying policy changes
3. **Shift-left validation** — run conftest against Terraform plans in CI before apply; catch policy violations before resources are created
4. **Gatekeeper for K8s** — deploy OPA Gatekeeper as a Kubernetes admission controller to enforce policies at deployment time
5. **Layered enforcement** — enforce policies at multiple points: PR review, CI pipeline, admission control, and runtime API authorization
6. **Exception handling** — support time-bounded policy exceptions with audit trails for legitimate edge cases
'''
    ),
    (
        "compliance/soc2-controls-automation",
        "Automate SOC2 compliance controls for a SaaS platform, including access management, change management, monitoring, and evidence collection.",
        '''SOC2 compliance controls automation:

```python
# --- SOC2 control framework and evidence collector ---

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import boto3
import httpx

logger = logging.getLogger(__name__)


class SOC2Category(str, Enum):
    SECURITY = "CC"       # Common Criteria (Security)
    AVAILABILITY = "A"    # Availability
    PROCESSING = "PI"     # Processing Integrity
    CONFIDENTIALITY = "C" # Confidentiality
    PRIVACY = "P"         # Privacy


class ControlStatus(str, Enum):
    PASSING = "passing"
    FAILING = "failing"
    NOT_EVALUATED = "not_evaluated"
    EXCEPTION = "exception"


@dataclass
class SOC2Control:
    """A single SOC2 control definition."""

    control_id: str          # e.g., CC6.1
    category: SOC2Category
    title: str
    description: str
    automated: bool = True   # Can be automatically verified
    evidence_type: str = ""  # screenshot, log, config, report
    evaluation_frequency: str = "daily"  # daily, weekly, monthly


@dataclass
class ControlEvidence:
    """Evidence collected for a control evaluation."""

    control_id: str
    timestamp: datetime
    status: ControlStatus
    evidence_data: dict[str, Any]
    evaluator: str  # automated, manual
    notes: str = ""


# --- SOC2 Control Definitions ---

SOC2_CONTROLS = [
    # CC6: Logical and Physical Access Controls
    SOC2Control(
        control_id="CC6.1",
        category=SOC2Category.SECURITY,
        title="Logical Access Security",
        description="Access to systems is restricted to authorized users through SSO and MFA",
        evidence_type="config",
    ),
    SOC2Control(
        control_id="CC6.2",
        category=SOC2Category.SECURITY,
        title="User Access Reviews",
        description="User access is reviewed quarterly and terminated on departure",
        evidence_type="report",
        evaluation_frequency="quarterly",
    ),
    SOC2Control(
        control_id="CC6.3",
        category=SOC2Category.SECURITY,
        title="Role-Based Access Control",
        description="Access is granted based on role with least privilege",
        evidence_type="config",
    ),

    # CC7: System Operations
    SOC2Control(
        control_id="CC7.1",
        category=SOC2Category.SECURITY,
        title="Monitoring and Detection",
        description="Infrastructure and application monitoring with alerting",
        evidence_type="config",
    ),
    SOC2Control(
        control_id="CC7.2",
        category=SOC2Category.SECURITY,
        title="Incident Response",
        description="Incident response procedures and runbooks are maintained",
        evidence_type="report",
        automated=False,
    ),

    # CC8: Change Management
    SOC2Control(
        control_id="CC8.1",
        category=SOC2Category.SECURITY,
        title="Change Management Process",
        description="All changes require PR review, CI/CD pipeline, and approval",
        evidence_type="log",
    ),

    # A1: Availability
    SOC2Control(
        control_id="A1.1",
        category=SOC2Category.AVAILABILITY,
        title="System Availability Monitoring",
        description="Uptime monitoring with SLO tracking and alerting",
        evidence_type="report",
    ),
    SOC2Control(
        control_id="A1.2",
        category=SOC2Category.AVAILABILITY,
        title="Disaster Recovery",
        description="DR procedures tested and documented",
        evidence_type="report",
        evaluation_frequency="quarterly",
        automated=False,
    ),

    # C1: Confidentiality
    SOC2Control(
        control_id="C1.1",
        category=SOC2Category.CONFIDENTIALITY,
        title="Encryption at Rest",
        description="All data stores use encryption at rest",
        evidence_type="config",
    ),
    SOC2Control(
        control_id="C1.2",
        category=SOC2Category.CONFIDENTIALITY,
        title="Encryption in Transit",
        description="All network communication uses TLS 1.2+",
        evidence_type="config",
    ),
]


@dataclass
class SOC2Evaluator:
    """Evaluates SOC2 controls and collects evidence."""

    session: boto3.Session
    github_token: str
    github_org: str
    okta_token: str
    okta_domain: str

    async def evaluate_all(self) -> list[ControlEvidence]:
        """Evaluate all automated SOC2 controls."""
        evidence: list[ControlEvidence] = []

        evaluators = {
            "CC6.1": self._eval_sso_mfa,
            "CC6.3": self._eval_rbac,
            "CC7.1": self._eval_monitoring,
            "CC8.1": self._eval_change_management,
            "A1.1": self._eval_availability,
            "C1.1": self._eval_encryption_at_rest,
            "C1.2": self._eval_encryption_in_transit,
        }

        for control in SOC2_CONTROLS:
            if control.control_id in evaluators:
                try:
                    result = await evaluators[control.control_id]()
                    evidence.append(result)
                except Exception as e:
                    evidence.append(
                        ControlEvidence(
                            control_id=control.control_id,
                            timestamp=datetime.utcnow(),
                            status=ControlStatus.FAILING,
                            evidence_data={"error": str(e)},
                            evaluator="automated",
                            notes=f"Evaluation error: {e}",
                        )
                    )

        return evidence

    async def _eval_sso_mfa(self) -> ControlEvidence:
        """CC6.1: Verify SSO and MFA enforcement."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Check Okta MFA policy
            resp = await client.get(
                f"https://{self.okta_domain}/api/v1/policies?type=MFA_ENROLL",
                headers={"Authorization": f"SSWS {self.okta_token}"},
            )
            resp.raise_for_status()
            policies = resp.json()

            mfa_enforced = any(
                p.get("status") == "ACTIVE"
                and p.get("conditions", {}).get("people", {}).get("groups", {}).get("include")
                for p in policies
            )

        return ControlEvidence(
            control_id="CC6.1",
            timestamp=datetime.utcnow(),
            status=ControlStatus.PASSING if mfa_enforced else ControlStatus.FAILING,
            evidence_data={
                "mfa_policies": len(policies),
                "mfa_enforced": mfa_enforced,
                "checked_at": datetime.utcnow().isoformat(),
            },
            evaluator="automated",
        )

    async def _eval_change_management(self) -> ControlEvidence:
        """CC8.1: Verify all changes go through PR + CI/CD."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Check branch protection rules
            repos_resp = await client.get(
                f"https://api.github.com/orgs/{self.github_org}/repos",
                headers={
                    "Authorization": f"token {self.github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params={"type": "all", "per_page": 100},
            )
            repos = repos_resp.json()

            protected = 0
            unprotected = []
            for repo in repos:
                bp_resp = await client.get(
                    f"https://api.github.com/repos/{self.github_org}"
                    f"/{repo['name']}/branches/main/protection",
                    headers={
                        "Authorization": f"token {self.github_token}",
                    },
                )
                if bp_resp.status_code == 200:
                    protection = bp_resp.json()
                    has_reviews = protection.get(
                        "required_pull_request_reviews", {}
                    ).get("required_approving_review_count", 0) >= 1
                    has_ci = bool(
                        protection.get("required_status_checks", {}).get("contexts")
                    )
                    if has_reviews and has_ci:
                        protected += 1
                    else:
                        unprotected.append(repo["name"])
                else:
                    unprotected.append(repo["name"])

        all_protected = len(unprotected) == 0
        return ControlEvidence(
            control_id="CC8.1",
            timestamp=datetime.utcnow(),
            status=ControlStatus.PASSING if all_protected else ControlStatus.FAILING,
            evidence_data={
                "total_repos": len(repos),
                "protected_repos": protected,
                "unprotected_repos": unprotected,
            },
            evaluator="automated",
        )

    async def _eval_encryption_at_rest(self) -> ControlEvidence:
        """C1.1: Verify encryption at rest for all data stores."""
        ec2 = self.session.client("ec2")
        rds = self.session.client("rds")
        s3 = self.session.client("s3")

        issues = []

        # Check EBS volumes
        volumes = ec2.describe_volumes()
        for vol in volumes["Volumes"]:
            if not vol.get("Encrypted"):
                issues.append(f"EBS volume {vol['VolumeId']} not encrypted")

        # Check RDS instances
        instances = rds.describe_db_instances()
        for db in instances["DBInstances"]:
            if not db.get("StorageEncrypted"):
                issues.append(
                    f"RDS {db['DBInstanceIdentifier']} not encrypted"
                )

        # Check S3 buckets
        buckets = s3.list_buckets()
        for bucket in buckets["Buckets"]:
            try:
                enc = s3.get_bucket_encryption(
                    Bucket=bucket["Name"]
                )
            except s3.exceptions.ClientError:
                issues.append(
                    f"S3 bucket {bucket['Name']} has no encryption config"
                )

        return ControlEvidence(
            control_id="C1.1",
            timestamp=datetime.utcnow(),
            status=(
                ControlStatus.PASSING if not issues
                else ControlStatus.FAILING
            ),
            evidence_data={
                "issues": issues[:20],
                "total_issues": len(issues),
            },
            evaluator="automated",
        )

    async def _eval_rbac(self) -> ControlEvidence:
        """CC6.3: Verify RBAC with least privilege."""
        iam = self.session.client("iam")
        issues = []

        # Check for users with direct policy attachments (should use groups)
        users = iam.list_users()
        for user in users["Users"]:
            policies = iam.list_attached_user_policies(
                UserName=user["UserName"]
            )
            if policies["AttachedPolicies"]:
                issues.append(
                    f"User {user['UserName']} has direct policy attachments"
                )

            # Check for admin access
            for pol in policies["AttachedPolicies"]:
                if "AdministratorAccess" in pol["PolicyArn"]:
                    issues.append(
                        f"User {user['UserName']} has AdministratorAccess"
                    )

        return ControlEvidence(
            control_id="CC6.3",
            timestamp=datetime.utcnow(),
            status=(
                ControlStatus.PASSING if not issues
                else ControlStatus.FAILING
            ),
            evidence_data={"issues": issues[:20], "total_issues": len(issues)},
            evaluator="automated",
        )

    async def _eval_monitoring(self) -> ControlEvidence:
        """CC7.1: Verify monitoring and alerting are active."""
        cloudwatch = self.session.client("cloudwatch")
        alarms = cloudwatch.describe_alarms(StateValue="ALARM")
        total_alarms = cloudwatch.describe_alarms()

        return ControlEvidence(
            control_id="CC7.1",
            timestamp=datetime.utcnow(),
            status=ControlStatus.PASSING,
            evidence_data={
                "total_alarms": len(total_alarms["MetricAlarms"]),
                "active_alarms": len(alarms["MetricAlarms"]),
            },
            evaluator="automated",
        )

    async def _eval_availability(self) -> ControlEvidence:
        """A1.1: Check uptime SLO compliance."""
        # Would query Prometheus/Grafana SLO dashboard
        return ControlEvidence(
            control_id="A1.1",
            timestamp=datetime.utcnow(),
            status=ControlStatus.PASSING,
            evidence_data={
                "slo_target": "99.9%",
                "current_uptime": "99.95%",
                "period": "last_30_days",
            },
            evaluator="automated",
        )

    async def _eval_encryption_in_transit(self) -> ControlEvidence:
        """C1.2: Verify TLS enforcement."""
        elbv2 = self.session.client("elbv2")
        lbs = elbv2.describe_load_balancers()
        issues = []

        for lb in lbs["LoadBalancers"]:
            listeners = elbv2.describe_listeners(
                LoadBalancerArn=lb["LoadBalancerArn"]
            )
            for listener in listeners["Listeners"]:
                if listener["Protocol"] == "HTTP" and listener["Port"] != 80:
                    issues.append(
                        f"LB {lb['LoadBalancerName']} has non-redirect HTTP listener"
                    )
                if listener["Protocol"] == "HTTPS":
                    policy = listener.get("SslPolicy", "")
                    if "TLS-1-0" in policy or "TLS-1-1" in policy:
                        issues.append(
                            f"LB {lb['LoadBalancerName']} uses outdated TLS policy"
                        )

        return ControlEvidence(
            control_id="C1.2",
            timestamp=datetime.utcnow(),
            status=(
                ControlStatus.PASSING if not issues
                else ControlStatus.FAILING
            ),
            evidence_data={"issues": issues, "total_issues": len(issues)},
            evaluator="automated",
        )
```

```yaml
# --- SOC2 evidence collection pipeline (GitHub Actions) ---

name: SOC2 Compliance Check

on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
  workflow_dispatch:

jobs:
  evaluate-controls:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/soc2-evaluator
          aws-region: us-east-1

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install -r requirements-compliance.txt

      - name: Run SOC2 evaluations
        env:
          GITHUB_TOKEN: ${{ secrets.COMPLIANCE_GITHUB_TOKEN }}
          OKTA_TOKEN: ${{ secrets.OKTA_API_TOKEN }}
          OKTA_DOMAIN: acme.okta.com
        run: |
          python -m compliance.evaluate_soc2 \
            --output evidence/$(date +%Y-%m-%d).json \
            --format json

      - name: Upload evidence to S3
        run: |
          aws s3 cp evidence/ s3://acme-compliance-evidence/soc2/ \
            --recursive \
            --sse aws:kms

      - name: Generate compliance dashboard
        run: python -m compliance.generate_dashboard

      - name: Alert on failures
        if: failure()
        run: |
          python -m compliance.notify_slack \
            --channel "#compliance-alerts" \
            --message "SOC2 control evaluation found failing controls"
```

| SOC2 Control | Automated Check | Evidence Type | Frequency |
|---|---|---|---|
| CC6.1 SSO/MFA | Okta API: MFA policy active | Config snapshot | Daily |
| CC6.2 Access reviews | Okta API: last review date | Report | Quarterly |
| CC6.3 RBAC | IAM: no direct policies, no admin | Config snapshot | Daily |
| CC7.1 Monitoring | CloudWatch: alarms configured | Config snapshot | Daily |
| CC7.2 Incident response | Manual: runbook review | Document | Quarterly |
| CC8.1 Change management | GitHub: branch protection rules | Config + logs | Daily |
| A1.1 Availability | Prometheus: SLO metrics | Metrics report | Daily |
| A1.2 DR testing | Manual: DR drill results | Test report | Quarterly |
| C1.1 Encryption at rest | AWS: EBS, RDS, S3 encryption | Config snapshot | Daily |
| C1.2 Encryption in transit | ALB: TLS policy, certificates | Config snapshot | Daily |

Key patterns:

1. **Automate evidence collection** — 80%+ of SOC2 controls can be verified automatically; collect evidence daily and store in immutable S3 with KMS encryption
2. **Continuous compliance** — shift from annual audits to daily automated checks; failing controls trigger immediate alerts, not year-end surprises
3. **Evidence preservation** — store evidence with timestamps in S3 with versioning and retention policies; auditors need historical proof
4. **Policy-as-code synergy** — OPA policies enforce controls preventively; SOC2 evaluations verify controls detectably; together they provide defense in depth
5. **Exception tracking** — document accepted risks with expiration dates, business justification, and compensating controls
6. **Dashboard for auditors** — generate a compliance dashboard showing control status, trend over time, and drill-down to evidence
'''
    ),
    (
        "compliance/audit-trail-evidence-collection",
        "Build an audit trail and evidence collection system that captures infrastructure changes, access events, and configuration drift for compliance reporting.",
        '''Audit trail and evidence collection system:

```python
# --- Centralized audit event model and collector ---

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    # Access events
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
    MFA_CHALLENGE = "auth.mfa_challenge"
    ACCESS_DENIED = "auth.access_denied"
    ROLE_CHANGE = "auth.role_change"

    # Infrastructure changes
    RESOURCE_CREATED = "infra.resource_created"
    RESOURCE_MODIFIED = "infra.resource_modified"
    RESOURCE_DELETED = "infra.resource_deleted"
    CONFIG_CHANGED = "infra.config_changed"
    DEPLOY = "infra.deploy"

    # Data access
    DATA_READ = "data.read"
    DATA_EXPORT = "data.export"
    PII_ACCESS = "data.pii_access"

    # Security events
    POLICY_VIOLATION = "security.policy_violation"
    VULNERABILITY_DETECTED = "security.vulnerability"
    SECRET_ACCESSED = "security.secret_accessed"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Immutable audit event."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: AuditEventType = AuditEventType.LOGIN
    timestamp: datetime = field(default_factory=datetime.utcnow)
    severity: AuditSeverity = AuditSeverity.INFO

    # Who
    actor_id: str = ""
    actor_email: str = ""
    actor_ip: str = ""
    actor_user_agent: str = ""

    # What
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    resource_name: str = ""

    # Where
    source_system: str = ""
    region: str = ""
    environment: str = ""

    # Details
    details: dict[str, Any] = field(default_factory=dict)
    previous_state: Optional[dict[str, Any]] = None
    new_state: Optional[dict[str, Any]] = None

    # Integrity
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum for tamper detection."""
        data = json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type.value,
                "timestamp": self.timestamp.isoformat(),
                "actor_id": self.actor_id,
                "action": self.action,
                "resource_id": self.resource_id,
                "details": self.details,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "actor": {
                "id": self.actor_id,
                "email": self.actor_email,
                "ip": self.actor_ip,
            },
            "action": self.action,
            "resource": {
                "type": self.resource_type,
                "id": self.resource_id,
                "name": self.resource_name,
            },
            "source": self.source_system,
            "region": self.region,
            "environment": self.environment,
            "details": self.details,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "checksum": self.checksum,
        }


@dataclass
class AuditStore:
    """Stores audit events in immutable append-only storage."""

    s3_bucket: str
    s3_prefix: str = "audit-events"
    session: Any = None  # boto3.Session

    def store_event(self, event: AuditEvent) -> str:
        """Store a single audit event in S3 (append-only)."""
        s3 = self.session.client("s3")
        date_prefix = event.timestamp.strftime("%Y/%m/%d")
        key = (
            f"{self.s3_prefix}/{date_prefix}/"
            f"{event.event_type.value}/{event.event_id}.json"
        )

        s3.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=json.dumps(event.to_dict(), indent=2),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
            Metadata={
                "event-type": event.event_type.value,
                "actor": event.actor_email,
                "checksum": event.checksum,
            },
        )

        logger.info(
            f"Audit event stored: {event.event_id} "
            f"({event.event_type.value})"
        )
        return key

    def store_batch(self, events: list[AuditEvent]) -> int:
        """Store multiple audit events."""
        stored = 0
        for event in events:
            try:
                self.store_event(event)
                stored += 1
            except Exception as e:
                logger.error(f"Failed to store event {event.event_id}: {e}")
        return stored

    def query_events(
        self,
        start_date: datetime,
        end_date: datetime,
        event_type: Optional[AuditEventType] = None,
        actor_email: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Query audit events from S3 (via Athena)."""
        # In production, use Athena or OpenSearch for querying
        s3 = self.session.client("s3")
        events: list[dict[str, Any]] = []

        # Simplified: list objects for date range
        current = start_date
        while current <= end_date:
            prefix = (
                f"{self.s3_prefix}/{current.strftime('%Y/%m/%d')}/"
            )
            if event_type:
                prefix += f"{event_type.value}/"

            resp = s3.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=prefix,
                MaxKeys=1000,
            )

            for obj in resp.get("Contents", []):
                body = s3.get_object(
                    Bucket=self.s3_bucket,
                    Key=obj["Key"],
                )
                event_data = json.loads(body["Body"].read())

                if actor_email and event_data["actor"]["email"] != actor_email:
                    continue
                events.append(event_data)

            current += timedelta(days=1)

        return events
```

```python
# --- AWS CloudTrail and Config integration ---

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import boto3


@dataclass
class CloudTrailCollector:
    """Collects CloudTrail events and converts to audit events."""

    session: boto3.Session
    region: str = "us-east-1"

    def collect_events(
        self,
        start_time: datetime,
        end_time: datetime,
        event_names: list[str] | None = None,
    ) -> list[AuditEvent]:
        """Collect CloudTrail events and convert to audit format."""
        ct = self.session.client("cloudtrail")
        events: list[AuditEvent] = []

        lookup_attrs = []
        if event_names:
            for name in event_names:
                lookup_attrs.append({
                    "AttributeKey": "EventName",
                    "AttributeValue": name,
                })

        paginator = ct.get_paginator("lookup_events")
        for page in paginator.paginate(
            StartTime=start_time,
            EndTime=end_time,
            LookupAttributes=lookup_attrs[:1] if lookup_attrs else [],
        ):
            for ct_event in page["Events"]:
                event_data = json.loads(ct_event.get("CloudTrailEvent", "{}"))
                audit_event = self._convert_event(ct_event, event_data)
                if audit_event:
                    events.append(audit_event)

        return events

    def _convert_event(
        self, ct_event: dict, event_data: dict
    ) -> AuditEvent | None:
        """Convert CloudTrail event to AuditEvent."""
        event_name = ct_event.get("EventName", "")
        user_identity = event_data.get("userIdentity", {})

        event_type_map = {
            "ConsoleLogin": AuditEventType.LOGIN,
            "CreateUser": AuditEventType.RESOURCE_CREATED,
            "DeleteUser": AuditEventType.RESOURCE_DELETED,
            "AttachUserPolicy": AuditEventType.ROLE_CHANGE,
            "RunInstances": AuditEventType.RESOURCE_CREATED,
            "TerminateInstances": AuditEventType.RESOURCE_DELETED,
            "CreateDBInstance": AuditEventType.RESOURCE_CREATED,
            "DeleteDBInstance": AuditEventType.RESOURCE_DELETED,
            "PutBucketPolicy": AuditEventType.CONFIG_CHANGED,
            "AuthorizeSecurityGroupIngress": AuditEventType.CONFIG_CHANGED,
        }

        event_type = event_type_map.get(event_name)
        if not event_type:
            return None

        return AuditEvent(
            event_type=event_type,
            timestamp=ct_event.get("EventTime", datetime.utcnow()),
            actor_id=user_identity.get("arn", ""),
            actor_email=user_identity.get("userName", ""),
            actor_ip=event_data.get("sourceIPAddress", ""),
            action=event_name,
            resource_type=ct_event.get("ResourceType", ""),
            resource_id=(
                ct_event.get("Resources", [{}])[0].get("ResourceName", "")
                if ct_event.get("Resources")
                else ""
            ),
            source_system="cloudtrail",
            region=event_data.get("awsRegion", ""),
            details={
                "event_source": event_data.get("eventSource", ""),
                "request_parameters": event_data.get("requestParameters", {}),
                "response_elements": event_data.get("responseElements", {}),
                "error_code": event_data.get("errorCode"),
                "error_message": event_data.get("errorMessage"),
            },
        )


@dataclass
class ConfigDriftDetector:
    """Detects configuration drift using AWS Config."""

    session: boto3.Session

    def get_compliance_summary(self) -> dict[str, Any]:
        """Get AWS Config compliance summary."""
        config = self.session.client("config")
        resp = config.get_compliance_summary_by_config_rule()

        summary = {
            "compliant_rules": 0,
            "non_compliant_rules": 0,
            "rules": [],
        }

        for rule_summary in resp["ComplianceSummariesByConfigRule"]:
            rule_name = rule_summary.get("ConfigRuleName", "")
            compliance = rule_summary.get("Compliance", {})
            compliance_type = compliance.get("ComplianceType", "UNKNOWN")

            if compliance_type == "COMPLIANT":
                summary["compliant_rules"] += 1
            else:
                summary["non_compliant_rules"] += 1

            summary["rules"].append({
                "name": rule_name,
                "compliance": compliance_type,
            })

        return summary

    def get_non_compliant_resources(
        self, rule_name: str
    ) -> list[dict[str, Any]]:
        """Get resources that violate a specific Config rule."""
        config = self.session.client("config")
        resources = []

        paginator = config.get_paginator(
            "get_compliance_details_by_config_rule"
        )
        for page in paginator.paginate(
            ConfigRuleName=rule_name,
            ComplianceTypes=["NON_COMPLIANT"],
        ):
            for result in page["EvaluationResults"]:
                resources.append({
                    "resource_type": result["EvaluationResultIdentifier"][
                        "EvaluationResultQualifier"
                    ]["ResourceType"],
                    "resource_id": result["EvaluationResultIdentifier"][
                        "EvaluationResultQualifier"
                    ]["ResourceId"],
                    "annotation": result.get("Annotation", ""),
                    "ordering_timestamp": str(
                        result.get("ResultRecordedTime", "")
                    ),
                })

        return resources
```

```hcl
# --- Terraform: audit infrastructure setup ---

# S3 bucket for audit events (immutable)
resource "aws_s3_bucket" "audit_events" {
  bucket = "acme-audit-events-${var.account_id}"

  tags = {
    Purpose   = "compliance-audit-trail"
    ManagedBy = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "audit_events" {
  bucket = aws_s3_bucket.audit_events.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Object lock: prevent deletion/modification
resource "aws_s3_bucket_object_lock_configuration" "audit_events" {
  bucket = aws_s3_bucket.audit_events.id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      years = 7  # 7-year retention for SOC2
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_events" {
  bucket = aws_s3_bucket.audit_events.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.audit.arn
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "audit_events" {
  bucket = aws_s3_bucket.audit_events.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudTrail for API-level auditing
resource "aws_cloudtrail" "main" {
  name                          = "acme-main-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  kms_key_id                    = aws_kms_key.audit.arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["arn:aws:s3"]
    }
  }

  insight_selector {
    insight_type = "ApiCallRateInsight"
  }
  insight_selector {
    insight_type = "ApiErrorRateInsight"
  }

  tags = {
    Purpose = "compliance-audit-trail"
  }
}

# Athena for querying audit data
resource "aws_athena_workgroup" "audit" {
  name = "audit-queries"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.audit_events.id}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.audit.arn
      }
    }
  }
}
```

| Audit Source | Events Captured | Storage | Retention |
|---|---|---|---|
| CloudTrail | AWS API calls (create, modify, delete) | S3 + CloudWatch Logs | 7 years |
| AWS Config | Configuration changes and drift | Config service | 7 years |
| VPC Flow Logs | Network traffic metadata | S3 / CloudWatch | 1 year |
| Application logs | Business events, data access | S3 via Fluentbit | 3 years |
| Okta/SSO | Authentication events | Okta + S3 export | 7 years |
| GitHub | Code changes, PR reviews, deployments | GitHub + S3 export | 7 years |
| Custom audit events | Application-specific actions | S3 (audit bucket) | 7 years |

Key patterns:

1. **Immutable storage** — use S3 Object Lock in COMPLIANCE mode to prevent audit log deletion or modification for the retention period
2. **Checksum integrity** — compute SHA-256 checksum for each audit event to detect tampering during forensic investigation
3. **Centralized collection** — aggregate events from CloudTrail, Config, application logs, and SSO into a single queryable audit store
4. **Athena for querying** — use Amazon Athena to run SQL queries across audit data without loading into a database
5. **Real-time alerting** — stream high-severity events (access denied, policy violations) to Slack/PagerDuty immediately
6. **7-year retention** — SOC2 and many regulatory frameworks require 7-year audit trail retention; automate lifecycle policies
'''
    ),
    (
        "compliance/cis-benchmark-scanning",
        "Implement automated CIS benchmark scanning for Kubernetes clusters and cloud accounts using kube-bench, ScoutSuite, and Prowler.",
        '''CIS benchmark scanning automation:

```python
# --- CIS benchmark scanning orchestrator ---

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CISBenchmarkResult:
    """Result of a CIS benchmark scan."""

    benchmark: str          # e.g., "CIS Kubernetes Benchmark v1.8"
    scanner: str            # kube-bench, prowler, scoutsuite
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    info: int = 0
    score_pct: float = 0.0
    findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class KubeBenchScanner:
    """Runs kube-bench CIS Kubernetes Benchmark scans."""

    kubeconfig: str | None = None

    def scan(self, target: str = "node") -> CISBenchmarkResult:
        """Run kube-bench scan against Kubernetes cluster."""
        cmd = ["kube-bench", "run", "--json"]

        if target == "master":
            cmd.extend(["--targets", "master"])
        elif target == "node":
            cmd.extend(["--targets", "node"])
        elif target == "policies":
            cmd.extend(["--targets", "policies"])

        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])

        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)

        findings = []
        totals = {"pass": 0, "fail": 0, "warn": 0, "info": 0}

        for control in data.get("Controls", []):
            for test in control.get("tests", []):
                for check in test.get("results", []):
                    status = check.get("status", "").lower()
                    totals[status] = totals.get(status, 0) + 1

                    if status in ("fail", "warn"):
                        findings.append({
                            "id": check.get("test_number", ""),
                            "description": check.get("test_desc", ""),
                            "status": status,
                            "section": control.get("text", ""),
                            "remediation": check.get("remediation", ""),
                            "scored": check.get("scored", True),
                        })

        total = sum(totals.values())
        return CISBenchmarkResult(
            benchmark="CIS Kubernetes Benchmark v1.8",
            scanner="kube-bench",
            total_checks=total,
            passed=totals["pass"],
            failed=totals["fail"],
            warned=totals["warn"],
            info=totals["info"],
            score_pct=round(totals["pass"] / max(total, 1) * 100, 1),
            findings=findings,
        )


@dataclass
class ProwlerScanner:
    """Runs Prowler CIS AWS Benchmark scans."""

    profile: str = "default"
    region: str = "us-east-1"

    def scan(
        self,
        checks: list[str] | None = None,
        severity: str = "critical,high",
    ) -> CISBenchmarkResult:
        """Run Prowler AWS security assessment."""
        cmd = [
            "prowler", "aws",
            "--output-formats", "json",
            "--output-directory", "/tmp/prowler",
            "--severity", severity,
            "--region", self.region,
            "--profile", self.profile,
        ]

        if checks:
            cmd.extend(["--checks", ",".join(checks)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Parse Prowler JSON output
        findings = []
        totals = {"PASS": 0, "FAIL": 0, "WARN": 0, "INFO": 0}

        output_file = "/tmp/prowler/prowler-output.json"
        try:
            with open(output_file) as f:
                for line in f:
                    check = json.loads(line)
                    status = check.get("StatusExtended", check.get("Status", "INFO"))
                    status_key = "PASS" if status == "PASS" else "FAIL" if status == "FAIL" else "WARN"
                    totals[status_key] = totals.get(status_key, 0) + 1

                    if status_key in ("FAIL", "WARN"):
                        findings.append({
                            "check_id": check.get("CheckID", ""),
                            "check_title": check.get("CheckTitle", ""),
                            "severity": check.get("Severity", ""),
                            "status": status,
                            "service": check.get("ServiceName", ""),
                            "region": check.get("Region", ""),
                            "resource_id": check.get("ResourceId", ""),
                            "remediation": check.get("Remediation", {}).get(
                                "Recommendation", {}
                            ).get("Text", ""),
                        })
        except FileNotFoundError:
            logger.error("Prowler output not found")

        total = sum(totals.values())
        return CISBenchmarkResult(
            benchmark="CIS AWS Foundations Benchmark v3.0",
            scanner="prowler",
            total_checks=total,
            passed=totals["PASS"],
            failed=totals["FAIL"],
            warned=totals["WARN"],
            info=totals["INFO"],
            score_pct=round(totals["PASS"] / max(total, 1) * 100, 1),
            findings=findings,
        )


@dataclass
class ScoutSuiteScanner:
    """Runs ScoutSuite multi-cloud security auditing."""

    provider: str = "aws"  # aws, gcp, azure

    def scan(self) -> CISBenchmarkResult:
        """Run ScoutSuite security assessment."""
        cmd = [
            "scout",
            self.provider,
            "--report-dir", "/tmp/scoutsuite",
            "--result-format", "json",
            "--no-browser",
        ]

        subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Parse ScoutSuite results
        results_file = f"/tmp/scoutsuite/scoutsuite-results/scoutsuite_results_{self.provider}.json"
        with open(results_file) as f:
            data = json.load(f)

        findings = []
        totals = {"pass": 0, "fail": 0, "warn": 0}

        for service_name, service_data in data.get("services", {}).items():
            for rule_name, rule_data in service_data.get("findings", {}).items():
                flagged = rule_data.get("flagged_items", 0)
                checked = rule_data.get("checked_items", 0)

                if flagged > 0:
                    totals["fail"] += 1
                    findings.append({
                        "service": service_name,
                        "rule": rule_name,
                        "description": rule_data.get("description", ""),
                        "severity": rule_data.get("level", "warning"),
                        "flagged_items": flagged,
                        "checked_items": checked,
                        "rationale": rule_data.get("rationale", ""),
                        "remediation": rule_data.get("remediation", ""),
                    })
                else:
                    totals["pass"] += 1

        total = sum(totals.values())
        return CISBenchmarkResult(
            benchmark=f"ScoutSuite {self.provider.upper()} Assessment",
            scanner="scoutsuite",
            total_checks=total,
            passed=totals["pass"],
            failed=totals["fail"],
            warned=totals["warn"],
            score_pct=round(totals["pass"] / max(total, 1) * 100, 1),
            findings=findings,
        )
```

```yaml
# --- Kubernetes CronJob for periodic CIS scanning ---

apiVersion: batch/v1
kind: CronJob
metadata:
  name: kube-bench-scan
  namespace: security
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: kube-bench
          hostPID: true
          containers:
            - name: kube-bench
              image: docker.io/aquasec/kube-bench:v0.7.0
              command:
                - /bin/sh
                - -c
                - |
                  kube-bench run --json > /tmp/results.json
                  # Upload results to S3
                  DATE=$(date +%Y-%m-%d)
                  aws s3 cp /tmp/results.json \
                    s3://acme-compliance-evidence/cis-k8s/${DATE}/kube-bench.json \
                    --sse aws:kms

                  # Check for critical failures
                  FAILURES=$(cat /tmp/results.json | jq '[.Controls[].tests[].results[] | select(.status=="FAIL")] | length')
                  if [ "$FAILURES" -gt 0 ]; then
                    echo "CIS scan found $FAILURES failures"
                    # Send alert
                    curl -X POST "$SLACK_WEBHOOK" \
                      -H 'Content-Type: application/json' \
                      -d "{\"text\": \":warning: kube-bench found $FAILURES CIS failures\"}"
                  fi
              env:
                - name: AWS_REGION
                  value: us-east-1
                - name: SLACK_WEBHOOK
                  valueFrom:
                    secretKeyRef:
                      name: slack-webhook
                      key: url
              volumeMounts:
                - name: var-lib-etcd
                  mountPath: /var/lib/etcd
                  readOnly: true
                - name: etc-kubernetes
                  mountPath: /etc/kubernetes
                  readOnly: true
          volumes:
            - name: var-lib-etcd
              hostPath:
                path: /var/lib/etcd
            - name: etc-kubernetes
              hostPath:
                path: /etc/kubernetes
          restartPolicy: OnFailure

---
# RBAC for kube-bench
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kube-bench
  namespace: security

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kube-bench
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods", "services", "configmaps"]
    verbs: ["get", "list"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
    verbs: ["get", "list"]
  - apiGroups: ["policy"]
    resources: ["podsecuritypolicies"]
    verbs: ["get", "list"]
```

```python
# --- Compliance dashboard and trending ---

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ComplianceDashboard:
    """Generates compliance dashboard data from scan results."""

    def generate_summary(
        self, results: list[CISBenchmarkResult]
    ) -> dict[str, Any]:
        """Generate compliance summary across all scanners."""
        overall_passed = sum(r.passed for r in results)
        overall_total = sum(r.total_checks for r in results)
        overall_failed = sum(r.failed for r in results)

        critical_findings = []
        for result in results:
            for finding in result.findings:
                severity = finding.get("severity", "").lower()
                if severity in ("critical", "high"):
                    critical_findings.append({
                        "scanner": result.scanner,
                        "benchmark": result.benchmark,
                        **finding,
                    })

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "overall_score_pct": round(
                overall_passed / max(overall_total, 1) * 100, 1
            ),
            "total_checks": overall_total,
            "total_passed": overall_passed,
            "total_failed": overall_failed,
            "by_scanner": [
                {
                    "scanner": r.scanner,
                    "benchmark": r.benchmark,
                    "score_pct": r.score_pct,
                    "passed": r.passed,
                    "failed": r.failed,
                    "findings_count": len(r.findings),
                }
                for r in results
            ],
            "critical_findings": sorted(
                critical_findings,
                key=lambda f: f.get("severity", "low"),
                reverse=True,
            )[:20],
            "remediation_priorities": self._prioritize_remediations(
                critical_findings
            ),
        }

    def _prioritize_remediations(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Prioritize remediations by severity and frequency."""
        remediation_map: dict[str, dict[str, Any]] = {}

        for finding in findings:
            key = finding.get("check_id") or finding.get("id") or finding.get("rule", "")
            if key not in remediation_map:
                remediation_map[key] = {
                    "check": key,
                    "description": finding.get("description") or finding.get("check_title", ""),
                    "severity": finding.get("severity", "medium"),
                    "remediation": finding.get("remediation", ""),
                    "count": 0,
                }
            remediation_map[key]["count"] += 1

        priorities = sorted(
            remediation_map.values(),
            key=lambda r: (
                {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                    r["severity"], 0
                ),
                r["count"],
            ),
            reverse=True,
        )
        return priorities[:10]
```

| Scanner | Target | Benchmark | Output | Frequency |
|---|---|---|---|---|
| kube-bench | Kubernetes nodes | CIS Kubernetes Benchmark | JSON | Daily |
| Prowler | AWS account | CIS AWS Foundations | JSON/HTML | Daily |
| ScoutSuite | Multi-cloud | Custom rules + CIS | JSON/HTML | Weekly |
| Trivy | Container images | CIS Docker Benchmark | JSON/SARIF | Per build |
| Lynis | Linux hosts | CIS Linux Benchmark | Text/JSON | Weekly |
| InSpec | Any target | Custom + CIS profiles | JSON/HTML | Per AMI build |
| CloudSploit | AWS/Azure/GCP | CIS multi-cloud | JSON | Daily |

Key patterns:

1. **Daily automated scanning** — run CIS benchmarks automatically via CronJobs; store results in immutable S3 for audit trail
2. **Multi-layer scanning** — scan at every layer: cloud account (Prowler), Kubernetes (kube-bench), containers (Trivy), and OS (Lynis)
3. **Prioritized remediation** — rank findings by severity and frequency; focus on critical/high findings that affect multiple resources
4. **Trend tracking** — store results over time and track compliance score trends; regressions trigger alerts
5. **Shift-left scanning** — run CIS checks during AMI builds (InSpec) and container builds (Trivy) to catch issues before deployment
6. **Exception management** — document accepted risks with business justification, compensating controls, and review dates
'''
    ),
]
"""
