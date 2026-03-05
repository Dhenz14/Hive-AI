"""Git — advanced workflows, hooks, bisect, and collaboration patterns."""

PAIRS = [
    (
        "devops/git-workflows",
        "Show advanced Git workflow patterns: branching strategies, merge vs rebase, cherry-pick, and release management.",
        '''Advanced Git workflow patterns:

```bash
# --- Branching strategy (trunk-based with feature flags) ---

# Feature branch workflow
git checkout -b feature/user-auth
# ... make commits ...
git push -u origin feature/user-auth
# Create PR, get review, merge via GitHub

# Release branches (for versioned releases)
git checkout -b release/v2.1 main
# Cherry-pick specific fixes
git cherry-pick abc1234
git cherry-pick def5678
git tag v2.1.0
git push origin release/v2.1 --tags


# --- Interactive rebase (clean up before merge) ---

# Squash last 5 commits into meaningful ones
git rebase -i HEAD~5
# In editor:
# pick abc1234 Add user model
# squash def5678 Fix typo in user model
# squash 123abcd Add validation
# pick 456defg Add user API endpoints
# squash 789ghij Fix endpoint tests

# Rebase onto latest main (before PR merge)
git fetch origin
git rebase origin/main
# Resolve conflicts if any, then:
git rebase --continue
# Or abort:
git rebase --abort


# --- Cherry-pick (selective commit porting) ---

# Pick specific commit to current branch
git cherry-pick abc1234

# Pick range of commits
git cherry-pick abc1234..def5678

# Cherry-pick without committing (stage changes only)
git cherry-pick --no-commit abc1234

# Cherry-pick with conflict resolution
git cherry-pick abc1234
# If conflict:
# Edit files to resolve
git add resolved_file.py
git cherry-pick --continue


# --- Bisect (find the commit that introduced a bug) ---

git bisect start
git bisect bad                    # Current commit is broken
git bisect good v2.0.0            # v2.0.0 was working

# Git checks out middle commit — test it
# If this commit is good:
git bisect good
# If this commit is bad:
git bisect bad
# Repeat until Git finds the first bad commit

# Automated bisect with a test script
git bisect start HEAD v2.0.0
git bisect run python -m pytest tests/test_auth.py -x
# Git automatically runs test at each step

git bisect reset  # Return to original state


# --- Stash workflows ---

# Save work in progress
git stash push -m "WIP: auth refactor"

# Stash specific files
git stash push -m "WIP: styles" -- src/styles.css src/theme.ts

# List stashes
git stash list
# stash@{0}: On feature/auth: WIP: auth refactor
# stash@{1}: On main: WIP: styles

# Apply and drop
git stash pop stash@{0}

# Apply without dropping (keep in stash)
git stash apply stash@{0}

# Create branch from stash
git stash branch feature/from-stash stash@{0}


# --- Useful log formats ---

# Compact one-line log
git log --oneline --graph --all -20

# Find commits touching specific file
git log --follow -p -- src/auth.py

# Find commits by message content
git log --grep="fix.*auth" -i --oneline

# Find commits that changed specific code
git log -S "def authenticate" --oneline

# Commits between two dates
git log --after="2024-01-01" --before="2024-02-01" --oneline

# See who changed each line
git blame -L 10,20 src/auth.py

# Show file at specific commit
git show abc1234:src/auth.py


# --- Cleanup ---

# Remove merged branches
git branch --merged main | grep -v "main" | xargs git branch -d

# Prune remote tracking branches
git fetch --prune

# Remove untracked files (dry run first!)
git clean -nd    # Show what would be deleted
git clean -fd    # Actually delete

# Reduce repo size
git gc --aggressive
git reflog expire --expire=30.days --all
git gc --prune=30.days
```

Git workflow patterns:
1. **`rebase -i`** — squash/reorder commits for clean PR history
2. **`bisect run`** — automated binary search for bug-introducing commit
3. **`cherry-pick`** — port specific fixes to release branches
4. **`stash push -m`** — named stashes for organized work-in-progress
5. **`log -S`** — "pickaxe" search finds commits that added/removed specific code'''
    ),
    (
        "devops/git-hooks",
        "Show Git hooks patterns: pre-commit linting, commit message validation, and CI integration hooks.",
        '''Git hooks patterns:

```bash
#!/usr/bin/env bash
# --- .git/hooks/pre-commit ---
# (Or use pre-commit framework: https://pre-commit.com)

set -euo pipefail

echo "Running pre-commit checks..."

# Get staged files
STAGED_PY=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.py$' || true)
STAGED_TS=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.(ts|tsx)$' || true)
STAGED_ALL=$(git diff --cached --name-only --diff-filter=ACM)

# Check for secrets/credentials
if echo "$STAGED_ALL" | xargs grep -lE '(password|secret|api_key|token)\s*=\s*["\x27][^\s]+' 2>/dev/null; then
    echo "ERROR: Possible hardcoded secrets detected!"
    echo "Use environment variables or a secrets manager instead."
    exit 1
fi

# Check for large files (> 5MB)
for file in $STAGED_ALL; do
    if [ -f "$file" ]; then
        size=$(wc -c < "$file")
        if [ "$size" -gt 5242880 ]; then
            echo "ERROR: $file is too large ($(( size / 1024 / 1024 ))MB). Use Git LFS."
            exit 1
        fi
    fi
done

# Python: format and lint
if [ -n "$STAGED_PY" ]; then
    echo "Checking Python files..."
    echo "$STAGED_PY" | xargs ruff check --fix
    echo "$STAGED_PY" | xargs ruff format --check
    # Re-add formatted files
    echo "$STAGED_PY" | xargs git add
fi

# TypeScript: lint
if [ -n "$STAGED_TS" ]; then
    echo "Checking TypeScript files..."
    echo "$STAGED_TS" | xargs npx eslint --fix
    echo "$STAGED_TS" | xargs git add
fi

echo "Pre-commit checks passed!"
```

```bash
#!/usr/bin/env bash
# --- .git/hooks/commit-msg ---

set -euo pipefail

COMMIT_MSG_FILE="$1"
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Conventional commit format
# type(scope): description
# Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore
PATTERN="^(feat|fix|docs|style|refactor|perf|test|build|ci|chore)(\([a-z0-9-]+\))?: .{1,72}$"

# Check first line
FIRST_LINE=$(head -1 "$COMMIT_MSG_FILE")

if ! echo "$FIRST_LINE" | grep -Eq "$PATTERN"; then
    echo "ERROR: Invalid commit message format."
    echo ""
    echo "Expected: type(scope): description"
    echo "Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore"
    echo "Example: feat(auth): add OAuth2 login with Google"
    echo ""
    echo "Your message: $FIRST_LINE"
    exit 1
fi

# Check description length
DESC_LENGTH=$(echo "$FIRST_LINE" | wc -c)
if [ "$DESC_LENGTH" -gt 72 ]; then
    echo "ERROR: First line must be 72 characters or fewer (got $DESC_LENGTH)"
    exit 1
fi

echo "Commit message format OK"
```

```yaml
# --- .pre-commit-config.yaml (pre-commit framework) ---

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=5000']
      - id: detect-private-key
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.56.0
    hooks:
      - id: eslint
        types: [javascript, typescript]
        additional_dependencies:
          - eslint@8.56.0
          - '@typescript-eslint/parser@7.0.0'
          - '@typescript-eslint/eslint-plugin@7.0.0'

  - repo: https://github.com/commitizen-tools/commitizen
    rev: v3.16.0
    hooks:
      - id: commitizen
        stages: [commit-msg]
```

```bash
# Setup pre-commit framework
pip install pre-commit
pre-commit install                    # Install pre-commit hook
pre-commit install --hook-type commit-msg  # Install commit-msg hook
pre-commit run --all-files            # Run on all files (first time)
pre-commit autoupdate                 # Update hook versions
```

Git hooks patterns:
1. **Pre-commit** — lint, format, and check for secrets before every commit
2. **Conventional commits** — enforce `type(scope): description` via commit-msg hook
3. **pre-commit framework** — declarative YAML config for multi-language hooks
4. **Large file detection** — prevent accidental commits of binaries/data files
5. **Auto-format + re-stage** — format code then `git add` changed files automatically'''
    ),
]
"""
