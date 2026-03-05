"""
Batch P5 — MLOps & Data Engineering: pipeline orchestration, feature stores,
Beam/Spark, data quality monitoring, model monitoring in production.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. ML Pipeline Orchestration with Airflow/Prefect ---
    (
        "ml_pipeline_orchestration_airflow_prefect",
        "Explain how to design and implement ML training pipeline orchestration using Airflow and "
        "Prefect — covering DAG design patterns for training pipelines, integrating data validation "
        "with Great Expectations, managing models through a model registry, and setting up A/B test "
        "deployment with canary rollouts. Include complete runnable Python code with type hints.",
        r"""
# ML Pipeline Orchestration: Airflow, Prefect, and Production Training Workflows

## Why Pipeline Orchestration Matters for ML

ML training is **not a single script** — it is a directed acyclic graph (DAG) of dependent
stages: data ingestion, validation, feature engineering, training, evaluation, registration,
and deployment. Without orchestration, teams fall into the **"notebook to production" trap**
where training lives in Jupyter notebooks that nobody can reproduce, schedule, or monitor.

The two dominant orchestrators are **Apache Airflow** (the industry standard, best for complex
enterprise DAGs) and **Prefect** (modern Python-native alternative with better developer
ergonomics). The trade-off is clear: Airflow has a larger ecosystem and more battle-tested
integrations, however Prefect offers simpler code, native async support, and less
boilerplate. A common mistake is choosing based on hype rather than team capabilities —
Airflow requires understanding of XCom serialization, executor backends, and connection
management, while Prefect requires understanding of its task runner model and result
persistence.

## DAG Design Patterns for Training Pipelines

The best practice for ML DAGs is the **"diamond pattern"**: a single ingestion step fans
out to parallel validation and feature engineering tasks, which converge at the training
step, followed by evaluation and conditional deployment.

```
DAG Structure (Diamond Pattern):

  [ingest_data]
       |
  +---------+
  |         |
[validate] [engineer_features]
  |         |
  +---------+
       |
    [train]
       |
   [evaluate]
       |
  +----+----+
  |         |
[register] [notify]
  |
[deploy_ab_test]
```

Therefore, each step should be **idempotent** (safe to retry) and produce **versioned
artifacts** (datasets, models, metrics) that downstream steps consume by reference rather
than by value.

## Complete Airflow DAG Implementation

```python
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass, field, asdict

from airflow import DAG
from airflow.decorators import task, dag
from airflow.operators.python import BranchPythonOperator
from airflow.models import Variable
import great_expectations as gx
import mlflow
from mlflow.tracking import MlflowClient


@dataclass
class TrainingConfig:
    # Configuration for one training run — all params versioned together
    model_name: str = "fraud-detector-v2"
    dataset_path: str = "s3://data-lake/fraud/daily/"
    features_version: str = "v3"
    hyperparams: Dict[str, Any] = field(default_factory=lambda: {
        "learning_rate": 0.001,
        "n_estimators": 500,
        "max_depth": 8,
        "min_samples_leaf": 50,
    })
    min_accuracy: float = 0.92
    min_precision: float = 0.85
    ab_test_traffic_pct: float = 10.0

    def fingerprint(self) -> str:
        # Deterministic hash for cache-busting and reproducibility
        raw = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


# -- Data validation with Great Expectations --

def validate_training_data(dataset_path: str) -> Dict[str, Any]:
    # Validate raw data before training using Great Expectations.
    # Returns validation results dict with success flag and statistics.
    #
    # Best practice: validate BEFORE feature engineering to catch
    # problems early. Common pitfalls include schema drift from
    # upstream changes and NULL spikes from failed ETL jobs.

    context = gx.get_context()

    datasource = context.sources.add_or_update_pandas_s3(
        name="training_data",
        bucket="data-lake",
        boto3_options={"region_name": "us-east-1"},
    )

    data_asset = datasource.add_csv_asset(
        name="fraud_transactions",
        batching_regex=r"fraud/daily/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})\.csv",
    )

    batch_request = data_asset.build_batch_request()

    # Define expectations — these act as contract tests for data
    expectation_suite = context.add_or_update_expectation_suite("fraud_training_suite")

    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name="fraud_training_suite",
    )

    # Schema expectations
    validator.expect_table_columns_to_match_ordered_list(
        column_list=["tx_id", "amount", "merchant_id", "category",
                     "timestamp", "is_fraud", "user_age", "tx_count_24h"]
    )

    # Completeness — no critical NULLs
    for col in ["amount", "is_fraud", "tx_count_24h"]:
        validator.expect_column_values_to_not_be_null(col, mostly=0.99)

    # Distribution checks — catch upstream drift
    validator.expect_column_mean_to_be_between("amount", min_value=10, max_value=5000)
    validator.expect_column_proportion_of_unique_values_to_be_between(
        "is_fraud", min_value=0.001, max_value=0.15
    )

    # Freshness — data should be recent
    validator.expect_column_max_to_be_between(
        "timestamp",
        min_value=(datetime.now() - timedelta(hours=48)).isoformat(),
        max_value=datetime.now().isoformat(),
    )

    results = validator.validate()
    return {
        "success": results.success,
        "statistics": results.statistics,
        "failed_expectations": [
            r.expectation_config.expectation_type
            for r in results.results if not r.success
        ],
    }


# -- Airflow DAG definition using TaskFlow API --

@dag(
    schedule="0 6 * * *",  # Daily at 6 AM UTC
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(hours=2),
    },
    tags=["ml", "training", "fraud-detection"],
)
def fraud_model_training_pipeline():
    config = TrainingConfig()

    @task()
    def ingest_data(cfg: Dict[str, Any]) -> str:
        # Snapshot raw data and return a versioned artifact path.
        # Idempotent because it writes to a fingerprinted path.
        import boto3
        import pandas as pd

        s3 = boto3.client("s3")
        df = pd.read_csv(cfg["dataset_path"])
        snapshot_path = f"s3://ml-artifacts/snapshots/{cfg['model_name']}/{datetime.now():%Y%m%d}.parquet"
        df.to_parquet(snapshot_path, index=False)
        return snapshot_path

    @task()
    def validate_data(snapshot_path: str) -> Dict[str, Any]:
        results = validate_training_data(snapshot_path)
        if not results["success"]:
            raise ValueError(
                f"Data validation failed: {results['failed_expectations']}"
            )
        return results

    @task()
    def engineer_features(snapshot_path: str, cfg: Dict[str, Any]) -> str:
        import pandas as pd
        df = pd.read_parquet(snapshot_path)

        # Feature engineering — time-windowed aggregates
        df["tx_amount_zscore"] = (
            (df["amount"] - df["amount"].mean()) / df["amount"].std()
        )
        df["hour_of_day"] = pd.to_datetime(df["timestamp"]).dt.hour
        df["is_weekend"] = pd.to_datetime(df["timestamp"]).dt.dayofweek >= 5

        feature_path = f"s3://ml-artifacts/features/{cfg['features_version']}/{datetime.now():%Y%m%d}.parquet"
        df.to_parquet(feature_path, index=False)
        return feature_path

    @task()
    def train_model(feature_path: str, cfg: Dict[str, Any]) -> str:
        import pandas as pd
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split

        df = pd.read_parquet(feature_path)
        feature_cols = ["amount", "tx_amount_zscore", "hour_of_day",
                        "is_weekend", "user_age", "tx_count_24h"]
        X = df[feature_cols]
        y = df["is_fraud"]
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )

        mlflow.set_experiment(cfg["model_name"])
        with mlflow.start_run() as run:
            model = GradientBoostingClassifier(**cfg["hyperparams"])
            model.fit(X_train, y_train)

            # Log everything for reproducibility
            mlflow.log_params(cfg["hyperparams"])
            mlflow.sklearn.log_model(model, "model")

            accuracy = model.score(X_val, y_val)
            mlflow.log_metric("val_accuracy", accuracy)

        return run.info.run_id

    @task.branch()
    def evaluate_model(run_id: str, cfg: Dict[str, Any]) -> str:
        # Branch operator: deploy if quality gates pass, else notify
        client = MlflowClient()
        run = client.get_run(run_id)
        accuracy = run.data.metrics.get("val_accuracy", 0)

        if accuracy >= cfg["min_accuracy"]:
            return "register_model"
        return "notify_failure"

    @task()
    def register_model(run_id: str, cfg: Dict[str, Any]) -> str:
        client = MlflowClient()
        model_uri = f"runs:/{run_id}/model"
        mv = mlflow.register_model(model_uri, cfg["model_name"])
        client.set_registered_model_tag(
            cfg["model_name"], "fingerprint", TrainingConfig().fingerprint()
        )
        return mv.version

    @task()
    def deploy_ab_test(model_version: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        # A/B deployment: route cfg["ab_test_traffic_pct"]% to new model
        deployment_config = {
            "model_name": cfg["model_name"],
            "champion_version": int(model_version) - 1,
            "challenger_version": int(model_version),
            "traffic_split": {
                "champion": 100 - cfg["ab_test_traffic_pct"],
                "challenger": cfg["ab_test_traffic_pct"],
            },
            "rollback_on_metric_drop": True,
            "metric_threshold": cfg["min_precision"],
        }
        # In production this calls your serving infra API (Seldon, KServe, etc.)
        return deployment_config

    @task()
    def notify_failure() -> None:
        # Send alert via PagerDuty / Slack
        pass

    # Wire the DAG
    cfg_dict = asdict(config)
    snapshot = ingest_data(cfg_dict)
    validation = validate_data(snapshot)
    features = engineer_features(snapshot, cfg_dict)
    run_id = train_model(features, cfg_dict)
    branch = evaluate_model(run_id, cfg_dict)
    version = register_model(run_id, cfg_dict)
    deploy_ab_test(version, cfg_dict)
    notify_failure()

    # Set dependencies
    validation >> features  # Only engineer features after validation passes

pipeline_dag = fraud_model_training_pipeline()
```

