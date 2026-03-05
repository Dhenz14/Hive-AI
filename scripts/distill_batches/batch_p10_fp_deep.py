PAIRS = [
    # --- 1. Monads and Functors ---
    (
        "fp/monads-functors-laws-maybe-io-transformers",
        "Explain monads and functors in depth including functor laws, monad laws of left identity "
        "right identity and associativity, Maybe/Option monad, IO monad, and monad transformers with "
        "complete Python implementations featuring chaining and compositional error handling",
        r"""# Monads and Functors: Laws, Implementations, and Compositional Patterns

## Why Functor and Monad Laws Matter

Understanding functors and monads is not about abstract mathematics for its own sake -- it is about writing **composable, predictable software**. The laws that govern these structures are guarantees that your abstractions behave consistently. When you violate a functor law, refactoring breaks. When you violate a monad law, composition produces unexpected results. **Therefore**, learning the laws is not optional -- it is the difference between a robust abstraction and a leaky one.

A **functor** is anything that can be mapped over. In category theory terms, a functor is a mapping between categories that preserves structure. In programming terms, it is a type that implements `map` (or `fmap`) in a law-abiding way.

A **monad** extends a functor with `bind` (also called `flatMap`, `>>=`, `and_then`, or `chain`), which lets you sequence computations where each step depends on the previous result and may itself produce a wrapped value. **Because** `bind` flattens the nesting automatically, you avoid the `Maybe(Maybe(Maybe(x)))` problem that arises if you only have `map`.

**Common mistake**: treating any class with a `map` method as a proper functor. A true functor must satisfy two laws, and violating them means your "functor" will surprise users during refactoring.

### The Two Functor Laws

1. **Identity**: `f.map(lambda x: x)` must equal `f`. Mapping the identity function over a functor must return the functor unchanged.
2. **Composition**: `f.map(g).map(h)` must equal `f.map(lambda x: h(g(x)))`. Mapping two functions sequentially must produce the same result as mapping their composition.

These laws guarantee that `map` is a **structure-preserving** operation. If identity fails, your `map` has hidden side effects. If composition fails, you cannot safely fuse or reorder map operations.

### The Three Monad Laws

1. **Left Identity**: `unit(a).bind(f)` must equal `f(a)`. Wrapping a value and immediately binding should be the same as just calling the function.
2. **Right Identity**: `m.bind(unit)` must equal `m`. Binding with the wrapping function should not change the monad.
3. **Associativity**: `m.bind(f).bind(g)` must equal `m.bind(lambda x: f(x).bind(g))`. The order of nesting binds should not matter.

**Best practice**: always verify your monad satisfies these three laws with unit tests. If associativity fails, monadic composition is unpredictable and pipelines will produce different results depending on how you parenthesize them.

## Implementing Maybe/Option Monad

The Maybe monad represents a computation that might produce no result. It replaces chains of `if x is not None` checks with clean, composable pipelines.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, Union

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


class Maybe(Generic[T]):
    # Base class for the Maybe/Option monad.
    # Wraps a value that may or may not exist.

    @staticmethod
    def of(value: T) -> Maybe[T]:
        # Unit/return: wraps a value in Just
        if value is None:
            return Nothing()
        return Just(value)

    def bind(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        # Monadic bind (>>=): chains computations that return Maybe
        if isinstance(self, Just):
            return f(self.value)
        return Nothing()

    def map(self, f: Callable[[T], U]) -> Maybe[U]:
        # Functor map: applies a pure function inside the context
        if isinstance(self, Just):
            return Just(f(self.value))
        return Nothing()

    def or_else(self, default: T) -> T:
        # Unwrap with a fallback for Nothing
        if isinstance(self, Just):
            return self.value
        return default

    def filter(self, predicate: Callable[[T], bool]) -> Maybe[T]:
        # Keep the value only if predicate passes
        if isinstance(self, Just) and predicate(self.value):
            return self
        return Nothing()

    def __repr__(self) -> str:
        if isinstance(self, Just):
            return f"Just({self.value!r})"
        return "Nothing()"


class Just(Maybe[T]):
    def __init__(self, value: T) -> None:
        self.value = value


class Nothing(Maybe):
    pass


# --- Verifying the Monad Laws ---
def test_maybe_laws():
    f = lambda x: Just(x * 2) if x > 0 else Nothing()
    g = lambda x: Just(x + 10)

    # Left Identity: unit(a).bind(f) == f(a)
    assert repr(Maybe.of(5).bind(f)) == repr(f(5))

    # Right Identity: m.bind(unit) == m
    m = Just(42)
    assert repr(m.bind(Maybe.of)) == repr(m)

    # Associativity: m.bind(f).bind(g) == m.bind(lambda x: f(x).bind(g))
    assert repr(m.bind(f).bind(g)) == repr(m.bind(lambda x: f(x).bind(g)))

test_maybe_laws()
```

## Implementing the Result Monad

The Result monad (also called Either) carries **error information** rather than just indicating absence. This is critical **because** in production code, knowing *why* something failed is just as important as knowing *that* it failed.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, Union

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


class Result(Generic[T, E]):
    # Result/Either monad: carries either a success value or an error.
    # Trade-off: more verbose than exceptions but makes error paths explicit
    # and composable, therefore easier to reason about.

    @staticmethod
    def ok(value: T) -> Result[T, E]:
        return Ok(value)

    @staticmethod
    def err(error: E) -> Result[T, E]:
        return Err(error)

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        # Monadic bind: short-circuits on Err
        if isinstance(self, Ok):
            return f(self.value)
        return self  # type: ignore

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        # Functor map: transforms success value, passes errors through
        if isinstance(self, Ok):
            return Ok(f(self.value))
        return self  # type: ignore

    def map_err(self, f: Callable[[E], E]) -> Result[T, E]:
        # Transform the error value while keeping successes unchanged
        if isinstance(self, Err):
            return Err(f(self.error))
        return self

    def unwrap_or(self, default: T) -> T:
        if isinstance(self, Ok):
            return self.value
        return default

    def __repr__(self) -> str:
        if isinstance(self, Ok):
            return f"Ok({self.value!r})"
        return f"Err({self.error!r})"


class Ok(Result[T, E]):
    def __init__(self, value: T) -> None:
        self.value = value


class Err(Result[T, E]):
    def __init__(self, error: E) -> None:
        self.error = error


# --- Railway-Oriented Pipeline ---
def parse_int(s: str) -> Result[int, str]:
    try:
        return Ok(int(s))
    except ValueError:
        return Err(f"Cannot parse '{s}' as integer")

def validate_positive(n: int) -> Result[int, str]:
    if n > 0:
        return Ok(n)
    return Err(f"Expected positive, got {n}")

def compute_sqrt(n: int) -> Result[float, str]:
    import math
    return Ok(math.sqrt(n))

# Clean pipeline -- errors short-circuit automatically
result = parse_int("49").bind(validate_positive).bind(compute_sqrt)
# result == Ok(7.0)

result_fail = parse_int("-3").bind(validate_positive).bind(compute_sqrt)
# result_fail == Err("Expected positive, got -3")
```

## The IO Monad: Taming Side Effects

The IO monad wraps side-effectful operations as **descriptions of effects** rather than executing them immediately. This is a **best practice** for separating pure logic from impure execution, making code testable and composable.

**Pitfall**: in Python, the IO monad is a discipline rather than a compiler-enforced boundary. You rely on convention to keep effects inside the IO wrapper.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable

A = TypeVar("A")
B = TypeVar("B")


class IO(Generic[A]):
    # The IO monad: wraps a side-effectful computation.
    # The effect is not executed until run() is called.
    # Therefore, IO values are referentially transparent descriptions.

    def __init__(self, effect: Callable[[], A]) -> None:
        self._effect = effect

    @staticmethod
    def pure(value: A) -> IO[A]:
        # Lift a pure value into IO (unit/return)
        return IO(lambda: value)

    def bind(self, f: Callable[[A], IO[B]]) -> IO[B]:
        # Monadic bind: sequence two IO actions
        # The second action depends on the result of the first
        def deferred():
            a = self._effect()
            return f(a)._effect()
        return IO(deferred)

    def map(self, f: Callable[[A], B]) -> IO[B]:
        # Functor map: transform the eventual result
        def deferred():
            return f(self._effect())
        return IO(deferred)

    def run(self) -> A:
        # Execute the described effect -- the only impure boundary
        return self._effect()


# --- Building composable IO programs ---
def read_line(prompt: str) -> IO[str]:
    return IO(lambda: input(prompt))

def print_line(msg: str) -> IO[None]:
    return IO(lambda: print(msg))

def get_file_contents(path: str) -> IO[str]:
    def _read():
        with open(path, "r") as f:
            return f.read()
    return IO(_read)

# Composing IO actions into a program description
# However, nothing executes until .run() is called
program = (
    read_line("Enter your name: ")
    .bind(lambda name: print_line(f"Hello, {name}!"))
)
# program.run()  # Only now does execution happen
```

## Monad Transformers: Stacking Contexts

A **common mistake** is trying to work with `IO[Maybe[T]]` or `Result[Maybe[T], E]` directly -- you end up with deeply nested `bind` and `map` calls. Monad transformers solve this by letting you **stack** monadic contexts into a single composable layer.

**However**, monad transformers add complexity. The **trade-off** is between the boilerplate of manual nesting versus the indirection of transformer stacks. In Python, keep transformer stacks shallow -- two or three layers maximum.

### MaybeT Transformer

The `MaybeT` transformer adds optional semantics to any outer monad. **Therefore**, `MaybeT[IO]` lets you write IO computations where any step can produce `Nothing`, and the pipeline short-circuits cleanly.

In Haskell this is standard library material. In Python, we build it manually but the principle is identical: lift operations from the inner monad, and short-circuit on `Nothing`.

## Summary and Key Takeaways

- **Functor laws** (identity and composition) guarantee that `map` is a safe, structure-preserving operation -- violating them makes refactoring unpredictable
- **Monad laws** (left identity, right identity, associativity) ensure that `bind` composes predictably regardless of how you group operations
- The **Maybe monad** eliminates nested `None` checks by short-circuiting on `Nothing` -- a **best practice** for option-chaining in Python
- The **Result monad** carries error context through pipelines, providing the **trade-off** of more explicit types in exchange for composable error handling
- The **IO monad** separates effect description from execution, **therefore** making side-effectful code testable by swapping interpreters
- **Monad transformers** stack contexts (e.g., `MaybeT[IO]`) but add indirection -- a **pitfall** is over-engineering with deep transformer stacks
- **Common mistake**: conflating `map` (functor) with `bind` (monad) -- `map` applies a pure function, `bind` applies a function that returns a wrapped value
- Always verify the three monad laws with tests -- **because** a law-violating monad will produce inconsistent behavior in composed pipelines"""
    ),
    # --- 2. Immutable Data Structures ---
    (
        "fp/immutable-persistent-data-structures-structural-sharing-hamt",
        "Explain immutable persistent data structures including structural sharing, Hash Array "
        "Mapped Tries (HAMTs), finger trees, and Okasaki's lazy evaluation patterns with Python "
        "implementations of a persistent vector and persistent hash map featuring path copying and "
        "efficient update operations",
        r"""# Immutable Persistent Data Structures: Structural Sharing and Efficient Updates

## The Problem: Mutability and Shared State

Mutable data structures are the root cause of an enormous class of bugs: race conditions, iterator invalidation, action-at-a-distance, and defensive copying overhead. **Because** immutable data structures never change after creation, they are inherently thread-safe, trivially cacheable, and support unlimited undo/redo by keeping references to previous versions.

**However**, naively copying an entire data structure on every "update" is prohibitively expensive -- O(n) time and space per operation. The breakthrough insight of **persistent data structures** is **structural sharing**: a new version reuses most of the old version's memory, copying only the nodes along the path from root to the modified element.

### Key Concepts

- **Persistence**: every version of the data structure is preserved after modification
- **Structural sharing**: new and old versions share unmodified subtrees
- **Path copying**: only the nodes on the path from root to the changed leaf are duplicated
- **HAMT (Hash Array Mapped Trie)**: the workhorse data structure behind Clojure's maps and Scala's immutable maps
- **Finger trees**: a general-purpose persistent data structure supporting O(1) amortized access to both ends

**Common mistake**: assuming immutable data structures are always slower than mutable ones. With structural sharing, updates are O(log n) -- typically log base 32, meaning a billion elements require only 6 levels. The constant factors are excellent **because** of CPU cache locality in wide branching nodes.

## Persistent Vector with Structural Sharing

The persistent vector (as popularized by Clojure) uses a **wide trie** with branching factor 32. Each internal node has up to 32 children, and leaves store up to 32 elements. **Therefore**, a vector with a billion elements has only 6 levels, making all operations effectively O(1) in practice.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Optional, List, Any
import copy

T = TypeVar("T")

BRANCH_FACTOR = 32
BITS = 5  # log2(32)
MASK = BRANCH_FACTOR - 1


class PersistentVector(Generic[T]):
    # A persistent vector using a 32-way trie with structural sharing.
    # Best practice: branching factor of 32 balances tree depth with
    # node copy cost, and fits nicely in CPU cache lines.

    def __init__(self) -> None:
        self._count: int = 0
        self._shift: int = BITS  # depth * BITS
        self._root: List[Any] = []
        self._tail: List[T] = []

    @staticmethod
    def empty() -> PersistentVector[T]:
        return PersistentVector()

    def __len__(self) -> int:
        return self._count

    def _tail_offset(self) -> int:
        if self._count < BRANCH_FACTOR:
            return 0
        return ((self._count - 1) >> BITS) << BITS

    def append(self, value: T) -> PersistentVector[T]:
        # Returns a NEW vector with value appended.
        # Trade-off: O(log32 n) time for immutability guarantees.
        result = PersistentVector.__new__(PersistentVector)
        result._count = self._count + 1

        # Tail has room -- just copy and extend tail
        if len(self._tail) < BRANCH_FACTOR:
            result._root = self._root  # Structural sharing: reuse root
            result._shift = self._shift
            result._tail = self._tail + [value]
            return result

        # Tail is full -- push tail into the trie
        new_tail_node = list(self._tail)
        result._tail = [value]

        # Tree needs to grow in height
        if (self._count >> BITS) > (1 << self._shift):
            new_root = [self._root, self._new_path(self._shift, new_tail_node)]
            result._shift = self._shift + BITS
            result._root = new_root
        else:
            result._root = self._push_tail(
                self._shift, self._root, new_tail_node
            )
            result._shift = self._shift
        return result

    def _push_tail(self, level: int, parent: List, tail_node: List) -> List:
        # Path copying: creates new nodes only along the insertion path
        new_parent = list(parent)  # Copy current node
        subidx = ((self._count - 1) >> level) & MASK

        if level == BITS:
            # Bottom level: insert the tail node
            if subidx < len(new_parent):
                new_parent[subidx] = tail_node
            else:
                new_parent.append(tail_node)
        else:
            if subidx < len(new_parent):
                child = new_parent[subidx]
                new_parent[subidx] = self._push_tail(
                    level - BITS, child, tail_node
                )
            else:
                new_parent.append(
                    self._new_path(level - BITS, tail_node)
                )
        return new_parent

    def _new_path(self, level: int, node: List) -> List:
        if level == 0:
            return node
        return [self._new_path(level - BITS, node)]

    def get(self, index: int) -> T:
        # O(log32 n) lookup -- effectively constant time
        if index < 0 or index >= self._count:
            raise IndexError(f"Index {index} out of range")

        # Check if index is in the tail
        if index >= self._tail_offset():
            return self._tail[index & MASK]

        # Walk down the trie
        node = self._root
        level = self._shift
        while level > 0:
            node = node[(index >> level) & MASK]
            level -= BITS
        return node[index & MASK]

    def set(self, index: int, value: T) -> PersistentVector[T]:
        # Returns a NEW vector with the value at index replaced.
        # Only copies nodes along the path -- O(log32 n)
        if index < 0 or index >= self._count:
            raise IndexError(f"Index {index} out of range")

        result = PersistentVector.__new__(PersistentVector)
        result._count = self._count
        result._shift = self._shift

        if index >= self._tail_offset():
            new_tail = list(self._tail)
            new_tail[index & MASK] = value
            result._tail = new_tail
            result._root = self._root  # Structural sharing
            return result

        result._tail = self._tail  # Structural sharing
        result._root = self._set_in_tree(
            self._shift, self._root, index, value
        )
        return result

    def _set_in_tree(self, level: int, node: List, index: int, value: T) -> List:
        new_node = list(node)  # Path copy
        if level == 0:
            new_node[index & MASK] = value
        else:
            subidx = (index >> level) & MASK
            new_node[subidx] = self._set_in_tree(
                level - BITS, node[subidx], index, value
            )
        return new_node


# --- Usage demonstrating persistence ---
v0 = PersistentVector.empty()
v1 = v0.append("a").append("b").append("c")
v2 = v1.set(1, "B")  # v1 is unchanged
# v1.get(1) == "b", v2.get(1) == "B"
# Both versions exist simultaneously -- therefore supporting undo/redo
```

## Persistent Hash Map (HAMT)

The **Hash Array Mapped Trie** is the persistent counterpart to a hash table. Instead of buckets, it uses a trie keyed on the bits of the hash value. Each level consumes 5 bits of the hash, giving 32-way branching.

**Pitfall**: implementing HAMTs correctly requires handling hash collisions. When two keys hash to identical 32-bit values, they must be stored in a collision node (a list of key-value pairs) at the leaf level.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Optional, Tuple, List

K = TypeVar("K")
V = TypeVar("V")


class HAMTNode(Generic[K, V]):
    # Internal node of a Hash Array Mapped Trie.
    # Uses a bitmap to track which of the 32 slots are populated,
    # therefore avoiding the memory cost of 32-element sparse arrays.

    def __init__(self) -> None:
        self.bitmap: int = 0
        self.children: List = []

    def _index(self, bit: int) -> int:
        # Population count of bits below the target bit
        # This is how HAMT achieves compact storage
        return bin(self.bitmap & (bit - 1)).count("1")

    def get(self, key: K, hash_val: int, shift: int) -> Optional[V]:
        bit = 1 << ((hash_val >> shift) & MASK)
        if not (self.bitmap & bit):
            return None
        idx = self._index(bit)
        child = self.children[idx]
        if isinstance(child, tuple):
            # Leaf node: (key, value) pair
            return child[1] if child[0] == key else None
        # Recurse into sub-trie
        return child.get(key, hash_val, shift + BITS)

    def insert(self, key: K, value: V, hash_val: int, shift: int) -> HAMTNode[K, V]:
        # Returns a NEW node with the key-value pair inserted.
        # Path copying ensures the original is unchanged.
        bit = 1 << ((hash_val >> shift) & MASK)
        idx = self._index(bit)

        new_node = HAMTNode()
        new_node.bitmap = self.bitmap
        new_node.children = list(self.children)  # Shallow copy

        if not (self.bitmap & bit):
            # Empty slot: insert new leaf
            new_node.bitmap |= bit
            new_node.children.insert(idx, (key, value))
        else:
            existing = self.children[idx]
            if isinstance(existing, tuple):
                if existing[0] == key:
                    # Update existing key
                    new_node.children[idx] = (key, value)
                else:
                    # Hash collision at this level: create sub-trie
                    sub = HAMTNode()
                    old_hash = hash(existing[0])
                    sub = sub.insert(existing[0], existing[1], old_hash, shift + BITS)
                    sub = sub.insert(key, value, hash_val, shift + BITS)
                    new_node.children[idx] = sub
            else:
                new_node.children[idx] = existing.insert(
                    key, value, hash_val, shift + BITS
                )
        return new_node


class PersistentHashMap(Generic[K, V]):
    # Persistent hash map using HAMT.
    # Because of structural sharing, creating a new version with one
    # key changed only copies O(log32 n) nodes.

    def __init__(self, root: Optional[HAMTNode] = None, count: int = 0):
        self._root = root or HAMTNode()
        self._count = count

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        result = self._root.get(key, hash(key), 0)
        return result if result is not None else default

    def insert(self, key: K, value: V) -> PersistentHashMap[K, V]:
        # Returns a NEW map with the key-value pair added/updated
        new_root = self._root.insert(key, value, hash(key), 0)
        return PersistentHashMap(new_root, self._count + 1)

    def __len__(self) -> int:
        return self._count


# --- Usage ---
m0 = PersistentHashMap()
m1 = m0.insert("name", "Alice").insert("age", 30)
m2 = m1.insert("name", "Bob")
# m1.get("name") == "Alice"  -- m1 is unchanged
# m2.get("name") == "Bob"    -- m2 is a new version
# Both share the "age" -> 30 subtree via structural sharing
```

### Okasaki's Lazy Evaluation Patterns

Chris Okasaki's *Purely Functional Data Structures* introduced techniques for achieving amortized efficiency in persistent settings using **lazy evaluation**. The key insight: memoized suspensions (thunks) let you spread the cost of expensive operations across future accesses.

**However**, Python's eager evaluation model makes true Okasaki-style data structures less natural. The **trade-off** is that you must explicitly represent suspensions as lambdas or use `functools.lru_cache` for memoization, adding boilerplate that languages like Haskell handle transparently.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, Optional

T = TypeVar("T")


class Suspension(Generic[T]):
    # A lazy thunk that memoizes its result on first evaluation.
    # This is the core building block of Okasaki-style persistence.
    # Best practice: use suspensions to defer expensive rebalancing
    # operations so they are amortized across multiple accesses.

    def __init__(self, thunk: Callable[[], T]) -> None:
        self._thunk = thunk
        self._value: Optional[T] = None
        self._evaluated: bool = False

    def force(self) -> T:
        # Evaluate the thunk and cache the result.
        # Because results are memoized, repeated calls are O(1).
        # Therefore, amortized cost is spread across all accessors.
        if not self._evaluated:
            self._value = self._thunk()
            self._evaluated = True
            self._thunk = None  # Free the closure for GC
        return self._value


class LazyList(Generic[T]):
    # A persistent lazy list using Okasaki-style suspensions.
    # The tail is a suspended computation, evaluated on demand.
    # Pitfall: without memoization, each access recomputes the tail,
    # destroying the amortized complexity guarantees.

    def __init__(self, head: T, tail: Suspension[Optional[LazyList[T]]]) -> None:
        self._head = head
        self._tail = tail

    @staticmethod
    def empty() -> Optional[LazyList[T]]:
        return None

    @staticmethod
    def cons(head: T, tail_thunk: Callable[[], Optional[LazyList[T]]]) -> LazyList[T]:
        return LazyList(head, Suspension(tail_thunk))

    @property
    def head(self) -> T:
        return self._head

    @property
    def tail(self) -> Optional[LazyList[T]]:
        return self._tail.force()

    def take(self, n: int) -> list:
        # Materialize the first n elements into a Python list
        result = []
        current = self
        while current is not None and n > 0:
            result.append(current.head)
            current = current.tail
            n -= 1
        return result

    @staticmethod
    def from_range(start: int, end: int) -> Optional[LazyList[int]]:
        # Create a lazy range -- elements computed on demand
        if start >= end:
            return None
        return LazyList.cons(start, lambda: LazyList.from_range(start + 1, end))


# --- Usage: lazy list with deferred computation ---
lazy_nums = LazyList.from_range(0, 1000000)
# Nothing computed yet -- only the first element exists
first_ten = lazy_nums.take(10)
# Only 10 thunks were forced -- the remaining 999,990 are untouched
```

## Summary and Key Takeaways

- **Structural sharing** makes immutable updates O(log n) instead of O(n) -- **because** only the path from root to the changed node is copied
- **Persistent vectors** use 32-way tries where log32(1 billion) is only 6 -- effectively O(1) in practice
- **HAMTs** are the persistent equivalent of hash tables, using bitmaps to compress sparse 32-slot arrays -- a **best practice** for persistent maps
- **Common mistake**: assuming persistent data structures are fundamentally slower -- the log32 factor is tiny and the thread-safety and undo/redo capabilities are free
- **Pitfall**: forgetting to handle hash collisions in HAMT implementations -- two different keys can hash to the same 32-bit value and must be stored in collision nodes
- The **trade-off** of persistence: slightly higher per-operation cost in exchange for complete version history, thread safety, and structural sharing
- Okasaki's lazy evaluation patterns achieve amortized efficiency but require explicit suspension management in eager languages like Python
- **Best practice**: use persistent data structures when you need safe concurrency, undo/redo, or time-travel debugging -- **therefore** they are ideal for state management in FRP systems and event-sourced architectures"""
    ),
    # --- 3. Functional Reactive Programming ---
    (
        "fp/functional-reactive-programming-signals-events-frp",
        "Explain functional reactive programming including signals and behaviors, event streams, "
        "push versus pull models, time-varying values, and FRP in user interfaces with a complete "
        "Python implementation of a reactive signal system supporting map filter combine and a "
        "mini spreadsheet application",
        r"""# Functional Reactive Programming: Signals, Events, and Time-Varying Values

## What Is Functional Reactive Programming?

**Functional Reactive Programming** (FRP) is a paradigm for working with values that change over time using the compositional tools of functional programming -- `map`, `filter`, `combine`, and `fold`. Instead of scattering callback spaghetti and mutable state across your codebase, FRP models time-varying values as **first-class signals** (also called behaviors) and **event streams** that can be composed declaratively.

**Because** FRP treats time as a continuous dimension and events as discrete points in that continuum, it provides a unified framework for handling UI updates, sensor data, network messages, and any other temporal data. The result is code that reads as a **description of relationships** rather than a sequence of mutations.

### Signals vs. Event Streams

- **Signal (Behavior)**: a value that varies continuously over time. Examples: mouse position, current temperature, a text field's content. At any point in time, a signal has a current value.
- **Event Stream**: a discrete sequence of occurrences at specific times. Examples: button clicks, key presses, network responses. An event stream does not have a "current value" -- it fires values intermittently.

**Common mistake**: conflating signals and event streams. A signal always has a value; an event stream is empty between occurrences. The conversion between them requires explicit operations: `stepper` (event stream to signal using the latest value) and `changes` (signal to event stream when the value changes).

### Push vs. Pull Models

- **Pull-based FRP**: consumers request the current value when needed. Efficient when consumers are slower than producers. **However**, determining *when* to pull requires polling or external triggers.
- **Push-based FRP**: producers notify consumers immediately on change. More responsive, but risks **glitches** -- temporary inconsistencies when dependent signals update before their dependencies.
- **Push-pull hybrid**: combines both approaches. Values are pushed lazily and pulled on demand. This avoids both glitches and wasted computation.

**Best practice**: use topological sorting of the dependency graph to eliminate glitches in push-based systems. Update signals in dependency order so that no signal reads a stale dependency.

## Implementing a Reactive Signal System

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, List, Optional, Set, Dict, Any
from collections import deque

T = TypeVar("T")
U = TypeVar("U")


class Signal(Generic[T]):
    # A reactive signal representing a time-varying value.
    # Supports map, filter, combine, and automatic propagation.
    # Best practice: signals form a DAG (directed acyclic graph) of dependencies.

    _update_queue: deque = deque()
    _is_propagating: bool = False

    def __init__(self, initial_value: T, name: str = "") -> None:
        self._value: T = initial_value
        self._dependents: List[Signal] = []
        self._compute: Optional[Callable[[], T]] = None
        self._sources: List[Signal] = []
        self.name = name or f"signal_{id(self)}"

    @property
    def value(self) -> T:
        return self._value

    @value.setter
    def value(self, new_value: T) -> None:
        if self._value != new_value:
            self._value = new_value
            self._notify_dependents()

    def _notify_dependents(self) -> None:
        # Push-based propagation with topological ordering.
        # Therefore, dependents always see consistent values.
        for dep in self._dependents:
            if dep not in Signal._update_queue:
                Signal._update_queue.append(dep)

        if not Signal._is_propagating:
            Signal._is_propagating = True
            while Signal._update_queue:
                signal = Signal._update_queue.popleft()
                signal._recompute()
            Signal._is_propagating = False

    def _recompute(self) -> None:
        if self._compute is not None:
            new_value = self._compute()
            if new_value != self._value:
                self._value = new_value
                # Propagate to further dependents
                for dep in self._dependents:
                    if dep not in Signal._update_queue:
                        Signal._update_queue.append(dep)

    def map(self, f: Callable[[T], U], name: str = "") -> Signal[U]:
        # Functor map: create a derived signal that transforms this value.
        # Pitfall: the mapped function must be pure -- side effects here
        # would execute on every propagation cycle.
        derived = Signal(f(self._value), name=name)
        derived._compute = lambda: f(self._value)
        derived._sources = [self]
        self._dependents.append(derived)
        return derived

    def filter(self, predicate: Callable[[T], bool], default: T = None, name: str = "") -> Signal[T]:
        # Create a derived signal that only updates when predicate is true.
        # However, it always has a value -- the last value that passed the filter.
        initial = self._value if predicate(self._value) else default
        derived = Signal(initial, name=name)

        def compute():
            val = self._value
            if predicate(val):
                return val
            return derived._value  # Keep previous value
        derived._compute = compute
        derived._sources = [self]
        self._dependents.append(derived)
        return derived

    @staticmethod
    def combine(
        signals: List[Signal],
        combiner: Callable[..., T],
        name: str = ""
    ) -> Signal[T]:
        # Combine multiple signals into one using a combiner function.
        # Because we use topological propagation, the combined signal
        # sees a consistent snapshot of all sources.
        initial = combiner(*[s._value for s in signals])
        derived = Signal(initial, name=name)
        derived._compute = lambda: combiner(*[s._value for s in signals])
        derived._sources = list(signals)
        for s in signals:
            s._dependents.append(derived)
        return derived

    @staticmethod
    def fold(
        source: Signal[T],
        initial: U,
        reducer: Callable[[U, T], U],
        name: str = ""
    ) -> Signal[U]:
        # Accumulate values over time using a reducer function.
        # This converts an event-like signal into accumulated state.
        # Trade-off: holds onto accumulated state forever, so be
        # careful with memory in long-running applications.
        acc = Signal(initial, name=name)

        def compute():
            return reducer(acc._value, source._value)
        acc._compute = compute
        acc._sources = [source]
        source._dependents.append(acc)
        return acc

    def __repr__(self) -> str:
        return f"Signal({self.name}={self._value!r})"
```

## Event Streams: Discrete Occurrences

```python
class EventStream(Generic[T]):
    # Represents discrete events that occur at specific points in time.
    # Unlike signals, event streams do not have a "current value" between events.
    # Common mistake: treating event streams like signals and reading their
    # value when no event has occurred.

    def __init__(self, name: str = "") -> None:
        self._listeners: List[Callable[[T], None]] = []
        self.name = name

    def emit(self, value: T) -> None:
        # Fire an event to all listeners
        for listener in self._listeners:
            listener(value)

    def on(self, callback: Callable[[T], None]) -> None:
        self._listeners.append(callback)

    def map(self, f: Callable[[T], U]) -> EventStream[U]:
        # Transform events as they pass through
        mapped = EventStream(name=f"{self.name}.map")
        self.on(lambda v: mapped.emit(f(v)))
        return mapped

    def filter(self, predicate: Callable[[T], bool]) -> EventStream[T]:
        # Only pass through events matching the predicate
        filtered = EventStream(name=f"{self.name}.filter")
        self.on(lambda v: filtered.emit(v) if predicate(v) else None)
        return filtered

    def to_signal(self, initial: T) -> Signal[T]:
        # Convert event stream to signal using latest event value.
        # Therefore, the signal always reflects the most recent event.
        sig = Signal(initial, name=f"{self.name}.signal")
        self.on(lambda v: setattr(sig, 'value', v))
        return sig

    def merge(self, other: EventStream[T]) -> EventStream[T]:
        # Merge two event streams into one
        merged = EventStream(name=f"merge({self.name},{other.name})")
        self.on(lambda v: merged.emit(v))
        other.on(lambda v: merged.emit(v))
        return merged
```

## Mini Spreadsheet with FRP

```python
class Spreadsheet:
    # A mini spreadsheet where cells are reactive signals.
    # Changing one cell automatically propagates to all dependent cells.
    # Best practice: model spreadsheet formulas as signal combinators
    # rather than manual recalculation loops.

    def __init__(self) -> None:
        self._cells: Dict[str, Signal] = {}

    def set_value(self, cell_name: str, value: Any) -> None:
        if cell_name in self._cells:
            self._cells[cell_name].value = value
        else:
            self._cells[cell_name] = Signal(value, name=cell_name)

    def set_formula(
        self, cell_name: str,
        source_names: List[str],
        formula: Callable[..., Any]
    ) -> None:
        # Create a formula cell that depends on other cells.
        # Because signals propagate automatically, formulas
        # recompute whenever their dependencies change.
        sources = [self._cells[name] for name in source_names]
        derived = Signal.combine(sources, formula, name=cell_name)
        self._cells[cell_name] = derived

    def get_value(self, cell_name: str) -> Any:
        return self._cells[cell_name].value

    def display(self) -> None:
        for name, signal in sorted(self._cells.items()):
            print(f"  {name}: {signal.value}")


# --- Usage ---
sheet = Spreadsheet()
sheet.set_value("A1", 10)
sheet.set_value("A2", 20)
sheet.set_value("B1", 5)

# C1 = A1 + A2 (auto-updates when A1 or A2 changes)
sheet.set_formula("C1", ["A1", "A2"], lambda a, b: a + b)

# D1 = C1 * B1 (depends on formula cell C1)
sheet.set_formula("D1", ["C1", "B1"], lambda c, b: c * b)

# sheet.get_value("C1") == 30
# sheet.get_value("D1") == 150

sheet.set_value("A1", 100)
# Now C1 == 120, D1 == 600 -- all propagated automatically
```

### Glitch Freedom and Topological Ordering

A **glitch** occurs when a derived signal reads inconsistent values from its sources during propagation. For example, if signal C depends on both A and B, and both A and B change, C might see the new A but old B temporarily.

**Therefore**, robust FRP implementations use topological sorting: compute signals in dependency order so every signal sees fully updated inputs. Our queue-based propagation above achieves this naturally **because** dependents are added to the queue after their sources update.

**Pitfall**: circular dependencies in the signal graph cause infinite loops. Always ensure signals form a directed acyclic graph (DAG). Detect cycles at construction time and raise an error immediately.

## Summary and Key Takeaways

- **FRP** models time-varying values as composable signals and event streams -- **therefore** eliminating callback spaghetti and mutable state
- **Signals** always have a current value; **event streams** fire discretely -- a **common mistake** is conflating the two
- **Push-based** propagation is responsive but risks glitches; **pull-based** avoids glitches but requires polling -- the **trade-off** favors push-pull hybrids
- **Best practice**: use topological ordering in the dependency graph to ensure glitch-free propagation
- **Pitfall**: circular dependencies in signal graphs cause infinite propagation loops -- detect and reject cycles at construction time
- The spreadsheet model is a natural fit for FRP **because** each cell's value is derived from other cells via formulas
- `fold` accumulates event values over time, converting discrete events into continuous state -- **however**, unbounded accumulation can leak memory"""
    ),
    # --- 4. Effect Systems and Algebraic Effects ---
    (
        "fp/effect-systems-algebraic-effects-free-monads-handlers",
        "Explain effect systems and algebraic effects including separating effect description from "
        "execution, free monads, effect handlers, comparison with dependency injection, and implement "
        "a complete effect system in Python with swappable interpreters for testing and production "
        "environments",
        r"""# Effect Systems and Algebraic Effects: Separating Description from Execution

## The Fundamental Problem: Side Effects Everywhere

Every useful program performs side effects -- reading files, querying databases, sending HTTP requests, writing logs. The problem is not that effects exist, but that they are **entangled** with business logic. When your `process_order` function directly calls `db.save()` and `email.send()`, you cannot test the business logic without a database and an email server.

**Because** effects are interleaved with pure computation, testing requires mocking, integration environments, and complex test fixtures. Effect systems solve this by **separating the description of effects from their execution**. Your business logic produces a data structure describing *what* effects it wants, and a separate interpreter decides *how* to execute them.

This is not just better testing. It enables:
- **Swappable interpreters**: test interpreter, production interpreter, dry-run interpreter
- **Effect composition**: combine logging, database, and HTTP effects without coupling
- **Reasoning about programs**: pure descriptions are easier to analyze, optimize, and transform

### Algebraic Effects vs. Free Monads vs. Dependency Injection

**Dependency injection** (DI) passes interfaces as parameters: `def process(db: DBInterface, email: EmailInterface)`. This works but has limitations -- you must thread dependencies through every function call, and combining multiple effects requires parameter explosion.

**Free monads** encode effects as an AST (Abstract Syntax Tree) of operations. Your program builds a tree of effect descriptions, and an interpreter folds over the tree to execute it. **However**, free monads in Python are verbose because Python lacks the syntactic support (do-notation) that Haskell provides.

**Algebraic effects** (as in languages like Eff, Koka, and OCaml 5) provide effect *handlers* that can intercept effect operations mid-execution and resume or modify the continuation. This is more powerful than free monads **because** handlers can choose to resume the computation multiple times, once, or not at all.

**Common mistake**: assuming dependency injection and effect systems are interchangeable. DI solves the "provide implementations" problem but does not give you composable effect descriptions, interpreter swapping at the boundary, or the ability to transform effect pipelines.

## Building an Effect System with Free Monads

The core idea: define effects as **data classes** (descriptions), compose them with `bind`, and interpret them with pattern matching.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, List, Any, Dict, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

A = TypeVar("A")
B = TypeVar("B")


# --- Effect descriptions (the "algebra") ---
# These are pure data -- no side effects occur when creating them.
# Therefore, they can be inspected, transformed, and tested.

class Effect(ABC):
    # Base class for all effect descriptions
    pass


@dataclass(frozen=True)
class ReadFile(Effect):
    path: str


@dataclass(frozen=True)
class WriteFile(Effect):
    path: str
    content: str


@dataclass(frozen=True)
class HttpGet(Effect):
    url: str


@dataclass(frozen=True)
class HttpPost(Effect):
    url: str
    body: str


@dataclass(frozen=True)
class LogMessage(Effect):
    level: str
    message: str


@dataclass(frozen=True)
class GetConfig(Effect):
    key: str


# --- Free monad: composing effect descriptions ---

class Free(Generic[A]):
    # The Free monad wraps effect descriptions into a composable structure.
    # Best practice: keep the Free structure minimal and push complexity
    # into interpreters.

    def bind(self, f: Callable[[A], Free[B]]) -> Free[B]:
        # Monadic bind: sequence two effectful computations
        if isinstance(self, Pure):
            return f(self.value)
        elif isinstance(self, Impure):
            # Defer the bind into the continuation
            original_cont = self.continuation
            return Impure(
                self.effect,
                lambda result: original_cont(result).bind(f)
            )
        raise TypeError(f"Unknown Free variant: {type(self)}")

    def map(self, f: Callable[[A], B]) -> Free[B]:
        return self.bind(lambda a: Pure(f(a)))


class Pure(Free[A]):
    # A pure value -- no effects needed
    def __init__(self, value: A) -> None:
        self.value = value


class Impure(Free[A]):
    # An effect to perform, followed by a continuation
    def __init__(self, effect: Effect, continuation: Callable[[Any], Free[A]]) -> None:
        self.effect = effect
        self.continuation = continuation


# --- Smart constructors: lift effects into Free ---
# These provide a clean API for building effect descriptions.
# Pitfall: forgetting to use smart constructors and manually
# constructing Impure nodes leads to brittle, unreadable code.

def read_file(path: str) -> Free[str]:
    return Impure(ReadFile(path), lambda content: Pure(content))

def write_file(path: str, content: str) -> Free[None]:
    return Impure(WriteFile(path, content), lambda _: Pure(None))

def http_get(url: str) -> Free[str]:
    return Impure(HttpGet(url), lambda response: Pure(response))

def http_post(url: str, body: str) -> Free[str]:
    return Impure(HttpPost(url, body), lambda response: Pure(response))

def log(level: str, message: str) -> Free[None]:
    return Impure(LogMessage(level, message), lambda _: Pure(None))

def get_config(key: str) -> Free[str]:
    return Impure(GetConfig(key), lambda value: Pure(value))
```

## Writing Business Logic as Pure Descriptions

```python
# --- Business logic: pure effect descriptions ---
# This function describes WHAT to do, not HOW to do it.
# Therefore, it is completely testable without mocks.

def sync_user_data(user_id: str) -> Free[Dict[str, Any]]:
    # Trade-off: more verbose than direct calls, but fully testable
    # and the execution strategy is determined by the interpreter.
    return (
        get_config("api_base_url")
        .bind(lambda base_url:
            log("info", f"Fetching data for user {user_id}")
            .bind(lambda _:
                http_get(f"{base_url}/users/{user_id}")
                .bind(lambda response:
                    log("info", f"Received {len(response)} bytes")
                    .bind(lambda _:
                        write_file(f"/data/users/{user_id}.json", response)
                        .bind(lambda _:
                            log("info", f"Saved user {user_id} data")
                            .bind(lambda _:
                                Pure({"user_id": user_id, "status": "synced",
                                      "bytes": len(response)})
                            )
                        )
                    )
                )
            )
        )
    )
```

## Interpreters: Swappable Execution Strategies

```python
# --- Production interpreter: executes real effects ---
class ProductionInterpreter:
    # Interprets effect descriptions by performing real I/O.
    # Because the business logic is pure, we only need to handle
    # each effect type here.

    def __init__(self, config: Dict[str, str]) -> None:
        self.config = config

    def run(self, program: Free[A]) -> A:
        current = program
        while True:
            if isinstance(current, Pure):
                return current.value

            if isinstance(current, Impure):
                result = self._handle_effect(current.effect)
                current = current.continuation(result)
            else:
                raise TypeError(f"Unknown Free variant: {type(current)}")

    def _handle_effect(self, effect: Effect) -> Any:
        if isinstance(effect, ReadFile):
            with open(effect.path, "r") as f:
                return f.read()
        elif isinstance(effect, WriteFile):
            with open(effect.path, "w") as f:
                f.write(effect.content)
            return None
        elif isinstance(effect, HttpGet):
            import urllib.request
            with urllib.request.urlopen(effect.url) as resp:
                return resp.read().decode()
        elif isinstance(effect, HttpPost):
            import urllib.request
            req = urllib.request.Request(
                effect.url, data=effect.body.encode(),
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                return resp.read().decode()
        elif isinstance(effect, LogMessage):
            print(f"[{effect.level.upper()}] {effect.message}")
            return None
        elif isinstance(effect, GetConfig):
            return self.config.get(effect.key, "")
        raise ValueError(f"Unhandled effect: {effect}")


# --- Test interpreter: records effects without executing them ---
class TestInterpreter:
    # Interprets effect descriptions by returning canned responses
    # and recording what effects were requested.
    # Best practice: use test interpreters to verify business logic
    # without any I/O, network, or filesystem access.

    def __init__(self) -> None:
        self.effects_log: List[Effect] = []
        self.responses: Dict[type, Any] = {
            ReadFile: "mock file content",
            WriteFile: None,
            HttpGet: '{"id": "123", "name": "Test User"}',
            HttpPost: '{"status": "ok"}',
            LogMessage: None,
            GetConfig: "https://api.example.com",
        }

    def set_response(self, effect_type: type, response: Any) -> None:
        self.responses[effect_type] = response

    def run(self, program: Free[A]) -> A:
        current = program
        while True:
            if isinstance(current, Pure):
                return current.value

            if isinstance(current, Impure):
                self.effects_log.append(current.effect)
                result = self.responses.get(type(current.effect))
                current = current.continuation(result)
            else:
                raise TypeError(f"Unknown Free variant")

    def assert_effect_occurred(self, effect_type: type, **kwargs) -> bool:
        # Verify specific effects were requested
        for effect in self.effects_log:
            if isinstance(effect, effect_type):
                if all(getattr(effect, k) == v for k, v in kwargs.items()):
                    return True
        return False


# --- Using test interpreter in tests ---
def test_sync_user_data():
    interpreter = TestInterpreter()
    interpreter.set_response(GetConfig, "https://api.test.com")
    interpreter.set_response(HttpGet, '{"id": "u42", "name": "Alice"}')

    result = interpreter.run(sync_user_data("u42"))

    assert result["user_id"] == "u42"
    assert result["status"] == "synced"

    # Verify the correct effects were requested
    assert interpreter.assert_effect_occurred(HttpGet, url="https://api.test.com/users/u42")
    assert interpreter.assert_effect_occurred(
        WriteFile, path="/data/users/u42.json"
    )
    # Verify logging happened
    log_effects = [e for e in interpreter.effects_log if isinstance(e, LogMessage)]
    assert len(log_effects) == 3  # Three log messages in the pipeline

test_sync_user_data()
```

### Comparison with Dependency Injection

| Aspect | Dependency Injection | Effect Systems |
|--------|---------------------|----------------|
| Testability | Good (mock interfaces) | Excellent (swap interpreters) |
| Composition | Manual parameter threading | Monadic composition |
| Effect tracking | Implicit in types | Explicit in effect descriptions |
| Reusability | Interface-bound | Interpreter-independent |
| Overhead | Minimal | More boilerplate in Python |

The **trade-off** is clear: effect systems provide stronger guarantees and more flexibility, but at the cost of verbosity in languages without native support. **However**, even a lightweight version (like the one above) dramatically improves testability.

**Pitfall**: over-engineering the effect system. In Python, you rarely need the full power of algebraic effects with resumable continuations. The free monad pattern shown above covers 90% of practical use cases -- testing, environment swapping, and effect logging.

## Summary and Key Takeaways

- Effect systems **separate description from execution** -- business logic produces pure data structures describing effects, interpreters decide how to run them
- **Free monads** encode effect sequences as composable ASTs -- **therefore** you can inspect, transform, and test effect pipelines without performing any I/O
- **Test interpreters** return canned responses and record requested effects -- **because** the business logic never directly performs I/O, tests require zero mocking frameworks
- **Common mistake**: confusing effect systems with dependency injection -- DI provides implementations, effect systems provide composable descriptions and swappable interpreters
- The **trade-off** of effect systems in Python: more boilerplate than direct calls, but dramatically improved testability and separation of concerns
- **Best practice**: define effects as frozen dataclasses, use smart constructors for ergonomics, and write one interpreter per execution environment
- **Pitfall**: building overly complex effect systems when a simple interpreter pattern suffices -- start with the free monad approach and add complexity only when needed
- Algebraic effects (in Koka, Eff, OCaml 5) go further with resumable handlers, but the free monad pattern covers the vast majority of practical use cases in Python"""
    ),
    # --- 5. Category Theory for Programmers ---
    (
        "fp/category-theory-functors-natural-transformations-yoneda",
        "Explain category theory concepts for programmers including functors as mappings between "
        "categories, natural transformations, adjunctions, and the Yoneda lemma in practical terms "
        "with Python implementations of functor applicative and monad typeclasses and real-world "
        "examples showing how category theory improves code design",
        r"""# Category Theory for Programmers: From Functors to the Yoneda Lemma

## Why Category Theory Matters for Software

Category theory is often called "the mathematics of mathematics" -- it studies structure and composition in their most abstract form. For programmers, this abstraction is not academic overhead. It provides a **precise vocabulary** for patterns you already use: mapping, chaining, combining, and transforming. When you understand these patterns categorically, you gain the ability to recognize them across domains, compose them safely, and extend them predictably.

**Because** category theory focuses on **composition** and **structure-preserving transformations**, it maps directly to software engineering goals: building systems from composable, well-behaved parts. The key structures -- functors, natural transformations, monads, and adjunctions -- each capture a specific kind of composition that appears repeatedly in real code.

**Common mistake**: trying to learn category theory from abstract math textbooks. Programmers should learn it through types and implementations, mapping each concept to concrete code patterns.

### What Is a Category?

A **category** consists of:
- **Objects**: think of these as types (`int`, `str`, `List[int]`, `Maybe[str]`)
- **Morphisms** (arrows): think of these as functions between types (`int -> str`, `str -> bool`)
- **Composition**: if you have `f: A -> B` and `g: B -> C`, you can compose them into `g . f: A -> C`
- **Identity**: every object has an identity morphism `id: A -> A`

Composition must be **associative** and identity must be a **unit** for composition. These are the category laws, and they map directly to how function composition works in programming.

## Functors: Structure-Preserving Mappings

A **functor** is a mapping between categories that preserves structure. In programming, a functor is a type constructor `F` with a `map` operation that satisfies the functor laws (identity and composition).

**Therefore**, `List`, `Maybe`, `Result`, `IO`, and `Future` are all functors -- they are type constructors that can be mapped over while preserving the computational context.

```python
from __future__ import annotations
from typing import TypeVar, Generic, Callable, List as PyList, Protocol, runtime_checkable
from abc import ABC, abstractmethod

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


# --- Functor typeclass ---
# In Haskell: class Functor f where fmap :: (a -> b) -> f a -> f b
# In Python: we use an abstract base class as the typeclass.
# Best practice: always verify functor laws in tests.

class Functor(ABC, Generic[A]):
    @abstractmethod
    def map(self, f: Callable[[A], B]) -> Functor[B]:
        # Apply f to the value(s) inside the functor context
        # Must satisfy:
        #   1. Identity: x.map(lambda a: a) == x
        #   2. Composition: x.map(f).map(g) == x.map(lambda a: g(f(a)))
        ...


# --- Concrete functor: Identity ---
class Identity(Functor[A]):
    # The simplest possible functor -- wraps a single value
    def __init__(self, value: A) -> None:
        self._value = value

    def map(self, f: Callable[[A], B]) -> Identity[B]:
        return Identity(f(self._value))

    @property
    def value(self) -> A:
        return self._value

    def __eq__(self, other) -> bool:
        return isinstance(other, Identity) and self._value == other._value

    def __repr__(self) -> str:
        return f"Identity({self._value!r})"


# --- Concrete functor: Box (like Maybe/Just without Nothing) ---
class Box(Functor[A]):
    # A functor that wraps a value in a "box" context
    def __init__(self, value: A) -> None:
        self._value = value

    def map(self, f: Callable[[A], B]) -> Box[B]:
        return Box(f(self._value))

    @property
    def value(self) -> A:
        return self._value

    def __eq__(self, other) -> bool:
        return isinstance(other, Box) and self._value == other._value

    def __repr__(self) -> str:
        return f"Box({self._value!r})"


# --- Verify functor laws ---
def verify_functor_laws(functor_instance: Functor[A], f: Callable, g: Callable) -> bool:
    # Identity law
    identity_holds = functor_instance.map(lambda x: x) == functor_instance

    # Composition law
    composed = functor_instance.map(f).map(g)
    fused = functor_instance.map(lambda x: g(f(x)))
    composition_holds = composed == fused

    return identity_holds and composition_holds

# Test
assert verify_functor_laws(Box(10), lambda x: x * 2, lambda x: x + 1)
assert verify_functor_laws(Identity("hello"), lambda s: s.upper(), lambda s: len(s))
```

## Applicative Functors: Applying Functions in Context

An **applicative functor** extends a functor with the ability to apply a function *that is itself inside the context* to a value in the context. While `map` applies a bare function `A -> B` to `F[A]`, applicative's `apply` takes an `F[A -> B]` and applies it to `F[A]`.

**However**, the real power of applicatives is combining **independent** computations. Monadic `bind` sequences computations (each depends on the previous), but applicative `apply` combines computations that are independent. **Therefore**, applicatives can be parallelized while monads cannot.

```python
# --- Applicative typeclass ---
# Extends Functor with pure (lift a value) and apply (apply lifted function)
# Pitfall: many developers skip Applicative and go straight to Monad,
# missing the opportunity for independent combination and parallelism.

class Applicative(Functor[A]):
    @staticmethod
    @abstractmethod
    def pure(value: A) -> Applicative[A]:
        # Lift a value into the applicative context
        ...

    @abstractmethod
    def apply(self, func_in_context: Applicative[Callable[[A], B]]) -> Applicative[B]:
        # Apply a function inside the context to a value inside the context
        # Must satisfy applicative laws:
        #   1. Identity: pure(id).apply(v) == v
        #   2. Composition: pure(compose).apply(u).apply(v).apply(w) == u.apply(v.apply(w))
        #   3. Homomorphism: pure(f).apply(pure(x)) == pure(f(x))
        #   4. Interchange: u.apply(pure(y)) == pure(lambda f: f(y)).apply(u)
        ...


class Maybe(Applicative[A]):
    # Maybe as a full Applicative Functor
    # Common mistake: not handling Nothing propagation in apply

    @staticmethod
    def pure(value: A) -> Maybe[A]:
        return MJust(value)

    @staticmethod
    def nothing() -> Maybe[A]:
        return MNothing()

    def map(self, f: Callable[[A], B]) -> Maybe[B]:
        if isinstance(self, MJust):
            return MJust(f(self._value))
        return MNothing()

    def apply(self, func_in_context: Maybe[Callable[[A], B]]) -> Maybe[B]:
        # Apply a Maybe-wrapped function to this Maybe-wrapped value
        if isinstance(func_in_context, MNothing) or isinstance(self, MNothing):
            return MNothing()
        return MJust(func_in_context._value(self._value))

    def bind(self, f: Callable[[A], Maybe[B]]) -> Maybe[B]:
        if isinstance(self, MJust):
            return f(self._value)
        return MNothing()

    def __eq__(self, other) -> bool:
        if isinstance(self, MJust) and isinstance(other, MJust):
            return self._value == other._value
        return isinstance(self, MNothing) and isinstance(other, MNothing)

    def __repr__(self) -> str:
        if isinstance(self, MJust):
            return f"Just({self._value!r})"
        return "Nothing"


class MJust(Maybe[A]):
    def __init__(self, value: A) -> None:
        self._value = value


class MNothing(Maybe[A]):
    pass


# --- Using applicative to combine independent computations ---
# Because applicatives combine independent values, they express
# "compute A and B, then combine" without sequential dependency.

def lift_a2(f: Callable[[A, B], C], fa: Maybe[A], fb: Maybe[B]) -> Maybe[C]:
    # Lift a 2-argument function into the applicative context.
    # This is how you combine independent Maybe values.
    return fb.apply(fa.map(lambda a: lambda b: f(a, b)))

# Example: combining two optional values
result = lift_a2(lambda x, y: x + y, Maybe.pure(10), Maybe.pure(20))
# result == Just(30)

result_fail = lift_a2(lambda x, y: x + y, Maybe.pure(10), Maybe.nothing())
# result_fail == Nothing
```

## Natural Transformations: Mappings Between Functors

A **natural transformation** is a mapping from one functor to another that preserves the structure. If you have functors `F` and `G`, a natural transformation `alpha` maps `F[A]` to `G[A]` for every type `A`, such that the transformation commutes with `map`.

**Therefore**, converting `List[A]` to `Maybe[A]` (by taking the head), or `Maybe[A]` to `List[A]` (by producing a 0-or-1 element list), are natural transformations.

```python
# --- Natural transformations ---
# A natural transformation alpha: F ~> G satisfies:
#   alpha(F.map(f)(x)) == G.map(f)(alpha(x))
# In other words: transforming then mapping == mapping then transforming.

# Trade-off: natural transformations constrain your implementation --
# they MUST work uniformly for all types A, not inspect the inner value.

def maybe_to_list(m: Maybe[A]) -> PyList[A]:
    # Natural transformation: Maybe ~> List
    if isinstance(m, MJust):
        return [m._value]
    return []

def list_head(lst: PyList[A]) -> Maybe[A]:
    # Natural transformation: List ~> Maybe
    if lst:
        return MJust(lst[0])
    return MNothing()

# Verify naturality: transform then map == map then transform
f = lambda x: x * 2
original = MJust(5)
# Path 1: transform then map
path1 = [f(x) for x in maybe_to_list(original)]
# Path 2: map then transform
path2 = maybe_to_list(original.map(f))
assert path1 == path2  # Naturality holds
```

### The Yoneda Lemma in Practical Terms

The **Yoneda lemma** states that for any functor `F`, the set of natural transformations from `Hom(A, -)` to `F` is isomorphic to `F(A)`. In practical terms: **a functor value `F[A]` is completely determined by how it responds to being mapped over**.

This has a practical consequence called the **Yoneda embedding** or **codensity optimization**: instead of storing `F[A]` directly, you can store a function `forall B. (A -> B) -> F[B]` and fuse multiple `map` calls into one. This eliminates intermediate data structures.

**Best practice**: the Yoneda optimization is useful when you have chains of `map` operations on expensive functors. Instead of creating intermediate wrapped values, you compose the functions and apply them once.

### Adjunctions: Paired Functors

An **adjunction** between functors `F` and `G` means that `F` is the "best approximation" of an inverse to `G`. The canonical example: the **currying adjunction** where `(A x B) -> C` is isomorphic to `A -> (B -> C)`. Here, `(- x B)` and `(B -> -)` form an adjoint pair.

**However**, adjunctions are rarely implemented explicitly in application code. Their importance is theoretical: every monad arises from an adjunction (`F . G` where `F` is left adjoint to `G`). Understanding this explains *why* monads have the structure they do.

## Summary and Key Takeaways

- A **category** is objects (types), morphisms (functions), and composition -- programming already operates within categories
- **Functors** are structure-preserving mappings between categories; in code, any type with a law-abiding `map` -- **therefore** List, Maybe, IO, and Future are all functors
- **Applicative functors** combine independent computations in context -- the **trade-off** versus monads is that applicatives cannot express sequential dependency but can be parallelized
- **Natural transformations** convert between functors uniformly for all types -- **because** they must commute with `map`, they are constrained to structural transformations
- The **Yoneda lemma** says a functor value equals its behavior under mapping -- **best practice**: use this to fuse chains of `map` into a single pass
- **Adjunctions** pair functors that are "approximate inverses" -- every monad arises from an adjunction, explaining the structure of `bind` and `return`
- **Common mistake**: treating category theory as purely abstract -- these concepts directly correspond to code patterns like mapping, chaining, and combining
- **Pitfall**: implementing typeclasses in Python without verifying the laws -- a `map` that violates identity or composition is worse than no abstraction at all"""
    ),
]
