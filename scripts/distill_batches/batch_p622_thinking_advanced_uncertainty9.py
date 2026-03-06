"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 9)"""

PAIRS = [
    (
        "thinking/uncertainty-sql-vs-nosql-for-user-profiles",
        "We're building a social platform. Should we use PostgreSQL or MongoDB for user profiles? Profiles have different fields depending on user type (personal, business, creator) and we add new fields frequently.",
        r'''<think>
SQL vs NoSQL for flexible user profiles. Let me think carefully.

**Arguments for MongoDB:**
- Schema flexibility: profiles with different fields per user type is natural in documents
- Adding new fields: no ALTER TABLE needed, just start writing the field
- Nested data: user preferences, settings, social links — all nested cleanly in one document
- Read performance: all profile data in one document read (no JOINs)

**Arguments for PostgreSQL:**
- JSONB column: gives schema flexibility WITHIN a relational database
- Relationships: social platform means users → friends, posts, messages, groups — all relational
- Transactions: friend requests, follows, blocks need ACID guarantees
- Mature ecosystem: better tooling, migration tools, ORM support
- Postgres scales well for read-heavy social workloads

**The specific use case details:**
- "Different fields depending on user type" — this is the MongoDB argument
  BUT: Postgres JSONB handles this equally well
- "Add new fields frequently" — MongoDB's schemaless approach helps
  BUT: Postgres JSONB is also schemaless for the flexible part
- "Social platform" — this is inherently relational (users, friendships, follows, posts, comments)

**My analysis:**
A social platform has TWO data characteristics:
1. User profile data: flexible, nested, varies by type → document-like
2. Social graph + content: relational (friends, posts, comments, likes) → relational

Postgres with JSONB handles BOTH. MongoDB handles #1 well but #2 poorly (no JOINs, no transactions across documents).

**Confidence:**
- 70% PostgreSQL with JSONB for profile flexibility
- 20% MongoDB for profiles + Postgres for relational data (polyglot persistence)
- 10% Pure MongoDB (if the social graph is simple and relationships are minimal)
</think>

For a social platform specifically, I'd recommend **PostgreSQL with JSONB** — confidence: **70%**.

## Why This Is My Recommendation

```
A social platform has TWO kinds of data:

1. PROFILE DATA (flexible, document-like):
   Personal: {name, bio, birthday, interests: [...]}
   Business: {company_name, industry, employee_count, tax_id}
   Creator:  {portfolio_url, monetization: {}, analytics: {}}
   → Different fields per type, changes frequently
   → BOTH MongoDB and Postgres JSONB handle this well

2. SOCIAL GRAPH (inherently relational):
   Users → Friends (many-to-many)
   Users → Posts → Comments → Likes (nested relationships)
   Users → Groups → Messages (complex relationships)
   Follow/Block/Mute relationships
   → JOINs, transactions, constraints are essential
   → PostgreSQL handles this natively. MongoDB struggles.
```

## PostgreSQL with JSONB: Best of Both Worlds

```sql
-- Fixed schema for core fields + JSONB for flexible data
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    user_type VARCHAR(20) NOT NULL,  -- 'personal', 'business', 'creator'
    display_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Flexible profile data as JSONB
    profile JSONB DEFAULT '{}',

    -- Indexes on JSONB fields you query frequently
    CONSTRAINT valid_profile CHECK (jsonb_typeof(profile) = 'object')
);

-- Index for querying JSONB fields
CREATE INDEX idx_users_profile_industry
    ON users USING GIN ((profile->'industry'));

-- Example data:
INSERT INTO users (email, user_type, display_name, profile) VALUES
('alice@example.com', 'personal', 'Alice', '{
    "bio": "Software developer",
    "interests": ["coding", "hiking"],
    "birthday": "1990-05-15",
    "social_links": {"twitter": "@alice", "github": "alice"}
}'),
('acme@example.com', 'business', 'Acme Corp', '{
    "industry": "Technology",
    "employee_count": 50,
    "tax_id": "XX-1234567",
    "headquarters": {"city": "Seattle", "country": "US"}
}');

-- Query JSONB naturally:
SELECT * FROM users
WHERE profile->>'industry' = 'Technology'
  AND (profile->>'employee_count')::int > 10;

-- Add new fields: just write them. No ALTER TABLE.
UPDATE users SET profile = profile || '{"verified": true}'
WHERE id = 42;
```

## Why Not Pure MongoDB (The 30% Case)

```
MongoDB would be fine for profiles ALONE.
But a social platform isn't just profiles:

-- This is natural in SQL:
SELECT u.display_name, COUNT(f.id) as friend_count
FROM users u
LEFT JOIN friendships f ON f.user_id = u.id
WHERE f.status = 'accepted'
GROUP BY u.id
HAVING COUNT(f.id) > 100;

-- Feed generation (show posts from friends):
SELECT p.*, u.display_name, u.profile->>'avatar_url'
FROM posts p
JOIN friendships f ON f.friend_id = p.author_id
JOIN users u ON u.id = p.author_id
WHERE f.user_id = 42 AND f.status = 'accepted'
ORDER BY p.created_at DESC
LIMIT 20;

-- In MongoDB, these require multiple queries or denormalization.
-- Social graphs are the textbook case for relational databases.
```

## When MongoDB WOULD Be Better

```
Choose MongoDB if:
  ✓ Profiles are the PRIMARY data (not social relationships)
  ✓ Each profile is read/written independently (no cross-profile queries)
  ✓ You don't need transactions across profiles
  ✓ The social graph is simple (follow/unfollow, no complex queries)
  ✓ You're at massive scale where horizontal sharding matters
    (MongoDB shards more easily than Postgres for write-heavy workloads)

Examples that fit MongoDB better:
  - CMS with varied content types
  - IoT device data (each device has different sensors)
  - Product catalog with varied attributes
  - Event logging / analytics storage
```

## Confidence Breakdown

```
70% PostgreSQL + JSONB:
  Handles both flexible profiles AND relational social data
  One database to operate, backup, and scale
  Mature ecosystem, great tooling

20% Polyglot (MongoDB for profiles + Postgres for relationships):
  Best of both worlds technically
  BUT: two databases to maintain, sync data between them, more operational burden
  Only worth it at significant scale

10% Pure MongoDB:
  If social features are minimal and profiles are the core product
  Or if team has deep MongoDB expertise and no Postgres experience
```'''
    ),
    (
        "thinking/uncertainty-build-vs-buy-auth",
        "Should we build our own authentication system or use Auth0/Clerk/Firebase Auth? We're a 4-person startup with a B2B SaaS product.",
        r'''<think>
Build vs buy auth for a 4-person B2B startup. Let me think carefully.

**Build your own:**
Pros:
- Full control over the auth flow
- No vendor lock-in
- No per-user pricing that scales with you
- Custom features (specific SSO requirements, custom MFA)

Cons:
- Security is HARD — one mistake = data breach
- Time to build: weeks/months (login, registration, password reset, MFA, social login, session management, email verification...)
- Ongoing maintenance: security patches, vulnerability monitoring
- A 4-person startup spending weeks on auth = not building their actual product

**Use Auth0/Clerk/Firebase Auth:**
Pros:
- Days instead of weeks/months to implement
- Security is their CORE BUSINESS — they're better at it than you
- MFA, social login, SSO out of the box
- Compliance certifications (SOC2, GDPR) included
- Your team can focus on the product

Cons:
- Cost: $0.50-3/user/month at scale (can get expensive)
- Vendor lock-in (auth is deeply integrated)
- Limited customization (their UI, their flow, their branding)
- Dependency on third party for core functionality
- B2B often needs SAML SSO — some providers charge extra for this

**For THIS company specifically:**
- 4-person startup: cannot afford to spend weeks on auth infrastructure
- B2B SaaS: will need SSO eventually (enterprise customers require it)
- Early stage: need to validate product, not build infrastructure

**My assessment:**
- 80% confidence: Use a third-party auth service
- 15%: Build your own (IF you have auth expertise on the team AND specific requirements)
- 5%: Hybrid (use an auth library like NextAuth/Passport.js — self-hosted but library-assisted)

For a 4-person startup, every week spent on auth is a week NOT spent on your product. The cost of Auth0 at startup scale ($0 for first 7,500 MAU) is trivially worth it compared to the cost of your developers' time.
</think>

For a 4-person B2B startup: **use a third-party auth service** — confidence: **80%**.

## The Build vs Buy Calculation

```
BUILDING AUTH YOURSELF:

Development time:
  Login/registration/logout:         1 week
  Password reset flow:               3 days
  Email verification:                2 days
  Session management (secure):       3 days
  Social login (Google, GitHub):     3 days
  MFA (TOTP, SMS):                  1 week
  SAML SSO (enterprise customers):  2-3 weeks
  Security audit and hardening:      1 week
  Total: 6-8 weeks of development

4-person startup: 6 weeks = 25% of your team's quarter.
That's 25% of your runway NOT building your actual product.

Cost: 6 weeks × $60K/yr salary ÷ 52 = ~$7K in developer time
      + ongoing maintenance, security patches, incident response

BUYING AUTH:

  Auth0 free tier:        7,500 MAU free
  Clerk:                  10,000 MAU free
  Firebase Auth:          50,000 MAU free (but limited features)
  Supabase Auth:          50,000 MAU free

  Implementation time: 1-3 days

  At 1,000 B2B users:    $0-50/month
  At 10,000 users:       $100-500/month
  At 100,000 users:      $500-3,000/month (this is a GOOD problem to have)

  For an early-stage startup: essentially free.
```

## B2B-Specific Considerations

```
Your enterprise customers WILL require:
  □ SAML SSO ("we need to log in with our Okta")
  □ SCIM user provisioning ("auto-create accounts from our directory")
  □ SOC2 compliance ("prove your auth is secure")
  □ Custom domains ("login.theircomain.com")
  □ Audit logs ("who logged in when")

Building all of this: 3-6 MONTHS of work.

Auth0 / WorkOS / Clerk:
  ✓ SAML SSO: checkbox configuration
  ✓ SCIM: built-in
  ✓ SOC2: they're already certified
  ✓ Custom domains: configuration
  ✓ Audit logs: built-in dashboard
```

## When to Build Your Own (The 15%)

```
Build your own auth IF:
  ✓ Auth IS your product (you're building an identity platform)
  ✓ You have a security engineer on the team
  ✓ You have specific requirements no provider supports
  ✓ Cost at scale is prohibitive (100K+ users × $1/user = $100K/month)
  ✓ You're past Series B and can afford the team to maintain it

Even then, consider: is your competitive advantage in auth?
If not, you're diverting engineering from your actual product.
```

## If You're Still Unsure: Decision Framework

```
QUESTION                                          BUILD    BUY
────────────────────────────────────────────────────────────────
Team size < 10?                                    ✗       ✓
Auth is core to your product?                      ✓       ✗
Need SSO within 6 months?                          ✗       ✓
Have a security engineer on staff?                 ✓       ✗
Pre-revenue or early revenue?                      ✗       ✓
Under 10,000 users?                                ✗       ✓
Over 100,000 users with cost pressure?             ✓       ✗
Enterprise customers requiring SOC2?               ✗       ✓
Custom auth flow (biometrics, hardware keys)?      ✓       ~
```

## Practical Recommendation

```
PHASE 1 (Now — months 0-12):
  Use Clerk or Auth0 free tier
  Implement in 1-2 days
  Focus 100% on building your product

PHASE 2 (When you hit scale — month 12-24):
  Evaluate: is auth cost > 5% of revenue?
  If no → stay with provider (most companies stay forever)
  If yes → plan migration (you'll have more team/resources by then)

PHASE 3 (If needed — month 24+):
  Migrate to self-hosted solution (Keycloak, Supertokens)
  Only if cost justifies it AND you have the team

The most expensive mistake a startup can make is building
infrastructure instead of product. Auth is infrastructure.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
