PAIRS = [
    ("thinking/debugging", r'''Our application gets intermittent "Connection reset by peer" errors:

```
requests.exceptions.ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
```

This happens roughly 1 in 100 requests to our upstream API. The error occurs during the response read phase, not during connection establishment. tcpdump shows:

```
14:23:45.001 client -> server [SYN]
14:23:45.002 server -> client [SYN, ACK]
14:23:45.002 client -> server [ACK]
14:23:45.003 client -> server [PSH, ACK] HTTP GET /api/data
14:23:45.105 server -> client [RST, ACK]
```

The server sends a RST immediately after receiving the request. What causes this?''', r'''<think>
A RST (reset) packet means the server is forcefully terminating the connection. The timing is interesting -- the RST comes ~100ms after the request is sent, which suggests the server received the request but decided to close the connection.

Common causes of server-side RST:
1. The server's connection pool is full and it's rejecting new connections
2. The server application crashed while processing the request
3. A load balancer or firewall is terminating idle connections
4. The client is reusing a connection that the server has already closed (stale connection in keep-alive pool)
5. The server's listen backlog is full

The 1 in 100 rate and the fact that it happens during response read suggests connection reuse issue -- the client sends a request on a keep-alive connection that the server has already closed. The RST is the server's response to receiving data on a connection it no longer recognizes.
</think>

The most likely cause is a stale keep-alive connection. HTTP persistent connections (keep-alive) are reused for multiple requests. However, the server has a keep-alive timeout after which it closes idle connections. If the client sends a request on a connection that the server has already closed, the server responds with RST because it does not recognize the connection.

**The race condition timeline:**

```
t=0.000: Server's keep-alive timer expires, server closes connection
t=0.001: Client picks this connection from its pool (doesn't know it's closed yet)
t=0.002: Client sends HTTP request on the closed connection
t=0.003: Server receives data on an unknown connection -> sends RST
t=0.004: Client receives RST -> "Connection reset by peer"
```

This happens because TCP's close notification (FIN) may not have reached the client yet, or the client's connection pool has not processed it.

**Fix 1: Enable retry on connection errors**

```python
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

session = requests.Session()

retry_strategy = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[502, 503, 504],
    allowed_methods=["GET", "HEAD", "OPTIONS"],
    # Retry on connection errors (includes RST)
    raise_on_status=False,
)

adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=10,
)
session.mount("https://", adapter)
session.mount("http://", adapter)

response = session.get("https://api.example.com/data")
```

**Fix 2: Reduce client keep-alive timeout**

Set the client's keep-alive timeout to be shorter than the server's:

```python
# If server closes connections after 60s, set client timeout lower
adapter = HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    pool_block=True,
)
# urllib3 does not directly expose keep-alive timeout,
# but you can use socket options:
import socket

def patch_socket(conn):
    sock = conn.sock
    # Enable TCP keep-alive probes
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # Send first probe after 30 seconds of idle
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
    # Send probes every 10 seconds
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
    # Close after 3 failed probes
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
```

**Fix 3: Disable keep-alive for problematic connections**

```python
response = requests.get(
    "https://api.example.com/data",
    headers={"Connection": "close"}
)
```

This forces a new TCP connection for each request. Slower but eliminates the stale connection issue.

**Other causes of RST packets:**

1. **Load balancer idle timeout**: AWS ALB/NLB has a 60s idle timeout. Connections idle longer get RST.
2. **Firewall state table cleanup**: Stateful firewalls drop connections after their timeout.
3. **Server overload**: Server's accept queue is full, kernel sends RST for new connections.
4. **Half-open connections**: Server crashed and restarted, client tries to use old connection.

**Diagnosing with tcpdump:**

```bash
# Capture TCP flags to identify RST patterns
tcpdump -i any -nn "host api.example.com and (tcp[tcpflags] & tcp-rst != 0)"

# Capture full handshake + RST
tcpdump -i any -nn -w capture.pcap "host api.example.com"
```

**Prevention tips:**
- Always implement retry logic for HTTP clients in production
- Match client keep-alive timeout to server timeout (client should be shorter)
- Monitor RST rates in your network metrics
- Use connection pooling libraries that handle stale connection detection
- Set TCP keep-alive probes to detect dead connections before sending data'''),

    ("thinking/debugging", r'''DNS resolution is failing intermittently in our Kubernetes pods:

```
socket.gaierror: [Errno -3] Temporary failure in name resolution
```

The DNS failures happen for external domains (api.example.com) and occasionally for internal services (my-service.default.svc.cluster.local). About 5% of requests fail.

```
$ nslookup api.example.com
;; connection timed out; no servers could be reached

$ cat /etc/resolv.conf
nameserver 10.96.0.10
search default.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

The DNS server 10.96.0.10 is kube-dns (CoreDNS). What's causing intermittent failures?''', r'''<think>
The `ndots:5` setting is likely the main culprit. With ndots:5, any hostname with fewer than 5 dots is treated as a "relative" name and the search domains are appended first before trying the absolute name.

For `api.example.com` (2 dots, less than 5):
1. First tries: api.example.com.default.svc.cluster.local
2. Then tries: api.example.com.svc.cluster.local
3. Then tries: api.example.com.cluster.local
4. Then tries: api.example.com. (absolute)

That is 4 DNS queries instead of 1. Each query goes to CoreDNS, which creates 4x the load. Under high traffic, CoreDNS can become overwhelmed and start dropping queries, causing the intermittent failures.

Additional factors:
- CoreDNS might be under-resourced
- conntrack table might be full (Linux netfilter issue with UDP)
- DNS race condition with concurrent A and AAAA queries on the same UDP port
</think>

There are likely multiple contributing factors, but the primary culprit is the `ndots:5` setting combined with high DNS query volume.

**The ndots:5 problem:**

With `ndots:5`, any hostname with fewer than 5 dots is treated as a relative name. DNS resolution tries all search domains before the absolute name:

```
Resolving "api.example.com" (2 dots, less than 5):
  1. api.example.com.default.svc.cluster.local -> NXDOMAIN
  2. api.example.com.svc.cluster.local         -> NXDOMAIN
  3. api.example.com.cluster.local              -> NXDOMAIN
  4. api.example.com.                           -> SUCCESS
```

Every external DNS lookup generates 4 queries instead of 1. Under load, this overwhelms CoreDNS.

**Fix 1: Reduce ndots or use FQDN**

```yaml
# Pod spec: reduce ndots
apiVersion: v1
kind: Pod
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"
  containers:
    - name: app
      image: myapp
```

Or append a trailing dot to force absolute resolution:

```python
# In application code, use FQDN with trailing dot
response = requests.get("https://api.example.com./data")
#                                              ^ trailing dot = absolute name
```

**Fix 2: Scale up CoreDNS**

```yaml
# Increase CoreDNS replicas
kubectl scale deployment coredns -n kube-system --replicas=4

# Or use DNS autoscaler
kubectl apply -f https://k8s.io/examples/admin/dns/dns-horizontal-autoscaler.yaml
```

**Fix 3: Enable DNS caching in pods (NodeLocal DNSCache)**

```bash
# Deploy NodeLocal DNSCache DaemonSet
# This runs a DNS cache on every node, reducing load on CoreDNS
kubectl apply -f https://raw.githubusercontent.com/kubernetes/kubernetes/master/cluster/addons/dns/nodelocaldns/nodelocaldns.yaml
```

NodeLocal DNSCache runs on each node, caching DNS responses and reducing the number of queries that reach CoreDNS.

**Fix 4: Fix the conntrack race condition**

On Linux, when a pod sends both A (IPv4) and AAAA (IPv6) DNS queries simultaneously, they may use the same UDP source port. The kernel's conntrack (connection tracking) table can get confused and drop one of the packets.

```yaml
# CoreDNS Corefile: disable IPv6 lookups if not needed
.:53 {
    forward . /etc/resolv.conf {
        prefer_udp
    }
    template IN AAAA . {
        rcode NXDOMAIN
    }
}
```

Or in the pod:

```yaml
dnsConfig:
  options:
    - name: single-request-reopen
      value: ""
    - name: ndots
      value: "2"
```

`single-request-reopen` forces A and AAAA queries to use different source ports, avoiding the conntrack race.

**Diagnosing DNS issues:**

```bash
# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Check CoreDNS metrics
kubectl port-forward -n kube-system svc/kube-dns 9153:9153
curl http://localhost:9153/metrics | grep dns_request

# Test from inside a pod
kubectl run dns-test --image=busybox --rm -it -- nslookup api.example.com
```

**Prevention tips:**
- Set ndots to 2 for workloads that primarily access external services
- Use FQDN (with trailing dot) for external hostnames
- Deploy NodeLocal DNSCache in production clusters
- Monitor CoreDNS latency and error rate
- Add `single-request-reopen` to dnsConfig to avoid UDP conntrack races
- Cache DNS results in your application layer for frequently-accessed hostnames'''),

    ("thinking/debugging", r'''Our HTTPS connection fails with a certificate error:

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1123)
```

The URL works fine in Chrome and curl on macOS. But our Python application on a Linux server fails:

```python
import requests
response = requests.get('https://api.partner.com/v2/data')
# SSLError: certificate verify failed
```

curl on the same server:
```
$ curl https://api.partner.com/v2/data
curl: (60) SSL certificate problem: unable to get local issuer certificate
```

The certificate chain from the server:
```
* Server certificate:
*  subject: CN=api.partner.com
*  issuer: CN=DigiCert SHA2 Extended Validation Server CA
*  Intermediate: CN=DigiCert SHA2 Extended Validation Server CA
*  Root: CN=DigiCert High Assurance EV Root CA (NOT sent by server)
```

The root CA is not sent by the server.''', r'''<think>
The issue is an incomplete SSL certificate chain. The server sends its leaf certificate and the intermediate certificate, but not the root CA certificate. Browsers and macOS have the DigiCert root CA in their trust store, so they can complete the chain. But the Linux server might not have the root CA installed, or the CA bundle is outdated.

The fact that Chrome works but curl on Linux fails confirms that the issue is the Linux server's CA certificate bundle.

Fixes:
1. Install/update the CA certificates on the server
2. Specify the CA bundle explicitly
3. Fix the server to send the complete chain
</think>

The server is not sending the complete certificate chain. It sends the leaf certificate and intermediate CA, but not the root CA (DigiCert High Assurance EV Root CA). Browsers have this root CA in their built-in trust store, so they can complete the chain. Your Linux server's CA bundle either does not include this root CA or is outdated.

**Why it works in Chrome but not on the Linux server:**

- Chrome/Firefox have their own bundled CA trust store (Mozilla NSS)
- macOS has the Apple trust store with the root CA
- Linux relies on the system CA bundle, which varies by distribution and may be outdated
- Python's `requests` library uses `certifi` or the system bundle

**Fix 1: Update the system CA certificates**

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y ca-certificates
sudo update-ca-certificates

# CentOS/RHEL
sudo yum install -y ca-certificates
sudo update-ca-trust

# Alpine
apk add --no-cache ca-certificates
update-ca-certificates
```

**Fix 2: Update Python's certifi package**

```bash
pip install --upgrade certifi

# Verify the CA bundle
python -c "import certifi; print(certifi.where())"
```

**Fix 3: Specify the CA bundle explicitly**

```python
import requests

response = requests.get(
    'https://api.partner.com/v2/data',
    verify='/etc/ssl/certs/ca-certificates.crt'
)

# Or with certifi:
import certifi
response = requests.get(
    'https://api.partner.com/v2/data',
    verify=certifi.where()
)
```

**Fix 4: Fix the server configuration (best long-term fix)**

The server should send the complete chain (leaf + intermediates). The root CA is optional but intermediates are required.

Nginx:
```nginx
ssl_certificate /etc/ssl/fullchain.pem;  # leaf + intermediate(s)
ssl_certificate_key /etc/ssl/private.pem;
```

Apache:
```apache
SSLCertificateFile /etc/ssl/cert.pem
SSLCertificateChainFile /etc/ssl/chain.pem
```

**Verify the certificate chain:**

```bash
# Check what the server sends
openssl s_client -connect api.partner.com:443 -showcerts < /dev/null 2>/dev/null | grep "s:"

# Test with specific CA bundle
openssl s_client -connect api.partner.com:443 -CAfile /etc/ssl/certs/ca-certificates.crt < /dev/null
# Look for "Verify return code: 0 (ok)"

# Download and inspect the certificate chain
openssl s_client -connect api.partner.com:443 < /dev/null 2>/dev/null | openssl x509 -text -noout
```

**NEVER disable certificate verification in production:**

```python
# DANGEROUS -- DO NOT DO THIS IN PRODUCTION
requests.get(url, verify=False)  # disables ALL certificate checking!
# This makes you vulnerable to man-in-the-middle attacks
```

**Prevention tips:**
- Keep system CA certificates updated via package manager
- Keep `certifi` updated in your Python dependencies
- Test SSL connections from the same environment where your app runs (not your laptop)
- Use SSL Labs (ssllabs.com/ssltest) to check your server's certificate chain
- Set up monitoring for certificate expiration dates
- In Docker, always install `ca-certificates` in your base image'''),

    ("thinking/debugging", r'''Large file transfers fail intermittently with connection timeouts. The transfer works for small files but fails for files over 1400 bytes:

```
$ curl -v http://internal-server:8080/api/large-response
...
* transfer closed with outstanding read data remaining
* Recv failure: Connection reset by peer
```

Network path goes through a VPN tunnel. Smaller requests work fine. The exact failure point varies but always happens early in large responses. tcpdump shows:

```
14:00:00.001 -> [SYN] MSS=1460
14:00:00.002 <- [SYN,ACK] MSS=1460
14:00:00.100 -> [PSH,ACK] 1460 bytes  (first data packet)
14:00:00.101 <- [ACK]
14:00:00.102 -> [PSH,ACK] 1460 bytes  (second data packet)
14:00:03.102 -> [PSH,ACK] 1460 bytes  (retransmit)
14:00:09.102 -> [PSH,ACK] 1460 bytes  (retransmit)
... (no ACK ever comes back for second packet)
```

The first 1460-byte packet goes through but the second one never gets ACK'd.''', r'''<think>
This is a classic MTU/fragmentation issue, particularly common with VPN tunnels.

The MSS (Maximum Segment Size) negotiated is 1460 bytes (standard for 1500 byte MTU Ethernet: 1500 - 20 IP header - 20 TCP header = 1460 MSS).

However, the VPN tunnel adds overhead (typically 20-60 bytes for encapsulation headers). So the actual MTU through the tunnel is less than 1500. When a 1460-byte TCP segment is encapsulated in the VPN, the total packet exceeds the tunnel's MTU.

If the DF (Don't Fragment) bit is set (which is default for TCP), the intermediate router drops the packet and should send an ICMP "Fragmentation Needed" message. But many firewalls block ICMP, so the sender never gets the message. This is called a "PMTU black hole."

The first packet (with SYN or small data) might be small enough to fit. But a full 1460-byte data segment exceeds the tunnel MTU.

The fix: reduce MSS or MTU to account for VPN overhead.
</think>

This is a classic MTU (Maximum Transmission Unit) black hole problem, very common with VPN tunnels.

**What is happening:**

1. TCP negotiates MSS of 1460 bytes (based on standard 1500 byte Ethernet MTU)
2. The VPN tunnel adds encapsulation overhead (typically 40-60 bytes)
3. Effective tunnel MTU is ~1440-1460 bytes
4. A TCP segment of 1460 bytes + 40 bytes IP/TCP headers = 1500 bytes
5. VPN encapsulation adds ~50 bytes -> 1550 bytes total
6. This exceeds the tunnel's MTU -> packet is too large
7. The DF (Don't Fragment) bit is set -> router should send ICMP "Fragmentation Needed"
8. But a firewall blocks the ICMP message -> sender never learns about the MTU limit
9. Sender keeps retransmitting the same oversized packet -> connection hangs

The first packet (SYN, 0 data) is small enough to pass. Small responses fit too. But full-sized data packets are silently dropped.

**Fix 1: Reduce MTU on the VPN interface**

```bash
# On the VPN tunnel interface
ip link set dev tun0 mtu 1400

# Or in VPN configuration (OpenVPN):
# In openvpn.conf:
tun-mtu 1400
mssfix 1360
```

**Fix 2: Clamp MSS at the firewall/router**

```bash
# iptables: clamp MSS to path MTU
iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

# Or set a specific MSS
iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1360
```

This modifies the MSS value in SYN packets passing through the firewall, so endpoints negotiate a smaller MSS that fits through the tunnel.

**Fix 3: Allow ICMP through firewalls**

```bash
# ICMP type 3 code 4 (Fragmentation Needed) MUST be allowed
iptables -A INPUT -p icmp --icmp-type fragmentation-needed -j ACCEPT
iptables -A FORWARD -p icmp --icmp-type fragmentation-needed -j ACCEPT
```

Blocking all ICMP is a common security misconfiguration that breaks Path MTU Discovery.

**Diagnosing MTU issues:**

```bash
# Find the working MTU by testing different packet sizes
# -M do = set DF bit (don't fragment)
ping -c 1 -M do -s 1472 internal-server  # 1472 + 28 ICMP/IP = 1500
# If this fails, reduce -s until it works

ping -c 1 -M do -s 1400 internal-server  # try 1400
ping -c 1 -M do -s 1350 internal-server  # try 1350

# The largest working size + 28 = your path MTU
```

```bash
# Check current interface MTU
ip link show tun0 | grep mtu

# Trace the MTU along the path
tracepath internal-server
# Shows MTU at each hop
```

**Fix 4: Application-level workaround**

```python
import socket

# Create a socket with smaller MSS
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, 1360)
```

**Prevention tips:**
- Always set VPN tunnel MTU to account for encapsulation overhead
- Never block ICMP type 3 (destination unreachable) -- it is essential for PMTU discovery
- Use `tracepath` or `pmtud` tools to verify path MTU before deploying
- Set MSS clamping on network equipment at VPN tunnel endpoints
- Monitor for TCP retransmissions as an indicator of MTU issues
- Common MTU values: Ethernet = 1500, VPN = 1400-1450, PPPoE = 1492'''),

    ("thinking/debugging", r'''Our websocket connections are dying after exactly 60 seconds of inactivity:

```
WebSocket connection closed: code=1006, reason=
```

The connections work fine when there's active message exchange. But if no messages are sent for 60 seconds, the connection drops silently. The close code 1006 means abnormal closure (no close frame was sent).

Our application sends a ping every 30 seconds:

```python
import websockets

async def handler(websocket, path):
    async for message in websocket:
        response = process(message)
        await websocket.send(response)
```

Server config:
```python
start_server = websockets.serve(
    handler,
    "0.0.0.0", 8765,
    ping_interval=30,
    ping_timeout=10,
)
```

But the connections still die at 60 seconds.''', r'''<think>
The websocket server has ping_interval=30 and ping_timeout=10, which should keep the connection alive. But there is likely a proxy, load balancer, or firewall between the client and server that has its own idle timeout of 60 seconds.

Common culprits:
- Nginx proxy_read_timeout defaults to 60 seconds
- AWS ALB idle timeout defaults to 60 seconds
- HAProxy timeout client/server defaults
- Cloud provider's firewall/NAT gateway

The proxy does not understand WebSocket ping/pong frames as "activity" -- it only sees TCP-level activity. If the proxy buffers the connection, it might not see the WebSocket pings as TCP traffic.

Or, more likely, the issue is that Nginx or the load balancer is configured for HTTP but not properly upgraded to WebSocket. The proxy_read_timeout then kills the "idle" HTTP connection.
</think>

The WebSocket pings keep the connection alive between your application server and the client, but there is almost certainly a proxy or load balancer between them with a 60-second idle timeout. The proxy terminates the connection because it does not recognize WebSocket ping/pong frames as meaningful activity.

**Common culprits with 60-second default timeouts:**

1. **Nginx** (most likely): `proxy_read_timeout` defaults to 60s
2. **AWS ALB**: idle timeout defaults to 60s
3. **HAProxy**: `timeout client` / `timeout server`
4. **Cloudflare**: 100s timeout, but can vary

**Fix 1: Configure Nginx for WebSocket**

```nginx
location /ws/ {
    proxy_pass http://backend:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;

    # Increase timeout for WebSocket connections
    proxy_read_timeout 3600s;   # 1 hour
    proxy_send_timeout 3600s;
}
```

The critical settings are:
- `proxy_http_version 1.1` -- required for WebSocket upgrade
- `proxy_set_header Upgrade` and `Connection "upgrade"` -- forward the WebSocket upgrade headers
- `proxy_read_timeout 3600s` -- prevent Nginx from closing idle connections

**Fix 2: Configure AWS ALB idle timeout**

```bash
# AWS CLI
aws elbv2 modify-load-balancer-attributes \
    --load-balancer-arn arn:aws:elasticloadbalancing:... \
    --attributes Key=idle_timeout.timeout_seconds,Value=3600
```

Or in Terraform:
```hcl
resource "aws_lb" "main" {
    idle_timeout = 3600
}
```

**Fix 3: Send application-level heartbeats**

Even with proper proxy config, add application-level heartbeats as a second layer:

```python
import asyncio
import websockets

async def handler(websocket, path):
    try:
        async for message in websocket:
            if message == 'ping':
                await websocket.send('pong')
            else:
                response = process(message)
                await websocket.send(response)
    except websockets.ConnectionClosed:
        pass
```

Client side:
```javascript
const ws = new WebSocket('wss://api.example.com/ws/');

// Application-level heartbeat (not WebSocket ping)
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
    }
}, 30000);
```

Application-level messages generate real TCP traffic that proxies recognize as activity, unlike WebSocket control frames which may be buffered or ignored.

**Fix 4: Use TCP keep-alive as a fallback**

```python
import socket

start_server = websockets.serve(
    handler,
    "0.0.0.0", 8765,
    ping_interval=30,
    ping_timeout=10,
    # Set TCP keep-alive
    create_protocol=lambda *args, **kwargs: websockets.WebSocketServerProtocol(
        *args, **kwargs,
    ),
)
```

**Diagnosing the idle timeout source:**

```bash
# Test directly to the WebSocket server (bypassing proxy)
wscat -c ws://backend-direct:8765
# If this works beyond 60s, the proxy is the culprit

# Check Nginx error log
tail -f /var/log/nginx/error.log
# Look for: "upstream timed out (110: Connection timed out)"
```

**Prevention tips:**
- Always configure proxy timeouts explicitly for WebSocket endpoints
- Use application-level heartbeats in addition to WebSocket pings
- Monitor WebSocket connection duration in your metrics
- Set proxy timeouts higher than your ping interval
- Document the full network path (client -> CDN -> LB -> proxy -> server) and check each hop's timeout'''),
]
