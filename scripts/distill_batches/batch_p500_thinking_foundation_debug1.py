"""Phase 1A: Foundation Thinking — Systematic Debugging (Part 1/4)
Off-by-one errors, null reference chains, race conditions, memory leaks."""

PAIRS = [
    (
        "thinking/debug-off-by-one-pagination",
        "Users report that page 2 of search results shows the last item from page 1. Here's the pagination code:\n\n```python\ndef get_page(items, page_num, page_size=10):\n    start = (page_num - 1) * page_size\n    end = start + page_size + 1\n    return items[start:end]\n```",
        r'''<think>
Let me trace through with concrete values.

Given: items = [0,1,2,3,4,5,6,7,8,9,10,11,12,...], page_size=10

Page 1 (page_num=1):
  start = (1-1) * 10 = 0
  end = 0 + 10 + 1 = 11
  items[0:11] = [0,1,2,3,4,5,6,7,8,9,10]  ← 11 items! Should be 10.

Page 2 (page_num=2):
  start = (2-1) * 10 = 10
  end = 10 + 10 + 1 = 21
  items[10:21] = [10,11,12,...,20]  ← starts at item 10

Item 10 appears on BOTH page 1 and page 2. That's the reported bug.

The bug is `+ 1` in the end calculation. Python slicing is already exclusive on the right side: `items[0:10]` gives items 0-9, which is 10 items. Adding 1 makes it 11 items per page, and the last item overlaps with the next page's first item.

Let me verify the fix: remove the `+ 1`.

Page 1: items[0:10] = [0,1,2,3,4,5,6,7,8,9] — 10 items ✓
Page 2: items[10:20] = [10,11,12,...,19] — 10 items, no overlap ✓

Also checking edge cases:
- Empty items: items[0:10] = [] — correct ✓
- Last page with fewer items: if 25 total, page 3 = items[20:30] = [20,21,22,23,24] — 5 items, correct ✓
- page_num=0: start = -10, items[-10:1] — this is a bug! Should validate page_num >= 1.
</think>

The bug is the `+ 1` in the end index. Python slicing is already exclusive on the right — `items[0:10]` returns 10 items (indices 0-9). The `+ 1` makes each page return 11 items, causing the last item to appear on the next page too.

```python
def get_page(items, page_num, page_size=10):
    if page_num < 1:
        page_num = 1
    start = (page_num - 1) * page_size
    end = start + page_size  # No +1: Python slicing is already exclusive
    return items[start:end]
```

**Trace to verify:**
```
Page 1: items[0:10]  = items 0-9   (10 items)
Page 2: items[10:20] = items 10-19 (10 items, no overlap)
Page 3: items[20:30] = items 20-24 (5 items if only 25 total)
```'''
    ),
    (
        "thinking/debug-off-by-one-binary-search",
        "My binary search sometimes returns -1 even when the element exists in the sorted array:\n\n```python\ndef binary_search(arr, target):\n    left, right = 0, len(arr)\n    while left < right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1\n```",
        r'''<think>
Let me trace through a failing case. The issue is likely at the boundaries.

Let me try arr = [1, 3, 5, 7, 9], target = 9 (last element).

Initial: left=0, right=5 (len(arr)=5)

Iteration 1: left=0 < right=5
  mid = (0+5)//2 = 2
  arr[2] = 5 < 9 → left = 3

Iteration 2: left=3 < right=5
  mid = (3+5)//2 = 4
  arr[4] = 9 == 9 → return 4 ✓

OK, that works. Let me try target = 1 (first element).

Initial: left=0, right=5

Iteration 1: mid=2, arr[2]=5 > 1 → right = 2-1 = 1

Iteration 2: left=0 < right=1
  mid = (0+1)//2 = 0
  arr[0] = 1 == 1 → return 0 ✓

Hmm, let me try target = 3.

Initial: left=0, right=5

Iteration 1: mid=2, arr[2]=5 > 3 → right = 1

Iteration 2: left=0 < right=1
  mid=0, arr[0]=1 < 3 → left = 1

Iteration 3: left=1, right=1 → left < right is FALSE → exit loop → return -1

But arr[1] = 3! We never checked index 1.

The problem: there's a mismatch between the loop invariant and the right bound update.

The code initializes `right = len(arr)` which means the search space is [left, right) — exclusive on the right. This is fine for the initial setup.

But then `right = mid - 1` treats right as inclusive (like the [left, right] convention). The `- 1` skips the element at `mid - 1`.

The fix: either use exclusive right consistently OR inclusive right consistently.

**Option A: Exclusive right (right = len(arr), right = mid)**
```
while left < right:
    right = mid  # not mid-1, because right is exclusive
```

**Option B: Inclusive right (right = len(arr)-1, right = mid-1)**
```
right = len(arr) - 1
while left <= right:  # <= because right is inclusive
    right = mid - 1
```

The current code mixes conventions: exclusive initialization with inclusive update. That's the bug.
</think>

The bug is a **mixed boundary convention**. `right = len(arr)` uses an exclusive upper bound (`[left, right)`), but `right = mid - 1` uses an inclusive convention (`[left, right]`). This mismatch causes elements to be skipped.

**Trace showing the bug** with `arr = [1, 3, 5, 7, 9]`, `target = 3`:
```
left=0, right=5 → mid=2, arr[2]=5 > 3 → right = 1
left=0, right=1 → mid=0, arr[0]=1 < 3 → left = 1
left=1, right=1 → loop exits (1 < 1 is false) → returns -1
arr[1] = 3 was NEVER checked!
```

**Fix — use consistent exclusive right:**
```python
def binary_search(arr, target):
    left, right = 0, len(arr)  # [left, right) exclusive
    while left < right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid  # NOT mid-1: right is exclusive
    return -1
```

**The rule:** if `right` starts as `len(arr)`, the convention is exclusive — use `right = mid` and `while left < right`. If `right` starts as `len(arr) - 1`, the convention is inclusive — use `right = mid - 1` and `while left <= right`. Never mix them.'''
    ),
    (
        "thinking/debug-off-by-one-fence-post",
        "We're building a grid layout. Users report that a 4x4 grid shows only 3 vertical divider lines instead of the expected number. Here's the code:\n\n```python\ndef draw_grid(cols, rows, cell_width, cell_height):\n    lines = []\n    # Vertical dividers\n    for i in range(1, cols):\n        x = i * cell_width\n        lines.append(Line(x, 0, x, rows * cell_height))\n    # Horizontal dividers\n    for j in range(1, rows):\n        y = j * cell_height\n        lines.append(Line(0, y, cols * cell_width, y))\n    return lines\n```\n\nIs this a bug or is the expected number wrong?",
        r'''<think>
This is a classic fence post problem. Let me think about what's correct.

A 4-column grid:
```
|  col1  |  col2  |  col3  |  col4  |
```

How many vertical lines? There are 5: the left border, 3 inner dividers, and the right border. Or there are 3: just the inner dividers (no outer borders).

The code draws `range(1, cols)` = range(1, 4) = [1, 2, 3] → 3 vertical lines at x=1*w, x=2*w, x=3*w. These are the 3 INNER dividers between the 4 columns.

Is this correct? It depends on the expectation:
- If the grid needs outer borders: need 5 vertical lines (0, w, 2w, 3w, 4w) → `range(0, cols+1)` = 5 lines
- If only inner dividers: need 3 lines → `range(1, cols)` = 3 lines ✓

The user says "3 vertical divider lines instead of the expected number" for a 4x4 grid. The expected number depends on whether they want borders.

For a standard grid with borders: N columns need N+1 vertical lines.
For inner dividers only: N columns need N-1 vertical lines.

The code produces N-1 = 3 lines. If the user expects a bordered grid (N+1 = 5), then yes, it's a bug. If they expect inner dividers only, 3 is correct and the expectation is wrong.

But "grid layout" typically includes the outer border. And the visual looks wrong without borders — cells on the edges look unbounded.

Let me also check: does the current code draw borders at all? No — both loops start at 1, skipping the 0 position and stopping before the max position. No outer borders are drawn.

Most likely the user wants a bordered grid. The fix is to include the borders.

But wait — there's another interpretation. Maybe "4x4 grid" means 4 CELLS, which needs 5 lines; or it could mean a grid with 4 lines on each side. Let me go with the standard interpretation: 4 columns of cells → 5 vertical lines (including borders).
</think>

This is a **fence post problem**. Whether it's a bug depends on whether you want outer borders.

```
With borders (5 lines):          Inner dividers only (3 lines):
|  1  |  2  |  3  |  4  |         1  |  2  |  3  |  4
                                   (no outer edges)
```

The code draws `range(1, 4)` = 3 lines — **inner dividers only, no borders**. For a standard grid, you want N+1 = 5 lines.

**Fix for bordered grid:**
```python
def draw_grid(cols, rows, cell_width, cell_height):
    lines = []
    # Vertical lines: 0 through cols (inclusive) = cols+1 lines
    for i in range(cols + 1):
        x = i * cell_width
        lines.append(Line(x, 0, x, rows * cell_height))
    # Horizontal lines: 0 through rows (inclusive) = rows+1 lines
    for j in range(rows + 1):
        y = j * cell_height
        lines.append(Line(0, y, cols * cell_width, y))
    return lines
```

**The fence post principle:** N sections need N+1 posts (with borders) or N-1 dividers (without borders). Common instances:
- N cells → N+1 grid lines
- N characters → N-1 separators (e.g., `",".join(items)`)
- N elements → N-1 gaps between them
- N segments → N+1 endpoints'''
    ),
    (
        "thinking/debug-null-chain-user-profile",
        "Our API sometimes returns 500 errors on the user profile endpoint. It works for most users but crashes for some:\n\n```python\n@app.get('/api/users/{user_id}/profile')\nasync def get_profile(user_id: int):\n    user = await db.get_user(user_id)\n    team = await db.get_team(user.team_id)\n    manager = await db.get_user(team.manager_id)\n    \n    return {\n        'name': user.name,\n        'email': user.email,\n        'team': team.name,\n        'manager': manager.name,\n        'manager_email': manager.email,\n        'department': team.department.name,\n    }\n```\n\nThe error is `AttributeError: 'NoneType' object has no attribute 'team_id'` but it doesn't always happen.",
        r'''<think>
The error says `'NoneType' object has no attribute 'team_id'`. That means `user` is None, which means `db.get_user(user_id)` returned None. This happens when the user_id doesn't exist in the database.

But wait — the endpoint is `/api/users/{user_id}/profile`, so the user_id comes from the URL. If someone requests `/api/users/99999/profile` and user 99999 doesn't exist, `user` is None and `user.team_id` crashes.

But the user says "it works for most users but crashes for some." So the users DO exist. Let me look for other None possibilities.

Actually, let me re-read the error. It says `'NoneType' object has no attribute 'team_id'`. The only place `.team_id` is accessed is `user.team_id`. So `user` is None.

But if the user exists... unless `db.get_user` returns None for some users that DO exist? That seems unlikely. More likely:

Wait — could `user.team_id` itself be None? No, the error says the object before `.team_id` is None, not that `team_id` is None.

Let me reconsider. The user says it "crashes for some users." Maybe those users were deleted? Or maybe there's a soft delete flag and `get_user` returns None for deleted users?

Actually, let me look at ALL the None-dereference risks in this code:

Line 1: `user = await db.get_user(user_id)` → could be None if user doesn't exist
Line 2: `user.team_id` → crashes if user is None
Line 2: `team = await db.get_team(user.team_id)` → could be None if team doesn't exist, AND could fail if user.team_id is None (no team assigned)
Line 3: `team.manager_id` → crashes if team is None
Line 3: `manager = await db.get_user(team.manager_id)` → could be None if manager was deleted, AND could fail if team.manager_id is None (no manager)
Line 9: `team.department.name` → crashes if team.department is None (no department assigned)

That's FIVE possible None dereferences in 3 lines of code!

The "works for most, crashes for some" pattern suggests it's not the user_id being invalid (that would be a 404). More likely:
1. Some users have `team_id = None` (not assigned to a team)
2. Some teams have `manager_id = None` (no manager)
3. Some teams have no department

Let me check: the error is specifically `'NoneType' has no attribute 'team_id'`, meaning `user` is None. But actually... could `user.team_id` be None, causing `db.get_team(None)` to return None, and then THAT would crash on `team.manager_id` with a different error? The reported error specifically mentions `team_id`.

So the crash is on line 2: `user.team_id` where `user` is None. The user_id must reference a nonexistent user.

But the user said "some" users — implying specific user IDs that worked before. Could be:
- Users were deleted from the database
- Users exist in the auth system but not in the users table (data inconsistency)
- A caching issue where stale user IDs reference deleted users

Regardless of root cause, the code needs None checks at every step.
</think>

There are **5 null dereference risks** in 3 lines. The specific crash (`user` is None) means `db.get_user(user_id)` returned None — likely a deleted or nonexistent user. But even fixing that reveals more crashes waiting to happen.

### All null dereference points

```python
user = await db.get_user(user_id)          # → None if user deleted/missing
team = await db.get_team(user.team_id)     # → crash if user is None
                                            # → None if user.team_id is None (no team)
manager = await db.get_user(team.manager_id)  # → crash if team is None
                                               # → None if team.manager_id is None
team.department.name                        # → crash if department is None
```

### Fixed version

```python
@app.get('/api/users/{user_id}/profile')
async def get_profile(user_id: int):
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(404, f"User {user_id} not found")

    result = {
        'name': user.name,
        'email': user.email,
        'team': None,
        'manager': None,
        'manager_email': None,
        'department': None,
    }

    if user.team_id:
        team = await db.get_team(user.team_id)
        if team:
            result['team'] = team.name
            result['department'] = team.department.name if team.department else None

            if team.manager_id:
                manager = await db.get_user(team.manager_id)
                if manager:
                    result['manager'] = manager.name
                    result['manager_email'] = manager.email

    return result
```

**The "works for most, crashes for some" pattern** almost always means a null reference chain — data that's present for most records but missing for edge cases (new users without a team, teams without a manager, deleted records referenced by foreign keys).'''
    ),
    (
        "thinking/debug-null-chain-nested-config",
        "Our app crashes on startup with `KeyError: 'database'` but only in the staging environment. The config loading code:\n\n```python\nimport yaml\nimport os\n\ndef load_config():\n    env = os.getenv('APP_ENV', 'development')\n    \n    with open('config/default.yaml') as f:\n        config = yaml.safe_load(f)\n    \n    env_file = f'config/{env}.yaml'\n    if os.path.exists(env_file):\n        with open(env_file) as f:\n            env_config = yaml.safe_load(f)\n        config.update(env_config)\n    \n    return config\n\nconfig = load_config()\ndb_host = config['database']['host']\n```\n\ndefault.yaml:\n```yaml\ndatabase:\n  host: localhost\n  port: 5432\nredis:\n  host: localhost\n```\n\nstaging.yaml:\n```yaml\ndatabase:\n  host: staging-db.internal\n```",
        r'''<think>
The error is `KeyError: 'database'` which means `config['database']` doesn't exist after loading. But `default.yaml` clearly has a `database` section. Let me trace through what happens.

Step 1: Load default.yaml
```python
config = {
    'database': {'host': 'localhost', 'port': 5432},
    'redis': {'host': 'localhost'}
}
```

Step 2: Load staging.yaml
```python
env_config = {
    'database': {'host': 'staging-db.internal'}
}
```

Step 3: `config.update(env_config)`

Here's the problem. `dict.update()` does a SHALLOW merge. It replaces top-level keys entirely, it doesn't deep-merge nested dicts.

After update:
```python
config = {
    'database': {'host': 'staging-db.internal'},  # port: 5432 is GONE!
    'redis': {'host': 'localhost'}
}
```

Wait, but the database key IS still there — it just lost the `port` field. The `KeyError: 'database'` wouldn't happen from this alone. Let me re-read...

Hmm, the error IS `KeyError: 'database'`. So config doesn't have a 'database' key at all. When would that happen?

What if `staging.yaml` is empty or has a YAML parsing issue? Let me check:

If staging.yaml is empty:
```python
env_config = yaml.safe_load(f)  # Returns None for empty YAML
config.update(None)  # TypeError: cannot convert 'NoneType' to dict
```

That would be a TypeError, not KeyError. But what if staging.yaml has just a comment? Same thing — `yaml.safe_load` returns None.

What if staging.yaml has a YAML syntax error? `yaml.safe_load` would raise `yaml.YAMLError`, not a KeyError.

Wait — what if the issue is different. What if `APP_ENV` is set to something like `staging ` (with a trailing space or newline)? Then `env_file = 'config/staging .yaml'` which doesn't exist, so the env override is skipped. But then config would have the defaults, including `database`. So it wouldn't crash...

Let me re-examine. Actually, could the staging.yaml file contain:

```yaml
database:
  host: staging-db.internal
```

But what if it's actually:
```yaml
database: null
```

or:
```yaml
database:
```

(database with no value = None in YAML)

If staging.yaml parses to `{'database': None}`, then after `config.update({'database': None})`:
```python
config = {
    'database': None,  # Overwrote the dict with None!
    'redis': {'host': 'localhost'}
}
```

Now `config['database']` is None, and `config['database']['host']` would give `TypeError: 'NoneType' object is not subscriptable`, not KeyError.

Hmm, let me reconsider the actual error. Oh wait — what if someone actually sets `database` as a top-level key with a string value? Like:

```yaml
database: staging-db.internal
```

Then `config['database']` is the string `'staging-db.internal'`, and `config['database']['host']` would give... well, strings support indexing, so `'staging-db.internal'['host']` would be TypeError.

I keep getting TypeError, not KeyError. When would we get KeyError: 'database'?

Oh! What if `yaml.safe_load` returns something that's not a dict? What if the staging.yaml file contains just:

```yaml
staging
```

Then `yaml.safe_load` returns the string `'staging'`. Then `config.update('staging')` — calling `.update()` with a string iterates over its characters. In Python, `dict.update(string)` raises: `ValueError: dictionary update sequence element #0 has length 1; 2 is required`.

Actually, I think the real issue might be simpler. Let me re-read the error message: `KeyError: 'database'`. What if the staging.yaml file overrides the ENTIRE config? What if staging.yaml looks like:

```yaml
app_name: staging-app
database:
  host: staging-db.internal
```

No wait, that still has 'database'.

Let me think differently. What if yaml.safe_load returns None (empty file), and instead of TypeError, Python's dict.update(None) raises... let me check. Actually `dict.update(None)` raises `TypeError: cannot convert 'NoneType' object to dict iteration`.

But what if the code handles this silently and config becomes empty? No, .update() on a TypeError would crash before that.

Actually, I think I may have been overthinking this. Let me re-read the code:

```python
env_config = yaml.safe_load(f)
config.update(env_config)
```

If staging.yaml is completely empty: `env_config = None`, `config.update(None)` → TypeError. App crashes with a different error.

But the user says the error is `KeyError: 'database'`. So config IS a dict, but it doesn't have 'database'.

NEW HYPOTHESIS: What if there's a `config/staging.yaml` file that exists but has been overwritten with completely different content? Like someone put environment variables there instead of YAML:

```
APP_NAME=staging
DB_HOST=staging-db.internal
```

`yaml.safe_load` would parse this as `{'APP_NAME': 'staging'}` (YAML is a superset of some key: value formats). No 'database' key.

OR: the simplest explanation — the original poster showed us the INTENDED staging.yaml, but the actual file on the staging server is different or corrupt.

Actually, wait. Let me re-read the code one more time. The REAL bug might be the shallow merge issue I identified first. The user says `KeyError: 'database'`, but maybe they misread the error. Maybe it's actually `KeyError: 'host'` — because after the shallow merge, `config['database']` is `{'host': 'staging-db.internal'}` (without 'port'), and somewhere else in the code `config['database']['port']` is accessed. But the user reported the error on `config['database']['host']`.

I think the most likely real-world cause is: staging.yaml is empty or malformed on the staging server, `yaml.safe_load` returns None, and the code should handle that. Combined with the shallow merge problem.

Let me present both issues.
</think>

Two bugs here — one that causes the immediate crash and one that will bite later.

### Bug 1: `yaml.safe_load` returns `None` for empty files

If `staging.yaml` is empty (or contains only comments), `yaml.safe_load` returns `None`. Then `config.update(None)` raises `TypeError`. If the file is malformed (e.g., plain text instead of YAML), the parsed result may have no `database` key.

### Bug 2: `dict.update()` is a shallow merge

Even with valid YAML, `update()` **replaces** nested dicts instead of merging:

```python
default:    {'database': {'host': 'localhost', 'port': 5432}}
staging:    {'database': {'host': 'staging-db.internal'}}
after update: {'database': {'host': 'staging-db.internal'}}
# port: 5432 is GONE
```

### Fixed version

```python
import yaml
import os
import copy

def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config() -> dict:
    env = os.getenv('APP_ENV', 'development').strip()

    with open('config/default.yaml') as f:
        config = yaml.safe_load(f) or {}  # Handle empty file

    env_file = f'config/{env}.yaml'
    if os.path.exists(env_file):
        with open(env_file) as f:
            env_config = yaml.safe_load(f)
        if isinstance(env_config, dict):  # Guard against malformed YAML
            config = deep_merge(config, env_config)

    return config
```

**After deep merge:**
```python
{'database': {'host': 'staging-db.internal', 'port': 5432}, 'redis': {'host': 'localhost'}}
#                                              ^^^^ preserved!
```'''
    ),
    (
        "thinking/debug-race-condition-counter",
        "Our analytics counter is inaccurate. We expect ~10,000 page views per hour but the counter shows only ~7,000-8,000. The code:\n\n```python\nimport redis\n\nr = redis.Redis()\n\ndef record_page_view(page_id):\n    key = f'views:{page_id}'\n    current = r.get(key)\n    if current is None:\n        r.set(key, 1)\n    else:\n        r.set(key, int(current) + 1)\n```",
        r'''<think>
This is a classic read-modify-write race condition. Let me trace through concurrent execution.

The operation is:
1. READ: `current = r.get(key)` → gets value, say 42
2. MODIFY: `int(current) + 1` → computes 43 in Python
3. WRITE: `r.set(key, 43)` → writes 43 to Redis

If two requests arrive simultaneously:

```
Thread A: r.get(key) → 42
Thread B: r.get(key) → 42        (BEFORE Thread A writes)
Thread A: r.set(key, 43)          (42 + 1)
Thread B: r.set(key, 43)          (42 + 1, same value!)
```

Both threads read 42, both compute 43, both write 43. One page view is lost. This is the "lost update" problem.

With 10,000 views/hour, that's ~2.8 views/second. At web-scale concurrency, many of these will overlap, easily losing 20-30% of counts. That matches the ~7,000-8,000 observed.

**Why not just use INCR?**

Redis has `INCR key` which atomically increments a value. It's a single command — no read-modify-write cycle, no race condition.

```python
def record_page_view(page_id):
    r.incr(f'views:{page_id}')
```

`INCR` is atomic because Redis is single-threaded — each command runs to completion before the next one starts. There's no window where two operations can interleave.

But what about the initialization? What if the key doesn't exist? `INCR` on a non-existent key initializes it to 0 then increments to 1. So the `if current is None` branch is unnecessary.

**Could there be other issues?**

1. **Pipeline batching**: if using Redis pipelines, multiple INCR commands in a pipeline are still atomic individually.
2. **Redis persistence**: if Redis isn't configured with AOF, counts could be lost on restart. But that's a different issue from the race condition.
3. **Key expiry**: no TTL is set, so keys accumulate forever. Should add expiry for time-windowed counters.

The race condition is the primary bug. INCR is the correct fix.
</think>

**Read-modify-write race condition.** Two concurrent requests both read the same value, both increment it, and one increment is lost.

```
Thread A: GET views:home → 42
Thread B: GET views:home → 42     ← reads BEFORE A writes
Thread A: SET views:home 43
Thread B: SET views:home 43       ← overwrites A's write
Result: 1 view lost
```

At 2.8 requests/second, overlapping reads happen frequently — easily losing 20-30% of counts.

### Fix: use Redis INCR (atomic)

```python
def record_page_view(page_id):
    r.incr(f'views:{page_id}')  # Atomic: read+increment+write in one command
```

`INCR` is atomic because Redis executes commands sequentially in a single thread. No interleaving is possible. If the key doesn't exist, `INCR` initializes it to 0 then increments to 1 — no need for the `if current is None` check.

### For more complex atomic operations, use Lua scripts

```python
# Atomic increment with max cap (can't do with INCR alone)
CAPPED_INCR = r.register_script("""
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    if current < tonumber(ARGV[1]) then
        return redis.call('INCR', KEYS[1])
    end
    return current
""")

def record_capped_view(page_id, max_views=100000):
    return CAPPED_INCR(keys=[f'views:{page_id}'], args=[max_views])
```'''
    ),
    (
        "thinking/debug-race-condition-file-write",
        "Two processes write to the same log file. Sometimes log lines are interleaved or corrupted:\n\n```python\ndef write_log(message):\n    with open('app.log', 'a') as f:\n        timestamp = datetime.now().isoformat()\n        f.write(f'[{timestamp}] {message}\\n')\n```\n\nCorrupted output:\n```\n[2026-03-05T10:23:45] User logged[2026-03-05T10:23:45] Payment processed\n in successfully\n```",
        r'''<think>
The corrupted output shows two log messages interleaved — part of one message, then a whole other message, then the rest of the first one. This is because writes to a file aren't atomic at the OS level (or rather, they ARE atomic only up to PIPE_BUF size on POSIX, typically 4096 bytes, and only for O_APPEND on some systems).

Let me trace what's happening:

Process A calls `write_log("User logged in successfully")`
Process B calls `write_log("Payment processed")`

```
Process A: open('app.log', 'a')
Process A: f.write("[2026-03-05T10:23:45] User logged")  ← partial write
Process B: open('app.log', 'a')
Process B: f.write("[2026-03-05T10:23:45] Payment processed\n")  ← full write
Process A: f.write(" in successfully\n")  ← rest of A's write
```

But wait — `f.write()` in Python writes the ENTIRE string in one call. The interleaving happens at the OS level, not at the Python level. Python calls `write()` with the full string, but the OS might break it into multiple writes if:
1. The write is larger than the kernel buffer
2. The process is preempted mid-write

For small messages (< 4KB), POSIX guarantees that `write()` to a file opened with `O_APPEND` is atomic. Python's `open('app.log', 'a')` uses `O_APPEND`. So for small log lines, the write should be atomic.

But! Python's file I/O is buffered. `f.write()` writes to Python's internal buffer, and the buffer is flushed to the OS in potentially multiple `write()` syscalls. The `with` statement flushes on close, but if the buffer fills mid-message, it might flush a partial message.

Also, the `f.write()` call writes the FORMATTED string, but Python's I/O layer might split it into multiple OS-level writes.

The real solutions:

1. **Use `os.write()` directly** — unbuffered, atomic for small writes
2. **Use file locking** — `fcntl.flock()` on Unix, `msvcrt.locking()` on Windows
3. **Use logging module** — has built-in locking with `FileHandler`
4. **Use a logging service** — write to syslog, journald, or a log aggregator

The simplest fix is to use Python's `logging` module, which handles file locking internally.
</think>

The interleaving happens because Python's buffered I/O may split a single `f.write()` into multiple OS-level `write()` syscalls. Even though the file is opened with append mode (`O_APPEND`), Python's buffer layer breaks the atomicity guarantee.

### Fix 1: Use Python's logging module (built-in locking)

```python
import logging

logger = logging.getLogger('app')
handler = logging.FileHandler('app.log')
handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def write_log(message):
    logger.info(message)  # Thread-safe and process-safe with locking
```

### Fix 2: Atomic write with OS-level guarantee

```python
import os

def write_log(message):
    timestamp = datetime.now().isoformat()
    line = f'[{timestamp}] {message}\n'
    # Encode first, then single unbuffered write — atomic for < PIPE_BUF (4096 bytes)
    fd = os.open('app.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    try:
        os.write(fd, line.encode())  # Single syscall, atomic for small messages
    finally:
        os.close(fd)
```

### Fix 3: File locking for guaranteed safety

```python
import fcntl  # Unix only

def write_log(message):
    with open('app.log', 'a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        try:
            timestamp = datetime.now().isoformat()
            f.write(f'[{timestamp}] {message}\n')
            f.flush()  # Ensure write hits OS before releasing lock
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

### Best practice: use the `logging` module. It handles all of this correctly and supports log rotation, formatting, and multiple handlers out of the box.'''
    ),
    (
        "thinking/debug-memory-leak-closure",
        "Our long-running Python service's memory grows by ~50MB/hour. After profiling, we found this event handler pattern throughout the code:\n\n```python\nclass EventBus:\n    def __init__(self):\n        self._handlers = {}\n    \n    def on(self, event_name, handler):\n        if event_name not in self._handlers:\n            self._handlers[event_name] = []\n        self._handlers[event_name].append(handler)\n    \n    def emit(self, event_name, data):\n        for handler in self._handlers.get(event_name, []):\n            handler(data)\n\nbus = EventBus()  # Global singleton\n\nclass RequestProcessor:\n    def __init__(self, request_data):\n        self.data = request_data  # Could be large (MB of JSON)\n        self.results = []\n        \n        # Register handler for this request\n        bus.on('data_ready', lambda d: self.handle_data(d))\n    \n    def handle_data(self, data):\n        self.results.append(data)\n```",
        r'''<think>
Let me trace the object lifecycle.

1. A request comes in, creating a `RequestProcessor` instance:
   ```python
   proc = RequestProcessor(large_json_data)  # proc holds MB of data
   ```

2. The constructor registers a lambda on the global EventBus:
   ```python
   bus.on('data_ready', lambda d: self.handle_data(d))
   ```

3. The request finishes, `proc` goes out of scope in the calling function.

4. But does `proc` get garbage collected? Let's check.

The lambda `lambda d: self.handle_data(d)` is a closure that captures `self` — a reference to the `RequestProcessor` instance. This lambda is stored in `bus._handlers['data_ready']`.

The `bus` is a global singleton. It persists for the lifetime of the process. The `_handlers` dict holds a list of lambdas. Each lambda holds a reference to its `RequestProcessor`. Each `RequestProcessor` holds `self.data` (potentially MB of JSON).

Reference chain:
```
bus (global) → _handlers dict → 'data_ready' list → lambda → self (RequestProcessor) → self.data (large JSON)
```

The `RequestProcessor` can NEVER be garbage collected because the global `bus` holds a reference to it (via the lambda). Every request creates a new handler that's never removed. After 1000 requests, there are 1000 lambdas, each holding a reference to a dead `RequestProcessor` with MB of data.

50MB/hour growth with, say, 500 requests/hour = ~100KB per request retained. That matches "large JSON" data.

**Fix options:**

1. **Remove the handler when done:**
   ```python
   bus.off('data_ready', handler)  # Need to add an off() method
   ```
   But the lambda is anonymous — can't reference it later to remove it.

2. **Use weak references:**
   ```python
   import weakref
   bus.on('data_ready', weakref.WeakMethod(self.handle_data))
   ```
   When the `RequestProcessor` is garbage collected, the weak reference becomes dead, and the handler can be cleaned up.

3. **Use a bounded/scoped event handler:**
   Don't register on the global bus. Give each request its own event scope.

4. **Context manager pattern:**
   ```python
   with bus.scoped_handler('data_ready', handler):
       # handler is active
   # handler is automatically removed
   ```

The best fix depends on the architecture. For a request-scoped handler, option 3 or 4 is cleanest. For general event buses, option 1 with named handlers.

The fundamental lesson: event handlers, callbacks, and closures that reference objects create implicit references that prevent garbage collection. ALWAYS have a corresponding "unsubscribe" for every "subscribe."
</think>

**Memory leak via closure references.** Each request registers a lambda on the global EventBus that captures `self`. The lambda is never removed, so every `RequestProcessor` is kept alive forever.

### Reference chain preventing GC

```
bus (global, lives forever)
  → _handlers['data_ready'] (list, grows forever)
    → lambda (closure, captures self)
      → RequestProcessor instance (MB of data)
        → self.data (large JSON, never freed)
```

After 1000 requests: 1000 dead processors still in memory, each holding MB of data.

### Fix: always unsubscribe

```python
class EventBus:
    def __init__(self):
        self._handlers = {}

    def on(self, event_name, handler):
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)
        # Return unsubscribe function
        def off():
            try:
                self._handlers[event_name].remove(handler)
            except ValueError:
                pass
        return off

    def emit(self, event_name, data):
        for handler in self._handlers.get(event_name, []):
            handler(data)


class RequestProcessor:
    def __init__(self, request_data):
        self.data = request_data
        self.results = []
        self._unsub = bus.on('data_ready', self.handle_data)

    def handle_data(self, data):
        self.results.append(data)

    def close(self):
        """Call when request is done to prevent memory leak."""
        self._unsub()
        self.data = None  # Release large data immediately
```

### Even better: use `weakref` for automatic cleanup

```python
import weakref

class EventBus:
    def on(self, event_name, handler):
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        # Store weak reference — auto-removed when object is GC'd
        if hasattr(handler, '__self__'):  # Bound method
            ref = weakref.WeakMethod(handler, lambda r: self._cleanup(event_name, r))
        else:
            ref = weakref.ref(handler, lambda r: self._cleanup(event_name, r))
        self._handlers[event_name].append(ref)

    def _cleanup(self, event_name, dead_ref):
        """Called automatically when the referenced object is garbage collected."""
        if event_name in self._handlers:
            self._handlers[event_name] = [
                r for r in self._handlers[event_name] if r() is not None
            ]

    def emit(self, event_name, data):
        for ref in self._handlers.get(event_name, []):
            handler = ref()  # Dereference
            if handler is not None:
                handler(data)
```

**The rule: every subscribe needs an unsubscribe.** Closures, callbacks, and event handlers create invisible reference chains that defeat garbage collection. In long-running services, this is the #1 cause of memory leaks.'''
    ),
    (
        "thinking/debug-memory-leak-cache-unbounded",
        "Our Django web app's memory grows to 4GB and then OOM-kills. We use a simple in-memory cache:\n\n```python\n_cache = {}\n\ndef get_user_profile(user_id):\n    if user_id not in _cache:\n        profile = User.objects.select_related('team', 'department').get(id=user_id)\n        _cache[user_id] = {\n            'name': profile.name,\n            'email': profile.email,\n            'team': profile.team.name,\n            'avatar_url': profile.avatar_url,\n            'preferences': profile.preferences,  # JSON field, can be large\n        }\n    return _cache[user_id]\n```",
        r'''<think>
Classic unbounded cache. Let me analyze the growth.

The `_cache` dict grows with every unique `user_id` that's requested. It never shrinks — there's no eviction, no TTL, no max size.

How fast does it grow?
- Each cache entry: name (50B) + email (50B) + team (30B) + avatar_url (100B) + preferences (could be KB)
- Let's estimate 2KB per user (preferences can be large)
- If the app serves 500,000 unique users: 500K × 2KB = 1GB
- If users have large preferences or the app serves more users: easily 4GB

The cache has two problems:
1. **No eviction**: entries are never removed, even for users who haven't visited in months
2. **No size limit**: the cache grows until it OOM-kills the process
3. **Stale data**: if a user updates their profile, the cached version is never invalidated

Additional issue: in Django with multiple workers (gunicorn/uwsgi), each worker has its OWN copy of `_cache`. 4 workers × 1GB cache = 4GB total memory. Each worker caches the same users independently.

**Fix options:**

1. **LRU cache with max size** — `functools.lru_cache` or `cachetools.TTLCache`
2. **External cache (Redis/Memcached)** — shared across workers, has built-in eviction
3. **TTL (time-to-live)** — entries expire after N minutes

For a Django app, the best fix is usually Redis (Django has built-in cache framework support). But for a quick fix, `cachetools.TTLCache` with a max size works.
</think>

**Unbounded cache with no eviction.** The dict grows with every unique user and never shrinks. With large `preferences` JSON fields, this hits 4GB and triggers OOM.

### The math

```
500K unique users × 2KB average entry = 1GB per worker
4 gunicorn workers × 1GB each = 4GB → OOM
```

### Fix 1: Bounded LRU with TTL (quick fix)

```python
from cachetools import TTLCache

# Max 10,000 entries, expire after 5 minutes
_cache = TTLCache(maxsize=10_000, ttl=300)

def get_user_profile(user_id):
    if user_id not in _cache:
        profile = User.objects.select_related('team', 'department').get(id=user_id)
        _cache[user_id] = {
            'name': profile.name,
            'email': profile.email,
            'team': profile.team.name,
            'avatar_url': profile.avatar_url,
            'preferences': profile.preferences,
        }
    return _cache[user_id]
```

Memory: 10K × 2KB = 20MB max. Bounded and predictable.

### Fix 2: Django cache framework with Redis (proper fix)

```python
from django.core.cache import cache

def get_user_profile(user_id):
    cache_key = f'user_profile:{user_id}'
    profile_data = cache.get(cache_key)
    if profile_data is None:
        profile = User.objects.select_related('team', 'department').get(id=user_id)
        profile_data = {
            'name': profile.name,
            'email': profile.email,
            'team': profile.team.name,
            'avatar_url': profile.avatar_url,
            'preferences': profile.preferences,
        }
        cache.set(cache_key, profile_data, timeout=300)
    return profile_data

# Invalidate on update
def update_user_profile(user_id, data):
    User.objects.filter(id=user_id).update(**data)
    cache.delete(f'user_profile:{user_id}')
```

Redis cache is shared across all workers (one copy, not N copies) and has built-in memory limits with eviction policies.

### Three rules for in-memory caches

1. **Always set a max size** — unbounded caches are memory leaks
2. **Always set a TTL** — stale data is a bug source
3. **Always invalidate on write** — or accept eventual consistency with short TTL'''
    ),
    (
        "thinking/debug-silent-data-corruption-float",
        "Our invoicing system occasionally generates invoices with wrong totals. The amounts are off by a cent or two. Example: items totaling $33.30 show as $33.29 on the invoice.\n\n```python\ndef calculate_invoice(items):\n    subtotal = 0.0\n    for item in items:\n        line_total = item['price'] * item['quantity']\n        subtotal += line_total\n    \n    tax = subtotal * 0.08875  # NYC tax rate\n    total = subtotal + tax\n    \n    return {\n        'subtotal': round(subtotal, 2),\n        'tax': round(tax, 2),\n        'total': round(total, 2),\n    }\n```",
        r'''<think>
This is floating-point representation error — one of the most dangerous bugs because it's silent and only shows up on certain values.

Let me demonstrate:

```python
>>> 0.1 + 0.2
0.30000000000000004

>>> 19.99 * 1
19.99

>>> 9.99 + 9.99 + 9.99 + 3.33
33.300000000000004  # Wait, this is MORE than 33.30

>>> 33.300000000000004 * 0.08875
2.955412500000001

>>> 33.300000000000004 + 2.955412500000001
36.255412500000005

>>> round(36.255412500000005, 2)
36.26
```

Hmm, that rounds UP. Let me try a case that rounds down:

```python
>>> 0.1 + 0.2 + 0.3
0.6000000000000001

>>> 0.1 + 0.1 + 0.1
0.30000000000000004

>>> 10.01 + 10.01 + 10.01
30.029999999999998  # LESS than 30.03!
```

There it is. `10.01 + 10.01 + 10.01` = `30.029999999999998` instead of `30.03`. When you round this to 2 decimal places, you get `30.03` (Python rounds to nearest even). But there are cases where the accumulated error pushes the value just below a rounding boundary.

The fundamental issue: `0.01` cannot be represented exactly in IEEE 754 binary floating point. It's stored as `0.01000000000000000020816681711721685228163...`. Each arithmetic operation introduces tiny errors that accumulate.

For money, this is unacceptable. The fix is to use `Decimal` which represents numbers in base 10 (like humans do) and avoids these representation errors.

Actually wait, there's an even subtler issue in this code. Each of these operations introduces a small error:
1. `item['price'] * item['quantity']` — multiplication error
2. `subtotal += line_total` — addition error (accumulates with each item)
3. `subtotal * 0.08875` — multiplication by tax rate (another error)
4. `subtotal + tax` — addition error
5. Three separate `round()` calls can each go different directions

The rounding is also problematic: `round(subtotal, 2) + round(tax, 2)` might not equal `round(total, 2)` because rounding is not distributive over addition.

Example:
```
subtotal = 33.295 → round → 33.30 (rounds up)
tax = 2.955 → round → 2.96 (rounds up)
total = 36.25 → round → 36.25

But 33.30 + 2.96 = 36.26 ≠ 36.25
```

Customer sees subtotal + tax doesn't match total. That's an accounting discrepancy.

The fix: use Decimal for all money calculations, and round consistently (round total, not components).
</think>

**Floating-point representation error.** `0.01` cannot be represented exactly in binary floating point. Errors accumulate across operations.

```python
>>> 10.01 + 10.01 + 10.01
30.029999999999998    # Not 30.03!

>>> 0.1 + 0.2
0.30000000000000004   # Not 0.3!
```

### Additional bug: rounding components separately

```python
round(subtotal, 2) + round(tax, 2) ≠ round(total, 2)
# Customer sees: $33.30 + $2.96 = $36.25 (but those add to $36.26)
```

### Fixed version using Decimal

```python
from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal('0.08875')

def calculate_invoice(items):
    subtotal = Decimal('0')
    for item in items:
        price = Decimal(str(item['price']))  # Convert from float safely
        quantity = Decimal(str(item['quantity']))
        line_total = (price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        subtotal += line_total

    tax = (subtotal * TAX_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total = subtotal + tax  # Exact: Decimal addition is precise

    return {
        'subtotal': str(subtotal),
        'tax': str(tax),
        'total': str(total),  # Always equals subtotal + tax exactly
    }
```

### Why Decimal works

```python
>>> Decimal('10.01') + Decimal('10.01') + Decimal('10.01')
Decimal('30.03')    # Exact!

>>> Decimal('0.1') + Decimal('0.2')
Decimal('0.3')      # Exact!
```

**The rule: never use `float` for money.** Use `Decimal` in Python, `BigDecimal` in Java, integers-as-cents in JavaScript, or `NUMERIC` in PostgreSQL.'''
    ),
    (
        "thinking/debug-encoding-mojibake",
        "Users in Japan report that their names show up as garbled characters like `å±±ç°` instead of `山田`. The data looks fine in the database. The API endpoint:\n\n```python\n@app.get('/api/users/{user_id}')\nasync def get_user(user_id: int):\n    user = await db.get_user(user_id)\n    return Response(\n        content=json.dumps({'name': user.name}),\n        media_type='application/json',\n    )\n```",
        r'''<think>
This is a classic encoding mismatch issue known as "mojibake." The characters `å±±ç°` are what you get when UTF-8 encoded bytes are interpreted as Latin-1 (ISO-8859-1).

Let me verify:
- `山田` in UTF-8 is: `\xe5\xb1\xb1\xe7\x94\xb0` (6 bytes)
- If those 6 bytes are interpreted as Latin-1:
  - `\xe5` = å
  - `\xb1` = ±
  - `\xb1` = ±
  - `\xe7` = ç
  - `\x94` = (non-printable, but in Windows-1252 it's `"`)
  - `\xb0` = °

So `å±±ç°` is exactly `山田` UTF-8 bytes read as Latin-1. ✓

Where does the encoding mismatch happen?

The data flow is: Database → Python → JSON → HTTP Response → Client

1. **Database → Python**: The DB returns the name as a Python string. If the DB connection is configured correctly, this should be proper Unicode. The user says "data looks fine in the database" — so the Python string is correct.

2. **Python → JSON**: `json.dumps({'name': '山田'})` produces `{"name": "\\u5c71\\u7530"}` by default (ASCII-safe with Unicode escapes). Wait — that's the default behavior. If `ensure_ascii=True` (default), non-ASCII characters are escaped as `\uXXXX`. The client would see proper characters after JSON parsing.

But if `ensure_ascii=False`: `json.dumps({'name': '山田'}, ensure_ascii=False)` produces `{"name": "山田"}` — the raw Unicode characters in the JSON string.

3. **JSON → HTTP Response**: The `Response` object takes `content` as a string. FastAPI/Starlette encodes it to bytes. But WHAT encoding?

Here's the bug: `Response(content=json_string, media_type='application/json')`.

The `Response` class encodes the string to bytes using its `charset` attribute. The default charset for `Response` in Starlette is... let me think. Actually, `Response` in Starlette defaults to `charset='utf-8'` for text types. But `media_type='application/json'` — does Starlette add `charset=utf-8` to the Content-Type header?

If the Content-Type header is `application/json` without `charset=utf-8`, the client might assume Latin-1 or the system default encoding.

Actually wait — the JSON spec (RFC 8259) says JSON MUST be encoded in UTF-8. Clients should always assume UTF-8 for `application/json`. So the client should decode correctly.

Let me reconsider. If `json.dumps` with `ensure_ascii=True` (default), all non-ASCII chars are `\uXXXX` escaped — no encoding issue possible. The client parses `\u5c71\u7530` as `山田` correctly.

So the bug only manifests if `ensure_ascii=False` AND the encoding is wrong somewhere. OR if there's a middleware/proxy that re-encodes the response.

Actually, the most common cause of this specific mojibake pattern is: the client receives UTF-8 bytes but interprets them as Latin-1. This usually happens due to:
1. Missing or wrong `Content-Type` charset
2. A reverse proxy (nginx) adding wrong charset
3. The client's default encoding is Latin-1

Let me look at the code again. `Response(content=..., media_type='application/json')`. In Starlette, this creates a response with `Content-Type: application/json` — without specifying `charset=utf-8`. Some clients (older browsers, certain HTTP libraries) default to Latin-1 when no charset is specified.

The fix: explicitly set charset, or use FastAPI's `JSONResponse` which handles this correctly.

Actually, the simplest fix is to use `JSONResponse` instead of manually creating a `Response` with `json.dumps`:

```python
return JSONResponse({'name': user.name})
```

`JSONResponse` handles encoding, content-type, and charset correctly. The manual approach with `Response` + `json.dumps` is error-prone.
</think>

**Encoding mismatch: UTF-8 bytes interpreted as Latin-1.** The characters `å±±ç°` are exactly what `山田` (UTF-8: `\xe5\xb1\xb1\xe7\x94\xb0`) looks like when decoded as Latin-1.

### The cause

`Response(content=json_string, media_type='application/json')` produces a `Content-Type: application/json` header **without** `charset=utf-8`. Some clients default to Latin-1 when no charset is specified, causing the mojibake.

### Fix: use JSONResponse

```python
from fastapi.responses import JSONResponse

@app.get('/api/users/{user_id}')
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    return JSONResponse({'name': user.name})
    # Sets: Content-Type: application/json; charset=utf-8
    # Handles json.dumps + encoding automatically
```

Or even simpler — FastAPI does this by default when you return a dict:

```python
@app.get('/api/users/{user_id}')
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    return {'name': user.name}  # FastAPI auto-converts to JSONResponse
```

### If you must use Response manually

```python
return Response(
    content=json.dumps({'name': user.name}, ensure_ascii=False).encode('utf-8'),
    media_type='application/json; charset=utf-8',  # Explicit charset
)
```

### Encoding debugging cheat sheet

| Mojibake pattern | What happened |
|-----------------|---------------|
| `å±±ç°` for `山田` | UTF-8 decoded as Latin-1 |
| `山田` for `山田` | UTF-8 decoded as UTF-8 ✓ |
| `???` for `山田` | UTF-8 decoded as ASCII (chars dropped) |
| `ÃÃÃ` for `ééé` | UTF-8 decoded as Latin-1 |
| `\u5c71\u7530` visible | JSON Unicode escapes not parsed |'''
    ),
    (
        "thinking/debug-async-ordering",
        "We send a welcome email, then a verification email after user signup. But sometimes users receive the verification email BEFORE the welcome email:\n\n```python\nasync def signup(user_data):\n    user = await create_user(user_data)\n    \n    # Send welcome email\n    asyncio.create_task(send_email(\n        to=user.email,\n        template='welcome',\n        data={'name': user.name}\n    ))\n    \n    # Send verification email\n    asyncio.create_task(send_email(\n        to=user.email,\n        template='verification',\n        data={'link': generate_verification_link(user.id)}\n    ))\n    \n    return user\n```",
        r'''<think>
`asyncio.create_task()` schedules a coroutine to run concurrently — it does NOT wait for it to complete. Both `send_email` calls are fired off as background tasks that run independently.

The execution order:
1. `create_user` completes (awaited)
2. `create_task(send_email(welcome))` — schedules task, returns immediately
3. `create_task(send_email(verification))` — schedules task, returns immediately
4. Function returns `user`

Now both tasks run concurrently. Which finishes first? It depends on:
- Network latency to the email service
- Email service processing time
- Which request gets picked up first by the server

There's no guarantee the welcome email is sent before the verification email. In fact, if the welcome email template is larger (has images, formatting), it might consistently take longer to send, making the verification email arrive first.

**Fix options:**

1. **Await sequentially**:
   ```python
   await send_email(welcome)
   await send_email(verification)
   ```
   But this makes signup slower — user waits for both emails to send.

2. **Single task with ordering**:
   ```python
   async def send_signup_emails(user):
       await send_email(welcome)
       await send_email(verification)
   asyncio.create_task(send_signup_emails(user))
   ```
   Background task, but emails are sent in order.

3. **Message queue with ordering**:
   Send both to a queue with sequence numbers. The email worker processes them in order.

4. **Single combined email**:
   Just put the verification link IN the welcome email. One email, no ordering problem.

Option 4 is actually the best UX — users don't want two emails within seconds of signup. But if they must be separate, option 2 is the simplest correct fix.

There's another subtle issue: `create_task` without `await` means if the `signup` function's caller doesn't keep the event loop running, the tasks might get garbage collected before completion. In a web framework like FastAPI this is usually fine (the server keeps the loop running), but in a script it would be a problem.
</think>

`asyncio.create_task()` fires both emails as **concurrent background tasks** with no ordering guarantee. Whichever email service call completes first gets delivered first.

```
create_task(welcome)        → starts sending (background)
create_task(verification)   → starts sending (background)
return user                 → both tasks racing in parallel
```

### Fix: ordered background task

```python
async def signup(user_data):
    user = await create_user(user_data)

    # Single background task that sends emails in order
    asyncio.create_task(send_signup_emails(user))

    return user

async def send_signup_emails(user):
    """Background task — emails sent sequentially, in guaranteed order."""
    await send_email(
        to=user.email,
        template='welcome',
        data={'name': user.name}
    )
    await send_email(
        to=user.email,
        template='verification',
        data={'link': generate_verification_link(user.id)}
    )
```

### Better fix: combine into one email

Two emails within seconds of signup is bad UX. Put the verification link in the welcome email:

```python
async def signup(user_data):
    user = await create_user(user_data)
    asyncio.create_task(send_email(
        to=user.email,
        template='welcome_with_verification',
        data={
            'name': user.name,
            'verification_link': generate_verification_link(user.id),
        }
    ))
    return user
```

### `create_task` vs `await` cheat sheet

| Pattern | Behavior | Use when |
|---------|----------|----------|
| `await send_email()` | Blocks until done | Result needed before continuing |
| `create_task(send_email())` | Fire and forget | Don't need result, don't care about order |
| `await asyncio.gather(a(), b())` | Parallel, wait for all | Need all results, order doesn't matter |
| `create_task` inside sequential wrapper | Background, ordered | Don't block caller, but maintain order |'''
    ),
    (
        "thinking/debug-orm-lazy-loading",
        "This Django view takes 15 seconds to load. It lists 100 blog posts with their authors and tags:\n\n```python\ndef blog_list(request):\n    posts = Post.objects.filter(published=True).order_by('-created_at')[:100]\n    data = []\n    for post in posts:\n        data.append({\n            'title': post.title,\n            'author': post.author.username,\n            'author_avatar': post.author.profile.avatar_url,\n            'tags': [tag.name for tag in post.tags.all()],\n            'comment_count': post.comments.count(),\n        })\n    return JsonResponse({'posts': data})\n```",
        r'''<think>
Let me count the database queries.

Query 1: `Post.objects.filter(published=True).order_by('-created_at')[:100]`
This fetches 100 posts. 1 query.

For each of the 100 posts:
- `post.author.username` — lazy loads the author (ForeignKey). 1 query per post.
- `post.author.profile.avatar_url` — lazy loads the profile (OneToOneField from author). This might be covered by the author query if profile is on the User model, but if Profile is a separate model, it's another query per post.
- `post.tags.all()` — lazy loads all tags (ManyToMany). 1 query per post.
- `post.comments.count()` — COUNT query on comments. 1 query per post.

Total: 1 + 100×(1 + 1 + 1 + 1) = 1 + 400 = 401 queries

At ~5-10ms per query (including network to DB): 401 × 7.5ms = ~3 seconds. But the user says 15 seconds, which suggests either the DB is slow, or there's even more queries (maybe profile loading triggers additional queries).

Actually, let me re-examine `post.author.profile.avatar_url`:
1. `post.author` — loads User object (1 query)
2. `.profile` — loads Profile object related to User (1 query)
So that's 2 queries per post just for the author+profile chain.

Revised: 1 + 100×(1 + 1 + 1 + 1) = 501 queries. Wait no:
- `post.author` is accessed twice (for .username and .profile), but Django caches the FK lookup, so it's still 1 query for author.
- But `.profile` is a separate access: 1 query.

So per post: author(1) + profile(1) + tags(1) + comment_count(1) = 4 queries.
Total: 1 + 100×4 = 401 queries. At 15 seconds, that's ~37ms per query — slow but plausible with a remote DB.

**Fix strategy:**

1. `select_related('author', 'author__profile')` — JOIN to load author and profile in the initial query. Converts 200 queries → 0.

2. `prefetch_related('tags')` — second query loads ALL tags for all 100 posts. Converts 100 queries → 1.

3. `.annotate(comment_count=Count('comments'))` — compute count in the initial query with GROUP BY. Converts 100 queries → 0.

After optimization: 1 main query (with JOINs and annotation) + 1 prefetch query = 2 queries total.

From 401 queries to 2 queries. That's a ~200x reduction.
</think>

**N+1 query problem × 4.** Each of the 100 posts triggers 4 extra queries:

```
1 query:   Fetch 100 posts
100 queries: Load author for each post (FK lazy load)
100 queries: Load author.profile for each (OneToOne lazy load)
100 queries: Load tags for each (M2M lazy load)
100 queries: COUNT comments for each
─────────────
401 queries total → 15 seconds
```

### Fixed version (2 queries instead of 401)

```python
from django.db.models import Count

def blog_list(request):
    posts = (
        Post.objects
        .filter(published=True)
        .select_related('author', 'author__profile')  # JOIN: 0 extra queries
        .prefetch_related('tags')                       # 1 batch query for all tags
        .annotate(comment_count=Count('comments'))      # COUNT in main query
        .order_by('-created_at')
        [:100]
    )

    data = [
        {
            'title': post.title,
            'author': post.author.username,           # Already loaded (JOIN)
            'author_avatar': post.author.profile.avatar_url,  # Already loaded (JOIN)
            'tags': [tag.name for tag in post.tags.all()],     # Already loaded (prefetch)
            'comment_count': post.comment_count,               # Already loaded (annotate)
        }
        for post in posts
    ]
    return JsonResponse({'posts': data})
```

### Result

```
Before: 401 queries, ~15 seconds
After:  2 queries, ~50ms
```

### When to use which

| Django tool | Use for | How it works |
|-------------|---------|-------------|
| `select_related()` | ForeignKey, OneToOne | SQL JOIN in main query |
| `prefetch_related()` | ManyToMany, reverse FK | Separate query, joined in Python |
| `.annotate(Count(...))` | Aggregates per row | SQL GROUP BY in main query |
| `.only('field1', 'field2')` | Reducing columns | SELECT only listed fields |'''
    ),
]
