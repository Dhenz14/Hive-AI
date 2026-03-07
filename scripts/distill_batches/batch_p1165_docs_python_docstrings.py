"""Documentation generation training pairs: Python docstrings (Google/NumPy style)."""

pairs = [
    {
        "instruction": r'''Write Google-style docstrings for this Python class and its methods:

class RetryHandler:
    def __init__(self, max_retries=3, backoff_factor=1.5, exceptions=(Exception,)):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions
        self._attempt = 0

    def execute(self, func, *args, **kwargs):
        self._attempt = 0
        while self._attempt <= self.max_retries:
            try:
                return func(*args, **kwargs)
            except self.exceptions as e:
                self._attempt += 1
                if self._attempt > self.max_retries:
                    raise
                time.sleep(self.backoff_factor ** self._attempt)

    def reset(self):
        self._attempt = 0

    @property
    def attempts_made(self):
        return self._attempt''',
        "output": r'''<think>
I need to write Google-style docstrings for this class. The key things to document:
- Class purpose and behavior (retry with exponential backoff)
- Constructor parameters with types and defaults
- Method args, return values, and raised exceptions
- The property should be documented too

Google style uses Args:, Returns:, Raises: sections with indented descriptions. I should note the exponential backoff formula and the fact that execute re-raises after exhausting retries.
</think>

```python
class RetryHandler:
    """Executes functions with automatic retry and exponential backoff.

    Catches specified exception types and retries the function call up to
    a configurable maximum, sleeping between attempts with exponentially
    increasing delays.

    Args:
        max_retries: Maximum number of retry attempts. Defaults to 3.
        backoff_factor: Base for exponential delay calculation. The sleep
            duration for attempt N is backoff_factor ** N seconds.
            Defaults to 1.5.
        exceptions: Tuple of exception classes to catch and retry on.
            Defaults to (Exception,), which catches all standard errors.

    Example:
        handler = RetryHandler(max_retries=5, backoff_factor=2.0)
        result = handler.execute(requests.get, "https://api.example.com/data")
    """

    def __init__(self, max_retries=3, backoff_factor=1.5, exceptions=(Exception,)):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.exceptions = exceptions
        self._attempt = 0

    def execute(self, func, *args, **kwargs):
        """Execute a function with retry logic.

        Resets the attempt counter, then calls func with the given
        arguments. On failure, retries up to max_retries times with
        exponential backoff.

        Args:
            func: Callable to execute.
            *args: Positional arguments passed to func.
            **kwargs: Keyword arguments passed to func.

        Returns:
            The return value of func on success.

        Raises:
            Exception: Re-raises the last caught exception if all
                retry attempts are exhausted.
        """
        ...

    def reset(self):
        """Reset the internal attempt counter to zero."""
        ...

    @property
    def attempts_made(self):
        """int: Number of attempts made during the last execute() call."""
        ...
```'''
    },
    {
        "instruction": r'''Add NumPy-style docstrings to this data processing function:

def interpolate_timeseries(data, timestamps, target_freq, method="linear", fill_limit=5):
    if len(data) != len(timestamps):
        raise ValueError("data and timestamps must have the same length")

    df = pd.DataFrame({"value": data}, index=pd.DatetimeIndex(timestamps))
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()

    new_index = pd.date_range(start=df.index[0], end=df.index[-1], freq=target_freq)
    df = df.reindex(new_index)

    if method == "linear":
        df["value"] = df["value"].interpolate(method="time", limit=fill_limit)
    elif method == "ffill":
        df["value"] = df["value"].ffill(limit=fill_limit)
    elif method == "cubic":
        df["value"] = df["value"].interpolate(method="cubic", limit=fill_limit)
    else:
        raise ValueError(f"Unknown method: {method}")

    return df["value"].values, df.index.tolist()''',
        "output": r'''```python
def interpolate_timeseries(data, timestamps, target_freq, method="linear", fill_limit=5):
    """
    Resample and interpolate a time series to a uniform frequency.

    Takes irregularly-spaced time series data and resamples it to a
    uniform frequency, filling gaps using the specified interpolation
    method. Duplicate timestamps are removed (keeping the first
    occurrence) and data is sorted chronologically before processing.

    Parameters
    ----------
    data : array-like
        The values of the time series. Must have the same length as
        `timestamps`.
    timestamps : array-like
        Datetime-like objects or strings parseable by pandas. Each
        entry corresponds to one value in `data`.
    target_freq : str
        Pandas frequency string for the output time series (e.g.,
        "1T" for 1-minute, "1H" for hourly, "1D" for daily).
    method : str, optional
        Interpolation method. One of:

        - "linear" -- time-weighted linear interpolation (default)
        - "ffill" -- forward fill from last known value
        - "cubic" -- cubic spline interpolation

    fill_limit : int, optional
        Maximum number of consecutive NaN values to fill. Gaps
        longer than this remain as NaN. Defaults to 5.

    Returns
    -------
    values : numpy.ndarray
        Interpolated values at the new uniform timestamps.
    new_timestamps : list of pandas.Timestamp
        The uniformly-spaced timestamps corresponding to `values`.

    Raises
    ------
    ValueError
        If `data` and `timestamps` have different lengths, or if
        `method` is not one of the supported methods.

    Examples
    --------
    >>> vals = [10.0, 20.0, 50.0]
    >>> times = ["2024-01-01 00:00", "2024-01-01 00:05", "2024-01-01 00:15"]
    >>> result, ts = interpolate_timeseries(vals, times, "5T")
    """
    ...
```'''
    },
    {
        "instruction": r'''Write a Google-style docstring for this async context manager:

class DatabasePool:
    def __init__(self, dsn, min_size=2, max_size=10, timeout=30.0):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout
        self._pool = None

    async def __aenter__(self):
        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=self.min_size, max_size=self.max_size
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._pool:
            await self._pool.close()
        return False

    async def fetch(self, query, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query, *args):
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def transaction(self):
        conn = await self._pool.acquire()
        tx = conn.transaction()
        await tx.start()
        return conn, tx''',
        "output": r'''<think>
This is an async context manager wrapping asyncpg's connection pool. I need to document:
- The class as an async context manager (mention async with usage)
- Constructor params with types
- Each async method with its args, returns, and behavior
- The transaction method returns a tuple which is worth highlighting
- Should mention that the pool auto-closes on context exit
</think>

```python
class DatabasePool:
    """Async context manager for PostgreSQL connection pooling via asyncpg.

    Manages the lifecycle of a connection pool. Use with ``async with``
    to ensure connections are properly released on exit.

    Args:
        dsn: PostgreSQL connection string
            (e.g., "postgresql://user:pass@localhost/dbname").
        min_size: Minimum number of connections to keep open. Defaults to 2.
        max_size: Maximum number of connections in the pool. Defaults to 10.
        timeout: Seconds to wait for a connection before raising an error.
            Defaults to 30.0.

    Example:
        async with DatabasePool("postgresql://localhost/mydb") as db:
            rows = await db.fetch("SELECT * FROM users WHERE active = $1", True)
    """

    async def __aenter__(self):
        """Create the connection pool and return this instance."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close all connections in the pool.

        Returns:
            False -- exceptions are never suppressed.
        """
        ...

    async def fetch(self, query, *args):
        """Execute a query and return all result rows.

        Acquires a connection from the pool, executes the query,
        and releases the connection automatically.

        Args:
            query: SQL query string with $1, $2, ... placeholders.
            *args: Values to bind to the query placeholders.

        Returns:
            list[asyncpg.Record]: The result rows.
        """
        ...

    async def execute(self, query, *args):
        """Execute a query without returning rows.

        Suitable for INSERT, UPDATE, DELETE, and DDL statements.

        Args:
            query: SQL query string with $1, $2, ... placeholders.
            *args: Values to bind to the query placeholders.

        Returns:
            str: A command status string (e.g., "INSERT 0 1").
        """
        ...

    async def transaction(self):
        """Acquire a connection and start a transaction.

        The caller is responsible for committing or rolling back
        the transaction and releasing the connection.

        Returns:
            tuple: A (connection, transaction) pair. Call
                ``await tx.commit()`` or ``await tx.rollback()``
                when done.
        """
        ...
```'''
    },
    {
        "instruction": r'''Generate docstrings for this caching decorator. Keep them concise but cover the important details:

def cached(ttl_seconds=300, max_size=128, key_func=None):
    def decorator(func):
        cache = OrderedDict()
        lock = threading.Lock()

        def make_key(*args, **kwargs):
            if key_func:
                return key_func(*args, **kwargs)
            return (args, tuple(sorted(kwargs.items())))

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = make_key(*args, **kwargs)
            now = time.monotonic()

            with lock:
                if key in cache:
                    value, timestamp = cache[key]
                    if now - timestamp < ttl_seconds:
                        cache.move_to_end(key)
                        return value
                    else:
                        del cache[key]

            result = func(*args, **kwargs)

            with lock:
                cache[key] = (result, now)
                while len(cache) > max_size:
                    cache.popitem(last=False)

            return result

        def clear():
            with lock:
                cache.clear()

        wrapper.clear_cache = clear
        return wrapper
    return decorator''',
        "output": r'''```python
def cached(ttl_seconds=300, max_size=128, key_func=None):
    """Thread-safe LRU cache decorator with time-based expiration.

    Caches function return values keyed by arguments. Expired entries
    are evicted on access. When the cache exceeds max_size, the least
    recently used entries are removed first.

    Args:
        ttl_seconds: Time-to-live for each cache entry in seconds.
            Defaults to 300 (5 minutes).
        max_size: Maximum number of entries to store. Defaults to 128.
        key_func: Optional callable that takes the same arguments as
            the decorated function and returns a hashable cache key.
            If None, the default key is (args, sorted_kwargs_tuple).

    Returns:
        A decorator that wraps the target function with caching.
        The wrapped function has a ``clear_cache()`` method attached
        to manually invalidate all cached entries.

    Example:
        @cached(ttl_seconds=60, max_size=256)
        def get_user(user_id):
            return db.query(User).get(user_id)

        get_user(42)       # executes query
        get_user(42)       # returns cached result
        get_user.clear_cache()  # invalidate all entries

    Notes:
        - Cache keys must be hashable. Passing unhashable arguments
          (like lists) without a custom key_func will raise TypeError.
        - The function call itself is NOT locked -- only cache reads
          and writes are synchronized. Two threads calling with the
          same uncached key may both execute the function.
    """
    ...
```'''
    },
    {
        "instruction": r'''Write NumPy-style docstrings for these two related functions:

def validate_schema(data, schema, strict=False):
    errors = []
    for field_name, rules in schema.items():
        if field_name not in data:
            if rules.get("required", False):
                errors.append({"field": field_name, "error": "missing required field"})
            continue

        value = data[field_name]
        expected_type = rules.get("type")
        if expected_type and not isinstance(value, expected_type):
            errors.append({"field": field_name, "error": f"expected {expected_type.__name__}"})
            continue

        min_val = rules.get("min")
        max_val = rules.get("max")
        if min_val is not None and value < min_val:
            errors.append({"field": field_name, "error": f"below minimum {min_val}"})
        if max_val is not None and value > max_val:
            errors.append({"field": field_name, "error": f"above maximum {max_val}"})

        pattern = rules.get("pattern")
        if pattern and isinstance(value, str) and not re.match(pattern, value):
            errors.append({"field": field_name, "error": "pattern mismatch"})

    if strict:
        extra = set(data.keys()) - set(schema.keys())
        for field_name in extra:
            errors.append({"field": field_name, "error": "unknown field"})

    return errors


def validate_or_raise(data, schema, strict=False):
    errors = validate_schema(data, schema, strict=strict)
    if errors:
        msg = "; ".join(f"{e['field']}: {e['error']}" for e in errors)
        raise ValidationError(msg, errors=errors)
    return data''',
        "output": r'''<think>
Two functions that work together. validate_schema returns a list of error dicts, validate_or_raise wraps it and raises on failure. I need to document the schema dict structure clearly since that is the most important part for users. NumPy style uses Parameters, Returns, Raises sections with dashed underlines.
</think>

```python
def validate_schema(data, schema, strict=False):
    """
    Validate a data dictionary against a schema definition.

    Checks each field in `schema` against the corresponding value in
    `data`, collecting all validation errors rather than failing on
    the first one.

    Parameters
    ----------
    data : dict
        The data to validate. Keys are field names, values are the
        data to check.
    schema : dict
        Validation rules keyed by field name. Each value is a dict
        that may contain:

        - "required" (bool) -- field must exist in data
        - "type" (type) -- expected Python type (checked via isinstance)
        - "min" (comparable) -- minimum allowed value (inclusive)
        - "max" (comparable) -- maximum allowed value (inclusive)
        - "pattern" (str) -- regex pattern that string values must match

    strict : bool, optional
        If True, fields in `data` not present in `schema` are flagged
        as errors. Defaults to False.

    Returns
    -------
    list of dict
        Each dict has keys "field" (str) and "error" (str). Returns
        an empty list if validation passes.

    Examples
    --------
    >>> schema = {"age": {"type": int, "min": 0, "max": 150, "required": True}}
    >>> validate_schema({"age": 25}, schema)
    []
    >>> validate_schema({"age": -1}, schema)
    [{"field": "age", "error": "below minimum 0"}]
    """
    ...


def validate_or_raise(data, schema, strict=False):
    """
    Validate data and raise on failure, or return the data unchanged.

    Thin wrapper around `validate_schema` that raises a
    ``ValidationError`` if any errors are found.

    Parameters
    ----------
    data : dict
        The data to validate.
    schema : dict
        Schema definition (see `validate_schema` for format).
    strict : bool, optional
        Reject unknown fields. Defaults to False.

    Returns
    -------
    dict
        The original `data` dict, unmodified, if validation passes.

    Raises
    ------
    ValidationError
        If one or more validation errors are found. The exception
        has an ``errors`` attribute containing the full error list.
    """
    ...
```'''
    },
]
