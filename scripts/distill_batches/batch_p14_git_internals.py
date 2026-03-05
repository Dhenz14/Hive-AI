"""p14 git internals"""

PAIRS = [
    (
        "tools/git-internals-object-model",
        "Explain Git's internal object model including blobs, trees, commits, and tags, how content-addressable storage works, the reflog, and how operations like merge, rebase, and cherry-pick manipulate these objects. Include commands for inspecting Git internals.",
        '''Git is fundamentally a content-addressable filesystem with a VCS interface on top. Understanding the internals explains why Git commands behave the way they do and helps debug complex situations.

### The Four Object Types

Everything in Git is stored as one of four object types, each identified by its SHA-1 hash:

```bash
# 1. BLOB -- file contents (no filename, no permissions)
echo "Hello World" | git hash-object --stdin -w
# Returns: 557db03de997c86a4a028e1ebd3a1ceb225be238
# Stored at: .git/objects/55/7db03de997c86a4a028e1ebd3a1ceb225be238

# Inspect any object
git cat-file -t 557db03  # Type: blob
git cat-file -p 557db03  # Contents: Hello World
git cat-file -s 557db03  # Size: 12 bytes

# 2. TREE -- directory listing (maps names to blobs/trees)
git cat-file -p HEAD^{tree}
# 100644 blob abc123...  README.md
# 100755 blob def456...  build.sh
# 040000 tree 789abc...  src

# 3. COMMIT -- snapshot + metadata
git cat-file -p HEAD
# tree 4b825dc642cb6eb9a060e54bf899d15f5e9e
# parent 8a5cbc430f1a9c3d00b678a5e3d1d   (can have 0, 1, or 2+ parents)
# author Dan <dan@example.com> 1709510400 +0000
# committer Dan <dan@example.com> 1709510400 +0000
#
# Initial commit message

# 4. TAG -- annotated tag pointing to an object
git cat-file -p v1.0
# object 8a5cbc430f1a9c3d00b678a5e3d1d
# type commit
# tag v1.0
# tagger Dan <dan@example.com> 1709510400 +0000
#
# Release v1.0
```

### Content-Addressable Storage

The key insight: **identical content always produces the same hash**, regardless of filename:

```bash
# These produce the SAME blob object:
echo "Hello" > file1.txt
echo "Hello" > file2.txt
cp file1.txt file3.txt

# Git stores "Hello" ONCE, referenced from three tree entries
# This is why Git repos are so space-efficient

# How objects are stored:
# 1. Content is prepended with "blob 6\0" (type + size + null byte)
# 2. SHA-1 hash is computed: sha1("blob 6\0Hello\n")
# 3. Content is zlib-compressed
# 4. Stored at .git/objects/XX/YYYYYY (first 2 chars = directory)

# Verify this manually:
printf "blob 6\0Hello\n" | sha1sum
# Should match: git hash-object <(echo "Hello")

# Pack files: Git periodically packs loose objects into .pack files
# for efficiency (delta compression between similar objects)
git gc  # Triggers packing
ls .git/objects/pack/
# pack-XXXXX.idx  (index for fast lookup)
# pack-XXXXX.pack (compressed objects with delta chains)

# Inspect pack file
git verify-pack -v .git/objects/pack/pack-XXXXX.idx
```

### References: Branches, Tags, HEAD

References are just files containing SHA-1 hashes:

```bash
# Branch = file containing a commit hash
cat .git/refs/heads/main
# 8a5cbc430f1a9c3d00b678a5e3d1d...

# HEAD = pointer to current branch (or detached commit)
cat .git/HEAD
# ref: refs/heads/main         (on a branch)
# 8a5cbc430f1a9c3d00b678a5e3d1d  (detached HEAD)

# Tag = file containing an object hash
cat .git/refs/tags/v1.0
# Points to tag object (annotated) or commit (lightweight)

# Remote tracking branches
cat .git/refs/remotes/origin/main

# Symbolic references
git symbolic-ref HEAD  # refs/heads/main
git symbolic-ref HEAD refs/heads/develop  # Switch branch (low-level)
```

### The Reflog: Safety Net

The reflog records every time HEAD or a branch ref changes:

```bash
# View reflog
git reflog
# 8a5cbc4 HEAD@{0}: commit: Add feature X
# 3f2b1a0 HEAD@{1}: checkout: moving from develop to main
# 7d4e5f6 HEAD@{2}: commit: Fix bug Y
# a1b2c3d HEAD@{3}: rebase (finish): refs/heads/develop onto main

# Reflog with timestamps
git reflog --date=iso
# 8a5cbc4 HEAD@{2024-03-01 14:30:00 +0000}: commit: Add feature X

# RECOVERY: Undo a bad rebase/reset
git reflog
# Find the commit BEFORE the bad operation
git reset --hard HEAD@{3}  # Restore to that point

# Reflog entries expire after 90 days (30 for unreachable)
# Override: git config gc.reflogExpire 180.days

# Branch-specific reflog
git reflog show develop
```

### How Merge Works Internally

```bash
# Fast-forward merge: just move the branch pointer
# Before:       A---B---C (main)
#                        \
#                         D---E (feature)
git merge feature
# After:        A---B---C---D---E (main, feature)
# Git just changes .git/refs/heads/main to point to E's hash

# Three-way merge: creates a merge commit
# Before:       A---B---C (main)
#                    \
#                     D---E (feature)
git merge feature
# After:        A---B---C---F (main)
#                    \     /
#                     D---E (feature)
# F is a new commit with TWO parents: C and E
# F's tree is computed by three-way merge of:
#   Base (B) vs Main (C) vs Feature (E)

git cat-file -p HEAD  # Shows two parent lines
# tree ...
# parent <hash-of-C>
# parent <hash-of-E>

# Merge base: the common ancestor
git merge-base main feature  # Returns B's hash
```

### How Rebase Works Internally

```bash
# Rebase replays commits on top of a new base
# Before:       A---B---C (main)
#                    \
#                     D---E (feature)
git checkout feature
git rebase main
# After:        A---B---C (main)
#                        \
#                         D'---E' (feature)

# What actually happens:
# 1. Git identifies commits to replay: D and E
# 2. Saves them as patches (diffs)
# 3. Resets feature branch to C (tip of main)
# 4. Applies D's diff -> creates D' (new hash, same changes)
# 5. Applies E's diff -> creates E' (new hash, same changes)
# 6. Updates feature ref to point to E'

# D and E still exist (unreachable, in reflog for 30 days)
# D' and E' are NEW commits with DIFFERENT hashes
# This is why you shouldn't rebase published commits

# Interactive rebase: reorder, squash, edit commits
git rebase -i HEAD~3
# pick abc1234 First commit
# squash def5678 Second commit (merge into first)
# reword 789abcd Third commit (edit message)
```

### How Cherry-Pick Works

```bash
# Cherry-pick applies a single commit's DIFF to the current branch
git cherry-pick abc1234

# Internally:
# 1. Compute the diff between abc1234 and its parent
# 2. Apply that diff to the current HEAD
# 3. Create a new commit with the same message
# The new commit has a DIFFERENT hash (different parent, tree)

# Cherry-pick with -x: add "(cherry picked from commit ...)" to message
git cherry-pick -x abc1234

# Cherry-pick a range
git cherry-pick A..B  # All commits after A up to and including B
git cherry-pick A^..B # Include A itself
```

### Inspecting and Debugging

```bash
# Trace the full history of a file
git log --follow --all -p -- path/to/file

# Find which commit introduced a string
git log -S "function_name" --source --all

# Find which commit introduced a regex pattern
git log -G "TODO|FIXME|HACK" --source --all

# Binary search for a bug
git bisect start
git bisect bad HEAD
git bisect good v1.0
# Git checks out middle commit, you test, mark good/bad
# Automated:
git bisect run python -m pytest tests/

# Show what's in the staging area (index)
git ls-files --stage
# 100644 abc123... 0    src/app.py
# Stage numbers: 0=normal, 1=base, 2=ours, 3=theirs (during merge)

# Diff between any two trees
git diff-tree --stat HEAD~3 HEAD

# Verify repository integrity
git fsck --full
# Checks all objects, finds dangling/unreachable objects

# Count objects and measure repo size
git count-objects -v
```

```python
# Programmatic Git inspection using gitpython
import subprocess
import json


def get_commit_graph(repo_path: str, max_commits: int = 50) -> dict:
    """Build a commit graph for visualization."""
    result = subprocess.run(
        ["git", "log", f"--max-count={max_commits}",
         "--format=%H|%P|%s|%an|%ai", "--all"],
        cwd=repo_path, capture_output=True, text=True'''
    ),
    (
        "tools/git-advanced-workflows",
        "Explain advanced Git workflows including worktrees for parallel development, sparse checkout for monorepos, Git hooks for automation, interactive staging with patch mode, and stash management patterns.",
        '''These workflows solve real problems that emerge in professional development: working on multiple branches simultaneously, handling massive repositories, automating quality checks, and making precise commits.

### Git Worktrees: Parallel Branch Development

Worktrees let you check out multiple branches simultaneously without cloning:

```bash
# Create a worktree for a feature branch
git worktree add ../feature-auth feature/auth
# Now you have TWO working directories sharing the same .git

# List worktrees
git worktree list
# /home/dev/project          abc1234 [main]
# /home/dev/feature-auth     def5678 [feature/auth]

# Create a worktree with a NEW branch
git worktree add -b hotfix/urgent ../hotfix main
# Creates new branch 'hotfix/urgent' based on 'main'

# Remove a worktree when done
git worktree remove ../feature-auth
# Or just delete the directory and run:
git worktree prune

# Use case: review a PR while your current work is in progress
git worktree add ../pr-review origin/pull/123
cd ../pr-review
# Review, test, then return to your work
cd ../project
git worktree remove ../pr-review
```

```python
# Script to manage worktrees for code review
import subprocess
import tempfile
from pathlib import Path


def review_branch(branch: str, repo_dir: str = ".") -> Path:
    """Create a temporary worktree for reviewing a branch."""
    worktree_dir = Path(tempfile.mkdtemp(prefix=f"review-{branch}-"))

    subprocess.run(
        ["git", "worktree", "add", str(worktree_dir), branch],
        cwd=repo_dir, check=True'''
    ),
    (
        "--include-untracked",
        "check=True ) try: return func(*args, **kwargs) finally: if has_changes: subprocess.run( ['git', 'stash', 'pop'] check=True ) return wrapper @auto_stash def safe_rebase(target_branch: str): subprocess.run(['git', 'rebase', target_branch], check=True) @auto_stash def safe_pull(): subprocess.run(['git', 'pull', '--rebase'], check=True)",
        '''### Useful Aliases

```bash
# Add to ~/.gitconfig or .git/config
[alias]
    # Pretty log graph
    lg = log --graph --oneline --decorate --all -20

    # Show what changed in each commit
    ll = log --stat --oneline -10

    # Amend without changing message
    amend = commit --amend --no-edit

    # Undo last commit (keep changes staged)
    undo = reset --soft HEAD~1

    # Show branches sorted by last commit
    recent = branch --sort=-committerdate --format='%(committerdate:relative)\t%(refname:short)'

    # Delete merged branches
    cleanup = "!git branch --merged main | grep -v main | xargs -r git branch -d"

    # Find commits by message
    find = log --all --grep

    # Diff with word-level highlighting
    wdiff = diff --word-diff=color
```

**Advanced workflow tips**: (1) Use worktrees for code review -- keep your WIP untouched, (2) Sparse checkout + partial clone for monorepos -- only download what you need, (3) Share hooks via `.githooks/` directory committed to the repo, (4) Use `git add -p` for atomic, focused commits -- one logical change per commit, (5) Name stashes descriptively -- unnamed stashes become unidentifiable quickly.'''
    ),
    (
        "tools/git-rebase-strategies",
        "Explain Git rebase strategies including when to rebase vs merge, handling rebase conflicts, autosquash workflow, rebase onto for branch transplanting, and recovering from a bad rebase. Include practical team workflow guidance.",
        '''Rebase is a powerful tool for maintaining a clean project history, but it rewrites commits. Understanding when and how to use it prevents data loss and team friction.

### When to Rebase vs Merge

```
REBASE when:
✓ Updating a feature branch with latest main (before PR)
✓ Cleaning up local commits before pushing (squash, reorder)
✓ Maintaining linear history in a project
✓ You haven't pushed the commits yet (local-only changes)

MERGE when:
✓ Integrating a feature branch into main (PR merge)
✓ Commits are already pushed and shared with others
✓ You want to preserve the exact development timeline
✓ Resolving divergence between long-lived branches

RULE: Never rebase commits that have been pushed to a shared branch
and that other people have based work on.
```

### Clean Rebase Workflow

```bash
# Before creating a PR, update your branch with latest main:

# Step 1: Fetch latest changes
git fetch origin

# Step 2: Rebase your feature branch onto latest main
git checkout feature/my-work
git rebase origin/main

# If there are conflicts:
# 1. Fix the conflicts in the marked files
# 2. Stage the resolved files
git add <resolved-files>
# 3. Continue the rebase
git rebase --continue
# 4. Repeat for each conflicting commit

# If the rebase is going badly and you want to abort:
git rebase --abort
# This restores your branch to its pre-rebase state

# Step 3: Force push (your branch only, never main!)
git push --force-with-lease origin feature/my-work
# --force-with-lease is safer than --force:
# it fails if someone else pushed to the same branch
```

### Autosquash Workflow

Clean up WIP commits before a PR review:

```bash
# During development, make fixup commits:
git commit -m "Add user validation"
# ... later, fixing a bug in the validation ...
git commit --fixup=HEAD      # or --fixup=<commit-hash>
# Creates: "fixup! Add user validation"

# ... adding more to that feature ...
git commit --squash=abc1234
# Creates: "squash! <message of abc1234>"

# Before PR: autosquash rebase
git rebase -i --autosquash origin/main
# fixup! commits are automatically moved next to their target
# and marked as 'fixup' (merge into parent, discard message)
# squash! commits are moved and marked as 'squash'
# (merge into parent, combine messages)

# Enable autosquash by default:
git config --global rebase.autosquash true
```

```bash
# Example interactive rebase session:
git rebase -i HEAD~5

# Editor shows:
pick abc1234 Add user model
pick def5678 Add validation
fixup ghi9012 fixup! Add validation    # Auto-moved by --autosquash
pick jkl3456 Add API endpoint
squash mno7890 squash! Add API endpoint # Auto-moved by --autosquash

# After saving, you get 3 clean commits instead of 5
```

### Rebase --onto for Branch Transplanting

Move a branch from one base to another:

```bash
# Scenario: You branched feature from develop, but it should
# be based on main instead

# Before:
#          A---B---C (main)
#               \
#                D---E (develop)
#                     \
#                      F---G (feature)

git rebase --onto main develop feature

# After:
#          A---B---C (main)
#               \   \
#                \   F'---G' (feature)
#                 \
#                  D---E (develop)

# Another use: remove commits from middle of a branch
# Remove commit D from: A-B-C-D-E-F
git rebase --onto C D F
# Result: A-B-C-E'-F' (D is removed)
```

### Handling Rebase Conflicts

```bash
# When a conflict occurs during rebase:
git rebase origin/main
# CONFLICT in src/app.py

# Check what's conflicting
git status
# both modified:   src/app.py

# Option 1: Fix manually
# Edit the file, resolve <<<<<<< markers
git add src/app.py
git rebase --continue

# Option 2: Accept theirs or ours
git checkout --theirs src/app.py  # Take the main branch version
git checkout --ours src/app.py    # Keep your version
git add src/app.py
git rebase --continue

# Option 3: Use a merge tool
git mergetool

# For repeated conflicts on same files, use rerere (reuse recorded resolution)
git config --global rerere.enabled true
# Git remembers how you resolved each conflict and auto-applies
# the same resolution if it sees the same conflict again

# Skip a commit entirely during rebase (drops the commit)
git rebase --skip
```

### Recovering from a Bad Rebase

```bash
# Method 1: Reflog (safest)
git reflog
# abc1234 HEAD@{0}: rebase (finish): returning to refs/heads/feature
# def5678 HEAD@{1}: rebase (pick): some commit
# ...
# 999aaaa HEAD@{5}: rebase (start): checkout main
# bbb1111 HEAD@{6}: commit: my last good commit  ← THIS ONE

git reset --hard HEAD@{6}  # or use the hash directly

# Method 2: ORIG_HEAD (only works immediately after rebase)
git reset --hard ORIG_HEAD

# Method 3: If you pushed before rebasing
git fetch origin
git reset --hard origin/feature/my-branch

# Method 4: Cherry-pick from reflog
git checkout -b recovery
git cherry-pick abc1234  # Pick specific commits from reflog
```

### Team Workflow: Rebase Policy

```bash
# RECOMMENDED: "Rebase before merge" workflow
# 1. Developer works on feature branch
# 2. Before PR, rebase onto latest main
# 3. PR is merged with merge commit (--no-ff) or squash merge
# 4. Feature branch is deleted

# GitHub PR merge strategies:
# "Merge commit"  -> Preserves all commits + merge commit
# "Squash merge"  -> Combines all commits into one (cleanest)
# "Rebase merge"  -> Replays commits onto main (linear history)

# Protect against force-push accidents:
# In GitHub: Settings -> Branches -> Branch protection rules
# ☑ Require pull request before merging
# ☑ Require status checks to pass
# ☑ Require linear history (enforces rebase)

# Handle diverged branches after someone else rebased:
git fetch origin
git rebase origin/feature/shared-branch
# NOT: git pull (which creates merge commits)
# Better: git pull --rebase
```

```python
# CI script to check if branch is up to date with main
import subprocess
import sys


def check_branch_freshness(base: str = "origin/main") -> bool:
    """Ensure feature branch is rebased on latest base branch."""
    subprocess.run(["git", "fetch", "origin"], check=True)

    # Find merge base
    result = subprocess.run(
        ["git", "merge-base", "HEAD", base],
        capture_output=True, text=True, check=True'''
    ),
    (
        "tools/git-monorepo-strategies",
        "Explain Git strategies for monorepo management including sparse checkout, partial clone, path-based ownership with CODEOWNERS, commit conventions for monorepos, and CI/CD optimization with affected path detection.",
        '''Monorepos -- single repositories containing multiple projects -- offer advantages in code sharing and atomic changes but challenge Git's performance. These strategies make monorepos practical.

### Partial Clone + Sparse Checkout

The combination that makes large monorepos workable:

```bash
# Partial clone: download commit/tree objects but skip file contents
# Blobs are fetched on-demand when needed
git clone --filter=blob:none --sparse https://github.com/org/monorepo.git

# Now set up sparse checkout for your team's directory
cd monorepo
git sparse-checkout init --cone
git sparse-checkout set \
    libs/shared \
    services/api \
    tools/build

# Your working directory only contains:
# libs/shared/
# services/api/
# tools/build/
# (plus root-level files)

# git log, git blame work across ALL files (fetches blobs lazily)
git log -- services/frontend/src/App.tsx
# Downloads just that file's history on demand

# Check sparse checkout size vs full repo
du -sh .     # Maybe 50MB (just your directories)
# vs 5GB+ for full checkout

# Configure fetch for partial clones
git config remote.origin.promisor true
git config remote.origin.partialclonefilter blob:none
```

### CODEOWNERS for Path-Based Ownership

```bash
# .github/CODEOWNERS
# Format: pattern  owner(s)

# Global default owners
*                            @org/platform-team

# Service-specific owners
/services/api/               @org/backend-team
/services/frontend/          @org/frontend-team
/services/ml-pipeline/       @org/ml-team

# Library owners
/libs/shared/                @org/platform-team
/libs/auth/                  @org/security-team

# Infrastructure
/terraform/                  @org/devops-team
/docker/                     @org/devops-team
/.github/                    @org/devops-team

# Specific critical files
/services/api/src/billing/   @org/billing-team @org/backend-team
*.proto                      @org/platform-team  # All proto files
```

### Affected Path Detection for CI

Only build and test what changed:

```python
#!/usr/bin/env python3
"""Detect which services/packages are affected by changes."""

import subprocess
import json
from pathlib import Path


# Define dependency graph between packages
DEPENDENCY_GRAPH = {'''
    ),
    (
        "services/ml-pipeline",
        "} def get_changed_files(base_ref: str = 'origin/main') -> list[str]:",
        '''["git", "diff", "--name-only", base_ref, "HEAD"],
        capture_output=True, text=True, check=True,'''
    ),
    (
        "should_build",
        "pkg: pkg in affected_pkgs for pkg in DEPENDENCY_GRAPH } } print(json.dumps(output, indent=2))",
        '''# echo "matrix={...}" >> $GITHUB_OUTPUT


if __name__ == "__main__":
    main()
```

### Commit Conventions for Monorepos

```bash
# Scope-based conventional commits
# Format: type(scope): description

# Examples:
git commit -m "feat(api): add user registration endpoint"
git commit -m "fix(frontend): resolve SSR hydration mismatch"
git commit -m "chore(libs/auth): update jwt dependency to v4"
git commit -m "refactor(shared): extract validation utilities"

# Cross-cutting changes
git commit -m "build: update TypeScript to 5.4 across all packages"
git commit -m "ci: add affected-package detection to pipeline"

# Breaking changes
git commit -m "feat(api)!: change authentication to OAuth2

BREAKING CHANGE: JWT tokens are no longer accepted.
Clients must use OAuth2 access tokens."
```

```bash
# .githooks/commit-msg for monorepo convention
#!/bin/bash
commit_msg=$(head -1 "$1")

# Valid scopes match directory structure
valid_scopes="api|frontend|worker|ml-pipeline|shared|auth|build|ci|deps"
pattern="^(feat|fix|docs|refactor|test|chore|perf|build|ci)(\(($valid_scopes)\))?!?: .{1,72}$"

if ! echo "$commit_msg" | grep -qE "$pattern"; then
    echo "Invalid commit message format."
    echo "Valid scopes: $valid_scopes"
    echo "Format: type(scope): description"
    exit 1
fi
```

### CI/CD Pipeline with Affected Path Detection

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      api: ${{ steps.filter.outputs.api }}
      frontend: ${{ steps.filter.outputs.frontend }}
      shared: ${{ steps.filter.outputs.shared }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            shared:
              - 'libs/shared/**'
            api:
              - 'services/api/**'
              - 'libs/shared/**'
              - 'libs/auth/**'
            frontend:
              - 'services/frontend/**'
              - 'libs/shared/**'

  test-api:
    needs: detect-changes
    if: needs.detect-changes.outputs.api == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: |
            services/api
            libs/shared
            libs/auth
      - run: cd services/api && npm test

  test-frontend:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: |
            services/frontend
            libs/shared
      - run: cd services/frontend && npm test
```

### Git Performance Optimization

```bash
# Enable filesystem monitor for large repos (tracks file changes)
git config core.fsmonitor true    # Built-in (Git 2.37+)
# OR use Watchman: git config core.fsmonitor "$HOME/.git-watchman.sh"

# Maintenance: schedule automatic optimization
git maintenance start
# Runs: gc, commit-graph, prefetch, pack-refs periodically

# Commit graph: speeds up log, merge-base, reachability queries
git commit-graph write --reachable --changed-paths
# --changed-paths enables Bloom filters for path-based log queries

# Speed up status in large repos
git config core.untrackedcache true
git config feature.manyFiles true

# Index version 4 (smaller, faster)
git config index.version 4
```

**Monorepo best practices**: (1) Partial clone + sparse checkout is essential above 1GB repo size, (2) CODEOWNERS enforces team ownership boundaries, (3) Build only affected packages -- CI should take minutes, not hours, (4) Scoped commit messages make changelogs and git log filtering practical, (5) Enable commit-graph and fsmonitor for status/log performance.'''
    ),
]
