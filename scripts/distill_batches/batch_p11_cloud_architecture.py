"""
Batch P11 — Cloud Architecture Patterns
Covers: AWS well-architected, Terraform IaC, multi-cloud strategies,
serverless architecture patterns, cloud-native security.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. AWS Well-Architected Patterns ---
    (
        "cloud-architecture/aws-well-architected-patterns",
        r"""Explain AWS well-architected framework patterns in production including multi-AZ deployment strategies, auto-scaling groups with predictive scaling, ALB versus NLB load balancer selection, CloudFront edge caching with origin shield, S3 lifecycle policies for cost optimization, and reserved instance strategies for compute savings.""",
        r"""# AWS Well-Architected Patterns: Multi-AZ, Auto-Scaling, Load Balancing, and Cost Optimization

## The Well-Architected Framework in Practice

The AWS Well-Architected Framework provides a structured approach to evaluating cloud architectures across six pillars: **Operational Excellence**, **Security**, **Reliability**, **Performance Efficiency**, **Cost Optimization**, and **Sustainability**. **However**, many teams treat these pillars as a checklist rather than a continuous engineering discipline. The real value comes from understanding the **trade-offs** between pillars — for example, maximizing reliability through multi-AZ redundancy increases cost, and optimizing performance with larger instance types conflicts with cost optimization goals.

A **common mistake** is designing for a single Availability Zone in production. AWS Availability Zones are physically isolated data centers within a region, each with independent power, cooling, and networking. When one AZ experiences an outage (which happens more often than people realize), your entire application goes down if you have no cross-AZ redundancy. **Therefore**, every production workload must span at least two AZs, and ideally three for critical systems.

## Multi-AZ Deployment Architecture

The foundation of a reliable AWS architecture is distributing resources across multiple Availability Zones. This applies to compute (EC2, ECS, Lambda), databases (RDS Multi-AZ, DynamoDB global tables), and caching (ElastiCache with replica nodes in different AZs).

```python
# aws_infra/multi_az_config.py
# Configuration builder for multi-AZ deployments using boto3

import boto3
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class MultiAZConfig:
    # Defines a multi-AZ deployment configuration
    region: str
    environment: str
    min_azs: int = 2
    preferred_azs: int = 3
    vpc_cidr: str = "10.0.0.0/16"
    subnet_mask_bits: int = 24

    def get_available_azs(self) -> list[str]:
        ec2 = boto3.client("ec2", region_name=self.region)
        response = ec2.describe_availability_zones(
            Filters=[{"Name": "state", "Values": ["available"]}]
        )
        azs = [az["ZoneName"] for az in response["AvailabilityZones"]]
        if len(azs) < self.min_azs:
            raise RuntimeError(
                f"Region {self.region} has only {len(azs)} AZs, "
                f"need at least {self.min_azs}"
            )
        return azs[: self.preferred_azs]

    def generate_subnet_cidrs(self) -> dict[str, list[dict[str, str]]]:
        # Generate public and private subnet CIDRs for each AZ
        azs = self.get_available_azs()
        subnets: dict[str, list[dict[str, str]]] = {
            "public": [],
            "private": [],
            "data": [],
        }
        base_parts = self.vpc_cidr.split(".")
        for i, az in enumerate(azs):
            subnets["public"].append({
                "az": az,
                "cidr": f"{base_parts[0]}.{base_parts[1]}.{i * 10}.0/{self.subnet_mask_bits}",
            })
            subnets["private"].append({
                "az": az,
                "cidr": f"{base_parts[0]}.{base_parts[1]}.{i * 10 + 1}.0/{self.subnet_mask_bits}",
            })
            subnets["data"].append({
                "az": az,
                "cidr": f"{base_parts[0]}.{base_parts[1]}.{i * 10 + 2}.0/{self.subnet_mask_bits}",
            })
        return subnets


@dataclass
class AutoScalingConfig:
    # Auto-scaling group configuration with predictive scaling
    group_name: str
    min_capacity: int
    max_capacity: int
    desired_capacity: int
    target_cpu_utilization: float = 60.0
    scale_in_cooldown: int = 300
    scale_out_cooldown: int = 60
    enable_predictive_scaling: bool = True
    predictive_mode: str = "ForecastAndScale"  # or ForecastOnly

    def create_scaling_policy(self) -> dict:
        asg_client = boto3.client("autoscaling")

        # Target tracking for reactive scaling
        asg_client.put_scaling_policy(
            AutoScalingGroupName=self.group_name,
            PolicyName=f"{self.group_name}-target-tracking",
            PolicyType="TargetTrackingScaling",
            TargetTrackingConfiguration={
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "ASGAverageCPUUtilization"
                },
                "TargetValue": self.target_cpu_utilization,
                "ScaleInCooldown": self.scale_in_cooldown,
                "ScaleOutCooldown": self.scale_out_cooldown,
            },
        )

        # Predictive scaling learns traffic patterns
        if self.enable_predictive_scaling:
            asg_client.put_scaling_policy(
                AutoScalingGroupName=self.group_name,
                PolicyName=f"{self.group_name}-predictive",
                PolicyType="PredictiveScaling",
                PredictiveScalingConfiguration={
                    "MetricSpecifications": [{
                        "TargetValue": self.target_cpu_utilization,
                        "PredefinedMetricPairSpecification": {
                            "PredefinedMetricType": "ASGCPUUtilization"
                        },
                    }],
                    "Mode": self.predictive_mode,
                    "SchedulingBufferTime": 300,
                },
            )
        return {"status": "policies_created", "group": self.group_name}
```

**Best practice**: Combine target-tracking scaling (reactive) with predictive scaling (proactive). Predictive scaling analyzes 14 days of historical metrics and pre-provisions capacity before anticipated load spikes. This eliminates the latency penalty of reactive scaling where instances take 3-5 minutes to become healthy.

## ALB vs NLB Load Balancer Selection

Choosing between Application Load Balancer (ALB) and Network Load Balancer (NLB) is a critical architectural decision. **Because** they operate at different OSI layers, they have fundamentally different capabilities and performance characteristics.

```python
# aws_infra/load_balancer_factory.py
# Factory pattern for selecting and configuring the right load balancer

import boto3
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class LBType(Enum):
    ALB = "application"
    NLB = "network"

@dataclass
class LoadBalancerSpec:
    # Specification for load balancer creation
    name: str
    lb_type: LBType
    internal: bool = False
    subnets: list[str] = field(default_factory=list)
    security_groups: list[str] = field(default_factory=list)
    idle_timeout: int = 60
    enable_waf: bool = False
    enable_access_logs: bool = True
    cross_zone: bool = True

def select_load_balancer(
    needs_path_routing: bool,
    needs_host_routing: bool,
    needs_websockets: bool,
    needs_grpc: bool,
    needs_static_ip: bool,
    needs_ultra_low_latency: bool,
    peak_connections: int,
    protocol: str = "HTTPS",
) -> LBType:
    # Decision matrix for ALB vs NLB selection
    # ALB: Layer 7, content-based routing, WAF integration
    # NLB: Layer 4, ultra-low latency, static IPs, millions of connections

    if needs_static_ip:
        # NLB provides static Elastic IPs per AZ
        # ALB only provides DNS names that resolve to changing IPs
        return LBType.NLB

    if needs_ultra_low_latency and peak_connections > 1_000_000:
        # NLB handles millions of requests per second at <100us latency
        return LBType.NLB

    if protocol in ("TCP", "UDP", "TLS"):
        # Non-HTTP protocols require NLB
        return LBType.NLB

    if any([needs_path_routing, needs_host_routing,
            needs_websockets, needs_grpc]):
        # ALB provides Layer 7 features
        return LBType.ALB

    # Default to ALB because it integrates with WAF, Cognito,
    # and provides richer metrics
    return LBType.ALB
```

