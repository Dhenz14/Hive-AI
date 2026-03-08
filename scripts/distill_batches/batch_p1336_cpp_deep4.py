"""C++ deep reasoning pairs batch 4: STL containers and algorithms."""
PAIRS = [
    ("cpp_deep/vector_growth_iterator_invalidation", r'''In C++17, I have a std::vector that I'm iterating over while occasionally inserting elements. I'm getting crashes. Can you explain the vector growth strategy, when iterators get invalidated, and show a safe pattern for insert-during-iteration?''', r'''<think>
This is about vector internals and iterator invalidation — a classic C++ footgun.
Key points to cover:
1. Vector growth strategy: typically doubles capacity (factor ~1.5 or 2 depending on implementation)
2. When reallocation happens, ALL iterators, pointers, and references are invalidated
3. Even without reallocation, insert/emplace invalidates iterators at or after the insertion point
4. erase invalidates iterators at or after the erased element
5. The safe pattern is to use index-based iteration, or collect insertions and apply after
6. Another approach: use the return value of insert() which gives a valid iterator
7. reserve() can prevent reallocation but doesn't prevent positional invalidation
8. Need to show capacity vs size distinction
9. The growth factor matters for amortized O(1) push_back
10. MSVC uses 1.5x, GCC/libstdc++ uses 2x typically
11. For the demo, I'll show the crash scenario, then the safe pattern using indices
12. Also show how insert() returns a valid iterator for the inserted element
13. Should mention that with reserve, only positional invalidation applies
14. The index-based approach is simplest and most robust
15. Could also show a pattern where we build a separate vector and merge
</think>

**Vector Growth and Iterator Invalidation**

When a `std::vector` runs out of capacity, it allocates a new larger buffer (typically 1.5x on MSVC, 2x on GCC), copies/moves elements, and deallocates the old buffer. This invalidates **all** iterators, pointers, and references. Even without reallocation, `insert`/`erase` invalidates iterators **at or after** the affected position.

```cpp
#include <vector>
#include <iostream>
#include <cassert>

// Demonstrate growth strategy
void show_growth() {
    std::vector<int> v;
    size_t old_cap = 0;
    for (int i = 0; i < 100; ++i) {
        v.push_back(i);
        if (v.capacity() != old_cap) {
            std::cout << "size=" << v.size()
                      << " capacity=" << v.capacity() << "\n";
            old_cap = v.capacity();
        }
    }
}

// BAD: iterator invalidation during insertion
void dangerous_insert() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    // DO NOT DO THIS — undefined behavior if reallocation occurs
    // for (auto it = v.begin(); it != v.end(); ++it) {
    //     if (*it == 3) v.insert(it, 99);  // crash or UB
    // }
}

// SAFE pattern 1: index-based iteration
void safe_index_insert() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    for (size_t i = 0; i < v.size(); ++i) {
        if (v[i] % 2 == 0) {
            v.insert(v.begin() + static_cast<ptrdiff_t>(i), v[i] * 10);
            ++i;  // skip the newly inserted element
        }
    }
    // v = {20, 2, 3, 40, 4, 5} — wait, let's trace:
    // i=0: 1 is odd, skip. i=1: 2 is even, insert 20 at i=1, then ++i -> i=2 (now pointing to 2)
    // Actually: after insert at position 1: {1, 20, 2, 3, 4, 5}, i becomes 2 -> v[2]=2
    // This needs care. Let me show a cleaner version:
    std::vector<int> src = {1, 2, 3, 4, 5};
    std::vector<int> result;
    result.reserve(src.size() * 2);  // pre-allocate to avoid repeated growth
    for (int val : src) {
        if (val % 2 == 0) {
            result.push_back(val * 10);  // insert doubled value before even numbers
        }
        result.push_back(val);
    }
    // result = {1, 20, 2, 3, 40, 4, 5}
    for (int x : result) std::cout << x << " ";
    std::cout << "\n";
}

// SAFE pattern 2: use insert()'s return value
void safe_iterator_insert() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    v.reserve(10);  // prevent reallocation (still need care with positional invalidation)

    for (auto it = v.begin(); it != v.end(); ++it) {
        if (*it == 3) {
            it = v.insert(it, 99);  // returns iterator to inserted element
            ++it;  // now points to the original element (3)
            // loop's ++it will advance past 3
        }
    }
    // v = {1, 2, 99, 3, 4, 5}
    for (int x : v) std::cout << x << " ";
    std::cout << "\n";
}

// Show that reserve prevents reallocation invalidation
void reserve_demo() {
    std::vector<int> v;
    v.reserve(100);
    v.push_back(1);
    int* ptr = &v[0];       // pointer to first element
    for (int i = 2; i <= 100; ++i) {
        v.push_back(i);
    }
    assert(ptr == &v[0]);   // still valid — no reallocation occurred
    std::cout << "reserve() kept pointer stable: " << *ptr << "\n";
}

int main() {
    std::cout << "=== Growth Strategy ===\n";
    show_growth();

    std::cout << "\n=== Safe Index Insert ===\n";
    safe_index_insert();

    std::cout << "\n=== Safe Iterator Insert ===\n";
    safe_iterator_insert();

    std::cout << "\n=== Reserve Demo ===\n";
    reserve_demo();
}
```

**Key rules:**
- `push_back`/`emplace_back`: invalidates all iterators if `size() == capacity()`, otherwise only `end()`
- `insert`: invalidates iterators at or after the insertion point (all if reallocation)
- `erase`: invalidates iterators at or after the erased position
- `reserve(n)`: guarantees no reallocation until `size() > n`, but positional invalidation still applies on insert/erase
- **Safest approach**: build a new vector or use index-based loops when modifying during iteration'''),

    ("cpp_deep/deque_vs_vector", r'''When should I prefer std::deque over std::vector in C++? I know vector is the default, but I've heard deque is better in certain scenarios. Can you show a concrete benchmark comparison?''', r'''<think>
Deque vs vector is a nuanced topic. Let me think about when deque actually wins:
1. Front insertion/deletion: deque is O(1) amortized, vector is O(n)
2. Memory: deque allocates in chunks, so never needs a huge contiguous block
3. Deque never invalidates pointers/references on push_front/push_back (only iterators)
4. Vector is better for: random access speed (single contiguous block, cache-friendly), less memory overhead per element
5. Deque's internal structure: array of pointers to fixed-size blocks
6. Deque wins when: queue/double-ended operations, very large containers where contiguous allocation fails, or when pointer stability matters on push operations
7. The benchmark should show front insertion (deque crushes vector), back insertion (roughly equal), and random access (vector slightly wins)
8. I should also mention that deque is the default underlying container for std::queue and std::stack
9. One gotcha: deque has higher per-element overhead and worse cache performance for sequential access
10. For the benchmark, use chrono high_resolution_clock
11. Need to be careful about optimizer eliminating dead code — use volatile or accumulate results
12. Show practical use case: sliding window / BFS where we pop front and push back
13. Memory fragmentation advantage of deque for large containers
14. Deque iterators are more complex (slower increment than pointer arithmetic)
15. Include a BFS example where deque is the natural choice
</think>

**`std::deque` vs `std::vector` -- When Deque Wins**

Deque stores data in **fixed-size chunks** linked by a map array, enabling O(1) front/back insertion without ever needing one contiguous allocation. Vector requires a single contiguous block and must copy everything on reallocation.

```cpp
#include <vector>
#include <deque>
#include <chrono>
#include <iostream>
#include <numeric>
#include <queue>

using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_ms(F&& fn) {
    auto start = Clock::now();
    fn();
    auto end = Clock::now();
    return std::chrono::duration<double, std::milli>(end - start).count();
}

// Benchmark 1: front insertion — deque dominates
void bench_front_insert(int n) {
    double vec_time = measure_ms([n]() {
        std::vector<int> v;
        for (int i = 0; i < n; ++i)
            v.insert(v.begin(), i);  // O(n) each time
    });

    double deq_time = measure_ms([n]() {
        std::deque<int> d;
        for (int i = 0; i < n; ++i)
            d.push_front(i);         // O(1) amortized
    });

    std::cout << "Front insert " << n << " elements:\n"
              << "  vector: " << vec_time << " ms\n"
              << "  deque:  " << deq_time << " ms\n\n";
}

// Benchmark 2: back insertion — roughly equal
void bench_back_insert(int n) {
    double vec_time = measure_ms([n]() {
        std::vector<int> v;
        for (int i = 0; i < n; ++i) v.push_back(i);
    });

    double deq_time = measure_ms([n]() {
        std::deque<int> d;
        for (int i = 0; i < n; ++i) d.push_back(i);
    });

    std::cout << "Back insert " << n << " elements:\n"
              << "  vector: " << vec_time << " ms\n"
              << "  deque:  " << deq_time << " ms\n\n";
}

// Benchmark 3: sequential access — vector wins (cache locality)
void bench_sequential_access(int n) {
    std::vector<int> v(n);
    std::deque<int> d(n);
    std::iota(v.begin(), v.end(), 0);
    std::iota(d.begin(), d.end(), 0);

    volatile long long sink = 0;

    double vec_time = measure_ms([&]() {
        long long sum = 0;
        for (int i = 0; i < n; ++i) sum += v[i];
        sink = sum;
    });

    double deq_time = measure_ms([&]() {
        long long sum = 0;
        for (int i = 0; i < n; ++i) sum += d[i];
        sink = sum;
    });

    std::cout << "Sequential access " << n << " elements:\n"
              << "  vector: " << vec_time << " ms\n"
              << "  deque:  " << deq_time << " ms\n\n";
}

// Practical use: BFS — deque is the natural choice
struct TreeNode {
    int val;
    TreeNode* left = nullptr;
    TreeNode* right = nullptr;
    TreeNode(int v) : val(v) {}
};

std::vector<std::vector<int>> level_order(TreeNode* root) {
    std::vector<std::vector<int>> result;
    if (!root) return result;

    std::deque<TreeNode*> q;  // push_back + pop_front = perfect for BFS
    q.push_back(root);

    while (!q.empty()) {
        size_t level_size = q.size();
        result.emplace_back();
        for (size_t i = 0; i < level_size; ++i) {
            TreeNode* node = q.front();
            q.pop_front();  // O(1) — vector would be O(n)
            result.back().push_back(node->val);
            if (node->left) q.push_back(node->left);
            if (node->right) q.push_back(node->right);
        }
    }
    return result;
}

int main() {
    bench_front_insert(100'000);
    bench_back_insert(1'000'000);
    bench_sequential_access(10'000'000);

    // BFS demo
    TreeNode root(1);
    TreeNode l(2), r(3), ll(4), lr(5);
    root.left = &l; root.right = &r;
    l.left = &ll; l.right = &lr;

    auto levels = level_order(&root);
    std::cout << "BFS level order:\n";
    for (auto& lev : levels) {
        for (int v : lev) std::cout << v << " ";
        std::cout << "\n";
    }
}
```

**Choose deque when:** front insertion/deletion is needed, container is huge and contiguous allocation may fail, or you need pointer/reference stability on `push_back`/`push_front`. **Stick with vector** for everything else -- its cache locality advantage is substantial.'''),

    ("cpp_deep/list_vs_vector_cache", r'''Everyone says "never use std::list" but surely linked lists have their place? Can you show a cache performance analysis comparing std::list vs std::vector, and demonstrate the rare cases where list actually wins?''', r'''<think>
This is a great topic. The "never use std::list" advice comes from Bjarne Stroustrup's talks about cache effects.
Key points:
1. std::list allocates each node separately on the heap — terrible cache locality
2. Vector elements are contiguous — CPU prefetcher works perfectly
3. Even insertion in the middle of a vector is often faster than list for small-to-medium sizes because memmove is extremely fast on modern CPUs
4. List wins when: elements are very large (moving is expensive), you need iterator/pointer stability through insertions, you splice between lists (O(1)), or you do lots of middle insertions with a retained iterator
5. For the benchmark: compare middle insertion, iteration sum, and splice operations
6. I should measure both and show the crossover point
7. std::list::splice is O(1) and has no equivalent in vector — that's a genuine win
8. Also list never invalidates iterators to other elements on insert/erase
9. For large objects, list avoids the copy cost on insert, but vector with move semantics narrows this gap
10. The benchmark should use elements of different sizes to show the crossover
11. Need to prevent optimizer from removing computations
12. Show the splice use case clearly — merging sorted lists is a classic
13. Modern alternative: could use std::deque or a flat structure with indices
14. Mention that Stroustrup's benchmark showed vector beating list even for middle insertion up to millions of elements
15. Key insight: cache misses cost ~100 cycles, a memmove of a few KB is cheaper than chasing pointers
</think>

**Cache Performance: `std::list` vs `std::vector`**

Bjarne Stroustrup famously demonstrated that `std::vector` beats `std::list` even for middle insertion in most cases, because cache locality and `memmove` efficiency dominate over algorithmic complexity. Here's the analysis:

```cpp
#include <list>
#include <vector>
#include <chrono>
#include <iostream>
#include <algorithm>
#include <numeric>
#include <random>

using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_us(F&& fn) {
    auto start = Clock::now();
    fn();
    auto end = Clock::now();
    return std::chrono::duration<double, std::micro>(end - start).count();
}

// Benchmark 1: Sequential iteration (vector dominates)
void bench_iteration(int n) {
    std::vector<int> v(n);
    std::list<int> l(n);
    std::iota(v.begin(), v.end(), 0);
    std::iota(l.begin(), l.end(), 0);

    volatile long long sink = 0;

    double vec_us = measure_us([&]() {
        long long sum = 0;
        for (int x : v) sum += x;
        sink = sum;
    });

    double list_us = measure_us([&]() {
        long long sum = 0;
        for (int x : l) sum += x;
        sink = sum;
    });

    std::cout << "Iteration over " << n << " ints:\n"
              << "  vector: " << vec_us << " us\n"
              << "  list:   " << list_us << " us  ("
              << list_us / vec_us << "x slower)\n\n";
}

// Benchmark 2: Sorted insertion (vector often wins for small-medium sizes)
void bench_sorted_insert(int n) {
    std::mt19937 rng(42);
    std::vector<int> data(n);
    for (auto& x : data) x = rng() % (n * 10);

    double vec_us = measure_us([&]() {
        std::vector<int> v;
        v.reserve(n);
        for (int x : data) {
            auto pos = std::lower_bound(v.begin(), v.end(), x);
            v.insert(pos, x);  // O(n) shift but cache-friendly
        }
    });

    double list_us = measure_us([&]() {
        std::list<int> l;
        for (int x : data) {
            // Must walk to find position — O(n) with cache misses
            auto it = l.begin();
            while (it != l.end() && *it < x) ++it;
            l.insert(it, x);  // O(1) insert but O(n) search with pointer chasing
        }
    });

    std::cout << "Sorted insert " << n << " elements:\n"
              << "  vector: " << vec_us << " us\n"
              << "  list:   " << list_us << " us\n\n";
}

// Benchmark 3: WHERE LIST WINS — splice operations (O(1), no copies)
void bench_splice() {
    const int n = 500'000;
    std::list<int> l1, l2;
    for (int i = 0; i < n; ++i) l1.push_back(i * 2);      // evens
    for (int i = 0; i < n; ++i) l2.push_back(i * 2 + 1);  // odds

    // Splice: move all of l2 into middle of l1 in O(1)
    auto mid = std::next(l1.begin(), n / 2);
    double splice_us = measure_us([&]() {
        l1.splice(mid, l2);  // O(1)! Just pointer reassignment
    });

    std::cout << "Splice " << n << " elements into another list:\n"
              << "  list splice: " << splice_us << " us (O(1))\n";

    // Equivalent vector operation: O(n) copy + shift
    std::vector<int> v1(n), v2(n);
    std::iota(v1.begin(), v1.end(), 0);
    std::iota(v2.begin(), v2.end(), n);

    double vec_us = measure_us([&]() {
        v1.insert(v1.begin() + n / 2, v2.begin(), v2.end());
    });

    std::cout << "  vector insert range: " << vec_us << " us (O(n))\n\n";
}

// WHERE LIST WINS: stable iterators through modifications
void demo_iterator_stability() {
    std::list<int> l = {1, 2, 3, 4, 5};

    // Save iterators to specific elements
    auto it3 = std::find(l.begin(), l.end(), 3);
    auto it5 = std::find(l.begin(), l.end(), 5);

    // Insert and erase — our saved iterators remain valid
    l.insert(it3, 99);     // {1, 2, 99, 3, 4, 5}
    l.erase(std::find(l.begin(), l.end(), 2));  // {1, 99, 3, 4, 5}
    l.push_back(6);
    l.push_front(0);

    // it3 and it5 still valid!
    std::cout << "Iterator stability demo:\n"
              << "  *it3 = " << *it3 << " (still 3)\n"
              << "  *it5 = " << *it5 << " (still 5)\n"
              << "  list: ";
    for (int x : l) std::cout << x << " ";
    std::cout << "\n\n";
}

int main() {
    bench_iteration(1'000'000);
    bench_sorted_insert(50'000);
    bench_splice();
    demo_iterator_stability();

    std::cout << "=== When to use std::list ===\n"
              << "1. O(1) splice between lists\n"
              << "2. Iterator/pointer/reference stability required\n"
              << "3. Very large non-movable objects\n"
              << "4. Frequent insert/erase with retained iterators\n"
              << "For everything else: use std::vector.\n";
}
```

**Bottom line:** Cache misses cost ~100+ cycles. A `memmove` of a few KB is often faster than chasing scattered heap pointers. Use `std::list` only when you need O(1) `splice`, guaranteed iterator stability, or you hold iterators to elements and modify the container around them.'''),

    ("cpp_deep/unordered_map_hash_collision", r'''Can you explain how std::unordered_map handles hash collisions internally, what bucket management looks like, and how to diagnose and fix performance degradation from bad hash distributions?''', r'''<think>
This touches on hash table internals in the STL. Key points:
1. std::unordered_map uses separate chaining (linked list per bucket) in all major implementations
2. Load factor = size / bucket_count. Default max_load_factor is 1.0
3. When load factor exceeds max, rehash doubles bucket count and redistributes
4. Bad hash = many collisions = long chains = O(n) lookup instead of O(1)
5. bucket_count(), bucket_size(), load_factor() are diagnostic tools
6. Can use bucket() to find which bucket a key maps to
7. For pathological cases, adversarial inputs can cause all keys to hash to same bucket
8. Solutions: better hash function, reserve/rehash upfront, lower max_load_factor
9. C++20 added heterogeneous lookup for unordered containers with is_transparent
10. I should show: creating a pathological case, diagnosing it, and fixing it
11. Show bucket distribution visualization
12. Mention that GCC/libstdc++ uses prime bucket counts, MSVC uses power-of-2
13. The hash_combine pattern from Boost is useful for composite keys
14. Should also mention that std::hash<int> is usually identity on some implementations
15. Demonstrate the performance cliff when all keys collide
</think>

**Hash Collision Handling and Bucket Management in `std::unordered_map`**

The STL unordered containers use **separate chaining** (each bucket is a linked list). When the load factor exceeds `max_load_factor()` (default 1.0), the table rehashes to roughly double the bucket count. Bad hashes create long chains, degrading O(1) to O(n).

```cpp
#include <unordered_map>
#include <iostream>
#include <string>
#include <chrono>
#include <vector>
#include <numeric>
#include <functional>

using Clock = std::chrono::high_resolution_clock;

// === Diagnostic tool: visualize bucket distribution ===
template <typename Map>
void diagnose_buckets(const Map& m, const std::string& label) {
    std::cout << "--- " << label << " ---\n";
    std::cout << "size: " << m.size()
              << "  buckets: " << m.bucket_count()
              << "  load_factor: " << m.load_factor()
              << "  max_load_factor: " << m.max_load_factor() << "\n";

    size_t max_chain = 0, empty_buckets = 0;
    std::vector<size_t> chain_lengths;

    for (size_t i = 0; i < m.bucket_count(); ++i) {
        size_t bs = m.bucket_size(i);
        chain_lengths.push_back(bs);
        if (bs == 0) ++empty_buckets;
        max_chain = std::max(max_chain, bs);
    }

    double avg_nonempty = 0;
    size_t nonempty = m.bucket_count() - empty_buckets;
    if (nonempty > 0) {
        avg_nonempty = static_cast<double>(m.size()) / nonempty;
    }

    std::cout << "empty buckets: " << empty_buckets << "/" << m.bucket_count()
              << "  max chain: " << max_chain
              << "  avg chain (non-empty): " << avg_nonempty << "\n\n";
}

// === Pathological hash: everything collides ===
struct BadHash {
    size_t operator()(int key) const {
        return 42;  // all keys -> same bucket!
    }
};

// === Good hash with proper distribution ===
struct GoodHash {
    size_t operator()(int key) const {
        // Fibonacci hashing — excellent distribution
        size_t h = static_cast<size_t>(key);
        h ^= h >> 16;
        h *= 0x45d9f3b;
        h ^= h >> 16;
        return h;
    }
};

template <typename Hash>
double bench_lookup(int n, const std::string& label) {
    std::unordered_map<int, int, Hash> m;
    for (int i = 0; i < n; ++i) m[i] = i;

    diagnose_buckets(m, label);

    volatile int sink = 0;
    auto start = Clock::now();
    for (int i = 0; i < n; ++i) {
        sink = m.find(i)->second;
    }
    auto end = Clock::now();
    double ms = std::chrono::duration<double, std::milli>(end - start).count();
    std::cout << label << " lookup " << n << " keys: " << ms << " ms\n\n";
    return ms;
}

// === Rehash and load factor tuning ===
void demo_rehash_tuning() {
    std::unordered_map<int, int> m;

    // Pre-allocate buckets to avoid repeated rehashing during bulk insert
    m.reserve(10'000);  // sets bucket_count so that 10000 elements won't trigger rehash
    std::cout << "After reserve(10000): bucket_count = " << m.bucket_count() << "\n";

    for (int i = 0; i < 10'000; ++i) m[i] = i;
    diagnose_buckets(m, "After 10K inserts with reserve");

    // Lower max_load_factor for faster lookups (more memory, fewer collisions)
    std::unordered_map<int, int> m2;
    m2.max_load_factor(0.5f);  // half the default — sparser table
    for (int i = 0; i < 10'000; ++i) m2[i] = i;
    diagnose_buckets(m2, "max_load_factor=0.5");
}

// === Investigate which bucket a key lands in ===
void demo_bucket_query() {
    std::unordered_map<std::string, int> m = {
        {"alpha", 1}, {"beta", 2}, {"gamma", 3}, {"delta", 4}
    };

    std::cout << "Bucket assignments:\n";
    for (auto& [key, val] : m) {
        size_t b = m.bucket(key);
        std::cout << "  \"" << key << "\" -> bucket " << b
                  << " (chain length: " << m.bucket_size(b) << ")\n";
    }
    std::cout << "\n";
}

int main() {
    const int N = 5'000;

    std::cout << "=== Pathological vs Good Hash ===\n\n";
    double bad_ms = bench_lookup<BadHash>(N, "BadHash (all collisions)");
    double good_ms = bench_lookup<GoodHash>(N, "GoodHash (well distributed)");
    std::cout << "BadHash is " << bad_ms / good_ms << "x slower\n\n";

    std::cout << "=== Rehash Tuning ===\n";
    demo_rehash_tuning();

    std::cout << "=== Bucket Query ===\n";
    demo_bucket_query();
}
```

**Key diagnostics:** Use `bucket_count()`, `bucket_size(i)`, and `load_factor()` to spot long chains. Fix bad distributions with a better hash, `reserve()` to avoid mid-insert rehashing, or a lower `max_load_factor` to trade memory for speed. For pathological inputs (e.g., DoS attacks on hash tables), consider using a seeded hash.'''),

    ("cpp_deep/custom_hash_equality", r'''I need to use a custom struct as a key in std::unordered_map. What's the right way to write a hash function and equality operator? Can you show both the member function approach and the std::hash specialization approach?''', r'''<think>
Custom hash and equality for unordered containers — a common need.
Two approaches:
1. Provide hash and equality as template parameters to unordered_map
2. Specialize std::hash<T> in the std namespace and define operator==
For the hash function:
- Need to combine multiple fields — use hash_combine pattern from Boost
- Or use XOR with bit shifting (simpler but slightly worse distribution)
- C++ has no built-in hash_combine, so we usually write our own
For equality:
- operator== is simplest (defaultable in C++20)
- Or provide a custom comparator functor
Should show:
1. A Point struct with x, y
2. A more complex struct like Employee with string + int
3. The hash_combine technique
4. std::hash specialization approach
5. C++20 defaulted operator== with operator<=>
6. Lambda-based hash/eq for quick prototyping
7. Performance consideration: good hash distribution matters more than hash speed
Let me also mention heterogeneous lookup with is_transparent in C++20
</think>

**Custom Hash and Equality for `std::unordered_map`**

There are multiple approaches: template parameters, `std::hash` specialization, and C++20 defaulted operators. Here's a comprehensive guide:

```cpp
#include <unordered_map>
#include <unordered_set>
#include <iostream>
#include <string>
#include <functional>
#include <cstdint>

// ============================================================
// Utility: hash_combine (not in the standard, borrowed from Boost)
// ============================================================
template <typename T>
inline void hash_combine(size_t& seed, const T& val) {
    seed ^= std::hash<T>{}(val) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
}

// ============================================================
// Approach 1: Functor-based hash + equality as template params
// ============================================================
struct Point {
    double x, y;
};

struct PointHash {
    size_t operator()(const Point& p) const {
        size_t seed = 0;
        hash_combine(seed, p.x);
        hash_combine(seed, p.y);
        return seed;
    }
};

struct PointEqual {
    bool operator()(const Point& a, const Point& b) const {
        return a.x == b.x && a.y == b.y;
    }
};

// Usage: std::unordered_map<Point, std::string, PointHash, PointEqual>

// ============================================================
// Approach 2: std::hash specialization + operator==
// ============================================================
struct Employee {
    std::string name;
    int department;
    int id;

    bool operator==(const Employee& other) const {
        return id == other.id;  // identity is based on ID alone
    }
};

// Specialize std::hash in namespace std
namespace std {
    template <>
    struct hash<Employee> {
        size_t operator()(const Employee& e) const {
            return std::hash<int>{}(e.id);  // hash only the fields used in ==
        }
    };
}
// Now std::unordered_set<Employee> works directly — no extra template args

// ============================================================
// Approach 3: C++20 defaulted operator== and structured hash
// ============================================================
struct Color {
    uint8_t r, g, b, a;

    bool operator==(const Color&) const = default;  // C++20: all fields compared

    // Can also define hash as a member struct
    struct Hash {
        size_t operator()(const Color& c) const {
            // Pack RGBA into a single 32-bit value for perfect hashing
            uint32_t packed = (static_cast<uint32_t>(c.r) << 24) |
                              (static_cast<uint32_t>(c.g) << 16) |
                              (static_cast<uint32_t>(c.b) << 8)  |
                              static_cast<uint32_t>(c.a);
            return std::hash<uint32_t>{}(packed);
        }
    };
};

// ============================================================
// Approach 4: Lambda-based (quick prototyping)
// ============================================================
struct Config {
    std::string section;
    std::string key;
};

// ============================================================
// Approach 5: Composite key with std::pair/tuple
// ============================================================
struct PairHash {
    template <typename T1, typename T2>
    size_t operator()(const std::pair<T1, T2>& p) const {
        size_t seed = 0;
        hash_combine(seed, p.first);
        hash_combine(seed, p.second);
        return seed;
    }
};
// Usage: std::unordered_map<std::pair<int,int>, double, PairHash>

int main() {
    // Approach 1: functor-based
    std::unordered_map<Point, std::string, PointHash, PointEqual> point_labels;
    point_labels[{1.0, 2.0}] = "origin-ish";
    point_labels[{3.0, 4.0}] = "far point";
    std::cout << "Point {1,2}: " << point_labels[{1.0, 2.0}] << "\n";

    // Approach 2: std::hash specialization
    std::unordered_set<Employee> staff;
    staff.insert({"Alice", 1, 1001});
    staff.insert({"Bob", 2, 1002});
    staff.insert({"Alice Clone", 3, 1001});  // same ID — won't insert (duplicate)
    std::cout << "Staff size: " << staff.size() << " (expected 2)\n";

    // Approach 3: member Hash struct
    std::unordered_map<Color, std::string, Color::Hash> color_names;
    color_names[{255, 0, 0, 255}] = "red";
    color_names[{0, 255, 0, 255}] = "green";
    std::cout << "Color {255,0,0,255}: " << color_names[{255, 0, 0, 255}] << "\n";

    // Approach 4: lambda-based
    auto cfg_hash = [](const Config& c) {
        size_t seed = 0;
        hash_combine(seed, c.section);
        hash_combine(seed, c.key);
        return seed;
    };
    auto cfg_eq = [](const Config& a, const Config& b) {
        return a.section == b.section && a.key == b.key;
    };
    std::unordered_map<Config, std::string,
                       decltype(cfg_hash), decltype(cfg_eq)> config(16, cfg_hash, cfg_eq);
    config[{"database", "host"}] = "localhost";
    std::cout << "Config: " << config[{"database", "host"}] << "\n";

    // Approach 5: pair keys
    std::unordered_map<std::pair<int,int>, double, PairHash> grid;
    grid[{0, 0}] = 1.0;
    grid[{1, 2}] = 3.5;
    std::cout << "Grid[1,2]: " << grid[{1, 2}] << "\n";
}
```

**Critical rule:** Only hash the fields used in `operator==`. If two objects compare equal, they **must** produce the same hash. The `hash_combine` pattern from Boost (magic constant `0x9e3779b9` = golden ratio) provides excellent distribution for composite keys.'''),

    ("cpp_deep/map_custom_comparator", r'''How do I use std::map with a custom comparator for complex keys? I need to sort a map of intervals [low, high] by their start point, then by length if starts are equal. Show the proper way in C++17 and C++20.''', r'''<think>
std::map with custom comparator for interval keys. Need to cover:
1. The comparator must define a strict weak ordering
2. In C++17: functor or function pointer or lambda
3. In C++20: can use operator<=> (three-way comparison)
4. Important: if two keys are "equivalent" under the comparator (neither is less than the other), map treats them as the same key
5. For intervals: sort by start, then by length (end - start)
6. Need to be careful: the comparator defines both ordering AND uniqueness
7. Show functor approach, lambda approach, and C++20 spaceship approach
8. Also show transparent comparator for heterogeneous lookup
9. Demonstrate that two intervals with same start and length would be "equal" in the map
10. Should show a practical use case like an interval scheduling or merge problem
11. The comparator must be consistent: if comp(a,b) is true, comp(b,a) must be false
12. If neither comp(a,b) nor comp(b,a), they're equivalent (same key)
13. Show the extract/merge operations available since C++17
14. Maybe show std::map::contains() from C++20 too
15. Keep the code compilable and practical
</think>

**`std::map` with Custom Comparator for Complex Keys**

The comparator defines both ordering and equivalence. If `!comp(a,b) && !comp(b,a)`, the map treats `a` and `b` as the **same key**. This must be a strict weak ordering.

```cpp
#include <map>
#include <set>
#include <iostream>
#include <string>
#include <functional>
#include <cassert>

// ============================================================
// The interval type
// ============================================================
struct Interval {
    int low, high;

    int length() const { return high - low; }

    friend std::ostream& operator<<(std::ostream& os, const Interval& iv) {
        return os << "[" << iv.low << ", " << iv.high << "]";
    }
};

// ============================================================
// C++17 Approach 1: Functor comparator
// ============================================================
struct IntervalCompare {
    bool operator()(const Interval& a, const Interval& b) const {
        if (a.low != b.low) return a.low < b.low;     // primary: start point
        return a.length() < b.length();                // secondary: shorter first
    }
};

// ============================================================
// C++17 Approach 2: Lambda comparator
// ============================================================
auto make_interval_map_lambda() {
    auto cmp = [](const Interval& a, const Interval& b) {
        if (a.low != b.low) return a.low < b.low;
        return a.length() < b.length();
    };
    return std::map<Interval, std::string, decltype(cmp)>(cmp);
}

// ============================================================
// C++20 Approach: operator<=> (spaceship)
// ============================================================
struct Interval20 {
    int low, high;

    int length() const { return high - low; }

    // Define ordering for use as map key — no separate comparator needed
    auto operator<=>(const Interval20& other) const {
        if (auto cmp = low <=> other.low; cmp != 0) return cmp;
        return length() <=> other.length();
    }

    bool operator==(const Interval20& other) const = default;

    friend std::ostream& operator<<(std::ostream& os, const Interval20& iv) {
        return os << "[" << iv.low << ", " << iv.high << "]";
    }
};

// ============================================================
// Practical: Interval scheduling with custom-sorted map
// ============================================================
void interval_scheduling_demo() {
    std::map<Interval, std::string, IntervalCompare> schedule;

    schedule[{9, 10}]  = "Standup";
    schedule[{9, 12}]  = "Workshop";     // same start, longer → sorted after
    schedule[{13, 14}] = "Lunch review";
    schedule[{10, 11}] = "Code review";
    schedule[{10, 15}] = "Deep work";    // same start as code review, longer

    std::cout << "=== Schedule (sorted by start, then length) ===\n";
    for (const auto& [interval, name] : schedule) {
        std::cout << "  " << interval << " len=" << interval.length()
                  << " -> " << name << "\n";
    }

    // Equivalence test: same start and same length = same key
    Interval a{9, 10}, b{9, 10};
    IntervalCompare cmp;
    bool equivalent = !cmp(a, b) && !cmp(b, a);
    std::cout << "\n[9,10] and [9,10] are equivalent (same key): "
              << std::boolalpha << equivalent << "\n";
}

// ============================================================
// C++20 map with spaceship operator — no comparator template param
// ============================================================
void cpp20_demo() {
    std::map<Interval20, std::string> events;

    events[{8, 9}]   = "Breakfast";
    events[{8, 12}]  = "Morning block";
    events[{12, 13}] = "Lunch";
    events[{14, 16}] = "Afternoon session";

    std::cout << "\n=== C++20 spaceship-ordered map ===\n";
    for (const auto& [iv, name] : events) {
        std::cout << "  " << iv << " -> " << name << "\n";
    }

    // C++20: contains()
    if (events.contains({12, 13})) {
        std::cout << "\nFound lunch slot!\n";
    }
}

// ============================================================
// Strict weak ordering violation demo (what NOT to do)
// ============================================================
void show_ordering_rules() {
    std::cout << "\n=== Strict Weak Ordering Rules ===\n";
    std::cout << "1. Irreflexivity:   comp(a, a) must be false\n";
    std::cout << "2. Asymmetry:       if comp(a,b) then !comp(b,a)\n";
    std::cout << "3. Transitivity:    if comp(a,b) and comp(b,c) then comp(a,c)\n";
    std::cout << "4. Equivalence transitivity: if equiv(a,b) and equiv(b,c) then equiv(a,c)\n";
    std::cout << "Violating these causes undefined behavior (crashes, infinite loops).\n";

    // BAD: using <= instead of < violates irreflexivity
    // auto bad_cmp = [](int a, int b) { return a <= b; }; // DO NOT USE
}

int main() {
    interval_scheduling_demo();
    cpp20_demo();
    show_ordering_rules();
}
```

**Key takeaways:** The comparator is the single source of truth for both ordering and key identity. Use `<` (not `<=`), ensure transitivity, and remember that "equivalent" keys are treated as duplicates. C++20's `operator<=>` eliminates the need for separate comparator structs entirely.'''),

    ("cpp_deep/set_operations", r'''Show me how to perform set operations (union, intersection, difference, symmetric difference) on std::set in C++17 and C++20 with ranges. I need both the algorithm-based approach and the merge/extract node approach.''', r'''<think>
Set operations in C++ — several approaches:
1. STL algorithms: set_union, set_intersection, set_difference, set_symmetric_difference
   - These work on sorted ranges, not just std::set
   - Need output iterators (back_inserter or inserter)
2. std::set::merge() (C++17) — transfers nodes, modifying source
3. Node extraction and insertion (C++17) — set::extract() and set::insert(node)
4. C++20 ranges versions of the algorithms
5. Should show all four set operations
6. Important: STL set algorithms require sorted input
7. Show the output_iterator approach and the node-based approach
8. Mention performance: algorithm approach copies, merge/extract moves nodes
9. Also show the ranges approach with views
10. Need practical examples
11. set::merge modifies the source set, unlike algorithm versions
12. The algorithms produce output into a separate container
13. Should demonstrate with both ints and strings
14. Show how merge handles duplicates (leaves them in source)
15. Keep it compilable
</think>

**Set Operations in C++17 and C++20**

```cpp
#include <set>
#include <vector>
#include <algorithm>
#include <iostream>
#include <iterator>
#include <string>

template <typename Container>
void print(const std::string& label, const Container& c) {
    std::cout << label << ": { ";
    for (const auto& x : c) std::cout << x << " ";
    std::cout << "}\n";
}

// ============================================================
// Approach 1: STL algorithms (works on any sorted range)
// ============================================================
void algorithm_approach() {
    std::cout << "=== STL Algorithm Approach ===\n";
    std::set<int> a = {1, 2, 3, 4, 5};
    std::set<int> b = {3, 4, 5, 6, 7};

    // Union: elements in A or B
    std::set<int> result;
    std::set_union(a.begin(), a.end(), b.begin(), b.end(),
                   std::inserter(result, result.begin()));
    print("A ∪ B", result);

    // Intersection: elements in both A and B
    result.clear();
    std::set_intersection(a.begin(), a.end(), b.begin(), b.end(),
                          std::inserter(result, result.begin()));
    print("A ∩ B", result);

    // Difference: elements in A but not B
    result.clear();
    std::set_difference(a.begin(), a.end(), b.begin(), b.end(),
                        std::inserter(result, result.begin()));
    print("A \\ B", result);

    // Symmetric difference: elements in A or B but not both
    result.clear();
    std::set_symmetric_difference(a.begin(), a.end(), b.begin(), b.end(),
                                  std::inserter(result, result.begin()));
    print("A △ B", result);
    std::cout << "\n";
}

// ============================================================
// Approach 2: Node-based merge and extract (C++17)
// ============================================================
void node_approach() {
    std::cout << "=== Node-Based Approach (C++17) ===\n";

    // merge(): transfers nodes from source to target (no copies!)
    std::set<std::string> team_a = {"Alice", "Bob", "Charlie"};
    std::set<std::string> team_b = {"Charlie", "Dave", "Eve"};

    print("Team A before merge", team_a);
    print("Team B before merge", team_b);

    // merge moves non-duplicate nodes from team_b into team_a
    team_a.merge(team_b);
    print("Team A after merge ", team_a);
    print("Team B after merge ", team_b);  // "Charlie" remains (duplicate)
    std::cout << "\n";

    // extract(): remove a node without deallocating, reinsert elsewhere
    std::set<int> source = {10, 20, 30, 40, 50};
    std::set<int> dest;

    auto node = source.extract(30);  // O(log n), no allocation
    if (!node.empty()) {
        node.value() = 35;           // can modify the value!
        dest.insert(std::move(node));
    }
    print("Source after extract", source);
    print("Dest after insert  ", dest);
    std::cout << "\n";
}

// ============================================================
// Approach 3: Using sorted vectors (often faster for bulk ops)
// ============================================================
void vector_approach() {
    std::cout << "=== Sorted Vector Approach ===\n";
    std::vector<int> a = {1, 2, 3, 4, 5};  // already sorted
    std::vector<int> b = {3, 4, 5, 6, 7};  // already sorted

    std::vector<int> union_result;
    std::set_union(a.begin(), a.end(), b.begin(), b.end(),
                   std::back_inserter(union_result));
    print("Union", union_result);

    std::vector<int> inter_result;
    std::set_intersection(a.begin(), a.end(), b.begin(), b.end(),
                          std::back_inserter(inter_result));
    print("Intersection", inter_result);

    // Check subset relationship: is B a subset of A?
    bool b_subset_a = std::includes(a.begin(), a.end(), b.begin(), b.end());
    std::cout << "B ⊆ A: " << std::boolalpha << b_subset_a << "\n\n";
}

// ============================================================
// Approach 4: Practical — tag system with set operations
// ============================================================
void practical_tag_system() {
    std::cout << "=== Practical: Tag-Based Query ===\n";

    using TagSet = std::set<std::string>;
    struct Article {
        std::string title;
        TagSet tags;
    };

    std::vector<Article> articles = {
        {"Intro to C++",       {"cpp", "beginner", "tutorial"}},
        {"Advanced Templates", {"cpp", "advanced", "templates"}},
        {"Rust Ownership",     {"rust", "beginner", "memory"}},
        {"C++ Memory Model",   {"cpp", "advanced", "memory"}},
    };

    // Find articles matching ALL query tags (intersection check)
    TagSet query = {"cpp", "advanced"};
    print("Query tags", query);

    std::cout << "Articles matching ALL query tags:\n";
    for (const auto& article : articles) {
        TagSet common;
        std::set_intersection(
            article.tags.begin(), article.tags.end(),
            query.begin(), query.end(),
            std::inserter(common, common.begin()));

        if (common == query) {  // all query tags present
            std::cout << "  \"" << article.title << "\" tags=";
            print("", article.tags);
        }
    }

    // Find all unique tags across articles (union)
    TagSet all_tags;
    for (const auto& article : articles) {
        TagSet merged;
        std::set_union(all_tags.begin(), all_tags.end(),
                       article.tags.begin(), article.tags.end(),
                       std::inserter(merged, merged.begin()));
        all_tags = std::move(merged);
    }
    print("\nAll unique tags", all_tags);
}

int main() {
    algorithm_approach();
    node_approach();
    vector_approach();
    practical_tag_system();
}
```

**Performance notes:** The STL set algorithms are O(n+m) on sorted ranges. Node-based `merge`/`extract` avoids allocation and copying entirely -- ideal for moving elements between sets. For bulk set operations on large data, sorted `std::vector` with `set_union`/`set_intersection` often outperforms `std::set` due to cache locality.'''),

    ("cpp_deep/priority_queue_custom_comparator", r'''I need a priority queue in C++ that supports custom comparison for a task scheduler (priority + timestamp ordering). Show std::priority_queue with custom comparator and explain why there's no decrease-key operation.''', r'''<think>
Priority queue with custom comparator for task scheduling:
1. std::priority_queue is a max-heap by default (using std::less)
2. To make a min-heap, use std::greater
3. For custom types, provide a comparator as template parameter
4. The comparator is "less" in the sense that the element that compares "less" has LOWER priority
5. No decrease-key because the heap doesn't track element positions
6. Workaround: lazy deletion — mark entries as invalid, skip on pop
7. For actual decrease-key, need a custom heap (e.g., Fibonacci heap) or use a set-based approach
8. Show the task scheduler example with priority + timestamp
9. Also show the lazy deletion pattern for updates
10. Compare with using std::set as a priority queue (supports erase/reinsert)
11. The three template params: value_type, container_type, comparator
12. Container is usually vector (default) but could be deque
13. Show make_heap/push_heap/pop_heap as the lower-level interface
14. For Dijkstra's, the lazy deletion approach is standard
15. Keep it practical with a task scheduler
</think>

**`std::priority_queue` with Custom Comparator and Decrease-Key Workaround**

```cpp
#include <queue>
#include <vector>
#include <set>
#include <iostream>
#include <string>
#include <functional>
#include <unordered_map>

// ============================================================
// Task struct for scheduling
// ============================================================
struct Task {
    int id;
    int priority;       // higher = more urgent
    uint64_t timestamp; // earlier = should run first at same priority
    std::string name;
};

// ============================================================
// Custom comparator: highest priority first, then earliest timestamp
// Note: operator() returns true if 'a' has LOWER priority than 'b'
// (because priority_queue is a max-heap: "less" = lower priority)
// ============================================================
struct TaskCompare {
    bool operator()(const Task& a, const Task& b) const {
        if (a.priority != b.priority)
            return a.priority < b.priority;   // higher priority wins
        return a.timestamp > b.timestamp;     // earlier timestamp wins (tie-break)
    }
};

void basic_priority_queue() {
    std::cout << "=== Task Scheduler with Custom Priority Queue ===\n";

    std::priority_queue<Task, std::vector<Task>, TaskCompare> pq;

    pq.push({1, 3, 100, "Low urgency task"});
    pq.push({2, 10, 105, "Critical fix"});
    pq.push({3, 10, 101, "Critical older task"});  // same priority, earlier timestamp
    pq.push({4, 5, 102, "Medium task"});
    pq.push({5, 1, 99, "Background job"});

    std::cout << "Processing order:\n";
    while (!pq.empty()) {
        const auto& t = pq.top();
        std::cout << "  [pri=" << t.priority << " ts=" << t.timestamp
                  << "] " << t.name << "\n";
        pq.pop();
    }
}

// ============================================================
// Min-heap: just use std::greater
// ============================================================
void min_heap_demo() {
    std::cout << "\n=== Min-Heap (smallest first) ===\n";
    std::priority_queue<int, std::vector<int>, std::greater<int>> min_pq;

    for (int x : {5, 1, 3, 9, 2}) min_pq.push(x);

    while (!min_pq.empty()) {
        std::cout << min_pq.top() << " ";
        min_pq.pop();
    }
    std::cout << "\n";
}

// ============================================================
// Why no decrease-key? Workaround: lazy deletion
// ============================================================
void lazy_deletion_dijkstra() {
    std::cout << "\n=== Lazy Deletion Pattern (Dijkstra-style) ===\n";

    // Simulate Dijkstra: nodes 0-4, edges with weights
    const int N = 5;
    using Edge = std::pair<int, int>;  // {weight, node}
    std::vector<std::vector<Edge>> graph(N);
    graph[0] = {{1, 1}, {4, 2}};
    graph[1] = {{1, 2}, {6, 3}};
    graph[2] = {{1, 3}, {2, 4}};
    graph[3] = {{1, 4}};

    std::vector<int> dist(N, INT_MAX);
    dist[0] = 0;

    // Min-heap of {distance, node}
    std::priority_queue<Edge, std::vector<Edge>, std::greater<Edge>> pq;
    pq.push({0, 0});

    while (!pq.empty()) {
        auto [d, u] = pq.top();
        pq.pop();

        // LAZY DELETION: skip if we've already found a better path
        if (d > dist[u]) continue;

        for (auto [w, v] : graph[u]) {
            if (dist[u] + w < dist[v]) {
                dist[v] = dist[u] + w;
                pq.push({dist[v], v});  // "decrease-key" by inserting new entry
                // old entry remains but will be skipped by the check above
            }
        }
    }

    for (int i = 0; i < N; ++i) {
        std::cout << "  dist[0 -> " << i << "] = " << dist[i] << "\n";
    }
}

// ============================================================
// Alternative: std::set as a priority queue (supports decrease-key)
// ============================================================
void set_as_priority_queue() {
    std::cout << "\n=== std::set as Priority Queue (true decrease-key) ===\n";

    // set is ordered, supports erase + reinsert = decrease-key
    using Entry = std::pair<int, int>;  // {priority, id}
    std::set<Entry> pq_set;

    pq_set.insert({5, 1});
    pq_set.insert({3, 2});
    pq_set.insert({8, 3});

    // "Decrease key" for id=3: change priority 8 -> 1
    pq_set.erase({8, 3});
    pq_set.insert({1, 3});

    std::cout << "Pop order (min-first):\n";
    while (!pq_set.empty()) {
        auto [pri, id] = *pq_set.begin();
        std::cout << "  id=" << id << " priority=" << pri << "\n";
        pq_set.erase(pq_set.begin());
    }

    std::cout << "\nstd::set gives O(log n) decrease-key via erase+insert,\n"
              << "whereas priority_queue has no decrease-key (use lazy deletion).\n";
}

int main() {
    basic_priority_queue();
    min_heap_demo();
    lazy_deletion_dijkstra();
    set_as_priority_queue();
}
```

**Why no `decrease_key`?** The binary heap inside `std::priority_queue` doesn't track element positions, so there's no way to find and update a specific element in O(log n). The standard workaround is **lazy deletion**: push a new entry with the updated priority and skip stale entries on pop. For algorithms needing true decrease-key (like Dijkstra's), `std::set` with erase/reinsert works at O(log n) per operation.'''),

    ("cpp_deep/flat_map_cpp23", r'''C++23 introduces std::flat_map. How does it differ from std::map in terms of memory layout and performance? When should I use it?''', r'''<think>
std::flat_map is a new C++23 container adaptor:
1. Stores keys and values in two separate sorted contiguous containers (usually vectors)
2. Unlike std::map which uses a red-black tree with node-based allocation
3. Benefits: cache-friendly iteration, less memory overhead (no tree node pointers), better for read-heavy workloads
4. Drawbacks: insertion/deletion is O(n) due to shifting elements, iterator invalidation on insert
5. Lookup is binary search on contiguous memory — faster constant factor than tree traversal
6. Similar to boost::flat_map which has been around for years
7. Construction from sorted range is O(n), from unsorted is O(n log n)
8. flat_map<K,V> template params include key container and value container types
9. Memory usage: no left/right/parent pointers per node (~3 pointers * 8 bytes = 24 bytes per node saved)
10. For small maps (< few hundred elements), flat_map dominates
11. For large maps with many insertions, std::map is better
12. flat_set also exists
13. sorted_unique_t tag for constructing from pre-sorted data
14. Show a benchmark comparing the two
15. Mention that it's a drop-in replacement API-wise
</think>

**`std::flat_map` (C++23) vs `std::map` -- Performance Tradeoffs**

`std::flat_map` stores keys and values in **sorted contiguous arrays** (typically `std::vector`), unlike `std::map`'s red-black tree. This changes the performance profile fundamentally.

```cpp
#include <iostream>
#include <map>
#include <vector>
#include <string>
#include <algorithm>
#include <chrono>
#include <random>
#include <numeric>
#include <cassert>

// If your compiler supports C++23 <flat_map>, uncomment:
// #include <flat_map>

// Otherwise, here is a simplified flat_map to demonstrate the concept:
template <typename Key, typename Value, typename Compare = std::less<Key>>
class FlatMap {
    std::vector<Key> keys_;
    std::vector<Value> values_;
    Compare comp_;

public:
    using iterator = typename std::vector<Key>::const_iterator;

    size_t size() const { return keys_.size(); }
    bool empty() const { return keys_.empty(); }

    // O(log n) lookup via binary search on contiguous memory
    const Value* find(const Key& key) const {
        auto it = std::lower_bound(keys_.begin(), keys_.end(), key, comp_);
        if (it != keys_.end() && !comp_(key, *it)) {
            size_t idx = static_cast<size_t>(it - keys_.begin());
            return &values_[idx];
        }
        return nullptr;
    }

    // O(n) insertion due to shifting
    void insert(const Key& key, const Value& value) {
        auto it = std::lower_bound(keys_.begin(), keys_.end(), key, comp_);
        if (it != keys_.end() && !comp_(key, *it)) {
            size_t idx = static_cast<size_t>(it - keys_.begin());
            values_[idx] = value;  // update existing
            return;
        }
        size_t idx = static_cast<size_t>(it - keys_.begin());
        keys_.insert(keys_.begin() + static_cast<ptrdiff_t>(idx), key);
        values_.insert(values_.begin() + static_cast<ptrdiff_t>(idx), value);
    }

    Value& operator[](const Key& key) {
        auto it = std::lower_bound(keys_.begin(), keys_.end(), key, comp_);
        if (it != keys_.end() && !comp_(key, *it)) {
            size_t idx = static_cast<size_t>(it - keys_.begin());
            return values_[idx];
        }
        size_t idx = static_cast<size_t>(it - keys_.begin());
        keys_.insert(keys_.begin() + static_cast<ptrdiff_t>(idx), key);
        values_.insert(values_.begin() + static_cast<ptrdiff_t>(idx), Value{});
        return values_[idx];
    }

    // O(n) iteration — contiguous, cache-friendly
    template <typename Fn>
    void for_each(Fn fn) const {
        for (size_t i = 0; i < keys_.size(); ++i) {
            fn(keys_[i], values_[i]);
        }
    }

    // Construct from sorted unique data: O(n)
    static FlatMap from_sorted(std::vector<Key> keys, std::vector<Value> values) {
        FlatMap fm;
        fm.keys_ = std::move(keys);
        fm.values_ = std::move(values);
        return fm;
    }
};

using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_us(F&& fn) {
    auto start = Clock::now();
    fn();
    return std::chrono::duration<double, std::micro>(Clock::now() - start).count();
}

void bench_lookup(int n) {
    std::mt19937 rng(42);
    std::vector<int> data(n);
    std::iota(data.begin(), data.end(), 0);
    std::shuffle(data.begin(), data.end(), rng);

    // Build std::map
    std::map<int, int> tree_map;
    for (int x : data) tree_map[x] = x * 2;

    // Build FlatMap
    FlatMap<int, int> flat;
    for (int x : data) flat[x] = x * 2;

    // Benchmark lookups
    volatile int sink = 0;
    std::shuffle(data.begin(), data.end(), rng);

    double tree_us = measure_us([&]() {
        for (int x : data) sink = tree_map.find(x)->second;
    });

    double flat_us = measure_us([&]() {
        for (int x : data) sink = *flat.find(x);
    });

    std::cout << "Lookup " << n << " elements:\n"
              << "  std::map:  " << tree_us << " us\n"
              << "  flat_map:  " << flat_us << " us\n"
              << "  speedup:   " << tree_us / flat_us << "x\n\n";
}

void bench_iteration(int n) {
    std::map<int, int> tree_map;
    FlatMap<int, int> flat;
    for (int i = 0; i < n; ++i) { tree_map[i] = i; flat[i] = i; }

    volatile long long sink = 0;

    double tree_us = measure_us([&]() {
        long long sum = 0;
        for (auto& [k, v] : tree_map) sum += v;
        sink = sum;
    });

    double flat_us = measure_us([&]() {
        long long sum = 0;
        flat.for_each([&](int, int v) { sum += v; });
        sink = sum;
    });

    std::cout << "Iteration " << n << " elements:\n"
              << "  std::map:  " << tree_us << " us\n"
              << "  flat_map:  " << flat_us << " us\n"
              << "  speedup:   " << tree_us / flat_us << "x\n\n";
}

void memory_comparison() {
    std::cout << "=== Memory Layout Comparison ===\n";
    std::cout << "std::map<int,int> node overhead:\n"
              << "  ~48 bytes per node (left, right, parent ptrs + color + key + value)\n"
              << "  1000 entries ≈ 48KB + allocator overhead\n\n";
    std::cout << "flat_map<int,int> overhead:\n"
              << "  8 bytes per entry (4 key + 4 value, contiguous)\n"
              << "  1000 entries ≈ 8KB total\n"
              << "  6x less memory, fully cache-line friendly\n\n";
}

int main() {
    memory_comparison();

    std::cout << "=== Benchmark: Lookup ===\n";
    bench_lookup(1'000);
    bench_lookup(100'000);

    std::cout << "=== Benchmark: Iteration ===\n";
    bench_iteration(100'000);

    std::cout << "=== When to use flat_map ===\n"
              << "1. Read-heavy workloads (many lookups, few insertions)\n"
              << "2. Small-to-medium maps (< 10K elements)\n"
              << "3. Iteration-heavy code (contiguous memory = fast scans)\n"
              << "4. Memory-constrained environments\n\n"
              << "=== When to stick with std::map ===\n"
              << "1. Frequent insertions/deletions in large maps\n"
              << "2. Iterator stability required\n"
              << "3. Pointer/reference stability required\n"
              << "4. Exception safety on insert (flat_map may partially modify)\n";
}
```

**Summary:** `flat_map` trades O(n) insert for dramatically faster lookup and iteration due to cache locality. Use it for read-heavy, build-once-query-many scenarios. It uses ~6x less memory than `std::map` for small types. Think of it as a sorted `vector<pair<K,V>>` with a map-like API.'''),

    ("cpp_deep/array_vs_c_array", r'''People say std::array has zero overhead compared to C arrays. Can you prove this by examining the generated assembly? Also show cases where std::array provides safety that C arrays don't.''', r'''<think>
This is about proving zero-overhead abstraction with std::array.
Key points:
1. std::array is a thin wrapper around a C array — no heap allocation, no extra members
2. sizeof(std::array<int,10>) == sizeof(int[10]) == 40
3. Same assembly generated for access operations
4. Benefits: bounds checking with .at(), doesn't decay to pointer, knows its size, works with STL algorithms, can be returned from functions
5. For the "assembly proof", I'll show equivalent code and indicate the assembly would be identical
6. Can't actually run a disassembler here, but I can show static_assert proofs of size equality and demonstrate optimization equivalence
7. Show the safety features: at() throws, size() works, no array-to-pointer decay bugs
8. Show the classic C array bugs that std::array prevents
9. C arrays can't be assigned, compared, or returned — std::array can
10. std::array works with structured bindings in C++17
11. Show constexpr usage — std::array is fully constexpr since C++17
12. Mention CTAD (Class Template Argument Deduction) in C++17: std::array{1,2,3}
13. The zero-overhead claim: compiler optimizes identically
14. Show a practical example where C array would be buggy
15. Include static_asserts to prove size and layout equivalence
</think>

**`std::array` vs C Array -- Zero Overhead Proof and Safety**

```cpp
#include <array>
#include <iostream>
#include <algorithm>
#include <numeric>
#include <cassert>
#include <cstring>
#include <type_traits>
#include <stdexcept>

// ============================================================
// Proof 1: Identical size and layout
// ============================================================
void prove_zero_overhead() {
    static_assert(sizeof(std::array<int, 10>) == sizeof(int[10]),
                  "std::array has same size as C array");

    static_assert(sizeof(std::array<double, 5>) == sizeof(double[5]),
                  "Same for doubles");

    static_assert(sizeof(std::array<char, 100>) == sizeof(char[100]),
                  "Same for chars");

    // std::array is trivially copyable when T is — no hidden vtable, no overhead
    static_assert(std::is_trivially_copyable_v<std::array<int, 10>>,
                  "std::array<int,10> is trivially copyable");

    // Standard layout — same memory layout as C array
    static_assert(std::is_standard_layout_v<std::array<int, 10>>,
                  "std::array has standard layout");

    // data() returns pointer to first element, just like C array name
    std::array<int, 5> arr = {1, 2, 3, 4, 5};
    int c_arr[5] = {1, 2, 3, 4, 5};

    // Can memcpy between them — identical binary representation
    static_assert(sizeof(arr) == sizeof(c_arr));
    assert(std::memcmp(arr.data(), c_arr, sizeof(c_arr)) == 0);

    std::cout << "sizeof(std::array<int,10>) = " << sizeof(std::array<int, 10>) << "\n";
    std::cout << "sizeof(int[10])            = " << sizeof(int[10]) << "\n";
    std::cout << "Zero overhead confirmed.\n\n";
}

// ============================================================
// Proof 2: Same generated code (compile with -O2 and compare)
// ============================================================
// These two functions generate IDENTICAL assembly at -O2:

int sum_c_array(const int arr[], int n) {
    int total = 0;
    for (int i = 0; i < n; ++i) total += arr[i];
    return total;
}

int sum_std_array(const std::array<int, 5>& arr) {
    int total = 0;
    for (size_t i = 0; i < arr.size(); ++i) total += arr[i];
    return total;
    // Compiler sees: arr.data()[i] which is just pointer + offset
    // Identical to C array access after inlining
}

// ============================================================
// Safety feature 1: Bounds checking with .at()
// ============================================================
void bounds_checking_demo() {
    std::cout << "=== Bounds Checking ===\n";

    std::array<int, 5> arr = {10, 20, 30, 40, 50};

    // operator[] — no bounds check (same as C array)
    // arr[10]; // undefined behavior, same as C array — no protection

    // .at() — bounds check with exception
    try {
        int val = arr.at(10);  // throws std::out_of_range
        (void)val;
    } catch (const std::out_of_range& e) {
        std::cout << "Caught: " << e.what() << "\n";
    }

    // C array equivalent: NO WAY to bounds-check
    // int c_arr[5]; c_arr[10]; // silent UB
    std::cout << "\n";
}

// ============================================================
// Safety feature 2: No pointer decay
// ============================================================

// C array decays to pointer — loses size information
void process_c(int arr[5]) {
    // sizeof(arr) is sizeof(int*), NOT sizeof(int[5])!
    // This is a common bug source
    std::cout << "C array in function: sizeof=" << sizeof(arr)
              << " (just a pointer!)\n";
}

// std::array preserves size
void process_std(const std::array<int, 5>& arr) {
    std::cout << "std::array in function: sizeof=" << sizeof(arr)
              << " size()=" << arr.size() << " (size preserved!)\n";
}

// ============================================================
// Safety feature 3: Can be returned, assigned, compared
// ============================================================
std::array<int, 3> make_array(int a, int b, int c) {
    return {a, b, c};  // C arrays CANNOT be returned from functions
}

void return_and_compare_demo() {
    std::cout << "\n=== Return, Assign, Compare ===\n";

    auto a = make_array(1, 2, 3);
    auto b = make_array(1, 2, 3);
    auto c = make_array(4, 5, 6);

    // Assignment (C arrays can't do this)
    auto d = a;
    std::cout << "Assignment works: d[0]=" << d[0] << "\n";

    // Comparison (C arrays compare pointers, not contents!)
    std::cout << "a == b: " << std::boolalpha << (a == b) << "\n";
    std::cout << "a == c: " << (a == c) << "\n";
    std::cout << "a < c:  " << (a < c) << " (lexicographic)\n";

    // C array comparison bug:
    int x[3] = {1, 2, 3};
    int y[3] = {1, 2, 3};
    // (x == y) compares POINTERS, always false! Silent bug.
    std::cout << "C array x==y: " << (x == y) << " (compares pointers!)\n\n";
}

// ============================================================
// C++17 bonuses: CTAD, structured bindings, constexpr
// ============================================================
void cpp17_features() {
    std::cout << "=== C++17 Features ===\n";

    // CTAD (Class Template Argument Deduction)
    std::array arr = {1, 2, 3, 4, 5};  // deduces std::array<int, 5>

    // Structured bindings
    std::array<int, 3> point = {10, 20, 30};
    auto [x, y, z] = point;
    std::cout << "Structured binding: x=" << x << " y=" << y << " z=" << z << "\n";

    // constexpr — entire computation at compile time
    constexpr std::array<int, 5> ca = {5, 3, 1, 4, 2};
    constexpr int first = ca.front();
    constexpr int last = ca.back();
    static_assert(first == 5 && last == 2);

    // Works with all STL algorithms
    std::array<int, 5> sorted_arr = {5, 3, 1, 4, 2};
    std::sort(sorted_arr.begin(), sorted_arr.end());
    int sum = std::accumulate(sorted_arr.begin(), sorted_arr.end(), 0);
    std::cout << "Sorted sum: " << sum << "\n";
    std::cout << "fill, swap, and all <algorithm> functions work naturally.\n";
}

int main() {
    prove_zero_overhead();
    bounds_checking_demo();
    process_c(nullptr);   // can pass nullptr to C array param! (UB on use)
    std::array<int, 5> arr = {1, 2, 3, 4, 5};
    process_std(arr);
    return_and_compare_demo();
    cpp17_features();
}
```

**Bottom line:** `std::array` generates identical machine code as C arrays at `-O2`. It adds: bounds-checked `.at()`, no pointer decay, value semantics (copy, compare, return), STL compatibility, and `constexpr` support. There is literally no reason to use C arrays in modern C++.'''),

    ("cpp_deep/custom_random_access_iterator", r'''I need to write a custom random access iterator for a circular buffer class. Show me the full implementation with all required iterator traits and operations, compatible with STL algorithms.''', r'''<think>
Custom random access iterator — this is one of the more complex C++ tasks.
Need to implement:
1. Iterator category tag: random_access_iterator_tag
2. Required types: value_type, difference_type, pointer, reference, iterator_category
3. Operations: *, ->, ++, --, +=, -=, +, -, [], ==, !=, <, >, <=, >=
4. For C++20: can use concepts instead of traits, but C++17 compatibility is important
5. Circular buffer: wraps around a fixed-size array
6. The iterator needs to handle wrap-around indexing
7. Should work with std::sort, std::find, std::distance, etc.
8. Need both iterator and const_iterator
9. Use CRTP or simple class with friend access to the buffer
10. The difference_type operations need to handle circular arithmetic
11. Should show it working with STL algorithms to prove correctness
12. For a circular buffer: head, tail, count, fixed capacity
13. The iterator stores a pointer to the buffer + a logical index
14. Random access: operator+ adds to logical index, physical = (head + logical) % capacity
15. Keep it complete but not overly complex
</think>

**Custom Random Access Iterator for a Circular Buffer**

```cpp
#include <iostream>
#include <algorithm>
#include <numeric>
#include <iterator>
#include <cassert>
#include <cstddef>

template <typename T, size_t Capacity>
class CircularBuffer {
    T data_[Capacity];
    size_t head_ = 0;   // index of first element
    size_t count_ = 0;  // number of elements

    size_t physical(size_t logical) const {
        return (head_ + logical) % Capacity;
    }

public:
    // ============================================================
    // Random Access Iterator
    // ============================================================
    class iterator {
    public:
        // Required type aliases for STL compatibility
        using iterator_category = std::random_access_iterator_tag;
        using value_type        = T;
        using difference_type   = std::ptrdiff_t;
        using pointer           = T*;
        using reference         = T&;

    private:
        CircularBuffer* buf_;
        size_t logical_idx_;  // 0 = first element, count_ = end

    public:
        iterator() : buf_(nullptr), logical_idx_(0) {}
        iterator(CircularBuffer* buf, size_t idx) : buf_(buf), logical_idx_(idx) {}

        // Dereference
        reference operator*() const { return buf_->data_[buf_->physical(logical_idx_)]; }
        pointer operator->() const { return &(**this); }
        reference operator[](difference_type n) const { return *(*this + n); }

        // Increment / Decrement
        iterator& operator++() { ++logical_idx_; return *this; }
        iterator operator++(int) { auto tmp = *this; ++(*this); return tmp; }
        iterator& operator--() { --logical_idx_; return *this; }
        iterator operator--(int) { auto tmp = *this; --(*this); return tmp; }

        // Arithmetic
        iterator& operator+=(difference_type n) { logical_idx_ += n; return *this; }
        iterator& operator-=(difference_type n) { logical_idx_ -= n; return *this; }

        friend iterator operator+(iterator it, difference_type n) { it += n; return it; }
        friend iterator operator+(difference_type n, iterator it) { it += n; return it; }
        friend iterator operator-(iterator it, difference_type n) { it -= n; return it; }
        friend difference_type operator-(const iterator& a, const iterator& b) {
            return static_cast<difference_type>(a.logical_idx_) -
                   static_cast<difference_type>(b.logical_idx_);
        }

        // Comparison
        friend bool operator==(const iterator& a, const iterator& b) {
            return a.logical_idx_ == b.logical_idx_;
        }
        friend bool operator!=(const iterator& a, const iterator& b) { return !(a == b); }
        friend bool operator<(const iterator& a, const iterator& b) {
            return a.logical_idx_ < b.logical_idx_;
        }
        friend bool operator>(const iterator& a, const iterator& b) { return b < a; }
        friend bool operator<=(const iterator& a, const iterator& b) { return !(b < a); }
        friend bool operator>=(const iterator& a, const iterator& b) { return !(a < b); }
    };

    // Const iterator (same pattern, returns const refs)
    class const_iterator {
    public:
        using iterator_category = std::random_access_iterator_tag;
        using value_type        = T;
        using difference_type   = std::ptrdiff_t;
        using pointer           = const T*;
        using reference         = const T&;

    private:
        const CircularBuffer* buf_;
        size_t logical_idx_;

    public:
        const_iterator() : buf_(nullptr), logical_idx_(0) {}
        const_iterator(const CircularBuffer* buf, size_t idx) : buf_(buf), logical_idx_(idx) {}
        const_iterator(const iterator& it) : buf_(it.buf_), logical_idx_(it.logical_idx_) {}

        reference operator*() const { return buf_->data_[buf_->physical(logical_idx_)]; }
        pointer operator->() const { return &(**this); }
        reference operator[](difference_type n) const { return *(*this + n); }

        const_iterator& operator++() { ++logical_idx_; return *this; }
        const_iterator operator++(int) { auto tmp = *this; ++(*this); return tmp; }
        const_iterator& operator--() { --logical_idx_; return *this; }
        const_iterator operator--(int) { auto tmp = *this; --(*this); return tmp; }

        const_iterator& operator+=(difference_type n) { logical_idx_ += n; return *this; }
        const_iterator& operator-=(difference_type n) { logical_idx_ -= n; return *this; }

        friend const_iterator operator+(const_iterator it, difference_type n) { it += n; return it; }
        friend const_iterator operator+(difference_type n, const_iterator it) { it += n; return it; }
        friend const_iterator operator-(const_iterator it, difference_type n) { it -= n; return it; }
        friend difference_type operator-(const const_iterator& a, const const_iterator& b) {
            return static_cast<difference_type>(a.logical_idx_) -
                   static_cast<difference_type>(b.logical_idx_);
        }

        friend bool operator==(const const_iterator& a, const const_iterator& b) {
            return a.logical_idx_ == b.logical_idx_;
        }
        friend bool operator!=(const const_iterator& a, const const_iterator& b) { return !(a == b); }
        friend bool operator<(const const_iterator& a, const const_iterator& b) {
            return a.logical_idx_ < b.logical_idx_;
        }
        friend bool operator>(const const_iterator& a, const const_iterator& b) { return b < a; }
        friend bool operator<=(const const_iterator& a, const const_iterator& b) { return !(b < a); }
        friend bool operator>=(const const_iterator& a, const const_iterator& b) { return !(a < b); }

        friend class iterator;
    };

    // Container interface
    void push_back(const T& val) {
        assert(count_ < Capacity);
        data_[(head_ + count_) % Capacity] = val;
        ++count_;
    }

    void pop_front() {
        assert(count_ > 0);
        head_ = (head_ + 1) % Capacity;
        --count_;
    }

    T& front() { return data_[head_]; }
    T& back() { return data_[physical(count_ - 1)]; }
    size_t size() const { return count_; }
    bool empty() const { return count_ == 0; }

    T& operator[](size_t i) { return data_[physical(i)]; }
    const T& operator[](size_t i) const { return data_[physical(i)]; }

    iterator begin() { return iterator(this, 0); }
    iterator end() { return iterator(this, count_); }
    const_iterator begin() const { return const_iterator(this, 0); }
    const_iterator end() const { return const_iterator(this, count_); }
    const_iterator cbegin() const { return begin(); }
    const_iterator cend() const { return end(); }
};

int main() {
    CircularBuffer<int, 16> buf;

    // Fill with wrap-around: push 10, pop 5, push 10 more
    for (int i = 0; i < 10; ++i) buf.push_back(i * 10);
    for (int i = 0; i < 5; ++i) buf.pop_front();
    for (int i = 10; i < 15; ++i) buf.push_back(i * 10);
    // Now head is at index 5, elements wrap around

    std::cout << "Buffer contents: ";
    for (int x : buf) std::cout << x << " ";
    std::cout << "\n";

    // std::sort works (requires random access iterator)
    std::sort(buf.begin(), buf.end(), std::greater<int>());
    std::cout << "After sort desc: ";
    for (int x : buf) std::cout << x << " ";
    std::cout << "\n";

    // std::find
    auto it = std::find(buf.begin(), buf.end(), 100);
    if (it != buf.end()) {
        std::cout << "Found 100 at logical index " << (it - buf.begin()) << "\n";
    }

    // std::accumulate
    int sum = std::accumulate(buf.begin(), buf.end(), 0);
    std::cout << "Sum: " << sum << "\n";

    // std::nth_element (requires random access)
    std::sort(buf.begin(), buf.end());
    std::cout << "Sorted: ";
    for (int x : buf) std::cout << x << " ";
    std::cout << "\n";

    // std::distance
    std::cout << "Distance begin->end: " << std::distance(buf.begin(), buf.end()) << "\n";
    std::cout << "Size: " << buf.size() << "\n";
}
```

**Key requirements for a random access iterator:** All five comparison operators, bidirectional increment/decrement, `+=`/`-=` with `difference_type`, `operator[]`, and iterator subtraction returning `difference_type`. Missing any of these causes cryptic template errors when used with STL algorithms like `std::sort`.'''),

    ("cpp_deep/stl_algorithm_composition", r'''Show me how to compose STL algorithms (transform + filter + accumulate) in C++17 without ranges, and then the clean C++20 ranges equivalent. I want to see a real data processing pipeline.''', r'''<think>
This is about composing STL algorithms — the ugly C++17 way vs the clean C++20 ranges way.
C++17: need intermediate containers for each step
C++20: ranges compose lazily with pipe syntax
Show a realistic example: processing a collection of records
1. Filter by some condition
2. Transform to extract/compute a value
3. Accumulate the results
In C++17, each step produces a new container
In C++20, views are lazy — no intermediate allocations
Also show the fold_left from C++23 as bonus
Should demonstrate the readability improvement clearly
Include a practical example like sales data processing
Keep it compilable with both approaches
</think>

**Algorithm Composition: C++17 Imperative vs C++20 Ranges**

```cpp
#include <vector>
#include <algorithm>
#include <numeric>
#include <iostream>
#include <string>
#include <cmath>

#if __cplusplus >= 202002L
#include <ranges>
#endif

struct Sale {
    std::string product;
    std::string region;
    double amount;
    int quantity;
    bool returned;
};

std::vector<Sale> get_sales_data() {
    return {
        {"Widget A", "North", 150.0, 3, false},
        {"Widget B", "South", 200.0, 1, true},   // returned
        {"Widget A", "North", 300.0, 5, false},
        {"Gadget X", "East",  450.0, 2, false},
        {"Widget B", "West",   80.0, 1, false},
        {"Gadget X", "North", 520.0, 4, false},
        {"Widget A", "South",  60.0, 1, true},   // returned
        {"Gadget Y", "East",  700.0, 3, false},
        {"Widget A", "East",  180.0, 2, false},
        {"Gadget Y", "North", 900.0, 6, false},
    };
}

// ============================================================
// C++17: Imperative composition with intermediate containers
// Pipeline: non-returned sales -> revenue per sale -> total revenue
// ============================================================
void cpp17_pipeline() {
    std::cout << "=== C++17 Pipeline ===\n";
    auto sales = get_sales_data();

    // Step 1: Filter — remove returned sales
    std::vector<Sale> valid_sales;
    std::copy_if(sales.begin(), sales.end(), std::back_inserter(valid_sales),
                 [](const Sale& s) { return !s.returned; });

    // Step 2: Transform — compute revenue (amount * quantity)
    std::vector<double> revenues;
    std::transform(valid_sales.begin(), valid_sales.end(),
                   std::back_inserter(revenues),
                   [](const Sale& s) { return s.amount * s.quantity; });

    // Step 3: Accumulate — total revenue
    double total = std::accumulate(revenues.begin(), revenues.end(), 0.0);

    std::cout << "Valid sales: " << valid_sales.size() << "\n";
    std::cout << "Total revenue: $" << total << "\n";

    // Step 4: Find max revenue sale (need another intermediate or re-derive)
    auto max_it = std::max_element(revenues.begin(), revenues.end());
    size_t max_idx = std::distance(revenues.begin(), max_it);
    std::cout << "Top sale: " << valid_sales[max_idx].product
              << " ($" << *max_it << ")\n";

    // Step 5: Average revenue
    double avg = total / revenues.size();
    std::cout << "Average revenue: $" << avg << "\n";

    // Count above average
    auto above_avg = std::count_if(revenues.begin(), revenues.end(),
                                   [avg](double r) { return r > avg; });
    std::cout << "Sales above average: " << above_avg << "\n\n";
    // Problem: 3 intermediate vectors allocated!
}

// ============================================================
// C++20: Ranges pipeline — zero intermediate allocations
// ============================================================
#if __cplusplus >= 202002L
void cpp20_pipeline() {
    std::cout << "=== C++20 Ranges Pipeline ===\n";
    auto sales = get_sales_data();

    // Lazy pipeline: filter -> transform -> no intermediate containers
    auto revenue_view = sales
        | std::views::filter([](const Sale& s) { return !s.returned; })
        | std::views::transform([](const Sale& s) { return s.amount * s.quantity; });

    // Accumulate (ranges::fold_left in C++23, use manual loop or std::accumulate)
    double total = 0.0;
    size_t count = 0;
    for (double rev : revenue_view) {
        total += rev;
        ++count;
    }

    std::cout << "Valid sales: " << count << "\n";
    std::cout << "Total revenue: $" << total << "\n";

    // Can also get min/max lazily
    auto valid_with_revenue = sales
        | std::views::filter([](const Sale& s) { return !s.returned; })
        | std::views::transform([](const Sale& s) -> std::pair<std::string, double> {
            return {s.product, s.amount * s.quantity};
        });

    std::string top_product;
    double top_revenue = 0;
    for (auto [product, rev] : valid_with_revenue) {
        if (rev > top_revenue) {
            top_revenue = rev;
            top_product = product;
        }
    }
    std::cout << "Top sale: " << top_product << " ($" << top_revenue << ")\n\n";
}
#endif

// ============================================================
// C++17: Composing without intermediates using accumulate + lambda
// ============================================================
void cpp17_functional() {
    std::cout << "=== C++17 Functional (single pass) ===\n";
    auto sales = get_sales_data();

    struct Stats {
        double total_revenue = 0;
        int count = 0;
        double max_revenue = 0;
        std::string top_product;
    };

    // Single pass with std::accumulate — no intermediate containers
    Stats stats = std::accumulate(sales.begin(), sales.end(), Stats{},
        [](Stats acc, const Sale& s) -> Stats {
            if (s.returned) return acc;  // filter
            double rev = s.amount * s.quantity;  // transform
            acc.total_revenue += rev;     // accumulate
            acc.count++;
            if (rev > acc.max_revenue) {
                acc.max_revenue = rev;
                acc.top_product = s.product;
            }
            return acc;
        });

    std::cout << "Total revenue: $" << stats.total_revenue << "\n";
    std::cout << "Valid sales: " << stats.count << "\n";
    std::cout << "Top sale: " << stats.top_product
              << " ($" << stats.max_revenue << ")\n";
    std::cout << "Average: $" << stats.total_revenue / stats.count << "\n";
    std::cout << "(Zero intermediate allocations!)\n\n";
}

int main() {
    cpp17_pipeline();
#if __cplusplus >= 202002L
    cpp20_pipeline();
#endif
    cpp17_functional();
}
```

**Key insight:** C++17 algorithm composition requires intermediate containers for each step. C++20 ranges compose lazily with zero allocation overhead. For C++17, the single-pass `std::accumulate` with a stateful lambda is the most efficient composition pattern — it avoids all intermediate containers at the cost of readability.'''),

    ("cpp_deep/partition_nth_element", r'''Explain std::partition and std::nth_element with practical examples. When would I use these instead of full sorting? Show the performance advantage.''', r'''<think>
partition and nth_element are partial sorting algorithms:
1. std::partition: rearranges so all elements satisfying predicate come first. O(n). Not stable.
2. std::stable_partition: same but preserves relative order. O(n) with extra memory, O(n log n) without.
3. std::nth_element: puts the nth element in its sorted position, with smaller elements before and larger after. O(n) average. Like quickselect.
4. Use cases: top-K, median finding, separating data into groups
5. Performance: O(n) vs O(n log n) for full sort
6. Show practical examples: filtering data, finding median, top-K results
7. nth_element is the C++ equivalent of quickselect
8. partition_point finds the boundary after partition
9. Show benchmarks comparing with full sort
10. Mention that partition is the foundation of quicksort
11. Three-way partition for Dutch national flag problem
12. nth_element guarantees: element at nth position is what would be there if sorted, everything before is <=, everything after is >=
</think>

**`std::partition` and `std::nth_element` -- Partial Sorting**

When you don't need full sorting, these O(n) algorithms are dramatically faster.

```cpp
#include <vector>
#include <algorithm>
#include <iostream>
#include <numeric>
#include <chrono>
#include <random>
#include <string>

using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_us(F&& fn) {
    auto start = Clock::now();
    fn();
    return std::chrono::duration<double, std::micro>(Clock::now() - start).count();
}

void print_vec(const std::string& label, const std::vector<int>& v, size_t limit = 20) {
    std::cout << label << ": ";
    for (size_t i = 0; i < std::min(v.size(), limit); ++i) std::cout << v[i] << " ";
    if (v.size() > limit) std::cout << "... (" << v.size() << " total)";
    std::cout << "\n";
}

// ============================================================
// std::partition: separate elements by predicate in O(n)
// ============================================================
void partition_demo() {
    std::cout << "=== std::partition ===\n";

    // Separate even and odd numbers
    std::vector<int> data = {7, 2, 5, 8, 1, 4, 9, 3, 6, 10};
    print_vec("Before", data);

    auto boundary = std::partition(data.begin(), data.end(),
                                   [](int x) { return x % 2 == 0; });

    std::cout << "After partition (evens first):\n";
    std::cout << "  Evens: ";
    for (auto it = data.begin(); it != boundary; ++it) std::cout << *it << " ";
    std::cout << "\n  Odds:  ";
    for (auto it = boundary; it != data.end(); ++it) std::cout << *it << " ";
    std::cout << "\n\n";

    // Practical: separate passing and failing students
    struct Student {
        std::string name;
        int score;
    };
    std::vector<Student> students = {
        {"Alice", 85}, {"Bob", 42}, {"Charlie", 91},
        {"Dave", 55}, {"Eve", 73}, {"Frank", 38}
    };

    auto pass_end = std::stable_partition(students.begin(), students.end(),
                                          [](const Student& s) { return s.score >= 60; });

    std::cout << "Passing students:\n";
    for (auto it = students.begin(); it != pass_end; ++it)
        std::cout << "  " << it->name << " (" << it->score << ")\n";
    std::cout << "Failing students:\n";
    for (auto it = pass_end; it != students.end(); ++it)
        std::cout << "  " << it->name << " (" << it->score << ")\n";
    std::cout << "\n";
}

// ============================================================
// std::nth_element: find median, top-K, percentiles in O(n)
// ============================================================
void nth_element_demo() {
    std::cout << "=== std::nth_element ===\n";

    // Find median without full sort
    std::vector<int> data = {45, 12, 89, 23, 67, 34, 78, 56, 91, 5, 43, 71};
    auto copy = data;
    print_vec("Original", data);

    size_t mid = data.size() / 2;
    std::nth_element(data.begin(), data.begin() + mid, data.end());
    std::cout << "Median (approx): " << data[mid] << "\n";
    print_vec("After nth_element", data);
    std::cout << "(Elements before median are all <= " << data[mid]
              << ", elements after are all >= " << data[mid] << ")\n\n";

    // Top-K: find the 3 largest elements
    data = copy;
    size_t k = 3;
    std::nth_element(data.begin(), data.begin() + k, data.end(), std::greater<int>());
    std::cout << "Top " << k << " elements: ";
    std::sort(data.begin(), data.begin() + k, std::greater<int>());  // sort just the top-K
    for (size_t i = 0; i < k; ++i) std::cout << data[i] << " ";
    std::cout << "\n\n";

    // Percentiles
    data = copy;
    size_t p90_idx = static_cast<size_t>(data.size() * 0.9);
    std::nth_element(data.begin(), data.begin() + p90_idx, data.end());
    std::cout << "90th percentile: " << data[p90_idx] << "\n\n";
}

// ============================================================
// Performance: partition/nth_element vs full sort
// ============================================================
void bench_comparison() {
    std::cout << "=== Performance Comparison ===\n";
    const int N = 1'000'000;
    std::mt19937 rng(42);

    auto make_data = [&]() {
        std::vector<int> v(N);
        std::generate(v.begin(), v.end(), rng);
        return v;
    };

    // Full sort
    auto data = make_data();
    double sort_us = measure_us([&]() {
        std::sort(data.begin(), data.end());
    });

    // nth_element (median)
    data = make_data();
    double nth_us = measure_us([&]() {
        std::nth_element(data.begin(), data.begin() + N / 2, data.end());
    });

    // partition
    data = make_data();
    double part_us = measure_us([&]() {
        std::partition(data.begin(), data.end(),
                       [](int x) { return x % 2 == 0; });
    });

    std::cout << "N = " << N << " elements:\n"
              << "  std::sort:        " << sort_us / 1000 << " ms\n"
              << "  std::nth_element: " << nth_us / 1000 << " ms ("
              << sort_us / nth_us << "x faster)\n"
              << "  std::partition:   " << part_us / 1000 << " ms ("
              << sort_us / part_us << "x faster)\n";
}

// ============================================================
// Three-way partition (Dutch National Flag)
// ============================================================
void three_way_partition() {
    std::cout << "\n=== Three-Way Partition ===\n";
    std::vector<int> data = {2, 0, 1, 2, 0, 1, 1, 0, 2, 1, 0};

    // Partition into {0s, 1s, 2s}
    auto mid1 = std::partition(data.begin(), data.end(),
                               [](int x) { return x == 0; });
    std::partition(mid1, data.end(),
                   [](int x) { return x == 1; });

    print_vec("Three-way partitioned", data);
}

int main() {
    partition_demo();
    nth_element_demo();
    bench_comparison();
    three_way_partition();
}
```

**When to use instead of sort:** `std::partition` for binary classification (O(n)), `std::nth_element` for median/top-K/percentile queries (O(n) average via introselect). Full `std::sort` is O(n log n) — unnecessary when you only need partial ordering. For 1M elements, `nth_element` is typically 3-5x faster than full sort.'''),

    ("cpp_deep/sort_stability_predicates", r'''Explain the difference between std::sort and std::stable_sort. When does stability matter? Show custom sort predicates including multi-key sorting and the C++20 projection approach.''', r'''<think>
Sort stability and custom predicates:
1. std::sort: O(n log n) average, not stable (equal elements may be reordered), typically introsort
2. std::stable_sort: O(n log n), preserves relative order of equal elements, requires extra memory
3. Stability matters when sorting by one key while preserving order from a previous sort
4. Multi-key sorting in C++17: comparison function that chains comparisons
5. C++20: ranges::sort with projections for cleaner syntax
6. Show a practical example where stability matters (e.g., sort by department then by name)
7. Custom predicates must be strict weak ordering
8. Show lambda predicates, function objects, and std::tie trick
9. C++20 projections: ranges::sort(v, {}, &Student::grade) — cleaner than lambda
10. Also mention partial_sort for top-K
11. std::sort uses introsort (quicksort + heapsort fallback)
12. std::stable_sort uses merge sort (needs O(n) extra space)
</think>

**Sort Stability, Custom Predicates, and C++20 Projections**

```cpp
#include <vector>
#include <algorithm>
#include <iostream>
#include <string>
#include <tuple>
#include <functional>

#if __cplusplus >= 202002L
#include <ranges>
#endif

struct Employee {
    std::string name;
    std::string department;
    int salary;
    int hire_year;

    friend std::ostream& operator<<(std::ostream& os, const Employee& e) {
        return os << e.department << " | " << e.name
                  << " | $" << e.salary << " | " << e.hire_year;
    }
};

void print_employees(const std::string& label, const std::vector<Employee>& emps) {
    std::cout << label << ":\n";
    for (const auto& e : emps) std::cout << "  " << e << "\n";
    std::cout << "\n";
}

// ============================================================
// Stability demonstration
// ============================================================
void stability_demo() {
    std::cout << "=== Sort Stability Demo ===\n";

    std::vector<Employee> emps = {
        {"Alice",   "Engineering", 95000, 2019},
        {"Bob",     "Engineering", 85000, 2020},
        {"Charlie", "Sales",       70000, 2018},
        {"Dave",    "Engineering", 95000, 2017},
        {"Eve",     "Sales",       80000, 2019},
        {"Frank",   "Sales",       70000, 2020},
    };

    // First: sort by name (gives us a baseline order)
    std::sort(emps.begin(), emps.end(),
              [](const Employee& a, const Employee& b) { return a.name < b.name; });
    print_employees("Sorted by name", emps);

    // Unstable sort by department — name order within department NOT guaranteed
    auto emps_unstable = emps;
    std::sort(emps_unstable.begin(), emps_unstable.end(),
              [](const Employee& a, const Employee& b) {
                  return a.department < b.department;
              });
    print_employees("std::sort by dept (name order may be lost)", emps_unstable);

    // Stable sort by department — preserves name order within same department
    auto emps_stable = emps;
    std::stable_sort(emps_stable.begin(), emps_stable.end(),
                     [](const Employee& a, const Employee& b) {
                         return a.department < b.department;
                     });
    print_employees("std::stable_sort by dept (name order preserved)", emps_stable);
}

// ============================================================
// Multi-key sorting with std::tie (C++17)
// ============================================================
void multikey_sort() {
    std::cout << "=== Multi-Key Sort with std::tie ===\n";

    std::vector<Employee> emps = {
        {"Alice",   "Engineering", 95000, 2019},
        {"Bob",     "Engineering", 85000, 2020},
        {"Charlie", "Sales",       70000, 2018},
        {"Dave",    "Engineering", 95000, 2017},
        {"Eve",     "Sales",       80000, 2019},
        {"Frank",   "Sales",       70000, 2020},
    };

    // Sort by department ASC, then salary DESC, then name ASC
    std::sort(emps.begin(), emps.end(),
              [](const Employee& a, const Employee& b) {
                  // std::tie creates a tuple for lexicographic comparison
                  // Negate salary for descending (or use separate comparisons)
                  if (a.department != b.department) return a.department < b.department;
                  if (a.salary != b.salary) return a.salary > b.salary;  // DESC
                  return a.name < b.name;
              });
    print_employees("By dept ASC, salary DESC, name ASC", emps);

    // Alternative: std::tie for all-ascending multi-key
    std::sort(emps.begin(), emps.end(),
              [](const Employee& a, const Employee& b) {
                  return std::tie(a.department, a.hire_year, a.name)
                       < std::tie(b.department, b.hire_year, b.name);
              });
    print_employees("By dept, hire_year, name (all ASC via std::tie)", emps);
}

// ============================================================
// C++20: Projections — cleaner than lambdas for simple cases
// ============================================================
#if __cplusplus >= 202002L
void projection_sort() {
    std::cout << "=== C++20 Projection Sort ===\n";

    std::vector<Employee> emps = {
        {"Alice",   "Engineering", 95000, 2019},
        {"Bob",     "Engineering", 85000, 2020},
        {"Charlie", "Sales",       70000, 2018},
        {"Dave",    "Engineering", 95000, 2017},
        {"Eve",     "Sales",       80000, 2019},
    };

    // Sort by salary — no lambda needed!
    std::ranges::sort(emps, {}, &Employee::salary);
    print_employees("Sorted by salary (projection)", emps);

    // Sort by salary descending
    std::ranges::sort(emps, std::greater{}, &Employee::salary);
    print_employees("Sorted by salary DESC", emps);

    // Sort by name length (computed projection)
    std::ranges::sort(emps, {}, [](const Employee& e) { return e.name.size(); });
    print_employees("Sorted by name length", emps);

    // stable_sort with projection
    std::ranges::stable_sort(emps, {}, &Employee::department);
    print_employees("Stable sort by dept", emps);
}
#endif

// ============================================================
// partial_sort: top-K without full sort
// ============================================================
void partial_sort_demo() {
    std::cout << "=== std::partial_sort (Top-K) ===\n";

    std::vector<Employee> emps = {
        {"Alice", "Eng", 95000, 2019}, {"Bob", "Eng", 85000, 2020},
        {"Charlie", "Sales", 70000, 2018}, {"Dave", "Eng", 120000, 2017},
        {"Eve", "Sales", 80000, 2019}, {"Frank", "HR", 110000, 2016},
    };

    // Get top 3 earners — O(n log k) instead of O(n log n)
    std::partial_sort(emps.begin(), emps.begin() + 3, emps.end(),
                      [](const Employee& a, const Employee& b) {
                          return a.salary > b.salary;
                      });

    std::cout << "Top 3 earners:\n";
    for (int i = 0; i < 3; ++i) std::cout << "  " << emps[i] << "\n";
    std::cout << "\n";
}

int main() {
    stability_demo();
    multikey_sort();
#if __cplusplus >= 202002L
    projection_sort();
#endif
    partial_sort_demo();
}
```

**When stability matters:** Whenever you sort by one key and need to preserve the order from a previous sort on a different key. Multi-pass sorting (sort by secondary key first, then stable_sort by primary key) produces correct multi-key order. C++20 projections eliminate most lambda boilerplate for single-key sorts.'''),

    ("cpp_deep/binary_search_lower_bound", r'''What's the difference between std::binary_search and std::lower_bound? When should I use each? Show practical examples including the common "find insertion point" pattern.''', r'''<think>
binary_search vs lower_bound:
1. binary_search returns bool — just tells you if element exists
2. lower_bound returns iterator to first element >= value
3. upper_bound returns iterator to first element > value
4. equal_range returns pair of iterators (lower_bound, upper_bound)
5. lower_bound is almost always more useful because you get the position
6. Common pattern: use lower_bound to find insertion point
7. To check existence with lower_bound: it != end && *it == value
8. All require sorted range
9. For map/set, prefer member functions (O(log n) vs O(n) for std::lower_bound on non-random-access)
10. Show: finding exact match, insertion point, counting occurrences, range queries
11. Mention that binary_search uses lower_bound internally
12. Show the off-by-one pitfalls
13. upper_bound - lower_bound = count of equal elements
14. equal_range is useful for multimap/multiset style queries
15. Custom comparators work with all of these
</think>

**`std::binary_search` vs `std::lower_bound` — When to Use Each**

`binary_search` returns `bool`. `lower_bound` returns an **iterator** to the insertion point, making it far more versatile.

```cpp
#include <vector>
#include <algorithm>
#include <iostream>
#include <string>
#include <cassert>

// ============================================================
// Basic comparison
// ============================================================
void basic_comparison() {
    std::cout << "=== binary_search vs lower_bound ===\n";
    std::vector<int> v = {10, 20, 30, 30, 30, 40, 50};

    // binary_search: just yes/no
    bool found = std::binary_search(v.begin(), v.end(), 30);
    std::cout << "binary_search(30): " << std::boolalpha << found << "\n";

    // lower_bound: WHERE is it (or where would it go)?
    auto it = std::lower_bound(v.begin(), v.end(), 30);
    std::cout << "lower_bound(30): index " << (it - v.begin())
              << ", value " << *it << "\n";

    // upper_bound: first element GREATER than value
    auto uit = std::upper_bound(v.begin(), v.end(), 30);
    std::cout << "upper_bound(30): index " << (uit - v.begin())
              << ", value " << *uit << "\n";

    // Count of 30s = upper_bound - lower_bound
    std::cout << "Count of 30: " << (uit - it) << "\n";

    // equal_range: both bounds at once
    auto [lo, hi] = std::equal_range(v.begin(), v.end(), 30);
    std::cout << "equal_range(30): [" << (lo - v.begin()) << ", "
              << (hi - v.begin()) << ")\n\n";
}

// ============================================================
// Pattern: Check existence with lower_bound (replaces binary_search)
// ============================================================
template <typename Container, typename T>
bool contains_sorted(const Container& c, const T& value) {
    auto it = std::lower_bound(c.begin(), c.end(), value);
    return it != c.end() && *it == value;
    // This is exactly what binary_search does internally,
    // but now you also have the iterator if you need it.
}

// ============================================================
// Pattern: Find insertion point for maintaining sorted order
// ============================================================
void insertion_point_demo() {
    std::cout << "=== Insertion Point Pattern ===\n";
    std::vector<int> sorted = {10, 20, 40, 50};

    int new_val = 35;
    auto pos = std::lower_bound(sorted.begin(), sorted.end(), new_val);
    sorted.insert(pos, new_val);

    std::cout << "After inserting " << new_val << ": ";
    for (int x : sorted) std::cout << x << " ";
    std::cout << "\n\n";
}

// ============================================================
// Pattern: Range queries on sorted data
// ============================================================
void range_query_demo() {
    std::cout << "=== Range Queries ===\n";
    std::vector<int> scores = {45, 52, 58, 63, 67, 71, 75, 82, 88, 91, 95};

    // Find all scores in [60, 80]
    auto start = std::lower_bound(scores.begin(), scores.end(), 60);
    auto end = std::upper_bound(scores.begin(), scores.end(), 80);

    std::cout << "Scores in [60, 80]: ";
    for (auto it = start; it != end; ++it) std::cout << *it << " ";
    std::cout << "\n";
    std::cout << "Count: " << std::distance(start, end) << "\n\n";
}

// ============================================================
// Custom comparator: binary search on struct
// ============================================================
struct Event {
    std::string name;
    int timestamp;
};

void custom_comparator_demo() {
    std::cout << "=== Custom Comparator Search ===\n";

    std::vector<Event> events = {
        {"Boot", 100}, {"Login", 200}, {"Query", 300},
        {"Update", 400}, {"Logout", 500}, {"Shutdown", 600}
    };
    // Sorted by timestamp

    // Find first event at or after timestamp 250
    auto it = std::lower_bound(events.begin(), events.end(), 250,
        [](const Event& e, int ts) { return e.timestamp < ts; });

    if (it != events.end()) {
        std::cout << "First event at/after t=250: "
                  << it->name << " (t=" << it->timestamp << ")\n";
    }

    // Find events in time range [200, 500)
    auto range_start = std::lower_bound(events.begin(), events.end(), 200,
        [](const Event& e, int ts) { return e.timestamp < ts; });
    auto range_end = std::lower_bound(events.begin(), events.end(), 500,
        [](const Event& e, int ts) { return e.timestamp < ts; });

    std::cout << "Events in [200, 500):\n";
    for (auto it2 = range_start; it2 != range_end; ++it2) {
        std::cout << "  " << it2->name << " (t=" << it2->timestamp << ")\n";
    }
    std::cout << "\n";
}

// ============================================================
// Gotcha: using member functions for sets/maps
// ============================================================
void member_function_note() {
    std::cout << "=== Prefer member functions for set/map ===\n";
    // std::set/map have member lower_bound() that is O(log n)
    // std::lower_bound() with non-random-access iterators is O(n)!
    // Always use: my_set.lower_bound(key), NOT std::lower_bound(my_set.begin(), ...)
    std::cout << "set::lower_bound() -> O(log n) [uses tree structure]\n"
              << "std::lower_bound(set.begin(), set.end(), ...) -> O(n) [linear iterator advance]\n"
              << "ALWAYS use member functions for associative containers!\n";
}

int main() {
    basic_comparison();

    std::cout << "contains_sorted({1,2,3,4,5}, 3): "
              << std::boolalpha
              << contains_sorted(std::vector{1, 2, 3, 4, 5}, 3) << "\n";
    std::cout << "contains_sorted({1,2,3,4,5}, 6): "
              << contains_sorted(std::vector{1, 2, 3, 4, 5}, 6) << "\n\n";

    insertion_point_demo();
    range_query_demo();
    custom_comparator_demo();
    member_function_note();
}
```

**Rule of thumb:** Never use `std::binary_search` — `std::lower_bound` does everything `binary_search` does and also gives you the iterator. The existence check is `it != end && *it == value`. For associative containers (`set`, `map`), always use member `lower_bound()` / `find()` instead of the free functions.'''),

    ("cpp_deep/ranges_filter_transform_compose", r'''Show me how to compose C++20 ranges views (filter, transform, take, drop) with pipe syntax. Include a real data processing example and explain lazy evaluation.''', r'''<think>
C++20 ranges views with pipe composition:
1. Views are lazy — nothing computed until iterated
2. Pipe syntax: data | filter(...) | transform(...) | take(n)
3. Each view wraps the previous, creating a chain of adaptors
4. No intermediate containers allocated
5. Show practical example: processing log entries or records
6. Demonstrate laziness with side effects or cout
7. Show filter, transform, take, drop, reverse, keys, values, elements
8. Explain how views compose — each stores a reference to the source
9. Important: views don't own data, source must outlive the view
10. Show that iterating multiple times re-evaluates (no caching)
11. Common pitfall: views of temporary — dangling reference
12. Show enumerate (C++23) if possible
13. Show iota for generating sequences
14. Keep it practical and demonstrate the lazy evaluation clearly
</think>

**C++20 Ranges: Lazy View Composition with Pipe Syntax**

```cpp
#include <ranges>
#include <vector>
#include <string>
#include <iostream>
#include <algorithm>
#include <numeric>

namespace rv = std::views;

// ============================================================
// Demonstration of lazy evaluation
// ============================================================
void lazy_evaluation_demo() {
    std::cout << "=== Lazy Evaluation Proof ===\n";

    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // This pipeline does NOTHING yet — just builds a view descriptor
    auto pipeline = data
        | rv::filter([](int x) {
            std::cout << "  filter(" << x << ")\n";
            return x % 2 == 0;
        })
        | rv::transform([](int x) {
            std::cout << "  transform(" << x << ")\n";
            return x * x;
        })
        | rv::take(3);

    std::cout << "Pipeline created. No output yet — lazy!\n\n";
    std::cout << "Now iterating:\n";

    // Only NOW does evaluation happen, and only as much as needed
    for (int val : pipeline) {
        std::cout << "  -> got " << val << "\n";
    }
    // Notice: filter(1) skipped, filter(2) -> transform(2) -> 4
    // Stops after 3 results — never processes 8, 9, 10
    std::cout << "\n";
}

// ============================================================
// Practical: Log analysis pipeline
// ============================================================
struct LogEntry {
    int timestamp;
    std::string level;   // "INFO", "WARN", "ERROR"
    std::string message;
    int response_ms;
};

void log_analysis() {
    std::cout << "=== Log Analysis Pipeline ===\n";

    std::vector<LogEntry> logs = {
        {1000, "INFO",  "Request /api/users",     45},
        {1001, "ERROR", "Database timeout",       5200},
        {1002, "INFO",  "Request /api/health",     12},
        {1003, "WARN",  "Slow query detected",   1500},
        {1004, "ERROR", "Connection refused",     3000},
        {1005, "INFO",  "Request /api/data",       89},
        {1006, "INFO",  "Request /api/users",      32},
        {1007, "ERROR", "Out of memory",          8000},
        {1008, "WARN",  "High CPU usage",          200},
        {1009, "INFO",  "Request /api/health",      8},
    };

    // Pipeline: errors only -> extract response times -> first 2
    std::cout << "First 2 error response times:\n";
    auto error_times = logs
        | rv::filter([](const LogEntry& e) { return e.level == "ERROR"; })
        | rv::transform([](const LogEntry& e) { return e.response_ms; })
        | rv::take(2);

    for (int ms : error_times) {
        std::cout << "  " << ms << " ms\n";
    }

    // Pipeline: skip first 3 INFO entries, get next 2 messages
    std::cout << "\nINFO entries (skip 3, take 2):\n";
    for (auto& entry : logs
            | rv::filter([](const LogEntry& e) { return e.level == "INFO"; })
            | rv::drop(3)
            | rv::take(2)) {
        std::cout << "  [" << entry.timestamp << "] " << entry.message << "\n";
    }

    // Pipeline: all slow responses (>1000ms) with their levels
    std::cout << "\nSlow responses (>1000ms):\n";
    for (auto& entry : logs
            | rv::filter([](const LogEntry& e) { return e.response_ms > 1000; })) {
        std::cout << "  " << entry.level << ": " << entry.message
                  << " (" << entry.response_ms << "ms)\n";
    }
    std::cout << "\n";
}

// ============================================================
// iota + views for generating sequences
// ============================================================
void generation_demo() {
    std::cout << "=== Sequence Generation ===\n";

    // First 10 squares of odd numbers
    std::cout << "First 10 odd squares: ";
    for (int x : rv::iota(1)                          // infinite: 1, 2, 3, ...
                 | rv::filter([](int n) { return n % 2 != 0; })  // 1, 3, 5, ...
                 | rv::transform([](int n) { return n * n; })    // 1, 9, 25, ...
                 | rv::take(10)) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    // FizzBuzz with ranges
    std::cout << "\nFizzBuzz (1-20):\n  ";
    for (auto s : rv::iota(1, 21)
                  | rv::transform([](int n) -> std::string {
                      if (n % 15 == 0) return "FizzBuzz";
                      if (n % 3 == 0)  return "Fizz";
                      if (n % 5 == 0)  return "Buzz";
                      return std::to_string(n);
                  })) {
        std::cout << s << " ";
    }
    std::cout << "\n\n";
}

// ============================================================
// Composing named views for reuse
// ============================================================
void composable_views() {
    std::cout << "=== Composable Named Views ===\n";
    std::vector<int> data = {-5, 3, -2, 8, -1, 7, 4, -9, 6, 2};

    // Build reusable view adaptors
    auto positives = rv::filter([](int x) { return x > 0; });
    auto doubled   = rv::transform([](int x) { return x * 2; });
    auto first_4   = rv::take(4);

    // Compose them
    std::cout << "Positive, doubled, first 4: ";
    for (int x : data | positives | doubled | first_4) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    // Reuse with different data
    std::vector<int> other = {-10, 20, -30, 40, 50};
    std::cout << "Same pipeline, different data: ";
    for (int x : other | positives | doubled | first_4) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";
}

// ============================================================
// Pitfall: dangling reference
// ============================================================
void pitfall_demo() {
    std::cout << "=== Pitfall: Views Don't Own Data ===\n";
    // WRONG: view of temporary
    // auto bad = std::vector{1,2,3} | rv::take(2); // dangling!

    // CORRECT: ensure source outlives the view
    std::vector<int> data = {1, 2, 3, 4, 5};
    auto view = data | rv::take(3);  // view references data
    // data must outlive view!

    for (int x : view) std::cout << x << " ";
    std::cout << "\n(Source must outlive view — no ownership transfer)\n";
}

int main() {
    lazy_evaluation_demo();
    log_analysis();
    generation_demo();
    composable_views();
    pitfall_demo();
}
```

**Key concepts:** Views are lazy wrappers that compose into a pipeline of iterator adaptors. Each `|` creates a new view layer — no data is copied or computed until you iterate. This means: (1) O(1) pipeline construction, (2) elements processed one at a time through the entire chain, (3) early termination with `take()` skips unneeded work. Always ensure the source data outlives any views referencing it.'''),

    ("cpp_deep/custom_range_view", r'''How do I create a custom C++20 range view? I want to write a stride_view that takes every Nth element from a range. Show the full implementation with proper range concepts.''', r'''<think>
Custom C++20 range view — this is advanced. Need:
1. A view class that satisfies std::ranges::view
2. An iterator that advances by N steps
3. A range adaptor closure for pipe syntax
4. Should work with any input range
5. In C++23, stride_view was added to the standard, but implementing it is educational
6. Need to implement: begin(), end(), iterator with proper traits
7. The view should inherit from std::ranges::view_interface for CRTP defaults
8. Need sentinel support for ranges without known size
9. For simplicity, I'll support at least forward ranges
10. The range adaptor closure pattern: a callable that returns a view when piped
11. Should demonstrate it works with other views in a pipeline
12. Keep the iterator implementation complete but not overly complex
13. Use concepts to constrain the template
14. Show the view_interface CRTP which provides empty(), operator bool, front(), back() etc.
15. This is a good teaching example for the ranges customization machinery
</think>

**Creating a Custom C++20 Range View: `stride_view`**

```cpp
#include <ranges>
#include <iterator>
#include <iostream>
#include <vector>
#include <string>
#include <cassert>
#include <type_traits>

// ============================================================
// stride_view: takes every Nth element from a range
// (C++23 has std::views::stride, this implements it from scratch)
// ============================================================
template <std::ranges::input_range V>
    requires std::ranges::view<V>
class stride_view : public std::ranges::view_interface<stride_view<V>> {
    V base_;
    std::ranges::range_difference_t<V> stride_;

public:
    // ============================================================
    // Iterator
    // ============================================================
    class iterator {
    public:
        using base_iter = std::ranges::iterator_t<V>;
        using difference_type = std::ranges::range_difference_t<V>;
        using value_type = std::ranges::range_value_t<V>;
        using reference = std::ranges::range_reference_t<V>;
        using iterator_category = std::input_iterator_tag;  // simplified

    private:
        base_iter current_;
        base_iter end_;       // need end to avoid advancing past it
        difference_type stride_;

    public:
        iterator() = default;
        iterator(base_iter current, base_iter end, difference_type stride)
            : current_(current), end_(end), stride_(stride) {}

        reference operator*() const { return *current_; }

        iterator& operator++() {
            // Advance by stride, but don't go past end
            for (difference_type i = 0; i < stride_ && current_ != end_; ++i) {
                ++current_;
            }
            return *this;
        }

        iterator operator++(int) {
            auto tmp = *this;
            ++(*this);
            return tmp;
        }

        friend bool operator==(const iterator& a, const iterator& b) {
            return a.current_ == b.current_;
        }

        friend bool operator!=(const iterator& a, const iterator& b) {
            return !(a == b);
        }

        // For sentinel comparison
        friend bool operator==(const iterator& it, std::default_sentinel_t) {
            return it.current_ == it.end_;
        }
    };

    // Constructors
    stride_view() = default;
    stride_view(V base, std::ranges::range_difference_t<V> stride)
        : base_(std::move(base)), stride_(stride) {
        assert(stride > 0);
    }

    auto begin() {
        return iterator(std::ranges::begin(base_), std::ranges::end(base_), stride_);
    }

    auto end() {
        // Use default_sentinel for simplicity (works with any range)
        return std::default_sentinel;
    }

    auto size() requires std::ranges::sized_range<V> {
        auto base_size = std::ranges::size(base_);
        return (base_size + stride_ - 1) / stride_;
    }
};

// Deduction guide
template <typename R>
stride_view(R&&, std::ranges::range_difference_t<R>) -> stride_view<std::views::all_t<R>>;

// ============================================================
// Range adaptor closure for pipe syntax
// ============================================================
struct stride_fn {
    template <std::ranges::viewable_range R>
    auto operator()(R&& r, std::ranges::range_difference_t<R> n) const {
        return stride_view(std::forward<R>(r), n);
    }

    // Partial application for pipe syntax: views::stride(3)
    auto operator()(int n) const {
        return [n]<std::ranges::viewable_range R>(R&& r) {
            return stride_view(std::forward<R>(r),
                               static_cast<std::ranges::range_difference_t<R>>(n));
        };
    }
};

// Pipe operator
template <std::ranges::viewable_range R>
auto operator|(R&& r, decltype(stride_fn{}(std::declval<int>()))&& adaptor) {
    return adaptor(std::forward<R>(r));
}

// Global instance
inline constexpr stride_fn stride{};

// ============================================================
// Demo
// ============================================================
int main() {
    std::cout << "=== Custom stride_view ===\n\n";

    // Basic usage
    std::vector<int> data = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};

    std::cout << "Every 3rd element: ";
    for (int x : stride_view(data, 3)) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    std::cout << "Every 2nd element: ";
    for (int x : stride_view(data, 2)) {
        std::cout << x << " ";
    }
    std::cout << "\n";

    std::cout << "Every 4th element: ";
    for (int x : stride_view(data, 4)) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";

    // Compose with standard views
    std::cout << "Compose: filter even | stride(2) | transform(square):\n  ";
    auto pipeline = data
        | std::views::filter([](int x) { return x % 2 == 0; })
        | std::views::transform([](int x) { return x * x; });

    // Apply stride to the result
    for (int x : stride_view(pipeline, 2)) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";

    // Works with iota (infinite range, lazily)
    std::cout << "Every 5th number from iota(0), take 8: ";
    for (int x : stride_view(std::views::iota(0, 100), 5)
                 | std::views::take(8)) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";

    // Practical: downsample a signal
    std::vector<double> signal;
    for (int i = 0; i < 100; ++i) {
        signal.push_back(std::sin(i * 0.1));
    }

    std::cout << "Signal downsampled (every 10th): ";
    for (double s : stride_view(signal, 10)) {
        std::cout << s << " ";
    }
    std::cout << "\n";

    // View interface gives us empty() and size() for free via CRTP
    auto sv = stride_view(data, 3);
    std::cout << "\nstride_view(12 elements, stride=3):\n"
              << "  empty(): " << std::boolalpha << sv.empty() << "\n";
}
```

**Anatomy of a custom view:** Inherit from `view_interface<YourView>` (CRTP) to get `empty()`, `operator bool`, `front()`, `back()` for free. Implement `begin()` returning your iterator and `end()` returning a sentinel. Your iterator needs `operator*`, `operator++`, and equality comparison. The range adaptor closure pattern enables pipe syntax by returning a partially applied callable.'''),

    ("cpp_deep/range_adaptors_pipe", r'''Explain the C++20 range adaptor pipe syntax in depth. How does the pipe operator work mechanically? Show how to write a custom pipe-compatible range adaptor.''', r'''<think>
Deep dive into how C++20 pipe syntax works mechanically:
1. The pipe operator | is overloaded for ranges
2. range | adaptor calls adaptor(range)
3. Range adaptor closures: objects where range | closure returns a view
4. Partial application: views::transform(fn) returns a closure, then range | closure = transform_view(range, fn)
5. The standard defines range_adaptor_closure as a CRTP base (C++23)
6. In C++20, the mechanism is implementation-defined but the behavior is specified
7. I should show: how pipe desugars, how to write a custom adaptor, how composition works
8. adaptor1 | adaptor2 returns a composed adaptor (both applied in sequence)
9. The key insight: adaptors are function objects with special | overloads
10. For a custom adaptor: need a closure object that has operator()(range)
11. And enable | via friend or ADL
12. Show the mechanical desugaring step by step
13. C++23 added std::ranges::range_adaptor_closure as official CRTP base
14. In C++20, we have to do it manually
15. Show practical custom adaptors: sliding_mean, debug_tap
</think>

**C++20 Range Adaptor Pipe Syntax — How It Works Mechanically**

```cpp
#include <ranges>
#include <vector>
#include <iostream>
#include <string>
#include <functional>
#include <numeric>

namespace rv = std::views;

// ============================================================
// How pipe desugars (mental model)
// ============================================================
void desugaring_demo() {
    std::cout << "=== Pipe Desugaring ===\n";
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

    // These are ALL equivalent:

    // 1. Explicit view construction
    auto v1 = std::ranges::filter_view(data, [](int x) { return x % 2 == 0; });

    // 2. Factory function
    auto v2 = rv::filter(data, [](int x) { return x % 2 == 0; });

    // 3. Pipe syntax (partial application)
    // rv::filter(pred) returns a range_adaptor_closure
    // data | closure calls closure(data)
    auto v3 = data | rv::filter([](int x) { return x % 2 == 0; });

    // 4. Chained pipes desugar left-to-right:
    // data | A | B | C  =>  C(B(A(data)))
    auto v4 = data
        | rv::filter([](int x) { return x % 2 == 0; })    // closure_A
        | rv::transform([](int x) { return x * x; })       // closure_B
        | rv::take(3);                                       // closure_C

    // Mechanically: take(3)( transform(sq)( filter(even)( data ) ) )

    std::cout << "Pipeline result: ";
    for (int x : v4) std::cout << x << " ";
    std::cout << "\n\n";
}

// ============================================================
// Custom range adaptor closure (C++20 compatible)
// ============================================================

// CRTP base for pipe support
template <typename Derived>
struct range_adaptor_closure {
    // Enable: range | adaptor
    template <std::ranges::viewable_range R>
    friend auto operator|(R&& r, const Derived& self) {
        return self(std::forward<R>(r));
    }

    // Enable: adaptor1 | adaptor2 (composition)
    template <typename Other>
        requires std::derived_from<Other, range_adaptor_closure<Other>>
    friend auto operator|(const Derived& lhs, const Other& rhs) {
        // Return a new closure that applies lhs then rhs
        return [lhs, rhs]<std::ranges::viewable_range R>(R&& r) {
            return std::forward<R>(r) | lhs | rhs;
        };
    }
};

// ============================================================
// Custom adaptor 1: debug_tap (prints each element without modifying)
// ============================================================
struct debug_tap_closure : range_adaptor_closure<debug_tap_closure> {
    std::string label;

    explicit debug_tap_closure(std::string lbl) : label(std::move(lbl)) {}

    template <std::ranges::viewable_range R>
    auto operator()(R&& r) const {
        return std::forward<R>(r) | rv::transform([label = this->label](auto&& x) -> decltype(auto) {
            std::cout << "[" << label << "] " << x << "\n";
            return std::forward<decltype(x)>(x);
        });
    }
};

auto debug_tap(std::string label) {
    return debug_tap_closure(std::move(label));
}

// ============================================================
// Custom adaptor 2: multiply_by(n)
// ============================================================
struct multiply_closure : range_adaptor_closure<multiply_closure> {
    int factor;
    explicit multiply_closure(int f) : factor(f) {}

    template <std::ranges::viewable_range R>
    auto operator()(R&& r) const {
        return std::forward<R>(r) | rv::transform([f = factor](auto x) { return x * f; });
    }
};

auto multiply_by(int n) { return multiply_closure(n); }

// ============================================================
// Custom adaptor 3: drop_while_then_take(pred, n)
// ============================================================
struct drop_while_take_closure : range_adaptor_closure<drop_while_take_closure> {
    std::function<bool(int)> pred;
    int count;

    drop_while_take_closure(std::function<bool(int)> p, int n)
        : pred(std::move(p)), count(n) {}

    template <std::ranges::viewable_range R>
    auto operator()(R&& r) const {
        return std::forward<R>(r)
            | rv::drop_while(pred)
            | rv::take(count);
    }
};

auto skip_until_then_take(std::function<bool(int)> pred, int n) {
    // "skip until NOT pred" = drop_while(pred)
    return drop_while_take_closure(std::move(pred), n);
}

// ============================================================
// Demonstration
// ============================================================
int main() {
    desugaring_demo();

    std::cout << "=== Custom Adaptors ===\n\n";

    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8};

    // debug_tap in a pipeline
    std::cout << "Debug tap demo:\n";
    auto result = data
        | rv::filter([](int x) { return x > 3; })
        | debug_tap("after filter")
        | rv::transform([](int x) { return x * 10; })
        | rv::take(3);

    std::cout << "Final: ";
    for (int x : result) std::cout << x << " ";
    std::cout << "\n\n";

    // multiply_by in a pipeline
    std::cout << "Multiply demo: ";
    for (int x : data | rv::filter([](int x) { return x % 2 == 0; })
                      | multiply_by(100)) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";

    // Composed adaptor
    std::cout << "Skip until >4, take 3, multiply by 5:\n  ";
    auto composed = skip_until_then_take([](int x) { return x <= 4; }, 3)
                    ;  // Note: full composition with | between closures needs more machinery
    for (int x : data | composed | multiply_by(5)) {
        std::cout << x << " ";
    }
    std::cout << "\n\n";

    // Show that adaptors compose
    std::cout << "iota | filter(even) | multiply(3) | take(5): ";
    for (int x : rv::iota(1)
                 | rv::filter([](int x) { return x % 2 == 0; })
                 | multiply_by(3)
                 | rv::take(5)) {
        std::cout << x << " ";
    }
    std::cout << "\n";
}
```

**Mechanical summary:** `views::X(args)` with a range argument returns a view directly. Without a range, it returns a **range adaptor closure** — a callable object. The pipe `range | closure` calls `closure(range)`. Composing closures `c1 | c2` creates a new closure that applies `c1` then `c2`. The CRTP base `range_adaptor_closure<Derived>` provides the `operator|` overloads. In C++23, `std::ranges::range_adaptor_closure` is standardized.'''),

    ("cpp_deep/lazy_vs_eager_algorithms", r'''Compare lazy evaluation with C++20 ranges views vs eager STL algorithms. When is lazy better? When is eager better? Show a benchmark with real numbers.''', r'''<think>
Lazy vs eager comparison:
1. Lazy (ranges views): no intermediate containers, processes elements on demand, short-circuits with take()
2. Eager (STL algorithms): allocates intermediate containers, processes all elements upfront
3. Lazy wins when: pipeline has take/early termination, large data with small output, memory constrained
4. Eager wins when: need to iterate multiple times (views re-evaluate), need random access on results, simple single-step operations
5. Show benchmark: filtering and transforming a large dataset
6. Show case where lazy wins (take small subset) and where eager has advantages (multiple iterations)
7. Also mention: views have overhead per element (virtual dispatch-like indirection through adaptor chain)
8. For small pipelines on all data, eager can be faster due to simpler iteration
9. The memory advantage of lazy is the main win
10. Show both approaches side by side
11. Measure memory usage conceptually (count allocations)
12. For the benchmark: process 1M elements, filter to 10%, transform, take first 100
</think>

**Lazy Ranges vs Eager STL Algorithms -- When Each Wins**

```cpp
#include <vector>
#include <algorithm>
#include <numeric>
#include <iostream>
#include <chrono>
#include <random>
#include <ranges>
#include <cmath>

namespace rv = std::views;
using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_us(F&& fn) {
    auto start = Clock::now();
    fn();
    return std::chrono::duration<double, std::micro>(Clock::now() - start).count();
}

// ============================================================
// Scenario 1: LAZY WINS — Early termination with take()
// Process 10M elements but only need first 10 matches
// ============================================================
void scenario_early_termination() {
    std::cout << "=== Scenario 1: Early Termination (Lazy Wins) ===\n";
    const int N = 10'000'000;
    std::vector<int> data(N);
    std::iota(data.begin(), data.end(), 0);

    volatile long long sink = 0;

    // EAGER: must process ALL elements, then take 10
    double eager_us = measure_us([&]() {
        std::vector<int> filtered;
        std::copy_if(data.begin(), data.end(), std::back_inserter(filtered),
                     [](int x) { return x % 100'000 == 0; });
        std::vector<int> transformed;
        std::transform(filtered.begin(), filtered.end(),
                       std::back_inserter(transformed),
                       [](int x) { return x * x; });
        long long sum = 0;
        for (size_t i = 0; i < std::min<size_t>(10, transformed.size()); ++i) {
            sum += transformed[i];
        }
        sink = sum;
    });

    // LAZY: stops after finding 10 matches — skips 99.99% of data
    double lazy_us = measure_us([&]() {
        long long sum = 0;
        for (auto x : data
                | rv::filter([](int x) { return x % 100'000 == 0; })
                | rv::transform([](int x) { return static_cast<long long>(x) * x; })
                | rv::take(10)) {
            sum += x;
        }
        sink = sum;
    });

    std::cout << "  Eager: " << eager_us / 1000 << " ms (processes all " << N << " elements)\n"
              << "  Lazy:  " << lazy_us / 1000 << " ms (stops after 10 matches)\n"
              << "  Speedup: " << eager_us / lazy_us << "x\n\n";
}

// ============================================================
// Scenario 2: EAGER WINS — Multiple iterations over result
// ============================================================
void scenario_multiple_iterations() {
    std::cout << "=== Scenario 2: Multiple Iterations (Eager Wins) ===\n";
    const int N = 1'000'000;
    std::vector<int> data(N);
    std::iota(data.begin(), data.end(), 0);

    volatile long long sink = 0;

    // EAGER: filter once, iterate result 10 times
    double eager_us = measure_us([&]() {
        std::vector<int> filtered;
        filtered.reserve(N / 2);
        std::copy_if(data.begin(), data.end(), std::back_inserter(filtered),
                     [](int x) { return x % 2 == 0; });

        long long total = 0;
        for (int pass = 0; pass < 10; ++pass) {
            for (int x : filtered) total += x;
        }
        sink = total;
    });

    // LAZY: re-evaluates the filter on EVERY iteration
    double lazy_us = measure_us([&]() {
        auto view = data | rv::filter([](int x) { return x % 2 == 0; });

        long long total = 0;
        for (int pass = 0; pass < 10; ++pass) {
            for (int x : view) total += x;  // filter runs again each time!
        }
        sink = total;
    });

    std::cout << "  Eager: " << eager_us / 1000 << " ms (filter once, iterate 10x)\n"
              << "  Lazy:  " << lazy_us / 1000 << " ms (filter re-runs each iteration)\n"
              << "  Eager is " << lazy_us / eager_us << "x faster\n\n";
}

// ============================================================
// Scenario 3: Memory — Lazy avoids intermediate allocations
// ============================================================
void scenario_memory() {
    std::cout << "=== Scenario 3: Memory Usage ===\n";
    const int N = 1'000'000;
    std::vector<double> data(N);
    std::mt19937 rng(42);
    for (auto& x : data) x = std::uniform_real_distribution<>(0, 100)(rng);

    // EAGER: creates 2 intermediate vectors
    size_t eager_alloc = 0;
    {
        std::vector<double> step1;
        std::copy_if(data.begin(), data.end(), std::back_inserter(step1),
                     [](double x) { return x > 50.0; });
        eager_alloc += step1.capacity() * sizeof(double);

        std::vector<double> step2;
        std::transform(step1.begin(), step1.end(), std::back_inserter(step2),
                       [](double x) { return std::sqrt(x); });
        eager_alloc += step2.capacity() * sizeof(double);
    }

    // LAZY: zero intermediate allocations
    double lazy_sum = 0;
    for (double x : data
            | rv::filter([](double x) { return x > 50.0; })
            | rv::transform([](double x) { return std::sqrt(x); })) {
        lazy_sum += x;
    }

    std::cout << "  Eager intermediate allocation: ~" << eager_alloc / 1024 << " KB\n"
              << "  Lazy intermediate allocation:  0 KB\n"
              << "  (Lazy computed sum: " << lazy_sum << ")\n\n";
}

// ============================================================
// Scenario 4: Complex pipeline — break-even analysis
// ============================================================
void scenario_pipeline_depth() {
    std::cout << "=== Scenario 4: Pipeline Depth Impact ===\n";
    const int N = 500'000;
    std::vector<int> data(N);
    std::iota(data.begin(), data.end(), 0);
    volatile long long sink = 0;

    // Shallow pipeline (1 step): eager is competitive
    double eager_1 = measure_us([&]() {
        std::vector<int> result;
        std::transform(data.begin(), data.end(), std::back_inserter(result),
                       [](int x) { return x * 2; });
        sink = std::accumulate(result.begin(), result.end(), 0LL);
    });

    double lazy_1 = measure_us([&]() {
        long long sum = 0;
        for (int x : data | rv::transform([](int x) { return x * 2; })) sum += x;
        sink = sum;
    });

    // Deep pipeline (4 steps): lazy avoids 4 intermediate containers
    double eager_4 = measure_us([&]() {
        std::vector<int> s1, s2, s3, s4;
        std::copy_if(data.begin(), data.end(), std::back_inserter(s1),
                     [](int x) { return x % 3 == 0; });
        std::transform(s1.begin(), s1.end(), std::back_inserter(s2),
                       [](int x) { return x * 2; });
        std::copy_if(s2.begin(), s2.end(), std::back_inserter(s3),
                     [](int x) { return x < 500'000; });
        std::transform(s3.begin(), s3.end(), std::back_inserter(s4),
                       [](int x) { return x + 1; });
        sink = std::accumulate(s4.begin(), s4.end(), 0LL);
    });

    double lazy_4 = measure_us([&]() {
        long long sum = 0;
        for (int x : data
                | rv::filter([](int x) { return x % 3 == 0; })
                | rv::transform([](int x) { return x * 2; })
                | rv::filter([](int x) { return x < 500'000; })
                | rv::transform([](int x) { return x + 1; })) {
            sum += x;
        }
        sink = sum;
    });

    std::cout << "  1-step pipeline:\n"
              << "    Eager: " << eager_1 / 1000 << " ms | Lazy: " << lazy_1 / 1000 << " ms\n"
              << "  4-step pipeline:\n"
              << "    Eager: " << eager_4 / 1000 << " ms | Lazy: " << lazy_4 / 1000 << " ms\n"
              << "  (Lazy advantage grows with pipeline depth)\n";
}

int main() {
    scenario_early_termination();
    scenario_multiple_iterations();
    scenario_memory();
    scenario_pipeline_depth();

    std::cout << "\n=== Summary ===\n"
              << "Use LAZY (ranges) when: early termination, deep pipelines, memory constrained\n"
              << "Use EAGER (STL algo) when: multiple iterations, need materialized result,\n"
              << "  simple single-step ops, or need random access on output\n";
}
```

**Key insight:** Lazy evaluation trades per-element overhead (adaptor indirection) for zero intermediate allocations and early termination. The deeper the pipeline and the more data gets filtered out, the bigger lazy's advantage. But if you re-iterate the result multiple times, eager (materialize once) wins because lazy re-evaluates the entire pipeline each time.'''),

    ("cpp_deep/views_zip_cpp23", r'''Show me std::views::zip from C++23 for parallel iteration over multiple ranges. How does it compare to manual index-based loops? Include practical examples.''', r'''<think>
views::zip in C++23:
1. Zips multiple ranges into a view of tuples
2. Equivalent to Python's zip()
3. Length is the minimum of all input ranges
4. Each element is a tuple of references
5. Can destructure with structured bindings
6. Also: zip_transform (like Python's map with multiple iterables)
7. Compare with manual index loop and traditional approach
8. Show practical examples: parallel arrays, dictionary construction, pairwise comparison
9. For C++20 compatibility, show how to do it without zip
10. zip produces tuple<ref, ref, ...> — can modify through references
11. Show zip_transform for computing from multiple sources
12. Also mention views::enumerate (C++23) as a special case of zip with indices
</think>

**`std::views::zip` (C++23) -- Parallel Iteration Over Multiple Ranges**

```cpp
#include <iostream>
#include <vector>
#include <string>
#include <array>
#include <numeric>
#include <cmath>

// C++23 features — if your compiler supports them:
#if __cpp_lib_ranges_zip >= 202110L
#include <ranges>
namespace rv = std::views;
#define HAS_ZIP 1
#else
#define HAS_ZIP 0
#endif

// ============================================================
// Manual zip for C++20 fallback (educational)
// ============================================================
template <typename R1, typename R2>
class zip_view_manual {
    R1& r1_;
    R2& r2_;
public:
    zip_view_manual(R1& a, R2& b) : r1_(a), r2_(b) {}

    class iterator {
        using It1 = decltype(std::begin(std::declval<R1&>()));
        using It2 = decltype(std::begin(std::declval<R2&>()));
        It1 it1_;
        It2 it2_;
        It1 end1_;
        It2 end2_;
    public:
        iterator(It1 a, It1 ae, It2 b, It2 be)
            : it1_(a), it2_(b), end1_(ae), end2_(be) {}

        auto operator*() const {
            return std::pair<decltype(*it1_), decltype(*it2_)>(*it1_, *it2_);
        }
        iterator& operator++() { ++it1_; ++it2_; return *this; }
        bool operator!=(const iterator& o) const {
            return it1_ != o.it1_ && it2_ != o.it2_;
        }
        bool operator==(const iterator& o) const { return !(*this != o); }
    };

    auto begin() { return iterator(std::begin(r1_), std::end(r1_),
                                   std::begin(r2_), std::end(r2_)); }
    auto end()   { return iterator(std::end(r1_), std::end(r1_),
                                   std::end(r2_), std::end(r2_)); }
};

template <typename R1, typename R2>
auto zip_manual(R1& a, R2& b) { return zip_view_manual<R1, R2>(a, b); }

// ============================================================
// Example 1: Basic parallel iteration
// ============================================================
void basic_zip() {
    std::cout << "=== Basic Parallel Iteration ===\n";

    std::vector<std::string> names = {"Alice", "Bob", "Charlie", "Dave"};
    std::vector<int> scores = {95, 87, 92, 78};
    std::vector<char> grades = {'A', 'B', 'A', 'C'};

    // Old way: manual index loop
    std::cout << "Index-based:\n";
    for (size_t i = 0; i < names.size(); ++i) {
        std::cout << "  " << names[i] << ": " << scores[i]
                  << " (" << grades[i] << ")\n";
    }

#if HAS_ZIP
    // C++23 zip: cleaner, no index bugs
    std::cout << "\nviews::zip:\n";
    for (auto [name, score, grade] : rv::zip(names, scores, grades)) {
        std::cout << "  " << name << ": " << score << " (" << grade << ")\n";
    }
#else
    // C++20 fallback
    std::cout << "\nManual zip (C++20):\n";
    for (auto [name, score] : zip_manual(names, scores)) {
        std::cout << "  " << name << ": " << score << "\n";
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 2: Dot product with zip
// ============================================================
void dot_product_demo() {
    std::cout << "=== Dot Product ===\n";
    std::vector<double> a = {1.0, 2.0, 3.0, 4.0};
    std::vector<double> b = {5.0, 6.0, 7.0, 8.0};

    // Manual
    double dot_manual = 0;
    for (size_t i = 0; i < a.size(); ++i) {
        dot_manual += a[i] * b[i];
    }
    std::cout << "Manual: " << dot_manual << "\n";

    // std::inner_product (C++17)
    double dot_ip = std::inner_product(a.begin(), a.end(), b.begin(), 0.0);
    std::cout << "inner_product: " << dot_ip << "\n";

#if HAS_ZIP
    // C++23 zip_transform
    double dot_zip = 0;
    for (double product : rv::zip_transform(std::multiplies{}, a, b)) {
        dot_zip += product;
    }
    std::cout << "zip_transform: " << dot_zip << "\n";
#endif
    std::cout << "\n";
}

// ============================================================
// Example 3: Pairwise differences (adjacent pairs)
// ============================================================
void pairwise_demo() {
    std::cout << "=== Pairwise Differences ===\n";
    std::vector<double> temps = {20.1, 21.3, 19.8, 22.5, 23.1, 21.7};

    // Create shifted views and zip them
    std::cout << "Temperature changes:\n";

#if HAS_ZIP
    // C++23: zip original with shifted-by-1
    for (auto [prev, curr] : rv::zip(temps, temps | rv::drop(1))) {
        double delta = curr - prev;
        std::cout << "  " << prev << " -> " << curr
                  << " (delta: " << (delta >= 0 ? "+" : "") << delta << ")\n";
    }

    // C++23 also has views::adjacent<2> (pairwise)
    // for (auto [a, b] : temps | rv::adjacent<2>) { ... }
#else
    for (size_t i = 1; i < temps.size(); ++i) {
        double delta = temps[i] - temps[i-1];
        std::cout << "  " << temps[i-1] << " -> " << temps[i]
                  << " (delta: " << (delta >= 0 ? "+" : "") << delta << ")\n";
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 4: Enumerate (zip with indices)
// ============================================================
void enumerate_demo() {
    std::cout << "=== Enumerate (zip with iota) ===\n";
    std::vector<std::string> items = {"apple", "banana", "cherry", "date"};

#if HAS_ZIP
    // C++23: views::enumerate is cleaner, but zip + iota works too
    for (auto [idx, item] : rv::zip(rv::iota(0), items)) {
        std::cout << "  [" << idx << "] " << item << "\n";
    }
    // Or with C++23 enumerate:
    // for (auto [idx, item] : items | rv::enumerate) { ... }
#else
    for (size_t i = 0; i < items.size(); ++i) {
        std::cout << "  [" << i << "] " << items[i] << "\n";
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 5: Building a map from parallel arrays
// ============================================================
void build_map_demo() {
    std::cout << "=== Build Map from Parallel Arrays ===\n";
    std::vector<std::string> keys = {"host", "port", "db", "timeout"};
    std::vector<std::string> vals = {"localhost", "5432", "mydb", "30s"};

    // Index-based (error-prone: easy to use wrong index)
    std::cout << "Config:\n";
#if HAS_ZIP
    for (auto [key, val] : rv::zip(keys, vals)) {
        std::cout << "  " << key << " = " << val << "\n";
    }
#else
    for (auto [key, val] : zip_manual(keys, vals)) {
        std::cout << "  " << key << " = " << val << "\n";
    }
#endif

    // Zip handles mismatched lengths safely (stops at shortest)
    std::vector<int> short_vec = {1, 2};
    std::vector<int> long_vec = {10, 20, 30, 40};
    std::cout << "\nMismatched lengths (zip stops at shortest):\n  ";
#if HAS_ZIP
    for (auto [a, b] : rv::zip(short_vec, long_vec)) {
        std::cout << "(" << a << "," << b << ") ";
    }
#else
    for (auto [a, b] : zip_manual(short_vec, long_vec)) {
        std::cout << "(" << a << "," << b << ") ";
    }
#endif
    std::cout << "\n";
}

int main() {
    basic_zip();
    dot_product_demo();
    pairwise_demo();
    enumerate_demo();
    build_map_demo();
}
```

**Why zip over index loops:** (1) No off-by-one or wrong-index bugs, (2) automatically stops at the shortest range, (3) structured bindings make intent clear, (4) composable with other views. `zip_transform` is the multi-range analog of `transform`. For C++20, you can approximate `zip` with a manual view or boost::combine.'''),

    ("cpp_deep/views_chunk_batch", r'''Show me std::views::chunk (C++23) for batch processing. How do I process a range in fixed-size chunks? Include the C++20 workaround.''', r'''<think>
views::chunk in C++23:
1. Splits a range into sub-ranges of N elements
2. Last chunk may be smaller
3. Useful for batch processing, pagination, matrix operations
4. C++20 workaround: manual chunking with iterators or sliding window
5. Also views::chunk_by for grouping by predicate (different from chunk)
6. Show practical examples: batch database inserts, processing pixels in blocks, pagination
7. Show the C++20 manual approach
8. chunk produces a view of subranges
9. Each chunk is itself a view/subrange
</think>

**`std::views::chunk` (C++23) -- Batch Processing**

```cpp
#include <iostream>
#include <vector>
#include <string>
#include <numeric>
#include <algorithm>

#if __cpp_lib_ranges_chunk >= 202202L
#include <ranges>
#define HAS_CHUNK 1
#else
#define HAS_CHUNK 0
#endif

// ============================================================
// C++20 workaround: manual chunk iterator
// ============================================================
template <typename Container>
class chunk_view_manual {
    const Container& data_;
    size_t chunk_size_;

public:
    chunk_view_manual(const Container& data, size_t sz)
        : data_(data), chunk_size_(sz) {}

    class iterator {
        const Container* data_;
        size_t pos_;
        size_t chunk_size_;
    public:
        iterator(const Container* d, size_t p, size_t cs)
            : data_(d), pos_(p), chunk_size_(cs) {}

        auto operator*() const {
            size_t end = std::min(pos_ + chunk_size_, data_->size());
            // Return a lightweight "span" as pair of iterators
            return std::pair(data_->begin() + pos_, data_->begin() + end);
        }
        iterator& operator++() { pos_ += chunk_size_; return *this; }
        bool operator!=(const iterator& o) const { return pos_ < o.pos_; }
        bool operator==(const iterator& o) const { return !(*this != o); }
    };

    auto begin() const { return iterator(&data_, 0, chunk_size_); }
    auto end() const { return iterator(&data_, data_.size(), chunk_size_); }
};

template <typename C>
auto chunks(const C& data, size_t n) { return chunk_view_manual<C>(data, n); }

// ============================================================
// Example 1: Basic chunking
// ============================================================
void basic_chunk() {
    std::cout << "=== Basic Chunking ===\n";
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};

#if HAS_CHUNK
    std::cout << "std::views::chunk(4):\n";
    int batch_num = 0;
    for (auto chunk : data | std::views::chunk(4)) {
        std::cout << "  Batch " << batch_num++ << ": ";
        for (int x : chunk) std::cout << x << " ";
        std::cout << "\n";
    }
#else
    std::cout << "Manual chunk(4):\n";
    int batch_num = 0;
    for (auto [begin, end] : chunks(data, 4)) {
        std::cout << "  Batch " << batch_num++ << ": ";
        for (auto it = begin; it != end; ++it) std::cout << *it << " ";
        std::cout << "\n";
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 2: Batch database inserts
// ============================================================
struct Record {
    int id;
    std::string name;
    double value;
};

void simulate_db_insert(const Record* begin, const Record* end) {
    std::cout << "  INSERT batch (" << (end - begin) << " records): ";
    for (auto it = begin; it != end; ++it) {
        std::cout << it->name << " ";
    }
    std::cout << "\n";
}

void batch_insert_demo() {
    std::cout << "=== Batch Database Insert ===\n";
    std::vector<Record> records = {
        {1, "Alice", 100.0}, {2, "Bob", 200.0}, {3, "Charlie", 150.0},
        {4, "Dave", 300.0}, {5, "Eve", 250.0}, {6, "Frank", 175.0},
        {7, "Grace", 225.0},
    };

    const size_t BATCH_SIZE = 3;

#if HAS_CHUNK
    for (auto batch : records | std::views::chunk(BATCH_SIZE)) {
        // Each batch is a subrange
        std::cout << "  INSERT batch: ";
        for (auto& rec : batch) std::cout << rec.name << " ";
        std::cout << "\n";
    }
#else
    // C++20 manual batching
    for (size_t i = 0; i < records.size(); i += BATCH_SIZE) {
        size_t end = std::min(i + BATCH_SIZE, records.size());
        simulate_db_insert(&records[i], &records[end]);
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 3: Matrix from flat array
// ============================================================
void matrix_demo() {
    std::cout << "=== Matrix from Flat Array ===\n";
    std::vector<int> flat = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
    const size_t COLS = 4;

#if HAS_CHUNK
    std::cout << "4-column matrix:\n";
    for (auto row : flat | std::views::chunk(COLS)) {
        std::cout << "  | ";
        for (int x : row) std::cout << x << "\t";
        std::cout << "|\n";
    }
#else
    std::cout << "4-column matrix (manual):\n";
    for (size_t i = 0; i < flat.size(); i += COLS) {
        std::cout << "  | ";
        for (size_t j = i; j < std::min(i + COLS, flat.size()); ++j) {
            std::cout << flat[j] << "\t";
        }
        std::cout << "|\n";
    }
#endif
    std::cout << "\n";
}

// ============================================================
// Example 4: Moving average with chunk
// ============================================================
void moving_average_demo() {
    std::cout << "=== Block Averages (non-overlapping windows) ===\n";
    std::vector<double> prices = {
        100.5, 101.2, 99.8, 102.3, 103.1,
        101.7, 100.9, 104.2, 103.5, 105.0,
        102.8, 106.1
    };

    const size_t WINDOW = 3;
    std::cout << "Block averages (window=" << WINDOW << "): ";

#if HAS_CHUNK
    for (auto block : prices | std::views::chunk(WINDOW)) {
        double sum = 0;
        int count = 0;
        for (double p : block) { sum += p; ++count; }
        std::cout << (sum / count) << " ";
    }
#else
    for (size_t i = 0; i < prices.size(); i += WINDOW) {
        double sum = 0;
        size_t count = 0;
        for (size_t j = i; j < std::min(i + WINDOW, prices.size()); ++j) {
            sum += prices[j];
            ++count;
        }
        std::cout << (sum / count) << " ";
    }
#endif
    std::cout << "\n\n";
}

// ============================================================
// Example 5: Pagination
// ============================================================
void pagination_demo() {
    std::cout << "=== Pagination ===\n";
    std::vector<std::string> items;
    for (int i = 1; i <= 23; ++i) {
        items.push_back("Item " + std::to_string(i));
    }

    const size_t PAGE_SIZE = 5;
    int page = 1;

#if HAS_CHUNK
    for (auto page_view : items | std::views::chunk(PAGE_SIZE)) {
        std::cout << "  Page " << page++ << ": ";
        for (const auto& item : page_view) std::cout << item << ", ";
        std::cout << "\n";
    }
#else
    for (size_t i = 0; i < items.size(); i += PAGE_SIZE) {
        std::cout << "  Page " << page++ << ": ";
        for (size_t j = i; j < std::min(i + PAGE_SIZE, items.size()); ++j) {
            std::cout << items[j] << ", ";
        }
        std::cout << "\n";
    }
#endif
}

int main() {
    basic_chunk();
    batch_insert_demo();
    matrix_demo();
    moving_average_demo();
    pagination_demo();
}
```

**`views::chunk(n)`** splits any range into sub-ranges of exactly `n` elements (last chunk may be smaller). It's lazy -- no copying. For C++20, the manual `for (i = 0; i < size; i += batch)` loop is the standard workaround, but it's error-prone (off-by-one on the last chunk). C++23 also offers `views::chunk_by(pred)` for grouping consecutive elements that satisfy a binary predicate (different semantics -- variable-size groups).'''),

    ("cpp_deep/projection_sort_comparison", r'''Explain C++20 projection-based sorting and comparison in depth. How do projections work with ranges algorithms? Show advanced uses beyond simple member access.''', r'''<think>
Projections in C++20 ranges algorithms:
1. A projection is a unary callable applied to elements before comparison
2. ranges::sort(v, comp, proj) compares proj(a) vs proj(b) using comp
3. Default comp is std::less{}, default proj is std::identity{}
4. Simple use: &Type::member for sorting by a field
5. Advanced: lambda projections, computed values, chained projections
6. Works with sort, find, min, max, count, etc.
7. Projections avoid writing custom comparators for simple cases
8. Can combine with comparators for complex ordering
9. Show: member pointer, lambda, composed projections
10. Show how it simplifies code compared to C++17 lambdas
</think>

**C++20 Projection-Based Sorting and Comparison**

Projections let you tell an algorithm *what to look at* separately from *how to compare*, eliminating most custom comparator lambdas.

```cpp
#include <algorithm>
#include <ranges>
#include <vector>
#include <string>
#include <iostream>
#include <numeric>
#include <cmath>
#include <functional>
#include <map>

struct Product {
    std::string name;
    double price;
    int stock;
    std::string category;

    friend std::ostream& operator<<(std::ostream& os, const Product& p) {
        return os << p.name << " ($" << p.price << ", stock:" << p.stock << ")";
    }
};

void print_products(const std::string& label, const std::vector<Product>& v) {
    std::cout << label << ":\n";
    for (const auto& p : v) std::cout << "  " << p << "\n";
    std::cout << "\n";
}

// ============================================================
// Basic projections: member pointer
// ============================================================
void basic_projections() {
    std::cout << "=== Basic Projections ===\n";
    std::vector<Product> products = {
        {"Widget",  29.99, 150, "Hardware"},
        {"Gadget",  49.99,  30, "Electronics"},
        {"Doohicky", 9.99, 500, "Hardware"},
        {"Thingamajig", 99.99, 10, "Electronics"},
        {"Gizmo",   19.99, 200, "Accessories"},
    };

    // C++17: verbose lambda comparator
    auto products17 = products;
    std::sort(products17.begin(), products17.end(),
              [](const Product& a, const Product& b) { return a.price < b.price; });

    // C++20: clean projection
    auto products20 = products;
    std::ranges::sort(products20, {}, &Product::price);  // {} = default std::less
    print_products("Sorted by price (projection)", products20);

    // Sort by stock descending
    std::ranges::sort(products20, std::greater{}, &Product::stock);
    print_products("Sorted by stock DESC", products20);

    // Sort by name (string comparison just works)
    std::ranges::sort(products20, {}, &Product::name);
    print_products("Sorted by name", products20);
}

// ============================================================
// Lambda projections: computed values
// ============================================================
void computed_projections() {
    std::cout << "=== Computed Projections ===\n";
    std::vector<Product> products = {
        {"Widget",  29.99, 150, "Hardware"},
        {"Gadget",  49.99,  30, "Electronics"},
        {"Doohicky", 9.99, 500, "Hardware"},
        {"Thingamajig", 99.99, 10, "Electronics"},
        {"Gizmo",   19.99, 200, "Accessories"},
    };

    // Sort by total inventory value (price * stock)
    std::ranges::sort(products, std::greater{},
                      [](const Product& p) { return p.price * p.stock; });
    print_products("Sorted by inventory value DESC", products);

    // Sort by name length
    std::ranges::sort(products, {},
                      [](const Product& p) { return p.name.size(); });
    print_products("Sorted by name length", products);
}

// ============================================================
// Projections with other algorithms
// ============================================================
void projection_algorithms() {
    std::cout << "=== Projections with Various Algorithms ===\n";
    std::vector<Product> products = {
        {"Widget",  29.99, 150, "Hardware"},
        {"Gadget",  49.99,  30, "Electronics"},
        {"Doohicky", 9.99, 500, "Hardware"},
        {"Thingamajig", 99.99, 10, "Electronics"},
        {"Gizmo",   19.99, 200, "Accessories"},
    };

    // min/max by projection
    auto cheapest = std::ranges::min(products, {}, &Product::price);
    auto priciest = std::ranges::max(products, {}, &Product::price);
    std::cout << "Cheapest: " << cheapest << "\n";
    std::cout << "Priciest: " << priciest << "\n";

    // find by projection
    auto it = std::ranges::find(products, "Gadget", &Product::name);
    if (it != products.end()) {
        std::cout << "Found: " << *it << "\n";
    }

    // count by projection
    auto hw_count = std::ranges::count(products, "Hardware", &Product::category);
    std::cout << "Hardware products: " << hw_count << "\n";

    // any_of by projection
    bool has_expensive = std::ranges::any_of(products,
        [](double p) { return p > 90.0; }, &Product::price);
    std::cout << "Has expensive (>$90): " << std::boolalpha << has_expensive << "\n";

    // lower_bound with projection (requires sorted range)
    std::ranges::sort(products, {}, &Product::price);
    auto lb = std::ranges::lower_bound(products, 30.0, {}, &Product::price);
    std::cout << "First product >= $30: " << *lb << "\n\n";
}

// ============================================================
// Advanced: multi-key sort with projection + comparator
// ============================================================
void multikey_projection() {
    std::cout << "=== Multi-Key with Projection ===\n";
    std::vector<Product> products = {
        {"Widget",  29.99, 150, "Hardware"},
        {"Bolt",    29.99,  50, "Hardware"},
        {"Gadget",  49.99,  30, "Electronics"},
        {"Doohicky", 9.99, 500, "Hardware"},
        {"Adapter", 49.99,  80, "Electronics"},
    };

    // Sort by category, then by price — projection returns a tuple
    std::ranges::sort(products, {},
        [](const Product& p) {
            return std::tie(p.category, p.price);
        });
    print_products("Sorted by (category, price)", products);

    // Sort by category ASC, price DESC — need custom comparator
    std::ranges::sort(products,
        [](const auto& a, const auto& b) {
            if (a.first != b.first) return a.first < b.first;
            return a.second > b.second;  // price descending
        },
        [](const Product& p) {
            return std::pair(p.category, p.price);
        });
    print_products("Sorted by category ASC, price DESC", products);
}

// ============================================================
// Projections with numeric algorithms
// ============================================================
void numeric_projections() {
    std::cout << "=== Numeric with Projections ===\n";
    std::vector<Product> products = {
        {"Widget",  29.99, 150, "Hardware"},
        {"Gadget",  49.99,  30, "Electronics"},
        {"Doohicky", 9.99, 500, "Hardware"},
        {"Gizmo",   19.99, 200, "Accessories"},
    };

    // Check if all products are in stock
    bool all_stocked = std::ranges::all_of(products,
        [](int s) { return s > 0; }, &Product::stock);
    std::cout << "All in stock: " << std::boolalpha << all_stocked << "\n";

    // Check if prices are sorted
    bool price_sorted = std::ranges::is_sorted(products, {}, &Product::price);
    std::cout << "Price sorted: " << price_sorted << "\n";

    // Unique by category (need sorted by category first)
    auto prods = products;
    std::ranges::sort(prods, {}, &Product::category);
    auto [first, last] = std::ranges::unique(prods, {}, &Product::category);
    prods.erase(first, last);
    std::cout << "Unique categories: ";
    for (auto& p : prods) std::cout << p.category << " ";
    std::cout << "\n";
}

int main() {
    basic_projections();
    computed_projections();
    projection_algorithms();
    multikey_projection();
    numeric_projections();
}
```

**Projections separate "what to compare" from "how to compare."** Instead of writing `[](const T& a, const T& b) { return a.field < b.field; }`, write `ranges::sort(v, {}, &T::field)`. For computed values, the projection lambda takes one argument and returns the sort key. This composes cleanly: `ranges::min(v, std::greater{}, [](auto& x) { return x.price * x.stock; })` finds the product with the highest inventory value.'''),

    ("cpp_deep/ranges_to_materialize", r'''Show me std::ranges::to (C++23) for materializing views into containers. How do I convert a lazy view into a vector, set, or map?''', r'''<think>
ranges::to in C++23:
1. Converts any range/view into a concrete container
2. Syntax: view | std::ranges::to<std::vector>()
3. Can deduce element type: ranges::to<vector>() infers vector<T>
4. Works with set, map, string, deque, etc.
5. Before C++23: had to manually construct or use insert iterators
6. Show the C++20 workaround and the clean C++23 version
7. Show converting to different container types
8. Show nested containers (e.g., vector of vectors from chunk)
9. Important for "materializing" a lazy pipeline into something you can iterate multiple times
</think>

**`std::ranges::to` (C++23) -- Materializing Views into Containers**

```cpp
#include <iostream>
#include <vector>
#include <set>
#include <map>
#include <string>
#include <ranges>
#include <algorithm>
#include <numeric>
#include <deque>

namespace rv = std::views;

// ============================================================
// C++20 workaround: manual materialization
// ============================================================
template <template <typename...> class Container, std::ranges::range R>
auto materialize(R&& range) {
    using T = std::ranges::range_value_t<R>;
    Container<T> result;
    if constexpr (requires { result.reserve(1); }) {
        if constexpr (std::ranges::sized_range<R>) {
            result.reserve(std::ranges::size(range));
        }
    }
    for (auto&& elem : range) {
        if constexpr (requires { result.push_back(elem); }) {
            result.push_back(std::forward<decltype(elem)>(elem));
        } else {
            result.insert(std::forward<decltype(elem)>(elem));
        }
    }
    return result;
}

// ============================================================
// Examples
// ============================================================
void to_vector_demo() {
    std::cout << "=== Materialize to vector ===\n";

    // Pipeline that we want to materialize
    auto evens_squared = rv::iota(1, 20)
        | rv::filter([](int x) { return x % 2 == 0; })
        | rv::transform([](int x) { return x * x; });

#if __cpp_lib_ranges_to_container >= 202202L
    // C++23: clean and direct
    auto vec = evens_squared | std::ranges::to<std::vector>();
    // Or: auto vec = std::ranges::to<std::vector>(evens_squared);
#else
    // C++20 workaround
    auto vec = materialize<std::vector>(evens_squared);
#endif

    std::cout << "Even squares: ";
    for (int x : vec) std::cout << x << " ";
    std::cout << "\nSize: " << vec.size() << "\n\n";
}

void to_set_demo() {
    std::cout << "=== Materialize to set (auto-dedup) ===\n";
    std::vector<int> data = {3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5};

    auto transformed = data
        | rv::transform([](int x) { return x * 10; });

#if __cpp_lib_ranges_to_container >= 202202L
    auto unique_vals = transformed | std::ranges::to<std::set>();
#else
    auto unique_vals = materialize<std::set>(transformed);
#endif

    std::cout << "Unique transformed: ";
    for (int x : unique_vals) std::cout << x << " ";
    std::cout << "\n\n";
}

void to_string_demo() {
    std::cout << "=== Materialize to string ===\n";
    std::vector<char> chars = {'H', 'e', 'l', 'l', 'o', ',', ' ', 'C', '+', '+'};

    auto upper_view = chars
        | rv::transform([](char c) { return static_cast<char>(std::toupper(c)); });

#if __cpp_lib_ranges_to_container >= 202202L
    auto str = upper_view | std::ranges::to<std::string>();
#else
    std::string str;
    for (char c : upper_view) str += c;
#endif

    std::cout << "Result: \"" << str << "\"\n\n";
}

void to_map_demo() {
    std::cout << "=== Materialize to map ===\n";
    std::vector<std::string> words = {"hello", "world", "ranges", "are", "great"};

    // Create word -> length mapping
    auto pairs = words | rv::transform([](const std::string& w) {
        return std::pair{w, w.size()};
    });

#if __cpp_lib_ranges_to_container >= 202202L
    auto word_lengths = pairs | std::ranges::to<std::map>();
#else
    std::map<std::string, size_t> word_lengths;
    for (auto [word, len] : pairs) {
        word_lengths[word] = len;
    }
#endif

    for (auto& [word, len] : word_lengths) {
        std::cout << "  \"" << word << "\" -> " << len << "\n";
    }
    std::cout << "\n";
}

void pipeline_materialize_demo() {
    std::cout << "=== Pipeline: Process -> Materialize -> Reuse ===\n";

    std::vector<int> raw_data(100);
    std::iota(raw_data.begin(), raw_data.end(), 1);

    // Problem: can't iterate a lazy view multiple times efficiently
    // Solution: materialize once, reuse the concrete container

    auto pipeline = raw_data
        | rv::filter([](int x) { return x % 7 == 0; })      // multiples of 7
        | rv::transform([](int x) { return x * x; });         // squared

#if __cpp_lib_ranges_to_container >= 202202L
    auto results = pipeline | std::ranges::to<std::vector>();
#else
    auto results = materialize<std::vector>(pipeline);
#endif

    // Now we can iterate multiple times without re-evaluation
    double sum = std::accumulate(results.begin(), results.end(), 0.0);
    auto [min_it, max_it] = std::minmax_element(results.begin(), results.end());

    std::cout << "Multiples of 7, squared:\n  ";
    for (int x : results) std::cout << x << " ";
    std::cout << "\n  Sum: " << sum
              << "\n  Min: " << *min_it
              << "\n  Max: " << *max_it << "\n\n";
}

void nested_container_demo() {
    std::cout << "=== Nested: Chunk -> Vector of Vectors ===\n";
    std::vector<int> data = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

#if __cpp_lib_ranges_to_container >= 202202L && __cpp_lib_ranges_chunk >= 202202L
    // C++23: materialize chunks into vector<vector<int>>
    auto matrix = data
        | rv::chunk(3)
        | rv::transform([](auto chunk) {
            return chunk | std::ranges::to<std::vector>();
        })
        | std::ranges::to<std::vector>();

    for (size_t i = 0; i < matrix.size(); ++i) {
        std::cout << "  Row " << i << ": ";
        for (int x : matrix[i]) std::cout << x << " ";
        std::cout << "\n";
    }
#else
    // C++20 manual
    std::vector<std::vector<int>> matrix;
    for (size_t i = 0; i < data.size(); i += 3) {
        size_t end = std::min(i + 3, data.size());
        matrix.emplace_back(data.begin() + i, data.begin() + end);
    }
    for (size_t i = 0; i < matrix.size(); ++i) {
        std::cout << "  Row " << i << ": ";
        for (int x : matrix[i]) std::cout << x << " ";
        std::cout << "\n";
    }
#endif
}

int main() {
    to_vector_demo();
    to_set_demo();
    to_string_demo();
    to_map_demo();
    pipeline_materialize_demo();
    nested_container_demo();
}
```

**`ranges::to<Container>()`** is the missing piece that makes ranges pipelines practical for production code. Without it, the C++20 workaround involves manual loops or `std::inserter` hacks. The key pattern is: build a lazy pipeline for processing, then `| ranges::to<vector>()` to materialize when you need to iterate multiple times, pass to APIs expecting containers, or store as a data member.'''),

    ("cpp_deep/erase_remove_vs_erase_if", r'''Compare the old erase-remove idiom with C++20's std::erase_if. Show both approaches and explain why the old way was error-prone.''', r'''<think>
Erase-remove idiom vs std::erase_if (C++20):
1. Old way: v.erase(std::remove_if(v.begin(), v.end(), pred), v.end())
2. New way: std::erase_if(v, pred)
3. Old way is error-prone: forgetting the v.end() argument, forgetting to call erase
4. std::remove/remove_if doesn't actually remove — it moves unwanted elements to the end and returns the new logical end
5. If you forget to erase, the container still has the old size with garbage at the end
6. C++20 std::erase_if works for vector, deque, list, set, map, unordered_map, etc.
7. For associative containers, erase_if is especially nice — no old idiom equivalent
8. Also std::erase(container, value) for removing by value
9. Show the bug when you forget the second argument to erase
10. Show all container types
</think>

**Erase-Remove Idiom vs C++20 `std::erase_if`**

```cpp
#include <vector>
#include <list>
#include <set>
#include <map>
#include <unordered_map>
#include <string>
#include <algorithm>
#include <iostream>

template <typename Container>
void print(const std::string& label, const Container& c) {
    std::cout << label << ": ";
    if constexpr (requires { c.begin()->first; }) {
        // map-like
        for (auto& [k, v] : c) std::cout << "{" << k << ":" << v << "} ";
    } else {
        for (const auto& x : c) std::cout << x << " ";
    }
    std::cout << "(size=" << c.size() << ")\n";
}

// ============================================================
// The OLD way: erase-remove idiom (C++98-C++17)
// ============================================================
void old_erase_remove() {
    std::cout << "=== Old Erase-Remove Idiom ===\n";
    std::vector<int> v = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    print("Before", v);

    // Remove all even numbers
    // Step 1: std::remove_if moves elements to keep to the front,
    //         returns iterator to "new end" (elements after are garbage)
    auto new_end = std::remove_if(v.begin(), v.end(),
                                  [](int x) { return x % 2 == 0; });

    // WARNING: size hasn't changed yet!
    std::cout << "After remove_if (before erase): ";
    for (int x : v) std::cout << x << " ";  // shows garbage at end
    std::cout << "(size still " << v.size() << "!)\n";

    // Step 2: Actually erase the "removed" elements
    v.erase(new_end, v.end());
    print("After erase", v);
    std::cout << "\n";
}

// ============================================================
// BUG: forgetting parts of the idiom
// ============================================================
void show_bugs() {
    std::cout << "=== Common Bugs ===\n";

    // Bug 1: Forgetting to call erase
    {
        std::vector<int> v = {1, 2, 3, 4, 5};
        std::remove(v.begin(), v.end(), 3);  // BUG: result ignored!
        print("Bug: forgot erase()", v);      // still has 5 elements with garbage
    }

    // Bug 2: Erasing only one element instead of the tail
    {
        std::vector<int> v = {1, 2, 3, 4, 5};
        auto it = std::remove(v.begin(), v.end(), 3);
        v.erase(it);  // BUG: erases only one element, not the whole tail
        print("Bug: erase(it) not erase(it, end())", v);
    }

    // Correct version
    {
        std::vector<int> v = {1, 2, 3, 4, 5};
        v.erase(std::remove(v.begin(), v.end(), 3), v.end());  // correct
        print("Correct erase-remove", v);
    }
    std::cout << "\n";
}

// ============================================================
// C++20: std::erase and std::erase_if — clean and correct
// ============================================================
void cpp20_erase() {
    std::cout << "=== C++20 std::erase / std::erase_if ===\n\n";

    // --- vector ---
    {
        std::vector<int> v = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        auto removed = std::erase_if(v, [](int x) { return x % 2 == 0; });
        print("vector after erase_if(even)", v);
        std::cout << "  Removed " << removed << " elements\n\n";
    }

    // --- erase by value ---
    {
        std::vector<int> v = {1, 3, 5, 3, 7, 3, 9};
        auto removed = std::erase(v, 3);  // remove all 3s
        print("vector after erase(3)", v);
        std::cout << "  Removed " << removed << " elements\n\n";
    }

    // --- list ---
    {
        std::list<int> l = {1, 2, 3, 4, 5, 6, 7, 8};
        std::erase_if(l, [](int x) { return x > 5; });
        print("list after erase_if(>5)", l);
    }

    // --- set ---
    {
        std::set<int> s = {10, 20, 30, 40, 50, 60};
        std::erase_if(s, [](int x) { return x % 20 == 0; });
        print("set after erase_if(%20==0)", s);
    }

    // --- map ---
    {
        std::map<std::string, int> m = {
            {"alice", 25}, {"bob", 17}, {"charlie", 30}, {"dave", 15}
        };
        // Remove entries where value < 18
        std::erase_if(m, [](const auto& pair) { return pair.second < 18; });
        print("map after erase_if(age<18)", m);
    }

    // --- unordered_map ---
    {
        std::unordered_map<int, std::string> um = {
            {1, "one"}, {2, "two"}, {3, "three"}, {4, "four"}, {5, "five"}
        };
        std::erase_if(um, [](const auto& p) { return p.first % 2 == 0; });
        print("unordered_map after erase_if(even keys)", um);
    }

    std::cout << "\n";
}

// ============================================================
// Before C++20: erasing from associative containers was ugly
// ============================================================
void old_associative_erase() {
    std::cout << "=== Old Way: Erasing from map (pre-C++20) ===\n";
    std::map<std::string, int> m = {
        {"a", 1}, {"b", 2}, {"c", 3}, {"d", 4}, {"e", 5}
    };

    // Can't use remove_if on maps! Must iterate manually:
    for (auto it = m.begin(); it != m.end(); /* no increment */) {
        if (it->second % 2 == 0) {
            it = m.erase(it);  // erase returns next valid iterator
        } else {
            ++it;
        }
    }
    print("map after manual erase (odd values only)", m);

    // Compare with C++20:
    // std::erase_if(m, [](auto& p) { return p.second % 2 == 0; });
    // One line. No iterator bugs.
    std::cout << "\n";
}

// ============================================================
// Performance note
// ============================================================
void performance_note() {
    std::cout << "=== Performance Notes ===\n"
              << "For vector/deque: erase_if uses the same algorithm as erase-remove\n"
              << "  internally (O(n) with element shifting). No performance difference.\n"
              << "For list: erase_if uses node unlinking (O(n), no shifting).\n"
              << "For set/map: erase_if iterates and erases matching nodes (O(n log n)).\n"
              << "\nThe benefit is purely ergonomic: fewer bugs, cleaner code.\n";
}

int main() {
    old_erase_remove();
    show_bugs();
    cpp20_erase();
    old_associative_erase();
    performance_note();
}
```

**C++20's `std::erase_if` eliminates three common bugs:** (1) forgetting to capture `remove_if`'s return value, (2) forgetting to call `erase()` after `remove_if`, (3) passing only the iterator instead of the range `[it, end)` to `erase`. It also unifies erasure across all container types -- the same `std::erase_if(container, pred)` works for vector, list, set, map, and unordered containers. Performance is identical; the improvement is purely about correctness and readability.'''),

    ("cpp_deep/container_choice_flowchart", r'''Help me choose the right container: vector vs map vs unordered_map vs set. Give me a decision framework with benchmarks showing the performance crossover points.''', r'''<think>
Container choice is one of the most important practical C++ topics.
Decision criteria:
1. Need ordering? -> map/set. Don't need? -> unordered variants or vector
2. Key-value? -> map/unordered_map. Just values? -> vector/set/unordered_set
3. Frequent lookup by key? -> map/unordered_map
4. Frequent insert/delete? -> list/set/map (no shifting)
5. Memory constrained? -> vector (most compact)
6. Small N? -> vector almost always wins due to cache
7. Need sorted iteration? -> map/set or sorted vector
8. The crossover point: for small N (<100-1000), sorted vector + binary_search beats map
9. unordered_map: O(1) average lookup, but high constant factor and memory overhead
10. Show benchmarks at different sizes
11. Include the flowchart as a decision tree
12. Mention flat_map, deque, and other alternatives
13. Key insight: "N is usually small" — default to vector
14. Show the performance characteristics table
15. Practical: when you think you need a map, consider if sorted vector works
</think>

**Container Choice Framework: vector vs map vs unordered_map**

```cpp
#include <vector>
#include <map>
#include <unordered_map>
#include <set>
#include <algorithm>
#include <chrono>
#include <iostream>
#include <random>
#include <string>
#include <numeric>

using Clock = std::chrono::high_resolution_clock;

template <typename F>
double measure_ns(F&& fn, int iterations = 1) {
    auto start = Clock::now();
    for (int i = 0; i < iterations; ++i) fn();
    auto end = Clock::now();
    return std::chrono::duration<double, std::nano>(end - start).count() / iterations;
}

// ============================================================
// Benchmark: Lookup performance at different sizes
// ============================================================
void bench_lookup(int n) {
    std::mt19937 rng(42);
    std::vector<int> keys(n);
    std::iota(keys.begin(), keys.end(), 0);
    std::shuffle(keys.begin(), keys.end(), rng);

    // Build containers
    std::vector<std::pair<int, int>> sorted_vec;
    std::map<int, int> tree_map;
    std::unordered_map<int, int> hash_map;

    for (int k : keys) {
        sorted_vec.push_back({k, k * 2});
        tree_map[k] = k * 2;
        hash_map[k] = k * 2;
    }
    std::sort(sorted_vec.begin(), sorted_vec.end());

    // Prepare random lookup keys
    std::shuffle(keys.begin(), keys.end(), rng);
    volatile int sink = 0;

    // Sorted vector + binary search
    double vec_ns = measure_ns([&]() {
        for (int k : keys) {
            auto it = std::lower_bound(sorted_vec.begin(), sorted_vec.end(),
                                       std::pair<int,int>{k, 0},
                                       [](const auto& a, const auto& b) {
                                           return a.first < b.first;
                                       });
            sink = it->second;
        }
    }) / n;

    // std::map
    double map_ns = measure_ns([&]() {
        for (int k : keys) sink = tree_map.find(k)->second;
    }) / n;

    // std::unordered_map
    double hash_ns = measure_ns([&]() {
        for (int k : keys) sink = hash_map.find(k)->second;
    }) / n;

    std::cout << "N=" << n << ":\n"
              << "  sorted vector:   " << vec_ns << " ns/lookup\n"
              << "  std::map:        " << map_ns << " ns/lookup\n"
              << "  unordered_map:   " << hash_ns << " ns/lookup\n\n";
}

// ============================================================
// Benchmark: Insertion performance
// ============================================================
void bench_insert(int n) {
    std::mt19937 rng(42);
    std::vector<int> keys(n);
    std::iota(keys.begin(), keys.end(), 0);
    std::shuffle(keys.begin(), keys.end(), rng);

    double vec_ns = measure_ns([&]() {
        std::vector<std::pair<int,int>> v;
        v.reserve(n);
        for (int k : keys) {
            auto pos = std::lower_bound(v.begin(), v.end(),
                                        std::pair<int,int>{k, 0},
                                        [](const auto& a, const auto& b) {
                                            return a.first < b.first;
                                        });
            v.insert(pos, {k, k * 2});
        }
    }) / n;

    double map_ns = measure_ns([&]() {
        std::map<int, int> m;
        for (int k : keys) m[k] = k * 2;
    }) / n;

    double hash_ns = measure_ns([&]() {
        std::unordered_map<int, int> m;
        m.reserve(n);
        for (int k : keys) m[k] = k * 2;
    }) / n;

    std::cout << "Insert N=" << n << ":\n"
              << "  sorted vector:   " << vec_ns << " ns/insert\n"
              << "  std::map:        " << map_ns << " ns/insert\n"
              << "  unordered_map:   " << hash_ns << " ns/insert\n\n";
}

// ============================================================
// Memory usage comparison
// ============================================================
void memory_comparison(int n) {
    std::cout << "=== Memory Usage (N=" << n << ", int->int) ===\n";

    // sorted vector<pair>: 8 bytes per entry + vector overhead
    size_t vec_bytes = n * sizeof(std::pair<int,int>) + sizeof(std::vector<int>);

    // std::map: ~48-64 bytes per node (RB-tree overhead)
    size_t map_bytes = n * 48;  // approximate: key+value+3 pointers+color+alignment

    // unordered_map: ~64-80 bytes per entry (node + bucket array)
    size_t hash_bytes = n * 64;  // approximate: node overhead + bucket array

    std::cout << "  sorted vector:   ~" << vec_bytes / 1024 << " KB\n"
              << "  std::map:        ~" << map_bytes / 1024 << " KB\n"
              << "  unordered_map:   ~" << hash_bytes / 1024 << " KB\n\n";
}

// ============================================================
// Decision framework
// ============================================================
void print_decision_framework() {
    std::cout << R"(
╔══════════════════════════════════════════════════════════════════╗
║                  CONTAINER CHOICE FRAMEWORK                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Start: What do you need?                                        ║
║                                                                  ║
║  1. Sequential storage, frequent iteration                       ║
║     └─> std::vector (always the default)                         ║
║                                                                  ║
║  2. Key-value lookup                                             ║
║     ├─ N < ~1000?                                                ║
║     │  └─> sorted std::vector<pair> + lower_bound                ║
║     │     (cache wins over O(log n) tree)                        ║
║     ├─ Need sorted order / range queries?                        ║
║     │  └─> std::map                                              ║
║     ├─ Need fastest point lookup, order irrelevant?              ║
║     │  └─> std::unordered_map                                    ║
║     └─ Read-heavy, build once?                                   ║
║        └─> sorted vector or std::flat_map (C++23)                ║
║                                                                  ║
║  3. Unique values only                                           ║
║     ├─ Need sorted? -> std::set                                  ║
║     └─> std::unordered_set                                       ║
║                                                                  ║
║  4. FIFO queue                                                   ║
║     └─> std::deque (or std::queue adaptor)                       ║
║                                                                  ║
║  5. Frequent insert/erase in middle + iterator stability         ║
║     └─> std::list (rare — verify with benchmarks!)               ║
║                                                                  ║
║  RULE OF THUMB: std::vector until profiler says otherwise.       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
)";
}

// ============================================================
// Practical: choosing container for a word frequency counter
// ============================================================
void practical_example() {
    std::cout << "=== Practical: Word Frequency Counter ===\n\n";

    std::vector<std::string> words = {
        "the", "quick", "brown", "fox", "jumps", "over", "the",
        "lazy", "dog", "the", "fox", "is", "quick", "and", "the"
    };

    // Approach 1: unordered_map (best for counting — O(1) per word)
    std::unordered_map<std::string, int> freq;
    for (const auto& w : words) ++freq[w];

    // Approach 2: sorted vector for ordered output
    std::vector<std::pair<std::string, int>> freq_vec(freq.begin(), freq.end());
    std::sort(freq_vec.begin(), freq_vec.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });

    std::cout << "Word frequencies (sorted by count):\n";
    for (auto& [word, count] : freq_vec) {
        std::cout << "  \"" << word << "\": " << count << "\n";
    }
    std::cout << "\nPattern: unordered_map for building, sorted vector for output.\n";
}

int main() {
    print_decision_framework();

    std::cout << "=== Lookup Benchmarks ===\n";
    bench_lookup(100);
    bench_lookup(10'000);
    bench_lookup(1'000'000);

    std::cout << "=== Insert Benchmarks ===\n";
    bench_insert(1'000);
    bench_insert(100'000);

    memory_comparison(10'000);
    practical_example();
}
```

**The golden rule: start with `std::vector`.** For small N (< ~1000), sorted vector + `lower_bound` beats `std::map` due to cache locality. `std::unordered_map` has the fastest point lookups at large N but uses 4-8x more memory than sorted vector. `std::map` is for when you need sorted iteration or range queries. When profiling shows your container is a bottleneck, only then consider alternatives. The right container depends on your access pattern (read vs write ratio, iteration vs point lookup, ordering needs).'''),
]
