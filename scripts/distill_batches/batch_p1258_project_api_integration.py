"""
Real-world project help training pairs - Third-party API integration
"""

pairs = [
    {
        "instruction": r'''I need to integrate Stripe for subscription billing in my FastAPI app. Users pick a plan, enter card details, and get billed monthly. What's the right architecture? I don't want to store any card data on my server.''',
        "output": r'''<think>
Stripe subscription integration. The key is using Stripe Checkout or Payment Elements so card data never touches their server. The flow should be:

1. Create a Stripe Customer when user signs up
2. Create a Checkout Session when they pick a plan
3. Stripe handles the payment page
4. Webhook confirms the subscription
5. Store subscription status locally, Stripe is the source of truth for billing

Never store card numbers. Never build a custom payment form that sends card data to your server.
</think>

Use Stripe Checkout Sessions -- Stripe hosts the payment page, card data never touches your server.

Architecture:

```
User picks plan -> Your API creates Checkout Session -> Redirect to Stripe
Stripe collects payment -> Webhook to your API -> Update subscription status
```

Models:

```python
# models.py
class UserSubscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    stripe_customer_id = Column(String(50))
    stripe_subscription_id = Column(String(50))
    plan = Column(String(20))  # "basic", "pro", "enterprise"
    status = Column(String(20), default="inactive")  # active, past_due, canceled
    current_period_end = Column(DateTime)
```

Endpoints:

```python
import stripe
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

PRICE_IDS = {
    "basic": "price_XXXXXXXXXXXX",
    "pro": "price_YYYYYYYYYYYY",
}

@app.post("/api/subscribe")
def create_checkout(plan: str, current_user=Depends(get_current_user)):
    sub = db.query(UserSubscription).filter_by(user_id=current_user.id).first()

    if not sub or not sub.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        if not sub:
            sub = UserSubscription(user_id=current_user.id)
            db.add(sub)
        sub.stripe_customer_id = customer.id
        db.commit()

    session = stripe.checkout.Session.create(
        customer=sub.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
        mode="subscription",
        success_url="https://myapp.com/billing?success=true",
        cancel_url="https://myapp.com/billing?canceled=true",
    )
    return {"checkout_url": session.url}
```

The critical part -- the webhook:

```python
@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        sub = db.query(UserSubscription).filter_by(
            stripe_customer_id=session["customer"]
        ).first()
        if sub:
            sub.stripe_subscription_id = session["subscription"]
            sub.status = "active"
            sub.plan = "pro"  # map from price ID
            db.commit()

    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        sub = db.query(UserSubscription).filter_by(
            stripe_customer_id=invoice["customer"]
        ).first()
        if sub:
            sub.status = "past_due"
            db.commit()

    return {"received": True}
```

Test with Stripe CLI: `stripe listen --forward-to localhost:8000/api/webhooks/stripe`

Key rule: always trust webhooks over client-side callbacks. The success_url redirect is just for UX -- the webhook is what actually activates the subscription.'''
    },
    {
        "instruction": r'''I need to send SMS notifications using Twilio. Users get an SMS when their order ships. I'm worried about error handling -- what happens when Twilio is down or the phone number is bad? This is a Django app with Celery.''',
        "output": r'''Good instinct on the error handling. SMS delivery has many failure modes. Wrap Twilio in a service with retries and proper error categorization.

```python
# services/sms.py
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger("sms")

class SMSService:
    # Twilio error codes that mean "don't retry"
    PERMANENT_ERRORS = {
        21211,  # Invalid phone number
        21614,  # Not a mobile number
        21408,  # Permission not enabled for region
        21610,  # Unsubscribed recipient
    }

    def __init__(self):
        self.client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        )
        self.from_number = settings.TWILIO_FROM_NUMBER

    def send(self, to, body):
        try:
            message = self.client.messages.create(
                body=body[:1600],  # Twilio limit
                from_=self.from_number,
                to=to,
            )
            logger.info(f"SMS sent: sid={message.sid} to={to}")
            return {"success": True, "sid": message.sid}

        except TwilioRestException as e:
            logger.error(f"Twilio error {e.code}: {e.msg} to={to}")

            if e.code in self.PERMANENT_ERRORS:
                return {"success": False, "error": e.msg, "retryable": False}

            # Transient errors (rate limit, server error)
            return {"success": False, "error": e.msg, "retryable": True}

        except Exception as e:
            logger.error(f"SMS unexpected error: {e} to={to}")
            return {"success": False, "error": str(e), "retryable": True}

sms_service = SMSService()
```

Celery task with smart retries:

```python
# tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_shipping_sms(self, order_id):
    order = Order.objects.select_related("user").get(id=order_id)
    user = order.user

    if not user.phone or not user.sms_enabled:
        return {"skipped": True, "reason": "no phone or sms disabled"}

    body = (
        f"Your order #{order.id} has shipped! "
        f"Tracking: {order.tracking_number}. "
        f"Expected delivery: {order.estimated_delivery:%b %d}."
    )

    result = sms_service.send(user.phone, body)

    if not result["success"]:
        if result.get("retryable"):
            raise self.retry(exc=Exception(result["error"]))
        else:
            # Permanent failure -- mark phone as invalid
            logger.warning(f"Permanent SMS failure for user {user.id}: {result['error']}")
            user.phone_valid = False
            user.save(update_fields=["phone_valid"])

    return result
```

Trigger it from the order update:

```python
# In your view or signal
def mark_order_shipped(order, tracking_number):
    order.status = "shipped"
    order.tracking_number = tracking_number
    order.save()

    # Fire and forget -- the task handles retries
    send_shipping_sms.delay(order.id)
```

Important details:
- Always check `sms_enabled` -- users must be able to opt out
- Truncate body to 1600 chars (Twilio's limit)
- Mark invalid phone numbers so you stop retrying permanently bad numbers
- Log the Twilio message SID for debugging delivery issues
- Use Celery retries with backoff, not Twilio's built-in retry (you have more control)'''
    },
    {
        "instruction": r'''I need to upload files to AWS S3 from my FastAPI app. Users upload profile pictures (max 5MB) and documents (max 50MB). I want presigned URLs so large files don't go through my server. How do I set this up?''',
        "output": r'''<think>
Presigned URL flow:
1. Client asks your API for an upload URL
2. API generates a presigned S3 PUT URL
3. Client uploads directly to S3 using that URL
4. Client tells your API the upload is complete
5. API verifies the file exists and saves the reference

This keeps large files off your server completely.
</think>

Use presigned URLs for direct browser-to-S3 uploads. Your server never handles the file bytes.

```python
# services/storage.py
import boto3
from botocore.config import Config
import uuid

s3 = boto3.client(
    "s3",
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)

BUCKET = "myapp-uploads"

UPLOAD_CONFIGS = {
    "profile_picture": {
        "max_size": 5 * 1024 * 1024,  # 5MB
        "allowed_types": ["image/jpeg", "image/png", "image/webp"],
        "prefix": "profiles",
    },
    "document": {
        "max_size": 50 * 1024 * 1024,  # 50MB
        "allowed_types": ["application/pdf", "image/jpeg", "image/png"],
        "prefix": "documents",
    },
}

def create_presigned_upload(upload_type, filename, content_type, user_id):
    config = UPLOAD_CONFIGS.get(upload_type)
    if not config:
        raise ValueError(f"Unknown upload type: {upload_type}")

    if content_type not in config["allowed_types"]:
        raise ValueError(f"File type {content_type} not allowed")

    # Generate a unique key
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    key = f"{config['prefix']}/{user_id}/{uuid.uuid4().hex}.{ext}"

    # Generate presigned URL
    presigned = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=600,  # URL valid for 10 minutes
    )

    return {"upload_url": presigned, "key": key}
```

API endpoints:

```python
from pydantic import BaseModel

class UploadRequest(BaseModel):
    upload_type: str  # "profile_picture" or "document"
    filename: str
    content_type: str

class UploadConfirm(BaseModel):
    key: str

@app.post("/api/uploads/presign")
def get_upload_url(req: UploadRequest, user=Depends(get_current_user)):
    try:
        result = create_presigned_upload(
            req.upload_type, req.filename, req.content_type, user.id
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/uploads/confirm")
def confirm_upload(req: UploadConfirm, user=Depends(get_current_user)):
    # Verify the file actually exists in S3
    try:
        head = s3.head_object(Bucket=BUCKET, Key=req.key)
    except s3.exceptions.ClientError:
        raise HTTPException(400, "File not found in S3")

    # Check the key belongs to this user
    if f"/{user.id}/" not in req.key:
        raise HTTPException(403, "Not your upload")

    # Check file size
    upload_type = req.key.split("/")[0]
    max_size = UPLOAD_CONFIGS.get(upload_type, {}).get("max_size", 0)
    if head["ContentLength"] > max_size:
        s3.delete_object(Bucket=BUCKET, Key=req.key)
        raise HTTPException(400, "File too large")

    # Save reference in database
    upload = Upload(user_id=user.id, s3_key=req.key, size=head["ContentLength"])
    db.add(upload)
    db.commit()

    return {"id": upload.id, "url": f"https://{BUCKET}.s3.amazonaws.com/{req.key}"}
```

Frontend usage:

```javascript
// 1. Get presigned URL
const { upload_url, key } = await api.post("/uploads/presign", {
    upload_type: "profile_picture",
    filename: file.name,
    content_type: file.type,
});

// 2. Upload directly to S3
await fetch(upload_url, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type },
});

// 3. Confirm upload
const result = await api.post("/uploads/confirm", { key });
```

S3 bucket CORS config (required for browser uploads):

```json
[{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT"],
    "AllowedOrigins": ["https://myapp.com"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
}]
```'''
    },
    {
        "instruction": r'''I'm integrating with a flaky third-party API that times out about 5% of the time. It's a payment processor we can't replace. How do I make my integration resilient without adding a bunch of complexity?''',
        "output": r'''Use the circuit breaker + retry pattern. Python has good libraries for this so you don't build it yourself.

Simple approach with tenacity (retry library) and a basic circuit breaker:

```python
# services/payment_gateway.py
import httpx
import logging
import time
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

logger = logging.getLogger("payment_gateway")

class PaymentGateway:
    BASE_URL = "https://api.paymentprocessor.com/v1"

    def __init__(self, api_key):
        self.api_key = api_key
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0),
        )
        # Simple circuit breaker state
        self._failures = 0
        self._last_failure = 0
        self._circuit_open = False

    def _check_circuit(self):
        if self._circuit_open:
            # Allow retry after 30 seconds
            if time.time() - self._last_failure > 30:
                self._circuit_open = False
                self._failures = 0
                logger.info("Circuit breaker: half-open, attempting request")
            else:
                raise CircuitOpenError("Payment gateway circuit breaker is open")

    def _record_success(self):
        self._failures = 0
        self._circuit_open = False

    def _record_failure(self):
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= 5:
            self._circuit_open = True
            logger.critical("Circuit breaker OPEN: payment gateway failing")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def charge(self, amount_cents, customer_id, idempotency_key):
        self._check_circuit()

        try:
            resp = self.client.post(
                "/charges",
                json={
                    "amount": amount_cents,
                    "customer_id": customer_id,
                    "currency": "usd",
                },
                headers={"Idempotency-Key": idempotency_key},
            )

            if resp.status_code == 200:
                self._record_success()
                return resp.json()
            elif resp.status_code == 429:
                self._record_failure()
                raise httpx.TimeoutException("Rate limited")
            elif resp.status_code >= 500:
                self._record_failure()
                raise httpx.NetworkError(f"Server error: {resp.status_code}")
            else:
                # 4xx client errors should NOT be retried
                return {"error": resp.json(), "status": resp.status_code}

        except (httpx.TimeoutException, httpx.NetworkError):
            self._record_failure()
            raise

class CircuitOpenError(Exception):
    pass
```

The idempotency key is critical for payment retries:

```python
import hashlib

def make_idempotency_key(order_id, attempt="initial"):
    return hashlib.sha256(f"charge-{order_id}-{attempt}".encode()).hexdigest()

# Usage
gateway = PaymentGateway(api_key=os.environ["PAYMENT_API_KEY"])

try:
    result = gateway.charge(
        amount_cents=2999,
        customer_id="cust_abc123",
        idempotency_key=make_idempotency_key(order.id),
    )
except CircuitOpenError:
    # Gateway is down -- show user a friendly message
    return {"error": "Payment processing is temporarily unavailable. Please try again in a few minutes."}
except Exception as e:
    # All retries exhausted
    logger.error(f"Payment failed after retries: {e}")
    return {"error": "Payment failed. You have not been charged."}
```

This handles the 5% failure rate transparently. Users experience a slight delay (retry backoff) instead of an error. The circuit breaker prevents cascading failures if the gateway goes fully down.'''
    },
    {
        "instruction": r'''I need to integrate Google OAuth login into my existing Django app that uses email/password auth. Users should be able to link their Google account to their existing account or sign up with Google directly. What's the cleanest way?''',
        "output": r'''Use django-allauth -- it handles Google OAuth plus the account linking logic you need. Don't build OAuth from scratch.

```bash
pip install django-allauth
```

Settings:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

MIDDLEWARE = [
    # ... existing middleware ...
    "allauth.account.middleware.AccountMiddleware",
]

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # keep existing login
    "allauth.account.auth_backends.AuthenticationBackend",
]

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "secret": os.environ["GOOGLE_CLIENT_SECRET"],
        },
    },
}

# Key settings for your use case:
ACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_AUTO_SIGNUP = True
ACCOUNT_UNIQUE_EMAIL = True
# This connects Google login to existing accounts with the same email:
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

LOGIN_REDIRECT_URL = "/dashboard/"
```

URLs:

```python
# urls.py
urlpatterns = [
    # ... existing urls ...
    path("accounts/", include("allauth.urls")),
]
```

Run migrations:

```bash
python manage.py migrate
```

Add the Google login button to your login template:

```html
<!-- templates/account/login.html -->
{% load socialaccount %}

<form method="post" action="{% url 'account_login' %}">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Sign in with email</button>
</form>

<hr>

<a href="{% provider_login_url 'google' %}">
    Sign in with Google
</a>
```

For account linking (logged-in user connects Google):

```html
<!-- templates/account/settings.html -->
{% load socialaccount %}
{% get_social_accounts user as accounts %}

{% if accounts.google %}
    <p>Google account connected: {{ accounts.google.0.extra_data.email }}</p>
{% else %}
    <a href="{% provider_login_url 'google' process='connect' %}">
        Connect Google account
    </a>
{% endif %}
```

Google Cloud Console setup:
1. Create OAuth 2.0 credentials at console.cloud.google.com
2. Set authorized redirect URI to: `https://yoursite.com/accounts/google/login/callback/`
3. Copy client ID and secret to your environment variables

The flow handles three scenarios automatically:
- New user signs up with Google -> creates account
- Existing user logs in with Google (same email) -> links and logs in
- Logged-in user clicks "Connect Google" -> links accounts

No custom OAuth code needed. django-allauth handles token exchange, profile fetching, and account matching.'''
    },
]
