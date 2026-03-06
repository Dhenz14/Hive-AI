PAIRS = [
    ("thinking/algorithms", r'''Implement Tower of Hanoi variants: (1) standard 3-peg, (2) Frame-Stewart algorithm for 4 pegs, (3) constrained version where moves can only go to adjacent pegs. Show move counts and optimality proofs.''', r'''<think>
Three Tower of Hanoi variants:

1. Standard 3-peg: T(n) = 2^n - 1 moves. Recursive: move n-1 disks to auxiliary, move largest to target, move n-1 from auxiliary to target.

2. Frame-Stewart for 4 pegs: partition n disks into groups. Move top k disks to a spare peg using 4 pegs, move remaining n-k disks to target using 3 pegs (2^(n-k)-1 moves), move k disks from spare to target using 4 pegs. Minimize over k: T4(n) = min over k of (2*T4(k) + 2^(n-k) - 1). This is conjectured optimal (proven only in 2014 by Bousch).

3. Adjacent-only moves: disks can only move to adjacent pegs (peg 0 <-> peg 1 <-> peg 2). This requires more moves: T_adj(n) = 3^n - 1 for moving from peg 0 to peg 2.

For the 4-peg variant, I need to compute the optimal k for each n. The Frame-Stewart numbers grow much slower than 2^n.

Let me implement all three with move generation and counting.
</think>

## Tower of Hanoi Variants

### Implementation

```python
def hanoi_3peg(n, source='A', target='C', auxiliary='B', moves=None):
    """Standard 3-peg Tower of Hanoi. T(n) = 2^n - 1."""
    if moves is None:
        moves = []
    if n == 0:
        return moves
    hanoi_3peg(n - 1, source, auxiliary, target, moves)
    moves.append((source, target, n))
    hanoi_3peg(n - 1, auxiliary, target, source, moves)
    return moves


def hanoi_3peg_count(n):
    """Count moves for 3-peg Hanoi: 2^n - 1."""
    return (1 << n) - 1


def frame_stewart_count(n):
    """Frame-Stewart optimal move count for 4-peg Hanoi.
    T4(n) = min over k of (2*T4(k) + 2^(n-k) - 1)."""
    if n <= 1:
        return n

    # DP table
    t4 = [0] * (n + 1)
    t4[1] = 1

    for i in range(2, n + 1):
        t4[i] = float('inf')
        for k in range(1, i):
            cost = 2 * t4[k] + (1 << (i - k)) - 1
            t4[i] = min(t4[i], cost)

    return t4[n]


def hanoi_4peg(n, source, target, aux1, aux2, moves=None):
    """4-peg Tower of Hanoi using Frame-Stewart algorithm."""
    if moves is None:
        moves = []
    if n == 0:
        return moves
    if n == 1:
        moves.append((source, target, 1))
        return moves

    # Find optimal k
    best_k = 1
    best_cost = float('inf')
    t4 = [0] * (n + 1)
    t4[1] = 1
    for i in range(2, n + 1):
        t4[i] = float('inf')
        for k in range(1, i):
            cost = 2 * t4[k] + (1 << (i - k)) - 1
            if cost < t4[i]:
                t4[i] = cost
    for k in range(1, n):
        cost = 2 * t4[k] + (1 << (n - k)) - 1
        if cost < best_cost:
            best_cost = cost
            best_k = k

    # Move top k disks to aux1 using 4 pegs
    hanoi_4peg(best_k, source, aux1, aux2, target, moves)
    # Move bottom n-k disks to target using 3 pegs (only source, target, aux2)
    hanoi_3peg(n - best_k, source, target, aux2, moves)
    # Move k disks from aux1 to target using 4 pegs
    hanoi_4peg(best_k, aux1, target, source, aux2, moves)

    return moves


def hanoi_adjacent_count(n):
    """Adjacent-only moves (0<->1<->2): T(n) = 3^n - 1 to go 0->2."""
    return 3**n - 1


def hanoi_adjacent(n, source=0, target=2, moves=None):
    """Adjacent-peg-only Hanoi. Pegs 0, 1, 2; only adjacent moves."""
    if moves is None:
        moves = []
    if n == 0:
        return moves
    middle = 3 - source - target  # the peg between source and target

    if abs(source - target) == 1:
        # Adjacent pegs: move n-1 to the other side, move largest, move n-1 back
        other = 3 - source - target
        hanoi_adjacent(n - 1, source, other, moves)
        moves.append((source, target, n))
        hanoi_adjacent(n - 1, other, target, moves)
    else:
        # Non-adjacent (0 to 2 or 2 to 0): must go through middle
        hanoi_adjacent(n - 1, source, target, moves)
        moves.append((source, middle, n))
        hanoi_adjacent(n - 1, target, source, moves)
        moves.append((middle, target, n))
        hanoi_adjacent(n - 1, source, target, moves)

    return moves


# Demo
print("=== Tower of Hanoi Variants ===\n")

# Move counts comparison
print(f"{'n':>3} {'3-peg':>10} {'4-peg (FS)':>12} {'Adjacent':>12}")
print("-" * 40)
for n in range(1, 16):
    t3 = hanoi_3peg_count(n)
    t4 = frame_stewart_count(n)
    ta = hanoi_adjacent_count(n) if n <= 10 else "..."
    print(f"{n:>3} {t3:>10} {t4:>12} {str(ta):>12}")

# Show moves for small n
print(f"\n--- 3-peg, n=3 ({hanoi_3peg_count(3)} moves) ---")
moves_3 = hanoi_3peg(3)
for src, dst, disk in moves_3:
    print(f"  Move disk {disk}: {src} -> {dst}")

print(f"\n--- 4-peg, n=4 ({frame_stewart_count(4)} moves) ---")
moves_4 = hanoi_4peg(4, 'A', 'D', 'B', 'C')
for src, dst, disk in moves_4:
    print(f"  Move disk {disk}: {src} -> {dst}")

print(f"\n--- Adjacent-only, n=2 ({hanoi_adjacent_count(2)} moves) ---")
moves_a = hanoi_adjacent(2, 0, 2)
for src, dst, disk in moves_a:
    print(f"  Move disk {disk}: peg {src} -> peg {dst}")

print(f"\n=== Growth Rates ===")
print(f"  3-peg: 2^n - 1 (exponential)")
print(f"  4-peg: ~2^(2*sqrt(n)) (sub-exponential)")
print(f"  Adjacent: 3^n - 1 (exponential, faster than 3-peg)")
```

### Move Count Formulas
| Variant | Moves | Growth |
|---------|-------|--------|
| 3-peg | 2^n - 1 | Exponential |
| 4-peg (Frame-Stewart) | ~2^(2*sqrt(n)) | Sub-exponential |
| Adjacent-only | 3^n - 1 | Exponential |'''),

    ("thinking/algorithms", r'''Implement a recursive descent parser for arithmetic expressions. Support +, -, *, /, parentheses, and operator precedence. Show the grammar and parse tree construction.''', r'''<think>
Recursive descent parsing for arithmetic expressions. The grammar (in order of increasing precedence):

expr     -> term (('+' | '-') term)*
term     -> factor (('*' | '/') factor)*
factor   -> NUMBER | '(' expr ')' | '-' factor (unary minus)

Each non-terminal becomes a function. The parser consumes tokens left-to-right, building an AST or directly evaluating.

I will implement:
1. A tokenizer (lexer) that produces tokens: NUMBER, PLUS, MINUS, STAR, SLASH, LPAREN, RPAREN
2. A parser that follows the grammar
3. AST construction
4. Evaluation

This handles operator precedence naturally: multiplication/division bind tighter because they are parsed at a deeper level of the grammar.
</think>

## Recursive Descent Parser for Arithmetic Expressions

### Implementation

```python
class Token:
    def __init__(self, type, value):
        self.type = type
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


def tokenize(expr):
    """Convert expression string to token list."""
    tokens = []
    i = 0
    while i < len(expr):
        if expr[i].isspace():
            i += 1
        elif expr[i].isdigit() or (expr[i] == '.' and i+1 < len(expr) and expr[i+1].isdigit()):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            tokens.append(Token('NUMBER', float(expr[i:j])))
            i = j
        elif expr[i] == '+':
            tokens.append(Token('PLUS', '+'))
            i += 1
        elif expr[i] == '-':
            tokens.append(Token('MINUS', '-'))
            i += 1
        elif expr[i] == '*':
            tokens.append(Token('STAR', '*'))
            i += 1
        elif expr[i] == '/':
            tokens.append(Token('SLASH', '/'))
            i += 1
        elif expr[i] == '(':
            tokens.append(Token('LPAREN', '('))
            i += 1
        elif expr[i] == ')':
            tokens.append(Token('RPAREN', ')'))
            i += 1
        else:
            raise ValueError(f"Unexpected character: {expr[i]}")

    tokens.append(Token('EOF', None))
    return tokens


class Parser:
    """Recursive descent parser for arithmetic expressions.

    Grammar:
        expr   -> term (('+' | '-') term)*
        term   -> factor (('*' | '/') factor)*
        factor -> NUMBER | '(' expr ')' | '-' factor
    """

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def consume(self, expected_type=None):
        token = self.tokens[self.pos]
        if expected_type and token.type != expected_type:
            raise SyntaxError(
                f"Expected {expected_type}, got {token.type} at position {self.pos}")
        self.pos += 1
        return token

    def parse(self):
        """Parse and return AST."""
        result = self.expr()
        self.consume('EOF')
        return result

    def expr(self):
        """expr -> term (('+' | '-') term)*"""
        node = self.term()
        while self.peek().type in ('PLUS', 'MINUS'):
            op = self.consume()
            right = self.term()
            node = ('binop', op.value, node, right)
        return node

    def term(self):
        """term -> factor (('*' | '/') factor)*"""
        node = self.factor()
        while self.peek().type in ('STAR', 'SLASH'):
            op = self.consume()
            right = self.factor()
            node = ('binop', op.value, node, right)
        return node

    def factor(self):
        """factor -> NUMBER | '(' expr ')' | '-' factor"""
        token = self.peek()
        if token.type == 'NUMBER':
            self.consume()
            return ('number', token.value)
        elif token.type == 'LPAREN':
            self.consume('LPAREN')
            node = self.expr()
            self.consume('RPAREN')
            return node
        elif token.type == 'MINUS':
            self.consume()
            operand = self.factor()
            return ('unary', '-', operand)
        else:
            raise SyntaxError(f"Unexpected token: {token}")


def evaluate(ast):
    """Evaluate an AST node."""
    if ast[0] == 'number':
        return ast[1]
    elif ast[0] == 'unary':
        return -evaluate(ast[2])
    elif ast[0] == 'binop':
        op = ast[1]
        left = evaluate(ast[2])
        right = evaluate(ast[3])
        if op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right
    raise ValueError(f"Unknown AST node: {ast[0]}")


def ast_to_string(ast, depth=0):
    """Pretty-print AST."""
    indent = "  " * depth
    if ast[0] == 'number':
        return f"{indent}{ast[1]}"
    elif ast[0] == 'unary':
        return f"{indent}(-)\n{ast_to_string(ast[2], depth+1)}"
    elif ast[0] == 'binop':
        return (f"{indent}({ast[1]})\n"
                f"{ast_to_string(ast[2], depth+1)}\n"
                f"{ast_to_string(ast[3], depth+1)}")


def calc(expr):
    """Parse and evaluate expression."""
    tokens = tokenize(expr)
    parser = Parser(tokens)
    ast = parser.parse()
    return evaluate(ast), ast


# Demo
print("=== Recursive Descent Parser ===\n")

expressions = [
    "2 + 3",
    "2 + 3 * 4",
    "(2 + 3) * 4",
    "10 - 2 * 3 + 4",
    "2 * (3 + 4) / (1 + 1)",
    "-5 + 3",
    "((1 + 2) * (3 + 4))",
]

for expr in expressions:
    result, ast = calc(expr)
    expected = eval(expr)  # verify with Python's eval
    status = "OK" if abs(result - expected) < 1e-9 else "FAIL"
    print(f"  {expr:30s} = {result:8.2f} [{status}]")

# Show AST for one expression
print(f"\nAST for '2 + 3 * 4':")
_, ast = calc("2 + 3 * 4")
print(ast_to_string(ast))

print(f"\nAST for '(2 + 3) * 4':")
_, ast = calc("(2 + 3) * 4")
print(ast_to_string(ast))
```

### Grammar (Precedence via Nesting)
```
expr   -> term (('+' | '-') term)*     # lowest precedence
term   -> factor (('*' | '/') factor)* # higher precedence
factor -> NUMBER | '(' expr ')' | '-' factor  # highest
```

### Complexity
- **Tokenization**: O(n) where n = expression length
- **Parsing**: O(n) -- each token consumed exactly once
- **Evaluation**: O(nodes in AST) = O(n)'''),

    ("thinking/algorithms", r'''Implement a complete expression evaluator that handles variables, function calls (sin, cos, sqrt), and operator precedence. Support assignment and multi-line evaluation.''', r'''<think>
Extending the recursive descent parser to support:
1. Variables (x = 5, then use x in expressions)
2. Built-in functions (sin, cos, sqrt, abs, pow)
3. Assignment operator (=)
4. Multi-line evaluation

The grammar extends:
statement -> assignment | expr
assignment -> IDENTIFIER '=' expr
expr -> term (('+' | '-') term)*
term -> factor (('*' | '/') factor)*
factor -> power ('^' power)*  (right-associative exponentiation)
power -> unary
unary -> '-' unary | atom
atom -> NUMBER | IDENTIFIER | IDENTIFIER '(' args ')' | '(' expr ')'
args -> expr (',' expr)*

I need to extend the tokenizer to handle identifiers (variable names and function names).

For the environment, I will use a dict mapping variable names to values.
</think>

## Expression Evaluator with Variables and Functions

### Implementation

```python
import math


def tokenize_extended(expr):
    """Tokenize with support for identifiers and commas."""
    tokens = []
    i = 0
    while i < len(expr):
        if expr[i].isspace():
            i += 1
        elif expr[i].isdigit() or (expr[i] == '.' and i+1 < len(expr)):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            tokens.append(('NUMBER', float(expr[i:j])))
            i = j
        elif expr[i].isalpha() or expr[i] == '_':
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            tokens.append(('IDENT', expr[i:j]))
            i = j
        elif expr[i] in '+-*/^=(),':
            token_map = {'+': 'PLUS', '-': 'MINUS', '*': 'STAR',
                         '/': 'SLASH', '^': 'CARET', '=': 'EQUALS',
                         '(': 'LPAREN', ')': 'RPAREN', ',': 'COMMA'}
            tokens.append((token_map[expr[i]], expr[i]))
            i += 1
        else:
            raise ValueError(f"Unexpected: '{expr[i]}'")
    tokens.append(('EOF', None))
    return tokens


class Evaluator:
    """Expression evaluator with variables and functions."""

    BUILTINS = {
        'sin': (math.sin, 1),
        'cos': (math.cos, 1),
        'tan': (math.tan, 1),
        'sqrt': (math.sqrt, 1),
        'abs': (abs, 1),
        'log': (math.log, 1),
        'exp': (math.exp, 1),
        'pow': (math.pow, 2),
        'min': (min, 2),
        'max': (max, 2),
        'pi': (math.pi, 0),
        'e': (math.e, 0),
    }

    def __init__(self):
        self.env = {}
        # Add constants
        self.env['pi'] = math.pi
        self.env['e'] = math.e

    def evaluate(self, expr):
        """Evaluate an expression string."""
        self.tokens = tokenize_extended(expr)
        self.pos = 0
        result = self.statement()
        self.expect('EOF')
        return result

    def peek(self):
        return self.tokens[self.pos]

    def consume(self):
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, type):
        t = self.consume()
        if t[0] != type:
            raise SyntaxError(f"Expected {type}, got {t[0]}")
        return t

    def statement(self):
        """statement -> IDENT '=' expr | expr"""
        # Look ahead for assignment
        if self.peek()[0] == 'IDENT' and self.pos + 1 < len(self.tokens):
            if self.tokens[self.pos + 1][0] == 'EQUALS':
                name = self.consume()[1]
                self.consume()  # '='
                value = self.expr()
                self.env[name] = value
                return value
        return self.expr()

    def expr(self):
        """expr -> term (('+' | '-') term)*"""
        left = self.term()
        while self.peek()[0] in ('PLUS', 'MINUS'):
            op = self.consume()[1]
            right = self.term()
            left = left + right if op == '+' else left - right
        return left

    def term(self):
        """term -> power (('*' | '/') power)*"""
        left = self.power()
        while self.peek()[0] in ('STAR', 'SLASH'):
            op = self.consume()[1]
            right = self.power()
            left = left * right if op == '*' else left / right
        return left

    def power(self):
        """power -> unary ('^' power)  (right-associative)"""
        base = self.unary()
        if self.peek()[0] == 'CARET':
            self.consume()
            exp = self.power()  # right-recursive for right-associativity
            return base ** exp
        return base

    def unary(self):
        """unary -> '-' unary | atom"""
        if self.peek()[0] == 'MINUS':
            self.consume()
            return -self.unary()
        return self.atom()

    def atom(self):
        """atom -> NUMBER | IDENT | IDENT '(' args ')' | '(' expr ')'"""
        t = self.peek()

        if t[0] == 'NUMBER':
            self.consume()
            return t[1]

        if t[0] == 'IDENT':
            name = self.consume()[1]
            if self.peek()[0] == 'LPAREN':
                # Function call
                self.consume()  # '('
                args = []
                if self.peek()[0] != 'RPAREN':
                    args.append(self.expr())
                    while self.peek()[0] == 'COMMA':
                        self.consume()
                        args.append(self.expr())
                self.expect('RPAREN')
                if name in self.BUILTINS:
                    func, arity = self.BUILTINS[name]
                    if callable(func):
                        return func(*args)
                raise NameError(f"Unknown function: {name}")
            # Variable
            if name in self.env:
                return self.env[name]
            raise NameError(f"Undefined variable: {name}")

        if t[0] == 'LPAREN':
            self.consume()
            result = self.expr()
            self.expect('RPAREN')
            return result

        raise SyntaxError(f"Unexpected token: {t}")


# Demo
print("=== Expression Evaluator ===\n")
ev = Evaluator()

lines = [
    "2 + 3 * 4",
    "x = 10",
    "y = 20",
    "x + y",
    "x * y - 5",
    "sqrt(x^2 + y^2)",
    "sin(pi / 6)",
    "cos(0)",
    "r = 5",
    "area = pi * r^2",
    "area",
    "max(3, 7) + min(2, 5)",
    "2^3^2",          # right-assoc: 2^(3^2) = 2^9 = 512
    "log(e^3)",
    "-abs(-42)",
]

for line in lines:
    try:
        result = ev.evaluate(line)
        print(f"  {line:30s} = {result:.6f}")
    except Exception as ex:
        print(f"  {line:30s} ERROR: {ex}")

print(f"\nVariables: { {k: round(v, 4) for k, v in ev.env.items() if k not in ('pi', 'e')} }")
```

### Supported Features
- **Operators**: +, -, *, /, ^ (right-associative)
- **Functions**: sin, cos, tan, sqrt, abs, log, exp, pow, min, max
- **Constants**: pi, e
- **Variables**: assignment with =
- **Parentheses**: arbitrary nesting
- **Unary minus**: -x, --x, etc.'''),

    ("thinking/algorithms", r'''Implement power set generation with pruning for constraint satisfaction. Given a set of items with weights and values, generate all subsets satisfying a weight constraint while maximizing value. Use branch-and-bound pruning.''', r'''<think>
Power set generation with branch and bound for the 0/1 knapsack problem. Instead of generating all 2^n subsets, prune branches that cannot improve on the current best solution.

Branch and bound approach:
1. Sort items by value/weight ratio (descending) for better pruning
2. At each step, decide to include or exclude the current item
3. Compute an upper bound for the remaining items (fractional knapsack relaxation)
4. If the upper bound + current value <= best known value, prune this branch

The upper bound: solve the fractional knapsack with remaining items and remaining capacity. This gives an optimistic estimate that can never be exceeded.

This turns exponential search into something much faster in practice, though worst case is still O(2^n).

I will implement:
1. The recursive branch-and-bound solver
2. Upper bound computation
3. Statistics on pruning effectiveness
</think>

## Power Set with Branch-and-Bound Pruning

### Implementation

```python
def knapsack_branch_and_bound(items, capacity):
    """Solve 0/1 knapsack using branch-and-bound on power set.

    Args:
        items: list of (value, weight) tuples
        capacity: maximum weight

    Returns:
        (max_value, selected_items, stats)
    """
    n = len(items)
    # Sort by value/weight ratio (descending) for better bounds
    indexed = sorted(enumerate(items), key=lambda x: -x[1][0] / max(x[1][1], 0.001))

    best_value = [0]
    best_selection = [[]]
    stats = {'nodes': 0, 'pruned': 0, 'leaves': 0}

    def upper_bound(idx, current_value, remaining_capacity):
        """Fractional knapsack upper bound on remaining items."""
        bound = current_value
        cap = remaining_capacity
        for i in range(idx, n):
            orig_idx, (val, wt) = indexed[i]
            if wt <= cap:
                bound += val
                cap -= wt
            else:
                bound += val * (cap / wt)
                break
        return bound

    def solve(idx, current_value, current_weight, selected):
        stats['nodes'] += 1

        # Base case: all items considered
        if idx == n:
            stats['leaves'] += 1
            if current_value > best_value[0]:
                best_value[0] = current_value
                best_selection[0] = list(selected)
            return

        # Check upper bound -- can we improve?
        remaining_cap = capacity - current_weight
        bound = upper_bound(idx, current_value, remaining_cap)
        if bound <= best_value[0]:
            stats['pruned'] += 1
            return

        orig_idx, (val, wt) = indexed[idx]

        # Branch 1: Include current item (if it fits)
        if current_weight + wt <= capacity:
            selected.append(orig_idx)
            solve(idx + 1, current_value + val, current_weight + wt, selected)
            selected.pop()

        # Branch 2: Exclude current item
        solve(idx + 1, current_value, current_weight, selected)

    solve(0, 0, 0, [])

    return best_value[0], sorted(best_selection[0]), stats


def knapsack_brute_force(items, capacity):
    """Brute force: enumerate all 2^n subsets."""
    n = len(items)
    best_value = 0
    best_selection = []
    total_subsets = 0

    for mask in range(1 << n):
        total_subsets += 1
        weight = 0
        value = 0
        selected = []
        for i in range(n):
            if mask & (1 << i):
                v, w = items[i]
                weight += w
                value += v
                selected.append(i)
        if weight <= capacity and value > best_value:
            best_value = value
            best_selection = selected

    return best_value, best_selection, total_subsets


# Demo
print("=== Branch-and-Bound Knapsack ===\n")

items = [
    (60, 10),   # item 0: value=60, weight=10
    (100, 20),  # item 1
    (120, 30),  # item 2
    (40, 15),   # item 3
    (50, 25),   # item 4
    (80, 12),   # item 5
    (70, 18),   # item 6
    (90, 22),   # item 7
]
capacity = 60

print(f"Items (value, weight): {items}")
print(f"Capacity: {capacity}")

bb_val, bb_sel, bb_stats = knapsack_branch_and_bound(items, capacity)
bf_val, bf_sel, bf_subsets = knapsack_brute_force(items, capacity)

print(f"\nBranch-and-Bound:")
print(f"  Max value: {bb_val}")
print(f"  Selected: {bb_sel}")
print(f"  Nodes explored: {bb_stats['nodes']}")
print(f"  Pruned branches: {bb_stats['pruned']}")
print(f"  Leaf nodes: {bb_stats['leaves']}")

print(f"\nBrute Force:")
print(f"  Max value: {bf_val}")
print(f"  Selected: {bf_sel}")
print(f"  Subsets checked: {bf_subsets} (2^{len(items)} = {1 << len(items)})")

print(f"\nPruning effectiveness:")
print(f"  B&B nodes: {bb_stats['nodes']} vs brute force: {bf_subsets}")
print(f"  Reduction: {100*(1 - bb_stats['nodes']/bf_subsets):.1f}%")
print(f"  Match: {'OK' if bb_val == bf_val else 'FAIL'}")

# Larger test
import random
random.seed(42)
large_items = [(random.randint(10, 100), random.randint(5, 30)) for _ in range(20)]
large_cap = 100

bb_val2, bb_sel2, bb_stats2 = knapsack_branch_and_bound(large_items, large_cap)
print(f"\nLarge instance (n=20, 2^20 = {1<<20}):")
print(f"  B&B nodes: {bb_stats2['nodes']}")
print(f"  Pruned: {bb_stats2['pruned']}")
print(f"  Max value: {bb_val2}")
```

### Complexity
- **Worst case**: O(2^n) (no pruning helps)
- **Best case**: O(n) (early pruning kills most branches)
- **Typical**: much better than 2^n due to upper bound pruning
- **Upper bound computation**: O(n) per node (fractional knapsack)'''),

    ("thinking/algorithms", r'''Implement the N-Queens problem with bitwise optimization. Place n queens on an n x n board so no two attack each other. Use bit manipulation for O(1) conflict checking per position.''', r'''<think>
N-Queens with bitwise optimization: instead of using arrays to track which columns and diagonals are attacked, use bitmasks. This gives O(1) conflict checking per position.

Three bitmasks:
1. cols: bits set for occupied columns
2. diag1: bits set for occupied "\" diagonals (row + col)
3. diag2: bits set for occupied "/" diagonals (row - col + n - 1)

For each row, the available positions are: ~(cols | diag1 | diag2) & ((1 << n) - 1).

To iterate over available positions efficiently:
- available = ~(cols | diag1 | diag2) & mask
- While available != 0: pick lowest set bit with (available & -available), then clear it

When moving to the next row:
- cols |= bit (column is now occupied)
- diag1 shifts: (diag1 | bit) << 1 (diagonal shifts right for next row)
  Wait, for "\" diagonals: row + col is constant. When we go to row+1, the diagonal from (row, col) affects column col-1 in the next row. So diag1 should shift left.
  Actually: for the "\" diagonal, a queen at column c in the current row attacks column c-1 in the next row. So (diag1 | bit) >> 1.
  For the "/" diagonal: attacks column c+1 in the next row. So (diag2 | bit) << 1.

Let me verify: queen at (row, col). It attacks:
- Same column: col (all rows)
- "\" diagonal: (row+1, col-1), (row+2, col-2), ... so shift right
- "/" diagonal: (row+1, col+1), (row+2, col+2), ... so shift left

So for next row: diag1 = (diag1 | bit) >> 1, diag2 = (diag2 | bit) << 1.

This is the standard N-Queens with bitmask optimization.
</think>

## N-Queens with Bitwise Optimization

### Implementation

```python
def n_queens_bitwise(n):
    """Solve N-Queens using bit manipulation.
    Returns list of all solutions (each as list of column positions)."""
    solutions = []
    mask = (1 << n) - 1  # all n bits set

    def solve(row, cols, diag_left, diag_right, queens):
        if row == n:
            solutions.append(list(queens))
            return

        # Available positions: not attacked by any existing queen
        available = mask & ~(cols | diag_left | diag_right)

        while available:
            # Pick the lowest set bit
            bit = available & (-available)
            available ^= bit  # clear that bit

            # Find column number from bit
            col = 0
            temp = bit
            while temp > 1:
                temp >>= 1
                col += 1

            queens.append(col)
            solve(
                row + 1,
                cols | bit,
                (diag_left | bit) >> 1,   # shift right for "\" diag
                (diag_right | bit) << 1,  # shift left for "/" diag
                queens
            )
            queens.pop()

    solve(0, 0, 0, 0, [])
    return solutions


def n_queens_count_bitwise(n):
    """Count N-Queens solutions using bit manipulation."""
    mask = (1 << n) - 1
    count = [0]

    def solve(row, cols, dl, dr):
        if row == n:
            count[0] += 1
            return
        available = mask & ~(cols | dl | dr)
        while available:
            bit = available & (-available)
            available ^= bit
            solve(row + 1, cols | bit, (dl | bit) >> 1, (dr | bit) << 1)

    solve(0, 0, 0, 0)
    return count[0]


def print_board(n, queens):
    """Print a single board configuration."""
    for row in range(n):
        line = ""
        for col in range(n):
            if queens[row] == col:
                line += "Q "
            else:
                line += ". "
        print(f"  {line}")


# Demo
print("=== N-Queens with Bitwise Optimization ===\n")

# Solution counts
print(f"{'n':>3} {'Solutions':>10}")
import time
for n in range(1, 14):
    start = time.time()
    count = n_queens_count_bitwise(n)
    elapsed = time.time() - start
    print(f"{n:>3} {count:>10} ({elapsed:.4f}s)")

# Show first solution for n=8
solutions_8 = n_queens_bitwise(8)
print(f"\nN=8: {len(solutions_8)} solutions")
print(f"First solution: {solutions_8[0]}")
print_board(8, solutions_8[0])

# Verify a solution
def verify_queens(n, queens):
    for i in range(n):
        for j in range(i + 1, n):
            if queens[i] == queens[j]:
                return False  # same column
            if abs(queens[i] - queens[j]) == abs(i - j):
                return False  # same diagonal
    return True

all_valid = all(verify_queens(8, sol) for sol in solutions_8)
print(f"\nAll 8-queens solutions valid: {all_valid}")

print(f"\n=== Why Bitwise is Fast ===")
print(f"  Standard: O(n) to check conflicts per position")
print(f"  Bitwise: O(1) per position using bit ops")
print(f"  Available = ~(cols | diag_L | diag_R) & mask")
print(f"  Iterate bits: bit = available & (-available)")
```

### The Bit Trick
```
cols:       bits for occupied columns
diag_left:  bits for "\" diagonals (shifts right each row)
diag_right: bits for "/" diagonals (shifts left each row)
available = ~(cols | diag_left | diag_right) & mask

For each available position:
  bit = available & (-available)  // lowest set bit
  available ^= bit               // clear it
```

### Known Solution Counts
| n | Solutions |
|---|-----------|
| 1 | 1 |
| 4 | 2 |
| 8 | 92 |
| 12 | 14200 |
| 14 | 365596 |

### Complexity
- **Time**: O(n!) worst case, much better with pruning
- **Space**: O(n) for recursion stack
- **Bitwise speedup**: ~3-5x over array-based checking'''),
]
