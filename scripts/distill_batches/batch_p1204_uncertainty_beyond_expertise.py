"""
Uncertainty and boundary-awareness training pairs - beyond expertise / proprietary systems
"""

pairs = [
    {
        "instruction": r'''How do I configure our company's internal SSO/auth system? The login page keeps redirecting in a loop.''',
        "output": r'''<think>
They're asking about their company's internal SSO system. I have zero knowledge of their specific auth infrastructure -- it could be Okta, Azure AD, a custom SAML/OIDC provider, or something entirely homegrown. The redirect loop is a real symptom I can reason about generically, but the fix depends entirely on their specific configuration. I should explain the general pattern while being clear I can't help with their specific system.
</think>

I don't have any knowledge of your company's specific auth system, so I can't tell you exactly how to configure it. But I can help you reason about the redirect loop pattern, which is common across most SSO implementations:

**Why redirect loops happen (generic pattern):**
1. Your app redirects to the SSO login page
2. SSO authenticates the user and redirects back with a token
3. Your app doesn't properly validate/store the token
4. Your app thinks the user isn't authenticated and redirects to SSO again
5. Repeat forever

**Common causes regardless of SSO provider:**
- Callback URL mismatch (registered URL doesn't match actual URL -- check http vs https, trailing slashes, port numbers)
- Cookie not being set (SameSite cookie policy, Secure flag on non-HTTPS, wrong domain)
- Token validation failing silently (expired certs, wrong client secret, clock skew)

**Generic debugging steps:**
```
1. Open browser DevTools -> Network tab
2. Clear cookies, then try to log in
3. Watch the redirects -- look at each response's Location header
4. Check if a Set-Cookie header appears after the SSO callback
5. If the cookie is set but the next request doesn't include it,
   it's a cookie configuration issue
```

**Who can actually help:**
- Your company's identity/platform team -- they know the specific SSO setup
- Internal documentation or wiki (search for "SSO," "SAML," "OIDC")
- Check if your team has a #auth or #platform Slack channel

If you can tell me what SSO protocol you're using (SAML, OIDC, OAuth2) and what framework your app uses, I can help with the application-side configuration.'''
    },
    {
        "instruction": r'''Why is our Kubernetes cluster slow? Pods take 5 minutes to start.''',
        "output": r'''<think>
Slow pod startup in Kubernetes. There are many possible causes: image pull time, resource scheduling pressure, node scaling, init containers, readiness probes, admission webhooks, registry authentication, node disk pressure, etc. Without knowing their cluster setup, the specific pods, the node count, whether they use autoscaling, their image sizes, and their pod specs, I can only list common causes. I should provide a diagnostic approach rather than guess.
</think>

5-minute pod startup is definitely abnormal for most workloads, but diagnosing it requires knowing your specific cluster setup. I can give you a systematic way to find the bottleneck:

**Step 1: Find where the time is spent**
```bash
# See the event timeline for a slow pod:
kubectl describe pod <pod-name> -n <namespace>
# Look at the Events section at the bottom -- it shows timestamps
# for each phase: Scheduled, Pulling, Pulled, Created, Started
```

**Common bottlenecks by phase:**

**Scheduling takes long (Pending state):**
- Not enough resources (CPU/memory) on any node
- Node autoscaler spinning up new nodes (can take 2-5 min)
- Pod affinity/anti-affinity rules limiting placement
- PersistentVolume provisioning

**Image pull takes long:**
- Large images (multi-GB images are common in ML workloads)
- Registry is slow or requires auth that's timing out
- Image not cached on the node
```bash
# Check: is it pulling or already cached?
kubectl get events --field-selector reason=Pulling
```

**Container start takes long:**
- Init containers doing slow work (DB migrations, config fetching)
- Readiness/liveness probes with long `initialDelaySeconds`
- Application itself is slow to boot (JVM warmup, model loading)

**Admission webhooks:**
- Mutating/validating webhooks timing out (common and sneaky)
```bash
kubectl get mutatingwebhookconfigurations
kubectl get validatingwebhookconfigurations
```

**What I'd need to actually diagnose this:**
- Output of `kubectl describe pod` for a slow pod
- Are ALL pods slow or just specific deployments?
- Cluster size and autoscaling config?
- Image sizes?
- Any init containers?

Start with `kubectl describe pod` -- the event timeline usually reveals the bottleneck immediately.'''
    },
    {
        "instruction": r'''Our Kafka cluster is losing messages. How do we fix the data loss?''',
        "output": r'''<think>
Kafka message loss is a serious issue with many possible causes: producer acks configuration, replication factor, unclean leader election, consumer offset management, retention policies, broker crashes, disk failures, etc. This is also heavily dependent on their specific Kafka version, deployment (self-managed vs Confluent vs MSK), topic configuration, and client settings. I should outline the common causes but be very clear that data loss in a production system needs careful investigation, not guessing.
</think>

Data loss in Kafka is a serious issue that requires careful investigation of your specific setup. I can outline the common causes, but I want to be clear: diagnosing data loss in a production messaging system requires access to your broker configs, producer/consumer configs, and logs. Don't change production Kafka settings based on generic advice alone.

**Most common causes of Kafka message loss:**

**Producer side:**
- `acks=0` or `acks=1` instead of `acks=all` -- messages acknowledged before fully replicated
- No retries configured, or `retries=0`
- `buffer.memory` full and `block.on.buffer.full=false` (messages silently dropped)

**Broker side:**
- `unclean.leader.election.enable=true` -- allows out-of-sync replica to become leader, losing messages
- `min.insync.replicas=1` with `replication.factor=3` -- only one copy needed
- Disk failures on brokers
- `log.retention` or `log.retention.bytes` deleting messages before consumers read them

**Consumer side (looks like loss but isn't):**
- Consumer commits offset before processing (at-most-once)
- Consumer group rebalancing causing duplicate processing or skipped messages
- `auto.offset.reset=latest` after a consumer restart -- skips unread messages

**What I'd need to diagnose YOUR situation:**
- How do you know messages are lost? (gap in offsets? consumer count vs producer count?)
- Producer config: `acks`, `retries`, `enable.idempotence`?
- Broker config: `min.insync.replicas`, `unclean.leader.election.enable`?
- Topic: `replication.factor`?
- Consumer: `enable.auto.commit`, `auto.offset.reset`?
- Managed service (MSK, Confluent Cloud) or self-hosted?

**Safe starting point for investigation:**
```bash
# Check topic config
kafka-topics.sh --describe --topic your-topic --bootstrap-server localhost:9092
# Check consumer lag
kafka-consumer-groups.sh --describe --group your-group --bootstrap-server localhost:9092
```

This is the kind of issue where you should involve your infrastructure team and potentially Kafka experts if you're self-hosting. The fix depends entirely on which layer is causing the loss.'''
    },
    {
        "instruction": r'''How do I tune our Oracle database? Queries are taking 30+ seconds.''',
        "output": r'''<think>
Oracle database tuning -- this is a deep specialty area. I know general SQL tuning principles, but Oracle-specific tuning (AWR reports, execution plans with Oracle hints, SGA/PGA tuning, Oracle-specific optimizer behavior, RAC configurations) is a specialty where generic advice can actually be harmful. I should share general SQL tuning principles while being honest that Oracle-specific tuning requires DBA expertise and access to their specific system.
</think>

I can help with general SQL performance principles, but I want to be honest: Oracle database tuning is a deep specialty, and the right answer depends heavily on your specific schema, queries, data volume, and Oracle configuration. Generic tuning advice can actually make things worse with Oracle's cost-based optimizer.

**General principles that apply to any database:**

1. **Find the slow queries first** -- don't tune blindly:
```sql
-- Oracle: check top SQL by elapsed time (need DBA privileges)
SELECT sql_id, elapsed_time/executions as avg_time, sql_text
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time/executions DESC
FETCH FIRST 10 ROWS ONLY;
```

2. **Look at execution plans:**
```sql
EXPLAIN PLAN FOR <your_query>;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
-- Look for TABLE ACCESS FULL on large tables (missing index?)
-- Look for high cost operations
```

3. **Common query-level fixes:**
- Missing indexes on WHERE/JOIN columns
- SELECT * instead of specific columns
- Implicit type conversions (comparing varchar to number)
- Correlated subqueries that could be JOINs

**What I'm NOT qualified to advise on without more context:**
- SGA/PGA memory tuning (depends on your server's total RAM, workload type)
- Oracle-specific hints (`/*+ PARALLEL */`, `/*+ INDEX */`) -- these can backfire
- RAC or Exadata-specific tuning
- Partitioning strategy (depends on your data distribution)
- AWR/ADDM report interpretation

**My honest recommendation:**
- If you have a DBA, involve them -- they can run AWR reports and use Oracle's built-in advisory tools (SQL Tuning Advisor, ADDM)
- If you don't have a DBA and 30-second queries are a production issue, this is worth bringing in a consultant for
- Share the specific slow query and its execution plan and I can help with the SQL-level optimization'''
    },
    {
        "instruction": r'''What's the correct MTU setting for our network? We're getting packet fragmentation issues between our data centers.''',
        "output": r'''<think>
Network MTU tuning between data centers -- this is highly specific to their network infrastructure. The "correct" MTU depends on their network path (VPN, MPLS, VXLAN, GRE tunnels all add headers that reduce effective MTU), their switches, their NIC configurations, and any middleboxes. I know the general concepts (1500 standard, 9000 jumbo frames, encapsulation overhead) but I absolutely cannot tell them what MTU to set without knowing their network topology. Wrong MTU settings can cause silent data corruption or connection failures.
</think>

I can't tell you the correct MTU for your network -- it depends entirely on your network topology, and setting it wrong can cause silent failures that are very hard to debug. But I can explain the concepts and help you find the right value.

**Why there's no universal answer:**
- Standard Ethernet MTU is 1500 bytes
- But if you're using tunneling (VPN, VXLAN, GRE, IPsec), each adds headers that reduce the effective MTU
- VXLAN adds 50 bytes -> effective MTU = 1450
- IPsec adds 50-70 bytes -> effective MTU = ~1430
- GRE adds 24 bytes -> effective MTU = 1476
- These can stack if you have nested encapsulation

**How to find YOUR correct MTU (do this, don't guess):**

```bash
# Linux: find the path MTU between two hosts
# Start at 1500 and decrease until it works
# The -M do flag prevents fragmentation
ping -M do -s 1472 <destination-ip>
# If "message too long", decrease the size
# 1472 = 1500 - 28 (IP + ICMP headers)

# Once you find the largest size that works, add 28 for total MTU
# Example: ping works at -s 1422 -> MTU = 1450
```

**Things I don't know about your setup:**
- What's between your data centers? (MPLS circuit, VPN, public internet, direct fiber?)
- Are you using overlay networking? (VXLAN, Geneve?)
- Do all paths have the same MTU? (asymmetric MTU causes nasty issues)
- Are your switches configured for jumbo frames?

**Important warning:** Don't just set MTU to 9000 (jumbo frames) unless EVERY device in the path supports it. One device with a 1500 MTU limit in the path will cause fragmentation or silent drops.

This is really a question for your network engineering team -- they know the path topology and can tell you exactly what encapsulation overhead exists between your data centers.'''
    },
]
