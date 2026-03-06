PAIRS = [
    ("thinking/algorithms", r'''Solve expected value problems algorithmically. Given a game where you roll a die and get the face value in dollars, but can choose to re-roll once (keeping the better result), what is the expected value? Generalize to n re-rolls.''', r'''<think>
Die re-roll problem. No re-rolls: E = (1+2+3+4+5+6)/6 = 3.5. With one re-roll, the question is: what threshold should I use for deciding whether to re-roll?

Let me try different thresholds. If I re-roll when the value is <= t and keep when > t:

t = 3 (re-roll 1,2,3; keep 4,5,6):
  P(keep) = 3/6, E(keep) = (4+5+6)/3 = 5
  P(reroll) = 3/6, E(reroll) = 3.5
  E = 0.5 * 5 + 0.5 * 3.5 = 4.25

t = 4 (re-roll 1,2,3,4; keep 5,6):
  P(keep) = 2/6, E(keep) = 5.5
  E = 1/3 * 5.5 + 2/3 * 3.5 = 4.167

Hmm, t=3 gives 4.25 which is better than t=4's 4.167. What about t=2?
  P(keep) = 4/6, E(keep) = 4.5
  E = 4/6 * 4.5 + 2/6 * 3.5 = 3 + 1.167 = 4.167

Same as t=4. So t=3 is optimal for one re-roll. Interesting.

Now for n re-rolls, I initially tried to generalize the threshold approach, but then realized there is a cleaner DP formulation. Let V(k) = expected value with k re-rolls remaining. V(0) = 3.5. The key insight: with k re-rolls, I should re-roll if and only if my current value is less than V(k-1), because V(k-1) is what I expect from using the remaining re-rolls.

So V(k) = (1/6) * sum(max(i, V(k-1)) for i = 1..6). Each face value is either kept (if >= V(k-1)) or we take the expected value of re-rolling (V(k-1)). Wait, actually it is max(i, V(k-1)) because if i >= V(k-1) we keep i, otherwise we would re-roll and get V(k-1) in expectation. That gives a clean recursive formula.
</think>

## Expected Value with Re-rolls

### Analysis and Implementation

```python
def expected_value_rerolls(sides, num_rerolls):
    """Compute optimal expected value for a die with given sides
    and num_rerolls re-rolls available.

    Strategy: re-roll if current value < E(remaining re-rolls).

    V(0) = average die value
    V(k) = (1/sides) * sum(max(i, V(k-1)) for i in 1..sides)
    """
    values = list(range(1, sides + 1))
    v = sum(values) / len(values)  # V(0)

    history = [v]
    for k in range(1, num_rerolls + 1):
        threshold = v  # re-roll if current < this
        v = sum(max(i, threshold) for i in values) / len(values)
        history.append(v)

    return v, history


def simulate_rerolls(sides, num_rerolls, trials=1000000):
    """Monte Carlo simulation to verify."""
    import random
    total = 0
    for _ in range(trials):
        # Compute optimal thresholds
        _, history = expected_value_rerolls(sides, num_rerolls)
        best = random.randint(1, sides)
        for k in range(num_rerolls, 0, -1):
            threshold = history[k - 1]
            if best < threshold:
                best = max(best, random.randint(1, sides))
        total += best
    return total / trials


# Standard 6-sided die
print("=== Expected Value with Re-rolls (d6) ===")
for n in range(6):
    ev, history = expected_value_rerolls(6, n)
    print(f"  {n} re-rolls: E = {ev:.4f}")

# Verify with simulation
print("\n=== Monte Carlo Verification ===")
import random
random.seed(42)
for n in [0, 1, 2, 3]:
    exact, _ = expected_value_rerolls(6, n)
    simulated = simulate_rerolls(6, n, trials=500000)
    print(f"  {n} re-rolls: exact={exact:.4f}, simulated={simulated:.4f}")

# Generalize: 20-sided die
print("\n=== d20 with re-rolls ===")
for n in range(6):
    ev, _ = expected_value_rerolls(20, n)
    print(f"  {n} re-rolls: E = {ev:.4f}")

# Threshold analysis for 1 re-roll
print("\n=== Optimal threshold for d6, 1 re-roll ===")
base_ev = 3.5
for t in range(1, 7):
    # Keep if roll >= t, else re-roll
    keep_vals = [i for i in range(1, 7) if i >= t]
    reroll_vals = [i for i in range(1, 7) if i < t]
    ev = (len(keep_vals) * (sum(keep_vals)/max(len(keep_vals),1))
          + len(reroll_vals) * base_ev) / 6
    print(f"  threshold={t}: E = {ev:.4f}")
```

### Key Formula
```
V(k) = (1/n) * sum_{i=1}^{n} max(i, V(k-1))
```

### Complexity
- **Computation**: O(sides * num_rerolls)
- **Insight**: Diminishing returns -- each additional re-roll helps less
- **Convergence**: V(k) approaches max(die) as k grows'''),

    ("thinking/algorithms", r'''Implement a Markov chain solver. Given transition probabilities, compute the stationary distribution, expected hitting times, and absorption probabilities. Demonstrate with the Gambler's Ruin problem.''', r'''<think>
Markov chain solver. I need to handle stationary distributions, hitting times, and absorption probabilities. Let me think about the math.

For the stationary distribution pi: we need pi * P = pi with sum(pi) = 1. This is an eigenvector equation -- pi is the left eigenvector of P with eigenvalue 1. I could use power iteration (repeatedly multiply P by itself until rows converge) or solve the linear system directly. The direct approach is: (P^T - I) * pi = 0 with the constraint sum(pi) = 1. Replace one equation with the sum constraint and solve. I will implement both.

For Gambler's Ruin specifically, this is an absorbing Markov chain: states 0 and N are absorbing, and 1..N-1 are transient. I need absorption probabilities and expected time to absorption.

The standard framework for absorbing chains:
- Rearrange the transition matrix so absorbing states come last: P = [[Q, R], [0, I]]
- Q is transient-to-transient transitions, R is transient-to-absorbing
- The fundamental matrix N = (I - Q)^(-1) gives expected visits to each transient state
- B = N * R gives absorption probabilities
- t = N * 1 (ones vector) gives expected steps to absorption

Wait, I should verify: is (I - Q) always invertible? Since Q is substochastic (rows sum to less than 1 for transient states), the spectral radius of Q is less than 1, so yes, (I - Q) is invertible and the Neumann series converges. Good.

I will use numpy for the matrix operations since the closed-form for Gambler's Ruin (P(win from k) = k/N for fair game) provides a nice verification check.
</think>

## Markov Chain Solver

### Implementation

```python
import numpy as np


class MarkovChain:
    """Solver for discrete-time Markov chains."""

    def __init__(self, transition_matrix):
        self.P = np.array(transition_matrix, dtype=float)
        self.n = len(self.P)

    def stationary_distribution(self, max_iter=10000):
        """Compute stationary distribution by repeated squaring."""
        P_power = self.P.copy()
        for _ in range(50):  # P^(2^50) converges for ergodic chains
            P_power = P_power @ P_power
        # All rows should converge to the same distribution
        return P_power[0]

    def stationary_exact(self):
        """Solve pi * P = pi, sum(pi) = 1 using linear algebra."""
        # (P^T - I) * pi = 0, with sum constraint
        A = self.P.T - np.eye(self.n)
        # Replace last equation with sum = 1
        A[-1] = np.ones(self.n)
        b = np.zeros(self.n)
        b[-1] = 1.0
        return np.linalg.solve(A, b)


class AbsorbingMarkovChain:
    """Solver for absorbing Markov chains."""

    def __init__(self, transition_matrix, absorbing_states):
        P = np.array(transition_matrix, dtype=float)
        n = len(P)
        self.absorbing = sorted(absorbing_states)
        self.transient = [i for i in range(n) if i not in self.absorbing]

        # Extract Q (transient->transient) and R (transient->absorbing)
        t_idx = self.transient
        a_idx = self.absorbing
        self.Q = P[np.ix_(t_idx, t_idx)]
        self.R = P[np.ix_(t_idx, a_idx)]

        # Fundamental matrix N = (I - Q)^(-1)
        I = np.eye(len(t_idx))
        self.N = np.linalg.inv(I - self.Q)

    def absorption_probabilities(self):
        """B[i][j] = P(absorbed in absorbing state j | start in transient state i)."""
        B = self.N @ self.R
        return B

    def expected_steps(self):
        """Expected number of steps before absorption from each transient state."""
        return self.N @ np.ones(len(self.transient))

    def expected_visits(self):
        """N[i][j] = expected visits to transient state j starting from i."""
        return self.N


def gamblers_ruin(N, p, start):
    """Gambler's Ruin: states 0..N, absorbing at 0 and N.
    Move up with prob p, down with prob 1-p."""
    q = 1 - p
    n_states = N + 1

    # Build transition matrix
    P = np.zeros((n_states, n_states))
    P[0][0] = 1.0  # absorbing
    P[N][N] = 1.0  # absorbing
    for i in range(1, N):
        P[i][i + 1] = p
        P[i][i - 1] = q

    amc = AbsorbingMarkovChain(P, absorbing_states=[0, N])

    abs_prob = amc.absorption_probabilities()
    exp_steps = amc.expected_steps()

    # Map start state to transient index
    t_idx = start - 1  # transient states are 1..N-1, indexed 0..N-2

    prob_ruin = abs_prob[t_idx][0]    # absorbed at 0
    prob_win = abs_prob[t_idx][1]     # absorbed at N
    steps = exp_steps[t_idx]

    return prob_win, prob_ruin, steps


# Demo: Gambler's Ruin
print("=== Gambler's Ruin ===")
N = 10
for p in [0.5, 0.4, 0.6]:
    for start in [3, 5, 7]:
        pw, pr, steps = gamblers_ruin(N, p, start)
        print(f"  N={N}, p={p}, start={start}: "
              f"P(win)={pw:.4f}, P(ruin)={pr:.4f}, E[steps]={steps:.1f}")

# Verify analytic formula for fair game (p=0.5)
print("\n=== Verification (p=0.5, analytic: P(win) = k/N) ===")
for k in range(1, 10):
    pw, _, _ = gamblers_ruin(10, 0.5, k)
    analytic = k / 10
    print(f"  start={k}: computed={pw:.4f}, analytic={analytic:.4f}")

# Simple ergodic chain: weather model
print("\n=== Weather Markov Chain ===")
# States: 0=Sunny, 1=Cloudy, 2=Rainy
P_weather = [
    [0.7, 0.2, 0.1],
    [0.3, 0.4, 0.3],
    [0.2, 0.3, 0.5],
]
mc = MarkovChain(P_weather)
pi = mc.stationary_exact()
print(f"  Stationary: Sunny={pi[0]:.3f}, Cloudy={pi[1]:.3f}, Rainy={pi[2]:.3f}")
```

### Complexity
- **Stationary distribution**: O(n^3) for linear solve or O(n^2 * log(k)) for power iteration
- **Absorption analysis**: O(n^3) for matrix inversion
- **Gambler's Ruin closed form**: P(win from k) = k/N (fair) or (1-(q/p)^k)/(1-(q/p)^N) (unfair)'''),

    ("thinking/algorithms", r'''Implement a random walk simulation on a 2D grid. Compute the expected return time to the origin, verify Polya's recurrence theorem, and show that 2D walks are recurrent but 3D walks are transient.''', r'''<think>
Polya's recurrence theorem: random walks on integer lattices are recurrent iff dimension <= 2. I need to verify this by simulation.

The theorem is counterintuitive at first. In 1D, a walk always returns to the origin -- that makes sense intuitively since it can only go left or right. But the expected return time is infinite, which is surprising. In 2D, the walk is still recurrent (returns with probability 1), again with infinite expected return time. But in 3D, suddenly the walk is transient -- only about 34% chance of ever returning.

Why does dimension 3 break things? Intuitively, in higher dimensions there is just "more space" to wander into, so the walk diffuses away faster than it can find its way back. The probability of returning to the origin after 2n steps decays as ~1/n^(d/2), so the sum diverges for d <= 2 (recurrent) but converges for d >= 3 (transient).

For the simulation, I will run many random walks in each dimension and track what fraction return within a given number of steps. As the step limit increases, 1D and 2D should approach 100%, while 3D should plateau around 34%.

Hmm, actually I need to be careful with the 3D simulation -- with only 10,000 steps, many 2D walks might not have returned yet either, since the expected time is infinite. I should use larger step counts for 2D to see the convergence.

The theoretical 3D return probability comes from Watson's triple integral: P(return) = 1 - 1/u(3) where u(3) is approximately 1.5163860591, giving about 0.3405. I will compare against this.
</think>

## Random Walk and Polya's Recurrence Theorem

### Implementation

```python
import random


def random_walk_return_rate(dim, max_steps, num_walks):
    """Simulate random walks and compute fraction returning to origin.

    Args:
        dim: dimension (1, 2, or 3)
        max_steps: maximum steps per walk
        num_walks: number of walks to simulate

    Returns:
        fraction of walks that returned to origin
    """
    returned = 0

    for _ in range(num_walks):
        pos = [0] * dim
        for step in range(1, max_steps + 1):
            # Choose random dimension and direction
            axis = random.randint(0, dim - 1)
            direction = random.choice([-1, 1])
            pos[axis] += direction

            if all(p == 0 for p in pos):
                returned += 1
                break

    return returned / num_walks


def polya_return_probability_3d():
    """Compute the theoretical return probability for 3D walk.
    P(return) = 1 - 1/u(3)
    u(3) = (6/(2*pi)^3) * triple integral ... approximately 1.5163860
    Simplified: P(return) ~= 0.340537
    """
    # Watson's triple integral result
    u3 = 1.5163860591
    return 1 - 1 / u3


# Simulation
random.seed(42)
print("=== Polya's Recurrence Theorem Verification ===")
print("Fraction of walks returning to origin:\n")

dims = [1, 2, 3]
step_limits = [100, 1000, 10000]
num_walks = 10000

for dim in dims:
    print(f"  {dim}D random walk:")
    for max_steps in step_limits:
        rate = random_walk_return_rate(dim, max_steps, num_walks)
        print(f"    {max_steps:6d} steps: {rate:.4f} ({rate*100:.1f}%)")
    print()

print("Theoretical 3D return probability: "
      f"{polya_return_probability_3d():.4f}")

print("\n=== Key Results ===")
print("1D: Recurrent (P(return) = 1, E[return time] = infinity)")
print("2D: Recurrent (P(return) = 1, E[return time] = infinity)")
print("3D: Transient (P(return) ~= 0.3405)")


# Expected displacement analysis
def expected_displacement(dim, steps, trials=50000):
    """Compute expected squared displacement after n steps.
    Theory: E[|X_n|^2] = n for all dimensions."""
    total_sq_dist = 0
    for _ in range(trials):
        pos = [0] * dim
        for _ in range(steps):
            axis = random.randint(0, dim - 1)
            pos[axis] += random.choice([-1, 1])
        total_sq_dist += sum(p * p for p in pos)
    return total_sq_dist / trials

print("\n=== Expected Squared Displacement (should equal n) ===")
for dim in [1, 2, 3]:
    for n in [10, 100, 500]:
        esd = expected_displacement(dim, n, trials=20000)
        print(f"  {dim}D, n={n:3d}: E[|X|^2] = {esd:.1f} (theory: {n})")
```

### Key Theoretical Results
| Dimension | Recurrent? | P(return) | E[return time] |
|-----------|-----------|-----------|---------------|
| 1D        | Yes       | 1         | Infinity      |
| 2D        | Yes       | 1         | Infinity      |
| 3D        | No        | ~0.3405   | N/A           |
| d >= 3    | No        | < 1       | N/A           |

### Complexity
- **Simulation**: O(num_walks * max_steps) per dimension
- **The paradox**: despite certain return in 2D, the expected time is infinite -- walks take arbitrarily long detours before returning'''),

    ("thinking/algorithms", r'''Analyze birthday problem variants algorithmically. Compute exact and approximate collision probabilities for: (1) standard birthday problem, (2) birthday with 3-way collisions, (3) birthday in a non-uniform distribution. Implement efficient solutions.''', r'''<think>
Birthday problem variants. Let me work through each one.

1. Standard: n people, 365 days. P(at least one collision) = 1 - P(all different) = 1 - 365!/(365^n * (365-n)!). The approximation uses P(all different) ~ e^(-n(n-1)/(2*365)), giving 50% around n=23. Straightforward.

2. Three-way collision: P(at least 3 people share a birthday). This is significantly harder. I need P(no triple collision) = ways to assign n people to 365 days with at most 2 per day, divided by 365^n.

My first attempt at a DP: dp[k][j] = ways to assign j people to the first k days, max 2 per day. For each new day, we can place 0, 1, or 2 people on it. But this requires tracking "remaining people" which makes the state space large.

Wait, actually I can think combinatorially instead. Let a = number of days with exactly 1 person, b = number of days with exactly 2 people. Then a + 2b = n and a + b <= d. The count is:
C(d, b) * C(d-b, a) * n! / 2^b

C(d,b) chooses which days get pairs, C(d-b,a) chooses which remaining days get singles, n! orders the people, and 2^b accounts for the pair ordering (within each pair the order does not matter). Then P(no triple) = sum of these over valid (a,b), divided by d^n.

Hmm, I need to be careful with numerical stability since these numbers get huge. I should work in log-space and use log-sum-exp.

3. Non-uniform distribution: birthdays are not equally likely. Intuitively, concentrating probability makes collisions MORE likely (by Schur convexity / Jensen's inequality). I will verify this with simulation, using a distribution where summer months are twice as likely.
</think>

## Birthday Problem Variants

### Implementation

```python
import math
from functools import lru_cache


def birthday_exact(n, d=365):
    """Exact probability of at least one collision among n people, d days."""
    if n > d:
        return 1.0
    # P(no collision) = d * (d-1) * ... * (d-n+1) / d^n
    log_no_collision = 0
    for i in range(n):
        log_no_collision += math.log(d - i) - math.log(d)
    return 1 - math.exp(log_no_collision)


def birthday_approx(n, d=365):
    """Approximation: P ~ 1 - exp(-n*(n-1)/(2*d))."""
    return 1 - math.exp(-n * (n - 1) / (2 * d))


def birthday_threshold(d=365, target=0.5):
    """Find smallest n where P(collision) >= target."""
    for n in range(1, d + 2):
        if birthday_exact(n, d) >= target:
            return n
    return d + 1


def birthday_triple_sim(n, d=365, trials=500000):
    """Simulate probability of 3+ people sharing a birthday."""
    import random
    collisions = 0
    for _ in range(trials):
        counts = [0] * d
        triple = False
        for _ in range(n):
            day = random.randint(0, d - 1)
            counts[day] += 1
            if counts[day] >= 3:
                triple = True
                break
        if triple:
            collisions += 1
    return collisions / trials


def birthday_triple_exact(n, d=365):
    """Exact P(triple collision) using DP.
    P(no triple) = ways to assign n people to d days, max 2 per day / d^n."""
    if n > 2 * d:
        return 1.0

    # dp[j] = number of ways (as log) to assign j people to first k days
    # Use combinatorial formula:
    # Ways = sum over b (days with 2 people): C(d,b) * C(d-b, n-2b) * n! / 2^b
    # where n - 2b people go to single days, b pairs go to double days
    log_total = n * math.log(d)

    log_ways = []
    for b in range(n // 2 + 1):
        a = n - 2 * b  # single-occupancy days
        if a < 0 or a + b > d:
            continue
        # C(d, b) * C(d-b, a) * n! / (2^b)
        log_term = (math.lgamma(d + 1) - math.lgamma(b + 1) - math.lgamma(d - b + 1)
                    + math.lgamma(d - b + 1) - math.lgamma(a + 1) - math.lgamma(d - b - a + 1)
                    + math.lgamma(n + 1)
                    - b * math.log(2))
        log_ways.append(log_term)

    if not log_ways:
        return 1.0

    # Log-sum-exp for numerical stability
    max_log = max(log_ways)
    log_sum = max_log + math.log(sum(math.exp(lw - max_log) for lw in log_ways))

    p_no_triple = math.exp(log_sum - log_total)
    return max(0, min(1, 1 - p_no_triple))


def birthday_nonuniform(n, probs, trials=500000):
    """Birthday problem with non-uniform day probabilities.
    probs[i] = probability of being born on day i."""
    import random
    days = list(range(len(probs)))
    cum = []
    s = 0
    for p in probs:
        s += p
        cum.append(s)

    def sample():
        r = random.random()
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < r:
                lo = mid + 1
            else:
                hi = mid
        return lo

    collisions = 0
    for _ in range(trials):
        seen = set()
        found = False
        for _ in range(n):
            day = sample()
            if day in seen:
                found = True
                break
            seen.add(day)
        if found:
            collisions += 1
    return collisions / trials


# Demo
print("=== Standard Birthday Problem ===")
for n in [10, 20, 23, 30, 50, 57, 70]:
    exact = birthday_exact(n)
    approx = birthday_approx(n)
    print(f"  n={n:2d}: exact={exact:.4f}, approx={approx:.4f}")

threshold = birthday_threshold()
print(f"\n  50% threshold: n = {threshold}")

print("\n=== Triple Birthday Collision ===")
import random
random.seed(42)
for n in [50, 80, 88, 100, 120]:
    sim = birthday_triple_sim(n, trials=200000)
    exact = birthday_triple_exact(n)
    print(f"  n={n:3d}: exact={exact:.4f}, simulated={sim:.4f}")

print("\n=== Non-uniform Birthdays ===")
# Half the population born in summer (days 150-240)
probs = [1.0 / 365] * 365
# Make summer 2x more likely
for d in range(150, 240):
    probs[d] = 2.0 / 365
total = sum(probs)
probs = [p / total for p in probs]
for n in [15, 20, 23, 30]:
    uniform = birthday_exact(n)
    nonunif = birthday_nonuniform(n, probs, trials=200000)
    print(f"  n={n:2d}: uniform={uniform:.4f}, non-uniform={nonunif:.4f}")
print("  (Non-uniform always has HIGHER collision probability)")
```

### Key Results
- Standard: 23 people for >50% collision in 365 days
- Triple collision: ~88 people for >50% probability
- Non-uniform distributions increase collision probability (Schur convexity)
- Approximation: n ~= sqrt(2 * d * ln(2)) for 50% threshold'''),

    ("thinking/algorithms", r'''Implement Monte Carlo methods for estimating pi, computing integrals, and solving optimization problems. Show importance sampling and variance reduction techniques.''', r'''<think>
Monte Carlo methods. I need to cover pi estimation, integration, and optimization. Let me think about variance reduction too.

1. Estimating pi: throw random points in [0,1]^2, check if they fall inside the quarter circle. Fraction inside ~ pi/4. Simple but converges as O(1/sqrt(n)) -- I would need 10^6 points for about 3 decimal places. Not great, but good for demonstration.

2. Integration: basic MC estimates integral of f(x) over [a,b] as (b-a) * mean(f(x_i)). But the variance can be high. How do we reduce it?

Antithetic variates: for each uniform sample u, also use 1-u. If f is monotonic, f(u) and f(1-u) are negatively correlated, so their average has lower variance than two independent samples. This should roughly halve the variance for functions like sin(x).

Stratified sampling: divide [a,b] into strata and sample from each. This ensures uniform coverage and eliminates the variance from "clumping" of random samples. In the best case this improves convergence from O(1/sqrt(n)) to O(1/n).

Importance sampling: instead of sampling uniformly, sample from a distribution g(x) proportional to |f(x)|. We reweight: I = E[f(x)/g(x)] under g. The variance is minimized when g matches |f| perfectly, but even a rough approximation helps. I initially considered implementing a full importance sampling example, but the proposal distribution choice is problem-specific, so I will keep it general.

3. Optimization via simulated annealing: accept random perturbations, sometimes accepting worse solutions with probability e^(-delta/T). As temperature T decreases, we become greedier. The Rastrigin function is a good test case -- many local minima but one global minimum at 0.
</think>

## Monte Carlo Methods

### Implementation

```python
import random
import math


def estimate_pi(n):
    """Estimate pi by random point-in-circle method."""
    inside = 0
    for _ in range(n):
        x = random.random()
        y = random.random()
        if x * x + y * y <= 1:
            inside += 1
    return 4 * inside / n


def monte_carlo_integral(f, a, b, n):
    """Estimate integral of f(x) from a to b using basic MC."""
    total = 0
    for _ in range(n):
        x = a + (b - a) * random.random()
        total += f(x)
    estimate = (b - a) * total / n
    return estimate


def mc_antithetic(f, a, b, n):
    """MC integration with antithetic variates for variance reduction."""
    total = 0
    for _ in range(n // 2):
        u = random.random()
        x1 = a + (b - a) * u
        x2 = a + (b - a) * (1 - u)  # antithetic
        total += f(x1) + f(x2)
    return (b - a) * total / n


def mc_stratified(f, a, b, n, num_strata=10):
    """Stratified sampling: divide [a,b] into strata."""
    total = 0
    strata_width = (b - a) / num_strata
    samples_per = n // num_strata
    for s in range(num_strata):
        lo = a + s * strata_width
        for _ in range(samples_per):
            x = lo + strata_width * random.random()
            total += f(x) * strata_width
    return total / samples_per


def mc_importance_sampling(f, g_sample, g_pdf, n):
    """Importance sampling: sample from g, weight by f/g.
    g_sample(): draw from proposal distribution g
    g_pdf(x): evaluate density of g at x
    Estimates integral of f(x) dx."""
    total = 0
    for _ in range(n):
        x = g_sample()
        total += f(x) / g_pdf(x)
    return total / n


def simulated_annealing(objective, x0, neighbor, T0=1.0,
                         cooling=0.999, steps=100000):
    """Minimize objective using simulated annealing."""
    x = x0
    fx = objective(x)
    best_x, best_fx = x, fx
    T = T0

    for _ in range(steps):
        x_new = neighbor(x)
        fx_new = objective(x_new)
        delta = fx_new - fx

        if delta < 0 or random.random() < math.exp(-delta / max(T, 1e-10)):
            x, fx = x_new, fx_new
            if fx < best_fx:
                best_x, best_fx = x, fx

        T *= cooling

    return best_x, best_fx


# Demo
random.seed(42)

# 1. Estimate pi
print("=== Estimating Pi ===")
for n in [1000, 10000, 100000, 1000000]:
    pi_est = estimate_pi(n)
    error = abs(pi_est - math.pi)
    print(f"  n={n:>8d}: pi ~= {pi_est:.6f}, error = {error:.6f}")

# 2. Integration: integral of sin(x) from 0 to pi = 2.0
print("\n=== Integration: integral sin(x) from 0 to pi ===")
f = math.sin
n = 100000
basic = monte_carlo_integral(f, 0, math.pi, n)
anti = mc_antithetic(f, 0, math.pi, n)
strat = mc_stratified(f, 0, math.pi, n)
print(f"  Exact:      2.000000")
print(f"  Basic MC:   {basic:.6f}")
print(f"  Antithetic: {anti:.6f}")
print(f"  Stratified: {strat:.6f}")

# Variance comparison
print("\n=== Variance Comparison (100 trials) ===")
basic_results = [monte_carlo_integral(f, 0, math.pi, 10000) for _ in range(100)]
anti_results = [mc_antithetic(f, 0, math.pi, 10000) for _ in range(100)]

def variance(vals):
    m = sum(vals) / len(vals)
    return sum((v - m) ** 2 for v in vals) / len(vals)

print(f"  Basic MC variance:   {variance(basic_results):.8f}")
print(f"  Antithetic variance: {variance(anti_results):.8f}")
print(f"  Variance reduction:  {variance(basic_results)/max(variance(anti_results),1e-15):.1f}x")

# 3. Optimization: minimize Rastrigin function
print("\n=== Simulated Annealing: Rastrigin Function ===")
def rastrigin(x):
    return 10 + x * x - 10 * math.cos(2 * math.pi * x)

def neighbor(x):
    return x + random.gauss(0, 0.1)

best_x, best_f = simulated_annealing(rastrigin, 5.0, neighbor)
print(f"  Minimum found at x = {best_x:.6f}, f(x) = {best_f:.6f}")
print(f"  True minimum at x = 0, f(0) = 0")
```

### Convergence Rates
| Method | Convergence | Variance |
|--------|------------|---------|
| Basic MC | O(1/sqrt(n)) | sigma^2/n |
| Antithetic | O(1/sqrt(n)) | Reduced by correlation |
| Stratified | O(1/n) in best case | Much lower |
| Importance | O(1/sqrt(n)) | Depends on proposal fit |'''),
]
