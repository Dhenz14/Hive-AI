"""Git advanced — workflows, hooks, bisect, rebase strategies, and monorepo patterns."""

PAIRS = [
    (
        "devops/git-workflows",
        "Show Git workflow patterns: trunk-based development, Git Flow, feature flags, and branch protection strategies.",
        '''Git workflows for team development:

```bash
# --- Trunk-based development (recommended for CI/CD) ---

# Short-lived feature branches, merge to main frequently
git checkout -b feature/add-search main
# ... make changes, commit
git push -u origin feature/add-search
# Create PR, get review, merge to main
# Branch lives < 2 days

# --- Feature branch with rebase (clean history) ---

# Start feature
git checkout -b feature/user-auth main

# Work on feature...
git add . && git commit -m "Add login endpoint"
git add . && git commit -m "Add JWT token generation"

# Before merging, rebase onto latest main
git fetch origin
git rebase origin/main

# If conflicts:
# Fix conflicts in each file
git add <resolved-files>
git rebase --continue

# Force push rebased branch (OK for feature branches)
git push --force-with-lease origin feature/user-auth

# Create PR and merge (with squash or merge commit)


# --- Useful Git commands ---

# Interactive rebase to clean up commits before PR
git rebase -i HEAD~5
# In editor: pick, squash, reword, drop, fixup

# Fixup commit (auto-squash later)
git commit --fixup=<commit-hash>
git rebase -i --autosquash main

# Cherry-pick specific commits
git cherry-pick abc123 def456

# Stash with message
git stash push -m "WIP: auth refactor"
git stash list
git stash pop stash@{0}

# Find which commit introduced a bug
git bisect start
git bisect bad HEAD
git bisect good v1.0.0
# Git checks out middle commit, you test, mark good/bad
git bisect good  # or git bisect bad
# Repeat until the bad commit is found
git bisect reset

# Automated bisect with test script
git bisect start HEAD v1.0.0
git bisect run pytest tests/test_auth.py

# View file at specific commit
git show abc123:src/auth.py

# Blame with ignore whitespace
git blame -w src/auth.py

# Find commits that changed a function
git log -p -S "def authenticate" -- "*.py"
git log --all --oneline -- src/auth.py
```

```yaml
# --- Branch protection (GitHub) ---
# .github/settings.yml (probot/settings app)

branches:
  - name: main
    protection:
      required_status_checks:
        strict: true
        contexts:
          - "test"
          - "lint"
          - "build"
      required_pull_request_reviews:
        required_approving_review_count: 1
        dismiss_stale_reviews: true
        require_code_owner_reviews: true
      enforce_admins: true
      required_linear_history: true
      restrictions: null
```

```
# --- CODEOWNERS file ---
# .github/CODEOWNERS

# Default owners
*                       @team-leads

# Specific paths
/src/auth/              @security-team
/src/api/               @backend-team
/src/frontend/          @frontend-team
/infrastructure/        @devops-team
/.github/workflows/     @devops-team
/docs/                  @docs-team
```

Workflow comparison:
- **Trunk-based** — merge to main daily, feature flags for incomplete work
- **GitHub Flow** — main + feature branches, deploy from main
- **Git Flow** — develop + feature + release + hotfix branches (complex)

Best practices:
1. **Small PRs** — easier to review, fewer conflicts, faster feedback
2. **Rebase before merge** — clean, linear history
3. **Squash merge** — one commit per feature in main
4. **Branch protection** — require reviews, CI passing, linear history
5. **CODEOWNERS** — automatic review assignment by file path'''
    ),
    (
        "devops/git-hooks",
        "Show Git hooks patterns: pre-commit validation, commit message standards, and automated checks with pre-commit framework.",
        '''Git hooks for code quality automation:

```yaml
# .pre-commit-config.yaml
repos:
  # General hooks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: detect-private-key
      - id: no-commit-to-branch
        args: ['--branch', 'main']

  # Python formatting
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: ['--fix']
      - id: ruff-format

  # Type checking
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: ['types-requests']

  # Security
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.7
    hooks:
      - id: bandit
        args: ['-c', 'pyproject.toml']

  # Secrets detection
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks

  # Commit message format
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.1.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        args: [feat, fix, docs, style, refactor, test, chore, ci]
```

```bash
# Setup pre-commit
pip install pre-commit
pre-commit install                      # Install pre-commit hook
pre-commit install --hook-type commit-msg  # Install commit-msg hook
pre-commit run --all-files              # Run on all files (first time)

# Skip hooks temporarily (use sparingly)
git commit --no-verify -m "WIP: debugging"

# Update hooks
pre-commit autoupdate
```

```bash
# --- Custom Git hooks ---

# .githooks/pre-push — prevent pushing to main directly
#!/usr/bin/env bash
protected_branch="main"
current_branch=$(git symbolic-ref HEAD | sed -e 's,.*/\\(.*\\),\\1,')

if [ "$current_branch" = "$protected_branch" ]; then
    echo "ERROR: Cannot push directly to $protected_branch"
    echo "Create a pull request instead."
    exit 1
fi

# Check for TODO/FIXME in staged changes
if git diff --cached --name-only | xargs grep -l "TODO\\|FIXME\\|HACK" 2>/dev/null; then
    echo "WARNING: Found TODO/FIXME/HACK markers in staged files"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi
```

```python
# --- Conventional commit message format ---

# Format: <type>(<scope>): <subject>
#
# Types:
#   feat:     New feature
#   fix:      Bug fix
#   docs:     Documentation only
#   style:    Formatting, no code change
#   refactor: Code change, no feature/fix
#   test:     Adding tests
#   chore:    Build, CI, tooling changes
#   ci:       CI configuration changes
#
# Examples:
#   feat(auth): add OAuth2 login with Google
#   fix(api): handle null response from payment provider
#   refactor(db): migrate from raw SQL to SQLAlchemy
#   test(orders): add integration tests for checkout flow
#   chore(deps): update FastAPI to 0.110

# Breaking changes:
#   feat(api)!: change authentication to use Bearer tokens
#   BREAKING CHANGE: API now requires Bearer token in Authorization header
```

Hook workflow:
1. **pre-commit** — format, lint, type check, detect secrets before commit
2. **commit-msg** — enforce conventional commit message format
3. **pre-push** — prevent direct push to main, run tests
4. **post-merge** — auto-install dependencies after pulling
5. **Framework** — use `pre-commit` tool for portable, shareable hooks'''
    ),
]
"""
