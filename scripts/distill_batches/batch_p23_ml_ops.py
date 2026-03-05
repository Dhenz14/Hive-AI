"""ML Operations — model serving, experiment tracking, feature stores, model monitoring."""

PAIRS = [
    (
        "ml/model-serving",
        "Show how to serve ML models in production with FastAPI. Include batching, async inference, model versioning, and A/B testing.",
        '''Production ML model serving with FastAPI:

```python
import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Model registry ---

class ModelVersion:
    def __init__(self, path: str, version: str):
        self.version = version
        self.model = self._load(path)
        self.load_time = time.time()

    def _load(self, path: str):
        import joblib
        return joblib.load(path)

    def predict(self, features: np.ndarray) -> np.ndarray:
        return self.model.predict(features)

class ModelRegistry:
    def __init__(self):
        self.models: dict[str, ModelVersion] = {}
        self.active_version: Optional[str] = None
        self.canary_version: Optional[str] = None
        self.canary_weight: float = 0.0  # 0-1

    def load(self, name: str, path: str, version: str):
        self.models[version] = ModelVersion(path, version)
        print(f"Loaded model {name} v{version}")

    def set_active(self, version: str):
        if version not in self.models:
            raise ValueError(f"Model version {version} not loaded")
        self.active_version = version

    def set_canary(self, version: str, weight: float):
        self.canary_version = version
        self.canary_weight = weight

    def get_model(self) -> tuple[ModelVersion, str]:
        """Route to active or canary model based on weight."""
        if (self.canary_version and self.canary_weight > 0
                and np.random.random() < self.canary_weight):
            return self.models[self.canary_version], "canary"
        return self.models[self.active_version], "active"

registry = ModelRegistry()

# --- Request batching for throughput ---

@dataclass
class PredictionRequest:
    features: np.ndarray
    future: asyncio.Future

class BatchPredictor:
    """Accumulate requests and predict in batches for GPU efficiency."""

    def __init__(self, max_batch: int = 32, max_wait_ms: float = 50):
        self.max_batch = max_batch
        self.max_wait = max_wait_ms / 1000
        self.queue: asyncio.Queue[PredictionRequest] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._task = asyncio.create_task(self._batch_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    async def predict(self, features: np.ndarray) -> np.ndarray:
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        await self.queue.put(PredictionRequest(features, future))
        return await future

    async def _batch_loop(self):
        while True:
            batch: list[PredictionRequest] = []

            # Wait for first request
            req = await self.queue.get()
            batch.append(req)

            # Collect more requests up to max_batch or max_wait
            deadline = time.monotonic() + self.max_wait
            while len(batch) < self.max_batch:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    req = await asyncio.wait_for(
                        self.queue.get(), timeout=remaining
                    )
                    batch.append(req)
                except asyncio.TimeoutError:
                    break

            # Run batch prediction
            try:
                features = np.vstack([r.features for r in batch])
                model, variant = registry.get_model()
                predictions = model.predict(features)

                for i, req in enumerate(batch):
                    req.future.set_result(predictions[i])
            except Exception as e:
                for req in batch:
                    if not req.future.done():
                        req.future.set_exception(e)

batcher = BatchPredictor(max_batch=32, max_wait_ms=50)

# --- FastAPI app ---

class PredictRequest(BaseModel):
    features: list[float]

class PredictResponse(BaseModel):
    prediction: float
    model_version: str
    latency_ms: float

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load models
    registry.load("recommender", "models/v1.joblib", "v1")
    registry.load("recommender", "models/v2.joblib", "v2")
    registry.set_active("v1")
    registry.set_canary("v2", weight=0.1)  # 10% canary
    await batcher.start()
    yield
    # Shutdown
    await batcher.stop()

app = FastAPI(lifespan=lifespan)

@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    start = time.perf_counter()
    features = np.array(req.features).reshape(1, -1)

    prediction = await batcher.predict(features)
    model, variant = registry.get_model()

    return PredictResponse(
        prediction=float(prediction),
        model_version=model.version,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
    )

@app.post("/admin/canary")
async def set_canary(version: str, weight: float):
    registry.set_canary(version, weight)
    return {"status": "ok", "canary": version, "weight": weight}

@app.post("/admin/promote")
async def promote_canary():
    if registry.canary_version:
        registry.set_active(registry.canary_version)
        registry.canary_version = None
        registry.canary_weight = 0.0
    return {"active": registry.active_version}
```

Key patterns:
- **Request batching** — accumulate requests, predict in batch (GPU-efficient)
- **Model registry** — load multiple versions, hot-swap without restart
- **Canary routing** — A/B test models with configurable traffic split
- **Async inference** — non-blocking prediction with Future-based batching'''
    ),
    (
        "ml/experiment-tracking",
        "Show how to track ML experiments with MLflow. Include metric logging, model registration, artifact management, and comparison.",
        '''ML experiment tracking with MLflow:

```python
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    classification_report, confusion_matrix, roc_auc_score,
)
import numpy as np
import pandas as pd
import json
import matplotlib.pyplot as plt

# --- Setup ---
mlflow.set_tracking_uri("http://mlflow-server:5000")
mlflow.set_experiment("fraud-detection")

# --- Training with full tracking ---

def train_and_track(X_train, y_train, X_test, y_test, params: dict):
    with mlflow.start_run(run_name=f"rf-{params.get('n_estimators', 100)}") as run:

        # Log parameters
        mlflow.log_params(params)
        mlflow.log_param("dataset_size", len(X_train))
        mlflow.log_param("feature_count", X_train.shape[1])
        mlflow.log_param("positive_ratio", y_train.mean())

        # Train model
        model = RandomForestClassifier(**params, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)

        # Predictions
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        # Log metrics
        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall": recall_score(y_test, y_pred),
            "f1": f1_score(y_test, y_pred),
            "roc_auc": roc_auc_score(y_test, y_proba),
        }
        mlflow.log_metrics(metrics)

        # Cross-validation scores
        cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="f1")
        mlflow.log_metric("cv_f1_mean", cv_scores.mean())
        mlflow.log_metric("cv_f1_std", cv_scores.std())

        # Log feature importance
        importance = pd.DataFrame({
            "feature": feature_names,
            "importance": model.feature_importances_,
        }).sort_values("importance", ascending=False)
        mlflow.log_text(importance.to_csv(index=False), "feature_importance.csv")

        # Log confusion matrix as artifact
        fig, ax = plt.subplots(figsize=(8, 6))
        cm = confusion_matrix(y_test, y_pred)
        ax.matshow(cm, cmap="Blues")
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        mlflow.log_figure(fig, "confusion_matrix.png")
        plt.close()

        # Log model with signature
        from mlflow.models.signature import infer_signature
        signature = infer_signature(X_test, y_pred)
        mlflow.sklearn.log_model(
            model, "model",
            signature=signature,
            input_example=X_test[:3],
            registered_model_name="fraud-detector",
        )

        # Log classification report
        report = classification_report(y_test, y_pred, output_dict=True)
        mlflow.log_dict(report, "classification_report.json")

        print(f"Run ID: {run.info.run_id}")
        print(f"Metrics: {metrics}")
        return run.info.run_id

# --- Hyperparameter sweep ---

def hyperparameter_search(X_train, y_train, X_test, y_test):
    param_grid = [
        {"n_estimators": n, "max_depth": d, "min_samples_split": s}
        for n in [100, 200, 500]
        for d in [10, 20, None]
        for s in [2, 5, 10]
    ]

    with mlflow.start_run(run_name="hyperparam-sweep") as parent:
        best_f1 = 0
        best_run_id = None

        for params in param_grid:
            with mlflow.start_run(nested=True, run_name=f"rf-n{params['n_estimators']}"):
                run_id = train_and_track(X_train, y_train, X_test, y_test, params)
                f1 = mlflow.get_run(run_id).data.metrics["f1"]
                if f1 > best_f1:
                    best_f1 = f1
                    best_run_id = run_id

        mlflow.log_metric("best_f1", best_f1)
        mlflow.log_param("best_run_id", best_run_id)

# --- Model registry workflow ---

client = MlflowClient()

def promote_model(model_name: str, version: int, stage: str):
    """Promote model version through stages."""
    # Validate before promotion
    model_uri = f"models:/{model_name}/{version}"
    model = mlflow.sklearn.load_model(model_uri)

    # Run validation checks
    run = client.get_run(client.get_model_version(model_name, str(version)).run_id)
    metrics = run.data.metrics

    if stage == "Production":
        assert metrics["roc_auc"] > 0.85, "AUC too low for production"
        assert metrics["cv_f1_std"] < 0.05, "Too much variance"

    client.transition_model_version_stage(
        name=model_name,
        version=version,
        stage=stage,  # "Staging" or "Production"
    )

# Load production model
def load_production_model(name: str):
    return mlflow.sklearn.load_model(f"models:/{name}/Production")
```

Experiment comparison:
```python
# Compare runs programmatically
runs = mlflow.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.roc_auc > 0.8",
    order_by=["metrics.f1 DESC"],
    max_results=10,
)
print(runs[["params.n_estimators", "metrics.f1", "metrics.roc_auc"]])
```'''
    ),
    (
        "ml/feature-stores",
        "Explain feature store concepts and implementation. Show how to define features, handle online/offline serving, and prevent training-serving skew.",
        '''Feature store pattern for consistent ML feature management:

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import hashlib
import json
import time

# --- Feature definition ---

@dataclass
class FeatureDefinition:
    name: str
    entity: str             # e.g., "user", "product"
    dtype: str              # "float", "int", "string", "embedding"
    description: str
    source: str             # "batch" or "stream"
    ttl: timedelta          # How long feature is valid
    version: int = 1
    tags: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.entity}:{self.name}:v{self.version}"

# Define features declaratively
USER_FEATURES = [
    FeatureDefinition(
        name="purchase_count_30d",
        entity="user",
        dtype="int",
        description="Number of purchases in last 30 days",
        source="batch",
        ttl=timedelta(hours=24),
        tags=["commerce", "engagement"],
    ),
    FeatureDefinition(
        name="avg_session_duration_7d",
        entity="user",
        dtype="float",
        description="Average session duration in seconds, last 7 days",
        source="batch",
        ttl=timedelta(hours=6),
        tags=["engagement"],
    ),
    FeatureDefinition(
        name="last_page_viewed",
        entity="user",
        dtype="string",
        description="Most recently viewed page URL",
        source="stream",
        ttl=timedelta(minutes=30),
        tags=["realtime", "engagement"],
    ),
]

# --- Feature store implementation ---

class FeatureStore:
    """Dual online/offline feature store."""

    def __init__(self, redis_client, warehouse_conn):
        self.redis = redis_client
        self.warehouse = warehouse_conn
        self.registry: dict[str, FeatureDefinition] = {}

    def register(self, features: list[FeatureDefinition]):
        for f in features:
            self.registry[f.full_name] = f

    # --- Online store (Redis) for real-time serving ---

    def set_online(self, entity_id: str, feature_name: str, value: Any,
                   timestamp: Optional[datetime] = None):
        """Write feature value to online store."""
        feat = self.registry[feature_name]
        key = f"feat:{feature_name}:{entity_id}"
        payload = json.dumps({
            "value": value,
            "ts": (timestamp or datetime.now(timezone.utc)).isoformat(),
        })
        self.redis.setex(key, int(feat.ttl.total_seconds()), payload)

    def get_online(self, entity_id: str, feature_names: list[str]) -> dict:
        """Fetch features from online store for inference."""
        result = {}
        keys = [f"feat:{fn}:{entity_id}" for fn in feature_names]
        values = self.redis.mget(keys)

        for name, raw in zip(feature_names, values):
            if raw:
                data = json.loads(raw)
                feat = self.registry[name]
                ts = datetime.fromisoformat(data["ts"])
                age = datetime.now(timezone.utc) - ts

                if age > feat.ttl:
                    result[name] = None  # Expired
                else:
                    result[name] = data["value"]
            else:
                result[name] = None  # Missing

        return result

    # --- Offline store (data warehouse) for training ---

    def get_training_data(self, entity_ids: list[str],
                          feature_names: list[str],
                          point_in_time: datetime) -> list[dict]:
        """Point-in-time correct feature retrieval for training.

        Prevents data leakage by only using features available
        at the time each example occurred.
        """
        query = self._build_pit_query(entity_ids, feature_names, point_in_time)
        return self.warehouse.execute(query).fetchall()

    def _build_pit_query(self, entity_ids, feature_names, pit):
        """Build point-in-time join query."""
        # For each entity and feature, get the latest value
        # that was available BEFORE the point-in-time
        return f"""
        WITH ranked AS (
            SELECT
                entity_id,
                feature_name,
                feature_value,
                event_time,
                ROW_NUMBER() OVER (
                    PARTITION BY entity_id, feature_name
                    ORDER BY event_time DESC
                ) as rn
            FROM feature_values
            WHERE entity_id IN ({','.join(f"'{e}'" for e in entity_ids)})
              AND feature_name IN ({','.join(f"'{f}'" for f in feature_names)})
              AND event_time <= '{pit.isoformat()}'
        )
        SELECT entity_id, feature_name, feature_value, event_time
        FROM ranked WHERE rn = 1
        """

    # --- Feature computation pipeline ---

    def compute_batch_features(self, date: str):
        """Daily batch feature computation job."""
        computations = {
            "user:purchase_count_30d:v1": f"""
                SELECT user_id as entity_id, COUNT(*) as value
                FROM orders
                WHERE order_date >= DATE('{date}') - INTERVAL '30 days'
                  AND order_date < DATE('{date}')
                GROUP BY user_id
            """,
            "user:avg_session_duration_7d:v1": f"""
                SELECT user_id as entity_id,
                       AVG(duration_seconds) as value
                FROM sessions
                WHERE session_date >= DATE('{date}') - INTERVAL '7 days'
                  AND session_date < DATE('{date}')
                GROUP BY user_id
            """,
        }

        for feature_name, query in computations.items():
            rows = self.warehouse.execute(query).fetchall()
            # Write to both offline (warehouse) and online (Redis)
            for row in rows:
                self.set_online(row["entity_id"], feature_name, row["value"])
                self._write_offline(row["entity_id"], feature_name,
                                    row["value"], date)

    # --- Feature validation ---

    def validate_feature_vector(self, features: dict) -> list[str]:
        """Check for common feature issues."""
        issues = []
        for name, value in features.items():
            if value is None:
                issues.append(f"Missing feature: {name}")
            feat = self.registry.get(name)
            if feat and feat.dtype == "float" and value is not None:
                if not isinstance(value, (int, float)):
                    issues.append(f"Type mismatch: {name} expected float, got {type(value)}")
        return issues
```

Key concepts:
- **Online store** (Redis) — low-latency serving for inference (<5ms)
- **Offline store** (warehouse) — batch access for training
- **Point-in-time correctness** — prevent data leakage in training
- **Feature TTL** — stale features return None, not wrong values
- **Training-serving skew** — same feature definitions used everywhere'''
    ),
    (
        "ml/model-monitoring",
        "Show how to monitor ML models in production: data drift detection, prediction monitoring, and automated retraining triggers.",
        '''ML model monitoring for production reliability:

```python
import numpy as np
from scipy import stats
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional
import json

@dataclass
class DriftResult:
    feature: str
    statistic: float
    p_value: float
    is_drifted: bool
    drift_type: str  # "distribution", "concept", "prediction"

class DataDriftDetector:
    """Detect distribution shifts in input features."""

    def __init__(self, reference_data: dict[str, np.ndarray],
                 threshold: float = 0.05):
        self.reference = reference_data
        self.threshold = threshold

    def check_drift(self, current_data: dict[str, np.ndarray]) -> list[DriftResult]:
        results = []
        for feature, ref_values in self.reference.items():
            if feature not in current_data:
                continue

            curr_values = current_data[feature]

            # KS test for continuous features
            if np.issubdtype(ref_values.dtype, np.floating):
                stat, p_value = stats.ks_2samp(ref_values, curr_values)
            # Chi-squared for categorical
            else:
                stat, p_value = self._chi_squared_test(ref_values, curr_values)

            results.append(DriftResult(
                feature=feature,
                statistic=float(stat),
                p_value=float(p_value),
                is_drifted=p_value < self.threshold,
                drift_type="distribution",
            ))

        return results

    def _chi_squared_test(self, ref, curr):
        ref_counts = np.unique(ref, return_counts=True)
        curr_counts = np.unique(curr, return_counts=True)

        all_categories = set(ref_counts[0]) | set(curr_counts[0])
        ref_freq = np.array([
            dict(zip(*ref_counts)).get(c, 0) for c in all_categories
        ])
        curr_freq = np.array([
            dict(zip(*curr_counts)).get(c, 0) for c in all_categories
        ])

        # Normalize
        ref_freq = ref_freq / ref_freq.sum()
        curr_freq = curr_freq / curr_freq.sum()

        stat, p_value = stats.chisquare(curr_freq, ref_freq + 1e-10)
        return stat, p_value

class PredictionMonitor:
    """Monitor model predictions for anomalies and drift."""

    def __init__(self, window_size: int = 1000):
        self.predictions = deque(maxlen=window_size)
        self.actuals = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)
        self.baseline_metrics: Optional[dict] = None

    def log_prediction(self, prediction: float, actual: Optional[float] = None):
        self.predictions.append(prediction)
        self.timestamps.append(datetime.now(timezone.utc))
        if actual is not None:
            self.actuals.append(actual)

    def set_baseline(self, metrics: dict):
        """Set baseline metrics from training/validation."""
        self.baseline_metrics = metrics

    def check_prediction_drift(self) -> dict:
        """Check if prediction distribution has shifted."""
        preds = np.array(self.predictions)
        alerts = {}

        # Prediction distribution statistics
        alerts["mean_prediction"] = float(preds.mean())
        alerts["std_prediction"] = float(preds.std())
        alerts["null_rate"] = float(np.isnan(preds).mean())

        # Compare to baseline
        if self.baseline_metrics:
            baseline_mean = self.baseline_metrics.get("mean_prediction", 0)
            if abs(preds.mean() - baseline_mean) > 2 * preds.std():
                alerts["prediction_shift"] = True

        # Check for stuck predictions (model returning same value)
        unique_ratio = len(np.unique(preds)) / len(preds)
        if unique_ratio < 0.01:
            alerts["stuck_predictions"] = True

        return alerts

    def check_performance(self) -> Optional[dict]:
        """Check if model performance has degraded."""
        if len(self.actuals) < 100:
            return None

        preds = np.array(list(self.predictions)[-len(self.actuals):])
        actuals = np.array(self.actuals)

        # Binary classification metrics
        from sklearn.metrics import accuracy_score, roc_auc_score
        binary_preds = (preds > 0.5).astype(int)

        current = {
            "accuracy": accuracy_score(actuals, binary_preds),
            "auc": roc_auc_score(actuals, preds),
        }

        degraded = {}
        if self.baseline_metrics:
            for metric, value in current.items():
                baseline = self.baseline_metrics.get(metric, 0)
                if value < baseline * 0.95:  # 5% degradation threshold
                    degraded[metric] = {
                        "current": value,
                        "baseline": baseline,
                        "degradation": (baseline - value) / baseline,
                    }

        return {"metrics": current, "degraded": degraded}

# --- Retraining trigger ---

class RetrainingOrchestrator:
    """Decide when to retrain based on monitoring signals."""

    def __init__(self, drift_detector: DataDriftDetector,
                 prediction_monitor: PredictionMonitor):
        self.drift_detector = drift_detector
        self.pred_monitor = prediction_monitor
        self.last_retrain: Optional[datetime] = None
        self.min_retrain_interval = timedelta(hours=24)

    def should_retrain(self, current_features: dict[str, np.ndarray]) -> dict:
        reasons = []

        # Check data drift
        drift_results = self.drift_detector.check_drift(current_features)
        drifted_features = [r for r in drift_results if r.is_drifted]
        if len(drifted_features) > len(drift_results) * 0.3:
            reasons.append(f"Data drift in {len(drifted_features)} features")

        # Check prediction drift
        pred_drift = self.pred_monitor.check_prediction_drift()
        if pred_drift.get("prediction_shift"):
            reasons.append("Prediction distribution shifted")
        if pred_drift.get("stuck_predictions"):
            reasons.append("Predictions appear stuck")

        # Check performance degradation
        perf = self.pred_monitor.check_performance()
        if perf and perf["degraded"]:
            reasons.append(f"Performance degraded: {list(perf['degraded'].keys())}")

        # Respect minimum interval
        should = len(reasons) > 0
        if should and self.last_retrain:
            elapsed = datetime.now(timezone.utc) - self.last_retrain
            if elapsed < self.min_retrain_interval:
                return {"should_retrain": False,
                        "reason": "Too soon since last retrain",
                        "next_eligible": (self.last_retrain + self.min_retrain_interval).isoformat()}

        return {
            "should_retrain": should,
            "reasons": reasons,
            "drift_summary": {r.feature: r.p_value for r in drift_results},
        }
```

Monitoring checklist:
1. **Input drift** — feature distributions shifting from training data
2. **Prediction drift** — model output distribution changing
3. **Performance decay** — accuracy/AUC declining over time
4. **Latency** — inference time increasing (model/data issues)
5. **Data quality** — null rates, schema violations, outliers'''
    ),
]
