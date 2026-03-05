"""MLOps — model serving, feature stores, experiment tracking, and ML pipelines."""

PAIRS = [
    (
        "mlops/model-serving",
        "Show model serving patterns: FastAPI inference endpoints, batching, model versioning, and A/B testing.",
        '''Model serving patterns:

```python
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import numpy as np
import asyncio
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# --- Model registry ---

class ModelRegistry:
    """Manage model versions and loading."""

    def __init__(self, model_dir: str = "models"):
        self.model_dir = Path(model_dir)
        self._models: dict[str, dict] = {}  # name -> {version: model}
        self._active: dict[str, str] = {}    # name -> active version

    def load_model(self, name: str, version: str):
        """Load a model version into memory."""
        path = self.model_dir / name / version / "model.pkl"
        import joblib
        model = joblib.load(path)

        if name not in self._models:
            self._models[name] = {}
        self._models[name][version] = model
        self._active[name] = version
        logger.info("Loaded model %s version %s", name, version)

    def get_model(self, name: str, version: str = None):
        """Get model by name and optional version."""
        version = version or self._active.get(name)
        if not version or name not in self._models:
            raise KeyError(f"Model {name} not found")
        return self._models[name][version]

    def set_active(self, name: str, version: str):
        self._active[name] = version


# --- Request/Response models ---

class PredictionRequest(BaseModel):
    features: list[list[float]] = Field(
        ..., min_length=1, max_length=1000,
        description="Batch of feature vectors"
    )
    model_version: Optional[str] = None

class PredictionResponse(BaseModel):
    predictions: list[float]
    model_version: str
    latency_ms: float


# --- Inference server ---

registry = ModelRegistry()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load default model on startup
    registry.load_model("classifier", "v2.1")
    registry.load_model("classifier", "v2.0")  # Keep previous for rollback
    yield

app = FastAPI(lifespan=lifespan)


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    start = time.perf_counter()

    model = registry.get_model("classifier", request.model_version)
    features = np.array(request.features)

    # Run inference in thread pool (model.predict may block)
    loop = asyncio.get_event_loop()
    predictions = await loop.run_in_executor(
        None, model.predict, features
    )

    latency = (time.perf_counter() - start) * 1000

    return PredictionResponse(
        predictions=predictions.tolist(),
        model_version=registry._active["classifier"],
        latency_ms=round(latency, 2),
    )


# --- Adaptive batching for throughput ---

class BatchPredictor:
    """Collect individual requests into batches for GPU efficiency."""

    def __init__(self, model, max_batch: int = 32,
                 max_wait_ms: float = 50):
        self.model = model
        self.max_batch = max_batch
        self.max_wait = max_wait_ms / 1000
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = True

    async def predict_one(self, features: list[float]) -> float:
        """Submit single prediction, wait for batched result."""
        future = asyncio.get_event_loop().create_future()
        await self._queue.put((features, future))
        return await future

    async def batch_loop(self):
        """Continuously process batches."""
        while self._running:
            batch_features = []
            batch_futures = []

            # Collect batch
            try:
                features, future = await asyncio.wait_for(
                    self._queue.get(), timeout=self.max_wait
                )
                batch_features.append(features)
                batch_futures.append(future)
            except asyncio.TimeoutError:
                continue

            # Fill batch up to max_batch
            while len(batch_features) < self.max_batch:
                try:
                    features, future = self._queue.get_nowait()
                    batch_features.append(features)
                    batch_futures.append(future)
                except asyncio.QueueEmpty:
                    break

            # Run batched inference
            try:
                input_array = np.array(batch_features)
                predictions = self.model.predict(input_array)

                for future, pred in zip(batch_futures, predictions):
                    future.set_result(float(pred))

            except Exception as e:
                for future in batch_futures:
                    future.set_exception(e)


# --- A/B testing with traffic splitting ---

class ABRouter:
    """Route requests between model versions for A/B testing."""

    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._experiments: dict[str, dict] = {}

    def create_experiment(self, name: str, control: str,
                          treatment: str, traffic_pct: float = 10):
        self._experiments[name] = {
            "control": control,
            "treatment": treatment,
            "traffic_pct": traffic_pct,
        }

    def get_version(self, experiment: str, user_id: str = "") -> str:
        """Deterministic routing based on user_id hash."""
        import hashlib
        exp = self._experiments[experiment]
        hash_val = int(hashlib.md5(
            f"{experiment}:{user_id}".encode()
        ).hexdigest(), 16) % 100

        if hash_val < exp["traffic_pct"]:
            return exp["treatment"]
        return exp["control"]
```

Model serving patterns:
1. **Model registry** — versioned model loading with rollback support
2. **Thread pool inference** — `run_in_executor` for CPU-bound model.predict
3. **Adaptive batching** — collect individual requests into GPU-efficient batches
4. **A/B testing** — deterministic routing by user hash for consistent assignment
5. **Graceful rollout** — keep previous version loaded for instant rollback'''
    ),
    (
        "mlops/experiment-tracking",
        "Show ML experiment tracking patterns: MLflow, metric logging, model comparison, and reproducibility.",
        '''ML experiment tracking patterns:

```python
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from sklearn.model_selection import cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, mean_absolute_error, r2_score,
)
import numpy as np
import json
import hashlib
from pathlib import Path
from datetime import datetime


# --- Experiment setup ---

mlflow.set_tracking_uri("http://mlflow-server:5000")
mlflow.set_experiment("customer-churn-prediction")


# --- Training with full tracking ---

def train_and_log(X_train, y_train, X_test, y_test,
                  model_class, params: dict,
                  feature_names: list[str] = None):
    """Train model with comprehensive MLflow logging."""

    with mlflow.start_run(run_name=f"{model_class.__name__}_{datetime.now():%H%M}"):

        # Log parameters
        mlflow.log_params(params)
        mlflow.log_param("model_type", model_class.__name__)
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("n_train_samples", X_train.shape[0])
        mlflow.log_param("n_test_samples", X_test.shape[0])

        # Data fingerprint for reproducibility
        data_hash = hashlib.md5(
            np.concatenate([X_train, X_test]).tobytes()
        ).hexdigest()[:8]
        mlflow.log_param("data_hash", data_hash)

        # Train
        model = model_class(**params)
        model.fit(X_train, y_train)

        # Predictions
        y_pred = model.predict(X_test)
        y_pred_proba = (model.predict_proba(X_test)[:, 1]
                       if hasattr(model, "predict_proba") else None)

        # Log metrics
        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, average="weighted"),
            "recall": recall_score(y_test, y_pred, average="weighted"),
            "f1": f1_score(y_test, y_pred, average="weighted"),
        }
        mlflow.log_metrics(metrics)

        # Cross-validation scores
        cv_scores = cross_val_score(model, X_train, y_train, cv=5)
        mlflow.log_metric("cv_mean", cv_scores.mean())
        mlflow.log_metric("cv_std", cv_scores.std())

        # Feature importance
        if hasattr(model, "feature_importances_") and feature_names:
            importance = dict(zip(feature_names, model.feature_importances_))
            mlflow.log_dict(importance, "feature_importance.json")

            # Log top features as metrics
            sorted_imp = sorted(importance.items(),
                              key=lambda x: x[1], reverse=True)
            for name, imp in sorted_imp[:10]:
                mlflow.log_metric(f"importance_{name}", imp)

        # Log model artifact
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name="churn-classifier",
            input_example=X_test[:5],
        )

        # Log confusion matrix as artifact
        from sklearn.metrics import confusion_matrix
        cm = confusion_matrix(y_test, y_pred)
        mlflow.log_dict(
            {"confusion_matrix": cm.tolist()},
            "confusion_matrix.json"
        )

        return metrics


# --- Model comparison ---

def compare_models(experiment_name: str, metric: str = "f1",
                   top_n: int = 5) -> list[dict]:
    """Compare top models from an experiment."""
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=[f"metrics.{metric} DESC"],
        max_results=top_n,
    )

    results = []
    for run in runs:
        results.append({
            "run_id": run.info.run_id,
            "model_type": run.data.params.get("model_type"),
            "metrics": {
                k: round(v, 4)
                for k, v in run.data.metrics.items()
                if k in ["accuracy", "precision", "recall", "f1", "cv_mean"]
            },
            "params": {
                k: v for k, v in run.data.params.items()
                if k not in ["model_type", "data_hash"]
            },
            "duration_s": (
                run.info.end_time - run.info.start_time
            ) / 1000 if run.info.end_time else None,
        })

    return results


# --- Model promotion pipeline ---

def promote_model(model_name: str, version: int, stage: str = "Production"):
    """Promote model version to Production/Staging."""
    client = MlflowClient()

    # Archive current production model
    current_prod = client.get_latest_versions(model_name, stages=[stage])
    for mv in current_prod:
        client.transition_model_version_stage(
            name=model_name,
            version=mv.version,
            stage="Archived",
        )

    # Promote new version
    client.transition_model_version_stage(
        name=model_name,
        version=version,
        stage=stage,
    )

    # Load for validation
    model_uri = f"models:/{model_name}/{stage}"
    model = mlflow.sklearn.load_model(model_uri)
    return model
```

Experiment tracking patterns:
1. **Comprehensive logging** — params, metrics, artifacts, data hash in every run
2. **Data fingerprinting** — hash training data to detect dataset changes
3. **Cross-validation** — log CV mean/std alongside test metrics
4. **Model registry** — version, stage (Staging/Production/Archived) lifecycle
5. **Model comparison** — search runs by metric for systematic evaluation'''
    ),
    (
        "mlops/feature-engineering",
        "Show feature engineering patterns: feature stores, transformations, online/offline serving, and drift detection.",
        '''Feature engineering patterns:

```python
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from datetime import datetime, timezone
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


# --- Feature definition ---

@dataclass
class FeatureDefinition:
    name: str
    dtype: str  # "float", "int", "string", "embedding"
    description: str
    source: str  # "batch", "streaming", "on-demand"
    transform: Optional[Callable] = None
    default_value: Any = None
    ttl_seconds: int = 86400  # Feature freshness


# --- Feature store ---

class FeatureStore:
    """Simple feature store with online/offline serving."""

    def __init__(self, redis=None, db=None):
        self.redis = redis  # Online store (low latency)
        self.db = db        # Offline store (full history)
        self._definitions: dict[str, FeatureDefinition] = {}

    def register(self, feature: FeatureDefinition):
        self._definitions[feature.name] = feature

    # --- Online serving (real-time inference) ---

    async def get_features(self, entity_id: str,
                           feature_names: list[str]) -> dict:
        """Get features for real-time inference."""
        key = f"features:{entity_id}"
        raw = await self.redis.hmget(key, *feature_names)

        features = {}
        for name, value in zip(feature_names, raw):
            if value is not None:
                features[name] = json.loads(value)
            else:
                defn = self._definitions.get(name)
                features[name] = defn.default_value if defn else None
                logger.warning("Feature %s missing for %s", name, entity_id)

        return features

    async def set_features(self, entity_id: str,
                           features: dict, ttl: int = None):
        """Write features to online store."""
        key = f"features:{entity_id}"
        pipeline = self.redis.pipeline()

        for name, value in features.items():
            pipeline.hset(key, name, json.dumps(value))

        defn_ttl = max(
            (self._definitions[n].ttl_seconds
             for n in features if n in self._definitions),
            default=86400,
        )
        pipeline.expire(key, ttl or defn_ttl)
        await pipeline.execute()

    # --- Offline serving (training data) ---

    async def get_training_data(self, entity_ids: list[str],
                                feature_names: list[str],
                                point_in_time: datetime = None) -> pd.DataFrame:
        """Get historical features for training (point-in-time correct)."""
        query = """
            SELECT entity_id, feature_name, feature_value, event_time
            FROM feature_history
            WHERE entity_id = ANY($1)
            AND feature_name = ANY($2)
            AND event_time <= $3
            ORDER BY entity_id, feature_name, event_time DESC
        """
        timestamp = point_in_time or datetime.now(timezone.utc)

        async with self.db.acquire() as conn:
            rows = await conn.fetch(query, entity_ids, feature_names, timestamp)

        # Pivot to wide format (one row per entity)
        records = {}
        seen = set()
        for row in rows:
            key = (row["entity_id"], row["feature_name"])
            if key not in seen:
                seen.add(key)
                if row["entity_id"] not in records:
                    records[row["entity_id"]] = {"entity_id": row["entity_id"]}
                records[row["entity_id"]][row["feature_name"]] = json.loads(
                    row["feature_value"]
                )

        return pd.DataFrame(list(records.values()))


# --- Feature transformations ---

class FeatureTransformer:
    """Compute derived features from raw data."""

    def __init__(self):
        self._transforms: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable):
        self._transforms[name] = fn

    def compute(self, raw_data: dict) -> dict:
        features = {}
        for name, fn in self._transforms.items():
            try:
                features[name] = fn(raw_data)
            except Exception as e:
                logger.error("Failed to compute %s: %s", name, e)
                features[name] = None
        return features


transformer = FeatureTransformer()

# Register feature computations
transformer.register("order_count_30d", lambda d:
    len([o for o in d.get("orders", [])
         if o["date"] > (datetime.now().timestamp() - 30*86400)]))

transformer.register("avg_order_value", lambda d:
    np.mean([o["total"] for o in d.get("orders", [])]) if d.get("orders") else 0)

transformer.register("days_since_last_order", lambda d:
    (datetime.now().timestamp() - max(o["date"] for o in d["orders"])) / 86400
    if d.get("orders") else 999)

transformer.register("email_domain", lambda d:
    d.get("email", "").split("@")[-1] if "@" in d.get("email", "") else "unknown")


# --- Drift detection ---

class DriftDetector:
    """Detect feature distribution drift."""

    def __init__(self, reference_stats: dict):
        self.reference = reference_stats

    def check_drift(self, current_data: pd.Series,
                    feature_name: str) -> dict:
        """Compare current distribution to reference."""
        ref = self.reference.get(feature_name, {})
        if not ref:
            return {"drift_detected": False, "reason": "no reference"}

        current_mean = current_data.mean()
        current_std = current_data.std()
        ref_mean = ref["mean"]
        ref_std = ref["std"]

        # PSI (Population Stability Index)
        # > 0.1 = moderate drift, > 0.25 = significant drift
        drift_score = abs(current_mean - ref_mean) / (ref_std + 1e-10)

        return {
            "feature": feature_name,
            "drift_detected": drift_score > 2.0,
            "drift_score": round(drift_score, 4),
            "reference_mean": ref_mean,
            "current_mean": round(current_mean, 4),
            "reference_std": ref_std,
            "current_std": round(current_std, 4),
        }
```

Feature engineering patterns:
1. **Feature store** — separate online (Redis, low latency) and offline (DB, full history)
2. **Point-in-time correct** — historical features at training time prevent data leakage
3. **Feature definitions** — schema with type, source, TTL, and default values
4. **Registered transforms** — named, composable feature computations
5. **Drift detection** — compare current feature distributions to training reference'''
    ),
]
