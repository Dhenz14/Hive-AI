"""Phase 3F: Metacognition -- Code Quality Judgment (Part 7)

Rate code security with threat modeling: OWASP-style analysis of common
vulnerability patterns including sequential tokens, GraphQL depth bombs,
localStorage sessions, wildcard CORS, and XXE attacks.
"""

PAIRS = [
    (
        "thinking/meta-quality-security-sequential-reset-tokens",
        r'''Rate the security of this password reset endpoint (1-10):

```python
import time

reset_counter = 0

def generate_reset_token(user_id):
    global reset_counter
    reset_counter += 1
    return f"reset-{user_id}-{reset_counter}-{int(time.time())}"

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = request.form["email"]
    user = db.users.find_one({"email": email})
    if user:
        token = generate_reset_token(user["_id"])
        db.password_resets.insert_one({
            "token": token,
            "user_id": user["_id"],
        })
        send_reset_email(email, token)
    return jsonify({"message": "If that email exists, a reset link was sent."})
```''',
        r'''<think>
Let me analyze this password reset endpoint for security vulnerabilities.

Token generation: The token is constructed as `reset-{user_id}-{counter}-{timestamp}`. Every component is predictable:
- user_id: often a MongoDB ObjectId which is partially guessable
- counter: sequential integer, trivially enumerable
- timestamp: the attacker knows approximately when the request was made

This means an attacker can brute-force or predict valid tokens with minimal effort. A proper token should use cryptographically secure random bytes (e.g., `secrets.token_urlsafe(32)`).

No expiration: The reset document has no TTL or expiry field, so tokens are valid forever once created.

No rate limiting: An attacker can flood the endpoint to enumerate valid emails via timing side-channels or to spam users.

No token hashing: Tokens are stored in plaintext in the database. A database leak exposes all active reset tokens.

The generic response message is good -- it prevents email enumeration via response content. But the other issues are severe.

Score: 2/10. The predictable token alone is critical. Combined with no expiration and no hashing, this is highly exploitable.
</think>

**Security: 2/10**

| Criterion               | Rating  | Notes                                        |
|--------------------------|---------|----------------------------------------------|
| Token entropy            | 1/10    | Fully predictable: sequential counter + timestamp |
| Token storage            | 2/10    | Stored in plaintext; DB leak = full compromise |
| Token expiration         | 1/10    | No TTL; tokens valid indefinitely             |
| Rate limiting            | 2/10    | No throttle on reset requests                 |
| Enumeration resistance   | 8/10    | Generic response message is correct           |
| OWASP A07 (Auth Failure) | FAIL    | Predictable credentials                       |

**What's good:**
- The response message does not reveal whether the email exists, which resists user enumeration.

**What's critically wrong:**
1. **Predictable tokens (CRITICAL):** The token format `reset-{uid}-{counter}-{timestamp}` is fully deterministic. An attacker who triggers a reset can guess the counter range and timestamp window to brute-force valid tokens.
2. **No expiration:** Tokens never expire, giving attackers unlimited time to guess or use stolen tokens.
3. **Plaintext token storage:** If the database is compromised, all pending reset tokens are immediately usable.

**Fixed version:**

```python
import secrets
from datetime import datetime, timedelta

def generate_reset_token():
    return secrets.token_urlsafe(32)

@app.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per minute")
def forgot_password():
    email = request.form["email"]
    user = db.users.find_one({"email": email})
    if user:
        token = generate_reset_token()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        db.password_resets.delete_many({"user_id": user["_id"]})
        db.password_resets.insert_one({
            "token_hash": token_hash,
            "user_id": user["_id"],
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        })
        send_reset_email(email, token)  # send raw token; store hash
    return jsonify({"message": "If that email exists, a reset link was sent."})
```'''
    ),
    (
        "thinking/meta-quality-security-graphql-depth",
        r'''Rate the security of this GraphQL endpoint (1-10):

```javascript
const { ApolloServer, gql } = require('apollo-server-express');

const typeDefs = gql`
  type User {
    id: ID!
    name: String!
    friends: [User!]!
    posts: [Post!]!
  }
  type Post {
    id: ID!
    title: String!
    author: User!
    comments: [Comment!]!
  }
  type Comment {
    id: ID!
    body: String!
    author: User!
  }
  type Query {
    user(id: ID!): User
    users: [User!]!
  }
`;

const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: true,
  playground: true,
});

server.applyMiddleware({ app });
```''',
        r'''<think>
Let me evaluate this GraphQL setup against known GraphQL-specific attack vectors.

1. Query depth: The schema has circular references (User -> friends -> [User], User -> posts -> Post -> author -> User, Post -> comments -> Comment -> author -> User). Without depth limiting, an attacker can craft deeply nested queries like `{ user(id:1) { friends { friends { friends { ... } } } } }` that cause exponential database load. This is a denial-of-service vector.

2. Query complexity / cost analysis: No complexity limiting either. Even without deep nesting, a wide query like `{ users { posts { comments { author { posts { comments ... } } } } } }` can explode combinatorially.

3. Introspection enabled: `introspection: true` in production exposes the entire schema, making it trivial for attackers to discover all types, fields, and relationships.

4. Playground enabled: GraphQL Playground in production gives attackers an interactive tool to craft and test malicious queries.

5. No rate limiting or authentication middleware visible.

6. No persisted queries / query allowlisting.

The circular type references without any depth or complexity protection is the most critical issue. A single malicious query can bring down the server.

Score: 2/10.
</think>

**Security: 2/10**

| Criterion                  | Rating  | Notes                                          |
|-----------------------------|---------|-------------------------------------------------|
| Query depth limiting        | 0/10    | No depth limit; circular refs enable DoS        |
| Query complexity analysis   | 0/10    | No cost/complexity cap                          |
| Introspection               | 2/10    | Enabled; exposes full schema to attackers        |
| Playground                  | 2/10    | Enabled; gives interactive attack surface        |
| Rate limiting               | 0/10    | Not present                                     |
| OWASP A05 (Misconfiguration)| FAIL    | Multiple misconfigurations                      |

**What's good:**
- The schema itself is cleanly typed with non-nullable annotations, which is good for data integrity.

**What's critically wrong:**
1. **No query depth limiting (CRITICAL):** Circular references (`User -> friends -> User`, `Post -> author -> User -> posts -> Post`) allow arbitrarily deep queries. A single request can trigger millions of database calls.
2. **No complexity analysis:** Even shallow-but-wide queries can explode in cost.
3. **Introspection + Playground in production:** Attackers get a full map of your API and a tool to exploit it interactively.

**Fixed version:**

```javascript
const depthLimit = require('graphql-depth-limit');
const { createComplexityLimitRule } = require('graphql-validation-complexity');

const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: process.env.NODE_ENV !== 'production',
  playground: process.env.NODE_ENV !== 'production',
  validationRules: [
    depthLimit(5),
    createComplexityLimitRule(1000),
  ],
  plugins: [
    {
      requestDidStart: () => ({
        didResolveOperation({ request }) {
          // Add query allowlisting or logging here
        },
      }),
    },
  ],
});
```

Additionally, add rate limiting middleware (e.g., `express-rate-limit`) upstream of the GraphQL endpoint and require authentication for non-public queries.'''
    ),
    (
        "thinking/meta-quality-security-localstorage-sessions",
        r'''Rate the security of this session management implementation (1-10):

```javascript
// Login handler
async function login(username, password) {
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();

  if (data.token) {
    localStorage.setItem('session_token', data.token);
    localStorage.setItem('user_role', data.role);
    localStorage.setItem('user_id', data.user_id);
    window.location.href = '/dashboard';
  }
}

// Auth check on each request
function getAuthHeaders() {
  return {
    'Authorization': 'Bearer ' + localStorage.getItem('session_token'),
    'X-User-Role': localStorage.getItem('user_role'),
    'X-User-Id': localStorage.getItem('user_id'),
  };
}

// Admin check
function isAdmin() {
  return localStorage.getItem('user_role') === 'admin';
}
```''',
        r'''<think>
Let me analyze this session management implementation for security issues.

1. localStorage for tokens: localStorage is accessible to any JavaScript running on the page. If there is ANY XSS vulnerability anywhere in the application, the attacker can steal the session token with `localStorage.getItem('session_token')`. HttpOnly cookies are immune to this because JavaScript cannot read them.

2. Client-side role storage and trust: The user role is stored in localStorage and sent as a custom header `X-User-Role`. This is catastrophic -- any user can open DevTools, run `localStorage.setItem('user_role', 'admin')`, and the application will treat them as an admin. If the server trusts the `X-User-Role` header for authorization decisions, this is a privilege escalation vulnerability.

3. Client-side admin check: `isAdmin()` checks localStorage, meaning the UI-level access control is trivially bypassable. If server-side authorization mirrors this trust, it's a complete auth bypass.

4. User ID from client: Sending `X-User-Id` from the client means the server might trust the client's claim about which user is making the request. This enables IDOR (Insecure Direct Object Reference) attacks.

5. No token expiration handling on the client side.

6. No CSRF protection visible (though Bearer tokens in headers are less susceptible than cookies to CSRF).

The combination of localStorage tokens (XSS-vulnerable) and client-trusted role/ID headers (privilege escalation + IDOR) is extremely dangerous.

Score: 1/10.
</think>

**Security: 1/10**

| Criterion                    | Rating  | Notes                                          |
|-------------------------------|---------|-------------------------------------------------|
| Token storage                 | 2/10    | localStorage is vulnerable to XSS theft         |
| Authorization model           | 0/10    | Client-supplied role header -- trivially spoofed |
| Identity verification         | 0/10    | Client-supplied user ID enables IDOR            |
| Session expiration            | 2/10    | No client-side expiry handling                  |
| XSS resilience                | 1/10    | Any XSS steals all credentials instantly        |
| OWASP A01 (Broken Access Ctrl)| FAIL    | Client-controlled authorization                 |
| OWASP A07 (Auth Failures)     | FAIL    | Fundamentally broken auth model                 |

**What's (marginally) acceptable:**
- Using Bearer tokens in the Authorization header (as opposed to query parameters) is at least a reasonable transport mechanism.

**What's critically wrong:**
1. **Client-trusted role (CRITICAL):** Sending `X-User-Role` from localStorage and relying on it for authorization is equivalent to asking the user "are you an admin?" Any user can escalate to admin.
2. **Client-trusted user ID (CRITICAL):** `X-User-Id` from the client enables impersonation of any user.
3. **localStorage token storage (HIGH):** A single XSS vulnerability anywhere in the app exfiltrates the token, role, and user ID simultaneously.
4. **Client-side `isAdmin()` (HIGH):** UI-level gating with no server enforcement is security theater.

**Fixed version:**

```javascript
// Login -- use HttpOnly cookie set by server, not localStorage
async function login(username, password) {
  const response = await fetch('/api/login', {
    method: 'POST',
    credentials: 'include',  // accept HttpOnly cookies
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (response.ok) {
    window.location.href = '/dashboard';
  }
}

// Auth -- cookie is sent automatically; role comes from server
function getAuthHeaders() {
  return {};  // HttpOnly cookie attached automatically
}

// Admin check -- ask the server, never trust the client
async function isAdmin() {
  const res = await fetch('/api/me', { credentials: 'include' });
  const data = await res.json();
  return data.role === 'admin';
}
```

The server must derive the user ID and role from the session token on every request. Never trust client-supplied identity or authorization claims.'''
    ),
    (
        "thinking/meta-quality-security-cors-wildcard",
        r'''Rate the security of this CORS configuration (1-10):

```python
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
    }
})

@app.route("/api/user/profile", methods=["GET"])
def get_profile():
    token = request.headers.get("Authorization")
    user = verify_token(token)
    return jsonify({"email": user.email, "name": user.name, "ssn": user.ssn})

@app.route("/api/user/transfer", methods=["POST"])
def transfer_funds():
    token = request.headers.get("Authorization")
    user = verify_token(token)
    data = request.get_json()
    execute_transfer(user.id, data["to_account"], data["amount"])
    return jsonify({"status": "success"})
```''',
        r'''<think>
Analyzing this CORS configuration for security issues.

1. `origins: "*"` with `supports_credentials: True`: This is the most dangerous CORS misconfiguration. Setting `Access-Control-Allow-Origin: *` tells browsers that ANY website can make requests to this API. Combined with `supports_credentials: True` (which sets `Access-Control-Allow-Credentials: true`), this means any malicious website can make authenticated cross-origin requests.

Actually, browsers will refuse to honor `Access-Control-Allow-Credentials: true` when the origin is the literal `*`. However, many CORS libraries (including flask-cors in some versions) work around this by reflecting the requesting origin back instead of sending `*` when credentials are enabled. This effectively makes it a dynamic wildcard that bypasses the browser's safety check.

2. All methods allowed: GET, POST, PUT, DELETE are all permitted cross-origin, meaning a malicious site can perform any action.

3. Authorization header exposed: Allowing the Authorization header cross-origin means any site can send authenticated requests.

4. Sensitive data exposure: The profile endpoint returns SSN -- highly sensitive PII accessible from any origin.

5. Financial operations: The transfer endpoint performs fund transfers, and with this CORS config, any website can trigger transfers on behalf of a logged-in user.

This is essentially a CSRF vulnerability enabled by CORS misconfiguration, but worse because it also allows reading the response (traditional CSRF is write-only).

Score: 1/10.
</think>

**Security: 1/10**

| Criterion                    | Rating  | Notes                                            |
|-------------------------------|---------|--------------------------------------------------|
| Origin restriction            | 0/10    | Wildcard allows any origin                       |
| Credentials handling          | 0/10    | Credentials with wildcard = full cross-origin access |
| Method restriction            | 2/10    | All mutating methods allowed cross-origin        |
| Data sensitivity awareness    | 0/10    | SSN exposed via unrestricted CORS endpoint       |
| OWASP A01 (Broken Access Ctrl)| FAIL    | Any website can act as the authenticated user    |
| OWASP A05 (Misconfiguration)  | FAIL    | Textbook CORS misconfiguration                   |

**What's good:**
- Token-based authentication is used (better than relying solely on cookies for API auth).
- At least some structure exists around CORS configuration rather than no CORS handling at all.

**What's critically wrong:**
1. **Wildcard + credentials (CRITICAL):** `origins: "*"` with `supports_credentials: True` means any website can make authenticated requests and read responses. A malicious page like `evil.com` can fetch the victim's SSN or initiate fund transfers.
2. **Sensitive PII exposure:** The profile endpoint returns SSN over an unrestricted CORS policy. This is a data breach waiting to happen.
3. **Financial operations exposed:** The transfer endpoint can be called cross-origin with full authentication, enabling cross-site fund theft.

**Fixed version:**

```python
ALLOWED_ORIGINS = [
    "https://myapp.example.com",
    "https://admin.example.com",
]

CORS(app, resources={
    r"/api/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "max_age": 600,
    }
})
```

Additionally, the `/api/user/profile` endpoint should never return full SSN in API responses. Return a masked version (e.g., `***-**-1234`) and require step-up authentication to reveal the full value. The transfer endpoint should require a CSRF token or re-authentication for high-value operations.'''
    ),
    (
        "thinking/meta-quality-security-xxe-attack",
        r'''Rate the security of this XML parser (1-10):

```java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.DocumentBuilder;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import java.io.InputStream;

public class UserImportService {

    public List<User> importUsers(InputStream xmlInput) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = factory.newDocumentBuilder();
        Document doc = builder.parse(xmlInput);

        NodeList userNodes = doc.getElementsByTagName("user");
        List<User> users = new ArrayList<>();

        for (int i = 0; i < userNodes.getLength(); i++) {
            Element el = (Element) userNodes.item(i);
            String name = el.getElementsByTagName("name").item(0).getTextContent();
            String email = el.getElementsByTagName("email").item(0).getTextContent();
            users.add(new User(name, email));
        }
        return users;
    }
}
```''',
        r'''<think>
Let me analyze this XML parsing code for XXE (XML External Entity) vulnerabilities.

The code creates a `DocumentBuilderFactory` with default settings and parses untrusted XML input. The default Java XML parser configuration has external entity processing ENABLED. This means an attacker can submit XML like:

```xml
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<users>
  <user>
    <name>&xxe;</name>
    <email>attacker@evil.com</email>
  </user>
</users>
```

This would cause the parser to read `/etc/passwd` and include its contents in the `name` field. The attack surface includes:

1. Local file disclosure: `file:///etc/passwd`, `file:///etc/shadow`, application config files with database credentials, etc.
2. SSRF (Server-Side Request Forgery): `http://169.254.169.254/latest/meta-data/` to access cloud instance metadata (AWS keys, etc.).
3. Denial of service: The "Billion Laughs" attack using nested entity expansion can consume all available memory.
4. Port scanning: Using `http://internal-host:port/` entities to probe internal network services.

The code takes an InputStream directly, which suggests it processes user-uploaded XML -- maximum exposure.

No input validation, no size limiting on the XML input, no error handling that would prevent information leakage in error messages.

Score: 1/10. XXE is OWASP A05 (Security Misconfiguration) and this is the textbook vulnerable pattern.
</think>

**Security: 1/10**

| Criterion                    | Rating  | Notes                                            |
|-------------------------------|---------|--------------------------------------------------|
| External entity protection    | 0/10    | Default settings allow XXE                       |
| DTD processing                | 0/10    | DTDs not disabled; enables entity expansion      |
| File disclosure risk          | 0/10    | Attacker can read arbitrary server files         |
| SSRF risk                     | 0/10    | Attacker can reach internal services and cloud metadata |
| DoS resilience                | 1/10    | Vulnerable to Billion Laughs entity expansion    |
| OWASP A05 (Misconfiguration)  | FAIL    | Textbook XXE vulnerability                       |

**What's good:**
- The parsing logic itself (extracting name/email from elements) is straightforward and correct.
- The method signature is clean and the code is readable.

**What's critically wrong:**
1. **XXE -- Local file disclosure (CRITICAL):** An attacker submits XML with `<!ENTITY xxe SYSTEM "file:///etc/passwd">` and reads arbitrary files from the server, including private keys, configuration files, and credentials.
2. **XXE -- SSRF (CRITICAL):** Entities like `SYSTEM "http://169.254.169.254/latest/meta-data/"` access cloud metadata services, potentially leaking IAM credentials.
3. **Billion Laughs DoS (HIGH):** Nested entity definitions can expand to gigabytes of data from a tiny XML payload, crashing the JVM with `OutOfMemoryError`.
4. **No input size limit:** The `InputStream` is parsed without any size constraint.

**Fixed version:**

```java
public List<User> importUsers(InputStream xmlInput) throws Exception {
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();

    // Disable XXE completely
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
    factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
    factory.setXIncludeAware(false);
    factory.setExpandEntityReferences(false);

    DocumentBuilder builder = factory.newDocumentBuilder();
    Document doc = builder.parse(xmlInput);

    NodeList userNodes = doc.getElementsByTagName("user");
    List<User> users = new ArrayList<>();

    for (int i = 0; i < userNodes.getLength(); i++) {
        Element el = (Element) userNodes.item(i);
        String name = el.getElementsByTagName("name").item(0).getTextContent();
        String email = el.getElementsByTagName("email").item(0).getTextContent();
        users.add(new User(name, email));
    }
    return users;
}
```

The single most important line is `disallow-doctype-decl: true`, which rejects any XML containing a DOCTYPE declaration, eliminating the entire class of XXE attacks. The additional flags provide defense in depth.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