## Equivalent Prefect Implementation

```python
from prefect import flow, task
from prefect.tasks import task_input_hash
from datetime import timedelta
from typing import Dict, Any


@task(
    retries=3,
    retry_delay_seconds=60,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=24),
)
def ingest_and_validate(dataset_path: str) -> str:
    # Prefect combines caching + retries natively — less boilerplate
    # than Airflow because the task_input_hash auto-deduplicates
    import pandas as pd
    df = pd.read_csv(dataset_path)
    # ... validation and snapshot logic ...
    return "s3://ml-artifacts/snapshots/latest.parquet"


@task(retries=2, retry_delay_seconds=120, timeout_seconds=3600)
def train_and_evaluate(feature_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    # Training with built-in timeout protection
    # Prefect advantage: native async, no XCom serialization issues
    return {"run_id": "abc123", "accuracy": 0.95}


@flow(
    name="fraud-model-training",
    description="Daily fraud model retraining pipeline",
    retries=1,
    log_prints=True,
)
def training_flow(config: Dict[str, Any]) -> Dict[str, Any]:
    # Prefect flows are just Python functions — therefore easier
    # to test than Airflow DAGs which require a running scheduler
    snapshot = ingest_and_validate(config["dataset_path"])
    results = train_and_evaluate(snapshot, config)

    if results["accuracy"] >= config["min_accuracy"]:
        # Conditional logic is native Python, not BranchPythonOperator
        return {"status": "deployed", "results": results}
    return {"status": "failed_quality_gate", "results": results}
```

## Summary and Key Takeaways

- **DAG design**: Use the diamond pattern — fan-out for validation and features, converge
  at training. Every step must be idempotent and produce versioned artifacts.
- **Data validation**: Integrate Great Expectations as a gate before training. A common
  mistake is validating after training, wasting compute on bad data.
- **Model registry**: MLflow provides versioning, tagging, and lineage. Always tag models
  with the config fingerprint for full reproducibility.
- **A/B deployment**: Start with low traffic (5-10%) to the challenger model. The best
  practice is automated rollback if precision drops below threshold.
- **Airflow vs Prefect**: Airflow for mature orgs with complex multi-team DAGs; Prefect
  for teams wanting Python-native simplicity. However, both require solid monitoring and
  alerting — the orchestrator failing silently is a critical pitfall in production ML.
"""
    ),
    # --- 2. Feature Stores ---
    (
        "feature_store_implementation_feast",
        "Explain feature stores in depth — covering online versus offline stores, point-in-time "
        "correctness and why it prevents data leakage, implementing a production feature store "
        "with Feast, monitoring feature freshness and drift, and the architectural patterns for "
        "serving features at low latency in real-time ML systems. Include complete Python code.",
        r"""
# Feature Stores: Online/Offline Serving, Point-in-Time Correctness, and Feast

## Why Feature Stores Exist

The central problem in production ML is the **training-serving skew**: features computed
during training (in batch, using Pandas on historical data) differ from features computed
during serving (in real-time, using streaming data). This causes **silent model degradation**
because the model sees feature distributions at inference time that it never saw during
training.

A feature store solves this by providing a **single source of truth** for feature definitions,
with two materialization paths:

```
Feature Store Architecture:

  [Raw Data Sources]
         |
  [Feature Definitions]  <-- single source of truth
         |
    +----+----+
    |         |
[Offline Store]  [Online Store]
  (historical)    (real-time)
    |                |
[Training]     [Serving]
    |                |
  (Batch SQL)   (Key-value lookup <10ms)
```

**Offline store**: Stores historical feature values. Used for training data generation
and batch predictions. Typically backed by a data warehouse (BigQuery, Redshift, S3/Parquet).

**Online store**: Stores the **latest** feature values for each entity. Used for real-time
inference. Backed by a low-latency key-value store (Redis, DynamoDB, Bigtable). The trade-off
is cost — maintaining a hot cache of features adds infrastructure expense, however the
alternative (computing features on-the-fly at serving time) introduces latency and
correctness risks.

## Point-in-Time Correctness

This is the **most critical concept** in feature stores and the most common mistake teams
make. Point-in-time correctness means: when generating training data, features must reflect
**only what was known at the time of the training event**, not future information.

```
Without point-in-time correctness (DATA LEAKAGE):

  Event: User made purchase at 2024-01-15 10:00
  Feature: user_purchase_count_30d

  WRONG: Query all purchases in [Dec 16 - Jan 15] at query time
         This includes purchases AFTER 10:00 on Jan 15 — future leakage!

  RIGHT: Query all purchases in [Dec 16 - Jan 15 10:00) — strictly before event

Timeline:
  Dec 16        Jan 14         Jan 15 10:00    Jan 15 23:59
  |-------------|--------------|x event        |
  |<-- correct window ------->|               |
  |<-- WRONG window (includes future) ------->|
```

Therefore, point-in-time joins must use an **as-of join** (also called a temporal join)
that looks up the feature value as it existed at the exact event timestamp. Feast handles
this automatically with its `get_historical_features()` API.

## Complete Feast Implementation

```python
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from feast import (
    Entity,
    FeatureService,
    FeatureView,
    Field,
    FileSource,
    PushSource,
    RequestSource,
    on_demand_feature_view,
)
from feast.types import Float32, Float64, Int64, String, UnixTimestamp
from feast.infra.offline_stores.contrib.spark_offline_store.spark_source import (
    SparkSource,
)
from feast.value_type import ValueType
import pandas as pd
import numpy as np


# -- Entity definitions --
# Entities are the primary keys for feature lookup

user_entity = Entity(
    name="user_id",
    join_keys=["user_id"],
    description="Unique user identifier for feature lookup",
)

merchant_entity = Entity(
    name="merchant_id",
    join_keys=["merchant_id"],
    description="Merchant identifier for merchant-level features",
)


# -- Offline data sources --

user_transaction_source = SparkSource(
    name="user_transactions",
    table="analytics.user_transaction_features",
    timestamp_field="feature_timestamp",
    created_timestamp_column="created_at",
    description="Daily aggregated user transaction features from Spark pipeline",
)

merchant_risk_source = FileSource(
    name="merchant_risk_scores",
    path="s3://feature-store/merchant_risk/",
    timestamp_field="score_date",
    file_format="parquet",
)

# Push source for real-time feature updates
user_realtime_source = PushSource(
    name="user_realtime_events",
    batch_source=user_transaction_source,
)


# -- Feature views --

user_transaction_fv = FeatureView(
    name="user_transaction_features",
    entities=[user_entity],
    ttl=timedelta(days=7),  # Features older than 7 days are stale
    schema=[
        Field(name="tx_count_24h", dtype=Int64),
        Field(name="tx_count_7d", dtype=Int64),
        Field(name="tx_amount_avg_30d", dtype=Float64),
        Field(name="tx_amount_std_30d", dtype=Float64),
        Field(name="unique_merchants_7d", dtype=Int64),
        Field(name="max_single_tx_24h", dtype=Float64),
        Field(name="avg_time_between_tx_hours", dtype=Float64),
    ],
    source=user_transaction_source,
    online=True,  # Materialize to online store for real-time serving
    tags={"team": "fraud", "sla": "p99_5ms"},
)

merchant_risk_fv = FeatureView(
    name="merchant_risk_features",
    entities=[merchant_entity],
    ttl=timedelta(days=30),
    schema=[
        Field(name="risk_score", dtype=Float64),
        Field(name="chargeback_rate_90d", dtype=Float64),
        Field(name="merchant_category", dtype=String),
        Field(name="days_since_registration", dtype=Int64),
    ],
    source=merchant_risk_source,
    online=True,
    tags={"team": "fraud", "sla": "p99_10ms"},
)


# -- On-demand feature (computed at request time) --

@on_demand_feature_view(
    sources=[user_transaction_fv],
    schema=[
        Field(name="tx_velocity_ratio", dtype=Float64),
        Field(name="amount_zscore", dtype=Float64),
    ],
)
def user_risk_signals(inputs: pd.DataFrame) -> pd.DataFrame:
    # Computed in real-time from stored features — no additional DB lookup.
    # Best practice: keep on-demand features lightweight (<1ms compute).
    # Pitfall: putting heavy computation here defeats the purpose of
    # precomputed features and adds serving latency.
    result = pd.DataFrame()
    result["tx_velocity_ratio"] = (
        inputs["tx_count_24h"] / inputs["tx_count_7d"].clip(lower=1)
    )
    result["amount_zscore"] = (
        (inputs["max_single_tx_24h"] - inputs["tx_amount_avg_30d"])
        / inputs["tx_amount_std_30d"].clip(lower=0.01)
    )
    return result


# -- Feature service (groups features for a model) --

fraud_detection_service = FeatureService(
    name="fraud_detection_v2",
    features=[
        user_transaction_fv,
        merchant_risk_fv,
        user_risk_signals,
    ],
    tags={"model": "fraud-detector-v2", "owner": "ml-team"},
)
```

