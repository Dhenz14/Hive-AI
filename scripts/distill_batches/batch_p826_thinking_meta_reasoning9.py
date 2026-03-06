"""Phase 3A: Metacognition — Reasoning About Edge Cases Systematically (Part 9)

Training the model to systematically identify edge cases rather than
relying on intuition, using structured approaches to find boundary
conditions and unusual inputs.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-edge-cases-input-validation",
        r'''I wrote a function to validate email addresses. How do I systematically think about edge cases?''',
        r'''<think>
Rather than listing edge cases for email specifically, I should teach a systematic approach to finding edge cases that applies to any validation problem. Then demonstrate with email as the example.

My systematic approach to edge cases uses categories:
1. Boundary values (empty, minimum, maximum)
2. Type variations (null, wrong type, special types)
3. Format variations (valid but unusual, technically valid per spec)
4. Encoding/character issues (Unicode, special characters)
5. Adversarial inputs (injection, overflow)
6. Domain-specific rules (email has many specific rules)

I'm confident in this systematic framework. Email validation specifically has well-known edge cases from RFC 5322 that most people get wrong.
</think>

Rather than listing email edge cases from memory, let me teach you a systematic framework you can apply to ANY validation problem.

**The BOUNDARY framework for edge case discovery:**

```
B - Boundaries:    Empty, minimum, maximum length/value
O - Omissions:     Missing parts, null, undefined
U - Unusual valid: Technically valid but unexpected
N - Negative:      Invalid inputs that should be rejected
D - Data types:    Wrong types, special encodings
A - Adversarial:   Malicious inputs, injection attempts
R - Repetition:    Duplicates, repeated characters
Y - Yesterday:     Historical formats, legacy data
```

**Applied to email validation:**

**B — Boundaries:**
```python
test_cases = [
    "",                           # Empty string
    "a@b.c",                     # Minimum plausible email (is this valid?)
    "a" * 64 + "@example.com",  # Max local part (64 chars per RFC)
    "a@" + "b" * 253 + ".com",  # Max domain (253 chars per RFC)
    "a" * 65 + "@example.com",  # Over max local part → should reject
]
```

**O — Omissions:**
```python
test_cases = [
    None,                    # Null input
    "alice",                 # Missing @ and domain
    "@example.com",         # Missing local part
    "alice@",               # Missing domain
    "alice@.com",           # Missing domain name before TLD
    "alice@example.",       # Missing TLD
    "alice@example",        # No dot in domain (technically valid for intranet!)
]
```

**U — Unusual but valid (per RFC 5322):**
```python
test_cases = [
    "alice+tag@example.com",         # Plus addressing
    "alice.bob@example.com",         # Dots in local part
    "alice@sub.domain.example.com",  # Subdomains
    '"alice bob"@example.com',       # Quoted local part with spaces
    "alice@123.123.123.123",         # IP address domain
    "alice@[IPv6:::1]",              # IPv6 domain
    "user@example.co.uk",            # Multi-part TLD
    "disposable@guerrillamail.com",  # Disposable email (valid but unwanted?)
]
```

**N — Negative (should reject):**
```python
test_cases = [
    "alice bob@example.com",    # Unquoted space
    "alice@@example.com",       # Double @
    "alice@example..com",       # Double dots in domain
    ".alice@example.com",       # Leading dot in local part
    "alice.@example.com",       # Trailing dot in local part
    "alice@-example.com",       # Domain starting with hyphen
]
```

**D — Data types and encoding:**
```python
test_cases = [
    123,                              # Integer, not string
    True,                             # Boolean
    "alice@example.com ",             # Trailing whitespace
    " alice@example.com",             # Leading whitespace
    "alice@example.com\n",            # Newline injection
    "\u0430lice@example.com",         # Cyrillic 'a' (homoglyph attack)
    "alice@exämple.com",              # IDN domain (internationalized)
]
```

**A — Adversarial:**
```python
test_cases = [
    "alice@example.com\r\nBCC: victim@example.com",  # Email header injection
    "alice'--@example.com",                           # SQL injection in email
    "<script>alert(1)</script>@example.com",          # XSS in email
    "alice@example.com" * 1000,                       # Amplification
]
```

**The systematic process:**
1. Walk through each BOUNDARY category
2. Generate 2-3 test cases per category
3. Determine expected behavior for each (accept or reject?)
4. Write the tests BEFORE fixing the validation
5. Run the tests — you'll find bugs

This framework works for any input validation: dates, phone numbers, URLs, usernames, file paths.'''
    ),
    (
        "thinking/meta-reasoning-edge-cases-pagination",
        r'''I'm implementing cursor-based pagination for our API. What edge cases should I handle?''',
        r'''<think>
Pagination edge cases are a classic source of bugs. Let me systematically think through the categories.

Cursor state edge cases:
- No cursor (first page)
- Invalid/malformed cursor
- Cursor pointing to deleted item
- Cursor from a different version of the data
- Expired cursor

Data mutation edge cases:
- Items inserted while paginating
- Items deleted while paginating
- Items updated to change sort order while paginating
- Empty result set

Boundary edge cases:
- Exactly N items (page size = total items)
- Zero items
- One item
- Page size of 1
- Very large page size
- Negative page size

Concurrency edge cases:
- Concurrent pagination requests
- Data changes between pages

I'm confident in these edge cases — pagination bugs are well-documented.
</think>

Pagination has more edge cases than most developers expect. Let me walk through them systematically.

**Category 1: Cursor validity**
```python
# Test case: No cursor (first page)
GET /api/items?limit=20
# → Should return first 20 items + next_cursor

# Test case: Invalid cursor
GET /api/items?cursor=GARBAGE&limit=20
# → Should return 400 error, not 500 or empty results

# Test case: Cursor for deleted item
# User paginates, item at cursor position is deleted between requests
GET /api/items?cursor=eyJpZCI6NDJ9&limit=20
# → Should return items AFTER the deleted item's position, not error

# Test case: Expired cursor (if using time-limited cursors)
GET /api/items?cursor=EXPIRED_TOKEN&limit=20
# → Should return 400 with message "cursor expired, start over"

# Test case: Cursor from old API version / schema change
# → Should fail gracefully, not crash
```

**Category 2: Boundary conditions**
```python
# Zero items in collection
GET /api/items?limit=20
# → { "data": [], "next_cursor": null, "has_more": false }

# Exactly one item
# → { "data": [item], "next_cursor": null, "has_more": false }

# Exactly page_size items (tricky!)
# If you have 20 items and limit=20:
# → Do you return has_more: true or false?
# → You don't know without fetching limit+1 items

# This is the standard trick:
async def paginate(query, limit):
    items = await query.limit(limit + 1).fetch()  # Fetch one extra
    has_more = len(items) > limit
    items = items[:limit]  # Return only requested amount
    return items, has_more

# Page size edge cases:
GET /api/items?limit=0    # → Error or empty result?
GET /api/items?limit=-1   # → Error (validate!)
GET /api/items?limit=10000 # → Cap at max (e.g., 100)
```

**Category 3: Data mutation during pagination**
```
Page 1: [A, B, C, D, E] — cursor points after E
  ← B is deleted between requests →
Page 2: [F, G, H, I, J] — B's deletion doesn't affect page 2 ✓

BUT with offset-based pagination:
Page 1: [A, B, C, D, E] (offset=0, limit=5)
  ← B is deleted →
Page 2: offset=5, limit=5 → [G, H, I, J, K]
  → F is SKIPPED! User never sees it.

This is why cursor-based is better than offset-based for mutable data.
```

**Category 4: Sort order edge cases**
```sql
-- What if multiple items have the same sort value?
-- cursor = { created_at: "2024-03-10T00:00:00Z" }
-- If 50 items were created at the exact same timestamp,
-- the cursor is ambiguous — which ones come "after"?

-- Fix: compound cursor with a unique tiebreaker
-- cursor = { created_at: "2024-03-10T00:00:00Z", id: 42 }
WHERE (created_at, id) > ($cursor_time, $cursor_id)
ORDER BY created_at, id
LIMIT $limit + 1
```

**Category 5: Security edge cases**
```python
# Can a user tamper with the cursor to access other users' data?
# If cursor contains a raw SQL offset or ID, probably yes.

# SAFE: Encrypt/sign cursors
import base64, json, hmac

def encode_cursor(data: dict, secret: str) -> str:
    payload = json.dumps(data)
    sig = hmac.new(secret.encode(), payload.encode(), 'sha256').hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

def decode_cursor(cursor: str, secret: str) -> dict:
    decoded = base64.urlsafe_b64decode(cursor).decode()
    payload, sig = decoded.rsplit('|', 1)
    expected = hmac.new(secret.encode(), payload.encode(), 'sha256').hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid cursor")
    return json.loads(payload)
```

**Implementation checklist:**
```
- [ ] Handle missing cursor (first page)
- [ ] Validate and reject malformed cursors
- [ ] Handle deleted items at cursor position
- [ ] Fetch limit+1 to determine has_more
- [ ] Cap maximum page size
- [ ] Reject negative/zero page sizes
- [ ] Use compound cursor (sort field + unique ID)
- [ ] Sign/encrypt cursor to prevent tampering
- [ ] Test with empty collection
- [ ] Test with exactly page_size items
```'''
    ),
    (
        "thinking/meta-reasoning-edge-cases-date-handling",
        r'''I need to implement a "subscription renewal" feature that charges users on the same day each month. What edge cases should I worry about?''',
        r'''<think>
Monthly billing on "the same day" is a deceptively complex problem. The fundamental issue is that months have different numbers of days.

Key edge cases:
1. The 31st of the month — what happens in February, April, June, etc.?
2. February 29 (leap year) — what happens in non-leap years?
3. Timezone considerations — whose "same day" are we talking about?
4. DST transitions — billing at midnight in a timezone that shifts
5. Failed charges — retry logic, grace periods
6. Plan changes mid-cycle — proration
7. Cancellation timing — charge before or after cancellation?

This is an area where I'm confident in the edge cases because billing is well-studied and these bugs are well-documented. Real-world billing systems all have to solve these same problems.
</think>

Monthly billing is one of those "simple" problems that's full of traps. Here are the edge cases, organized by category.

**Category 1: Day-of-month doesn't exist**

This is the most fundamental edge case:
```
User subscribes January 31
  February renewal: Feb 31 doesn't exist
  Solution options:
    a) Bill on Feb 28/29 (last day of month)
    b) Bill on March 1 (next valid day)
    c) Bill on March 3 (31 days later)

Each choice has different implications:
  Option (a): "Same day or last day" — most common, user-friendly
  Option (b): Skips February billing entirely? Or double-bills?
  Option (c): Billing drifts — eventually billing on the 2nd, 3rd, etc.
```

```python
from datetime import date
from calendar import monthrange

def next_billing_date(anchor_day: int, current_date: date) -> date:
    """Calculate next billing date, clamping to last day of month."""
    next_month = current_date.month + 1
    next_year = current_date.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    last_day = monthrange(next_year, next_month)[1]
    billing_day = min(anchor_day, last_day)
    return date(next_year, next_month, billing_day)

# Store the ORIGINAL anchor day (31), not the calculated day
# So Jan 31 → Feb 28 → Mar 31 (returns to 31, not stuck on 28)
```

**Category 2: Leap year**
```
User subscribes February 29, 2024 (leap year)
  March 2024: March 29 ✓
  February 2025 (not leap year): Feb 29 doesn't exist
  → Bill on Feb 28

User subscribes February 28, 2024
  February 2025: Feb 28 ✓
  February 2028 (leap year): Feb 28 (not Feb 29)
  → Anchor is 28, always bill on 28
```

**Category 3: Timezone and timing**
```
User in UTC+12 (New Zealand), server in UTC
  "March 15" for user starts at March 14 12:00 UTC

If you bill at midnight UTC:
  User sees charge on "March 14" in their timezone

Solution: Bill based on user's timezone, or bill early morning
in the latest timezone (UTC-12) to ensure correct date globally.
```

**Category 4: Payment failures**
```
First attempt fails → retry when?
  Day 1: Attempt charge
  Day 1: Failure → retry in 24 hours
  Day 2: Retry → failure → retry in 48 hours
  Day 4: Retry → failure → send warning email
  Day 7: Final retry → failure → suspend account
  Day 14: No payment → cancel subscription

Edge cases in retry:
  - What if retry succeeds on day 4? Is the NEXT billing from day 1 or day 4?
  - Keep billing from original anchor date (day 1), not retry date
```

**Category 5: Plan changes and cancellations**
```
Upgrade mid-cycle:
  Billed $10 on March 1 for Basic plan
  Upgrades to Pro ($20) on March 15
  Options: Charge $20 immediately? Prorate? Wait until April 1?

Cancellation timing:
  User cancels March 10, paid through March 31
  → Access until March 31, no charge April 1
  → What if they resubscribe March 25? Do they pay again?

Downgrade mid-cycle:
  Paid $20, downgrades to $10 plan
  → Credit the difference? Apply at next billing?
```

**Category 6: Edge cases most teams miss**
```
- Currency changes (user moves countries)
- Price changes (do existing subscribers get new price?)
- Tax calculation changes (VAT rate changes)
- Free trial to paid transition (trial ends on the 31st)
- Annual billing with monthly option (switching between)
- Refunds and their effect on the billing cycle
- Multiple subscriptions per user
```

**My strong recommendation:** Use a billing library or service (Stripe Billing, Recurly, Chargebee) rather than implementing this yourself. The edge cases above represent years of bugs that these services have already solved.'''
    ),
    (
        "thinking/meta-reasoning-edge-cases-file-upload",
        r'''I'm building a file upload endpoint for user profile pictures. What edge cases should my validation handle?''',
        r'''<think>
File upload validation is a security-critical feature. Let me think systematically about edge cases across categories.

Content-related:
- Wrong file type (not an image)
- File with image extension but non-image content
- Corrupted image file
- Zero-byte file
- Very large file
- Image with embedded executable (polyglot file)

Filename-related:
- Path traversal (../../etc/passwd)
- Null bytes in filename
- Very long filenames
- Special characters in filenames
- Duplicate filenames
- No extension
- Multiple extensions (.jpg.php)

Processing-related:
- Image with extreme dimensions (100000x1 pixel)
- Animated GIF (memory during processing)
- EXIF data containing PII (GPS coordinates)
- ZIP bomb disguised as image
- SVG with embedded JavaScript

Infrastructure-related:
- Concurrent uploads from same user
- Disk full during upload
- Partial upload (connection dropped)
- Multiple simultaneous uploads

I'm confident in these edge cases — file upload vulnerabilities are one of the OWASP top attack vectors.
</think>

File uploads are one of the most common attack vectors in web applications. Here's a systematic edge case analysis.

**Category 1: Content validation (security-critical)**
```python
# DON'T trust the file extension or Content-Type header
# Both are user-controlled and trivially spoofed

# BAD: trusting the extension
if filename.endswith('.jpg'):  # Attacker sends malware.php.jpg
    save(file)

# GOOD: validate actual content
import magic  # python-magic library

def validate_image(file_bytes: bytes) -> bool:
    mime = magic.from_buffer(file_bytes, mime=True)
    return mime in {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

# ALSO: re-process the image to strip any embedded content
from PIL import Image
import io

def sanitize_image(file_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert('RGB')  # Strip alpha, metadata, embedded content
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85)
    return output.getvalue()
```

**Category 2: Size and dimension limits**
```python
MAX_FILE_SIZE = 5 * 1024 * 1024   # 5MB
MAX_DIMENSION = 4096               # pixels
MIN_DIMENSION = 50                 # pixels

def validate_size(file_bytes: bytes) -> None:
    if len(file_bytes) == 0:
        raise ValueError("Empty file")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("File too large")

    img = Image.open(io.BytesIO(file_bytes))
    w, h = img.size

    if w > MAX_DIMENSION or h > MAX_DIMENSION:
        raise ValueError("Image dimensions too large")
    if w < MIN_DIMENSION or h < MIN_DIMENSION:
        raise ValueError("Image too small")
    if w * h > 20_000_000:  # Decompression bomb check
        raise ValueError("Image pixel count too high")
```

**Category 3: Filename attacks**
```python
import os
import uuid

# NEVER use the user-provided filename for storage
# Generate your own filename:
def safe_filename(original_name: str) -> str:
    # Ignore the original name entirely
    return f"{uuid.uuid4().hex}.jpg"

# If you MUST preserve the original name:
import re
def sanitize_filename(name: str) -> str:
    # Remove path components
    name = os.path.basename(name)
    # Remove null bytes
    name = name.replace('\x00', '')
    # Allow only safe characters
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    # Prevent double extensions (.jpg.php)
    name = name.split('.')[0] + '.jpg'  # Force single known extension
    # Limit length
    return name[:100]
```

**Category 4: Metadata privacy (GDPR concern)**
```python
# Images from phones contain EXIF data:
# - GPS coordinates (where the photo was taken)
# - Device model, serial number
# - Date/time
# - Thumbnail of original (even if cropped!)

# ALWAYS strip EXIF data:
def strip_exif(file_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(file_bytes))
    # Create new image without metadata
    data = list(img.getdata())
    clean = Image.new(img.mode, img.size)
    clean.putdata(data)
    output = io.BytesIO()
    clean.save(output, format='JPEG', quality=85)
    return output.getvalue()
```

**Category 5: Infrastructure edge cases**
```python
# Concurrent uploads — user uploads twice quickly
# → Use idempotent storage (overwrite, don't append)
# → Or queue uploads and process sequentially per user

# Partial upload — connection drops mid-upload
# → Set upload timeout
# → Clean up incomplete files (cron job or TTL on temp storage)

# Disk full during upload
# → Upload to object storage (S3), not local disk
# → Handle storage errors gracefully
```

**Complete validation checklist:**
```
- [ ] Validate actual content type (magic bytes, not extension)
- [ ] Enforce file size limit (reject before fully reading)
- [ ] Check image dimensions (prevent decompression bombs)
- [ ] Strip EXIF metadata (privacy)
- [ ] Generate new filename (prevent path traversal)
- [ ] Re-encode the image (strip embedded content)
- [ ] Serve from separate domain (prevent XSS from SVGs)
- [ ] Rate limit uploads per user
- [ ] Scan for malware (if high-security environment)
```'''
    ),
    (
        "thinking/meta-reasoning-edge-cases-concurrent-updates",
        r'''Two users are editing the same document simultaneously in our app. How do I handle conflicts? I'm currently using "last write wins."''',
        r'''<think>
Concurrent editing conflicts are a well-studied problem with multiple solution strategies depending on requirements. Let me think through the edge cases and approaches.

"Last write wins" problems:
- User A edits paragraph 1, User B edits paragraph 2
- B saves last, B's version overwrites A's paragraph 1 changes
- Work is silently lost — A doesn't know their changes were overwritten

The spectrum of solutions:
1. Pessimistic locking (one user at a time)
2. Optimistic concurrency control (detect conflicts, reject stale writes)
3. Operational Transform (Google Docs approach)
4. CRDTs (conflict-free replicated data types)

Each has different complexity and tradeoffs. I should present the edge cases that make "last write wins" dangerous, then present solutions in order of complexity.
</think>

"Last write wins" is the most dangerous conflict resolution strategy because it silently loses data. Let me walk through the edge cases and solutions.

**Why "last write wins" fails:**

```
Timeline:
  10:00:00  User A loads document (version 1)
  10:00:05  User B loads document (version 1)
  10:00:30  User A changes title, saves (version 2)
  10:00:35  User B changes body, saves (version 3)

Result: User B's save overwrites User A's title change
        User A's work is silently lost
        Neither user knows this happened
```

**Solution 1: Optimistic Concurrency Control (recommended starting point)**

Detect conflicts instead of overwriting:

```python
# Add a version number to your documents
# PUT /documents/123
{
    "title": "Updated title",
    "body": "...",
    "version": 5  # "I'm editing version 5"
}

# Server checks:
def update_document(doc_id, data, expected_version):
    current = db.get(doc_id)
    if current.version != expected_version:
        raise ConflictError(
            "Document was modified by another user",
            current_version=current.version,
            your_version=expected_version
        )
    db.update(doc_id, data, version=expected_version + 1)

# With SQL (atomic check-and-update):
UPDATE documents
SET title = $title, body = $body, version = version + 1
WHERE id = $id AND version = $expected_version;
-- If 0 rows affected → conflict detected
```

**Edge cases for optimistic concurrency:**
```
- Both users edit simultaneously → first save wins, second gets conflict error
- User leaves page open overnight → stale version, will conflict on save
- Auto-save every 30 seconds → increases conflict frequency
- Merge is needed → what does the user do with the conflict?
```

**Solution 2: Field-level merging (medium complexity)**

Instead of whole-document conflicts, track changes per field:

```python
# Track which fields each user changed
User A changed: {"title": "New Title"}
User B changed: {"body": "New Body"}

# If different fields → auto-merge (no conflict)
# If same field → ask user to resolve

def merge_changes(base, change_a, change_b):
    merged = dict(base)
    conflicts = {}
    all_fields = set(change_a.keys()) | set(change_b.keys())
    for field in all_fields:
        a_changed = field in change_a and change_a[field] != base.get(field)
        b_changed = field in change_b and change_b[field] != base.get(field)
        if a_changed and b_changed:
            conflicts[field] = {"a": change_a[field], "b": change_b[field]}
        elif a_changed:
            merged[field] = change_a[field]
        elif b_changed:
            merged[field] = change_b[field]
    return merged, conflicts
```

**Solution 3: Real-time collaboration (high complexity)**

If you need Google Docs-style simultaneous editing:
```
Options:
1. Operational Transform (OT) — used by Google Docs
   Complex to implement correctly, battle-tested
   Libraries: ShareDB, Yjs

2. CRDTs — used by Figma
   Mathematically guaranteed conflict-free
   Libraries: Yjs, Automerge

3. Use a service:
   - Liveblocks (real-time collaboration as a service)
   - Yjs + WebSocket (open source)
```

**Decision guide:**
```
Simple forms (settings, profiles):
  → Optimistic concurrency with version numbers
  → Show "modified by someone else, reload?" on conflict

Structured documents (articles, wikis):
  → Field-level merging + version numbers
  → Auto-merge when possible, prompt on field conflicts

Real-time text editing (docs, notes):
  → CRDTs or OT (Yjs, Automerge)
  → Significant engineering investment

Your current situation:
  → Start with optimistic concurrency control
  → It's a 1-day implementation that eliminates silent data loss
```

The most important thing is to **stop silently losing data**. Even showing a "conflict detected" error is better than "last write wins."'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
