"""
Concise answer training pairs - Quick shell/bash answers
Teaches the model that short, direct answers are often best.
"""

pairs = [
    {
        "instruction": r'''How do I find files modified today in bash?''',
        "output": r'''find . -mtime 0 -type f'''
    },
    {
        "instruction": r'''How do I count lines in all Python files?''',
        "output": r'''find . -name "*.py" | xargs wc -l'''
    },
    {
        "instruction": r'''<think>
Quick question about killing a process on a port. lsof + kill or fuser. Keep it short.
</think>

How do I kill a process running on port 8080?''',
        "output": r'''lsof -ti:8080 | xargs kill -9

Or on one line with fuser:
fuser -k 8080/tcp'''
    },
    {
        "instruction": r'''How do I watch a file for changes in bash?''',
        "output": r'''watch -n 1 cat /path/to/file'''
    },
    {
        "instruction": r'''How do I compare two directories?''',
        "output": r'''diff -rq dir1/ dir2/'''
    },
]
