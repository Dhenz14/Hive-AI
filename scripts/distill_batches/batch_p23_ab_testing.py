"""A/B testing and experimentation — statistical foundations, Bayesian methods, multi-armed bandits."""

PAIRS = [
    (
        "statistics/ab-testing",
        "Explain A/B testing from scratch: sample size calculation, hypothesis testing, multiple comparison correction, and common pitfalls.",
        '''A/B testing with statistical rigor:

```python
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional

@dataclass
class ABTestResult:
    control_rate: float
    treatment_rate: float
    relative_lift: float
    p_value: float
    confidence_interval: tuple[float, float]
    is_significant: bool
    power: float
    sample_size_each: int

# --- Sample Size Calculator ---

def required_sample_size(baseline_rate: float,
                         minimum_detectable_effect: float,
                         alpha: float = 0.05,
                         power: float = 0.8) -> int:
    """Calculate required sample size per group.

    Args:
        baseline_rate: Current conversion rate (e.g., 0.05 for 5%)
        minimum_detectable_effect: Relative change to detect (e.g., 0.1 for 10% lift)
        alpha: Significance level (Type I error rate)
        power: Statistical power (1 - Type II error rate)
    """
    p1 = baseline_rate
    p2 = baseline_rate * (1 + minimum_detectable_effect)
    p_avg = (p1 + p2) / 2

    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)

    n = ((z_alpha * np.sqrt(2 * p_avg * (1 - p_avg)) +
          z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
         / (p2 - p1) ** 2)

    return int(np.ceil(n))

# Example:
# 5% baseline conversion, detect 10% relative lift
n = required_sample_size(0.05, 0.10)
# n ≈ 29,000 per group

# --- Frequentist A/B Test ---

def analyze_ab_test(control_conversions: int, control_total: int,
                    treatment_conversions: int, treatment_total: int,
                    alpha: float = 0.05) -> ABTestResult:
    """Two-proportion z-test for A/B experiment."""
    p_c = control_conversions / control_total
    p_t = treatment_conversions / treatment_total

    # Pooled proportion
    p_pool = (control_conversions + treatment_conversions) / (control_total + treatment_total)

    # Standard error
    se = np.sqrt(p_pool * (1 - p_pool) * (1/control_total + 1/treatment_total))

    # Z-statistic
    z = (p_t - p_c) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # Confidence interval for difference
    se_diff = np.sqrt(p_c * (1 - p_c) / control_total +
                      p_t * (1 - p_t) / treatment_total)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci = (p_t - p_c - z_crit * se_diff,
          p_t - p_c + z_crit * se_diff)

    # Relative lift
    relative_lift = (p_t - p_c) / p_c if p_c > 0 else 0

    # Post-hoc power
    effect_size = abs(p_t - p_c) / np.sqrt(p_pool * (1 - p_pool))
    power_actual = stats.norm.cdf(
        effect_size * np.sqrt(min(control_total, treatment_total)) - z_crit
    )

    return ABTestResult(
        control_rate=p_c,
        treatment_rate=p_t,
        relative_lift=relative_lift,
        p_value=p_value,
        confidence_interval=ci,
        is_significant=p_value < alpha,
        power=power_actual,
        sample_size_each=max(control_total, treatment_total),
    )

# --- Multiple Comparison Correction ---

def bonferroni_correction(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Conservative: divide alpha by number of tests."""
    adjusted_alpha = alpha / len(p_values)
    return [p < adjusted_alpha for p in p_values]

def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """FDR control — less conservative, better for many comparisons."""
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]

    # BH critical values
    thresholds = [(i + 1) / n * alpha for i in range(n)]

    # Find largest k where p(k) <= threshold(k)
    significant = [False] * n
    max_significant = -1
    for i in range(n):
        if sorted_p[i] <= thresholds[i]:
            max_significant = i

    # All tests up to max_significant are significant
    for i in range(max_significant + 1):
        significant[sorted_indices[i]] = True

    return significant

# --- Bayesian A/B Test ---

def bayesian_ab_test(control_conversions: int, control_total: int,
                     treatment_conversions: int, treatment_total: int,
                     n_samples: int = 100_000) -> dict:
    """Bayesian approach with Beta posterior."""
    # Beta posterior (conjugate prior for Bernoulli)
    # Prior: Beta(1, 1) = Uniform
    alpha_c = 1 + control_conversions
    beta_c = 1 + control_total - control_conversions
    alpha_t = 1 + treatment_conversions
    beta_t = 1 + treatment_total - treatment_conversions

    # Sample from posteriors
    samples_c = np.random.beta(alpha_c, beta_c, n_samples)
    samples_t = np.random.beta(alpha_t, beta_t, n_samples)

    # P(treatment > control)
    prob_t_better = (samples_t > samples_c).mean()

    # Expected lift distribution
    lift_samples = (samples_t - samples_c) / samples_c
    expected_lift = lift_samples.mean()
    lift_ci = (np.percentile(lift_samples, 2.5),
               np.percentile(lift_samples, 97.5))

    # Expected loss (risk of choosing treatment if it's worse)
    loss_t = np.maximum(samples_c - samples_t, 0).mean()
    loss_c = np.maximum(samples_t - samples_c, 0).mean()

    return {
        "prob_treatment_better": prob_t_better,
        "expected_lift": expected_lift,
        "lift_95_ci": lift_ci,
        "expected_loss_choosing_treatment": loss_t,
        "expected_loss_choosing_control": loss_c,
        "recommendation": "treatment" if prob_t_better > 0.95 else
                          "control" if prob_t_better < 0.05 else "inconclusive",
    }

# --- Sequential Testing (avoid peeking problem) ---

def sequential_test(daily_results: list[tuple[int, int, int, int]],
                    alpha: float = 0.05) -> dict:
    """Group sequential test with O\'Brien-Fleming spending function."""
    n_looks = len(daily_results)
    z_boundaries = []

    # O'Brien-Fleming boundaries (more conservative early, less late)
    for k in range(1, n_looks + 1):
        info_fraction = k / n_looks
        z_boundary = stats.norm.ppf(1 - alpha / 2) / np.sqrt(info_fraction)
        z_boundaries.append(z_boundary)

    for i, (c_conv, c_total, t_conv, t_total) in enumerate(daily_results):
        result = analyze_ab_test(c_conv, c_total, t_conv, t_total)
        z_stat = stats.norm.ppf(1 - result.p_value / 2)

        if z_stat > z_boundaries[i]:
            return {
                "stopped_at_look": i + 1,
                "significant": True,
                "result": result,
            }

    return {"stopped_at_look": n_looks, "significant": False}
```

Common pitfalls:
1. **Peeking** — checking results daily inflates false positive rate (use sequential testing)
2. **Under-powered tests** — too small sample → miss real effects
3. **Multiple comparisons** — testing 20 metrics guarantees ~1 false positive at α=0.05
4. **SRM (sample ratio mismatch)** — unequal group sizes indicate randomization bug
5. **Novelty/primacy effects** — short tests capture temporary behavior changes'''
    ),
    (
        "statistics/bayesian-methods",
        "Show practical Bayesian inference in Python: prior selection, MCMC sampling, and posterior analysis for real-world problems.",
        '''Practical Bayesian inference with PyMC:

```python
import numpy as np
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt

# --- Example 1: Bayesian Linear Regression ---

def bayesian_regression(X: np.ndarray, y: np.ndarray):
    """Bayesian linear regression with uncertainty quantification."""

    with pm.Model() as model:
        # Priors
        intercept = pm.Normal("intercept", mu=0, sigma=10)
        slopes = pm.Normal("slopes", mu=0, sigma=5, shape=X.shape[1])
        sigma = pm.HalfNormal("sigma", sigma=5)

        # Linear model
        mu = intercept + pm.math.dot(X, slopes)

        # Likelihood
        y_obs = pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)

        # Sample
        trace = pm.sample(2000, tune=1000, chains=4, random_seed=42)

    # Analyze results
    summary = az.summary(trace, hdi_prob=0.95)
    print(summary)

    # Posterior predictive check
    with model:
        ppc = pm.sample_posterior_predictive(trace)

    return trace, ppc

# --- Example 2: Hierarchical Model (multi-level) ---

def hierarchical_conversion_rates(groups: list[str],
                                  conversions: list[int],
                                  totals: list[int]):
    """Estimate conversion rates with partial pooling."""

    with pm.Model() as model:
        # Hyperpriors (population level)
        mu = pm.Beta("mu", alpha=2, beta=8)  # Overall mean
        kappa = pm.HalfNormal("kappa", sigma=50)  # Concentration

        # Group-level rates (partial pooling toward mu)
        alpha = mu * kappa
        beta = (1 - mu) * kappa
        theta = pm.Beta("theta", alpha=alpha, beta=beta, shape=len(groups))

        # Likelihood
        obs = pm.Binomial("obs", n=totals, p=theta, observed=conversions)

        trace = pm.sample(3000, tune=1500, chains=4)

    # Results: each group's rate is "shrunk" toward the population mean
    # Small groups shrink more, large groups shrink less
    summary = az.summary(trace, var_names=["theta"])
    for i, group in enumerate(groups):
        row = summary.iloc[i]
        print(f"{group}: {row['mean']:.4f} [{row['hdi_3%']:.4f}, {row['hdi_97%']:.4f}]")

    return trace

# --- Example 3: Change Point Detection ---

def detect_change_point(data: np.ndarray):
    """Find when a time series distribution changed."""

    n = len(data)

    with pm.Model() as model:
        # Change point (discrete uniform)
        tau = pm.DiscreteUniform("tau", lower=0, upper=n - 1)

        # Parameters before and after change
        mu1 = pm.Normal("mu1", mu=data.mean(), sigma=data.std())
        mu2 = pm.Normal("mu2", mu=data.mean(), sigma=data.std())
        sigma = pm.HalfNormal("sigma", sigma=data.std())

        # Switch mean at change point
        idx = np.arange(n)
        mu = pm.math.switch(tau >= idx, mu1, mu2)

        obs = pm.Normal("obs", mu=mu, sigma=sigma, observed=data)

        trace = pm.sample(5000, tune=2000, chains=4)

    # Most likely change point
    tau_samples = trace.posterior["tau"].values.flatten()
    change_point = int(np.median(tau_samples))
    print(f"Change point at index {change_point}")
    print(f"Before: mean={trace.posterior['mu1'].mean():.2f}")
    print(f"After: mean={trace.posterior['mu2'].mean():.2f}")

    return trace, change_point

# --- Prior Selection Guide ---

PRIOR_GUIDE = """
Common prior choices:

| Parameter Type | Prior | When to Use |
|---------------|-------|-------------|
| Location (mean) | Normal(0, σ) | Centered, weakly informative |
| Positive scale | HalfNormal(σ) | Standard deviations, rates |
| Probability | Beta(α, β) | Proportions, conversion rates |
| Count | Poisson(λ) | Event counts |
| Categorical | Dirichlet(α) | Probability vectors |
| Correlation | LKJCholesky(η) | Correlation matrices |

Weakly informative strategy:
1. Set priors that allow reasonable values
2. Put low probability on extreme values
3. Use prior predictive checks to verify
"""

# --- Prior predictive check ---

def check_priors():
    """Simulate from priors to verify they're reasonable."""
    with pm.Model() as model:
        mu = pm.Normal("mu", mu=0, sigma=10)
        sigma = pm.HalfNormal("sigma", sigma=5)
        y = pm.Normal("y", mu=mu, sigma=sigma)

        prior_samples = pm.sample_prior_predictive(1000)

    # Check if prior predictions are in a reasonable range
    y_prior = prior_samples.prior["y"].values.flatten()
    print(f"Prior predictive range: [{y_prior.min():.1f}, {y_prior.max():.1f}]")
    print(f"95% of predictions in [{np.percentile(y_prior, 2.5):.1f}, "
          f"{np.percentile(y_prior, 97.5):.1f}]")
```

Key Bayesian advantages:
- **Uncertainty quantification** — get distributions, not point estimates
- **Small samples** — priors regularize with limited data
- **Hierarchical models** — share strength across groups
- **Sequential updating** — update beliefs as data arrives
- **Decision theory** — expected loss framework for decision-making'''
    ),
]
