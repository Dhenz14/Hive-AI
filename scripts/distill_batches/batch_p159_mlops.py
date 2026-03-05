"""MLOps — model serving, experiment tracking, feature stores, and ML pipelines."""

PAIRS = [
    (
        "ai/model-serving",
        "Show ML model serving patterns: FastAPI + torch, batched inference, model versioning, and A/B testing.",
        '''ML model serving in production:

```python
import torch
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from collections import deque
import time
import hashlib


# === Model Registry ===

class ModelRegistry:
    """Manage multiple model versions with hot-swapping."""

    def __init__(self):
        self.models: dict[str, dict] = {}
        self.active_version: str | None = None

    def register(self, version: str, model: torch.nn.Module, metadata: dict | None = None):
        model.eval()
        self.models[version] = {
            "model": model,
            "metadata": metadata or {},
            "loaded_at": time.time(),
        }
        if self.active_version is None:
            self.active_version = version

    def get_active(self) -> torch.nn.Module:
        if not self.active_version:
            raise RuntimeError("No active model")
        return self.models[self.active_version]["model"]

    def promote(self, version: str):
        if version not in self.models:
            raise ValueError(f"Unknown version: {version}")
        self.active_version = version

    def rollback(self, version: str):
        self.promote(version)


# === Batched Inference ===

class DynamicBatcher:
    """Accumulate requests and batch them for GPU efficiency.

    Instead of processing one request at a time, collect requests
    for up to max_wait_ms, then process as a batch on GPU.
    """

    def __init__(self, model: torch.nn.Module, max_batch_size: int = 32,
                 max_wait_ms: float = 50):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._batch_loop())

    async def predict(self, input_tensor: torch.Tensor) -> torch.Tensor:
        """Submit a single prediction request, get result when batch completes."""
        future = asyncio.get_event_loop().create_future()
        await self.queue.put((input_tensor, future))
        return await future

    async def _batch_loop(self):
        while self._running:
            batch_inputs = []
            batch_futures = []
            deadline = time.monotonic() + self.max_wait_ms / 1000

            # Collect requests until batch is full or timeout
            while len(batch_inputs) < self.max_batch_size:
                timeout = max(0, deadline - time.monotonic())
                try:
                    tensor, future = await asyncio.wait_for(
                        self.queue.get(), timeout=timeout
                    )
                    batch_inputs.append(tensor)
                    batch_futures.append(future)
                except asyncio.TimeoutError:
                    break

            if not batch_inputs:
                continue

            # Process batch on GPU
            try:
                batch = torch.stack(batch_inputs).cuda()
                with torch.no_grad():
                    outputs = self.model(batch)

                # Distribute results back to individual requests
                for i, future in enumerate(batch_futures):
                    future.set_result(outputs[i].cpu())
            except Exception as e:
                for future in batch_futures:
                    future.set_exception(e)


# === A/B Testing ===

class ABRouter:
    """Route requests to different model versions for A/B testing."""

    def __init__(self):
        self.experiments: dict[str, dict] = {}

    def create_experiment(self, name: str, control: str, treatment: str,
                          traffic_split: float = 0.1):
        self.experiments[name] = {
            "control": control,
            "treatment": treatment,
            "traffic_split": traffic_split,
            "metrics": {"control": [], "treatment": []},
        }

    def route(self, experiment_name: str, request_id: str) -> str:
        """Deterministic routing based on request hash."""
        exp = self.experiments[experiment_name]
        hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16) % 100
        if hash_val < exp["traffic_split"] * 100:
            return exp["treatment"]
        return exp["control"]

    def record_metric(self, experiment_name: str, variant: str, metric: float):
        self.experiments[experiment_name]["metrics"][variant].append(metric)


# === FastAPI Serving Endpoint ===

registry = ModelRegistry()
batcher: DynamicBatcher | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global batcher
    # Load model on startup
    model = torch.jit.load("model_v1.pt").cuda()
    registry.register("v1", model, {"accuracy": 0.95})
    batcher = DynamicBatcher(registry.get_active())
    await batcher.start()
    yield

app = FastAPI(lifespan=lifespan)

class PredictRequest(BaseModel):
    features: list[float] = Field(..., min_length=1, max_length=1024)
    request_id: str | None = None

class PredictResponse(BaseModel):
    prediction: list[float]
    model_version: str
    latency_ms: float

@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    start = time.monotonic()
    tensor = torch.tensor(request.features, dtype=torch.float32)

    result = await batcher.predict(tensor)

    return PredictResponse(
        prediction=result.tolist(),
        model_version=registry.active_version,
        latency_ms=(time.monotonic() - start) * 1000,
    )

@app.post("/models/{version}/promote")
async def promote_model(version: str):
    registry.promote(version)
    return {"status": "promoted", "version": version}
```

Key patterns:
1. **Dynamic batching** — accumulate individual requests into GPU batches for throughput (50ms max wait)
2. **Model registry** — version management with hot-swap, promote, and rollback
3. **A/B testing** — deterministic hash-based routing ensures consistent user experience
4. **Async serving** — FastAPI async endpoints handle concurrent requests while GPU batches process
5. **Graceful updates** — promote new version atomically; rollback instantly if metrics degrade'''
    ),
    (
        "ai/experiment-tracking",
        "Show ML experiment tracking patterns: MLflow logging, hyperparameter sweeps, artifact management, and model comparison.",
        '''ML experiment tracking with MLflow:

```python
import mlflow
import mlflow.pytorch
from mlflow.tracking import MlflowClient
import optuna
import torch
from pathlib import Path
import json


# === MLflow Experiment Setup ===

def setup_tracking(experiment_name: str, tracking_uri: str = "sqlite:///mlflow.db"):
    """Initialize MLflow experiment tracking."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)


# === Training with Experiment Logging ===

def train_with_tracking(
    model: torch.nn.Module,
    train_loader,
    val_loader,
    config: dict,
    tags: dict | None = None,
) -> str:
    """Train model with comprehensive MLflow logging."""
    with mlflow.start_run(tags=tags) as run:
        # Log hyperparameters
        mlflow.log_params({
            "learning_rate": config["lr"],
            "batch_size": config["batch_size"],
            "epochs": config["epochs"],
            "optimizer": config["optimizer"],
            "model_type": config["model_type"],
            "hidden_dim": config["hidden_dim"],
            "num_layers": config["num_layers"],
            "dropout": config.get("dropout", 0.0),
        })

        # Log model architecture
        mlflow.log_text(str(model), "model_architecture.txt")

        optimizer = torch.optim.AdamW(model.parameters(), lr=config["lr"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=config["epochs"]
        )
        best_val_loss = float("inf")

        for epoch in range(config["epochs"]):
            # Training
            model.train()
            train_loss = 0
            for batch in train_loader:
                optimizer.zero_grad()
                loss = model.training_step(batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation
            model.eval()
            val_loss = 0
            val_metrics = {"correct": 0, "total": 0}
            with torch.no_grad():
                for batch in val_loader:
                    loss, preds = model.validation_step(batch)
                    val_loss += loss.item()
                    val_metrics["correct"] += preds["correct"]
                    val_metrics["total"] += preds["total"]

            val_loss /= len(val_loader)
            val_accuracy = val_metrics["correct"] / val_metrics["total"]

            # Log metrics per epoch
            mlflow.log_metrics({
                "train_loss": train_loss,
                "val_loss": val_loss,
                "val_accuracy": val_accuracy,
                "learning_rate": scheduler.get_last_lr()[0],
            }, step=epoch)

            scheduler.step()

            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                mlflow.pytorch.log_model(model, "best_model")
                mlflow.log_metric("best_val_loss", best_val_loss)
                mlflow.log_metric("best_epoch", epoch)

        # Log final model and artifacts
        mlflow.pytorch.log_model(model, "final_model")
        mlflow.log_metric("final_val_accuracy", val_accuracy)

        return run.info.run_id


# === Hyperparameter Optimization with Optuna + MLflow ===

def optimize_hyperparameters(
    create_model_fn,
    train_loader,
    val_loader,
    n_trials: int = 50,
) -> dict:
    """Optuna hyperparameter search with MLflow logging."""

    def objective(trial: optuna.Trial) -> float:
        config = {
            "lr": trial.suggest_float("lr", 1e-5, 1e-2, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [16, 32, 64, 128]),
            "hidden_dim": trial.suggest_categorical("hidden_dim", [128, 256, 512]),
            "num_layers": trial.suggest_int("num_layers", 2, 6),
            "dropout": trial.suggest_float("dropout", 0.0, 0.5),
            "optimizer": trial.suggest_categorical("optimizer", ["adam", "adamw", "sgd"]),
            "epochs": 10,
            "model_type": "transformer",
        }

        model = create_model_fn(config)
        run_id = train_with_tracking(
            model, train_loader, val_loader, config,
            tags={"trial": str(trial.number), "study": "hparam_search"},
        )

        # Return validation loss for Optuna to minimize
        client = MlflowClient()
        run = client.get_run(run_id)
        return float(run.data.metrics["best_val_loss"])

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler())
    study.optimize(objective, n_trials=n_trials)

    # Log best parameters
    with mlflow.start_run(tags={"type": "best_hparams"}):
        mlflow.log_params(study.best_params)
        mlflow.log_metric("best_val_loss", study.best_value)

    return study.best_params


# === Model Comparison ===

def compare_models(experiment_name: str, metric: str = "val_accuracy",
                   top_k: int = 5) -> list[dict]:
    """Compare runs in an experiment and rank by metric."""
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=[f"metrics.{metric} DESC"],
        max_results=top_k,
    )

    results = []
    for run in runs:
        results.append({
            "run_id": run.info.run_id,
            "status": run.info.status,
            metric: run.data.metrics.get(metric),
            "params": run.data.params,
            "duration_min": (run.info.end_time - run.info.start_time) / 60000
            if run.info.end_time else None,
        })

    return results


# === Model Registry (staging -> production) ===

def promote_model(run_id: str, model_name: str = "production_model"):
    """Promote a model from experiment to production registry."""
    client = MlflowClient()

    # Register model version
    model_uri = f"runs:/{run_id}/best_model"
    mv = mlflow.register_model(model_uri, model_name)

    # Transition to production
    client.transition_model_version_stage(
        name=model_name,
        version=mv.version,
        stage="Production",
        archive_existing_versions=True,
    )

    return {"model": model_name, "version": mv.version, "stage": "Production"}
```

MLOps workflow:
```
Experiment → HPO (Optuna) → Best Run → Register Model → Stage (Staging/Production)
     ↓                                       ↓
  MLflow UI                          Model Serving (FastAPI)
  (compare runs)                     (A/B testing, monitoring)
```

Key patterns:
1. **Structured logging** — log params, metrics (per step), and artifacts (models, configs) for reproducibility
2. **Optuna + MLflow** — Optuna suggests hyperparameters, MLflow tracks each trial as a run
3. **Model registry** — versioned model management with staging → production promotion
4. **Best model checkpointing** — save model only when validation improves; log best epoch
5. **Run comparison** — query MLflow API to rank runs by metric and identify best configurations'''
    ),
    (
        "ai/feature-store",
        "Show feature store patterns: online/offline serving, feature engineering pipelines, and point-in-time joins with Feast.",
        '''Feature store patterns with Feast:

```python
from feast import FeatureStore, Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64, String
from datetime import timedelta
import pandas as pd
import numpy as np


# === Feature Store Definition ===

# feature_repo/feature_definitions.py

# Entity: the primary key for feature lookup
user = Entity(
    name="user_id",
    description="Unique user identifier",
    join_keys=["user_id"],
)

merchant = Entity(
    name="merchant_id",
    description="Unique merchant identifier",
    join_keys=["merchant_id"],
)

# Data source: where raw features come from
user_stats_source = FileSource(
    path="data/user_stats.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

transaction_source = FileSource(
    path="data/transaction_features.parquet",
    timestamp_field="event_timestamp",
)

# Feature views: logical groups of features
user_stats_fv = FeatureView(
    name="user_stats",
    entities=[user],
    ttl=timedelta(days=1),
    schema=[
        Field(name="total_transactions", dtype=Int64),
        Field(name="avg_transaction_amount", dtype=Float32),
        Field(name="days_since_last_transaction", dtype=Int64),
        Field(name="transaction_frequency_7d", dtype=Float32),
        Field(name="unique_merchants_30d", dtype=Int64),
        Field(name="max_transaction_amount_7d", dtype=Float32),
        Field(name="account_age_days", dtype=Int64),
        Field(name="risk_score", dtype=Float32),
    ],
    source=user_stats_source,
    online=True,   # Available for real-time serving
)

transaction_fv = FeatureView(
    name="transaction_context",
    entities=[user, merchant],
    ttl=timedelta(hours=1),
    schema=[
        Field(name="amount", dtype=Float32),
        Field(name="is_international", dtype=Int64),
        Field(name="merchant_category", dtype=String),
        Field(name="hour_of_day", dtype=Int64),
        Field(name="day_of_week", dtype=Int64),
        Field(name="distance_from_home_km", dtype=Float32),
    ],
    source=transaction_source,
    online=True,
)


# === Feature Engineering Pipeline ===

def compute_user_features(transactions: pd.DataFrame) -> pd.DataFrame:
    """Compute aggregate user features from raw transactions."""
    now = pd.Timestamp.now()

    features = transactions.groupby("user_id").agg(
        total_transactions=("transaction_id", "count"),
        avg_transaction_amount=("amount", "mean"),
        max_transaction_amount_7d=("amount", lambda x: x[
            transactions.loc[x.index, "timestamp"] > now - timedelta(days=7)
        ].max() if len(x) > 0 else 0),
        transaction_frequency_7d=("transaction_id", lambda x: len(x[
            transactions.loc[x.index, "timestamp"] > now - timedelta(days=7)
        ])),
        unique_merchants_30d=("merchant_id", lambda x: x[
            transactions.loc[x.index, "timestamp"] > now - timedelta(days=30)
        ].nunique()),
        last_transaction=("timestamp", "max"),
        first_transaction=("timestamp", "min"),
    ).reset_index()

    features["days_since_last_transaction"] = (now - features["last_transaction"]).dt.days
    features["account_age_days"] = (now - features["first_transaction"]).dt.days
    features["risk_score"] = compute_risk_score(features)
    features["event_timestamp"] = now
    features["created_timestamp"] = now

    return features.drop(columns=["last_transaction", "first_transaction"])


def compute_risk_score(features: pd.DataFrame) -> pd.Series:
    """Simple risk scoring based on behavioral features."""
    score = np.zeros(len(features))
    score += (features["transaction_frequency_7d"] > 20).astype(float) * 0.3
    score += (features["avg_transaction_amount"] > 1000).astype(float) * 0.2
    score += (features["unique_merchants_30d"] > 15).astype(float) * 0.1
    score += (features["days_since_last_transaction"] > 30).astype(float) * -0.2
    return score.clip(0, 1)


# === Online Serving (real-time predictions) ===

class FraudPredictionService:
    """Real-time fraud prediction using feature store."""

    def __init__(self, feature_store_path: str = "feature_repo/"):
        self.store = FeatureStore(repo_path=feature_store_path)
        self.model = self._load_model()

    def predict(self, user_id: int, merchant_id: int,
                transaction: dict) -> dict:
        """Get features from store + real-time features -> prediction."""

        # Fetch pre-computed features from online store (< 10ms)
        entity_rows = [{"user_id": user_id, "merchant_id": merchant_id}]
        feature_vector = self.store.get_online_features(
            features=[
                "user_stats:total_transactions",
                "user_stats:avg_transaction_amount",
                "user_stats:risk_score",
                "user_stats:transaction_frequency_7d",
                "transaction_context:merchant_category",
            ],
            entity_rows=entity_rows,
        ).to_dict()

        # Combine with real-time transaction features
        features = {
            **{k: v[0] for k, v in feature_vector.items()},
            "amount": transaction["amount"],
            "hour_of_day": transaction["timestamp"].hour,
        }

        # Model prediction
        score = self.model.predict(features)
        return {"fraud_probability": score, "features_used": list(features.keys())}

    def _load_model(self):
        # Load trained model
        pass


# === Offline Training (point-in-time correct) ===

def get_training_data(store: FeatureStore, labels: pd.DataFrame) -> pd.DataFrame:
    """Fetch historical features with point-in-time correctness.

    Point-in-time join ensures no data leakage: features are
    retrieved as they were AT THE TIME of each label event.
    """
    training_df = store.get_historical_features(
        entity_df=labels[["user_id", "merchant_id", "event_timestamp"]],
        features=[
            "user_stats:total_transactions",
            "user_stats:avg_transaction_amount",
            "user_stats:risk_score",
            "user_stats:transaction_frequency_7d",
            "user_stats:unique_merchants_30d",
            "transaction_context:is_international",
            "transaction_context:distance_from_home_km",
        ],
    ).to_df()

    # Join labels
    training_df = training_df.merge(
        labels[["user_id", "merchant_id", "event_timestamp", "is_fraud"]],
        on=["user_id", "merchant_id", "event_timestamp"],
    )

    return training_df
```

Feature store architecture:
```
Raw Data → Feature Engineering → Offline Store (Parquet/BigQuery)
                                        ↓
                                 Materialization job
                                        ↓
                                 Online Store (Redis/DynamoDB)
                                        ↓
                                 Real-time Serving (< 10ms)
```

Key patterns:
1. **Online vs offline** — online store (Redis) for real-time serving; offline store (Parquet) for training
2. **Point-in-time joins** — prevent data leakage by fetching features as they existed at label time
3. **Feature views** — logical groups of features with TTL, entities, and source definitions
4. **Materialization** — periodic job pushes computed features from offline to online store
5. **Feature reuse** — same features serve both training and inference; prevents training-serving skew'''
    ),
]