## Training Data Generation with Point-in-Time Joins

```python
from feast import FeatureStore
import pandas as pd
from typing import Dict, List


def generate_training_data(
    entity_df: pd.DataFrame,
    feature_service_name: str = "fraud_detection_v2",
) -> pd.DataFrame:
    # Generate training dataset with point-in-time correct features.
    #
    # entity_df must have columns: user_id, merchant_id, event_timestamp, label
    # Feast automatically performs as-of joins to prevent data leakage.
    #
    # Because Feast uses event_timestamp for the temporal join, each row
    # gets features as they existed AT that timestamp, not current values.

    store = FeatureStore(repo_path="./feature_repo")

    training_df = store.get_historical_features(
        entity_df=entity_df,
        features=store.get_feature_service(feature_service_name),
    ).to_df()

    # Validate no future leakage
    assert training_df["feature_timestamp"].max() <= training_df["event_timestamp"].max(), \
        "Feature timestamps exceed event timestamps — potential leakage!"

    return training_df


def serve_features_online(
    user_id: str,
    merchant_id: str,
    store: Optional[FeatureStore] = None,
) -> Dict[str, Any]:
    # Real-time feature retrieval for inference (<10ms target).
    # Online store returns the LATEST materialized values.
    if store is None:
        store = FeatureStore(repo_path="./feature_repo")

    feature_vector = store.get_online_features(
        features=store.get_feature_service("fraud_detection_v2"),
        entity_rows=[{"user_id": user_id, "merchant_id": merchant_id}],
    ).to_dict()

    return feature_vector


# -- Feature freshness monitoring --

@dataclass
class FeatureFreshnessReport:
    # Tracks staleness of features in the online store
    feature_view: str
    latest_timestamp: datetime
    staleness_hours: float
    is_stale: bool
    row_count: int


def monitor_feature_freshness(
    store: FeatureStore,
    max_staleness_hours: float = 24.0,
) -> List[FeatureFreshnessReport]:
    # Check all feature views for staleness. A common mistake is assuming
    # the materialization pipeline never fails — however Spark jobs crash,
    # S3 partitions go missing, and schema changes break pipelines silently.
    # Therefore always monitor freshness as a first-class metric.

    reports: List[FeatureFreshnessReport] = []
    now = datetime.utcnow()

    for fv in store.list_feature_views():
        # Query online store metadata
        try:
            materialization_intervals = store.get_feature_view(fv.name)
            latest = max(
                (interval.end_date for interval in fv.materialization_intervals),
                default=datetime.min,
            )
            staleness = (now - latest).total_seconds() / 3600
            reports.append(FeatureFreshnessReport(
                feature_view=fv.name,
                latest_timestamp=latest,
                staleness_hours=staleness,
                is_stale=staleness > max_staleness_hours,
                row_count=len(fv.schema),
            ))
        except Exception as e:
            reports.append(FeatureFreshnessReport(
                feature_view=fv.name,
                latest_timestamp=datetime.min,
                staleness_hours=float("inf"),
                is_stale=True,
                row_count=0,
            ))

    stale_views = [r for r in reports if r.is_stale]
    if stale_views:
        # Alert on stale features — this is a production best practice
        alert_msg = "STALE FEATURES: " + ", ".join(
            f"{r.feature_view} ({r.staleness_hours:.1f}h)" for r in stale_views
        )
        # send_pagerduty_alert(alert_msg)

    return reports
```

## Summary and Key Takeaways

- **Online vs offline**: Offline stores (warehouse) serve training; online stores (Redis/DynamoDB)
  serve inference. The trade-off is cost versus latency — not every feature needs online serving.
  Best practice is to start with offline-only features and promote to online only when a model
  requires real-time serving with sub-10ms latency requirements.
- **Point-in-time correctness**: The single most important concept. Without it, training data
  contains future information, leading to inflated metrics that collapse in production. Feast's
  `get_historical_features()` handles this automatically because it performs as-of temporal joins.
  A common mistake is building custom feature joins that look up the "latest" value rather than
  the value at the exact event timestamp — this introduces subtle data leakage that inflates
  offline metrics by 5-15% but causes production performance to degrade immediately after
  deployment, which is extremely difficult to debug after the fact.
- **Feature freshness**: Monitor materialization staleness as a first-class production metric.
  A common mistake is assuming pipelines never fail. Best practice is automated alerting when
  any feature view exceeds its SLA. Set different staleness thresholds per feature view because
  some features (like daily aggregates) naturally update less frequently than others (like
  real-time counters). The pitfall is applying a single global freshness threshold to all
  feature views, which either misses stale real-time features or floods alerts for batch features.
- **On-demand features**: Use sparingly for lightweight transformations that combine stored
  features. The pitfall is putting heavy computation in on-demand views, which adds serving
  latency and defeats the purpose of precomputed features.
- **Feature services**: Group features by model to version and deploy feature sets independently.
  This prevents the common mistake of one team's feature change breaking another team's model.
  However, feature service versioning requires governance — therefore establish a process for
  deprecating old feature versions and migrating consumers before removing features from the
  store.
"""
    ),
    # --- 3. Data Pipeline with Apache Beam/Spark ---
    (
        "data_pipeline_beam_spark_unified",
        "Explain how to build unified batch and streaming data pipelines using Apache Beam and "
        "PySpark — covering windowing strategies, watermarks for handling late data, exactly-once "
        "processing guarantees, and the trade-offs between batch and streaming architectures. "
        "Include complete runnable Python implementations with type hints and tests.",
        r"""
# Unified Batch & Streaming Pipelines: Apache Beam and PySpark

## The Batch-Streaming Convergence Problem

Traditional data architectures maintained **two separate codepaths**: a batch pipeline
(daily Spark jobs) and a streaming pipeline (Kafka consumers). This "Lambda Architecture"
works but creates an enormous maintenance burden because every transformation must be
implemented twice and kept in sync. A common mistake is assuming the batch and streaming
versions produce identical results — they almost never do, because windowing semantics,
late data handling, and aggregation boundaries differ.

**Apache Beam** solves this with a unified programming model: write once, run in batch
or streaming mode. The Beam model is built on four questions:

```
The Four Questions of Stream Processing:

1. WHAT results are computed?     --> Transformations (Map, GroupByKey, Combine)
2. WHERE in event time?           --> Windowing (Fixed, Sliding, Session)
3. WHEN in processing time?       --> Triggers (watermark, early/late firings)
4. HOW do refinements relate?     --> Accumulation (discard, accumulate, retract)

These four questions apply to BOTH batch and streaming — batch is just a
special case where the window is "all time" and the trigger is "when done."
```

Therefore, understanding windowing and watermarks is essential for any data
engineer working with real-time systems.

## Windowing Strategies Explained

**Fixed windows** divide time into non-overlapping intervals (e.g., every 5 minutes).
Best for regular aggregation: hourly revenue, daily active users.

**Sliding windows** overlap — a 10-minute window sliding every 2 minutes produces
5 windows per element. Best for moving averages and trend detection. The trade-off
is compute cost: more overlap means more redundant computation.

**Session windows** group events by activity gaps. A 30-minute session gap means
"if no events for 30 minutes, close the window." Best for user engagement analysis.
However, session windows are the most complex because their boundaries are
data-dependent.

## Complete Apache Beam Pipeline

