"""
Concise answer training pairs - Quick debugging answers
Teaches the model that short, direct answers are often best.
"""

pairs = [
    {
        "instruction": r'''<think>
TypeError about unpacking NoneType -- the function returned None. Quick explanation.
</think>

I'm getting "TypeError: cannot unpack non-iterable NoneType object". What does it mean?''',
        "output": r'''Your function is returning None instead of a tuple/list. Check:

1. The function actually has a `return` statement
2. It doesn't return None on some code path
3. You're calling the right function'''
    },
    {
        "instruction": r'''I'm getting "ModuleNotFoundError: No module named 'requests'". How do I fix it?''',
        "output": r'''pip install requests

If already installed, check you're using the right environment:
which python
pip list | grep requests

You may need to activate your venv first:
source venv/bin/activate'''
    },
    {
        "instruction": r'''I'm getting a CORS error in my browser console. How do I fix it?''',
        "output": r'''Add CORS headers on your backend. With Flask:

from flask_cors import CORS
CORS(app)

With Express:
const cors = require("cors");
app.use(cors());

Or for a quick test, allow the specific origin in your response headers.'''
    },
    {
        "instruction": r'''I get "Permission denied" when trying to run a server on port 80.''',
        "output": r'''Ports below 1024 require root. Either:
- Use port 8080 instead (recommended)
- Run with sudo (not recommended for dev)'''
    },
    {
        "instruction": r'''<think>
Git merge conflict markers -- just show what they look like and how to resolve. Keep it short.
</think>

How do I resolve git merge conflict markers?''',
        "output": r'''The markers look like:

<<<<<<< HEAD
your changes
=======
their changes
>>>>>>> branch-name

Edit the file to keep the code you want, delete the marker lines, then:
git add the-file
git commit'''
    },
]
