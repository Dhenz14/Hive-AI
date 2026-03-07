"""
Ambiguous request handling pairs - underspecified feature requests
"""

pairs = [
    {
        "instruction": r'''Add search to our app.''',
        "output": r'''<think>
"Add search" -- search over what? A product catalog? Users? Documents? Full-text search or just filtering? Frontend autocomplete or backend API? Do they need fuzzy matching, relevance ranking, faceted search? What's the data size -- hundreds of records (just use SQL LIKE) or millions (need Elasticsearch)? Way too vague to implement without clarification.
</think>

Search can range from simple filtering to a full search engine. A few questions:

1. **What are users searching for?** Products, users, documents, messages, something else?
2. **How much data?** Hundreds of records, thousands, millions? This determines whether SQL is enough or you need something like Elasticsearch.
3. **What features matter?** Simple text matching? Fuzzy/typo-tolerant? Autocomplete? Filters (category, date range)?

Here's a practical starting point assuming a medium-sized dataset (under 100k records) with PostgreSQL -- this covers most apps without adding infrastructure:

```python
# Simple but effective: PostgreSQL full-text search
from sqlalchemy import func, or_

class ProductSearch:
    def __init__(self, db_session):
        self.db = db_session

    def search(self, query: str, category: str = None, limit: int = 20, offset: int = 0):
        """Search products by name and description with optional category filter."""
        base = self.db.query(Product)

        if query:
            # PostgreSQL full-text search with ranking
            ts_query = func.plainto_tsquery("english", query)
            ts_vector = func.to_tsvector(
                "english",
                func.coalesce(Product.name, "") + " " + func.coalesce(Product.description, "")
            )
            base = base.filter(ts_vector.op("@@")(ts_query))
            base = base.order_by(func.ts_rank(ts_vector, ts_query).desc())

        if category:
            base = base.filter(Product.category == category)

        total = base.count()
        results = base.offset(offset).limit(limit).all()

        return {
            "results": [r.to_dict() for r in results],
            "total": total,
            "query": query,
        }

# API endpoint
@app.get("/api/search")
def search_products(q: str = "", category: str = None, page: int = 1, per_page: int = 20):
    searcher = ProductSearch(db.session)
    return searcher.search(q, category=category, limit=per_page, offset=(page - 1) * per_page)
```

```sql
-- Add a GIN index for fast full-text search (run once)
CREATE INDEX idx_products_search ON products
    USING GIN (to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')));
```

If you need autocomplete, fuzzy matching, or the dataset is over 100k records, we should look at Elasticsearch or Typesense instead. Let me know what you're searching over and I'll tailor the solution.'''
    },
    {
        "instruction": r'''We need notifications in our app.''',
        "output": r'''<think>
"We need notifications" -- this is very underspecified. What kind? Email, push (mobile/web), in-app (toasts/bell icon), SMS? What triggers them -- user actions, system events, scheduled reminders? Do they need read/unread tracking? Preferences (users opting out of certain types)? Real-time delivery? This is a significant feature that needs scoping before building.
</think>

Notifications is a big feature with many dimensions. Let me ask:

1. **What channels?** In-app (bell icon), email, push notifications (mobile/web), SMS, or some combination?
2. **What triggers them?** Examples: "someone commented on your post", "your order shipped", "payment failed", "reminder: meeting in 1 hour"?
3. **Do users need preferences?** Can they mute certain notification types or channels?

Here's a flexible notification system design that supports multiple channels. Starting with in-app notifications since those are almost always needed:

```python
# models.py
from datetime import datetime
from enum import Enum

class NotificationType(str, Enum):
    ORDER_UPDATE = "order_update"
    NEW_COMMENT = "new_comment"
    MENTION = "mention"
    SYSTEM = "system"

class Notification:
    """Database model -- adapt to your ORM."""
    id: int
    user_id: int
    type: NotificationType
    title: str
    body: str
    read: bool = False
    created_at: datetime
    action_url: str = None  # where to go when clicked

# service.py
class NotificationService:
    def __init__(self, db, channels=None):
        self.db = db
        self.channels = channels or []  # email, push, etc.

    async def notify(self, user_id: int, type: str, title: str, body: str, action_url: str = None):
        # 1. Always save to DB (in-app notification)
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            action_url=action_url,
        )
        self.db.add(notif)
        await self.db.commit()

        # 2. Fan out to other channels based on user preferences
        prefs = await self.get_user_preferences(user_id)
        for channel in self.channels:
            if channel.name in prefs.get("enabled_channels", []):
                await channel.send(user_id, title, body)

    async def get_unread(self, user_id: int, limit: int = 20):
        return await self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.read == False,
        ).order_by(Notification.created_at.desc()).limit(limit).all()

    async def mark_read(self, user_id: int, notification_ids: list[int]):
        await self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.id.in_(notification_ids),
        ).update({"read": True})
        await self.db.commit()

# API endpoints
@app.get("/api/notifications")
async def get_notifications(current_user=Depends(get_current_user)):
    return await notification_service.get_unread(current_user.id)

@app.post("/api/notifications/read")
async def mark_notifications_read(ids: list[int], current_user=Depends(get_current_user)):
    await notification_service.mark_read(current_user.id, ids)
    return {"status": "ok"}
```

Tell me which channels and triggers matter most, and I'll flesh out the implementation.'''
    },
    {
        "instruction": r'''Add user roles to the system.''',
        "output": r'''<think>
"Add user roles" -- do they mean simple fixed roles (admin, user, moderator) or a full RBAC system with permissions? Do roles need to be hierarchical? Can users have multiple roles? Do they need per-resource permissions (e.g., "editor of project X but viewer of project Y")? The complexity ranges from a single string column to a full permission system. I need to understand the requirements.
</think>

Roles can be simple or very complex. Let me understand what you need:

1. **What roles?** Fixed set (admin, user, moderator) or dynamic (users can create custom roles)?
2. **Permissions granularity?** Role-level ("admins can do everything") or permission-level ("editors can edit posts but not delete users")?
3. **Resource-scoped?** Global roles ("Dan is an admin everywhere") or per-resource ("Dan is an editor on Project X but viewer on Project Y")?

Here's a practical implementation covering two common levels. Pick the one that fits:

```python
# === OPTION A: Simple fixed roles (most apps start here) ===

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"

# Add to your User model:
# role: UserRole = UserRole.USER

def require_role(*allowed_roles):
    """Decorator to restrict endpoints by role."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, current_user=Depends(get_current_user), **kwargs):
            if current_user.role not in allowed_roles:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@app.delete("/api/users/{user_id}")
@require_role(UserRole.ADMIN)
async def delete_user(user_id: int, current_user=Depends(get_current_user)):
    # Only admins reach here
    pass


# === OPTION B: Permission-based RBAC (for complex apps) ===

# roles table: id, name
# permissions table: id, name (e.g., "users:delete", "posts:edit")
# role_permissions table: role_id, permission_id
# user_roles table: user_id, role_id

ROLE_PERMISSIONS = {
    "admin": ["users:read", "users:write", "users:delete", "posts:read", "posts:write", "posts:delete"],
    "editor": ["users:read", "posts:read", "posts:write"],
    "viewer": ["users:read", "posts:read"],
}

def require_permission(permission: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, current_user=Depends(get_current_user), **kwargs):
            user_permissions = get_permissions_for_role(current_user.role)
            if permission not in user_permissions:
                raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@app.put("/api/posts/{post_id}")
@require_permission("posts:write")
async def update_post(post_id: int, current_user=Depends(get_current_user)):
    pass
```

Most apps should start with Option A and only move to Option B when the role/permission matrix gets complex. Which level do you need?'''
    },
    {
        "instruction": r'''Make it work offline.''',
        "output": r'''<think>
"Make it work offline" -- this is a huge feature with many dimensions. What kind of app? Web, mobile, desktop? What should work offline -- just reading cached data, or creating/editing too? How do they handle sync conflicts when the user comes back online? What data needs to be available offline? This requires significant architectural decisions.
</think>

Offline support is a major architectural decision. I need to understand:

1. **What kind of app?** Web (PWA), React Native, native mobile, Electron desktop?
2. **What should work offline?** Just viewing previously loaded data? Or also creating/editing items that sync when back online?
3. **How do you handle conflicts?** If two people edit the same thing offline, who wins?

Here's a starting point for a web app (PWA approach), since that's the most common case:

```javascript
// 1. Service Worker for caching (register in your main JS)
// sw.js
const CACHE_NAME = 'app-v1';
const PRECACHE_URLS = [
    '/',
    '/index.html',
    '/static/app.js',
    '/static/style.css',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(PRECACHE_URLS))
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        // Try network first, fall back to cache
        fetch(event.request)
            .then((response) => {
                // Cache successful responses for next offline use
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

// 2. Offline data queue -- save actions while offline, replay when online
class OfflineQueue {
    constructor() {
        this.queue = JSON.parse(localStorage.getItem('offlineQueue') || '[]');
    }

    add(action) {
        this.queue.push({ ...action, timestamp: Date.now() });
        localStorage.setItem('offlineQueue', JSON.stringify(this.queue));
    }

    async flush() {
        while (this.queue.length > 0) {
            const action = this.queue[0];
            try {
                await fetch(action.url, {
                    method: action.method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(action.body),
                });
                this.queue.shift();
                localStorage.setItem('offlineQueue', JSON.stringify(this.queue));
            } catch (e) {
                break;  // still offline, stop trying
            }
        }
    }
}

// Listen for connectivity changes
window.addEventListener('online', () => offlineQueue.flush());
```

```text
// 3. manifest.json for PWA install
{
    "name": "Your App",
    "short_name": "App",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff"
}
```

The sync/conflict strategy is the hardest part. Common approaches: last-write-wins (simple but lossy), server-wins (safe but frustrating), or operational transforms (complex but correct). Tell me the app type and what data needs offline access, and I'll design the right approach.'''
    },
    {
        "instruction": r'''Add analytics to our platform.''',
        "output": r'''<think>
"Add analytics" -- product analytics (user behavior tracking)? Business metrics (revenue, conversion)? Performance monitoring (page load times, error rates)? Admin dashboard with charts? Self-hosted or third-party like Mixpanel/Amplitude? What events do they want to track? This word means completely different things to different people.
</think>

"Analytics" can mean very different things. Let me clarify:

1. **What kind of analytics?**
   - **Product analytics**: Track user behavior (clicks, page views, feature usage)
   - **Business metrics**: Revenue, conversion rates, churn, displayed in a dashboard
   - **Performance monitoring**: Page load times, error rates, API latency
2. **Build or buy?** Open to services like Mixpanel/Amplitude/PostHog, or want self-hosted?
3. **Who consumes the data?** Product managers? Developers? Executives?

Here's a lightweight, self-hosted event tracking system you can extend. This is the "build it yourself" approach -- if you just want user behavior tracking, PostHog (open-source) or Mixpanel might save you weeks:

```python
# analytics/tracker.py -- server-side event tracking
from datetime import datetime
from typing import Optional

class EventTracker:
    def __init__(self, db):
        self.db = db

    async def track(
        self,
        event_name: str,
        user_id: Optional[int] = None,
        properties: dict = None,
        session_id: str = None,
    ):
        event = {
            "event": event_name,
            "user_id": user_id,
            "properties": properties or {},
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
        }
        await self.db.insert("events", event)

# Usage in your routes
tracker = EventTracker(db)

@app.post("/api/orders")
async def create_order(order_data: dict, current_user=Depends(get_current_user)):
    order = await order_service.create(order_data)
    await tracker.track("order_created", user_id=current_user.id, properties={
        "total": order.total,
        "item_count": len(order.items),
        "coupon_used": order.coupon is not None,
    })
    return order

# analytics/queries.py -- query helpers for dashboards
class AnalyticsQueries:
    def __init__(self, db):
        self.db = db

    async def daily_active_users(self, days: int = 30):
        return await self.db.execute("""
            SELECT DATE(timestamp) as day, COUNT(DISTINCT user_id) as dau
            FROM events
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        """, [days])

    async def event_counts(self, event_name: str, days: int = 7):
        return await self.db.execute("""
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM events
            WHERE event = %s AND timestamp > NOW() - INTERVAL '%s days'
            GROUP BY DATE(timestamp)
            ORDER BY day
        """, [event_name, days])
```

```javascript
// Client-side tracking (add to your frontend)
const analytics = {
    track(event, properties = {}) {
        fetch('/api/analytics/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event, properties }),
        }).catch(() => {});  // fire and forget
    },
};

// Usage:
// analytics.track('button_clicked', { button: 'signup', page: '/home' });
// analytics.track('search_performed', { query: 'shoes', results_count: 42 });
```

Tell me what metrics matter most to your team and I'll help you design the right event schema and dashboards.'''
    },
]
