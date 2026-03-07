"""
Shell/CLI training pairs - Git CLI workflows (rebase, bisect, cherry-pick, stash).
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''I merged a feature branch but it introduced a bug somewhere in the last 20 commits. How do I use git bisect to find the exact commit that broke things?''',
        "output": r'''<think>
Git bisect does a binary search through commits to find which one introduced a bug. The user needs to:
1. Start bisect
2. Mark the current (broken) commit as bad
3. Mark a known-good commit as good
4. Git will checkout commits for testing, and the user marks each as good/bad
5. After log2(20) ~ 5 steps, it finds the culprit

I should also show the automated version with `git bisect run` since that is much more practical if they have a test script.
</think>

Manual bisect workflow:

```bash
# Start bisect
git bisect start

# Mark current commit as bad
git bisect bad

# Mark a known-good commit (e.g., 20 commits ago)
git bisect good HEAD~20
```

Git will now checkout a commit halfway between good and bad. Test your code, then:

```bash
# If this commit has the bug:
git bisect bad

# If this commit is fine:
git bisect good
```

Repeat 4-5 times (binary search through 20 commits). Git tells you the first bad commit.

```bash
# When done, return to your original branch
git bisect reset
```

Automated bisect with a test script (much faster):

```bash
git bisect start
git bisect bad HEAD
git bisect good HEAD~20

# Run a test command automatically -- exit 0 = good, non-zero = bad
git bisect run python -m pytest tests/test_feature.py -x

# Or use any shell command
git bisect run sh -c 'make build && ./run_test.sh'
```

The automated version runs the entire bisect without interaction. View the log afterward:

```bash
git bisect log
```'''
    },
    {
        "instruction": r'''How do I cherry-pick a range of commits from another branch without immediately committing them?''',
        "output": r'''```bash
# Cherry-pick a range of commits without committing (stages changes only)
git cherry-pick --no-commit abc123..def456

# Review what's staged
git diff --cached

# Then commit as a single commit
git commit -m "Cherry-pick features X, Y, Z from feature-branch"
```

Important: the range `abc123..def456` does NOT include `abc123` itself. To include it:

```bash
git cherry-pick --no-commit abc123^..def456
```

Other useful cherry-pick patterns:

```bash
# Cherry-pick specific non-contiguous commits
git cherry-pick --no-commit abc123 def456 ghi789

# Cherry-pick from another branch by reference
git cherry-pick --no-commit feature-branch~5..feature-branch

# If conflicts arise during cherry-pick
git status                    # see conflicted files
# ... resolve conflicts ...
git add resolved-file.py
git cherry-pick --continue

# Abort if it gets messy
git cherry-pick --abort
```

To preview which commits you would cherry-pick:

```bash
git log --oneline abc123^..def456
```'''
    },
    {
        "instruction": r'''What are some practical git stash workflows beyond basic stash/pop?''',
        "output": r'''```bash
# Stash with a descriptive message
git stash push -m "WIP: refactoring auth middleware"

# Stash only specific files
git stash push -m "config changes" config.yaml settings.py

# Stash including untracked files
git stash push -u -m "includes new files"

# Stash including ignored files too
git stash push -a -m "everything"

# List all stashes
git stash list
# stash@{0}: On main: WIP: refactoring auth middleware
# stash@{1}: On feature: config changes

# Show what's in a specific stash
git stash show -p stash@{1}

# Apply a specific stash (keeps it in the list)
git stash apply stash@{1}

# Pop a specific stash (removes it from the list)
git stash pop stash@{1}

# Create a branch from a stash
git stash branch new-feature stash@{0}

# Drop a specific stash
git stash drop stash@{2}

# Apply only parts of a stash interactively
git stash show -p stash@{0} | git apply --3way

# Clear all stashes (careful!)
git stash clear
```

Pro tip -- stash before risky operations:

```bash
# Quick save before a rebase
git stash push -m "pre-rebase safety net"
git rebase main
git stash pop
```'''
    },
    {
        "instruction": r'''I need to rewrite the author email on the last 5 commits because I committed with my personal email instead of my work email. What's the safest way?''',
        "output": r'''<think>
The user wants to rewrite author info on recent commits. Options:
1. `git rebase -i` with exec commands -- works but clunky
2. `git filter-branch` -- deprecated, should not recommend
3. `git filter-repo` -- modern replacement, but requires install
4. `git rebase` with `--exec` to run `git commit --amend` on each commit

For just 5 commits, the simplest is `git rebase` with `--exec` and environment variables. I should warn that this rewrites history and should not be done on shared/pushed branches without coordination.
</think>

For the last 5 commits, use rebase with --exec:

```bash
git rebase HEAD~5 --exec 'if [ "$(git log -1 --format=%ae)" = "personal@gmail.com" ]; then
  GIT_COMMITTER_EMAIL="work@company.com" \
  git commit --amend --author="Your Name <work@company.com>" --no-edit
fi'
```

Simpler version if ALL 5 commits need the change:

```bash
git rebase HEAD~5 --exec 'GIT_COMMITTER_EMAIL="work@company.com" git commit --amend --author="Your Name <work@company.com>" --no-edit'
```

Verify the result:

```bash
git log --format='%h %ae %s' -5
```

WARNING: This rewrites commit hashes. If you already pushed these commits:

```bash
# You will need a force push
git push --force-with-lease origin your-branch
```

Use `--force-with-lease` instead of `--force` -- it refuses to push if someone else has pushed to the branch since your last fetch.

To prevent this in the future, set per-repo email:

```bash
cd /path/to/work-repo
git config user.email "work@company.com"
```'''
    },
    {
        "instruction": r'''How do I find which commit deleted a specific file in git history?''',
        "output": r'''```bash
# Find the commit that deleted a file
git log --diff-filter=D --summary -- path/to/deleted-file.py
```

This shows the commit where the file was removed, with a summary of changes.

More specific approaches:

```bash
# Just the commit hash and message
git log --diff-filter=D --oneline -- path/to/deleted-file.py

# If you don't remember the exact path
git log --diff-filter=D --summary --all -- '**/filename.py'

# Find when any file matching a pattern was deleted
git log --diff-filter=D --name-only --oneline -- '*.config'

# Show the full content of the file before deletion
git show $(git rev-list -1 HEAD -- path/to/deleted-file.py):path/to/deleted-file.py

# Restore the deleted file
git checkout $(git rev-list -1 HEAD -- path/to/deleted-file.py)^ -- path/to/deleted-file.py
```

The `^` after the commit hash means "the commit before" -- because at the deletion commit the file no longer exists, you need to checkout from the parent commit.

To search for deleted files by content:

```bash
# Find commits where a file containing "class MyService" was deleted
git log --diff-filter=D -S "class MyService" --source --all
```'''
    },
]
