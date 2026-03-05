"""Email and notifications — SMTP, templates, push notifications, and webhook patterns."""

PAIRS = [
    (
        "patterns/email-sending",
        "Show email sending patterns: SMTP with templates, HTML emails, attachments, and async sending.",
        '''Email sending patterns:

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from dataclasses import dataclass
from jinja2 import Environment, FileSystemLoader
import asyncio
import logging

logger = logging.getLogger(__name__)


# --- Email configuration ---

@dataclass
class EmailConfig:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "MyApp"
    use_tls: bool = True


# --- HTML email template rendering ---

class EmailTemplateEngine:
    """Render HTML email templates with Jinja2."""

    def __init__(self, template_dir: str = "templates/email"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

    def render(self, template_name: str, **context) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)


# --- Email builder ---

class EmailMessage:
    """Build email messages with HTML, text fallback, and attachments."""

    def __init__(self, config: EmailConfig):
        self.config = config
        self.msg = MIMEMultipart("alternative")

    def to(self, *recipients: str) -> "EmailMessage":
        self.msg["To"] = ", ".join(recipients)
        self._recipients = list(recipients)
        return self

    def subject(self, subject: str) -> "EmailMessage":
        self.msg["Subject"] = subject
        return self

    def text(self, body: str) -> "EmailMessage":
        self.msg.attach(MIMEText(body, "plain"))
        return self

    def html(self, body: str) -> "EmailMessage":
        self.msg.attach(MIMEText(body, "html"))
        return self

    def attach_file(self, path: Path) -> "EmailMessage":
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={path.name}")
        self.msg.attach(part)
        return self

    def reply_to(self, email: str) -> "EmailMessage":
        self.msg["Reply-To"] = email
        return self

    def send(self) -> bool:
        """Send email via SMTP."""
        self.msg["From"] = f"{self.config.from_name} <{self.config.from_email}>"

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()
                server.login(self.config.username, self.config.password)
                server.sendmail(
                    self.config.from_email,
                    self._recipients,
                    self.msg.as_string(),
                )
            logger.info("Email sent to %s", self._recipients)
            return True
        except Exception as e:
            logger.error("Email failed: %s", e)
            return False


# --- Email service with templates ---

class EmailService:
    """High-level email service with template support."""

    def __init__(self, config: EmailConfig):
        self.config = config
        self.templates = EmailTemplateEngine()

    def send_welcome(self, user_email: str, user_name: str):
        html = self.templates.render("welcome.html", name=user_name)
        text = f"Welcome to MyApp, {user_name}!"

        return (
            EmailMessage(self.config)
            .to(user_email)
            .subject("Welcome to MyApp!")
            .text(text)
            .html(html)
            .send()
        )

    def send_password_reset(self, user_email: str, reset_url: str):
        html = self.templates.render("password_reset.html", reset_url=reset_url)
        text = f"Reset your password: {reset_url}"

        return (
            EmailMessage(self.config)
            .to(user_email)
            .subject("Reset Your Password")
            .text(text)
            .html(html)
            .send()
        )

    def send_report(self, recipients: list[str], report_path: Path):
        return (
            EmailMessage(self.config)
            .to(*recipients)
            .subject("Monthly Report")
            .text("Please find the monthly report attached.")
            .attach_file(report_path)
            .send()
        )


# --- Async email queue ---

class AsyncEmailQueue:
    """Queue emails for background sending."""

    def __init__(self, config: EmailConfig, max_concurrent: int = 5):
        self.config = config
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue: asyncio.Queue = asyncio.Queue()

    async def enqueue(self, builder_fn):
        await self.queue.put(builder_fn)

    async def worker(self):
        while True:
            builder_fn = await self.queue.get()
            async with self.semaphore:
                try:
                    await asyncio.to_thread(builder_fn)
                except Exception as e:
                    logger.error("Async email failed: %s", e)
                finally:
                    self.queue.task_done()

    async def start(self, num_workers: int = 3):
        workers = [asyncio.create_task(self.worker()) for _ in range(num_workers)]
        await self.queue.join()
        for w in workers:
            w.cancel()
```

```html
<!-- templates/email/welcome.html -->
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: #3b82f6; padding: 24px; text-align: center;">
    <h1 style="color: white; margin: 0;">Welcome to MyApp</h1>
  </div>
  <div style="padding: 24px;">
    <p>Hi {{ name }},</p>
    <p>Thanks for joining! Get started by exploring your dashboard.</p>
    <a href="https://myapp.com/dashboard"
       style="display: inline-block; background: #3b82f6; color: white;
              padding: 12px 24px; border-radius: 6px; text-decoration: none;">
      Go to Dashboard
    </a>
  </div>
</body>
</html>
```

Email patterns:
1. **Builder pattern** — chain `.to()`, `.subject()`, `.html()`, `.attach_file()`, `.send()`
2. **HTML + text fallback** — `MIMEMultipart("alternative")` for email client compatibility
3. **Jinja2 templates** — HTML emails with dynamic content and `autoescape=True`
4. **`EmailService`** — high-level methods per email type (welcome, reset, report)
5. **Async queue** — background sending with concurrency limit via `Semaphore`'''
    ),
    (
        "patterns/webhooks",
        "Show webhook patterns: receiving webhooks, signature verification, retry handling, and outgoing webhooks.",
        '''Webhook patterns:

```python
import hmac
import hashlib
import json
import time
import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Header

logger = logging.getLogger(__name__)
app = FastAPI()


# --- Receiving webhooks (with signature verification) ---

WEBHOOK_SECRET = "whsec_your_secret_here"

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify webhook signature (Stripe-style)."""
    parts = dict(item.split("=", 1) for item in signature.split(","))

    timestamp = parts.get("t", "")
    expected_sig = parts.get("v1", "")

    # Check timestamp freshness (prevent replay attacks)
    if abs(time.time() - int(timestamp)) > tolerance_seconds:
        return False

    # Compute expected signature
    signed_payload = f"{timestamp}.{payload.decode()}"
    computed = hmac.new(
        secret.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


@app.post("/webhooks/stripe")
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
):
    payload = await request.body()

    if not verify_webhook_signature(payload, stripe_signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(payload)
    event_type = event["type"]

    # Route to handlers
    handlers = {
        "payment_intent.succeeded": handle_payment_success,
        "payment_intent.failed": handle_payment_failure,
        "customer.subscription.created": handle_subscription_created,
        "customer.subscription.deleted": handle_subscription_cancelled,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(event["data"]["object"])
    else:
        logger.info("Unhandled webhook event: %s", event_type)

    # Always return 200 quickly to avoid retries
    return {"status": "ok"}


async def handle_payment_success(data: dict):
    logger.info("Payment succeeded: %s", data["id"])

async def handle_payment_failure(data: dict):
    logger.warning("Payment failed: %s", data["id"])

async def handle_subscription_created(data: dict):
    logger.info("Subscription created: %s", data["id"])

async def handle_subscription_cancelled(data: dict):
    logger.info("Subscription cancelled: %s", data["id"])


# --- Sending webhooks (outgoing) ---

@dataclass
class WebhookDelivery:
    url: str
    event_type: str
    payload: dict
    attempt: int = 0
    max_attempts: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookSender:
    """Send webhooks with retry and signature."""

    def __init__(self, signing_secret: str):
        self.secret = signing_secret
        self.client = httpx.AsyncClient(timeout=10.0)

    def _sign_payload(self, payload: str) -> str:
        timestamp = str(int(time.time()))
        signed = f"{timestamp}.{payload}"
        sig = hmac.new(
            self.secret.encode(), signed.encode(), hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={sig}"

    async def send(self, delivery: WebhookDelivery) -> bool:
        """Send webhook with exponential backoff retry."""
        payload_str = json.dumps(delivery.payload, default=str)
        signature = self._sign_payload(payload_str)

        while delivery.attempt < delivery.max_attempts:
            delivery.attempt += 1
            try:
                response = await self.client.post(
                    delivery.url,
                    content=payload_str,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Event": delivery.event_type,
                        "X-Webhook-Attempt": str(delivery.attempt),
                    },
                )
                if response.status_code < 300:
                    logger.info("Webhook delivered: %s -> %s", delivery.event_type, delivery.url)
                    return True

                logger.warning(
                    "Webhook %s returned %d (attempt %d/%d)",
                    delivery.url, response.status_code,
                    delivery.attempt, delivery.max_attempts,
                )
            except httpx.RequestError as e:
                logger.warning("Webhook request failed: %s (attempt %d)", e, delivery.attempt)

            # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            if delivery.attempt < delivery.max_attempts:
                delay = 2 ** (delivery.attempt - 1)
                await asyncio.sleep(delay)

        logger.error("Webhook exhausted retries: %s -> %s", delivery.event_type, delivery.url)
        return False


# --- Idempotent webhook processing ---

class IdempotentWebhookHandler:
    """Process each webhook event exactly once."""

    def __init__(self, cache):
        self.cache = cache  # Redis or similar

    async def process(self, event_id: str, handler_fn, data: dict) -> bool:
        # Check if already processed
        cache_key = f"webhook:processed:{event_id}"
        if await self.cache.exists(cache_key):
            logger.info("Webhook %s already processed, skipping", event_id)
            return True

        # Process
        await handler_fn(data)

        # Mark as processed (TTL: 7 days)
        await self.cache.set(cache_key, "1", ex=7 * 86400)
        return True
```

Webhook patterns:
1. **HMAC signature verification** — `timestamp.payload` signed with SHA256
2. **Replay protection** — reject signatures older than tolerance window (5 min)
3. **Return 200 immediately** — process async to avoid sender timeout/retry
4. **Exponential backoff** — outgoing retries at 1s, 2s, 4s, 8s, 16s intervals
5. **Idempotent processing** — deduplicate by event_id with TTL cache'''
    ),
]
"""
