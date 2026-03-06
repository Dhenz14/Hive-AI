r"""Thinking-trace pairs: Functional Python code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from typing import Generator, Iterator, List, Any
import os

def read_large_file(filepath: str) -> Generator[str, None, None]:
    with open(filepath, 'r') as f:
        for line in f:
            yield line.strip()

def process_log_lines(filepath: str) -> List[dict]:
    lines = list(read_large_file(filepath))
    results = []
    for line in lines:
        parts = line.split('|')
        if len(parts) >= 4:
            entry = {
                'timestamp': parts[0],
                'level': parts[1],
                'source': parts[2],
                'message': '|'.join(parts[3:]),
            }
            results.append(entry)
    return results

def filter_errors(entries: List[dict]) -> List[dict]:
    return [e for e in entries if e['level'].strip().upper() == 'ERROR']

def aggregate_by_source(entries: List[dict]) -> dict:
    result = {}
    for entry in entries:
        source = entry['source'].strip()
        if source not in result:
            result[source] = {'count': 0, 'messages': []}
        result[source]['count'] += 1
        result[source]['messages'].append(entry['message'])
    return result

def get_top_sources(aggregated: dict, n: int = 5) -> List[tuple]:
    sorted_sources = sorted(
        aggregated.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )
    return sorted_sources[:n]

def analyze_logs(directory: str) -> dict:
    all_entries = []
    for filename in os.listdir(directory):
        if filename.endswith('.log'):
            filepath = os.path.join(directory, filename)
            entries = process_log_lines(filepath)
            all_entries.extend(entries)

    errors = filter_errors(all_entries)
    aggregated = aggregate_by_source(errors)
    top = get_top_sources(aggregated)

    return {
        'total_entries': len(all_entries),
        'total_errors': len(errors),
        'top_error_sources': top,
        'aggregated': aggregated,
    }

def search_logs(directory: str, pattern: str) -> List[dict]:
    results = []
    for filename in os.listdir(directory):
        if filename.endswith('.log'):
            filepath = os.path.join(directory, filename)
            entries = process_log_lines(filepath)
            for entry in entries:
                if pattern.lower() in entry['message'].lower():
                    entry['file'] = filename
                    results.append(entry)
    return results
```''', r'''<think>
Let me trace through this code from top to bottom. The first thing I see is read_large_file -- a generator that yields lines lazily from a file. Good, that's memory-efficient for large files. But then process_log_lines calls `lines = list(read_large_file(filepath))`. Wait... that converts the entire generator to a list, loading the whole file into memory. For a 10GB log file, that's 10GB of RAM consumed in a single line. The generator is completely pointless here.

So the first fix is obvious -- keep things lazy. But let me see if the rest of the pipeline would even support streaming...

analyze_logs builds up `all_entries` as a list, extending it for each file. So even if process_log_lines were lazy, all entries from all files end up in memory anyway. The pipeline is fundamentally batch-oriented: read all, parse all, filter all, aggregate. A streaming approach would process entries one at a time through the whole pipeline without accumulating intermediates.

aggregate_by_source is interesting -- it stores ALL error messages in a messages list per source. If one source has a million errors, that's a million strings in memory. In practice, you'd want a count and maybe the last 10 messages, not every single one.

search_logs has a mutation issue I almost missed: `entry['file'] = filename` modifies the dict returned by process_log_lines. If anyone else holds a reference to the same dict, they now see the unexpected 'file' key. Should create a new dict: `{**entry, 'file': filename}`.

The error handling is basically nonexistent. No handling for file I/O errors (what if a file is deleted between listing and opening?), no handling for malformed log lines (what if line.split('|') returns 2 parts instead of 4?). Lines that don't match the expected format are silently skipped with no warning.

For search_logs specifically -- it reads and parses ALL entries from ALL files, then filters. For a directory with hundreds of log files, you'd want to skip files quickly (maybe by date in filename) rather than parsing everything.

Actually, let me reconsider the architecture. The core problem is that this is written as imperative "get all, then process all" instead of composable generator pipelines. With generators, you'd chain: read lines -> parse entries -> filter -> aggregate, processing one entry at a time with constant memory usage regardless of input size.

</think>

## Code Review: Python Log Analysis Pipeline

### HIGH - Generator Defeated by list()

**G1: Entire file loaded into memory (Severity: HIGH)**
```python
def process_log_lines(filepath: str) -> List[dict]:
    lines = list(read_large_file(filepath))  # defeats generator
```
`read_large_file` correctly yields lines lazily, but `list()` immediately materializes the entire file in memory. For a 10GB log file, this uses 10GB of RAM. Process lazily:
```python
def process_log_lines(filepath: str) -> Generator[dict, None, None]:
    for line in read_large_file(filepath):
        parts = line.split('|')
        if len(parts) >= 4:
            yield {
                'timestamp': parts[0],
                'level': parts[1],
                'source': parts[2],
                'message': '|'.join(parts[3:]),
            }
```

### HIGH - No Streaming Pipeline

**SP1: All entries accumulated in memory (Severity: HIGH)**
`analyze_logs` extends `all_entries` with every file's entries before any filtering. For a directory of log files totaling 50GB, all parsed entries exist simultaneously in memory.

Refactor into a streaming pipeline:
```python
def iter_all_entries(directory: str) -> Generator[dict, None, None]:
    for filename in os.listdir(directory):
        if filename.endswith('.log'):
            yield from process_log_lines(os.path.join(directory, filename))

def analyze_logs(directory: str) -> dict:
    total_entries = 0
    total_errors = 0
    aggregated = {}
    for entry in iter_all_entries(directory):
        total_entries += 1
        if entry['level'].strip().upper() == 'ERROR':
            total_errors += 1
            source = entry['source'].strip()
            if source not in aggregated:
                aggregated[source] = {'count': 0, 'messages': []}
            aggregated[source]['count'] += 1
```

### HIGH - Unbounded Message Accumulation

**MA1: All error messages stored per source (Severity: HIGH)**
```python
result[source]['messages'].append(entry['message'])
```
If one source produces 1 million errors, 1 million message strings are stored. This is rarely useful and wastes memory. Store only the count and the last N messages:
```python
MAX_MESSAGES = 10
result[source]['messages'] = result[source]['messages'][-MAX_MESSAGES:]
```
Or use `collections.deque(maxlen=10)`.

### MEDIUM - Mutation of Shared Data

**MUT1: search_logs mutates entry dicts (Severity: MEDIUM)**
```python
entry['file'] = filename
results.append(entry)
```
This modifies the dict object in-place. If any other code holds a reference to the same dict, it sees the unexpected `file` key. Create a new dict:
```python
results.append({**entry, 'file': filename})
```

### MEDIUM - Error Handling

**EH1: No I/O error handling (Severity: MEDIUM)**
If a log file is unreadable (permissions, corruption), the entire analysis fails. Wrap file reading:
```python
try:
    entries = process_log_lines(filepath)
except (OSError, UnicodeDecodeError) as e:
    logging.warning(f"Skipping {filepath}: {e}")
    continue
```

**EH2: Silently dropped malformed lines (Severity: LOW)**
Lines with fewer than 4 pipe-separated fields are silently skipped. Consider logging a warning for debugging:
```python
if len(parts) < 4:
    logging.debug(f"Malformed log line: {line[:100]}")
    continue
```

### LOW - Functional Composition

**FC1: Imperative pipeline style (Severity: LOW)**
The pipeline in analyze_logs could use itertools for clearer composition:
```python
from itertools import chain as ichain
import itertools

entries = ichain.from_iterable(
    process_log_lines(os.path.join(directory, f))
    for f in os.listdir(directory) if f.endswith('.log')
)
errors = (e for e in entries if e['level'].strip().upper() == 'ERROR')
```
This makes the data flow explicit and keeps everything lazy.'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from functools import reduce, partial, lru_cache, wraps
from typing import Callable, TypeVar, Any
from itertools import chain, groupby, starmap
import operator
import time

T = TypeVar('T')

def compose(*functions):
    return reduce(lambda f, g: lambda *args, **kwargs: f(g(*args, **kwargs)), functions)

def pipe(value, *functions):
    return reduce(lambda v, f: f(v), functions, value)

def memoize(func):
    cache = {}
    @wraps(func)
    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return wrapper

def retry(max_attempts=3, delay=1.0, exceptions=(Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

def curry(func):
    @wraps(func)
    def curried(*args, **kwargs):
        if len(args) + len(kwargs) >= func.__code__.co_argcount:
            return func(*args, **kwargs)
        return lambda *more_args, **more_kwargs: curried(
            *(args + more_args), **{**kwargs, **more_kwargs}
        )
    return curried

@curry
def map_over(func, iterable):
    return [func(x) for x in iterable]

@curry
def filter_by(predicate, iterable):
    return [x for x in iterable if predicate(x)]

@curry
def sort_by(key_func, iterable):
    return sorted(iterable, key=key_func)

def flatten(nested):
    for item in nested:
        if isinstance(item, (list, tuple)):
            yield from flatten(item)
        else:
            yield item

def chunk(iterable, size):
    iterator = iter(iterable)
    while True:
        batch = []
        try:
            for _ in range(size):
                batch.append(next(iterator))
        except StopIteration:
            if batch:
                yield batch
            return
        yield batch

def pluck(key, dicts):
    return [d[key] for d in dicts]

def group_by_key(key, items):
    sorted_items = sorted(items, key=lambda x: x[key])
    return {k: list(v) for k, v in groupby(sorted_items, key=lambda x: x[key])}

users = [
    {'name': 'Alice', 'age': 30, 'dept': 'eng'},
    {'name': 'Bob', 'age': 25, 'dept': 'eng'},
    {'name': 'Charlie', 'age': 35, 'dept': 'sales'},
]

result = pipe(
    users,
    filter_by(lambda u: u['age'] > 25),
    sort_by(lambda u: u['age']),
    map_over(lambda u: u['name']),
)
```''', r'''<think>
Let me review this functional programming utilities code.

1. compose function:
- The reduce-based compose is clever but hard to read and debug. Stack traces will show nested lambdas. Also, it composes right-to-left (mathematical convention) which may surprise Python programmers.
- No type safety or function signature checking.

2. memoize issues:
- Unbounded cache -- no size limit. A function called with many different arguments will consume unlimited memory.
- kwargs are sorted and converted to tuple, but this fails if any kwarg value is unhashable (e.g., a list). The `args` tuple also fails if any argument is unhashable.
- Mutable return values are cached by reference. If the caller modifies the returned value, the cache is corrupted:
```python
@memoize
def get_list(): return [1, 2, 3]
a = get_list()
a.append(4)  # cache now contains [1, 2, 3, 4]
```
- lru_cache from functools is better maintained and has maxsize parameter.

3. retry issues:
- Fixed delay between retries (no exponential backoff). Hammers the failing service at constant rate.
- Catches broad Exception by default. Will retry on programming errors (TypeError, ValueError) which will never succeed.
- time.sleep in the decorator blocks the thread. In async code, this is a problem.
- The last attempt's exception is raised, but the previous attempts' exceptions are lost (no exception chaining).

4. curry function:
- Uses func.__code__.co_argcount to determine arity. This breaks for functions with *args, **kwargs, defaults, or methods (self counts as an argument).
- Calling a curried function with too many arguments may silently call the function before all intended arguments are provided.

5. map_over, filter_by, sort_by:
- These return lists, not lazy iterators. This defeats the purpose of functional composition for large datasets. The pipe(users, filter_by(...), sort_by(...), map_over(...)) creates 3 intermediate lists.
- Using @curry on these means the type hints are lost.

6. flatten:
- Recursive approach with yield from. For deeply nested structures, this can hit Python's recursion limit.
- Only handles list and tuple, not other iterables (set, generator).
- Strings are iterable but should NOT be flattened character by character. Need to exclude strings.

7. group_by_key:
- Sorts the entire list before grouping. groupby() from itertools requires sorted input, so this is correct, but the sort is O(n log n) when a single-pass dict approach is O(n).

8. pluck:
- Raises KeyError if any dict is missing the key. No default value option.

Let me write the review.
</think>

## Code Review: Python Functional Utilities

### HIGH - Unbounded Memoization Cache

**MC1: memoize has no size limit (Severity: HIGH)**
```python
def memoize(func):
    cache = {}
```
The cache dict grows without bound. A memoized function called with millions of unique arguments consumes unlimited memory. Use `functools.lru_cache(maxsize=128)` which has built-in eviction.

**MC2: Mutable return values corrupt cache (Severity: HIGH)**
```python
@memoize
def get_defaults():
    return {'timeout': 30, 'retries': 3}

config = get_defaults()
config['timeout'] = 999  # corrupts cached value
```
The cached reference is returned directly. Callers mutating the return value corrupt the cache. Either return deep copies or document that returned values must not be modified.

**MC3: Unhashable arguments cause TypeError (Severity: MEDIUM)**
`(args, tuple(sorted(kwargs.items())))` as cache key fails when args contain unhashable types (lists, dicts). No graceful fallback.

### HIGH - Curry Breaks on Complex Signatures

**CR1: curry uses co_argcount incorrectly (Severity: HIGH)**
```python
if len(args) + len(kwargs) >= func.__code__.co_argcount:
```
`co_argcount` includes parameters with defaults, excludes `*args` and `**kwargs`. This means:
- Functions with `*args` never accumulate arguments (co_argcount excludes them)
- Functions with defaults may be called too early
- Methods count `self` in co_argcount, breaking currying on bound methods

Use `inspect.signature` for robust arity detection, or avoid general-purpose curry in Python (it fights the language's design).

### MEDIUM - Eagerness Defeats Composition

**EG1: Intermediate lists in pipeline (Severity: MEDIUM)**
```python
@curry
def map_over(func, iterable):
    return [func(x) for x in iterable]
```
All three curried helpers (map_over, filter_by, sort_by) return lists. The pipeline `filter_by -> sort_by -> map_over` creates 3 intermediate lists. For large datasets, this wastes memory. Return generators for filter and map:
```python
@curry
def map_over(func, iterable):
    return (func(x) for x in iterable)
```
Note: sort_by inherently requires materialization (cannot sort lazily).

### MEDIUM - Retry Design

**RT1: No exponential backoff (Severity: MEDIUM)**
Fixed `delay=1.0` between retries hammers the failing service at a constant rate. Use exponential backoff:
```python
time.sleep(delay * (2 ** attempt))
```

**RT2: Catches Exception by default (Severity: MEDIUM)**
Retrying on TypeError or ValueError (programming errors) will never succeed and wastes time. Default to a narrower set of exceptions or require explicit specification.

**RT3: Lost exception context (Severity: LOW)**
Only the last exception is raised. Previous attempts' exceptions are lost. Use exception chaining:
```python
raise last_exception from first_exception
```

### MEDIUM - Flatten Recursion Limit

**FL1: Recursive flatten hits recursion limit (Severity: MEDIUM)**
```python
def flatten(nested):
    for item in nested:
        if isinstance(item, (list, tuple)):
            yield from flatten(item)
```
Deeply nested structures (depth > 1000) cause RecursionError. Use an iterative approach with a stack.

**FL2: Strings are iterable but should not be flattened (Severity: MEDIUM)**
If a list contains strings, they are not flattened (strings are not list/tuple). But if the isinstance check were broadened to include all iterables, strings would be flattened character by character. The current check is safe but fragile -- adding `set` or `Iterable` to the check would break on strings. Add an explicit string exclusion.

### LOW - group_by_key Performance

**GK1: O(n log n) sort when O(n) is possible (Severity: LOW)**
`groupby` requires sorted input, forcing an O(n log n) sort. A defaultdict approach is O(n):
```python
from collections import defaultdict

def group_by_key(key, items):
    groups = defaultdict(list)
    for item in items:
        groups[item[key]].append(item)
    return dict(groups)
```

### LOW - Compose Readability

**CO1: Nested lambdas produce unreadable stack traces (Severity: LOW)**
The reduce-based compose creates deeply nested lambda closures. Debugging errors in composed functions shows `<lambda>` at every level. Consider a class-based approach with `__call__` for better traceability.'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import csv
import json
from io import StringIO

def parse_csv_data(raw_data: str) -> List[Dict[str, str]]:
    reader = csv.DictReader(StringIO(raw_data))
    return list(reader)

def transform_records(records: List[dict], mappings: dict) -> List[dict]:
    results = []
    for record in records:
        transformed = {}
        for target_key, source_key in mappings.items():
            if callable(source_key):
                transformed[target_key] = source_key(record)
            elif '.' in source_key:
                parts = source_key.split('.')
                value = record
                for part in parts:
                    value = value.get(part, {})
                transformed[target_key] = value
            else:
                transformed[target_key] = record.get(source_key, '')
        results.append(transformed)
    return results

def validate_records(records: List[dict], rules: dict) -> Tuple[List[dict], List[dict]]:
    valid = []
    invalid = []
    for record in records:
        errors = []
        for field, validators in rules.items():
            value = record.get(field)
            for validator in validators:
                error = validator(value, field)
                if error:
                    errors.append(error)
        if errors:
            record['_errors'] = errors
            invalid.append(record)
        else:
            valid.append(record)
    return valid, invalid

def required(value, field):
    if value is None or value == '':
        return f'{field} is required'

def min_length(n):
    def validator(value, field):
        if value and len(value) < n:
            return f'{field} must be at least {n} characters'
    return validator

def numeric(value, field):
    try:
        float(value)
    except (TypeError, ValueError):
        return f'{field} must be numeric'

def deduplicate(records: List[dict], key_fields: List[str]) -> List[dict]:
    seen = set()
    unique = []
    for record in records:
        key = tuple(record.get(f) for f in key_fields)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique

def batch_process(records: List[dict], batch_size: int,
                  processor: callable) -> List:
    results = []
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        result = processor(batch)
        results.extend(result)
    return results

def build_pipeline(*steps):
    def run(data):
        for step in steps:
            data = step(data)
        return data
    return run

pipeline = build_pipeline(
    lambda records: transform_records(records, {
        'full_name': lambda r: f"{r.get('first', '')} {r.get('last', '')}",
        'email': 'email_address',
        'age': 'user_age',
    }),
    lambda records: [r for r in records if r.get('email')],
    lambda records: deduplicate(records, ['email']),
)
```''', r'''<think>
Let me review this data processing pipeline code.

1. transform_records nested key access:
- The dot-notation access `value = value.get(part, {})` falls through to an empty dict for missing intermediate keys. But the last access also returns {} for missing final keys, instead of None or a meaningful default. This means a missing nested key returns {} rather than ''.
- If the source data has actual dict values (not just strings), the `.get(part, {})` approach only works for dicts. If any intermediate value is a string or list, `.get()` raises AttributeError.

2. validate_records mutation:
- `record['_errors'] = errors` mutates the original record dict. The caller's data is modified with _errors fields. This is a side effect that can cause unexpected behavior if records are reused.

3. Validator design:
- required() returns None on success (implicit) and a string on failure. This works but is fragile -- a validator that returns an empty string (falsy) would be treated as success.
- min_length returns None (implicit) when value is falsy. So a missing field passes min_length validation. The validators are not composable -- required and min_length must be used together.
- numeric() catches TypeError/ValueError but if value is None, float(None) raises TypeError. This means numeric() on an optional field returns "must be numeric" when the field is absent. Should check for None first.

4. deduplicate key handling:
- `tuple(record.get(f) for f in key_fields)` -- if any key field value is unhashable (a list or dict), this fails with TypeError. Also, None values in key fields mean records with missing keys are grouped together.

5. batch_process:
- Takes List[dict] and processor returns a list. But there is no error handling for individual batch failures. If one batch fails, the entire process fails.
- Uses len(records) so it does not work with generators/iterators.

6. build_pipeline:
- Simple and clean, but no error handling between steps. If one step returns None, the next step crashes.
- No logging or progress tracking.
- Steps must return the same type they receive (List[dict] -> List[dict]). No type checking.

7. Pipeline usage:
- The pipeline uses lambdas for steps, making it hard to debug. Stack traces show <lambda> with no context.
- The filter step `lambda records: [r for r in records if r.get('email')]` silently drops records without email. No logging of dropped records.

8. parse_csv_data:
- Returns list(reader) which loads entire CSV into memory. For large CSVs, should use a generator.
- No error handling for malformed CSV.

Let me write the review.
</think>

## Code Review: Python Data Processing Pipeline

### HIGH - Mutation of Input Records

**MUT1: validate_records modifies caller's data (Severity: HIGH)**
```python
record['_errors'] = errors
invalid.append(record)
```
The `_errors` field is added to the original record dict, not a copy. The caller's data is permanently modified with validation error metadata. Create a copy:
```python
error_record = {**record, '_errors': errors}
invalid.append(error_record)
```

### HIGH - Validator Inconsistencies

**V1: numeric() rejects None/missing fields (Severity: HIGH)**
```python
def numeric(value, field):
    try:
        float(value)
    except (TypeError, ValueError):
        return f'{field} must be numeric'
```
`float(None)` raises TypeError, so an optional field that is absent fails the numeric check. Validators should handle None gracefully:
```python
def numeric(value, field):
    if value is None or value == '':
        return  # let required() handle presence
    try:
        float(value)
    except (TypeError, ValueError):
        return f'{field} must be numeric'
```

**V2: Empty string return treated as success (Severity: MEDIUM)**
Validators signal failure by returning a truthy string. If a validator accidentally returns `''` (empty string, falsy), it is treated as success. Use explicit `None` vs string comparison instead of truthiness, or return a Result type.

### MEDIUM - Nested Key Access Fragility

**NK1: Missing nested key returns empty dict (Severity: MEDIUM)**
```python
for part in parts:
    value = value.get(part, {})
transformed[target_key] = value
```
If any intermediate key is missing, the default `{}` propagates. The final value stored is `{}` instead of a meaningful default like `None` or `''`. Also, if any intermediate value is not a dict (e.g., it is a string or int), `.get()` raises AttributeError:
```python
# If record = {'address': '123 Main St'}
# and source_key = 'address.city'
# 'address' returns a string, then '123 Main St'.get('city') crashes
```

Fix with proper error handling:
```python
value = record
for part in parts:
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
transformed[target_key] = value if value is not None else ''
```

### MEDIUM - deduplicate with Unhashable Values

**DK1: Unhashable key field values crash deduplication (Severity: MEDIUM)**
```python
key = tuple(record.get(f) for f in key_fields)
seen.add(key)  # TypeError if key contains unhashable values
```
If any key field contains a list or dict, the tuple is unhashable. Either convert values to strings for the key, or handle the TypeError.

### MEDIUM - Pipeline Debugging

**PD1: Lambda steps are opaque in stack traces (Severity: MEDIUM)**
```python
pipeline = build_pipeline(
    lambda records: transform_records(records, {...}),
    lambda records: [r for r in records if r.get('email')],
)
```
When a step fails, the traceback shows `<lambda>` with no indication which pipeline step caused the error. Use named functions:
```python
def transform_step(records):
    return transform_records(records, {...})

def filter_email_step(records):
    return [r for r in records if r.get('email')]

pipeline = build_pipeline(transform_step, filter_email_step)
```

### LOW - Memory Efficiency

**ME1: parse_csv_data loads entire CSV into memory (Severity: LOW)**
`list(reader)` materializes the entire CSV. For large files, return the reader as a generator. This requires callers to consume it within the StringIO context.

**ME2: batch_process requires a list (Severity: LOW)**
`len(records)` and `records[i:i+batch_size]` require the input to be a sequence, not a generator. Use itertools.islice for generator-compatible batching:
```python
from itertools import islice

def batch_process(records, batch_size, processor):
    iterator = iter(records)
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            break
        results.extend(processor(batch))
```'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from typing import Any, Callable, Iterator, TypeVar, Generic
from functools import reduce
import itertools

T = TypeVar('T')
U = TypeVar('U')

class LazySeq(Generic[T]):
    def __init__(self, iterable):
        self._iterable = iterable
        self._operations = []

    def map(self, func: Callable[[T], U]) -> 'LazySeq[U]':
        self._operations.append(('map', func))
        return self

    def filter(self, predicate: Callable[[T], bool]) -> 'LazySeq[T]':
        self._operations.append(('filter', predicate))
        return self

    def flat_map(self, func: Callable[[T], list]) -> 'LazySeq':
        self._operations.append(('flat_map', func))
        return self

    def take(self, n: int) -> 'LazySeq[T]':
        self._operations.append(('take', n))
        return self

    def skip(self, n: int) -> 'LazySeq[T]':
        self._operations.append(('skip', n))
        return self

    def _evaluate(self) -> Iterator:
        result = iter(self._iterable)
        for op, arg in self._operations:
            if op == 'map':
                result = map(arg, result)
            elif op == 'filter':
                result = filter(arg, result)
            elif op == 'flat_map':
                result = itertools.chain.from_iterable(map(arg, result))
            elif op == 'take':
                result = itertools.islice(result, arg)
            elif op == 'skip':
                result = itertools.islice(result, arg, None)
        return result

    def to_list(self) -> list:
        return list(self._evaluate())

    def first(self) -> T:
        return next(self._evaluate())

    def reduce(self, func: Callable, initial=None):
        if initial is not None:
            return reduce(func, self._evaluate(), initial)
        return reduce(func, self._evaluate())

    def for_each(self, func: Callable[[T], None]):
        for item in self._evaluate():
            func(item)

    def count(self) -> int:
        return sum(1 for _ in self._evaluate())

    def group_by(self, key_func: Callable) -> dict:
        groups = {}
        for item in self._evaluate():
            key = key_func(item)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)
        return groups

    def __iter__(self):
        return self._evaluate()

    def __repr__(self):
        return f"LazySeq({self._operations})"


# Usage
data = range(1000000)
result = (
    LazySeq(data)
    .filter(lambda x: x % 2 == 0)
    .map(lambda x: x ** 2)
    .take(10)
    .to_list()
)

words = ["hello world", "foo bar", "baz"]
flat = (
    LazySeq(words)
    .flat_map(lambda s: s.split())
    .filter(lambda w: len(w) > 3)
    .map(str.upper)
    .to_list()
)
```''', r'''<think>
Let me review this lazy sequence implementation.

1. Critical bug -- mutation/reuse:
- The _operations list is mutated by each chained method (map, filter, etc.). The methods return `self`, not a new LazySeq. This means:
  - The sequence can only be evaluated once correctly. After adding operations and calling to_list(), the operations list has been consumed.
  - Actually, _evaluate creates a new iterator chain each time, so multiple evaluations should work... but the operations list is mutated, so this pattern fails:

```python
base = LazySeq(range(10)).filter(lambda x: x > 5)
a = base.map(lambda x: x * 2)  # modifies base._operations
b = base.map(lambda x: x * 3)  # ALSO modifies base._operations, now has both maps
# a and b are the same object (both are `base`)
```

This is because `return self` means a, b, and base are all the same object. The operations list now has [filter, map(x2), map(x3)]. Both a.to_list() and b.to_list() would apply all three operations.

2. Not truly lazy for terminal operations:
- count() evaluates the entire sequence. If there are 1 million items, all are processed.
- group_by materializes everything into a dict. These are terminal operations, which is fine, but they defeat laziness for large datasets.

3. Type safety:
- map returns LazySeq[U] but actually returns self which is LazySeq[T]. The generic type annotations are incorrect because the same object is used throughout.
- _iterable could be a generator, which is consumed on first _evaluate(). Subsequent calls to to_list() or count() return empty results.

4. No error handling:
- first() raises StopIteration if the sequence is empty. This is confusing for callers. Should raise a custom exception or return None.
- Operations with None functions would cause errors deep in the chain.

5. Thread safety:
- _operations is a shared mutable list. Not thread-safe if methods are called from multiple threads.

6. Missing operations:
- No distinct/unique
- No zip
- No sorted (which would require materialization)
- No peek for debugging

Let me write the review.
</think>

## Code Review: Lazy Sequence Implementation

### CRITICAL - Mutation Makes Branching Impossible

**MUT1: Methods mutate self instead of creating copies (Severity: CRITICAL)**
```python
def map(self, func):
    self._operations.append(('map', func))
    return self  # returns the SAME object
```
Every method modifies the internal `_operations` list and returns `self`. This means branching fails completely:
```python
base = LazySeq(range(10)).filter(lambda x: x > 5)
doubled = base.map(lambda x: x * 2)
tripled = base.map(lambda x: x * 3)
# doubled IS tripled IS base -- all the same object
# _operations = [filter, map(*2), map(*3)]
# doubled.to_list() applies BOTH maps
```

Fix: Return a new LazySeq for each operation:
```python
def map(self, func):
    new_seq = LazySeq(self._iterable)
    new_seq._operations = self._operations + [('map', func)]
    return new_seq
```

### HIGH - Generator Source Consumed on First Evaluation

**GC1: Generator-based iterables only work once (Severity: HIGH)**
```python
gen = (x for x in range(10))
seq = LazySeq(gen)
seq.to_list()  # returns [0, 1, 2, ..., 9]
seq.to_list()  # returns [] -- generator exhausted
seq.count()    # returns 0
```
The generator is consumed on the first `_evaluate()` call. All subsequent calls return empty results. Either:
- Document that the source must be a reusable iterable (list, range, etc.)
- Cache the source on first use: `self._iterable = list(self._iterable)` (but this defeats laziness)
- Detect generators and warn

### HIGH - first() Raises StopIteration

**SI1: StopIteration leaks through first() (Severity: HIGH)**
```python
def first(self) -> T:
    return next(self._evaluate())
```
On an empty sequence, `next()` raises `StopIteration`. In Python 3.7+, StopIteration inside a generator causes RuntimeError. Even outside generators, callers may not expect StopIteration from a method call. Return a sentinel or raise ValueError:
```python
def first(self, default=_MISSING) -> T:
    try:
        return next(self._evaluate())
    except StopIteration:
        if default is _MISSING:
            raise ValueError("Sequence is empty")
        return default
```

### MEDIUM - Type Safety Illusion

**TS1: Generic annotations are incorrect (Severity: MEDIUM)**
```python
def map(self, func: Callable[[T], U]) -> 'LazySeq[U]':
    self._operations.append(('map', func))
    return self  # type is LazySeq[T], not LazySeq[U]
```
The method claims to return `LazySeq[U]` but returns `self` which is `LazySeq[T]`. The generic type parameter changes with each operation, but the actual object never changes type. Type checkers will report incorrect types for chained operations. With the immutable copy fix, each new LazySeq would genuinely have the correct type.

### MEDIUM - String-Based Dispatch

**SD1: Operation dispatch via string matching (Severity: MEDIUM)**
```python
for op, arg in self._operations:
    if op == 'map':
        ...
    elif op == 'filter':
        ...
```
String-based dispatch is fragile -- a typo in the operation name silently does nothing. Use callables or an enum:
```python
# Store the transformation function directly
self._operations.append(lambda result: map(func, result))
```
Then evaluation is simply:
```python
def _evaluate(self):
    result = iter(self._iterable)
    for transform in self._operations:
        result = transform(result)
    return result
```

### LOW - Missing Convenience Methods

**MC1: No distinct/sorted/zip (Severity: LOW)**
Common operations like deduplication, sorting, and zipping are missing. Adding `distinct()` would require maintaining a seen-set, which is a stateful lazy operation.'''),

    ("thinking/code-review", r'''Review this Python code and identify issues:

```python
from typing import List, Tuple, Dict, Set, Optional
from collections import Counter
import re

def word_frequency(text: str) -> Dict[str, int]:
    words = text.lower().split()
    return dict(Counter(words))

def ngrams(text: str, n: int) -> List[Tuple[str, ...]]:
    words = text.lower().split()
    return [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def fuzzy_match(query: str, candidates: List[str],
                threshold: float = 0.7) -> List[Tuple[str, float]]:
    results = []
    for candidate in candidates:
        distance = levenshtein_distance(query.lower(), candidate.lower())
        max_len = max(len(query), len(candidate))
        similarity = 1 - (distance / max_len) if max_len > 0 else 1.0
        if similarity >= threshold:
            results.append((candidate, similarity))
    return sorted(results, key=lambda x: x[1], reverse=True)

def extract_emails(text: str) -> List[str]:
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(pattern, text)

def extract_urls(text: str) -> List[str]:
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(pattern, text)

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b\w+\b', text.lower())

def tfidf(documents: List[str]) -> List[Dict[str, float]]:
    import math
    doc_tokens = [tokenize(doc) for doc in documents]
    doc_count = len(documents)

    # Term frequency
    tf_docs = []
    for tokens in doc_tokens:
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        for token in tf:
            tf[token] /= len(tokens)
        tf_docs.append(tf)

    # Inverse document frequency
    idf = {}
    all_tokens = set()
    for tokens in doc_tokens:
        all_tokens.update(tokens)
    for token in all_tokens:
        containing = sum(1 for tokens in doc_tokens if token in tokens)
        idf[token] = math.log(doc_count / containing)

    # TF-IDF
    tfidf_docs = []
    for tf in tf_docs:
        tfidf = {}
        for token, freq in tf.items():
            tfidf[token] = freq * idf[token]
        tfidf_docs.append(tfidf)

    return tfidf_docs

def find_similar_documents(documents: List[str], query: str,
                          top_n: int = 5) -> List[Tuple[int, float]]:
    all_docs = documents + [query]
    vectors = tfidf(all_docs)
    query_vector = vectors[-1]
    doc_vectors = vectors[:-1]

    scores = []
    for i, doc_vec in enumerate(doc_vectors):
        # Cosine similarity
        common_tokens = set(query_vector.keys()) & set(doc_vec.keys())
        if not common_tokens:
            scores.append((i, 0.0))
            continue
        dot = sum(query_vector[t] * doc_vec[t] for t in common_tokens)
        mag_q = sum(v**2 for v in query_vector.values()) ** 0.5
        mag_d = sum(v**2 for v in doc_vec.values()) ** 0.5
        if mag_q == 0 or mag_d == 0:
            scores.append((i, 0.0))
        else:
            scores.append((i, dot / (mag_q * mag_d)))

    return sorted(scores, key=lambda x: x[1], reverse=True)[:top_n]
```''', r'''<think>
Let me review this text processing code for correctness, performance, and edge cases.

1. word_frequency:
- `text.lower().split()` splits on whitespace only. Punctuation is kept attached to words: "hello," and "hello" are different words. Should strip punctuation or use a proper tokenizer.

2. ngrams:
- Same issue with split(). Also, if n > len(words), the range is empty and returns []. This is correct but not documented.
- List comprehension with tuple() for each ngram creates many tuple objects. For large texts, this consumes a lot of memory. Should be a generator.

3. levenshtein_distance:
- The implementation is correct (Wagner-Fischer algorithm) and O(n*m) time. But it creates a new list for each row. For very long strings, this is slow. Could use numpy or C extension.
- `previous_row = range(len(s2) + 1)` creates a range object, then `previous_row[j + 1] + 1` works because range supports indexing. But it would be clearer to use `list(range(...))`.

4. fuzzy_match:
- Computes levenshtein_distance for every candidate. For large candidate lists, this is O(n * m * k) where n = number of candidates, m = query length, k = max candidate length. Very slow.
- No early termination. Even if a perfect match is found, all remaining candidates are checked.

5. extract_emails regex:
- The pattern is reasonable but misses some valid email formats and matches some invalid ones. For example, it matches consecutive dots like "a..b@c.com" which is invalid. But for practical purposes this is usually acceptable.

6. extract_urls regex:
- `https?://[^\s<>"{}|\\^`\[\]]+` -- the backtick in the character class may cause issues. Also, this matches trailing punctuation: "http://example.com." matches with the trailing period.

7. tfidf implementation:
- Variable name shadowing: the local variable `tfidf` inside the function shadows the function name `tfidf`. After the local `tfidf = {}` assignment, the function name is no longer accessible inside that scope. This is a maintainability issue.
- `token in tokens` in the IDF calculation does a linear search through a list for each token. Should convert tokens to a set first.
- IDF uses `log(doc_count / containing)` without +1 smoothing. If a token appears in all documents, IDF is log(1) = 0, which zeros out the TF-IDF. This is technically correct but can cause all common words to vanish.
- Division by zero: `tf[token] /= len(tokens)` -- if a document is empty (no tokens), len(tokens) is 0 and this raises ZeroDivisionError.

8. find_similar_documents:
- Appends the query to documents and recomputes TF-IDF for ALL documents every time. If called multiple times with different queries, the entire corpus is re-processed each time. Should precompute document vectors once.
- The cosine similarity is computed per-query which is fine, but the IDF is affected by including the query as a document, which subtly changes the scores.

Let me structure the review.
</think>

## Code Review: Python Text Processing Utilities

### HIGH - Tokenization Inconsistency

**TK1: split() includes punctuation in tokens (Severity: HIGH)**
```python
words = text.lower().split()
```
`word_frequency` and `ngrams` use `split()` which keeps punctuation attached: `"hello,"` and `"hello"` are counted as different words. But `tokenize` uses `re.findall(r'\b\w+\b', ...)` which correctly strips punctuation. The tokenization is inconsistent across functions. Use `tokenize()` everywhere or provide a consistent tokenizer parameter.

### HIGH - Variable Name Shadowing

**SH1: Local variable shadows function name (Severity: HIGH)**
```python
def tfidf(documents):
    ...
    for tf in tf_docs:
        tfidf = {}  # shadows the function name 'tfidf'
```
The local variable `tfidf` shadows the outer function name. While this does not cause an immediate error in this code, it prevents recursive calls and confuses IDE tooling. Rename the local variable to `tfidf_scores` or similar.

### HIGH - Performance Issues

**P1: Linear search in IDF calculation (Severity: HIGH)**
```python
containing = sum(1 for tokens in doc_tokens if token in tokens)
```
`token in tokens` does a linear search through a list for each token and each document. For a corpus with V unique tokens and D documents of average length L, this is O(V * D * L). Convert to sets:
```python
doc_token_sets = [set(tokens) for tokens in doc_tokens]
containing = sum(1 for token_set in doc_token_sets if token in token_set)
```

**P2: TF-IDF recomputed on every query (Severity: HIGH)**
`find_similar_documents` adds the query to the corpus and recomputes TF-IDF for all documents. For repeated queries against the same corpus, precompute document vectors once and only compute the query vector at search time.

**P3: Query changes IDF values (Severity: MEDIUM)**
Including the query as a document when computing IDF subtly changes the IDF weights for all terms. The query's presence affects the document frequency calculation, producing slightly different scores than expected.

### MEDIUM - Division by Zero

**DZ1: Empty document causes ZeroDivisionError (Severity: MEDIUM)**
```python
tf[token] /= len(tokens)
```
If a document is empty (`tokenize("")` returns `[]`), `len(tokens)` is 0. This raises ZeroDivisionError. Guard against empty documents:
```python
if tokens:
    for token in tf:
        tf[token] /= len(tokens)
```

### MEDIUM - fuzzy_match Scalability

**FM1: O(n * m * k) fuzzy matching (Severity: MEDIUM)**
Computing Levenshtein distance for every candidate is quadratic in string length and linear in candidate count. For 100,000 candidates with strings averaging 50 characters, this is extremely slow. Consider:
- BK-trees for approximate matching
- Trigram indexing for candidate pruning
- rapidfuzz library for C-optimized Levenshtein

### MEDIUM - URL Extraction

**URL1: Trailing punctuation matched (Severity: MEDIUM)**
```python
pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
```
This matches trailing periods and commas: `"Visit http://example.com."` returns `"http://example.com."` with the period. Strip common trailing punctuation:
```python
urls = re.findall(pattern, text)
return [url.rstrip('.,;:!?)') for url in urls]
```

### LOW - Memory

**ME1: ngrams returns list instead of generator (Severity: LOW)**
For large texts, generating all n-grams as tuples in a list consumes significant memory. Return a generator:
```python
def ngrams(text, n):
    words = text.lower().split()
    for i in range(len(words) - n + 1):
        yield tuple(words[i:i+n])
```'''),
]
