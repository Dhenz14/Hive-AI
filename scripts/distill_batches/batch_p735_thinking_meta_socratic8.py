"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 8)

Final batch to reach 60 pairs for Phase 3C.
"""

PAIRS = [
    (
        "thinking/meta-socratic-simplest-solution-auth-service",
        r'''I want to add authentication to my Flask app. I'm planning to build a separate auth microservice with JWT token generation, refresh token rotation, token blacklisting, OAuth2 provider support, RBAC, and an admin dashboard. The app currently has 200 users. Should I build this?''',
        r'''<think>
My initial approach: A separate auth microservice sounds robust...

Q: Is this the simplest solution? 200 users?
A: 200 users is TINY. Most auth libraries handle millions of users. Building a separate microservice for 200 users is like building a custom CMS to write a blog post.

Q: What's the simplest auth that works?
A: Flask-Login + Flask-Bcrypt. It's session-based auth built into Flask. 20 lines of code for login/logout/protected routes.

Q: Do they actually need JWTs?
A: JWTs are for stateless auth in distributed systems. A single Flask app with 200 users doesn't need stateless auth. Server-side sessions are simpler, more secure (revocable), and sufficient.

Q: Do they need a separate microservice?
A: No. Auth in a separate service means:
  - Network call for every authenticated request
  - Single point of failure (auth service down = entire app down)
  - Token synchronization complexity
  - Two services to deploy, monitor, and maintain

For a monolith with 200 users, auth is just another module.

Q: Do they need OAuth2 provider support?
A: Probably not yet. If they do later, Flask-OAuthlib or Authlib adds it incrementally.

Q: Do they need RBAC?
A: With 200 users, probably just admin/regular. A boolean `is_admin` column works. Full RBAC is for complex permission hierarchies.

Q: What about using an auth SaaS?
A: Auth0, Clerk, or Firebase Auth handle everything — OAuth, MFA, RBAC — for free at 200 users. If they don't want to build auth at all, this is the answer.

This is a massive over-engineering situation.
</think>

**Way over-engineered for 200 users.** Here's what you actually need:

**Option 1 — Flask-Login (10 minutes):**
```python
from flask_login import LoginManager, login_user, login_required, current_user
from flask_bcrypt import Bcrypt

login_manager = LoginManager(app)
bcrypt = Bcrypt(app)

@app.route('/login', methods=['POST'])
def login():
    user = User.query.filter_by(email=request.form['email']).first()
    if user and bcrypt.check_password_hash(user.password, request.form['password']):
        login_user(user)
        return redirect('/dashboard')
    flash('Invalid credentials')
    return redirect('/login')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)
```

**Option 2 — Auth SaaS (if you don't want to build auth at all):**
- Auth0, Clerk, or Firebase Auth — free for 200 users
- Handles OAuth, MFA, password reset, email verification
- You focus on your app, not auth infrastructure

**Your proposed features vs what you need:**

| Feature | Need at 200 users? | Simple alternative |
|---------|--------------------|--------------------|
| Separate microservice | No | Flask module |
| JWT tokens | No | Server-side sessions |
| Refresh token rotation | No | Session cookie |
| Token blacklisting | No | Session invalidation (built-in) |
| OAuth2 provider | Maybe later | Add Authlib when needed |
| RBAC | No | `is_admin` boolean column |
| Admin dashboard | No | Flask-Admin (10 lines) |

**When to build a dedicated auth service:**
- 100K+ users across multiple applications
- Multiple apps sharing the same user base
- Compliance requirements (SOC2, HIPAA)
- Dedicated security team to maintain it

At 200 users, use Flask-Login or an auth SaaS.'''
    ),
    (
        "thinking/meta-socratic-anchored-graphql",
        r'''I'm building a simple blog API with posts and comments. I want to use GraphQL because it's "more modern" than REST. Here's my plan:

```python
# schema.py
import graphene
from graphene_sqlalchemy import SQLAlchemyObjectType

class PostType(SQLAlchemyObjectType):
    class Meta:
        model = Post

class CommentType(SQLAlchemyObjectType):
    class Meta:
        model = Comment

class Query(graphene.ObjectType):
    posts = graphene.List(PostType)
    post = graphene.Field(PostType, id=graphene.Int())

    def resolve_posts(self, info):
        return Post.query.all()

    def resolve_post(self, info, id):
        return Post.query.get(id)

class CreatePost(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        content = graphene.String(required=True)

    post = graphene.Field(PostType)

    def mutate(self, info, title, content):
        post = Post(title=title, content=content)
        db.session.add(post)
        db.session.commit()
        return CreatePost(post=post)
```

Good approach?''',
        r'''<think>
My initial approach: GraphQL for a blog API...

Q: Am I anchored on "GraphQL is more modern"? Is modern = better?
A: "More modern" isn't a technical reason. Let me evaluate on actual merits.

Q: What problem does GraphQL solve?
A: GraphQL solves:
  - Over-fetching: getting too many fields when you only need a few
  - Under-fetching: needing multiple requests to get related data
  - Schema evolution: adding fields without versioning

Q: Does a blog API have these problems?
A: A blog has:
  - GET /posts — returns title, content, author, date. Client always needs all of these. No over-fetching.
  - GET /posts/1 with comments — one JOIN query. No under-fetching.
  - Simple, stable schema — posts and comments rarely change structure.

GraphQL's advantages don't apply here.

Q: What does GraphQL COST for a blog?
A:
  - More complex setup (schema definitions, resolvers)
  - N+1 query problem (each post resolves comments separately unless using DataLoader)
  - No HTTP caching (all POST requests to /graphql)
  - Harder to rate limit (one endpoint, varying query complexity)
  - Less tooling for monitoring and debugging
  - More code for the same functionality

Q: How much code for the same blog API in REST?
A:
```python
@app.route('/posts')
def list_posts():
    return jsonify([p.to_dict() for p in Post.query.all()])

@app.route('/posts/<int:id>')
def get_post(id):
    post = Post.query.get_or_404(id)
    return jsonify(post.to_dict())
```
Half the code, standard HTTP caching, familiar to everyone.

Q: When IS GraphQL the right choice?
A: Mobile apps with bandwidth constraints, apps with deeply nested related data, APIs consumed by multiple clients with different data needs.

A blog API is the textbook case where REST is perfect.
</think>

**GraphQL is overkill for a blog API.** REST solves this in half the code with better caching and simpler tooling.

**REST version (simpler, faster to build):**
```python
@app.route('/posts')
def list_posts():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return jsonify([p.to_dict() for p in posts])

@app.route('/posts/<int:id>')
def get_post(id):
    post = Post.query.get_or_404(id)
    return jsonify(post.to_dict(include_comments=True))

@app.route('/posts', methods=['POST'])
def create_post():
    data = request.get_json()
    post = Post(title=data['title'], content=data['content'])
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict()), 201
```

**Why REST wins for a blog:**

| Concern | REST | GraphQL |
|---------|------|---------|
| Code complexity | 15 lines | 40+ lines |
| HTTP caching | Built-in (GET cacheable) | No (all POST requests) |
| N+1 queries | Eager load in query | Need DataLoader |
| Rate limiting | Per endpoint | Per query complexity |
| Monitoring | Standard HTTP metrics | Custom query analysis |
| Learning curve | Universal | Team must learn GraphQL |

**GraphQL's "over-fetching" problem doesn't exist here:**
```
GET /posts returns: title, content, author, date
Client needs:       title, content, author, date
Over-fetching:      zero
```

**When GraphQL IS justified:**
- Mobile apps with bandwidth constraints (fetch exactly needed fields)
- Complex nested data (user → orders → items → reviews)
- Multiple clients needing different views of the same data
- Rapidly evolving schema with many consumers

A blog API has none of these. Use REST.'''
    ),
    (
        "thinking/meta-socratic-testing-coverage-false",
        r'''We have 95% code coverage on our Python project. My manager says our code quality must be excellent since we have high coverage. Is that right?''',
        r'''<think>
Q: Am I testing what matters or what's easy to measure?

Q: Does 95% coverage mean 95% of bugs are caught?
A: No. Code coverage means 95% of lines EXECUTED during tests, not that 95% of behavior is VERIFIED. A test can execute code without checking its correctness.

Q: Can you have 100% coverage with zero useful tests?
A: Yes:
```python
def calculate_tax(income):
    if income <= 50000:
        return income * 0.2
    return income * 0.3

# "Test" with 100% coverage:
def test_tax():
    calculate_tax(30000)  # Executes branch 1
    calculate_tax(60000)  # Executes branch 2
    # No assertions! Never checks if results are correct!
```
This has 100% line coverage but tests NOTHING.

Q: What does coverage actually miss?
A:
  - Missing functionality: code that SHOULD exist but doesn't (no test for edge cases that aren't handled)
  - Integration issues: each unit tested alone, but they fail when combined
  - Concurrency bugs: race conditions not triggered by sequential tests
  - Error handling: happy path covered, but error paths return wrong values
  - Security: XSS, injection — not caught by functional tests
  - Performance: O(n²) algorithm with 100% coverage

Q: What metrics better indicate code quality?
A:
  - Mutation testing: automatically introduce bugs, check if tests catch them
  - Bug escape rate: how many bugs reach production?
  - Test quality: do tests have meaningful assertions?
  - Integration test coverage: not just unit tests

Q: What should I tell the manager?
A: Coverage is a necessary but not sufficient condition. Low coverage = definitely under-tested. High coverage ≠ well-tested. It's like saying "we visited every room in the house" — you visited but did you check the plumbing?
</think>

**No. 95% coverage means 95% of lines EXECUTED, not 95% of bugs caught.** Coverage is a useful metric but a terrible quality indicator on its own.

**How 95% coverage can be meaningless:**

```python
# 100% coverage, ZERO value:
def test_process_order():
    process_order(sample_order)  # Runs all lines
    # No assertions — never checks if the order was processed correctly

# 100% coverage, misses the critical bug:
def divide(a, b):
    return a / b  # What about b=0?

def test_divide():
    assert divide(10, 2) == 5   # ✅ Covers the only line
    # Never tests divide(10, 0) → ZeroDivisionError
```

**What coverage DOES tell you:**
- Lines that are NEVER executed → definitely untested
- Useful for finding dead code or untested branches

**What coverage DOESN'T tell you:**
- Whether assertions are correct
- Whether edge cases are tested
- Whether error paths handle errors properly
- Whether security vulnerabilities exist
- Whether performance is acceptable

**Better quality indicators:**

| Metric | What it measures |
|--------|-----------------|
| Mutation testing | Do tests detect introduced bugs? |
| Bug escape rate | How many bugs reach production? |
| Assertion density | Number of assertions per test |
| Test failure on bad code | Does `mutmut` find untested logic? |
| Integration test coverage | Does the system work end-to-end? |

**Try mutation testing:**
```bash
pip install mutmut
mutmut run  # Introduces bugs, checks if tests catch them

# Result might show:
# 95% line coverage, but only 60% mutation score
# = 40% of bugs would NOT be caught by your tests
```

**What to tell your manager:** "95% coverage means we've touched 95% of the code. To know if we're actually catching bugs, we should look at mutation testing scores and our production bug rate."'''
    ),
    (
        "thinking/meta-socratic-coupling-orm-views",
        r'''In my Django views, I query the database directly:

```python
# views.py
def user_dashboard(request):
    user = request.user
    recent_orders = Order.objects.filter(
        user=user, status__in=['pending', 'processing']
    ).select_related('product').order_by('-created_at')[:10]

    total_spent = Order.objects.filter(
        user=user, status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    recommendations = Product.objects.filter(
        category__in=user.favorite_categories.all()
    ).exclude(
        id__in=Order.objects.filter(user=user).values('product_id')
    ).order_by('-rating')[:5]

    return render(request, 'dashboard.html', {
        'orders': recent_orders,
        'total_spent': total_spent,
        'recommendations': recommendations,
    })
```

Is putting these queries in the view okay?''',
        r'''<think>
My initial approach: Django views often contain queries...

Q: Am I introducing tight coupling? Let me think about what changes would require modifying this view.

Q: What if the business logic changes?
A: "Recent orders" means status in ['pending', 'processing']. If we add a 'shipped' status that should also appear, we modify the VIEW. If we change how recommendations work (ML-based instead of category-based), we modify the VIEW. The view is coupled to business rules.

Q: What if we need the same data elsewhere?
A: If a mobile API endpoint needs "recent orders," we'd copy-paste the query. Now the definition of "recent orders" exists in two places. Change one, forget the other → inconsistency.

Q: Is this actually a problem for this specific codebase?
A: It depends. For a small project with one developer, this is FINE. For a growing project where:
  - Multiple views need the same queries
  - Business logic is complex
  - Multiple developers work on the codebase
  ...then yes, it becomes a problem.

Q: Am I over-engineering by suggesting a service layer?
A: For a simple dashboard with 3 queries? Maybe. The Django convention is "fat models, thin views." The middle ground is model managers or model methods.

Q: What would Django's conventions suggest?
A: Custom managers or model methods:
  ```python
  class OrderManager(models.Manager):
      def recent_for_user(self, user):
          return self.filter(user=user, status__in=['pending', 'processing'])...
  ```

This keeps queries near the model (where they belong) without adding a full service layer.

Q: What would the next maintainer think?
A: Complex ORM queries in views are hard to unit test (need full request/response cycle). Model methods can be tested independently.

The answer depends on project size. For a small project, this is fine. For a growing one, move to model managers.
</think>

**It depends on project size.** For a small project, this is standard Django. For a growing project, the queries should move closer to the models.

**The problem with queries in views:**
- **Duplication**: If an API endpoint also needs "recent orders," you copy the query
- **Testability**: Testing this view requires HTTP request setup. Testing a model method just needs a model
- **Business logic scattered**: "recent = pending + processing" is a business rule living in a view

**Django-idiomatic fix — custom managers:**
```python
# models.py
class OrderQuerySet(models.QuerySet):
    def recent_for_user(self, user):
        return self.filter(
            user=user, status__in=['pending', 'processing']
        ).select_related('product').order_by('-created_at')

    def total_spent_by(self, user):
        result = self.filter(
            user=user, status='completed'
        ).aggregate(total=Sum('amount'))
        return result['total'] or 0

class Order(models.Model):
    objects = OrderQuerySet.as_manager()
    # ...

class Product(models.Model):
    @classmethod
    def recommendations_for(cls, user, limit=5):
        return cls.objects.filter(
            category__in=user.favorite_categories.all()
        ).exclude(
            id__in=Order.objects.filter(user=user).values('product_id')
        ).order_by('-rating')[:limit]
```

```python
# views.py — thin and clean
def user_dashboard(request):
    user = request.user
    return render(request, 'dashboard.html', {
        'orders': Order.objects.recent_for_user(user)[:10],
        'total_spent': Order.objects.total_spent_by(user),
        'recommendations': Product.recommendations_for(user),
    })
```

**Benefits:**
- Reusable: API view uses same `Order.objects.recent_for_user(user)`
- Testable: `assert Order.objects.total_spent_by(user) == 150.00`
- Single definition: "recent orders" defined once in the manager
- Django-idiomatic: fat models, thin views

**When to keep queries in views:**
- Small project, single developer
- Query used in exactly one place
- Simple queries (no business logic)

**When to extract to managers/services:**
- Same query needed in multiple views
- Complex business logic in filters
- Team > 2 developers
- You need to unit test the query logic'''
    ),
    (
        "thinking/meta-socratic-not-considering-backwards-compat",
        r'''I'm renaming our API field from `userName` to `username` to follow Python conventions. I'll update the response schema:

```python
# Before:
return {'userName': user.name, 'email': user.email}

# After:
return {'username': user.name, 'email': user.email}
```

Simple rename. Should I just deploy this?''',
        r'''<think>
My initial approach: Rename the field, deploy.

Q: What am I not considering?

Q: Who consumes this API?
A: Every client — mobile apps, frontend SPAs, third-party integrations, internal services. ALL of them currently expect `userName`. Changing to `username` breaks ALL of them simultaneously.

Q: Is this a breaking change?
A: YES. Any client doing `response.data.userName` gets `undefined`. Any client deserializing into a class with a `userName` field gets null.

Q: How bad is a breaking API change?
A:
  - Web frontend: you control it, update simultaneously → fixable
  - Mobile apps: users have old app versions that can't be force-updated → BROKEN for days/weeks
  - Third-party integrations: partners using your API → BROKEN until they notice and update
  - Internal services: other teams consuming your API → BROKEN, angry colleagues

Q: What's the safe way to rename an API field?
A: Gradual migration:
  1. Add new field (`username`) alongside old field (`userName`)
  2. Notify consumers to switch
  3. Monitor usage of old field
  4. Deprecate old field
  5. Eventually remove old field

Q: How long should the transition period be?
A: Depends on your consumers:
  - Only internal web frontend: same PR can update both → minutes
  - Mobile apps: until old versions fall below threshold → months
  - Third-party APIs: contractual notice period → could be months to years

Q: Is this rename even worth the effort?
A: For an already-deployed API with consumers, consistency with Python conventions matters less than not breaking clients. The field name works. Leave it.

Never deploy breaking API changes without a migration path.
</think>

**Do NOT just deploy this.** This is a breaking change that will immediately break every client consuming your API.

**What breaks:**
```javascript
// Every frontend/mobile app doing this:
const name = response.data.userName;  // → undefined after your change

// Every third-party integration:
user_name = api_response['userName']  # → KeyError
```

**Safe migration path:**

**Step 1: Return both fields**
```python
return {
    'username': user.name,     # New field
    'userName': user.name,     # Old field (deprecated)
    'email': user.email
}
```

**Step 2: Notify consumers**
```python
# Add deprecation header
response.headers['Deprecation'] = 'true'
response.headers['Sunset'] = 'Wed, 01 Jun 2026 00:00:00 GMT'

# Log which clients still use the old field
if 'userName' in request.args.get('fields', ''):
    logger.info(f"Client using deprecated userName field",
        extra={'client': request.headers.get('User-Agent')})
```

**Step 3: Monitor and remove**
- Track usage of `userName` in logs
- When no clients use it → remove in next major version

**Or: just don't rename it.**

An API field name that works is more valuable than one that follows Python conventions. `userName` is valid JSON and every client already handles it. The cost of renaming (migration, coordination, potential breakage) vastly exceeds the benefit (slightly prettier field name).

**When breaking changes ARE acceptable:**
- API is versioned (`/v1/users` → `/v2/users`)
- Only consumed by your own frontend (deploy simultaneously)
- Pre-production / no external consumers
- Major version bump with migration period'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