```python
import apache_beam as beam
from apache_beam import window, trigger
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.transforms.combiners import MeanCombineFn, CountCombineFn
from apache_beam.io.kafka import ReadFromKafka, WriteToKafka
from apache_beam.transforms.trigger import (
    AfterWatermark,
    AfterProcessingTime,
    AfterCount,
    AccumulationMode,
    Repeatedly,
)
from typing import Tuple, Dict, Any, Optional, Iterable, Iterator
from dataclasses import dataclass
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    # Represents a single IoT sensor measurement
    sensor_id: str
    temperature: float
    humidity: float
    event_time: float  # Unix timestamp
    received_time: float


class ParseSensorReading(beam.DoFn):
    # Parse raw JSON messages into SensorReading objects.
    # Handles malformed data gracefully with dead-letter output.

    VALID_TAG = "valid"
    DEAD_LETTER_TAG = "dead_letter"

    def process(
        self, element: bytes, timestamp=beam.DoFn.TimestampParam
    ) -> Iterator[beam.pvalue.TaggedOutput]:
        try:
            raw = json.loads(element.decode("utf-8"))
            reading = SensorReading(
                sensor_id=raw["sensor_id"],
                temperature=float(raw["temperature"]),
                humidity=float(raw["humidity"]),
                event_time=float(raw["event_time"]),
                received_time=datetime.utcnow().timestamp(),
            )

            # Validate ranges — common pitfall: trusting raw sensor data
            if not (-50 <= reading.temperature <= 150):
                yield beam.pvalue.TaggedOutput(
                    self.DEAD_LETTER_TAG,
                    {"raw": raw, "reason": "temperature_out_of_range"},
                )
                return

            yield beam.pvalue.TaggedOutput(self.VALID_TAG, reading)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            yield beam.pvalue.TaggedOutput(
                self.DEAD_LETTER_TAG,
                {"raw": str(element), "reason": str(e)},
            )


class ComputeWindowedAggregates(beam.DoFn):
    # Compute per-sensor aggregates within each window.
    # The window information is available via the WindowParam.

    def process(
        self,
        element: Tuple[str, Iterable[SensorReading]],
        window_info=beam.DoFn.WindowParam,
    ) -> Iterator[Dict[str, Any]]:
        sensor_id, readings = element
        readings_list = list(readings)

        if not readings_list:
            return

        temps = [r.temperature for r in readings_list]
        humidities = [r.humidity for r in readings_list]

        yield {
            "sensor_id": sensor_id,
            "window_start": window_info.start.to_utc_datetime().isoformat(),
            "window_end": window_info.end.to_utc_datetime().isoformat(),
            "reading_count": len(readings_list),
            "avg_temperature": sum(temps) / len(temps),
            "max_temperature": max(temps),
            "min_temperature": min(temps),
            "avg_humidity": sum(humidities) / len(humidities),
            # Latency tracking — how late was the data?
            "max_latency_seconds": max(
                r.received_time - r.event_time for r in readings_list
            ),
        }


def build_sensor_pipeline(
    pipeline_options: Optional[PipelineOptions] = None,
    bootstrap_servers: str = "kafka:9092",
    input_topic: str = "sensor-readings",
    output_table: str = "project:dataset.sensor_aggregates",
    window_size_minutes: int = 5,
    allowed_lateness_minutes: int = 30,
) -> beam.Pipeline:
    # Build the unified batch/streaming sensor pipeline.
    #
    # Key design decisions:
    # - Fixed 5-min windows with 30-min allowed lateness
    # - Early firings every 60s for real-time dashboards
    # - Late firings for correctness (retracts previous results)
    # - Dead letter queue for bad data
    #
    # Because Beam separates the pipeline definition from execution,
    # this same pipeline runs on Dataflow, Flink, or Spark runners.

    if pipeline_options is None:
        pipeline_options = PipelineOptions()

    p = beam.Pipeline(options=pipeline_options)

    # Read from Kafka (streaming) or file (batch)
    raw_messages = (
        p
        | "ReadFromKafka" >> ReadFromKafka(
            consumer_config={"bootstrap.servers": bootstrap_servers},
            topics=[input_topic],
            with_metadata=False,
        )
        | "ExtractValues" >> beam.Map(lambda kv: kv[1])
    )

    # Parse with dead-letter handling
    parsed = raw_messages | "ParseReadings" >> beam.ParDo(
        ParseSensorReading()
    ).with_outputs(
        ParseSensorReading.DEAD_LETTER_TAG,
        main=ParseSensorReading.VALID_TAG,
    )

    valid_readings = parsed[ParseSensorReading.VALID_TAG]
    dead_letters = parsed[ParseSensorReading.DEAD_LETTER_TAG]

    # Apply windowing with watermarks and triggers
    windowed_readings = (
        valid_readings
        | "AssignEventTime" >> beam.Map(
            lambda r: beam.window.TimestampedValue(r, r.event_time)
        )
        | "ApplyWindowing" >> beam.WindowInto(
            window.FixedWindows(window_size_minutes * 60),
            trigger=AfterWatermark(
                # Early: fire every 60s for dashboard freshness
                early=AfterProcessingTime(60),
                # Late: fire on each late arrival for correction
                late=AfterCount(1),
            ),
            # Accumulate mode means late firings include ALL data
            # (not just new arrivals) — therefore results are always complete
            accumulation_mode=AccumulationMode.ACCUMULATING,
            allowed_lateness=beam.utils.timestamp.Duration(
                seconds=allowed_lateness_minutes * 60
            ),
        )
    )

    # Aggregate per sensor per window
    aggregates = (
        windowed_readings
        | "KeyBySensor" >> beam.Map(lambda r: (r.sensor_id, r))
        | "GroupBySensor" >> beam.GroupByKey()
        | "ComputeAggregates" >> beam.ParDo(ComputeWindowedAggregates())
    )

    # Write results to BigQuery
    aggregates | "WriteToBigQuery" >> beam.io.WriteToBigQuery(
        output_table,
        schema="sensor_id:STRING,window_start:TIMESTAMP,window_end:TIMESTAMP,"
               "reading_count:INTEGER,avg_temperature:FLOAT,max_temperature:FLOAT,"
               "min_temperature:FLOAT,avg_humidity:FLOAT,max_latency_seconds:FLOAT",
        write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
        create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
    )

    # Dead letters to separate table for debugging
    dead_letters | "WriteDeadLetters" >> beam.io.WriteToBigQuery(
        f"{output_table}_dead_letters",
        schema="raw:STRING,reason:STRING",
        write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
        create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
    )

    return p
```

## PySpark Structured Streaming Equivalent

```python
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType, LongType
)
from typing import Optional


def build_spark_streaming_pipeline(
    spark: Optional[SparkSession] = None,
    kafka_servers: str = "kafka:9092",
    input_topic: str = "sensor-readings",
    checkpoint_dir: str = "s3://checkpoints/sensor-pipeline/",
    output_path: str = "s3://data-lake/sensor_aggregates/",
    window_duration: str = "5 minutes",
    watermark_delay: str = "30 minutes",
) -> None:
    # PySpark Structured Streaming pipeline — equivalent to the Beam pipeline.
    #
    # Key difference from Beam: Spark uses processing-time triggers only
    # (micro-batch or continuous), while Beam has richer trigger semantics.
    # However, Spark's checkpoint-based exactly-once is simpler to reason about
    # because it relies on WAL (write-ahead log) rather than Beam's per-element
    # acknowledgment model.

    if spark is None:
        spark = (
            SparkSession.builder
            .appName("SensorStreamingPipeline")
            .config("spark.sql.shuffle.partitions", "200")
            .config("spark.streaming.kafka.maxRatePerPartition", "10000")
            .getOrCreate()
        )

    sensor_schema = StructType([
        StructField("sensor_id", StringType(), False),
        StructField("temperature", DoubleType(), False),
        StructField("humidity", DoubleType(), False),
        StructField("event_time", DoubleType(), False),
    ])

    # Read from Kafka
    raw_stream: DataFrame = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_servers)
        .option("subscribe", input_topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # Parse JSON and apply watermark
    parsed_stream = (
        raw_stream
        .select(F.from_json(F.col("value").cast("string"), sensor_schema).alias("data"))
        .select("data.*")
        .withColumn("event_timestamp", F.from_unixtime("event_time").cast(TimestampType()))
        .filter(F.col("temperature").between(-50, 150))  # Range validation
        .withWatermark("event_timestamp", watermark_delay)
    )

    # Windowed aggregation — exactly-once via checkpointing
    aggregated = (
        parsed_stream
        .groupBy(
            F.col("sensor_id"),
            F.window("event_timestamp", window_duration),
        )
        .agg(
            F.count("*").alias("reading_count"),
            F.avg("temperature").alias("avg_temperature"),
            F.max("temperature").alias("max_temperature"),
            F.min("temperature").alias("min_temperature"),
            F.avg("humidity").alias("avg_humidity"),
        )
        .select(
            "sensor_id",
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "reading_count",
            "avg_temperature",
            "max_temperature",
            "min_temperature",
            "avg_humidity",
        )
    )

    # Write with exactly-once checkpoint guarantee
    query = (
        aggregated.writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", output_path)
        .option("checkpointLocation", checkpoint_dir)
        .trigger(processingTime="1 minute")
        .start()
    )

    query.awaitTermination()
```

## Testing Beam Pipelines