The **trade-off** between ALB and NLB centers on features versus performance. ALB gives you path-based routing, host-based routing, WebSocket support, gRPC support, WAF integration, and authentication offloading. NLB gives you static IPs, sub-millisecond latency, and the ability to handle millions of simultaneous connections. A **pitfall** is using NLB when you need WAF protection — NLB does not integrate with AWS WAF, so you must place a CloudFront distribution in front of it for DDoS protection.

## CloudFront and S3 Lifecycle Cost Optimization

CloudFront with **Origin Shield** adds an additional caching layer between regional edge caches and your origin, reducing origin load by up to 90%. S3 lifecycle policies automate storage class transitions to optimize cost.

```python
# aws_infra/cost_optimization.py

import boto3
from datetime import datetime
from typing import Any

def configure_s3_lifecycle(
    bucket_name: str,
    ia_transition_days: int = 30,
    glacier_transition_days: int = 90,
    deep_archive_days: int = 180,
    expiration_days: Optional[int] = 365,
    noncurrent_expiration_days: int = 30,
) -> dict[str, Any]:
    # Configure S3 lifecycle rules for automatic cost optimization
    # Transitions: Standard -> IA -> Glacier -> Deep Archive -> Delete
    s3 = boto3.client("s3")

    rules: list[dict[str, Any]] = [
        {
            "ID": "optimize-storage-classes",
            "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "Transitions": [
                {"Days": ia_transition_days, "StorageClass": "STANDARD_IA"},
                {"Days": glacier_transition_days, "StorageClass": "GLACIER"},
                {"Days": deep_archive_days, "StorageClass": "DEEP_ARCHIVE"},
            ],
            "NoncurrentVersionTransitions": [
                {"NoncurrentDays": 7, "StorageClass": "GLACIER"},
            ],
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": noncurrent_expiration_days
            },
        },
        {
            "ID": "abort-incomplete-uploads",
            "Status": "Enabled",
            "Filter": {"Prefix": ""},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
        },
    ]

    if expiration_days:
        rules[0]["Expiration"] = {"Days": expiration_days}

    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket_name,
        LifecycleConfiguration={"Rules": rules},
    )
    return {"bucket": bucket_name, "rules_applied": len(rules)}


def estimate_monthly_savings(
    total_gb: float,
    access_pattern: str,  # "hot", "warm", "cold", "archive"
) -> dict[str, float]:
    # Estimate savings from storage class optimization
    # Prices per GB/month (us-east-1, approximate)
    prices = {
        "STANDARD": 0.023,
        "STANDARD_IA": 0.0125,
        "GLACIER_IR": 0.004,
        "GLACIER": 0.0036,
        "DEEP_ARCHIVE": 0.00099,
    }
    pattern_map = {
        "hot": "STANDARD",
        "warm": "STANDARD_IA",
        "cold": "GLACIER",
        "archive": "DEEP_ARCHIVE",
    }
    optimal_class = pattern_map.get(access_pattern, "STANDARD")
    current_cost = total_gb * prices["STANDARD"]
    optimized_cost = total_gb * prices[optimal_class]
    return {
        "current_monthly_cost": round(current_cost, 2),
        "optimized_monthly_cost": round(optimized_cost, 2),
        "monthly_savings": round(current_cost - optimized_cost, 2),
        "annual_savings": round((current_cost - optimized_cost) * 12, 2),
        "recommended_class": optimal_class,
    }
```

## Summary / Key Takeaways

- **Multi-AZ is non-negotiable** for production workloads. Distribute compute, databases, and caches across at least 2 AZs, ideally 3, to survive AZ-level failures.
- **Combine predictive and reactive auto-scaling** because predictive scaling eliminates the 3-5 minute warm-up penalty by pre-provisioning capacity based on historical patterns.
- **Choose ALB for Layer 7 features** (path routing, WAF, auth offload) and **NLB for Layer 4 performance** (static IPs, millions of connections, sub-millisecond latency). A common **pitfall** is using NLB without CloudFront when WAF protection is needed.
- **CloudFront Origin Shield** reduces origin load by up to 90% and should be enabled for any S3 or API origin with global traffic.
- **S3 lifecycle policies** automate storage class transitions. Moving infrequently accessed data from Standard to IA saves ~46%, and archival data to Deep Archive saves ~96%.
- **Reserved Instances and Savings Plans** reduce compute cost by 40-72% for predictable baseline workloads. Use on-demand and spot only for variable burst capacity.
- **Best practice**: Implement tagging strategies from day one for cost allocation. Without consistent tags, cost attribution across teams and projects becomes impossible at scale.
"""
    ),

    # --- 2. Infrastructure as Code with Terraform ---
    (
        "cloud-architecture/terraform-infrastructure-as-code",
        r"""Describe advanced Terraform infrastructure as code patterns including module composition and versioning strategies, remote state management with locking, workspace-based environment separation, provider configuration patterns, drift detection and remediation workflows, and testing infrastructure code with Terratest and policy validation.""",
        r"""# Infrastructure as Code with Terraform: Modules, State Management, and Testing

## Why Terraform Dominates IaC

Terraform has become the de facto standard for infrastructure as code **because** it provides a declarative, cloud-agnostic approach to provisioning resources. Unlike imperative tools like Ansible or cloud-specific tools like CloudFormation, Terraform's **HCL (HashiCorp Configuration Language)** describes the desired end state, and the Terraform engine computes the plan to reach that state. **However**, Terraform's power comes with complexity — state management, module design, and provider versioning require disciplined engineering practices to avoid catastrophic mistakes.

The **trade-off** with Terraform versus cloud-native IaC (CloudFormation, ARM templates, Deployment Manager) is portability versus integration depth. Terraform works across clouds but sometimes lags behind native IaC in supporting new services. A **common mistake** is choosing Terraform for a single-cloud shop and then fighting with provider gaps. **Therefore**, evaluate whether multi-cloud portability genuinely matters for your organization before committing to Terraform.

## Module Composition and Versioning

Well-designed Terraform modules are the building blocks of maintainable infrastructure. Modules should encapsulate a single logical concern — a VPC, a Kubernetes cluster, an RDS database — and expose a clean interface through variables and outputs.

```hcl
# modules/vpc/main.tf
# Reusable VPC module with multi-AZ subnets and NAT gateways

variable "name" {
  type        = string
  description = "Name prefix for all VPC resources"
}

variable "cidr_block" {
  type        = string
  default     = "10.0.0.0/16"
  description = "CIDR block for the VPC"
}

variable "availability_zones" {
  type        = list(string)
  description = "List of AZs to deploy subnets into"
}

variable "enable_nat_gateway" {
  type        = bool
  default     = true
  description = "Whether to create NAT gateways for private subnets"
}

variable "single_nat_gateway" {
  type        = bool
  default     = false
  description = "Use a single NAT gateway (cost saving, less HA)"
}

resource "aws_vpc" "main" {
  cidr_block           = var.cidr_block
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "${var.name}-vpc"
    ManagedBy   = "terraform"
    Module      = "vpc"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.cidr_block, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name}-public-${var.availability_zones[count.index]}"
    Tier = "public"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.cidr_block, 8, count.index + 100)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.name}-private-${var.availability_zones[count.index]}"
    Tier = "private"
  }
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
```

**Best practice**: Version your modules using Git tags and reference them with version constraints. Never use branch references (like `ref=main`) in production because a breaking change upstream immediately affects all consumers.

## Remote State Management with Locking

Terraform state is the mapping between your HCL configuration and the real-world infrastructure. Losing or corrupting state is catastrophic — it makes Terraform unable to manage existing resources. **Therefore**, remote state with locking is mandatory for any team environment.

