"""AI ethics and fairness — bias detection, fairness metrics, responsible AI."""

PAIRS = [
    (
        "ai/bias-detection",
        "Show ML bias detection and mitigation: group fairness metrics, disparate impact analysis, and debiasing techniques.",
        '''ML fairness and bias detection:

```python
import numpy as np
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class FairnessReport:
    metric: str
    group_a: str
    group_b: str
    value_a: float
    value_b: float
    ratio: float
    passes_threshold: bool


class FairnessAuditor:
    """Audit ML model predictions for group fairness."""

    def __init__(self, predictions: np.ndarray, labels: np.ndarray,
                 sensitive_attr: np.ndarray):
        self.preds = predictions
        self.labels = labels
        self.groups = sensitive_attr
        self.unique_groups = np.unique(sensitive_attr)

    def demographic_parity(self) -> dict:
        """Equal positive prediction rates across groups.

        P(Y_hat=1 | A=a) = P(Y_hat=1 | A=b)
        """
        rates = {}
        for group in self.unique_groups:
            mask = self.groups == group
            rates[group] = self.preds[mask].mean()
        return rates

    def equalized_odds(self) -> dict:
        """Equal TPR and FPR across groups.

        P(Y_hat=1 | Y=y, A=a) = P(Y_hat=1 | Y=y, A=b) for y in {0,1}
        """
        result = {}
        for group in self.unique_groups:
            mask = self.groups == group
            # True positive rate
            pos_mask = mask & (self.labels == 1)
            tpr = self.preds[pos_mask].mean() if pos_mask.sum() > 0 else 0
            # False positive rate
            neg_mask = mask & (self.labels == 0)
            fpr = self.preds[neg_mask].mean() if neg_mask.sum() > 0 else 0
            result[group] = {"tpr": tpr, "fpr": fpr}
        return result

    def disparate_impact_ratio(self, privileged: str, unprivileged: str) -> float:
        """Ratio of positive rates. Legal threshold: > 0.8 (80% rule)."""
        rates = self.demographic_parity()
        return rates[unprivileged] / max(rates[privileged], 1e-10)

    def calibration_by_group(self, n_bins: int = 10) -> dict:
        """Check if predicted probabilities are calibrated per group."""
        result = {}
        for group in self.unique_groups:
            mask = self.groups == group
            group_preds = self.preds[mask]
            group_labels = self.labels[mask]

            bins = np.linspace(0, 1, n_bins + 1)
            calibration = []
            for i in range(n_bins):
                bin_mask = (group_preds >= bins[i]) & (group_preds < bins[i+1])
                if bin_mask.sum() > 0:
                    pred_mean = group_preds[bin_mask].mean()
                    true_mean = group_labels[bin_mask].mean()
                    calibration.append({"pred": pred_mean, "true": true_mean,
                                         "count": int(bin_mask.sum())})
            result[group] = calibration
        return result

    def full_audit(self) -> list[FairnessReport]:
        """Run all fairness checks."""
        reports = []
        groups = list(self.unique_groups)

        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]

                # Demographic parity
                rates = self.demographic_parity()
                ratio = rates[b] / max(rates[a], 1e-10)
                reports.append(FairnessReport(
                    "demographic_parity", str(a), str(b),
                    rates[a], rates[b], ratio, 0.8 <= ratio <= 1.25
                ))

                # Equalized odds
                odds = self.equalized_odds()
                tpr_ratio = odds[b]["tpr"] / max(odds[a]["tpr"], 1e-10)
                reports.append(FairnessReport(
                    "equalized_odds_tpr", str(a), str(b),
                    odds[a]["tpr"], odds[b]["tpr"], tpr_ratio,
                    0.8 <= tpr_ratio <= 1.25
                ))

        return reports
```

Fairness metrics summary:

| Metric | Definition | When to use |
|--------|-----------|-------------|
| **Demographic parity** | Equal positive rate | Hiring, lending |
| **Equalized odds** | Equal TPR and FPR | Criminal justice |
| **Calibration** | Equal accuracy per group | Risk scoring |
| **Individual fairness** | Similar inputs → similar outputs | Any |
| **Disparate impact** | 80% rule (legal standard) | Compliance |

Key patterns:
1. **Group fairness** — compare metrics across protected groups; multiple definitions exist
2. **80% rule** — disparate impact ratio > 0.8; widely used legal threshold
3. **Equalized odds** — equal error rates across groups; prevents different error burdens
4. **Calibration** — predicted probabilities match true outcomes per group; trustworthy scores
5. **Tension between metrics** — impossible to satisfy all fairness criteria simultaneously (Chouldechova)'''
    ),
    (
        "ai/explainable-ai",
        "Show explainable AI patterns: feature attribution, counterfactual explanations, and model-agnostic interpretability.",
        '''Explainable AI — making models interpretable:

```python
import numpy as np
from dataclasses import dataclass
from typing import Callable


@dataclass
class Explanation:
    feature_names: list[str]
    feature_importances: np.ndarray
    prediction: float
    base_value: float
    method: str


class LIME:
    """Local Interpretable Model-agnostic Explanations.

    Explain any model by fitting a local linear model around the prediction.
    """

    def __init__(self, model_fn: Callable, n_features: int):
        self.model_fn = model_fn
        self.n_features = n_features

    def explain(self, instance: np.ndarray, n_samples: int = 1000,
                feature_names: list[str] = None) -> Explanation:
        """Generate local explanation for a single prediction."""
        # Generate perturbed samples near the instance
        perturbations = np.random.binomial(1, 0.5, (n_samples, self.n_features))
        samples = np.tile(instance, (n_samples, 1))

        # Zero out features according to perturbation mask
        background = np.zeros_like(instance)
        for i in range(n_samples):
            for j in range(self.n_features):
                if perturbations[i, j] == 0:
                    samples[i, j] = background[j]

        # Get model predictions for perturbed samples
        predictions = self.model_fn(samples)
        original_pred = self.model_fn(instance.reshape(1, -1))[0]

        # Weight by proximity to original instance
        distances = np.sqrt(((perturbations - 1) ** 2).sum(axis=1))
        weights = np.exp(-distances / (0.75 ** 2))

        # Fit weighted linear model
        from numpy.linalg import lstsq
        W = np.diag(weights)
        coeffs = lstsq(W @ perturbations, W @ predictions, rcond=None)[0]

        names = feature_names or [f"feature_{i}" for i in range(self.n_features)]
        return Explanation(
            feature_names=names,
            feature_importances=coeffs,
            prediction=float(original_pred),
            base_value=float(predictions.mean()),
            method="LIME"
        )


class CounterfactualExplainer:
    """Generate counterfactual explanations.

    'If feature X were Y instead of Z, the prediction would change.'
    """

    def __init__(self, model_fn: Callable, feature_ranges: dict):
        self.model_fn = model_fn
        self.feature_ranges = feature_ranges

    def find_counterfactual(self, instance: np.ndarray,
                             target_class: int,
                             max_changes: int = 3,
                             n_candidates: int = 1000) -> dict:
        """Find minimal change to flip prediction."""
        best = None
        best_distance = float("inf")

        for _ in range(n_candidates):
            candidate = instance.copy()
            # Randomly modify 1 to max_changes features
            n_mods = np.random.randint(1, max_changes + 1)
            features_to_change = np.random.choice(
                len(instance), n_mods, replace=False
            )

            for feat_idx in features_to_change:
                feat_name = list(self.feature_ranges.keys())[feat_idx]
                lo, hi = self.feature_ranges[feat_name]
                candidate[feat_idx] = np.random.uniform(lo, hi)

            pred = self.model_fn(candidate.reshape(1, -1))
            if np.argmax(pred) == target_class:
                distance = np.sum((candidate - instance) ** 2)
                if distance < best_distance:
                    best_distance = distance
                    best = {
                        "original": instance.copy(),
                        "counterfactual": candidate.copy(),
                        "changes": {
                            list(self.feature_ranges.keys())[i]:
                                (float(instance[i]), float(candidate[i]))
                            for i in features_to_change
                            if instance[i] != candidate[i]
                        },
                        "n_changes": len(features_to_change),
                    }

        return best
```

Key patterns:
1. **LIME** — local linear approximation; perturb input, fit simple model around prediction
2. **Proximity weighting** — samples closer to original instance count more in local model
3. **Counterfactuals** — find minimal changes to flip prediction; actionable explanations
4. **Model-agnostic** — works with any black-box model; only needs predict function
5. **Feature attribution** — rank features by contribution to prediction; debugging and trust'''
    ),
    (
        "ai/responsible-deployment",
        "Show responsible AI deployment: model cards, monitoring for drift, and automated safety checks in production.",
        '''Responsible AI deployment patterns:

```python
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class ModelCard:
    """Standardized model documentation (Mitchell et al., 2019)."""
    name: str
    version: str
    description: str
    intended_use: str
    out_of_scope_uses: list[str]
    training_data: str
    eval_results: dict[str, float]
    ethical_considerations: list[str]
    limitations: list[str]
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        lines = [f"# Model Card: {self.name} v{self.version}"]
        lines.append(f"\\n## Description\\n{self.description}")
        lines.append(f"\\n## Intended Use\\n{self.intended_use}")
        lines.append("\\n## Out of Scope\\n" + "\\n".join(f"- {u}" for u in self.out_of_scope_uses))
        lines.append("\\n## Evaluation Results")
        for metric, value in self.eval_results.items():
            lines.append(f"- {metric}: {value:.4f}")
        lines.append("\\n## Limitations\\n" + "\\n".join(f"- {l}" for l in self.limitations))
        lines.append("\\n## Ethical Considerations\\n" + "\\n".join(f"- {e}" for e in self.ethical_considerations))
        return "\\n".join(lines)


class DriftDetector:
    """Monitor production data for distribution shift."""

    def __init__(self, reference_stats: dict):
        self.reference = reference_stats
        self.alerts: list[dict] = []

    @staticmethod
    def compute_stats(data: np.ndarray, feature_names: list[str]) -> dict:
        return {
            name: {
                "mean": float(data[:, i].mean()),
                "std": float(data[:, i].std()),
                "min": float(data[:, i].min()),
                "max": float(data[:, i].max()),
                "p25": float(np.percentile(data[:, i], 25)),
                "p75": float(np.percentile(data[:, i], 75)),
            }
            for i, name in enumerate(feature_names)
        }

    def check_drift(self, current_data: np.ndarray,
                     feature_names: list[str],
                     threshold: float = 2.0) -> list[dict]:
        """Check for distribution drift using z-score method."""
        current = self.compute_stats(current_data, feature_names)
        alerts = []

        for feat in feature_names:
            if feat not in self.reference:
                continue
            ref = self.reference[feat]
            cur = current[feat]

            # Mean shift detection
            z_score = abs(cur["mean"] - ref["mean"]) / max(ref["std"], 1e-10)
            if z_score > threshold:
                alerts.append({
                    "feature": feat,
                    "type": "mean_shift",
                    "z_score": z_score,
                    "ref_mean": ref["mean"],
                    "cur_mean": cur["mean"],
                    "severity": "high" if z_score > 3 * threshold else "medium",
                })

            # Variance change detection
            var_ratio = cur["std"] / max(ref["std"], 1e-10)
            if var_ratio > 2.0 or var_ratio < 0.5:
                alerts.append({
                    "feature": feat,
                    "type": "variance_change",
                    "ratio": var_ratio,
                    "severity": "medium",
                })

        self.alerts.extend(alerts)
        return alerts


class SafetyChecker:
    """Pre-deployment safety validation."""

    def __init__(self, model_fn, test_suite: list[dict]):
        self.model_fn = model_fn
        self.test_suite = test_suite

    def run_checks(self) -> dict:
        results = {"passed": 0, "failed": 0, "failures": []}

        for test in self.test_suite:
            output = self.model_fn(test["input"])
            passed = test["check_fn"](output)
            if passed:
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["failures"].append({
                    "test": test["name"],
                    "input": test["input"][:100],
                    "output": str(output)[:100],
                })

        results["pass_rate"] = results["passed"] / len(self.test_suite)
        results["deploy_ok"] = results["pass_rate"] >= 0.95
        return results
```

Key patterns:
1. **Model cards** — standardized documentation; intended use, limitations, ethical considerations
2. **Drift detection** — monitor production data for distribution shift; z-score and variance checks
3. **Safety testing** — automated test suite before deployment; minimum pass rate gate
4. **Deploy gate** — 95%+ safety test pass rate required; prevents shipping unsafe models
5. **Alert severity** — classify drift as medium/high; route to appropriate response team'''
    ),
]
"""
