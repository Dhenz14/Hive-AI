"""Advanced Git — rebase strategies, hooks, monorepo, worktrees."""

PAIRS = [
    (
        "tools/git-rebase-strategies",
        "Show Git rebase strategies: interactive rebase, fixup commits, autosquash, and rebase onto for branch management.",
        '''Git rebase strategies:

```bash
# Interactive rebase — clean up commit history before merge
git rebase -i HEAD~5
# Opens editor with:
# pick abc1234 Add user model
# pick def5678 Fix typo in model      ← squash into previous
# pick ghi9012 Add user API            ← keep
# pick jkl3456 WIP: debugging          ← drop
# pick mno7890 Add user tests          ← reorder

# Change to:
# pick abc1234 Add user model
# fixup def5678 Fix typo in model    ← merge into above, discard message
# pick ghi9012 Add user API
# pick mno7890 Add user tests       ← moved up
# drop jkl3456 WIP: debugging       ← removed

# Autosquash workflow — mark fixup commits during development
git commit --fixup abc1234     # Creates "fixup! Add user model"
git commit --fixup abc1234     # Another fixup for same commit
git rebase -i --autosquash HEAD~5  # Automatically reorders and marks fixup

# Rebase onto — move branch to different base
# Before: main → A → B → feature (branched from B)
# Want: main → A → B → C → D → feature (rebase onto latest main)
git rebase --onto main feature~3 feature  # Move last 3 commits onto main

# Rebase with conflict resolution strategy
git rebase -i main --strategy-option theirs  # Auto-resolve favoring our changes

# Preserve merge commits during rebase
git rebase --rebase-merges main

# Abort if things go wrong
git rebase --abort

# After resolving conflicts
git add .
git rebase --continue
```

```python
# Git hook: pre-commit (runs before each commit)
#!/usr/bin/env python3
# .git/hooks/pre-commit

import subprocess
import sys

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

# Check for debug statements
code, out, _ = run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"])
staged_files = [f for f in out.strip().split("\\n") if f.endswith(".py")]

for f in staged_files:
    with open(f) as fh:
        for i, line in enumerate(fh, 1):
            if "breakpoint()" in line or "import pdb" in line:
                print(f"ERROR: Debug statement in {f}:{i}")
                sys.exit(1)

# Run linting on staged files
if staged_files:
    code, _, err = run(["ruff", "check"] + staged_files)
    if code != 0:
        print(f"Linting failed:\\n{err}")
        sys.exit(1)

# Run type checking
code, _, err = run(["mypy"] + staged_files)
if code != 0:
    print(f"Type errors:\\n{err}")
    sys.exit(1)
```

Key patterns:
1. **Interactive rebase** — squash, fixup, reorder, drop commits for clean history
2. **Autosquash** — `--fixup` during development + `--autosquash` at cleanup time
3. **Rebase onto** — transplant commits to different base; useful for branch management
4. **Pre-commit hooks** — catch debug statements, lint errors, type errors before commit
5. **Conflict strategy** — `--strategy-option theirs/ours` for automated conflict resolution'''
    ),
    (
        "tools/git-worktrees",
        "Show Git worktrees: parallel development, managing multiple branches simultaneously, and monorepo strategies.",
        '''Git worktrees and monorepo patterns:

```bash
# Git worktrees — work on multiple branches simultaneously
# Main checkout stays on main
git worktree add ../feature-auth feature/auth
git worktree add ../hotfix-123 hotfix/123

# List active worktrees
git worktree list
# /home/user/project          abc1234 [main]
# /home/user/feature-auth     def5678 [feature/auth]
# /home/user/hotfix-123       ghi9012 [hotfix/123]

# Remove worktree when done
git worktree remove ../feature-auth

# Create worktree for new branch
git worktree add -b feature/new-api ../new-api main

# Prune stale worktree references
git worktree prune
```

```python
# Monorepo management with sparse checkout
import subprocess
from pathlib import Path


class MonorepoManager:
    """Manage monorepo with sparse checkout for large repos."""

    def __init__(self, repo_path: str):
        self.repo = Path(repo_path)

    def setup_sparse_checkout(self, packages: list[str]):
        """Only checkout specified packages for faster clone."""
        subprocess.run(["git", "sparse-checkout", "init", "--cone"],
                       cwd=self.repo)
        subprocess.run(["git", "sparse-checkout", "set"] + packages,
                       cwd=self.repo)

    def get_changed_packages(self, base_ref: str = "main") -> list[str]:
        """Find which packages have changes (for selective CI)."""
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True, text=True, cwd=self.repo,
        )
        changed_files = result.stdout.strip().split("\\n")

        # Extract package names from file paths
        packages = set()
        for f in changed_files:
            parts = Path(f).parts
            if len(parts) >= 2 and parts[0] == "packages":
                packages.add(parts[1])

        return sorted(packages)

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Build dependency graph between packages."""
        import json
        graph = {}
        for pkg_dir in (self.repo / "packages").iterdir():
            if not pkg_dir.is_dir():
                continue
            pkg_json = pkg_dir / "package.json"
            if pkg_json.exists():
                data = json.loads(pkg_json.read_text())
                deps = list(data.get("dependencies", {}).keys())
                # Filter to local workspace packages
                local_deps = [d.replace("@myorg/", "")
                              for d in deps if d.startswith("@myorg/")]
                graph[pkg_dir.name] = local_deps
        return graph

    def get_affected_packages(self, changed: list[str]) -> list[str]:
        """Get all packages affected by changes (including dependents)."""
        graph = self.get_dependency_graph()
        affected = set(changed)
        changed_set = True

        while changed_set:
            changed_set = False
            for pkg, deps in graph.items():
                if pkg not in affected and any(d in affected for d in deps):
                    affected.add(pkg)
                    changed_set = True

        return sorted(affected)
```

Key patterns:
1. **Worktrees** — separate directories for each branch; no stashing/switching needed
2. **Sparse checkout** — only download relevant packages in large monorepos
3. **Changed package detection** — diff against base ref to find modified packages
4. **Dependency graph** — know which packages depend on which; build affected set
5. **Selective CI** — only test/build packages affected by changes; faster pipelines'''
    ),
]
"""