```python
# scripts/terraform_state_manager.py
# Utility to initialize and validate Terraform remote state configuration

import subprocess
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class StateBackendConfig:
    # S3 backend configuration for Terraform state
    bucket: str
    key: str
    region: str
    dynamodb_table: str
    encrypt: bool = True
    kms_key_id: Optional[str] = None

    def to_backend_config(self) -> dict[str, str]:
        config = {
            "bucket": self.bucket,
            "key": self.key,
            "region": self.region,
            "dynamodb_table": self.dynamodb_table,
            "encrypt": str(self.encrypt).lower(),
        }
        if self.kms_key_id:
            config["kms_key_id"] = self.kms_key_id
        return config

    def generate_init_args(self) -> list[str]:
        args = ["-backend=true"]
        for k, v in self.to_backend_config().items():
            args.append(f"-backend-config={k}={v}")
        return args


def run_terraform_plan(
    working_dir: str,
    var_file: Optional[str] = None,
    target: Optional[str] = None,
    detailed_exitcode: bool = True,
) -> dict:
    # Run terraform plan and parse the output
    cmd = ["terraform", "plan", "-no-color", "-json"]
    if detailed_exitcode:
        cmd.append("-detailed-exitcode")
    if var_file:
        cmd.extend(["-var-file", var_file])
    if target:
        cmd.extend(["-target", target])

    result = subprocess.run(
        cmd, cwd=working_dir, capture_output=True, text=True
    )

    changes = {"create": 0, "update": 0, "delete": 0, "no_op": 0}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("type") == "change_summary":
                ch = entry.get("changes", {})
                changes["create"] = ch.get("add", 0)
                changes["update"] = ch.get("change", 0)
                changes["delete"] = ch.get("remove", 0)
        except json.JSONDecodeError:
            continue

    return {
        "exit_code": result.returncode,
        "has_changes": result.returncode == 2 if detailed_exitcode else bool(result.stdout),
        "changes": changes,
        "stderr": result.stderr,
    }


def detect_drift(working_dir: str, var_file: Optional[str] = None) -> dict:
    # Detect configuration drift by running refresh then plan
    # Drift occurs when real infrastructure diverges from state
    subprocess.run(
        ["terraform", "refresh", "-no-color"],
        cwd=working_dir, capture_output=True, text=True,
    )
    plan_result = run_terraform_plan(working_dir, var_file)

    drift_detected = plan_result["has_changes"]
    return {
        "drift_detected": drift_detected,
        "changes": plan_result["changes"],
        "remediation": "Run terraform apply to reconcile" if drift_detected else "No drift",
    }
```

A critical **pitfall** with state management is the state locking mechanism. Without DynamoDB-backed locking, two engineers running `terraform apply` simultaneously can corrupt state. The DynamoDB lock table uses a `LockID` attribute that Terraform automatically manages — never delete or modify these entries manually.

## Testing Infrastructure with Terratest

Infrastructure code must be tested just like application code. **However**, testing IaC is fundamentally different because you are creating real cloud resources. Terratest, written in Go, provides the framework for deploying infrastructure, validating it, and destroying it.

```go
// test/vpc_test.go
// Terratest integration test for the VPC module

package test

import (
    "testing"
    "fmt"

    "github.com/gruntwork-io/terratest/modules/aws"
    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestVpcModule(t *testing.T) {
    t.Parallel()

    awsRegion := "us-east-1"
    availabilityZones := []string{
        "us-east-1a", "us-east-1b", "us-east-1c",
    }

    terraformOptions := terraform.WithDefaultRetryableErrors(t, &terraform.Options{
        TerraformDir: "../modules/vpc",
        Vars: map[string]interface{}{
            "name":               fmt.Sprintf("test-vpc-%s", t.Name()),
            "cidr_block":         "10.99.0.0/16",
            "availability_zones": availabilityZones,
            "enable_nat_gateway": true,
            "single_nat_gateway": true,
        },
        EnvVars: map[string]string{
            "AWS_DEFAULT_REGION": awsRegion,
        },
    })

    // Ensure cleanup even if test fails
    defer terraform.Destroy(t, terraformOptions)

    // Deploy the module
    terraform.InitAndApply(t, terraformOptions)

    // Validate outputs
    vpcID := terraform.Output(t, terraformOptions, "vpc_id")
    require.NotEmpty(t, vpcID, "VPC ID should not be empty")

    publicSubnetIDs := terraform.OutputList(t, terraformOptions, "public_subnet_ids")
    assert.Len(t, publicSubnetIDs, len(availabilityZones),
        "Should have one public subnet per AZ")

    privateSubnetIDs := terraform.OutputList(t, terraformOptions, "private_subnet_ids")
    assert.Len(t, privateSubnetIDs, len(availabilityZones),
        "Should have one private subnet per AZ")

    // Verify VPC exists in AWS
    vpc := aws.GetVpcById(t, vpcID, awsRegion)
    assert.Equal(t, "10.99.0.0/16", vpc.CidrBlock)
    assert.True(t, vpc.EnableDnsHostnames, "DNS hostnames should be enabled")
}
```

## Workspace and Environment Separation

Terraform workspaces provide lightweight environment isolation using the same configuration with different state files. **However**, workspaces have limitations — they share the same backend configuration and provider versions. **Best practice** for production is to use a directory-per-environment structure for large deployments and workspaces only for simple multi-environment setups.

## Summary / Key Takeaways

- **Module design** should follow the single-responsibility principle. Each module encapsulates one logical concern with a clean interface of variables and outputs. Version modules with Git tags, never branch references.
- **Remote state with locking** is mandatory for teams. Use S3 + DynamoDB for AWS, GCS + Cloud Storage for GCP. **Because** state corruption is catastrophic, always enable versioning on your state bucket.
- **Drift detection** should run on a schedule (e.g., nightly CI job) that compares real infrastructure against state. Manual changes are the primary source of drift and a **common mistake** in organizations transitioning to IaC.
- **Terratest** enables integration testing of infrastructure modules by deploying real resources, validating them, and tearing them down. Despite the cost of real resources, this is the only way to catch provider-specific issues.
- **Policy validation** with tools like OPA/Conftest or Sentinel (Terraform Enterprise) should enforce guardrails such as "no public S3 buckets" or "all EC2 instances must be tagged" at the plan stage before any resources are created.
- **Best practice**: Use `-detailed-exitcode` in CI pipelines to distinguish between "no changes" (exit 0) and "changes needed" (exit 2), enabling automated approval gates.
"""
    ),

    # --- 3. Multi-Cloud Strategies ---
    (
        "cloud-architecture/multi-cloud-strategies",
        r"""Explain multi-cloud architecture strategies in depth including cloud abstraction layer design with provider interfaces, service mesh connectivity across AWS and GCP and Azure, data residency and sovereignty compliance patterns, active-active and active-passive failover architectures, cost arbitrage between cloud providers, and avoiding vendor lock-in while maintaining operational efficiency.""",
        r"""# Multi-Cloud Strategies: Abstraction Layers, Service Mesh, and Failover Patterns

## The Multi-Cloud Reality

Multi-cloud architecture — running workloads across two or more cloud providers — is increasingly common but widely misunderstood. **However**, there is a fundamental distinction between **multi-cloud by design** (intentionally distributing workloads across clouds) and **multi-cloud by accident** (different teams chose different clouds). The first is an architectural strategy; the second is organizational dysfunction.

The primary motivations for intentional multi-cloud are **avoiding vendor lock-in**, **regulatory compliance** (data residency requirements), **best-of-breed service selection** (e.g., GCP for ML, AWS for breadth), and **negotiation leverage** with cloud providers. **Because** each motivation leads to a different architecture, there is no one-size-fits-all multi-cloud pattern. A **common mistake** is adopting multi-cloud "for resilience" without understanding that cross-cloud failover is orders of magnitude more complex than cross-region failover within a single cloud.

The fundamental **trade-off** is this: the more portable your architecture, the less you can leverage cloud-native services. Using only Kubernetes, PostgreSQL, and S3-compatible storage gives you portability but sacrifices DynamoDB, BigQuery, Cosmos DB, and hundreds of managed services that dramatically reduce operational burden.

## Cloud Abstraction Layer Design

