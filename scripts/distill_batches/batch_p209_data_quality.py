"""Data quality monitoring — Great Expectations, metrics, anomaly detection, data contracts."""

PAIRS = [
    (
        "data-engineering/great-expectations-suites-checkpoints",
        "Implement a comprehensive Great Expectations setup with expectation suites, checkpoints, data docs, and integration into CI/CD pipelines for automated data validation.",
        '''Great Expectations setup with suites, checkpoints, and CI/CD integration:

```python
# --- great_expectations/plugins/custom_expectations.py ---
"""Custom expectations for domain-specific data quality rules."""

from __future__ import annotations

from typing import Any, Dict, Optional

from great_expectations.core import ExpectationConfiguration
from great_expectations.execution_engine import (
    PandasExecutionEngine,
    SparkDFExecutionEngine,
    SqlAlchemyExecutionEngine,
)
from great_expectations.expectations.expectation import ColumnMapExpectation
from great_expectations.expectations.metrics import (
    ColumnMapMetricProvider,
    column_condition_partial,
)


class ColumnValuesMatchPhoneFormat(ColumnMapMetricProvider):
    """Metric: checks if values match E.164 phone format."""

    condition_metric_name = "column_values.match_phone_format"
    condition_value_keys = ("country_code",)

    @column_condition_partial(engine=PandasExecutionEngine)
    def _pandas(cls, column: Any, country_code: str = "US", **kwargs: Any) -> Any:
        import re

        patterns = {
            "US": r"^\+1[2-9]\d{9}$",
            "UK": r"^\+44[1-9]\d{9,10}$",
            "DE": r"^\+49[1-9]\d{6,12}$",
            "INTL": r"^\+[1-9]\d{6,14}$",
        }
        pattern = patterns.get(country_code, patterns["INTL"])
        return column.astype(str).str.match(pattern)

    @column_condition_partial(engine=SqlAlchemyExecutionEngine)
    def _sqlalchemy(cls, column: Any, country_code: str = "US", **kwargs: Any) -> Any:
        import sqlalchemy as sa

        if country_code == "US":
            return column.op("~")(r"^\+1[2-9]\d{9}$")
        return column.op("~")(r"^\+[1-9]\d{6,14}$")


class ExpectColumnValuesToMatchPhoneFormat(ColumnMapExpectation):
    """Expect column values to match E.164 phone number format."""

    map_metric = "column_values.match_phone_format"
    success_keys = ("mostly", "country_code")

    default_kwarg_values = {
        "mostly": 0.95,
        "country_code": "US",
    }

    library_metadata = {
        "maturity": "experimental",
        "tags": ["phone", "format", "validation"],
        "contributors": ["@data-quality-team"],
    }
```

```python
# --- data_quality/ge_suite_builder.py ---
"""Programmatic expectation suite construction with profiling."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import great_expectations as gx
from great_expectations.checkpoint import Checkpoint
from great_expectations.core import ExpectationSuite
from great_expectations.core.batch import BatchRequest
from great_expectations.data_context import FileDataContext
from great_expectations.profile.user_configurable_profiler import (
    UserConfigurableProfiler,
)

logger = logging.getLogger(__name__)


@dataclass
class SuiteConfig:
    """Configuration for an expectation suite."""

    suite_name: str
    datasource_name: str
    data_asset_name: str
    table_name: str
    schema_name: str = "public"
    expectations: List[Dict[str, Any]] = field(default_factory=list)
    profiling_enabled: bool = False
    profiling_columns: Optional[List[str]] = None


class GESuiteManager:
    """Manages Great Expectations suites, checkpoints, and validation."""

    def __init__(self, context_root: str = "great_expectations") -> None:
        self.context = FileDataContext(context_root_dir=context_root)
        self._suites_cache: Dict[str, ExpectationSuite] = {}

    def create_suite_from_config(self, config: SuiteConfig) -> ExpectationSuite:
        """Build expectation suite from typed configuration."""
        suite = self.context.add_or_update_expectation_suite(
            expectation_suite_name=config.suite_name
        )

        if config.profiling_enabled:
            suite = self._profile_and_merge(config, suite)

        for exp_config in config.expectations:
            expectation_type = exp_config.pop("expectation_type")
            suite.add_expectation(
                gx.core.ExpectationConfiguration(
                    expectation_type=expectation_type,
                    kwargs=exp_config.get("kwargs", {}),
                    meta=exp_config.get("meta", {}),
                )
            )

        self.context.update_expectation_suite(suite)
        self._suites_cache[config.suite_name] = suite
        logger.info(
            "Suite '%s' created with %d expectations",
            config.suite_name,
            len(suite.expectations),
        )
        return suite

    def _profile_and_merge(
        self, config: SuiteConfig, suite: ExpectationSuite
    ) -> ExpectationSuite:
        """Auto-profile data and merge with manual expectations."""
        batch_request = BatchRequest(
            datasource_name=config.datasource_name,
            data_asset_name=config.data_asset_name,
        )
        profiler = UserConfigurableProfiler(
            profile_dataset=self.context.get_validator(
                batch_request=batch_request,
                expectation_suite_name=config.suite_name,
            ),
            excluded_expectations=[
                "expect_column_values_to_be_in_type_list",
            ],
            ignored_columns=["_metadata", "_loaded_at"],
            primary_or_compound_key=None,
        )
        profiled_suite = profiler.build_suite()
        for exp in profiled_suite.expectations:
            suite.add_expectation(exp)
        return suite

    def create_checkpoint(
        self,
        checkpoint_name: str,
        suite_name: str,
        datasource_name: str,
        data_asset_name: str,
        slack_webhook: Optional[str] = None,
        notify_on: str = "failure",
    ) -> Checkpoint:
        """Create a checkpoint with optional Slack alerting."""
        action_list = [
            {
                "name": "store_validation_result",
                "action": {
                    "class_name": "StoreValidationResultAction",
                },
            },
            {
                "name": "update_data_docs",
                "action": {
                    "class_name": "UpdateDataDocsAction",
                },
            },
        ]

        if slack_webhook:
            action_list.append(
                {
                    "name": "send_slack_notification",
                    "action": {
                        "class_name": "SlackNotificationAction",
                        "slack_webhook": slack_webhook,
                        "notify_on": notify_on,
                        "renderer": {
                            "module_name": "great_expectations.render.renderer.slack_renderer",
                            "class_name": "SlackRenderer",
                        },
                    },
                }
            )

        checkpoint = Checkpoint(
            name=checkpoint_name,
            data_context=self.context,
            config_version=1,
            run_name_template=f"%Y%m%d-%H%M%S-{checkpoint_name}",
            validations=[
                {
                    "batch_request": {
                        "datasource_name": datasource_name,
                        "data_asset_name": data_asset_name,
                    },
                    "expectation_suite_name": suite_name,
                },
            ],
            action_list=action_list,
        )
        self.context.add_or_update_checkpoint(checkpoint=checkpoint)
        return checkpoint

    def run_checkpoint(
        self, checkpoint_name: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Execute checkpoint and return (success, results_summary)."""
        result = self.context.run_checkpoint(
            checkpoint_name=checkpoint_name
        )

        summary = {
            "success": result.success,
            "run_id": str(result.run_id),
            "statistics": {},
        }

        for validation_key, validation_result in result.run_results.items():
            stats = validation_result["validation_result"].statistics
            summary["statistics"][str(validation_key)] = {
                "evaluated_expectations": stats["evaluated_expectations"],
                "successful_expectations": stats["successful_expectations"],
                "unsuccessful_expectations": stats["unsuccessful_expectations"],
                "success_percent": stats["success_percent"],
            }

        return result.success, summary

    def build_data_docs(self, site_names: Optional[List[str]] = None) -> Dict[str, str]:
        """Build data docs and return site URLs."""
        urls = self.context.build_data_docs(site_names=site_names)
        return {name: url for name, url in urls.items()}
```

```python
# --- ci_cd/ge_pipeline_runner.py ---
"""CI/CD integration for Great Expectations validation."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from data_quality.ge_suite_builder import GESuiteManager, SuiteConfig


@dataclass
class PipelineValidation:
    """Result of a CI/CD pipeline data validation run."""

    checkpoint_name: str
    success: bool
    summary: Dict[str, Any]
    data_docs_url: Optional[str] = None


def build_orders_suite() -> SuiteConfig:
    """Define the orders table expectation suite."""
    return SuiteConfig(
        suite_name="orders_quality_suite",
        datasource_name="warehouse_postgres",
        data_asset_name="public.orders",
        table_name="orders",
        expectations=[
            {
                "expectation_type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1000, "max_value": 10_000_000},
            },
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "order_id"},
            },
            {
                "expectation_type": "expect_column_values_to_be_unique",
                "kwargs": {"column": "order_id"},
            },
            {
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "customer_id"},
            },
            {
                "expectation_type": "expect_column_values_to_be_between",
                "kwargs": {
                    "column": "total_amount",
                    "min_value": 0.01,
                    "max_value": 1_000_000,
                },
            },
            {
                "expectation_type": "expect_column_values_to_be_in_set",
                "kwargs": {
                    "column": "status",
                    "value_set": [
                        "pending", "confirmed", "processing",
                        "shipped", "delivered", "cancelled", "refunded",
                    ],
                },
            },
            {
                "expectation_type": "expect_column_values_to_match_strftime_format",
                "kwargs": {
                    "column": "created_at",
                    "strftime_format": "%Y-%m-%d %H:%M:%S",
                },
                "meta": {"notes": "ISO timestamp format enforcement"},
            },
            {
                "expectation_type": "expect_column_pair_values_a_to_be_greater_than_b",
                "kwargs": {
                    "column_A": "updated_at",
                    "column_B": "created_at",
                    "or_equal": True,
                },
            },
        ],
    )


def run_pipeline_validation(
    ge_root: str = "great_expectations",
    slack_webhook: Optional[str] = None,
) -> PipelineValidation:
    """Run full validation pipeline for CI/CD."""
    manager = GESuiteManager(context_root=ge_root)

    # Build suite
    suite_config = build_orders_suite()
    manager.create_suite_from_config(suite_config)

    # Create checkpoint
    checkpoint_name = "orders_ci_checkpoint"
    manager.create_checkpoint(
        checkpoint_name=checkpoint_name,
        suite_name=suite_config.suite_name,
        datasource_name=suite_config.datasource_name,
        data_asset_name=suite_config.data_asset_name,
        slack_webhook=slack_webhook,
    )

    # Execute
    success, summary = manager.run_checkpoint(checkpoint_name)

    # Build docs
    docs_urls = manager.build_data_docs()
    primary_url = next(iter(docs_urls.values()), None)

    return PipelineValidation(
        checkpoint_name=checkpoint_name,
        success=success,
        summary=summary,
        data_docs_url=primary_url,
    )


def main() -> int:
    """Entry point for CI/CD pipeline."""
    slack_url = os.environ.get("GE_SLACK_WEBHOOK")
    ge_root = os.environ.get("GE_ROOT_DIR", "great_expectations")

    result = run_pipeline_validation(
        ge_root=ge_root,
        slack_webhook=slack_url,
    )

    print(json.dumps(result.summary, indent=2))

    if not result.success:
        print(f"VALIDATION FAILED — Data docs: {result.data_docs_url}")
        return 1

    print(f"VALIDATION PASSED — Data docs: {result.data_docs_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

| Feature | Great Expectations | Soda Core | dbt Tests | Deequ |
|---|---|---|---|---|
| Language | Python | Python/YAML | SQL/Jinja | Scala/Java |
| Execution Engine | Pandas/Spark/SQL | SQL-native | In-warehouse | Spark |
| Data Docs | Built-in HTML | Soda Cloud | dbt docs | External |
| Custom Expectations | Python classes | SodaCL metrics | Custom SQL | Analyzers |
| CI/CD Integration | Checkpoint CLI | soda scan CLI | dbt test | Spark job |
| Profiling | Auto-profiler | Auto-discover | Not built-in | ConstraintSuggestion |
| Alerting | Slack/PagerDuty/email | Slack/webhook | Webhooks | Custom |

**Key patterns:**

1. **Suite composition** -- combine auto-profiled expectations with manually defined business rules for complete coverage
2. **Checkpoint orchestration** -- wrap validation + alerting + data docs updates in a single atomic checkpoint
3. **CI/CD gating** -- fail the pipeline with non-zero exit codes when validation thresholds are not met
4. **Custom expectations** -- extend the framework with domain-specific checks (phone format, address, etc.)
5. **Data docs** -- auto-generate browsable HTML documentation of all validations and their results
6. **Profiling-first approach** -- bootstrap initial expectations from data profiling, then refine manually
7. **Action lists** -- chain post-validation actions (store, notify, update docs) for observability'''
    ),

    (
        "data-engineering/data-quality-metrics-completeness-accuracy",
        "Build a data quality metrics framework that tracks completeness, accuracy, freshness, consistency, and uniqueness with historical trending and SLA alerting.",
        '''Data quality metrics framework with trending and SLA alerting:

```python
# --- data_quality/metrics_engine.py ---
"""Data quality metrics computation engine."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DQDimension(str, Enum):
    """Data quality measurement dimensions."""

    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    FRESHNESS = "freshness"
    CONSISTENCY = "consistency"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    TIMELINESS = "timeliness"


@dataclass
class MetricResult:
    """Result of a single data quality metric computation."""

    metric_name: str
    dimension: DQDimension
    table_name: str
    column_name: Optional[str]
    value: float
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    passed: bool = True
    measured_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def metric_id(self) -> str:
        key = f"{self.table_name}.{self.column_name or '*'}.{self.metric_name}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def check_thresholds(self) -> bool:
        """Evaluate value against configured thresholds."""
        if self.threshold_min is not None and self.value < self.threshold_min:
            self.passed = False
        if self.threshold_max is not None and self.value > self.threshold_max:
            self.passed = False
        return self.passed


@dataclass
class MetricSpec:
    """Specification for a metric to compute."""

    metric_name: str
    dimension: DQDimension
    table_name: str
    column_name: Optional[str] = None
    sql_template: Optional[str] = None
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)


class MetricComputer(ABC):
    """Base class for metric computation."""

    @abstractmethod
    def compute(
        self, engine: Engine, spec: MetricSpec
    ) -> MetricResult:
        """Compute a single metric value."""
        ...


class CompletenessComputer(MetricComputer):
    """Measures percentage of non-null values in a column."""

    def compute(self, engine: Engine, spec: MetricSpec) -> MetricResult:
        query = text(f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT({spec.column_name}) AS non_null_rows,
                ROUND(
                    COUNT({spec.column_name})::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2
                ) AS completeness_pct
            FROM {spec.table_name}
        """)
        with engine.connect() as conn:
            row = conn.execute(query).fetchone()

        value = float(row.completeness_pct) if row.completeness_pct else 0.0
        result = MetricResult(
            metric_name="completeness",
            dimension=DQDimension.COMPLETENESS,
            table_name=spec.table_name,
            column_name=spec.column_name,
            value=value,
            threshold_min=spec.threshold_min,
            threshold_max=spec.threshold_max,
            metadata={
                "total_rows": row.total_rows,
                "non_null_rows": row.non_null_rows,
            },
        )
        result.check_thresholds()
        return result


class FreshnessComputer(MetricComputer):
    """Measures data freshness as hours since last update."""

    def compute(self, engine: Engine, spec: MetricSpec) -> MetricResult:
        timestamp_col = spec.column_name or "updated_at"
        query = text(f"""
            SELECT
                MAX({timestamp_col}) AS latest_ts,
                EXTRACT(EPOCH FROM (NOW() - MAX({timestamp_col}))) / 3600.0
                    AS hours_since_update
            FROM {spec.table_name}
        """)
        with engine.connect() as conn:
            row = conn.execute(query).fetchone()

        hours = float(row.hours_since_update) if row.hours_since_update else float("inf")
        result = MetricResult(
            metric_name="freshness_hours",
            dimension=DQDimension.FRESHNESS,
            table_name=spec.table_name,
            column_name=timestamp_col,
            value=round(hours, 2),
            threshold_max=spec.threshold_max,
            metadata={"latest_timestamp": str(row.latest_ts)},
        )
        result.check_thresholds()
        return result


class UniquenessComputer(MetricComputer):
    """Measures percentage of unique values in a column."""

    def compute(self, engine: Engine, spec: MetricSpec) -> MetricResult:
        query = text(f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT {spec.column_name}) AS distinct_values,
                ROUND(
                    COUNT(DISTINCT {spec.column_name})::NUMERIC
                    / NULLIF(COUNT(*), 0) * 100, 2
                ) AS uniqueness_pct
            FROM {spec.table_name}
        """)
        with engine.connect() as conn:
            row = conn.execute(query).fetchone()

        value = float(row.uniqueness_pct) if row.uniqueness_pct else 0.0
        result = MetricResult(
            metric_name="uniqueness",
            dimension=DQDimension.UNIQUENESS,
            table_name=spec.table_name,
            column_name=spec.column_name,
            value=value,
            threshold_min=spec.threshold_min,
            metadata={
                "total_rows": row.total_rows,
                "distinct_values": row.distinct_values,
            },
        )
        result.check_thresholds()
        return result


class ConsistencyComputer(MetricComputer):
    """Measures cross-table referential consistency."""

    def compute(self, engine: Engine, spec: MetricSpec) -> MetricResult:
        ref_table = spec.params["reference_table"]
        ref_column = spec.params["reference_column"]
        query = text(f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (
                    WHERE {spec.column_name} NOT IN (
                        SELECT {ref_column} FROM {ref_table}
                    )
                ) AS orphan_rows,
                ROUND(
                    (1 - COUNT(*) FILTER (
                        WHERE {spec.column_name} NOT IN (
                            SELECT {ref_column} FROM {ref_table}
                        )
                    )::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2
                ) AS consistency_pct
            FROM {spec.table_name}
        """)
        with engine.connect() as conn:
            row = conn.execute(query).fetchone()

        value = float(row.consistency_pct) if row.consistency_pct else 0.0
        result = MetricResult(
            metric_name="referential_consistency",
            dimension=DQDimension.CONSISTENCY,
            table_name=spec.table_name,
            column_name=spec.column_name,
            value=value,
            threshold_min=spec.threshold_min,
            metadata={
                "reference": f"{ref_table}.{ref_column}",
                "orphan_rows": row.orphan_rows,
            },
        )
        result.check_thresholds()
        return result


class CustomSQLComputer(MetricComputer):
    """Executes arbitrary SQL for custom accuracy checks."""

    def compute(self, engine: Engine, spec: MetricSpec) -> MetricResult:
        if not spec.sql_template:
            raise ValueError("sql_template required for custom SQL metric")

        query = text(spec.sql_template)
        with engine.connect() as conn:
            row = conn.execute(query, spec.params).fetchone()

        value = float(row[0])
        result = MetricResult(
            metric_name=spec.metric_name,
            dimension=spec.dimension,
            table_name=spec.table_name,
            column_name=spec.column_name,
            value=value,
            threshold_min=spec.threshold_min,
            threshold_max=spec.threshold_max,
        )
        result.check_thresholds()
        return result


# --- Computer registry ---
COMPUTERS: Dict[str, type[MetricComputer]] = {
    "completeness": CompletenessComputer,
    "freshness": FreshnessComputer,
    "uniqueness": UniquenessComputer,
    "consistency": ConsistencyComputer,
    "custom_sql": CustomSQLComputer,
}
```

```python
# --- data_quality/metrics_store.py ---
"""Historical metric storage and SLA evaluation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    Column, DateTime, Float, Integer, String, Text, Boolean,
    create_engine, Index,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from data_quality.metrics_engine import DQDimension, MetricResult

logger = logging.getLogger(__name__)
Base = declarative_base()


class MetricHistory(Base):
    """Stores historical metric measurements."""

    __tablename__ = "dq_metric_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_id = Column(String(16), nullable=False, index=True)
    metric_name = Column(String(128), nullable=False)
    dimension = Column(String(32), nullable=False)
    table_name = Column(String(256), nullable=False)
    column_name = Column(String(256), nullable=True)
    value = Column(Float, nullable=False)
    threshold_min = Column(Float, nullable=True)
    threshold_max = Column(Float, nullable=True)
    passed = Column(Boolean, nullable=False, default=True)
    metadata_json = Column(Text, nullable=True)
    measured_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_metric_time", "metric_id", "measured_at"),
    )


class SLARule:
    """SLA evaluation rule for data quality metrics."""

    def __init__(
        self,
        metric_name: str,
        table_name: str,
        column_name: Optional[str],
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        lookback_hours: int = 24,
        min_consecutive_failures: int = 3,
        severity: str = "critical",
    ) -> None:
        self.metric_name = metric_name
        self.table_name = table_name
        self.column_name = column_name
        self.min_value = min_value
        self.max_value = max_value
        self.lookback_hours = lookback_hours
        self.min_consecutive_failures = min_consecutive_failures
        self.severity = severity


class MetricStore:
    """Persists metrics and evaluates SLA compliance."""

    def __init__(self, connection_string: str) -> None:
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(bind=self.engine)

    def store_results(self, results: List[MetricResult]) -> int:
        """Persist a batch of metric results, returns count stored."""
        session = self._session_factory()
        try:
            records = [
                MetricHistory(
                    metric_id=r.metric_id,
                    metric_name=r.metric_name,
                    dimension=r.dimension.value,
                    table_name=r.table_name,
                    column_name=r.column_name,
                    value=r.value,
                    threshold_min=r.threshold_min,
                    threshold_max=r.threshold_max,
                    passed=r.passed,
                    metadata_json=json.dumps(r.metadata),
                    measured_at=r.measured_at,
                )
                for r in results
            ]
            session.add_all(records)
            session.commit()
            return len(records)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_trend(
        self,
        metric_id: str,
        hours: int = 168,
    ) -> List[Dict[str, Any]]:
        """Get metric trend over the last N hours."""
        session = self._session_factory()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            rows = (
                session.query(MetricHistory)
                .filter(
                    MetricHistory.metric_id == metric_id,
                    MetricHistory.measured_at >= cutoff,
                )
                .order_by(MetricHistory.measured_at.asc())
                .all()
            )
            return [
                {
                    "value": r.value,
                    "passed": r.passed,
                    "measured_at": r.measured_at.isoformat(),
                }
                for r in rows
            ]
        finally:
            session.close()

    def evaluate_slas(
        self, rules: List[SLARule]
    ) -> List[Dict[str, Any]]:
        """Evaluate SLA rules against recent metric history."""
        violations: List[Dict[str, Any]] = []
        session = self._session_factory()

        try:
            for rule in rules:
                cutoff = datetime.utcnow() - timedelta(
                    hours=rule.lookback_hours
                )
                query = (
                    session.query(MetricHistory)
                    .filter(
                        MetricHistory.metric_name == rule.metric_name,
                        MetricHistory.table_name == rule.table_name,
                        MetricHistory.measured_at >= cutoff,
                    )
                    .order_by(MetricHistory.measured_at.desc())
                )
                if rule.column_name:
                    query = query.filter(
                        MetricHistory.column_name == rule.column_name
                    )

                recent = query.limit(rule.min_consecutive_failures).all()

                if len(recent) < rule.min_consecutive_failures:
                    continue

                all_failed = all(not r.passed for r in recent)
                if all_failed:
                    violations.append(
                        {
                            "rule": rule.metric_name,
                            "table": rule.table_name,
                            "column": rule.column_name,
                            "severity": rule.severity,
                            "consecutive_failures": len(recent),
                            "latest_value": recent[0].value,
                            "threshold_min": rule.min_value,
                            "threshold_max": rule.max_value,
                        }
                    )
        finally:
            session.close()

        return violations
```

```python
# --- data_quality/metrics_scheduler.py ---
"""Orchestrates periodic metric collection and SLA evaluation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import create_engine

from data_quality.metrics_engine import (
    COMPUTERS,
    DQDimension,
    MetricResult,
    MetricSpec,
)
from data_quality.metrics_store import MetricStore, SLARule

logger = logging.getLogger(__name__)


def run_metrics_collection(
    warehouse_url: str,
    metrics_db_url: str,
    specs: List[MetricSpec],
    sla_rules: List[SLARule],
) -> Dict[str, Any]:
    """Execute metrics collection cycle."""
    engine = create_engine(warehouse_url)
    store = MetricStore(metrics_db_url)

    results: List[MetricResult] = []
    errors: List[Dict[str, str]] = []

    for spec in specs:
        computer_cls = COMPUTERS.get(spec.metric_name)
        if not computer_cls:
            computer_cls = COMPUTERS.get("custom_sql")
        try:
            computer = computer_cls()
            result = computer.compute(engine, spec)
            results.append(result)
        except Exception as exc:
            errors.append({
                "metric": spec.metric_name,
                "table": spec.table_name,
                "error": str(exc),
            })
            logger.exception("Failed computing %s", spec.metric_name)

    stored_count = store.store_results(results) if results else 0
    violations = store.evaluate_slas(sla_rules) if sla_rules else []

    summary = {
        "total_metrics": len(specs),
        "computed": len(results),
        "errors": len(errors),
        "stored": stored_count,
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "sla_violations": violations,
        "error_details": errors,
    }

    if violations:
        logger.warning("SLA violations detected: %s", violations)

    return summary
```

| Dimension | What It Measures | Typical Threshold | SQL Pattern |
|---|---|---|---|
| Completeness | % non-null values | >= 99.5% | COUNT(col) / COUNT(*) |
| Accuracy | % values matching reference | >= 99.0% | JOIN + compare |
| Freshness | Hours since last update | <= 4 hours | NOW() - MAX(ts) |
| Consistency | % matching cross-table refs | >= 99.9% | LEFT JOIN IS NULL |
| Uniqueness | % distinct values | = 100% for PKs | COUNT(DISTINCT) / COUNT |
| Validity | % matching format rules | >= 99.0% | REGEXP / CHECK |
| Timeliness | % records arriving on time | >= 95.0% | ts < deadline |

**Key patterns:**

1. **Dimension-based architecture** -- organize metrics by DQ dimensions (completeness, accuracy, freshness) for systematic coverage
2. **Threshold-driven alerting** -- attach min/max thresholds to every metric and auto-evaluate pass/fail
3. **Historical trending** -- store every measurement with timestamps for trend analysis and regression detection
4. **SLA rules with consecutive failures** -- only alert after N consecutive threshold breaches to reduce noise
5. **Pluggable computers** -- register metric computation strategies by name for extensibility
6. **Metric identity hashing** -- generate stable metric IDs for deduplication and time-series lookups
7. **Batch collection cycles** -- run all metrics in a single orchestrated sweep for efficiency and atomic reporting'''
    ),

    (
        "data-engineering/anomaly-detection-data-pipelines",
        "Implement anomaly detection for data pipelines that catches volume spikes, schema drift, distribution shifts, and late-arriving data using statistical methods.",
        '''Anomaly detection for data pipelines with statistical methods:

```python
# --- data_quality/anomaly_detector.py ---
"""Statistical anomaly detection for data pipeline monitoring."""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class AnomalyType(str, Enum):
    """Types of data anomalies detected."""

    VOLUME_SPIKE = "volume_spike"
    VOLUME_DROP = "volume_drop"
    SCHEMA_DRIFT = "schema_drift"
    DISTRIBUTION_SHIFT = "distribution_shift"
    LATE_ARRIVING = "late_arriving"
    NULL_SPIKE = "null_spike"
    CARDINALITY_CHANGE = "cardinality_change"


class Severity(str, Enum):
    """Anomaly severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    """Detected anomaly in a data pipeline."""

    anomaly_type: AnomalyType
    severity: Severity
    table_name: str
    column_name: Optional[str]
    description: str
    current_value: float
    expected_range: Tuple[float, float]
    z_score: Optional[float] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoricalBaseline:
    """Statistical baseline computed from historical data."""

    mean: float
    std: float
    median: float
    p5: float
    p95: float
    sample_size: int
    computed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def z_threshold(self) -> float:
        """Dynamic Z-score threshold based on sample size."""
        if self.sample_size < 7:
            return 4.0  # very lenient with limited history
        elif self.sample_size < 30:
            return 3.5
        else:
            return 3.0

    def is_anomalous(self, value: float) -> Tuple[bool, float]:
        """Check if value is anomalous, return (is_anomaly, z_score)."""
        if self.std == 0:
            z = 0.0 if value == self.mean else float("inf")
        else:
            z = abs(value - self.mean) / self.std
        return z > self.z_threshold, z


class BaseDetector(ABC):
    """Base class for anomaly detectors."""

    def __init__(self, engine: Engine, lookback_days: int = 30) -> None:
        self.engine = engine
        self.lookback_days = lookback_days

    @abstractmethod
    def detect(self, table_name: str, **kwargs: Any) -> List[Anomaly]:
        ...

    def _get_baseline(self, values: Sequence[float]) -> HistoricalBaseline:
        """Compute statistical baseline from historical values."""
        arr = np.array(values, dtype=np.float64)
        return HistoricalBaseline(
            mean=float(np.mean(arr)),
            std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            median=float(np.median(arr)),
            p5=float(np.percentile(arr, 5)),
            p95=float(np.percentile(arr, 95)),
            sample_size=len(arr),
        )


class VolumeAnomalyDetector(BaseDetector):
    """Detects anomalous row count changes."""

    def detect(self, table_name: str, **kwargs: Any) -> List[Anomaly]:
        anomalies: List[Anomaly] = []

        # Get historical daily row counts from audit table
        query = text("""
            SELECT
                DATE(measured_at) AS measure_date,
                value AS row_count
            FROM dq_metric_history
            WHERE table_name = :table
              AND metric_name = 'row_count'
              AND measured_at >= NOW() - INTERVAL ':days days'
            ORDER BY measured_at ASC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(
                query,
                {"table": table_name, "days": self.lookback_days},
            ).fetchall()

        if len(rows) < 3:
            logger.warning("Insufficient history for %s", table_name)
            return anomalies

        historical = [float(r.row_count) for r in rows[:-1]]
        current = float(rows[-1].row_count)
        baseline = self._get_baseline(historical)
        is_anomalous, z_score = baseline.is_anomalous(current)

        if is_anomalous:
            anomaly_type = (
                AnomalyType.VOLUME_SPIKE
                if current > baseline.mean
                else AnomalyType.VOLUME_DROP
            )
            severity = (
                Severity.CRITICAL if abs(z_score) > 5
                else Severity.WARNING
            )
            anomalies.append(
                Anomaly(
                    anomaly_type=anomaly_type,
                    severity=severity,
                    table_name=table_name,
                    column_name=None,
                    description=(
                        f"Row count {anomaly_type.value}: {current:,.0f} rows "
                        f"(expected {baseline.p5:,.0f}-{baseline.p95:,.0f})"
                    ),
                    current_value=current,
                    expected_range=(baseline.p5, baseline.p95),
                    z_score=z_score,
                    metadata={
                        "mean": baseline.mean,
                        "std": baseline.std,
                        "sample_size": baseline.sample_size,
                    },
                )
            )
        return anomalies


class SchemaDriftDetector(BaseDetector):
    """Detects schema changes between pipeline runs."""

    def detect(self, table_name: str, **kwargs: Any) -> List[Anomaly]:
        anomalies: List[Anomaly] = []

        schema_name, tbl = (
            table_name.split(".", 1)
            if "." in table_name
            else ("public", table_name)
        )

        # Get current schema from information_schema
        query = text("""
            SELECT column_name, data_type, is_nullable,
                   character_maximum_length, numeric_precision
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
        """)
        with self.engine.connect() as conn:
            current_cols = conn.execute(
                query, {"schema": schema_name, "table": tbl}
            ).fetchall()

        # Get last known schema snapshot from registry
        snapshot_query = text("""
            SELECT column_name, data_type, is_nullable
            FROM dq_schema_snapshots
            WHERE table_name = :full_table
            ORDER BY snapshot_at DESC
            LIMIT 100
        """)
        with self.engine.connect() as conn:
            prev_cols = conn.execute(
                snapshot_query, {"full_table": table_name}
            ).fetchall()

        if not prev_cols:
            return anomalies

        current_names = {c.column_name for c in current_cols}
        prev_names = {c.column_name for c in prev_cols}

        added = current_names - prev_names
        removed = prev_names - current_names

        if added:
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.SCHEMA_DRIFT,
                    severity=Severity.WARNING,
                    table_name=table_name,
                    column_name=None,
                    description=f"New columns added: {sorted(added)}",
                    current_value=len(current_names),
                    expected_range=(len(prev_names), len(prev_names)),
                    metadata={"added_columns": sorted(added)},
                )
            )

        if removed:
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.SCHEMA_DRIFT,
                    severity=Severity.CRITICAL,
                    table_name=table_name,
                    column_name=None,
                    description=f"Columns removed: {sorted(removed)}",
                    current_value=len(current_names),
                    expected_range=(len(prev_names), len(prev_names)),
                    metadata={"removed_columns": sorted(removed)},
                )
            )

        # Check type changes
        current_types = {c.column_name: c.data_type for c in current_cols}
        prev_types = {c.column_name: c.data_type for c in prev_cols}

        for col in current_names & prev_names:
            if current_types.get(col) != prev_types.get(col):
                anomalies.append(
                    Anomaly(
                        anomaly_type=AnomalyType.SCHEMA_DRIFT,
                        severity=Severity.CRITICAL,
                        table_name=table_name,
                        column_name=col,
                        description=(
                            f"Type changed: {prev_types[col]} -> "
                            f"{current_types[col]}"
                        ),
                        current_value=0,
                        expected_range=(0, 0),
                        metadata={
                            "old_type": prev_types[col],
                            "new_type": current_types[col],
                        },
                    )
                )

        return anomalies


class DistributionShiftDetector(BaseDetector):
    """Detects distribution shifts using KS test and KL divergence."""

    def detect(
        self,
        table_name: str,
        column_name: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        if not column_name:
            return anomalies

        # Get current and historical value samples
        current_query = text(f"""
            SELECT {column_name}::FLOAT AS val
            FROM {table_name}
            WHERE {column_name} IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 10000
        """)
        historical_query = text(f"""
            SELECT {column_name}::FLOAT AS val
            FROM {table_name}_history
            WHERE {column_name} IS NOT NULL
              AND snapshot_date >= CURRENT_DATE - INTERVAL '{self.lookback_days} days'
              AND snapshot_date < CURRENT_DATE
            ORDER BY RANDOM()
            LIMIT 10000
        """)

        with self.engine.connect() as conn:
            current_data = [r.val for r in conn.execute(current_query).fetchall()]
            hist_data = [r.val for r in conn.execute(historical_query).fetchall()]

        if len(current_data) < 100 or len(hist_data) < 100:
            return anomalies

        current_arr = np.array(current_data)
        hist_arr = np.array(hist_data)

        # Two-sample Kolmogorov-Smirnov test
        ks_stat, ks_pvalue = stats.ks_2samp(hist_arr, current_arr)

        if ks_pvalue < 0.001:  # highly significant shift
            severity = (
                Severity.CRITICAL if ks_stat > 0.3
                else Severity.WARNING
            )
            anomalies.append(
                Anomaly(
                    anomaly_type=AnomalyType.DISTRIBUTION_SHIFT,
                    severity=severity,
                    table_name=table_name,
                    column_name=column_name,
                    description=(
                        f"Distribution shift detected (KS stat={ks_stat:.4f}, "
                        f"p={ks_pvalue:.2e})"
                    ),
                    current_value=ks_stat,
                    expected_range=(0.0, 0.1),
                    metadata={
                        "ks_statistic": ks_stat,
                        "ks_pvalue": ks_pvalue,
                        "current_mean": float(np.mean(current_arr)),
                        "historical_mean": float(np.mean(hist_arr)),
                        "current_std": float(np.std(current_arr)),
                        "historical_std": float(np.std(hist_arr)),
                    },
                )
            )

        return anomalies
```

```python
# --- data_quality/anomaly_orchestrator.py ---
"""Orchestrates anomaly detection across pipeline tables."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine

from data_quality.anomaly_detector import (
    Anomaly,
    AnomalyType,
    DistributionShiftDetector,
    SchemaDriftDetector,
    Severity,
    VolumeAnomalyDetector,
)

logger = logging.getLogger(__name__)


@dataclass
class TableMonitorConfig:
    """Monitoring configuration for a single table."""

    table_name: str
    check_volume: bool = True
    check_schema: bool = True
    check_distribution: bool = False
    distribution_columns: Optional[List[str]] = None
    lookback_days: int = 30


@dataclass
class AnomalyReport:
    """Summary of anomaly detection run."""

    total_checks: int
    total_anomalies: int
    critical_count: int
    warning_count: int
    anomalies: List[Dict[str, Any]]
    generated_at: datetime


class AnomalyOrchestrator:
    """Runs anomaly detection across monitored tables."""

    def __init__(
        self,
        warehouse_url: str,
        configs: List[TableMonitorConfig],
    ) -> None:
        self.engine = create_engine(warehouse_url)
        self.configs = configs

    def run_detection(self) -> AnomalyReport:
        """Execute all configured anomaly detectors."""
        all_anomalies: List[Anomaly] = []
        total_checks = 0

        for config in self.configs:
            if config.check_volume:
                total_checks += 1
                detector = VolumeAnomalyDetector(
                    self.engine, config.lookback_days
                )
                all_anomalies.extend(
                    detector.detect(config.table_name)
                )

            if config.check_schema:
                total_checks += 1
                detector = SchemaDriftDetector(
                    self.engine, config.lookback_days
                )
                all_anomalies.extend(
                    detector.detect(config.table_name)
                )

            if config.check_distribution and config.distribution_columns:
                dist_detector = DistributionShiftDetector(
                    self.engine, config.lookback_days
                )
                for col in config.distribution_columns:
                    total_checks += 1
                    all_anomalies.extend(
                        dist_detector.detect(
                            config.table_name, column_name=col
                        )
                    )

        critical_count = sum(
            1 for a in all_anomalies if a.severity == Severity.CRITICAL
        )
        warning_count = sum(
            1 for a in all_anomalies if a.severity == Severity.WARNING
        )

        return AnomalyReport(
            total_checks=total_checks,
            total_anomalies=len(all_anomalies),
            critical_count=critical_count,
            warning_count=warning_count,
            anomalies=[
                {
                    "type": a.anomaly_type.value,
                    "severity": a.severity.value,
                    "table": a.table_name,
                    "column": a.column_name,
                    "description": a.description,
                    "current_value": a.current_value,
                    "expected_range": list(a.expected_range),
                    "z_score": a.z_score,
                    "metadata": a.metadata,
                }
                for a in all_anomalies
            ],
            generated_at=datetime.utcnow(),
        )


# --- Example usage ---
def monitor_warehouse() -> AnomalyReport:
    """Run anomaly detection on warehouse tables."""
    configs = [
        TableMonitorConfig(
            table_name="public.orders",
            check_volume=True,
            check_schema=True,
            check_distribution=True,
            distribution_columns=["total_amount", "discount_pct"],
        ),
        TableMonitorConfig(
            table_name="public.customers",
            check_volume=True,
            check_schema=True,
        ),
        TableMonitorConfig(
            table_name="public.events",
            check_volume=True,
            check_schema=False,
            check_distribution=True,
            distribution_columns=["event_duration_ms"],
            lookback_days=14,
        ),
    ]

    orchestrator = AnomalyOrchestrator(
        warehouse_url="postgresql://analyst:pass@warehouse:5432/analytics",
        configs=configs,
    )
    return orchestrator.run_detection()
```

```python
# --- data_quality/late_data_detector.py ---
"""Detects late-arriving data and SLA breaches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from data_quality.anomaly_detector import Anomaly, AnomalyType, Severity


@dataclass
class FreshnessExpectation:
    """Expected data arrival schedule."""

    table_name: str
    timestamp_column: str = "created_at"
    max_delay_minutes: int = 60
    schedule_cron: Optional[str] = None  # e.g., "0 */4 * * *"
    severity_on_breach: Severity = Severity.WARNING


class LateDataDetector:
    """Detects tables with stale or late-arriving data."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def check_freshness(
        self, expectations: List[FreshnessExpectation]
    ) -> List[Anomaly]:
        """Check all tables against freshness expectations."""
        anomalies: List[Anomaly] = []

        for exp in expectations:
            query = text(f"""
                SELECT
                    MAX({exp.timestamp_column}) AS latest_ts,
                    COUNT(*) AS total_rows,
                    EXTRACT(EPOCH FROM
                        (NOW() - MAX({exp.timestamp_column}))
                    ) / 60.0 AS minutes_since_update
                FROM {exp.table_name}
            """)

            with self.engine.connect() as conn:
                row = conn.execute(query).fetchone()

            if row is None or row.latest_ts is None:
                anomalies.append(
                    Anomaly(
                        anomaly_type=AnomalyType.LATE_ARRIVING,
                        severity=Severity.CRITICAL,
                        table_name=exp.table_name,
                        column_name=exp.timestamp_column,
                        description=f"No data found in {exp.table_name}",
                        current_value=float("inf"),
                        expected_range=(0, exp.max_delay_minutes),
                    )
                )
                continue

            delay = float(row.minutes_since_update)

            if delay > exp.max_delay_minutes:
                severity = (
                    Severity.CRITICAL
                    if delay > exp.max_delay_minutes * 3
                    else exp.severity_on_breach
                )
                anomalies.append(
                    Anomaly(
                        anomaly_type=AnomalyType.LATE_ARRIVING,
                        severity=severity,
                        table_name=exp.table_name,
                        column_name=exp.timestamp_column,
                        description=(
                            f"Data is {delay:.0f} min stale "
                            f"(SLA: {exp.max_delay_minutes} min)"
                        ),
                        current_value=delay,
                        expected_range=(0, exp.max_delay_minutes),
                        metadata={
                            "latest_timestamp": str(row.latest_ts),
                            "total_rows": row.total_rows,
                            "delay_minutes": delay,
                        },
                    )
                )

        return anomalies
```

| Detection Method | Best For | Algorithm | False Positive Rate | Latency |
|---|---|---|---|---|
| Z-score | Volume changes | Mean + std dev | Medium | Low |
| KS test | Distribution shifts | Non-parametric | Low | Medium |
| IQR fence | Outlier values | Quartile-based | Low | Low |
| CUSUM | Trend detection | Cumulative sums | Low | Medium |
| Prophet | Seasonal patterns | Time-series ML | Very low | High |
| Isolation Forest | Multi-dimensional | Tree-based | Low | High |

**Key patterns:**

1. **Baseline-first detection** -- compute statistical baselines from historical data before checking current values
2. **Dynamic Z-thresholds** -- adjust sensitivity based on sample size (stricter with more history)
3. **Multi-detector orchestration** -- run volume, schema, distribution, and freshness checks in a single sweep
4. **KS test for distributions** -- use non-parametric Kolmogorov-Smirnov test for distribution shift detection
5. **Severity escalation** -- automatically escalate from WARNING to CRITICAL when anomaly magnitude is extreme
6. **Schema drift tracking** -- compare current information_schema against stored snapshots to catch additions, removals, and type changes
7. **Late-data SLA monitoring** -- track minutes since last update against configurable freshness expectations'''
    ),

    (
        "data-engineering/data-contracts-schema-registries",
        "Implement data contracts with schema registries, contract testing, versioned evolution, and producer-consumer validation for reliable data pipelines.",
        '''Data contracts with schema registries and contract testing:

```python
# --- data_quality/contracts/contract_model.py ---
"""Data contract definition and versioning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class FieldType(str, Enum):
    """Supported contract field types."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMP = "timestamp"
    ARRAY = "array"
    MAP = "map"
    STRUCT = "struct"
    DECIMAL = "decimal"
    BINARY = "binary"


class EvolutionRule(str, Enum):
    """Schema evolution compatibility rules."""

    BACKWARD = "backward"        # new schema can read old data
    FORWARD = "forward"          # old schema can read new data
    FULL = "full"                # both backward and forward
    NONE = "none"                # no compatibility guarantee


class SLATier(str, Enum):
    """Data delivery SLA tiers."""

    PLATINUM = "platinum"   # < 5 min latency, 99.99% uptime
    GOLD = "gold"           # < 15 min latency, 99.9% uptime
    SILVER = "silver"       # < 1 hr latency, 99.5% uptime
    BRONZE = "bronze"       # best effort


@dataclass
class FieldContract:
    """Contract for a single field/column."""

    name: str
    field_type: FieldType
    required: bool = True
    nullable: bool = False
    description: str = ""
    pii: bool = False
    primary_key: bool = False
    constraints: Dict[str, Any] = field(default_factory=dict)
    # constraints examples: {"min": 0, "max": 1000, "pattern": "^[A-Z]+$",
    #   "enum": ["a", "b"], "max_length": 255}
    tags: List[str] = field(default_factory=list)


@dataclass
class QualityContract:
    """Quality expectations embedded in the contract."""

    completeness_threshold: float = 0.99   # % non-null for required fields
    freshness_max_hours: float = 4.0       # max hours since last update
    uniqueness_columns: List[str] = field(default_factory=list)
    custom_checks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DataContract:
    """Full data contract specification."""

    contract_id: str
    name: str
    version: str
    owner_team: str
    domain: str
    description: str
    fields: List[FieldContract]
    quality: QualityContract = field(default_factory=QualityContract)
    evolution_rule: EvolutionRule = EvolutionRule.BACKWARD
    sla_tier: SLATier = SLATier.SILVER
    consumers: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    deprecated: bool = False

    @property
    def schema_fingerprint(self) -> str:
        """Deterministic fingerprint of the schema structure."""
        schema_data = [
            {
                "name": f.name,
                "type": f.field_type.value,
                "required": f.required,
                "nullable": f.nullable,
            }
            for f in sorted(self.fields, key=lambda x: x.name)
        ]
        blob = json.dumps(schema_data, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def pii_fields(self) -> List[str]:
        """List of fields marked as PII."""
        return [f.name for f in self.fields if f.pii]

    @property
    def primary_key_fields(self) -> List[str]:
        """List of primary key fields."""
        return [f.name for f in self.fields if f.primary_key]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return {
            "contract_id": self.contract_id,
            "name": self.name,
            "version": self.version,
            "owner_team": self.owner_team,
            "domain": self.domain,
            "description": self.description,
            "evolution_rule": self.evolution_rule.value,
            "sla_tier": self.sla_tier.value,
            "schema_fingerprint": self.schema_fingerprint,
            "fields": [
                {
                    "name": f.name,
                    "type": f.field_type.value,
                    "required": f.required,
                    "nullable": f.nullable,
                    "pii": f.pii,
                    "description": f.description,
                    "constraints": f.constraints,
                }
                for f in self.fields
            ],
            "quality": {
                "completeness_threshold": self.quality.completeness_threshold,
                "freshness_max_hours": self.quality.freshness_max_hours,
                "uniqueness_columns": self.quality.uniqueness_columns,
            },
            "consumers": self.consumers,
            "deprecated": self.deprecated,
        }
```

```python
# --- data_quality/contracts/schema_registry.py ---
"""Schema registry with versioning and compatibility checking."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean,
    create_engine, text,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from data_quality.contracts.contract_model import (
    DataContract,
    EvolutionRule,
    FieldContract,
    FieldType,
)

logger = logging.getLogger(__name__)
Base = declarative_base()


class ContractVersion(Base):
    """Versioned contract storage."""

    __tablename__ = "dq_contract_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(String(128), nullable=False, index=True)
    version = Column(String(32), nullable=False)
    schema_fingerprint = Column(String(16), nullable=False)
    contract_json = Column(Text, nullable=False)
    is_latest = Column(Boolean, default=True)
    registered_at = Column(DateTime, default=datetime.utcnow)
    registered_by = Column(String(128), nullable=True)


class CompatibilityError:
    """Describes a compatibility violation."""

    def __init__(
        self,
        field_name: str,
        violation_type: str,
        description: str,
    ) -> None:
        self.field_name = field_name
        self.violation_type = violation_type
        self.description = description

    def __repr__(self) -> str:
        return (
            f"CompatibilityError({self.field_name}: "
            f"{self.violation_type} - {self.description})"
        )


class SchemaRegistry:
    """Manages data contract versions and compatibility."""

    def __init__(self, connection_string: str) -> None:
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(bind=self.engine)

    def register_contract(
        self,
        contract: DataContract,
        registered_by: str = "system",
    ) -> Tuple[bool, List[CompatibilityError]]:
        """Register a new contract version with compatibility check."""
        session = self._session_factory()
        try:
            # Get latest version
            latest = (
                session.query(ContractVersion)
                .filter(
                    ContractVersion.contract_id == contract.contract_id,
                    ContractVersion.is_latest == True,
                )
                .first()
            )

            # Check compatibility if previous version exists
            errors: List[CompatibilityError] = []
            if latest:
                prev_contract = self._deserialize(latest.contract_json)
                errors = self.check_compatibility(
                    prev_contract, contract, contract.evolution_rule
                )
                if errors:
                    logger.warning(
                        "Compatibility errors for %s: %s",
                        contract.contract_id,
                        errors,
                    )
                    return False, errors

                # Mark previous as not latest
                latest.is_latest = False

            # Store new version
            version_record = ContractVersion(
                contract_id=contract.contract_id,
                version=contract.version,
                schema_fingerprint=contract.schema_fingerprint,
                contract_json=json.dumps(contract.to_dict()),
                is_latest=True,
                registered_by=registered_by,
            )
            session.add(version_record)
            session.commit()
            logger.info(
                "Registered contract %s v%s (fingerprint: %s)",
                contract.contract_id,
                contract.version,
                contract.schema_fingerprint,
            )
            return True, []

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_compatibility(
        self,
        old: DataContract,
        new: DataContract,
        rule: EvolutionRule,
    ) -> List[CompatibilityError]:
        """Check schema evolution compatibility."""
        errors: List[CompatibilityError] = []

        if rule == EvolutionRule.NONE:
            return errors

        old_fields = {f.name: f for f in old.fields}
        new_fields = {f.name: f for f in new.fields}

        old_names: Set[str] = set(old_fields.keys())
        new_names: Set[str] = set(new_fields.keys())

        removed = old_names - new_names
        added = new_names - old_names

        # BACKWARD: new schema reads old data
        # Cannot remove fields (old data has them)
        if rule in (EvolutionRule.BACKWARD, EvolutionRule.FULL):
            for field_name in removed:
                errors.append(
                    CompatibilityError(
                        field_name=field_name,
                        violation_type="field_removed",
                        description=(
                            f"Cannot remove field '{field_name}' under "
                            f"{rule.value} compatibility"
                        ),
                    )
                )

            # New required fields must have defaults
            for field_name in added:
                f = new_fields[field_name]
                if f.required and not f.nullable:
                    errors.append(
                        CompatibilityError(
                            field_name=field_name,
                            violation_type="required_field_added",
                            description=(
                                f"New required non-nullable field "
                                f"'{field_name}' breaks backward compat"
                            ),
                        )
                    )

        # FORWARD: old schema reads new data
        # Cannot add fields (old schema doesn't know them)
        if rule in (EvolutionRule.FORWARD, EvolutionRule.FULL):
            for field_name in added:
                f = new_fields[field_name]
                if f.required:
                    errors.append(
                        CompatibilityError(
                            field_name=field_name,
                            violation_type="required_field_added_forward",
                            description=(
                                f"Adding required field '{field_name}' "
                                f"breaks forward compatibility"
                            ),
                        )
                    )

        # Type changes are breaking under all rules
        for field_name in old_names & new_names:
            old_type = old_fields[field_name].field_type
            new_type = new_fields[field_name].field_type
            if old_type != new_type:
                if not self._is_safe_type_promotion(old_type, new_type):
                    errors.append(
                        CompatibilityError(
                            field_name=field_name,
                            violation_type="type_changed",
                            description=(
                                f"Type changed from {old_type.value} to "
                                f"{new_type.value}"
                            ),
                        )
                    )

        return errors

    def _is_safe_type_promotion(
        self, old_type: FieldType, new_type: FieldType
    ) -> bool:
        """Check if type change is a safe widening promotion."""
        safe_promotions = {
            (FieldType.INTEGER, FieldType.FLOAT),
            (FieldType.INTEGER, FieldType.DECIMAL),
            (FieldType.FLOAT, FieldType.DECIMAL),
            (FieldType.DATE, FieldType.TIMESTAMP),
        }
        return (old_type, new_type) in safe_promotions

    def get_contract(
        self, contract_id: str, version: Optional[str] = None
    ) -> Optional[DataContract]:
        """Retrieve a contract by ID and optional version."""
        session = self._session_factory()
        try:
            query = session.query(ContractVersion).filter(
                ContractVersion.contract_id == contract_id
            )
            if version:
                query = query.filter(ContractVersion.version == version)
            else:
                query = query.filter(ContractVersion.is_latest == True)

            record = query.first()
            if not record:
                return None
            return self._deserialize(record.contract_json)
        finally:
            session.close()

    def list_contracts(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered contracts, optionally filtered by domain."""
        session = self._session_factory()
        try:
            query = session.query(ContractVersion).filter(
                ContractVersion.is_latest == True
            )
            records = query.all()
            contracts = []
            for r in records:
                data = json.loads(r.contract_json)
                if domain and data.get("domain") != domain:
                    continue
                contracts.append({
                    "contract_id": r.contract_id,
                    "version": r.version,
                    "domain": data.get("domain"),
                    "owner_team": data.get("owner_team"),
                    "fingerprint": r.schema_fingerprint,
                    "registered_at": r.registered_at.isoformat(),
                })
            return contracts
        finally:
            session.close()

    def _deserialize(self, contract_json: str) -> DataContract:
        """Reconstruct DataContract from stored JSON."""
        data = json.loads(contract_json)
        fields = [
            FieldContract(
                name=f["name"],
                field_type=FieldType(f["type"]),
                required=f.get("required", True),
                nullable=f.get("nullable", False),
                pii=f.get("pii", False),
                description=f.get("description", ""),
                constraints=f.get("constraints", {}),
            )
            for f in data["fields"]
        ]
        return DataContract(
            contract_id=data["contract_id"],
            name=data["name"],
            version=data["version"],
            owner_team=data["owner_team"],
            domain=data["domain"],
            description=data.get("description", ""),
            fields=fields,
            evolution_rule=EvolutionRule(data.get("evolution_rule", "backward")),
        )
```

```python
# --- data_quality/contracts/contract_tester.py ---
"""Contract testing for producer-consumer validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from data_quality.contracts.contract_model import (
    DataContract,
    FieldContract,
    FieldType,
)

logger = logging.getLogger(__name__)


@dataclass
class ContractTestResult:
    """Result of a contract test."""

    test_name: str
    field_name: Optional[str]
    passed: bool
    description: str
    actual_value: Optional[Any] = None
    expected_value: Optional[Any] = None


@dataclass
class ContractTestReport:
    """Full report from contract testing."""

    contract_id: str
    contract_version: str
    table_name: str
    total_tests: int
    passed: int
    failed: int
    results: List[ContractTestResult]
    tested_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def success(self) -> bool:
        return self.failed == 0


# SQL type mapping for contract field types
FIELD_TYPE_SQL_MAP: Dict[FieldType, List[str]] = {
    FieldType.STRING: ["character varying", "text", "varchar", "char"],
    FieldType.INTEGER: ["integer", "bigint", "smallint", "int4", "int8"],
    FieldType.FLOAT: ["double precision", "real", "float4", "float8"],
    FieldType.BOOLEAN: ["boolean", "bool"],
    FieldType.DATE: ["date"],
    FieldType.TIMESTAMP: [
        "timestamp without time zone",
        "timestamp with time zone",
        "timestamptz",
    ],
    FieldType.DECIMAL: ["numeric", "decimal"],
}


class ContractTester:
    """Tests actual data against contract specifications."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def test_contract(
        self,
        contract: DataContract,
        table_name: str,
        sample_size: int = 100_000,
    ) -> ContractTestReport:
        """Run all contract tests against a table."""
        results: List[ContractTestResult] = []

        # 1. Schema tests
        results.extend(self._test_schema(contract, table_name))

        # 2. Nullability tests
        results.extend(self._test_nullability(contract, table_name))

        # 3. Uniqueness tests
        results.extend(
            self._test_uniqueness(contract, table_name)
        )

        # 4. Constraint tests
        results.extend(
            self._test_constraints(contract, table_name, sample_size)
        )

        # 5. Freshness test
        results.extend(self._test_freshness(contract, table_name))

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return ContractTestReport(
            contract_id=contract.contract_id,
            contract_version=contract.version,
            table_name=table_name,
            total_tests=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )

    def _test_schema(
        self, contract: DataContract, table_name: str
    ) -> List[ContractTestResult]:
        """Verify table schema matches contract fields."""
        results: List[ContractTestResult] = []

        schema_name, tbl = (
            table_name.split(".", 1)
            if "." in table_name
            else ("public", table_name)
        )

        query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(
                query, {"schema": schema_name, "table": tbl}
            ).fetchall()

        actual_cols = {r.column_name: r for r in rows}

        for field_def in contract.fields:
            if field_def.name not in actual_cols:
                if field_def.required:
                    results.append(
                        ContractTestResult(
                            test_name="field_exists",
                            field_name=field_def.name,
                            passed=False,
                            description=(
                                f"Required field '{field_def.name}' "
                                f"missing from table"
                            ),
                        )
                    )
                continue

            # Check type compatibility
            actual_type = actual_cols[field_def.name].data_type
            expected_types = FIELD_TYPE_SQL_MAP.get(
                field_def.field_type, []
            )
            type_ok = any(
                actual_type.lower().startswith(t) for t in expected_types
            )
            results.append(
                ContractTestResult(
                    test_name="field_type",
                    field_name=field_def.name,
                    passed=type_ok,
                    description=(
                        f"Type check: expected {field_def.field_type.value} "
                        f"({expected_types}), got '{actual_type}'"
                    ),
                    actual_value=actual_type,
                    expected_value=field_def.field_type.value,
                )
            )

        return results

    def _test_nullability(
        self, contract: DataContract, table_name: str
    ) -> List[ContractTestResult]:
        """Test non-nullable fields for NULL violations."""
        results: List[ContractTestResult] = []
        non_nullable = [
            f for f in contract.fields
            if not f.nullable and f.required
        ]

        for field_def in non_nullable:
            query = text(f"""
                SELECT COUNT(*) AS null_count
                FROM {table_name}
                WHERE {field_def.name} IS NULL
            """)
            with self.engine.connect() as conn:
                row = conn.execute(query).fetchone()

            null_count = row.null_count if row else 0
            results.append(
                ContractTestResult(
                    test_name="not_null",
                    field_name=field_def.name,
                    passed=null_count == 0,
                    description=(
                        f"NULL check: found {null_count} NULL values "
                        f"in non-nullable field"
                    ),
                    actual_value=null_count,
                    expected_value=0,
                )
            )

        return results

    def _test_uniqueness(
        self, contract: DataContract, table_name: str
    ) -> List[ContractTestResult]:
        """Test uniqueness constraints from contract."""
        results: List[ContractTestResult] = []

        pk_fields = contract.primary_key_fields
        if pk_fields:
            pk_cols = ", ".join(pk_fields)
            query = text(f"""
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT ({pk_cols})) AS distinct_count
                FROM {table_name}
            """)
            with self.engine.connect() as conn:
                row = conn.execute(query).fetchone()

            is_unique = row.total == row.distinct_count
            results.append(
                ContractTestResult(
                    test_name="primary_key_unique",
                    field_name=pk_cols,
                    passed=is_unique,
                    description=(
                        f"PK uniqueness: {row.distinct_count}/{row.total} "
                        f"distinct values"
                    ),
                    actual_value=row.distinct_count,
                    expected_value=row.total,
                )
            )

        for col in contract.quality.uniqueness_columns:
            query = text(f"""
                SELECT COUNT(*) AS total,
                       COUNT(DISTINCT {col}) AS distinct_count
                FROM {table_name}
            """)
            with self.engine.connect() as conn:
                row = conn.execute(query).fetchone()

            is_unique = row.total == row.distinct_count
            results.append(
                ContractTestResult(
                    test_name="uniqueness",
                    field_name=col,
                    passed=is_unique,
                    description=(
                        f"Uniqueness: {row.distinct_count}/{row.total} "
                        f"distinct values"
                    ),
                    actual_value=row.distinct_count,
                    expected_value=row.total,
                )
            )

        return results

    def _test_constraints(
        self,
        contract: DataContract,
        table_name: str,
        sample_size: int,
    ) -> List[ContractTestResult]:
        """Test field-level constraints (min, max, pattern, enum)."""
        results: List[ContractTestResult] = []

        for field_def in contract.fields:
            if not field_def.constraints:
                continue

            c = field_def.constraints

            if "min" in c or "max" in c:
                conditions: List[str] = []
                if "min" in c:
                    conditions.append(
                        f"{field_def.name} < {c['min']}"
                    )
                if "max" in c:
                    conditions.append(
                        f"{field_def.name} > {c['max']}"
                    )
                where = " OR ".join(conditions)
                query = text(f"""
                    SELECT COUNT(*) AS violation_count
                    FROM {table_name}
                    WHERE {where}
                """)
                with self.engine.connect() as conn:
                    row = conn.execute(query).fetchone()

                results.append(
                    ContractTestResult(
                        test_name="range_constraint",
                        field_name=field_def.name,
                        passed=row.violation_count == 0,
                        description=(
                            f"Range [{c.get('min')}, {c.get('max')}]: "
                            f"{row.violation_count} violations"
                        ),
                        actual_value=row.violation_count,
                        expected_value=0,
                    )
                )

            if "enum" in c:
                values = ", ".join(
                    f"'{v}'" for v in c["enum"]
                )
                query = text(f"""
                    SELECT COUNT(*) AS violation_count
                    FROM {table_name}
                    WHERE {field_def.name} IS NOT NULL
                      AND {field_def.name}::TEXT NOT IN ({values})
                """)
                with self.engine.connect() as conn:
                    row = conn.execute(query).fetchone()

                results.append(
                    ContractTestResult(
                        test_name="enum_constraint",
                        field_name=field_def.name,
                        passed=row.violation_count == 0,
                        description=(
                            f"Enum values: {row.violation_count} "
                            f"values outside allowed set"
                        ),
                        actual_value=row.violation_count,
                        expected_value=0,
                    )
                )

        return results

    def _test_freshness(
        self, contract: DataContract, table_name: str
    ) -> List[ContractTestResult]:
        """Test data freshness against contract SLA."""
        results: List[ContractTestResult] = []
        max_hours = contract.quality.freshness_max_hours

        # Try common timestamp columns
        for ts_col in ["updated_at", "created_at", "event_time"]:
            try:
                query = text(f"""
                    SELECT EXTRACT(EPOCH FROM
                        (NOW() - MAX({ts_col}))
                    ) / 3600.0 AS hours_stale
                    FROM {table_name}
                """)
                with self.engine.connect() as conn:
                    row = conn.execute(query).fetchone()

                if row and row.hours_stale is not None:
                    hours = float(row.hours_stale)
                    results.append(
                        ContractTestResult(
                            test_name="freshness",
                            field_name=ts_col,
                            passed=hours <= max_hours,
                            description=(
                                f"Freshness: {hours:.1f}h stale "
                                f"(SLA: {max_hours}h)"
                            ),
                            actual_value=hours,
                            expected_value=max_hours,
                        )
                    )
                    break  # found a valid timestamp column
            except Exception:
                continue

        return results
```

```yaml
# --- contracts/orders_contract.yaml ---
# Example contract definition in YAML format

contract_id: "orders-v1"
name: "Orders Data Contract"
version: "2.1.0"
owner_team: "commerce-platform"
domain: "ecommerce"
description: "Order events from the commerce platform"

evolution_rule: backward
sla_tier: gold

fields:
  - name: order_id
    type: string
    required: true
    nullable: false
    primary_key: true
    description: "Unique order identifier (UUID)"
    constraints:
      pattern: "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

  - name: customer_id
    type: string
    required: true
    nullable: false
    pii: true
    description: "Customer identifier"

  - name: status
    type: string
    required: true
    nullable: false
    constraints:
      enum: [pending, confirmed, processing, shipped, delivered, cancelled, refunded]

  - name: total_amount
    type: decimal
    required: true
    nullable: false
    constraints:
      min: 0.01
      max: 1000000

  - name: currency
    type: string
    required: true
    nullable: false
    constraints:
      enum: [USD, EUR, GBP, CAD, AUD, JPY]
      max_length: 3

  - name: created_at
    type: timestamp
    required: true
    nullable: false

  - name: updated_at
    type: timestamp
    required: true
    nullable: false

  - name: shipping_address
    type: string
    required: false
    nullable: true
    pii: true

quality:
  completeness_threshold: 0.995
  freshness_max_hours: 2.0
  uniqueness_columns: [order_id]
  custom_checks:
    - name: "updated_after_created"
      sql: "SELECT COUNT(*) FROM orders WHERE updated_at < created_at"
      expected: 0

consumers:
  - analytics-team
  - fulfillment-service
  - finance-reporting

tags:
  cost_center: "CC-1234"
  data_classification: "confidential"
  retention_days: "2555"
```

| Evolution Rule | Add Optional Field | Add Required Field | Remove Field | Change Type | Use Case |
|---|---|---|---|---|---|
| BACKWARD | Allowed | Blocked | Blocked | Safe promote only | Consumer-first |
| FORWARD | Blocked (req) | Blocked | Allowed | Blocked | Producer-first |
| FULL | Optional only | Blocked | Blocked | Safe promote only | Strict compat |
| NONE | Allowed | Allowed | Allowed | Allowed | Breaking changes OK |

**Key patterns:**

1. **Contract-as-code** -- define data contracts as typed Python dataclasses with fields, constraints, quality rules, and SLA tiers
2. **Schema fingerprinting** -- generate deterministic hashes of schema structure for change detection
3. **Compatibility checking** -- enforce BACKWARD/FORWARD/FULL evolution rules before registering new versions
4. **Safe type promotions** -- allow widening type changes (int to float, date to timestamp) while blocking narrowing
5. **Contract testing** -- validate actual data against contract specifications (schema, nullability, uniqueness, constraints, freshness)
6. **PII tagging** -- mark sensitive fields in the contract for downstream masking and access control
7. **YAML + Python duality** -- support both YAML contract definitions (for humans) and Python dataclass serialization (for automation)'''
    ),
]
