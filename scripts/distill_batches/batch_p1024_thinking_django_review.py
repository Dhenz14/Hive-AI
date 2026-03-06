r"""Thinking-trace pairs: Django code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Django code and identify issues:

```python
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bio = models.TextField()
    avatar_url = models.URLField()
    follower_count = models.IntegerField(default=0)
    following_count = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)

class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    likes_count = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)
    tags = models.CharField(max_length=500)  # comma separated

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey('self', null=True, on_delete=models.CASCADE)

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created = models.DateTimeField(auto_now_add=True)
```''', r'''<think>
Let me review these Django models for design issues, missing constraints, and performance problems.

Starting with Profile -- it uses ForeignKey to User. At first glance that could be intentional for a multi-profile system... but wait, this is clearly a social media app with a single bio and avatar per user. ForeignKey allows multiple Profile rows per User, which is almost certainly a bug. Should be OneToOneField. Hmm, also no related_name, so Django auto-generates `profile_set` instead of a clean `profile` accessor.

The follower_count and following_count fields on Profile are interesting. I considered whether these might be acceptable denormalization for read performance... but actually, without signals or triggers to keep them in sync with the Follow table, they will inevitably drift. Every code path that creates or deletes a Follow must manually update these counters -- that is a guaranteed source of bugs since developers will forget.

Now the Post model -- tags stored as a comma-separated CharField. Could this be a pragmatic choice for simplicity? No, wait, this is a classic antipattern because you cannot index individual tags, enforce referential integrity, or query without LIKE. Should be a ManyToManyField or django-taggit. Also likes_count has the same denormalization risk as the profile counters. And view_count as IntegerField will cause write contention under high traffic since every page view triggers an UPDATE on the same row.

For Comment, the parent FK uses on_delete=CASCADE. I initially thought that might be fine for threaded comments... but actually, deleting a parent comment wipes out the entire reply chain, which is rarely the desired UX. SET_NULL would preserve replies as orphaned comments. No ordering defined either, so comments come back in arbitrary order.

The Like model is missing a unique_together on (user, post). Without it, a user can like the same post unlimited times -- that is a data integrity hole, not a feature. Similarly, Follow has no unique constraint on (follower, following) and no CheckConstraint preventing self-follows (follower == following).

General issues across all models: no __str__ methods (admin shows "Post object (1)"), no Meta classes with indexes or ordering, and missing related_name on most ForeignKeys which leads to confusing auto-generated reverse accessors. Let me structure this review by severity.
</think>

## Code Review: Django Social Media Models

### CRITICAL - Data Integrity

**DI1: Profile uses ForeignKey instead of OneToOneField (Severity: CRITICAL)**
`ForeignKey(User)` allows multiple Profile rows per user. This is almost certainly a bug. Use `OneToOneField(User, on_delete=models.CASCADE, related_name='profile')`.

**DI2: Like model has no unique constraint (Severity: CRITICAL)**
Without `unique_together = ('user', 'post')`, a user can like the same post an unlimited number of times. Add a Meta constraint:
```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=['user', 'post'], name='unique_user_post_like')
    ]
```

**DI3: Follow model has no unique constraint (Severity: CRITICAL)**
Same issue -- a user can follow another user multiple times. Also, there is no constraint preventing self-follows.

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=['follower', 'following'], name='unique_follow'),
        models.CheckConstraint(
            check=~models.Q(follower=models.F('following')),
            name='no_self_follow'
        ),
    ]
```

### HIGH - Denormalization Risks

**DN1: Counters will desynchronize (Severity: HIGH)**
`follower_count`, `following_count`, `likes_count`, and `view_count` are denormalized counters with no mechanism to keep them in sync with the source tables. Every code path that creates/deletes a Like or Follow must remember to update these counters -- a guaranteed source of bugs.

Options: (a) Remove them and use annotations (`Count`) in queries, (b) add post_save/post_delete signals with F() expressions, or (c) use periodic reconciliation tasks.

### HIGH - Schema Design

**SD1: Tags as comma-separated string (Severity: HIGH)**
`tags = models.CharField(max_length=500)` storing comma-separated values is a well-known antipattern. You cannot index individual tags, enforce referential integrity, or query efficiently (requires LIKE queries). Use a separate Tag model with ManyToManyField or django-taggit.

**SD2: Comment parent cascade deletes replies (Severity: MEDIUM)**
`on_delete=models.CASCADE` on the parent FK means deleting a comment removes all its replies. Consider `on_delete=models.SET_NULL` with `null=True, blank=True` so replies remain visible as orphaned comments.

### MEDIUM - Performance

**P1: No database indexes (Severity: MEDIUM)**
No `db_index=True` or Meta indexes defined. Common query patterns (posts by author, posts by date, comments by post) will do full table scans. Add indexes:
```python
class Meta:
    indexes = [
        models.Index(fields=['author', '-created']),
        models.Index(fields=['-created']),
    ]
```

**P2: view_count update contention (Severity: MEDIUM)**
Incrementing `view_count` on every page view creates write contention on the Post row. Use `F('view_count') + 1` at minimum, or move analytics to a separate system.

### LOW - Code Quality

**CQ1: No __str__ methods**
All models lack `__str__`. The Django admin will display "Post object (1)" instead of meaningful identifiers.

**CQ2: Missing related_name on ForeignKeys**
Post.author, Comment.author, Comment.post, Like.user, Like.post all lack explicit `related_name`, leading to confusing auto-generated names.

**CQ3: No default ordering**
Models lack `class Meta: ordering = [...]`. Query results come in arbitrary order unless explicitly ordered in every query.'''),

    ("thinking/code-review", r'''Review this Django view code and identify issues:

```python
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from .models import Post, Comment, Like
import json

def post_list(request):
    posts = Post.objects.all()
    for post in posts:
        post.comment_count = Comment.objects.filter(post=post).count()
        post.author_name = post.author.username
        post.author_avatar = post.author.profile.avatar_url
    return render(request, 'posts/list.html', {'posts': posts})

def post_detail(request, post_id):
    post = Post.objects.get(id=post_id)
    comments = Comment.objects.filter(post=post)
    post.view_count += 1
    post.save()
    return render(request, 'posts/detail.html', {
        'post': post,
        'comments': comments,
    })

@login_required
def create_post(request):
    if request.method == 'POST':
        title = request.POST['title']
        body = request.POST['body']
        tags = request.POST['tags']
        post = Post(author=request.user, title=title, body=body, tags=tags)
        post.save()
        return redirect('/posts/')
    return render(request, 'posts/create.html')

@login_required
def delete_post(request, post_id):
    post = Post.objects.get(id=post_id)
    post.delete()
    return redirect('/posts/')

@login_required
def like_post(request, post_id):
    post = Post.objects.get(id=post_id)
    Like.objects.create(user=request.user, post=post)
    post.likes_count += 1
    post.save()
    return JsonResponse({'likes': post.likes_count})

class CommentView(View):
    def post(self, request, post_id):
        data = json.loads(request.body)
        post = Post.objects.get(id=post_id)
        comment = Comment.objects.create(
            post=post,
            author=request.user,
            body=data['body'],
            parent_id=data.get('parent_id')
        )
        return JsonResponse({
            'id': comment.id,
            'body': comment.body,
            'author': comment.author.username,
        })

    def delete(self, request, post_id, comment_id):
        comment = Comment.objects.get(id=comment_id)
        comment.delete()
        return JsonResponse({'deleted': True})
```''', r'''<think>
Let me review these Django views systematically. The first thing that jumps out is post_list.

Looking at post_list -- it does `Post.objects.all()` then loops over each post calling `Comment.objects.filter(post=post).count()`, accessing `post.author.username`, and `post.author.profile.avatar_url`. That could be fine for a small dataset... but wait, each of those is a separate query per post. That is 3N+1 queries. With 100 posts, we are hitting the database 301 times. This is textbook N+1 and should use select_related plus annotate.

Now for security -- delete_post catches my eye. It has @login_required, so I initially thought it might be okay... but actually there is no authorization check at all. Any logged-in user can delete any other user's post. That is a privilege escalation vulnerability. CommentView.delete has the same problem. And hmm, CommentView.post does not even have LoginRequiredMixin, so anonymous users can create comments.

I considered whether delete_post accepting GET requests might be intentional for some AJAX workflow, but no -- destructive actions must never respond to GET. A prefetching browser or a simple <img> tag could trigger deletion.

The error handling is concerning too. Every Post.objects.get(id=post_id) call will raise DoesNotExist for invalid IDs, returning a raw 500 error instead of 404. Should be get_object_or_404. Similarly, json.loads(request.body) can raise JSONDecodeError and request.POST['title'] raises KeyError if the field is missing.

For data integrity, post_detail does `post.view_count += 1; post.save()`. I first thought this might be acceptable for low-traffic views... but actually it is a classic race condition. Two simultaneous requests read the same count N, both write N+1 instead of N+2. Must use F('view_count') + 1. The same problem exists in like_post. Also, post.save() saves ALL fields, potentially overwriting concurrent edits to title or body since there is no update_fields restriction.

Other issues: hardcoded '/posts/' URLs instead of reverse(), no pagination, no CSRF handling for JSON endpoints, and no Django Form class for create_post.
</think>

## Code Review: Django Views

### CRITICAL - N+1 Query Problem

**Q1: post_list has 3N+1 queries (Severity: CRITICAL)**
For N posts, this view executes:
- 1 query for all posts
- N queries for `Comment.objects.filter(post=post).count()`
- N queries for `post.author.username` (lazy load)
- N queries for `post.author.profile.avatar_url` (lazy load)

With 100 posts, this fires 301 database queries. Fix with select_related and annotate:

```python
from django.db.models import Count

def post_list(request):
    posts = Post.objects.select_related(
        'author', 'author__profile'
    ).annotate(
        comment_count=Count('comment')
    ).order_by('-created')
    return render(request, 'posts/list.html', {'posts': posts})
```

### CRITICAL - Authorization

**A1: delete_post has no ownership check (Severity: CRITICAL)**
Any logged-in user can delete any post. This is a privilege escalation vulnerability:
```python
if post.author != request.user:
    return HttpResponseForbidden()
```

**A2: CommentView.delete has no ownership check (Severity: CRITICAL)**
Same problem -- any user can delete any comment.

**A3: CommentView.post requires no authentication (Severity: HIGH)**
The class-based view has no `LoginRequiredMixin`. Anonymous users can create comments. Add `LoginRequiredMixin` as the first parent class.

**A4: delete_post allows GET requests (Severity: HIGH)**
Destructive actions must not be triggered by GET requests. A simple link or image tag can trigger deletion. Check `request.method == 'POST'` or use `@require_POST`.

### HIGH - Race Conditions

**RC1: view_count increment is not atomic (Severity: HIGH)**
```python
post.view_count += 1
post.save()
```
This reads the count, adds 1 in Python, and writes back. Two concurrent requests both read N and write N+1 instead of N+2. Use:
```python
Post.objects.filter(id=post_id).update(view_count=F('view_count') + 1)
```

**RC2: likes_count has same race condition (Severity: HIGH)**
Same pattern in `like_post`. Also, `post.save()` overwrites ALL fields, potentially clobbering concurrent changes to title, body, etc.

### HIGH - Error Handling

**E1: DoesNotExist raises 500 (Severity: HIGH)**
Every `Post.objects.get(id=post_id)` will raise `Post.DoesNotExist` for invalid IDs, returning a 500 error instead of 404. Use `get_object_or_404(Post, id=post_id)`.

**E2: KeyError on missing form fields (Severity: MEDIUM)**
`request.POST['title']` raises KeyError if the field is absent. Use Django forms for proper validation.

**E3: No JSON parse error handling (Severity: MEDIUM)**
`json.loads(request.body)` and `data['body']` can both raise exceptions.

### MEDIUM - Design Issues

**D1: No pagination (Severity: MEDIUM)**
`Post.objects.all()` loads every post. Use Django Paginator.

**D2: Duplicate likes allowed (Severity: MEDIUM)**
`like_post` creates a new Like every time without checking for existing likes. Use `get_or_create`.

**D3: Hardcoded URLs (Severity: LOW)**
`redirect('/posts/')` breaks if URL patterns change. Use `redirect(reverse('post-list'))`.

**D4: No Django Form for create_post (Severity: LOW)**
Manual field extraction skips validation, sanitization, and CSRF-aware form rendering.'''),

    ("thinking/code-review", r'''Review this Django code and identify issues:

```python
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.conf import settings
import requests
import logging

from .models import Post, Comment, Like, Follow, Profile

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        send_mail(
            'Welcome!',
            f'Hello {instance.username}, welcome to our platform!',
            settings.DEFAULT_FROM_EMAIL,
            [instance.email],
        )
        requests.post(
            'https://analytics.example.com/events',
            json={'event': 'user_created', 'user_id': instance.id}
        )

@receiver(post_save, sender=Post)
def notify_followers_on_new_post(sender, instance, created, **kwargs):
    if created:
        followers = Follow.objects.filter(following=instance.author)
        for follow in followers:
            send_mail(
                f'New post from {instance.author.username}',
                f'{instance.author.username} published: {instance.title}',
                settings.DEFAULT_FROM_EMAIL,
                [follow.follower.email],
            )

@receiver(post_save, sender=Like)
def update_like_count(sender, instance, created, **kwargs):
    if created:
        post = instance.post
        post.likes_count = Like.objects.filter(post=post).count()
        post.save()

@receiver(post_delete, sender=Like)
def decrease_like_count(sender, instance, **kwargs):
    post = instance.post
    post.likes_count = Like.objects.filter(post=post).count()
    post.save()

@receiver(post_save, sender=Follow)
def update_follow_counts(sender, instance, created, **kwargs):
    if created:
        instance.follower.profile.following_count += 1
        instance.follower.profile.save()
        instance.following.profile.followers_count += 1
        instance.following.profile.save()

@receiver(post_delete, sender=Follow)
def decrease_follow_counts(sender, instance, **kwargs):
    instance.follower.profile.following_count -= 1
    instance.follower.profile.save()
    instance.following.profile.followers_count -= 1
    instance.following.profile.save()

@receiver(pre_save, sender=Post)
def auto_moderate_post(sender, instance, **kwargs):
    banned_words = ['spam', 'scam', 'free money']
    for word in banned_words:
        if word in instance.title.lower() or word in instance.body.lower():
            instance.is_published = False
            logger.warning(f'Post by {instance.author.username} flagged: {instance.title}')
            break
```''', r'''<think>
Let me review these Django signal handlers. The first thing I notice is create_user_profile -- it does three things: creates a Profile, sends an email, and hits an external analytics API. All synchronously inside a signal.

Could the synchronous send_mail be acceptable if the SMTP server is fast? Hmm, actually no -- this signal fires during User.save(), which means the request thread blocks on SMTP. If the mail server is slow or unreachable, user creation hangs. But wait, the requests.post() to analytics.example.com is even worse. If that external service is down, the entire User.save() fails because there is no try/except. The user does not get a profile at all because an unrelated analytics call raised ConnectionError. That is a critical reliability issue.

Then there is notify_followers_on_new_post. I initially thought it might be tolerable for small follower counts... but actually it sends one email per follower synchronously in a loop. An author with 10,000 followers triggers 10,000 blocking SMTP calls during the post creation request. The user will absolutely see a timeout. Also, `follow.follower.email` triggers a lazy load per follower -- that is an N+1 query on top of the N blocking emails. Needs select_related('follower').

For the counter signals, update_follow_counts does `instance.follower.profile.following_count += 1` which is a read-modify-write in Python. I considered whether this might be safe under low concurrency... but no, two concurrent follows will both read the same count and one increment is lost. The like count signals are smarter -- they use .count() to get the true value -- but then they call post.save() which saves ALL fields, potentially overwriting concurrent edits to the post title or body.

Wait, there is also a field name mismatch: the model defines `follower_count` but the signal references `followers_count`. That is a runtime AttributeError -- this code has never been tested successfully.

The moderation signal has naive word matching where "spam" in "wingspan" is a false positive. The banned_words list is hardcoded rather than stored in config, and is_published is referenced but never defined in the original model. These signals also create hidden coupling -- a developer calling User.objects.create() has no idea it triggers emails and external API calls.
</think>

## Code Review: Django Signal Handlers

### CRITICAL - Blocking I/O in Signals

**BIO1: Synchronous email in user creation signal (Severity: CRITICAL)**
`send_mail()` in `create_user_profile` blocks the request thread. If the SMTP server is slow or unreachable, user registration hangs or fails. This signal also runs during `createsuperuser`, admin user creation, and tests.

**BIO2: Synchronous HTTP request in signal (Severity: CRITICAL)**
`requests.post('https://analytics.example.com/events', ...)` blocks the request thread and introduces an external dependency into user creation. If the analytics service is down, `User.save()` fails.

**BIO3: Email loop in notify_followers_on_new_post (Severity: CRITICAL)**
Sends one email per follower synchronously during the request. An author with 1,000 followers causes 1,000 blocking SMTP calls. The post creation request will time out.

Fix: Move all I/O to Celery tasks:
```python
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        send_welcome_email.delay(instance.id)
        track_event.delay('user_created', instance.id)
```

### HIGH - Race Conditions

**RC1: Non-atomic counter updates in follow signals (Severity: HIGH)**
```python
instance.follower.profile.following_count += 1
instance.follower.profile.save()
```
This reads the count, increments in Python, and saves. Concurrent follows cause lost updates. Use F() expressions:
```python
Profile.objects.filter(user=instance.follower).update(
    following_count=F('following_count') + 1
)
```

**RC2: post.save() in like signals overwrites all fields (Severity: MEDIUM)**
`post.save()` after updating likes_count writes all Post fields, potentially overwriting concurrent edits to title, body, etc. Use `post.save(update_fields=['likes_count'])` or `Post.objects.filter(...).update(...)`.

### HIGH - Error Handling

**EH1: No exception handling around I/O (Severity: HIGH)**
If `send_mail()` or `requests.post()` raises an exception, the entire database transaction is rolled back. The Profile is not created because the analytics call failed. Wrap in try/except or move to async tasks.

**EH2: Profile existence not verified (Severity: MEDIUM)**
`decrease_follow_counts` accesses `instance.follower.profile` which may not exist if the profile was deleted.

### HIGH - Field Name Mismatch

**BUG1: followers_count vs follower_count (Severity: HIGH)**
The signal references `instance.following.profile.followers_count` but the model defines `follower_count`. This is a runtime AttributeError that will crash on every Follow creation.

### MEDIUM - N+1 Queries

**Q1: notify_followers_on_new_post (Severity: MEDIUM)**
`follow.follower.email` triggers a lazy load per iteration. Fix:
```python
followers = Follow.objects.filter(
    following=instance.author
).select_related('follower')
```

### MEDIUM - Design

**D1: Hidden side effects (Severity: MEDIUM)**
Signals create invisible coupling. A `User.objects.create()` call silently sends emails and hits external APIs. This makes testing difficult and behavior surprising. Consider explicit service functions instead.

**D2: Naive word matching in moderation (Severity: MEDIUM)**
`'spam' in instance.title.lower()` matches "wingspan", "Spamberg", etc. Use regex word boundaries: `r'\bspam\b'`.

**D3: Hardcoded banned words list (Severity: LOW)**
Store moderation terms in the database or a configuration file so they can be updated without deployment.'''),

    ("thinking/code-review", r'''Review this Django code and identify issues:

```python
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import Post, Comment, Profile
import re

class RegistrationForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    bio = forms.CharField(widget=forms.Textarea, required=False)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if password != confirm:
            raise ValidationError('Passwords do not match')
        return cleaned_data

    def save(self):
        user = User.objects.create(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
        )
        user.password = self.cleaned_data['password']
        user.save()
        Profile.objects.create(user=user, bio=self.cleaned_data.get('bio', ''))
        return user

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = '__all__'

    def clean_title(self):
        title = self.cleaned_data['title']
        if len(title) < 5:
            raise ValidationError('Title too short')
        return title

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = '__all__'

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar_url', 'is_verified', 'follower_count']

class SearchForm(forms.Form):
    query = forms.CharField(max_length=200)

    def search(self):
        q = self.cleaned_data['query']
        posts = Post.objects.raw(
            f"SELECT * FROM myapp_post WHERE title LIKE '%%{q}%%' OR body LIKE '%%{q}%%'"
        )
        return posts

class BulkDeleteForm(forms.Form):
    post_ids = forms.CharField()

    def clean_post_ids(self):
        ids_str = self.cleaned_data['post_ids']
        ids = ids_str.split(',')
        return [int(id) for id in ids]

    def execute(self):
        Post.objects.filter(id__in=self.cleaned_data['post_ids']).delete()
```''', r'''<think>
Let me carefully review these Django form classes. Starting with RegistrationForm.

The save() method does `user.password = self.cleaned_data['password']` -- wait, that stores the password in PLAIN TEXT. Django's User model expects a hashed value in the password field. Every user's password is stored raw. Actually, looking more carefully, User.objects.create() also does not hash the password. The correct approach is User.objects.create_user(username, email, password) which handles hashing. This is the most critical security issue here.

Beyond the password, there is no uniqueness check on username or email. I considered whether Django might handle this at the model level... but no, without form-level validation, the create() call will raise IntegrityError which surfaces as an ugly 500 error. Also no password strength validation at all, and save() is not wrapped in a transaction -- if Profile creation fails, we get an orphaned user without a profile.

Now PostForm uses fields = '__all__'. Could this be intentional for an admin form? Hmm, but it is a regular ModelForm, not an admin form. This exposes author, likes_count, view_count, and timestamps to user input. A malicious user can set themselves as a different author or inflate like counts. This is a mass-assignment vulnerability. CommentForm has the same problem -- exposing author and post fields.

ProfileUpdateForm is alarming -- it includes is_verified and follower_count in the editable fields. A user can literally verify themselves and set follower_count to 999999. These are clearly admin-only fields that slipped into the user-facing form.

The SearchForm is where things get really dangerous. It uses `f"SELECT * FROM myapp_post WHERE title LIKE '%%{q}%%'"` with raw(). That is textbook SQL injection. An attacker can inject arbitrary SQL through the search query field, potentially dumping the entire database or deleting tables.

BulkDeleteForm has no authorization check -- any user can delete any posts by ID. And clean_post_ids will raise ValueError on non-numeric input, but since it is not caught and converted to ValidationError, it becomes an unhandled 500 error. Also `int(id)` shadows the built-in, though that is minor compared to the other issues.
</think>

## Code Review: Django Forms

### CRITICAL - Security Vulnerabilities

**SEC1: Plain text password storage (Severity: CRITICAL)**
```python
user.password = self.cleaned_data['password']
user.save()
```
This stores the raw password string in the database. Django expects a hashed value. Every user's password is stored in plain text and immediately compromised if the database is breached.

Fix: Use `User.objects.create_user()` which hashes automatically:
```python
def save(self):
    user = User.objects.create_user(
        username=self.cleaned_data['username'],
        email=self.cleaned_data['email'],
        password=self.cleaned_data['password'],
    )
    Profile.objects.create(user=user, bio=self.cleaned_data.get('bio', ''))
    return user
```

**SEC2: SQL injection in SearchForm (Severity: CRITICAL)**
```python
f"SELECT * FROM myapp_post WHERE title LIKE '%%{q}%%'"
```
User-supplied `q` is interpolated directly into raw SQL. An attacker can inject arbitrary queries. Use Django ORM:
```python
def search(self):
    q = self.cleaned_data['query']
    return Post.objects.filter(
        Q(title__icontains=q) | Q(body__icontains=q)
    )
```

**SEC3: Mass assignment via fields = '__all__' (Severity: CRITICAL)**
`PostForm` with `fields = '__all__'` exposes `author`, `likes_count`, `view_count`, and timestamp fields. A malicious user can submit arbitrary values for these fields, impersonating other authors or inflating counts.

`CommentForm` has the same problem -- exposes `author` and `parent`.

Fix: Explicitly list only user-editable fields:
```python
class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'body', 'tags']
```

**SEC4: ProfileUpdateForm exposes privileged fields (Severity: CRITICAL)**
Users can set `is_verified = True` and `follower_count = 999999` through this form. Remove these fields:
```python
fields = ['bio', 'avatar_url']
```

### HIGH - Data Integrity

**DI1: No transaction in RegistrationForm.save (Severity: HIGH)**
If Profile creation fails after User creation, you have an orphaned user. Wrap in `transaction.atomic()`:
```python
from django.db import transaction

def save(self):
    with transaction.atomic():
        user = User.objects.create_user(...)
        Profile.objects.create(user=user, ...)
    return user
```

**DI2: No username uniqueness check (Severity: HIGH)**
If the username already exists, `User.objects.create()` raises `IntegrityError`, which becomes a 500 error. Validate in `clean_username`:
```python
def clean_username(self):
    username = self.cleaned_data['username']
    if User.objects.filter(username=username).exists():
        raise ValidationError('Username already taken')
    return username
```

### MEDIUM - Validation

**V1: No password strength validation (Severity: MEDIUM)**
No minimum length, complexity, or common-password checks. Use Django's built-in validators:
```python
from django.contrib.auth.password_validation import validate_password

def clean_password(self):
    password = self.cleaned_data['password']
    validate_password(password)
    return password
```

**V2: BulkDeleteForm crashes on non-numeric input (Severity: MEDIUM)**
`int(id)` raises `ValueError` if any ID is not numeric. This should be caught and converted to a validation error. Also, no authorization check -- any authenticated user can delete arbitrary posts.

### LOW - Design

**D1: BulkDeleteForm has no ownership verification**
The form deletes any Post by ID without checking if the current user owns it. Authorization logic must be added either in the form or the view.'''),

    ("thinking/code-review", r'''Review this Django code and identify issues:

```python
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Count, Avg
from django.core.cache import cache
from django.core.serializers import serialize
from .models import Post, Comment, Like, Follow, Profile
import json

@csrf_exempt
def api_posts(request):
    if request.method == 'GET':
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))
        category = request.GET.get('category')
        search = request.GET.get('search')

        posts = Post.objects.all()
        if category:
            posts = posts.filter(tags__contains=category)
        if search:
            posts = posts.filter(
                Q(title__contains=search) | Q(body__contains=search)
            )

        start = (page - 1) * per_page
        end = start + per_page
        posts = posts[start:end]

        data = []
        for post in posts:
            data.append({
                'id': post.id,
                'title': post.title,
                'body': post.body,
                'author': post.author.username,
                'author_avatar': post.author.profile.avatar_url,
                'likes': post.likes_count,
                'comments': Comment.objects.filter(post=post).count(),
                'created': str(post.created),
            })
        return JsonResponse({'posts': data})

    elif request.method == 'POST':
        data = json.loads(request.body)
        post = Post.objects.create(
            author_id=data['author_id'],
            title=data['title'],
            body=data['body'],
            tags=data.get('tags', ''),
        )
        return JsonResponse({'id': post.id, 'title': post.title})

@csrf_exempt
def api_feed(request):
    user = request.user
    following_ids = Follow.objects.filter(
        follower=user
    ).values_list('following_id', flat=True)

    cache_key = f'feed_{user.id}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'posts': cached})

    posts = Post.objects.filter(
        author_id__in=list(following_ids)
    ).select_related('author').order_by('-created')[:50]

    data = serialize('json', posts)
    cache.set(cache_key, data)
    return JsonResponse({'posts': data})

@csrf_exempt
def api_trending(request):
    posts = Post.objects.annotate(
        engagement=F('likes_count') + F('view_count') + Count('comment')
    ).order_by('-engagement')[:20]

    result = []
    for post in posts:
        result.append({
            'id': post.id,
            'title': post.title,
            'engagement': post.engagement,
            'author': post.author.username,
        })
    return JsonResponse({'posts': result})

@csrf_exempt
def api_stats(request):
    stats = {
        'total_posts': Post.objects.count(),
        'total_comments': Comment.objects.count(),
        'total_users': Profile.objects.count(),
        'avg_likes': Post.objects.aggregate(avg=Avg('likes_count'))['avg'],
        'top_authors': list(
            Post.objects.values('author__username').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
        ),
    }
    return JsonResponse(stats)
```''', r'''<think>
Let me review this Django API code. The first thing I notice is @csrf_exempt on every single view.

Could the csrf_exempt be intentional for a JSON API? Possibly, but without any alternative authentication (token auth, API keys), this just disables CSRF protection entirely. Any malicious website can submit POST requests on behalf of authenticated users. And api_posts POST lets the client set author_id directly from request data -- so any user can create posts attributed to anyone. That is author impersonation.

Looking at api_feed, it accesses request.user but has no @login_required decorator. I initially thought Django might handle this gracefully... but wait, for anonymous users, request.user is AnonymousUser, and filtering Follow objects by AnonymousUser will either fail or return empty results silently. No authentication on any endpoint is a fundamental security gap.

The N+1 query pattern appears again in api_posts GET. For each post in the loop, we access post.author.username (lazy load), post.author.profile.avatar_url (another lazy load), and run Comment.objects.filter(post=post).count() (yet another query). With the default per_page=50, that is 151 database queries. api_trending has the same issue -- post.author.username in the loop without select_related.

For input validation, `int(request.GET.get('page', 1))` will crash with ValueError if someone passes page=abc. I considered whether this might be caught by middleware... but no, there is no error handling, so it returns a raw 500. Also per_page has no upper bound -- a client can request per_page=1000000, loading the entire table into memory.

The caching in api_feed is particularly broken. serialize('json', posts) produces a JSON string, which then gets passed to JsonResponse({'posts': data}). Wait, that means JsonResponse encodes it again -- the client receives escaped JSON inside JSON, like `{"posts": "[{\"model\": ...}]"}`. The data is double-serialized. Additionally, cache.set has no TTL, so entries persist indefinitely, and there is no invalidation when followed users publish new posts.

The annotation in api_trending mixes F() with Count() in a single annotate call. Because the Count('comment') join duplicates post rows, the F('likes_count') and F('view_count') values get multiplied by the number of comments. The engagement score is inflated. This is a subtle but well-known Django ORM gotcha.
</think>

## Code Review: Django API Views

### CRITICAL - Security

**SEC1: CSRF disabled on all endpoints (Severity: CRITICAL)**
Every view uses `@csrf_exempt`, removing all CSRF protection. Any malicious website can submit POST requests on behalf of authenticated users. If you need a CSRF-exempt JSON API, use Django REST Framework with token authentication or implement proper API authentication.

**SEC2: Author impersonation in api_posts POST (Severity: CRITICAL)**
```python
author_id=data['author_id']
```
The client supplies the author ID, allowing any user to create posts attributed to anyone. The author should come from `request.user`.

**SEC3: No authentication on any endpoint (Severity: HIGH)**
All endpoints are accessible to anonymous users. `api_feed` accesses `request.user` without `@login_required`, so an anonymous user triggers queries with `AnonymousUser`, which may fail or return unexpected results.

### CRITICAL - N+1 Queries

**Q1: api_posts has 3N+1 query problem (Severity: CRITICAL)**
The serialization loop lazy-loads `post.author`, `post.author.profile`, and runs a COUNT query per post. For 50 posts (the default per_page), this is 151 queries.

Fix:
```python
posts = Post.objects.select_related(
    'author', 'author__profile'
).annotate(
    comment_count=Count('comment')
)[start:end]
```

**Q2: api_trending lazy-loads authors (Severity: HIGH)**
`post.author.username` in the loop fires N queries. Add `.select_related('author')`.

### HIGH - Caching Bugs

**C1: Double-serialized feed response (Severity: HIGH)**
`serialize('json', posts)` produces a JSON string. `cache.set(cache_key, data)` stores that string. `JsonResponse({'posts': data})` then JSON-encodes it again, producing escaped JSON inside JSON:
```json
{"posts": "[{\"model\": \"app.post\", ...}]"}
```
The client receives a string instead of an array.

**C2: Feed cache never invalidated (Severity: HIGH)**
No cache invalidation when followed users publish new posts. The feed is stale until the cache expires. Also, `cache.set(cache_key, data)` without a timeout may cache indefinitely.

### HIGH - Annotation Bug

**Q3: Count + F() annotation produces wrong results (Severity: HIGH)**
```python
engagement=F('likes_count') + F('view_count') + Count('comment')
```
If a Post has multiple comments, the JOIN duplicates the post row, inflating the Count. The F() values get multiplied by the number of joined rows. Use a Subquery for the count, or annotate in a separate step.

### MEDIUM - Input Validation

**V1: Unchecked type conversions (Severity: MEDIUM)**
`int(request.GET.get('page', 1))` crashes with ValueError if a non-numeric value is passed. Wrap in try/except or use a form for validation.

**V2: Unbounded per_page (Severity: MEDIUM)**
No upper limit on `per_page`. A client can request `per_page=1000000`, loading the entire table into memory. Add a cap: `per_page = min(int(request.GET.get('per_page', 50)), 100)`.

**V3: No error handling on JSON parsing (Severity: MEDIUM)**
`json.loads(request.body)` and `data['title']` can both raise exceptions, returning 500 errors.

### MEDIUM - Query Issues

**Q4: Substring tag matching (Severity: MEDIUM)**
`tags__contains=category` does a SQL LIKE substring match. Searching for "art" matches "smart", "start", etc. This is a consequence of the comma-separated tags design. Use a proper tag model with ManyToManyField.

### LOW - Performance

**P1: api_stats is uncached (Severity: LOW)**
Runs 4 queries (count, count, count, aggregate + annotate) on every request. Cache the result for a few minutes since these statistics do not need real-time accuracy.'''),
]
