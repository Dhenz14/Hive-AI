"""Model quantization, pruning, and optimization for deployment."""

PAIRS = [
    (
        "ml/model-quantization",
        "Explain model quantization techniques: post-training quantization, quantization-aware training, and GPTQ/AWQ for LLMs. Show practical examples.",
        '''Model quantization reduces model size and inference cost:

```python
import torch
import torch.nn as nn
from torch.quantization import quantize_dynamic, prepare, convert
import numpy as np

# --- Post-Training Dynamic Quantization ---
# Simplest approach: quantize weights to INT8 at runtime

class SimpleModel(nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        return self.fc2(self.relu(self.fc1(x)))

model = SimpleModel(768, 256, 10)

# Dynamic quantization — weights quantized, activations at runtime
quantized_model = quantize_dynamic(
    model,
    {nn.Linear},  # Which layers to quantize
    dtype=torch.qint8,
)

# Compare sizes
def model_size_mb(model):
    param_size = sum(p.nelement() * p.element_size() for p in model.parameters())
    buffer_size = sum(b.nelement() * b.element_size() for b in model.buffers())
    return (param_size + buffer_size) / 1024 / 1024

print(f"Original: {model_size_mb(model):.2f} MB")
print(f"Quantized: {model_size_mb(quantized_model):.2f} MB")

# --- Static Quantization (calibration required) ---

class QuantizableModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.quant = torch.quantization.QuantStub()
        self.fc1 = nn.Linear(768, 256)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(256, 10)
        self.dequant = torch.quantization.DeQuantStub()

    def forward(self, x):
        x = self.quant(x)
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        x = self.dequant(x)
        return x

model = QuantizableModel()
model.eval()

# Configure quantization
model.qconfig = torch.quantization.get_default_qconfig("x86")
prepared = prepare(model)

# Calibrate with representative data
calibration_data = torch.randn(1000, 768)
with torch.no_grad():
    for i in range(0, len(calibration_data), 32):
        prepared(calibration_data[i:i+32])

# Convert to quantized model
quantized = convert(prepared)

# --- Quantization-Aware Training (QAT) ---

model = QuantizableModel()
model.train()
model.qconfig = torch.quantization.get_default_qat_qconfig("x86")
prepared_qat = torch.quantization.prepare_qat(model)

# Train with fake quantization nodes
optimizer = torch.optim.Adam(prepared_qat.parameters(), lr=1e-4)
for epoch in range(5):
    for batch_x, batch_y in train_loader:
        optimizer.zero_grad()
        output = prepared_qat(batch_x)
        loss = nn.CrossEntropyLoss()(output, batch_y)
        loss.backward()
        optimizer.step()

# Convert to actual quantized model
prepared_qat.eval()
quantized_qat = convert(prepared_qat)

# --- GPTQ for LLMs (via auto-gptq) ---
# GPTQ: layer-wise weight quantization using second-order information

from transformers import AutoModelForCausalLM, AutoTokenizer

# With auto-gptq
GPTQ_CONFIG = """
# Using auto-gptq Python API:
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

quantize_config = BaseQuantizeConfig(
    bits=4,                  # 4-bit quantization
    group_size=128,          # Quantize in groups of 128
    desc_act=True,           # Activation-order quantization
    damp_percent=0.01,       # Dampening for Hessian
)

# Load model
model = AutoGPTQForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b-hf",
    quantize_config=quantize_config,
)
tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-2-7b-hf")

# Quantize with calibration data
calibration_texts = load_calibration_dataset()
examples = [tokenizer(t, return_tensors="pt") for t in calibration_texts[:128]]
model.quantize(examples)

# Save quantized model
model.save_quantized("llama-2-7b-gptq-4bit")
"""

# --- GGUF quantization (for llama.cpp) ---
GGUF_COMMANDS = """
# Convert HF model to GGUF
python convert_hf_to_gguf.py ./model-dir --outfile model-f16.gguf --outtype f16

# Quantize to various formats
./llama-quantize model-f16.gguf model-Q4_K_M.gguf Q4_K_M
./llama-quantize model-f16.gguf model-Q5_K_M.gguf Q5_K_M
./llama-quantize model-f16.gguf model-Q8_0.gguf Q8_0

# Quantization format comparison:
# Q4_K_M: 4-bit, medium quality    | ~4.0 bpw | Good balance
# Q5_K_M: 5-bit, medium quality    | ~5.0 bpw | Better quality
# Q6_K:   6-bit                    | ~6.0 bpw | Near-FP16 quality
# Q8_0:   8-bit                    | ~8.0 bpw | Minimal quality loss
# IQ4_XS: 4-bit, importance-aware  | ~4.2 bpw | Best 4-bit quality
"""
```

Quantization tradeoffs:
| Method | Size Reduction | Speed | Quality | Effort |
|--------|---------------|-------|---------|--------|
| Dynamic INT8 | 2-4x | 1.5-2x | ~99% | None |
| Static INT8 | 2-4x | 2-3x | ~98% | Calibration |
| QAT INT8 | 2-4x | 2-3x | ~99.5% | Retraining |
| GPTQ 4-bit | 4-8x | 2-3x | ~95-97% | Calibration |
| AWQ 4-bit | 4-8x | 2-3x | ~96-98% | Calibration |
| GGUF Q4_K_M | 4-8x | CPU-friendly | ~95% | None |'''
    ),
    (
        "ml/time-series-forecasting",
        "Show time series forecasting patterns: classical methods, feature engineering, and modern approaches with Prophet and neural forecasters.",
        '''Time series forecasting from classical to modern methods:

```python
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# --- Feature Engineering for Time Series ---

def create_time_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Extract temporal features from datetime column."""
    df = df.copy()
    dt = pd.to_datetime(df[date_col])

    # Calendar features
    df["day_of_week"] = dt.dt.dayofweek
    df["day_of_month"] = dt.dt.day
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter
    df["year"] = dt.dt.year
    df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
    df["is_month_start"] = dt.dt.is_month_start.astype(int)
    df["is_month_end"] = dt.dt.is_month_end.astype(int)

    # Cyclical encoding (prevents 12→1 discontinuity)
    df["month_sin"] = np.sin(2 * np.pi * dt.dt.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * dt.dt.month / 12)
    df["dow_sin"] = np.sin(2 * np.pi * dt.dt.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dt.dt.dayofweek / 7)

    return df

def create_lag_features(df: pd.DataFrame, target: str,
                        lags: list[int], windows: list[int]) -> pd.DataFrame:
    """Create lag and rolling window features."""
    df = df.copy()

    # Lag features
    for lag in lags:
        df[f"{target}_lag_{lag}"] = df[target].shift(lag)

    # Rolling statistics
    for window in windows:
        df[f"{target}_rolling_mean_{window}"] = (
            df[target].shift(1).rolling(window).mean()
        )
        df[f"{target}_rolling_std_{window}"] = (
            df[target].shift(1).rolling(window).std()
        )
        df[f"{target}_rolling_min_{window}"] = (
            df[target].shift(1).rolling(window).min()
        )
        df[f"{target}_rolling_max_{window}"] = (
            df[target].shift(1).rolling(window).max()
        )

    # Expanding features
    df[f"{target}_expanding_mean"] = df[target].shift(1).expanding().mean()

    return df

# --- Prophet for business forecasting ---

from prophet import Prophet

def forecast_with_prophet(df: pd.DataFrame, periods: int = 30) -> pd.DataFrame:
    """Forecast using Facebook Prophet with holidays and regressors."""
    # Prophet requires columns: ds (date), y (value)
    prophet_df = df.rename(columns={"date": "ds", "sales": "y"})

    model = Prophet(
        growth="linear",
        seasonality_mode="multiplicative",
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,  # Flexibility of trend
        seasonality_prior_scale=10.0,  # Flexibility of seasonality
    )

    # Custom seasonality
    model.add_seasonality(
        name="monthly",
        period=30.5,
        fourier_order=5,
    )

    # External regressors
    if "temperature" in df.columns:
        model.add_regressor("temperature")
    if "is_holiday" in df.columns:
        model.add_regressor("is_holiday", mode="multiplicative")

    model.fit(prophet_df)

    # Create future dataframe
    future = model.make_future_dataframe(periods=periods)
    # Fill in regressors for future dates
    if "temperature" in df.columns:
        future["temperature"] = get_weather_forecast(periods)

    forecast = model.predict(future)
    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

# --- Cross-validation for time series ---

def time_series_cv(model_fn, df, target, n_splits=5, test_size=30):
    """Walk-forward validation — never look into the future."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    results = []
    total_size = len(df)
    train_size = total_size - (n_splits * test_size)

    for i in range(n_splits):
        train_end = train_size + (i * test_size)
        test_end = train_end + test_size

        train = df.iloc[:train_end]
        test = df.iloc[train_end:test_end]

        model = model_fn()
        model.fit(train.drop(columns=[target]), train[target])
        predictions = model.predict(test.drop(columns=[target]))

        mae = mean_absolute_error(test[target], predictions)
        rmse = np.sqrt(mean_squared_error(test[target], predictions))

        results.append({
            "fold": i,
            "train_size": len(train),
            "test_start": train_end,
            "mae": mae,
            "rmse": rmse,
        })

    return pd.DataFrame(results)

# --- Anomaly detection in time series ---

def detect_anomalies_zscore(series: pd.Series, window: int = 30,
                            threshold: float = 3.0) -> pd.Series:
    """Detect anomalies using rolling z-score."""
    rolling_mean = series.rolling(window, center=False).mean()
    rolling_std = series.rolling(window, center=False).std()
    z_scores = (series - rolling_mean) / rolling_std
    return z_scores.abs() > threshold

def detect_anomalies_iqr(series: pd.Series, window: int = 30,
                         factor: float = 1.5) -> pd.Series:
    """Detect anomalies using rolling IQR method."""
    rolling_q1 = series.rolling(window).quantile(0.25)
    rolling_q3 = series.rolling(window).quantile(0.75)
    iqr = rolling_q3 - rolling_q1
    lower = rolling_q1 - factor * iqr
    upper = rolling_q3 + factor * iqr
    return (series < lower) | (series > upper)
```

Method selection:
- **ARIMA/SARIMA** — stationary data, well-understood seasonality
- **Prophet** — business time series with holidays, multiple seasonalities
- **XGBoost with lag features** — when you have strong exogenous features
- **N-BEATS/TFT** — complex patterns, multiple related series
- **Walk-forward CV** — always validate with time-respecting splits'''
    ),
    (
        "ml/recommendation-systems",
        "Explain recommendation system architectures: collaborative filtering, content-based, hybrid approaches, and two-tower models.",
        '''Recommendation system implementations from simple to production:

```python
import numpy as np
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional
import heapq

# --- Collaborative Filtering (memory-based) ---

class UserBasedCF:
    """User-user collaborative filtering with cosine similarity."""

    def __init__(self):
        self.user_items: dict[str, dict[str, float]] = {}  # user -> {item: rating}
        self.item_users: dict[str, set[str]] = defaultdict(set)

    def fit(self, interactions: list[tuple[str, str, float]]):
        for user, item, rating in interactions:
            if user not in self.user_items:
                self.user_items[user] = {}
            self.user_items[user][item] = rating
            self.item_users[item].add(user)

    def _cosine_similarity(self, user_a: str, user_b: str) -> float:
        items_a = self.user_items[user_a]
        items_b = self.user_items[user_b]
        common = set(items_a) & set(items_b)

        if not common:
            return 0.0

        dot = sum(items_a[i] * items_b[i] for i in common)
        norm_a = np.sqrt(sum(v**2 for v in items_a.values()))
        norm_b = np.sqrt(sum(v**2 for v in items_b.values()))

        return dot / (norm_a * norm_b + 1e-8)

    def recommend(self, user: str, n: int = 10, k_neighbors: int = 20) -> list[tuple[str, float]]:
        if user not in self.user_items:
            return []

        # Find similar users
        similarities = []
        for other in self.user_items:
            if other != user:
                sim = self._cosine_similarity(user, other)
                if sim > 0:
                    similarities.append((other, sim))

        # Top-k neighbors
        neighbors = sorted(similarities, key=lambda x: -x[1])[:k_neighbors]

        # Score unseen items
        user_items = set(self.user_items[user])
        scores: dict[str, float] = defaultdict(float)
        weights: dict[str, float] = defaultdict(float)

        for neighbor, sim in neighbors:
            for item, rating in self.user_items[neighbor].items():
                if item not in user_items:
                    scores[item] += sim * rating
                    weights[item] += abs(sim)

        # Normalize
        recommendations = [
            (item, scores[item] / (weights[item] + 1e-8))
            for item in scores
        ]
        return sorted(recommendations, key=lambda x: -x[1])[:n]

# --- Matrix Factorization (ALS) ---

class ALSRecommender:
    """Alternating Least Squares for matrix factorization."""

    def __init__(self, n_factors: int = 50, reg: float = 0.01, n_iters: int = 20):
        self.n_factors = n_factors
        self.reg = reg
        self.n_iters = n_iters

    def fit(self, user_ids: np.ndarray, item_ids: np.ndarray, ratings: np.ndarray):
        self.n_users = user_ids.max() + 1
        self.n_items = item_ids.max() + 1

        # Initialize factor matrices
        self.user_factors = np.random.normal(0, 0.1, (self.n_users, self.n_factors))
        self.item_factors = np.random.normal(0, 0.1, (self.n_items, self.n_factors))

        # Build sparse interaction maps
        user_to_items = defaultdict(list)
        item_to_users = defaultdict(list)
        for u, i, r in zip(user_ids, item_ids, ratings):
            user_to_items[u].append((i, r))
            item_to_users[i].append((u, r))

        # Alternating optimization
        for iteration in range(self.n_iters):
            # Fix items, solve for users
            for u in range(self.n_users):
                if u not in user_to_items:
                    continue
                items = user_to_items[u]
                item_idx = [i for i, _ in items]
                ratings_u = np.array([r for _, r in items])
                V = self.item_factors[item_idx]  # (n_rated, factors)
                self.user_factors[u] = np.linalg.solve(
                    V.T @ V + self.reg * np.eye(self.n_factors),
                    V.T @ ratings_u,
                )

            # Fix users, solve for items
            for i in range(self.n_items):
                if i not in item_to_users:
                    continue
                users = item_to_users[i]
                user_idx = [u for u, _ in users]
                ratings_i = np.array([r for _, r in users])
                U = self.user_factors[user_idx]
                self.item_factors[i] = np.linalg.solve(
                    U.T @ U + self.reg * np.eye(self.n_factors),
                    U.T @ ratings_i,
                )

    def predict(self, user_id: int, item_id: int) -> float:
        return self.user_factors[user_id] @ self.item_factors[item_id]

    def recommend(self, user_id: int, n: int = 10,
                  exclude: Optional[set[int]] = None) -> list[tuple[int, float]]:
        scores = self.user_factors[user_id] @ self.item_factors.T
        if exclude:
            for idx in exclude:
                scores[idx] = -np.inf
        top_n = np.argsort(scores)[-n:][::-1]
        return [(int(idx), float(scores[idx])) for idx in top_n]

# --- Two-Tower Model (retrieval) ---

import torch
import torch.nn as nn
import torch.nn.functional as F

class TwoTowerModel(nn.Module):
    """Dual encoder for candidate retrieval."""

    def __init__(self, n_users: int, n_items: int,
                 embedding_dim: int = 64, hidden_dim: int = 128):
        super().__init__()

        # User tower
        self.user_embedding = nn.Embedding(n_users, embedding_dim)
        self.user_mlp = nn.Sequential(
            nn.Linear(embedding_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, embedding_dim),
            nn.LayerNorm(embedding_dim),
        )

        # Item tower
        self.item_embedding = nn.Embedding(n_items, embedding_dim)
        self.item_mlp = nn.Sequential(
            nn.Linear(embedding_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, embedding_dim),
            nn.LayerNorm(embedding_dim),
        )

        self.temperature = nn.Parameter(torch.tensor(0.07))

    def encode_user(self, user_ids: torch.Tensor) -> torch.Tensor:
        x = self.user_embedding(user_ids)
        return F.normalize(self.user_mlp(x), dim=-1)

    def encode_item(self, item_ids: torch.Tensor) -> torch.Tensor:
        x = self.item_embedding(item_ids)
        return F.normalize(self.item_mlp(x), dim=-1)

    def forward(self, user_ids, pos_items, neg_items):
        user_emb = self.encode_user(user_ids)          # (B, D)
        pos_emb = self.encode_item(pos_items)           # (B, D)
        neg_emb = self.encode_item(neg_items)           # (B, N, D)

        pos_score = (user_emb * pos_emb).sum(-1) / self.temperature
        neg_score = (user_emb.unsqueeze(1) * neg_emb).sum(-1) / self.temperature

        # InfoNCE loss
        logits = torch.cat([pos_score.unsqueeze(1), neg_score], dim=1)
        labels = torch.zeros(len(user_ids), dtype=torch.long, device=logits.device)
        return F.cross_entropy(logits, labels)
```

Production architecture:
1. **Retrieval** (two-tower) — fast candidate generation from millions of items via ANN search
2. **Ranking** — detailed scoring of ~100 candidates with full feature model
3. **Re-ranking** — business rules, diversity, freshness, fairness constraints'''
    ),
]
