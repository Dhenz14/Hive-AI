"""ML serving — model deployment, inference APIs, and batch prediction patterns."""

PAIRS = [
    (
        "ml/model-serving",
        "Show ML model serving patterns: FastAPI inference endpoint, model loading, batching, and health checks.",
        '''ML model serving patterns:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from typing import Any
import numpy as np
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


# --- Model manager (singleton, lazy loading) ---

class ModelManager:
    """Manage ML model lifecycle: load, predict, health check."""

    def __init__(self):
        self.model = None
        self.model_name = ""
        self.model_version = ""
        self.loaded_at = None
        self._lock = asyncio.Lock()

    async def load(self, model_path: str):
        async with self._lock:
            logger.info("Loading model from %s", model_path)
            start = time.monotonic()

            # Example: load ONNX model
            # import onnxruntime as ort
            # self.model = ort.InferenceSession(model_path)

            # Example: load PyTorch model
            # import torch
            # self.model = torch.jit.load(model_path)
            # self.model.eval()

            # Example: load scikit-learn model
            import joblib
            self.model = joblib.load(model_path)

            elapsed = time.monotonic() - start
            self.model_name = model_path.split("/")[-1]
            self.model_version = "1.0.0"
            self.loaded_at = time.time()
            logger.info("Model loaded in %.2fs", elapsed)

    def predict(self, features: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        return self.model.predict(features)

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not loaded")
        return self.model.predict_proba(features)

    @property
    def is_ready(self) -> bool:
        return self.model is not None


model_manager = ModelManager()


# --- FastAPI with lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load model
    await model_manager.load("models/classifier_v1.joblib")
    yield
    # Shutdown: cleanup
    logger.info("Shutting down model server")

app = FastAPI(title="ML Inference API", lifespan=lifespan)


# --- Request/Response models ---

class PredictionRequest(BaseModel):
    features: list[list[float]] = Field(
        ..., min_length=1, max_length=1000,
        description="2D array of features [samples x features]",
    )
    return_probabilities: bool = False

class PredictionResponse(BaseModel):
    predictions: list[Any]
    probabilities: list[list[float]] | None = None
    model_version: str
    latency_ms: float

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str
    model_version: str
    uptime_seconds: float


# --- Endpoints ---

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    if not model_manager.is_ready:
        raise HTTPException(status_code=503, detail="Model not loaded")

    start = time.monotonic()

    features = np.array(request.features)

    # Run prediction (offload to thread for CPU-bound work)
    predictions = await asyncio.to_thread(model_manager.predict, features)

    probabilities = None
    if request.return_probabilities:
        proba = await asyncio.to_thread(model_manager.predict_proba, features)
        probabilities = proba.tolist()

    latency = (time.monotonic() - start) * 1000

    return PredictionResponse(
        predictions=predictions.tolist(),
        probabilities=probabilities,
        model_version=model_manager.model_version,
        latency_ms=round(latency, 2),
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    uptime = time.time() - model_manager.loaded_at if model_manager.loaded_at else 0
    return HealthResponse(
        status="healthy" if model_manager.is_ready else "degraded",
        model_loaded=model_manager.is_ready,
        model_name=model_manager.model_name,
        model_version=model_manager.model_version,
        uptime_seconds=round(uptime, 1),
    )


@app.get("/ready")
async def readiness():
    if not model_manager.is_ready:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"ready": True}


# --- Request batching (accumulate + batch predict) ---

class PredictionBatcher:
    """Accumulate individual requests into batches for efficient GPU inference."""

    def __init__(self, model_manager: ModelManager, max_batch: int = 32, max_wait_ms: float = 50):
        self.model = model_manager
        self.max_batch = max_batch
        self.max_wait = max_wait_ms / 1000
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._batch_worker())

    async def predict(self, features: list[float]) -> list[float]:
        future = asyncio.get_event_loop().create_future()
        await self._queue.put((features, future))
        return await future

    async def _batch_worker(self):
        while True:
            batch = []
            futures = []

            # Collect items up to max_batch or max_wait
            try:
                features, future = await asyncio.wait_for(
                    self._queue.get(), timeout=self.max_wait,
                )
                batch.append(features)
                futures.append(future)
            except asyncio.TimeoutError:
                continue

            # Drain queue up to max_batch
            while len(batch) < self.max_batch and not self._queue.empty():
                features, future = self._queue.get_nowait()
                batch.append(features)
                futures.append(future)

            # Batch predict
            try:
                input_array = np.array(batch)
                results = await asyncio.to_thread(self.model.predict, input_array)

                for future, result in zip(futures, results):
                    future.set_result(result.tolist())
            except Exception as e:
                for future in futures:
                    future.set_exception(e)
```

ML serving patterns:
1. **`asynccontextmanager` lifespan** — load model at startup, cleanup at shutdown
2. **`asyncio.to_thread()`** — offload CPU-bound inference to thread pool
3. **Health + readiness endpoints** — K8s probe compatibility
4. **Request batching** — accumulate individual requests for efficient batch inference
5. **`PredictionResponse`** — include model version and latency for monitoring'''
    ),
    (
        "ml/feature-engineering",
        "Show feature engineering patterns: feature pipelines, transformations, and feature stores.",
        '''Feature engineering patterns:

```python
from dataclasses import dataclass, field
from typing import Callable, Any
from datetime import datetime, timezone
import numpy as np
from collections import defaultdict


# --- Feature transformer pipeline ---

@dataclass
class FeatureConfig:
    name: str
    dtype: str = "float"
    default: Any = 0.0
    description: str = ""


class FeatureTransformer:
    """Composable feature transformation pipeline."""

    def __init__(self):
        self._transforms: list[tuple[str, Callable]] = []
        self._fitted_params: dict[str, Any] = {}

    def add(self, name: str, fn: Callable) -> "FeatureTransformer":
        self._transforms.append((name, fn))
        return self

    def fit(self, data: list[dict]) -> "FeatureTransformer":
        """Learn parameters from training data."""
        # Example: compute statistics for normalization
        numeric_cols = defaultdict(list)
        for row in data:
            for key, value in row.items():
                if isinstance(value, (int, float)):
                    numeric_cols[key].append(value)

        for col, values in numeric_cols.items():
            arr = np.array(values)
            self._fitted_params[f"{col}_mean"] = float(np.mean(arr))
            self._fitted_params[f"{col}_std"] = float(np.std(arr)) or 1.0
            self._fitted_params[f"{col}_min"] = float(np.min(arr))
            self._fitted_params[f"{col}_max"] = float(np.max(arr))

        return self

    def transform(self, row: dict) -> dict:
        """Apply all transformations to a single row."""
        result = dict(row)
        for name, fn in self._transforms:
            try:
                result = fn(result, self._fitted_params)
            except Exception as e:
                result[f"_error_{name}"] = str(e)
        return result

    def transform_batch(self, data: list[dict]) -> list[dict]:
        return [self.transform(row) for row in data]


# --- Common transformations ---

def normalize(row: dict, params: dict) -> dict:
    """Z-score normalization using fitted params."""
    for key in list(row.keys()):
        mean_key = f"{key}_mean"
        std_key = f"{key}_std"
        if mean_key in params and isinstance(row[key], (int, float)):
            row[f"{key}_normalized"] = (
                (row[key] - params[mean_key]) / params[std_key]
            )
    return row


def one_hot_encode(columns: list[str], categories: dict[str, list[str]]):
    """One-hot encode categorical columns."""
    def transform(row: dict, params: dict) -> dict:
        for col in columns:
            value = row.get(col, "")
            for cat in categories.get(col, []):
                row[f"{col}_{cat}"] = 1.0 if value == cat else 0.0
        return row
    return transform


def time_features(timestamp_col: str):
    """Extract time-based features from a timestamp."""
    def transform(row: dict, params: dict) -> dict:
        ts = row.get(timestamp_col)
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if isinstance(ts, datetime):
            row[f"{timestamp_col}_hour"] = ts.hour
            row[f"{timestamp_col}_day_of_week"] = ts.weekday()
            row[f"{timestamp_col}_month"] = ts.month
            row[f"{timestamp_col}_is_weekend"] = 1.0 if ts.weekday() >= 5 else 0.0
        return row
    return transform


def interaction_features(col_a: str, col_b: str):
    """Create interaction feature (product of two columns)."""
    def transform(row: dict, params: dict) -> dict:
        a = row.get(col_a, 0)
        b = row.get(col_b, 0)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            row[f"{col_a}_x_{col_b}"] = a * b
        return row
    return transform


def log_transform(columns: list[str]):
    """Log transform for skewed distributions."""
    def transform(row: dict, params: dict) -> dict:
        for col in columns:
            value = row.get(col)
            if isinstance(value, (int, float)) and value > 0:
                row[f"{col}_log"] = float(np.log1p(value))
        return row
    return transform


def clip_outliers(columns: list[str], n_std: float = 3.0):
    """Clip outliers beyond n standard deviations."""
    def transform(row: dict, params: dict) -> dict:
        for col in columns:
            value = row.get(col)
            mean = params.get(f"{col}_mean")
            std = params.get(f"{col}_std")
            if all(v is not None for v in [value, mean, std]):
                lower = mean - n_std * std
                upper = mean + n_std * std
                row[col] = max(lower, min(upper, value))
        return row
    return transform


# --- Build pipeline ---

pipeline = (
    FeatureTransformer()
    .add("time_features", time_features("created_at"))
    .add("one_hot", one_hot_encode(
        ["category"], {"category": ["electronics", "books", "clothing"]},
    ))
    .add("log_price", log_transform(["price", "quantity"]))
    .add("clip", clip_outliers(["price", "quantity"]))
    .add("normalize", normalize)
    .add("interaction", interaction_features("price", "quantity"))
)

# Fit on training data
pipeline.fit(training_data)

# Transform single row (for real-time inference)
features = pipeline.transform({"price": 29.99, "quantity": 5, "category": "books"})

# Transform batch (for batch prediction)
batch_features = pipeline.transform_batch(test_data)
```

Feature engineering patterns:
1. **Composable pipeline** — chain transforms with `.add()`, apply in order
2. **`fit()` / `transform()`** — learn statistics from training data, apply to new data
3. **Time features** — extract hour, day_of_week, is_weekend from timestamps
4. **`log1p` transform** — handle skewed distributions (prices, counts)
5. **Interaction features** — product of columns captures non-linear relationships'''
    ),
]
