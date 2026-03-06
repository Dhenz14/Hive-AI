PAIRS = [
    ("thinking/debugging", r'''I'm getting a circular import error in my Flask application:

```
ImportError: cannot import name 'db' from partially initialized module 'app.models'
(most likely due to a circular import)
```

Project structure:
```
app/
  __init__.py
  models.py
  routes.py
```

app/__init__.py:
```python
from flask import Flask
from app.models import db, User

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
db.init_app(app)

from app.routes import bp
app.register_blueprint(bp)
```

app/models.py:
```python
from flask_sqlalchemy import SQLAlchemy
from app import app  # <-- circular import!

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
```

app/routes.py:
```python
from flask import Blueprint
from app.models import db, User

bp = Blueprint('main', __name__)

@bp.route('/users')
def list_users():
    return [u.name for u in User.query.all()]
```

How do I fix this?''', r'''<think>
Let me trace the import chain:

1. Python tries to import `app` (the package, via `app/__init__.py`)
2. `app/__init__.py` line 2: `from app.models import db, User`
3. Python starts importing `app.models`
4. `app/models.py` line 2: `from app import app` -- this tries to import `app` from the `app` package
5. But `app/__init__.py` is still being executed (it is at line 2, it has not finished yet). The `app` variable (Flask instance) has not been created yet because that is on line 4 of `__init__.py`.
6. Python sees that `app` (the package) is partially initialized. It tries to find `app` as a name in the partially-initialized module, but the Flask `app` variable has not been assigned yet.
7. ImportError!

The fix is to remove the circular dependency. The models.py file should NOT import from app/__init__.py. Instead, the db object should be created independently and the app should be passed to it later.

This is the classic Flask application factory pattern.
</think>

The circular import chain is:

```
app/__init__.py imports app.models (to get db, User)
  -> app/models.py imports app (to get the Flask app instance)
    -> app/__init__.py is still loading! The Flask 'app' variable does not exist yet.
```

Python detects that `app/__init__.py` is partially initialized and cannot find the `app` name because that line has not executed yet.

**The root cause:** `models.py` imports `app` to... do nothing with it. Looking at the code, `models.py` does not actually need the Flask app instance. The `from app import app` line is unnecessary.

**Fix 1: Remove the unnecessary import**

```python
# app/models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
```

The `db.init_app(app)` call in `__init__.py` already connects the SQLAlchemy instance to the Flask app. The models file does not need to know about the app.

**Fix 2: Use the Application Factory pattern (best practice)**

```python
# app/__init__.py
from flask import Flask
from app.models import db

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

    db.init_app(app)

    from app.routes import bp  # import inside function to avoid circular
    app.register_blueprint(bp)

    return app
```

```python
# app/models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
```

```python
# app/routes.py
from flask import Blueprint
from app.models import db, User

bp = Blueprint('main', __name__)

@bp.route('/users')
def list_users():
    return [u.name for u in User.query.all()]
```

```python
# run.py (entry point)
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
```

**Why the factory pattern prevents circular imports:**

- `app/models.py` creates `db` independently -- no imports from `app`
- `app/__init__.py` imports models at the top level (safe, no cycle)
- `app/routes.py` imports models at the top level (safe, no cycle)
- The blueprint import in `create_app()` is deferred inside the function, after `app` exists

**General rules for avoiding circular imports:**
- Keep shared objects (db, cache, etc.) in their own module with no local imports
- Use the factory pattern for Flask/Django apps
- Move imports inside functions when they are only needed at runtime
- Use `TYPE_CHECKING` for type hints that would cause circular imports:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from app.models import User
  ```'''),

    ("thinking/debugging", r'''I'm confused about relative vs absolute imports. This worked locally but fails in production:

```
ModuleNotFoundError: No module named 'utils'
```

Project structure:
```
myproject/
  setup.py
  myproject/
    __init__.py
    main.py
    utils.py
    processors/
      __init__.py
      text.py
```

myproject/processors/text.py:
```python
from utils import clean_text  # Works when run as: python processors/text.py
```

myproject/main.py:
```python
from processors.text import TextProcessor  # Works when run as: python main.py
```

But when installed with `pip install -e .`, both imports break differently. What's going on?''', r'''<think>
This is about the difference between running scripts directly vs importing from installed packages.

When you run `python processors/text.py` directly:
- Python adds the directory containing `text.py` (i.e., `processors/`) to sys.path
- Wait, actually Python adds the directory of the script being run. If you run `python processors/text.py` from the `myproject/` directory, Python adds `myproject/processors/` to sys.path
- Actually no. Python adds the directory containing the script to sys.path[0]. So if you run `python processors/text.py`, it adds `processors/` to the path... no.

Let me be more precise. Python adds the directory of the script to sys.path[0]. So:

Running `cd myproject && python processors/text.py`:
- sys.path[0] = 'myproject/processors/'
- `from utils import clean_text` would look for utils in processors/ directory, which would NOT work because utils.py is in the parent directory.

Hmm, actually running `cd myproject && python main.py`:
- sys.path[0] = 'myproject/'
- `from processors.text import TextProcessor` works because processors/ is a subdirectory
- But when text.py does `from utils import clean_text`, this works because sys.path[0] is 'myproject/' and utils.py is there.

When installed as a package:
- The package is `myproject` (the inner directory)
- Imports should be `from myproject.utils import clean_text` (absolute) or `from ..utils import clean_text` (relative)
- `from utils import clean_text` fails because `utils` is not a top-level package -- it is `myproject.utils`

The fix: use either absolute imports with the full package path, or relative imports.
</think>

The issue is the difference between running scripts directly (where Python adds the script's directory to `sys.path`) and importing from an installed package (where only the package root matters).

**What happens when running directly:**

```bash
cd myproject/
python main.py
```
Python adds `myproject/` to `sys.path[0]`. From that perspective:
- `from processors.text import ...` works (processors/ is a subdirectory)
- Inside text.py, `from utils import ...` works because `utils.py` is in `sys.path[0]`

**What happens when installed as a package:**

```bash
pip install -e .
python -c "from myproject.main import ..."
```
The package root is `myproject` (the inner directory). Python knows about `myproject.utils`, `myproject.processors.text`, etc. But:
- `from utils import clean_text` fails because there is no top-level package called `utils`
- `from processors.text import ...` fails because there is no top-level package called `processors`

**Fix: Use absolute or relative imports consistently**

```python
# myproject/processors/text.py

# Option A: Absolute imports (preferred)
from myproject.utils import clean_text

# Option B: Relative imports
from ..utils import clean_text
```

```python
# myproject/main.py

# Option A: Absolute imports
from myproject.processors.text import TextProcessor
from myproject.utils import clean_text

# Option B: Relative imports
from .processors.text import TextProcessor
from .utils import clean_text
```

**Important rules:**

1. **Never rely on `sys.path` containing your project directory.** It works during development with `python script.py` but breaks when the package is installed.

2. **Relative imports (with dots) only work inside packages.** You cannot use relative imports in a script run directly with `python script.py`. The file must be imported as part of a package.

3. **Use `python -m` to run modules within packages:**
   ```bash
   # Instead of: python myproject/main.py
   # Use:
   python -m myproject.main
   ```
   This preserves the package context and makes relative imports work.

4. **Add a `__main__.py` for runnable packages:**
   ```python
   # myproject/__main__.py
   from myproject.main import main
   main()
   ```
   Then run with: `python -m myproject`

**Prevention tips:**
- Always use absolute imports with the full package path in any non-trivial project
- Never run internal modules directly with `python file.py` -- use `python -m package.module`
- Set up `entry_points` in `setup.py` or `pyproject.toml` for CLI commands
- Use a linter like `pylint` or `isort` to enforce import style
- Test imports by installing your package in a fresh virtualenv, not just running from the source directory'''),

    ("thinking/debugging", r'''I'm using importlib.reload() to hot-reload a module but changes don't take effect:

```python
import importlib
import config

def reload_config():
    importlib.reload(config)
    print(f"Reloaded! DB_URL = {config.DB_URL}")

# config.py:
# DB_URL = "postgres://localhost/mydb"
# MAX_CONNECTIONS = 10
```

After editing config.py to change DB_URL, I call reload_config(). It prints the new value. But my application still uses the old value:

```python
# worker.py
from config import DB_URL, MAX_CONNECTIONS

class Worker:
    def __init__(self):
        self.db = connect(DB_URL)  # still uses old value after reload!
```

Why doesn't the reload propagate?''', r'''<think>
This is a subtle but important issue. When worker.py does `from config import DB_URL, MAX_CONNECTIONS`, it creates new names `DB_URL` and `MAX_CONNECTIONS` in the worker module's namespace. These are bound to the string/integer objects that existed at import time.

When you call `importlib.reload(config)`, it re-executes config.py, which creates new string/integer objects and rebinds the names in the `config` module's namespace. But worker.py's `DB_URL` is still bound to the old string object. The reload does not update references in other modules.

The fix: either import the module itself (not individual names), or use a configuration object that can be mutated.
</think>

The issue is how Python's import system binds names. When you write:

```python
from config import DB_URL, MAX_CONNECTIONS
```

Python creates two new name bindings in `worker.py`'s namespace: `DB_URL` points to the string object `"postgres://localhost/mydb"` and `MAX_CONNECTIONS` points to the integer `10`. These are **copies of the references**, not live links to the config module.

When `importlib.reload(config)` runs, it re-executes `config.py` and updates the names inside the `config` module object. But `worker.py`'s `DB_URL` is a separate name binding that still points to the old string.

**Analogy:** It is like copying a phone number from a contact card. If the contact card is updated, your copy does not magically change.

**Fix 1: Import the module, not individual names**

```python
# worker.py
import config  # import the module object

class Worker:
    def __init__(self):
        self.db = connect(config.DB_URL)  # always reads from module
```

Now `config.DB_URL` goes through the module object to look up the name, so it always gets the current value after a reload.

**Fix 2: Use a mutable configuration object**

```python
# config.py
class Config:
    DB_URL = "postgres://localhost/mydb"
    MAX_CONNECTIONS = 10

config = Config()
```

```python
# worker.py
from config import config  # import the mutable object

class Worker:
    def __init__(self):
        self.db = connect(config.DB_URL)  # reads attribute from object
```

Since you imported the Config instance (a mutable object), any changes to its attributes are visible everywhere that holds a reference to it.

**Fix 3: Use a callback/observer pattern for hot reload**

```python
# config.py
import importlib

_subscribers = []

def subscribe(callback):
    _subscribers.append(callback)

def reload():
    import config as self_module
    importlib.reload(self_module)
    for callback in _subscribers:
        callback(self_module)
```

```python
# worker.py
import config

class Worker:
    def __init__(self):
        self.db_url = config.DB_URL
        self.db = connect(self.db_url)
        config.subscribe(self._on_config_reload)

    def _on_config_reload(self, new_config):
        if new_config.DB_URL != self.db_url:
            self.db_url = new_config.DB_URL
            self.db = connect(self.db_url)
```

**Other pitfalls of importlib.reload():**

- Classes instantiated before reload still use the old class definition
- `isinstance()` checks may fail because old and new classes are different objects
- Submodules are NOT reloaded automatically -- you must reload the entire chain
- Module-level side effects (like registering handlers) run again

**Prevention tips:**
- Avoid `from module import name` for anything that might be reloaded
- Use environment variables or config files read at runtime instead of module-level constants
- Consider `watchdog` or `watchfiles` for automatic file change detection
- In production, prefer restarting the process over hot-reloading -- it is safer'''),

    ("thinking/debugging", r'''My namespace package is interfering with a third-party package:

```
ImportError: cannot import name 'utils' from 'mycompany' (unknown location)
```

We have two internal packages installed:

```
mycompany-auth/
  mycompany/
    auth/
      __init__.py
      client.py

mycompany-utils/
  mycompany/
    utils/
      __init__.py
      helpers.py
```

Both are installed via pip. The intent is that `mycompany` is a namespace package so both can coexist as `mycompany.auth` and `mycompany.utils`. But importing fails:

```python
from mycompany.auth import AuthClient  # works
from mycompany.utils import helpers    # ImportError!
```

One package has an __init__.py in mycompany/ and the other doesn't. What's wrong?''', r'''<think>
Namespace packages (PEP 420) work by NOT having an `__init__.py` in the shared parent directory. When Python finds a directory without `__init__.py`, it treats it as a namespace package and continues searching other paths for additional portions.

But if ANY portion of the namespace has an `__init__.py` in the parent `mycompany/` directory, Python treats it as a regular package and stops looking. Other portions become invisible.

The user says "One package has an __init__.py in mycompany/ and the other doesn't." This is exactly the problem. The package with `__init__.py` in `mycompany/` "claims" the namespace, and the other package's `mycompany/` directory is never searched.

The fix: remove ALL `__init__.py` files from the `mycompany/` directory in both packages. Only the subdirectories (auth/, utils/) should have `__init__.py`.
</think>

The problem is that one of your packages has an `__init__.py` file in the `mycompany/` directory, which breaks namespace package discovery for all other portions.

**How namespace packages work (PEP 420):**

When Python encounters a directory WITHOUT `__init__.py` during import, it creates a namespace package. Python continues searching all paths in `sys.path` for additional directories with the same name. Multiple directories are merged into a single namespace.

When Python encounters a directory WITH `__init__.py`, it creates a regular package and **stops searching**. Only that single directory is used.

**Your situation:**

```
site-packages/
  mycompany-auth/
    mycompany/
      __init__.py      # <-- THIS IS THE PROBLEM
      auth/
        __init__.py
        client.py
  mycompany-utils/
    mycompany/
                       # no __init__.py here (correct for namespace)
      utils/
        __init__.py
        helpers.py
```

Python finds `mycompany/` in `mycompany-auth` first, sees `__init__.py`, treats it as a regular package, and stops. It never looks at `mycompany-utils/mycompany/`. Therefore, `mycompany.utils` is invisible.

**Fix: Remove __init__.py from ALL mycompany/ directories**

```
mycompany-auth/
  mycompany/           # NO __init__.py!
    auth/
      __init__.py
      client.py

mycompany-utils/
  mycompany/           # NO __init__.py!
    utils/
      __init__.py
      helpers.py
```

**Update setup.py or pyproject.toml:**

```python
# setup.py for mycompany-auth
from setuptools import setup, find_namespace_packages

setup(
    name='mycompany-auth',
    packages=find_namespace_packages(),  # NOT find_packages()!
    # ...
)
```

Or with pyproject.toml:

```toml
[tool.setuptools.packages.find]
namespaces = true
```

**Critical difference:**
- `find_packages()` requires `__init__.py` everywhere -- wrong for namespace packages
- `find_namespace_packages()` works without `__init__.py` in the shared parent

**Verify it works:**

```python
import mycompany
print(mycompany.__path__)
# Should show BOTH paths:
# _NamespacePath(['.../mycompany-auth/mycompany', '.../mycompany-utils/mycompany'])
```

If it shows only one path, the fix has not been applied correctly.

**Prevention tips:**
- Establish a company-wide rule: namespace package parents NEVER have `__init__.py`
- Use `find_namespace_packages()` in ALL packages that share a namespace
- Add a CI check that validates no `__init__.py` exists in the namespace root
- Document the namespace convention in your internal packaging guide
- Test namespace imports in CI after installing all related packages together'''),

    ("thinking/debugging", r'''My sys.path manipulation is causing import conflicts:

```python
import sys
sys.path.insert(0, '/opt/app/vendor')
sys.path.insert(0, '/opt/app/lib')

import requests  # Which requests gets imported?
```

We vendor some dependencies in /opt/app/vendor/ but the system also has them installed. Users report that sometimes the wrong version loads:

```
>>> import requests
>>> requests.__version__
'2.25.1'  # Expected '2.31.0' from our vendor directory
>>> requests.__file__
'/usr/lib/python3.10/site-packages/requests/__init__.py'  # WRONG!
```

Despite sys.path having our vendor directory first, the system version is loaded. Why?''', r'''<think>
There are several possible reasons why sys.path manipulation is not working as expected:

1. The module was already imported before sys.path was modified. Python caches imported modules in sys.modules. Once requests is imported, subsequent imports return the cached version regardless of sys.path.

2. .pth files in site-packages might be adding paths before the script runs

3. The vendor directory might not have the package installed correctly (no __init__.py, wrong structure)

4. PYTHONPATH environment variable might be prepending paths

5. The import might be happening in a different process or at a different point in startup

The most likely cause is #1 -- the module was already imported (perhaps by another module's import chain) before the sys.path.insert() calls.

Let me also consider: could there be a .pth file or sitecustomize.py that imports requests early?
</think>

The most likely cause is that `requests` was already imported before your `sys.path.insert()` runs. Python caches all imported modules in `sys.modules`. Once a module is cached, all subsequent `import` statements return the cached version, completely ignoring `sys.path`.

**How to diagnose:**

```python
import sys

# Check if requests is already cached BEFORE your path manipulation
print('requests' in sys.modules)  # If True, it was imported earlier!
print(sys.modules.get('requests'))

sys.path.insert(0, '/opt/app/vendor')
import requests  # Returns cached version, ignores sys.path!
```

**Common causes of early imports:**

1. A `.pth` file in `site-packages/` that triggers an import
2. `sitecustomize.py` or `usercustomize.py` importing packages at startup
3. Another module in your import chain importing `requests` before your path setup
4. PYTHONPATH or PYTHONSTARTUP loading modules early

**Fix 1: Manipulate sys.path before ANY imports**

```python
# This MUST be the very first thing in your entry point script
import sys
sys.path.insert(0, '/opt/app/vendor')
sys.path.insert(0, '/opt/app/lib')

# Now import everything else
import requests
```

**Fix 2: Force reimport by clearing sys.modules**

```python
import sys

sys.path.insert(0, '/opt/app/vendor')

# Remove the cached module and all its submodules
for key in list(sys.modules.keys()):
    if key == 'requests' or key.startswith('requests.'):
        del sys.modules[key]

import requests  # Now it searches sys.path fresh
print(requests.__version__)  # Should be the vendor version
```

**Fix 3: Use importlib to import from a specific path**

```python
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "requests",
    "/opt/app/vendor/requests/__init__.py",
    submodule_search_locations=["/opt/app/vendor/requests"]
)
requests = importlib.util.module_from_spec(spec)
sys.modules['requests'] = requests
spec.loader.exec_module(requests)
```

**Fix 4: Use virtual environments instead of vendoring (best practice)**

```bash
python -m venv /opt/app/venv
/opt/app/venv/bin/pip install requests==2.31.0
# Run with: /opt/app/venv/bin/python app.py
```

Virtual environments isolate the entire import namespace, eliminating conflicts with system packages.

**Fix 5: Use the -S flag to skip site-packages**

```bash
python -S -c "
import sys
sys.path.insert(0, '/opt/app/vendor')
import requests
print(requests.__version__)
"
```

The `-S` flag prevents Python from processing `site-packages` and `.pth` files at startup.

**Prevention tips:**
- Prefer virtual environments over sys.path manipulation
- If you must vendor, do it in a uniquely-named directory and import early
- Never modify sys.path after other modules have been imported
- Use `python -v` to see every import as it happens and find the early import
- Consider using `importlib.metadata` to verify package versions at startup'''),
]
