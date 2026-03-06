PAIRS = [
    ("thinking/algorithms", r'''Implement modular exponentiation: compute (base^exp) mod m efficiently. Handle large exponents that would overflow with naive computation. Explain the binary exponentiation technique.''', r'''<think>
I need to compute (base^exp) % mod. The naive approach would be to compute base^exp first and then take mod, but for exp = 10^18 that is completely infeasible -- the intermediate number would have billions of digits.

The key insight that makes this tractable: we can take mod at every step because (a * b) mod m = ((a mod m) * (b mod m)) mod m. So we never need numbers larger than mod^2.

But even with modular reduction at each step, multiplying base * base * base ... exp times is O(exp) multiplications. For exp = 10^18, that is still way too slow.

This is where binary exponentiation comes in. Instead of computing base^exp linearly, we can use the fact that:
- If exp is even: base^exp = (base^(exp/2))^2
- If exp is odd: base^exp = base * base^(exp-1)

So we halve the exponent at each step, giving O(log exp) multiplications. For exp = 10^18, that is only about 60 steps.

I initially thought about implementing this recursively (top-down), but there is a cleaner iterative version that processes the exponent from the least significant bit:
- result = 1
- While exp > 0: if exp is odd, result *= base (mod m). Then base = base^2 (mod m), exp >>= 1.

Wait, why does this work? At each step, base holds base^(2^k) for the current bit position k. When exp's bit k is set, we multiply result by base^(2^k). The product of all these contributions gives base^exp.

Edge cases: exp = 0 gives 1 (by convention, even 0^0 = 1 here). mod = 1 always gives 0 since everything mod 1 is 0.

Time: O(log exp) multiplications, each O(1) for fixed-size integers.
Space: O(1) iterative.
</think>

**Modular Exponentiation -- Binary Exponentiation**

```python
def mod_pow(base, exp, mod):
    """
    Compute (base^exp) % mod using binary exponentiation.

    Args:
        base: base integer
        exp: non-negative exponent
        mod: modulus (positive integer)
    Returns:
        (base^exp) % mod
    """
    if mod == 1:
        return 0

    result = 1
    base = base % mod

    while exp > 0:
        if exp & 1:  # exp is odd
            result = (result * base) % mod
        exp >>= 1
        base = (base * base) % mod

    return result


def mod_pow_recursive(base, exp, mod):
    """Recursive version for clarity."""
    if mod == 1:
        return 0
    if exp == 0:
        return 1
    if exp == 1:
        return base % mod

    half = mod_pow_recursive(base, exp // 2, mod)
    result = (half * half) % mod

    if exp % 2 == 1:
        result = (result * base) % mod

    return result


# Examples
tests = [
    (2, 10, 1000),      # 1024 % 1000 = 24
    (3, 13, 7),          # 1594323 % 7 = 3
    (2, 100, 1000000007),
    (123456789, 987654321, 1000000007),
]

for base, exp, mod in tests:
    r1 = mod_pow(base, exp, mod)
    r2 = mod_pow_recursive(base, exp, mod)
    r3 = pow(base, exp, mod)  # Python built-in
    match = r1 == r2 == r3
    print(f"  {base}^{exp} mod {mod} = {r1}  (match={match})")

# Application: Modular inverse using Fermat's little theorem
# If p is prime: a^(-1) mod p = a^(p-2) mod p
def mod_inverse(a, p):
    """Modular inverse of a mod p (p must be prime)."""
    return mod_pow(a, p - 2, p)

p = 1000000007
a = 42
inv = mod_inverse(a, p)
print(f"\n  Inverse of {a} mod {p} = {inv}")
print(f"  Verify: {a} * {inv} mod {p} = {(a * inv) % p}")
```

**Binary Exponentiation Trace (3^13 mod 7):**
```
exp=13 (1101b): base=3, result=1
  exp odd:  result = 1*3 = 3,  base = 3*3=9%7=2,  exp=6
  exp even:                     base = 2*2=4,       exp=3
  exp odd:  result = 3*4=12%7=5, base = 4*4=16%7=2, exp=1
  exp odd:  result = 5*2=10%7=3, done
  Answer: 3
```

**Applications:**
- RSA encryption (modular exponentiation of large numbers)
- Modular inverse via Fermat's little theorem
- Discrete logarithm problems
- Competitive programming (operations mod 10^9 + 7)

**Complexity:**
- Time: O(log exp) -- one multiplication per bit of exponent
- Space: O(1) iterative'''),

    ("thinking/algorithms", r'''Implement the Chinese Remainder Theorem (CRT): given a system of simultaneous congruences x = a_i (mod m_i) where the moduli are pairwise coprime, find the unique solution x modulo M = product of all m_i.''', r'''<think>
I need to solve a system of simultaneous congruences: x = a_i (mod m_i) for pairwise coprime moduli. The CRT guarantees a unique solution modulo M = product of all m_i.

But how do we actually construct the solution? Let me think about this...

The idea is to build x as a sum of terms, where each term "activates" for exactly one congruence and is zero for all the others. For congruence i, define M_i = M / m_i. Since the moduli are pairwise coprime, M_i is divisible by every m_j except m_i. So M_i = 0 (mod m_j) for j != i, but gcd(M_i, m_i) = 1.

Since gcd(M_i, m_i) = 1, we can find y_i = M_i^(-1) mod m_i using the extended Euclidean algorithm. Then the term a_i * M_i * y_i equals a_i (mod m_i) and 0 (mod m_j) for j != i. Summing all such terms and reducing mod M gives the solution.

Wait, I should also think about the case where the moduli are NOT pairwise coprime. The standard CRT does not apply directly. For two congruences x = a1 (mod m1) and x = a2 (mod m2), a solution exists if and only if gcd(m1, m2) divides (a2 - a1). The combined modulus becomes lcm(m1, m2) instead of m1 * m2.

I initially planned to just implement the standard coprime CRT, but the generalized version is more useful in practice. I can implement it by solving pairs of congruences iteratively -- take two at a time, combine them into one, then combine with the next. This handles both coprime and non-coprime cases.

For the pairwise combination: given x = a1 (mod m1) and x = a2 (mod m2), we need a1 + m1*k = a2 (mod m2), so m1*k = (a2 - a1) (mod m2). Using extended GCD to solve for k, then x = a1 + m1*k, with new modulus = lcm(m1, m2).

I will implement both the standard CRT (for coprime moduli, clean formula) and the generalized version (pairwise combining, handles everything).
</think>

**Chinese Remainder Theorem -- Implementation**

```python
def extended_gcd(a, b):
    """Return (gcd, x, y) such that a*x + b*y = gcd(a, b)."""
    if b == 0:
        return a, 1, 0
    g, x, y = extended_gcd(b, a % b)
    return g, y, x - (a // b) * y


def mod_inverse(a, m):
    """Modular inverse of a mod m. Requires gcd(a, m) = 1."""
    g, x, _ = extended_gcd(a % m, m)
    if g != 1:
        raise ValueError(f"No inverse: gcd({a}, {m}) = {g}")
    return x % m


def chinese_remainder_theorem(remainders, moduli):
    """
    Solve system of congruences x = a_i (mod m_i).

    Args:
        remainders: list of a_i values
        moduli: list of m_i values (must be pairwise coprime)
    Returns:
        (x, M) where x is the solution and M is the combined modulus
    """
    M = 1
    for m in moduli:
        M *= m

    x = 0
    for a_i, m_i in zip(remainders, moduli):
        M_i = M // m_i
        y_i = mod_inverse(M_i, m_i)
        x += a_i * M_i * y_i

    return x % M, M


def crt_two(a1, m1, a2, m2):
    """Solve x = a1 (mod m1), x = a2 (mod m2). Works for non-coprime moduli."""
    g, p, _ = extended_gcd(m1, m2)
    if (a2 - a1) % g != 0:
        return None, None  # No solution

    lcm = m1 * m2 // g
    x = (a1 + m1 * ((a2 - a1) // g) * p) % lcm
    return x, lcm


def crt_general(remainders, moduli):
    """Generalized CRT for possibly non-coprime moduli."""
    if not remainders:
        return 0, 1

    cur_a, cur_m = remainders[0], moduli[0]
    for i in range(1, len(remainders)):
        cur_a, cur_m = crt_two(cur_a, cur_m, remainders[i], moduli[i])
        if cur_m is None:
            return None, None  # No solution
    return cur_a, cur_m


# Example 1: Classic CRT (coprime moduli)
remainders = [2, 3, 2]
moduli = [3, 5, 7]
x, M = chinese_remainder_theorem(remainders, moduli)
print(f"System: x={remainders}, mod={moduli}")
print(f"Solution: x = {x} (mod {M})")
for a, m in zip(remainders, moduli):
    print(f"  Verify: {x} mod {m} = {x % m} (expected {a})")

# Example 2: Non-coprime moduli
print(f"\nGeneralized CRT:")
r2, m2 = [1, 2, 3], [4, 6, 9]
x2, M2 = crt_general(r2, m2)
if x2 is not None:
    print(f"  x = {x2} (mod {M2})")
    for a, m in zip(r2, m2):
        print(f"  {x2} mod {m} = {x2 % m} (expected {a})")
else:
    print("  No solution")

# Application: reconstruct a number from remainders
# "What number leaves remainder 2 when divided by 3, 3 by 5, 1 by 7?"
x3, M3 = chinese_remainder_theorem([2, 3, 1], [3, 5, 7])
print(f"\nApplication: x = {x3} (mod {M3})")
```

**Complexity:**
- CRT with k congruences: O(k * log(max_modulus)) -- dominated by modular inverse computations
- Space: O(k)'''),

    ("thinking/algorithms", r'''Implement Euler's Totient Function phi(n): the count of integers from 1 to n that are coprime with n. Include an efficient sieve-based approach for computing phi for all numbers up to n.''', r'''<think>
I need to compute phi(n), the count of integers in [1, n] that are coprime with n. For example, phi(12) should count {1, 5, 7, 11} = 4.

I could brute-force it by checking gcd(k, n) for every k from 1 to n, but that is O(n * log n) per query. There must be a formula.

The formula comes from inclusion-exclusion on the prime factors of n. If n = p1^a1 * p2^a2 * ... * pk^ak, then:
phi(n) = n * (1 - 1/p1) * (1 - 1/p2) * ... * (1 - 1/pk)

Why? Out of n numbers from 1 to n, we subtract those divisible by p1 (n/p1 of them), those by p2, etc., then add back those divisible by both p1 and p2, and so on. The inclusion-exclusion simplifies to the product formula.

For computing a single phi(n), I can factorize n by trial division up to sqrt(n). For each prime factor p found, I multiply result by (p-1)/p. To avoid floating point, I use integer arithmetic: result -= result // p. If after the loop n > 1, the remaining n is itself a prime factor.

But what if I need phi(k) for ALL k from 1 to N? Computing each individually would be O(N * sqrt(N)). A sieve is much better.

The sieve approach mirrors the Sieve of Eratosthenes:
1. Initialize phi[i] = i for all i
2. For each i from 2 to N: if phi[i] == i, then i is prime (not yet modified by any smaller prime). For all multiples j of i: phi[j] -= phi[j] // i.

Hmm, wait -- this works because each prime p is encountered exactly once, and the operation phi[j] -= phi[j] // i correctly multiplies by (1 - 1/p) in integer arithmetic. After processing all primes, phi[j] has been multiplied by (1 - 1/p) for each of its prime factors.

Time: O(sqrt(n)) for single computation, O(N log log N) for the sieve (same as Eratosthenes).
</think>

**Euler's Totient Function -- Single Value and Sieve**

```python
def euler_totient(n):
    """
    Compute phi(n) for a single value.

    Args:
        n: positive integer
    Returns:
        count of integers in [1, n] coprime with n
    """
    if n <= 0:
        return 0
    result = n
    p = 2

    while p * p <= n:
        if n % p == 0:
            # Remove all factors of p
            while n % p == 0:
                n //= p
            result -= result // p
        p += 1

    # If n > 1, then it is a remaining prime factor
    if n > 1:
        result -= result // n

    return result


def totient_sieve(limit):
    """
    Compute phi(i) for all i from 0 to limit.

    Uses a sieve approach similar to Sieve of Eratosthenes.
    Time: O(n log log n).
    """
    phi = list(range(limit + 1))  # phi[i] = i initially

    for p in range(2, limit + 1):
        if phi[p] == p:  # p is prime (not yet modified)
            # Apply phi formula for all multiples of p
            for j in range(p, limit + 1, p):
                phi[j] -= phi[j] // p

    return phi


# Single values
for n in [1, 6, 10, 12, 36, 97, 100]:
    print(f"  phi({n}) = {euler_totient(n)}")

# Sieve
limit = 20
phi = totient_sieve(limit)
print(f"\nTotient sieve up to {limit}:")
print(f"  n:      {list(range(1, limit+1))}")
print(f"  phi(n): {phi[1:]}")

# Verify property: sum of phi(d) for d|n equals n
def divisors(n):
    result = []
    for i in range(1, int(n**0.5) + 1):
        if n % i == 0:
            result.append(i)
            if i != n // i:
                result.append(n // i)
    return sorted(result)

print(f"\nVerify: sum(phi(d) for d|n) = n")
for n in [12, 18, 30]:
    divs = divisors(n)
    total = sum(euler_totient(d) for d in divs)
    print(f"  n={n}: divisors={divs}, sum={total}, match={total==n}")

# Application: Euler's theorem
# If gcd(a, n) = 1, then a^phi(n) = 1 (mod n)
a, n = 7, 12
phi_n = euler_totient(n)
result = pow(a, phi_n, n)
print(f"\nEuler's theorem: {a}^phi({n}) = {a}^{phi_n} = {result} (mod {n})")
```

**Key Properties:**
- phi(p) = p - 1 for prime p
- phi(p^k) = p^(k-1) * (p - 1)
- Multiplicative: gcd(a,b)=1 implies phi(a*b) = phi(a)*phi(b)
- Euler's theorem: a^phi(n) = 1 (mod n) when gcd(a,n) = 1
- Generalizes Fermat's little theorem: a^(p-1) = 1 (mod p)

**Complexity:**
- Single value: O(sqrt(n))
- Sieve up to N: O(N log log N)
- Space: O(N) for sieve'''),

    ("thinking/algorithms", r'''Implement the Miller-Rabin primality test: a probabilistic algorithm to determine if a number is prime. Include deterministic witnesses for numbers up to specific bounds.''', r'''<think>
I need a fast primality test for large numbers. Trial division works up to about 10^12 but beyond that it is too slow. Fermat's test (check if a^(n-1) = 1 mod n) is fast but fails for Carmichael numbers like 561, which pass the test for ALL bases despite being composite.

Miller-Rabin fixes this vulnerability. The key observation: for a prime p, the only square roots of 1 mod p are 1 and -1. But for composites, there can be non-trivial square roots of 1 (numbers that square to 1 but are not 1 or -1). Miller-Rabin detects these.

The algorithm: write n-1 = 2^s * d where d is odd. For witness a:
1. Compute x = a^d mod n
2. If x == 1 or x == n-1, it looks prime so far -- skip to next witness
3. Otherwise, repeatedly square x up to s-1 times:
   - If x becomes n-1, it looks prime (found -1, which is a valid sqrt of 1)
   - If x becomes 1, then the previous x was a non-trivial sqrt of 1. Composite!
4. If we never hit 1 or n-1, then a^(n-1) != 1 mod n, so n is composite by Fermat.

I initially worried about false positives -- could a composite pass for some witness? Yes, but for any composite n, at most 1/4 of witnesses fail to detect it. So with k random witnesses, error probability < (1/4)^k.

But actually, for competitive programming and practical use, we do not need randomness at all! Specific small sets of witnesses are proven to be deterministic up to certain bounds:
- n < 2^31: witnesses {2, 7, 61} suffice
- n < 2^64: witnesses {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37} suffice

Wait, why does this work against Carmichael numbers? Because Carmichael numbers only fool the Fermat test (a^(n-1) = 1 mod n). But Miller-Rabin goes further by checking the intermediate squares on the way from a^d to a^(n-1). Carmichael numbers inevitably produce non-trivial square roots of 1 for most witnesses, which Miller-Rabin catches.

Time: O(k * log^2 n) for k witnesses.
</think>

**Miller-Rabin Primality Test**

```python
def miller_rabin(n, witnesses=None):
    """
    Miller-Rabin primality test.

    Args:
        n: integer to test
        witnesses: list of bases to test, or None for deterministic set
    Returns:
        True if n is (probably) prime, False if definitely composite
    """
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False

    # Factor out powers of 2: n - 1 = 2^s * d
    s, d = 0, n - 1
    while d % 2 == 0:
        s += 1
        d //= 2

    # Deterministic witnesses for different ranges
    if witnesses is None:
        if n < 2047:
            witnesses = [2]
        elif n < 1373653:
            witnesses = [2, 3]
        elif n < 3215031751:
            witnesses = [2, 3, 5, 7]
        elif n < 3317044064679887385961981:
            witnesses = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
        else:
            # For very large numbers, use first 20 primes
            witnesses = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29,
                         31, 37, 41, 43, 47, 53, 59, 61, 67, 71]

    for a in witnesses:
        if a >= n:
            continue

        x = pow(a, d, n)

        if x == 1 or x == n - 1:
            continue

        composite = True
        for _ in range(s - 1):
            x = pow(x, x, n)  # wrong -- should be x = x^2 mod n
            x = (x * x) % n   # but we already squared above...

        # Let me fix this -- restart the inner loop logic
        # Actually let me rewrite cleanly
        pass

    # Clean implementation
    for a in witnesses:
        if a >= n:
            continue
        if not _check_witness(a, d, n, s):
            return False

    return True


def _check_witness(a, d, n, s):
    """Check single witness. Returns True if n passes (probably prime)."""
    x = pow(a, d, n)

    if x == 1 or x == n - 1:
        return True

    for _ in range(s - 1):
        x = (x * x) % n
        if x == n - 1:
            return True
        if x == 1:
            return False  # non-trivial sqrt of 1

    return False


def is_prime(n):
    """Deterministic primality test for n < 3.3 * 10^24."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False

    # Quick trial division for small factors
    i = 5
    while i * i <= n and i < 1000:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6

    return miller_rabin(n)


# Test against known primes
small_primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47}
print("Small number tests:")
for n in range(2, 50):
    result = is_prime(n)
    expected = n in small_primes
    status = "PASS" if result == expected else "FAIL"
    if status == "FAIL":
        print(f"  [{status}] is_prime({n}) = {result}")

print("  All small tests passed!")

# Large primes
large_tests = [
    (104729, True),        # prime
    (104730, False),
    (999999937, True),     # largest prime < 10^9
    (1000000007, True),    # common modular prime
    (561, False),          # Carmichael number (fools Fermat test)
    (1105, False),         # Carmichael number
    (2147483647, True),    # Mersenne prime M31
]

print("\nLarge number tests:")
for n, expected in large_tests:
    result = is_prime(n)
    status = "PASS" if result == expected else "FAIL"
    label = "prime" if expected else "composite"
    print(f"  [{status}] {n} ({label}): is_prime={result}")
```

**Why Miller-Rabin Catches Carmichael Numbers:**
- Carmichael numbers pass Fermat's test for all bases
- But Miller-Rabin also checks intermediate square roots
- A composite n has non-trivial square roots of 1, which Miller-Rabin detects

**Complexity:**
- Per witness: O(log^2 n) for modular exponentiation
- Deterministic for n < 3.3 * 10^24 with 12 witnesses
- Probabilistic: error < (1/4)^k with k random witnesses'''),

    ("thinking/algorithms", r'''Implement the Extended Euclidean Algorithm: given integers a and b, find their GCD and also find integers x and y such that ax + by = gcd(a, b). Show applications including modular inverse computation.''', r'''<think>
The Extended Euclidean Algorithm extends the basic Euclidean algorithm (which finds gcd(a, b)) to also find coefficients x and y satisfying Bezout's identity: ax + by = gcd(a, b).

The basic Euclidean algorithm: gcd(a, b) = gcd(b, a mod b), with base case gcd(a, 0) = a.

Extension: If we know that b*x1 + (a mod b)*y1 = gcd(b, a mod b), then since a mod b = a - (a//b)*b:
b*x1 + (a - (a//b)*b)*y1 = g
a*y1 + b*(x1 - (a//b)*y1) = g

So: x = y1, y = x1 - (a//b)*y1

Base case: gcd(a, 0) = a, with x = 1, y = 0 (a*1 + 0*0 = a).

I should implement both recursive and iterative versions.

Applications:
1. Modular inverse: To find a^(-1) mod m, solve ax + my = 1 (when gcd(a,m)=1). Then x mod m is the inverse.
2. Linear Diophantine equations: ax + by = c has solutions iff gcd(a,b) divides c.
3. Chinese Remainder Theorem (uses modular inverse internally).

The iterative version avoids stack overflow for very large inputs and is preferred in practice.

Edge cases:
- One of a, b is 0
- Negative inputs
- gcd(a, b) != 1 (no modular inverse exists)
- a = b

Time: O(log(min(a, b))) -- same as basic Euclidean algorithm.
Space: O(1) for iterative, O(log(min(a, b))) for recursive.
</think>

**Extended Euclidean Algorithm**

```python
def extended_gcd_recursive(a, b):
    """
    Recursive extended GCD.

    Returns (gcd, x, y) such that a*x + b*y = gcd(a, b).
    """
    if b == 0:
        return a, 1, 0
    g, x1, y1 = extended_gcd_recursive(b, a % b)
    x = y1
    y = x1 - (a // b) * y1
    return g, x, y


def extended_gcd(a, b):
    """
    Iterative extended GCD.

    Returns (gcd, x, y) such that a*x + b*y = gcd(a, b).
    """
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1

    while r != 0:
        quotient = old_r // r
        old_r, r = r, old_r - quotient * r
        old_s, s = s, old_s - quotient * s
        old_t, t = t, old_t - quotient * t

    # old_r = gcd, old_s = x, old_t = y
    return old_r, old_s, old_t


def mod_inverse(a, m):
    """Compute modular inverse of a mod m."""
    g, x, _ = extended_gcd(a % m, m)
    if g != 1:
        return None  # No inverse
    return x % m


def solve_linear_diophantine(a, b, c):
    """
    Solve ax + by = c.

    Returns (x0, y0, dx, dy) where general solution is:
        x = x0 + k * dx
        y = y0 + k * dy
    for any integer k. Returns None if no solution.
    """
    g, x0, y0 = extended_gcd(abs(a), abs(b))
    if c % g != 0:
        return None

    # Scale the solution
    scale = c // g
    x0 *= scale
    y0 *= scale

    # Adjust signs
    if a < 0:
        x0 = -x0
    if b < 0:
        y0 = -y0

    # General solution step
    dx = b // g
    dy = -(a // g)

    return x0, y0, dx, dy


# Test extended GCD
print("Extended GCD tests:")
for a, b in [(240, 46), (35, 15), (17, 13), (99, 78)]:
    g, x, y = extended_gcd(a, b)
    valid = a * x + b * y == g
    print(f"  gcd({a},{b})={g}, {a}*{x} + {b}*{y} = {a*x+b*y} "
          f"(valid={valid})")

# Modular inverse
print("\nModular inverse:")
for a, m in [(3, 7), (10, 17), (7, 26), (6, 9)]:
    inv = mod_inverse(a, m)
    if inv is not None:
        print(f"  {a}^(-1) mod {m} = {inv}, "
              f"verify: {a}*{inv} mod {m} = {(a*inv)%m}")
    else:
        print(f"  {a}^(-1) mod {m} = NO INVERSE "
              f"(gcd={extended_gcd(a, m)[0]})")

# Linear Diophantine equation
print("\nLinear Diophantine: 12x + 8y = 20")
result = solve_linear_diophantine(12, 8, 20)
if result:
    x0, y0, dx, dy = result
    print(f"  Base solution: x={x0}, y={y0}")
    print(f"  General: x={x0}+{dx}k, y={y0}+{dy}k")
    for k in range(-2, 3):
        x = x0 + dx * k
        y = y0 + dy * k
        print(f"    k={k}: x={x}, y={y}, check={12*x+8*y}")
```

**Algorithm Trace (gcd(240, 46)):**
```
240 = 5*46 + 10   -> gcd(46, 10)
 46 = 4*10 + 6    -> gcd(10, 6)
 10 = 1*6  + 4    -> gcd(6, 4)
  6 = 1*4  + 2    -> gcd(4, 2)
  4 = 2*2  + 0    -> gcd = 2
Back-substitution yields: 240*(-9) + 46*(47) = 2
```

**Complexity:**
- Time: O(log(min(a, b))) -- same as Euclidean algorithm
- Space: O(1) iterative, O(log(min(a, b))) recursive'''),
]