An abstraction layer insulates application code from cloud-specific APIs. This is the foundation of portable multi-cloud architecture. **Best practice** is to use the **provider pattern** — define interfaces for infrastructure operations, then implement them per cloud.

```python
# multi_cloud/providers/base.py
# Abstract provider interface for cloud-agnostic operations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, BinaryIO

class CloudProvider(Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"

@dataclass
class StorageObject:
    # Cloud-agnostic representation of a storage object
    key: str
    size_bytes: int
    content_type: str
    etag: str
    last_modified: str
    metadata: dict[str, str]

@dataclass
class ComputeInstance:
    # Cloud-agnostic representation of a compute instance
    instance_id: str
    provider: CloudProvider
    region: str
    zone: str
    instance_type: str
    state: str
    private_ip: str
    public_ip: Optional[str]
    tags: dict[str, str]

class ObjectStorageProvider(ABC):
    # Abstract interface for object storage operations

    @abstractmethod
    def upload_object(
        self, bucket: str, key: str, data: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict[str, str]] = None,
    ) -> StorageObject:
        ...

    @abstractmethod
    def download_object(self, bucket: str, key: str) -> bytes:
        ...

    @abstractmethod
    def list_objects(
        self, bucket: str, prefix: str = "",
        max_keys: int = 1000,
    ) -> list[StorageObject]:
        ...

    @abstractmethod
    def delete_object(self, bucket: str, key: str) -> bool:
        ...

    @abstractmethod
    def generate_presigned_url(
        self, bucket: str, key: str, expiration_seconds: int = 3600,
    ) -> str:
        ...


class ComputeProvider(ABC):
    # Abstract interface for compute operations

    @abstractmethod
    def launch_instance(
        self, instance_type: str, image_id: str,
        region: str, tags: dict[str, str],
    ) -> ComputeInstance:
        ...

    @abstractmethod
    def terminate_instance(self, instance_id: str) -> bool:
        ...

    @abstractmethod
    def list_instances(
        self, filters: Optional[dict[str, str]] = None,
    ) -> list[ComputeInstance]:
        ...
```

```python
# multi_cloud/providers/aws_provider.py
# AWS implementation of the cloud abstraction layer

import boto3
from typing import Optional, BinaryIO
from .base import (
    ObjectStorageProvider, ComputeProvider,
    StorageObject, ComputeInstance, CloudProvider,
)

class AWSObjectStorage(ObjectStorageProvider):
    def __init__(self, region: str = "us-east-1"):
        self.s3 = boto3.client("s3", region_name=region)
        self.region = region

    def upload_object(
        self, bucket: str, key: str, data: BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict[str, str]] = None,
    ) -> StorageObject:
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata

        self.s3.upload_fileobj(data, bucket, key, ExtraArgs=extra_args)

        response = self.s3.head_object(Bucket=bucket, Key=key)
        return StorageObject(
            key=key,
            size_bytes=response["ContentLength"],
            content_type=response["ContentType"],
            etag=response["ETag"].strip('"'),
            last_modified=response["LastModified"].isoformat(),
            metadata=response.get("Metadata", {}),
        )

    def download_object(self, bucket: str, key: str) -> bytes:
        response = self.s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def list_objects(
        self, bucket: str, prefix: str = "",
        max_keys: int = 1000,
    ) -> list[StorageObject]:
        response = self.s3.list_objects_v2(
            Bucket=bucket, Prefix=prefix, MaxKeys=max_keys,
        )
        return [
            StorageObject(
                key=obj["Key"],
                size_bytes=obj["Size"],
                content_type="",  # Not returned by list
                etag=obj["ETag"].strip('"'),
                last_modified=obj["LastModified"].isoformat(),
                metadata={},
            )
            for obj in response.get("Contents", [])
        ]

    def delete_object(self, bucket: str, key: str) -> bool:
        self.s3.delete_object(Bucket=bucket, Key=key)
        return True

    def generate_presigned_url(
        self, bucket: str, key: str, expiration_seconds: int = 3600,
    ) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration_seconds,
        )
```

## Service Mesh Across Clouds

Connecting services across cloud boundaries requires a **service mesh** that handles service discovery, load balancing, mutual TLS, and observability across networks. **Because** cloud provider networks are isolated by default, you need either VPN tunnels, dedicated interconnects, or an overlay network.

```yaml
# mesh-config/istio-multicluster.yaml
# Istio multi-cluster mesh configuration for cross-cloud connectivity

apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: cross-cloud-mesh
spec:
  profile: default
  meshConfig:
    defaultConfig:
      proxyMetadata:
        ISTIO_META_DNS_CAPTURE: "true"
        ISTIO_META_DNS_AUTO_ALLOCATE: "true"
    enableAutoMtls: true
    accessLogFile: /dev/stdout
    outboundTrafficPolicy:
      mode: REGISTRY_ONLY  # Only allow registered services
  values:
    global:
      meshID: cross-cloud-mesh
      multiCluster:
        clusterName: aws-primary
      network: aws-network
    pilot:
      env:
        PILOT_ENABLE_CROSS_CLUSTER_WORKLOAD_ENTRY: "true"
```

## Active-Active Failover Architecture

True active-active multi-cloud means both clouds serve production traffic simultaneously, with the ability to absorb the other's traffic during failures. This is the most resilient but also the most complex and expensive pattern.

**Best practice** for active-active multi-cloud involves global DNS-based traffic management (Route53, Cloud DNS, or a third-party like Cloudflare), synchronized data stores (which is the hardest problem), and health-check-driven failover. The **pitfall** is data consistency — if you have mutable state, you must choose between strong consistency (high latency due to cross-cloud replication) and eventual consistency (risk of conflicts and data loss).

**Therefore**, most organizations that claim active-active actually implement **active-passive** with automated failover: one cloud handles all production traffic while the other runs in standby with continuous data replication. The RTO (Recovery Time Objective) for active-passive is typically 5-15 minutes versus near-zero for true active-active, but the complexity and cost reduction is substantial.

## Data Residency and Sovereignty

Data residency requirements — mandating that data stays within specific geographic boundaries — are a strong driver for multi-cloud. **Because** not all cloud providers have data centers in every country, you may need AWS in Frankfurt for EU data and Azure in Zurich for Swiss banking data.

```python
# multi_cloud/data_residency.py
# Data residency policy engine for multi-cloud compliance

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

@dataclass
class ResidencyPolicy:
    # Data residency policy linking data classification to allowed regions
    name: str
    classification: DataClassification
    allowed_regions: list[str]
    allowed_providers: list[str]
    encryption_required: bool = True
    cross_border_transfer_allowed: bool = False
    retention_days: Optional[int] = None

@dataclass
class ResidencyEngine:
    policies: list[ResidencyPolicy] = field(default_factory=list)

    def validate_placement(
        self, classification: DataClassification,
        provider: str, region: str,
    ) -> dict[str, bool | str]:
        matching = [
            p for p in self.policies
            if p.classification == classification
        ]
        if not matching:
            return {"allowed": False, "reason": "No policy found for classification"}

        for policy in matching:
            if provider not in policy.allowed_providers:
                return {
                    "allowed": False,
                    "reason": f"Provider {provider} not in allowed list: {policy.allowed_providers}",
                }
            if region not in policy.allowed_regions:
                return {
                    "allowed": False,
                    "reason": f"Region {region} violates residency policy {policy.name}",
                }
        return {"allowed": True, "reason": "Compliant"}
```

## Summary / Key Takeaways