```python
import apache_beam as beam
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to
import json
import unittest


class TestSensorPipeline(unittest.TestCase):
    # Unit tests for the sensor pipeline transforms.
    # Best practice: test DoFns in isolation, then test the pipeline end-to-end.
    # Beam's TestPipeline provides a local runner for deterministic testing.

    def test_parse_valid_reading(self) -> None:
        valid_msg = json.dumps({
            "sensor_id": "s1",
            "temperature": 25.5,
            "humidity": 60.0,
            "event_time": 1700000000.0,
        }).encode("utf-8")

        with TestPipeline() as p:
            output = (
                p
                | beam.Create([valid_msg])
                | beam.ParDo(ParseSensorReading()).with_outputs(
                    ParseSensorReading.DEAD_LETTER_TAG,
                    main=ParseSensorReading.VALID_TAG,
                )
            )
            # Verify valid readings are emitted
            assert_that(
                output[ParseSensorReading.VALID_TAG]
                | beam.Map(lambda r: r.sensor_id),
                equal_to(["s1"]),
                label="ValidOutput",
            )

    def test_parse_malformed_json(self) -> None:
        bad_msg = b"not-json"
        with TestPipeline() as p:
            output = (
                p
                | beam.Create([bad_msg])
                | beam.ParDo(ParseSensorReading()).with_outputs(
                    ParseSensorReading.DEAD_LETTER_TAG,
                    main=ParseSensorReading.VALID_TAG,
                )
            )
            # Malformed data goes to dead letter queue
            assert_that(
                output[ParseSensorReading.DEAD_LETTER_TAG]
                | beam.Map(lambda r: r["reason"]),
                equal_to(["Expecting value: line 1 column 1 (char 0)"]),
                label="DeadLetterOutput",
            )

    def test_temperature_out_of_range_goes_to_dead_letter(self) -> None:
        hot_msg = json.dumps({
            "sensor_id": "s1",
            "temperature": 999.0,  # Way out of range
            "humidity": 50.0,
            "event_time": 1700000000.0,
        }).encode("utf-8")

        with TestPipeline() as p:
            output = (
                p
                | beam.Create([hot_msg])
                | beam.ParDo(ParseSensorReading()).with_outputs(
                    ParseSensorReading.DEAD_LETTER_TAG,
                    main=ParseSensorReading.VALID_TAG,
                )
            )
            assert_that(
                output[ParseSensorReading.DEAD_LETTER_TAG]
                | beam.Map(lambda r: r["reason"]),
                equal_to(["temperature_out_of_range"]),
                label="OutOfRangeDeadLetter",
            )


if __name__ == "__main__":
    unittest.main()
```

## Summary and Key Takeaways

- **Batch is a special case of streaming** — Beam's unified model proves this. Write
  transformations once, run in either mode by swapping the runner.
- **Windowing answers "where in event time"** — fixed for regular aggregation, sliding
  for moving averages, session for user behavior. The trade-off is compute cost versus
  granularity.
- **Watermarks handle late data** — they represent "the system's estimate of completeness."
  A common mistake is setting watermarks too tight (dropping late data) or too loose
  (high latency before results finalize). Best practice: allow 10-30 minutes of lateness
  for most IoT pipelines.
- **Exactly-once processing**: Beam achieves it through per-element acknowledgment and
  idempotent sinks; Spark achieves it through checkpoint-based WAL. However, exactly-once
  is an end-to-end property — the sink must also support it (BigQuery does, S3 append does
  not natively).
- **Dead letter queues** are essential — never drop bad data silently. Route it to a
  separate table for debugging and monitoring pipeline health.
"""
    ),
    # --- 4. Data Quality Monitoring ---
    (
        "data_quality_monitoring_drift_detection",
        "Explain data quality monitoring in production ML systems — covering statistical drift "
        "detection methods including PSI, KL divergence, and the KS test, schema validation for "
        "evolving data sources, anomaly detection in data pipeline metrics, and how to build an "
        "automated data quality framework with alerting. Include complete Python implementations.",
        r"""
# Data Quality Monitoring: Drift Detection, Schema Validation, and Anomaly Detection

## Why Data Quality Is the #1 Production ML Problem

Model performance degrades not because the model changes, but because **the data changes**.
A fraud detection model trained on 2024 data will silently fail when merchant categories
shift, transaction patterns evolve, or upstream ETL introduces bugs. The insidious part
is that the model continues making predictions — it just makes **wrong** predictions with
high confidence.

Data quality monitoring must detect three types of problems:

```
Data Quality Problem Taxonomy:

1. SCHEMA PROBLEMS (immediate, detectable)
   - Missing columns, type changes, new categories
   - Detection: schema validation, contract tests
   - Impact: pipeline crashes or silent misinterpretation

2. DISTRIBUTION DRIFT (gradual, statistical)
   - Feature distributions shift over time
   - Detection: PSI, KL divergence, KS test
   - Impact: model predictions become unreliable

3. DATA ANOMALIES (sudden, point-in-time)
   - NULL spikes, duplicate surges, volume drops
   - Detection: statistical process control, z-scores
   - Impact: corrupted training data or serving features
```

Therefore, a comprehensive data quality framework must address all three simultaneously.
A common mistake is monitoring only schema changes while ignoring distribution drift —
the data "looks right" structurally but is semantically different.

## Statistical Drift Detection Methods

### Population Stability Index (PSI)

PSI measures **how much a distribution has shifted** relative to a baseline. It was
originally developed for credit scoring and is the most widely used drift metric in
industry because it is intuitive and has well-established thresholds.

```
PSI Formula:
  PSI = Σ (P_actual(i) - P_expected(i)) * ln(P_actual(i) / P_expected(i))

  where i iterates over histogram bins

Interpretation:
  PSI < 0.1:  No significant shift
  0.1 ≤ PSI < 0.25: Moderate shift — investigate
  PSI ≥ 0.25: Significant shift — likely model retraining needed
```

### KL Divergence

KL divergence measures the **information lost** when approximating one distribution
with another. Unlike PSI, it is asymmetric: D_KL(P||Q) != D_KL(Q||P). Best practice
is to use the symmetric Jensen-Shannon divergence (JSD) which averages both directions.

### Kolmogorov-Smirnov Test

The KS test is a **non-parametric hypothesis test** that measures the maximum distance
between two cumulative distribution functions. It provides a p-value, making it useful
for automated statistical decision-making. However, the pitfall is that with large sample
sizes, even trivially small differences become "statistically significant" — therefore
always pair the p-value with effect size (the KS statistic itself).

## Complete Data Quality Framework

```python
import numpy as np
import pandas as pd
from scipy import stats
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class DriftSeverity(Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DriftResult:
    # Result of a single drift check on one feature
    feature_name: str
    metric_name: str
    metric_value: float
    severity: DriftSeverity
    threshold: float
    p_value: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQualityReport:
    # Comprehensive data quality report for a dataset
    timestamp: datetime
    dataset_name: str
    row_count: int
    drift_results: List[DriftResult] = field(default_factory=list)
    schema_violations: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    overall_healthy: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "dataset_name": self.dataset_name,
            "row_count": self.row_count,
            "overall_healthy": self.overall_healthy,
            "drift_count": len([d for d in self.drift_results
                               if d.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)]),
            "schema_violation_count": len(self.schema_violations),
            "anomaly_count": len(self.anomalies),
        }


class StatisticalDriftDetector:
    # Detects distribution drift using multiple statistical methods.
    #
    # Best practice: use multiple tests and aggregate because each method has
    # different strengths. PSI is best for binned categorical-like features,
    # KS test for continuous features, and JSD for general-purpose comparison.

    def __init__(self, n_bins: int = 10, psi_threshold: float = 0.25):
        self.n_bins = n_bins
        self.psi_threshold = psi_threshold

    def compute_psi(
        self,
        reference: np.ndarray,
        current: np.ndarray,
    ) -> float:
        # Compute Population Stability Index between reference and current.
        #
        # Because PSI uses histogram bins, the bin edges must come from the
        # REFERENCE distribution (not current) to measure how current deviates
        # from the expected baseline.

        # Create bins from reference distribution
        _, bin_edges = np.histogram(reference, bins=self.n_bins)

        # Compute proportions in each bin
        ref_counts, _ = np.histogram(reference, bins=bin_edges)
        cur_counts, _ = np.histogram(current, bins=bin_edges)

        # Convert to proportions with smoothing to avoid division by zero
        # Pitfall: without smoothing, empty bins cause log(0) = -inf
        epsilon = 1e-6
        ref_pct = (ref_counts + epsilon) / (ref_counts.sum() + epsilon * self.n_bins)
        cur_pct = (cur_counts + epsilon) / (cur_counts.sum() + epsilon * self.n_bins)

        # PSI = sum((cur - ref) * ln(cur / ref))
        psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
        return float(psi)

    def compute_kl_divergence(
        self,
        reference: np.ndarray,
        current: np.ndarray,
    ) -> Tuple[float, float]:
        # Compute KL divergence and symmetric Jensen-Shannon divergence.
        # Returns (kl_divergence, js_divergence).

        _, bin_edges = np.histogram(reference, bins=self.n_bins)

        ref_counts, _ = np.histogram(reference, bins=bin_edges)
        cur_counts, _ = np.histogram(current, bins=bin_edges)

        epsilon = 1e-6
        ref_prob = (ref_counts + epsilon) / (ref_counts.sum() + epsilon * self.n_bins)
        cur_prob = (cur_counts + epsilon) / (cur_counts.sum() + epsilon * self.n_bins)

        # KL(current || reference)
        kl_div = float(np.sum(cur_prob * np.log(cur_prob / ref_prob)))

        # Jensen-Shannon divergence (symmetric, bounded [0, ln(2)])
        m = 0.5 * (ref_prob + cur_prob)
        js_div = float(0.5 * np.sum(ref_prob * np.log(ref_prob / m))
                        + 0.5 * np.sum(cur_prob * np.log(cur_prob / m)))

        return kl_div, js_div

    def compute_ks_test(
        self,
        reference: np.ndarray,
        current: np.ndarray,
    ) -> Tuple[float, float]:
        # Two-sample Kolmogorov-Smirnov test.
        # Returns (ks_statistic, p_value).
        #
        # However, with large sample sizes the KS test becomes overly sensitive
        # (even trivial differences produce p < 0.05). Therefore always check
        # the KS statistic magnitude alongside the p-value.

        ks_stat, p_value = stats.ks_2samp(reference, current)
        return float(ks_stat), float(p_value)

    def detect_drift(
        self,
        feature_name: str,
        reference: np.ndarray,
        current: np.ndarray,
    ) -> DriftResult:
        # Run all drift tests on a single feature and return aggregated result.

        psi = self.compute_psi(reference, current)
        kl_div, js_div = self.compute_kl_divergence(reference, current)
        ks_stat, ks_p = self.compute_ks_test(reference, current)

        # Determine severity based on PSI (primary) + KS (secondary)
        if psi >= 0.25 and ks_stat >= 0.1:
            severity = DriftSeverity.CRITICAL
        elif psi >= 0.25 or (ks_p < 0.001 and ks_stat >= 0.1):
            severity = DriftSeverity.HIGH
        elif psi >= 0.1:
            severity = DriftSeverity.MODERATE
        elif psi >= 0.05:
            severity = DriftSeverity.LOW
        else:
            severity = DriftSeverity.NONE

        return DriftResult(
            feature_name=feature_name,
            metric_name="psi",
            metric_value=psi,
            severity=severity,
            threshold=self.psi_threshold,
            p_value=ks_p,
            details={
                "psi": psi,
                "kl_divergence": kl_div,
                "js_divergence": js_div,
                "ks_statistic": ks_stat,
                "ks_p_value": ks_p,
                "reference_mean": float(np.mean(reference)),
                "current_mean": float(np.mean(current)),
                "reference_std": float(np.std(reference)),
                "current_std": float(np.std(current)),
            },
        )
```

