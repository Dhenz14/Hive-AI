"""
Real-world project help training pairs - MVP startup and project bootstrapping
"""

pairs = [
    {
        "instruction": r'''I'm building a SaaS app for small restaurants to manage online orders. I need to get an MVP out in 6 weeks. My background is mostly Python/Django but I've heard FastAPI is better for APIs. The frontend will be React. What tech stack should I go with and how should I structure the project?''',
        "output": r'''<think>
They need to ship fast, they know Django, and the product is a standard CRUD-heavy SaaS. Let me think about what actually matters for a 6-week MVP timeline.

Django vs FastAPI: Django has admin panel, ORM, auth, sessions built in. FastAPI is faster for pure APIs but they'd need to wire up everything themselves. For a 6-week MVP with order management, Django wins on speed-to-ship.

They mentioned React frontend -- so Django REST Framework for the API layer makes sense. Django serves the API, React is a separate SPA.
</think>

Stick with Django. Here's why: you know it, and for a CRUD-heavy ordering system, Django's admin panel alone saves you 1-2 weeks. You can use it internally to manage restaurants while the React frontend handles customer-facing ordering.

Recommended stack:
- Django 5 + Django REST Framework for the API
- PostgreSQL (you'll want relational integrity for orders/payments)
- React frontend as a separate app (Vite for build tooling)
- Redis for order queue / real-time updates later
- Stripe for payments (don't build billing yourself)

Project structure:

```
restaurant-orders/
  backend/
    manage.py
    config/           # settings, urls, wsgi
    apps/
      restaurants/    # Restaurant model, menu items
      orders/         # Order model, order items, status tracking
      accounts/       # Custom user model, auth
    requirements/
      base.txt
      dev.txt
      prod.txt
  frontend/
    src/
      components/
      pages/
      api/            # API client functions
      hooks/
  docker-compose.yml  # Postgres + Redis + backend + frontend
```

Week-by-week rough plan:
1. Models + admin panel + basic API endpoints
2. Auth (django-allauth) + restaurant onboarding
3. Menu management API + React menu pages
4. Order placement flow + Stripe checkout
5. Order status tracking + restaurant dashboard
6. Testing, deploy to Railway/Render, bug fixes

One critical decision: use a custom User model from day one. Changing it later in Django is painful. Add this before your first migration:

```python
# apps/accounts/models.py
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    is_restaurant_owner = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
```

Don't optimize for scale yet. Django on a single $20/month server handles thousands of orders per day easily.'''
    },
    {
        "instruction": r'''I'm starting a new project -- a CLI tool that fetches data from multiple cloud providers (AWS, GCP, Azure) and generates a unified cost report. I want it in Python. What's the right way to structure this so it's extensible when I add more providers later?''',
        "output": r'''The key pattern here is a provider plugin architecture. Define a base class that each cloud provider implements, then discover/load them dynamically.

```python
# src/cloud_cost/providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

@dataclass
class CostEntry:
    provider: str
    service: str
    amount: float
    currency: str
    date: date
    tags: dict

class CloudProvider(ABC):
    @abstractmethod
    def authenticate(self, config: dict) -> None:
        ...

    @abstractmethod
    def fetch_costs(self, start: date, end: date) -> list[CostEntry]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
```

Then each provider gets its own module:

```python
# src/cloud_cost/providers/aws.py
import boto3
from .base import CloudProvider, CostEntry

class AWSProvider(CloudProvider):
    name = "aws"

    def authenticate(self, config):
        self.client = boto3.client(
            "ce",
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
        )

    def fetch_costs(self, start, end):
        resp = self.client.get_cost_and_usage(
            TimePeriod={"Start": str(start), "End": str(end)},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        # ... parse response into CostEntry objects
```

Project layout:

```
cloud-cost-report/
  src/cloud_cost/
    __init__.py
    cli.py              # click or typer CLI
    config.py            # YAML config loader
    providers/
      __init__.py        # provider registry
      base.py
      aws.py
      gcp.py
      azure.py
    reports/
      __init__.py
      csv_report.py
      html_report.py
  tests/
  pyproject.toml
```

For the registry, keep it simple -- don't over-engineer with entry_points yet:

```python
# src/cloud_cost/providers/__init__.py
from .aws import AWSProvider
from .gcp import GCPProvider
from .azure import AzureProvider

PROVIDERS = {p.name: p for p in [AWSProvider, GCPProvider, AzureProvider]}

def get_provider(name):
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDERS)}")
    return PROVIDERS[name]()
```

Use `typer` for the CLI and `pyyaml` for config. Start with CSV output, add HTML later.'''
    },
    {
        "instruction": r'''I need to build the first API endpoints for a job board. I have a FastAPI project set up with SQLAlchemy and Postgres. What should my first endpoints look like? I want companies to post jobs and candidates to browse/apply. Show me the job posting endpoints to start with.''',
        "output": r'''<think>
Job board MVP -- the core resource is a Job posting. Companies create them, candidates read them. Let me focus on the CRUD for jobs since that's the foundation everything else builds on.

Key decisions:
- Jobs need a status (draft/active/closed) so companies can prepare postings
- Pagination is essential from day one -- job boards get big fast
- Filtering by location/type is table stakes
</think>

Here are the job posting endpoints. I'm assuming you have a basic SQLAlchemy setup already.

```python
# models/job.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
import enum
from db.base import Base

class JobStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    closed = "closed"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(100))
    job_type = Column(String(20))  # full-time, part-time, contract
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    status = Column(Enum(JobStatus), default=JobStatus.draft)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
```

```python
# schemas/job.py
from pydantic import BaseModel, Field

class JobCreate(BaseModel):
    title: str = Field(max_length=200)
    description: str
    location: str | None = None
    job_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None

class JobResponse(JobCreate):
    id: int
    company_id: int
    status: str
    created_at: str

    class Config:
        from_attributes = True

class JobList(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
```

```python
# routes/jobs.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("/", response_model=JobList)
def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    location: str | None = None,
    job_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Job).filter(Job.status == JobStatus.active)
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if job_type:
        query = query.filter(Job.job_type == job_type)

    total = query.count()
    jobs = query.offset((page - 1) * per_page).limit(per_page).all()
    return JobList(jobs=jobs, total=total, page=page)

@router.post("/", response_model=JobResponse, status_code=201)
def create_job(
    job_in: JobCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_company_user),
):
    job = Job(**job_in.model_dump(), company_id=current_user.company_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

@router.patch("/{job_id}/publish")
def publish_job(job_id: int, db: Session = Depends(get_db),
                current_user=Depends(get_current_company_user)):
    job = db.query(Job).filter(Job.id == job_id,
                                Job.company_id == current_user.company_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = JobStatus.active
    db.commit()
    return {"status": "published"}
```

Build these first, then add the application endpoints next. The browse/search endpoint is already here -- candidates just hit GET /api/jobs with filters.'''
    },
    {
        "instruction": r'''I'm a solo dev building a personal finance tracker as a side project. I want to use it myself but maybe open-source it later. Should I use a monorepo or separate repos for frontend and backend? And what's the simplest deploy setup?''',
        "output": r'''Monorepo, no question. For a solo dev side project, separate repos add overhead with zero benefit. You'll be switching between frontend and backend constantly, and having them in one repo means one PR covers a full feature.

```
finance-tracker/
  backend/
    app/
      main.py
      models/
      routes/
      services/
    requirements.txt
    Dockerfile
  frontend/
    src/
    package.json
    Dockerfile
  docker-compose.yml
  .github/workflows/deploy.yml
  README.md
```

For deploy, the simplest setup that's actually production-ready:

Option A -- Cheapest: Railway or Render
- Push to main -> auto-deploy
- Managed Postgres included
- Free tier works for personal use
- Total cost: $0-7/month

Option B -- More control: A single VPS (Hetzner, $5/month)
- docker-compose up on the server
- Caddy as reverse proxy (auto HTTPS)
- Simple deploy script:

```bash
#!/bin/bash
# deploy.sh
ssh fintrack "cd /opt/finance-tracker && git pull && docker compose up -d --build"
```

Your docker-compose.yml:

```yaml
services:
  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/finance
    ports:
      - "8000:8000"
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=localdevpassword
volumes:
  pgdata:
```

I'd go with Option A (Railway) to start. You can always move to a VPS later when you want more control. Don't set up Kubernetes, don't set up Terraform -- that's all yak-shaving for a side project.

One tip: use SQLite for local dev and Postgres for prod. It removes the "need Docker running to develop" friction that kills side projects.'''
    },
    {
        "instruction": r'''I want to build a real-time chat feature for my existing Django app. Users are already authenticated. What's the quickest path to get basic 1-on-1 messaging working? I don't want to rewrite anything in Node.''',
        "output": r'''<think>
Django + real-time chat. The standard answer is Django Channels with WebSockets. They already have Django with auth, so Channels can piggyback on that. Let me give them the minimal setup.

Key pieces:
1. Django Channels + Daphne (ASGI server)
2. Redis as the channel layer (message broker)
3. A simple Message model for persistence
4. WebSocket consumer for real-time delivery
</think>

Use Django Channels. It adds WebSocket support to Django without leaving the ecosystem, and it reuses your existing auth.

Install and configure:

```bash
pip install channels channels-redis daphne
```

```python
# settings.py
INSTALLED_APPS = [
    "daphne",  # must be before django.contrib.staticfiles
    # ... your existing apps
    "channels",
    "chat",
]

ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [("127.0.0.1", 6379)]},
    },
}
```

```python
# config/asgi.py
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from chat.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
```

```python
# chat/models.py
from django.db import models
from django.conf import settings

class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL,
                               on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL,
                                  on_delete=models.CASCADE, related_name="received_messages")
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["timestamp"]
```

```python
# chat/consumers.py
import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
            return
        self.room_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

    async def receive_json(self, data):
        msg = await self.save_message(data["recipient_id"], data["content"])
        recipient_room = f"user_{data['recipient_id']}"
        await self.channel_layer.group_send(recipient_room, {
            "type": "chat.message",
            "message": {"sender_id": self.user.id, "content": data["content"],
                        "timestamp": str(msg.timestamp)},
        })

    async def chat_message(self, event):
        await self.send_json(event["message"])

    @database_sync_to_async
    def save_message(self, recipient_id, content):
        return Message.objects.create(
            sender=self.user, recipient_id=recipient_id, content=content
        )
```

Run with `daphne config.asgi:application` instead of `gunicorn` in production. The frontend connects via `new WebSocket("ws://yoursite/ws/chat/")` and sends JSON. This handles the real-time part; add a REST endpoint to load message history on page load.'''
    },
]
