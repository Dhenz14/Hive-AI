"""Notification system design — service architecture, email delivery, deduplication and batching, preference management."""

PAIRS = [
    (
        "system-design/notification-service-architecture",
        "Design a notification service architecture supporting multiple channels, templates, and user preferences.",
        '''Notification service architecture with channels, templates, and preferences:

```python
# --- notification_service.py --- Core notification orchestrator ---

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class Channel(Enum):
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"
    SLACK = "slack"


class Priority(Enum):
    CRITICAL = "critical"     # auth codes, security alerts — always send
    HIGH = "high"             # order confirmations, mentions
    NORMAL = "normal"         # comments, updates
    LOW = "low"               # digests, recommendations


class NotificationStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


@dataclass
class Notification:
    """A single notification to be delivered."""
    id: str
    user_id: str
    type: str                      # "order.confirmed", "comment.reply", etc.
    channel: Channel
    priority: Priority
    status: NotificationStatus
    template_id: str
    template_data: dict[str, Any]
    subject: Optional[str] = None  # for email
    body: Optional[str] = None     # rendered content
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class NotificationRequest:
    """Incoming notification request — may fan out to multiple channels."""
    user_id: str
    type: str                      # notification type (maps to template + channels)
    priority: Priority
    data: dict[str, Any]           # template variables
    idempotency_key: str = ""
    channels: list[Channel] | None = None  # override default channels
    metadata: dict[str, Any] = field(default_factory=dict)


class NotificationService:
    """Orchestrate notification delivery across channels.

    Flow:
    1. Receive request
    2. Check user preferences
    3. Select channels
    4. Render templates
    5. Deduplicate
    6. Enqueue for delivery
    """

    def __init__(
        self,
        config: NotificationConfig,
        preference_store: PreferenceStore,
        template_engine: TemplateEngine,
        dedup_service: DeduplicationService,
        queue: NotificationQueue,
        repo: NotificationRepository,
    ):
        self.config = config
        self.preferences = preference_store
        self.templates = template_engine
        self.dedup = dedup_service
        self.queue = queue
        self.repo = repo

    async def send(self, request: NotificationRequest) -> list[Notification]:
        """Process a notification request."""
        notifications: list[Notification] = []

        # Step 1: Resolve notification type to channels
        type_config = self.config.get_type_config(request.type)
        if not type_config:
            logger.warning(f"Unknown notification type: {request.type}")
            return []

        channels = request.channels or type_config.default_channels

        # Step 2: Check user preferences
        prefs = await self.preferences.get_preferences(request.user_id)
        channels = self._filter_by_preferences(channels, prefs, request)

        if not channels:
            logger.info(
                f"All channels suppressed for user {request.user_id}, "
                f"type {request.type}"
            )
            return []

        # Step 3: Deduplicate
        if request.idempotency_key:
            if await self.dedup.is_duplicate(request.idempotency_key):
                logger.info(f"Duplicate notification: {request.idempotency_key}")
                return []

        # Step 4: Create and enqueue for each channel
        for channel in channels:
            notification = Notification(
                id=f"notif_{uuid.uuid4().hex[:12]}",
                user_id=request.user_id,
                type=request.type,
                channel=channel,
                priority=request.priority,
                status=NotificationStatus.PENDING,
                template_id=type_config.templates.get(channel.value, type_config.default_template),
                template_data=request.data,
                idempotency_key=request.idempotency_key,
                metadata=request.metadata,
            )

            # Render template
            rendered = await self.templates.render(
                notification.template_id,
                notification.template_data,
                channel=channel,
            )
            notification.subject = rendered.get("subject")
            notification.body = rendered.get("body")

            # Save and enqueue
            await self.repo.save(notification)
            await self.queue.enqueue(notification)
            notification.status = NotificationStatus.QUEUED

            notifications.append(notification)

        # Record for dedup
        if request.idempotency_key:
            await self.dedup.record(request.idempotency_key)

        logger.info(
            f"Queued {len(notifications)} notifications for "
            f"user {request.user_id}, type {request.type}"
        )
        return notifications

    def _filter_by_preferences(
        self,
        channels: list[Channel],
        prefs: UserPreferences,
        request: NotificationRequest,
    ) -> list[Channel]:
        """Filter channels based on user preferences."""
        filtered = []

        for channel in channels:
            # Critical notifications always go through
            if request.priority == Priority.CRITICAL:
                filtered.append(channel)
                continue

            # Check channel-level opt-out
            if not prefs.is_channel_enabled(channel):
                continue

            # Check notification-type opt-out
            if not prefs.is_type_enabled(request.type, channel):
                continue

            # Check DND schedule
            if prefs.is_in_dnd() and request.priority != Priority.HIGH:
                continue

            # Check frequency cap
            if prefs.is_frequency_capped(request.type):
                continue

            filtered.append(channel)

        return filtered


@dataclass
class NotificationTypeConfig:
    """Configuration for a notification type."""
    type_id: str                        # "order.confirmed"
    display_name: str                   # "Order Confirmed"
    category: str                       # "orders", "social", "marketing"
    default_channels: list[Channel]
    default_template: str               # fallback template ID
    templates: dict[str, str]           # channel -> template_id
    priority: Priority = Priority.NORMAL
    batchable: bool = False             # can be batched into digest
    dedup_window_seconds: int = 300     # dedup within 5 minutes


class NotificationConfig:
    """Registry of all notification types."""

    TYPES = {
        "order.confirmed": NotificationTypeConfig(
            type_id="order.confirmed",
            display_name="Order Confirmed",
            category="orders",
            default_channels=[Channel.EMAIL, Channel.PUSH, Channel.IN_APP],
            default_template="order_confirmed",
            templates={
                "email": "email_order_confirmed",
                "push": "push_order_confirmed",
                "in_app": "inapp_order_confirmed",
            },
            priority=Priority.HIGH,
        ),
        "comment.reply": NotificationTypeConfig(
            type_id="comment.reply",
            display_name="Comment Reply",
            category="social",
            default_channels=[Channel.PUSH, Channel.IN_APP],
            default_template="comment_reply",
            templates={
                "push": "push_comment_reply",
                "in_app": "inapp_comment_reply",
                "email": "email_comment_reply",
            },
            batchable=True,
        ),
        "auth.login_code": NotificationTypeConfig(
            type_id="auth.login_code",
            display_name="Login Verification Code",
            category="security",
            default_channels=[Channel.EMAIL, Channel.SMS],
            default_template="auth_login_code",
            templates={
                "email": "email_login_code",
                "sms": "sms_login_code",
            },
            priority=Priority.CRITICAL,
            dedup_window_seconds=60,
        ),
    }

    def get_type_config(self, type_id: str) -> Optional[NotificationTypeConfig]:
        return self.TYPES.get(type_id)
```

```python
# --- template_engine.py --- Notification template rendering ---

from __future__ import annotations

import logging
from typing import Any, Optional
from jinja2 import Environment, DictLoader, select_autoescape

logger = logging.getLogger(__name__)


class TemplateEngine:
    """Render notification templates for different channels."""

    def __init__(self):
        self.templates: dict[str, str] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in templates."""
        self.templates.update({
            # Email templates
            "email_order_confirmed": """
                <h2>Order Confirmed!</h2>
                <p>Hi {{ user_name }},</p>
                <p>Your order <strong>{{ order_id }}</strong> has been confirmed.</p>
                <table>
                    <tr><td>Total:</td><td>${{ total }}</td></tr>
                    <tr><td>Items:</td><td>{{ item_count }}</td></tr>
                    <tr><td>Delivery:</td><td>{{ delivery_date }}</td></tr>
                </table>
                <a href="{{ order_url }}">View Order</a>
            """,
            "email_comment_reply": """
                <p><strong>{{ replier_name }}</strong> replied to your comment:</p>
                <blockquote>{{ reply_text }}</blockquote>
                <a href="{{ thread_url }}">View Thread</a>
            """,
            "email_login_code": """
                <p>Your verification code is: <strong>{{ code }}</strong></p>
                <p>This code expires in {{ expiry_minutes }} minutes.</p>
                <p>If you didn't request this, ignore this email.</p>
            """,

            # Push templates
            "push_order_confirmed": "{{ user_name }}, your order {{ order_id }} is confirmed!",
            "push_comment_reply": "{{ replier_name }} replied: {{ reply_text | truncate(80) }}",

            # In-app templates
            "inapp_order_confirmed": "Order {{ order_id }} confirmed - ${{ total }}",
            "inapp_comment_reply": "{{ replier_name }} replied to your comment",

            # SMS templates
            "sms_login_code": "Your code: {{ code }}. Expires in {{ expiry_minutes }}min.",
        })

    async def render(
        self,
        template_id: str,
        data: dict[str, Any],
        channel: Optional[Channel] = None,
    ) -> dict[str, str]:
        """Render a template with the given data."""
        template_str = self.templates.get(template_id)
        if not template_str:
            logger.warning(f"Template not found: {template_id}")
            return {"body": str(data)}

        env = Environment(
            loader=DictLoader({template_id: template_str}),
            autoescape=select_autoescape(["html"]),
        )

        template = env.get_template(template_id)
        body = template.render(**data)

        result = {"body": body.strip()}

        # Add subject for email
        if channel == Channel.EMAIL and "subject" not in result:
            subject_templates = {
                "email_order_confirmed": "Order {{ order_id }} Confirmed",
                "email_comment_reply": "{{ replier_name }} replied to your comment",
                "email_login_code": "Your verification code: {{ code }}",
            }
            subject_tmpl = subject_templates.get(template_id)
            if subject_tmpl:
                subject = env.from_string(subject_tmpl).render(**data)
                result["subject"] = subject

        return result
```

```
Notification Service Architecture:

  [Event Sources]              [Notification Service]              [Delivery]
  +-------------+           +------------------------+         +-----------+
  | Order Svc   |--event--> |  1. Type Resolution    |-------> | Email     |
  | Auth Svc    |--event--> |  2. Preference Check   |         | (SES/SG)  |
  | Comment Svc |--event--> |  3. Template Render    |-------> | Push      |
  | Billing Svc |--API----> |  4. Deduplication      |         | (APNS/FCM)|
  | Admin Tool  |--API----> |  5. Batching           |-------> | SMS       |
  +-------------+           |  6. Queue              |         | (Twilio)  |
                            +------------------------+         | In-App    |
                                     |                         | (WebSocket)|
                                     v                         | Webhook   |
                            +------------------+               | Slack     |
                            | Notification DB  |               +-----------+
                            | - History        |
                            | - Preferences    |                    |
                            | - Templates      |                    v
                            +------------------+            +------------+
                                                            | Delivery   |
                                                            | Tracking   |
                                                            | (opens,    |
                                                            |  clicks,   |
                                                            |  bounces)  |
                                                            +------------+

  Key design decisions:
  - Events trigger notifications (loose coupling with source services)
  - Preferences checked BEFORE rendering to avoid unnecessary work
  - Templates per channel (email is HTML, push is plain text, SMS is short)
  - Queue decouples orchestration from delivery for reliability
  - Delivery tracking feeds back into bounce handling and preference updates
```

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| Event ingestion | Receive notification triggers | Kafka, SQS, HTTP API |
| Preference store | User channel/type preferences | PostgreSQL + Redis cache |
| Template engine | Render per-channel content | Jinja2, Handlebars |
| Deduplication | Prevent duplicate notifications | Redis with TTL |
| Queue | Decouple dispatch from delivery | SQS, RabbitMQ, Celery |
| Channel providers | Platform-specific delivery | SES, APNS, FCM, Twilio |
| Delivery tracker | Opens, clicks, bounces | Webhooks + DB |

Key patterns:
1. Define notification types as configuration (type -> channels, template, priority)
2. Check user preferences BEFORE rendering templates to save compute
3. Critical notifications (auth codes, security) bypass DND and preference filtering
4. Use separate templates per channel — email is rich HTML, push is short text, SMS is minimal
5. Decouple event ingestion from delivery with a queue for reliability and retry'''
    ),
    (
        "system-design/email-delivery-pipeline",
        "Design an email delivery pipeline covering queuing, templating, sending, bounce handling, and reputation management.",
        '''Email delivery pipeline with queuing, bounce handling, and reputation:

```python
# --- email_pipeline.py --- Email delivery pipeline ---

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class EmailStatus(Enum):
    QUEUED = "queued"
    RENDERING = "rendering"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"    # confirmed by recipient server
    OPENED = "opened"         # tracking pixel loaded
    CLICKED = "clicked"       # link clicked
    BOUNCED = "bounced"       # delivery failed
    COMPLAINED = "complained" # marked as spam
    UNSUBSCRIBED = "unsubscribed"


class BounceType(Enum):
    HARD = "hard"     # permanent: invalid address, domain doesn't exist
    SOFT = "soft"     # temporary: mailbox full, server down
    COMPLAINT = "complaint"  # spam report


@dataclass
class Email:
    id: str
    to: str
    from_addr: str
    from_name: str
    subject: str
    html_body: str
    text_body: str
    reply_to: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    status: EmailStatus = EmailStatus.QUEUED
    provider_message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    bounce_type: Optional[BounceType] = None
    bounce_reason: Optional[str] = None


class EmailDeliveryPipeline:
    """Production email delivery pipeline.

    Stages:
    1. Queue: receive and validate email
    2. Render: apply template, inline CSS, add tracking
    3. Send: dispatch via provider (SES, SendGrid, Mailgun)
    4. Track: handle delivery webhooks (bounces, opens, clicks)
    5. Manage: reputation, suppression list, warm-up
    """

    def __init__(
        self,
        provider: EmailProvider,
        suppression_list: SuppressionList,
        reputation_monitor: ReputationMonitor,
        repo: EmailRepository,
    ):
        self.provider = provider
        self.suppression = suppression_list
        self.reputation = reputation_monitor
        self.repo = repo

    async def send_email(self, email: Email) -> Email:
        """Process a single email through the pipeline."""
        # Stage 1: Validate
        validation = await self._validate(email)
        if not validation.valid:
            email.status = EmailStatus.BOUNCED
            email.bounce_type = BounceType.HARD
            email.bounce_reason = validation.reason
            await self.repo.save(email)
            return email

        # Stage 2: Check suppression list
        if await self.suppression.is_suppressed(email.to):
            email.status = EmailStatus.BOUNCED
            email.bounce_reason = "Address on suppression list"
            await self.repo.save(email)
            logger.info(f"Suppressed: {email.to}")
            return email

        # Stage 3: Add tracking
        email = self._add_tracking(email)

        # Stage 4: Send via provider
        try:
            email.status = EmailStatus.SENDING
            result = await self.provider.send(
                to=email.to,
                from_addr=email.from_addr,
                from_name=email.from_name,
                subject=email.subject,
                html=email.html_body,
                text=email.text_body,
                headers=email.headers,
                tags=email.tags,
                metadata={"email_id": email.id},
            )

            email.status = EmailStatus.SENT
            email.provider_message_id = result["message_id"]
            email.sent_at = datetime.utcnow()

            # Update reputation metrics
            await self.reputation.record_send(email.from_addr)

        except EmailProviderError as e:
            email.status = EmailStatus.BOUNCED
            email.bounce_type = BounceType.SOFT
            email.bounce_reason = str(e)
            logger.error(f"Send failed for {email.to}: {e}")

        await self.repo.save(email)
        return email

    async def handle_webhook(self, event: dict) -> None:
        """Process delivery webhooks from the email provider.

        Webhook events: delivered, bounced, complained, opened, clicked
        """
        event_type = event["type"]
        message_id = event["message_id"]

        email = await self.repo.find_by_provider_id(message_id)
        if not email:
            logger.warning(f"Unknown message ID in webhook: {message_id}")
            return

        if event_type == "delivered":
            email.status = EmailStatus.DELIVERED

        elif event_type == "bounced":
            email.status = EmailStatus.BOUNCED
            email.bounce_type = BounceType(event.get("bounce_type", "soft"))
            email.bounce_reason = event.get("reason", "")

            if email.bounce_type == BounceType.HARD:
                # Permanent failure — add to suppression list
                await self.suppression.add(
                    email.to, reason=email.bounce_reason
                )
                await self.reputation.record_bounce(email.from_addr, hard=True)
            else:
                await self.reputation.record_bounce(email.from_addr, hard=False)

        elif event_type == "complained":
            email.status = EmailStatus.COMPLAINED
            # Spam complaint — immediately suppress and alert
            await self.suppression.add(email.to, reason="spam_complaint")
            await self.reputation.record_complaint(email.from_addr)
            logger.warning(f"Spam complaint from {email.to}")

        elif event_type == "opened":
            email.status = EmailStatus.OPENED
            email.opened_at = datetime.utcnow()

        elif event_type == "clicked":
            email.status = EmailStatus.CLICKED

        elif event_type == "unsubscribed":
            email.status = EmailStatus.UNSUBSCRIBED
            await self.suppression.add(email.to, reason="unsubscribed")

        await self.repo.save(email)

    async def _validate(self, email: Email) -> ValidationResult:
        """Validate email before sending."""
        # Basic format check
        if not email.to or "@" not in email.to:
            return ValidationResult(False, "Invalid email address")

        # Check domain MX records (in production)
        domain = email.to.split("@")[1]
        # if not await check_mx_record(domain):
        #     return ValidationResult(False, f"No MX record for {domain}")

        # Check content
        if not email.subject:
            return ValidationResult(False, "Missing subject")
        if not email.html_body and not email.text_body:
            return ValidationResult(False, "Missing body")

        return ValidationResult(True, "")

    def _add_tracking(self, email: Email) -> Email:
        """Add open tracking pixel and click tracking."""
        # Open tracking: 1x1 transparent pixel
        tracking_pixel = (
            f'<img src="https://track.example.com/open/{email.id}" '
            f'width="1" height="1" style="display:none" />'
        )
        email.html_body += tracking_pixel

        # Add List-Unsubscribe header (required for good reputation)
        email.headers["List-Unsubscribe"] = (
            f"<https://example.com/unsubscribe/{email.id}>, "
            f"<mailto:unsubscribe@example.com?subject=unsubscribe-{email.id}>"
        )
        email.headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        return email


@dataclass
class ValidationResult:
    valid: bool
    reason: str
```

```python
# --- reputation.py --- Email reputation monitoring ---

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class ReputationMetrics:
    """Email sending reputation metrics."""
    sender: str
    period: str
    total_sent: int
    total_delivered: int
    total_bounced: int
    hard_bounces: int
    soft_bounces: int
    complaints: int
    delivery_rate: float
    bounce_rate: float
    complaint_rate: float
    health: str              # "good", "warning", "critical"


class ReputationMonitor:
    """Monitor and protect email sending reputation.

    Key thresholds (ISP guidelines):
    - Bounce rate: < 2% (warning), < 5% (critical)
    - Complaint rate: < 0.1% (warning), < 0.3% (critical)
    - Delivery rate: > 95% (good)
    """

    BOUNCE_WARNING = 0.02
    BOUNCE_CRITICAL = 0.05
    COMPLAINT_WARNING = 0.001
    COMPLAINT_CRITICAL = 0.003

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def record_send(self, sender: str) -> None:
        key = f"email:rep:{sender}:{datetime.utcnow().strftime('%Y%m%d')}"
        await self.redis.hincrby(key, "sent", 1)
        await self.redis.expire(key, 86400 * 30)  # keep 30 days

    async def record_bounce(self, sender: str, hard: bool = False) -> None:
        key = f"email:rep:{sender}:{datetime.utcnow().strftime('%Y%m%d')}"
        await self.redis.hincrby(key, "bounced", 1)
        if hard:
            await self.redis.hincrby(key, "hard_bounces", 1)
        else:
            await self.redis.hincrby(key, "soft_bounces", 1)

        # Check if we should pause sending
        metrics = await self.get_metrics(sender, days=1)
        if metrics and metrics.bounce_rate > self.BOUNCE_CRITICAL:
            logger.critical(
                f"CRITICAL: Bounce rate {metrics.bounce_rate:.1%} for {sender}. "
                f"Pausing email delivery!"
            )
            await self.redis.set(f"email:paused:{sender}", "1", ex=3600)

    async def record_complaint(self, sender: str) -> None:
        key = f"email:rep:{sender}:{datetime.utcnow().strftime('%Y%m%d')}"
        await self.redis.hincrby(key, "complaints", 1)

        metrics = await self.get_metrics(sender, days=1)
        if metrics and metrics.complaint_rate > self.COMPLAINT_CRITICAL:
            logger.critical(
                f"CRITICAL: Complaint rate {metrics.complaint_rate:.3%} for {sender}. "
                f"Pausing email delivery!"
            )
            await self.redis.set(f"email:paused:{sender}", "1", ex=3600)

    async def get_metrics(
        self, sender: str, days: int = 7
    ) -> ReputationMetrics | None:
        """Get reputation metrics for a sender over N days."""
        totals = {"sent": 0, "bounced": 0, "hard_bounces": 0,
                  "soft_bounces": 0, "complaints": 0}

        for i in range(days):
            date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y%m%d")
            key = f"email:rep:{sender}:{date}"
            data = await self.redis.hgetall(key)
            for field_name, value in data.items():
                fn = field_name.decode() if isinstance(field_name, bytes) else field_name
                val = int(value)
                if fn in totals:
                    totals[fn] += val

        if totals["sent"] == 0:
            return None

        sent = totals["sent"]
        bounced = totals["bounced"]
        complaints = totals["complaints"]
        delivered = sent - bounced

        bounce_rate = bounced / sent
        complaint_rate = complaints / sent
        delivery_rate = delivered / sent

        # Determine health
        if bounce_rate > self.BOUNCE_CRITICAL or complaint_rate > self.COMPLAINT_CRITICAL:
            health = "critical"
        elif bounce_rate > self.BOUNCE_WARNING or complaint_rate > self.COMPLAINT_WARNING:
            health = "warning"
        else:
            health = "good"

        return ReputationMetrics(
            sender=sender,
            period=f"{days}d",
            total_sent=sent,
            total_delivered=delivered,
            total_bounced=bounced,
            hard_bounces=totals["hard_bounces"],
            soft_bounces=totals["soft_bounces"],
            complaints=complaints,
            delivery_rate=delivery_rate,
            bounce_rate=bounce_rate,
            complaint_rate=complaint_rate,
            health=health,
        )

    async def is_sending_paused(self, sender: str) -> bool:
        return await self.redis.exists(f"email:paused:{sender}") > 0
```

```python
# --- suppression.py --- Email suppression list ---

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class SuppressionEntry:
    email: str
    reason: str              # "hard_bounce", "spam_complaint", "unsubscribed"
    source: str              # "webhook", "manual", "import"
    created_at: datetime
    expires_at: Optional[datetime] = None  # None = permanent


class SuppressionList:
    """Maintain a list of email addresses that should never receive emails.

    Reasons for suppression:
    - Hard bounce: address doesn't exist
    - Spam complaint: user marked as spam
    - Unsubscribe: user opted out
    - Manual: admin-added
    """

    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client
        self.cache_prefix = "suppression:"

    async def is_suppressed(self, email: str) -> bool:
        """Check if an email is on the suppression list."""
        normalized = email.strip().lower()

        # Check cache first
        cached = await self.redis.get(f"{self.cache_prefix}{normalized}")
        if cached is not None:
            return cached == b"1"

        # Check database
        entry = await self.db.fetch_one(
            "SELECT 1 FROM suppression_list WHERE email = :email "
            "AND (expires_at IS NULL OR expires_at > NOW())",
            {"email": normalized},
        )

        suppressed = entry is not None
        # Cache for 1 hour
        await self.redis.set(
            f"{self.cache_prefix}{normalized}",
            "1" if suppressed else "0",
            ex=3600,
        )
        return suppressed

    async def add(
        self,
        email: str,
        reason: str,
        source: str = "webhook",
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Add email to suppression list."""
        normalized = email.strip().lower()

        await self.db.execute(
            """INSERT INTO suppression_list (email, reason, source, created_at, expires_at)
               VALUES (:email, :reason, :source, NOW(), :expires_at)
               ON CONFLICT (email) DO UPDATE SET
                   reason = :reason, source = :source, created_at = NOW()""",
            {"email": normalized, "reason": reason, "source": source, "expires_at": expires_at},
        )

        # Update cache
        await self.redis.set(f"{self.cache_prefix}{normalized}", "1", ex=3600)
        logger.info(f"Suppressed: {normalized} ({reason})")

    async def remove(self, email: str) -> None:
        """Remove email from suppression list (e.g., re-subscription)."""
        normalized = email.strip().lower()
        await self.db.execute(
            "DELETE FROM suppression_list WHERE email = :email",
            {"email": normalized},
        )
        await self.redis.delete(f"{self.cache_prefix}{normalized}")
```

| Metric | Good | Warning | Critical | Action |
|--------|------|---------|----------|--------|
| Bounce rate | < 2% | 2-5% | > 5% | Clean list, pause sending |
| Complaint rate | < 0.1% | 0.1-0.3% | > 0.3% | Review content, add unsubscribe |
| Delivery rate | > 95% | 90-95% | < 90% | Check DNS, authentication |
| Open rate | > 20% | 10-20% | < 10% | Improve subject lines |
| Unsubscribe rate | < 0.5% | 0.5-1% | > 1% | Review frequency, content |

Key patterns:
1. Always check the suppression list before sending — never email bounced or complained addresses
2. Add List-Unsubscribe headers to every email for ISP compliance and reputation
3. Monitor bounce and complaint rates daily — auto-pause sending if thresholds are breached
4. Hard bounces go straight to suppression; soft bounces retry 3 times then suppress
5. Track delivery, open, and click rates per sender domain for reputation visibility'''
    ),
    (
        "system-design/notification-dedup-batching",
        "Design notification deduplication and batching to prevent spam and support digest-style notifications.",
        '''Notification deduplication and batching for digest notifications:

```python
# --- dedup.py --- Notification deduplication service ---

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Prevent duplicate notifications using multiple strategies.

    Strategies:
    1. Idempotency key: exact duplicate of same request
    2. Content dedup: same type + user within time window
    3. Rate limiting: max N notifications per type per window
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        default_window_seconds: int = 300,  # 5 minutes
    ):
        self.redis = redis_client
        self.default_window = default_window_seconds

    async def is_duplicate(
        self,
        key: str,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """Check if this exact notification was already sent."""
        window = window_seconds or self.default_window
        redis_key = f"dedup:{key}"

        exists = await self.redis.exists(redis_key)
        return exists > 0

    async def record(
        self,
        key: str,
        window_seconds: Optional[int] = None,
    ) -> None:
        """Record a notification for dedup checking."""
        window = window_seconds or self.default_window
        redis_key = f"dedup:{key}"
        await self.redis.set(redis_key, "1", ex=window)

    async def is_rate_limited(
        self,
        user_id: str,
        notification_type: str,
        max_per_window: int = 5,
        window_seconds: int = 3600,
    ) -> bool:
        """Check if user has received too many of this type recently."""
        key = f"rate:{user_id}:{notification_type}"
        count = await self.redis.get(key)

        if count and int(count) >= max_per_window:
            logger.info(
                f"Rate limited: {user_id} has received {count} "
                f"{notification_type} notifications in the window"
            )
            return True
        return False

    async def record_send(
        self,
        user_id: str,
        notification_type: str,
        window_seconds: int = 3600,
    ) -> int:
        """Record a send for rate limiting."""
        key = f"rate:{user_id}:{notification_type}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, window_seconds)
        return count

    @staticmethod
    def generate_content_key(
        user_id: str,
        notification_type: str,
        content_hash: str = "",
    ) -> str:
        """Generate a dedup key from notification content."""
        raw = f"{user_id}:{notification_type}:{content_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

```python
# --- batching.py --- Notification batching and digest system ---

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class BatchedNotification:
    """A notification that has been queued for batching."""
    notification_type: str
    data: dict[str, Any]
    created_at: datetime


@dataclass
class DigestConfig:
    """Configuration for a notification digest."""
    notification_types: list[str]    # types to include in digest
    interval_minutes: int            # how often to send digest
    min_items: int = 1               # minimum items before sending
    max_items: int = 50              # maximum items in one digest
    template_id: str = "digest_email"
    channel: str = "email"


class NotificationBatcher:
    """Batch individual notifications into periodic digests.

    Instead of sending 20 "new comment" notifications in an hour,
    send one digest email with all 20 comments.
    """

    def __init__(self, redis_client: redis.Redis, repo):
        self.redis = redis_client
        self.repo = repo

    async def add_to_batch(
        self,
        user_id: str,
        notification_type: str,
        data: dict[str, Any],
    ) -> int:
        """Add a notification to the user's pending batch.

        Returns the current batch size.
        """
        key = f"batch:{user_id}:{notification_type}"
        item = json.dumps({
            "type": notification_type,
            "data": data,
            "created_at": datetime.utcnow().isoformat(),
        })

        # Add to sorted set with timestamp as score
        score = datetime.utcnow().timestamp()
        await self.redis.zadd(key, {item: score})

        # Set TTL (auto-expire if digest job doesn't run)
        await self.redis.expire(key, 86400)  # 24 hours

        count = await self.redis.zcard(key)
        logger.debug(f"Batch {user_id}/{notification_type}: {count} items")
        return count

    async def flush_batch(
        self,
        user_id: str,
        notification_type: str,
        max_items: int = 50,
    ) -> list[BatchedNotification]:
        """Get and clear pending batch items.

        Called by the digest cron job.
        """
        key = f"batch:{user_id}:{notification_type}"

        # Atomically get and delete items
        items = await self.redis.zrange(key, 0, max_items - 1)
        if not items:
            return []

        # Remove flushed items
        await self.redis.zremrangebyrank(key, 0, len(items) - 1)

        batched = []
        for item_bytes in items:
            item_str = item_bytes.decode() if isinstance(item_bytes, bytes) else item_bytes
            item = json.loads(item_str)
            batched.append(BatchedNotification(
                notification_type=item["type"],
                data=item["data"],
                created_at=datetime.fromisoformat(item["created_at"]),
            ))

        return batched

    async def get_batch_size(
        self, user_id: str, notification_type: str
    ) -> int:
        """Check how many items are pending in a batch."""
        key = f"batch:{user_id}:{notification_type}"
        return await self.redis.zcard(key)


class DigestService:
    """Generate and send notification digests.

    Run as a cron job (e.g., every 15 minutes or hourly).
    """

    def __init__(
        self,
        batcher: NotificationBatcher,
        notification_service: NotificationService,
        preference_store: PreferenceStore,
        configs: dict[str, DigestConfig],
    ):
        self.batcher = batcher
        self.notifier = notification_service
        self.preferences = preference_store
        self.configs = configs

    async def process_digests(self) -> dict:
        """Process all pending digests for all users."""
        stats = {"processed": 0, "sent": 0, "skipped": 0}

        for digest_type, config in self.configs.items():
            # Find users with pending batched notifications
            users_with_batches = await self._find_users_with_batches(
                config.notification_types
            )

            for user_id in users_with_batches:
                # Check if enough items for a digest
                items = []
                for notif_type in config.notification_types:
                    batch_items = await self.batcher.flush_batch(
                        user_id, notif_type, config.max_items
                    )
                    items.extend(batch_items)

                if len(items) < config.min_items:
                    # Not enough items — put back
                    for item in items:
                        await self.batcher.add_to_batch(
                            user_id, item.notification_type, item.data
                        )
                    stats["skipped"] += 1
                    continue

                # Check user preferences
                prefs = await self.preferences.get_preferences(user_id)
                if prefs and prefs.digest_frequency != config.interval_minutes:
                    continue

                # Send digest
                await self._send_digest(user_id, items, config)
                stats["sent"] += 1
                stats["processed"] += len(items)

        logger.info(f"Digest processing: {stats}")
        return stats

    async def _send_digest(
        self,
        user_id: str,
        items: list[BatchedNotification],
        config: DigestConfig,
    ) -> None:
        """Render and send a digest notification."""
        # Group items by type
        grouped: dict[str, list] = {}
        for item in items:
            grouped.setdefault(item.notification_type, []).append(item.data)

        await self.notifier.send(NotificationRequest(
            user_id=user_id,
            type="digest",
            priority=Priority.LOW,
            data={
                "items": [
                    {"type": t, "entries": entries, "count": len(entries)}
                    for t, entries in grouped.items()
                ],
                "total_count": len(items),
                "period": f"Last {config.interval_minutes} minutes",
            },
            channels=[Channel(config.channel)],
        ))

    async def _find_users_with_batches(
        self, notification_types: list[str]
    ) -> list[str]:
        """Scan Redis for users with pending batch items."""
        users = set()
        for notif_type in notification_types:
            cursor = 0
            while True:
                cursor, keys = await self.batcher.redis.scan(
                    cursor, match=f"batch:*:{notif_type}", count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    parts = key_str.split(":")
                    if len(parts) >= 3:
                        users.add(parts[1])
                if cursor == 0:
                    break
        return list(users)


# --- Digest configurations ---
DIGEST_CONFIGS = {
    "social_digest": DigestConfig(
        notification_types=["comment.reply", "mention", "like"],
        interval_minutes=60,     # hourly digest
        min_items=3,             # don't send for < 3 items
        max_items=50,
        template_id="digest_social",
    ),
    "activity_digest": DigestConfig(
        notification_types=["project.update", "task.assigned", "review.requested"],
        interval_minutes=240,    # every 4 hours
        min_items=1,
        max_items=20,
        template_id="digest_activity",
    ),
}
```

```python
# --- smart_dedup.py --- Intelligent notification coalescing ---

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CoalescingRule:
    """Rule for coalescing similar notifications."""
    notification_type: str
    window_seconds: int
    group_by: list[str]          # fields to group by
    summary_template: str        # template for coalesced notification
    max_individual: int = 3      # show up to N individual, then summarize


COALESCING_RULES = {
    "comment.reply": CoalescingRule(
        notification_type="comment.reply",
        window_seconds=300,       # 5 minute window
        group_by=["thread_id"],   # coalesce per thread
        summary_template="{count} new replies in {thread_name}",
        max_individual=3,
    ),
    "like": CoalescingRule(
        notification_type="like",
        window_seconds=600,       # 10 minute window
        group_by=["post_id"],     # coalesce per post
        summary_template="{first_name} and {count} others liked your post",
        max_individual=1,
    ),
    "follow": CoalescingRule(
        notification_type="follow",
        window_seconds=3600,      # 1 hour window
        group_by=[],              # coalesce all follows
        summary_template="{first_name} and {count} others followed you",
        max_individual=1,
    ),
}


# Coalescing example:
#
# Without coalescing (annoying):
#   "Alice liked your post"
#   "Bob liked your post"
#   "Charlie liked your post"
#   "Dave liked your post"
#   "Eve liked your post"
#
# With coalescing (clean):
#   "Alice and 4 others liked your post"
#
# Push notification for comments:
#   Individual (1-3 replies):
#     "Alice: Great article!"
#     "Bob: I agree with your point about..."
#     "Charlie: Have you considered..."
#   Coalesced (4+ replies):
#     "3 new replies in 'System Design Best Practices'"
```

| Strategy | When to use | Implementation |
|----------|-------------|---------------|
| Idempotency dedup | Prevent exact duplicates from retries | Hash-based key in Redis with TTL |
| Content dedup | Same type for same user in window | user_id + type + window in Redis |
| Rate limiting | Max N per type per hour | Redis counter with TTL |
| Batching | Group into periodic digests | Redis sorted set + cron flush |
| Coalescing | Merge similar real-time notifications | Group by field, summary template |

Key patterns:
1. Deduplicate by idempotency key first, then by content hash within a time window
2. Batch "batchable" notification types (social, activity) into periodic digests
3. Use coalescing rules to merge similar real-time notifications ("Alice and 4 others")
4. Allow users to configure digest frequency (immediate, hourly, daily, weekly)
5. Set a minimum batch size to avoid sending a "digest" with only one item'''
    ),
    (
        "system-design/notification-preferences",
        "Design a notification preference management system with per-channel, per-type controls, DND schedules, and frequency settings.",
        '''Notification preference management with granular controls:

```python
# --- preferences.py --- User notification preferences ---

from __future__ import annotations

import json
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DigestFrequency(Enum):
    IMMEDIATE = "immediate"    # send individually, no batching
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    NONE = "none"              # disable entirely


@dataclass
class DNDSchedule:
    """Do Not Disturb schedule."""
    enabled: bool = False
    start_time: dt_time = field(default_factory=lambda: dt_time(22, 0))  # 10 PM
    end_time: dt_time = field(default_factory=lambda: dt_time(8, 0))     # 8 AM
    timezone: str = "UTC"
    allow_critical: bool = True  # always allow critical notifications


@dataclass
class ChannelPreference:
    """Per-channel notification preference."""
    channel: str               # "email", "push", "sms", "in_app"
    enabled: bool = True
    digest_frequency: DigestFrequency = DigestFrequency.IMMEDIATE


@dataclass
class TypePreference:
    """Per-notification-type preference."""
    type_id: str               # "comment.reply", "order.confirmed"
    enabled: bool = True
    channels: dict[str, bool] = field(default_factory=dict)  # channel -> enabled
    digest_frequency: Optional[DigestFrequency] = None  # override channel default


@dataclass
class UserPreferences:
    """Complete notification preferences for a user."""
    user_id: str
    global_enabled: bool = True
    channels: dict[str, ChannelPreference] = field(default_factory=dict)
    types: dict[str, TypePreference] = field(default_factory=dict)
    dnd: DNDSchedule = field(default_factory=DNDSchedule)
    digest_frequency: DigestFrequency = DigestFrequency.IMMEDIATE
    muted_rooms: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def is_channel_enabled(self, channel) -> bool:
        """Check if a channel is globally enabled."""
        channel_name = channel.value if hasattr(channel, "value") else str(channel)
        pref = self.channels.get(channel_name)
        return pref.enabled if pref else True  # default: enabled

    def is_type_enabled(self, type_id: str, channel) -> bool:
        """Check if a notification type is enabled for a channel."""
        type_pref = self.types.get(type_id)
        if not type_pref:
            return True  # default: enabled

        if not type_pref.enabled:
            return False

        channel_name = channel.value if hasattr(channel, "value") else str(channel)
        channel_enabled = type_pref.channels.get(channel_name)
        if channel_enabled is not None:
            return channel_enabled

        return True  # default: enabled for unspecified channels

    def is_in_dnd(self) -> bool:
        """Check if user is currently in DND window."""
        if not self.dnd.enabled:
            return False

        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self.dnd.timezone)
        now = datetime.now(tz).time()

        start = self.dnd.start_time
        end = self.dnd.end_time

        if start <= end:
            return start <= now <= end
        else:
            # Overnight DND (e.g., 22:00 - 08:00)
            return now >= start or now <= end

    def is_frequency_capped(self, type_id: str) -> bool:
        """Check if digest frequency means this should be batched."""
        type_pref = self.types.get(type_id)
        freq = None
        if type_pref and type_pref.digest_frequency:
            freq = type_pref.digest_frequency
        else:
            freq = self.digest_frequency

        return freq != DigestFrequency.IMMEDIATE

    def is_room_muted(self, room_id: str) -> bool:
        return room_id in self.muted_rooms


class PreferenceStore:
    """Store and retrieve user notification preferences."""

    def __init__(self, db, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self.cache_ttl = 300  # 5 minutes

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences (cached)."""
        cache_key = f"prefs:{user_id}"
        cached = await self.redis.get(cache_key)

        if cached:
            return self._deserialize(cached)

        # Load from database
        row = await self.db.fetch_one(
            "SELECT preferences FROM user_notification_preferences WHERE user_id = :user_id",
            {"user_id": user_id},
        )

        if row:
            prefs = self._deserialize(row["preferences"])
        else:
            prefs = self._default_preferences(user_id)

        # Cache
        await self.redis.set(
            cache_key,
            self._serialize(prefs),
            ex=self.cache_ttl,
        )

        return prefs

    async def update_preferences(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> UserPreferences:
        """Update user preferences."""
        prefs = await self.get_preferences(user_id)

        # Apply updates
        if "global_enabled" in updates:
            prefs.global_enabled = updates["global_enabled"]

        if "channels" in updates:
            for channel_name, settings in updates["channels"].items():
                prefs.channels[channel_name] = ChannelPreference(
                    channel=channel_name,
                    **settings,
                )

        if "types" in updates:
            for type_id, settings in updates["types"].items():
                prefs.types[type_id] = TypePreference(
                    type_id=type_id,
                    **settings,
                )

        if "dnd" in updates:
            dnd_data = updates["dnd"]
            prefs.dnd = DNDSchedule(
                enabled=dnd_data.get("enabled", False),
                start_time=dt_time.fromisoformat(dnd_data.get("start_time", "22:00")),
                end_time=dt_time.fromisoformat(dnd_data.get("end_time", "08:00")),
                timezone=dnd_data.get("timezone", "UTC"),
            )

        if "digest_frequency" in updates:
            prefs.digest_frequency = DigestFrequency(updates["digest_frequency"])

        if "muted_rooms" in updates:
            prefs.muted_rooms = updates["muted_rooms"]

        prefs.updated_at = datetime.utcnow()

        # Persist
        serialized = self._serialize(prefs)
        await self.db.execute(
            """INSERT INTO user_notification_preferences (user_id, preferences, updated_at)
               VALUES (:user_id, :preferences, NOW())
               ON CONFLICT (user_id) DO UPDATE
               SET preferences = :preferences, updated_at = NOW()""",
            {"user_id": user_id, "preferences": serialized},
        )

        # Invalidate cache
        await self.redis.delete(f"prefs:{user_id}")

        return prefs

    def _default_preferences(self, user_id: str) -> UserPreferences:
        """Default preferences for new users."""
        return UserPreferences(
            user_id=user_id,
            global_enabled=True,
            channels={
                "email": ChannelPreference(channel="email", enabled=True),
                "push": ChannelPreference(channel="push", enabled=True),
                "in_app": ChannelPreference(channel="in_app", enabled=True),
                "sms": ChannelPreference(channel="sms", enabled=False),
            },
            dnd=DNDSchedule(enabled=False),
            digest_frequency=DigestFrequency.IMMEDIATE,
        )

    def _serialize(self, prefs: UserPreferences) -> str:
        return json.dumps(prefs, default=self._json_encoder)

    def _deserialize(self, data) -> UserPreferences:
        if isinstance(data, bytes):
            data = data.decode()
        if isinstance(data, str):
            data = json.loads(data)
        # Reconstruct UserPreferences from dict
        return UserPreferences(
            user_id=data.get("user_id", ""),
            global_enabled=data.get("global_enabled", True),
            channels={
                k: ChannelPreference(**v)
                for k, v in data.get("channels", {}).items()
            },
            types={
                k: TypePreference(**v)
                for k, v in data.get("types", {}).items()
            },
            dnd=DNDSchedule(**data.get("dnd", {})) if "dnd" in data else DNDSchedule(),
            digest_frequency=DigestFrequency(data.get("digest_frequency", "immediate")),
            muted_rooms=data.get("muted_rooms", []),
        )

    @staticmethod
    def _json_encoder(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dt_time):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            from dataclasses import asdict
            return asdict(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
```

```python
# --- preferences_api.py --- REST API for notification preferences ---

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional


app = FastAPI()


class ChannelUpdate(BaseModel):
    enabled: bool
    digest_frequency: Optional[str] = None


class TypeUpdate(BaseModel):
    enabled: bool
    channels: Optional[dict[str, bool]] = None
    digest_frequency: Optional[str] = None


class DNDUpdate(BaseModel):
    enabled: bool
    start_time: str = "22:00"
    end_time: str = "08:00"
    timezone: str = "UTC"


class PreferenceUpdate(BaseModel):
    global_enabled: Optional[bool] = None
    channels: Optional[dict[str, ChannelUpdate]] = None
    types: Optional[dict[str, TypeUpdate]] = None
    dnd: Optional[DNDUpdate] = None
    digest_frequency: Optional[str] = None
    muted_rooms: Optional[list[str]] = None


@app.get("/api/notifications/preferences")
async def get_preferences(user_id: str = Depends(get_current_user_id)):
    """Get current user's notification preferences."""
    store = get_preference_store()
    prefs = await store.get_preferences(user_id)
    return {
        "global_enabled": prefs.global_enabled,
        "channels": {
            name: {"enabled": cp.enabled, "digest_frequency": cp.digest_frequency.value}
            for name, cp in prefs.channels.items()
        },
        "types": {
            tid: {
                "enabled": tp.enabled,
                "channels": tp.channels,
                "digest_frequency": tp.digest_frequency.value if tp.digest_frequency else None,
            }
            for tid, tp in prefs.types.items()
        },
        "dnd": {
            "enabled": prefs.dnd.enabled,
            "start_time": prefs.dnd.start_time.isoformat(),
            "end_time": prefs.dnd.end_time.isoformat(),
            "timezone": prefs.dnd.timezone,
        },
        "digest_frequency": prefs.digest_frequency.value,
        "muted_rooms": prefs.muted_rooms,
    }


@app.patch("/api/notifications/preferences")
async def update_preferences(
    update: PreferenceUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update notification preferences.

    Supports partial updates — only specified fields are changed.
    """
    store = get_preference_store()
    updates = update.model_dump(exclude_none=True)

    if not updates:
        raise HTTPException(400, "No updates provided")

    prefs = await store.update_preferences(user_id, updates)
    return {"status": "updated"}


@app.post("/api/notifications/preferences/mute/{room_id}")
async def mute_room(
    room_id: str,
    duration_hours: Optional[int] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Mute notifications for a specific room/channel."""
    store = get_preference_store()
    prefs = await store.get_preferences(user_id)

    if room_id not in prefs.muted_rooms:
        prefs.muted_rooms.append(room_id)

    await store.update_preferences(user_id, {"muted_rooms": prefs.muted_rooms})
    return {"status": "muted", "room_id": room_id}


@app.delete("/api/notifications/preferences/mute/{room_id}")
async def unmute_room(
    room_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Unmute notifications for a room."""
    store = get_preference_store()
    prefs = await store.get_preferences(user_id)

    prefs.muted_rooms = [r for r in prefs.muted_rooms if r != room_id]
    await store.update_preferences(user_id, {"muted_rooms": prefs.muted_rooms})
    return {"status": "unmuted", "room_id": room_id}
```

| Preference Level | Scope | Example |
|-----------------|-------|---------|
| Global | All notifications | "Pause all notifications" |
| Channel | All notifications on one channel | "Disable email notifications" |
| Category | Group of notification types | "Disable all marketing notifications" |
| Type + Channel | Specific type on specific channel | "Disable push for comment replies" |
| Room/Thread | Specific conversation | "Mute #general channel" |
| DND schedule | Time-based suppression | "No notifications 10 PM - 8 AM" |
| Digest frequency | Batching preference | "Send hourly digests for social notifications" |

Key patterns:
1. Default preferences should be sensible — enable essential channels, disable SMS by default
2. Critical notifications (auth codes, security alerts) bypass ALL preferences including DND
3. Cache preferences in Redis with short TTL (5 min) since they are checked on every notification
4. Support partial updates via PATCH — users should not need to send full preference objects
5. Provide both per-type and per-channel granularity — users want "no push for likes" not "no push at all"'''
    ),
]
