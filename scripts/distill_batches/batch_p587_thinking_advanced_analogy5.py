"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 5/8)"""

PAIRS = [
    (
        "thinking/analogy-dns-to-phonebook",
        "Can you explain DNS resolution in a way that would make sense to a non-technical person? I need to present this to business stakeholders.",
        r'''<think>
DNS resolution — I need an analogy that non-technical people can relate to. Let me think about what DNS actually does:

1. You type "google.com" in your browser
2. Your computer doesn't know google.com's IP address
3. It asks a DNS resolver (usually your ISP's)
4. The resolver checks its cache, then asks root servers, then TLD servers, then authoritative servers
5. Eventually gets back 142.250.80.46
6. Your browser connects to that IP

What real-world process works like this?

**Phone book analogy:**
- Domain name = person's name
- IP address = phone number
- DNS server = phone book / directory assistance
- Cache = your phone's contact list

This works well! But let me extend it to cover the hierarchy (root → TLD → authoritative):

1. You want to call "John Smith at Acme Corp in New York"
2. First check your phone contacts (local cache) — not there
3. Call directory assistance (recursive resolver)
4. They say "for New York businesses, call the NYC business directory" (root → TLD)
5. NYC business directory says "for Acme Corp, their receptionist number is..." (TLD → authoritative)
6. You get the phone number (IP address)
7. You save it in your contacts for next time (caching with TTL)

**Where the analogy works:**
- Hierarchical lookup ✓
- Caching ✓
- Human-readable name → machine-usable number ✓
- Multiple intermediaries ✓

**Where it breaks down:**
- Phone numbers don't change often; DNS records can change frequently (TTL)
- Phone books are centralized; DNS is distributed
- DNS has different record types (A, CNAME, MX) — phone books don't have equivalents
- DNS can do load balancing (multiple IPs for one name)

For a business audience, keep it simple and focus on the core concept.
</think>

Think of DNS like **calling directory assistance to find a phone number** — except the directory is organized in layers.

## The Analogy

**The problem:** You want to call John Smith at Acme Corp in New York, but you don't have his number.

| Real World | DNS |
|-----------|-----|
| Person's name ("John Smith at Acme Corp") | Domain name (`www.acme.com`) |
| Phone number (212-555-0100) | IP address (93.184.216.34) |
| Your phone's contact list | Your computer's DNS cache |
| Directory assistance operator | DNS resolver (usually your ISP) |

## How the Lookup Works

```
You: "I need to reach www.acme.com"

Step 1: Check your contacts (local cache)
   → Not saved. Ask directory assistance.

Step 2: Call directory assistance (DNS resolver)
   → "I don't know that one either. Let me make some calls."

Step 3: Resolver calls the global switchboard (root DNS server)
   → "For .com names, contact the .com directory."

Step 4: Resolver calls .com directory (TLD server)
   → "For acme.com, their operator is at ns1.acme.com."

Step 5: Resolver calls Acme's operator (authoritative DNS server)
   → "www.acme.com is at 93.184.216.34."

Step 6: Resolver tells you the number. You save it in your contacts
   for next time (cached for a set period, like "valid for 1 hour").
```

## Why This Matters for Business

- **When DNS is slow:** It's like directory assistance putting you on hold — your customers wait before they even reach your website
- **When DNS goes down:** It's like the phone directory going offline — nobody can look up your number even though your phones are working fine (this happened to major sites when Dyn DNS was attacked in 2016)
- **DNS TTL (cache duration):** When you move offices and get a new phone number, it takes time for all the directories to update — during a migration, some customers might still call the old number

## Where This Analogy Has Limits

For the technical team's benefit: DNS also handles things phone directories don't — like pointing mail to a different server (MX records), aliasing one name to another (CNAME), and returning different numbers to different callers for load balancing. But for understanding the core concept, the directory assistance model covers 90% of what stakeholders need to know.'''
    ),
    (
        "thinking/analogy-oauth-to-hotel-keycard",
        "I need to explain OAuth 2.0 to junior developers who keep confusing authentication vs authorization. What's a good way to think about it?",
        r'''<think>
OAuth 2.0 is one of the most commonly confused protocols. The key confusion points:
- Authentication (who you are) vs authorization (what you're allowed to do)
- The role of the authorization server vs the resource server
- Why the user's password never goes to the third-party app
- Access tokens vs refresh tokens

I need an analogy that captures ALL of these. Let me think...

**Hotel keycard analogy:**
- Guest (Resource Owner / User)
- Hotel front desk (Authorization Server)
- Hotel room (Resource Server / Protected Resource)
- Keycard (Access Token)
- Room service app (Third-Party Client Application)

The flow:
1. You (guest) check into the hotel (authenticate with the authorization server)
2. Front desk gives you a keycard (access token) that opens YOUR room
3. Room service app needs to deliver food to your room — you don't give them your ID or the master key
4. Instead, you go to the front desk and say "give room service a temporary card for my room, but only for delivery access, not minibar"
5. Front desk issues a LIMITED keycard (scoped access token) to room service
6. Room service uses that card to access your room, but can't open the safe or other rooms

This captures:
- Authentication (checking in with ID) ✓
- Authorization (keycard with limited access) ✓
- Scopes (delivery access but not minibar) ✓
- Token expiry (keycard expires at checkout) ✓
- No password sharing (room service never sees your ID) ✓
- Resource server vs auth server (room vs front desk) ✓

**Where it breaks down:**
- Hotel keycards are physical; tokens are digital and can be copied
- OAuth has redirect flows; hotels don't redirect you
- Refresh tokens don't have a clean hotel equivalent
- The consent screen concept is a stretch

Let me map the OAuth flows to the hotel scenario.
</think>

The best analogy for OAuth 2.0 is a **hotel keycard system**. It cleanly separates authentication from authorization and shows why passwords are never shared.

## The Cast of Characters

| OAuth Concept | Hotel Analogy |
|--------------|--------------|
| **You** (Resource Owner) | Hotel guest |
| **Your Data** (Protected Resource) | Your hotel room & belongings |
| **Google/GitHub** (Authorization Server) | Hotel front desk |
| **Third-Party App** (Client) | Room service / housekeeping |
| **Access Token** | Keycard |
| **Scopes** | Keycard permissions (room only, no safe, no minibar) |
| **Token Expiry** | Checkout time on the keycard |

## The Flow (Authorization Code Grant)

```
WRONG WAY (sharing passwords):
  Room service: "What's your room number and ID?"
  You: "Room 405, here's my driver's license"
  Room service: *now has your identity AND full room access*
  ❌ They could copy your ID, access your safe, come back anytime

OAUTH WAY (keycard delegation):

1. Room service app: "I need to deliver food to your room"
   → App redirects you to the hotel front desk

2. Front desk (Authorization Server): "Can I see your ID?"
   → You authenticate directly with the front desk (login page)
   → Room service NEVER sees your ID

3. Front desk: "Room service wants access to deliver to your room.
               Allow: room entry for delivery? [Yes/No]"
   → This is the CONSENT SCREEN

4. You: "Yes, delivery access only"

5. Front desk creates a LIMITED keycard:
   - Opens room 405 ✓
   - Delivery hours only (10am-10pm) ✓
   - Cannot open safe ✗
   - Cannot access minibar ✗
   - Expires in 1 hour ✓
   → This is the ACCESS TOKEN with SCOPES

6. Front desk gives the keycard to room service
   → Room service can now deliver food without knowing who you are
```

## The Key Insights This Teaches

### Authentication ≠ Authorization
```
Authentication: Showing your ID at the front desk
  → "You ARE John Smith" (identity verification)

Authorization: The keycard you're given
  → "You CAN open room 405" (permission grant)

OAuth is about AUTHORIZATION — the third-party app
never authenticates you. The front desk does that.
```

### Why Scopes Matter
```python
# OAuth scopes are like keycard permissions
scopes = ["room:enter", "room:delivery"]  # Can enter for delivery

# NOT included:
# "room:safe"    — can't open the safe
# "room:minibar" — can't access minibar
# "hotel:pool"   — can't use the pool
# "hotel:spa"    — can't charge to the room

# In real OAuth:
# scope=read:user — can read profile
# scope=repo      — can access repositories
# scope=write:org — can modify organization (dangerous!)
```

### Token Expiry and Refresh
```
Access Token = Day keycard
  → Works for a few hours, then stops working
  → Room service must go back to the front desk for a new one

Refresh Token = VIP guest card
  → Lets you get new day keycards without showing ID again
  → Valid for the duration of your stay
  → If stolen, front desk can revoke it (you report it lost)
```

## Where the Analogy Breaks Down

Be upfront with juniors about the limits:
1. **Redirect flow**: In real OAuth, you're "redirected" to the auth server's login page — hotels don't redirect you physically, but the concept of "go talk to the front desk directly" maps reasonably
2. **Token copying**: Digital tokens can be intercepted (HTTPS prevents this); keycards are physical
3. **Multiple resource servers**: OAuth tokens can work across different APIs — like a keycard working at multiple hotel chains (federated identity)

Start with this analogy, then move to actual code. Juniors who understand the hotel model rarely confuse auth*entication* with auth*orization* again.'''
    ),
    (
        "thinking/analogy-microservices-to-restaurant-kitchen",
        "We're moving from a monolith to microservices. The team is excited but I'm worried they don't understand the operational complexity they're signing up for. How do I explain the trade-offs?",
        r'''<think>
Microservices vs monolith — I need an analogy that shows BOTH the benefits AND the often-underestimated costs.

**Restaurant kitchen analogy:**

Monolith = One big kitchen with all cooks working together
- One head chef oversees everything
- Cooks share ingredients, tools, and counter space
- Communication is instant (just talk to each other)
- If the oven breaks, nobody can bake
- If you want to change the dessert menu, you have to work around the dinner prep

Microservices = Multiple specialized food stations (like a food court)
- Pizza station, sushi station, burger station, dessert station
- Each has its own chef, ingredients, equipment
- They operate independently
- But... how does a customer order a meal that combines pizza AND sushi?
- And who makes sure the pizza doesn't arrive 20 minutes before the sushi?

**Where this works well:**
- Independent scaling (pizza station can add more ovens without affecting sushi)
- Independent deployment (change the burger recipe without touching pizza)
- Team autonomy (pizza team doesn't need to coordinate with sushi team for most changes)
- Fault isolation (if pizza oven breaks, sushi still works)

**The hidden costs the analogy reveals:**
- Order coordination (distributed transactions / saga pattern)
- Delivery timing (eventual consistency)
- Shared ingredients problem (shared data / data duplication)
- Customer confusion ("I ordered from three stations, who do I complain to?")
- Quality control across stations (observability, tracing)
- Supply chain management (dependency management, versioning)
- Rent for multiple kitchens (infrastructure costs)

This analogy is great because it naturally leads to understanding WHY microservices are hard — the coordination overhead is obvious in a food court.
</think>

Think of it as going from **one big restaurant kitchen** to a **food court with specialized stations**. The analogy reveals both the appeal AND the hidden operational costs.

## The Monolith: One Kitchen

```
┌─────────────────────────────────────┐
│           RESTAURANT KITCHEN         │
│                                     │
│  👨‍🍳 All cooks share:              │
│    - Same ingredients (database)    │
│    - Same counter space (memory)    │
│    - Same recipe book (codebase)    │
│    - Same head chef (deployment)    │
│                                     │
│  ✅ Easy communication (just talk)  │
│  ✅ One supply order (one deploy)   │
│  ✅ One quality check (one test)    │
│  ❌ Can't change stove without      │
│     stopping everything             │
│  ❌ One cook's mess affects all     │
└─────────────────────────────────────┘
```

## Microservices: Food Court

```
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 🍕 PIZZA │ │ 🍣 SUSHI │ │ 🍔 BURGER│
│ Station  │ │ Station  │ │ Station  │
│          │ │          │ │          │
│ Own oven │ │ Own fish │ │ Own grill│
│ Own chef │ │ Own chef │ │ Own chef │
│ Own menu │ │ Own menu │ │ Own menu │
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │
     └──────┬─────┘────────────┘
            │
     ┌──────┴──────┐
     │ FOOD COURT  │  ← This coordination layer
     │  MANAGER    │    is the part teams forget
     └─────────────┘    to budget for
```

## The Hidden Costs Your Team Needs to Hear

### 1. The "Combo Meal" Problem (Distributed Transactions)
```
Customer: "I want pizza AND sushi, served together."

Monolith: Chef makes both, plates together. Simple.

Microservices:
- Pizza station starts making pizza
- Sushi station starts making sushi
- Pizza is ready in 8 minutes, sushi in 15
- Customer waits with cold pizza? Or pizza station holds it?
- What if sushi station runs out of fish mid-order?
  → Does pizza station un-make the pizza? (rollback)
  → Or serve pizza alone? (partial failure)

This is the SAGA PATTERN. Every cross-service operation
needs a choreographed sequence with compensating actions.
```

### 2. The "Shared Ingredients" Problem (Data Ownership)
```
Both pizza and burger stations need cheese.

Monolith: One fridge, everyone grabs cheese.

Microservices:
- Option A: Shared fridge (shared database) → defeats the purpose
- Option B: Each station stocks own cheese (data duplication)
  → Pizza station thinks there's plenty of mozzarella
  → Burger station already used it all
  → Nobody has the "true" cheese inventory

This is the data consistency problem. Every shared entity
needs a clear owner, and others get COPIES that may be stale.
```

### 3. The "Who Dropped the Order?" Problem (Observability)
```
Customer: "My order is wrong!"

Monolith: Check the kitchen log. One place to look.

Microservices:
- Was it the order-taking service?
- The pizza station?
- The delivery coordination service?
- The billing service?
- Need to trace the order across ALL stations
  with a tracking number (distributed tracing / correlation IDs)
```

### 4. The "Staffing" Problem (Operational Overhead)
```
Monolith: 1 kitchen manager, 1 supply chain, 1 health inspection.

Microservices: Each station needs:
- Its own manager (on-call rotation per service)
- Its own supply chain (CI/CD pipeline per service)
- Its own health inspection (monitoring per service)
- Its own recipe versioning (API contracts)

With 5 stations: 5x the operational overhead.
```

## The Decision Framework for Your Team

| You NEED microservices if... | You DON'T if... |
|---|---|
| Different parts need to scale independently (pizza is 10x more popular) | Everything scales roughly together |
| Teams are large enough to own services (2+ devs per service) | You have < 15 developers |
| Different parts have different uptime requirements | Everything can tolerate the same SLA |
| You need to deploy parts independently multiple times/day | Deploying together weekly is fine |

**The uncomfortable truth:** if your team is excited about microservices but hasn't budgeted for distributed tracing, service mesh, CI/CD per service, and on-call per service, they're signing up for the food court's rent without the food court's management team.

Start with a **well-structured monolith** (clear module boundaries, like stations within ONE kitchen), and extract services only when you have a specific scaling or team-autonomy reason.'''
    ),
    (
        "thinking/analogy-git-branching-to-parallel-universes",
        "How do I explain Git branching to designers and project managers who don't code? They need to understand our branching workflow to coordinate releases.",
        r'''<think>
Git branching for non-technical people. I need an analogy that captures:
- Branches as parallel streams of work
- Merging as combining changes
- Conflicts as incompatible changes
- Main branch as the "real" version

**Parallel universes / timelines analogy:**
This is intuitive and matches well:
- `main` = the "real world" — what customers see
- Branch = a parallel universe where you can experiment
- Merge = bringing changes from the parallel universe back to reality
- Conflict = two universes changed the same thing differently

**Document editing analogy might be simpler:**
Like Google Docs, but instead of everyone editing the same document:
- You make a COPY of the document
- Work on your copy independently
- When done, ask someone to review your changes
- They merge your edits back into the original

Actually, let me combine both. The parallel universe idea is more intuitive for the branching concept, and the document analogy helps explain conflicts.

For project managers, the key concepts are:
1. What is a branch? (parallel workspace)
2. What is a PR? (request to merge changes)
3. What are conflicts? (two people changed the same thing)
4. What is main? (production-ready code)
5. What is a release branch? (a snapshot being prepared for release)
</think>

Think of Git branches as **parallel copies of the project** — like having multiple drafts of a document that can be edited independently and combined later.

## The Analogy: Drafting a Company Report

```
MAIN BRANCH = The published report (what customers see)
              Everyone agrees this is the "official" version.

FEATURE BRANCH = A working draft
                 "I'm going to try rewriting Chapter 3."
                 You make a copy, edit freely, without affecting
                 the published version.

PULL REQUEST = Submitting your draft for review
               "I've finished my Chapter 3 rewrite.
                Can someone review it before we publish?"

MERGE = Incorporating the approved draft
        Your Chapter 3 rewrite replaces the old one
        in the published report.

CONFLICT = Two people edited the same paragraph
           Alice rewrote the intro paragraph.
           Bob also rewrote the intro paragraph.
           Someone needs to decide which version to keep
           (or combine both).
```

## Your Release Workflow, Translated

```
Week 1-2: Writing Phase
┌─────────────────────────────────────────┐
│ Published Report (main)                  │
├──────────┬──────────┬───────────────────┤
│ Alice's  │ Bob's    │ Carol's           │
│ draft    │ draft    │ draft             │
│ (Ch. 3)  │ (Ch. 5)  │ (new appendix)   │
│          │          │                    │
│ Working  │ Working  │ Working           │
│ ...      │ ...      │ ...               │
│ Done! ✓  │ Done! ✓  │ Still working     │
└──────────┴──────────┴───────────────────┘

Week 3: Review Phase
  Alice's draft → Reviewed → Approved → Merged into report ✓
  Bob's draft   → Reviewed → "Fix the chart on p.12" → Revised → Merged ✓
  Carol's draft → Still working (goes in NEXT release)

Week 4: Release
  Published report now includes Alice's and Bob's changes.
  Carol's work continues separately for the next cycle.
```

## Key Concepts for Coordination

### For Project Managers:
```
"Is this feature in the release?"
  → Is the draft merged into the published version? Check the PR status.

"Can we delay this feature?"
  → Don't merge that draft yet. It stays as a separate copy
    and doesn't affect the release.

"Two features conflict"
  → Two people edited the same section. A developer will
    combine both changes manually. It takes 30 minutes, not days.

"Can we undo a feature after release?"
  → Yes, like reverting to the previous edition of the report.
    The old version is always saved.
```

### For Designers:
```
"Where should I put my design assets?"
  → In the same draft (branch) as the feature they belong to.
    They travel together through review and release.

"I updated the icon but it's not live yet"
  → Your draft hasn't been merged into the published version.
    Check with the developer on the PR status.
```

## Common Branching Workflows, Translated

| Workflow | Report Analogy |
|----------|---------------|
| **Feature branch** | Each person works on their own copy of the relevant chapter |
| **Release branch** | "Lock the report for final proofreading — new chapters go in the NEXT edition" |
| **Hotfix** | "There's a typo in the published report — fix it directly, don't wait for the next edition" |
| **Code freeze** | "No more drafts accepted — we're finalizing this edition" |

The core idea: everyone works on their own copy, changes are reviewed before publishing, and the published version is always stable. That's Git branching in a nutshell.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
