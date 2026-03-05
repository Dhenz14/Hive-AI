"""Feature toggles and progressive delivery — flags, rollouts, A/B testing."""

PAIRS = [
    (
        "architecture/feature-flags",
        "Show feature flag system: boolean flags, percentage rollouts, user targeting, and flag evaluation engine.",
        '''Feature flag evaluation engine:

```python
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class FlagType(Enum):
    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    RULE_BASED = "rule_based"


@dataclass
class FlagRule:
    attribute: str      # e.g., "country", "plan", "user_id"
    operator: str       # "eq", "in", "gt", "lt", "contains"
    value: Any
    variation: Any      # What to return if rule matches


@dataclass
class FeatureFlag:
    key: str
    flag_type: FlagType
    enabled: bool = True
    default_value: Any = False
    percentage: float = 0.0      # For percentage rollout
    user_list: list[str] = field(default_factory=list)
    rules: list[FlagRule] = field(default_factory=list)
    variations: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalContext:
    user_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


class FlagEngine:
    """Evaluate feature flags with targeting rules."""

    def __init__(self):
        self.flags: dict[str, FeatureFlag] = {}

    def register(self, flag: FeatureFlag):
        self.flags[flag.key] = flag

    def evaluate(self, flag_key: str, context: EvalContext) -> Any:
        flag = self.flags.get(flag_key)
        if not flag or not flag.enabled:
            return flag.default_value if flag else False

        # Check user list first (overrides)
        if context.user_id in flag.user_list:
            return True

        # Evaluate rules in order (first match wins)
        for rule in flag.rules:
            if self._evaluate_rule(rule, context):
                return rule.variation

        # Percentage rollout (deterministic by user)
        if flag.flag_type == FlagType.PERCENTAGE:
            return self._in_percentage(flag.key, context.user_id, flag.percentage)

        return flag.default_value

    def _in_percentage(self, flag_key: str, user_id: str, pct: float) -> bool:
        """Deterministic percentage check using hash."""
        h = hashlib.md5(f"{flag_key}:{user_id}".encode()).hexdigest()
        bucket = int(h[:8], 16) % 100
        return bucket < pct

    def _evaluate_rule(self, rule: FlagRule, ctx: EvalContext) -> bool:
        value = ctx.attributes.get(rule.attribute)
        if value is None:
            return False
        ops = {
            "eq": lambda a, b: a == b,
            "neq": lambda a, b: a != b,
            "in": lambda a, b: a in b,
            "gt": lambda a, b: a > b,
            "lt": lambda a, b: a < b,
            "contains": lambda a, b: b in str(a),
        }
        op = ops.get(rule.operator)
        return op(value, rule.value) if op else False


# Usage
engine = FlagEngine()
engine.register(FeatureFlag(
    key="new_checkout",
    flag_type=FlagType.RULE_BASED,
    rules=[
        FlagRule("plan", "eq", "enterprise", variation=True),
        FlagRule("country", "in", ["US", "CA"], variation=True),
    ],
    default_value=False,
))
engine.register(FeatureFlag(
    key="dark_mode",
    flag_type=FlagType.PERCENTAGE,
    percentage=25.0,  # 25% of users
))

ctx = EvalContext(user_id="user-123", attributes={"plan": "enterprise", "country": "US"})
assert engine.evaluate("new_checkout", ctx) is True
```

Key patterns:
1. **Deterministic hashing** — same user always gets same flag value; consistent experience
2. **Rule evaluation** — first matching rule wins; attribute-based targeting
3. **User overrides** — whitelist specific users for testing; bypass all rules
4. **Percentage rollout** — gradual rollout (5% → 25% → 50% → 100%); hash-based bucketing
5. **Kill switch** — `enabled=False` instantly disables; emergency rollback'''
    ),
    (
        "architecture/ab-testing",
        "Show A/B testing: experiment assignment, statistical significance, and metrics collection.",
        '''A/B testing framework:

```python
import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class Experiment:
    id: str
    name: str
    variants: list[str]          # e.g., ["control", "variant_a", "variant_b"]
    weights: list[float] = None  # Traffic split (default: equal)
    active: bool = True
    start_time: float = 0
    end_time: float = 0


@dataclass
class ExperimentResult:
    variant: str
    conversions: int
    total: int
    rate: float
    ci_lower: float
    ci_upper: float


class ABTestEngine:
    """A/B test assignment and analysis."""

    def __init__(self):
        self.experiments: dict[str, Experiment] = {}
        self.assignments: dict[str, dict[str, str]] = {}  # user -> {exp -> variant}
        self.metrics: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    def create_experiment(self, experiment: Experiment):
        if experiment.weights is None:
            n = len(experiment.variants)
            experiment.weights = [1.0 / n] * n
        self.experiments[experiment.id] = experiment

    def assign(self, user_id: str, experiment_id: str) -> str:
        """Deterministically assign user to variant."""
        exp = self.experiments.get(experiment_id)
        if not exp or not exp.active:
            return exp.variants[0] if exp else "control"

        # Check for existing assignment
        if user_id in self.assignments:
            if experiment_id in self.assignments[user_id]:
                return self.assignments[user_id][experiment_id]

        # Hash-based assignment
        h = hashlib.sha256(f"{experiment_id}:{user_id}".encode()).hexdigest()
        bucket = int(h[:8], 16) % 10000 / 10000.0

        cumulative = 0.0
        variant = exp.variants[0]
        for v, w in zip(exp.variants, exp.weights):
            cumulative += w
            if bucket < cumulative:
                variant = v
                break

        self.assignments.setdefault(user_id, {})[experiment_id] = variant
        return variant

    def record_metric(self, experiment_id: str, user_id: str,
                       metric: str, value: float):
        variant = self.assignments.get(user_id, {}).get(experiment_id)
        if variant:
            self.metrics[experiment_id][f"{variant}:{metric}"].append(value)

    def analyze(self, experiment_id: str, metric: str = "conversion") -> dict:
        """Statistical analysis of experiment results."""
        exp = self.experiments[experiment_id]
        results = {}

        for variant in exp.variants:
            key = f"{variant}:{metric}"
            values = self.metrics[experiment_id].get(key, [])
            n = len(values)
            if n == 0:
                continue
            conversions = sum(1 for v in values if v > 0)
            rate = conversions / n
            # Wilson confidence interval
            ci_lower, ci_upper = self._wilson_ci(conversions, n)
            results[variant] = ExperimentResult(
                variant=variant, conversions=conversions,
                total=n, rate=rate,
                ci_lower=ci_lower, ci_upper=ci_upper,
            )

        return {
            "experiment": experiment_id,
            "results": results,
            "significant": self._is_significant(results, exp.variants),
        }

    def _wilson_ci(self, successes: int, total: int,
                    z: float = 1.96) -> tuple[float, float]:
        """Wilson score interval (better than normal approx for small n)."""
        if total == 0:
            return 0.0, 0.0
        p = successes / total
        denom = 1 + z**2 / total
        center = (p + z**2 / (2 * total)) / denom
        spread = z * math.sqrt((p * (1-p) + z**2 / (4*total)) / total) / denom
        return max(0, center - spread), min(1, center + spread)

    def _is_significant(self, results: dict, variants: list) -> bool:
        if len(results) < 2:
            return False
        control = results.get(variants[0])
        for v in variants[1:]:
            treatment = results.get(v)
            if control and treatment:
                if treatment.ci_lower > control.ci_upper:
                    return True
                if control.ci_lower > treatment.ci_upper:
                    return True
        return False
```

Key patterns:
1. **Deterministic assignment** — hash user+experiment for consistent variant; no coin flips
2. **Weighted splits** — unequal traffic allocation; 90% control / 10% variant for risky changes
3. **Wilson interval** — better confidence interval than normal approximation for small samples
4. **Significance test** — non-overlapping confidence intervals indicate real difference
5. **Sticky assignments** — user always sees same variant; prevents flickering'''
    ),
]
"""
