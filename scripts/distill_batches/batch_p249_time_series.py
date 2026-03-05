"""Time series forecasting — transformer models, anomaly detection, feature engineering."""

PAIRS = [
    (
        "ai/time-series-transformer",
        "Show time series forecasting with transformers: PatchTST-style patching, temporal embeddings, and multi-horizon prediction.",
        '''Time series transformer forecasting:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class PatchEmbedding(nn.Module):
    """Patch time series into segments (PatchTST-style).

    Instead of token-per-timestep, group timesteps into patches.
    Reduces sequence length and captures local patterns.
    """

    def __init__(self, patch_len: int = 16, stride: int = 8, d_model: int = 256, n_features: int = 1):
        super().__init__()
        self.patch_len = patch_len
        self.stride = stride
        self.proj = nn.Linear(patch_len * n_features, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, T, C] -> patches: [B, n_patches, d_model]"""
        B, T, C = x.shape
        # Unfold into patches
        x = x.unfold(1, self.patch_len, self.stride)  # [B, n_patches, C, patch_len]
        x = x.reshape(B, -1, C * self.patch_len)       # [B, n_patches, C*patch_len]
        return self.proj(x)


class TemporalEmbedding(nn.Module):
    """Encode temporal features: hour, day of week, month, etc."""

    def __init__(self, d_model: int = 256):
        super().__init__()
        self.hour_embed = nn.Embedding(24, d_model)
        self.dow_embed = nn.Embedding(7, d_model)
        self.month_embed = nn.Embedding(12, d_model)

    def forward(self, timestamps: dict[str, torch.Tensor]) -> torch.Tensor:
        """Combine temporal embeddings."""
        embed = self.hour_embed(timestamps["hour"])
        embed = embed + self.dow_embed(timestamps["day_of_week"])
        embed = embed + self.month_embed(timestamps["month"])
        return embed


class TimeSeriesTransformer(nn.Module):
    """PatchTST-style forecaster for multivariate time series.

    Key innovations:
    - Patch embedding reduces sequence length
    - Channel independence: each variable processed separately
    - Instance normalization for distribution shift
    """

    def __init__(self, n_features: int = 7, d_model: int = 256,
                 n_heads: int = 8, n_layers: int = 3,
                 patch_len: int = 16, stride: int = 8,
                 lookback: int = 336, horizon: int = 96):
        super().__init__()
        self.n_features = n_features
        self.horizon = horizon

        # Per-channel patch embedding
        self.patch_embed = PatchEmbedding(patch_len, stride, d_model, n_features=1)
        n_patches = (lookback - patch_len) // stride + 1

        self.pos_embed = nn.Parameter(torch.randn(1, n_patches, d_model) * 0.02)

        # Transformer encoder
        layer = nn.TransformerEncoderLayer(
            d_model, n_heads, d_model * 4, dropout=0.1,
            batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, n_layers)
        self.norm = nn.LayerNorm(d_model)

        # Prediction head: flatten patches -> predict horizon
        self.head = nn.Linear(n_patches * d_model, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, T, C] -> predictions: [B, horizon, C]"""
        B, T, C = x.shape

        # Instance normalization (RevIN)
        mean = x.mean(dim=1, keepdim=True)
        std = x.std(dim=1, keepdim=True).clamp(min=1e-5)
        x = (x - mean) / std

        # Channel-independent processing
        predictions = []
        for c in range(C):
            x_c = x[:, :, c:c+1]  # [B, T, 1]
            patches = self.patch_embed(x_c) + self.pos_embed
            encoded = self.encoder(patches)
            encoded = self.norm(encoded)
            flat = encoded.reshape(B, -1)
            pred = self.head(flat)  # [B, horizon]
            predictions.append(pred)

        predictions = torch.stack(predictions, dim=-1)  # [B, horizon, C]

        # Denormalize
        predictions = predictions * std + mean
        return predictions


class QuantileForecaster(nn.Module):
    """Probabilistic forecasting with quantile regression.

    Predict multiple quantiles (e.g., 10th, 50th, 90th percentile)
    for uncertainty estimation.
    """

    def __init__(self, base_model: nn.Module, quantiles: list[float] = None):
        super().__init__()
        self.base = base_model
        self.quantiles = quantiles or [0.1, 0.5, 0.9]
        d_model = 256
        self.quantile_heads = nn.ModuleList([
            nn.Linear(d_model, base_model.horizon) for _ in self.quantiles
        ])

    def forward(self, x):
        """Returns predictions for each quantile."""
        features = self.base.encoder(self.base.patch_embed(x[:, :, 0:1]))
        features = features.reshape(x.shape[0], -1)
        return {q: head(features) for q, head in zip(self.quantiles, self.quantile_heads)}

    @staticmethod
    def quantile_loss(predictions: dict, targets: torch.Tensor) -> torch.Tensor:
        """Pinball loss for quantile regression."""
        total_loss = 0
        for quantile, pred in predictions.items():
            errors = targets - pred
            loss = torch.where(
                errors >= 0,
                quantile * errors,
                (quantile - 1) * errors,
            )
            total_loss += loss.mean()
        return total_loss / len(predictions)
```

Key patterns:
1. **Patch embedding** — group timesteps into patches; reduces O(n²) attention cost
2. **Channel independence** — process each variable separately; prevents cross-channel leakage
3. **RevIN normalization** — instance normalize, predict, denormalize; handles distribution shift
4. **Quantile regression** — predict confidence intervals; pinball loss for each quantile
5. **Multi-horizon** — predict all future timesteps at once (direct forecasting) vs autoregressive'''
    ),
    (
        "ai/anomaly-detection-ts",
        "Show time series anomaly detection: statistical methods, autoencoders, and isolation forests for detecting outliers in temporal data.",
        '''Time series anomaly detection:

```python
import torch
import torch.nn as nn
import numpy as np
from dataclasses import dataclass
from collections import deque


@dataclass
class AnomalyResult:
    timestamp: int
    value: float
    score: float
    is_anomaly: bool
    method: str
    threshold: float


class StatisticalDetector:
    """Z-score and moving average anomaly detection."""

    def __init__(self, window_size: int = 100, z_threshold: float = 3.0):
        self.window = deque(maxlen=window_size)
        self.z_threshold = z_threshold

    def detect(self, value: float, timestamp: int) -> AnomalyResult:
        self.window.append(value)

        if len(self.window) < 10:
            return AnomalyResult(timestamp, value, 0.0, False, "z-score", self.z_threshold)

        mean = np.mean(self.window)
        std = np.std(self.window)
        z_score = abs(value - mean) / max(std, 1e-10)

        return AnomalyResult(
            timestamp=timestamp,
            value=value,
            score=z_score,
            is_anomaly=z_score > self.z_threshold,
            method="z-score",
            threshold=self.z_threshold,
        )


class AutoencoderDetector(nn.Module):
    """Reconstruction-based anomaly detection.

    Normal patterns: low reconstruction error.
    Anomalies: high reconstruction error (model hasn't seen similar patterns).
    """

    def __init__(self, seq_len: int = 64, n_features: int = 1, latent_dim: int = 16):
        super().__init__()
        input_dim = seq_len * n_features

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128), nn.ReLU(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64), nn.ReLU(),
            nn.Linear(64, 128), nn.ReLU(),
            nn.Linear(128, input_dim),
        )
        self.seq_len = seq_len
        self.n_features = n_features

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, seq_len, n_features] -> reconstruction"""
        B = x.shape[0]
        flat = x.reshape(B, -1)
        z = self.encoder(flat)
        recon = self.decoder(z)
        return recon.reshape(B, self.seq_len, self.n_features)

    def anomaly_score(self, x: torch.Tensor) -> torch.Tensor:
        """Reconstruction error as anomaly score."""
        recon = self.forward(x)
        return ((x - recon) ** 2).mean(dim=(1, 2))  # MSE per sample

    def fit_threshold(self, normal_data: torch.Tensor, percentile: float = 99.0) -> float:
        """Set threshold from normal data distribution."""
        with torch.no_grad():
            scores = self.anomaly_score(normal_data)
            return np.percentile(scores.numpy(), percentile)


class TemporalConvAE(nn.Module):
    """Temporal convolutional autoencoder for sequence anomaly detection."""

    def __init__(self, n_features: int = 1, seq_len: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv1d(n_features, 32, 7, padding=3), nn.ReLU(),
            nn.Conv1d(32, 16, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv1d(16, 8, 3, stride=2, padding=1), nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose1d(8, 16, 3, stride=2, padding=1, output_padding=1), nn.ReLU(),
            nn.ConvTranspose1d(16, 32, 5, stride=2, padding=2, output_padding=1), nn.ReLU(),
            nn.Conv1d(32, n_features, 7, padding=3),
        )

    def forward(self, x):
        """x: [B, features, time]"""
        z = self.encoder(x)
        return self.decoder(z)


class EnsembleDetector:
    """Combine multiple anomaly detectors for robustness."""

    def __init__(self, detectors: list, weights: list[float] = None):
        self.detectors = detectors
        self.weights = weights or [1.0 / len(detectors)] * len(detectors)

    def detect(self, data, **kwargs) -> dict:
        scores = []
        for detector, weight in zip(self.detectors, self.weights):
            if hasattr(detector, 'anomaly_score'):
                score = detector.anomaly_score(data)
            elif hasattr(detector, 'detect'):
                result = detector.detect(data, **kwargs)
                score = result.score
            else:
                continue
            scores.append(score * weight)

        ensemble_score = sum(scores)
        return {"score": ensemble_score, "per_detector": scores}
```

Key patterns:
1. **Reconstruction error** — autoencoders learn normal patterns; anomalies have high reconstruction loss
2. **Z-score baseline** — simple but effective; works well for stationary data
3. **Sliding window** — process fixed-length subsequences; detect local anomalies
4. **Threshold from normal data** — fit threshold on clean data using 99th percentile
5. **Ensemble** — combine multiple detectors for robustness; reduce false positives'''
    ),
    (
        "ai/feature-engineering-ts",
        "Show time series feature engineering: lag features, rolling statistics, Fourier features, and automated feature generation.",
        '''Time series feature engineering:

```python
import numpy as np
import pandas as pd
from typing import Optional


class TimeSeriesFeatureEngineer:
    """Comprehensive feature engineering for time series.

    Features fall into categories:
    - Lag features (autoregressive)
    - Rolling statistics (windowed)
    - Calendar features (temporal)
    - Fourier features (seasonal)
    - Difference features (trend/stationarity)
    """

    def __init__(self, target_col: str = "value", date_col: str = "timestamp"):
        self.target_col = target_col
        self.date_col = date_col

    def create_lag_features(self, df: pd.DataFrame, lags: list[int] = None) -> pd.DataFrame:
        """Create lagged versions of target variable."""
        lags = lags or [1, 2, 3, 7, 14, 28]
        result = df.copy()
        for lag in lags:
            result[f"lag_{lag}"] = result[self.target_col].shift(lag)
        return result

    def create_rolling_features(self, df: pd.DataFrame,
                                 windows: list[int] = None) -> pd.DataFrame:
        """Rolling statistics: mean, std, min, max, skew."""
        windows = windows or [7, 14, 30]
        result = df.copy()
        for w in windows:
            rolling = result[self.target_col].rolling(window=w)
            result[f"roll_mean_{w}"] = rolling.mean()
            result[f"roll_std_{w}"] = rolling.std()
            result[f"roll_min_{w}"] = rolling.min()
            result[f"roll_max_{w}"] = rolling.max()
            result[f"roll_skew_{w}"] = rolling.skew()
            # Exponential moving average
            result[f"ewm_{w}"] = result[self.target_col].ewm(span=w).mean()
        return result

    def create_calendar_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract calendar features from datetime."""
        result = df.copy()
        dt = pd.to_datetime(result[self.date_col])
        result["hour"] = dt.dt.hour
        result["day_of_week"] = dt.dt.dayofweek
        result["day_of_month"] = dt.dt.day
        result["month"] = dt.dt.month
        result["is_weekend"] = dt.dt.dayofweek.isin([5, 6]).astype(int)
        result["quarter"] = dt.dt.quarter
        result["week_of_year"] = dt.dt.isocalendar().week.astype(int)
        return result

    def create_fourier_features(self, df: pd.DataFrame,
                                 periods: list[int] = None,
                                 n_harmonics: int = 3) -> pd.DataFrame:
        """Fourier features for capturing seasonality."""
        periods = periods or [24, 168, 8760]  # daily, weekly, yearly
        result = df.copy()
        t = np.arange(len(result))

        for period in periods:
            for k in range(1, n_harmonics + 1):
                result[f"sin_{period}_{k}"] = np.sin(2 * np.pi * k * t / period)
                result[f"cos_{period}_{k}"] = np.cos(2 * np.pi * k * t / period)
        return result

    def create_difference_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Difference features for stationarity."""
        result = df.copy()
        result["diff_1"] = result[self.target_col].diff(1)
        result["diff_7"] = result[self.target_col].diff(7)
        result["pct_change_1"] = result[self.target_col].pct_change(1)
        result["pct_change_7"] = result[self.target_col].pct_change(7)
        return result

    def create_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all features."""
        result = df.copy()
        result = self.create_lag_features(result)
        result = self.create_rolling_features(result)
        result = self.create_calendar_features(result)
        result = self.create_fourier_features(result)
        result = self.create_difference_features(result)
        return result.dropna()
```

Key patterns:
1. **Lag features** — autoregressive inputs; most important for short-term forecasting
2. **Rolling statistics** — capture local trends and volatility; multiple window sizes
3. **Fourier features** — sin/cos pairs encode cyclical patterns without discontinuities
4. **Calendar features** — hour, day-of-week, holiday flags; domain-specific seasonality
5. **Differencing** — first/seasonal differences for stationarity; pct_change for scale-invariance'''
    ),
    (
        "ai/automl-forecasting",
        "Show AutoML for time series: automated model selection, hyperparameter optimization, and ensemble methods for forecasting.",
        '''AutoML for time series forecasting:

```python
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class ForecastResult:
    model_name: str
    predictions: np.ndarray
    metrics: dict[str, float]
    params: dict[str, Any]


class TimeSeriesAutoML:
    """Automated model selection and ensembling for forecasting.

    Evaluates multiple model families and selects the best
    based on cross-validation performance.
    """

    def __init__(self, horizon: int = 24, n_splits: int = 3):
        self.horizon = horizon
        self.n_splits = n_splits
        self.results: list[ForecastResult] = []

    def _temporal_cv_split(self, n_samples: int):
        """Expanding window cross-validation (respects time order)."""
        min_train = max(n_samples // 3, self.horizon * 2)
        test_size = self.horizon
        splits = []

        for i in range(self.n_splits):
            train_end = min_train + i * (n_samples - min_train - test_size) // self.n_splits
            test_end = min(train_end + test_size, n_samples)
            splits.append((list(range(train_end)), list(range(train_end, test_end))))

        return splits

    def evaluate_statistical(self, train: np.ndarray, test: np.ndarray) -> list[ForecastResult]:
        """Evaluate statistical models."""
        results = []

        # Naive: last value
        pred_naive = np.full(len(test), train[-1])
        results.append(ForecastResult(
            "naive_last", pred_naive,
            self._compute_metrics(test, pred_naive), {},
        ))

        # Seasonal naive
        if len(train) >= self.horizon:
            pred_seasonal = train[-self.horizon:][:len(test)]
            results.append(ForecastResult(
                "seasonal_naive", pred_seasonal,
                self._compute_metrics(test, pred_seasonal), {},
            ))

        # Exponential smoothing
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model = ExponentialSmoothing(
                train, seasonal_periods=min(self.horizon, len(train) // 3),
                trend="add", seasonal="add",
            ).fit(optimized=True)
            pred_ets = model.forecast(len(test))
            results.append(ForecastResult(
                "ets", pred_ets,
                self._compute_metrics(test, pred_ets),
                {"trend": "add", "seasonal": "add"},
            ))
        except Exception:
            pass

        return results

    def evaluate_ml(self, train: np.ndarray, test: np.ndarray) -> list[ForecastResult]:
        """Evaluate ML models with lag features."""
        results = []
        lookback = min(28, len(train) // 3)

        # Create features
        X_train, y_train = self._create_supervised(train, lookback)
        X_test = train[-lookback:].reshape(1, -1)  # Last window for prediction

        # LightGBM
        try:
            import lightgbm as lgb
            for n_est in [100, 500]:
                for lr in [0.05, 0.1]:
                    model = lgb.LGBMRegressor(
                        n_estimators=n_est, learning_rate=lr,
                        num_leaves=31, verbose=-1,
                    )
                    model.fit(X_train, y_train)

                    # Multi-step: recursive prediction
                    pred = self._recursive_predict(model, train, lookback, len(test))
                    results.append(ForecastResult(
                        f"lgbm_n{n_est}_lr{lr}", pred,
                        self._compute_metrics(test, pred),
                        {"n_estimators": n_est, "lr": lr},
                    ))
        except ImportError:
            pass

        return results

    def _create_supervised(self, data, lookback):
        X, y = [], []
        for i in range(lookback, len(data)):
            X.append(data[i-lookback:i])
            y.append(data[i])
        return np.array(X), np.array(y)

    def _recursive_predict(self, model, history, lookback, n_steps):
        """Recursive multi-step prediction."""
        preds = []
        window = list(history[-lookback:])
        for _ in range(n_steps):
            x = np.array(window[-lookback:]).reshape(1, -1)
            pred = model.predict(x)[0]
            preds.append(pred)
            window.append(pred)
        return np.array(preds)

    def _compute_metrics(self, actual, predicted) -> dict:
        n = min(len(actual), len(predicted))
        actual, predicted = actual[:n], predicted[:n]
        mae = np.mean(np.abs(actual - predicted))
        mse = np.mean((actual - predicted) ** 2)
        mape = np.mean(np.abs((actual - predicted) / np.clip(np.abs(actual), 1e-8, None))) * 100
        return {"mae": mae, "rmse": np.sqrt(mse), "mape": mape}

    def fit(self, data: np.ndarray) -> dict:
        """Run full AutoML pipeline."""
        splits = self._temporal_cv_split(len(data))
        all_results = {}

        for train_idx, test_idx in splits:
            train = data[train_idx]
            test = data[test_idx]

            for result in self.evaluate_statistical(train, test) + self.evaluate_ml(train, test):
                if result.model_name not in all_results:
                    all_results[result.model_name] = []
                all_results[result.model_name].append(result.metrics)

        # Average metrics across folds
        summary = {}
        for name, fold_metrics in all_results.items():
            summary[name] = {
                metric: np.mean([fm[metric] for fm in fold_metrics])
                for metric in fold_metrics[0].keys()
            }

        # Rank by MAE
        ranked = sorted(summary.items(), key=lambda x: x[1]["mae"])
        return {"ranking": ranked, "best_model": ranked[0][0]}
```

Key patterns:
1. **Expanding window CV** — train on growing history, test on next window; respects time order
2. **Model zoo** — evaluate statistical (ETS, ARIMA) and ML (LightGBM, XGBoost) together
3. **Recursive prediction** — for multi-step: predict one step, append, predict next
4. **Metric-based selection** — rank models by MAE/RMSE across CV folds; pick best
5. **Baselines first** — always include naive (last value) and seasonal naive as benchmarks'''
    ),
]
"""
