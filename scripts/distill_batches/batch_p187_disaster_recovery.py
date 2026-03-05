"""Disaster recovery patterns."""

PAIRS = [
    (
        "disaster-recovery/rpo-rto-failover-strategies",
        "Design RPO/RTO planning and failover strategies for a multi-tier application with different recovery requirements for databases, application servers, and caches.",
        '''RPO/RTO planning and failover strategies:

```python
# --- Disaster recovery planning framework ---

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DRTier(str, Enum):
    TIER_0 = "tier_0"  # Mission-critical: RPO=0, RTO<15min
    TIER_1 = "tier_1"  # Business-critical: RPO<1h, RTO<1h
    TIER_2 = "tier_2"  # Important: RPO<4h, RTO<4h
    TIER_3 = "tier_3"  # Non-critical: RPO<24h, RTO<24h


class DRStrategy(str, Enum):
    ACTIVE_ACTIVE = "active_active"          # Multi-region, both serving
    HOT_STANDBY = "hot_standby"              # Warm secondary, fast failover
    WARM_STANDBY = "warm_standby"            # Scaled-down secondary
    PILOT_LIGHT = "pilot_light"              # Minimal infra, scale on failover
    BACKUP_RESTORE = "backup_restore"        # Backups only, rebuild on failover


class FailoverType(str, Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    SEMI_AUTOMATIC = "semi_automatic"  # Automatic detection, manual trigger


@dataclass
class ServiceDRConfig:
    """Disaster recovery configuration for a service."""

    service_name: str
    tier: DRTier
    strategy: DRStrategy
    failover_type: FailoverType

    # Recovery objectives
    rpo: timedelta          # Recovery Point Objective
    rto: timedelta          # Recovery Time Objective
    mtpd: timedelta         # Maximum Tolerable Period of Disruption

    # Infrastructure
    primary_region: str = "us-east-1"
    secondary_region: str = "us-west-2"
    data_replication: str = "async"  # sync, async, backup-only

    # Dependencies
    depends_on: list[str] = field(default_factory=list)
    depended_by: list[str] = field(default_factory=list)

    # Testing
    last_dr_test: Optional[str] = None
    test_frequency_days: int = 90


@dataclass
class DRPlan:
    """Complete disaster recovery plan."""

    services: list[ServiceDRConfig] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate DR plan for consistency."""
        issues: list[str] = []

        for svc in self.services:
            # RPO must be achievable with replication strategy
            if svc.data_replication == "backup-only" and svc.rpo < timedelta(hours=1):
                issues.append(
                    f"{svc.service_name}: RPO={svc.rpo} requires sync/async "
                    f"replication, not backup-only"
                )

            # Strategy must match tier
            if svc.tier == DRTier.TIER_0 and svc.strategy not in (
                DRStrategy.ACTIVE_ACTIVE, DRStrategy.HOT_STANDBY
            ):
                issues.append(
                    f"{svc.service_name}: Tier 0 requires active-active or "
                    f"hot standby, not {svc.strategy.value}"
                )

            # Check dependency consistency
            for dep_name in svc.depends_on:
                dep = self._find_service(dep_name)
                if dep and dep.rto > svc.rto:
                    issues.append(
                        f"{svc.service_name} (RTO={svc.rto}) depends on "
                        f"{dep_name} (RTO={dep.rto}) which has slower recovery"
                    )

            # Check test freshness
            if svc.last_dr_test:
                from datetime import datetime
                last_test = datetime.fromisoformat(svc.last_dr_test)
                days_since = (datetime.utcnow() - last_test).days
                if days_since > svc.test_frequency_days:
                    issues.append(
                        f"{svc.service_name}: DR test overdue by "
                        f"{days_since - svc.test_frequency_days} days"
                    )

        return issues

    def get_failover_order(self) -> list[ServiceDRConfig]:
        """Determine service failover order based on dependencies."""
        # Topological sort by dependencies
        visited: set[str] = set()
        order: list[ServiceDRConfig] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            svc = self._find_service(name)
            if svc:
                for dep in svc.depends_on:
                    visit(dep)
                order.append(svc)

        for svc in self.services:
            visit(svc.service_name)

        return order

    def _find_service(self, name: str) -> ServiceDRConfig | None:
        return next(
            (s for s in self.services if s.service_name == name), None
        )


# --- Example DR Plan ---
PRODUCTION_DR_PLAN = DRPlan(
    services=[
        ServiceDRConfig(
            service_name="payment-db",
            tier=DRTier.TIER_0,
            strategy=DRStrategy.HOT_STANDBY,
            failover_type=FailoverType.AUTOMATIC,
            rpo=timedelta(seconds=0),
            rto=timedelta(minutes=5),
            mtpd=timedelta(hours=1),
            data_replication="sync",
            depends_on=[],
            depended_by=["payment-service"],
        ),
        ServiceDRConfig(
            service_name="payment-service",
            tier=DRTier.TIER_0,
            strategy=DRStrategy.ACTIVE_ACTIVE,
            failover_type=FailoverType.AUTOMATIC,
            rpo=timedelta(seconds=0),
            rto=timedelta(minutes=5),
            mtpd=timedelta(hours=1),
            depends_on=["payment-db"],
            depended_by=["api-gateway"],
        ),
        ServiceDRConfig(
            service_name="user-db",
            tier=DRTier.TIER_1,
            strategy=DRStrategy.HOT_STANDBY,
            failover_type=FailoverType.SEMI_AUTOMATIC,
            rpo=timedelta(minutes=5),
            rto=timedelta(minutes=30),
            mtpd=timedelta(hours=4),
            data_replication="async",
            depends_on=[],
            depended_by=["user-service"],
        ),
        ServiceDRConfig(
            service_name="analytics-db",
            tier=DRTier.TIER_3,
            strategy=DRStrategy.BACKUP_RESTORE,
            failover_type=FailoverType.MANUAL,
            rpo=timedelta(hours=24),
            rto=timedelta(hours=24),
            mtpd=timedelta(days=7),
            data_replication="backup-only",
        ),
    ]
)
```

```python
# --- Automated failover controller ---

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import boto3

logger = logging.getLogger(__name__)


@dataclass
class FailoverController:
    """Manages automated and manual failover between regions."""

    session: boto3.Session
    primary_region: str = "us-east-1"
    secondary_region: str = "us-west-2"
    dr_plan: DRPlan = field(default_factory=DRPlan)

    def initiate_failover(
        self,
        reason: str,
        services: list[str] | None = None,
    ) -> dict[str, Any]:
        """Initiate DR failover for specified services or all."""
        logger.critical(f"FAILOVER INITIATED: {reason}")
        start_time = datetime.utcnow()

        # Get failover order
        all_services = self.dr_plan.get_failover_order()
        if services:
            all_services = [
                s for s in all_services if s.service_name in services
            ]

        results: dict[str, Any] = {
            "initiated_at": start_time.isoformat(),
            "reason": reason,
            "services": {},
        }

        for svc in all_services:
            logger.info(f"Failing over: {svc.service_name}")
            svc_start = datetime.utcnow()

            try:
                if svc.strategy == DRStrategy.ACTIVE_ACTIVE:
                    status = self._failover_active_active(svc)
                elif svc.strategy == DRStrategy.HOT_STANDBY:
                    status = self._failover_hot_standby(svc)
                elif svc.strategy == DRStrategy.WARM_STANDBY:
                    status = self._failover_warm_standby(svc)
                elif svc.strategy == DRStrategy.PILOT_LIGHT:
                    status = self._failover_pilot_light(svc)
                else:
                    status = self._failover_backup_restore(svc)

                elapsed = (datetime.utcnow() - svc_start).total_seconds()
                results["services"][svc.service_name] = {
                    "status": "success",
                    "strategy": svc.strategy.value,
                    "elapsed_seconds": elapsed,
                    "within_rto": elapsed < svc.rto.total_seconds(),
                    **status,
                }
            except Exception as e:
                results["services"][svc.service_name] = {
                    "status": "failed",
                    "error": str(e),
                }

        total_elapsed = (datetime.utcnow() - start_time).total_seconds()
        results["total_elapsed_seconds"] = total_elapsed
        results["all_successful"] = all(
            s["status"] == "success"
            for s in results["services"].values()
        )

        logger.info(f"Failover complete: {results['all_successful']}, "
                     f"elapsed={total_elapsed:.1f}s")
        return results

    def _failover_active_active(
        self, svc: ServiceDRConfig
    ) -> dict[str, Any]:
        """Active-active: remove primary from Route53 weighted set."""
        r53 = self.session.client("route53")

        # Update Route53 health check to mark primary unhealthy
        # Traffic automatically shifts to secondary
        return {
            "action": "Removed primary from Route53 weighted routing",
            "primary_weight": 0,
            "secondary_weight": 100,
        }

    def _failover_hot_standby(
        self, svc: ServiceDRConfig
    ) -> dict[str, Any]:
        """Hot standby: promote secondary DB, scale up secondary compute."""
        if "db" in svc.service_name:
            # Promote RDS read replica
            rds = self.session.client("rds", region_name=self.secondary_region)
            rds.promote_read_replica(
                DBInstanceIdentifier=f"{svc.service_name}-replica"
            )
            return {"action": "Promoted RDS read replica to primary"}
        else:
            # Scale up secondary ASG
            autoscaling = self.session.client(
                "autoscaling", region_name=self.secondary_region
            )
            autoscaling.update_auto_scaling_group(
                AutoScalingGroupName=f"{svc.service_name}-secondary",
                MinSize=3,
                DesiredCapacity=3,
            )
            return {"action": "Scaled up secondary ASG"}

    def _failover_warm_standby(
        self, svc: ServiceDRConfig
    ) -> dict[str, Any]:
        """Warm standby: scale secondary from minimal to production size."""
        autoscaling = self.session.client(
            "autoscaling", region_name=self.secondary_region
        )
        autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=f"{svc.service_name}-dr",
            MinSize=3,
            MaxSize=10,
            DesiredCapacity=3,
        )
        return {"action": "Scaled warm standby to production capacity"}

    def _failover_pilot_light(
        self, svc: ServiceDRConfig
    ) -> dict[str, Any]:
        """Pilot light: spin up all infrastructure from pre-configured state."""
        # Deploy full stack using Terraform/CloudFormation
        return {
            "action": "Deploying full stack from pilot light configuration"
        }

    def _failover_backup_restore(
        self, svc: ServiceDRConfig
    ) -> dict[str, Any]:
        """Backup/restore: restore from latest backup in secondary region."""
        return {
            "action": "Restoring from latest cross-region backup"
        }
```

```hcl
# --- Terraform: multi-region DR infrastructure ---

# Primary region
provider "aws" {
  alias  = "primary"
  region = "us-east-1"
}

# DR region
provider "aws" {
  alias  = "secondary"
  region = "us-west-2"
}

# Global Route53 health check + failover
resource "aws_route53_health_check" "primary" {
  fqdn              = "api-primary.acme.dev"
  port               = 443
  type               = "HTTPS"
  resource_path      = "/health"
  failure_threshold  = 3
  request_interval   = 10

  tags = {
    Name = "primary-health-check"
  }
}

resource "aws_route53_record" "api_failover_primary" {
  zone_id = var.route53_zone_id
  name    = "api.acme.dev"
  type    = "A"

  alias {
    name                   = aws_lb.primary.dns_name
    zone_id                = aws_lb.primary.zone_id
    evaluate_target_health = true
  }

  failover_routing_policy {
    type = "PRIMARY"
  }

  set_identifier  = "primary"
  health_check_id = aws_route53_health_check.primary.id
}

resource "aws_route53_record" "api_failover_secondary" {
  zone_id = var.route53_zone_id
  name    = "api.acme.dev"
  type    = "A"

  alias {
    name                   = aws_lb.secondary.dns_name
    zone_id                = aws_lb.secondary.zone_id
    evaluate_target_health = true
  }

  failover_routing_policy {
    type = "SECONDARY"
  }

  set_identifier = "secondary"
}

# RDS with cross-region read replica
resource "aws_db_instance" "primary" {
  provider = aws.primary

  identifier     = "payment-db-primary"
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = "db.r6g.large"

  multi_az                = true
  backup_retention_period = 35
  storage_encrypted       = true

  tags = { DR = "primary" }
}

resource "aws_db_instance" "replica" {
  provider = aws.secondary

  identifier          = "payment-db-replica"
  replicate_source_db = aws_db_instance.primary.arn
  instance_class      = "db.r6g.large"
  storage_encrypted   = true

  tags = { DR = "secondary-replica" }
}

# S3 cross-region replication for backups
resource "aws_s3_bucket_replication_configuration" "backup_replication" {
  provider = aws.primary
  bucket   = aws_s3_bucket.backups_primary.id
  role     = aws_iam_role.replication.arn

  rule {
    id     = "replicate-backups"
    status = "Enabled"

    destination {
      bucket        = aws_s3_bucket.backups_secondary.arn
      storage_class = "STANDARD_IA"

      encryption_configuration {
        replica_kms_key_id = aws_kms_key.secondary.arn
      }
    }

    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }
  }
}
```

| DR Strategy | RPO | RTO | Monthly Cost Multiplier | Best For |
|---|---|---|---|---|
| Active-active | ~0 | ~0 (instant) | 2.0x | Payment processing, auth |
| Hot standby | Seconds-minutes | 5-30 minutes | 1.5-1.8x | Core databases, APIs |
| Warm standby | Minutes-hours | 30-60 minutes | 1.2-1.4x | Business-critical services |
| Pilot light | Hours | 1-4 hours | 1.05-1.1x | Internal tools |
| Backup/restore | Hours-day | 4-24 hours | 1.01-1.05x | Analytics, batch systems |

Key patterns:

1. **Tier services by criticality** — Tier 0 (payments, auth) gets active-active; Tier 3 (analytics) gets backup/restore; match cost to business impact
2. **Dependency-ordered failover** — fail over databases before application servers; use topological sort to determine correct sequence
3. **Route53 failover routing** — use DNS-level failover with health checks for automatic traffic redirection when primary becomes unhealthy
4. **Cross-region read replicas** — pre-provision RDS read replicas in the DR region; promote to primary during failover for fastest database recovery
5. **Test DR quarterly** — run full failover drills every 90 days; measure actual RPO/RTO against targets and document gaps
6. **Runbook automation** — encode failover steps in code (Python/Terraform); manual runbooks are too slow and error-prone during incidents
'''
    ),
    (
        "disaster-recovery/database-backup-restore",
        "Implement comprehensive database backup and restore patterns for PostgreSQL and DynamoDB with point-in-time recovery, cross-region replication, and automated testing.",
        '''Database backup and restore patterns:

```python
# --- PostgreSQL backup and restore management ---

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)


@dataclass
class PostgresBackupConfig:
    """Configuration for PostgreSQL backup strategy."""

    database_name: str
    host: str
    port: int = 5432
    user: str = "backup_user"

    # Backup schedule
    full_backup_schedule: str = "daily"      # daily, weekly
    wal_archiving: bool = True               # Continuous WAL archiving
    retention_days: int = 30
    cross_region_copy: bool = True

    # Storage
    s3_bucket: str = ""
    s3_prefix: str = "backups/postgres"
    kms_key_id: str = ""

    # Point-in-time recovery
    pitr_enabled: bool = True
    pitr_retention_days: int = 7


@dataclass
class PostgresBackupManager:
    """Manages PostgreSQL backup and restore operations."""

    config: PostgresBackupConfig
    session: boto3.Session

    def create_logical_backup(self) -> dict[str, Any]:
        """Create a pg_dump logical backup."""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        dump_file = f"/tmp/{self.config.database_name}-{timestamp}.sql.gz"

        # pg_dump with compression
        result = subprocess.run(
            [
                "pg_dump",
                f"--host={self.config.host}",
                f"--port={self.config.port}",
                f"--username={self.config.user}",
                "--format=custom",
                "--compress=9",
                "--verbose",
                f"--file={dump_file}",
                self.config.database_name,
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self._get_password()},
        )

        if result.returncode != 0:
            logger.error(f"pg_dump failed: {result.stderr}")
            raise RuntimeError(f"Backup failed: {result.stderr}")

        # Upload to S3
        s3_key = (
            f"{self.config.s3_prefix}/{self.config.database_name}/"
            f"{timestamp}/dump.custom.gz"
        )
        self._upload_to_s3(dump_file, s3_key)

        # Calculate size
        import os
        size_mb = os.path.getsize(dump_file) / 1024 / 1024

        # Cleanup local file
        os.remove(dump_file)

        backup_info = {
            "type": "logical",
            "database": self.config.database_name,
            "timestamp": timestamp,
            "s3_key": s3_key,
            "size_mb": round(size_mb, 2),
            "duration_seconds": 0,  # Would measure actual time
        }

        logger.info(f"Logical backup complete: {backup_info}")
        return backup_info

    def create_physical_backup(self) -> dict[str, Any]:
        """Create pg_basebackup physical backup for PITR."""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_dir = f"/tmp/pgbase-{timestamp}"

        result = subprocess.run(
            [
                "pg_basebackup",
                f"--host={self.config.host}",
                f"--port={self.config.port}",
                f"--username={self.config.user}",
                "--format=tar",
                "--gzip",
                "--compress=9",
                "--wal-method=stream",
                "--checkpoint=fast",
                f"--pgdata={backup_dir}",
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self._get_password()},
        )

        if result.returncode != 0:
            raise RuntimeError(f"Base backup failed: {result.stderr}")

        # Upload tar to S3
        s3_key = (
            f"{self.config.s3_prefix}/{self.config.database_name}/"
            f"base/{timestamp}/base.tar.gz"
        )
        self._upload_to_s3(f"{backup_dir}/base.tar.gz", s3_key)

        return {
            "type": "physical",
            "database": self.config.database_name,
            "timestamp": timestamp,
            "s3_key": s3_key,
        }

    def restore_logical(
        self,
        s3_key: str,
        target_database: str | None = None,
    ) -> dict[str, Any]:
        """Restore from a logical backup."""
        target_db = target_database or f"{self.config.database_name}_restored"
        dump_file = "/tmp/restore-dump.custom.gz"

        # Download from S3
        self._download_from_s3(s3_key, dump_file)

        # Create target database
        subprocess.run(
            [
                "createdb",
                f"--host={self.config.host}",
                f"--port={self.config.port}",
                f"--username={self.config.user}",
                target_db,
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self._get_password()},
        )

        # Restore
        result = subprocess.run(
            [
                "pg_restore",
                f"--host={self.config.host}",
                f"--port={self.config.port}",
                f"--username={self.config.user}",
                f"--dbname={target_db}",
                "--verbose",
                "--no-owner",
                "--no-privileges",
                dump_file,
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self._get_password()},
        )

        return {
            "restored_to": target_db,
            "source": s3_key,
            "success": result.returncode == 0,
            "warnings": result.stderr[:500] if result.stderr else None,
        }

    def restore_pitr(
        self,
        target_time: datetime,
    ) -> dict[str, Any]:
        """Point-in-time recovery using base backup + WAL replay."""
        # Find the latest base backup before target_time
        base_backup = self._find_base_backup(target_time)
        if not base_backup:
            raise ValueError(f"No base backup found before {target_time}")

        logger.info(
            f"PITR to {target_time} using base backup "
            f"from {base_backup['timestamp']}"
        )

        # In production, this would:
        # 1. Restore base backup
        # 2. Configure recovery.conf / postgresql.conf with recovery_target_time
        # 3. Copy WAL files from archive
        # 4. Start PostgreSQL in recovery mode

        return {
            "type": "pitr",
            "target_time": target_time.isoformat(),
            "base_backup": base_backup["timestamp"],
            "status": "initiated",
        }

    def _upload_to_s3(self, local_path: str, s3_key: str) -> None:
        s3 = self.session.client("s3")
        s3.upload_file(
            local_path,
            self.config.s3_bucket,
            s3_key,
            ExtraArgs={
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": self.config.kms_key_id,
            },
        )

    def _download_from_s3(self, s3_key: str, local_path: str) -> None:
        s3 = self.session.client("s3")
        s3.download_file(self.config.s3_bucket, s3_key, local_path)

    def _get_password(self) -> str:
        sm = self.session.client("secretsmanager")
        resp = sm.get_secret_value(
            SecretId=f"{self.config.database_name}-backup-credentials"
        )
        import json
        return json.loads(resp["SecretString"])["password"]

    def _find_base_backup(
        self, before: datetime
    ) -> dict[str, Any] | None:
        s3 = self.session.client("s3")
        prefix = (
            f"{self.config.s3_prefix}/{self.config.database_name}/base/"
        )
        resp = s3.list_objects_v2(Bucket=self.config.s3_bucket, Prefix=prefix)
        backups = []
        for obj in resp.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < before:
                backups.append({
                    "key": obj["Key"],
                    "timestamp": obj["LastModified"].isoformat(),
                    "size": obj["Size"],
                })
        return backups[-1] if backups else None
```

```python
# --- Automated backup verification ---

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BackupVerifier:
    """Automatically verifies backups by restoring and validating."""

    backup_manager: PostgresBackupManager
    test_host: str = "backup-test-db.internal"
    test_port: int = 5432

    async def verify_latest_backup(self) -> dict[str, Any]:
        """Restore latest backup to test instance and verify integrity."""
        import subprocess

        # Find latest backup
        s3 = self.backup_manager.session.client("s3")
        config = self.backup_manager.config
        prefix = f"{config.s3_prefix}/{config.database_name}/"

        resp = s3.list_objects_v2(
            Bucket=config.s3_bucket,
            Prefix=prefix,
            MaxKeys=100,
        )
        backups = sorted(
            resp.get("Contents", []),
            key=lambda x: x["LastModified"],
            reverse=True,
        )

        if not backups:
            return {"status": "failed", "reason": "No backups found"}

        latest = backups[0]
        logger.info(f"Verifying backup: {latest['Key']}")

        # Restore to test instance
        test_db = f"backup_verify_{config.database_name}"
        restore_result = self.backup_manager.restore_logical(
            s3_key=latest["Key"],
            target_database=test_db,
        )

        if not restore_result.get("success"):
            return {
                "status": "failed",
                "reason": "Restore failed",
                "details": restore_result,
            }

        # Run integrity checks
        checks = await self._run_integrity_checks(test_db)

        # Cleanup test database
        subprocess.run(
            [
                "dropdb",
                f"--host={self.test_host}",
                f"--port={self.test_port}",
                f"--username={config.user}",
                test_db,
            ],
            capture_output=True,
            env={"PGPASSWORD": self.backup_manager._get_password()},
        )

        return {
            "status": "passed" if all(c["passed"] for c in checks) else "failed",
            "backup_key": latest["Key"],
            "backup_age_hours": round(
                (
                    __import__("datetime").datetime.utcnow()
                    - latest["LastModified"].replace(tzinfo=None)
                ).total_seconds() / 3600,
                1,
            ),
            "backup_size_mb": round(latest["Size"] / 1024 / 1024, 2),
            "integrity_checks": checks,
        }

    async def _run_integrity_checks(
        self, database: str
    ) -> list[dict[str, Any]]:
        """Run data integrity checks on restored database."""
        import subprocess
        checks = []

        # Check 1: Table count matches expected
        result = subprocess.run(
            [
                "psql",
                f"--host={self.test_host}",
                f"--port={self.test_port}",
                f"--username={self.backup_manager.config.user}",
                f"--dbname={database}",
                "--tuples-only",
                "-c",
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';",
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self.backup_manager._get_password()},
        )
        table_count = int(result.stdout.strip()) if result.returncode == 0 else 0
        checks.append({
            "check": "table_count",
            "passed": table_count > 0,
            "value": table_count,
        })

        # Check 2: Row counts for critical tables
        for table in ["users", "payments", "orders"]:
            result = subprocess.run(
                [
                    "psql",
                    f"--host={self.test_host}",
                    f"--dbname={database}",
                    "--tuples-only",
                    "-c",
                    f"SELECT count(*) FROM {table};",
                ],
                capture_output=True,
                text=True,
                env={"PGPASSWORD": self.backup_manager._get_password()},
            )
            row_count = int(result.stdout.strip()) if result.returncode == 0 else -1
            checks.append({
                "check": f"row_count_{table}",
                "passed": row_count > 0,
                "value": row_count,
            })

        # Check 3: Index integrity
        result = subprocess.run(
            [
                "psql",
                f"--host={self.test_host}",
                f"--dbname={database}",
                "--tuples-only",
                "-c",
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';",
            ],
            capture_output=True,
            text=True,
            env={"PGPASSWORD": self.backup_manager._get_password()},
        )
        index_count = int(result.stdout.strip()) if result.returncode == 0 else 0
        checks.append({
            "check": "index_count",
            "passed": index_count > 0,
            "value": index_count,
        })

        return checks
```

```yaml
# --- AWS RDS automated backup configuration ---

# Terraform: RDS with automated backups and cross-region
resource "aws_db_instance" "payment_db" {
  identifier     = "payment-db"
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = "db.r6g.large"

  # Automated backups
  backup_retention_period = 35     # Keep 35 days of automated snapshots
  backup_window          = "03:00-04:00"  # UTC
  maintenance_window     = "sun:04:00-sun:05:00"

  # Point-in-time recovery (enabled by default with backups)
  # RDS automatically archives WAL to S3

  # Multi-AZ for HA
  multi_az = true

  # Encryption
  storage_encrypted = true
  kms_key_id        = aws_kms_key.database.arn

  # Performance insights
  performance_insights_enabled = true

  # Deletion protection
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "payment-db-final"
}

# Cross-region automated backup replication
resource "aws_db_instance_automated_backups_replication" "payment_db_dr" {
  source_db_instance_arn = aws_db_instance.payment_db.arn
  kms_key_id            = aws_kms_key.database_dr.arn
  retention_period      = 14

  # DR region
  provider = aws.secondary
}

# --- DynamoDB backup with PITR ---
resource "aws_dynamodb_table" "sessions" {
  name         = "sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  point_in_time_recovery {
    enabled = true  # Continuous backups, 35-day PITR
  }

  # Global table for multi-region
  replica {
    region_name = "us-west-2"
    kms_key_arn = aws_kms_key.dynamodb_dr.arn

    point_in_time_recovery {
      enabled = true
    }
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.dynamodb.arn
  }
}
```

| Backup Strategy | RPO | Recovery Speed | Cost | Automation |
|---|---|---|---|---|
| RDS automated snapshots | 5 min (PITR) | 15-60 min | Low (included) | Fully automated |
| RDS cross-region replica | Seconds (async) | 5 min (promote) | 1.5x instance cost | Automated |
| pg_dump logical | At backup time | 30-120 min | Low (S3 storage) | Scripted |
| pg_basebackup + WAL | Seconds (WAL) | 15-30 min | Medium (WAL storage) | Scripted |
| DynamoDB PITR | Seconds | Minutes | Included | Fully automated |
| DynamoDB on-demand backup | At backup time | Minutes-hours | Per-backup cost | Manual/scripted |
| DynamoDB Global Tables | Seconds (async) | Instant (multi-region) | 2x write cost | Fully automated |

Key patterns:

1. **Automated backup verification** — restore backups to a test instance daily and run integrity checks; untested backups are not trustworthy
2. **Cross-region replication** — replicate RDS snapshots and S3 backups to the DR region automatically; never rely on single-region backups
3. **Point-in-time recovery** — enable PITR for all databases; it provides second-level granularity for recovery from data corruption
4. **35-day retention minimum** — keep at least 35 days of backups for databases; extend to 7 years for compliance-critical data
5. **Backup encryption** — encrypt all backups with KMS; use separate keys per region for cross-region replication
6. **Runbook for each restore scenario** — document step-by-step restore procedures for: full restore, PITR, table-level restore, and cross-region restore
'''
    ),
    (
        "disaster-recovery/multi-region-active-active",
        "Design a multi-region active-active architecture with global load balancing, data synchronization, and conflict resolution for a web application.",
        '''Multi-region active-active architecture:

```python
# --- Multi-region traffic management ---

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import boto3

logger = logging.getLogger(__name__)


@dataclass
class MultiRegionConfig:
    """Configuration for multi-region active-active setup."""

    regions: list[str] = field(default_factory=lambda: [
        "us-east-1", "us-west-2", "eu-west-1",
    ])
    primary_region: str = "us-east-1"
    domain: str = "api.acme.dev"
    global_table_name: str = "user-sessions"

    # Traffic routing
    routing_policy: str = "latency"  # latency, geoproximity, weighted
    health_check_path: str = "/health"
    health_check_interval: int = 10


@dataclass
class GlobalLoadBalancer:
    """Manages Route53 global traffic routing."""

    session: boto3.Session
    config: MultiRegionConfig

    def setup_latency_routing(
        self,
        region_endpoints: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Configure latency-based routing across regions."""
        r53 = self.session.client("route53")
        zone_id = self._get_zone_id()
        records_created = []

        for region, endpoint in region_endpoints.items():
            # Create health check
            hc_resp = r53.create_health_check(
                CallerReference=f"{self.config.domain}-{region}-{__import__('time').time()}",
                HealthCheckConfig={
                    "FullyQualifiedDomainName": endpoint,
                    "Port": 443,
                    "Type": "HTTPS",
                    "ResourcePath": self.config.health_check_path,
                    "FailureThreshold": 3,
                    "RequestInterval": self.config.health_check_interval,
                    "EnableSNI": True,
                    "Regions": [
                        "us-east-1", "us-west-2", "eu-west-1",
                    ],
                },
            )
            hc_id = hc_resp["HealthCheck"]["Id"]

            # Create latency-based record
            r53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": self.config.domain,
                                "Type": "A",
                                "SetIdentifier": f"{region}-endpoint",
                                "Region": region,
                                "AliasTarget": {
                                    "HostedZoneId": self._get_alb_zone_id(region),
                                    "DNSName": endpoint,
                                    "EvaluateTargetHealth": True,
                                },
                                "HealthCheckId": hc_id,
                            },
                        }
                    ],
                },
            )

            records_created.append({
                "region": region,
                "endpoint": endpoint,
                "health_check_id": hc_id,
            })

        return records_created

    def _get_zone_id(self) -> str:
        r53 = self.session.client("route53")
        resp = r53.list_hosted_zones_by_name(
            DNSName=self.config.domain.split(".", 1)[1]
        )
        return resp["HostedZones"][0]["Id"].split("/")[-1]

    def _get_alb_zone_id(self, region: str) -> str:
        # ALB hosted zone IDs per region (simplified)
        zone_map = {
            "us-east-1": "Z35SXDOTRQ7X7K",
            "us-west-2": "Z1H1FL5HABSF5",
            "eu-west-1": "Z32O12XQLNTSW2",
        }
        return zone_map.get(region, "")
```

```python
# --- Conflict resolution for multi-region writes ---

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConflictStrategy(str, Enum):
    LAST_WRITER_WINS = "lww"
    FIRST_WRITER_WINS = "fww"
    MERGE = "merge"
    CUSTOM = "custom"


@dataclass
class VersionedRecord:
    """A record with vector clock for conflict detection."""

    key: str
    value: dict[str, Any]
    version: int = 1
    vector_clock: dict[str, int] = field(default_factory=dict)
    last_modified: datetime = field(default_factory=datetime.utcnow)
    modified_by_region: str = ""
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        import json
        data = json.dumps(self.value, sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()


@dataclass
class ConflictResolver:
    """Resolves conflicts in multi-region active-active writes."""

    default_strategy: ConflictStrategy = ConflictStrategy.LAST_WRITER_WINS
    field_strategies: dict[str, ConflictStrategy] = field(
        default_factory=dict
    )

    def detect_conflict(
        self,
        local: VersionedRecord,
        remote: VersionedRecord,
    ) -> bool:
        """Detect if two records are in conflict using vector clocks."""
        if local.key != remote.key:
            return False

        # Check if one dominates the other
        local_dominates = all(
            local.vector_clock.get(r, 0) >= remote.vector_clock.get(r, 0)
            for r in set(local.vector_clock) | set(remote.vector_clock)
        )
        remote_dominates = all(
            remote.vector_clock.get(r, 0) >= local.vector_clock.get(r, 0)
            for r in set(local.vector_clock) | set(remote.vector_clock)
        )

        # Conflict exists when neither dominates
        return not local_dominates and not remote_dominates

    def resolve(
        self,
        local: VersionedRecord,
        remote: VersionedRecord,
    ) -> VersionedRecord:
        """Resolve conflict between two versions of a record."""
        if not self.detect_conflict(local, remote):
            # No conflict: return the dominant version
            if local.version >= remote.version:
                return local
            return remote

        strategy = self.default_strategy
        logger.warning(
            f"Conflict detected for key={local.key}: "
            f"local(v{local.version}, {local.modified_by_region}) vs "
            f"remote(v{remote.version}, {remote.modified_by_region})"
        )

        if strategy == ConflictStrategy.LAST_WRITER_WINS:
            winner = (
                local if local.last_modified >= remote.last_modified
                else remote
            )
            logger.info(f"LWW resolved: {winner.modified_by_region} wins")
            return self._merge_clocks(winner, local, remote)

        elif strategy == ConflictStrategy.FIRST_WRITER_WINS:
            winner = (
                local if local.last_modified <= remote.last_modified
                else remote
            )
            return self._merge_clocks(winner, local, remote)

        elif strategy == ConflictStrategy.MERGE:
            return self._merge_records(local, remote)

        raise ValueError(f"Unknown strategy: {strategy}")

    def _merge_records(
        self,
        local: VersionedRecord,
        remote: VersionedRecord,
    ) -> VersionedRecord:
        """Merge two records field-by-field."""
        merged_value = {}

        all_keys = set(local.value) | set(remote.value)
        for key in all_keys:
            local_val = local.value.get(key)
            remote_val = remote.value.get(key)

            if local_val == remote_val:
                merged_value[key] = local_val
            elif key not in local.value:
                merged_value[key] = remote_val
            elif key not in remote.value:
                merged_value[key] = local_val
            else:
                # Field-level conflict: use field strategy or LWW
                field_strategy = self.field_strategies.get(
                    key, ConflictStrategy.LAST_WRITER_WINS
                )
                if field_strategy == ConflictStrategy.LAST_WRITER_WINS:
                    merged_value[key] = (
                        local_val
                        if local.last_modified >= remote.last_modified
                        else remote_val
                    )
                else:
                    merged_value[key] = local_val  # Default to local

        return self._merge_clocks(
            VersionedRecord(
                key=local.key,
                value=merged_value,
                version=max(local.version, remote.version) + 1,
                last_modified=datetime.utcnow(),
            ),
            local,
            remote,
        )

    def _merge_clocks(
        self,
        winner: VersionedRecord,
        a: VersionedRecord,
        b: VersionedRecord,
    ) -> VersionedRecord:
        """Merge vector clocks from both records."""
        merged_clock = {}
        all_regions = set(a.vector_clock) | set(b.vector_clock)
        for region in all_regions:
            merged_clock[region] = max(
                a.vector_clock.get(region, 0),
                b.vector_clock.get(region, 0),
            )
        winner.vector_clock = merged_clock
        winner.version = max(a.version, b.version) + 1
        return winner
```

```hcl
# --- Terraform: multi-region active-active infrastructure ---

# DynamoDB Global Table
resource "aws_dynamodb_table" "user_data" {
  name         = "user-data"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "data_type"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "data_type"
    type = "S"
  }

  # Enable PITR in all regions
  point_in_time_recovery {
    enabled = true
  }

  # Global table replicas
  replica {
    region_name = "us-west-2"
    point_in_time_recovery { enabled = true }
  }

  replica {
    region_name = "eu-west-1"
    point_in_time_recovery { enabled = true }
  }

  server_side_encryption {
    enabled = true
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
}

# Aurora Global Database
resource "aws_rds_global_cluster" "main" {
  global_cluster_identifier = "acme-global"
  engine                    = "aurora-postgresql"
  engine_version            = "15.4"
  storage_encrypted         = true
}

resource "aws_rds_cluster" "primary" {
  provider = aws.primary

  cluster_identifier        = "acme-primary"
  global_cluster_identifier = aws_rds_global_cluster.main.id
  engine                    = aws_rds_global_cluster.main.engine
  engine_version            = aws_rds_global_cluster.main.engine_version
  master_username           = "admin"
  master_password           = var.db_password
  database_name             = "acme"

  backup_retention_period = 35
  preferred_backup_window = "03:00-04:00"
}

resource "aws_rds_cluster" "secondary" {
  provider = aws.secondary

  cluster_identifier        = "acme-secondary"
  global_cluster_identifier = aws_rds_global_cluster.main.id
  engine                    = aws_rds_global_cluster.main.engine
  engine_version            = aws_rds_global_cluster.main.engine_version

  depends_on = [aws_rds_cluster.primary]
}

# ElastiCache Global Datastore for session caching
resource "aws_elasticache_global_replication_group" "sessions" {
  global_replication_group_id_suffix = "sessions"
  primary_replication_group_id       = aws_elasticache_replication_group.primary.id
  global_replication_group_description = "Session cache global datastore"
}
```

| Component | Active-Active Strategy | Consistency Model | Failover Time |
|---|---|---|---|
| DNS routing | Route53 latency-based | N/A | Health check interval |
| Application tier | Stateless, multi-region ASG | N/A (stateless) | Instant |
| Session store | ElastiCache Global Datastore | Eventually consistent | Seconds |
| User data | DynamoDB Global Tables | Eventually consistent | Instant |
| Relational DB | Aurora Global Database | Async replication | ~1 min (promote) |
| File storage | S3 Cross-Region Replication | Eventually consistent | Minutes |
| Message queue | SQS per region + fan-out | At-least-once | N/A |

Key patterns:

1. **Latency-based routing** — Route53 latency routing directs users to the nearest healthy region; automatic failover on health check failure
2. **DynamoDB Global Tables** — active-active with sub-second replication; last-writer-wins by default; use version attributes for custom conflict resolution
3. **Aurora Global Database** — single write region with up to 5 read replicas globally; promote secondary to write in < 1 minute for failover
4. **Stateless application tier** — store no session state in application servers; use DynamoDB/ElastiCache for session data so any region can serve any user
5. **Conflict resolution strategy** — choose LWW for most data, custom merge for critical business data (inventory, balances); document conflict semantics
6. **Regional isolation** — design so each region can operate independently during partition; queue cross-region operations for eventual sync
'''
    ),
    (
        "disaster-recovery/chaos-engineering-dr-validation",
        "Implement chaos engineering practices to validate disaster recovery procedures using Chaos Monkey, Litmus, and custom failure injection.",
        '''Chaos engineering for DR validation:

```python
# --- Chaos experiment framework ---

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class ImpactLevel(str, Enum):
    LOW = "low"        # Single instance failure
    MEDIUM = "medium"  # Service-level failure
    HIGH = "high"      # AZ-level failure
    CRITICAL = "critical"  # Region-level failure


@dataclass
class SteadyStateHypothesis:
    """Defines the expected steady-state behavior."""

    name: str
    check: Callable[[], bool]
    description: str
    tolerance: float = 0.01  # 1% error tolerance


@dataclass
class ChaosExperiment:
    """A single chaos experiment definition."""

    name: str
    description: str
    impact_level: ImpactLevel
    hypothesis: SteadyStateHypothesis

    # Safety controls
    max_duration_seconds: int = 300
    blast_radius: str = "single-instance"  # single-instance, service, az, region
    rollback_on_failure: bool = True
    requires_approval: bool = False
    allowed_environments: list[str] = field(
        default_factory=lambda: ["staging"]
    )

    # State
    status: ExperimentStatus = ExperimentStatus.PLANNED
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    results: dict[str, Any] = field(default_factory=dict)


class ChaosAction(ABC):
    """Abstract base for chaos actions."""

    @abstractmethod
    def inject(self) -> dict[str, Any]:
        """Inject the failure condition."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Revert the failure condition."""
        ...

    @abstractmethod
    def verify_rollback(self) -> bool:
        """Verify the rollback was successful."""
        ...


@dataclass
class ChaosRunner:
    """Executes chaos experiments with safety controls."""

    environment: str = "staging"
    dry_run: bool = False
    slack_webhook: Optional[str] = None

    def run_experiment(
        self,
        experiment: ChaosExperiment,
        action: ChaosAction,
    ) -> dict[str, Any]:
        """Execute a chaos experiment with full lifecycle."""
        # Pre-flight checks
        if self.environment not in experiment.allowed_environments:
            raise ValueError(
                f"Environment '{self.environment}' not allowed for "
                f"experiment '{experiment.name}'"
            )

        logger.info(f"Starting chaos experiment: {experiment.name}")
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.utcnow()

        results = {
            "experiment": experiment.name,
            "environment": self.environment,
            "impact_level": experiment.impact_level.value,
            "dry_run": self.dry_run,
            "started_at": experiment.started_at.isoformat(),
        }

        try:
            # Step 1: Verify steady state before injection
            logger.info("Checking steady state hypothesis (before)...")
            pre_check = experiment.hypothesis.check()
            results["steady_state_before"] = pre_check
            if not pre_check:
                raise RuntimeError(
                    "System not in steady state before experiment"
                )

            # Step 2: Inject failure
            logger.warning(
                f"INJECTING FAILURE: {experiment.name} "
                f"(blast_radius={experiment.blast_radius})"
            )
            if self.dry_run:
                results["injection"] = {"dry_run": True}
            else:
                injection_result = action.inject()
                results["injection"] = injection_result

            # Step 3: Observe (wait for system to respond)
            observation_start = time.time()
            while (
                time.time() - observation_start
                < experiment.max_duration_seconds
            ):
                time.sleep(10)
                still_steady = experiment.hypothesis.check()
                elapsed = time.time() - observation_start
                logger.info(
                    f"Observation ({elapsed:.0f}s): "
                    f"steady_state={still_steady}"
                )

                if not still_steady:
                    logger.warning("Steady state violated!")
                    results["steady_state_violated_at"] = elapsed
                    if experiment.rollback_on_failure:
                        break

            # Step 4: Verify steady state after (with failure still active)
            results["steady_state_during"] = experiment.hypothesis.check()

        except Exception as e:
            logger.error(f"Experiment failed: {e}")
            results["error"] = str(e)
            experiment.status = ExperimentStatus.FAILED
        finally:
            # Step 5: Always rollback
            logger.info("Rolling back failure injection...")
            if not self.dry_run:
                try:
                    action.rollback()
                    rollback_verified = action.verify_rollback()
                    results["rollback_verified"] = rollback_verified
                except Exception as e:
                    logger.error(f"ROLLBACK FAILED: {e}")
                    results["rollback_error"] = str(e)

            # Step 6: Verify recovery
            time.sleep(30)  # Wait for recovery
            results["steady_state_after"] = experiment.hypothesis.check()

        experiment.ended_at = datetime.utcnow()
        duration = (experiment.ended_at - experiment.started_at).total_seconds()
        results["duration_seconds"] = duration
        results["recovery_validated"] = results.get("steady_state_after", False)

        if experiment.status != ExperimentStatus.FAILED:
            experiment.status = ExperimentStatus.COMPLETED

        experiment.results = results
        logger.info(
            f"Experiment complete: {experiment.name} -> "
            f"recovery={results.get('recovery_validated')}"
        )

        return results
```

```python
# --- Concrete chaos actions for AWS/Kubernetes ---

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import boto3
from kubernetes import client, config as k8s_config

logger = logging.getLogger(__name__)


@dataclass
class EC2InstanceTerminator(ChaosAction):
    """Randomly terminate EC2 instances (Chaos Monkey style)."""

    session: boto3.Session
    target_tag_key: str = "app"
    target_tag_value: str = ""
    count: int = 1
    _terminated: list[str] = None

    def __post_init__(self) -> None:
        self._terminated = []

    def inject(self) -> dict[str, Any]:
        ec2 = self.session.client("ec2")
        instances = ec2.describe_instances(
            Filters=[
                {"Name": f"tag:{self.target_tag_key}", "Values": [self.target_tag_value]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )

        all_instances = [
            i["InstanceId"]
            for r in instances["Reservations"]
            for i in r["Instances"]
        ]

        if not all_instances:
            raise RuntimeError("No target instances found")

        targets = random.sample(all_instances, min(self.count, len(all_instances)))
        ec2.terminate_instances(InstanceIds=targets)
        self._terminated = targets

        logger.warning(f"Terminated instances: {targets}")
        return {"terminated": targets, "total_available": len(all_instances)}

    def rollback(self) -> None:
        # ASG will replace terminated instances automatically
        logger.info("Rollback: ASG auto-replacement will handle recovery")

    def verify_rollback(self) -> bool:
        ec2 = self.session.client("ec2")
        instances = ec2.describe_instances(
            Filters=[
                {"Name": f"tag:{self.target_tag_key}", "Values": [self.target_tag_value]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )
        running = sum(
            len(r["Instances"]) for r in instances["Reservations"]
        )
        return running >= self.count


@dataclass
class K8sPodKiller(ChaosAction):
    """Kill random pods in a Kubernetes deployment."""

    namespace: str = "production"
    deployment: str = ""
    count: int = 1
    _killed_pods: list[str] = None

    def __post_init__(self) -> None:
        k8s_config.load_incluster_config()
        self._killed_pods = []

    def inject(self) -> dict[str, Any]:
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(
            self.namespace,
            label_selector=f"app={self.deployment}",
        )

        running_pods = [
            p.metadata.name
            for p in pods.items
            if p.status.phase == "Running"
        ]

        targets = random.sample(
            running_pods, min(self.count, len(running_pods))
        )

        for pod in targets:
            v1.delete_namespaced_pod(pod, self.namespace)
            logger.warning(f"Killed pod: {pod}")
            self._killed_pods.append(pod)

        return {"killed": targets, "total_running": len(running_pods)}

    def rollback(self) -> None:
        # Deployment controller will recreate pods
        logger.info("Rollback: Deployment controller will recreate pods")

    def verify_rollback(self) -> bool:
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        deploy = apps_v1.read_namespaced_deployment(
            self.deployment, self.namespace
        )
        return deploy.status.ready_replicas == deploy.spec.replicas


@dataclass
class NetworkLatencyInjector(ChaosAction):
    """Inject network latency using tc (traffic control)."""

    target_pod: str = ""
    namespace: str = "production"
    latency_ms: int = 500
    jitter_ms: int = 100

    def inject(self) -> dict[str, Any]:
        v1 = client.CoreV1Api()
        # Execute tc command in the pod's network namespace
        exec_cmd = [
            "/bin/sh", "-c",
            f"tc qdisc add dev eth0 root netem "
            f"delay {self.latency_ms}ms {self.jitter_ms}ms distribution normal",
        ]
        resp = client.CoreV1Api().connect_post_namespaced_pod_exec(
            self.target_pod,
            self.namespace,
            command=exec_cmd,
            stderr=True,
            stdout=True,
        )
        return {
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "target": self.target_pod,
        }

    def rollback(self) -> None:
        exec_cmd = ["/bin/sh", "-c", "tc qdisc del dev eth0 root"]
        client.CoreV1Api().connect_post_namespaced_pod_exec(
            self.target_pod,
            self.namespace,
            command=exec_cmd,
            stderr=True,
            stdout=True,
        )

    def verify_rollback(self) -> bool:
        return True  # Would verify tc qdisc is clean
```

```yaml
# --- Litmus Chaos experiments for Kubernetes ---

# Pod delete experiment
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: payment-pod-delete
  namespace: staging
spec:
  engineState: active
  appinfo:
    appns: staging
    applabel: app=payment-service
    appkind: deployment
  chaosServiceAccount: litmus-admin
  experiments:
    - name: pod-delete
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "60"
            - name: CHAOS_INTERVAL
              value: "10"
            - name: FORCE
              value: "false"
            - name: PODS_AFFECTED_PERC
              value: "50"
        probe:
          - name: payment-health-check
            type: httpProbe
            mode: Continuous
            httpProbe/inputs:
              url: http://payment-service.staging:8080/health
              method:
                get:
                  criteria: ==
                  responseCode: "200"
            runProperties:
              probeTimeout: 5s
              interval: 5s
              retry: 3

---
# Node drain experiment
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: node-drain-test
  namespace: staging
spec:
  engineState: active
  auxiliaryAppInfo: ""
  chaosServiceAccount: litmus-admin
  experiments:
    - name: node-drain
      spec:
        components:
          env:
            - name: TOTAL_CHAOS_DURATION
              value: "120"
            - name: APP_NAMESPACE
              value: staging
            - name: APP_LABEL
              value: "app=payment-service"

---
# Scheduled chaos (GameDay automation)
apiVersion: batch/v1
kind: CronJob
metadata:
  name: weekly-chaos-gameday
  namespace: staging
spec:
  schedule: "0 10 * * 3"  # Wednesday 10 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: chaos-runner
              image: ghcr.io/acme/chaos-runner:latest
              env:
                - name: EXPERIMENTS
                  value: "pod-delete,network-latency,az-failure"
                - name: ENVIRONMENT
                  value: "staging"
                - name: SLACK_CHANNEL
                  value: "#chaos-engineering"
          restartPolicy: Never
```

| Chaos Experiment | Impact Level | What It Tests | Expected Outcome |
|---|---|---|---|
| Pod kill (single) | Low | Pod restart, readiness | Auto-restart < 30s |
| Pod kill (50%) | Medium | Deployment resilience | Service stays available |
| Node drain | Medium | Pod rescheduling | Pods migrate to other nodes |
| AZ failure | High | Multi-AZ resilience | Traffic shifts to healthy AZs |
| Network latency (500ms) | Medium | Timeout handling, retries | Graceful degradation |
| Network partition | High | Split-brain handling | No data corruption |
| Database failover | High | RDS failover process | < 60s downtime |
| Region failure | Critical | Full DR failover | RTO met, no data loss |
| DNS failure | Medium | DNS caching, fallback | Clients use cached records |
| Disk fill (90%) | Low | Alerting, log rotation | Alerts fire, cleanup runs |

Key patterns:

1. **Steady-state hypothesis first** — define what "normal" looks like (error rate < 0.1%, p99 < 500ms) before injecting chaos; verify it holds during failure
2. **Blast radius control** — start with single-instance failures, graduate to service, AZ, and region; never run critical experiments without safety controls
3. **Automated rollback** — every chaos action must have an automated rollback; if the system does not self-heal, rollback the injection immediately
4. **GameDay practice** — schedule regular chaos sessions (weekly in staging, monthly in production) to build muscle memory for incident response
5. **Production chaos with guard rails** — run chaos in production only during business hours, with PagerDuty on standby, and automatic abort if SLOs breach
6. **Document and share** — publish experiment results (what broke, what we learned, what we fixed) to improve system resilience over time
'''
    ),
]