- **Multi-cloud is a spectrum**, not a binary choice. Range from "use the best service from each cloud" to "fully portable workloads across all clouds." Choose your position on this spectrum deliberately based on actual business requirements, not theoretical resilience benefits.
- **Abstraction layers** with the provider pattern decouple application logic from cloud APIs. **However**, the **trade-off** is that you can only abstract the lowest common denominator of features across clouds, losing access to cloud-native differentiators.
- **Service mesh** (Istio, Linkerd, Consul Connect) provides the connectivity fabric for cross-cloud communication with mutual TLS, observability, and traffic management. **Best practice** is to use a mesh with multi-cluster support built in rather than trying to bridge separate meshes.
- **Active-active is rarely worth the complexity**. Most organizations should implement **active-passive with automated failover** unless they have genuine requirements for sub-second RTO across cloud boundaries.
- **Data residency** is often the strongest driver for multi-cloud. Build a policy engine that validates data placement against regulatory requirements before any write operation.
- **Cost arbitrage** — running workloads on whichever cloud is cheapest — sounds appealing but is a **pitfall** in practice. The engineering cost of maintaining portable infrastructure typically exceeds the savings from price differences between providers.
"""
    ),

    # --- 4. Serverless Architecture Patterns ---
    (
        "cloud-architecture/serverless-architecture-patterns",
        r"""Describe advanced serverless architecture patterns including event-driven design with EventBridge and SNS fan-out, fan-out and fan-in parallel processing with Step Functions, implementing the saga pattern for distributed transactions in serverless, cold start mitigation strategies across runtimes, and building comprehensive observability for serverless applications with distributed tracing and structured logging.""",
        r"""# Serverless Architecture Patterns: Event-Driven Design, Sagas, and Observability

## Beyond Simple Lambda Functions

Serverless architecture is far more than deploying individual functions. Production serverless systems require carefully designed patterns for event routing, parallel processing, distributed transactions, and observability. **However**, many teams adopt serverless function-by-function without a coherent architectural vision, resulting in what is derisively called a **"Lambda spaghetti"** — hundreds of loosely connected functions with no clear data flow, error handling, or observability.

The fundamental insight is that serverless is an **event-driven architecture** by nature. Every Lambda invocation is triggered by an event — an HTTP request, an SQS message, a DynamoDB stream record, an S3 notification. **Therefore**, mastering serverless means mastering event-driven design patterns. The **trade-off** is that event-driven systems are inherently asynchronous and eventually consistent, which requires a different mental model than request-response synchronous architectures.

## Event-Driven Design with EventBridge

Amazon EventBridge is the backbone of modern serverless event routing. Unlike SNS (which is a simple pub/sub), EventBridge provides **content-based routing** — events are matched against rules using JSON patterns, and only matching events are delivered to targets. This enables loose coupling between producers and consumers.

```python
# serverless/event_router.py
# EventBridge event publishing and routing configuration

import json
import boto3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

@dataclass
class DomainEvent:
    # Base class for all domain events
    event_type: str
    source: str
    detail_type: str
    detail: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    version: str = "1.0"
    correlation_id: Optional[str] = None

    def to_eventbridge_entry(self, bus_name: str = "default") -> dict:
        return {
            "Source": self.source,
            "DetailType": self.detail_type,
            "Detail": json.dumps({
                **self.detail,
                "event_id": self.event_id,
                "timestamp": self.timestamp,
                "version": self.version,
                "correlation_id": self.correlation_id,
            }),
            "EventBusName": bus_name,
        }


class EventPublisher:
    # Publishes domain events to EventBridge with batching support

    def __init__(self, bus_name: str = "custom-events"):
        self.client = boto3.client("events")
        self.bus_name = bus_name
        self._batch: list[dict] = []
        self._max_batch_size = 10  # EventBridge limit

    def publish(self, event: DomainEvent) -> dict:
        entry = event.to_eventbridge_entry(self.bus_name)
        response = self.client.put_events(Entries=[entry])

        if response["FailedEntryCount"] > 0:
            failed = response["Entries"][0]
            raise RuntimeError(
                f"Failed to publish event: {failed.get('ErrorMessage')}"
            )
        return {"event_id": event.event_id, "status": "published"}

    def add_to_batch(self, event: DomainEvent) -> None:
        self._batch.append(event.to_eventbridge_entry(self.bus_name))
        if len(self._batch) >= self._max_batch_size:
            self.flush_batch()

    def flush_batch(self) -> dict:
        if not self._batch:
            return {"published": 0, "failed": 0}

        response = self.client.put_events(Entries=self._batch)
        result = {
            "published": len(self._batch) - response["FailedEntryCount"],
            "failed": response["FailedEntryCount"],
        }
        self._batch.clear()
        return result


# Event definitions for an order processing system
class OrderEvents:
    SOURCE = "com.myapp.orders"

    @staticmethod
    def order_placed(order_id: str, customer_id: str, total: float,
                     items: list[dict], correlation_id: str) -> DomainEvent:
        return DomainEvent(
            event_type="OrderPlaced",
            source=OrderEvents.SOURCE,
            detail_type="Order Placed",
            detail={
                "order_id": order_id,
                "customer_id": customer_id,
                "total_amount": total,
                "items": items,
                "currency": "USD",
            },
            correlation_id=correlation_id,
        )

    @staticmethod
    def order_fulfilled(order_id: str, tracking_number: str,
                        correlation_id: str) -> DomainEvent:
        return DomainEvent(
            event_type="OrderFulfilled",
            source=OrderEvents.SOURCE,
            detail_type="Order Fulfilled",
            detail={
                "order_id": order_id,
                "tracking_number": tracking_number,
                "fulfilled_at": datetime.utcnow().isoformat(),
            },
            correlation_id=correlation_id,
        )
```

## Fan-Out/Fan-In with Step Functions

The **fan-out/fan-in** pattern processes items in parallel and aggregates results. AWS Step Functions provides native support through **Map state**, which dynamically spawns parallel branches for each element in an input array. This is dramatically more reliable than implementing parallelism with SQS and Lambda **because** Step Functions handles retries, error catching, and result aggregation automatically.

```python
# serverless/step_functions_workflow.py
# Step Functions state machine definition for fan-out/fan-in

import json
from typing import Any

def build_fan_out_state_machine(
    processor_lambda_arn: str,
    aggregator_lambda_arn: str,
    error_handler_lambda_arn: str,
    max_concurrency: int = 40,
    retry_max_attempts: int = 3,
) -> dict[str, Any]:
    # Build a Step Functions ASL definition for parallel processing
    # with error handling and result aggregation

    state_machine: dict[str, Any] = {
        "Comment": "Fan-out/fan-in processing pipeline",
        "StartAt": "ValidateInput",
        "States": {
            "ValidateInput": {
                "Type": "Pass",
                "Next": "FanOutProcess",
            },
            "FanOutProcess": {
                "Type": "Map",
                "ItemsPath": "$.items",
                "MaxConcurrency": max_concurrency,
                "ResultPath": "$.results",
                "Iterator": {
                    "StartAt": "ProcessItem",
                    "States": {
                        "ProcessItem": {
                            "Type": "Task",
                            "Resource": processor_lambda_arn,
                            "TimeoutSeconds": 300,
                            "Retry": [{
                                "ErrorEquals": [
                                    "States.TaskFailed",
                                    "Lambda.ServiceException",
                                ],
                                "IntervalSeconds": 2,
                                "MaxAttempts": retry_max_attempts,
                                "BackoffRate": 2.0,
                            }],
                            "Catch": [{
                                "ErrorEquals": ["States.ALL"],
                                "ResultPath": "$.error",
                                "Next": "HandleItemError",
                            }],
                            "End": True,
                        },
                        "HandleItemError": {
                            "Type": "Task",
                            "Resource": error_handler_lambda_arn,
                            "End": True,
                        },
                    },
                },
                "Next": "AggregateResults",
            },
            "AggregateResults": {
                "Type": "Task",
                "Resource": aggregator_lambda_arn,
                "End": True,
            },
        },
    }
    return state_machine
```

## Saga Pattern for Distributed Transactions

In serverless architectures, distributed transactions across multiple services cannot use traditional two-phase commit. The **saga pattern** breaks a transaction into a sequence of local transactions, each with a compensating action that undoes it if a later step fails. **Because** each step is independent, the saga can execute asynchronously through events.

