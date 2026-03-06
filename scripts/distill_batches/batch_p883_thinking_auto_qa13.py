"""Phase 4F: Self-Improvement — Quality Assurance (Part 13)

Quality checklists for security incident response guidance —
ensuring advice on security incidents is accurate, prioritized,
and doesn't cause additional harm during response.
"""

PAIRS = [
    (
        "thinking/auto-qa-security-incident-triage",
        r'''What quality checks should I apply when advising on security incident triage? How do I ensure my incident response guidance prioritizes correctly and doesn't make things worse?''',
        r'''<think>
Security incident response advice is uniquely high-stakes because bad advice can:
1. Cause additional data loss (destroying evidence)
2. Alert the attacker (causing them to escalate or hide)
3. Extend the breach (leaving attack vectors open)
4. Create legal liability (mishandling notification requirements)

The quality check must ensure advice follows incident response best practices: contain first, investigate second, remediate third, and communicate throughout.
</think>

**Security Incident Triage Quality Checklist**

**Before giving any security incident advice:**
```
□ DO NO HARM: Will this advice make the situation worse?
  - Don't recommend deleting logs (you need them for investigation)
  - Don't recommend rebooting immediately (you lose volatile evidence)
  - Don't recommend public disclosure before understanding scope
  - Don't recommend confronting suspected insiders

□ PRESERVE EVIDENCE: Does the advice preserve forensic data?
  Before taking any action:
  - Capture system state (memory dumps, running processes)
  - Copy relevant logs to a secure location
  - Document the timeline of discovery
  - Screenshot any anomalous behavior

□ PROFESSIONAL BOUNDARIES: Is this beyond AI advice territory?
  ALWAYS recommend:
  - Involving a security professional for confirmed breaches
  - Consulting legal counsel for data breach notifications
  - Following the organization's incident response plan

  AI advice should support, not replace, professional response.
```

**Phase 1: Identification and classification**
```
□ CONFIRM THE INCIDENT:
  Is this actually a security incident or a false alarm?
  Check:
  - Is the anomaly explained by legitimate activity?
  - Are multiple indicators present? (one indicator may be noise)
  - Can you reproduce the suspicious behavior?

  Common false alarms:
  - Failed logins from password managers (not brute force)
  - Vulnerability scanner traffic (not an attack)
  - Automated testing hitting security controls

□ CLASSIFY SEVERITY:
  CRITICAL: Active data exfiltration, ransomware executing,
    system compromise with ongoing access
    → Immediate containment, all hands

  HIGH: Confirmed unauthorized access, credential compromise,
    sensitive data exposure
    → Rapid containment within 1 hour

  MEDIUM: Suspicious activity indicating possible compromise,
    vulnerability being actively exploited
    → Investigation within 4 hours

  LOW: Minor policy violation, unsuccessful attack attempt,
    informational security event
    → Investigation within 24 hours

□ SCOPE ASSESSMENT:
  - Which systems are affected?
  - Which data may be compromised?
  - How many users are potentially impacted?
  - Is the attack ongoing or historical?
```

**Phase 2: Containment**
```
□ CONTAINMENT PRIORITIES:
  1. Stop ongoing data loss (highest priority)
  2. Prevent lateral movement (contain to affected systems)
  3. Preserve evidence (don't destroy what you need)
  4. Maintain business operations (if safely possible)

□ SHORT-TERM CONTAINMENT:
  Actions to stop the immediate threat:
  - Isolate affected systems from the network
  - Disable compromised accounts
  - Block known attacker IP addresses
  - Revoke compromised API keys or tokens
  - Enable enhanced logging on affected systems

  IMPORTANT: Do NOT power off systems unless absolutely
  necessary — this destroys volatile memory evidence.

□ COMMUNICATION:
  - Notify incident response team
  - Notify management (for resource allocation)
  - Do NOT notify public or customers yet (too early)
  - Do NOT discuss on public channels (Slack channels
    may be compromised)
```

**Phase 3: Investigation guidance**
```
□ EVIDENCE COLLECTION:
  Recommend collecting (in priority order):
  1. Volatile data: Memory dumps, running processes, network connections
  2. Logs: Authentication logs, application logs, network logs
  3. Artifacts: Modified files, new accounts, scheduled tasks
  4. Timeline: Sequence of events from first indicator

□ INVESTIGATION QUESTIONS:
  - How did the attacker gain access? (initial vector)
  - What did they do after gaining access? (lateral movement)
  - What data was accessed or exfiltrated? (impact)
  - Are they still present? (persistence mechanisms)
  - How long have they had access? (dwell time)

□ DO NOT:
  - Use compromised systems for investigation
  - Communicate investigation details over compromised channels
  - Modify evidence without documenting the change
  - Rush to blame individuals before facts are established
```

**Quality checks for advice accuracy**
```
□ PROPORTIONAL RESPONSE:
  Is the recommended response proportional to the incident?
  Don't recommend shutting down all systems for a minor
  policy violation. Don't recommend "just change the password"
  for a confirmed system compromise.

□ UP-TO-DATE PRACTICES:
  Security best practices evolve. Verify:
  - Recommended tools are current (not deprecated)
  - Compliance requirements reflect current regulations
  - Attack patterns reflect current threat landscape

□ CONTEXT-APPROPRIATE:
  Consider the organization's resources:
  - Small team: Focus on containment and external help
  - Security team available: Guide toward their processes
  - Regulated industry: Emphasize compliance requirements
```

**The meta-principle:** Security incident response is a process of controlled urgency — act quickly enough to limit damage, but deliberately enough to preserve evidence and avoid making the situation worse. The first priority is always containment (stop the bleeding), followed by investigation (understand what happened), then remediation (fix the vulnerability). Never skip steps, and always recommend involving security professionals for confirmed incidents.'''
    ),
    (
        "thinking/auto-qa-security-credential-compromise",
        r'''What quality checks should I apply when advising on credential compromise incidents? How do I ensure my guidance covers all necessary steps when passwords, API keys, or tokens are leaked?''',
        r'''<think>
Credential compromise is one of the most common security incidents. The response seems simple (change the password) but is actually complex because:
1. The credential may have been used to access other systems
2. The credential may have been leaked to multiple parties
3. There may be other compromised credentials not yet discovered
4. Automated systems using the credential will break when rotated

Quality checks must ensure the response is complete, not just addressing the obvious symptom.
</think>

**Credential Compromise Response Checklist**

**Immediate actions (first 30 minutes)**
```
□ IDENTIFY SCOPE:
  What type of credential was compromised?
  - User password → account takeover risk
  - API key → service access risk
  - SSH key → server access risk
  - Database credentials → data access risk
  - Cloud provider credentials → infrastructure risk
  - JWT signing key → all sessions compromised

  Each type has different blast radius and response steps.

□ REVOKE IMMEDIATELY:
  Don't wait to investigate — revoke first, investigate second.
  - Password: Force password reset, invalidate all sessions
  - API key: Rotate the key, deploy new key to legitimate consumers
  - SSH key: Remove from authorized_keys on all servers
  - Database creds: Change password, update connection strings
  - Cloud creds: Deactivate access keys, issue new ones
  - JWT signing key: Rotate key, all existing tokens become invalid

□ CHECK FOR USAGE:
  Was the credential used by an attacker?
  - Check authentication logs for unusual access patterns
  - Check API logs for unexpected requests
  - Check cloud provider audit logs for unauthorized actions
  - Check for new resources created (VMs, users, storage)
```

**Investigation (first 24 hours)**
```
□ HOW WAS IT COMPROMISED?
  Common sources:
  - Committed to public Git repository
  - Included in client-side code (JavaScript bundles)
  - Exposed in error messages or logs
  - Phishing attack on credential holder
  - Shared in plaintext (email, Slack, docs)
  - Stolen from insecure storage
  - Extracted from a compromised system

  Finding the source prevents recurrence.

□ WHAT ELSE IS COMPROMISED?
  One compromised credential often means others are too:
  - Same password used elsewhere? (credential stuffing)
  - Same source contains other secrets? (check the repo/config)
  - Same system stores other credentials? (compromised system)
  - Other users affected by the same attack vector?

□ WHAT WAS ACCESSED?
  Determine what the attacker could have done:
  - Which systems does this credential access?
  - What data is accessible with this credential?
  - What actions can be performed with this credential?
  - Audit logs: What was actually done?
```

**Remediation**
```
□ ROTATE ALL POTENTIALLY AFFECTED CREDENTIALS:
  Not just the known compromised one:
  - All credentials from the same source
  - All credentials on the same compromised system
  - All credentials that could have been derived

  When in doubt, rotate.

□ FIX THE ROOT CAUSE:
  - Committed to Git: Use git-filter-repo to remove from history,
    add pre-commit hooks for secret detection
  - In client code: Move to server-side, use environment variables
  - In logs: Add log redaction, review logging practices
  - Phishing: Security awareness training, enable MFA
  - Plaintext sharing: Implement a secrets manager
  - Insecure storage: Migrate to vault/secrets manager

□ IMPLEMENT PREVENTIVE MEASURES:
  - Secret scanning in CI/CD (detect before commit)
  - Regular credential rotation schedule
  - Multi-factor authentication on all accounts
  - Principle of least privilege (credentials only access what's needed)
  - Secret manager adoption (HashiCorp Vault, AWS Secrets Manager)

□ NOTIFY AFFECTED PARTIES:
  - Users whose data may have been accessed
  - Teams whose services were affected
  - Compliance/legal if regulated data was exposed
  - Third parties if their credentials or data were involved
```

**The meta-principle:** Credential compromise response follows the pattern: revoke immediately, investigate scope, remediate root cause, prevent recurrence. The most common mistake is treating it as a simple password change when it should be treated as a potential system compromise. Always ask "what could someone do with this credential?" and investigate whether they actually did it.'''
    ),
    (
        "thinking/auto-qa-security-vulnerability-response",
        r'''What quality checks should I apply when advising on vulnerability disclosure and patching? How do I help teams respond appropriately when a vulnerability is discovered in their software or dependencies?''',
        r'''<think>
Vulnerability response advice must balance urgency (patch quickly) with thoroughness (don't break things while patching). The quality check must ensure:
1. Severity is accurately assessed
2. Patching is prioritized correctly
3. The patch doesn't introduce new problems
4. Communication is appropriate
5. Root cause is addressed
</think>

**Vulnerability Response Quality Checklist**

**Step 1: Severity assessment**
```
□ CVSS SCORE CONTEXT:
  Don't just report the CVSS score — contextualize it:
  - Is the vulnerable component exposed to the internet?
  - Is the vulnerable component processing user input?
  - Are there compensating controls in place?
  - Is an exploit publicly available?

  A CVSS 9.8 vulnerability in an internal-only library
  with no network exposure is lower priority than a
  CVSS 7.0 in a public-facing authentication component.

□ EXPLOITABILITY:
  - Is there a known exploit in the wild?
  - Is exploit code publicly available?
  - How complex is exploitation? (requires special access?)
  - Is the vulnerability actively being exploited?

  Active exploitation → immediate patching
  No known exploit → prioritized patching

□ IMPACT ASSESSMENT:
  If exploited, what can the attacker do?
  - Read sensitive data (confidentiality)
  - Modify data or systems (integrity)
  - Disrupt service (availability)
  - Gain further access (privilege escalation)
```

**Step 2: Patching prioritization**
```
□ CRITICAL (patch within 24 hours):
  - Actively exploited vulnerabilities
  - Remote code execution on public-facing systems
  - Authentication bypass
  - Data exfiltration vulnerabilities with public exploit

□ HIGH (patch within 1 week):
  - Remote code execution without public exploit
  - SQL injection, XSS in authenticated areas
  - Privilege escalation
  - Denial of service on critical systems

□ MEDIUM (patch within 1 month):
  - Vulnerabilities requiring specific conditions to exploit
  - Information disclosure of non-sensitive data
  - DoS on non-critical systems

□ LOW (patch in next maintenance cycle):
  - Vulnerabilities with no practical exploit
  - Low-impact issues in non-production systems
  - Informational findings
```

**Step 3: Patching process**
```
□ TEST THE PATCH:
  Never apply security patches directly to production
  without testing (except for actively exploited critical vulns).

  Testing checklist:
  - Does the application still work? (smoke tests)
  - Are there breaking changes in the patch? (changelog review)
  - Does the patch affect performance? (load test if critical path)
  - Are there dependency conflicts? (check lockfile resolution)

□ STAGED ROLLOUT:
  1. Apply patch to development environment
  2. Run automated tests
  3. Apply to staging environment
  4. Verify with manual testing
  5. Apply to production
  6. Monitor for issues

  For actively exploited critical vulnerabilities:
  Accelerate this process but don't skip testing entirely.
  Minimum: Run automated tests before production deployment.

□ ROLLBACK PLAN:
  What if the patch breaks something?
  - Can you revert the dependency update?
  - Is there a workaround (WAF rule, config change)?
  - What is the risk of reverting (re-exposing the vulnerability)?
```

**Step 4: Communication**
```
□ INTERNAL COMMUNICATION:
  - Security team: Full details of vulnerability and response
  - Engineering team: What's being patched and timeline
  - Management: Business impact and response status
  - Support team: If users may be affected

□ EXTERNAL COMMUNICATION (if applicable):
  - Customers: If their data was at risk (follow disclosure policy)
  - Security researchers: If vulnerability was reported externally
  - Regulatory bodies: If required by compliance
  - Public: If widespread impact (coordinated disclosure)

□ AVOID:
  - Disclosing vulnerability details before patching
  - Minimizing the severity to avoid embarrassment
  - Blaming individuals or teams publicly
  - Providing exploit details in public communications
```

**Step 5: Post-patch review**
```
□ ROOT CAUSE ANALYSIS:
  Why did this vulnerability exist?
  - Missing input validation → improve validation practices
  - Outdated dependency → improve dependency management
  - Insecure coding pattern → update coding standards
  - Missing security review → add security review to process

□ DETECTION IMPROVEMENT:
  How can we find similar vulnerabilities faster?
  - Add SAST/DAST to CI pipeline
  - Implement dependency scanning
  - Add security-focused code review checklist
  - Schedule regular security assessments

□ PROCESS IMPROVEMENT:
  How can we respond faster next time?
  - Was the patching process smooth?
  - Were the right people notified quickly?
  - Was the communication appropriate?
  - What would we do differently?
```

**The meta-principle:** Vulnerability response is about risk management, not perfection. The goal is to reduce risk as quickly as possible while not creating new risks through hasty patching. Assess severity in context (not just CVSS), prioritize based on actual exploitability, test patches before deploying, and improve processes after every incident. The best vulnerability response is one where the team follows a well-practiced process calmly and efficiently.'''
    ),
    (
        "thinking/auto-qa-security-data-breach-guidance",
        r'''What quality checks should I apply when advising on data breach response? How do I ensure breach guidance covers technical, legal, and communication requirements?''',
        r'''<think>
Data breach response advice is the highest-stakes security guidance because it involves legal obligations, regulatory requirements, and potential harm to real people. AI advice must be careful to:
1. Recommend professional legal and security counsel
2. Not provide legal advice (which I am not qualified for)
3. Cover the technical response accurately
4. Emphasize notification obligations
5. Not minimize the breach or encourage hiding it
</think>

**Data Breach Response Quality Checklist**

**Critical first principles**
```
□ RECOMMEND PROFESSIONAL HELP:
  ALWAYS recommend engaging:
  - Legal counsel (breach notification requirements vary by jurisdiction)
  - Incident response firm (for forensic investigation)
  - Public relations (for customer communication)

  AI advice supports but does NOT replace professional guidance.

□ DO NOT:
  - Provide specific legal advice about notification requirements
  - Recommend delaying notification beyond what's legally required
  - Minimize the scope or impact of the breach
  - Suggest hiding the breach from affected parties
  - Provide jurisdiction-specific legal guidance
```

**Technical response**
```
□ CONTAINMENT:
  Stop the breach from continuing:
  - Close the attack vector
  - Revoke compromised access
  - Isolate affected systems
  - Preserve evidence

□ SCOPE DETERMINATION:
  What data was exposed?
  - Types of data: PII, financial, health, credentials
  - Volume: How many records?
  - Duration: How long was data accessible?
  - Access: Who accessed the data? (attacker, public, etc.)

  Accurate scope determines notification requirements
  and the seriousness of the response.

□ EVIDENCE PRESERVATION:
  Preserve all evidence for:
  - Legal proceedings
  - Regulatory investigations
  - Insurance claims
  - Root cause analysis

  Implement legal hold on all relevant systems and logs.
  Do not modify, delete, or overwrite evidence.
```

**Notification guidance (general, not legal advice)**
```
□ REGULATORY AWARENESS:
  Different regulations have different requirements:
  - GDPR: 72 hours to notify supervisory authority
  - HIPAA: 60 days to notify affected individuals
  - State laws: Vary by US state
  - Industry regulations: PCI-DSS, SOX, etc.

  ALWAYS recommend legal counsel for specific obligations.

□ AFFECTED INDIVIDUALS:
  When notification is required, include:
  - What happened (factual description)
  - What data was affected
  - What the organization is doing about it
  - What the individual can do to protect themselves
  - Contact information for questions

□ COMMUNICATION PRINCIPLES:
  - Be honest about what happened
  - Be clear about what is and isn't known
  - Provide actionable guidance for affected individuals
  - Don't use jargon or minimize the impact
  - Update as more information becomes available
```

**Post-breach improvement**
```
□ ROOT CAUSE REMEDIATION:
  Fix the vulnerability that allowed the breach.
  This is obvious but sometimes deprioritized
  in the chaos of breach response.

□ SECURITY POSTURE REVIEW:
  The breach indicates a gap. Review for similar gaps:
  - Are other systems vulnerable to the same attack?
  - Are data protection measures adequate?
  - Is monitoring sufficient to detect similar breaches faster?
  - Are access controls properly configured?

□ PROCESS IMPROVEMENT:
  - Was the breach detected quickly enough?
  - Was the response effective?
  - Were the right people involved?
  - Was communication appropriate and timely?
  - What tools or processes would have prevented this?

□ DOCUMENTATION:
  Document everything:
  - Timeline of the breach and response
  - Decisions made and rationale
  - Actions taken and outcomes
  - Lessons learned and improvements planned

  This documentation is needed for legal, regulatory,
  and insurance purposes.
```

**The meta-principle:** Data breach response is a serious matter with legal, ethical, and technical dimensions. Technical advice should focus on containment, investigation, and remediation while always deferring legal and regulatory questions to qualified professionals. The organization's priority should be protecting affected individuals, not protecting its reputation. Honest, timely communication builds more trust than a perfect but delayed response.'''
    ),
    (
        "thinking/auto-qa-security-incident-prevention",
        r'''What quality checks should I apply when advising on security incident prevention? How do I ensure preventive security advice is practical and covers the most impactful controls?''',
        r'''<think>
Security prevention advice often falls into the trap of recommending everything — resulting in an overwhelming list that teams implement partially or not at all. The quality check should ensure prevention advice is:
1. Prioritized by impact (most common attack vectors first)
2. Practical (implementable with the team's resources)
3. Layered (defense in depth, not single point of failure)
4. Appropriate for the risk level
</think>

**Security Incident Prevention Quality Checklist**

**Prioritized prevention controls**
```
□ PRIORITY 1 — Authentication and access (blocks most attacks):
  - Multi-factor authentication on all accounts
  - Strong password policies (length > complexity)
  - API key rotation schedule
  - Principle of least privilege (minimal permissions)
  - Regular access reviews (who has access to what?)

  Impact: Blocks credential stuffing, phishing, and
  unauthorized access — the most common attack vectors.

□ PRIORITY 2 — Dependency management (blocks supply chain attacks):
  - Automated dependency scanning (Dependabot, Snyk)
  - Lockfile committed and enforced
  - Regular dependency updates (monthly)
  - Review of new dependencies before adoption

  Impact: Prevents exploitation of known vulnerabilities
  in third-party code.

□ PRIORITY 3 — Input validation (blocks injection attacks):
  - Parameterized queries (never string concatenation for SQL)
  - Output encoding for HTML (prevents XSS)
  - Input validation on all user-supplied data
  - Content Security Policy headers

  Impact: Prevents SQL injection, XSS, and related
  injection attacks.

□ PRIORITY 4 — Secrets management (prevents credential leaks):
  - No secrets in source code
  - Secret scanning in CI/CD pipeline
  - Secrets manager for runtime secrets
  - Regular secret rotation

  Impact: Prevents accidental exposure of credentials.

□ PRIORITY 5 — Monitoring and detection (reduces breach impact):
  - Authentication logging (all login attempts)
  - Access logging (who accessed what data)
  - Anomaly alerting (unusual patterns)
  - Regular log review

  Impact: Reduces time to detect and contain breaches.
```

**Quality check for prevention advice**
```
□ PROPORTIONAL TO RISK:
  Is the recommended investment proportional to the asset value?
  Internal wiki → basic authentication + backups
  Customer payment data → comprehensive security program

□ IMPLEMENTABLE:
  Can the team actually do this?
  Small team → managed security tools, not custom solutions
  No security expertise → focus on defaults and automation

  Advice to "implement a WAF with custom rules" isn't helpful
  if nobody on the team knows how to configure a WAF.
  "Use Cloudflare with default security settings" is better.

□ DEFENSE IN DEPTH:
  Does the advice include multiple layers?
  If the firewall fails → authentication still protects
  If authentication fails → authorization limits damage
  If authorization fails → encryption protects data
  If encryption fails → monitoring detects the breach

  No single control should be the only protection.

□ MEASURABLE:
  Can the team verify the controls are working?
  - Run security scans regularly
  - Test incident response procedures
  - Track and fix findings from security reviews
  - Measure time to detect test incidents
```

**Prevention anti-patterns**
```
□ SECURITY THEATER:
  Controls that look good but don't reduce risk:
  - Password complexity rules (users write them down)
  - Frequent password changes (users increment a number)
  - Checkbox compliance (meeting the letter, not spirit)

  Real prevention focuses on actual attack vectors,
  not on looking secure.

□ ALL OR NOTHING:
  "You need to implement everything or it's not worth doing."
  Wrong. Each layer of defense reduces risk.
  MFA alone blocks 99% of credential attacks.
  Start with the highest-impact, lowest-effort controls.

□ SET AND FORGET:
  Security controls need maintenance:
  - Access reviews (people change roles)
  - Tool updates (new vulnerabilities discovered)
  - Policy reviews (threat landscape changes)
  - Training updates (new attack techniques)
```

**The meta-principle:** Security prevention is about reducing risk to an acceptable level, not eliminating all risk (which is impossible). Focus on the controls that address the most common and most impactful threats first. A team that implements MFA, dependency scanning, and parameterized queries has addressed the vast majority of common attack vectors. Start there, and add more sophisticated controls as the team's security maturity grows.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
