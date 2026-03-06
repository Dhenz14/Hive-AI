PAIRS = [
    ("thinking/debugging", r'''I accidentally ran `git reset --hard HEAD~5` and lost 5 commits that were never pushed. Is there any way to recover them?

```
$ git log --oneline
a1b2c3d Fix: some older commit
...

$ git reset --hard HEAD~5
HEAD is now at a1b2c3d Fix: some older commit

# The 5 lost commits:
# f6e5d4c Add payment processing
# 9a8b7c6 Add user authentication
# 1d2e3f4 Add API rate limiting
# 5g6h7i8 Add caching layer
# j9k0l1m Add logging middleware
```

These commits represent two weeks of work. Please tell me they're not gone forever.''', r'''<think>
Okay, the user ran `git reset --hard HEAD~5` on unpushed commits. This could be catastrophic... but wait, does git actually delete commit data immediately? I considered that maybe the objects are removed from the database right away, but that won't work because git uses a garbage collector that runs on a schedule, not inline with reset operations.

Hmm, actually, git almost never truly deletes data immediately. When you do `git reset --hard`, the commits still exist in the object database -- they just become "unreachable" (no branch or tag points to them). The key mechanism here is the reflog. Because git's reflog records every change to HEAD, the old HEAD positions are still tracked.

The recovery steps:
1. Use `git reflog` to find the lost commit hashes
2. Create a branch pointing to the most recent lost commit

I initially thought the user might need `git fsck --lost-found` to hunt for dangling objects, but that is the harder path. Because the reflog entries exist, `git reflog` is simpler and more reliable. The reflog approach is simpler but `git fsck` handles edge cases where the reflog itself is corrupted.

The commits will remain in the object database until `git gc` prunes unreachable objects, which by default happens after 90 days for reflog entries and 2 weeks for unreachable objects without reflog entries. Since the reflog entries exist, the user has about 90 days. Wait, I need to reconsider -- if someone runs `git gc --prune=now` manually, the window shrinks to zero. But that is unlikely unless explicitly invoked.
</think>

Good news: your commits are almost certainly recoverable. Git rarely deletes data immediately. The commits still exist in Git's object database -- they are just "unreachable" because no branch points to them anymore. Git's reflog keeps a record of every position HEAD has been at.

**Step 1: Find the lost commits using reflog**

```bash
git reflog
```

Output will look something like:
```
a1b2c3d HEAD@{0}: reset: moving to HEAD~5
f6e5d4c HEAD@{1}: commit: Add payment processing
9a8b7c6 HEAD@{2}: commit: Add user authentication
1d2e3f4 HEAD@{3}: commit: Add API rate limiting
5g6h7i8 HEAD@{4}: commit: Add caching layer
j9k0l1m HEAD@{5}: commit: Add logging middleware
```

**Step 2: Recover by pointing your branch back to the lost commit**

```bash
# Reset to the most recent lost commit (which includes all 5)
git reset --hard f6e5d4c
```

Or, if you want to be safer and create a recovery branch first:

```bash
# Create a new branch at the lost commit
git branch recovery f6e5d4c

# Verify the commits are there
git log recovery --oneline

# If everything looks good, merge or reset
git reset --hard recovery
git branch -d recovery
```

**Alternative: Use git cherry-pick to selectively recover**

```bash
# If you only want some of the lost commits
git cherry-pick j9k0l1m  # logging middleware
git cherry-pick 5g6h7i8  # caching layer
# etc.
```

**If reflog has been cleared or corrupted:**

```bash
# Find dangling commits (unreachable objects)
git fsck --lost-found

# This outputs something like:
# dangling commit f6e5d4c...
# dangling commit 9a8b7c6...

# Inspect each one
git show f6e5d4c
```

**How long do unreachable commits survive?**

- Reflog entries: 90 days by default (`gc.reflogExpire`)
- Unreachable objects with reflog entries: 90 days
- Unreachable objects without reflog entries: 14 days (`gc.pruneExpire`)
- Running `git gc --prune=now` will delete them immediately (never do this during recovery!)

**Prevention tips:**
- Push commits frequently, even to a personal branch
- Before destructive operations, create a backup branch: `git branch backup-before-reset`
- Use `git reset --soft` or `git reset --mixed` instead of `--hard` when possible (they preserve working directory changes)
- Increase reflog retention: `git config gc.reflogExpire never`
- Consider setting up a pre-reset hook that warns about unpushed commits'''),

    ("thinking/debugging", r'''I'm in a detached HEAD state and don't know how I got here or how to get back:

```
$ git status
HEAD detached at 8a7b6c5
nothing to commit, working tree clean

$ git log --oneline -5
8a7b6c5 (HEAD) Refactor database module
7f6e5d4 Add unit tests
6c5b4a3 Fix memory leak
5d4c3b2 (origin/main, main) Update dependencies
4e3d2c1 Initial commit
```

I've made 3 commits (8a7b6c5, 7f6e5d4, 6c5b4a3) while in detached HEAD. If I checkout main, will I lose these commits?''', r'''<think>
The user is in detached HEAD state with 3 commits. My first instinct is that if they simply `git checkout main`, those commits are gone forever... but wait, that is not quite right. They become unreachable (no branch points to them) but they still exist in the reflog temporarily. However, relying on the reflog is risky because they could be lost after GC.

I considered suggesting they just do `git checkout main` and then recover via reflog, but that won't work reliably because it adds unnecessary risk. The safer fix is to create a branch at the current HEAD before switching away, or merge/rebase these commits onto main.

Hmm, actually, there are multiple ways they could have ended up here. Let me think through the common causes:
- `git checkout <commit-hash>` or `git checkout <tag>` -- most likely
- `git checkout origin/main` (checking out a remote tracking branch)
- `git rebase` in progress
- `git bisect` in progress

Because the user has 3 commits on the detached HEAD that are ahead of main, the cleanest approach is option A (create a branch then merge) since it preserves the commit history. Option B (force-moving main) is simpler but only safe if nobody else has pushed to main, therefore it depends on team context.
</think>

If you `git checkout main` right now, the 3 commits (8a7b6c5, 7f6e5d4, 6c5b4a3) will become unreachable. They will still exist temporarily in the reflog but are at risk of being garbage collected. You need to save them first.

**How you likely got into detached HEAD:**
- `git checkout 5d4c3b2` (checked out a specific commit)
- `git checkout origin/main` (checked out a remote tracking branch)
- A `git rebase` or `git bisect` operation

**Fix 1: Create a branch to save your commits, then merge**

```bash
# Create a branch at current HEAD to save the commits
git branch my-work

# Now switch to main safely
git checkout main

# Merge your work into main
git merge my-work

# Clean up
git branch -d my-work
```

**Fix 2: Directly move main to include your commits**

If main should include these commits (and nobody else has pushed to main):

```bash
# Move main branch to current HEAD
git branch -f main HEAD

# Switch to main
git checkout main

# Verify
git log --oneline -5
# 8a7b6c5 (HEAD -> main) Refactor database module
# 7f6e5d4 Add unit tests
# 6c5b4a3 Fix memory leak
# 5d4c3b2 (origin/main) Update dependencies
# 4e3d2c1 Initial commit
```

**Fix 3: Rebase your detached commits onto an updated main**

If main has moved since you detached:

```bash
# First, save your work on a branch
git branch my-work

# Update main
git checkout main
git pull

# Rebase your work onto updated main
git rebase main my-work

# Fast-forward main to include your work
git checkout main
git merge my-work
git branch -d my-work
```

**Understanding detached HEAD:**

In normal Git operation, HEAD points to a branch name, which points to a commit:
```
HEAD -> main -> 5d4c3b2
```

In detached HEAD, HEAD points directly to a commit:
```
HEAD -> 8a7b6c5  (no branch!)
main -> 5d4c3b2
```

Any commits made in detached HEAD are not on any branch. They exist but are "floating" -- only reachable through HEAD. The moment HEAD moves away (checkout, reset), they become unreachable.

**Prevention tips:**
- Always check `git status` before committing -- it warns about detached HEAD
- If you need to look at an old commit, use `git log` or `git show` instead of `git checkout <hash>`
- If you need a throwaway exploration, create a branch first: `git checkout -b explore <hash>`
- Configure your shell prompt to show the current branch/detached state (git-prompt.sh)'''),

    ("thinking/debugging", r'''Two team members edited the same file and git merge is showing a complex conflict:

```
$ git merge feature-branch
Auto-merging src/config.py
CONFLICT (content): Merge conflict in src/config.py
Automatic merge failed; fix conflicts and then commit the result.
```

The conflict markers in src/config.py:
```python
class Config:
<<<<<<< HEAD
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://localhost/mydb')
    CACHE_TTL = 300
    MAX_WORKERS = 4
    LOG_LEVEL = 'INFO'
=======
    DATABASE_URL = os.environ.get('DB_URL', 'postgres://localhost/prod')
    CACHE_TTL = 600
    MAX_WORKERS = 8
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
>>>>>>> feature-branch
```

Both sides renamed the env var, changed values, and added different new settings. How do I resolve this properly?''', r'''<think>
Let me analyze the conflict carefully. This could be a simple "pick one side" situation... but wait, both sides changed multiple settings independently, so I need to look at each line.

HEAD (current branch) has:
- DATABASE_URL using 'DATABASE_URL' env var, default 'postgres://localhost/mydb'
- CACHE_TTL = 300
- MAX_WORKERS = 4
- LOG_LEVEL = 'INFO'

feature-branch has:
- DATABASE_URL using 'DB_URL' env var, default 'postgres://localhost/prod'
- CACHE_TTL = 600
- MAX_WORKERS = 8
- DEBUG = True (new)
- LOG_LEVEL = 'DEBUG'

I considered just telling them to accept one side entirely, but that won't work because both sides have valid changes that should be kept. The developer needs to decide per-line:
1. Which env var name to use (DATABASE_URL or DB_URL) -- keeping DATABASE_URL is safer since existing deployments may depend on it
2. Which default database URL
3. Which CACHE_TTL value
4. Which MAX_WORKERS value
5. Whether to include DEBUG -- the feature branch added it, probably needed
6. Which LOG_LEVEL -- DEBUG in production is risky, so INFO is likely better as default

Hmm, actually, without seeing the original (common ancestor), I cannot tell what each side actually changed vs what was already there. The diff3 conflict style would show the common ancestor, making it much clearer. Because knowing the original state tells you the intent behind each change, therefore I should recommend enabling diff3 first.
</think>

Merge conflicts require understanding the intent of both changes and making a deliberate decision about each conflicting line. Here is the systematic approach:

**Step 1: Understand what each side changed**

Use `git log` to understand the context:
```bash
# What changed on your branch (HEAD)
git log --oneline main..HEAD -- src/config.py

# What changed on feature-branch
git log --oneline main..feature-branch -- src/config.py

# See the original (before either change)
git show main:src/config.py
```

**Step 2: Use diff3 conflict style for more context**

```bash
git config merge.conflictstyle diff3
git merge feature-branch
```

This shows three sections instead of two:
```python
<<<<<<< HEAD
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://localhost/mydb')
    CACHE_TTL = 300
    MAX_WORKERS = 4
    LOG_LEVEL = 'INFO'
||||||| merged common ancestor
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://localhost/dev')
    CACHE_TTL = 300
    MAX_WORKERS = 2
    LOG_LEVEL = 'INFO'
=======
    DATABASE_URL = os.environ.get('DB_URL', 'postgres://localhost/prod')
    CACHE_TTL = 600
    MAX_WORKERS = 8
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
>>>>>>> feature-branch
```

Now you can see what the original was and what each side actually changed:
- HEAD: changed default URL from 'dev' to 'mydb', MAX_WORKERS from 2 to 4
- feature-branch: renamed env var to DB_URL, changed default to 'prod', CACHE_TTL 300->600, MAX_WORKERS 2->8, added DEBUG, changed LOG_LEVEL

**Step 3: Resolve manually**

Edit the file to combine both changes intentionally:
```python
class Config:
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://localhost/mydb')
    CACHE_TTL = 600              # accept feature-branch's increase
    MAX_WORKERS = 8              # accept feature-branch's increase
    DEBUG = False                # keep the setting but default to False
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')  # make it configurable
```

Remove ALL conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

**Step 4: Mark as resolved and commit**

```bash
git add src/config.py
git commit  # Git auto-generates a merge commit message
```

**Using a merge tool:**

```bash
# Configure a visual merge tool
git mergetool --tool=vimdiff  # or meld, kdiff3, vscode

# VS Code as merge tool:
git config merge.tool vscode
git config mergetool.vscode.cmd 'code --wait $MERGED'
```

**Prevention tips:**
- Enable diff3 conflict style globally: `git config --global merge.conflictstyle diff3`
- Keep configuration in environment variables to minimize config file conflicts
- Split large config files into smaller, domain-specific files
- Communicate with team members about files you are actively modifying
- Rebase feature branches frequently to catch conflicts early and keep them small
- Use `git rerere` (reuse recorded resolution) to automatically apply previously resolved conflicts: `git config rerere.enabled true`'''),

    ("thinking/debugging", r'''Someone on my team force-pushed to main and overwrote my last 3 commits:

```
$ git fetch
$ git log --oneline origin/main -5
d4c3b2a (origin/main) Teammate's rewrite
c3b2a1f Teammate's refactor
b2a1f0e Base commit

$ git log --oneline main -5
f6e5d4c (main) My commit 3 - Add validation
e5d4c3b My commit 2 - Add error handling
d4c3b2a My commit 1 - Add logging
c3b2a1f Teammate's refactor
b2a1f0e Base commit
```

My 3 commits (d4c3b2a through f6e5d4c) are on my local main but not on origin/main anymore. The teammate's force-push replaced them with "Teammate's rewrite" (which coincidentally has the same hash prefix d4c3b2a as my commit 1, but it's a different commit).

How do I recover and get my changes back?''', r'''<think>
The user's 3 commits exist locally but were overwritten on the remote by a force push. My first thought is that the commits might be lost... but wait, the local branch still has them. The local branch has the commits, so they are not lost -- yet. The critical danger is if the user runs `git pull` or `git reset --hard origin/main`, which would discard the local commits.

I considered suggesting a simple `git push --force` to restore the remote, but that won't work because the teammate's rewrite commit also needs to be preserved. Because both sets of changes need to coexist, therefore the approach should be to rebase the local commits onto the new remote main.

Steps:
1. First, create a backup branch immediately -- this is non-negotiable safety
2. Need to rebase the local commits onto the new remote main, or cherry-pick them
3. Then push (possibly force push if the teammate's rewrite conflicts)

Option A (rebase --onto) is cleaner but harder to understand. Option B (cherry-pick) is more manual but handles edge cases better when there are complex conflicts. I will present both and let the user choose based on their comfort level.
</think>

Your commits are safe on your local `main` branch. Do NOT run `git pull`, `git reset --hard origin/main`, or `git checkout .` -- any of these could discard your local commits.

**Step 1: Save your commits on a backup branch immediately**

```bash
git branch backup-my-work main
```

This ensures your commits are preserved even if something goes wrong.

**Step 2: Understand the divergence**

```bash
git log --oneline --graph main origin/main --all
```

Your local main:
```
f6e5d4c My commit 3 - Add validation
e5d4c3b My commit 2 - Add error handling
d4c3b2a My commit 1 - Add logging
c3b2a1f Teammate's refactor
b2a1f0e Base commit
```

Remote main (after force push):
```
d4c3b2a Teammate's rewrite (different commit, same hash prefix coincidence)
c3b2a1f Teammate's refactor
b2a1f0e Base commit
```

**Step 3: Rebase your commits onto the new remote main**

```bash
# Update remote tracking
git fetch origin

# Rebase your 3 commits onto the new remote main
git rebase --onto origin/main c3b2a1f main
```

This takes the commits between c3b2a1f (the common ancestor) and your main, and replays them on top of origin/main.

If there are conflicts, resolve them for each commit:
```bash
# Fix conflicts in the file
git add <resolved-files>
git rebase --continue
```

**Step 4: Push the combined history**

```bash
# If your team agrees this is correct:
git push origin main

# If the remote has branch protection, create a PR:
git checkout -b recover-my-work
git push origin recover-my-work
# Then create a pull request
```

**Alternative: Cherry-pick if rebase is too complex**

```bash
# Reset local main to match remote
git checkout main
git reset --hard origin/main

# Cherry-pick your commits one by one
git cherry-pick d4c3b2a  # My commit 1 (use full hash to avoid ambiguity)
git cherry-pick e5d4c3b  # My commit 2
git cherry-pick f6e5d4c  # My commit 3
```

**Step 5: Prevent this from happening again**

```bash
# Protect the main branch on GitHub/GitLab:
# - Require pull request reviews
# - Disable force pushes
# - Require status checks to pass

# On GitHub CLI:
gh api repos/{owner}/{repo}/branches/main/protection -X PUT -f \
  required_pull_request_reviews='{"required_approving_review_count":1}' \
  allow_force_pushes=false
```

**Prevention tips:**
- Enable branch protection rules that prevent force pushes to main
- Communicate with your team before any force push operation
- Use `git push --force-with-lease` instead of `--force` -- it fails if the remote has changed since your last fetch
- Set up a Git hook or CI check that warns about force pushes
- Regularly push your work to personal branches as backups'''),

    ("thinking/debugging", r'''A regression was introduced somewhere in the last 200 commits. I need to find which commit caused the tests to fail. Manual bisection would take forever.

```
$ git log --oneline | wc -l
847

$ git bisect start
$ git bisect bad HEAD
$ git bisect good v2.1.0  # this was working 200 commits ago

Bisecting: 100 revisions left to test after this (roughly 7 steps)
```

But the test I need to run takes 5 minutes. Is there a way to automate this?''', r'''<think>
The user needs to find a regression in 200 commits. Manual bisection would be 200 * 5 minutes = over 16 hours, which is clearly impractical. This could be solved with a linear search... but wait, binary search is far more efficient here.

Git bisect can be automated with `git bisect run`. You provide a script that exits with 0 for "good" and non-zero for "bad", and git bisect will automatically binary search through the commits.

With 200 commits, binary search needs about log2(200) = ~7.6, so roughly 8 steps. At 5 minutes per step, that is about 40 minutes -- much better than manual testing of 200 commits.

I considered suggesting they just run `git bisect` manually (mark good/bad interactively), but that won't work well because the user said it takes 5 minutes per test -- they would need to sit and wait at each step. Because `git bisect run` automates the waiting, therefore it is strictly better here. The key is writing a good test script that exits with the right codes.

Hmm, actually, I need to handle an edge case: what if some commits do not compile? Exit code 125 tells bisect to skip that commit rather than marking it as good or bad. The tradeoff is that skipping too many commits reduces the efficiency of binary search, but it is better than a false result.
</think>

`git bisect run` automates the entire process. With 200 commits, binary search needs only about 8 steps (log2(200) = 7.6). At 5 minutes per test, the total time is roughly 40 minutes of unattended execution.

**Step 1: Start bisect**

```bash
git bisect start
git bisect bad HEAD                 # current commit is broken
git bisect good v2.1.0              # this tag was working
```

**Step 2: Create a test script**

```bash
#!/bin/bash
# bisect_test.sh

# Run the specific failing test
python -m pytest tests/test_payment.py::test_charge_card -x --timeout=120

# Exit code rules for git bisect:
# 0 = good (test passed)
# 1-124, 126-127 = bad (test failed)
# 125 = skip (cannot test this commit, e.g., build failure)

exit_code=$?

if [ $exit_code -eq 0 ]; then
    exit 0    # good commit
elif [ $exit_code -eq 125 ]; then
    exit 125  # skip this commit
else
    exit 1    # bad commit
fi
```

```bash
chmod +x bisect_test.sh
```

**Step 3: Run automated bisect**

```bash
git bisect run ./bisect_test.sh
```

Git will automatically:
1. Check out the middle commit
2. Run your script
3. Based on the exit code, narrow the search range
4. Repeat until it finds the first bad commit

Output will look like:
```
running ./bisect_test.sh
Bisecting: 50 revisions left to test (roughly 6 steps)
running ./bisect_test.sh
...
abc123def is the first bad commit
commit abc123def
Author: John Doe <john@example.com>
Date:   Thu Mar 10 14:32:11 2024

    Optimize payment processing queries

bisect run success
```

**Step 4: Clean up**

```bash
git bisect reset   # returns to original branch
```

**Handling builds that don't compile (skip):**

```bash
#!/bin/bash
# bisect_test.sh with build check

# First, make sure the project builds
python setup.py build 2>/dev/null
if [ $? -ne 0 ]; then
    exit 125  # can't test, skip this commit
fi

# Then run the test
python -m pytest tests/test_payment.py::test_charge_card -x
```

**Using git bisect with a Python script:**

```python
#!/usr/bin/env python3
# bisect_test.py
import subprocess
import sys

result = subprocess.run(
    ['python', '-m', 'pytest', 'tests/test_payment.py', '-x', '--tb=no', '-q'],
    capture_output=True, timeout=300,
)

sys.exit(0 if result.returncode == 0 else 1)
```

**Advanced: Bisect with multiple test criteria**

```bash
#!/bin/bash
# Check for performance regression
DURATION=$(python -c "
import time
start = time.time()
from myapp import process_batch
process_batch(test_data)
print(time.time() - start)
")

# Bad if duration > 2 seconds (was < 1 second before)
python -c "exit(0 if float('$DURATION') < 2.0 else 1)"
```

**Prevention tips:**
- Write focused, fast-running regression tests that can be used with bisect
- Tag releases so you always have known-good commits to bisect from
- Keep commits atomic (one logical change per commit) so bisect finds meaningful results
- Use `git bisect log` to save and replay bisect sessions
- Run `git bisect visualize` to see the remaining search space
- After finding the bad commit, write a test that would have caught the regression'''),
]
