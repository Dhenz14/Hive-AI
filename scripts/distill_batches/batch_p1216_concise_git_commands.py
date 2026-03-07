"""
Concise answer training pairs - Quick git answers
Teaches the model that short, direct answers are often best.
"""

pairs = [
    {
        "instruction": r'''How do I undo the last git commit?''',
        "output": r'''git reset --soft HEAD~1'''
    },
    {
        "instruction": r'''How do I see what changed in a specific file in git?''',
        "output": r'''git diff path/to/file'''
    },
    {
        "instruction": r'''How do I create a branch from a git tag?''',
        "output": r'''git checkout -b new-branch v1.2.3'''
    },
    {
        "instruction": r'''How do I squash the last 3 commits in git?''',
        "output": r'''git reset --soft HEAD~3
git commit -m "Combined commit message"'''
    },
    {
        "instruction": r'''<think>
The user is asking about finding which commit introduced a bug. The standard tool for this is git bisect. I should give a concise but complete answer showing the basic workflow.
</think>

How do I find which git commit introduced a bug?''',
        "output": r'''git bisect start
git bisect bad          # current commit is broken
git bisect good abc123  # last known good commit

Git will binary-search through commits. At each step, test and run `git bisect good` or `git bisect bad`. When done: `git bisect reset`.'''
    },
]
