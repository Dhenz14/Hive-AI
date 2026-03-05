"""Email and notification systems — templating, queuing, and multi-channel delivery."""

PAIRS = [
    (
        "python/email-patterns",
        "Show email sending patterns: templating, SMTP, transactional emails, and bulk sending with rate limiting.",
        '''Email sending patterns:

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
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


# --- Template-based email ---

class EmailTemplateEngine:
    def __init__(self, template_dir: str = "templates/email"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

    def render(self, template_name: str, **context) -> tuple[str, str]:
        """Render both HTML and text versions."""
        html_template = self.env.get_template(f"{template_name}.html")
        text_template = self.env.get_template(f"{template_name}.txt")

        html = html_template.render(**context)
        text = text_template.render(**context)
        return html, text


# --- Email sender ---

class EmailSender:
    def __init__(self, config: EmailConfig):
        self.config = config
        self.templates = EmailTemplateEngine()

    def send(self, to: str | list[str], subject: str,
             html: str, text: str = "",
             attachments: list[Path] = None,
             reply_to: str = None,
             cc: list[str] = None,
             bcc: list[str] = None):
        """Send a single email."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.config.from_name} <{self.config.from_email}>"
        msg["To"] = to if isinstance(to, str) else ", ".join(to)

        if cc:
            msg["Cc"] = ", ".join(cc)
        if reply_to:
            msg["Reply-To"] = reply_to

        # Text fallback
        if text:
            msg.attach(MIMEText(text, "plain"))

        # HTML body
        msg.attach(MIMEText(html, "html"))

        # Attachments
        for filepath in (attachments or []):
            part = MIMEBase("application", "octet-stream")
            part.set_payload(filepath.read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={filepath.name}",
            )
            msg.attach(part)

        # All recipients
        recipients = [to] if isinstance(to, str) else list(to)
        recipients.extend(cc or [])
        recipients.extend(bcc or [])

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            if self.config.use_tls:
                server.starttls()
            server.login(self.config.username, self.config.password)
            server.sendmail(self.config.from_email, recipients, msg.as_string())

        logger.info("Email sent to %s: %s", to, subject)

    def send_template(self, to: str, template: str, subject: str, **context):
        """Send templated email."""
        html, text = self.templates.render(template, **context)
        self.send(to=to, subject=subject, html=html, text=text)


# --- Transactional email service ---

class TransactionalEmailService:
    """High-level service for common email types."""

    def __init__(self, sender: EmailSender):
        self.sender = sender

    def send_welcome(self, user_email: str, user_name: str):
        self.sender.send_template(
            to=user_email,
            template="welcome",
            subject=f"Welcome to MyApp, {user_name}!",
            user_name=user_name,
            login_url="https://myapp.com/login",
        )

    def send_password_reset(self, user_email: str, reset_token: str):
        self.sender.send_template(
            to=user_email,
            template="password_reset",
            subject="Password Reset Request",
            reset_url=f"https://myapp.com/reset?token={reset_token}",
            expires_in="1 hour",
        )

    def send_order_confirmation(self, user_email: str, order: dict):
        self.sender.send_template(
            to=user_email,
            template="order_confirmation",
            subject=f"Order #{order['id']} Confirmed",
            order=order,
        )

    def send_invoice(self, user_email: str, invoice: dict,
                     pdf_path: Path):
        html, text = self.sender.templates.render(
            "invoice", invoice=invoice
        )
        self.sender.send(
            to=user_email,
            subject=f"Invoice #{invoice['number']}",
            html=html, text=text,
            attachments=[pdf_path],
        )


# --- Bulk sender with rate limiting ---

import time
from collections import deque

class BulkEmailSender:
    """Send bulk emails with rate limiting and tracking."""

    def __init__(self, sender: EmailSender,
                 rate_limit: int = 100,  # emails per minute
                 batch_size: int = 50):
        self.sender = sender
        self.rate_limit = rate_limit
        self.batch_size = batch_size
        self.sent_timestamps: deque = deque()

    def _wait_for_rate_limit(self):
        now = time.time()
        # Remove timestamps older than 60 seconds
        while self.sent_timestamps and now - self.sent_timestamps[0] > 60:
            self.sent_timestamps.popleft()

        if len(self.sent_timestamps) >= self.rate_limit:
            sleep_time = 60 - (now - self.sent_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

    def send_campaign(self, recipients: list[dict], template: str,
                      subject: str, **common_context) -> dict:
        """Send campaign to list of recipients."""
        stats = {"sent": 0, "failed": 0, "errors": []}

        for recipient in recipients:
            self._wait_for_rate_limit()
            try:
                self.sender.send_template(
                    to=recipient["email"],
                    template=template,
                    subject=subject,
                    **{**common_context, **recipient},
                )
                stats["sent"] += 1
                self.sent_timestamps.append(time.time())
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append({
                    "email": recipient["email"],
                    "error": str(e),
                })
                logger.error("Failed to send to %s: %s",
                           recipient["email"], e)

        logger.info("Campaign complete: %d sent, %d failed",
                   stats["sent"], stats["failed"])
        return stats
```

Email patterns:
1. **Multipart** — always include plain text fallback for HTML emails
2. **Templates** — Jinja2 for consistent, maintainable email layouts
3. **Transactional service** — high-level API for common email types
4. **Rate limiting** — respect SMTP provider limits to avoid blocks
5. **Error tracking** — log failures individually for retry'''
    ),
    (
        "python/notification-system",
        "Show multi-channel notification system: email, push, SMS, in-app, with preferences and queuing.",
        '''Multi-channel notification system:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# --- Notification types ---

class Channel(Enum):
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"
    SLACK = "slack"

class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

@dataclass
class Notification:
    recipient_id: str
    type: str            # "order_confirmed", "password_reset", etc.
    title: str
    body: str
    channels: list[Channel] = field(default_factory=lambda: [Channel.IN_APP])
    priority: Priority = Priority.NORMAL
    data: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Channel providers (strategy pattern) ---

class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, notification: Notification,
                   recipient: dict) -> bool: ...

class EmailProvider(NotificationProvider):
    def __init__(self, email_sender):
        self.sender = email_sender

    async def send(self, notification, recipient) -> bool:
        self.sender.send_template(
            to=recipient["email"],
            template=f"notifications/{notification.type}",
            subject=notification.title,
            body=notification.body,
            **notification.data,
        )
        return True

class PushProvider(NotificationProvider):
    def __init__(self, push_client):
        self.client = push_client

    async def send(self, notification, recipient) -> bool:
        tokens = recipient.get("push_tokens", [])
        for token in tokens:
            await self.client.send(
                token=token,
                title=notification.title,
                body=notification.body,
                data=notification.data,
            )
        return bool(tokens)

class SMSProvider(NotificationProvider):
    def __init__(self, sms_client):
        self.client = sms_client

    async def send(self, notification, recipient) -> bool:
        phone = recipient.get("phone")
        if not phone:
            return False
        await self.client.send(to=phone, body=notification.body)
        return True

class InAppProvider(NotificationProvider):
    def __init__(self, db):
        self.db = db

    async def send(self, notification, recipient) -> bool:
        await self.db.notifications.insert_one({
            "user_id": notification.recipient_id,
            "type": notification.type,
            "title": notification.title,
            "body": notification.body,
            "data": notification.data,
            "read": False,
            "created_at": notification.created_at,
        })
        return True


# --- Notification service ---

class NotificationService:
    def __init__(self):
        self.providers: dict[Channel, NotificationProvider] = {}
        self.preference_store = None  # UserPreferenceStore

    def register_provider(self, channel: Channel,
                          provider: NotificationProvider):
        self.providers[channel] = provider

    async def send(self, notification: Notification):
        """Send notification through all specified channels."""
        # Get user preferences
        preferences = await self._get_preferences(
            notification.recipient_id
        )
        recipient = await self._get_recipient(notification.recipient_id)

        results = {}
        for channel in notification.channels:
            # Check user preference (urgent bypasses preferences)
            if notification.priority != Priority.URGENT:
                if not preferences.get(channel.value, True):
                    results[channel] = "opted_out"
                    continue

                # Check quiet hours
                if self._is_quiet_hours(preferences, channel):
                    results[channel] = "quiet_hours"
                    continue

            # Send through provider
            provider = self.providers.get(channel)
            if not provider:
                results[channel] = "no_provider"
                continue

            try:
                sent = await provider.send(notification, recipient)
                results[channel] = "sent" if sent else "skipped"
            except Exception as e:
                logger.error("Failed to send %s via %s: %s",
                           notification.type, channel.value, e)
                results[channel] = "failed"

        # Log delivery
        await self._log_delivery(notification, results)
        return results

    async def send_batch(self, notifications: list[Notification]):
        """Send multiple notifications efficiently."""
        import asyncio
        tasks = [self.send(n) for n in notifications]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def _is_quiet_hours(self, preferences: dict,
                        channel: Channel) -> bool:
        quiet = preferences.get("quiet_hours", {})
        if not quiet.get("enabled"):
            return False
        now = datetime.now(timezone.utc).hour
        start = quiet.get("start", 22)
        end = quiet.get("end", 8)
        if start > end:
            return now >= start or now < end
        return start <= now < end


# --- Usage ---
# service = NotificationService()
# service.register_provider(Channel.EMAIL, EmailProvider(email_sender))
# service.register_provider(Channel.PUSH, PushProvider(firebase))
# service.register_provider(Channel.IN_APP, InAppProvider(db))
#
# await service.send(Notification(
#     recipient_id="user123",
#     type="order_shipped",
#     title="Your order has shipped!",
#     body="Order #456 is on its way.",
#     channels=[Channel.EMAIL, Channel.PUSH, Channel.IN_APP],
#     priority=Priority.NORMAL,
#     data={"order_id": "456", "tracking_url": "..."},
# ))
```

Notification patterns:
1. **Strategy pattern** — pluggable providers per channel
2. **User preferences** — respect opt-outs and quiet hours
3. **Priority levels** — urgent notifications bypass preferences
4. **Multi-channel** — same notification across email, push, SMS, in-app
5. **Batch sending** — async gather for concurrent delivery'''
    ),
]