```python
# serverless/saga_orchestrator.py
# Saga pattern orchestrator for serverless distributed transactions

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional
from datetime import datetime

class SagaStepStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"

@dataclass
class SagaStep:
    # A single step in a saga with its compensating action
    name: str
    action: Callable[..., dict[str, Any]]
    compensation: Callable[..., dict[str, Any]]
    status: SagaStepStatus = SagaStepStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    max_retries: int = 3
    timeout_seconds: int = 30

@dataclass
class SagaExecution:
    # Tracks the state of a saga execution
    saga_id: str
    steps: list[SagaStep]
    context: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = "pending"

    def execute(self) -> dict[str, Any]:
        # Execute the saga steps in order
        # If any step fails, compensate all completed steps in reverse order
        self.started_at = datetime.utcnow().isoformat()
        self.status = "executing"
        completed_steps: list[SagaStep] = []

        for step in self.steps:
            step.status = SagaStepStatus.EXECUTING
            retries = 0

            while retries <= step.max_retries:
                try:
                    step.result = step.action(self.context)
                    step.status = SagaStepStatus.COMPLETED
                    self.context.update(step.result or {})
                    completed_steps.append(step)
                    break
                except Exception as e:
                    retries += 1
                    if retries > step.max_retries:
                        step.status = SagaStepStatus.FAILED
                        step.error = str(e)
                        # Compensate all completed steps in reverse
                        self._compensate(completed_steps)
                        self.status = "compensated"
                        self.completed_at = datetime.utcnow().isoformat()
                        return {
                            "saga_id": self.saga_id,
                            "status": "compensated",
                            "failed_step": step.name,
                            "error": str(e),
                        }

        self.status = "completed"
        self.completed_at = datetime.utcnow().isoformat()
        return {
            "saga_id": self.saga_id,
            "status": "completed",
            "context": self.context,
        }

    def _compensate(self, completed_steps: list[SagaStep]) -> None:
        # Run compensating actions in reverse order
        for step in reversed(completed_steps):
            step.status = SagaStepStatus.COMPENSATING
            try:
                step.compensation(self.context)
                step.status = SagaStepStatus.COMPENSATED
            except Exception as e:
                # Compensation failure is critical - log and alert
                step.status = SagaStepStatus.FAILED
                step.error = f"Compensation failed: {e}"
                # In production, this would trigger a dead letter queue
                # and manual intervention alert
```

A critical **pitfall** with sagas is compensation failure. If a compensating action fails (e.g., you cannot refund a payment), you have an inconsistent system. **Best practice** is to make compensating actions idempotent and to implement a dead letter queue with alerting for compensation failures that require manual intervention.

## Cold Start Mitigation Strategies

Cold starts remain the primary performance concern in serverless. The mitigation strategy depends on your runtime, deployment size, and latency requirements.

**Best practice**: Use lightweight runtimes (Node.js, Python) for latency-sensitive APIs. Java and .NET have significantly longer cold starts (3-10 seconds vs 200-500ms). If you must use Java, GraalVM native compilation with custom runtimes reduces cold starts to under 500ms. **Therefore**, choose your runtime based on cold start requirements, not just developer familiarity.

Provisioned concurrency eliminates cold starts entirely but costs money for idle capacity. A **common mistake** is applying provisioned concurrency uniformly — instead, analyze your traffic patterns and apply it only to the hot path functions that serve user-facing requests.

## Serverless Observability

Observability in serverless requires structured logging, distributed tracing, and custom metrics. **Because** you do not control the infrastructure, traditional monitoring approaches (host metrics, log files, APM agents) do not work.

```python
# serverless/observability.py
# Structured logging and tracing for Lambda functions

import json
import os
import time
from functools import wraps
from typing import Callable, Any
from uuid import uuid4

class StructuredLogger:
    # JSON-structured logger for Lambda with correlation tracking
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.correlation_id: str = ""
        self.function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "local")
        self.cold_start = True

    def bind_context(self, event: dict) -> None:
        self.correlation_id = (
            event.get("headers", {}).get("x-correlation-id", "")
            or event.get("detail", {}).get("correlation_id", "")
            or str(uuid4())
        )

    def _log(self, level: str, message: str, **extra: Any) -> None:
        entry = {
            "timestamp": time.time(),
            "level": level,
            "message": message,
            "service": self.service_name,
            "function": self.function_name,
            "correlation_id": self.correlation_id,
            "cold_start": self.cold_start,
            **extra,
        }
        print(json.dumps(entry, default=str))

    def info(self, message: str, **extra: Any) -> None:
        self._log("INFO", message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        self._log("ERROR", message, **extra)

    def metric(self, name: str, value: float, unit: str = "Count") -> None:
        # Emit CloudWatch Embedded Metric Format
        self._log("METRIC", name, metric_name=name,
                  metric_value=value, metric_unit=unit)


def traced_handler(logger: StructuredLogger) -> Callable:
    # Decorator that adds tracing and structured logging to Lambda handlers
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: dict, context: Any) -> dict:
            logger.bind_context(event)
            start = time.time()
            logger.info("Handler invoked", event_source=_detect_source(event))

            try:
                result = func(event, context)
                duration = (time.time() - start) * 1000
                logger.info("Handler completed",
                            duration_ms=round(duration, 2),
                            status="success")
                logger.metric("HandlerDuration", duration, "Milliseconds")
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error("Handler failed",
                             duration_ms=round(duration, 2),
                             error_type=type(e).__name__,
                             error_message=str(e))
                logger.metric("HandlerErrors", 1)
                raise
            finally:
                logger.cold_start = False
        return wrapper
    return decorator


def _detect_source(event: dict) -> str:
    if "httpMethod" in event:
        return "api_gateway"
    if "Records" in event:
        first = event["Records"][0]
        return first.get("eventSource", "unknown")
    if "detail-type" in event:
        return "eventbridge"
    return "unknown"
```

## Summary / Key Takeaways

- **Event-driven design** with EventBridge provides content-based routing and loose coupling. Use SNS for simple fan-out and EventBridge when you need pattern matching, schema validation, or archive/replay capabilities.
- **Fan-out/fan-in** with Step Functions Map state is the reliable way to parallelize serverless workloads. It handles retries, timeouts, and result aggregation automatically, which is a massive advantage over manual SQS-based parallelism.
- **The saga pattern** replaces distributed transactions in serverless. Each step has a compensating action. The critical **pitfall** is compensation failure — always make compensations idempotent and implement dead letter queues for manual intervention.
- **Cold start mitigation** is runtime-dependent. Python/Node.js cold starts are 200-500ms; Java/NET are 3-10 seconds. Use provisioned concurrency surgically on hot-path functions, not globally.
- **Structured JSON logging** with correlation IDs is mandatory for serverless observability. **Because** you cannot SSH into Lambda, your logs and traces are the only window into runtime behavior.
- **Best practice**: Treat every Lambda function as an event handler, even HTTP-triggered ones. This mindset naturally leads to better error handling, idempotency, and eventual consistency patterns.
"""
    ),

    # --- 5. Cloud-Native Security ---
    (
        "cloud-architecture/cloud-native-security",
        r"""Explain cloud-native security architecture comprehensively including IAM least privilege policy design with permission boundaries, secrets management using HashiCorp Vault with dynamic credentials and auto-rotation, Kubernetes network policies for microsegmentation, encryption at rest and in transit with KMS key hierarchy, and compliance automation with policy-as-code frameworks like Open Policy Agent and AWS Config rules.""",
        r"""# Cloud-Native Security: IAM, Secrets Management, Encryption, and Compliance Automation

## Security as Architecture, Not Afterthought

Cloud-native security is fundamentally different from traditional perimeter-based security. In the cloud, the **network perimeter is dissolved** — workloads run across multiple services, regions, and sometimes providers. Identity becomes the new perimeter. **Therefore**, cloud security must be built into every layer of the architecture: identity and access management, secrets management, network segmentation, encryption, and continuous compliance validation.

