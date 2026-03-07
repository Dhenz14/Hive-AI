"""
Anti-pattern training pairs - Database anti-patterns
Topics: N+1 queries, SELECT *, no indexes, string SQL, no transactions
"""

pairs = [
    {
        "instruction": r'''My Django view is slow when displaying a list of blog posts with their authors. It takes 3 seconds for 100 posts:

```python
# views.py
def post_list(request):
    posts = Post.objects.all()
    data = []
    for post in posts:
        data.append({
            'title': post.title,
            'author_name': post.author.name,
            'author_email': post.author.email,
        })
    return JsonResponse({'posts': data})
```''',
        "output": r'''<think>
Classic N+1 query problem. Post.objects.all() runs 1 query for all posts, then accessing post.author triggers a separate query for each post's author. 100 posts = 101 SQL queries. The fix is select_related which does a JOIN in one query. The user sees slowness but doesn't realize the ORM is generating hundreds of queries behind the scenes.
</think>

This is the **N+1 query problem**, the most common ORM performance killer. Your code executes 101 SQL queries, not 1.

**What happens behind the scenes:**

```sql
-- Query 1: get all posts
SELECT * FROM posts;

-- Query 2: get author for post 1
SELECT * FROM authors WHERE id = 1;
-- Query 3: get author for post 2
SELECT * FROM authors WHERE id = 2;
-- ... 98 more queries, one per post
```

Each `post.author` triggers a separate database query because Django lazy-loads relationships by default.

**The fix -- use `select_related` for foreign keys:**

```python
def post_list(request):
    # ONE query with a JOIN
    posts = Post.objects.select_related('author').all()
    data = []
    for post in posts:
        data.append({
            'title': post.title,
            'author_name': post.author.name,  # no extra query
            'author_email': post.author.email,
        })
    return JsonResponse({'posts': data})
```

This generates a single query:

```sql
SELECT posts.*, authors.*
FROM posts
INNER JOIN authors ON posts.author_id = authors.id;
```

**101 queries down to 1.** Your 3-second view will likely drop to under 50ms.

**Quick reference:**
- `select_related('fk_field')` -- for ForeignKey/OneToOne (uses SQL JOIN)
- `prefetch_related('m2m_field')` -- for ManyToMany/reverse ForeignKey (uses 2 queries)

**How to detect N+1 in the future:** Use `django-debug-toolbar` in development. It shows the query count per request. If you see 100+ queries on a list page, you almost certainly have an N+1 problem.'''
    },
    {
        "instruction": r'''What's wrong with this query? It returns what I need:

```python
cursor.execute("SELECT * FROM orders WHERE customer_id = %s", (customer_id,))
orders = cursor.fetchall()
# I only use order_id, status, and total from each row
```''',
        "output": r'''<think>
SELECT * anti-pattern. The user only needs 3 columns but fetches all of them. This wastes bandwidth, memory, and prevents the database from using covering indexes. It also creates fragile code -- if someone adds a large BLOB column later, this query silently slows down. At least they are using parameterized queries (the %s), so no SQL injection.
</think>

The query works, but `SELECT *` is an anti-pattern when you only need specific columns. You use 3 columns but fetch all of them.

**Why SELECT * hurts:**

1. **Wasted bandwidth and memory.** If the `orders` table has 20 columns including a `notes` TEXT field with kilobytes of data, you transfer and store all of that for nothing.

2. **Breaks covering indexes.** If you have an index on `(customer_id, status, total)`, the database can answer your query entirely from the index without touching the table. But `SELECT *` forces it to read the full row from disk.

3. **Fragile code.** If someone adds a `large_attachment BYTEA` column next month, your query silently starts transferring megabytes of blob data. With explicit columns, this cannot happen.

4. **Unclear intent.** A reader cannot tell which columns matter without reading all the code that uses the result.

**The fix -- select only what you need:**

```python
cursor.execute(
    "SELECT order_id, status, total FROM orders WHERE customer_id = %s",
    (customer_id,)
)
orders = cursor.fetchall()
```

**With an ORM like SQLAlchemy:**

```python
# BAD
session.query(Order).filter_by(customer_id=cid).all()

# GOOD -- only loads 3 columns
session.query(Order.id, Order.status, Order.total)\
    .filter_by(customer_id=cid).all()

# Django equivalent:
Order.objects.filter(customer_id=cid).values('id', 'status', 'total')
```

**When SELECT * is acceptable:** Quick ad-hoc queries during debugging, or when you genuinely need every column. In application code, always list your columns explicitly.'''
    },
    {
        "instruction": r'''My users table has millions of rows and this query takes 30 seconds:

```sql
SELECT * FROM users WHERE email = 'alice@example.com';
```

I don't understand why it's slow -- I'm only looking for one row.''',
        "output": r'''<think>
Missing index on the email column. Without an index, the database must do a full table scan -- reading every single row to find the one matching email. With millions of rows this is extremely slow. The user thinks "one row" should be fast, not realizing the database doesn't know where that row is without an index. Simple fix: CREATE INDEX.
</think>

Without an index on the `email` column, the database must read every single row in the table to find the match. This is called a **full table scan**. With millions of rows, it reads millions of rows to return just one.

**Think of it like a book without an index:** To find a topic, you must read every page. Add an index, and you jump straight to the right page.

**The fix:**

```sql
CREATE INDEX idx_users_email ON users (email);
```

After this, the same query uses the index to jump directly to the matching row. It goes from scanning millions of rows to reading 2-3 index pages. Your 30-second query will take under 1 millisecond.

**Check if you have indexes with:**

```sql
-- PostgreSQL
\d users

-- MySQL
SHOW INDEX FROM users;
```

**Common columns that need indexes:**
- Anything in a `WHERE` clause that runs frequently
- Foreign keys (`user_id`, `order_id`, etc.)
- Columns used in `JOIN` conditions
- Columns used in `ORDER BY` on large result sets

**For unique columns like email, use a unique index:**

```sql
CREATE UNIQUE INDEX idx_users_email ON users (email);
```

This also enforces uniqueness at the database level -- no two users can have the same email.

**Warning:** Don't add indexes blindly to every column. Each index slows down INSERT/UPDATE/DELETE operations because the index must be updated too. Index the columns that appear in your frequent queries.'''
    },
    {
        "instruction": r'''I build my queries dynamically based on filters the user selects. Here's my approach:

```python
def search_products(filters):
    query = "SELECT id, name, price FROM products WHERE 1=1"

    if filters.get('category'):
        query += f" AND category = '{filters['category']}'"
    if filters.get('min_price'):
        query += f" AND price >= {filters['min_price']}"
    if filters.get('max_price'):
        query += f" AND price <= {filters['max_price']}"
    if filters.get('name'):
        query += f" AND name LIKE '%{filters['name']}%'"

    cursor.execute(query)
    return cursor.fetchall()
```''',
        "output": r'''<think>
SQL injection via string concatenation. Even though dynamic query building is a valid need, the user is interpolating user input directly into SQL using f-strings. Every filter parameter is an injection vector. The WHERE 1=1 trick is fine for building dynamic queries, but the values must be parameterized. Need to show how to build dynamic queries safely.
</think>

Every single filter is a SQL injection vector. An attacker can pass `category = "'; DROP TABLE products; --"` and destroy your data.

The need for dynamic queries is valid, but you must **parameterize the values**. Here is how to build dynamic queries safely:

**The fix -- dynamic query with parameter list:**

```python
def search_products(filters):
    query = "SELECT id, name, price FROM products WHERE 1=1"
    params = []

    if filters.get('category'):
        query += " AND category = %s"
        params.append(filters['category'])

    if filters.get('min_price'):
        query += " AND price >= %s"
        params.append(filters['min_price'])

    if filters.get('max_price'):
        query += " AND price <= %s"
        params.append(filters['max_price'])

    if filters.get('name'):
        query += " AND name LIKE %s"
        params.append(f"%{filters['name']}%")

    cursor.execute(query, params)
    return cursor.fetchall()
```

**What changed:**
- Every value is replaced with `%s` (the placeholder)
- Values are collected in a list and passed to `execute()` separately
- The database driver handles escaping and quoting -- injection is impossible

**The LIKE wildcard is tricky.** Note that `%` for the LIKE pattern is in the parameter value, not in the SQL string. The `%s` in the SQL is the placeholder.

**With SQLAlchemy, this is even cleaner:**

```python
from sqlalchemy import select, and_

def search_products(filters):
    stmt = select(Product)
    conditions = []

    if filters.get('category'):
        conditions.append(Product.category == filters['category'])
    if filters.get('min_price'):
        conditions.append(Product.price >= filters['min_price'])

    if conditions:
        stmt = stmt.where(and_(*conditions))

    return session.execute(stmt).scalars().all()
```

The ORM approach makes it impossible to accidentally write raw SQL with user input.'''
    },
    {
        "instruction": r'''I'm transferring money between accounts. This works in my testing:

```python
def transfer(from_account, to_account, amount):
    cursor.execute(
        "UPDATE accounts SET balance = balance - %s WHERE id = %s",
        (amount, from_account)
    )
    cursor.execute(
        "UPDATE accounts SET balance = balance + %s WHERE id = %s",
        (amount, to_account)
    )
    connection.commit()
```''',
        "output": r'''<think>
No transaction safety. If the first UPDATE succeeds but the second fails (crash, network error, constraint violation), money disappears from one account but never arrives in the other. The commit at the end is too late if the process dies between the two updates. Need to wrap in a transaction and handle errors atomically. Also missing balance check for overdraft.
</think>

This code can lose money. If the first UPDATE succeeds (deducting from the sender) but the second fails (crash, network error, disk full), the money vanishes. The sender's balance is reduced but the recipient never gets it.

**What can go wrong between the two UPDATEs:**
- Server crashes or power loss
- Network timeout to the database
- A constraint violation on the second account
- The process is killed by the OS

**The fix -- use an explicit transaction with error handling:**

```python
def transfer(from_account, to_account, amount):
    try:
        # Start explicit transaction
        cursor.execute("BEGIN")

        # Check sufficient balance
        cursor.execute(
            "SELECT balance FROM accounts WHERE id = %s FOR UPDATE",
            (from_account,)
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Source account not found")
        if row[0] < amount:
            raise ValueError("Insufficient balance")

        cursor.execute(
            "UPDATE accounts SET balance = balance - %s WHERE id = %s",
            (amount, from_account)
        )
        cursor.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (amount, to_account)
        )

        connection.commit()  # both succeed or neither does

    except Exception:
        connection.rollback()  # undo everything
        raise
```

**Key improvements:**
1. **Atomic transaction** -- `BEGIN` ... `COMMIT` ensures both updates happen together. If anything fails, `ROLLBACK` undoes all changes.
2. **Balance check with `FOR UPDATE`** -- locks the row to prevent concurrent transfers from overdrawing. Without this, two simultaneous transfers could both pass the balance check.
3. **Rollback on error** -- any failure between BEGIN and COMMIT undoes all changes, so money is never lost.

**This is exactly why databases have transactions.** Financial operations, inventory updates, and any multi-step change that must be all-or-nothing should always use explicit transactions.'''
    },
]
