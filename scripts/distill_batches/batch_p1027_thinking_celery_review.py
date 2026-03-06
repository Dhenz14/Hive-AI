r"""Thinking-trace pairs: Celery code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Celery code and identify issues:

```python
from celery import Celery
from celery.utils.log import get_task_logger
import requests
import time
import json
from datetime import datetime

app = Celery('tasks', broker='redis://localhost:6379/0')
app.conf.result_backend = 'redis://localhost:6379/1'
app.conf.task_serializer = 'pickle'
app.conf.result_serializer = 'pickle'
app.conf.accept_content = ['pickle', 'json']

logger = get_task_logger(__name__)

@app.task
def send_email(user_email, subject, body):
    response = requests.post(
        'https://api.mailservice.com/send',
        json={'to': user_email, 'subject': subject, 'body': body},
        timeout=30,
    )
    if response.status_code != 200:
        raise Exception(f"Email failed: {response.text}")
    return {'sent': True, 'timestamp': str(datetime.now())}

@app.task
def process_order(order_dict):
    from app.models import Order, Product
    from app import db

    order = Order.query.get(order_dict['id'])
    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock -= item.quantity
        db.session.add(product)

    order.status = 'processed'
    db.session.commit()

    send_email.delay(
        order.user.email,
        'Order Confirmed',
        f'Your order #{order.id} has been processed.'
    )
    send_notification.delay(order.user_id, 'order_processed', order.id)
    update_analytics.delay('order_processed', order.total)
    return {'order_id': order.id, 'status': 'processed'}

@app.task
def generate_report(report_type, date_range):
    from app.models import Order
    from app import db

    orders = Order.query.filter(
        Order.created_at.between(date_range['start'], date_range['end'])
    ).all()

    report_data = []
    for order in orders:
        report_data.append({
            'id': order.id,
            'user': order.user.username,
            'total': float(order.total),
            'items': len(order.items),
        })

    filename = f'/tmp/report_{report_type}_{datetime.now().strftime("%Y%m%d")}.json'
    with open(filename, 'w') as f:
        json.dump(report_data, f)

    return {'filename': filename, 'rows': len(report_data)}

@app.task
def cleanup_old_sessions():
    from app.models import Session
    from app import db
    old = Session.query.filter(Session.expires_at < datetime.now()).all()
    for s in old:
        db.session.delete(s)
    db.session.commit()
    return {'deleted': len(old)}

@app.task
def sync_inventory():
    from app.models import Product
    from app import db
    products = Product.query.all()
    for product in products:
        response = requests.get(
            f'https://warehouse-api.example.com/stock/{product.sku}',
            timeout=10,
        )
        if response.ok:
            product.stock = response.json()['quantity']
            db.session.add(product)
    db.session.commit()
    return {'synced': len(products)}
```''', r'''<think>
Let me review this Celery task code for task design, retry logic, serialization, error handling, and configuration.

1. Serialization security:
- task_serializer = 'pickle' and accept_content includes 'pickle'. Pickle deserialization is a well-known remote code execution vector. If an attacker can inject messages into the broker (Redis), they can execute arbitrary code on workers. NEVER use pickle serializer in production.

2. No retry logic:
- send_email has no retry mechanism. If the mail service is temporarily down, the email is lost. Should use autoretry_for with exponential backoff.
- sync_inventory makes HTTP requests in a loop with no retry per-product. If one request fails, the entire task could fail (unhandled exception).

3. Task design issues:
- process_order does too much: updates stock, changes status, sends email, sends notification, updates analytics. If the email send fails to queue, the order is still committed as processed. These should be separate tasks or use a chain/chord.
- process_order passes the entire order as a dict, then re-queries it from the database. This is fine for the initial load, but the object is stale -- another process could have modified it.
- process_order has no idempotency. If the task is retried (duplicate delivery), it decrements stock again.

4. Database issues:
- No error handling or rollback. If db.session.commit() fails, the session is in a dirty state.
- cleanup_old_sessions loads all old sessions into memory then deletes one by one. Should use a bulk DELETE query.
- sync_inventory loads all products and makes an HTTP request per product. For thousands of products, this task runs for hours.

5. File path issues:
- generate_report writes to /tmp with a date-based filename. If run multiple times on the same day with the same report_type, it overwrites the previous report. Also, /tmp files can be read by other users on the system.
- The report filename is constructed with datetime.now() which uses local time, not UTC.

6. No task timeouts:
- None of the tasks have time_limit or soft_time_limit set. A hung HTTP request or infinite loop will block the worker forever.

7. sync_inventory:
- Makes one HTTP request per product sequentially. For 1000 products with 10s timeout each, worst case is 10,000 seconds (2.7 hours). Should batch requests or use concurrent I/O.
- No rate limiting on the warehouse API calls.

Let me structure this.
</think>

## Code Review: Celery Task Suite

### CRITICAL - Security

**SEC1: Pickle serializer enables remote code execution (Severity: CRITICAL)**
```python
app.conf.task_serializer = 'pickle'
app.conf.accept_content = ['pickle', 'json']
```
Pickle deserialization executes arbitrary code. If an attacker gains access to the Redis broker (which has no authentication by default), they can craft a malicious pickle payload that executes shell commands on every worker. Switch to JSON:
```python
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']
```

### CRITICAL - No Retry Logic

**RT1: send_email has no retry (Severity: CRITICAL)**
If the mail service returns an error or times out, the email is permanently lost. Add retries with exponential backoff:
```python
@app.task(bind=True, autoretry_for=(requests.RequestException,),
          retry_backoff=60, retry_backoff_max=3600, max_retries=5)
def send_email(self, user_email, subject, body):
    ...
```

**RT2: sync_inventory has no per-item error handling (Severity: HIGH)**
One failed HTTP request crashes the entire task, leaving remaining products unsynced. Catch per-item errors:
```python
for product in products:
    try:
        response = requests.get(...)
        ...
    except requests.RequestException as e:
        logger.warning(f"Failed to sync {product.sku}: {e}")
        continue
```

### HIGH - Task Design

**TD1: process_order is not idempotent (Severity: HIGH)**
If the task is retried (broker duplicate delivery, worker crash during commit), stock is decremented again. The order may already be in 'processed' state. Add an idempotency check:
```python
if order.status == 'processed':
    return {'order_id': order.id, 'status': 'already_processed'}
```

**TD2: process_order does too many things (Severity: HIGH)**
Stock update, status change, email, notification, and analytics all in one task. If the commit succeeds but `send_email.delay` fails to enqueue, the user never gets confirmation. Use Celery chains or groups:
```python
from celery import chain
chain(
    update_stock.s(order_id),
    group(
        send_email.s(email, subject, body),
        send_notification.s(user_id, 'order_processed', order_id),
        update_analytics.s('order_processed', total),
    )
).apply_async()
```

### HIGH - Performance

**P1: cleanup_old_sessions loads and deletes row by row (Severity: HIGH)**
Loads all expired sessions into memory, then issues individual DELETE statements. For thousands of expired sessions, this is extremely slow. Use bulk delete:
```python
Session.query.filter(Session.expires_at < datetime.utcnow()).delete()
db.session.commit()
```

**P2: sync_inventory makes sequential HTTP requests (Severity: HIGH)**
One HTTP request per product, sequentially. For 1000 products at 10s timeout, worst case is 2.7 hours. Either batch the API calls, use async I/O, or split into sub-tasks:
```python
@app.task
def sync_inventory():
    product_ids = [p.id for p in Product.query.all()]
    group(sync_single_product.s(pid) for pid in product_ids).apply_async()
```

### MEDIUM - Missing Safeguards

**SG1: No task timeouts (Severity: MEDIUM)**
No `time_limit` or `soft_time_limit` on any task. A hung HTTP request blocks the worker indefinitely. Add limits:
```python
@app.task(soft_time_limit=300, time_limit=600)
```

**SG2: No database error handling (Severity: MEDIUM)**
No try/except around `db.session.commit()`. A failed commit leaves the session dirty, and subsequent operations on the same worker may fail.

### LOW - File Handling

**FH1: Report overwrites on same day (Severity: LOW)**
Filename uses date only. Multiple runs overwrite. Add a timestamp or UUID. Also, /tmp files may be readable by other system users -- use a secure temporary directory.'''),

    ("thinking/code-review", r'''Review this Celery code and identify issues:

```python
from celery import Celery, chain, group, chord
from celery.schedules import crontab
import redis
import json
import time

app = Celery('pipeline')
app.config_from_object('celeryconfig')

redis_client = redis.from_url('redis://localhost:6379/2')

@app.task(bind=True, max_retries=None)
def fetch_data(self, source_url):
    import requests
    try:
        response = requests.get(source_url, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        self.retry(exc=exc, countdown=5)

@app.task(bind=True, max_retries=3)
def transform_data(self, data, rules):
    try:
        result = apply_rules(data, rules)
        redis_client.set(f'transform:{self.request.id}', json.dumps(result))
        return result
    except Exception as exc:
        self.retry(exc=exc, countdown=10)

@app.task(bind=True)
def load_data(self, data, destination):
    from app.models import DataRecord
    from app import db
    records = []
    for item in data:
        record = DataRecord(**item)
        records.append(record)
    db.session.add_all(records)
    db.session.commit()
    return {'loaded': len(records)}

@app.task
def etl_pipeline(source_url, rules, destination):
    data = fetch_data.delay(source_url)
    result = data.get(timeout=300)
    transformed = transform_data.delay(result, rules)
    transformed_result = transformed.get(timeout=300)
    loaded = load_data.delay(transformed_result, destination)
    return loaded.get(timeout=300)

@app.task
def parallel_etl(sources):
    tasks = []
    for source in sources:
        task = chain(
            fetch_data.s(source['url']),
            transform_data.s(source['rules']),
            load_data.s(source['destination']),
        )
        tasks.append(task)
    result = group(tasks).apply_async()
    return result.get(timeout=3600)

@app.task
def aggregate_results(results):
    total = sum(r['loaded'] for r in results)
    redis_client.set('last_aggregate', json.dumps({
        'total': total,
        'timestamp': time.time(),
    }))
    return {'total_loaded': total}

app.conf.beat_schedule = {
    'daily-etl': {
        'task': 'tasks.parallel_etl',
        'schedule': crontab(hour=2, minute=0),
        'args': ([
            {'url': 'https://api.example.com/data1', 'rules': ['clean', 'normalize'], 'destination': 'table1'},
            {'url': 'https://api.example.com/data2', 'rules': ['clean', 'dedupe'], 'destination': 'table2'},
        ],),
    },
    'hourly-check': {
        'task': 'tasks.fetch_data',
        'schedule': crontab(minute=0),
        'args': ('https://api.example.com/health',),
    },
}
```''', r'''<think>
Let me review this Celery ETL pipeline code.

1. Critical anti-pattern -- .get() inside tasks:
- etl_pipeline calls `data.get(timeout=300)` which is a synchronous blocking call INSIDE a Celery task. This blocks the worker thread for up to 5 minutes while waiting for another task to complete. This is Celery's most well-known anti-pattern -- it can cause deadlocks if the worker pool is exhausted.
- parallel_etl also calls `result.get(timeout=3600)` -- blocking a worker for up to 1 hour.
- The proper pattern is to use chains and chords to compose tasks without blocking.

2. Infinite retries:
- fetch_data has max_retries=None with a fixed countdown of 5 seconds. If the source URL is permanently down, this task retries infinitely every 5 seconds forever. This floods the broker with retries and consumes worker resources permanently.
- No exponential backoff on retry countdown.

3. Data flow issues:
- transform_data stores results in Redis AND returns them. The Redis storage is redundant if the result is passed to the next task in a chain. If it's meant for monitoring, there is no TTL, so these keys persist forever.
- load_data does mass assignment with `DataRecord(**item)` -- same mass assignment risk discussed in other reviews.
- load_data has no error handling. If commit fails, no rollback.

4. Memory issues:
- load_data creates all DataRecord objects in memory before adding them. For large datasets, this consumes excessive memory. Should use bulk_save_objects or batch processing.
- The entire dataset flows through the result backend (Redis). Large datasets stored as task results can exhaust Redis memory.

5. Beat schedule:
- The daily-etl schedule uses parallel_etl which blocks a worker for up to 1 hour. If the worker pool is small, this can monopolize it.
- hourly-check fetches health data but does nothing with the result. The infinite retries on fetch_data mean a health check failure retries forever.

6. Redis client at module level:
- redis_client is created at import time. If Redis is unavailable when the module is imported, the worker fails to start.

Let me write the structured review.
</think>

## Code Review: Celery ETL Pipeline

### CRITICAL - Blocking .get() Inside Tasks

**BLK1: etl_pipeline blocks worker with .get() (Severity: CRITICAL)**
```python
@app.task
def etl_pipeline(source_url, rules, destination):
    data = fetch_data.delay(source_url)
    result = data.get(timeout=300)  # blocks worker for up to 5 min
```
Calling `.get()` inside a task blocks the worker thread, waiting synchronously for another task to finish. If all workers are blocked waiting for tasks that need a worker to execute, you get a deadlock. This is Celery's most well-known anti-pattern.

Fix: Use chains instead of blocking gets:
```python
@app.task
def run_etl(source_url, rules, destination):
    chain(
        fetch_data.s(source_url),
        transform_data.s(rules),
        load_data.s(destination),
    ).apply_async()
```

**BLK2: parallel_etl blocks for up to 1 hour (Severity: CRITICAL)**
`result.get(timeout=3600)` monopolizes a worker for an hour. Use a chord with a callback instead:
```python
@app.task
def parallel_etl(sources):
    pipelines = [
        chain(fetch_data.s(s['url']), transform_data.s(s['rules']), load_data.s(s['destination']))
        for s in sources
    ]
    chord(group(pipelines))(aggregate_results.s())
```

### CRITICAL - Infinite Retry Loop

**IR1: fetch_data retries forever (Severity: CRITICAL)**
```python
@app.task(bind=True, max_retries=None)
def fetch_data(self, source_url):
    ...
    self.retry(exc=exc, countdown=5)
```
If the source URL is permanently unreachable, this task retries every 5 seconds indefinitely. This floods the broker queue and wastes worker resources. Set a reasonable max_retries and use exponential backoff:
```python
@app.task(bind=True, max_retries=10, retry_backoff=True, retry_backoff_max=600)
def fetch_data(self, source_url):
    ...
```

### HIGH - Memory Issues

**MEM1: Large datasets in result backend (Severity: HIGH)**
Task results (potentially megabytes of data) are serialized and stored in Redis. For large datasets, this exhausts Redis memory. Consider:
- Store data in a database or object store, pass only a reference (ID or URL) between tasks
- Set `result_expires` to auto-delete old results

**MEM2: load_data creates all objects in memory (Severity: HIGH)**
```python
records = []
for item in data:
    record = DataRecord(**item)
    records.append(record)
db.session.add_all(records)
```
For large datasets, all records exist in memory simultaneously. Use batch processing:
```python
BATCH_SIZE = 1000
for i in range(0, len(data), BATCH_SIZE):
    batch = [DataRecord(**item) for item in data[i:i+BATCH_SIZE]]
    db.session.bulk_save_objects(batch)
    db.session.commit()
```

### HIGH - Error Handling

**EH1: load_data has no rollback (Severity: HIGH)**
If `db.session.commit()` fails, the session is left dirty. Add try/except/rollback.

**EH2: transform_data catches Exception broadly (Severity: MEDIUM)**
Retrying on any Exception includes programming errors (TypeError, AttributeError). Only retry on transient errors.

### MEDIUM - Redundant Storage

**RS1: transform_data writes to Redis and returns (Severity: MEDIUM)**
`redis_client.set(f'transform:{self.request.id}', ...)` stores the result in Redis with no TTL, alongside the Celery result backend also storing it. This doubles storage and the Redis keys are never cleaned up.

### MEDIUM - Beat Schedule

**BS1: Health check with infinite retries (Severity: MEDIUM)**
The hourly health check uses `fetch_data` which has `max_retries=None`. A health check failure spawns infinite retries that overlap with the next hourly check. Use a separate task with limited retries.

**BS2: No monitoring on failed scheduled tasks (Severity: LOW)**
No alerting or logging when scheduled ETL jobs fail. Consider adding on_failure callbacks or Celery event monitoring.'''),

    ("thinking/code-review", r'''Review this Celery code and identify issues:

```python
from celery import Celery
from celery.signals import task_failure, task_success, worker_ready
import logging
import smtplib
from email.mime.text import MIMEText

app = Celery('notifications')
app.config_from_object({
    'broker_url': 'amqp://guest:guest@localhost//',
    'result_backend': 'rpc://',
    'task_acks_late': True,
    'worker_prefetch_multiplier': 1,
    'task_reject_on_worker_lost': True,
    'task_default_rate_limit': '100/m',
    'worker_concurrency': 16,
})

logger = logging.getLogger(__name__)

@worker_ready.connect
def on_worker_ready(**kwargs):
    logger.info("Worker ready")
    # Warm up connections
    from app import db
    db.engine.connect()

@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None,
                    traceback=None, **kwargs):
    msg = MIMEText(f"Task {sender.name} failed: {exception}\n{traceback}")
    msg['Subject'] = f'Celery Task Failure: {sender.name}'
    msg['From'] = 'alerts@example.com'
    msg['To'] = 'dev-team@example.com'
    smtp = smtplib.SMTP('localhost')
    smtp.send_message(msg)
    smtp.quit()

@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    logger.info(f"Task {sender.name} succeeded with result: {result}")

@app.task(bind=True, acks_late=True, reject_on_worker_lost=True)
def send_push_notification(self, user_id, message, platform):
    from app.services import apns_client, fcm_client
    if platform == 'ios':
        apns_client.send(user_id, message)
    elif platform == 'android':
        fcm_client.send(user_id, message)
    else:
        raise ValueError(f"Unknown platform: {platform}")

@app.task(bind=True, rate_limit='10/s')
def send_bulk_notifications(self, user_ids, message):
    results = []
    for user_id in user_ids:
        try:
            send_push_notification(user_id, message, get_platform(user_id))
            results.append({'user_id': user_id, 'status': 'sent'})
        except Exception as e:
            results.append({'user_id': user_id, 'status': 'failed', 'error': str(e)})
    return results

@app.task(bind=True, max_retries=5)
def send_scheduled_notification(self, notification_id):
    from app.models import Notification
    from app import db

    notification = Notification.query.get(notification_id)
    if notification.sent:
        return {'status': 'already_sent'}

    send_push_notification.delay(
        notification.user_id,
        notification.message,
        notification.platform,
    )
    notification.sent = True
    db.session.commit()
    return {'status': 'sent'}

@app.task
def process_notification_batch(batch_id):
    from app.models import NotificationBatch
    from app import db

    batch = NotificationBatch.query.get(batch_id)
    notifications = batch.notifications.all()

    for notification in notifications:
        send_push_notification.delay(
            notification.user_id,
            notification.message,
            notification.platform,
        )

    batch.status = 'dispatched'
    db.session.commit()
```''', r'''<think>
Let me review this Celery notification system.

1. Signal handler issues:
- on_task_failure sends an email via SMTP synchronously in a signal handler. This blocks the worker for every failed task. If the SMTP server is slow or down, it delays all failure processing.
- If the SMTP send itself fails, it raises an exception in the signal handler, which can cause unpredictable behavior.
- Sending an email per failed task can flood the inbox. If 1000 tasks fail in a minute, that is 1000 emails.
- on_task_success logs the full result, which may contain sensitive data or large payloads.

2. Worker ready signal:
- on_worker_ready connects to the database but does not close the connection. Also, db.engine.connect() returns a connection object that is never used or closed. The intention was probably to "warm up" the pool, but this leaks a connection.

3. send_bulk_notifications:
- Calls send_push_notification DIRECTLY (not .delay()). This means notifications are sent synchronously inside the bulk task, losing all the benefits of task distribution, retries, and rate limiting on the individual task.
- The rate_limit='10/s' applies to the bulk task itself, not the individual notifications inside it.
- For a large user_ids list, this task runs for a very long time with no checkpointing. If the worker crashes, all progress is lost.

4. send_scheduled_notification:
- Marks notification.sent = True AFTER calling send_push_notification.delay(). But .delay() only enqueues the task -- it does not mean the notification was actually sent. If the push notification task fails later, sent=True is wrong.
- Race condition: two workers could both check notification.sent == False and both dispatch.

5. process_notification_batch:
- Dispatches all notifications in a loop, then marks batch as 'dispatched'. If the worker crashes mid-loop, some are dispatched but the batch is not marked, causing re-dispatch on retry (duplicate notifications).
- No limit on batch size. A batch with 1 million notifications queues 1 million tasks in a tight loop, potentially overwhelming the broker.

6. Configuration:
- broker_url uses guest:guest default credentials. These should be changed for production.
- result_backend = 'rpc://' uses an RPC-style result backend which creates a unique queue per result. This creates many short-lived queues in RabbitMQ, which can cause performance issues at scale.
- worker_concurrency=16 may be too high for I/O-bound tasks that make external API calls, or too low for CPU-bound tasks. Should be tuned based on workload.

7. Error handling:
- send_push_notification raises ValueError for unknown platform but has no retry for transient errors (network timeouts, service unavailability).
- No dead letter queue or failure tracking beyond email alerts.

Let me structure the review.
</think>

## Code Review: Celery Notification System

### CRITICAL - Direct Call Instead of .delay()

**DC1: send_bulk_notifications calls task synchronously (Severity: CRITICAL)**
```python
send_push_notification(user_id, message, get_platform(user_id))
```
This calls the task function directly, not via `.delay()`. All notifications are sent synchronously inside a single task, losing task distribution, individual retries, and rate limiting. For 10,000 users, this monopolizes one worker for the entire duration with no fault tolerance.

Fix: Use `.delay()` or `.apply_async()`:
```python
send_push_notification.delay(user_id, message, get_platform(user_id))
```
Or better, use a group for parallel execution with rate limiting.

### HIGH - Signal Handler Problems

**SH1: SMTP in failure signal blocks workers (Severity: HIGH)**
```python
@task_failure.connect
def on_task_failure(...):
    smtp = smtplib.SMTP('localhost')
    smtp.send_message(msg)
```
Sending email synchronously in a signal handler blocks the worker thread. If SMTP is slow or down, every task failure causes a delay. If the SMTP call itself fails, the unhandled exception in the signal causes unpredictable behavior.

Fix: Queue the alert as a separate task, or use a batched alerting system:
```python
@task_failure.connect
def on_task_failure(sender=None, **kwargs):
    send_alert_email.delay(sender.name, str(kwargs.get('exception')))
```

**SH2: Email flood on mass failures (Severity: HIGH)**
One email per failed task. If 1000 tasks fail simultaneously (e.g., downstream service outage), 1000 emails are sent. Use aggregation with a time window.

### HIGH - Premature Sent Flag

**PF1: Notification marked sent before delivery (Severity: HIGH)**
```python
send_push_notification.delay(...)
notification.sent = True
db.session.commit()
```
`.delay()` only enqueues the task. If the push notification task later fails (network error, invalid token), the notification is incorrectly marked as sent. Mark it as 'queued' and use a task callback to set 'sent' on success.

**PF2: Race condition on sent check (Severity: MEDIUM)**
Two workers could both check `notification.sent == False` simultaneously and both dispatch. Use `SELECT ... FOR UPDATE` or an atomic compare-and-set.

### HIGH - Batch Processing

**BP1: No batch size limit (Severity: HIGH)**
`process_notification_batch` dispatches all notifications in a tight loop. A batch with 1 million notifications queues 1 million tasks, potentially overwhelming the RabbitMQ broker. Add throttling:
```python
for i, notification in enumerate(notifications):
    send_push_notification.apply_async(
        args=[notification.user_id, notification.message, notification.platform],
        countdown=i * 0.01  # stagger delivery
    )
```

**BP2: No atomicity on batch status (Severity: MEDIUM)**
If the worker crashes mid-loop, some notifications are dispatched but the batch is not marked 'dispatched'. On retry, those notifications are sent again (duplicates).

### MEDIUM - Configuration

**CFG1: Default broker credentials (Severity: MEDIUM)**
`amqp://guest:guest@localhost` uses default RabbitMQ credentials that are well-known. Use environment variables with strong credentials.

**CFG2: RPC result backend scaling (Severity: MEDIUM)**
`result_backend = 'rpc://'` creates a unique queue per result in RabbitMQ. At high volume, this creates thousands of short-lived queues, degrading broker performance. Use Redis result backend instead.

### LOW - Resource Leak

**RL1: Worker ready signal leaks connection (Severity: LOW)**
```python
db.engine.connect()
```
Creates a database connection that is never closed or used. This was likely meant to warm up the pool, but the connection object must be explicitly closed.

### LOW - Missing Retry on Push Tasks

**MR1: send_push_notification has no retry (Severity: LOW)**
Network errors when calling APNS or FCM are not retried. Add `autoretry_for` for transient exceptions.'''),

    ("thinking/code-review", r'''Review this Celery configuration and worker code and identify issues:

```python
from celery import Celery
from celery.signals import celeryd_after_setup
from kombu import Exchange, Queue
import os

app = Celery('myapp')

app.conf.update(
    broker_url=os.environ.get('BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.environ.get('RESULT_BACKEND', 'redis://localhost:6379/1'),
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_max_tasks_per_child=1000,
    worker_max_memory_per_child=200000,
    broker_connection_retry_on_startup=True,
    result_expires=86400,
)

default_exchange = Exchange('default', type='direct')
priority_exchange = Exchange('priority', type='direct')

app.conf.task_queues = (
    Queue('default', default_exchange, routing_key='default'),
    Queue('priority', priority_exchange, routing_key='priority'),
    Queue('bulk', default_exchange, routing_key='bulk'),
)

app.conf.task_routes = {
    'myapp.tasks.send_email': {'queue': 'priority'},
    'myapp.tasks.send_notification': {'queue': 'priority'},
    'myapp.tasks.generate_report': {'queue': 'bulk'},
    'myapp.tasks.cleanup': {'queue': 'bulk'},
}

app.conf.task_annotations = {
    'myapp.tasks.send_email': {'rate_limit': '100/m'},
    'myapp.tasks.generate_report': {'rate_limit': '5/h'},
}

@app.task(bind=True, name='myapp.tasks.health_check')
def health_check(self):
    import psutil
    return {
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent': psutil.disk_usage('/').percent,
        'worker_id': self.request.hostname,
        'active_tasks': len(app.control.inspect().active() or {}),
    }

@app.task(bind=True, name='myapp.tasks.purge_results')
def purge_results(self):
    backend = app.backend
    if hasattr(backend, 'client'):
        keys = backend.client.keys('celery-task-meta-*')
        if keys:
            backend.client.delete(*keys)
            return {'purged': len(keys)}
    return {'purged': 0}

@app.task(bind=True, name='myapp.tasks.restart_workers')
def restart_workers(self):
    app.control.broadcast('shutdown')
    return {'status': 'restart_initiated'}

app.conf.beat_schedule = {
    'health-check': {
        'task': 'myapp.tasks.health_check',
        'schedule': 30.0,
    },
    'purge-old-results': {
        'task': 'myapp.tasks.purge_results',
        'schedule': 3600.0,
    },
}
```''', r'''<think>
Let me review this Celery configuration and worker management code.

1. Health check issues:
- health_check runs every 30 seconds via beat. The task calls `app.control.inspect().active()` which broadcasts a message to ALL workers and waits for responses. This is an expensive operation that creates network traffic proportional to the number of workers, every 30 seconds.
- The health check is a Celery task itself, so if workers are overloaded (which is what you want to detect), the health check task waits in the queue and gives stale results.
- psutil import inside the task is fine but adds a dependency.

2. purge_results is dangerous:
- Uses `backend.client.keys('celery-task-meta-*')` which is the Redis KEYS command. KEYS blocks the Redis server and scans the entire keyspace. On a Redis instance with millions of keys, this can block for seconds, causing cascading failures.
- There is already `result_expires=86400` configured, which handles cleanup automatically via TTL. This manual purge is redundant AND dangerous.
- Running every hour means it calls KEYS every hour.

3. restart_workers is extremely dangerous:
- `app.control.broadcast('shutdown')` shuts down ALL workers. This is exposed as a Celery task, which means it can be triggered by anything that can submit tasks. If there is no access control on the broker, anyone can shut down the entire cluster.
- The task itself runs on a worker that is about to be shut down. The result may never be stored.
- This does not actually restart workers -- it only shuts them down. Restart depends on a process supervisor (systemd, supervisord) being configured correctly.

4. Queue configuration:
- The 'bulk' queue uses `default_exchange`. This means 'default' and 'bulk' share the same exchange but different routing keys. This works but is confusing -- they could use the same queue config.
- No dead letter queue configured. Failed tasks that exceed max_retries are silently discarded.

5. Time limits:
- task_time_limit=3600 (1 hour) and task_soft_time_limit=3000 (50 min) are global defaults. The generate_report task in the 'bulk' queue with rate_limit='5/h' might need different time limits than send_email.
- 1 hour is a very long time limit for most tasks. If a task hangs, it blocks a worker slot for an hour.

6. Worker settings:
- worker_max_memory_per_child=200000 (200MB in KB). This kills workers that exceed 200MB, which might be too low for report generation tasks that handle large datasets.
- worker_max_tasks_per_child=1000 causes worker recycling every 1000 tasks, which helps with memory leaks but adds overhead.

7. Missing configuration:
- No broker_transport_options for visibility_timeout
- No task_default_queue set explicitly
- No task_create_missing_queues = False (default creates queues dynamically, which can mask routing errors)

Let me write the review.
</think>

## Code Review: Celery Configuration and Worker Management

### CRITICAL - Dangerous Operations

**DNG1: restart_workers can take down entire cluster (Severity: CRITICAL)**
```python
@app.task
def restart_workers(self):
    app.control.broadcast('shutdown')
```
This task shuts down ALL workers when executed. Since it is a normal Celery task, anyone with access to submit tasks to the broker can trigger a complete cluster shutdown. This is not a restart -- it only shuts down. Workers only come back if a process supervisor is configured.

Remove this task entirely or gate it behind a separate admin system with strong authentication. Worker management should never be a queued task.

**DNG2: purge_results uses Redis KEYS command (Severity: CRITICAL)**
```python
keys = backend.client.keys('celery-task-meta-*')
```
The Redis `KEYS` command scans the entire keyspace, blocking the Redis server for the duration. On a Redis instance with millions of keys, this blocks for seconds, causing timeouts for all other Redis clients (including the broker). This is a well-documented production killer.

Remove this task. The configured `result_expires=86400` already handles cleanup via TTL. If manual cleanup is needed, use `SCAN` iteratively:
```python
cursor = 0
while True:
    cursor, keys = backend.client.scan(cursor, match='celery-task-meta-*', count=100)
    if keys:
        backend.client.delete(*keys)
    if cursor == 0:
        break
```

### HIGH - Health Check Design

**HC1: Expensive inspect call every 30 seconds (Severity: HIGH)**
```python
app.control.inspect().active()
```
This broadcasts a control message to all workers and waits for responses. With 50 workers, that is 50 control messages and responses every 30 seconds. This creates significant overhead and the results are unreliable because the health check task itself runs on a (possibly overloaded) worker.

Fix: Use an external monitoring tool (Flower, Prometheus with celery-exporter) instead of self-monitoring via tasks. For basic health, check the broker connection directly:
```python
@app.task(bind=True)
def health_check(self):
    return {
        'worker_id': self.request.hostname,
        'timestamp': time.time(),
    }
```

### MEDIUM - Queue Configuration

**QC1: No dead letter queue (Severity: MEDIUM)**
Tasks that fail after exhausting retries are silently discarded. Configure a dead letter queue to capture failed tasks for investigation:
```python
dead_letter_exchange = Exchange('dead-letter', type='direct')
Queue('dead-letter', dead_letter_exchange, routing_key='dead-letter')
```

**QC2: Missing task_create_missing_queues = False (Severity: MEDIUM)**
The default `task_create_missing_queues=True` means a typo in routing configuration silently creates a new queue that no worker consumes from. Tasks accumulate in the phantom queue with no errors. Set to False to catch routing errors immediately.

**QC3: No default queue specified (Severity: LOW)**
Tasks not matching any route go to the Celery default queue, but no worker may be consuming that specific queue name. Set `task_default_queue = 'default'` explicitly.

### MEDIUM - Time Limits

**TL1: One-hour global time limit is excessive (Severity: MEDIUM)**
`task_time_limit=3600` means a hung task blocks a worker slot for an hour. Most tasks (email, notification) should complete in seconds. Set short global defaults and override per-task:
```python
app.conf.task_time_limit = 300  # 5 min default
app.conf.task_annotations = {
    'myapp.tasks.generate_report': {'time_limit': 3600},
}
```

### LOW - Worker Memory

**WM1: 200MB memory limit may be too low (Severity: LOW)**
`worker_max_memory_per_child=200000` kills workers exceeding 200MB. Report generation tasks processing large datasets may routinely exceed this. Monitor actual memory usage before setting this limit.

### Configuration Improvements

```python
app.conf.update(
    task_create_missing_queues=False,
    task_default_queue='default',
    broker_transport_options={
        'visibility_timeout': 43200,
    },
    task_time_limit=300,
    task_soft_time_limit=240,
)
```'''),

    ("thinking/code-review", r'''Review this Celery code and identify issues:

```python
from celery import Celery, states
from celery.result import AsyncResult
from celery.exceptions import Ignore
import json
import time
from typing import Any, Dict, List

app = Celery('processor')

class TaskProgressMixin:
    def update_progress(self, current, total, status=''):
        self.update_state(
            state='PROGRESS',
            meta={'current': current, 'total': total, 'status': status}
        )

@app.task(bind=True, base=TaskProgressMixin)
def process_large_dataset(self, dataset_id: int, options: dict):
    from app.models import Dataset, ProcessedRecord
    from app import db

    dataset = Dataset.query.get(dataset_id)
    records = dataset.records.all()
    total = len(records)

    results = []
    for i, record in enumerate(records):
        processed = transform_record(record, options)
        results.append(processed)
        if i % 100 == 0:
            self.update_progress(i, total, f'Processing record {i}')

    # Bulk insert results
    for result in results:
        db.session.add(ProcessedRecord(**result))
    db.session.commit()

    self.update_progress(total, total, 'Complete')
    return {'processed': total, 'dataset_id': dataset_id}

@app.task(bind=True)
def chained_processor(self, data: dict, step: int = 1):
    if step == 1:
        result = validate_data(data)
        chained_processor.delay(result, step=2)
    elif step == 2:
        result = enrich_data(data)
        chained_processor.delay(result, step=3)
    elif step == 3:
        result = store_data(data)
        return result

@app.task(bind=True, max_retries=3)
def resilient_api_call(self, endpoint: str, payload: dict):
    import requests
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        self.retry(countdown=60)
    except requests.ConnectionError:
        self.retry(countdown=30)
    except requests.HTTPError as exc:
        if exc.response.status_code == 429:
            retry_after = int(exc.response.headers.get('Retry-After', 60))
            self.retry(countdown=retry_after)
        elif exc.response.status_code >= 500:
            self.retry(countdown=120)
        else:
            raise

def get_task_progress(task_id: str) -> Dict[str, Any]:
    result = AsyncResult(task_id)
    if result.state == 'PROGRESS':
        return result.info
    elif result.state == 'SUCCESS':
        return {'current': 100, 'total': 100, 'status': 'Complete', 'result': result.result}
    elif result.state == 'FAILURE':
        return {'status': 'Failed', 'error': str(result.result)}
    else:
        return {'status': result.state}

@app.task
def fire_and_forget(data: dict):
    process_data(data)

app.conf.update(
    task_ignore_result=True,
)
```''', r'''<think>
Let me review this Celery task code for design patterns, error handling, and anti-patterns.

1. process_large_dataset:
- Loads all records into memory with dataset.records.all(), then len(records) evaluates the entire queryset. For a large dataset with millions of records, this consumes excessive memory.
- All results are accumulated in a list, then bulk inserted one at a time (db.session.add in a loop, not bulk insert). This is slow and memory-intensive.
- No error handling. If transform_record fails on record 500 of 1000, all progress is lost.
- No checkpointing. If the worker crashes at 90% completion, everything starts over.

2. TaskProgressMixin:
- This mixin pattern works but has a subtle issue: update_state requires the task to have a result backend. But the global config sets task_ignore_result=True. When results are ignored, update_state/update_progress silently does nothing, and get_task_progress will always return PENDING state.

3. chained_processor:
- Implements a state machine by recursively calling itself with a step number. This is an anti-pattern because:
  - Task IDs change at each step, making it impossible to track the overall chain
  - If step 2 fails and retries, the original caller has no visibility
  - The chain is not composable or reusable
- Should use Celery's built-in chain primitive instead.

4. resilient_api_call:
- Good pattern for retry on different HTTP errors. But max_retries=3 and the retry does not pass the exception. Should pass exc=exc for proper traceback.
- After max_retries, Timeout and ConnectionError retries will raise MaxRetriesExceededError instead of the original exception. Should re-raise explicitly.

5. fire_and_forget with task_ignore_result=True:
- The global task_ignore_result=True means ALL tasks ignore results, including process_large_dataset which uses update_state for progress tracking. This breaks the progress feature completely.
- If only fire_and_forget should ignore results, set it per-task: @app.task(ignore_result=True).

6. get_task_progress:
- str(result.result) on failure exposes the exception object. If the exception contains sensitive data (database errors, API keys in URLs), this leaks information.
- Does not handle REVOKED state.

Let me structure this.
</think>

## Code Review: Celery Task Patterns

### CRITICAL - Global Config Breaks Progress Tracking

**CFG1: task_ignore_result=True disables progress (Severity: CRITICAL)**
```python
app.conf.update(task_ignore_result=True)
```
This global setting means ALL tasks ignore results, including `process_large_dataset` which uses `update_state` for progress tracking. With results ignored, `update_state` is silently discarded and `get_task_progress` always returns PENDING. The progress feature is completely broken.

Fix: Set per-task, not globally:
```python
@app.task(ignore_result=True)
def fire_and_forget(data):
    process_data(data)

@app.task(bind=True, base=TaskProgressMixin, ignore_result=False)
def process_large_dataset(self, dataset_id, options):
    ...
```

### HIGH - Memory Issues

**MEM1: process_large_dataset loads all records into memory (Severity: HIGH)**
```python
records = dataset.records.all()
total = len(records)
```
For a million-record dataset, this loads all records plus all result objects into memory. Use streaming:
```python
total = dataset.records.count()
for i, record in enumerate(dataset.records.yield_per(1000)):
    processed = transform_record(record, options)
    db.session.add(ProcessedRecord(**processed))
    if i % 1000 == 0:
        db.session.flush()
        self.update_progress(i, total)
db.session.commit()
```

**MEM2: Results accumulated in list then inserted one-by-one (Severity: HIGH)**
All processed results are stored in a Python list, then inserted via individual `db.session.add()` calls. Use `db.session.bulk_insert_mappings(ProcessedRecord, results)` for bulk insertion, and flush in batches to limit memory usage.

### HIGH - No Fault Tolerance

**FT1: No checkpointing in process_large_dataset (Severity: HIGH)**
If the worker crashes at record 999,999 of 1,000,000, all progress is lost. Implement checkpointing by tracking the last processed record ID and resuming from there on retry.

**FT2: No error handling for individual records (Severity: HIGH)**
If `transform_record` raises an exception on one record, the entire task fails. Consider catching per-record errors and continuing:
```python
for i, record in enumerate(records):
    try:
        processed = transform_record(record, options)
        results.append(processed)
    except Exception as e:
        errors.append({'record_id': record.id, 'error': str(e)})
```

### HIGH - Anti-Pattern

**AP1: chained_processor reimplements Celery chains poorly (Severity: HIGH)**
Self-calling with step numbers is an anti-pattern:
- Each step gets a new task ID, breaking traceability
- No overall success/failure tracking
- Not composable with other tasks

Use Celery's chain primitive:
```python
from celery import chain

pipeline = chain(
    validate_data_task.s(data),
    enrich_data_task.s(),
    store_data_task.s(),
)
pipeline.apply_async()
```

### MEDIUM - Retry Improvements

**RT1: Retry does not preserve original exception (Severity: MEDIUM)**
```python
except requests.Timeout:
    self.retry(countdown=60)
```
Without `exc=exc`, the retry raises `MaxRetriesExceededError` after exhausting retries instead of the original Timeout. Pass the exception:
```python
except requests.Timeout as exc:
    self.retry(exc=exc, countdown=60)
```

### LOW - Progress Reporting

**PR1: get_task_progress may leak sensitive errors (Severity: LOW)**
`str(result.result)` on FAILURE can expose exception details containing database connection strings, file paths, or API keys. Sanitize error messages before exposing.

**PR2: Missing REVOKED state handling (Severity: LOW)**
`get_task_progress` does not handle the REVOKED state, which occurs when tasks are cancelled.'''),
]
