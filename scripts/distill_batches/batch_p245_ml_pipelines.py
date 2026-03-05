"""ML pipeline orchestration — training pipelines, data validation, model registry."""

PAIRS = [
    (
        "ai/training-pipeline",
        "Show ML training pipeline patterns: data loading, preprocessing, training loop, evaluation, and checkpointing with PyTorch Lightning.",
        '''Production ML training pipeline:

```python
import torch
import pytorch_lightning as pl
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping, LearningRateMonitor
from pytorch_lightning.loggers import WandbLogger
from torch.utils.data import DataLoader, Dataset
from torchmetrics import Accuracy, F1Score
import torch.nn.functional as F


class TextClassifier(pl.LightningModule):
    """Production training module with best practices."""

    def __init__(self, vocab_size: int, num_classes: int, embed_dim: int = 256,
                 hidden_dim: int = 512, lr: float = 1e-3, weight_decay: float = 1e-4):
        super().__init__()
        self.save_hyperparameters()

        self.embedding = torch.nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.encoder = torch.nn.TransformerEncoder(
            torch.nn.TransformerEncoderLayer(
                d_model=embed_dim, nhead=8, dim_feedforward=hidden_dim,
                dropout=0.1, batch_first=True,
            ),
            num_layers=4,
        )
        self.classifier = torch.nn.Sequential(
            torch.nn.Linear(embed_dim, hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.3),
            torch.nn.Linear(hidden_dim, num_classes),
        )

        # Metrics (torchmetrics handles distributed automatically)
        self.train_acc = Accuracy(task="multiclass", num_classes=num_classes)
        self.val_acc = Accuracy(task="multiclass", num_classes=num_classes)
        self.val_f1 = F1Score(task="multiclass", num_classes=num_classes, average="macro")

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        x = self.embedding(input_ids)
        # Mask padding tokens in attention
        src_key_padding_mask = ~attention_mask.bool()
        x = self.encoder(x, src_key_padding_mask=src_key_padding_mask)
        # Pool: mean of non-padding tokens
        mask = attention_mask.unsqueeze(-1).float()
        x = (x * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        return self.classifier(x)

    def training_step(self, batch, batch_idx):
        logits = self(batch["input_ids"], batch["attention_mask"])
        loss = F.cross_entropy(logits, batch["labels"])
        preds = logits.argmax(dim=-1)
        self.train_acc(preds, batch["labels"])
        self.log("train/loss", loss, prog_bar=True)
        self.log("train/acc", self.train_acc, on_step=False, on_epoch=True)
        return loss

    def validation_step(self, batch, batch_idx):
        logits = self(batch["input_ids"], batch["attention_mask"])
        loss = F.cross_entropy(logits, batch["labels"])
        preds = logits.argmax(dim=-1)
        self.val_acc(preds, batch["labels"])
        self.val_f1(preds, batch["labels"])
        self.log("val/loss", loss, prog_bar=True, sync_dist=True)
        self.log("val/acc", self.val_acc, on_step=False, on_epoch=True)
        self.log("val/f1", self.val_f1, on_step=False, on_epoch=True)

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=10, T_mult=2,
        )
        return {"optimizer": optimizer, "lr_scheduler": scheduler}


def train_pipeline(
    train_dataset: Dataset,
    val_dataset: Dataset,
    config: dict,
    project_name: str = "text-classifier",
) -> str:
    """Full training pipeline with monitoring and checkpointing."""
    # Data loaders
    train_loader = DataLoader(
        train_dataset, batch_size=config["batch_size"],
        shuffle=True, num_workers=4, pin_memory=True,
        persistent_workers=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=config["batch_size"] * 2,
        num_workers=4, pin_memory=True,
    )

    # Model
    model = TextClassifier(
        vocab_size=config["vocab_size"],
        num_classes=config["num_classes"],
        lr=config["lr"],
    )

    # Callbacks
    callbacks = [
        ModelCheckpoint(
            monitor="val/f1",
            mode="max",
            save_top_k=3,
            filename="{epoch}-{val/f1:.3f}",
        ),
        EarlyStopping(
            monitor="val/loss",
            patience=5,
            mode="min",
        ),
        LearningRateMonitor(logging_interval="step"),
    ]

    # Logger
    logger = WandbLogger(project=project_name, log_model=True)

    # Trainer
    trainer = pl.Trainer(
        max_epochs=config["epochs"],
        accelerator="gpu",
        devices=1,
        precision="16-mixed",          # Automatic mixed precision
        gradient_clip_val=1.0,
        accumulate_grad_batches=config.get("grad_accumulation", 1),
        callbacks=callbacks,
        logger=logger,
        deterministic=True,
        val_check_interval=0.5,         # Validate twice per epoch
    )

    trainer.fit(model, train_loader, val_loader)

    # Return best checkpoint path
    return trainer.checkpoint_callback.best_model_path
```

Key patterns:
1. **`save_hyperparameters()`** — auto-saves all init args; enables reproducible model loading
2. **torchmetrics** — handles metric computation across distributed GPUs automatically
3. **Mixed precision** — `precision="16-mixed"` halves memory and doubles throughput
4. **Model checkpoint** — save top-3 models by validation F1; resume from best after training
5. **Early stopping** — stop training when validation loss hasn't improved for 5 epochs'''
    ),
    (
        "ai/data-validation-ml",
        "Show ML data validation patterns: schema validation, distribution drift detection, and data quality checks before training.",
        '''ML data validation before training:

```python
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Any
from scipy import stats


@dataclass
class ValidationResult:
    passed: bool
    check_name: str
    details: str
    severity: str = "error"  # error, warning, info


class DataValidator:
    """Validate training data quality before model training.

    Catches problems early: missing values, label imbalance,
    distribution drift, schema violations.
    """

    def __init__(self):
        self.checks: list[callable] = []
        self.results: list[ValidationResult] = []

    def validate(self, df: pd.DataFrame, reference_df: pd.DataFrame | None = None) -> list[ValidationResult]:
        """Run all validation checks."""
        self.results = []
        self.results.extend(self.check_schema(df))
        self.results.extend(self.check_missing_values(df))
        self.results.extend(self.check_label_distribution(df))
        self.results.extend(self.check_duplicates(df))
        self.results.extend(self.check_outliers(df))

        if reference_df is not None:
            self.results.extend(self.check_drift(df, reference_df))

        return self.results

    def check_schema(self, df: pd.DataFrame) -> list[ValidationResult]:
        """Validate column types and required fields."""
        results = []

        required_columns = {"text", "label"}
        missing = required_columns - set(df.columns)
        if missing:
            results.append(ValidationResult(
                passed=False,
                check_name="schema_required_columns",
                details=f"Missing required columns: {missing}",
            ))

        # Check for unexpected types
        if "label" in df.columns:
            if df["label"].dtype == "object":
                unique_labels = df["label"].nunique()
                if unique_labels > 1000:
                    results.append(ValidationResult(
                        passed=False,
                        check_name="schema_label_cardinality",
                        details=f"Too many unique labels: {unique_labels}. Likely a data error.",
                    ))

        if not results:
            results.append(ValidationResult(True, "schema", "Schema valid"))

        return results

    def check_missing_values(self, df: pd.DataFrame, threshold: float = 0.05) -> list[ValidationResult]:
        """Check for missing or null values."""
        results = []
        for col in df.columns:
            null_ratio = df[col].isnull().mean()
            if null_ratio > threshold:
                results.append(ValidationResult(
                    passed=False,
                    check_name=f"missing_values_{col}",
                    details=f"Column '{col}' has {null_ratio:.1%} missing values (threshold: {threshold:.1%})",
                ))
            elif null_ratio > 0:
                results.append(ValidationResult(
                    passed=True,
                    check_name=f"missing_values_{col}",
                    details=f"Column '{col}' has {null_ratio:.1%} missing values",
                    severity="warning",
                ))
        return results

    def check_label_distribution(self, df: pd.DataFrame, max_imbalance_ratio: float = 10.0) -> list[ValidationResult]:
        """Check for severe label imbalance."""
        if "label" not in df.columns:
            return []

        label_counts = df["label"].value_counts()
        imbalance_ratio = label_counts.max() / label_counts.min()

        if imbalance_ratio > max_imbalance_ratio:
            return [ValidationResult(
                passed=False,
                check_name="label_imbalance",
                details=f"Label imbalance ratio: {imbalance_ratio:.1f}x (max class: {label_counts.idxmax()}, min class: {label_counts.idxmin()})",
                severity="warning",
            )]
        return [ValidationResult(True, "label_imbalance", f"Imbalance ratio: {imbalance_ratio:.1f}x")]

    def check_duplicates(self, df: pd.DataFrame, threshold: float = 0.01) -> list[ValidationResult]:
        """Check for duplicate rows."""
        if "text" not in df.columns:
            return []

        dup_ratio = df["text"].duplicated().mean()
        if dup_ratio > threshold:
            return [ValidationResult(
                passed=False,
                check_name="duplicates",
                details=f"{dup_ratio:.1%} duplicate texts ({int(dup_ratio * len(df))} rows)",
            )]
        return [ValidationResult(True, "duplicates", f"{dup_ratio:.2%} duplicates")]

    def check_outliers(self, df: pd.DataFrame) -> list[ValidationResult]:
        """Check for statistical outliers in numeric columns."""
        results = []
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            outlier_mask = (df[col] < q1 - 3 * iqr) | (df[col] > q3 + 3 * iqr)
            outlier_ratio = outlier_mask.mean()

            if outlier_ratio > 0.01:
                results.append(ValidationResult(
                    passed=True,
                    check_name=f"outliers_{col}",
                    details=f"Column '{col}' has {outlier_ratio:.1%} outliers (3*IQR)",
                    severity="warning",
                ))
        return results

    def check_drift(self, current: pd.DataFrame, reference: pd.DataFrame,
                     threshold: float = 0.05) -> list[ValidationResult]:
        """Detect distribution drift between current and reference data."""
        results = []
        numeric_cols = set(current.select_dtypes(include=[np.number]).columns) & set(reference.columns)

        for col in numeric_cols:
            # Kolmogorov-Smirnov test
            statistic, p_value = stats.ks_2samp(
                current[col].dropna(), reference[col].dropna()
            )

            if p_value < threshold:
                results.append(ValidationResult(
                    passed=False,
                    check_name=f"drift_{col}",
                    details=f"Distribution drift detected in '{col}' (KS={statistic:.3f}, p={p_value:.4f})",
                    severity="warning",
                ))

        # Label distribution drift
        if "label" in current.columns and "label" in reference.columns:
            current_dist = current["label"].value_counts(normalize=True).sort_index()
            ref_dist = reference["label"].value_counts(normalize=True).sort_index()

            # Align distributions
            all_labels = sorted(set(current_dist.index) | set(ref_dist.index))
            curr = [current_dist.get(l, 0) for l in all_labels]
            ref = [ref_dist.get(l, 0) for l in all_labels]

            # Jensen-Shannon divergence
            from scipy.spatial.distance import jensenshannon
            jsd = jensenshannon(curr, ref)

            if jsd > 0.1:
                results.append(ValidationResult(
                    passed=False,
                    check_name="drift_labels",
                    details=f"Label distribution drift: JSD={jsd:.3f}",
                ))

        return results


def validate_before_training(train_path: str, reference_path: str | None = None) -> bool:
    """Gate: validate data before starting training."""
    df = pd.read_parquet(train_path)
    ref = pd.read_parquet(reference_path) if reference_path else None

    validator = DataValidator()
    results = validator.validate(df, ref)

    errors = [r for r in results if not r.passed and r.severity == "error"]
    warnings = [r for r in results if not r.passed and r.severity == "warning"]

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.check_name}: {r.details}")

    if errors:
        print(f"\\nBlocked: {len(errors)} errors found. Fix before training.")
        return False

    if warnings:
        print(f"\\n{len(warnings)} warnings. Proceeding with caution.")

    return True
```

Key patterns:
1. **Schema validation** — verify required columns exist, types are correct, cardinality is reasonable
2. **Drift detection** — KS test for numeric features, JSD for label distribution; catch training-serving skew
3. **Label imbalance** — flag when majority/minority ratio exceeds 10x; may need oversampling or class weights
4. **Gate pattern** — validate data BEFORE training starts; fail fast instead of wasting GPU hours
5. **Reference comparison** — compare new training data against a known-good reference set for drift'''
    ),
]
"""
