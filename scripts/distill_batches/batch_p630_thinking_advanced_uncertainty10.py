"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 10)"""

PAIRS = [
    (
        "thinking/uncertainty-spa-vs-ssr-vs-mpa",
        "We're starting a new web project — an internal tool for our 50-person company. Should we build it as a SPA (React), SSR (Next.js), or a traditional server-rendered MPA (Django templates)? The team knows Django well.",
        r'''<think>
SPA vs SSR vs MPA for an internal tool with a Django-experienced team. Let me think carefully.

**Context factors:**
- Internal tool (not public-facing)
- 50 users (not millions)
- Team knows Django
- "Starting new"

**SPA (React/Vue):**
- Rich, interactive UI
- Best for complex interactive features (drag-drop, real-time updates)
- Requires: building an API, learning React, managing frontend state
- For 50 users of an internal tool: overkill

**SSR (Next.js):**
- Good SEO (irrelevant for internal tool)
- Good initial load time (irrelevant for 50 users)
- Requires: learning Next.js, running Node.js alongside Django
- Adds complexity without solving a problem for this use case

**MPA (Django templates):**
- Team already knows it
- Simple: HTML rendered on server, full page reloads
- Fast to build — Django admin alone might cover many needs
- For complex interactivity, can add HTMX or Alpine.js
- 50 internal users don't need a SPA experience

**My assessment:**
- 75% Django templates + HTMX for interactivity
- 15% SPA (if the tool needs very complex interactive UI — dashboards, kanban boards, etc.)
- 10% Next.js/SSR (no clear advantage for this use case)

The team knows Django. The users are internal. The fastest path to value is Django templates, possibly enhanced with HTMX for dynamic interactions.
</think>

For an internal tool with a Django-skilled team: **Django templates (MPA)** — confidence: **75%**.

## Why MPA Wins for This Use Case

```
YOUR SITUATION:
  ✓ Internal tool (no SEO, no public traffic)
  ✓ 50 users (not performance-critical)
  ✓ Team knows Django (no learning curve)
  ✓ Starting new (can choose the simplest approach)

WHAT EACH APPROACH COSTS:

Django templates (MPA):
  Learning curve:     0 (team knows it)
  Setup time:         1 day
  API needed:         No (templates render data directly)
  Deployment:         1 server, 1 process
  Interactivity:      HTMX or Alpine.js for dynamic parts
  Time to first feature: 1-2 days

React SPA:
  Learning curve:     2-4 weeks (React, state management, API design)
  Setup time:         1 week (create-react-app, API, auth integration)
  API needed:         Yes (build a REST/GraphQL API for React to consume)
  Deployment:         2 deployments (API + frontend)
  Time to first feature: 2-3 weeks

Next.js SSR:
  Learning curve:     2-4 weeks (Next.js, React, API routes)
  Setup time:         1 week
  API needed:         Partial (API routes in Next.js, but still need Django for logic)
  Deployment:         2 servers (Next.js + Django API)
  Time to first feature: 2-3 weeks
```

## Django Templates + HTMX (The Sweet Spot)

```python
# Django template — no JavaScript framework needed
# views.py
def dashboard(request):
    tasks = Task.objects.filter(assigned_to=request.user)
    return render(request, "dashboard.html", {"tasks": tasks})

# dashboard.html — plain HTML, enhanced with HTMX for interactivity
{% extends "base.html" %}
{% block content %}
<h1>Dashboard</h1>

<!-- HTMX: mark task complete without page reload -->
<ul>
{% for task in tasks %}
  <li id="task-{{ task.id }}">
    {{ task.title }}
    <button hx-post="/tasks/{{ task.id }}/complete/"
            hx-target="#task-{{ task.id }}"
            hx-swap="outerHTML">
      ✓ Complete
    </button>
  </li>
{% endfor %}
</ul>

<!-- HTMX: search with live results -->
<input type="search"
       hx-get="/tasks/search/"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#search-results"
       placeholder="Search tasks...">
<div id="search-results"></div>

{% endblock %}
```

```
HTMX gives you SPA-like interactions without:
  - A JavaScript framework
  - An API layer
  - Client-side state management
  - A separate build step
  - Learning React/Vue/Svelte

You get: dynamic updates, live search, form submissions without
page reload — all with HTML attributes on your Django templates.
```

## When I'd Change My Mind (The 25%)

```
Choose SPA (React/Vue) if:
  ✓ Complex real-time interactions (kanban board, drag-drop, live collaboration)
  ✓ Offline support needed (service workers, local storage)
  ✓ The tool is more like an "app" than a "website"
  ✓ Heavy client-side computation (data visualization, spreadsheet-like UI)
  ✓ You're building a design tool, IDE, or rich editor

Choose Next.js SSR if:
  ✓ Public-facing with SEO requirements
  ✓ Team already knows React/Next.js better than Django
  ✓ Need both static and dynamic pages

Stick with Django MPA if:
  ✓ CRUD operations (forms, lists, detail views)
  ✓ Admin dashboards with charts and tables
  ✓ Report generation
  ✓ Internal workflows (approvals, ticketing, tracking)
  → This covers 90% of internal tools
```

## The Django Admin Shortcut

```python
# For an internal tool, Django Admin might be ALL you need:

from django.contrib import admin

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'assigned_to', 'status', 'due_date']
    list_filter = ['status', 'assigned_to']
    search_fields = ['title', 'description']
    list_editable = ['status']
    date_hierarchy = 'created_at'
    actions = ['mark_complete']

    @admin.action(description="Mark selected tasks as complete")
    def mark_complete(self, request, queryset):
        queryset.update(status='complete')

# This gives you: CRUD, search, filtering, bulk actions, user management
# in about 20 lines of code. No frontend needed.
# Customize with django-unfold or django-jazzmin for better UI.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
