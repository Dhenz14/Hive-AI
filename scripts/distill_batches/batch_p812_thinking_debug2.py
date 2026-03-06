"""Phase 1X: Foundation Thinking — Systematic Debugging (Part 2)

Five training pairs on systematic debugging: regex bugs, serialization bugs,
import/dependency cycles, signal handling, and type coercion bugs.
"""

PAIRS = [
    (
        "thinking/debug-regex",
        r'''Our URL validation rejects valid URLs and accepts invalid ones. Find the bugs:

import re

URL_PATTERN = re.compile(
    r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]*)?$'
)

def is_valid_url(url: str) -> bool:
    """Returns True if url is a valid HTTP/HTTPS URL."""
    return bool(URL_PATTERN.match(url))

# These should all pass but some fail:
assert is_valid_url("https://example.com")           # OK
assert is_valid_url("https://example.com/path")      # OK
assert is_valid_url("https://sub.example.co.uk")     # OK
assert is_valid_url("https://example.com/path?q=1&b=2")  # FAILS
assert is_valid_url("https://example.com/path%20here")    # FAILS
assert not is_valid_url("https://example..com")           # SHOULD FAIL but passes
assert not is_valid_url("https://.example.com")           # SHOULD FAIL but passes''',
        r'''<think>
Let me trace through each failing assertion to find the regex bugs.

First, let me look at the character class in the path portion:
`[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]`

Assertion 4: `https://example.com/path?q=1&b=2`
The path part is `/path?q=1&b=2`. Let me check each character:
- `/path?q=1` -- all in the character class
- `&` -- is `&` in the class? Yes, `&` is there
- `b=2` -- all valid

Wait, let me look more carefully at the character class. The issue might be with unescaped special characters inside the class.

Inside `[...]`:
- `*` is literal inside a character class -- OK
- `+` is literal inside a character class -- OK
- But `)` and `(` are literal inside a character class -- OK
- `\[` and `\]` -- escaped brackets, OK

Hmm, actually let me look at the `%` character. Assertion 5 fails on `path%20here`. The `%` character is NOT in the character class! That's bug #1 -- percent-encoded characters like `%20` are valid in URLs but `%` isn't in the allowed characters.

Now for assertion 4 -- `?q=1&b=2`. Let me recheck... `?` IS in the class, `=` IS in the class, `&` IS in the class, digits are in the class. This should match. Wait, let me look at the `-` placement in the character class.

The class ends with `...;=-]`. The `-` between `=` and `]` is being treated as a literal because it's at the end. But wait, is `=` actually in the class? Let me look: `$&\'()*+,;=-`. So we have `;`, `=`, `-`. The `-` between `=` and `]` -- actually this creates a range `=-]` which is `=`, `>`, `?`, `@`, ... up to `]`. Wait no, `]` closes the class. So it's the range `=` to nothing?

Actually, let me re-examine. The full character class string is:
`[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]`

The `\]` is an escaped `]` so it doesn't close the class. Then we have `@!$&\'()*+,;=-]`. The `-` here is between `=` and `]`. Since `]` closes the class, the `-` is at the end and is literal. So `=` and `-` are both included.

Hmm, let me look at this differently. What if the regex is actually matching fine but there's an issue with the `'` in the raw string? The pattern has `\'` -- in a raw string, that's a literal backslash followed by a single quote. In the regex, `\'` inside a character class is just a literal quote. That should be fine.

Wait, actually, let me re-examine assertion 4 more carefully. The URL is `https://example.com/path?q=1&b=2`. The regex path section is:
`(/[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]*)?`

So it matches `/` followed by zero or more characters from the class. The path after the first `/` is `path?q=1&b=2`. All these characters should be in the class. Let me check each: p-a-t-h-?-q-=-1-&-b-=-2. Yes, all are in the class.

Actually, I wonder if I'm wrong about the assertion failing. Let me re-read the user's claim... they say assertion 4 "FAILS". Let me look at this from a different angle.

Oh! I see it now. The `?` in the regex character class -- is `?` actually in there? The class contains `/?#` -- yes, `?` is there. And `q`, `=`, `1`, `&`, `b`, `2` are all alphanumeric or in the class.

Hmm wait. Let me look at the regex more carefully. The issue might be with `$` in the character class. `$` is a special regex character outside a character class, but inside `[...]` it's literal. That's fine.

Actually, I think I need to look at the actual regex compilation. The pattern uses a raw string `r'^...'`. Let me look at the `\[` and `\]` -- in a raw string, these are `\[` and `\]`, which in regex match literal `[` and `]`. But wait -- `\]` inside a character class could be interpreted as escaping the closing bracket... Let me think about this.

`[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]`

Python's `re` engine processes `\[` as literal `[`, then `\]` as literal `]`. So the character class contains literal `[` and `]`. Then it continues with `@!$&...`. The character class is properly terminated by the final `]`. This should work.

Let me reconsider. Maybe the issue is that `*` inside the character class is literal, but in the context of the full regex, maybe there's a parsing issue? No, `*` is always literal inside `[...]`.

Actually, I think I may have been overthinking this. Let me focus on what's definitively wrong:

1. `%` is not in the character class -- percent-encoded URLs fail. Bug confirmed.

2. For the double-dot domain `example..com` and leading-dot `.example.com`: the domain pattern is `[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`. This allows:
   - `example..com` -- the `[a-zA-Z0-9.-]+` matches `example.`, then `\.` matches the second `.`, then `[a-zA-Z]{2,}` matches `com`. Yes, this passes.
   - `.example.com` -- `[a-zA-Z0-9.-]+` matches `.example`, then `\.` matches `.`, then `com` matches. Yes, this passes too.

   Bug: the domain regex doesn't prevent consecutive dots or leading dots.

3. For assertion 4 (`?q=1&b=2`), let me try once more. I'll carefully check if `&` is being treated as literal inside the character class. In Python regex, `&` has no special meaning anywhere, so inside `[...]` it's just literal `&`. So this should match...

Unless the issue is something else entirely. Let me look at `\'` in the raw string context. In a raw string `r'...'`, the sequence `\'` is literally backslash + single quote. But we're inside `r'...'` delimited by single quotes. Actually, `r'...\'..'` -- does `\'` terminate the raw string? In Python, raw strings still treat `\'` as not ending the string (the backslash still escapes the quote for string delimiter purposes, but the backslash IS included in the string). So the raw string contains a literal `\` before the `'`.

But wait, the regex pattern is inside `re.compile(r'^...$')`. Let me look at the actual line:
```
r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[a-zA-Z0-9._~:/?#\[\]@!$&\'()*+,;=-]*)?$'
```

In a raw string delimited by `'`, the `\'` does NOT end the string -- Python keeps the backslash. So the regex engine sees `\[\]@!$&\'()*+,;=-` which in the character class means: `\[` = literal `[`, `\]` = literal `]`, `@`, `!`, `$`, `&`, `\'` = literal `'`, `(`, `)`, `*`, `+`, `,`, `;`, `=`, `-`.

So the character class is valid and contains all those characters. The `?q=1&b=2` should match...

I wonder if the issue is with how the raw string is actually parsed. `r'...\'..'` -- actually in Python, `r'\''` is NOT valid. A raw string can't end with an odd number of backslashes. So `r'...\'...'` -- the `\'` doesn't end the string, and then the next `'` after `)*+,;=-]` would end it. Wait but then `)?$'` -- is that the end? Let me count the quotes...

The string starts with `r'` and the content has `\'` in the middle. Actually, I think this raw string IS valid in Python -- `\'` inside a raw string makes the `'` not terminate the string, and the `\` IS included in the string value. So the string ends at the `$'` at the very end.

OK I think assertion 4 should actually pass with this regex. Let me reconsider -- maybe the user's claim about which assertions fail is slightly imprecise, and the key bugs are:

1. Missing `%` in character class (assertion 5 definitely fails)
2. Domain allows `..` and leading `.` (assertions 6 and 7 pass when they shouldn't)
3. The regex doesn't properly validate URL structure (query string, fragment, etc. are all mixed into one character class)

Let me provide these as the bugs.
</think>

There are three bugs in this regex:

**Bug 1: Missing `%` in the path character class.**
Percent-encoded sequences like `%20` are valid in URLs, but `%` is not in the allowed character set. This is why assertion 5 fails.

**Bug 2: Domain pattern allows invalid hostnames.**
`[a-zA-Z0-9.-]+` permits consecutive dots (`example..com`) and leading dots (`.example.com`). This is why assertions 6 and 7 don't fail as expected.

**Bug 3: Monolithic path regex is too fragile.**
Stuffing all valid URL characters into one character class makes the regex hard to maintain and easy to miss characters like `%`.

```python
import re

# Fix: proper domain validation + percent-encoding support
URL_PATTERN = re.compile(
    r'^https?://'
    r'(?!-)'                          # no leading hyphen
    r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*'  # subdomains
    r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'         # second-level
    r'\.[a-zA-Z]{2,}'                 # TLD
    r'(?::\d{1,5})?'                  # optional port
    r'(?:/[a-zA-Z0-9._~:/?#@!$&\'()*+,;=%\[\]-]*)?'  # path/query/fragment with %
    r'$'
)

def is_valid_url(url: str) -> bool:
    return bool(URL_PATTERN.match(url))
```

**Key fixes:**
- Added `%` to the path character class for percent-encoding
- Domain segments must start/end with alphanumeric (no leading dots)
- Each segment is 1-63 characters with hyphens only in the middle
- Consecutive dots are structurally impossible with the new pattern'''
    ),
    (
        "thinking/debug-serialization",
        r'''We serialize objects to JSON, store them, and deserialize later. Some objects round-trip incorrectly. Find the bugs:

import json
from datetime import datetime, date
from enum import Enum

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class Task:
    def __init__(self, title, due_date, priority, tags, metadata=None):
        self.title = title
        self.due_date = due_date      # datetime or date
        self.priority = priority      # Priority enum
        self.tags = tags              # set of strings
        self.metadata = metadata      # dict, may contain tuples as keys

    def to_dict(self):
        return {
            "title": self.title,
            "due_date": str(self.due_date),
            "priority": self.priority.value,
            "tags": list(self.tags),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            title=d["title"],
            due_date=datetime.fromisoformat(d["due_date"]),
            priority=Priority(d["priority"]),
            tags=set(d["tags"]),
            metadata=d.get("metadata"),
        )

# Usage
task = Task("Deploy", datetime(2025, 3, 15, 14, 30), Priority.HIGH,
            {"urgent", "prod"}, {(1, 2): "coord"})
blob = json.dumps(task.to_dict())
restored = Task.from_dict(json.loads(blob))''',
        r'''<think>
Let me trace through the serialization round-trip step by step.

1. **`due_date`**: `str(datetime(2025, 3, 15, 14, 30))` produces `"2025-03-15 14:30:00"`. Then `datetime.fromisoformat("2025-03-15 14:30:00")` -- this actually works in Python 3.7+ because `fromisoformat` accepts the space separator. BUT if `due_date` is a `date` object (not datetime), `str(date(2025, 3, 15))` gives `"2025-03-15"`, and `datetime.fromisoformat("2025-03-15")` returns a datetime at midnight in Python 3.11+, but raises ValueError in Python 3.7-3.10. So there's a version-dependent bug if `due_date` is a `date`.

   Also, `str()` on datetime doesn't produce strict ISO format -- it uses a space instead of `T`. And if there are microseconds, the format changes. This is fragile.

2. **`tags`**: `set` -> `list(self.tags)` -> JSON array -> `set(d["tags"])`. This actually round-trips correctly for strings. BUT the ordering of set->list is non-deterministic, which means the JSON output isn't stable (bad for hashing/comparison, though it doesn't break correctness).

3. **`metadata`**: The metadata dict has tuple keys `{(1, 2): "coord"}`. JSON only supports string keys. `json.dumps({(1, 2): "coord"})` will raise `TypeError: keys must be str, int, float, bool or None`. So this crashes on serialization!

4. **`priority`**: `Priority.HIGH.value` = 3 (int). After JSON round-trip, `d["priority"]` is still 3 (int). `Priority(3)` gives `Priority.HIGH`. This works correctly.

5. **`due_date` type loss**: Even if we fix the `str()` issue, `from_dict` always creates a `datetime`, even if the original was a `date`. The type information is lost.

So the bugs are:
1. `metadata` with tuple keys crashes `json.dumps` -- TypeError
2. `str(due_date)` is not proper ISO format and loses type info (date vs datetime)
3. Even if metadata had string keys, nested types (like tuples in values) would become lists after JSON round-trip

Let me provide a robust fix.
</think>

Three bugs that break the round-trip:

**Bug 1 (crash): `metadata` with tuple keys.**
`json.dumps({(1, 2): "coord"})` raises `TypeError` because JSON only allows string keys. This isn't a silent corruption -- it crashes.

**Bug 2 (data loss): `str(due_date)` is fragile.**
`str(datetime(...))` uses a space separator (`2025-03-15 14:30:00`), not ISO `T` format. Worse, if `due_date` is a `date` object, `from_dict` always reconstructs it as `datetime` -- type information is lost.

**Bug 3 (silent corruption): `set` ordering is non-deterministic.**
`list(self.tags)` produces different JSON each time, breaking content hashing, caching, and diff comparisons.

```python
import json
from datetime import datetime, date
from enum import Enum

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class Task:
    def __init__(self, title, due_date, priority, tags, metadata=None):
        self.title = title
        self.due_date = due_date
        self.priority = priority
        self.tags = tags
        self.metadata = metadata

    def to_dict(self):
        return {
            "title": self.title,
            "due_date": self.due_date.isoformat(),  # proper ISO format
            "due_date_type": type(self.due_date).__name__,  # preserve type
            "priority": self.priority.name,  # use name, not value (more stable)
            "tags": sorted(self.tags),  # deterministic ordering
            "metadata": self._serialize_metadata(self.metadata),
        }

    @staticmethod
    def _serialize_metadata(meta):
        if meta is None:
            return None
        # Convert tuple keys to string representation
        return {repr(k) if isinstance(k, tuple) else k: v
                for k, v in meta.items()}

    @staticmethod
    def _deserialize_metadata(meta):
        if meta is None:
            return None
        import ast
        result = {}
        for k, v in meta.items():
            try:
                parsed = ast.literal_eval(k)
                result[parsed] = v
            except (ValueError, SyntaxError):
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, d):
        date_str = d["due_date"]
        if d.get("due_date_type") == "date":
            due = date.fromisoformat(date_str)
        else:
            due = datetime.fromisoformat(date_str)

        return cls(
            title=d["title"],
            due_date=due,
            priority=Priority[d["priority"]],  # by name, not value
            tags=set(d["tags"]),
            metadata=cls._deserialize_metadata(d.get("metadata")),
        )
```

**Key fixes:**
- `.isoformat()` instead of `str()` for stable, standard date formatting
- Store `due_date_type` to correctly restore `date` vs `datetime`
- Serialize tuple keys as `repr()` strings, deserialize with `ast.literal_eval`
- `sorted(self.tags)` for deterministic JSON output
- Use enum `name` instead of `value` for resilience against reordering'''
    ),
    (
        "thinking/debug-import-cycle",
        r'''Our Flask app crashes on startup with ImportError. The traceback shows a circular import but we can't figure out how to fix it without breaking the architecture:

# app/models/user.py
from app.services.auth import hash_password

class User:
    def __init__(self, username, raw_password):
        self.username = username
        self.password_hash = hash_password(raw_password)

    def check_password(self, raw_password):
        from app.services.auth import verify_password
        return verify_password(raw_password, self.password_hash)

# app/services/auth.py
from app.models.user import User
from app.db import session
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(raw: str, hashed: str) -> bool:
    return hash_password(raw) == hashed

def get_current_user(user_id: int) -> User:
    return session.query(User).filter_by(id=user_id).first()

def create_user(username: str, password: str) -> User:
    user = User(username, password)
    session.add(user)
    session.commit()
    return user

# app/routes/api.py
from app.services.auth import get_current_user, create_user

The app crashes with: ImportError: cannot import name 'User' from partially initialized module 'app.models.user' ''',
        r'''<think>
Let me trace the import chain:

1. Something imports `app.routes.api`
2. `app.routes.api` imports from `app.services.auth`
3. `app.services.auth` imports `User` from `app.models.user` (top-level)
4. `app.models.user` imports `hash_password` from `app.services.auth` (top-level)
5. But `app.services.auth` is still being initialized (step 3 hasn't finished), so `hash_password` isn't defined yet
6. ImportError!

The cycle is: `auth` -> `user` -> `auth`

The existing code already has one deferred import: `check_password` does `from app.services.auth import verify_password` inside the method. But the top-level `from app.services.auth import hash_password` still creates the cycle.

Solutions:
1. **Move `hash_password` to a utility module** -- break the cycle by extracting the pure function.
2. **Defer the import in `User.__init__`** -- import `hash_password` inside the method, not at the top.
3. **Dependency inversion** -- `User` shouldn't know about `auth`. Instead, the caller should hash the password before passing it to `User`.

Option 3 is the best architecture. The `User` model should be a pure data model. Password hashing is a service concern, not a model concern. The model should just store the hash, not compute it.

The issue is that `User.__init__` calls `hash_password` directly. This violates separation of concerns AND creates the import cycle.

Also worth noting: using plain SHA-256 for password hashing is a serious security flaw (should use bcrypt/argon2), but that's a separate issue.

Let me restructure:
- `User` becomes a pure data class that stores a pre-hashed password
- `auth.py` handles all password hashing logic
- The cycle is broken because `user.py` no longer imports from `auth.py`
</think>

The import cycle is: `auth.py` imports `User` from `user.py`, and `user.py` imports `hash_password` from `auth.py`. Python can't resolve this because both modules need each other at import time.

**Root cause: wrong responsibility placement.** `User.__init__` calls `hash_password`, making the model depend on the service. Models should be pure data; hashing is a service concern.

```python
# app/models/user.py  -- NO imports from services
class User:
    def __init__(self, username, password_hash):
        self.username = username
        self.password_hash = password_hash  # already hashed

# app/services/auth.py  -- owns all password logic
from app.models.user import User  # one-way dependency, no cycle
from app.db import session
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(raw: str, hashed: str) -> bool:
    return hash_password(raw) == hashed

def get_current_user(user_id: int) -> User:
    return session.query(User).filter_by(id=user_id).first()

def create_user(username: str, password: str) -> User:
    hashed = hash_password(password)     # hash BEFORE creating User
    user = User(username, hashed)
    session.add(user)
    session.commit()
    return user

def check_user_password(user: User, raw_password: str) -> bool:
    return verify_password(raw_password, user.password_hash)
```

**Why this fixes it:**
- `user.py` has zero imports from `services` -- the cycle is broken
- `auth.py` imports from `user.py` (one-way dependency)
- `User` is a pure data model: it stores a hash, doesn't compute one
- Password logic is consolidated in `auth.py` where it belongs
- The deferred import hack in `check_password` is eliminated

**General rule for breaking import cycles:**
Models should never import from services. The dependency arrow is always: routes -> services -> models. If a model needs service logic, the architecture is wrong -- move that logic to the service layer.'''
    ),
    (
        "thinking/debug-signal-handling",
        r'''Our long-running data processor sometimes leaves temp files and half-written outputs when killed. The signal handling code doesn't seem to work:

import signal
import sys
import os
import tempfile
import time

class DataProcessor:
    def __init__(self, output_path):
        self.output_path = output_path
        self.temp_file = None
        self.running = True
        self._setup_signals()

    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        print(f"Received signal {signum}, shutting down...")
        self.running = False

    def process(self, data_chunks):
        self.temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.tmp', delete=False
        )
        try:
            for i, chunk in enumerate(data_chunks):
                if not self.running:
                    break
                result = self._expensive_computation(chunk)
                self.temp_file.write(result + '\n')
                if i % 100 == 0:
                    self.temp_file.flush()

            if self.running:
                self.temp_file.close()
                os.rename(self.temp_file.name, self.output_path)
            else:
                self.temp_file.close()
                os.unlink(self.temp_file.name)
        except Exception as e:
            print(f"Error: {e}")

    def _expensive_computation(self, chunk):
        time.sleep(0.1)  # simulate work
        return f"processed:{chunk}"

if __name__ == "__main__":
    proc = DataProcessor("/tmp/output.dat")
    proc.process(range(10000))''',
        r'''<think>
Let me trace through the signal handling flow to find the bugs.

1. **Signal handler sets `self.running = False`** -- the main loop checks `self.running` and breaks. This part seems correct for graceful shutdown.

2. **Bug 1: Exception handler doesn't clean up temp file.**
If an exception occurs (e.g., disk full, permission error), the `except` block prints the error but doesn't close or delete the temp file. The `self.temp_file` remains on disk.

3. **Bug 2: `os.rename` can fail across filesystems.**
`tempfile.NamedTemporaryFile` creates files in the system temp directory (e.g., `/tmp`), but `output_path` could be on a different filesystem. `os.rename` doesn't work across filesystem boundaries -- it raises `OSError`. Should use `shutil.move`.

Actually wait, the output_path in the example is `/tmp/output.dat` and temp files are also in `/tmp`, so this might work in the example. But it's a latent bug.

4. **Bug 3: Signal during `os.rename` or `os.unlink`.**
If a signal arrives during the `os.rename` or between `self.temp_file.close()` and `os.rename`, the handler sets `self.running = False`, but we've already exited the loop. The rename may or may not complete.

Actually, in Python, signal handlers are only invoked between bytecode instructions. `os.rename` is a single C call, so the signal handler won't interrupt it. But the signal could arrive between `close()` and `rename()`, which isn't handled.

5. **Bug 4 (the big one): Signal during `_expensive_computation` or `time.sleep`.**
`time.sleep(0.1)` is interruptible by signals. When a signal arrives during `sleep`, the signal handler runs (setting `self.running = False`), and then `sleep` raises... actually no, in Python 3, `time.sleep` doesn't raise on signal -- the handler runs and then sleep resumes for the remaining time. Wait, actually, in Python 3.5+, `time.sleep` uses `clock_nanosleep` and restarts automatically. But the signal handler DOES run.

So after the signal handler sets `self.running = False`, the current `sleep` finishes, `_expensive_computation` returns, `write` happens for the current chunk, and THEN the loop checks `self.running` and breaks. That's correct behavior -- process current chunk, then stop.

6. **Bug 5 (the actual big one): The exception handler catches EVERYTHING including KeyboardInterrupt.**
Wait, no -- `KeyboardInterrupt` is not a subclass of `Exception` in Python. So Ctrl+C generates SIGINT, the handler sets `self.running = False`, and the loop exits normally. If Ctrl+C arrives when there's no signal handler... but we registered one.

Actually, the signal handler replaces the default SIGINT handler. The default SIGINT handler raises `KeyboardInterrupt`. Our handler just sets a flag. So `KeyboardInterrupt` is never raised. That's fine for graceful shutdown.

7. **Bug 6: The `except Exception` swallows errors and leaves temp files.**
```python
except Exception as e:
    print(f"Error: {e}")
```
If ANY exception occurs (like `os.rename` failing), the temp file is never cleaned up. There's no `finally` block.

8. **Bug 7: `self.temp_file` is set before try block.**
If `NamedTemporaryFile` succeeds but then something fails, the file handle might leak.

Let me also consider: what if the process receives SIGKILL (kill -9)? Signal handlers can't catch SIGKILL. The temp file will be left behind. The only fix for SIGKILL is to clean up stale temp files on startup, or use a temp directory that's cleaned by the OS.

Key bugs summary:
1. No `finally` block -- temp files leak on exceptions
2. `os.rename` fails across filesystems (latent bug)
3. Cross-filesystem rename failure is silently caught by `except Exception`
4. No cleanup of temp files on unhandled errors
5. Second signal (e.g., user presses Ctrl+C again) during cleanup could be problematic

Let me write the fix.
</think>

Several bugs that conspire to leave temp files behind:

**Bug 1: No `finally` block.** If any exception occurs (disk full, permission error, cross-filesystem rename failure), the `except` block just prints the error. The temp file is never cleaned up.

**Bug 2: `os.rename` fails across filesystems.** `NamedTemporaryFile` creates files in the system temp dir, but `output_path` could be on a different mount. `os.rename` raises `OSError` across filesystem boundaries, which is silently caught by `except Exception`.

**Bug 3: Double signal isn't handled.** If the user sends SIGINT twice (impatient Ctrl+C), the second signal arrives during cleanup code. The handler just sets `self.running = False` again (no-op), but if cleanup is slow, the user might escalate to SIGKILL.

**Bug 4: Temp file leaks if `write()` or `flush()` raises.** A disk-full error during `write()` jumps to `except`, which doesn't close or remove the temp file.

```python
import signal
import sys
import os
import shutil
import tempfile
import time

class DataProcessor:
    def __init__(self, output_path):
        self.output_path = output_path
        self.temp_file = None
        self.running = True
        self._setup_signals()

    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        print(f"\nReceived signal {signum}, finishing current chunk...")
        self.running = False
        # On second signal, exit immediately
        signal.signal(signum, signal.SIG_DFL)

    def process(self, data_chunks):
        # Create temp file next to output to avoid cross-filesystem rename
        output_dir = os.path.dirname(self.output_path) or '.'
        fd, temp_path = tempfile.mkstemp(
            suffix='.tmp', dir=output_dir
        )
        self.temp_file = os.fdopen(fd, 'w')
        completed = False
        try:
            for i, chunk in enumerate(data_chunks):
                if not self.running:
                    break
                result = self._expensive_computation(chunk)
                self.temp_file.write(result + '\n')
                if i % 100 == 0:
                    self.temp_file.flush()

            if self.running:
                self.temp_file.flush()
                os.fsync(self.temp_file.fileno())  # ensure data hits disk
                self.temp_file.close()
                self.temp_file = None
                os.rename(temp_path, self.output_path)  # atomic, same FS
                completed = True
        finally:
            # Always clean up, no matter what happened
            if self.temp_file is not None:
                self.temp_file.close()
            if not completed and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _expensive_computation(self, chunk):
        time.sleep(0.1)
        return f"processed:{chunk}"
```

**Key fixes:**
- `finally` block guarantees temp file cleanup on any exit path
- Temp file created in same directory as output (no cross-FS rename)
- `os.fsync` before rename ensures data durability
- Second signal restores default handler (immediate kill on Ctrl+C+C)
- `completed` flag tracks whether rename succeeded'''
    ),
    (
        "thinking/debug-type-coercion",
        r'''Our API validation passes bad data through. Users can submit negative prices and string quantities. Find the type coercion bugs:

from typing import Optional

class OrderValidator:
    VALID_STATUSES = {"pending", "confirmed", "shipped"}

    def validate_order(self, data: dict) -> tuple[bool, list[str]]:
        errors = []

        # Validate quantity
        qty = data.get("quantity", 0)
        if qty <= 0:
            errors.append("Quantity must be positive")

        # Validate price
        price = data.get("price")
        if price is not None and price < 0:
            errors.append("Price cannot be negative")

        # Validate discount percentage
        discount = data.get("discount", 0)
        if discount < 0 or discount > 100:
            errors.append("Discount must be 0-100")

        # Validate status
        status = data.get("status", "pending")
        if status not in self.VALID_STATUSES:
            errors.append(f"Invalid status: {status}")

        # Validate email
        email = data.get("email", "")
        if email and "@" not in email:
            errors.append("Invalid email")

        return (len(errors) == 0, errors)

# These all pass validation but shouldn't:
v = OrderValidator()
print(v.validate_order({"quantity": "5", "price": "-10"}))
print(v.validate_order({"quantity": True, "price": False}))
print(v.validate_order({"discount": "50", "status": True}))''',
        r'''<think>
Let me trace through each of the "bad" inputs that pass validation but shouldn't.

**Test 1: `{"quantity": "5", "price": "-10"}`**

- `qty = "5"` (string)
- `"5" <= 0` -- this compares string to int. In Python 3, this raises `TypeError: '<=' not supported between instances of 'str' and 'int'`. Wait, does it? Let me think... Yes, in Python 3, `"5" <= 0` raises TypeError. So this would actually CRASH, not silently pass.

Hmm, but the user says these "pass validation." Maybe the data comes from a JSON API where values are sometimes strings? If the web framework auto-parses JSON, `"5"` would be a string in the dict. But `"5" <= 0` would crash in Python 3...

Unless there's a try/except somewhere I'm not seeing. Or unless the user is running Python 2 where mixed-type comparisons work. But let me assume Python 3.

Wait, let me re-examine. `"5" <= 0` in Python 3:
```
>>> "5" <= 0
TypeError: '<=' not supported between instances of 'str' and 'int'
```

So test 1 would crash, not silently pass. Let me re-read the user's claim... "These all pass validation but shouldn't." Maybe the user is wrong about the crash vs pass distinction, or maybe there's error handling wrapping this.

Actually, I bet the real issue is more subtle. Let me look at each case more carefully:

**Test 2: `{"quantity": True, "price": False}`**
- `qty = True`
- `True <= 0` -- `bool` is a subclass of `int` in Python! `True == 1`, so `1 <= 0` is `False`. No error added.
- `price = False` -- `False == 0`, and `0 < 0` is `False`. No error added.
- Result: `(True, [])` -- validation passes! But `quantity=True` and `price=False` are clearly invalid.

**Test 3: `{"discount": "50", "status": True}`**
- `discount = "50"` (string)
- `"50" < 0` -- TypeError in Python 3. Crash.
- But `status = True` -- `True in {"pending", "confirmed", "shipped"}` is `False` (True is not a string). So status check would catch it IF we got that far.

OK so the user's claims about test 1 and 3 might be slightly wrong (they crash rather than pass), but the core issues are real. Let me focus on the actual bugs:

1. **No type checking at all.** The validator assumes values have the right type but never verifies. JSON APIs can send strings, bools, nulls, arrays, etc.

2. **Bool is int in Python.** `True` passes as quantity 1, `False` passes as price 0. This is the sneakiest bug.

3. **Default values mask missing fields.** `data.get("quantity", 0)` defaults to 0, then `0 <= 0` adds an error. But `data.get("discount", 0)` defaults to 0, which passes all checks. Missing required fields should be errors, not silently defaulted.

4. **String comparisons with numbers.** If data comes from form submissions (not JSON), values are strings. `"5" <= 0` crashes in Python 3.

5. **Email validation is trivially bypassable.** `"@"` passes the check.

Let me write a proper fix.
</think>

Several type coercion bugs. The worst is that Python's `bool` is a subclass of `int`:

**Bug 1: `bool` passes as numeric.** `True` is `1` and `False` is `0` in Python. So `quantity=True` passes the `> 0` check, and `price=False` passes the `>= 0` check. Both are clearly invalid order data.

**Bug 2: No type enforcement.** String values like `"5"` and `"-10"` either crash (Python 3 can't compare `str < int`) or silently pass depending on the operation. The validator never checks types.

**Bug 3: Defaults mask missing required fields.** `data.get("quantity", 0)` treats a missing quantity the same as `quantity=0`. Missing fields should be explicit errors, not silently defaulted.

**Bug 4: Trivial email check.** `"@"` passes the `"@" in email` validation.

```python
from typing import Any

class OrderValidator:
    VALID_STATUSES = {"pending", "confirmed", "shipped"}

    def _require_type(self, value: Any, expected: type,
                      field: str, errors: list) -> bool:
        # bool check MUST come before int check because bool is subclass of int
        if expected in (int, float) and isinstance(value, bool):
            errors.append(f"{field} must be a number, not boolean")
            return False
        if not isinstance(value, expected):
            errors.append(
                f"{field} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )
            return False
        return True

    def validate_order(self, data: dict) -> tuple[bool, list[str]]:
        errors = []

        # Quantity: required, must be int, must be positive
        if "quantity" not in data:
            errors.append("Quantity is required")
        elif self._require_type(data["quantity"], int, "quantity", errors):
            if data["quantity"] <= 0:
                errors.append("Quantity must be positive")

        # Price: required, must be numeric, non-negative
        if "price" not in data:
            errors.append("Price is required")
        elif self._require_type(data["price"], (int, float), "price", errors):
            if data["price"] < 0:
                errors.append("Price cannot be negative")

        # Discount: optional, must be numeric, 0-100
        if "discount" in data:
            if self._require_type(data["discount"], (int, float),
                                  "discount", errors):
                if data["discount"] < 0 or data["discount"] > 100:
                    errors.append("Discount must be 0-100")

        # Status: optional with default, must be string
        if "status" in data:
            if self._require_type(data["status"], str, "status", errors):
                if data["status"] not in self.VALID_STATUSES:
                    errors.append(f"Invalid status: {data['status']}")

        # Email: optional, basic format check
        if "email" in data:
            if self._require_type(data["email"], str, "email", errors):
                email = data["email"]
                parts = email.split("@")
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    errors.append("Invalid email format")

        return (len(errors) == 0, errors)

    def _require_type(self, value, expected, field, errors):
        # Handle tuple of types
        if isinstance(expected, tuple):
            if isinstance(value, bool):  # bool before int check
                errors.append(f"{field} must be numeric, not boolean")
                return False
            if not isinstance(value, expected):
                names = "/".join(t.__name__ for t in expected)
                errors.append(f"{field} must be {names}")
                return False
        else:
            if expected in (int, float) and isinstance(value, bool):
                errors.append(f"{field} must be {expected.__name__}, not boolean")
                return False
            if not isinstance(value, expected):
                errors.append(f"{field} must be {expected.__name__}")
                return False
        return True
```

**Key principle:** Always check `isinstance(value, bool)` BEFORE `isinstance(value, int)` because `bool` is a subclass of `int`. This is Python's most common type coercion trap in validation code.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