## Schema Validation and Anomaly Detection

```python
@dataclass
class SchemaExpectation:
    # Define expected schema for a dataset column
    column_name: str
    dtype: str  # "int64", "float64", "object", "datetime64"
    nullable: bool = True
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    max_null_pct: float = 0.05


class SchemaValidator:
    # Validates that a DataFrame conforms to expected schema.
    # Best practice: define schema expectations alongside feature definitions
    # in the feature store, not as a separate artifact.

    def __init__(self, expectations: List[SchemaExpectation]):
        self.expectations = {e.column_name: e for e in expectations}

    def validate(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []

        # Check for missing columns
        expected_cols = set(self.expectations.keys())
        actual_cols = set(df.columns)
        missing = expected_cols - actual_cols
        extra = actual_cols - expected_cols

        for col in missing:
            violations.append({
                "type": "missing_column",
                "column": col,
                "severity": "critical",
                "message": f"Expected column '{col}' not found in dataset",
            })

        if extra:
            violations.append({
                "type": "extra_columns",
                "columns": list(extra),
                "severity": "warning",
                "message": f"Unexpected columns: {extra}",
            })

        # Validate each expected column
        for col_name, expectation in self.expectations.items():
            if col_name not in df.columns:
                continue

            col = df[col_name]

            # Null check
            null_pct = col.isnull().mean()
            if null_pct > expectation.max_null_pct:
                violations.append({
                    "type": "null_spike",
                    "column": col_name,
                    "severity": "high" if null_pct > 0.5 else "moderate",
                    "null_pct": float(null_pct),
                    "threshold": expectation.max_null_pct,
                    "message": f"Null rate {null_pct:.2%} exceeds threshold "
                               f"{expectation.max_null_pct:.2%}",
                })

            # Range check for numeric columns
            if expectation.min_value is not None:
                below_min = (col < expectation.min_value).sum()
                if below_min > 0:
                    violations.append({
                        "type": "range_violation",
                        "column": col_name,
                        "severity": "high",
                        "count": int(below_min),
                        "message": f"{below_min} values below minimum "
                                   f"{expectation.min_value}",
                    })

            if expectation.max_value is not None:
                above_max = (col > expectation.max_value).sum()
                if above_max > 0:
                    violations.append({
                        "type": "range_violation",
                        "column": col_name,
                        "severity": "high",
                        "count": int(above_max),
                        "message": f"{above_max} values above maximum "
                                   f"{expectation.max_value}",
                    })

            # Categorical validation
            if expectation.allowed_values is not None:
                unexpected = set(col.dropna().unique()) - set(expectation.allowed_values)
                if unexpected:
                    violations.append({
                        "type": "unexpected_categories",
                        "column": col_name,
                        "severity": "moderate",
                        "unexpected_values": list(unexpected)[:20],
                        "message": f"Found {len(unexpected)} unexpected categories",
                    })

        return violations


class PipelineAnomalyDetector:
    # Detects anomalies in pipeline operational metrics using
    # statistical process control (SPC) methods.
    #
    # A common mistake is using static thresholds. However, pipeline
    # metrics are often seasonal (weekend traffic differs from weekday).
    # Therefore we use rolling z-scores with configurable windows.

    def __init__(
        self,
        lookback_days: int = 30,
        z_threshold: float = 3.0,
    ):
        self.lookback_days = lookback_days
        self.z_threshold = z_threshold

    def detect_anomalies(
        self,
        metric_history: pd.DataFrame,
        metric_column: str,
        timestamp_column: str = "timestamp",
    ) -> List[Dict[str, Any]]:
        # Detect anomalies in a time series of pipeline metrics.
        # Uses rolling z-score with day-of-week adjustment.

        df = metric_history.copy().sort_values(timestamp_column)
        df["day_of_week"] = pd.to_datetime(df[timestamp_column]).dt.dayofweek

        anomalies: List[Dict[str, Any]] = []

        # Compute rolling stats per day-of-week (handles seasonality)
        for dow in range(7):
            mask = df["day_of_week"] == dow
            subset = df[mask]

            if len(subset) < 4:
                continue

            rolling_mean = subset[metric_column].rolling(
                window=self.lookback_days // 7, min_periods=2
            ).mean()
            rolling_std = subset[metric_column].rolling(
                window=self.lookback_days // 7, min_periods=2
            ).std()

            z_scores = (subset[metric_column] - rolling_mean) / rolling_std.clip(lower=1e-6)

            # Flag points exceeding threshold
            anomaly_mask = z_scores.abs() > self.z_threshold
            for idx in subset[anomaly_mask].index:
                anomalies.append({
                    "timestamp": str(df.loc[idx, timestamp_column]),
                    "metric": metric_column,
                    "value": float(df.loc[idx, metric_column]),
                    "z_score": float(z_scores.loc[idx]),
                    "expected_mean": float(rolling_mean.loc[idx]),
                    "expected_std": float(rolling_std.loc[idx]),
                    "severity": "critical" if abs(z_scores.loc[idx]) > 5 else "high",
                })

        return anomalies
```

## Orchestrating the Full Quality Pipeline

```python
def run_data_quality_check(
    current_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    schema_expectations: List[SchemaExpectation],
    feature_columns: List[str],
    dataset_name: str = "training_data",
    psi_threshold: float = 0.25,
) -> DataQualityReport:
    # Run comprehensive data quality checks and produce a report.
    # This is the main entry point for automated quality monitoring.
    #
    # Best practice: run this after every ETL stage, not just at the end.
    # The earlier you catch problems, the cheaper they are to fix.

    report = DataQualityReport(
        timestamp=datetime.utcnow(),
        dataset_name=dataset_name,
        row_count=len(current_df),
    )

    # 1. Schema validation
    validator = SchemaValidator(schema_expectations)
    report.schema_violations = validator.validate(current_df)

    # 2. Distribution drift for each feature
    drift_detector = StatisticalDriftDetector(psi_threshold=psi_threshold)
    for col in feature_columns:
        if col in current_df.columns and col in reference_df.columns:
            ref_vals = reference_df[col].dropna().values
            cur_vals = current_df[col].dropna().values
            if len(ref_vals) > 0 and len(cur_vals) > 0:
                drift_result = drift_detector.detect_drift(col, ref_vals, cur_vals)
                report.drift_results.append(drift_result)

    # 3. Determine overall health
    critical_drifts = [
        d for d in report.drift_results
        if d.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)
    ]
    critical_schema = [
        v for v in report.schema_violations if v.get("severity") == "critical"
    ]

    report.overall_healthy = len(critical_drifts) == 0 and len(critical_schema) == 0

    if not report.overall_healthy:
        logger.warning(
            f"Data quality check FAILED for {dataset_name}: "
            f"{len(critical_drifts)} drift alerts, {len(critical_schema)} schema violations"
        )

    return report
```

## Summary and Key Takeaways

- **Three types of data problems**: Schema changes (detectable immediately), distribution
  drift (requires statistical tests), and point anomalies (requires time series monitoring).
  A common mistake is monitoring only one type.
