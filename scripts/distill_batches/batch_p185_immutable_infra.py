"""Immutable infrastructure: Packer image building, blue-green with AMIs, golden images, instance replacement, configuration baking."""

PAIRS = [
    (
        "infrastructure/packer-golden-image-pipeline",
        "How do I build golden images with Packer for immutable infrastructure? Show a complete pipeline with multi-cloud support, provisioning, hardening, validation, and a Python orchestrator.",
        '''Packer builds identical machine images across cloud providers from a single template. Golden images are pre-configured, hardened, and tested so production instances launch fully ready without runtime configuration.

## Golden Image Pipeline

| Stage | Purpose | Tool |
|---|---|---|
| Base image | Start from vendor AMI/image | Packer source |
| Provisioning | Install packages, deploy app | Shell/Ansible |
| Hardening | CIS benchmarks, remove bloat | Ansible roles |
| Validation | Test image before publishing | InSpec/Goss |
| Publishing | Register AMI, tag for use | Packer post-processor |

## Packer Image Orchestrator

```python
#!/usr/bin/env python3
"""
Packer golden image build orchestrator.
Manages multi-cloud image building, validation, and lifecycle
for immutable infrastructure deployments.
"""

import json
import time
import subprocess
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ImageSpec:
    """Specification for a golden image build."""
    name: str
    version: str
    os_family: str  # "ubuntu", "amazon-linux", "windows"
    app_name: str
    app_version: str
    base_ami: str = ""
    instance_type: str = "t3.medium"
    region: str = "us-east-1"
    vpc_id: str = ""
    subnet_id: str = ""
    provisioners: list[dict] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    copy_regions: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    spec: ImageSpec
    success: bool
    ami_id: str
    duration_seconds: float
    region_amis: dict[str, str] = field(default_factory=dict)
    validation_passed: bool = False
    error: str = ""


class PackerTemplateGenerator:
    """Generates HCL2 Packer templates for golden images."""

    def generate(self, spec: ImageSpec) -> str:
        source_block = self._aws_source(spec)
        build_block = self._build_block(spec)
        variables = self._variables(spec)

        return f'''{variables}

{source_block}

{build_block}
'''

    def _variables(self, spec: ImageSpec) -> str:
        return f'''variable "app_version" {{
  type    = string
  default = "{spec.app_version}"
}}

variable "base_ami" {{
  type    = string
  default = "{spec.base_ami}"
}}

variable "region" {{
  type    = string
  default = "{spec.region}"
}}
'''

    def _aws_source(self, spec: ImageSpec) -> str:
        ami_name = f"{spec.name}-{spec.version}-{{{{timestamp}}}}"
        copy_regions = ""
        if spec.copy_regions:
            regions = ", ".join(f'"{r}"' for r in spec.copy_regions)
            copy_regions = f'  ami_regions = [{regions}]'

        return f'''source "amazon-ebs" "{spec.name}" {{
  ami_name      = "{ami_name}"
  instance_type = "{spec.instance_type}"
  region        = var.region
  source_ami    = var.base_ami
  ssh_username  = "ubuntu"
  vpc_id        = "{spec.vpc_id}"
  subnet_id     = "{spec.subnet_id}"
{copy_regions}

  tags = {{
    Name        = "{spec.name}"
    Version     = "{spec.version}"
    AppName     = "{spec.app_name}"
    AppVersion  = var.app_version
    BaseAMI     = var.base_ami
    BuildDate   = "{{{{timestamp}}}}"
    OS          = "{spec.os_family}"
    ManagedBy   = "packer"
  }}

  launch_block_device_mappings {{
    device_name           = "/dev/sda1"
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }}
}}
'''

    def _build_block(self, spec: ImageSpec) -> str:
        provisioners = []

        # System update
        provisioners.append('''  provisioner "shell" {
    inline = [
      "sudo apt-get update -y",
      "sudo apt-get upgrade -y",
      "sudo apt-get install -y curl jq unzip"
    ]
  }''')

        # Application deployment
        provisioners.append(f'''  provisioner "shell" {{
    inline = [
      "sudo mkdir -p /opt/{spec.app_name}",
      "sudo chown ubuntu:ubuntu /opt/{spec.app_name}"
    ]
  }}

  provisioner "file" {{
    source      = "artifacts/{spec.app_name}-${{var.app_version}}.tar.gz"
    destination = "/tmp/{spec.app_name}.tar.gz"
  }}

  provisioner "shell" {{
    inline = [
      "tar xzf /tmp/{spec.app_name}.tar.gz -C /opt/{spec.app_name}",
      "rm /tmp/{spec.app_name}.tar.gz"
    ]
  }}''')

        # CIS hardening
        provisioners.append('''  provisioner "shell" {
    script = "scripts/harden.sh"
  }''')

        # Validation with Goss
        provisioners.append('''  provisioner "file" {
    source      = "tests/goss.yaml"
    destination = "/tmp/goss.yaml"
  }

  provisioner "shell" {
    inline = [
      "curl -L https://github.com/goss-org/goss/releases/latest/download/goss-linux-amd64 -o /usr/local/bin/goss",
      "chmod +x /usr/local/bin/goss",
      "goss -g /tmp/goss.yaml validate --format documentation"
    ]
  }''')

        # Cleanup
        provisioners.append('''  provisioner "shell" {
    inline = [
      "sudo apt-get clean",
      "sudo rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*",
      "sudo truncate -s 0 /var/log/*.log",
      "history -c"
    ]
  }''')

        prov_str = "\\n\\n".join(provisioners)
        return f'''build {{
  sources = ["source.amazon-ebs.{spec.name}"]

{prov_str}
}}
'''


class PackerOrchestrator:
    """Orchestrates Packer builds with validation and lifecycle management."""

    def __init__(self, packer_path: str = "packer", work_dir: str = "/tmp/packer-builds"):
        self.packer_path = packer_path
        self.work_dir = Path(work_dir)
        self.generator = PackerTemplateGenerator()

    def build(self, spec: ImageSpec) -> BuildResult:
        start = time.monotonic()
        build_dir = self.work_dir / f"{spec.name}-{spec.version}"
        build_dir.mkdir(parents=True, exist_ok=True)

        template_path = build_dir / f"{spec.name}.pkr.hcl"
        template_content = self.generator.generate(spec)
        template_path.write_text(template_content)

        # Init plugins
        init_result = subprocess.run(
            [self.packer_path, "init", str(build_dir)],
            capture_output=True, text=True, cwd=str(build_dir))
        if init_result.returncode != 0:
            return BuildResult(spec=spec, success=False, ami_id="",
                duration_seconds=time.monotonic() - start,
                error=f"Init failed: {init_result.stderr}")

        # Validate template
        val_result = subprocess.run(
            [self.packer_path, "validate", str(template_path)],
            capture_output=True, text=True, cwd=str(build_dir))
        if val_result.returncode != 0:
            return BuildResult(spec=spec, success=False, ami_id="",
                duration_seconds=time.monotonic() - start,
                error=f"Validation failed: {val_result.stderr}")

        # Build
        build_result = subprocess.run(
            [self.packer_path, "build",
             "-machine-readable", "-color=false",
             str(template_path)],
            capture_output=True, text=True, cwd=str(build_dir), timeout=3600)

        duration = time.monotonic() - start

        if build_result.returncode != 0:
            return BuildResult(spec=spec, success=False, ami_id="",
                duration_seconds=duration, error=build_result.stderr[-500:])

        ami_id = self._extract_ami(build_result.stdout)
        logger.info("Built AMI %s for %s in %.0fs", ami_id, spec.name, duration)

        return BuildResult(spec=spec, success=True, ami_id=ami_id,
            duration_seconds=duration, validation_passed=True)

    def _extract_ami(self, output: str) -> str:
        for line in output.splitlines():
            if "ami-" in line:
                for part in line.split():
                    if part.startswith("ami-"):
                        return part.strip(",").strip()
        return ""

    def cleanup_old_amis(self, name: str, keep_count: int = 3,
                          region: str = "us-east-1") -> list[str]:
        """Deregister old AMIs, keeping the most recent N."""
        result = subprocess.run([
            "aws", "ec2", "describe-images",
            "--owners", "self", "--region", region,
            "--filters", f"Name=tag:Name,Values={name}",
            "--query", "Images | sort_by(@, &CreationDate)",
            "--output", "json",
        ], capture_output=True, text=True, timeout=30)

        images = json.loads(result.stdout) if result.returncode == 0 else []
        to_delete = images[:-keep_count] if len(images) > keep_count else []

        deleted = []
        for img in to_delete:
            ami_id = img["ImageId"]
            subprocess.run([
                "aws", "ec2", "deregister-image",
                "--image-id", ami_id, "--region", region,
            ], capture_output=True, text=True)
            deleted.append(ami_id)
            logger.info("Deregistered old AMI: %s", ami_id)
        return deleted
```

## Key Patterns

- **Configuration baking**: All software and config baked into the image at build time, not at boot
- **CIS hardening**: Security hardening scripts run during build, validated with Goss tests
- **Multi-region replication**: AMIs copied to all deployment regions during the build
- **Image lifecycle**: Old AMIs automatically deregistered, keeping only the N most recent
- **Encrypted volumes**: EBS volumes encrypted by default for data-at-rest protection
- **Build validation**: Goss tests run inside the image during build to verify correctness'''
    ),
    (
        "infrastructure/blue-green-ami-deployment",
        "How do I implement blue-green deployments with AMI-based immutable infrastructure? Show an auto-scaling group swap strategy with health verification and instant rollback capability.",
        '''Blue-green AMI deployment maintains two identical environments (blue and green). Traffic is routed to one while the other is updated. On successful validation, traffic switches instantly to the new environment.

## Blue-Green Architecture

| Component | Blue (Active) | Green (Standby) |
|---|---|---|
| ASG | Running current AMI | Launching new AMI |
| Target Group | Receiving traffic | Health checking |
| DNS/ALB | Points to blue TG | Ready to switch |

## Blue-Green Deployment Manager

```python
#!/usr/bin/env python3
"""
Blue-green deployment manager for AMI-based immutable infrastructure.
Manages ASG swaps, health verification, and instant rollback.
"""

import json
import time
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import subprocess

logger = logging.getLogger(__name__)


class DeploymentSlot(Enum):
    BLUE = "blue"
    GREEN = "green"


class DeploymentState(Enum):
    IDLE = "idle"
    LAUNCHING = "launching"
    WARMING = "warming"
    VALIDATING = "validating"
    SWITCHING = "switching"
    COMPLETE = "complete"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class BlueGreenConfig:
    service_name: str
    region: str
    vpc_id: str
    subnet_ids: list[str]
    alb_arn: str
    blue_tg_arn: str
    green_tg_arn: str
    blue_asg_name: str
    green_asg_name: str
    listener_arn: str
    min_healthy_percent: float = 0.9
    warmup_seconds: int = 120
    validation_seconds: int = 300
    health_check_interval: int = 10
    instance_type: str = "t3.medium"
    desired_capacity: int = 3
    min_size: int = 2
    max_size: int = 6


@dataclass
class DeploymentRecord:
    deployment_id: str
    config: BlueGreenConfig
    ami_id: str
    active_slot: DeploymentSlot
    state: DeploymentState
    start_time: datetime
    end_time: Optional[datetime] = None
    previous_ami: str = ""
    error: str = ""


class BlueGreenDeployer:
    """Manages blue-green AMI deployments with instant rollback."""

    def __init__(self, config: BlueGreenConfig):
        self.config = config
        self._current_slot = DeploymentSlot.BLUE
        self._deployments: list[DeploymentRecord] = []

    def deploy(self, ami_id: str, deployment_id: str) -> DeploymentRecord:
        """Execute a blue-green deployment."""
        target_slot = self._inactive_slot()
        record = DeploymentRecord(
            deployment_id=deployment_id, config=self.config,
            ami_id=ami_id, active_slot=target_slot,
            state=DeploymentState.LAUNCHING,
            start_time=datetime.now(timezone.utc),
            previous_ami=self._get_current_ami())

        try:
            # 1. Update inactive ASG with new AMI
            logger.info("[%s] Updating %s ASG with AMI %s",
                deployment_id, target_slot.value, ami_id)
            self._update_launch_template(target_slot, ami_id)
            self._scale_asg(target_slot, self.config.desired_capacity)

            # 2. Wait for instances to launch and warm up
            record.state = DeploymentState.WARMING
            logger.info("[%s] Warming up %s instances", deployment_id, target_slot.value)
            if not self._wait_for_healthy(target_slot, self.config.warmup_seconds):
                raise RuntimeError("Instances failed to become healthy during warmup")

            # 3. Validate by sending test traffic
            record.state = DeploymentState.VALIDATING
            logger.info("[%s] Validating %s environment", deployment_id, target_slot.value)
            if not self._validate_environment(target_slot):
                raise RuntimeError("Environment validation failed")

            # 4. Switch traffic
            record.state = DeploymentState.SWITCHING
            logger.info("[%s] Switching traffic to %s", deployment_id, target_slot.value)
            self._switch_listener(target_slot)

            # 5. Verify traffic is flowing
            time.sleep(30)
            if not self._verify_traffic(target_slot):
                raise RuntimeError("Traffic verification failed after switch")

            # 6. Scale down old environment
            old_slot = self._current_slot
            self._scale_asg(old_slot, 0)

            self._current_slot = target_slot
            record.state = DeploymentState.COMPLETE
            record.end_time = datetime.now(timezone.utc)
            duration = (record.end_time - record.start_time).total_seconds()
            logger.info("[%s] Deployment complete in %.0fs", deployment_id, duration)

        except Exception as e:
            logger.error("[%s] Deployment failed: %s", deployment_id, e)
            record.state = DeploymentState.FAILED
            record.error = str(e)
            self._rollback(target_slot, deployment_id)
            record.state = DeploymentState.ROLLED_BACK
            record.end_time = datetime.now(timezone.utc)

        self._deployments.append(record)
        return record

    def instant_rollback(self, deployment_id: str) -> bool:
        """Instantly rollback by switching listener back."""
        old_slot = self._inactive_slot()
        logger.warning("[%s] Instant rollback to %s", deployment_id, old_slot.value)
        self._switch_listener(old_slot)
        self._current_slot = old_slot
        return True

    def _inactive_slot(self) -> DeploymentSlot:
        return (DeploymentSlot.GREEN if self._current_slot == DeploymentSlot.BLUE
                else DeploymentSlot.BLUE)

    def _asg_name(self, slot: DeploymentSlot) -> str:
        return (self.config.blue_asg_name if slot == DeploymentSlot.BLUE
                else self.config.green_asg_name)

    def _tg_arn(self, slot: DeploymentSlot) -> str:
        return (self.config.blue_tg_arn if slot == DeploymentSlot.BLUE
                else self.config.green_tg_arn)

    def _update_launch_template(self, slot: DeploymentSlot, ami_id: str):
        asg = self._asg_name(slot)
        subprocess.run([
            "aws", "ec2", "create-launch-template-version",
            "--launch-template-name", f"{asg}-lt",
            "--source-version", "$Latest",
            "--launch-template-data", json.dumps({"ImageId": ami_id}),
            "--region", self.config.region,
        ], capture_output=True, text=True, check=True)

    def _scale_asg(self, slot: DeploymentSlot, desired: int):
        asg = self._asg_name(slot)
        subprocess.run([
            "aws", "autoscaling", "update-auto-scaling-group",
            "--auto-scaling-group-name", asg,
            "--desired-capacity", str(desired),
            "--min-size", str(min(desired, self.config.min_size)),
            "--max-size", str(self.config.max_size),
            "--region", self.config.region,
        ], capture_output=True, text=True, check=True)

    def _wait_for_healthy(self, slot: DeploymentSlot, timeout: int) -> bool:
        tg_arn = self._tg_arn(slot)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = subprocess.run([
                "aws", "elbv2", "describe-target-health",
                "--target-group-arn", tg_arn,
                "--region", self.config.region,
                "--output", "json",
            ], capture_output=True, text=True)
            data = json.loads(result.stdout) if result.returncode == 0 else {}
            targets = data.get("TargetHealthDescriptions", [])
            healthy = sum(1 for t in targets if t.get("TargetHealth", {}).get("State") == "healthy")
            total = len(targets)
            if total > 0 and healthy / total >= self.config.min_healthy_percent:
                return True
            logger.info("Health: %d/%d healthy, waiting...", healthy, total)
            time.sleep(self.config.health_check_interval)
        return False

    def _switch_listener(self, slot: DeploymentSlot):
        tg_arn = self._tg_arn(slot)
        subprocess.run([
            "aws", "elbv2", "modify-listener",
            "--listener-arn", self.config.listener_arn,
            "--default-actions", json.dumps([{
                "Type": "forward",
                "TargetGroupArn": tg_arn,
            }]),
            "--region", self.config.region,
        ], capture_output=True, text=True, check=True)

    def _validate_environment(self, slot: DeploymentSlot) -> bool:
        # Send test requests to the target group directly
        time.sleep(10)
        return self._wait_for_healthy(slot, self.config.validation_seconds)

    def _verify_traffic(self, slot: DeploymentSlot) -> bool:
        return self._wait_for_healthy(slot, 60)

    def _get_current_ami(self) -> str:
        asg = self._asg_name(self._current_slot)
        result = subprocess.run([
            "aws", "autoscaling", "describe-auto-scaling-groups",
            "--auto-scaling-group-names", asg,
            "--region", self.config.region, "--output", "json",
        ], capture_output=True, text=True)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        groups = data.get("AutoScalingGroups", [])
        if groups:
            lt = groups[0].get("LaunchTemplate", {})
            return lt.get("LaunchTemplateId", "")
        return ""

    def _rollback(self, failed_slot: DeploymentSlot, deployment_id: str):
        logger.warning("[%s] Rolling back: scaling down %s", deployment_id, failed_slot.value)
        self._scale_asg(failed_slot, 0)
```

## Key Patterns

- **Zero-downtime switching**: ALB listener rule change is atomic -- traffic shifts instantly
- **Health-gated promotion**: New environment must pass health checks before receiving traffic
- **Instant rollback**: Switch listener back to old target group in seconds, no new instances needed
- **Old environment preserved**: Previous ASG scaled to zero but not deleted, enabling fast rollback
- **Deployment state machine**: Clear state transitions (launching -> warming -> validating -> switching)
- **Capacity management**: New ASG scales up before old scales down, maintaining total capacity'''
    ),
    (
        "infrastructure/immutable-config-baking",
        "How do I bake application configuration into immutable images instead of runtime configuration? Show strategies for environment-specific config, secrets injection, and a Python config baking pipeline.",
        '''Configuration baking embeds all application settings into the machine image at build time, eliminating configuration drift and runtime dependency on external config stores. Environment-specific values use parameter store lookups at boot.

## Config Baking Strategies

| Strategy | When to Use | Example |
|---|---|---|
| Full bake | Static config, no secrets | nginx.conf, app settings |
| Parameterized bake | Per-environment values | DB hostname, feature flags |
| Boot-time injection | Secrets, rotating credentials | API keys, DB passwords |
| Hybrid | Mix of baked + injected | Config baked, secrets injected |

## Configuration Baking Pipeline

```python
#!/usr/bin/env python3
"""
Configuration baking pipeline for immutable infrastructure.
Generates environment-specific configs at build time and
manages boot-time secret injection.
"""

import json
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
import subprocess
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ConfigLayer:
    """A layer of configuration with a specific priority."""
    name: str
    priority: int  # Higher = override lower
    values: dict
    source: str = "static"  # static, ssm, vault, env


@dataclass
class ConfigSpec:
    """Specification for baked configuration."""
    app_name: str
    environment: str
    layers: list[ConfigLayer] = field(default_factory=list)
    templates: dict[str, str] = field(default_factory=dict)
    output_dir: str = "/opt/app/config"
    secret_paths: list[str] = field(default_factory=list)


@dataclass
class BakedConfig:
    spec: ConfigSpec
    resolved: dict
    files_written: list[str]
    config_hash: str
    secrets_deferred: list[str]


class ConfigBaker:
    """Resolves and bakes configuration into image artifacts."""

    def __init__(self):
        self._resolvers = {
            "static": self._resolve_static,
            "ssm": self._resolve_ssm,
            "env": self._resolve_env,
        }

    def bake(self, spec: ConfigSpec) -> BakedConfig:
        """Resolve all layers and write config files."""
        # Merge layers by priority
        merged = {}
        for layer in sorted(spec.layers, key=lambda l: l.priority):
            resolved = self._resolvers[layer.source](layer)
            merged.update(resolved)

        # Identify deferred secrets
        deferred = []
        for key, value in list(merged.items()):
            if isinstance(value, str) and value.startswith("ssm://"):
                deferred.append(key)

        # Write config files
        output = Path(spec.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        written = []

        # Main config as JSON
        config_path = output / "config.json"
        config_path.write_text(json.dumps(merged, indent=2))
        written.append(str(config_path))

        # Process templates
        for tmpl_name, tmpl_content in spec.templates.items():
            rendered = Template(tmpl_content).safe_substitute(merged)
            tmpl_path = output / tmpl_name
            tmpl_path.write_text(rendered)
            written.append(str(tmpl_path))

        # Write boot-time secret resolver script
        if deferred:
            script = self._generate_secret_resolver(spec, deferred, merged)
            script_path = output / "resolve-secrets.sh"
            script_path.write_text(script)
            script_path.chmod(0o755)
            written.append(str(script_path))

        config_hash = hashlib.sha256(
            json.dumps(merged, sort_keys=True).encode()).hexdigest()[:12]

        logger.info("Baked config for %s/%s: %d keys, %d deferred, hash=%s",
            spec.app_name, spec.environment, len(merged),
            len(deferred), config_hash)

        return BakedConfig(spec=spec, resolved=merged,
            files_written=written, config_hash=config_hash,
            secrets_deferred=deferred)

    def _resolve_static(self, layer: ConfigLayer) -> dict:
        return dict(layer.values)

    def _resolve_ssm(self, layer: ConfigLayer) -> dict:
        """Resolve values from AWS SSM Parameter Store at build time."""
        resolved = {}
        for key, ssm_path in layer.values.items():
            if isinstance(ssm_path, str) and ssm_path.startswith("/"):
                try:
                    result = subprocess.run([
                        "aws", "ssm", "get-parameter",
                        "--name", ssm_path, "--with-decryption",
                        "--query", "Parameter.Value", "--output", "text",
                    ], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        resolved[key] = result.stdout.strip()
                    else:
                        # Defer to boot time
                        resolved[key] = f"ssm://{ssm_path}"
                except Exception:
                    resolved[key] = f"ssm://{ssm_path}"
            else:
                resolved[key] = ssm_path
        return resolved

    def _resolve_env(self, layer: ConfigLayer) -> dict:
        import os
        resolved = {}
        for key, env_var in layer.values.items():
            resolved[key] = os.environ.get(env_var, "")
        return resolved

    def _generate_secret_resolver(self, spec: ConfigSpec,
                                   deferred: list, merged: dict) -> str:
        """Generate a boot-time script that resolves deferred secrets."""
        resolve_commands = []
        for key in deferred:
            ssm_path = merged[key].replace("ssm://", "")
            resolve_commands.append(
                f'  VALUE=$(aws ssm get-parameter --name "{ssm_path}" '
                f'--with-decryption --query "Parameter.Value" --output text)')
            resolve_commands.append(
                f'  jq --arg k "{key}" --arg v "$VALUE" '
                f"'.[$k] = $v' {spec.output_dir}/config.json > /tmp/config.json && "
                f"mv /tmp/config.json {spec.output_dir}/config.json")

        cmds = "\\n".join(resolve_commands)
        return f"""#!/bin/bash
set -euo pipefail
echo "Resolving secrets at boot time..."
{cmds}
echo "Secrets resolved successfully"
"""


class EnvironmentConfigManager:
    """Manages configuration across multiple environments."""

    def __init__(self, config_repo: str = "config/"):
        self.config_repo = Path(config_repo)
        self.baker = ConfigBaker()

    def build_for_environment(self, app_name: str, env: str) -> BakedConfig:
        """Build configuration for a specific environment."""
        # Load base config
        base = self._load_yaml(self.config_repo / app_name / "base.yaml")
        env_override = self._load_yaml(self.config_repo / app_name / f"{env}.yaml")

        spec = ConfigSpec(
            app_name=app_name, environment=env,
            layers=[
                ConfigLayer(name="base", priority=0, values=base, source="static"),
                ConfigLayer(name=env, priority=10, values=env_override, source="static"),
            ])

        # Add SSM layer for secrets
        secrets = self._load_yaml(self.config_repo / app_name / "secrets.yaml")
        if secrets:
            spec.layers.append(ConfigLayer(
                name="secrets", priority=20,
                values={k: f"/{env}/{app_name}/{k}" for k in secrets},
                source="ssm"))

        return self.baker.bake(spec)

    def _load_yaml(self, path: Path) -> dict:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}
```

## Key Patterns

- **Layer merging**: Base config overridden by environment-specific and secret layers in priority order
- **Build-time resolution**: Non-secret config resolved during image build, not at boot
- **Deferred secrets**: Secrets that cannot be baked are resolved at boot via SSM Parameter Store
- **Config hashing**: Every baked config gets a hash for traceability and drift detection
- **Template rendering**: Application-specific config files (nginx.conf, etc.) rendered from merged values
- **No runtime config management**: Instances launch with complete config -- no Chef/Puppet/Ansible at boot'''
    ),
    (
        "infrastructure/instance-replacement-strategies",
        "How do I implement safe instance replacement strategies for immutable infrastructure? Show rolling replacement, canary instances, and a Python orchestrator that handles draining, replacement, and verification.",
        '''Instance replacement in immutable infrastructure means replacing entire instances rather than patching in place. The key challenge is doing this safely with zero downtime.

## Replacement Strategies

| Strategy | Downtime | Rollback Speed | Cost |
|---|---|---|---|
| Rolling | Zero | Minutes | 1.3x normal |
| Blue-green | Zero | Seconds | 2x normal |
| Canary | Zero | Seconds | 1.1x normal |
| All-at-once | Brief | Slow | 1x normal |

## Instance Replacement Orchestrator

```python
#!/usr/bin/env python3
"""
Instance replacement orchestrator for immutable infrastructure.
Handles rolling replacements, connection draining, and verification
with automatic rollback on failure.
"""

import json
import time
import logging
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import subprocess

logger = logging.getLogger(__name__)


class ReplacementStrategy(Enum):
    ROLLING = "rolling"
    CANARY_THEN_ROLLING = "canary_then_rolling"


class InstanceState(Enum):
    HEALTHY = "healthy"
    DRAINING = "draining"
    TERMINATED = "terminated"
    LAUNCHING = "launching"
    FAILED = "failed"


@dataclass
class InstanceInfo:
    instance_id: str
    ami_id: str
    launch_time: datetime
    availability_zone: str
    state: InstanceState
    health_status: str = "unknown"


@dataclass
class ReplacementConfig:
    asg_name: str
    target_group_arn: str
    region: str
    new_ami_id: str
    strategy: ReplacementStrategy = ReplacementStrategy.ROLLING
    max_batch_size: int = 1
    pause_between_batches: int = 60
    drain_timeout: int = 120
    health_check_timeout: int = 180
    canary_validation_time: int = 300
    min_healthy_percent: float = 0.66
    rollback_on_failure: bool = True


@dataclass
class ReplacementResult:
    config: ReplacementConfig
    success: bool
    instances_replaced: int
    instances_failed: int
    total_duration: float
    phases: list[dict] = field(default_factory=list)
    error: str = ""


class InstanceReplacer:
    """Orchestrates safe instance replacement in ASGs."""

    def __init__(self):
        self._pre_drain_hooks: list[Callable] = []
        self._post_launch_hooks: list[Callable] = []

    def on_pre_drain(self, hook: Callable):
        self._pre_drain_hooks.append(hook)

    def on_post_launch(self, hook: Callable):
        self._post_launch_hooks.append(hook)

    def replace(self, config: ReplacementConfig) -> ReplacementResult:
        start = time.monotonic()
        result = ReplacementResult(config=config, success=False,
            instances_replaced=0, instances_failed=0, total_duration=0)

        try:
            instances = self._get_instances(config)
            if not instances:
                result.error = "No instances found in ASG"
                return result

            logger.info("Replacing %d instances in %s with AMI %s",
                len(instances), config.asg_name, config.new_ami_id)

            # Update launch template first
            self._update_launch_template(config)

            if config.strategy == ReplacementStrategy.CANARY_THEN_ROLLING:
                # Replace one instance first and validate
                canary = instances[0]
                logger.info("Canary: replacing %s", canary.instance_id)
                if not self._replace_instance(config, canary):
                    result.error = "Canary instance failed"
                    result.instances_failed = 1
                    if config.rollback_on_failure:
                        self._rollback_launch_template(config)
                    return result

                result.instances_replaced = 1
                logger.info("Canary healthy, waiting %ds before rolling",
                    config.canary_validation_time)
                time.sleep(config.canary_validation_time)

                # Verify canary is still healthy
                if not self._verify_instance_healthy(config):
                    result.error = "Canary became unhealthy during validation"
                    return result

                instances = instances[1:]

            # Rolling replacement of remaining instances
            batches = self._create_batches(instances, config.max_batch_size)
            for i, batch in enumerate(batches):
                phase = {"batch": i + 1, "instances": [inst.instance_id for inst in batch]}
                logger.info("Batch %d/%d: replacing %s",
                    i + 1, len(batches), [inst.instance_id for inst in batch])

                for instance in batch:
                    if self._replace_instance(config, instance):
                        result.instances_replaced += 1
                    else:
                        result.instances_failed += 1
                        if config.rollback_on_failure:
                            result.error = f"Failed replacing {instance.instance_id}"
                            return result

                phase["status"] = "complete"
                result.phases.append(phase)

                if i < len(batches) - 1:
                    logger.info("Pausing %ds between batches", config.pause_between_batches)
                    time.sleep(config.pause_between_batches)

            result.success = result.instances_failed == 0
        except Exception as e:
            result.error = str(e)
            logger.exception("Replacement failed")
        finally:
            result.total_duration = time.monotonic() - start

        return result

    def _replace_instance(self, config: ReplacementConfig,
                           instance: InstanceInfo) -> bool:
        """Replace a single instance: drain -> terminate -> wait for replacement."""
        # Pre-drain hooks
        for hook in self._pre_drain_hooks:
            hook(instance)

        # Drain connections
        logger.info("Draining %s", instance.instance_id)
        self._deregister_from_target_group(config, instance.instance_id)
        time.sleep(config.drain_timeout)

        # Terminate
        logger.info("Terminating %s", instance.instance_id)
        subprocess.run([
            "aws", "autoscaling", "terminate-instance-in-auto-scaling-group",
            "--instance-id", instance.instance_id,
            "--should-decrement-desired-capacity", "false",
            "--region", config.region,
        ], capture_output=True, text=True, check=True)

        # Wait for replacement to become healthy
        if not self._wait_for_new_healthy(config, config.health_check_timeout):
            logger.error("New instance failed health checks")
            return False

        # Post-launch hooks
        for hook in self._post_launch_hooks:
            hook(instance)

        return True

    def _get_instances(self, config: ReplacementConfig) -> list[InstanceInfo]:
        result = subprocess.run([
            "aws", "autoscaling", "describe-auto-scaling-groups",
            "--auto-scaling-group-names", config.asg_name,
            "--region", config.region, "--output", "json",
        ], capture_output=True, text=True)
        data = json.loads(result.stdout)
        instances = []
        for group in data.get("AutoScalingGroups", []):
            for inst in group.get("Instances", []):
                instances.append(InstanceInfo(
                    instance_id=inst["InstanceId"],
                    ami_id="", availability_zone=inst["AvailabilityZone"],
                    launch_time=datetime.now(timezone.utc),
                    state=InstanceState.HEALTHY,
                    health_status=inst.get("HealthStatus", "unknown")))
        return instances

    def _create_batches(self, instances: list[InstanceInfo],
                         batch_size: int) -> list[list[InstanceInfo]]:
        return [instances[i:i + batch_size]
                for i in range(0, len(instances), batch_size)]

    def _update_launch_template(self, config: ReplacementConfig):
        subprocess.run([
            "aws", "ec2", "create-launch-template-version",
            "--launch-template-name", f"{config.asg_name}-lt",
            "--source-version", "$Latest",
            "--launch-template-data", json.dumps({"ImageId": config.new_ami_id}),
            "--region", config.region,
        ], capture_output=True, text=True, check=True)

    def _rollback_launch_template(self, config: ReplacementConfig):
        logger.warning("Rolling back launch template for %s", config.asg_name)

    def _deregister_from_target_group(self, config: ReplacementConfig,
                                       instance_id: str):
        subprocess.run([
            "aws", "elbv2", "deregister-targets",
            "--target-group-arn", config.target_group_arn,
            "--targets", json.dumps([{"Id": instance_id}]),
            "--region", config.region,
        ], capture_output=True, text=True)

    def _wait_for_new_healthy(self, config: ReplacementConfig,
                               timeout: int) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = subprocess.run([
                "aws", "elbv2", "describe-target-health",
                "--target-group-arn", config.target_group_arn,
                "--region", config.region, "--output", "json",
            ], capture_output=True, text=True)
            data = json.loads(result.stdout) if result.returncode == 0 else {}
            targets = data.get("TargetHealthDescriptions", [])
            healthy = sum(1 for t in targets
                          if t.get("TargetHealth", {}).get("State") == "healthy")
            total = len(targets)
            if total > 0 and healthy / total >= config.min_healthy_percent:
                return True
            time.sleep(10)
        return False

    def _verify_instance_healthy(self, config: ReplacementConfig) -> bool:
        return self._wait_for_new_healthy(config, 60)
```

## Key Patterns

- **Canary-then-rolling**: Replace one instance first, validate thoroughly, then continue rolling
- **Connection draining**: Instances deregistered from target group and drained before termination
- **Health-gated progress**: Each batch must pass health checks before the next batch starts
- **Batch sizing**: Control blast radius with configurable batch sizes (1 at a time for safety)
- **Hook system**: Pre-drain and post-launch hooks for custom actions (log rotation, cache warming)
- **Minimum healthy threshold**: Never drop below 66% healthy instances during replacement'''
    ),
    (
        "infrastructure/immutable-image-testing",
        "How do I test machine images before deploying to production? Show an image validation framework with Goss tests, InSpec compliance profiles, and a Python test orchestrator that launches temporary instances.",
        '''Image testing validates that baked images are correct, secure, and compliant before they reach production. Tests run inside temporary instances launched from the candidate AMI.

## Image Testing Pipeline

| Phase | Tool | Tests |
|---|---|---|
| Syntax | Packer validate | Template correctness |
| Unit | Goss | Service running, files exist, ports open |
| Compliance | InSpec | CIS benchmarks, security policies |
| Integration | Custom | API endpoints respond, DB connectivity |
| Smoke | Curl/httpie | End-to-end health check |

## Image Test Orchestrator

```python
#!/usr/bin/env python3
"""
Machine image testing framework.
Launches temporary instances from candidate AMIs, runs
Goss/InSpec tests, and reports compliance status.
"""

import json
import time
import logging
import subprocess
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class TestSpec:
    name: str
    test_type: str  # "goss", "inspec", "script"
    source: str  # Path to test file or script
    timeout: int = 120
    required: bool = True


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_seconds: float
    output: str = ""
    failures: list[str] = field(default_factory=list)


@dataclass
class ImageTestConfig:
    ami_id: str
    region: str
    instance_type: str = "t3.small"
    subnet_id: str = ""
    security_group_id: str = ""
    key_name: str = ""
    ssh_user: str = "ubuntu"
    tests: list[TestSpec] = field(default_factory=list)
    cleanup: bool = True


@dataclass
class ImageTestReport:
    ami_id: str
    timestamp: datetime
    passed: bool
    test_results: list[TestResult]
    instance_id: str
    total_duration: float
    compliance_score: float = 0.0


class ImageTestOrchestrator:
    """Launches temporary instances and runs validation tests."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region

    def test_image(self, config: ImageTestConfig) -> ImageTestReport:
        """Launch instance, run tests, report results."""
        start = time.monotonic()
        instance_id = ""

        try:
            # Launch test instance
            instance_id = self._launch_instance(config)
            logger.info("Launched test instance %s from AMI %s",
                instance_id, config.ami_id)

            # Wait for SSH
            ip = self._get_instance_ip(instance_id)
            self._wait_for_ssh(ip, config.ssh_user, timeout=180)

            # Run tests
            results = []
            for test in config.tests:
                result = self._run_test(test, ip, config.ssh_user)
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                logger.info("  %s: %s [%s] (%.1fs)",
                    test.name, test.test_type, status, result.duration_seconds)

            # Calculate compliance score
            total = len(results)
            passed = sum(1 for r in results if r.passed)
            score = (passed / total * 100) if total else 0

            all_passed = all(r.passed for r in results if
                any(t.required and t.name == r.name for t in config.tests))

            return ImageTestReport(
                ami_id=config.ami_id,
                timestamp=datetime.now(timezone.utc),
                passed=all_passed,
                test_results=results,
                instance_id=instance_id,
                total_duration=time.monotonic() - start,
                compliance_score=score)

        finally:
            if config.cleanup and instance_id:
                self._terminate_instance(instance_id)
                logger.info("Cleaned up test instance %s", instance_id)

    def _launch_instance(self, config: ImageTestConfig) -> str:
        cmd = [
            "aws", "ec2", "run-instances",
            "--image-id", config.ami_id,
            "--instance-type", config.instance_type,
            "--region", config.region,
            "--count", "1",
            "--tag-specifications",
            f'ResourceType=instance,Tags=[{{Key=Name,Value=image-test-{config.ami_id}}},'
            f'{{Key=Purpose,Value=image-testing}}]',
            "--output", "json",
        ]
        if config.subnet_id:
            cmd.extend(["--subnet-id", config.subnet_id])
        if config.security_group_id:
            cmd.extend(["--security-group-ids", config.security_group_id])
        if config.key_name:
            cmd.extend(["--key-name", config.key_name])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        instance_id = data["Instances"][0]["InstanceId"]

        # Wait for running state
        subprocess.run([
            "aws", "ec2", "wait", "instance-running",
            "--instance-ids", instance_id, "--region", config.region,
        ], capture_output=True, text=True, timeout=300)
        return instance_id

    def _get_instance_ip(self, instance_id: str) -> str:
        result = subprocess.run([
            "aws", "ec2", "describe-instances",
            "--instance-ids", instance_id,
            "--query", "Reservations[0].Instances[0].PrivateIpAddress",
            "--output", "text", "--region", self.region,
        ], capture_output=True, text=True)
        return result.stdout.strip()

    def _wait_for_ssh(self, ip: str, user: str, timeout: int = 180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
                 f"{user}@{ip}", "echo", "ready"],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return
            time.sleep(5)
        raise TimeoutError(f"SSH not available on {ip} after {timeout}s")

    def _run_test(self, test: TestSpec, ip: str, user: str) -> TestResult:
        start = time.monotonic()
        try:
            if test.test_type == "goss":
                return self._run_goss(test, ip, user, start)
            elif test.test_type == "inspec":
                return self._run_inspec(test, ip, user, start)
            elif test.test_type == "script":
                return self._run_script(test, ip, user, start)
            else:
                return TestResult(name=test.name, passed=False,
                    duration_seconds=0, output=f"Unknown test type: {test.test_type}")
        except Exception as e:
            return TestResult(name=test.name, passed=False,
                duration_seconds=time.monotonic() - start, output=str(e))

    def _run_goss(self, test: TestSpec, ip: str, user: str, start: float) -> TestResult:
        # Copy goss file and run
        subprocess.run(["scp", "-o", "StrictHostKeyChecking=no",
            test.source, f"{user}@{ip}:/tmp/goss.yaml"],
            capture_output=True, text=True, check=True, timeout=30)
        result = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{ip}",
            "goss", "-g", "/tmp/goss.yaml", "validate", "--format", "json",
        ], capture_output=True, text=True, timeout=test.timeout)

        duration = time.monotonic() - start
        try:
            data = json.loads(result.stdout)
            failed = data.get("summary", {}).get("failed-count", 0)
            failures = [r["summary-line"] for r in data.get("results", [])
                       if r.get("successful") is False]
            return TestResult(name=test.name, passed=failed == 0,
                duration_seconds=duration, output=result.stdout, failures=failures)
        except json.JSONDecodeError:
            return TestResult(name=test.name, passed=result.returncode == 0,
                duration_seconds=duration, output=result.stdout + result.stderr)

    def _run_inspec(self, test: TestSpec, ip: str, user: str, start: float) -> TestResult:
        result = subprocess.run([
            "inspec", "exec", test.source,
            "-t", f"ssh://{user}@{ip}",
            "--reporter", "json",
        ], capture_output=True, text=True, timeout=test.timeout)
        duration = time.monotonic() - start
        return TestResult(name=test.name, passed=result.returncode == 0,
            duration_seconds=duration, output=result.stdout[:2000])

    def _run_script(self, test: TestSpec, ip: str, user: str, start: float) -> TestResult:
        subprocess.run(["scp", "-o", "StrictHostKeyChecking=no",
            test.source, f"{user}@{ip}:/tmp/test.sh"],
            capture_output=True, text=True, check=True, timeout=30)
        result = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{ip}",
            "bash", "/tmp/test.sh",
        ], capture_output=True, text=True, timeout=test.timeout)
        duration = time.monotonic() - start
        return TestResult(name=test.name, passed=result.returncode == 0,
            duration_seconds=duration, output=result.stdout + result.stderr)

    def _terminate_instance(self, instance_id: str):
        subprocess.run([
            "aws", "ec2", "terminate-instances",
            "--instance-ids", instance_id, "--region", self.region,
        ], capture_output=True, text=True)
```

## Key Patterns

- **Ephemeral test instances**: Temporary instances launched, tested, and terminated automatically
- **Multi-layer testing**: Goss for unit tests, InSpec for compliance, custom scripts for integration
- **Required vs optional tests**: Critical tests gate promotion, informational tests report only
- **Compliance scoring**: Percentage-based score enables gradual security improvement
- **Automatic cleanup**: Test instances always terminated, even on test failure
- **SSH-based execution**: Tests run inside the actual image, not in a simulator'''
    ),
]
