"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 11)"""

PAIRS = [
    (
        "thinking/adversarial-email-sending-system",
        "We're building a transactional email system. Users trigger emails (password reset, order confirmation, etc.) and we send them via an SMTP service. What security and reliability issues should I think about?",
        r'''<think>
Email sending system — let me think about attack vectors and reliability issues.

**Security attacks:**
1. Email injection: user input in email headers (To, CC, Subject) allows injecting additional recipients or headers
2. Template injection: user-controlled data rendered in email templates without escaping (HTML injection, phishing links)
3. Open relay abuse: if the API doesn't authenticate senders, attackers use your system to send spam
4. Enumeration: password reset reveals whether an email is registered ("no account found" vs "email sent")
5. Spam bombing: attacker triggers thousands of password reset emails to one victim
6. Link manipulation: password reset links that are predictable or reusable

**Reliability issues:**
7. Bounce handling: hard bounces (invalid email) should stop future sends
8. Rate limiting: don't send more than your SMTP provider allows
9. Queue management: if SMTP is down, emails should queue and retry, not be lost
10. Deliverability: emails landing in spam (missing SPF, DKIM, DMARC)
11. Template rendering failures: missing variables crash the template engine

Let me focus on the most impactful ones.
</think>

Email systems have both security and deliverability risks. Here are the critical ones.

## Critical: Email Header Injection

```python
# ❌ VULNERABLE: user input in email headers
from email.mime.text import MIMEText

def send_email(to_address, subject, body):
    msg = MIMEText(body)
    msg['To'] = to_address     # What if to_address contains newlines?
    msg['Subject'] = subject    # What if subject has injected headers?
    smtp.send(msg)

# Attacker sends:
#   to_address = "victim@example.com\nBcc: spam-list@attacker.com"
#   subject = "Reset\nContent-Type: text/html\n\n<script>..."
# Result: email sent to victim AND attacker's spam list

# ✅ FIXED: validate and sanitize all email fields
import re

def validate_email(email: str) -> str:
    if '\n' in email or '\r' in email:
        raise ValueError("Invalid email address")
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValueError("Invalid email format")
    return email

def sanitize_header(value: str) -> str:
    # Remove all newlines and carriage returns from header values
    return value.replace('\n', '').replace('\r', '')

def send_email(to_address, subject, body):
    to_address = validate_email(to_address)
    subject = sanitize_header(subject)
    # Now safe to use in headers
```

## Critical: Password Reset Email Abuse

```python
# ❌ VULNERABLE: no rate limit on password reset
@app.post("/forgot-password")
def forgot_password(email: str):
    user = User.get_by_email(email)
    if user:
        send_reset_email(user)
        return {"message": "Reset email sent"}
    return {"error": "No account with this email"}, 404
    # Problem 1: reveals whether email is registered (enumeration)
    # Problem 2: attacker sends 10,000 reset emails to victim (email bomb)

# ✅ FIXED: constant response + rate limiting
@app.post("/forgot-password")
@rate_limit("3/hour", key=lambda: request.json.get("email"))
def forgot_password(email: str):
    user = User.get_by_email(email)
    if user:
        # Rate limit per user too
        if not rate_limiter.allow(f"reset:{email}", max=3, window=3600):
            pass  # Silently skip — don't reveal rate limit
        else:
            send_reset_email(user)

    # SAME response whether user exists or not (prevents enumeration)
    return {"message": "If an account exists, a reset email has been sent"}
```

## High: Template Injection (Phishing via Your System)

```python
# ❌ VULNERABLE: user-controlled data in HTML email without escaping
def send_order_confirmation(user, order):
    html = f"""
    <h1>Order Confirmation</h1>
    <p>Thank you, {user.name}!</p>
    <p>Notes: {order.notes}</p>
    """
    # If order.notes = '<a href="phishing.com">Click to track</a>'
    # The email contains a phishing link that looks legitimate
    # because it came from YOUR email system

# ✅ FIXED: escape user content in HTML emails
from markupsafe import escape

def send_order_confirmation(user, order):
    html = f"""
    <h1>Order Confirmation</h1>
    <p>Thank you, {escape(user.name)}!</p>
    <p>Notes: {escape(order.notes)}</p>
    """
    # HTML entities escaped — no injection possible

# Or better: use a template engine with auto-escaping
from jinja2 import Environment, select_autoescape
env = Environment(autoescape=select_autoescape(['html']))
template = env.get_template('order_confirmation.html')
html = template.render(user=user, order=order)  # Auto-escaped
```

## High: Deliverability (Emails Landing in Spam)

```
Your emails won't reach users if you're missing:

1. SPF (Sender Policy Framework):
   DNS TXT record: "v=spf1 include:_spf.google.com include:sendgrid.net ~all"
   Tells receiving servers: "these servers are allowed to send email as us"

2. DKIM (DomainKeys Identified Mail):
   DNS TXT record with a public key
   Your mail server signs emails with a private key
   Receiving server verifies the signature → email wasn't tampered with

3. DMARC (Domain-based Message Authentication):
   DNS TXT record: "v=DMARC1; p=reject; rua=mailto:dmarc@yoursite.com"
   Tells receiving servers: "reject emails that fail SPF/DKIM checks"
   Without DMARC, spoofed emails from your domain will be delivered

CHECK YOUR SETUP:
   https://mxtoolbox.com/SuperTool.aspx — enter your domain
   All three (SPF, DKIM, DMARC) should be configured
```

## Medium: Queue and Retry for Reliability

```python
# ❌ VULNERABLE: synchronous email sending
@app.post("/orders")
def create_order(data):
    order = Order.create(data)
    send_confirmation_email(order.user, order)  # If SMTP is down → request fails!
    return {"id": order.id}

# ✅ FIXED: async email queue with retry
from celery import Celery

@app.post("/orders")
def create_order(data):
    order = Order.create(data)
    send_confirmation_email.delay(order.id)  # Queue, don't block
    return {"id": order.id}

@celery.task(bind=True, max_retries=5, default_retry_delay=60)
def send_confirmation_email(self, order_id):
    try:
        order = Order.get(order_id)
        send_email(order.user.email, "Order Confirmation", render_template(order))
    except SMTPConnectionError as e:
        self.retry(exc=e)  # Retry in 60 seconds
```

## Email Security Checklist

```
INPUT VALIDATION:
  □ Validate email format (no newlines, valid pattern)
  □ Sanitize all header values (remove CR/LF)
  □ Escape user content in HTML templates
  □ Rate limit email-triggering endpoints

AUTHENTICATION:
  □ Password reset: same response for existing/non-existing emails
  □ Password reset tokens: random, time-limited, single-use
  □ Email verification before accepting new email addresses

DELIVERABILITY:
  □ SPF record configured
  □ DKIM signing enabled
  □ DMARC policy set
  □ Unsubscribe header for marketing emails (CAN-SPAM)
  □ Bounce handling (stop sending to invalid addresses)

RELIABILITY:
  □ Async sending via queue (don't block API requests)
  □ Retry with backoff for transient SMTP failures
  □ Dead letter queue for permanently failed emails
  □ Monitor bounce rate and complaint rate
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
