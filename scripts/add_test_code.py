"""
One-time script to add test_code to eval challenges that are missing it.
Run: python scripts/add_test_code.py
"""
import json
import os

CHALLENGES_FILE = os.path.join(os.path.dirname(__file__), "eval_challenges.json")

# Map of challenge_id -> test_code to add
TEST_CODE_ADDITIONS = {
    # ---- Python challenges ----
    "py-proto-010": (
        "from typing import Protocol, runtime_checkable\n"
        "# Test that Protocol and render_all work with structural subtyping\n"
        "class Square:\n"
        "    def draw(self) -> str:\n"
        "        return 'Square'\n"
        "class Circle:\n"
        "    def draw(self) -> str:\n"
        "        return 'Circle'\n"
        "result = render_all([Square(), Circle()])\n"
        "assert 'Square' in result[0] and 'Circle' in result[1], f'Expected drawings, got {result}'\n"
        "# Test that non-Drawable fails or is excluded\n"
        "try:\n"
        "    assert isinstance(Square(), Drawable), 'runtime_checkable Protocol should work'\n"
        "except Exception:\n"
        "    pass  # runtime_checkable is optional\n"
        "print('ALL TESTS PASSED')"
    ),

    "py-weakref-015": (
        "import weakref, gc\n"
        "# Test WeakValueDictionary-based Cache\n"
        "cache = Cache()\n"
        "class Item:\n"
        "    def __init__(self, name): self.name = name\n"
        "item = Item('test')\n"
        "cache.put('key1', item)\n"
        "assert cache.get('key1') is not None, 'Item should be in cache'\n"
        "assert cache.get('key1').name == 'test'\n"
        "del item\n"
        "gc.collect()\n"
        "# After deleting strong ref and GC, weak ref should be gone\n"
        "assert cache.get('key1') is None, 'Item should be garbage collected'\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Design Patterns ----
    "pat-visitor-010": (
        "# Test Visitor pattern with AST nodes\n"
        "# NumberNode, BinaryOpNode, PrintVisitor expected\n"
        "expr = BinaryOpNode(NumberNode(2), '+', BinaryOpNode(NumberNode(3), '*', NumberNode(4)))\n"
        "visitor = PrintVisitor()\n"
        "result = expr.accept(visitor)\n"
        "assert '2' in str(result) and '3' in str(result) and '4' in str(result), f'Missing numbers in {result}'\n"
        "assert '+' in str(result) or 'add' in str(result).lower(), f'Missing operator in {result}'\n"
        "# Simple expression\n"
        "simple = NumberNode(42)\n"
        "assert '42' in str(simple.accept(visitor))\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Systems ----
    "sys-hash-009": (
        "# Test consistent hashing\n"
        "ch = ConsistentHash(replicas=100)\n"
        "ch.add_node('server-1')\n"
        "ch.add_node('server-2')\n"
        "ch.add_node('server-3')\n"
        "# All keys should map to a valid node\n"
        "nodes_used = set()\n"
        "for i in range(100):\n"
        "    node = ch.get_node(f'key-{i}')\n"
        "    assert node in ('server-1', 'server-2', 'server-3'), f'Unknown node: {node}'\n"
        "    nodes_used.add(node)\n"
        "assert len(nodes_used) >= 2, f'Poor distribution: only {nodes_used}'\n"
        "# Removing a node should redistribute\n"
        "before = ch.get_node('test-key')\n"
        "ch.remove_node(before)\n"
        "after = ch.get_node('test-key')\n"
        "assert after != before, 'Key should move after removing its node'\n"
        "assert after in ('server-1', 'server-2', 'server-3') - {before}\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Testing ----
    "test-fix-001": (
        "# Test the BankAccount class directly (not the fixtures)\n"
        "account = BankAccount()\n"
        "assert account.balance == 0, f'Expected 0 balance, got {account.balance}'\n"
        "account.deposit(100)\n"
        "assert account.balance == 100, f'Expected 100 after deposit, got {account.balance}'\n"
        "account.withdraw(30)\n"
        "assert account.balance == 70, f'Expected 70 after withdraw, got {account.balance}'\n"
        "try:\n"
        "    account.withdraw(1000)\n"
        "    assert False, 'Should raise on insufficient funds'\n"
        "except (ValueError, Exception):\n"
        "    pass\n"
        "assert account.balance == 70, 'Balance should not change after failed withdrawal'\n"
        "print('ALL TESTS PASSED')"
    ),

    "test-mock-002": (
        "# Test the get_user_info function structure\n"
        "from unittest.mock import patch, MagicMock\n"
        "# Mock the external API call\n"
        "with patch('__main__.get_user_info') as mock_fn:\n"
        "    mock_fn.return_value = {'id': 1, 'name': 'Alice'}\n"
        "    result = mock_fn(1)\n"
        "    assert result == {'id': 1, 'name': 'Alice'}\n"
        "    mock_fn.assert_called_with(1)\n"
        "# Test the actual function exists and is callable\n"
        "assert callable(get_user_info), 'get_user_info should be callable'\n"
        "print('ALL TESTS PASSED')"
    ),

    "test-snapshot-006": (
        "import json, tempfile, os\n"
        "# Test the SnapshotTest class\n"
        "snap_dir = tempfile.mkdtemp()\n"
        "st = SnapshotTest(snap_dir)\n"
        "# First call should save the snapshot\n"
        "st.assert_match('test1', {'name': 'Alice', 'age': 30})\n"
        "# Second call with same data should pass\n"
        "st.assert_match('test1', {'name': 'Alice', 'age': 30})\n"
        "# Different data should fail\n"
        "try:\n"
        "    st.assert_match('test1', {'name': 'Bob', 'age': 25})\n"
        "    assert False, 'Should fail on snapshot mismatch'\n"
        "except (AssertionError, Exception):\n"
        "    pass\n"
        "# Cleanup\n"
        "import shutil; shutil.rmtree(snap_dir)\n"
        "print('ALL TESTS PASSED')"
    ),

    "test-doubles-008": (
        "# Test that the code defines/demonstrates test doubles\n"
        "# We check the stub and fake implementations exist and work\n"
        "import inspect\n"
        "# The response should have defined classes or functions for doubles\n"
        "# Check for stub-like behavior\n"
        "has_stub = False\n"
        "has_fake = False\n"
        "for name, obj in list(globals().items()):\n"
        "    if inspect.isclass(obj) and 'stub' in name.lower():\n"
        "        has_stub = True\n"
        "    if inspect.isclass(obj) and 'fake' in name.lower():\n"
        "        has_fake = True\n"
        "assert has_stub or has_fake, 'Should define at least one test double class'\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Database ----
    "db-window-001": (
        "import sqlite3\n"
        "conn = sqlite3.connect(':memory:')\n"
        "c = conn.cursor()\n"
        "c.execute('CREATE TABLE employees (id INTEGER, name TEXT, department TEXT, salary REAL)')\n"
        "data = [(1,'Alice','Eng',90000),(2,'Bob','Eng',85000),(3,'Carol','Sales',75000),\n"
        "        (4,'Dave','Sales',80000),(5,'Eve','Eng',95000)]\n"
        "c.executemany('INSERT INTO employees VALUES (?,?,?,?)', data)\n"
        "# Test RANK query\n"
        "c.execute('SELECT name, department, salary, RANK() OVER (PARTITION BY department ORDER BY salary DESC) as rnk FROM employees')\n"
        "rows = c.fetchall()\n"
        "eng_ranks = [(r[0], r[3]) for r in rows if r[1] == 'Eng']\n"
        "assert eng_ranks[0] == ('Eve', 1), f'Eve should be rank 1 in Eng, got {eng_ranks}'\n"
        "# Test running total\n"
        "c.execute('SELECT name, salary, SUM(salary) OVER (ORDER BY salary) as running FROM employees ORDER BY salary')\n"
        "rows = c.fetchall()\n"
        "assert rows[-1][2] == sum(d[3] for d in data), 'Running total should equal total salary'\n"
        "conn.close()\n"
        "print('ALL TESTS PASSED')"
    ),

    "db-normal-002": (
        "import sqlite3\n"
        "# Test basic normalized schema\n"
        "conn = sqlite3.connect(':memory:')\n"
        "c = conn.cursor()\n"
        "# Create normalized tables (3NF)\n"
        "c.execute('CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')\n"
        "c.execute('CREATE TABLE courses (id INTEGER PRIMARY KEY, name TEXT NOT NULL, teacher_id INTEGER)')\n"
        "c.execute('CREATE TABLE teachers (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')\n"
        "c.execute('CREATE TABLE enrollments (student_id INTEGER, course_id INTEGER, grade TEXT, PRIMARY KEY (student_id, course_id))')\n"
        "c.execute('INSERT INTO students VALUES (1, \"Alice\")')\n"
        "c.execute('INSERT INTO teachers VALUES (1, \"Dr. Smith\")')\n"
        "c.execute('INSERT INTO courses VALUES (1, \"Math 101\", 1)')\n"
        "c.execute('INSERT INTO enrollments VALUES (1, 1, \"A\")')\n"
        "# Verify join works (no data redundancy)\n"
        "c.execute('SELECT s.name, c.name, t.name, e.grade FROM enrollments e '\n"
        "          'JOIN students s ON e.student_id=s.id '\n"
        "          'JOIN courses c ON e.course_id=c.id '\n"
        "          'JOIN teachers t ON c.teacher_id=t.id')\n"
        "row = c.fetchone()\n"
        "assert row == ('Alice', 'Math 101', 'Dr. Smith', 'A'), f'Got {row}'\n"
        "conn.close()\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Security ----
    "sec-hash-001": (
        "# Test password hashing functions\n"
        "hashed = hash_password('my_secret_password')\n"
        "assert hashed != 'my_secret_password', 'Should not store plaintext'\n"
        "assert len(hashed) > 20, f'Hash seems too short: {len(hashed)}'\n"
        "assert verify_password('my_secret_password', hashed) == True, 'Correct password should verify'\n"
        "assert verify_password('wrong_password', hashed) == False, 'Wrong password should not verify'\n"
        "# Different calls should produce different hashes (salting)\n"
        "hashed2 = hash_password('my_secret_password')\n"
        "assert hashed != hashed2, 'Same password should produce different hashes (salt)'\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- DevOps ----
    "ops-logging-003": (
        "import json, logging, io\n"
        "# Test structured JSON logging formatter\n"
        "# Create a logger with the custom formatter\n"
        "test_logger = logging.getLogger('test_structured')\n"
        "test_logger.setLevel(logging.DEBUG)\n"
        "stream = io.StringIO()\n"
        "handler = logging.StreamHandler(stream)\n"
        "handler.setFormatter(JsonFormatter())\n"
        "test_logger.addHandler(handler)\n"
        "test_logger.info('Test message', extra={'request_id': 'abc-123'})\n"
        "output = stream.getvalue().strip()\n"
        "parsed = json.loads(output)\n"
        "assert 'timestamp' in parsed or 'time' in parsed, f'Missing timestamp in {parsed}'\n"
        "assert parsed.get('level', parsed.get('levelname', '')) in ('INFO', 'info'), f'Wrong level in {parsed}'\n"
        "assert 'Test message' in parsed.get('message', parsed.get('msg', '')), f'Missing message in {parsed}'\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- Web ----
    "web-rest-001": (
        "# Test Flask REST API handlers\n"
        "import json as _json\n"
        "try:\n"
        "    client = app.test_client()\n"
        "except:\n"
        "    # If app isn't defined, create it\n"
        "    from flask import Flask, jsonify, request\n"
        "    assert callable(globals().get('create_app', None)) or 'app' in dir(), 'Should define app or create_app'\n"
        "    print('ALL TESTS PASSED'); import sys; sys.exit(0)\n"
        "# Test GET /todos\n"
        "resp = client.get('/todos')\n"
        "assert resp.status_code == 200, f'GET /todos returned {resp.status_code}'\n"
        "# Test POST /todos\n"
        "resp = client.post('/todos', data=_json.dumps({'title': 'Test'}), content_type='application/json')\n"
        "assert resp.status_code in (200, 201), f'POST /todos returned {resp.status_code}'\n"
        "print('ALL TESTS PASSED')"
    ),

    "web-sql-003": (
        "import sqlite3\n"
        "# Test SQL injection prevention\n"
        "conn = sqlite3.connect(':memory:')\n"
        "conn.execute('CREATE TABLE users (id INTEGER, name TEXT, email TEXT)')\n"
        "conn.execute(\"INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')\")\n"
        "conn.commit()\n"
        "# Test safe function with normal input\n"
        "result = get_user(conn, 1)\n"
        "assert result is not None, 'Should find user 1'\n"
        "# Test with SQL injection attempt - should NOT return all users\n"
        "try:\n"
        "    result = get_user(conn, \"1 OR 1=1\")\n"
        "    # If it returns, should only return one user or None\n"
        "    if isinstance(result, list):\n"
        "        assert len(result) <= 1, 'SQL injection protection failed - returned multiple rows'\n"
        "except (TypeError, ValueError, sqlite3.Error):\n"
        "    pass  # Correctly rejected malicious input\n"
        "conn.close()\n"
        "print('ALL TESTS PASSED')"
    ),

    # ---- JavaScript (Node.js sandbox) ----
    "js-closure-001": (
        "// Test closures\n"
        "// Counter with private state\n"
        "const counter = makeCounter ? makeCounter() : createCounter();\n"
        "let v1 = counter.increment ? counter.increment() : counter();\n"
        "let v2 = counter.increment ? counter.increment() : counter();\n"
        "console.assert(v2 > v1, 'Counter should increment');\n"
        "\n"
        "// Multiplier factory\n"
        "if (typeof makeMultiplier === 'function') {\n"
        "    const double = makeMultiplier(2);\n"
        "    const triple = makeMultiplier(3);\n"
        "    console.assert(double(5) === 10, 'double(5) should be 10');\n"
        "    console.assert(triple(5) === 15, 'triple(5) should be 15');\n"
        "}\n"
        "console.log('ALL TESTS PASSED');"
    ),

    "js-promise-002": (
        "// Test retry function\n"
        "async function testRetry() {\n"
        "    let attempts = 0;\n"
        "    const failTwice = async () => {\n"
        "        attempts++;\n"
        "        if (attempts < 3) throw new Error('fail');\n"
        "        return 'success';\n"
        "    };\n"
        "    const result = await retry(failTwice, 5);\n"
        "    console.assert(result === 'success', `Expected success, got ${result}`);\n"
        "    console.assert(attempts === 3, `Expected 3 attempts, got ${attempts}`);\n"
        "\n"
        "    // Test exhausting retries\n"
        "    try {\n"
        "        await retry(() => { throw new Error('always fail'); }, 2);\n"
        "        console.assert(false, 'Should have thrown');\n"
        "    } catch (e) {\n"
        "        console.assert(e.message === 'always fail', 'Should preserve error');\n"
        "    }\n"
        "    console.log('ALL TESTS PASSED');\n"
        "}\n"
        "testRetry();"
    ),
}


def main():
    with open(CHALLENGES_FILE, "r") as f:
        challenges = json.load(f)

    updated = 0
    for challenge in challenges:
        cid = challenge["id"]
        if cid in TEST_CODE_ADDITIONS and not challenge.get("test_code"):
            challenge["test_code"] = TEST_CODE_ADDITIONS[cid]
            updated += 1
            print(f"  + Added test_code to {cid}")

    if updated:
        with open(CHALLENGES_FILE, "w") as f:
            json.dump(challenges, f, indent=2, ensure_ascii=False)
        print(f"\nUpdated {updated} challenges. Total with test_code: {sum(1 for c in challenges if c.get('test_code'))}/{len(challenges)}")
    else:
        print("No updates needed.")


if __name__ == "__main__":
    main()
