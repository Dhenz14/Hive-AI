"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 7/8)"""

PAIRS = [
    (
        "thinking/firstprinciples-why-immutability",
        "Why do functional programmers love immutability so much? What's wrong with just mutating variables? It seems like extra work for no benefit.",
        r'''<think>
Immutability from first principles. Let me derive WHY it matters rather than just saying "it's good."

**The root problem: shared mutable state**
When multiple parts of your code can read AND modify the same data, bugs arise from unexpected changes.

**Step 1: In a single-threaded world**
```
user = {"name": "Alice", "role": "admin"}
process_user(user)
# What is user["role"] now?
# Did process_user modify it? Who knows without reading process_user's code.
```

With mutation, you can't reason about a variable's value without tracing every function that touches it. In a large codebase, this becomes impossible.

**Step 2: In a multi-threaded world**
```
# Thread A: user["balance"] -= 100
# Thread B: user["balance"] -= 50
# Race condition! Final value depends on timing.
```

With mutation + concurrency, bugs become timing-dependent and nearly impossible to reproduce.

**Step 3: What immutability gives you**
If data can't change after creation:
- No race conditions (nobody modifies shared data)
- No spooky action at a distance (function can't change your data)
- Time travel debugging (old values still exist)
- Safe sharing (pass references freely — nobody will modify them)
- Easier testing (no setup/teardown of mutable state)

**Step 4: The cost**
- Creating new objects instead of modifying old ones → more allocations
- Performance overhead for frequent updates (games, real-time systems)
- Structural sharing mitigates this (persistent data structures)

**First principle: Immutability trades write convenience for read safety.**

In most applications, data is read far more than it's written. Optimizing for read safety (immutability) over write convenience (mutation) is the right trade-off for most software.
</think>

Let me derive the value of immutability from the problems mutation causes.

## The Root Problem: You Can't Trust Mutable Data

```python
# WITH MUTATION: what's the value of `order` after this?
order = {"items": ["book", "pen"], "total": 25.00}
apply_discount(order)
validate_order(order)
calculate_shipping(order)

# What is order["total"] now?
# Did apply_discount modify it? Did validate_order add a field?
# Did calculate_shipping remove an item?
# You don't know without reading ALL THREE functions.

# In a large codebase: 20 functions touch this dict.
# Good luck tracing mutations.
```

```python
# WITH IMMUTABILITY: each step returns a NEW value
order = {"items": ["book", "pen"], "total": 25.00}
discounted = apply_discount(order)       # order unchanged
validated = validate_order(discounted)    # discounted unchanged
final = calculate_shipping(validated)     # validated unchanged

# You can ALWAYS inspect any intermediate state.
# order is STILL {"items": ["book", "pen"], "total": 25.00}
# No function can surprise you by changing it.
```

## Problem 1: Spooky Action at a Distance

```python
# ❌ MUTATION: function silently modifies your data
def format_for_display(user):
    user["name"] = user["name"].upper()  # MUTATES the original!
    return user

user = {"name": "Alice", "email": "alice@example.com"}
display = format_for_display(user)
print(user["name"])  # "ALICE" — SURPRISE! Your data was modified.

# Did you expect format_for_display to change your user dict?
# Probably not. But mutation lets any function change anything
# passed to it, anywhere, at any time.
```

```python
# ✅ IMMUTABILITY: function returns new data, leaves original alone
def format_for_display(user):
    return {**user, "name": user["name"].upper()}  # NEW dict

user = {"name": "Alice", "email": "alice@example.com"}
display = format_for_display(user)
print(user["name"])  # "Alice" — unchanged, as expected
```

## Problem 2: Concurrency Nightmares

```python
# ❌ MUTATION + THREADS: race conditions
shared_list = []

# Thread A                    # Thread B
shared_list.append("a")      shared_list.append("b")
# What order? Depends on timing. Hard to reproduce, hard to debug.

# Worse with complex mutations:
shared_config = {"retries": 3, "timeout": 30}
# Thread A updates retries
# Thread B reads retries while A is mid-update
# Thread B gets inconsistent state
```

```python
# ✅ IMMUTABILITY: no shared mutable state = no race conditions
from dataclasses import dataclass, replace

@dataclass(frozen=True)  # frozen = immutable
class Config:
    retries: int = 3
    timeout: int = 30

config = Config()
# Thread A: new_config = replace(config, retries=5)  # Creates NEW Config
# Thread B: reads config — still retries=3, always consistent
# No locks needed. No race conditions possible.
```

## Problem 3: Debugging is Harder with Mutation

```python
# ❌ MUTATION: "what was the state before the bug?"
orders = load_orders()
process_orders(orders)         # Mutated orders
apply_refunds(orders)          # Mutated again
# Bug report: "order #42 has wrong total"
# What was order #42's total at each step?
# You have NO WAY TO KNOW — intermediate states are gone.

# ✅ IMMUTABILITY: time travel
orders_v1 = load_orders()
orders_v2 = process_orders(orders_v1)     # v1 still exists
orders_v3 = apply_refunds(orders_v2)      # v1 and v2 still exist
# Bug report: "order #42 has wrong total"
# Check v1 (original), v2 (after processing), v3 (after refunds)
# Instantly find which step introduced the bug.
```

## "But Isn't Immutability Slow?"

```python
# Common concern: creating new objects = more allocations = slow?

# For most apps: the overhead is negligible.
# Creating a new dict: ~100 nanoseconds
# Database query: ~1,000,000 nanoseconds (10,000x more)
# Network call: ~10,000,000 nanoseconds (100,000x more)

# For performance-critical code: use structural sharing
# Libraries like immer (JS) or pyrsistent (Python) reuse unchanged parts:

# Naive immutable update (copies everything):
new_list = old_list + [new_item]  # O(n) — copies entire list

# Structural sharing (smart immutable update):
# Only the changed path is new; rest shares memory with original
# O(log n) — used by Clojure, Scala, Haskell, immer.js
```

## When Mutation IS Appropriate

```
USE MUTATION when:
  - Performance-critical inner loops (game engines, real-time audio)
  - Local variables that never escape the function
  - Builder patterns (accumulate state, then freeze)
  - Working with I/O (files, network — inherently stateful)

USE IMMUTABILITY when:
  - Data shared between functions/modules/threads
  - State that flows through a pipeline
  - Configuration objects
  - Data passed to callbacks or event handlers
  - Anything stored in a cache or map

THE RULE: mutable by default is fine for local variables.
Immutable by default is better for shared state.
```

## First Principle Summary

```
Immutability = trading write convenience for read safety.

Most software reads data MORE than it writes data.
  - User object created once, read hundreds of times
  - Config loaded once, read thousands of times
  - HTTP request parsed once, accessed by many middleware

Optimizing for read safety (immutability) over write convenience
(mutation) is the right trade-off for most software.

Mutation is like a global GOTO — powerful, fast, and the source
of an entire class of bugs that simply cannot exist with immutability.
```'''
    ),
    (
        "thinking/firstprinciples-why-https-exists",
        "Why does HTTPS exist? I know HTTP is 'insecure' but what specifically can go wrong? My site doesn't handle passwords or credit cards, so do I even need it?",
        r'''<think>
HTTPS from first principles. Let me derive the threats that HTTPS prevents, starting from how HTTP works.

**HTTP: plain text over the network**
When you visit http://example.com, your browser sends a request and receives a response. Both are plain text traveling through multiple networks.

**The path of an HTTP request:**
Your device → your router → your ISP → [many routers/switches] → website's server

At EVERY hop, the data can be:
1. READ (eavesdropping)
2. MODIFIED (tampering)
3. INTERCEPTED and replaced (impersonation)

**Threat 1: Eavesdropping (confidentiality)**
Anyone on the same Wi-Fi, your ISP, any network hop can READ your traffic.
- Coffee shop Wi-Fi: the person next to you sees your requests
- ISP: can see every page you visit, every form you submit
- Government: can monitor traffic at backbone level

Even without passwords: your browsing history, search queries, medical information, political reading, financial info — all visible.

**Threat 2: Tampering (integrity)**
Any hop can MODIFY the content in transit.
- ISP injects ads into web pages (actually happened with Comcast, AT&T)
- Malicious router changes download links to malware
- Wi-Fi operator modifies form submissions

Even without credit cards: if your site serves a download, someone can replace it with malware.

**Threat 3: Impersonation (authentication)**
How do you know you're talking to the REAL example.com?
- DNS poisoning: redirect your domain to attacker's server
- Wi-Fi evil twin: fake access point that serves fake pages
- Without HTTPS, there's no way to verify the server's identity

**So HTTPS provides three things:**
1. Encryption (confidentiality) — traffic can't be read
2. Integrity — traffic can't be modified
3. Authentication — you're talking to the real server (via certificates)

**Does the user's site need it?**
YES, even without passwords or credit cards, because:
- SEO: Google penalizes HTTP sites
- Browser warnings: Chrome shows "Not Secure" for HTTP
- ISP injection: your content can be modified in transit
- User privacy: browsing history is visible
- Mixed content: HTTPS sites can't load HTTP resources
- New web APIs require HTTPS (geolocation, service workers, etc.)

And: Let's Encrypt makes it free and automated. There's no reason NOT to use HTTPS.
</think>

Even without passwords or credit cards, you need HTTPS. Let me show you why by tracing what happens without it.

## How HTTP Actually Works (The Problem)

```
Your HTTP request travels through:

  Your laptop
    → Your router  (can read everything)
    → Your ISP     (can read AND modify everything)
    → Internet backbone (multiple hops, each can read)
    → Website's server

Every step of this journey, your data is PLAIN TEXT.
Like sending a postcard — everyone who handles it can read it.

HTTPS = putting the postcard in a LOCKED BOX.
Only your browser and the server have the key.
```

## Threat 1: Anyone Can READ Your Traffic

```
ON HTTP (plain text):

Coffee shop Wi-Fi:
  You visit: http://health-info.com/depression-symptoms
  Person with laptop nearby sees: "User at 192.168.1.42 visited
  /depression-symptoms"

Your ISP:
  You search: http://search.com/q=divorce+lawyer+near+me
  ISP logs: "Customer #42391 searched for divorce lawyers at 11:42pm"
  ISP can SELL this browsing data (legal in many jurisdictions)

Employer network:
  You visit: http://indeed.com/jobs/software-engineer
  IT department sees: "Employee Dan is job hunting"

"My site doesn't handle passwords..."
  Your USERS' browsing patterns are still private information.
  Even reading a blog: the TOPICS someone reads reveal personal info.
```

## Threat 2: Anyone Can MODIFY Your Content

```
ON HTTP (no integrity verification):

ISP ad injection (this actually happened):
  Your site serves: <html><body>Welcome to my blog...</body></html>
  ISP modifies it to: <html><body><script src="isp-ads.js"></script>
                       Welcome to my blog...</body></html>
  User sees: your site with ads YOU didn't put there.

  Real examples:
  - Comcast injected JavaScript to show data cap warnings
  - Hotel Wi-Fi injected ads into guests' web browsing
  - Chinese ISPs injected cryptocurrency mining scripts

Download tampering:
  Your site offers: http://mysite.com/download/myapp.exe
  Attacker modifies: the download is replaced with malware
  User downloads: malware that looks like your app
  "But I don't handle passwords" — you don't have to.
  You just distributed malware to your users.
```

## Threat 3: Anyone Can IMPERSONATE Your Site

```
ON HTTP (no server authentication):

DNS poisoning:
  User types: http://mysite.com
  Attacker corrupts DNS: mysite.com → 6.6.6.6 (attacker's server)
  User sees: a perfect copy of your site (with malware/phishing)
  User thinks they're on YOUR site.

Evil twin Wi-Fi:
  Coffee shop: "Free_Coffee_WiFi" (legitimate)
  Attacker:    "Free_Coffee_WiFi" (fake, same name)
  User connects to fake → ALL HTTP traffic goes through attacker
  Attacker serves fake versions of every site

HTTPS prevents this because:
  Certificate proves: "This server IS mysite.com, verified by
  Let's Encrypt / DigiCert / etc."
  Fake server can't get a valid certificate for YOUR domain.
```

## What HTTPS Actually Does (The Three Guarantees)

```
1. ENCRYPTION (confidentiality):
   Traffic is encrypted end-to-end.
   Anyone in the middle sees: aN9x+Kf3...meaningless bytes
   Can't read your users' requests or your responses.

2. INTEGRITY (tamper-proof):
   Any modification is detected and rejected.
   ISP can't inject ads. Router can't modify downloads.
   What you send = what the user receives. Guaranteed.

3. AUTHENTICATION (identity verification):
   Certificate proves the server is who it claims to be.
   Browser shows: 🔒 mysite.com (verified by Let's Encrypt)
   Fake servers can't forge this.
```

## "But My Site Doesn't Need It" — Yes It Does

```
Even for a static blog with no login:

1. SEO: Google ranks HTTPS sites higher than HTTP
2. Browser UI: Chrome shows "Not Secure" warning on HTTP sites
3. Modern APIs: Geolocation, Service Workers, Push Notifications,
   Clipboard API, WebUSB all REQUIRE HTTPS
4. Referrer data: HTTPS→HTTP transitions strip the Referrer header
   (you lose analytics data)
5. ISP injection: your content can be modified without HTTPS
6. User privacy: your visitors' reading habits are their business
7. Trust: "Not Secure" warning makes users leave

Cost of HTTPS: $0 (Let's Encrypt) + 5 minutes setup
Cost of NOT using HTTPS: SEO penalty + user distrust + security risks
```

## How to Set Up HTTPS (It's Free)

```bash
# With Let's Encrypt + Certbot (most common):
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mysite.com -d www.mysite.com
# Done. Auto-renews every 90 days.

# With Cloudflare (even easier):
# Point DNS to Cloudflare → enable "Full (strict)" SSL
# Cloudflare provides free HTTPS + CDN

# With any modern hosting (automatic):
# Netlify, Vercel, GitHub Pages, Railway, Fly.io
# All provide HTTPS by default. Zero configuration.
```

There is no legitimate reason to serve a website over HTTP in 2026. HTTPS is free, fast (HTTP/2 requires it), and protects both you and your users.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