- **PSI is the workhorse metric** for drift detection — well-established thresholds (0.1/0.25)
  and intuitive interpretation. However, always pair it with the KS test for continuous
  features because PSI's binning can miss distributional shape changes.
- **Schema validation is a contract test** — define expectations alongside feature definitions,
  not as afterthoughts. Best practice: fail the pipeline immediately on critical schema
  violations rather than propagating bad data.
- **Seasonal adjustment matters** — pipeline metrics vary by day of week and time of day.
  Therefore, use rolling z-scores with day-of-week stratification rather than static thresholds.
  The pitfall of static thresholds is excessive false alarms on weekends.
- **Monitor at every ETL stage**, not just the final output. Catching a NULL spike after
  ingestion is far cheaper than discovering it after a 4-hour training run fails.
"""
    ),
    # --- 5. Model Monitoring in Production ---
    (
        "model_monitoring_production_drift_retraining",
        "Explain comprehensive model monitoring in production — covering concept drift detection, "
        "prediction quality monitoring with and without ground truth, feature attribution drift "
        "using SHAP values, automated retraining triggers based on performance degradation, and "
        "building a complete monitoring system. Include Python implementations with type hints.",
        r"""
# Model Monitoring in Production: Drift, Quality, and Automated Retraining

## The Production ML Monitoring Stack

Deploying a model is **not the end** — it is the beginning of a monitoring lifecycle. Models
degrade for reasons that unit tests and offline evaluation cannot catch: the world changes,
user behavior shifts, and upstream data evolves. Without monitoring, teams discover problems
only when business metrics drop — often weeks after the model started failing.

A comprehensive monitoring system tracks four layers:

```
Model Monitoring Stack:

Layer 4: BUSINESS METRICS      (revenue, conversion, churn)
  ^      Lagging — takes weeks to surface
  |
Layer 3: PREDICTION QUALITY    (accuracy, precision, recall, calibration)
  ^      Requires ground truth — may be delayed hours/days/weeks
  |
Layer 2: OUTPUT DRIFT           (prediction distribution, confidence scores)
  ^      Immediate — no ground truth needed
  |
Layer 1: INPUT DRIFT            (feature distribution, correlations)
         Immediate — detectable before model even runs

Best practice: monitor ALL layers. Common mistake: only monitoring
Layer 4 (business metrics) and missing the root cause.
```

Therefore, you should **detect problems at the lowest layer possible** because earlier
detection means faster remediation. Input drift (Layer 1) is detectable in real-time;
business metric drops (Layer 4) take weeks to manifest.

## Concept Drift vs Data Drift

**Data drift** (covariate shift): the input distribution P(X) changes, but the relationship
P(Y|X) stays the same. Example: more high-value transactions in December because of holiday
shopping. The model may still be correct, but it sees more inputs in regions where it has
less training data.

**Concept drift**: the relationship P(Y|X) changes — the same inputs should now produce
different outputs. Example: a new type of fraud emerges that looks like legitimate
transactions under the old feature set. This is far more dangerous because the model is
**fundamentally wrong**, not just uncertain.

```
Data Drift:    P(X) changes, P(Y|X) stable
               Solution: retrain on new distribution, features still valid

Concept Drift: P(Y|X) changes
               Solution: may need new features, model architecture changes
               Much harder to detect without ground truth

Virtual Drift: P(Y|X) changes gradually over time
               Solution: continuous retraining with recency weighting
```

## Complete Model Monitor Implementation

```python
import numpy as np
import pandas as pd
from scipy import stats
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import logging
import json

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MonitoringAlert:
    # Single alert generated by the monitoring system
    timestamp: datetime
    alert_level: AlertLevel
    monitor_name: str
    metric_name: str
    metric_value: float
    threshold: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelPerformanceSnapshot:
    # Point-in-time snapshot of model performance
    timestamp: datetime
    prediction_count: int
    mean_confidence: float
    prediction_distribution: Dict[str, float]
    feature_means: Dict[str, float]
    feature_stds: Dict[str, float]
    # Ground truth metrics (may be None if delayed)
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    calibration_error: Optional[float] = None


class PredictionDistributionMonitor:
    # Monitors the distribution of model predictions over time.
    # This is the fastest signal available because it requires no ground truth.
    #
    # The key insight: if the prediction distribution shifts significantly
    # without a known cause, something is wrong — either input drift,
    # concept drift, or a pipeline bug. However, prediction shift alone
    # does not tell you WHICH one, so it triggers investigation.

    def __init__(
        self,
        reference_predictions: np.ndarray,
        window_size: int = 1000,
        psi_threshold: float = 0.2,
        confidence_drift_threshold: float = 0.1,
    ):
        self.reference_predictions = reference_predictions
        self.reference_mean = float(np.mean(reference_predictions))
        self.reference_std = float(np.std(reference_predictions))
        self.window_size = window_size
        self.psi_threshold = psi_threshold
        self.confidence_drift_threshold = confidence_drift_threshold
        self.prediction_buffer: deque = deque(maxlen=window_size)

    def add_prediction(self, prediction: float, confidence: float) -> Optional[MonitoringAlert]:
        # Add a new prediction and check for drift.
        # Returns alert if drift detected, None otherwise.

        self.prediction_buffer.append({
            "prediction": prediction,
            "confidence": confidence,
            "timestamp": datetime.utcnow(),
        })

        if len(self.prediction_buffer) < self.window_size:
            return None

        current_preds = np.array([p["prediction"] for p in self.prediction_buffer])
        current_confs = np.array([p["confidence"] for p in self.prediction_buffer])

        # Check prediction distribution drift (PSI)
        psi = self._compute_psi(self.reference_predictions, current_preds)

        if psi > self.psi_threshold:
            return MonitoringAlert(
                timestamp=datetime.utcnow(),
                alert_level=AlertLevel.CRITICAL if psi > 0.4 else AlertLevel.WARNING,
                monitor_name="prediction_distribution",
                metric_name="psi",
                metric_value=psi,
                threshold=self.psi_threshold,
                message=f"Prediction distribution drift detected: PSI={psi:.4f} "
                        f"(threshold={self.psi_threshold})",
                metadata={
                    "reference_mean": self.reference_mean,
                    "current_mean": float(np.mean(current_preds)),
                    "confidence_mean": float(np.mean(current_confs)),
                },
            )

        # Check confidence score drift
        conf_shift = abs(float(np.mean(current_confs)) - self.reference_mean)
        if conf_shift > self.confidence_drift_threshold:
            return MonitoringAlert(
                timestamp=datetime.utcnow(),
                alert_level=AlertLevel.WARNING,
                monitor_name="confidence_drift",
                metric_name="mean_confidence_shift",
                metric_value=conf_shift,
                threshold=self.confidence_drift_threshold,
                message=f"Model confidence shifted by {conf_shift:.4f}",
            )

        return None

    def _compute_psi(self, reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
        _, bin_edges = np.histogram(reference, bins=n_bins)
        ref_counts, _ = np.histogram(reference, bins=bin_edges)
        cur_counts, _ = np.histogram(current, bins=bin_edges)
        epsilon = 1e-6
        ref_pct = (ref_counts + epsilon) / (ref_counts.sum() + epsilon * n_bins)
        cur_pct = (cur_counts + epsilon) / (cur_counts.sum() + epsilon * n_bins)
        return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


class FeatureAttributionMonitor:
    # Monitors drift in feature importance using SHAP values.
    #
    # The rationale: even if individual feature distributions look stable,
    # the model's RELIANCE on features may shift, indicating concept drift.
    # For example, if the model suddenly relies heavily on a feature that
    # was previously unimportant, the decision boundary has shifted.
    #
    # This is a best practice for catching concept drift without ground truth
    # because it looks at HOW the model is making decisions, not just WHAT
    # it predicts.

    def __init__(
        self,
        reference_shap_values: np.ndarray,
        feature_names: List[str],
        importance_drift_threshold: float = 0.15,
    ):
        # reference_shap_values: shape (n_samples, n_features)
        self.feature_names = feature_names
        self.importance_drift_threshold = importance_drift_threshold

        # Compute reference feature importance (mean |SHAP|)
        self.reference_importance = np.mean(np.abs(reference_shap_values), axis=0)
        # Normalize to proportions
        total = self.reference_importance.sum()
        if total > 0:
            self.reference_importance = self.reference_importance / total

    def check_attribution_drift(
        self,
        current_shap_values: np.ndarray,
    ) -> List[MonitoringAlert]:
        # Compare current SHAP-based feature importance to reference.
        # Returns alerts for features whose importance shifted significantly.

        current_importance = np.mean(np.abs(current_shap_values), axis=0)
        total = current_importance.sum()
        if total > 0:
            current_importance = current_importance / total

        alerts: List[MonitoringAlert] = []

        for i, feature in enumerate(self.feature_names):
            ref_imp = float(self.reference_importance[i])
            cur_imp = float(current_importance[i])
            shift = abs(cur_imp - ref_imp)

            if shift > self.importance_drift_threshold:
                direction = "increased" if cur_imp > ref_imp else "decreased"
                alerts.append(MonitoringAlert(
                    timestamp=datetime.utcnow(),
                    alert_level=AlertLevel.WARNING,
                    monitor_name="feature_attribution",
                    metric_name=f"importance_shift_{feature}",
                    metric_value=shift,
                    threshold=self.importance_drift_threshold,
                    message=f"Feature '{feature}' importance {direction}: "
                            f"{ref_imp:.3f} -> {cur_imp:.3f} (shift={shift:.3f})",
                    metadata={
                        "feature": feature,
                        "reference_importance": ref_imp,
                        "current_importance": cur_imp,
                        "direction": direction,
                    },
                ))

        return alerts
```

