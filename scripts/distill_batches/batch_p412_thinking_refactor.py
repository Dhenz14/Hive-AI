"""Thinking-trace pairs: multi-file refactoring with change planning."""

PAIRS = [
    (
        "thinking/refactor-god-class",
        "This UserManager class is 800 lines and handles authentication, profile management, email notifications, permission checks, and audit logging. How do I break it apart without breaking everything?",
        '''<think>
An 800-line god class touching 5 different concerns. The key challenge isn't the refactoring itself -- it's doing it without breaking the 50+ places that probably import UserManager.

Let me think about the dependency graph first:
- Authentication: login, logout, password reset, token management
- Profile: update name/email/avatar, settings, preferences
- Notifications: send email on signup, password change, etc.
- Permissions: check_permission, has_role, is_admin
- Audit: log every action to audit trail

These have internal dependencies:
- Authentication USES Permissions (check if account is locked)
- Profile USES Notifications (send email on profile change)
- Audit is USED BY everything (cross-cutting concern)

The refactoring order matters. I should extract the most independent concerns first, then work inward.

Extraction order:
1. AuditLogger -- no dependencies on other UserManager methods, used by everything
2. NotificationService -- depends on user data but not on auth/permissions
3. PermissionService -- depends on user roles, not on auth flow
4. ProfileService -- depends on notifications, permissions
5. AuthService -- depends on permissions, audit

The critical insight: I need to maintain backwards compatibility during the migration. If I just delete UserManager, 50+ files break simultaneously. Instead:

Step 1: Extract classes but keep UserManager as a facade
Step 2: Gradually update callers to use new classes directly
Step 3: Once all callers are migrated, delete the facade

This is the Strangler Fig pattern applied to a class.

For the facade, UserManager delegates to the new classes. Old code still works. New code can import the specific service it needs.

I also need to think about initialization. Currently UserManager probably takes a db connection. Each new service needs the same db. Use dependency injection -- pass db to each service in the constructor.
</think>

Use the **Strangler Fig pattern** -- extract new classes but keep UserManager as a thin facade during migration. Nothing breaks, and callers migrate gradually.

**Step 1: Identify the extraction order (least dependencies first):**

```
AuditLogger       (0 internal deps -- extract first)
    ^
NotificationService (depends on user data only)
    ^
PermissionService   (depends on roles/user data)
    ^
ProfileService      (uses notifications + permissions)
    ^
AuthService         (uses permissions + audit)
```

**Step 2: Extract each class, wire into facade:**

```python
# services/audit.py -- extracted first (no deps)
class AuditLogger:
    def __init__(self, db):
        self.db = db

    def log_action(self, user_id: int, action: str, details: dict = None):
        self.db.execute(
            "INSERT INTO audit_log (user_id, action, details, created_at) "
            "VALUES (?, ?, ?, NOW())",
            (user_id, action, json.dumps(details or {}))
        )


# services/permissions.py
class PermissionService:
    def __init__(self, db):
        self.db = db

    def has_role(self, user_id: int, role: str) -> bool:
        row = self.db.fetch_one(
            "SELECT 1 FROM user_roles WHERE user_id = ? AND role = ?",
            (user_id, role)
        )
        return row is not None

    def check_permission(self, user_id: int, permission: str) -> bool:
        roles = self.db.fetch_all(
            "SELECT role FROM user_roles WHERE user_id = ?", (user_id,)
        )
        return any(
            permission in ROLE_PERMISSIONS.get(r["role"], [])
            for r in roles
        )

    def is_admin(self, user_id: int) -> bool:
        return self.has_role(user_id, "admin")


# services/notifications.py
class NotificationService:
    def __init__(self, email_client):
        self.email = email_client

    def send_welcome(self, user_email: str, user_name: str):
        self.email.send(
            to=user_email,
            subject="Welcome!",
            template="welcome",
            context={"name": user_name},
        )

    def send_password_changed(self, user_email: str):
        self.email.send(
            to=user_email,
            subject="Password Changed",
            template="password_changed",
        )


# services/auth.py
class AuthService:
    def __init__(self, db, permissions: PermissionService,
                 audit: AuditLogger):
        self.db = db
        self.permissions = permissions
        self.audit = audit

    def login(self, email: str, password: str) -> dict | None:
        user = self.db.fetch_one(
            "SELECT * FROM users WHERE email = ?", (email,)
        )
        if not user or not verify_password(password, user["password_hash"]):
            self.audit.log_action(0, "login_failed", {"email": email})
            return None
        if user["is_locked"]:
            return None
        self.audit.log_action(user["id"], "login_success")
        return create_token(user)


# services/profile.py
class ProfileService:
    def __init__(self, db, notifications: NotificationService,
                 audit: AuditLogger):
        self.db = db
        self.notifications = notifications
        self.audit = audit

    def update_email(self, user_id: int, new_email: str):
        self.db.execute(
            "UPDATE users SET email = ? WHERE id = ?",
            (new_email, user_id)
        )
        self.notifications.send_email_changed(new_email)
        self.audit.log_action(user_id, "email_changed")
```

**Step 3: UserManager becomes a facade (backwards compatible):**

```python
# user_manager.py -- thin facade, delegates everything
class UserManager:
    """DEPRECATED: Use individual services directly.
    This facade exists for backwards compatibility during migration.
    """
    def __init__(self, db, email_client):
        self.audit = AuditLogger(db)
        self.permissions = PermissionService(db)
        self.notifications = NotificationService(email_client)
        self.auth = AuthService(db, self.permissions, self.audit)
        self.profile = ProfileService(db, self.notifications, self.audit)

    # Old methods delegate to new services
    def login(self, email, password):
        return self.auth.login(email, password)

    def has_role(self, user_id, role):
        return self.permissions.has_role(user_id, role)

    def update_email(self, user_id, new_email):
        return self.profile.update_email(user_id, new_email)

    # ... one-liner delegation for every old method
```

**Step 4: Migrate callers gradually:**

```python
# BEFORE (still works -- facade delegates):
from user_manager import UserManager
manager = UserManager(db, email)
manager.login(email, pwd)

# AFTER (direct import -- no facade):
from services.auth import AuthService
auth = AuthService(db, permissions, audit)
auth.login(email, pwd)
```

**Step 5: Once all callers are migrated, delete the facade.**

Track migration with: `grep -r "UserManager" --include="*.py" | wc -l` -- when it hits 0 (excluding the facade itself), delete it.'''
    ),
    (
        "thinking/refactor-callback-hell",
        "Convert this nested callback JavaScript code to clean async/await. It handles a multi-step checkout process:\n\nfunction checkout(cart, user, callback) {\n  validateCart(cart, function(err, validCart) {\n    if (err) return callback(err);\n    calculateTax(validCart, user.address, function(err, tax) {\n      if (err) return callback(err);\n      applyDiscount(validCart, user.membership, function(err, discount) {\n        if (err) return callback(err);\n        chargePayment(user.paymentMethod, validCart.total + tax - discount, function(err, charge) {\n          if (err) return callback(err);\n          createOrder(user.id, validCart, charge.id, function(err, order) {\n            if (err) return callback(err);\n            sendConfirmation(user.email, order, function(err) {\n              if (err) return callback(err);\n              updateInventory(validCart.items, function(err) {\n                if (err) return callback(err);\n                callback(null, order);\n              });\n            });\n          });\n        });\n      });\n    });\n  });\n}",
        '''<think>
7 levels of nested callbacks. Let me first understand the dependency chain:

1. validateCart(cart) -> validCart
2. calculateTax(validCart, address) -> tax (depends on step 1)
3. applyDiscount(validCart, membership) -> discount (depends on step 1, NOT step 2)
4. chargePayment(paymentMethod, total + tax - discount) -> charge (depends on 2 AND 3)
5. createOrder(userId, validCart, chargeId) -> order (depends on 1 and 4)
6. sendConfirmation(email, order) (depends on 5)
7. updateInventory(items) (depends on 1, but NOT on 5 or 6)

Key insight: steps 2 and 3 are INDEPENDENT -- they both only need validCart. They can run in parallel with Promise.all. The original callback version runs them sequentially, which is slower.

Also: steps 6 and 7 are somewhat independent -- sendConfirmation and updateInventory don't depend on each other. They could also run in parallel.

But wait -- should updateInventory really be last? If it fails, we've already charged the customer and created the order. In the original code, an inventory update failure returns an error but the payment is already charged. That's a bug in the business logic, not just the code structure.

For the refactoring, I should:
1. Convert each callback function to return a Promise (or assume they already have Promise versions)
2. Use async/await for the sequential parts
3. Use Promise.all for the parallel parts (tax + discount)
4. Add proper error handling with try/catch
5. Note the business logic issue with inventory

I should also wrap the whole thing in a transaction-like pattern -- if chargePayment succeeds but createOrder fails, we need to refund.
</think>

Steps 2-3 (tax and discount) are independent and can run in parallel. Steps 6-7 (confirmation and inventory) are also independent. The original runs everything sequentially.

```javascript
async function checkout(cart, user) {
  // Step 1: Validate
  const validCart = await validateCart(cart);

  // Steps 2-3: Tax and discount are independent -- run in parallel
  const [tax, discount] = await Promise.all([
    calculateTax(validCart, user.address),
    applyDiscount(validCart, user.membership),
  ]);

  // Step 4: Charge (needs both tax and discount)
  const finalAmount = validCart.total + tax - discount;
  const charge = await chargePayment(user.paymentMethod, finalAmount);

  // Step 5: Create order
  let order;
  try {
    order = await createOrder(user.id, validCart, charge.id);
  } catch (err) {
    // Payment succeeded but order creation failed -- refund
    await refundPayment(charge.id);
    throw new Error(`Order creation failed, payment refunded: ${err.message}`);
  }

  // Steps 6-7: Confirmation and inventory are independent -- run in parallel
  // Use allSettled so one failure doesn't block the other
  const [confirmResult, inventoryResult] = await Promise.allSettled([
    sendConfirmation(user.email, order),
    updateInventory(validCart.items),
  ]);

  // Log failures but don't fail the checkout (payment already charged)
  if (confirmResult.status === 'rejected') {
    console.error('Confirmation email failed:', confirmResult.reason);
    // Queue for retry
    await queueRetry('sendConfirmation', { email: user.email, orderId: order.id });
  }
  if (inventoryResult.status === 'rejected') {
    console.error('Inventory update failed:', inventoryResult.reason);
    await queueRetry('updateInventory', { items: validCart.items });
  }

  return order;
}
```

**What changed beyond syntax:**

1. **Parallel execution**: Tax + discount run simultaneously (was sequential). Confirmation + inventory run simultaneously. This cuts total latency significantly.

2. **Error recovery**: If `createOrder` fails after payment, we refund. The original just propagated the error, leaving a charged customer with no order.

3. **Graceful degradation**: `Promise.allSettled` for post-checkout steps means a failed confirmation email doesn't prevent inventory update. Failed non-critical steps are queued for retry.

4. **No callback argument**: Throws on error instead of `callback(err)`. Callers use try/catch.

```javascript
// Caller:
try {
  const order = await checkout(cart, user);
  res.json({ success: true, order });
} catch (err) {
  res.status(400).json({ error: err.message });
}
```'''
    ),
]
