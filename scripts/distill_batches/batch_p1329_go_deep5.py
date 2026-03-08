"""
Batch p1329 - Go generics, type system, and interfaces (25 pairs)
Topics: generic data structures, generic algorithms, interface design patterns,
        type constraints / advanced generics, reflection & type assertions.
"""

PAIRS = [
    # -- 1-5: Generic data structures --

    (
        "go_deep5_01",
        r'''Implement a generic singly linked list in Go with Append, Prepend, and Iterate methods.''',
        r'''<think>
A generic linked list needs a type parameter for the element type.
I will use a Node[T] struct with a value and next pointer.
The List[T] struct holds a pointer to the head and tracks length.
Append traverses to the tail - O(n) unless we keep a tail pointer.
I will keep both head and tail for O(1) append.
Prepend is always O(1) - just update head.
Iterate should use a callback pattern - idiomatic in Go generics.
Need to handle the empty-list edge case in both Append and Prepend.
I will also add a Len() method for convenience.
No error handling needed here since these operations cannot fail.
</think>

```go
package list

// Node is a single element in the linked list.
type Node[T any] struct {
	Value T
	next  *Node[T]
}

// List is a generic singly linked list with O(1) append.
type List[T any] struct {
	head   *Node[T]
	tail   *Node[T]
	length int
}

// New creates an empty linked list.
func New[T any]() *List[T] {
	return &List[T]{}
}

// Append adds an element to the end of the list in O(1).
func (l *List[T]) Append(val T) {
	node := &Node[T]{Value: val}
	if l.head == nil {
		l.head = node
		l.tail = node
	} else {
		l.tail.next = node
		l.tail = node
	}
	l.length++
}

// Prepend adds an element to the front of the list in O(1).
func (l *List[T]) Prepend(val T) {
	node := &Node[T]{Value: val, next: l.head}
	l.head = node
	if l.tail == nil {
		l.tail = node
	}
	l.length++
}

// Iterate calls fn for each element. Return false from fn to stop early.
func (l *List[T]) Iterate(fn func(T) bool) {
	for cur := l.head; cur != nil; cur = cur.next {
		if !fn(cur.Value) {
			return
		}
	}
}

// Len returns the number of elements.
func (l *List[T]) Len() int {
	return l.length
}
```

The list uses two type-parameterized structs. Keeping a `tail` pointer avoids the O(n) traversal on every `Append`. The `Iterate` method follows the Go convention of accepting a callback that returns `false` to stop, similar to `filepath.WalkFunc` or `sync.Map.Range`.'''
    ),

    (
        "go_deep5_02",
        r'''Write a generic stack in Go with Push, Pop, Peek, and IsEmpty. Pop and Peek should return (T, bool) to signal empty stack.''',
        r'''<think>
A stack is LIFO - a slice works perfectly as the backing store.
Push appends to the slice, Pop removes the last element.
Returning (T, bool) is the Go idiom for optional values - no sentinel needed.
For Pop, I need to return the zero value of T when the stack is empty.
I should use var zero T to get the zero value generically.
Peek is like Pop but without removing the element.
I will keep it simple - no need for a capacity hint, but I could add one.
Thread safety is out of scope unless asked - document that.
The constraint is any since we do not need ordering.
</think>

```go
package stack

// Stack is a generic LIFO data structure backed by a slice.
type Stack[T any] struct {
	items []T
}

// New creates an empty stack. An optional size hint pre-allocates capacity.
func New[T any](sizeHint ...int) *Stack[T] {
	cap := 0
	if len(sizeHint) > 0 && sizeHint[0] > 0 {
		cap = sizeHint[0]
	}
	return &Stack[T]{items: make([]T, 0, cap)}
}

// Push adds an element to the top of the stack.
func (s *Stack[T]) Push(val T) {
	s.items = append(s.items, val)
}

// Pop removes and returns the top element. Returns false if the stack is empty.
func (s *Stack[T]) Pop() (T, bool) {
	if len(s.items) == 0 {
		var zero T
		return zero, false
	}
	top := s.items[len(s.items)-1]
	s.items = s.items[:len(s.items)-1]
	return top, true
}

// Peek returns the top element without removing it. Returns false if empty.
func (s *Stack[T]) Peek() (T, bool) {
	if len(s.items) == 0 {
		var zero T
		return zero, false
	}
	return s.items[len(s.items)-1], true
}

// IsEmpty reports whether the stack has no elements.
func (s *Stack[T]) IsEmpty() bool {
	return len(s.items) == 0
}

// Len returns the number of elements on the stack.
func (s *Stack[T]) Len() int {
	return len(s.items)
}
```

The `(T, bool)` return pattern mirrors how Go maps return values - the boolean tells the caller whether the value is meaningful. Using `var zero T` is the standard way to produce a zero value for any generic type.'''
    ),

    (
        "go_deep5_03",
        r'''Create a generic concurrent-safe queue in Go using a ring buffer with generics. It should support Enqueue, Dequeue, and handle resizing when full.''',
        r'''<think>
A ring buffer queue uses a fixed-size array with head and tail indices.
When full, we double the capacity and re-copy elements in order.
For concurrency safety, I will use a sync.Mutex - simpler than channels for this.
Head points to the next element to dequeue, tail to the next write slot.
Size tracks the count so we can distinguish full from empty.
On resize, I allocate a new buffer of 2x size and copy elements from head
around the ring to the new contiguous buffer.
Dequeue returns (T, bool) to signal empty.
Initial capacity should default to something reasonable like 16.
Edge case: when size == 0 on dequeue, return zero value and false.
I should also handle the wrap-around math with modulo.
</think>

```go
package queue

import "sync"

// Queue is a concurrent-safe generic ring buffer queue.
type Queue[T any] struct {
	mu   sync.Mutex
	buf  []T
	head int
	tail int
	size int
}

// New creates a queue with the given initial capacity (default 16).
func New[T any](capacity ...int) *Queue[T] {
	cap := 16
	if len(capacity) > 0 && capacity[0] > 0 {
		cap = capacity[0]
	}
	return &Queue[T]{buf: make([]T, cap)}
}

// Enqueue adds an element to the back of the queue.
func (q *Queue[T]) Enqueue(val T) {
	q.mu.Lock()
	defer q.mu.Unlock()

	if q.size == len(q.buf) {
		q.grow()
	}
	q.buf[q.tail] = val
	q.tail = (q.tail + 1) % len(q.buf)
	q.size++
}

// Dequeue removes and returns the front element. Returns false if empty.
func (q *Queue[T]) Dequeue() (T, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()

	if q.size == 0 {
		var zero T
		return zero, false
	}
	val := q.buf[q.head]
	var zero T
	q.buf[q.head] = zero // clear reference for GC
	q.head = (q.head + 1) % len(q.buf)
	q.size--
	return val, true
}

// Len returns the number of elements in the queue.
func (q *Queue[T]) Len() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.size
}

// grow doubles the buffer capacity and re-linearizes elements.
func (q *Queue[T]) grow() {
	newCap := len(q.buf) * 2
	newBuf := make([]T, newCap)
	for i := 0; i < q.size; i++ {
		newBuf[i] = q.buf[(q.head+i)%len(q.buf)]
	}
	q.buf = newBuf
	q.head = 0
	q.tail = q.size
}
```

The ring buffer avoids repeated slice shifting. On `grow()`, elements are copied in logical order so `head` resets to 0. Clearing dequeued slots with the zero value prevents holding stale references - important when `T` is a pointer or contains one.'''
    ),

    (
        "go_deep5_04",
        r'''Implement a generic min-heap priority queue in Go. The caller should provide a comparison function. Include Push, Pop, and Peek.''',
        r'''<think>
A priority queue backed by a binary heap stored in a slice.
The comparison function less(a, b T) bool defines ordering.
For a min-heap, less should return true when a is smaller than b.
Push appends to the slice then sifts up (bubble up).
Pop swaps root with last element, shrinks slice, then sifts down.
Peek just returns index 0.
Parent of i is (i-1)/2, children are 2*i+1 and 2*i+2.
I should handle the empty heap case in Pop and Peek.
No mutex here - keep it single-threaded, user can wrap with sync if needed.
The less function approach is more flexible than requiring constraints.Ordered.
I will make it a struct with the less func stored at construction time.
</think>

```go
package pq

// PriorityQueue is a generic binary-heap priority queue.
type PriorityQueue[T any] struct {
	data []T
	less func(a, b T) bool
}

// New creates a priority queue. less(a,b) should return true when a has
// higher priority (e.g., a < b for a min-heap).
func New[T any](less func(a, b T) bool) *PriorityQueue[T] {
	return &PriorityQueue[T]{less: less}
}

// Push adds an element and restores heap order.
func (pq *PriorityQueue[T]) Push(val T) {
	pq.data = append(pq.data, val)
	pq.siftUp(len(pq.data) - 1)
}

// Pop removes and returns the highest-priority element.
func (pq *PriorityQueue[T]) Pop() (T, bool) {
	if len(pq.data) == 0 {
		var zero T
		return zero, false
	}
	top := pq.data[0]
	last := len(pq.data) - 1
	pq.data[0] = pq.data[last]
	pq.data = pq.data[:last]
	if len(pq.data) > 0 {
		pq.siftDown(0)
	}
	return top, true
}

// Peek returns the highest-priority element without removing it.
func (pq *PriorityQueue[T]) Peek() (T, bool) {
	if len(pq.data) == 0 {
		var zero T
		return zero, false
	}
	return pq.data[0], true
}

// Len returns the number of elements.
func (pq *PriorityQueue[T]) Len() int {
	return len(pq.data)
}

func (pq *PriorityQueue[T]) siftUp(i int) {
	for i > 0 {
		parent := (i - 1) / 2
		if !pq.less(pq.data[i], pq.data[parent]) {
			break
		}
		pq.data[i], pq.data[parent] = pq.data[parent], pq.data[i]
		i = parent
	}
}

func (pq *PriorityQueue[T]) siftDown(i int) {
	n := len(pq.data)
	for {
		smallest := i
		left := 2*i + 1
		right := 2*i + 2
		if left < n && pq.less(pq.data[left], pq.data[smallest]) {
			smallest = left
		}
		if right < n && pq.less(pq.data[right], pq.data[smallest]) {
			smallest = right
		}
		if smallest == i {
			break
		}
		pq.data[i], pq.data[smallest] = pq.data[smallest], pq.data[i]
		i = smallest
	}
}
```

Using a `less` function rather than `cmp.Ordered` lets users define priority for structs (e.g., by timestamp, by weight). The sift operations maintain the heap invariant in O(log n). This is simpler and faster than using `container/heap` which requires implementing a four-method interface.'''
    ),

    (
        "go_deep5_05",
        r'''Build a generic sorted set in Go that maintains elements in sorted order. Support Add, Remove, Contains, and Range iteration. Elements must satisfy cmp.Ordered.''',
        r'''<think>
A sorted set needs unique elements stored in order.
Backing it with a sorted slice gives O(log n) search via binary search.
Insert: binary search for position, check for duplicate, then splice in.
Remove: binary search, splice out if found.
Contains: binary search.
Range: iterate over the slice between two bounds.
Using cmp.Ordered from the standard library constrains to comparable ordered types.
Insertion into a slice middle is O(n) due to shifting - acceptable for moderate sizes.
For very large sets, a balanced BST would be better, but slice is simpler and cache-friendly.
I will use sort.Search for the lookup.
Since T is cmp.Ordered, I can use cmp.Compare directly.
</think>

```go
package sortedset

import (
	"cmp"
	"sort"
)

// SortedSet is a generic ordered set of unique elements.
type SortedSet[T cmp.Ordered] struct {
	items []T
}

// New creates an empty sorted set.
func New[T cmp.Ordered]() *SortedSet[T] {
	return &SortedSet[T]{}
}

// Add inserts an element. Returns true if the element was new.
func (s *SortedSet[T]) Add(val T) bool {
	i := s.search(val)
	if i < len(s.items) && s.items[i] == val {
		return false // duplicate
	}
	// splice in at position i
	s.items = append(s.items, val) // grow by one
	copy(s.items[i+1:], s.items[i:])
	s.items[i] = val
	return true
}

// Remove deletes an element. Returns true if it was present.
func (s *SortedSet[T]) Remove(val T) bool {
	i := s.search(val)
	if i >= len(s.items) || s.items[i] != val {
		return false
	}
	s.items = append(s.items[:i], s.items[i+1:]...)
	return true
}

// Contains reports whether the set includes val.
func (s *SortedSet[T]) Contains(val T) bool {
	i := s.search(val)
	return i < len(s.items) && s.items[i] == val
}

// Range calls fn for every element e where lo <= e <= hi, in order.
// Return false from fn to stop early.
func (s *SortedSet[T]) Range(lo, hi T, fn func(T) bool) {
	start := s.search(lo)
	for i := start; i < len(s.items) && cmp.Compare(s.items[i], hi) <= 0; i++ {
		if !fn(s.items[i]) {
			return
		}
	}
}

// Len returns the number of elements.
func (s *SortedSet[T]) Len() int {
	return len(s.items)
}

// Values returns a copy of the sorted elements.
func (s *SortedSet[T]) Values() []T {
	out := make([]T, len(s.items))
	copy(out, s.items)
	return out
}

func (s *SortedSet[T]) search(val T) int {
	return sort.Search(len(s.items), func(i int) bool {
		return cmp.Compare(s.items[i], val) >= 0
	})
}
```

The `cmp.Ordered` constraint restricts T to types that support `<`, `>`, `==` - integers, floats, and strings. Binary search gives O(log n) lookups. The `Range` method is useful for queries like "all users with IDs between 100 and 200". Returning a copy from `Values()` prevents external mutation of the internal slice.'''
    ),

    # -- 6-10: Generic algorithms --

    (
        "go_deep5_06",
        r'''Write generic Map, Filter, and Reduce functions in Go. Show usage with a slice of structs.''',
        r'''<think>
These are the classic functional primitives.
Map transforms []T to []U, so it needs two type parameters.
Filter keeps elements matching a predicate, returns same type []T.
Reduce folds []T into a single U with an accumulator.
I should pre-allocate slices where possible for performance.
For Filter, I cannot pre-allocate since I do not know how many will pass.
For Map, the output length equals input length - pre-allocate exactly.
I will include a usage example with an Employee struct.
These functions work with any types - constraint is just any.
Edge case: empty slice should return empty result, not nil.
I should make Reduce take an initial value to avoid zero-value confusion.
</think>

```go
package fp

// Map transforms each element of src using fn.
func Map[T, U any](src []T, fn func(T) U) []U {
	result := make([]U, len(src))
	for i, v := range src {
		result[i] = fn(v)
	}
	return result
}

// Filter returns elements of src for which pred returns true.
func Filter[T any](src []T, pred func(T) bool) []T {
	result := make([]T, 0)
	for _, v := range src {
		if pred(v) {
			result = append(result, v)
		}
	}
	return result
}

// Reduce folds src into a single value starting from init.
func Reduce[T, U any](src []T, init U, fn func(U, T) U) U {
	acc := init
	for _, v := range src {
		acc = fn(acc, v)
	}
	return acc
}

// --- Example usage ---

type Employee struct {
	Name   string
	Salary float64
	Active bool
}

func Example() {
	employees := []Employee{
		{"Alice", 95000, true},
		{"Bob", 82000, false},
		{"Carol", 110000, true},
	}

	// Get names of active employees
	activeNames := Map(
		Filter(employees, func(e Employee) bool { return e.Active }),
		func(e Employee) string { return e.Name },
	)
	// activeNames = ["Alice", "Carol"]

	// Total salary
	totalSalary := Reduce(employees, 0.0, func(sum float64, e Employee) float64 {
		return sum + e.Salary
	})
	// totalSalary = 287000.0

	_ = activeNames
	_ = totalSalary
}
```

Note that `Map` returns `[]U` - a different type than the input - which requires two type parameters. `Filter` initializes with `make([]T, 0)` (empty non-nil slice) even when nothing matches, avoiding nil-slice surprises in JSON marshaling. These compose cleanly: `Map(Filter(...), fn)` reads left-to-right.'''
    ),

    (
        "go_deep5_07",
        r'''Implement a generic sorting function in Go that works with any type satisfying a custom Sortable constraint. Support both ascending and descending order.''',
        r'''<think>
I will define a custom constraint that requires ordering.
A flexible approach: accept a comparison function plus define constraints.
I will create a Comparable interface for types with a Compare method.
I will use sort.Slice under the hood for the actual sorting.
For descending, I can provide two functions (SortAsc/SortDesc) rather than a bool.
Two functions is a cleaner API than a boolean parameter.
I should also provide SortBy for struct slices sorted by a key extractor.
That covers the common patterns: sort ints, sort structs by field.
I will use cmp.Compare from the standard library for ordered types.
The Comparable constraint handles custom types with their own ordering logic.
</think>

```go
package gsort

import (
	"cmp"
	"sort"
)

// Comparable types expose their own ordering.
type Comparable[T any] interface {
	Compare(other T) int // -1, 0, +1
}

// SortAsc sorts a slice of ordered types in ascending order.
func SortAsc[T cmp.Ordered](s []T) {
	sort.Slice(s, func(i, j int) bool {
		return cmp.Compare(s[i], s[j]) < 0
	})
}

// SortDesc sorts a slice of ordered types in descending order.
func SortDesc[T cmp.Ordered](s []T) {
	sort.Slice(s, func(i, j int) bool {
		return cmp.Compare(s[i], s[j]) > 0
	})
}

// SortBy sorts a slice by a key extracted from each element.
func SortBy[T any, K cmp.Ordered](s []T, key func(T) K) {
	sort.Slice(s, func(i, j int) bool {
		return cmp.Compare(key(s[i]), key(s[j])) < 0
	})
}

// SortByDesc is SortBy in descending order.
func SortByDesc[T any, K cmp.Ordered](s []T, key func(T) K) {
	sort.Slice(s, func(i, j int) bool {
		return cmp.Compare(key(s[i]), key(s[j])) > 0
	})
}

// SortComparable sorts types implementing the Comparable interface.
func SortComparable[T Comparable[T]](s []T) {
	sort.Slice(s, func(i, j int) bool {
		return s[i].Compare(s[j]) < 0
	})
}

// --- Example ---

type Task struct {
	Name     string
	Priority int
}

func Example() {
	tasks := []Task{
		{"deploy", 3},
		{"test", 1},
		{"build", 2},
	}

	// Sort by priority ascending
	SortBy(tasks, func(t Task) int { return t.Priority })
	// tasks = [{test 1} {build 2} {deploy 3}]

	nums := []int{5, 2, 8, 1, 9}
	SortDesc(nums)
	// nums = [9, 8, 5, 2, 1]
}
```

The `SortBy` function is the most useful - it lets you sort any struct slice by any ordered field without implementing `sort.Interface`. The `Comparable` constraint is for types with custom ordering logic (e.g., semantic versions). Using `cmp.Compare` instead of `<` avoids NaN issues with floats.'''
    ),

    (
        "go_deep5_08",
        r'''Write a generic binary search function in Go that returns the index and whether the element was found. Support both cmp.Ordered types and custom comparators.''',
        r'''<think>
Two variants: one for cmp.Ordered using the natural order,
one with a custom comparator function for arbitrary types.
The slice must be sorted - document that precondition.
Return (index, found) where index is the insertion point if not found.
This matches the sort.Search semantics but with a cleaner API.
For the ordered version, I use cmp.Compare directly.
For the comparator version, the func takes (element) and returns int.
Edge cases: empty slice returns (0, false), single element.
I should use the standard binary search algorithm: lo, hi, mid.
The comparator approach lets users search structs by a specific field.
</think>

```go
package search

import "cmp"

// BinarySearch searches a sorted slice for target.
// Returns (index, true) if found, or (insertionPoint, false) if not.
// The slice must be sorted in ascending order.
func BinarySearch[T cmp.Ordered](sorted []T, target T) (int, bool) {
	lo, hi := 0, len(sorted)
	for lo < hi {
		mid := lo + (hi-lo)/2
		switch c := cmp.Compare(sorted[mid], target); {
		case c < 0:
			lo = mid + 1
		case c > 0:
			hi = mid
		default:
			return mid, true
		}
	}
	return lo, false
}

// BinarySearchFunc searches using a custom comparator.
// cmpFn(element) should return:
//   negative if element comes before target
//   0 if element equals target
//   positive if element comes after target
func BinarySearchFunc[T any](sorted []T, cmpFn func(T) int) (int, bool) {
	lo, hi := 0, len(sorted)
	for lo < hi {
		mid := lo + (hi-lo)/2
		switch c := cmpFn(sorted[mid]); {
		case c < 0:
			lo = mid + 1
		case c > 0:
			hi = mid
		default:
			return mid, true
		}
	}
	return lo, false
}

// --- Example ---

type User struct {
	ID   int
	Name string
}

func Example() {
	// Simple ordered search
	nums := []int{1, 3, 5, 7, 9, 11}
	idx, found := BinarySearch(nums, 7)
	// idx=3, found=true

	// Struct search by field
	users := []User{{1, "Alice"}, {5, "Bob"}, {9, "Carol"}}
	idx, found = BinarySearchFunc(users, func(u User) int {
		return cmp.Compare(u.ID, 5)
	})
	// idx=1, found=true (Bob)

	_, _ = idx, found
}
```

Using `lo + (hi-lo)/2` instead of `(lo+hi)/2` prevents integer overflow - a classic binary search bug. The `BinarySearchFunc` variant is especially powerful: it lets you search a `[]User` by `ID` without extracting IDs into a separate slice first. Go 1.21+ has `slices.BinarySearch` in the stdlib, but this custom version demonstrates the pattern.'''
    ),

    (
        "go_deep5_09",
        r'''Implement generic Merge and MergeSorted functions in Go. Merge combines two slices, MergeSorted merges two already-sorted slices into one sorted result.''',
        r'''<think>
Merge is simple concatenation - just append.
MergeSorted is the merge step from merge sort: two-pointer technique.
Both inputs must be sorted; output is sorted.
MergeSorted needs cmp.Ordered constraint since we compare elements.
I should pre-allocate the result slice to len(a)+len(b) for efficiency.
Edge cases: one or both slices empty.
I could also add MergeSortedFunc with a custom comparator.
The two-pointer approach is O(n+m) time and O(n+m) space.
I will also add a MergeSortedUnique variant that deduplicates.
Using <= 0 in the comparison preserves stable relative order of equals.
</think>

```go
package merge

import "cmp"

// Merge concatenates two slices into a new slice.
func Merge[T any](a, b []T) []T {
	result := make([]T, 0, len(a)+len(b))
	result = append(result, a...)
	result = append(result, b...)
	return result
}

// MergeSorted merges two sorted slices into one sorted result.
// Both inputs must be sorted in ascending order.
func MergeSorted[T cmp.Ordered](a, b []T) []T {
	result := make([]T, 0, len(a)+len(b))
	i, j := 0, 0
	for i < len(a) && j < len(b) {
		if cmp.Compare(a[i], b[j]) <= 0 {
			result = append(result, a[i])
			i++
		} else {
			result = append(result, b[j])
			j++
		}
	}
	result = append(result, a[i:]...)
	result = append(result, b[j:]...)
	return result
}

// MergeSortedFunc merges two sorted slices using a custom comparator.
// cmpFn(a, b) returns negative if a < b, 0 if equal, positive if a > b.
func MergeSortedFunc[T any](a, b []T, cmpFn func(T, T) int) []T {
	result := make([]T, 0, len(a)+len(b))
	i, j := 0, 0
	for i < len(a) && j < len(b) {
		if cmpFn(a[i], b[j]) <= 0 {
			result = append(result, a[i])
			i++
		} else {
			result = append(result, b[j])
			j++
		}
	}
	result = append(result, a[i:]...)
	result = append(result, b[j:]...)
	return result
}

// MergeSortedUnique merges and removes duplicates.
func MergeSortedUnique[T cmp.Ordered](a, b []T) []T {
	result := make([]T, 0, len(a)+len(b))
	i, j := 0, 0
	for i < len(a) && j < len(b) {
		c := cmp.Compare(a[i], b[j])
		switch {
		case c < 0:
			result = append(result, a[i])
			i++
		case c > 0:
			result = append(result, b[j])
			j++
		default:
			result = append(result, a[i])
			i++
			j++
		}
	}
	result = append(result, a[i:]...)
	result = append(result, b[j:]...)
	return result
}
```

The two-pointer technique runs in O(n+m) - optimal for merging sorted data. Pre-allocating with `cap = len(a)+len(b)` avoids repeated slice growth. `MergeSortedUnique` handles the common case of merging two sorted-unique lists (like set union). Using `<= 0` in the comparison preserves the relative order of equal elements (stable merge).'''
    ),

    (
        "go_deep5_10",
        r'''Write a generic GroupBy function in Go that groups a slice by a key extracted from each element, returning a map[K][]T.''',
        r'''<think>
GroupBy is a common data transformation: split a slice into buckets by key.
Key type K must be comparable (map key constraint).
Value type T can be anything.
The key extractor is a function T to K.
Result is map[K][]T where each key maps to all elements with that key.
I should also provide a GroupByTransform that applies a value transform.
This is useful for things like: group users by department, group logs by level.
Edge case: empty input returns an empty (non-nil) map.
I could also add a Count variant that returns map[K]int.
Let me include GroupBy, GroupByTransform, and CountBy for completeness.
</think>

```go
package fp

// GroupBy groups elements by a key function, returning map[K][]T.
func GroupBy[T any, K comparable](src []T, key func(T) K) map[K][]T {
	result := make(map[K][]T)
	for _, v := range src {
		k := key(v)
		result[k] = append(result[k], v)
	}
	return result
}

// GroupByTransform groups and transforms values simultaneously.
func GroupByTransform[T any, K comparable, V any](
	src []T,
	key func(T) K,
	val func(T) V,
) map[K][]V {
	result := make(map[K][]V)
	for _, item := range src {
		k := key(item)
		result[k] = append(result[k], val(item))
	}
	return result
}

// CountBy counts elements per group.
func CountBy[T any, K comparable](src []T, key func(T) K) map[K]int {
	result := make(map[K]int)
	for _, v := range src {
		result[key(v)]++
	}
	return result
}

// --- Example ---

type LogEntry struct {
	Level   string
	Message string
	Line    int
}

func Example() {
	logs := []LogEntry{
		{"ERROR", "nil pointer", 42},
		{"INFO", "started", 1},
		{"ERROR", "timeout", 88},
		{"WARN", "deprecated", 15},
		{"INFO", "ready", 5},
	}

	// Group by level
	byLevel := GroupBy(logs, func(l LogEntry) string { return l.Level })
	// byLevel["ERROR"] = [{ERROR nil pointer 42}, {ERROR timeout 88}]

	// Get just messages per level
	msgByLevel := GroupByTransform(logs,
		func(l LogEntry) string { return l.Level },
		func(l LogEntry) string { return l.Message },
	)
	// msgByLevel["INFO"] = ["started", "ready"]

	// Count per level
	counts := CountBy(logs, func(l LogEntry) string { return l.Level })
	// counts = {"ERROR": 2, "INFO": 2, "WARN": 1}

	_, _, _ = byLevel, msgByLevel, counts
}
```

The `comparable` constraint on `K` is required because map keys must be comparable in Go. `GroupByTransform` saves an extra pass when you need to extract a sub-field per group - instead of grouping then mapping each group. The `CountBy` variant is a common aggregation pattern that avoids allocating slice values when you only need counts.'''
    ),

    # -- 11-15: Interface design patterns --

    (
        "go_deep5_11",
        r'''Implement the functional options pattern in Go for configuring an HTTP server struct. Show how to use variadic option functions with defaults.''',
        r'''<think>
Functional options is the idiomatic Go pattern for complex constructors.
Each option is a function that modifies the config/struct.
The constructor accepts variadic ...Option parameters.
Benefits: backwards-compatible API, self-documenting, no config struct explosion.
I need a Server struct with fields like addr, readTimeout, writeTimeout, TLS, logger.
Each WithXxx function returns an Option that sets one field.
The constructor applies defaults first, then options override.
I should show how to compose options and pass them around.
Error-returning options are safer but less common - I will use the simpler variant.
This pattern was popularized by Dave Cheney and Rob Pike.
</think>

```go
package server

import (
	"log"
	"net/http"
	"os"
	"time"
)

// Server is an HTTP server with configurable options.
type Server struct {
	addr         string
	readTimeout  time.Duration
	writeTimeout time.Duration
	maxBodyBytes int64
	logger       *log.Logger
	handler      http.Handler
}

// Option configures a Server.
type Option func(*Server)

// New creates a Server with sensible defaults, overridden by options.
func New(handler http.Handler, opts ...Option) *Server {
	s := &Server{
		addr:         ":8080",
		readTimeout:  5 * time.Second,
		writeTimeout: 10 * time.Second,
		maxBodyBytes: 1 << 20, // 1 MB
		logger:       log.New(os.Stdout, "[server] ", log.LstdFlags),
		handler:      handler,
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

// WithAddr sets the listen address.
func WithAddr(addr string) Option {
	return func(s *Server) { s.addr = addr }
}

// WithReadTimeout sets the read timeout.
func WithReadTimeout(d time.Duration) Option {
	return func(s *Server) { s.readTimeout = d }
}

// WithWriteTimeout sets the write timeout.
func WithWriteTimeout(d time.Duration) Option {
	return func(s *Server) { s.writeTimeout = d }
}

// WithMaxBodyBytes sets the maximum request body size.
func WithMaxBodyBytes(n int64) Option {
	return func(s *Server) { s.maxBodyBytes = n }
}

// WithLogger sets a custom logger.
func WithLogger(l *log.Logger) Option {
	return func(s *Server) { s.logger = l }
}

// Start begins listening.
func (s *Server) Start() error {
	srv := &http.Server{
		Addr:         s.addr,
		Handler:      http.MaxBytesHandler(s.handler, s.maxBodyBytes),
		ReadTimeout:  s.readTimeout,
		WriteTimeout: s.writeTimeout,
	}
	s.logger.Printf("listening on %s", s.addr)
	return srv.ListenAndServe()
}

// --- Usage ---

func Example() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})

	// Options can be stored and reused
	prodDefaults := []Option{
		WithAddr(":443"),
		WithReadTimeout(30 * time.Second),
		WithMaxBodyBytes(10 << 20),
	}

	srv := New(mux, prodDefaults...)
	_ = srv
}
```

Functional options give you a clean, extensible constructor API. Adding new options never breaks existing callers - they just keep using the defaults. Options can be collected into slices and passed around (like `prodDefaults` above). For validation, use `type Option func(*Server) error` and check errors during `New()`.'''
    ),

    (
        "go_deep5_12",
        r'''Design a generic middleware chain in Go for processing requests. Each middleware wraps the next handler. Show how to compose middlewares for logging, auth, and rate limiting.''',
        r'''<think>
Middleware chains follow the decorator pattern.
Each middleware takes a handler and returns a wrapped handler.
In Go net/http, the pattern is func(http.Handler) http.Handler.
I should show a generic approach that works beyond HTTP too.
The key insight is that Middleware is a function type that composes.
A Chain function applies middlewares in order (outermost first).
For the HTTP case, I will show logging, auth, and rate limiting.
Logging wraps to log before/after, auth checks a header, rate limit uses a counter.
The chain should be easy to read: Chain(logging, auth, rateLimit)(handler).
I need to be careful about ordering - first middleware in the list is outermost.
This is the same pattern used by chi, echo, and other Go routers.
</think>

```go
package middleware

import (
	"log"
	"net/http"
	"sync/atomic"
	"time"
)

// Middleware wraps an http.Handler.
type Middleware func(http.Handler) http.Handler

// Chain composes middlewares so that the first in the list is the outermost.
// Chain(A, B, C)(handler) produces A(B(C(handler)))
func Chain(mws ...Middleware) Middleware {
	return func(final http.Handler) http.Handler {
		for i := len(mws) - 1; i >= 0; i-- {
			final = mws[i](final)
		}
		return final
	}
}

// Logging logs method, path, and duration for each request.
func Logging(logger *log.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			logger.Printf("-> %s %s", r.Method, r.URL.Path)
			next.ServeHTTP(w, r)
			logger.Printf("<- %s %s (%v)", r.Method, r.URL.Path, time.Since(start))
		})
	}
}

// Auth checks for a valid API key in the Authorization header.
func Auth(validKey string) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("Authorization") != "Bearer "+validKey {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RateLimit rejects requests after maxReqs total (simple global counter).
func RateLimit(maxReqs int64) Middleware {
	var count atomic.Int64
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if count.Add(1) > maxReqs {
				http.Error(w, "rate limit exceeded", http.StatusTooManyRequests)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// --- Usage ---

func Example() {
	logger := log.Default()

	// Compose the middleware stack
	stack := Chain(
		Logging(logger),    // outermost: logs all requests
		Auth("secret-key"), // rejects unauthenticated
		RateLimit(1000),    // innermost: rate-limits authenticated requests
	)

	mux := http.NewServeMux()
	mux.HandleFunc("/api/data", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status":"ok"}`))
	})

	// Apply stack to the handler
	http.ListenAndServe(":8080", stack(mux))
}
```

The `Chain` function applies middlewares right-to-left so the first listed middleware is the outermost wrapper - matching reading order. Each middleware returns early to short-circuit (auth returns 401, rate limit returns 429). This pattern is identical to what `chi.Use()` and `alice.New()` implement internally.'''
    ),

    (
        "go_deep5_13",
        r'''Build a plugin system in Go using interfaces. Plugins register by name, can be loaded/unloaded, and implement a common lifecycle interface (Init, Execute, Shutdown).''',
        r'''<think>
A plugin system needs: a Plugin interface, a Registry to manage plugins,
and lifecycle management (init, execute, shutdown).
The Plugin interface defines the contract: Name, Init, Execute, Shutdown.
Registry stores plugins by name in a map.
Register adds a plugin, Load initializes it, Unload shuts it down.
I should track plugin state (registered, loaded, running).
Shutdown should be called in reverse order of initialization.
I will use a mutex for thread safety since plugins might be managed concurrently.
This pattern is used in systems like Terraform providers, Caddy modules.
Error handling: Init failure should prevent the plugin from being marked loaded.
I will track load order in a slice for reverse shutdown.
</think>

```go
package plugin

import (
	"fmt"
	"sync"
)

// Plugin defines the lifecycle interface for all plugins.
type Plugin interface {
	Name() string
	Init(config map[string]string) error
	Execute(input []byte) ([]byte, error)
	Shutdown() error
}

// State represents a plugin lifecycle state.
type State int

const (
	Registered State = iota
	Loaded
	Stopped
)

type entry struct {
	plugin Plugin
	state  State
}

// Registry manages plugin registration and lifecycle.
type Registry struct {
	mu      sync.RWMutex
	plugins map[string]*entry
	order   []string // tracks load order for ordered shutdown
}

// NewRegistry creates an empty plugin registry.
func NewRegistry() *Registry {
	return &Registry{plugins: make(map[string]*entry)}
}

// Register adds a plugin without initializing it.
func (r *Registry) Register(p Plugin) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	name := p.Name()
	if _, exists := r.plugins[name]; exists {
		return fmt.Errorf("plugin %q already registered", name)
	}
	r.plugins[name] = &entry{plugin: p, state: Registered}
	return nil
}

// Load initializes a registered plugin with the given config.
func (r *Registry) Load(name string, config map[string]string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	e, ok := r.plugins[name]
	if !ok {
		return fmt.Errorf("plugin %q not found", name)
	}
	if e.state == Loaded {
		return fmt.Errorf("plugin %q already loaded", name)
	}
	if err := e.plugin.Init(config); err != nil {
		return fmt.Errorf("init %q: %w", name, err)
	}
	e.state = Loaded
	r.order = append(r.order, name)
	return nil
}

// Execute runs a specific loaded plugin.
func (r *Registry) Execute(name string, input []byte) ([]byte, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	e, ok := r.plugins[name]
	if !ok {
		return nil, fmt.Errorf("plugin %q not found", name)
	}
	if e.state != Loaded {
		return nil, fmt.Errorf("plugin %q not loaded", name)
	}
	return e.plugin.Execute(input)
}

// ShutdownAll stops all loaded plugins in reverse load order.
func (r *Registry) ShutdownAll() error {
	r.mu.Lock()
	defer r.mu.Unlock()

	var errs []error
	for i := len(r.order) - 1; i >= 0; i-- {
		name := r.order[i]
		e := r.plugins[name]
		if e.state == Loaded {
			if err := e.plugin.Shutdown(); err != nil {
				errs = append(errs, fmt.Errorf("shutdown %q: %w", name, err))
			}
			e.state = Stopped
		}
	}
	if len(errs) > 0 {
		return fmt.Errorf("shutdown errors: %v", errs)
	}
	return nil
}

// List returns the names and states of all plugins.
func (r *Registry) List() map[string]State {
	r.mu.RLock()
	defer r.mu.RUnlock()
	result := make(map[string]State, len(r.plugins))
	for name, e := range r.plugins {
		result[name] = e.state
	}
	return result
}
```

Reverse-order shutdown prevents dependency issues - if plugin B depends on A, B was loaded after A and will be shut down first. The `RWMutex` allows concurrent `Execute` calls (read lock) while serializing registration and lifecycle changes (write lock). This pattern scales well: add `Dependencies() []string` to the interface for automatic topological ordering.'''
    ),

    (
        "go_deep5_14",
        r'''Implement the strategy pattern in Go using interfaces for different compression algorithms. The caller selects the strategy at runtime.''',
        r'''<think>
The strategy pattern lets you swap algorithms at runtime.
I will define a Compressor interface with Compress and Decompress methods.
Concrete strategies: Gzip, Zlib, NoOp (passthrough).
A Processor struct holds the current strategy and delegates to it.
The caller can change the strategy without changing the Processor.
I should use real Go compression packages for authenticity.
Each strategy wraps the stdlib compress packages.
Error handling is important - compression can fail on invalid data.
I will keep the interface simple: Compress([]byte) ([]byte, error).
The ByName factory function bridges string configs to typed strategies.
</think>

```go
package compression

import (
	"bytes"
	"compress/gzip"
	"compress/zlib"
	"fmt"
	"io"
)

// Compressor defines a compression strategy.
type Compressor interface {
	Name() string
	Compress(data []byte) ([]byte, error)
	Decompress(data []byte) ([]byte, error)
}

// Processor applies a pluggable compression strategy.
type Processor struct {
	strategy Compressor
}

// NewProcessor creates a processor with the given strategy.
func NewProcessor(strategy Compressor) *Processor {
	return &Processor{strategy: strategy}
}

// SetStrategy changes the compression strategy at runtime.
func (p *Processor) SetStrategy(s Compressor) {
	p.strategy = s
}

// Process compresses data using the current strategy.
func (p *Processor) Process(data []byte) ([]byte, error) {
	return p.strategy.Compress(data)
}

// --- Strategies ---

// GzipStrategy compresses using gzip.
type GzipStrategy struct{}

func (GzipStrategy) Name() string { return "gzip" }

func (GzipStrategy) Compress(data []byte) ([]byte, error) {
	var buf bytes.Buffer
	w := gzip.NewWriter(&buf)
	if _, err := w.Write(data); err != nil {
		return nil, fmt.Errorf("gzip write: %w", err)
	}
	if err := w.Close(); err != nil {
		return nil, fmt.Errorf("gzip close: %w", err)
	}
	return buf.Bytes(), nil
}

func (GzipStrategy) Decompress(data []byte) ([]byte, error) {
	r, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("gzip reader: %w", err)
	}
	defer r.Close()
	return io.ReadAll(r)
}

// ZlibStrategy compresses using zlib.
type ZlibStrategy struct{}

func (ZlibStrategy) Name() string { return "zlib" }

func (ZlibStrategy) Compress(data []byte) ([]byte, error) {
	var buf bytes.Buffer
	w := zlib.NewWriter(&buf)
	if _, err := w.Write(data); err != nil {
		return nil, fmt.Errorf("zlib write: %w", err)
	}
	if err := w.Close(); err != nil {
		return nil, fmt.Errorf("zlib close: %w", err)
	}
	return buf.Bytes(), nil
}

func (ZlibStrategy) Decompress(data []byte) ([]byte, error) {
	r, err := zlib.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("zlib reader: %w", err)
	}
	defer r.Close()
	return io.ReadAll(r)
}

// NoOpStrategy passes data through unchanged.
type NoOpStrategy struct{}

func (NoOpStrategy) Name() string                           { return "none" }
func (NoOpStrategy) Compress(data []byte) ([]byte, error)   { return data, nil }
func (NoOpStrategy) Decompress(data []byte) ([]byte, error) { return data, nil }

// ByName returns a strategy by name, or an error for unknown names.
func ByName(name string) (Compressor, error) {
	switch name {
	case "gzip":
		return GzipStrategy{}, nil
	case "zlib":
		return ZlibStrategy{}, nil
	case "none":
		return NoOpStrategy{}, nil
	default:
		return nil, fmt.Errorf("unknown compression: %q", name)
	}
}
```

The strategy pattern shines when the algorithm must be selected at runtime - e.g., based on a config file or HTTP Accept-Encoding header. The `ByName` factory function bridges string configs to typed strategies. Each strategy is a small struct with no state, making them safe to share across goroutines. Adding a new strategy (e.g., Snappy, Zstd) requires zero changes to the `Processor`.'''
    ),

    (
        "go_deep5_15",
        r'''Create a generic event emitter in Go where listeners subscribe to typed events. Use generics so each event type has its own subscriber list with type-safe callbacks.''',
        r'''<think>
A type-safe event emitter is tricky in Go because you need different
callback signatures per event type.
One approach: an Emitter[T] per event type, stored in a bus.
Each Emitter[T] holds []func(T) subscribers.
The cleanest approach is to make Emitter[T] standalone and
let the user compose them. A Bus with type erasure is less type-safe.
I will show both: a generic Emitter[T] and a typed EventBus that composes them.
Emitter should support Subscribe (returns unsubscribe func), Emit, and Clear.
Thread safety via RWMutex - multiple emitters, concurrent emit/subscribe.
The unsubscribe function removes the specific listener by ID.
I will use an incrementing ID rather than searching by function pointer.
</think>

```go
package events

import (
	"sync"
	"sync/atomic"
)

// Emitter is a type-safe event emitter for events of type T.
type Emitter[T any] struct {
	mu        sync.RWMutex
	listeners map[uint64]func(T)
	nextID    atomic.Uint64
}

// NewEmitter creates an emitter for a specific event type.
func NewEmitter[T any]() *Emitter[T] {
	return &Emitter[T]{listeners: make(map[uint64]func(T))}
}

// Subscribe registers a listener. Returns an unsubscribe function.
func (e *Emitter[T]) Subscribe(fn func(T)) func() {
	id := e.nextID.Add(1)
	e.mu.Lock()
	e.listeners[id] = fn
	e.mu.Unlock()

	return func() {
		e.mu.Lock()
		delete(e.listeners, id)
		e.mu.Unlock()
	}
}

// Emit sends an event to all registered listeners.
func (e *Emitter[T]) Emit(event T) {
	e.mu.RLock()
	// Copy listeners to avoid holding the lock during callbacks
	fns := make([]func(T), 0, len(e.listeners))
	for _, fn := range e.listeners {
		fns = append(fns, fn)
	}
	e.mu.RUnlock()

	for _, fn := range fns {
		fn(event)
	}
}

// Count returns the number of active listeners.
func (e *Emitter[T]) Count() int {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return len(e.listeners)
}

// Clear removes all listeners.
func (e *Emitter[T]) Clear() {
	e.mu.Lock()
	e.listeners = make(map[uint64]func(T))
	e.mu.Unlock()
}

// --- Typed event bus example ---

type UserCreated struct {
	ID    int
	Email string
}

type OrderPlaced struct {
	OrderID string
	Total   float64
}

// AppEvents composes type-safe emitters for each event kind.
type AppEvents struct {
	UserCreated *Emitter[UserCreated]
	OrderPlaced *Emitter[OrderPlaced]
}

func NewAppEvents() *AppEvents {
	return &AppEvents{
		UserCreated: NewEmitter[UserCreated](),
		OrderPlaced: NewEmitter[OrderPlaced](),
	}
}

func Example() {
	bus := NewAppEvents()

	unsub := bus.UserCreated.Subscribe(func(e UserCreated) {
		// send welcome email
		_ = e.Email
	})
	defer unsub()

	bus.OrderPlaced.Subscribe(func(e OrderPlaced) {
		// process payment
		_ = e.Total
	})

	bus.UserCreated.Emit(UserCreated{ID: 1, Email: "alice@example.com"})
	bus.OrderPlaced.Emit(OrderPlaced{OrderID: "ORD-001", Total: 59.99})
}
```

Each `Emitter[T]` is fully type-safe - you cannot subscribe to `UserCreated` with an `OrderPlaced` handler. The unsubscribe function returned by `Subscribe` captures the listener ID via closure, making cleanup easy with `defer`. Listeners are copied before emission so that a callback can safely unsubscribe without deadlocking. The `AppEvents` struct acts as a typed bus - add new event types by adding new fields.'''
    ),

    # -- 16-20: Type constraints and advanced generics --

    (
        "go_deep5_16",
        r'''Define custom type constraints in Go generics for numeric operations. Create a Number constraint that includes all integer and float types, and write generic Sum, Average, and Clamp functions.''',
        r'''<think>
Go type constraints use interface type sets.
I can build a Number constraint by listing all numeric types with the tilde prefix.
The tilde includes named types derived from the base types.
golang.org/x/exp/constraints has these, but I will define them manually.
Sum is straightforward - loop and add.
Average needs to return float64 since integer division loses precision.
Clamp restricts a value to [min, max] range.
For Sum and Average, I need the + operator - hence the Number constraint.
Edge case: Average of an empty slice - return 0.
I will also add Min, Max, and Abs as utility functions.
The tilde prefix is crucial for named types like type Celsius float64.
</think>

```go
package numeric

// Signed includes all signed integer types.
type Signed interface {
	~int | ~int8 | ~int16 | ~int32 | ~int64
}

// Unsigned includes all unsigned integer types.
type Unsigned interface {
	~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 | ~uintptr
}

// Integer includes all integer types.
type Integer interface {
	Signed | Unsigned
}

// Float includes all floating-point types.
type Float interface {
	~float32 | ~float64
}

// Number includes all numeric types that support arithmetic.
type Number interface {
	Integer | Float
}

// Sum returns the sum of all elements.
func Sum[T Number](vals []T) T {
	var total T
	for _, v := range vals {
		total += v
	}
	return total
}

// Average returns the arithmetic mean as float64.
// Returns 0 for an empty slice.
func Average[T Number](vals []T) float64 {
	if len(vals) == 0 {
		return 0
	}
	var total float64
	for _, v := range vals {
		total += float64(v)
	}
	return total / float64(len(vals))
}

// Clamp restricts val to the range [lo, hi].
func Clamp[T Number](val, lo, hi T) T {
	if val < lo {
		return lo
	}
	if val > hi {
		return hi
	}
	return val
}

// Min returns the smaller of two values.
func Min[T Number](a, b T) T {
	if a < b {
		return a
	}
	return b
}

// Max returns the larger of two values.
func Max[T Number](a, b T) T {
	if a > b {
		return a
	}
	return b
}

// Abs returns the absolute value. Only meaningful for signed types and floats.
func Abs[T Signed | Float](val T) T {
	if val < 0 {
		return -val
	}
	return val
}

// --- Example with named types ---

type Celsius float64
type Meters int

func Example() {
	temps := []Celsius{20.5, 22.1, 19.8}
	avg := Average(temps) // works because ~float64

	distances := []Meters{100, 200, 300}
	total := Sum(distances) // works because ~int

	clamped := Clamp(Celsius(45.0), 0.0, 40.0)
	// clamped = 40.0

	_, _, _ = avg, total, clamped
}
```

The `~` prefix in type constraints is crucial - it means "any type whose underlying type is X". Without it, named types like `Celsius` (underlying `float64`) would not satisfy the constraint. The `Number` constraint composes `Integer | Float` using union syntax. `Average` converts to `float64` internally to avoid integer truncation.'''
    ),

    (
        "go_deep5_17",
        r'''Create a generic Repository interface in Go with CRUD operations that uses type parameters for both the entity and its ID type. Implement an in-memory version.''',
        r'''<think>
A generic repository abstracts data access with type-safe CRUD.
Two type parameters: T for the entity, ID for the primary key.
The entity needs a way to get its ID - I will use an interface constraint.
Repository methods: Create, FindByID, FindAll, Update, Delete.
The in-memory implementation uses a map[ID]T.
ID must be comparable for map keys.
I should define an Entity[ID] interface that requires GetID() ID.
Create should fail if the ID already exists.
Update should fail if the ID does not exist.
I will add thread safety with RWMutex.
Return custom errors for not-found and duplicate cases.
This same interface can back SQL or Redis implementations.
</think>

```go
package repo

import (
	"errors"
	"fmt"
	"sync"
)

var (
	ErrNotFound  = errors.New("entity not found")
	ErrDuplicate = errors.New("entity already exists")
)

// Entity is a constraint requiring entities to expose their ID.
type Entity[ID comparable] interface {
	GetID() ID
}

// Repository defines generic CRUD operations.
type Repository[T Entity[ID], ID comparable] interface {
	Create(entity T) error
	FindByID(id ID) (T, error)
	FindAll() []T
	Update(entity T) error
	Delete(id ID) error
}

// MemoryRepo is a thread-safe in-memory Repository.
type MemoryRepo[T Entity[ID], ID comparable] struct {
	mu    sync.RWMutex
	store map[ID]T
}

// NewMemoryRepo creates an empty in-memory repository.
func NewMemoryRepo[T Entity[ID], ID comparable]() *MemoryRepo[T, ID] {
	return &MemoryRepo[T, ID]{store: make(map[ID]T)}
}

func (r *MemoryRepo[T, ID]) Create(entity T) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	id := entity.GetID()
	if _, exists := r.store[id]; exists {
		return fmt.Errorf("%w: %v", ErrDuplicate, id)
	}
	r.store[id] = entity
	return nil
}

func (r *MemoryRepo[T, ID]) FindByID(id ID) (T, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	entity, ok := r.store[id]
	if !ok {
		var zero T
		return zero, fmt.Errorf("%w: %v", ErrNotFound, id)
	}
	return entity, nil
}

func (r *MemoryRepo[T, ID]) FindAll() []T {
	r.mu.RLock()
	defer r.mu.RUnlock()

	result := make([]T, 0, len(r.store))
	for _, entity := range r.store {
		result = append(result, entity)
	}
	return result
}

func (r *MemoryRepo[T, ID]) Update(entity T) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	id := entity.GetID()
	if _, exists := r.store[id]; !exists {
		return fmt.Errorf("%w: %v", ErrNotFound, id)
	}
	r.store[id] = entity
	return nil
}

func (r *MemoryRepo[T, ID]) Delete(id ID) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.store[id]; !exists {
		return fmt.Errorf("%w: %v", ErrNotFound, id)
	}
	delete(r.store, id)
	return nil
}

// --- Usage ---

type User struct {
	ID    int
	Name  string
	Email string
}

func (u User) GetID() int { return u.ID }

func Example() {
	users := NewMemoryRepo[User, int]()

	_ = users.Create(User{ID: 1, Name: "Alice", Email: "alice@example.com"})
	_ = users.Create(User{ID: 2, Name: "Bob", Email: "bob@example.com"})

	user, err := users.FindByID(1)
	if err != nil {
		// handle
	}

	user.Email = "newalice@example.com"
	_ = users.Update(user)

	all := users.FindAll()
	_ = all
}
```

The dual type parameters `[T Entity[ID], ID comparable]` give full type safety - `FindByID` returns a `User`, not `any`. Wrapping sentinel errors with `%w` lets callers use `errors.Is(err, ErrNotFound)` for control flow. The `Entity` constraint avoids needing a separate ID extractor function - the entity itself knows its ID.'''
    ),

    (
        "go_deep5_18",
        r'''Implement a type-safe builder pattern in Go using generics and method chaining. The builder should enforce required fields at compile time through staged types.''',
        r'''<think>
Using staged types to encode state in the type system at compile time.
The idea: the builder changes its type after each required field is set.
So you cannot call Build() until all required fields have been set.
A pragmatic approach: use separate builder types for each stage.
Stage 1: RequiresName leads to Stage 2: RequiresEmail leads to ReadyBuilder.
Each stage only exposes the next setter and Build is only on the final stage.
This gives compile-time safety at the cost of more boilerplate.
I will show both the stage-based approach and a simpler runtime-validated version.
Go generics cannot change type parameters via method returns easily,
so the staged approach uses concrete types rather than phantom type params.
Optional fields are methods on the final ReadyBuilder that return self.
</think>

```go
package builder

import "fmt"

// --- Staged builder: compile-time required field enforcement ---

// User is the final constructed type.
type User struct {
	Name    string
	Email   string
	Age     int    // optional
	Country string // optional
}

// Stage1 requires Name to be set.
type Stage1 struct{}

// Stage2 requires Email to be set.
type Stage2 struct {
	name string
}

// ReadyBuilder has all required fields and can build.
type ReadyBuilder struct {
	name    string
	email   string
	age     int
	country string
}

// NewUserBuilder starts the builder chain.
func NewUserBuilder() Stage1 {
	return Stage1{}
}

// WithName sets the name (required, moves to Stage2).
func (Stage1) WithName(name string) Stage2 {
	return Stage2{name: name}
}

// WithEmail sets the email (required, moves to ReadyBuilder).
func (s Stage2) WithEmail(email string) *ReadyBuilder {
	return &ReadyBuilder{name: s.name, email: email}
}

// WithAge sets an optional age.
func (b *ReadyBuilder) WithAge(age int) *ReadyBuilder {
	b.age = age
	return b
}

// WithCountry sets an optional country.
func (b *ReadyBuilder) WithCountry(c string) *ReadyBuilder {
	b.country = c
	return b
}

// Build creates the User. Only available after required fields are set.
func (b *ReadyBuilder) Build() User {
	return User{
		Name:    b.name,
		Email:   b.email,
		Age:     b.age,
		Country: b.country,
	}
}

// --- Generic builder with runtime validation ---

// Builder is a generic builder with runtime required-field checking.
type Builder[T any] struct {
	setters  []func(*T)
	required map[string]bool
	set      map[string]bool
}

// NewBuilder creates a generic builder for any type.
func NewBuilder[T any]() *Builder[T] {
	return &Builder[T]{
		required: make(map[string]bool),
		set:      make(map[string]bool),
	}
}

// Require marks a field name as required.
func (b *Builder[T]) Require(fields ...string) *Builder[T] {
	for _, f := range fields {
		b.required[f] = true
	}
	return b
}

// Set applies a setter function and marks the field as set.
func (b *Builder[T]) Set(field string, fn func(*T)) *Builder[T] {
	b.setters = append(b.setters, fn)
	b.set[field] = true
	return b
}

// Build creates T after validating all required fields are set.
func (b *Builder[T]) Build() (T, error) {
	var zero T
	for field := range b.required {
		if !b.set[field] {
			return zero, fmt.Errorf("required field %q not set", field)
		}
	}
	val := new(T)
	for _, fn := range b.setters {
		fn(val)
	}
	return *val, nil
}

// --- Usage ---

func Example() {
	// Staged builder: will not compile without Name and Email
	user := NewUserBuilder().
		WithName("Alice").
		WithEmail("alice@example.com").
		WithAge(30).
		Build()
	_ = user

	// Generic builder: runtime validation
	cfg, err := NewBuilder[User]().
		Require("name", "email").
		Set("name", func(u *User) { u.Name = "Bob" }).
		Set("email", func(u *User) { u.Email = "bob@example.com" }).
		Build()
	if err != nil {
		panic(err)
	}
	_ = cfg
}
```

The staged builder gives true compile-time safety: calling `Build()` on `Stage1` or `Stage2` is a type error. The trade-off is boilerplate - each required field needs a new stage type. The generic runtime builder is more flexible and scales to many fields but catches missing fields at runtime. Choose staged for critical types with few required fields; choose the generic builder for config objects with many fields.'''
    ),

    (
        "go_deep5_19",
        r'''Show how to use type sets in Go constraints to restrict generic functions to specific concrete types. Demonstrate with a ParseID function that only accepts string and int ID types.''',
        r'''<think>
Type sets let you list exactly which types a constraint allows.
This is more restrictive than cmp.Ordered - only specific types.
A ParseID function that accepts string or int IDs is a good example.
I can define an IDType constraint: ~string | ~int | ~int64.
The function behavior differs per type - so I need a type switch on any.
In Go generics, you cannot do type switches on T directly.
But you can convert to any and switch. That is the standard pattern.
I will show how type sets interact with method constraints too.
Also show that type sets can include methods: constraint with both type list and methods.
This is useful for domain types: only accept our specific ID types.
</think>

```go
package ids

import (
	"fmt"
	"strconv"
)

// IDType restricts to types that can serve as identifiers.
type IDType interface {
	~string | ~int | ~int64
}

// ParseID converts a string representation to the target ID type.
func ParseID[T IDType](raw string) (T, error) {
	var zero T

	// Convert T to any for type switching
	switch any(zero).(type) {
	case string:
		return any(raw).(T), nil
	case int:
		v, err := strconv.Atoi(raw)
		if err != nil {
			return zero, fmt.Errorf("invalid int ID %q: %w", raw, err)
		}
		return any(v).(T), nil
	case int64:
		v, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			return zero, fmt.Errorf("invalid int64 ID %q: %w", raw, err)
		}
		return any(v).(T), nil
	default:
		return zero, fmt.Errorf("unsupported ID type %T", zero)
	}
}

// FormatID converts any ID to its string form.
func FormatID[T IDType](id T) string {
	switch v := any(id).(type) {
	case string:
		return v
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	default:
		return fmt.Sprintf("%v", id)
	}
}

// --- Type set with methods ---

// Stringer is a type set that also requires String().
type Stringer interface {
	~int | ~string
	String() string
}

// Named types that satisfy Stringer

type UserID int

func (u UserID) String() string { return fmt.Sprintf("user-%d", u) }

type TeamID string

func (t TeamID) String() string { return fmt.Sprintf("team-%s", t) }

// Describe only accepts types in the type set that also have String().
func Describe[T Stringer](id T) string {
	return "ID: " + id.String()
}

// --- Usage ---

func Example() {
	// ParseID infers T from usage context
	userID, _ := ParseID[int]("42")       // 42
	slug, _ := ParseID[string]("abc-123") // "abc-123"

	// FormatID works with named types too (tilde prefix)
	type OrderID int64
	formatted := FormatID(OrderID(999)) // "999"

	// Stringer constraint: must be ~int|~string AND have String()
	desc := Describe(UserID(7))        // "ID: user-7"
	desc2 := Describe(TeamID("alpha")) // "ID: team-alpha"

	// This would NOT compile:
	// Describe(42)  -- int has no String() method
	// ParseID[float64]("3.14")  -- float64 not in IDType

	_, _, _, _, _ = userID, slug, formatted, desc, desc2
}
```

Type sets are Go's answer to "I want this generic to work with exactly these types." The tilde prefix includes derived types - so `type OrderID int64` satisfies `~int64`. Combining a type set with method requirements (like `Stringer`) creates powerful constraints: the type must be structurally one of the listed types AND implement the required methods. The `any(zero).(type)` pattern is the canonical way to do type-dependent logic inside a generic function.'''
    ),

    (
        "go_deep5_20",
        r'''Build a generic Result[T] type in Go (similar to Rust's Result) with Ok, Err constructors and Map, FlatMap, UnwrapOr methods.''',
        r'''<think>
Rust's Result is a sum type - Go does not have native sum types.
I will simulate it with a struct holding value and error, plus a flag.
Ok(value) creates a success, Err(error) creates a failure.
Map transforms the value if Ok, passes through Err.
FlatMap (AndThen) applies a function that itself returns Result.
UnwrapOr returns the value or a default.
I need to handle the type parameter carefully - Map changes T to U.
In Go, you cannot have methods with new type parameters, so Map and FlatMap
must be standalone functions, not methods.
This is a known limitation of Go generics.
I will add methods for same-type operations and functions for type-changing ones.
Also add IsOk, IsErr, Match for pattern matching.
</think>

```go
package result

import "fmt"

// Result represents either a success value or an error.
type Result[T any] struct {
	value T
	err   error
	ok    bool
}

// Ok creates a successful Result.
func Ok[T any](val T) Result[T] {
	return Result[T]{value: val, ok: true}
}

// Err creates a failed Result.
func Err[T any](err error) Result[T] {
	return Result[T]{err: err, ok: false}
}

// Errf creates a failed Result with a formatted error message.
func Errf[T any](format string, args ...any) Result[T] {
	return Result[T]{err: fmt.Errorf(format, args...), ok: false}
}

// IsOk reports whether the result is successful.
func (r Result[T]) IsOk() bool { return r.ok }

// IsErr reports whether the result is an error.
func (r Result[T]) IsErr() bool { return !r.ok }

// Unwrap returns the value or panics if Err.
func (r Result[T]) Unwrap() T {
	if !r.ok {
		panic(fmt.Sprintf("unwrap on Err: %v", r.err))
	}
	return r.value
}

// UnwrapOr returns the value or the provided default.
func (r Result[T]) UnwrapOr(def T) T {
	if r.ok {
		return r.value
	}
	return def
}

// UnwrapOrElse returns the value or calls fn to compute a default.
func (r Result[T]) UnwrapOrElse(fn func(error) T) T {
	if r.ok {
		return r.value
	}
	return fn(r.err)
}

// Error returns the error, or nil if Ok.
func (r Result[T]) Error() error { return r.err }

// Match calls okFn if successful, errFn if failed.
func (r Result[T]) Match(okFn func(T), errFn func(error)) {
	if r.ok {
		okFn(r.value)
	} else {
		errFn(r.err)
	}
}

// ToGoStyle converts Result to Go's (T, error) idiom.
func (r Result[T]) ToGoStyle() (T, error) {
	return r.value, r.err
}

// --- Free functions for type-changing operations ---

// Map transforms Result[T] to Result[U] if Ok.
func Map[T, U any](r Result[T], fn func(T) U) Result[U] {
	if !r.ok {
		return Err[U](r.err)
	}
	return Ok(fn(r.value))
}

// FlatMap (AndThen) chains operations that return Result.
func FlatMap[T, U any](r Result[T], fn func(T) Result[U]) Result[U] {
	if !r.ok {
		return Err[U](r.err)
	}
	return fn(r.value)
}

// FromGoStyle converts Go's (T, error) to Result[T].
func FromGoStyle[T any](val T, err error) Result[T] {
	if err != nil {
		return Err[T](err)
	}
	return Ok(val)
}

// --- Example ---

func Example() {
	// Chain operations that might fail
	r := Ok(42)
	doubled := Map(r, func(n int) int { return n * 2 })
	// doubled = Ok(84)

	asStr := Map(doubled, func(n int) string {
		return fmt.Sprintf("value: %d", n)
	})
	// asStr = Ok("value: 84")

	// FlatMap for operations that return Result
	parsed := FlatMap(Ok("123"), func(s string) Result[int] {
		return Ok(123)
	})

	// Bridge with Go idiom
	val := parsed.UnwrapOr(0) // 123

	// Pattern matching
	asStr.Match(
		func(s string) { fmt.Println(s) },
		func(err error) { fmt.Println("error:", err) },
	)

	_ = val
}
```

Go generics cannot add new type parameters to methods - that is why `Map` and `FlatMap` are free functions, not methods. This is a well-known limitation. `FromGoStyle` and `ToGoStyle` bridge between Go's `(T, error)` convention and the `Result` type, making incremental adoption easy. The `Match` method simulates pattern matching - useful when you need to handle both cases without unpacking.'''
    ),

    # -- 21-25: Reflection and type assertions --

    (
        "go_deep5_21",
        r'''Write a Go function that parses struct tags using reflection to build a map of field names to their tag values. Support multiple tag keys like json, db, and validate.''',
        r'''<think>
Go's reflect package provides StructTag parsing via field.Tag.Get().
I need to iterate over struct fields using reflect.TypeOf.
For each field, extract the requested tag values.
Result: map[fieldName]map[tagKey]tagValue.
I should handle unexported fields (skip them).
Tag values can have options: json:"name,omitempty" - I should parse those.
I will split on comma and return the primary name plus options.
I will accept the struct as any and use reflection to get its type.
Edge case: tag not present returns empty string from Get().
I should distinguish "not present" from "empty value" - use Lookup().
Also handle the json:"-" convention for excluded fields.
</think>

```go
package tags

import (
	"reflect"
	"strings"
)

// TagInfo holds parsed tag information for a single field.
type TagInfo struct {
	Name    string   // primary tag value (before first comma)
	Options []string // everything after the first comma
	Raw     string   // full tag value
}

// FieldTags maps tag keys to their parsed info for one field.
type FieldTags map[string]TagInfo

// ParseStructTags extracts tag values for the given keys from a struct.
// Returns map[fieldName]FieldTags.
func ParseStructTags(v any, tagKeys ...string) map[string]FieldTags {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil
	}

	result := make(map[string]FieldTags)

	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)

		// Skip unexported fields
		if !field.IsExported() {
			continue
		}

		fieldTags := make(FieldTags)
		for _, key := range tagKeys {
			raw, ok := field.Tag.Lookup(key)
			if !ok {
				continue
			}
			info := TagInfo{Raw: raw}
			parts := strings.Split(raw, ",")
			if len(parts) > 0 {
				info.Name = parts[0]
				info.Options = parts[1:]
			}
			fieldTags[key] = info
		}

		if len(fieldTags) > 0 {
			result[field.Name] = fieldTags
		}
	}

	return result
}

// ColumnNames extracts a specific tag key primary name for each field.
// Useful for quick "give me all JSON names" or "all DB columns".
func ColumnNames(v any, tagKey string) map[string]string {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil
	}

	result := make(map[string]string)
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}
		raw, ok := field.Tag.Lookup(tagKey)
		if !ok {
			continue
		}
		name := strings.SplitN(raw, ",", 2)[0]
		if name == "-" {
			continue // field explicitly excluded
		}
		if name == "" {
			name = field.Name // use struct field name as fallback
		}
		result[field.Name] = name
	}
	return result
}

// HasOption checks whether a field tag includes a specific option.
func HasOption(v any, fieldName, tagKey, option string) bool {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}
	field, ok := t.FieldByName(fieldName)
	if !ok {
		return false
	}
	raw, ok := field.Tag.Lookup(tagKey)
	if !ok {
		return false
	}
	parts := strings.Split(raw, ",")
	for _, p := range parts[1:] { // skip the name part
		if p == option {
			return true
		}
	}
	return false
}

// --- Example ---

type User struct {
	ID        int    `json:"id" db:"user_id"`
	FirstName string `json:"first_name,omitempty" db:"first_name" validate:"required"`
	Email     string `json:"email" db:"email" validate:"required,email"`
	password  string // unexported, skipped
	Ignore    string `json:"-"`
}

func Example() {
	tags := ParseStructTags(User{}, "json", "db", "validate")
	// tags["Email"]["validate"] = TagInfo{Name:"required", Options:["email"]}

	cols := ColumnNames(User{}, "db")
	// cols = {"ID":"user_id", "FirstName":"first_name", "Email":"email"}

	hasOmit := HasOption(User{}, "FirstName", "json", "omitempty")
	// true

	_, _, _ = tags, cols, hasOmit
}
```

Using `field.Tag.Lookup()` instead of `Get()` lets you distinguish between a missing tag and an empty tag value. The `"-"` check in `ColumnNames` respects the convention where `json:"-"` means "skip this field." Splitting on the first comma separates the name from options. This is essentially what `encoding/json` does internally to resolve field names.'''
    ),

    (
        "go_deep5_22",
        r'''Implement a dynamic dispatch system in Go where handlers are registered by type and dispatched at runtime. Use type assertions and a registry pattern.''',
        r'''<think>
Dynamic dispatch by type: register a handler for each concrete type,
then dispatch an incoming value to the correct handler.
This is like a type-safe command/event bus.
Use reflect.TypeOf to get the runtime type as a map key.
The handler registry maps reflect.Type to a handler function.
The handler function needs to accept the specific type - but the registry
stores func(any) since we need a uniform signature.
I can add type-safe registration via a generic helper function.
Dispatch does a map lookup on the runtime type and calls the handler.
Edge case: no handler registered - return an error.
This pattern is used in message routers, event sourcing, CQRS.
I will use RWMutex for concurrent access safety.
</think>

```go
package dispatch

import (
	"fmt"
	"reflect"
	"sync"
)

// Handler processes a value of a specific type.
type Handler func(any) error

// Dispatcher routes values to type-specific handlers.
type Dispatcher struct {
	mu       sync.RWMutex
	handlers map[reflect.Type]Handler
}

// NewDispatcher creates an empty dispatcher.
func NewDispatcher() *Dispatcher {
	return &Dispatcher{handlers: make(map[reflect.Type]Handler)}
}

// Register adds a type-safe handler. Uses generics to wrap the typed function.
func Register[T any](d *Dispatcher, handler func(T) error) {
	var zero T
	t := reflect.TypeOf(zero)
	if t == nil {
		// T is an interface - use pointer-to-interface trick
		t = reflect.TypeOf((*T)(nil)).Elem()
	}

	d.mu.Lock()
	defer d.mu.Unlock()

	d.handlers[t] = func(v any) error {
		typed, ok := v.(T)
		if !ok {
			return fmt.Errorf("type assertion failed: expected %T, got %T", zero, v)
		}
		return handler(typed)
	}
}

// Dispatch routes a value to its registered handler.
func (d *Dispatcher) Dispatch(v any) error {
	t := reflect.TypeOf(v)

	d.mu.RLock()
	handler, ok := d.handlers[t]
	d.mu.RUnlock()

	if !ok {
		return fmt.Errorf("no handler registered for type %s", t)
	}
	return handler(v)
}

// DispatchAll sends multiple values, stopping on first error.
func (d *Dispatcher) DispatchAll(values ...any) error {
	for _, v := range values {
		if err := d.Dispatch(v); err != nil {
			return err
		}
	}
	return nil
}

// HasHandler checks if a handler exists for the given type.
func HasHandler[T any](d *Dispatcher) bool {
	var zero T
	t := reflect.TypeOf(zero)
	if t == nil {
		t = reflect.TypeOf((*T)(nil)).Elem()
	}
	d.mu.RLock()
	defer d.mu.RUnlock()
	_, ok := d.handlers[t]
	return ok
}

// --- Example: event sourcing ---

type UserCreated struct {
	ID   int
	Name string
}

type OrderPlaced struct {
	OrderID string
	UserID  int
	Total   float64
}

type OrderShipped struct {
	OrderID    string
	TrackingNo string
}

func Example() {
	d := NewDispatcher()

	// Register type-safe handlers
	Register(d, func(e UserCreated) error {
		fmt.Printf("Creating user %d: %s\n", e.ID, e.Name)
		return nil
	})

	Register(d, func(e OrderPlaced) error {
		fmt.Printf("Order %s placed: $%.2f\n", e.OrderID, e.Total)
		return nil
	})

	Register(d, func(e OrderShipped) error {
		fmt.Printf("Order %s shipped: %s\n", e.OrderID, e.TrackingNo)
		return nil
	})

	// Dispatch events
	events := []any{
		UserCreated{ID: 1, Name: "Alice"},
		OrderPlaced{OrderID: "ORD-1", UserID: 1, Total: 99.99},
		OrderShipped{OrderID: "ORD-1", TrackingNo: "TRK-12345"},
	}

	for _, event := range events {
		if err := d.Dispatch(event); err != nil {
			fmt.Println("error:", err)
		}
	}
}
```

The `Register` generic function wraps a `func(T) error` into a `func(any) error`, preserving type safety at the registration site while allowing dynamic dispatch at runtime. Using `reflect.TypeOf` as map keys gives O(1) handler lookup. The `(*T)(nil)).Elem()` trick handles interface types where the zero value is nil. This pattern is the foundation of event-sourced systems and CQRS command handlers in Go.'''
    ),

    (
        "go_deep5_23",
        r'''Write a comprehensive type switch example in Go that handles interfaces, concrete types, and nested type assertions. Show how to build a JSON-like value formatter.''',
        r'''<think>
Type switches are Go's primary mechanism for polymorphic behavior at runtime.
A JSON value formatter needs to handle: string, int, float, bool, nil,
slices (as JSON arrays), maps (as JSON objects), and structs.
I should use a recursive approach - arrays and objects contain nested values.
The type switch should demonstrate:
1. Basic type matching (string, int, bool)
2. Multiple types in one case
3. Interface matching (fmt.Stringer)
4. Default case with reflection fallback
5. Nested type assertions within cases
I will build a Format function that produces indented JSON-like output.
For structs, I will use reflection to iterate fields.
Edge case: cycles in data - will not handle for simplicity.
This pattern is heavily used in template engines, serializers, query builders.
</think>

```go
package jsonlike

import (
	"fmt"
	"reflect"
	"strings"
)

// Format converts an arbitrary Go value to a JSON-like string representation.
func Format(v any) string {
	return formatValue(v, 0)
}

func formatValue(v any, depth int) string {
	indent := strings.Repeat("  ", depth)
	childIndent := strings.Repeat("  ", depth+1)

	if v == nil {
		return "null"
	}

	// Type switch handles concrete types and interfaces
	switch val := v.(type) {
	case string:
		return fmt.Sprintf("%q", val)

	case bool:
		if val {
			return "true"
		}
		return "false"

	case int, int8, int16, int32, int64:
		return fmt.Sprintf("%d", val)

	case uint, uint8, uint16, uint32, uint64:
		return fmt.Sprintf("%d", val)

	case float32, float64:
		return fmt.Sprintf("%g", val)

	case fmt.Stringer:
		// Types implementing Stringer get quoted string representation
		return fmt.Sprintf("%q", val.String())

	case error:
		return fmt.Sprintf("%q", val.Error())

	case []any:
		if len(val) == 0 {
			return "[]"
		}
		parts := make([]string, len(val))
		for i, item := range val {
			parts[i] = childIndent + formatValue(item, depth+1)
		}
		return "[\n" + strings.Join(parts, ",\n") + "\n" + indent + "]"

	case map[string]any:
		if len(val) == 0 {
			return "{}"
		}
		parts := make([]string, 0, len(val))
		for k, item := range val {
			parts = append(parts,
				fmt.Sprintf("%s%q: %s", childIndent, k, formatValue(item, depth+1)))
		}
		return "{\n" + strings.Join(parts, ",\n") + "\n" + indent + "}"

	default:
		// Fall back to reflection for structs and typed slices
		return formatReflect(val, depth)
	}
}

func formatReflect(v any, depth int) string {
	rv := reflect.ValueOf(v)
	indent := strings.Repeat("  ", depth)
	childIndent := strings.Repeat("  ", depth+1)

	switch rv.Kind() {
	case reflect.Struct:
		t := rv.Type()
		parts := make([]string, 0, t.NumField())
		for i := 0; i < t.NumField(); i++ {
			field := t.Field(i)
			if !field.IsExported() {
				continue
			}
			name := field.Name
			if tag, ok := field.Tag.Lookup("json"); ok {
				name = strings.SplitN(tag, ",", 2)[0]
				if name == "-" {
					continue
				}
			}
			val := formatValue(rv.Field(i).Interface(), depth+1)
			parts = append(parts, fmt.Sprintf("%s%q: %s", childIndent, name, val))
		}
		return "{\n" + strings.Join(parts, ",\n") + "\n" + indent + "}"

	case reflect.Slice, reflect.Array:
		if rv.Len() == 0 {
			return "[]"
		}
		parts := make([]string, rv.Len())
		for i := 0; i < rv.Len(); i++ {
			parts[i] = childIndent + formatValue(rv.Index(i).Interface(), depth+1)
		}
		return "[\n" + strings.Join(parts, ",\n") + "\n" + indent + "]"

	case reflect.Map:
		if rv.Len() == 0 {
			return "{}"
		}
		parts := make([]string, 0, rv.Len())
		iter := rv.MapRange()
		for iter.Next() {
			key := fmt.Sprintf("%v", iter.Key().Interface())
			val := formatValue(iter.Value().Interface(), depth+1)
			parts = append(parts, fmt.Sprintf("%s%q: %s", childIndent, key, val))
		}
		return "{\n" + strings.Join(parts, ",\n") + "\n" + indent + "}"

	case reflect.Ptr:
		if rv.IsNil() {
			return "null"
		}
		return formatValue(rv.Elem().Interface(), depth)

	default:
		return fmt.Sprintf("%v", v)
	}
}

// --- Example ---

type Address struct {
	Street string `json:"street"`
	City   string `json:"city"`
}

type Person struct {
	Name    string  `json:"name"`
	Age     int     `json:"age"`
	Address Address `json:"address"`
}

func Example() {
	data := map[string]any{
		"user": Person{
			Name: "Alice",
			Age:  30,
			Address: Address{Street: "123 Main St", City: "Portland"},
		},
		"tags":   []any{"admin", "active"},
		"score":  95.5,
		"active": true,
	}

	output := Format(data)
	fmt.Println(output)
}
```

The type switch cascade demonstrates Go's dispatch rules: concrete types are checked first, then interfaces (`fmt.Stringer`), then the default falls through to reflection. The multi-type case `int, int8, int16, ...` matches any of the listed types. Reflection handles structs, typed slices (like `[]Person`), and maps with non-string keys - cases the type switch cannot cover statically. This is essentially how `encoding/json.Marshal` works internally.'''
    ),

    (
        "go_deep5_24",
        r'''Build a generic struct validator in Go using reflection. Read "validate" struct tags and enforce rules like required, min, max, oneof. Return all validation errors.''',
        r'''<think>
A struct validator reads tags like validate:"required,min=3,max=100".
I need to:
1. Reflect over all exported fields
2. Parse the validate tag for each field
3. Apply each rule against the field value
4. Collect all errors (do not stop at first)
Rules to implement: required, min, max, oneof.
For strings: required means non-empty, min/max is length.
For numbers: min/max is value comparison.
For slices: min/max is length.
oneof checks that value is one of a set: oneof=active inactive.
I should return a structured ValidationErrors type.
Use reflect to get field values and kinds.
Edge case: pointers - dereference nil pointers for required check.
This is similar to go-playground/validator but simplified.
</think>

```go
package validate

import (
	"fmt"
	"reflect"
	"strconv"
	"strings"
)

// FieldError represents a validation failure for one field.
type FieldError struct {
	Field   string
	Rule    string
	Message string
}

func (e FieldError) Error() string {
	return fmt.Sprintf("%s: %s", e.Field, e.Message)
}

// ValidationErrors collects all field errors.
type ValidationErrors []FieldError

func (ve ValidationErrors) Error() string {
	msgs := make([]string, len(ve))
	for i, e := range ve {
		msgs[i] = e.Error()
	}
	return strings.Join(msgs, "; ")
}

// Validate checks a struct against its validate tags.
// Returns nil if valid, ValidationErrors otherwise.
func Validate(v any) error {
	rv := reflect.ValueOf(v)
	if rv.Kind() == reflect.Ptr {
		if rv.IsNil() {
			return ValidationErrors{{Field: "(root)", Rule: "required", Message: "nil pointer"}}
		}
		rv = rv.Elem()
	}
	if rv.Kind() != reflect.Struct {
		return fmt.Errorf("validate: expected struct, got %s", rv.Kind())
	}

	var errs ValidationErrors
	t := rv.Type()

	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}

		tag, ok := field.Tag.Lookup("validate")
		if !ok || tag == "-" {
			continue
		}

		fv := rv.Field(i)
		rules := strings.Split(tag, ",")

		for _, rule := range rules {
			rule = strings.TrimSpace(rule)
			if fe := applyRule(field.Name, fv, rule); fe != nil {
				errs = append(errs, *fe)
			}
		}
	}

	if len(errs) > 0 {
		return errs
	}
	return nil
}

func applyRule(name string, fv reflect.Value, rule string) *FieldError {
	parts := strings.SplitN(rule, "=", 2)
	ruleName := parts[0]
	ruleParam := ""
	if len(parts) == 2 {
		ruleParam = parts[1]
	}

	switch ruleName {
	case "required":
		if isEmpty(fv) {
			return &FieldError{name, "required", "is required"}
		}

	case "min":
		n, _ := strconv.ParseFloat(ruleParam, 64)
		length := getLength(fv)
		if length < n {
			return &FieldError{name, "min",
				fmt.Sprintf("must be at least %s (got %g)", ruleParam, length)}
		}

	case "max":
		n, _ := strconv.ParseFloat(ruleParam, 64)
		length := getLength(fv)
		if length > n {
			return &FieldError{name, "max",
				fmt.Sprintf("must be at most %s (got %g)", ruleParam, length)}
		}

	case "oneof":
		allowed := strings.Fields(ruleParam)
		val := fmt.Sprintf("%v", fv.Interface())
		found := false
		for _, a := range allowed {
			if a == val {
				found = true
				break
			}
		}
		if !found {
			return &FieldError{name, "oneof",
				fmt.Sprintf("must be one of [%s]", strings.Join(allowed, ", "))}
		}
	}
	return nil
}

func isEmpty(v reflect.Value) bool {
	switch v.Kind() {
	case reflect.String:
		return v.Len() == 0
	case reflect.Slice, reflect.Map, reflect.Array:
		return v.Len() == 0
	case reflect.Ptr, reflect.Interface:
		return v.IsNil()
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return v.Int() == 0
	case reflect.Float32, reflect.Float64:
		return v.Float() == 0
	case reflect.Bool:
		return !v.Bool()
	default:
		return false
	}
}

func getLength(v reflect.Value) float64 {
	switch v.Kind() {
	case reflect.String, reflect.Slice, reflect.Map, reflect.Array:
		return float64(v.Len())
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return float64(v.Int())
	case reflect.Float32, reflect.Float64:
		return v.Float()
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return float64(v.Uint())
	default:
		return 0
	}
}

// --- Example ---

type CreateUserRequest struct {
	Name  string `validate:"required,min=2,max=50"`
	Email string `validate:"required"`
	Age   int    `validate:"min=13,max=150"`
	Role  string `validate:"required,oneof=admin user guest"`
	Bio   string `validate:"max=500"`
}

func Example() {
	req := CreateUserRequest{
		Name:  "A",          // too short (min=2)
		Email: "",           // empty (required)
		Age:   10,           // too young (min=13)
		Role:  "superadmin", // not in allowed list
	}

	err := Validate(req)
	if errs, ok := err.(ValidationErrors); ok {
		for _, e := range errs {
			fmt.Printf("  %s [%s]: %s\n", e.Field, e.Rule, e.Message)
		}
	}
}
```

The validator collects all errors rather than failing fast - this gives the caller a complete picture of what is wrong. The `getLength` function interprets min/max contextually: for strings and slices it checks length, for numbers it checks the value itself. This matches how `go-playground/validator` works. The `oneof` rule uses `strings.Fields` to split by whitespace, supporting multi-value lists naturally.'''
    ),

    (
        "go_deep5_25",
        r'''Write a Go function that uses reflection to deep-compare two structs, identifying which fields differ. Return a list of differences with field path, old value, and new value. Handle nested structs and slices.''',
        r'''<think>
Deep comparison with diff output is useful for audit logs, testing, and change detection.
I will use reflection to walk both structs recursively.
For each field, compare values. If different, record the diff.
For nested structs, recurse with a dot-separated path: "Address.City".
For slices, compare element by element; note added/removed/changed elements.
For maps, compare by key.
Pointer fields: dereference both, handle nil cases.
I need to handle the case where types do not match - that is an error.
Use reflect.DeepEqual for leaf comparisons, but record diffs for reporting.
The Change struct should contain: Path, OldValue, NewValue as any.
Edge cases: nil pointers vs non-nil, different slice lengths.
I will limit recursion depth to prevent infinite loops with cycles.
</think>

```go
package diff

import (
	"fmt"
	"reflect"
)

// Change represents a single field difference between two structs.
type Change struct {
	Path     string // dot-separated field path, e.g., "Address.City"
	OldValue any
	NewValue any
}

func (c Change) String() string {
	return fmt.Sprintf("%s: %v -> %v", c.Path, c.OldValue, c.NewValue)
}

// Compare returns all differences between two values.
// Both must be the same type (struct, pointer to struct, etc.).
func Compare(old, new any) ([]Change, error) {
	oldV := reflect.ValueOf(old)
	newV := reflect.ValueOf(new)

	if oldV.Type() != newV.Type() {
		return nil, fmt.Errorf("type mismatch: %T vs %T", old, new)
	}

	var changes []Change
	compareValues(&changes, "", oldV, newV, 0)
	return changes, nil
}

const maxDepth = 20

func compareValues(changes *[]Change, path string, oldV, newV reflect.Value, depth int) {
	if depth > maxDepth {
		return
	}

	// Handle pointers
	if oldV.Kind() == reflect.Ptr {
		switch {
		case oldV.IsNil() && newV.IsNil():
			return
		case oldV.IsNil() || newV.IsNil():
			*changes = append(*changes, Change{
				Path:     pathOrRoot(path),
				OldValue: safeInterface(oldV),
				NewValue: safeInterface(newV),
			})
			return
		default:
			compareValues(changes, path, oldV.Elem(), newV.Elem(), depth+1)
			return
		}
	}

	switch oldV.Kind() {
	case reflect.Struct:
		t := oldV.Type()
		for i := 0; i < t.NumField(); i++ {
			field := t.Field(i)
			if !field.IsExported() {
				continue
			}
			fieldPath := joinPath(path, field.Name)
			compareValues(changes, fieldPath, oldV.Field(i), newV.Field(i), depth+1)
		}

	case reflect.Slice, reflect.Array:
		oldLen := oldV.Len()
		newLen := newV.Len()
		minLen := oldLen
		if newLen < minLen {
			minLen = newLen
		}

		// Compare common elements
		for i := 0; i < minLen; i++ {
			elemPath := fmt.Sprintf("%s[%d]", path, i)
			compareValues(changes, elemPath, oldV.Index(i), newV.Index(i), depth+1)
		}

		// Elements removed
		for i := minLen; i < oldLen; i++ {
			*changes = append(*changes, Change{
				Path:     fmt.Sprintf("%s[%d]", path, i),
				OldValue: oldV.Index(i).Interface(),
				NewValue: nil,
			})
		}

		// Elements added
		for i := minLen; i < newLen; i++ {
			*changes = append(*changes, Change{
				Path:     fmt.Sprintf("%s[%d]", path, i),
				OldValue: nil,
				NewValue: newV.Index(i).Interface(),
			})
		}

	case reflect.Map:
		// Check all keys in old map
		for _, key := range oldV.MapKeys() {
			keyStr := fmt.Sprintf("%v", key.Interface())
			mapPath := fmt.Sprintf("%s[%s]", path, keyStr)

			newVal := newV.MapIndex(key)
			if !newVal.IsValid() {
				*changes = append(*changes, Change{
					Path:     mapPath,
					OldValue: oldV.MapIndex(key).Interface(),
					NewValue: nil,
				})
				continue
			}
			compareValues(changes, mapPath, oldV.MapIndex(key), newVal, depth+1)
		}

		// Check for new keys
		for _, key := range newV.MapKeys() {
			if !oldV.MapIndex(key).IsValid() {
				keyStr := fmt.Sprintf("%v", key.Interface())
				*changes = append(*changes, Change{
					Path:     fmt.Sprintf("%s[%s]", path, keyStr),
					OldValue: nil,
					NewValue: newV.MapIndex(key).Interface(),
				})
			}
		}

	default:
		// Leaf value comparison
		if !reflect.DeepEqual(oldV.Interface(), newV.Interface()) {
			*changes = append(*changes, Change{
				Path:     pathOrRoot(path),
				OldValue: oldV.Interface(),
				NewValue: newV.Interface(),
			})
		}
	}
}

func joinPath(base, field string) string {
	if base == "" {
		return field
	}
	return base + "." + field
}

func pathOrRoot(path string) string {
	if path == "" {
		return "(root)"
	}
	return path
}

func safeInterface(v reflect.Value) any {
	if v.IsNil() {
		return nil
	}
	return v.Interface()
}

// --- Example ---

type Address struct {
	Street string
	City   string
	Zip    string
}

type User struct {
	Name    string
	Age     int
	Address Address
	Tags    []string
}

func Example() {
	old := User{
		Name:    "Alice",
		Age:     30,
		Address: Address{Street: "123 Main", City: "Portland", Zip: "97201"},
		Tags:    []string{"admin", "active"},
	}
	updated := User{
		Name:    "Alice",
		Age:     31,
		Address: Address{Street: "456 Oak", City: "Portland", Zip: "97202"},
		Tags:    []string{"admin", "inactive", "reviewed"},
	}

	diffs, _ := Compare(old, updated)
	for _, d := range diffs {
		fmt.Println(d)
	}
	// Output:
	// Age: 30 -> 31
	// Address.Street: 123 Main -> 456 Oak
	// Address.Zip: 97201 -> 97202
	// Tags[1]: active -> inactive
	// Tags[2]: <nil> -> reviewed
}
```

The recursive approach handles arbitrarily nested structures. The `maxDepth` guard prevents infinite recursion from cyclic references. For slices, comparing by index is correct for ordered data; for unordered sets, you would need a set-diff algorithm. Using `reflect.DeepEqual` for leaf comparisons handles edge cases like NaN != NaN. This function is invaluable for audit logging - record exactly which fields changed on every update.'''
    ),
]
