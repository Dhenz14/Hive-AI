"""
Concise answer training pairs - Quick Python answers
Teaches the model that short, direct answers are often best.
"""

pairs = [
    {
        "instruction": r'''How do I reverse a list in Python?''',
        "output": r'''reversed_list = my_list[::-1]

Or in-place:
my_list.reverse()'''
    },
    {
        "instruction": r'''How do I read a JSON file in Python?''',
        "output": r'''import json

with open("data.json") as f:
    data = json.load(f)'''
    },
    {
        "instruction": r'''How do I merge two dicts in Python?''',
        "output": r'''merged = {**dict_a, **dict_b}'''
    },
    {
        "instruction": r'''How do I check if a key exists in a Python dict?''',
        "output": r'''if "key" in my_dict:'''
    },
    {
        "instruction": r'''How do I sort a list of dicts by a specific key?''',
        "output": r'''sorted_list = sorted(my_list, key=lambda x: x["name"])'''
    },
]