## Automated Retraining Trigger System

```python
@dataclass
class RetrainingDecision:
    # Encapsulates the decision of whether to retrain
    should_retrain: bool
    reason: str
    urgency: str  # "immediate", "scheduled", "none"
    triggered_by: List[str]
    recommended_config: Dict[str, Any] = field(default_factory=dict)


class AutomatedRetrainingTrigger:
    # Decides when to retrain based on monitoring signals.
    #
    # A common mistake is setting a single threshold (e.g., "retrain when
    # accuracy drops below 0.9"). However, this is brittle because:
    # 1. Accuracy may fluctuate naturally (weekday vs weekend traffic)
    # 2. Ground truth may be delayed, so accuracy lags by hours/days
    # 3. A single bad batch of data can trigger unnecessary retraining
    #
    # Best practice: use a weighted scoring system across multiple signals
    # with cooldown periods to prevent thrashing.

    def __init__(
        self,
        min_accuracy: float = 0.90,
        max_psi_drift: float = 0.25,
        max_attribution_shift: float = 0.20,
        cooldown_hours: float = 24.0,
        consecutive_alerts_required: int = 3,
    ):
        self.min_accuracy = min_accuracy
        self.max_psi_drift = max_psi_drift
        self.max_attribution_shift = max_attribution_shift
        self.cooldown_hours = cooldown_hours
        self.consecutive_alerts_required = consecutive_alerts_required
        self.alert_history: List[MonitoringAlert] = []
        self.last_retraining: Optional[datetime] = None

    def evaluate(
        self,
        alerts: List[MonitoringAlert],
        current_metrics: Optional[ModelPerformanceSnapshot] = None,
    ) -> RetrainingDecision:
        # Evaluate whether retraining should be triggered.
        #
        # The decision is based on a scoring system:
        #   - Performance drop below threshold: +3 points (immediate)
        #   - Prediction distribution drift: +2 points
        #   - Feature attribution drift: +2 points
        #   - Input feature drift: +1 point
        # Retrain if score >= 3 (tunable)

        # Check cooldown — prevent retraining thrashing
        if self.last_retraining:
            hours_since = (datetime.utcnow() - self.last_retraining).total_seconds() / 3600
            if hours_since < self.cooldown_hours:
                return RetrainingDecision(
                    should_retrain=False,
                    reason=f"Cooldown active: {self.cooldown_hours - hours_since:.1f}h remaining",
                    urgency="none",
                    triggered_by=[],
                )

        self.alert_history.extend(alerts)

        # Score the current state
        score = 0.0
        triggers: List[str] = []

        # Performance-based trigger (requires ground truth)
        if current_metrics and current_metrics.accuracy is not None:
            if current_metrics.accuracy < self.min_accuracy:
                score += 3.0
                triggers.append(
                    f"accuracy={current_metrics.accuracy:.3f} < {self.min_accuracy}"
                )

        # Alert-based triggers
        recent_window = datetime.utcnow() - timedelta(hours=6)
        recent_alerts = [
            a for a in self.alert_history
            if a.timestamp > recent_window
        ]

        critical_prediction_alerts = [
            a for a in recent_alerts
            if a.monitor_name == "prediction_distribution"
            and a.alert_level == AlertLevel.CRITICAL
        ]
        if len(critical_prediction_alerts) >= self.consecutive_alerts_required:
            score += 2.0
            triggers.append(
                f"prediction_drift: {len(critical_prediction_alerts)} consecutive alerts"
            )

        attribution_alerts = [
            a for a in recent_alerts
            if a.monitor_name == "feature_attribution"
        ]
        if len(attribution_alerts) >= 2:
            score += 2.0
            triggers.append(
                f"attribution_drift: {len(attribution_alerts)} features shifted"
            )

        # Make decision
        if score >= 3.0:
            urgency = "immediate" if score >= 5.0 else "scheduled"
            return RetrainingDecision(
                should_retrain=True,
                reason=f"Retraining score {score:.1f} >= threshold 3.0",
                urgency=urgency,
                triggered_by=triggers,
                recommended_config={
                    "use_recent_data_weight": True,
                    "lookback_days": 90 if urgency == "immediate" else 180,
                    "include_hard_examples": True,
                    "priority": "high" if urgency == "immediate" else "normal",
                },
            )

        return RetrainingDecision(
            should_retrain=False,
            reason=f"Retraining score {score:.1f} < threshold 3.0",
            urgency="none",
            triggered_by=triggers,
        )

    def record_retraining(self) -> None:
        # Call after retraining completes to reset cooldown
        self.last_retraining = datetime.utcnow()
        self.alert_history.clear()
```

## Integration: Full Monitoring Loop

```python
def run_monitoring_cycle(
    model: Any,
    feature_data: pd.DataFrame,
    predictions: np.ndarray,
    confidence_scores: np.ndarray,
    reference_predictions: np.ndarray,
    reference_shap: np.ndarray,
    feature_names: List[str],
    ground_truth: Optional[np.ndarray] = None,
) -> Tuple[List[MonitoringAlert], RetrainingDecision]:
    # Run a complete monitoring cycle — called periodically (e.g., hourly).
    #
    # This orchestrates all monitors and feeds results into the
    # retraining trigger. Because monitors are independent, they
    # can run in parallel for latency optimization.

    all_alerts: List[MonitoringAlert] = []

    # 1. Prediction distribution monitoring
    pred_monitor = PredictionDistributionMonitor(reference_predictions)
    for pred, conf in zip(predictions, confidence_scores):
        alert = pred_monitor.add_prediction(float(pred), float(conf))
        if alert:
            all_alerts.append(alert)

    # 2. Feature attribution monitoring (SHAP-based)
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        current_shap = explainer.shap_values(feature_data)

        attr_monitor = FeatureAttributionMonitor(
            reference_shap, feature_names
        )
        attr_alerts = attr_monitor.check_attribution_drift(current_shap)
        all_alerts.extend(attr_alerts)
    except Exception as e:
        logger.warning(f"SHAP computation failed: {e}")

    # 3. Build performance snapshot
    snapshot = ModelPerformanceSnapshot(
        timestamp=datetime.utcnow(),
        prediction_count=len(predictions),
        mean_confidence=float(np.mean(confidence_scores)),
        prediction_distribution={
            "mean": float(np.mean(predictions)),
            "std": float(np.std(predictions)),
            "p25": float(np.percentile(predictions, 25)),
            "p75": float(np.percentile(predictions, 75)),
        },
        feature_means={f: float(feature_data[f].mean()) for f in feature_names},
        feature_stds={f: float(feature_data[f].std()) for f in feature_names},
    )

    # Add ground truth metrics if available
    if ground_truth is not None:
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        binary_preds = (predictions > 0.5).astype(int)
        snapshot.accuracy = float(accuracy_score(ground_truth, binary_preds))
        snapshot.precision = float(precision_score(ground_truth, binary_preds, zero_division=0))
        snapshot.recall = float(recall_score(ground_truth, binary_preds, zero_division=0))
        snapshot.f1 = float(f1_score(ground_truth, binary_preds, zero_division=0))

    # 4. Evaluate retraining decision
    trigger = AutomatedRetrainingTrigger()
    decision = trigger.evaluate(all_alerts, snapshot)

    if decision.should_retrain:
        logger.critical(
            f"RETRAINING TRIGGERED ({decision.urgency}): {decision.reason} | "
            f"Triggers: {decision.triggered_by}"
        )

    return all_alerts, decision
```

## Summary and Key Takeaways

- **Monitor all four layers**: input drift, output drift, prediction quality, and business
  metrics. The common mistake is only watching business metrics, which creates a weeks-long
  feedback delay.
- **Concept drift vs data drift**: Data drift (P(X) shifts) is detectable and often benign;
  concept drift (P(Y|X) shifts) is dangerous and harder to catch. Feature attribution
  monitoring via SHAP is the best practice for detecting concept drift without ground truth.
- **Prediction distribution is the fastest signal** — no ground truth needed, detectable
  in real-time. However, it only tells you THAT something changed, not WHY. Therefore,
  combine it with input drift analysis for root-cause diagnosis.
- **Automated retraining needs safeguards**: Use a weighted scoring system across multiple
  signals, require consecutive alerts (not one-shot), and implement cooldown periods. The
  pitfall of naive retraining triggers is thrashing — retraining every hour wastes compute
  and can introduce instability.
- **Ground truth delay is the fundamental challenge** — in fraud detection, labels arrive
  days or weeks later. Best practice: use proxy metrics (prediction confidence, feature
  drift) for immediate detection and ground truth metrics for confirmation.
"""
    ),
]
