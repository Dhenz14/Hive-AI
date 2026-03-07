"""
Response variety training pairs - Conversational, warm tone
Opens with natural language, no headers. Feels like talking to a senior dev.
"""

pairs = [
    {
        "instruction": r'''How do I remove duplicates from a Python list while preserving order?''',
        "output": r'''So the classic trick here is to use a dict, since Python 3.7+ guarantees insertion order in dicts. You just do:

```python
items = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
unique = list(dict.fromkeys(items))
# [3, 1, 4, 5, 9, 2, 6]
```

That's it -- one line, preserves order, and it's fast because dict lookups are O(1).

If you need it as a reusable function with a key function (like deduplicating objects by a specific attribute), here's what I'd reach for:

```python
def deduplicate(items, key=None):
    seen = set()
    result = []
    for item in items:
        k = key(item) if key else item
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result

# Usage with objects
users = [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 1, "name": "Alice (duplicate)"},
]
unique_users = deduplicate(users, key=lambda u: u["id"])
# [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
```

The set-based approach is better when you need a custom key because `dict.fromkeys` only works when the items themselves are hashable and are what you want to deduplicate by. For simple lists of strings or numbers though, `dict.fromkeys` is the way to go.'''
    },
    {
        "instruction": r'''My JavaScript fetch calls keep failing with CORS errors in development. How do I fix this?''',
        "output": r'''This is a classic dev environment headache. The browser is blocking your frontend (say, localhost:3000) from calling your API (localhost:8000) because they're different origins.

You've got two solid options depending on your setup:

If you control the backend, add CORS headers there. For Express:

```javascript
const cors = require('cors');

// Allow your dev frontend origin
app.use(cors({
    origin: 'http://localhost:3000',
    credentials: true
}));
```

For production you'd lock that down to your actual domain, but for dev this works great.

If you don't control the backend (or just want a quick fix), set up a proxy in your frontend dev server. For Vite:

```javascript
// vite.config.js
export default defineConfig({
    server: {
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, '')
            }
        }
    }
});
```

Now your frontend calls `/api/users` and Vite forwards it to `http://localhost:8000/users`. No CORS issue because the browser thinks it's the same origin.

One thing to watch out for -- if you're sending cookies or auth headers, make sure `credentials: 'include'` is set on your fetch call AND the server allows it. That trips people up constantly.'''
    },
    {
        "instruction": r'''What's the best way to write a SQL query that finds customers who made purchases in every month of 2024?''',
        "output": r'''This is a classic relational division problem, and honestly it's one of those SQL puzzles that looks simple but has a few gotchas.

The cleanest approach is to count distinct months per customer and check if it equals 12:

```sql
SELECT c.customer_id, c.name
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_date >= '2024-01-01'
  AND o.order_date < '2025-01-01'
GROUP BY c.customer_id, c.name
HAVING COUNT(DISTINCT EXTRACT(MONTH FROM o.order_date)) = 12;
```

The reason I use `EXTRACT(MONTH FROM ...)` with `COUNT(DISTINCT ...)` is that a customer might have multiple orders in the same month, and we only want to count each month once.

Also notice I'm using `< '2025-01-01'` instead of `<= '2024-12-31'` -- this handles timestamps correctly. If your order_date has a time component, `<= '2024-12-31'` would miss anything after midnight on Dec 31st.

If you wanted to make this more flexible (say, find customers active in at least N of the last M months), you'd parameterize it:

```sql
SELECT customer_id, COUNT(DISTINCT DATE_TRUNC('month', order_date)) AS active_months
FROM orders
WHERE order_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY customer_id
HAVING COUNT(DISTINCT DATE_TRUNC('month', order_date)) >= 10;
```

That version is more useful for real analytics work where "every single month" might be too strict.'''
    },
    {
        "instruction": r'''How do I set up a multi-stage Docker build for a Node.js app?''',
        "output": r'''The idea behind multi-stage builds is simple -- you use one stage to build your app (with all the dev dependencies, compilers, etc.) and then copy just the output into a lean production image. Your final image ends up way smaller.

Here's what I'd use for a typical Node.js app:

```dockerfile
# Stage 1: Install dependencies and build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Production image
FROM node:20-alpine AS production
WORKDIR /app

# Only install production deps
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy built output from builder stage
COPY --from=builder /app/dist ./dist

# Non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 3000
CMD ["node", "dist/index.js"]
```

A few things worth noting here. First, I copy `package*.json` before the rest of the source code -- this means Docker caches the `npm ci` layer, so reinstalling dependencies only happens when package.json actually changes. Huge time saver during development.

Second, `npm ci` instead of `npm install` -- it's faster and deterministic because it installs exactly what's in package-lock.json.

Third, running as a non-root user is a security best practice that a lot of people skip. Takes two lines and prevents a whole class of container escape vulnerabilities.

Your final image will only have the production node_modules and the compiled dist folder -- typically 5-10x smaller than if you'd done everything in one stage.'''
    },
    {
        "instruction": r'''I accidentally committed a large file to git. How do I remove it from the history?''',
        "output": r'''Oh no, we've all been there. The good news is it's fixable, but the approach depends on whether you've pushed yet.

If you haven't pushed, it's easy -- just do an interactive rebase:

```bash
# If it was in the last commit
git reset HEAD~1
# Remove the file, recommit without it
echo "big_file.bin" >> .gitignore
git add .gitignore
git rm --cached big_file.bin
git commit -m "Add feature without the large file"
```

If it's buried a few commits back, `git rebase -i` works but gets messy. The better tool is `git filter-repo` (install it with pip):

```bash
pip install git-filter-repo

# Remove the file from ALL history
git filter-repo --invert-paths --path big_file.bin

# Don't forget to prevent it from coming back
echo "big_file.bin" >> .gitignore
git add .gitignore
git commit -m "Add big_file.bin to gitignore"
```

If you already pushed, you still run filter-repo but then need a force push:

```bash
git push --force-with-lease origin main
```

Heads up -- `--force-with-lease` is safer than `--force` because it won't overwrite someone else's changes. But either way, tell your team because they'll need to re-clone or do a hard reset.

One more thing: add a `.gitattributes` or pre-commit hook to prevent this from happening again:

```bash
# .pre-commit-config.yaml (using pre-commit framework)
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
        args: ['--maxkb=500']
```

That'll block any file over 500KB from being committed.'''
    },
]
