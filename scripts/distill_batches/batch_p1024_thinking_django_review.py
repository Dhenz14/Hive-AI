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
Let me review these Django models for design issues, missing constraints, performance concerns, and data integrity problems.

1. Profile model:
- Uses ForeignKey instead of OneToOneField. A user could have multiple profiles, which is almost certainly not intended.
- follower_count and following_count are denormalized counters that can get out of sync with the actual Follow table. This is a common source of bugs -- need signals or triggers to keep them in sync.
- No related_name set, so Django auto-generates `profile_set` instead of a clean `profile` accessor.

2. Post model:
- tags stored as comma-separated string -- this is a classic antipattern. Cannot query efficiently, no referential integrity, no normalization. Should use a ManyToManyField or a library like django-taggit.
- likes_count is denormalized like the profile counters. Same sync risk.
- view_count as IntegerField will cause contention under high traffic if every page view does an UPDATE. Consider a separate analytics system.
- No indexes defined -- queries filtering by author, created date, or tags will be slow.

3. Comment model:
- parent FK with on_delete=CASCADE means deleting a parent comment deletes all replies, which may not be the desired behavior. Often SET_NULL is better so replies remain visible.
- No ordering defined -- comments will come back in arbitrary order.
- No max depth enforcement for nested comments.

4. Like model:
- No unique_together constraint on (user, post). A user can like the same post multiple times.
- No related_name specified.

5. Follow model:
- No unique_together constraint on (follower, following). A user can follow the same person multiple times.
- No constraint preventing self-follows (follower == following).

6. General issues:
- No __str__ methods on any model -- admin interface will show "Post object (1)".
- No Meta classes with ordering, indexes, or verbose names.
- No related_name on most ForeignKeys -- will cause clashes or confusing reverse accessors.

Let me structure this review.
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
Let me review these Django views for N+1 queries, security, error handling, and design issues.

1. N+1 Query Problems:
- post_list: `Post.objects.all()` then for each post: `Comment.objects.filter(post=post).count()` (N queries), `post.author.username` (N queries for author), `post.author.profile.avatar_url` (N queries for profile). This is 3N+1 queries. With 100 posts, that is 301 queries.

2. Security:
- delete_post has no authorization check -- any logged-in user can delete any post. Must check post.author == request.user.
- CommentView.delete has the same issue -- no ownership check.
- CommentView.post does not require login (no LoginRequiredMixin).
- create_post does no input validation or sanitization. request.POST['title'] will raise KeyError if field is missing.
- like_post allows unlimited likes from the same user.
- delete_post accepts GET requests -- should require POST/DELETE for destructive actions.

3. Error handling:
- Every .get() call can raise DoesNotExist, resulting in 500 errors. Should use get_object_or_404.
- json.loads(request.body) can raise JSONDecodeError.
- data['body'] can raise KeyError.

4. Data integrity:
- post_detail does `post.view_count += 1; post.save()` which is a race condition. Two simultaneous requests can read the same count and both write count+1 instead of count+2. Use F() expression.
- like_post has the same race condition with likes_count.
- post.save() in post_detail saves ALL fields, potentially overwriting concurrent changes to other fields. Use update() or save(update_fields=['view_count']).

5. Design:
- Hardcoded URL '/posts/' in redirects instead of using reverse().
- No CSRF protection consideration for JSON endpoints.
- No pagination on post_list.
- No form class for create_post.

Let me write the structured review.
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
Let me review these Django signals for performance, reliability, and design issues.

1. Performance / Blocking operations in signals:
- create_user_profile calls send_mail() synchronously in a signal handler. This blocks the request thread. If the mail server is slow, user creation will be slow.
- create_user_profile also calls requests.post() to an external analytics service. This is even worse -- if analytics.example.com is down, the User.save() call will hang or fail.
- notify_followers_on_new_post sends an email per follower, synchronously, in a loop. If an author has 10,000 followers, this sends 10,000 emails during the request. The user will see a timeout.

2. N+1 queries in signals:
- notify_followers_on_new_post: `follow.follower.email` triggers a query per follower to load the User object. Need select_related('follower').
- update_follow_counts: Each call does 4 queries (2 profile loads + 2 saves). And it accesses instance.follower.profile which is not select_related.

3. Race conditions:
- update_follow_counts does `+= 1` in Python, same non-atomic pattern. Two concurrent follows will lose one increment.
- The like count signals use `.count()` which is better (gets current truth), but calling `post.save()` saves all fields on the post, potentially overwriting concurrent edits.