A **common mistake** is treating cloud security as a configuration checklist — "enable encryption, restrict security groups, use MFA." While these are necessary, they are insufficient. Production cloud security requires **defense in depth**: multiple overlapping controls where the failure of any single control does not compromise the system. **Because** cloud environments are dynamic (auto-scaling, ephemeral containers, serverless functions), static security controls are inadequate. Security must be automated, policy-driven, and continuously validated.

## IAM Least Privilege with Permission Boundaries

The principle of least privilege states that every identity should have only the minimum permissions needed to perform its function. In AWS, this is implemented through IAM policies, but the challenge is determining what "minimum" means. **Best practice** is to start with no permissions and iteratively add only what is needed, using tools like IAM Access Analyzer and CloudTrail to identify actually-used permissions.

```python
# security/iam_policy_builder.py
# IAM least-privilege policy builder with permission boundaries

import json
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

class Effect(Enum):
    ALLOW = "Allow"
    DENY = "Deny"

@dataclass
class IAMStatement:
    # A single IAM policy statement
    effect: Effect
    actions: list[str]
    resources: list[str]
    conditions: Optional[dict[str, Any]] = None
    sid: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        stmt: dict[str, Any] = {
            "Effect": self.effect.value,
            "Action": self.actions,
            "Resource": self.resources,
        }
        if self.sid:
            stmt["Sid"] = self.sid
        if self.conditions:
            stmt["Condition"] = self.conditions
        return stmt


@dataclass
class PolicyBuilder:
    # Builds IAM policies following least-privilege principles
    statements: list[IAMStatement] = field(default_factory=list)

    def allow(self, actions: list[str], resources: list[str],
              conditions: Optional[dict] = None,
              sid: Optional[str] = None) -> "PolicyBuilder":
        self.statements.append(IAMStatement(
            effect=Effect.ALLOW, actions=actions,
            resources=resources, conditions=conditions, sid=sid,
        ))
        return self

    def deny(self, actions: list[str], resources: list[str],
             conditions: Optional[dict] = None,
             sid: Optional[str] = None) -> "PolicyBuilder":
        self.statements.append(IAMStatement(
            effect=Effect.DENY, actions=actions,
            resources=resources, conditions=conditions, sid=sid,
        ))
        return self

    def build(self) -> dict[str, Any]:
        return {
            "Version": "2012-10-17",
            "Statement": [s.to_dict() for s in self.statements],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.build(), indent=indent)


def build_lambda_execution_policy(
    function_name: str,
    dynamodb_table_arn: str,
    s3_bucket_arn: str,
    kms_key_arn: str,
    log_group_arn: str,
) -> dict[str, Any]:
    # Build a minimal IAM policy for a Lambda function
    # Only grants access to specific resources it needs
    builder = PolicyBuilder()

    # CloudWatch Logs - write only to its own log group
    builder.allow(
        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
        resources=[f"{log_group_arn}:*"],
        sid="AllowLogging",
    )

    # DynamoDB - read/write to specific table, no admin actions
    builder.allow(
        actions=[
            "dynamodb:GetItem", "dynamodb:PutItem",
            "dynamodb:UpdateItem", "dynamodb:DeleteItem",
            "dynamodb:Query",
        ],
        resources=[
            dynamodb_table_arn,
            f"{dynamodb_table_arn}/index/*",
        ],
        sid="AllowDynamoDB",
    )

    # S3 - read/write to specific bucket with encryption
    builder.allow(
        actions=["s3:GetObject", "s3:PutObject"],
        resources=[f"{s3_bucket_arn}/*"],
        conditions={
            "StringEquals": {
                "s3:x-amz-server-side-encryption": "aws:kms",
                "s3:x-amz-server-side-encryption-aws-kms-key-id": kms_key_arn,
            }
        },
        sid="AllowS3WithEncryption",
    )

    # KMS - only encrypt/decrypt, not manage keys
    builder.allow(
        actions=["kms:Decrypt", "kms:GenerateDataKey"],
        resources=[kms_key_arn],
        sid="AllowKMSUsage",
    )

    # Explicit deny on sensitive operations
    builder.deny(
        actions=[
            "iam:*", "organizations:*", "account:*",
            "kms:ScheduleKeyDeletion", "kms:DisableKey",
        ],
        resources=["*"],
        sid="DenyAdminActions",
    )

    return builder.build()


def build_permission_boundary(
    organization_id: str,
    allowed_regions: list[str],
    allowed_services: list[str],
) -> dict[str, Any]:
    # Permission boundary limits the maximum permissions
    # any role in the account can have, regardless of attached policies
    boundary = PolicyBuilder()

    # Allow only specified services
    boundary.allow(
        actions=[f"{svc}:*" for svc in allowed_services],
        resources=["*"],
        conditions={
            "StringEquals": {
                "aws:RequestedRegion": allowed_regions
            }
        },
        sid="AllowApprovedServicesInRegion",
    )

    # Always deny leaving the organization
    boundary.deny(
        actions=["organizations:LeaveOrganization"],
        resources=["*"],
        sid="DenyLeaveOrg",
    )

    # Deny disabling CloudTrail
    boundary.deny(
        actions=["cloudtrail:StopLogging", "cloudtrail:DeleteTrail"],
        resources=["*"],
        sid="ProtectAuditTrail",
    )

    return boundary.build()
```

**Permission boundaries** are the guard rails that prevent privilege escalation. Even if a developer attaches `AdministratorAccess` to a role, the permission boundary limits the effective permissions to the intersection of the boundary and the attached policies. **Therefore**, every IAM role in your organization should have a permission boundary that prevents actions like disabling CloudTrail, leaving the organization, or managing IAM in production accounts.

## Secrets Management with HashiCorp Vault

Static secrets (API keys, database passwords stored in environment variables or config files) are one of the most common security vulnerabilities. HashiCorp Vault solves this with **dynamic secrets** — credentials generated on-demand with automatic expiration. **Because** dynamic credentials are unique per consumer and short-lived, a leaked credential has limited blast radius.

```python
# security/vault_client.py
# HashiCorp Vault client for dynamic secrets and auto-rotation

import hvac
import time
from dataclasses import dataclass
from typing import Optional, Any
from functools import lru_cache

@dataclass
class VaultConfig:
    # Vault connection configuration
    url: str
    auth_method: str  # "kubernetes", "aws_iam", "approle"
    role: str
    namespace: Optional[str] = None
    tls_verify: bool = True

@dataclass
class DynamicCredential:
    # A Vault-issued dynamic credential with TTL
    username: str
    password: str
    lease_id: str
    lease_duration: int
    renewable: bool
    issued_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.issued_at + self.lease_duration)

    @property
    def time_remaining(self) -> float:
        return max(0, (self.issued_at + self.lease_duration) - time.time())

    @property
    def should_renew(self) -> bool:
        # Renew when 2/3 of the lease has elapsed
        return self.time_remaining < (self.lease_duration / 3)


class VaultSecretsManager:
    # Manages dynamic credentials from HashiCorp Vault

    def __init__(self, config: VaultConfig):
        self.config = config
        self.client = hvac.Client(
            url=config.url,
            verify=config.tls_verify,
            namespace=config.namespace,
        )
        self._credentials_cache: dict[str, DynamicCredential] = {}
        self._authenticate()

    def _authenticate(self) -> None:
        if self.config.auth_method == "kubernetes":
            # Read the service account token
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token") as f:
                jwt = f.read()
            self.client.auth.kubernetes.login(
                role=self.config.role, jwt=jwt,
            )
        elif self.config.auth_method == "aws_iam":
            self.client.auth.aws.iam_login(
                role=self.config.role,
            )
        elif self.config.auth_method == "approle":
            # AppRole auth - role_id and secret_id from environment
            import os
            self.client.auth.approle.login(
                role_id=os.environ["VAULT_ROLE_ID"],
                secret_id=os.environ["VAULT_SECRET_ID"],
            )

    def get_database_credentials(
        self, db_role: str,
    ) -> DynamicCredential:
        # Get or renew dynamic database credentials
        cached = self._credentials_cache.get(db_role)
        if cached and not cached.should_renew:
            return cached

        if cached and cached.renewable and not cached.is_expired:
            renewed = self.client.sys.renew_lease(
                lease_id=cached.lease_id,
            )
            cached.lease_duration = renewed["lease_duration"]
            cached.issued_at = time.time()
            return cached

        # Generate new credentials
        response = self.client.secrets.database.generate_credentials(
            name=db_role,
        )

        credential = DynamicCredential(
            username=response["data"]["username"],
            password=response["data"]["password"],
            lease_id=response["lease_id"],
            lease_duration=response["lease_duration"],
            renewable=response["renewable"],
            issued_at=time.time(),
        )
        self._credentials_cache[db_role] = credential
        return credential

    def get_static_secret(self, path: str, key: str) -> str:
        # Read a static secret from KV v2 engine
        # Use this for API keys and other non-rotatable secrets
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path,
        )
        return response["data"]["data"][key]

    def revoke_all_leases(self) -> None:
        # Revoke all active leases on shutdown
        for role, cred in self._credentials_cache.items():
            try:
                self.client.sys.revoke_lease(lease_id=cred.lease_id)
            except Exception:
                pass  # Best effort revocation
        self._credentials_cache.clear()
```

