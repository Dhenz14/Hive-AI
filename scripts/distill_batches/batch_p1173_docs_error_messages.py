"""Documentation generation training pairs: error messages and troubleshooting guides."""

pairs = [
    {
        "instruction": r'''Write helpful error messages for this database connection module. Currently it just raises generic exceptions:

def connect(config):
    if not config.get("host"):
        raise ValueError("bad config")
    if not config.get("port"):
        raise ValueError("bad config")
    try:
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            dbname=config.get("database", "postgres"),
            user=config.get("user"),
            password=config.get("password"),
            connect_timeout=config.get("timeout", 5),
        )
    except psycopg2.OperationalError:
        raise ConnectionError("connection failed")
    return conn''',
        "output": r'''<think>
The current error messages are useless -- "bad config" and "connection failed" tell the user nothing about what went wrong or how to fix it. I need to:
1. Be specific about what is missing or wrong
2. Suggest how to fix each issue
3. Include the actual values (where safe) to help debugging
4. Distinguish between different failure modes in the OperationalError catch
</think>

```python
def connect(config):
    # -- Validate required configuration --
    if not config.get("host"):
        raise ValueError(
            "Database connection requires 'host' in config. "
            "Set config['host'] to your database hostname or IP address. "
            "Example: config = {'host': 'localhost', 'port': 5432}"
        )

    if not config.get("port"):
        raise ValueError(
            "Database connection requires 'port' in config. "
            "PostgreSQL default port is 5432. "
            "Example: config = {'host': 'localhost', 'port': 5432}"
        )

    host = config["host"]
    port = config["port"]
    dbname = config.get("database", "postgres")

    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=config.get("user"), password=config.get("password"),
            connect_timeout=config.get("timeout", 5),
        )
    except psycopg2.OperationalError as e:
        error_msg = str(e).strip()

        if "could not connect to server" in error_msg:
            raise ConnectionError(
                "Cannot reach database at " + host + ":" + str(port) + ". "
                "Check that the server is running and no firewall "
                "is blocking the connection. Error: " + error_msg
            ) from e

        if "password authentication failed" in error_msg:
            raise ConnectionError(
                "Auth failed for user on database '" + dbname + "'. "
                "Check username/password. If using env vars, verify they are set."
            ) from e

        if "does not exist" in error_msg:
            raise ConnectionError(
                "Database '" + dbname + "' does not exist on " + host + ". "
                "Create it with: createdb " + dbname
            ) from e

        raise ConnectionError(
            "Failed to connect to " + host + ":" + str(port) + ": " + error_msg
        ) from e

    return conn
```'''
    },
    {
        "instruction": r'''Write a troubleshooting guide for common errors users encounter with this Docker Compose setup:

version: "3.8"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    environment:
      - DATABASE_URL=postgresql://app:secret@db:5432/myapp
      - REDIS_URL=redis://redis:6379/0

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=myapp
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:''',
        "output": r'''# Troubleshooting Guide

## "Connection refused" to the database on startup

**Symptom:** The web service crashes with `psycopg2.OperationalError: could not connect to server: Connection refused` even though `depends_on: db` is set.

**Cause:** `depends_on` only waits for the container to start, not for PostgreSQL to be ready to accept connections. The database needs a few seconds to initialize.

**Fix:** Add a health check and use `depends_on` with condition:

```yaml
  db:
    image: postgres:15
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 3s
      retries: 5

  web:
    depends_on:
      db:
        condition: service_healthy
```

Or add retry logic in your application's database connection code.

---

## "Address already in use" on port 8000 or 6379

**Symptom:** `docker compose up` fails with `Bind for 0.0.0.0:8000 failed: port is already allocated`.

**Cause:** Another process is using that port on your host machine.

**Fix:**
1. Find what is using the port: `lsof -i :8000` (macOS/Linux) or `netstat -ano | findstr :8000` (Windows)
2. Stop that process, or change the host port mapping: `"9000:8000"`

---

## Database data disappears after rebuild

**Symptom:** Running `docker compose down` and `docker compose up` loses all database data.

**Cause:** `docker compose down` with `-v` flag removes named volumes, deleting PostgreSQL data.

**Fix:** Use `docker compose down` WITHOUT the `-v` flag to preserve volumes. The `pgdata` volume in this setup is a named volume, so data persists across normal restarts. Only `docker compose down -v` or `docker volume rm` will delete it.

---

## "FATAL: role 'app' does not exist"

**Symptom:** Database connection fails with role error after changing POSTGRES_USER.

**Cause:** PostgreSQL only creates the user/database on first initialization. If the volume already contains data from a previous run with different settings, the new environment variables are ignored.

**Fix:** Remove the old volume and re-initialize:

```bash
docker compose down -v
docker compose up -d
```

---

## Redis connection timeout from web container

**Symptom:** The web app cannot connect to Redis, but `redis-cli` works from the host.

**Cause:** The web container should connect using the Docker service name (`redis`) as the hostname, not `localhost`. Verify `REDIS_URL` uses `redis://redis:6379/0` (service name), not `redis://localhost:6379/0`.'''
    },
    {
        "instruction": r'''Improve the error messages in this API validation function. Current messages are too terse:

def validate_upload(file, metadata):
    if file is None:
        raise ValidationError("no file")
    if file.size > 50_000_000:
        raise ValidationError("too large")
    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError("bad type")
    if not metadata.get("title"):
        raise ValidationError("no title")
    if len(metadata.get("title", "")) > 200:
        raise ValidationError("title too long")
    if metadata.get("tags") and len(metadata["tags"]) > 10:
        raise ValidationError("too many tags")''',
        "output": r'''```python
ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain",
}

MAX_FILE_SIZE = 50_000_000  # 50 MB
MAX_TITLE_LENGTH = 200
MAX_TAGS = 10


def validate_upload(file, metadata):
    if file is None:
        raise ValidationError(
            "No file was provided in the upload request. "
            "Send the file as multipart form data with field name 'file'."
        )

    if file.size > MAX_FILE_SIZE:
        size_mb = round(file.size / 1_000_000, 1)
        raise ValidationError(
            "File is too large: " + str(size_mb) + " MB. "
            "Maximum allowed size is 50 MB. "
            "Consider compressing the file or reducing its resolution."
        )

    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError(
            "File type '" + str(file.content_type) + "' is not supported. "
            "Allowed types: " + ", ".join(sorted(ALLOWED_TYPES)) + ". "
            "If your file is one of these types but has the wrong Content-Type "
            "header, check your upload client configuration."
        )

    title = metadata.get("title", "")
    if not title or not title.strip():
        raise ValidationError(
            "A title is required in the metadata. "
            "Provide metadata.title as a non-empty string."
        )

    if len(title) > MAX_TITLE_LENGTH:
        raise ValidationError(
            "Title is " + str(len(title)) + " characters, "
            "but the maximum is " + str(MAX_TITLE_LENGTH) + ". "
            "Please shorten the title."
        )

    tags = metadata.get("tags", [])
    if len(tags) > MAX_TAGS:
        raise ValidationError(
            "Too many tags: " + str(len(tags)) + " provided, "
            "but the maximum is " + str(MAX_TAGS) + ". "
            "Remove some tags and try again."
        )
```

Key improvements:
- Include the actual value that failed (file size, content type, character count)
- State the limit alongside the violation
- Suggest what the user should do to fix the problem
- Use named constants so limits are easy to change'''
    },
    {
        "instruction": r'''Write a troubleshooting section for a Python package that users install with pip. Cover the 5 most common installation and runtime issues.''',
        "output": r'''<think>
The most common issues with pip-installed Python packages are:
1. Import errors after install (wrong Python/venv)
2. Version conflicts with dependencies
3. Missing system libraries for C extensions
4. Permission errors
5. "Module not found" in Jupyter notebooks (kernel mismatch)

I should give concrete diagnostic commands and fixes for each.
</think>

# Troubleshooting

## 1. "ModuleNotFoundError: No module named 'mypackage'"

**Cause:** The package was installed in a different Python environment than the one you are running.

**Diagnosis:**
```bash
# Check which Python you are using
which python
# Check where pip installs to
pip show mypackage
```

If the paths do not match, you are using different environments.

**Fix:** Install explicitly with the Python you are using:
```bash
python -m pip install mypackage
```

If using a virtual environment, make sure it is activated before installing and running.

## 2. Dependency version conflict

**Symptom:** `pip install` prints `ERROR: Cannot install mypackage because these package versions have conflicting dependencies`.

**Fix:** Try installing in a fresh virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install mypackage
```

If you must use specific versions of conflicting packages, check our compatibility matrix in the README.

## 3. Build fails with "gcc" or "fatal error: Python.h"

**Symptom:** Installation fails while building a C extension with errors about missing headers or compilers.

**Fix (Ubuntu/Debian):**
```bash
sudo apt install build-essential python3-dev
```

**Fix (macOS):**
```bash
xcode-select --install
```

**Fix (Windows):** Install the [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the "Desktop development with C++" workload.

## 4. "Permission denied" during install

**Symptom:** `PermissionError: [Errno 13] Permission denied` when running `pip install`.

**Fix:** Do NOT use `sudo pip install`. Instead, use a virtual environment (see #2 above) or install for your user only:
```bash
pip install --user mypackage
```

## 5. Works in terminal but not in Jupyter

**Symptom:** `import mypackage` works in the terminal but raises `ModuleNotFoundError` in a Jupyter notebook.

**Cause:** The Jupyter kernel is using a different Python than your terminal.

**Fix:** Install the package from within the notebook:
```python
import sys
!{sys.executable} -m pip install mypackage
```

Then restart the kernel.'''
    },
    {
        "instruction": r'''Write user-facing error messages and a troubleshooting section for this OAuth2 login flow:

def oauth_callback(code, state):
    if not code:
        raise OAuthError("missing_code")
    if state != session.get("oauth_state"):
        raise OAuthError("state_mismatch")
    try:
        token_resp = requests.post(PROVIDER_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }, timeout=10)
    except requests.Timeout:
        raise OAuthError("timeout")
    if token_resp.status_code != 200:
        raise OAuthError("token_exchange_failed")
    tokens = token_resp.json()
    user_resp = requests.get(PROVIDER_USERINFO_URL,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10)
    if user_resp.status_code != 200:
        raise OAuthError("userinfo_failed")''',
        "output": r'''```python
OAUTH_ERROR_MESSAGES = {
    "missing_code": (
        "Login failed: the authentication provider did not return an "
        "authorization code. This can happen if you denied the login "
        "request or if the provider is experiencing issues. "
        "Please try logging in again."
    ),
    "state_mismatch": (
        "Login failed: the session state does not match. This is a "
        "security check to prevent cross-site request forgery (CSRF). "
        "Common causes: (1) your session expired -- try again from the "
        "login page, (2) you opened multiple login tabs, or (3) a "
        "browser extension modified the request."
    ),
    "timeout": (
        "Login failed: the authentication provider did not respond "
        "within 10 seconds. This is usually a temporary issue on "
        "their end. Please wait a moment and try again."
    ),
    "token_exchange_failed": (
        "Login failed: could not exchange the authorization code for "
        "an access token. If this persists, the application's OAuth "
        "credentials may be misconfigured. Contact support."
    ),
    "userinfo_failed": (
        "Login succeeded but we could not retrieve your profile "
        "information from the provider. Try logging in again. If "
        "this persists, check that you granted profile access "
        "permissions during the login prompt."
    ),
}
```

# Troubleshooting: Login with OAuth

## "Session state does not match"

This is the most common error. Solutions:

1. **Clear cookies** for this site and try again
2. **Do not open multiple login tabs** -- start a fresh login from the main page
3. **Disable browser extensions** that modify requests (privacy extensions, ad blockers) temporarily
4. If using **incognito/private mode**, make sure cookies are enabled for the session

## "Authentication provider did not respond"

The OAuth provider (Google, GitHub, etc.) is temporarily slow or unreachable.

- Wait 30 seconds and try again
- Check the provider's status page for outages
- If you are behind a corporate firewall, ensure `accounts.google.com` (or similar) is not blocked

## "Could not exchange authorization code"

This typically means the OAuth application is misconfigured. If you are a developer:

- Verify `CLIENT_ID` and `CLIENT_SECRET` are correct
- Confirm the `REDIRECT_URI` exactly matches what is registered with the provider (including trailing slashes, http vs https)
- Check that the authorization code has not already been used (codes are single-use)

## Login works locally but not in production

Common cause: the redirect URI in your OAuth provider settings points to `http://localhost:8000/callback` but production uses `https://myapp.com/callback`. Add the production URL to your provider's allowed redirect URIs.'''
    },
]
