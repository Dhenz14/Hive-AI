"""Development workflow — Git patterns, code review, and documentation."""

PAIRS = [
    (
        "workflow/git-advanced",
        "Show advanced Git patterns: branching strategies, interactive rebase, bisect, worktrees, and hooks.",
        '''Advanced Git patterns:

```bash
# --- Branching strategy (GitHub Flow) ---

# Create feature branch
git checkout -b feature/user-auth main

# Work on feature with atomic commits
git add src/auth.py tests/test_auth.py
git commit -m "Add JWT token generation and validation"

git add src/middleware.py
git commit -m "Add authentication middleware with token refresh"

git add src/routes/login.py tests/test_login.py
git commit -m "Add login endpoint with rate limiting"

# Push and create PR
git push -u origin feature/user-auth
gh pr create --title "Add user authentication" --body "..."


# --- Interactive rebase (clean up before PR) ---

# Squash/reword last 3 commits
git rebase -i HEAD~3

# In editor:
# pick abc1234 Add JWT token generation
# squash def5678 Fix typo in token validation
# squash ghi9012 Add missing test case

# Rebase onto updated main
git fetch origin
git rebase origin/main

# If conflicts:
# 1. Fix conflicts in files
# 2. git add <fixed files>
# 3. git rebase --continue
# To abort: git rebase --abort


# --- Git bisect (find bug-introducing commit) ---

git bisect start
git bisect bad                    # Current commit is broken
git bisect good v1.2.0           # This version was working

# Git checks out middle commit — test it
# If broken:
git bisect bad
# If working:
git bisect good

# Automated bisect with test script:
git bisect start HEAD v1.2.0
git bisect run pytest tests/test_auth.py -x

# When done:
git bisect reset


# --- Worktrees (work on multiple branches simultaneously) ---

# Create worktree for hotfix while keeping feature branch
git worktree add ../hotfix-branch hotfix/critical-fix

# Work in hotfix directory
cd ../hotfix-branch
# ... make fixes ...
git commit -m "Fix critical auth bypass"
git push

# Remove when done
git worktree remove ../hotfix-branch


# --- Stash patterns ---

# Stash with message
git stash push -m "WIP: auth refactor"

# Stash specific files
git stash push -m "WIP: just the config" -- src/config.py

# List and apply
git stash list
git stash apply stash@{0}    # Apply without removing
git stash pop stash@{0}      # Apply and remove

# Create branch from stash
git stash branch feature/from-stash stash@{0}


# --- Cherry-pick ---

# Apply specific commit to current branch
git cherry-pick abc1234

# Cherry-pick range
git cherry-pick abc1234..def5678

# Cherry-pick without committing (stage changes only)
git cherry-pick --no-commit abc1234


# --- Pre-commit hooks ---
# .pre-commit-config.yaml

# repos:
#   - repo: https://github.com/astral-sh/ruff-pre-commit
#     rev: v0.4.0
#     hooks:
#       - id: ruff
#         args: [--fix]
#       - id: ruff-format
#
#   - repo: https://github.com/pre-commit/pre-commit-hooks
#     rev: v4.6.0
#     hooks:
#       - id: trailing-whitespace
#       - id: end-of-file-fixer
#       - id: check-yaml
#       - id: check-added-large-files
#         args: [--maxkb=500]
#       - id: detect-private-key
#
#   - repo: https://github.com/pre-commit/mirrors-mypy
#     rev: v1.10.0
#     hooks:
#       - id: mypy
#         additional_dependencies: [types-requests]


# --- Useful aliases (.gitconfig) ---

# [alias]
#   co = checkout
#   br = branch
#   ci = commit
#   st = status -sb
#   lg = log --oneline --graph --decorate -20
#   undo = reset --soft HEAD~1
#   amend = commit --amend --no-edit
#   wip = !git add -A && git commit -m "WIP"
#   cleanup = !git branch --merged main | grep -v main | xargs git branch -d
```

Git patterns:
1. **Interactive rebase** — squash/reword commits before merging PR
2. **`git bisect run`** — automated binary search for bug-introducing commit
3. **Worktrees** — work on multiple branches without stashing
4. **Pre-commit hooks** — auto-lint, format, and check before every commit
5. **Cherry-pick** — apply specific commits across branches'''
    ),
    (
        "workflow/code-review",
        "Show code review patterns: PR templates, review checklists, and automated checks.",
        '''Code review patterns:

```markdown
<!-- .github/pull_request_template.md -->

## Summary
<!-- What does this PR do? Why is it needed? -->

## Changes
<!-- List key changes -->
-

## Test Plan
<!-- How was this tested? -->
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] No unnecessary changes included
- [ ] Documentation updated (if applicable)
- [ ] No secrets or credentials in code

## Screenshots
<!-- If UI changes, add before/after screenshots -->
```

```python
# --- Automated review checks ---

# .github/workflows/pr-checks.yml equivalent logic

import subprocess
import sys
from pathlib import Path


def run_pr_checks() -> list[str]:
    """Run automated PR checks."""
    issues = []

    # 1. Check for large files
    result = subprocess.run(
        ["git", "diff", "--staged", "--stat"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if "Bin" in line:
            size_str = line.split("Bin")[1].strip().split()[0]
            if int(size_str) > 500_000:
                issues.append(f"Large binary file: {line.split('|')[0].strip()}")

    # 2. Check for secrets
    secret_patterns = [
        r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]+['\"]",
        r"AKIA[0-9A-Z]{16}",  # AWS access key
        r"-----BEGIN (RSA|EC|DSA) PRIVATE KEY-----",
    ]
    import re
    result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True, text=True,
    )
    for pattern in secret_patterns:
        matches = re.findall(pattern, result.stdout)
        if matches:
            issues.append(f"Potential secret detected: {pattern}")

    # 3. Check for TODO/FIXME without ticket
    for line in result.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b(?!.*#\d+)", line):
                issues.append(f"TODO without ticket reference: {line[:80]}")

    # 4. Check test coverage delta
    result = subprocess.run(
        ["pytest", "--cov=app", "--cov-report=json", "-q"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        import json
        coverage = json.loads(Path("coverage.json").read_text())
        total_pct = coverage["totals"]["percent_covered"]
        if total_pct < 80:
            issues.append(f"Test coverage below 80%: {total_pct:.1f}%")

    return issues


# --- Review comment templates ---

REVIEW_COMMENTS = {
    "nit": "nit: {comment}",
    "question": "question: {comment}",
    "suggestion": "suggestion: {comment}\n\n```suggestion\n{code}\n```",
    "blocking": "blocking: {comment}\n\nThis needs to be addressed before merge.",
    "praise": "praise: {comment}",
}


# --- PR size guidelines ---

def check_pr_size() -> str:
    """Categorize PR size and suggest splitting if too large."""
    result = subprocess.run(
        ["git", "diff", "--stat", "origin/main...HEAD"],
        capture_output=True, text=True,
    )

    lines = result.stdout.strip().splitlines()
    if not lines:
        return "empty"

    # Parse summary line
    summary = lines[-1]
    import re
    insertions = int(re.search(r"(\d+) insertion", summary).group(1)
                     if "insertion" in summary else 0)
    deletions = int(re.search(r"(\d+) deletion", summary).group(1)
                    if "deletion" in summary else 0)
    total = insertions + deletions

    if total < 50:
        return "XS - Quick review"
    elif total < 200:
        return "S - Standard review"
    elif total < 500:
        return "M - Careful review needed"
    elif total < 1000:
        return "L - Consider splitting"
    else:
        return "XL - Should be split into smaller PRs"
```

Code review patterns:
1. **PR template** — structured format ensures context and test plans
2. **Automated checks** — secrets, large files, TODOs, coverage in CI
3. **Comment prefixes** — `nit:`, `blocking:`, `question:` clarify severity
4. **PR size limits** — >500 lines should be split for reviewability
5. **Self-review first** — reviewers check their own diff before requesting review'''
    ),
]