The **trade-off** with dynamic secrets is operational complexity versus security. Static secrets are simple but dangerous; dynamic secrets are secure but require Vault infrastructure, auth method configuration, and lease management. **However**, the security benefit is enormous — a leaked dynamic credential expires in minutes or hours, versus a leaked static credential that may be valid indefinitely.

## Kubernetes Network Policies for Microsegmentation

Kubernetes network policies implement **microsegmentation** — controlling traffic between pods at Layer 3/4. By default, Kubernetes allows all pod-to-pod communication, which means a compromised pod can reach every other pod in the cluster. Network policies are the **best practice** for implementing zero-trust networking within Kubernetes.

```yaml
# k8s/network-policies.yaml
# Zero-trust network policies for microservices

# Default deny all ingress and egress for the namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress

---
# Allow the API gateway to receive external traffic
# and communicate with backend services
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-gateway
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-gateway
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              tier: backend
      ports:
        - protocol: TCP
          port: 8080
    - to:  # Allow DNS resolution
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53

---
# Allow order-service to talk only to database and payment-service
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-order-service
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: order-service
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: payment-service
      ports:
        - protocol: TCP
          port: 8080
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
    - to:  # DNS
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
```

A critical **pitfall** with Kubernetes network policies is that they require a CNI plugin that supports them (Calico, Cilium, Weave). The default kubenet and AWS VPC CNI (without Calico) **do not enforce** network policies — the resources are accepted but silently ignored. **Therefore**, always verify that your CNI plugin enforces network policies before relying on them for security.

## Encryption and KMS Key Hierarchy

Encryption at rest and in transit is non-negotiable for production systems. **However**, encryption is only as strong as the key management behind it. AWS KMS provides a **key hierarchy** where a Customer Master Key (CMK) never leaves KMS — it encrypts data keys, which in turn encrypt your data. This is called **envelope encryption**.

**Best practice**: Use separate KMS keys per service and per environment. This enables granular access control — the order-service CMK policy only allows the order-service IAM role to use it for encryption and decryption. If the payment-service is compromised, it cannot decrypt order data **because** it lacks permission to use the order-service CMK.

## Compliance Automation with OPA

Open Policy Agent (OPA) enables **policy-as-code** — writing compliance rules in Rego that are automatically evaluated against infrastructure configuration, Kubernetes manifests, and Terraform plans.

```python
# security/compliance_checker.py
# Compliance automation with OPA and AWS Config

import json
import subprocess
from dataclasses import dataclass
from typing import Any
from pathlib import Path

@dataclass
class ComplianceResult:
    # Result of a compliance check
    rule_name: str
    resource_id: str
    compliant: bool
    severity: str  # "critical", "high", "medium", "low"
    message: str
    remediation: str

def evaluate_opa_policy(
    policy_path: str,
    input_data: dict[str, Any],
    query: str = "data.policy.violations",
) -> list[dict[str, Any]]:
    # Evaluate an OPA policy against input data
    input_json = json.dumps(input_data)

    result = subprocess.run(
        ["opa", "eval", "--data", policy_path,
         "--input", "/dev/stdin",
         "--format", "json", query],
        input=input_json, capture_output=True, text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"OPA evaluation failed: {result.stderr}")

    output = json.loads(result.stdout)
    violations = output.get("result", [{}])[0].get("expressions", [{}])
    if violations and violations[0].get("value"):
        return violations[0]["value"]
    return []


def check_s3_compliance(bucket_config: dict) -> list[ComplianceResult]:
    # Check S3 bucket configuration against security best practices
    results: list[ComplianceResult] = []
    bucket_name = bucket_config.get("bucket_name", "unknown")

    # Check encryption
    if not bucket_config.get("encryption_enabled", False):
        results.append(ComplianceResult(
            rule_name="s3-encryption-required",
            resource_id=bucket_name,
            compliant=False,
            severity="critical",
            message="S3 bucket does not have encryption enabled",
            remediation="Enable SSE-KMS encryption with a customer-managed key",
        ))

    # Check public access block
    pub_access = bucket_config.get("public_access_block", {})
    if not all([
        pub_access.get("block_public_acls", False),
        pub_access.get("block_public_policy", False),
        pub_access.get("ignore_public_acls", False),
        pub_access.get("restrict_public_buckets", False),
    ]):
        results.append(ComplianceResult(
            rule_name="s3-no-public-access",
            resource_id=bucket_name,
            compliant=False,
            severity="critical",
            message="S3 bucket public access block is not fully configured",
            remediation="Enable all four public access block settings",
        ))

    # Check versioning
    if not bucket_config.get("versioning_enabled", False):
        results.append(ComplianceResult(
            rule_name="s3-versioning-required",
            resource_id=bucket_name,
            compliant=False,
            severity="high",
            message="S3 bucket versioning is not enabled",
            remediation="Enable versioning for data protection and recovery",
        ))

    if not results:
        results.append(ComplianceResult(
            rule_name="s3-all-checks",
            resource_id=bucket_name,
            compliant=True,
            severity="low",
            message="All S3 compliance checks passed",
            remediation="",
        ))

    return results
```

## Summary / Key Takeaways

- **IAM least privilege** starts with zero permissions and adds only what is needed. Use **permission boundaries** as guard rails that prevent privilege escalation regardless of attached policies. **Because** IAM is the most critical security control in the cloud, every role should follow the principle of least privilege.
- **Dynamic secrets with Vault** eliminate the risk of long-lived credentials. The **trade-off** is operational complexity, but the security benefit (leaked credentials expire in minutes) far outweighs it.
- **Kubernetes network policies** implement microsegmentation but require a compatible CNI plugin. The critical **pitfall** is that default CNI plugins silently ignore network policies, creating a false sense of security.
- **Envelope encryption** with KMS separates key management from data encryption. Use separate CMKs per service and environment for granular access control.
- **Policy-as-code** with OPA enables automated compliance checking. Run policy evaluations in CI/CD pipelines to catch violations before deployment, not after.
- **Best practice**: Implement **defense in depth** — never rely on a single security control. Combine IAM, network policies, encryption, secrets management, and compliance automation so that the failure of any single layer does not result in a breach.
- **Common mistake**: Treating security as a one-time setup. Cloud environments change continuously (new services, new IAM roles, auto-scaling), so security validation must be continuous and automated.
"""
    ),
]