4. Error handling:
- No try/except around send_mail or requests.post. If any of these fail, the entire save transaction fails. The user profile might not get created because the analytics POST failed.
- decrease_follow_counts assumes profile exists. If the profile was deleted, this crashes.

5. Signal design issues:
- These signals create hidden side effects. A developer calling User.objects.create() has no idea it will send emails and hit external APIs.
- update_like_count calls post.save(), which triggers post_save on Post, which triggers notify_followers_on_new_post (if it checks for created, it won't fire, but it's still confusing cascading behavior).
- The field name inconsistency: model has follower_count but signal references followers_count.

6. Moderation signal:
- auto_moderate_post has naive word matching. "spam" matches "wingspan". Should use word boundary matching.
- banned_words is hardcoded -- should be in database or config.
- is_published field is referenced but not defined in the original model.

Let me structure the review.
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
Let me carefully review these Django form classes.

1. RegistrationForm:
- user.password = self.cleaned_data['password'] stores the PASSWORD IN PLAIN TEXT. This is the most critical issue. Django expects hashed passwords. Must use user.set_password() or User.objects.create_user().
- Actually, User.objects.create() does not hash the password either. Should be User.objects.create_user(username, email, password).
- No uniqueness check on username or email -- will raise IntegrityError.
- No password strength validation at all.
- save() is not wrapped in a transaction -- if Profile creation fails, we have a user without a profile.

2. PostForm:
- fields = '__all__' exposes every field, including author, likes_count, view_count, created, updated. A user could set themselves as a different author or set arbitrary like counts. This is a mass-assignment vulnerability.

3. CommentForm:
- fields = '__all__' again. Exposes author, post, parent fields. A user could impersonate another user as comment author.

4. ProfileUpdateForm:
- Exposes is_verified and follower_count! A user can verify themselves and set arbitrary follower counts. These should be admin-only fields.

5. SearchForm:
- SQL INJECTION! Using f-string with raw() to build a query from user input. An attacker can inject arbitrary SQL via the search query field.

6. BulkDeleteForm:
- No authorization check -- any user could delete any posts.
- clean_post_ids will raise ValueError if any ID is not a number, but this becomes an unhandled exception rather than a validation error.
- int(id) -- `id` shadows the built-in.

Let me structure this review.
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
Let me review this Django API code.

1. CSRF and Authentication:
- Every view uses @csrf_exempt, completely disabling CSRF protection. This allows cross-site request forgery attacks on all endpoints including POST.
- api_posts POST allows setting author_id from request data -- any client can impersonate any user
- api_feed accesses request.user but has no @login_required. For anonymous users, request.user is AnonymousUser, and the query will fail or return empty results silently.
- No authentication on any endpoint.

2. N+1 queries:
- api_posts GET: for each post, accesses post.author.username (lazy load), post.author.profile.avatar_url (lazy load), and runs Comment.objects.filter(post=post).count(). This is 3N+1 queries again.
- api_trending: post.author.username in the loop without select_related.

3. Input validation:
- int(request.GET.get('page', 1)) -- if someone passes page=abc, this raises ValueError and returns 500.
- per_page has no upper bound -- a client can request per_page=1000000.
- json.loads(request.body) has no error handling.
- data['author_id'], data['title'], data['body'] can all raise KeyError.

4. Caching issues in api_feed:
- Cache is never invalidated. When a followed user publishes a new post, the feed stays stale until TTL expires.
- cache.set without TTL means the entry may persist indefinitely depending on backend.
- The cache stores serialized Django model data, but the response wraps it in JsonResponse. This double-serializes: serialize('json', posts) produces a JSON string, which then gets JSON-encoded again inside JsonResponse, resulting in escaped JSON inside JSON.

5. Query issues:
- api_trending annotates with Count('comment'). This needs the related_name to be correct. Also, mixing F() expressions with Count() in annotate can produce incorrect results due to the join producing duplicate rows. The count will be inflated by the join.
- api_posts uses tags__contains which does a substring match on the comma-separated tags string. Searching for "art" would match "smart", "start", etc.
- following_ids is converted to list() unnecessarily -- Django querysets work fine as subqueries.

6. Performance:
- api_stats runs 4 separate database queries with no caching. This could be expensive on large tables.
- No database indexes implied for the query patterns used.

Let me write the structured review.
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
