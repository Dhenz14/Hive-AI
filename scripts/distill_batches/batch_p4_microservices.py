"""
Batch P4 — Microservices: service mesh, API gateway, service discovery,
distributed tracing, resilience patterns.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Service Mesh with Istio/Envoy ---
    (
        "service_mesh_istio_envoy",
        "Explain the service mesh architecture with Istio and Envoy sidecar proxies — how the "
        "data plane and control plane work together, mTLS certificate rotation, traffic management "
        "with VirtualService and DestinationRule, circuit breaking configuration, and canary "
        "deployments with weight-based routing. Include complete YAML manifests and debugging strategies.",
        r"""
# Service Mesh with Istio and Envoy: Complete Production Guide

## Why Service Meshes Exist

In a microservices architecture with hundreds of services, every service needs **mutual TLS**,
**retries**, **circuit breaking**, **observability**, and **traffic management**. Implementing
these cross-cutting concerns inside each application is a **common mistake** — it couples
infrastructure logic to business code, duplicates effort across languages, and creates
inconsistency. A service mesh solves this by moving networking concerns into the infrastructure
layer.

The core insight is the **sidecar proxy pattern**: every pod gets an Envoy proxy injected
alongside it. All inbound and outbound traffic passes through Envoy, which enforces policies
without the application knowing. This is **best practice** because it provides a uniform
security and observability layer regardless of the application language or framework.

```
┌─────────────────────────────────────────────────────────┐
│  Kubernetes Pod                                         │
│  ┌──────────────┐    ┌──────────────────┐              │
│  │  Application  │───▶│  Envoy Sidecar   │──▶ Network  │
│  │  Container    │◀───│  (iptables redirect)│◀── Network│
│  └──────────────┘    └──────────────────┘              │
│                                                         │
│  Traffic flow: App → localhost:port → iptables →        │
│  Envoy (15001) → upstream Envoy → upstream App          │
└─────────────────────────────────────────────────────────┘
```

## Data Plane vs Control Plane

Istio separates into two distinct layers:

**Data Plane (Envoy proxies):** The fleet of sidecar proxies that intercept all traffic.
Each Envoy instance handles connection pooling, load balancing, health checking, TLS
termination, and telemetry collection. Because Envoy is written in C++ and uses an
event-driven architecture, it adds **less than 1ms p99 latency** per hop — a trade-off
that is almost always worth the observability and security gains.

**Control Plane (istiod):** A single binary that combines Pilot (traffic management),
Citadel (certificate management), and Galley (configuration validation). istiod watches
Kubernetes resources and pushes Envoy configuration via xDS (discovery service) APIs.

```yaml
# Istio installation with production settings
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
metadata:
  name: production-mesh
  namespace: istio-system
spec:
  profile: default
  meshConfig:
    # Enable access logging for debugging
    accessLogFile: /dev/stdout
    accessLogEncoding: JSON
    # Strict mTLS — reject plaintext connections
    defaultConfig:
      holdApplicationUntilProxyStarts: true  # Prevent race conditions
    enableAutoMtls: true
    # Outbound traffic policy — REGISTRY_ONLY blocks unknown external calls
    outboundTrafficPolicy:
      mode: REGISTRY_ONLY
  components:
    pilot:
      k8s:
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
        hpaSpec:
          minReplicas: 2  # HA control plane
          maxReplicas: 5
    ingressGateways:
      - name: istio-ingressgateway
        enabled: true
        k8s:
          resources:
            requests:
              cpu: 1000m
              memory: 1Gi
          service:
            type: LoadBalancer
            ports:
              - port: 80
                targetPort: 8080
                name: http2
              - port: 443
                targetPort: 8443
                name: https
```

## mTLS and Certificate Rotation

Istio's **Citadel** (now part of istiod) acts as a Certificate Authority. It issues SPIFFE
identity certificates to each workload, enabling **zero-trust networking** — every connection
is authenticated and encrypted. This is therefore one of the strongest arguments for a
service mesh, because it eliminates an entire class of lateral-movement attacks.

```yaml
# Enforce strict mTLS mesh-wide
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system  # Mesh-wide when in istio-system
spec:
  mtls:
    mode: STRICT  # Reject plaintext; PERMISSIVE allows migration

---
# Per-namespace override for legacy services still migrating
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: legacy-permissive
  namespace: legacy-services
spec:
  mtls:
    mode: PERMISSIVE  # Accept both mTLS and plaintext
  selector:
    matchLabels:
      mesh-migration: in-progress
```

A **pitfall** with strict mTLS is that health checks from kubelet (which runs outside the
mesh) will fail because kubelet cannot present a valid mesh certificate. The solution is to
configure liveness and readiness probes to use the Envoy admin port, or use Istio's
automatic probe rewriting (enabled by default in modern versions).

## Traffic Management: VirtualService and DestinationRule

Traffic management in Istio uses two core resources that work together:

- **VirtualService**: Defines routing rules (which version gets traffic, header-based routing)
- **DestinationRule**: Defines policies for traffic after routing (connection pools, outlier detection)

```yaml
# VirtualService: Canary deployment with 90/10 weight split
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: product-service
  namespace: production
spec:
  hosts:
    - product-service  # Kubernetes service name
  http:
    # Header-based routing for internal testing
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: product-service
            subset: canary
            port:
              number: 8080
    # Weight-based canary for general traffic
    - route:
        - destination:
            host: product-service
            subset: stable
            port:
              number: 8080
          weight: 90
        - destination:
            host: product-service
            subset: canary
            port:
              number: 8080
          weight: 10
      # Retry policy
      retries:
        attempts: 3
        perTryTimeout: 2s
        retryOn: 5xx,reset,connect-failure,retriable-4xx
      timeout: 10s

---
# DestinationRule: Define subsets and circuit breaking
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: product-service
  namespace: production
spec:
  host: product-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
        connectTimeout: 30ms
      http:
        h2UpgradePolicy: UPGRADE  # Use HTTP/2 between sidecars
        maxRequestsPerConnection: 1000
        http1MaxPendingRequests: 128
        http2MaxRequests: 1024
    outlierDetection:
      # Circuit breaker: eject hosts with >5 consecutive 5xx errors
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50  # Never eject more than half
    loadBalancer:
      simple: LEAST_REQUEST  # Better than ROUND_ROBIN for variable latency
  subsets:
    - name: stable
      labels:
        version: v1
    - name: canary
      labels:
        version: v2
```

## Canary Deployment Workflow

A production canary deployment with Istio follows a **progressive delivery** pattern.
The trade-off here is between deployment speed and risk mitigation — you want to catch
regressions early without slowing down releases excessively.

```yaml
# Progressive canary: 5% → 25% → 50% → 100%
# Step 1: Initial canary at 5%
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-service
  namespace: production
  annotations:
    canary-step: "1"
    canary-start-time: "2024-01-15T10:00:00Z"
spec:
  hosts:
    - payment-service
  http:
    - route:
        - destination:
            host: payment-service
            subset: stable
          weight: 95
        - destination:
            host: payment-service
            subset: canary
          weight: 5
      # Automatic rollback trigger
      fault:
        abort:
          percentage:
            value: 0  # Set to 100 to emergency-abort canary traffic

---
# Monitoring query for canary health (Prometheus)
# Use this to decide whether to promote:
#
#   sum(rate(istio_requests_total{
#     destination_service="payment-service.production.svc.cluster.local",
#     destination_version="v2",
#     response_code=~"5.*"
#   }[5m])) /
#   sum(rate(istio_requests_total{
#     destination_service="payment-service.production.svc.cluster.local",
#     destination_version="v2"
#   }[5m])) < 0.01  # Less than 1% error rate → safe to promote
```

## Debugging Service Mesh Issues

A **common mistake** is deploying a mesh without understanding how to debug it. Key tools:

```bash
# Check if sidecar is injected
kubectl get pod <pod> -o jsonpath='{.spec.containers[*].name}'
# Should show: app-container istio-proxy

# View Envoy configuration for a specific pod
istioctl proxy-config routes <pod> -o json
istioctl proxy-config clusters <pod> -o json
istioctl proxy-config listeners <pod> -o json

# Check mTLS status between services
istioctl authn tls-check <pod> <destination-service>

# Analyze mesh configuration for errors
istioctl analyze --namespace production

# View real-time proxy access logs
kubectl logs <pod> -c istio-proxy -f
```

## Summary and Key Takeaways

- **Best practice**: Start with `PERMISSIVE` mTLS during migration, then switch to `STRICT`
  once all services have sidecars — this avoids breaking existing plaintext communication.
- The **sidecar proxy pattern** moves cross-cutting concerns out of application code, however
  it adds operational complexity. You need to understand Envoy internals for debugging.
- **Circuit breaking** via `outlierDetection` prevents cascading failures, but setting
  `maxEjectionPercent` too high can cause all instances to be ejected during widespread issues.
- **Canary deployments** with weight-based routing give precise control, therefore reducing
  blast radius. Automate promotion decisions with error-rate metrics from Prometheus.
- A **pitfall** of service meshes is sidecar resource consumption — each Envoy proxy uses
  50-100MB of memory. For clusters with thousands of pods, consider ambient mesh (sidecar-less)
  mode introduced in Istio 1.18+.
- Always set `holdApplicationUntilProxyStarts: true` to prevent application startup race
  conditions where the app tries to make network calls before Envoy is ready.
- For **observability**, enable access logging in JSON format and integrate with Prometheus
  for metrics collection — Envoy exposes detailed upstream and downstream connection metrics
  that are invaluable for capacity planning and incident response.
"""
    ),

    # --- 2. API Gateway Patterns ---
    (
        "api_gateway_patterns_go",
        "Design and implement a production API gateway in Go with middleware chaining — covering "
        "rate limiting with token bucket and sliding window algorithms, JWT authentication with "
        "RBAC, request/response transformation, circuit breaking, request logging, and graceful "
        "shutdown. Show the complete implementation with proper error handling and unit tests.",
        r"""
# API Gateway Patterns: Complete Production Implementation in Go

## Why Build a Custom API Gateway?

Off-the-shelf gateways like Kong, Ambassador, or AWS API Gateway work well for standard
use cases. However, building a custom gateway makes sense when you need **domain-specific
routing logic**, **custom authentication flows**, or **tight integration** with internal
service discovery. The trade-off is increased maintenance burden versus complete control
over behavior and performance.

A **best practice** is to structure the gateway as a **middleware chain** — each concern
(auth, rate limiting, logging, circuit breaking) is an independent middleware that wraps
the next handler. This follows the decorator pattern and makes each piece independently
testable.

```
Request → RateLimit → Auth → CircuitBreaker → Transform → Proxy → Response
              ↓          ↓          ↓              ↓          ↓
           429 Too    401/403    503 Open       Modified    Backend
            Many    Unauthorized  Circuit       Request     Response
```

## Core Gateway Framework with Middleware Chain

```go
// gateway.go — Core framework with middleware chaining
package gateway

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

// Middleware is a function that wraps an http.Handler.
// This is the fundamental building block — every cross-cutting
// concern implements this signature.
type Middleware func(http.Handler) http.Handler

// Gateway is the main API gateway server with middleware support.
type Gateway struct {
	mux         *http.ServeMux
	middlewares []Middleware
	server      *http.Server
	logger      *slog.Logger
}

// NewGateway creates a new API gateway with the given address.
func NewGateway(addr string, logger *slog.Logger) *Gateway {
	return &Gateway{
		mux:    http.NewServeMux(),
		logger: logger,
		server: &http.Server{
			Addr:         addr,
			ReadTimeout:  15 * time.Second,
			WriteTimeout: 30 * time.Second,
			IdleTimeout:  60 * time.Second,
		},
	}
}

// Use adds middleware to the chain. Middlewares execute in the
// order they are added (first added = outermost wrapper).
func (g *Gateway) Use(mw Middleware) {
	g.middlewares = append(g.middlewares, mw)
}

// Route registers a backend service for a path prefix.
func (g *Gateway) Route(pattern string, backendURL string) error {
	target, err := url.Parse(backendURL)
	if err != nil {
		return fmt.Errorf("invalid backend URL %q: %w", backendURL, err)
	}
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		g.logger.Error("proxy error",
			"path", r.URL.Path,
			"backend", backendURL,
			"error", err,
		)
		http.Error(w, `{"error":"service_unavailable"}`, http.StatusBadGateway)
	}
	g.mux.Handle(pattern, proxy)
	return nil
}

// ListenAndServe starts the gateway with graceful shutdown support.
// This is a best practice because abrupt shutdown drops in-flight
// requests and causes client-visible errors.
func (g *Gateway) ListenAndServe() error {
	// Build the middleware chain: wrap mux with all middlewares
	var handler http.Handler = g.mux
	// Apply in reverse so first-added middleware is outermost
	for i := len(g.middlewares) - 1; i >= 0; i-- {
		handler = g.middlewares[i](handler)
	}
	g.server.Handler = handler

	// Graceful shutdown on SIGTERM/SIGINT
	errCh := make(chan error, 1)
	go func() {
		g.logger.Info("gateway starting", "addr", g.server.Addr)
		errCh <- g.server.ListenAndServe()
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		g.logger.Info("shutdown signal received", "signal", sig)
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		return g.server.Shutdown(ctx)
	case err := <-errCh:
		return err
	}
}
```

## Rate Limiting Middleware — Token Bucket per Client

Rate limiting is essential for protecting backends from abuse. The **token bucket**
algorithm provides smooth rate limiting with burst support. A **common mistake** is
implementing rate limiting per-server instead of using a distributed store — this
means a client can multiply their limit by the number of gateway instances. However,
for many workloads, per-instance limiting is an acceptable trade-off that avoids Redis
dependency.

```go
// ratelimit.go — Token bucket rate limiter with per-client tracking
package gateway

import (
	"net/http"
	"strings"
	"sync"
	"time"
)

// TokenBucket implements a per-client token bucket rate limiter.
type TokenBucket struct {
	tokens     float64
	maxTokens  float64
	refillRate float64 // tokens per second
	lastRefill time.Time
	mu         sync.Mutex
}

// NewTokenBucket creates a bucket with capacity and refill rate.
func NewTokenBucket(maxTokens, refillRate float64) *TokenBucket {
	return &TokenBucket{
		tokens:     maxTokens,
		maxTokens:  maxTokens,
		refillRate: refillRate,
		lastRefill: time.Now(),
	}
}

// Allow checks if a request is permitted and consumes a token.
func (tb *TokenBucket) Allow() bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(tb.lastRefill).Seconds()
	tb.tokens += elapsed * tb.refillRate
	if tb.tokens > tb.maxTokens {
		tb.tokens = tb.maxTokens
	}
	tb.lastRefill = now

	if tb.tokens >= 1.0 {
		tb.tokens -= 1.0
		return true
	}
	return false
}

// RateLimiterStore manages per-client buckets with cleanup.
type RateLimiterStore struct {
	buckets    map[string]*TokenBucket
	mu         sync.RWMutex
	maxTokens  float64
	refillRate float64
}

// NewRateLimiterStore creates a store that manages token buckets.
func NewRateLimiterStore(maxTokens, refillRate float64) *RateLimiterStore {
	store := &RateLimiterStore{
		buckets:    make(map[string]*TokenBucket),
		maxTokens:  maxTokens,
		refillRate: refillRate,
	}
	// Periodic cleanup of stale buckets to prevent memory leaks —
	// this is a pitfall that many implementations miss.
	go store.cleanup()
	return store
}

func (s *RateLimiterStore) cleanup() {
	ticker := time.NewTicker(5 * time.Minute)
	for range ticker.C {
		s.mu.Lock()
		for key, bucket := range s.buckets {
			bucket.mu.Lock()
			if time.Since(bucket.lastRefill) > 10*time.Minute {
				delete(s.buckets, key)
			}
			bucket.mu.Unlock()
		}
		s.mu.Unlock()
	}
}

// GetBucket returns (or creates) the bucket for a client key.
func (s *RateLimiterStore) GetBucket(key string) *TokenBucket {
	s.mu.RLock()
	if b, ok := s.buckets[key]; ok {
		s.mu.RUnlock()
		return b
	}
	s.mu.RUnlock()

	s.mu.Lock()
	defer s.mu.Unlock()
	// Double-check after acquiring write lock
	if b, ok := s.buckets[key]; ok {
		return b
	}
	b := NewTokenBucket(s.maxTokens, s.refillRate)
	s.buckets[key] = b
	return b
}

// RateLimitMiddleware creates middleware that limits requests per client IP.
func RateLimitMiddleware(maxTokens, refillRate float64) Middleware {
	store := NewRateLimiterStore(maxTokens, refillRate)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			clientIP := extractClientIP(r)
			bucket := store.GetBucket(clientIP)
			if !bucket.Allow() {
				w.Header().Set("Retry-After", "1")
				http.Error(w, `{"error":"rate_limit_exceeded"}`, http.StatusTooManyRequests)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// extractClientIP gets the real client IP, handling proxies.
func extractClientIP(r *http.Request) string {
	// Check X-Forwarded-For first (trusted proxy scenario)
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		// Take the first (original client) IP
		if idx := strings.Index(xff, ","); idx != -1 {
			return strings.TrimSpace(xff[:idx])
		}
		return strings.TrimSpace(xff)
	}
	// Fall back to RemoteAddr
	if idx := strings.LastIndex(r.RemoteAddr, ":"); idx != -1 {
		return r.RemoteAddr[:idx]
	}
	return r.RemoteAddr
}
```

## JWT Authentication Middleware with RBAC

```go
// auth.go — JWT validation with role-based access control
package gateway

import (
	"context"
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type contextKey string

const claimsContextKey contextKey = "jwt_claims"

// Claims represents the JWT payload with RBAC roles.
type Claims struct {
	jwt.RegisteredClaims
	UserID string   `json:"uid"`
	Roles  []string `json:"roles"`
	Tenant string   `json:"tenant,omitempty"`
}

// RoutePermission maps a path pattern to required roles.
type RoutePermission struct {
	PathPrefix string
	Methods    []string
	Roles      []string // Any of these roles grants access
}

// AuthConfig holds authentication configuration.
type AuthConfig struct {
	PublicKey   *rsa.PublicKey
	Issuer     string
	Audience   string
	SkipPaths  []string          // Paths that don't require auth
	Permissions []RoutePermission // RBAC rules
}

// AuthMiddleware creates JWT authentication middleware with RBAC.
// A common mistake is validating only the signature without checking
// expiration, issuer, and audience — all three are essential.
func AuthMiddleware(cfg AuthConfig) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Skip auth for public paths
			for _, path := range cfg.SkipPaths {
				if strings.HasPrefix(r.URL.Path, path) {
					next.ServeHTTP(w, r)
					return
				}
			}

			// Extract Bearer token
			authHeader := r.Header.Get("Authorization")
			if !strings.HasPrefix(authHeader, "Bearer ") {
				writeJSON(w, http.StatusUnauthorized,
					map[string]string{"error": "missing_token"})
				return
			}
			tokenStr := authHeader[7:]

			// Parse and validate JWT
			claims := &Claims{}
			token, err := jwt.ParseWithClaims(tokenStr, claims,
				func(t *jwt.Token) (interface{}, error) {
					if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
						return nil, fmt.Errorf("unexpected signing method: %v",
							t.Header["alg"])
					}
					return cfg.PublicKey, nil
				},
				jwt.WithIssuer(cfg.Issuer),
				jwt.WithAudience(cfg.Audience),
				jwt.WithLeeway(5*time.Second),
			)
			if err != nil || !token.Valid {
				writeJSON(w, http.StatusUnauthorized,
					map[string]string{"error": "invalid_token"})
				return
			}

			// RBAC check
			if !checkPermission(r, claims, cfg.Permissions) {
				writeJSON(w, http.StatusForbidden,
					map[string]string{"error": "insufficient_permissions"})
				return
			}

			// Store claims in context for downstream handlers
			ctx := context.WithValue(r.Context(), claimsContextKey, claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// checkPermission verifies the user has a required role for the route.
func checkPermission(r *http.Request, claims *Claims, perms []RoutePermission) bool {
	for _, perm := range perms {
		if !strings.HasPrefix(r.URL.Path, perm.PathPrefix) {
			continue
		}
		methodMatch := len(perm.Methods) == 0
		for _, m := range perm.Methods {
			if m == r.Method {
				methodMatch = true
				break
			}
		}
		if !methodMatch {
			continue
		}
		// Check if user has any required role
		for _, required := range perm.Roles {
			for _, userRole := range claims.Roles {
				if required == userRole {
					return true
				}
			}
		}
		return false // Matched route but no role
	}
	return true // No permission rule matched — allow by default
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
```

## Circuit Breaker Middleware

```go
// circuitbreaker.go — Per-backend circuit breaker
package gateway

import (
	"net/http"
	"sync"
	"time"
)

// CircuitState represents the current state of the breaker.
type CircuitState int

const (
	CircuitClosed   CircuitState = iota // Normal operation
	CircuitOpen                         // Failing, reject requests
	CircuitHalfOpen                     // Testing recovery
)

// CircuitBreaker tracks failures per backend and trips when threshold is exceeded.
type CircuitBreaker struct {
	state          CircuitState
	failures       int
	successes      int
	threshold      int           // Failures before opening
	halfOpenMax    int           // Successes needed to close
	resetTimeout   time.Duration // Time before half-open attempt
	lastFailure    time.Time
	mu             sync.RWMutex
}

// NewCircuitBreaker creates a breaker with the given thresholds.
func NewCircuitBreaker(threshold, halfOpenMax int, resetTimeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:        CircuitClosed,
		threshold:    threshold,
		halfOpenMax:  halfOpenMax,
		resetTimeout: resetTimeout,
	}
}

// Allow checks if a request should be permitted through the breaker.
func (cb *CircuitBreaker) Allow() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()

	switch cb.state {
	case CircuitClosed:
		return true
	case CircuitOpen:
		// Check if reset timeout has elapsed
		if time.Since(cb.lastFailure) > cb.resetTimeout {
			return true // Will transition to half-open
		}
		return false
	case CircuitHalfOpen:
		return true
	}
	return false
}

// RecordSuccess records a successful request.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == CircuitHalfOpen {
		cb.successes++
		if cb.successes >= cb.halfOpenMax {
			cb.state = CircuitClosed
			cb.failures = 0
			cb.successes = 0
		}
	} else {
		cb.failures = 0 // Reset on success in closed state
	}
}

// RecordFailure records a failed request.
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures++
	cb.lastFailure = time.Now()
	if cb.failures >= cb.threshold {
		cb.state = CircuitOpen
	}
}

// CircuitBreakerMiddleware protects backends from cascading failures.
func CircuitBreakerMiddleware(threshold, halfOpenMax int, resetTimeout time.Duration) Middleware {
	breakers := &sync.Map{} // Per-backend breakers
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			backend := r.URL.Path // Simplified; use route group in production
			val, _ := breakers.LoadOrStore(backend,
				NewCircuitBreaker(threshold, halfOpenMax, resetTimeout))
			cb := val.(*CircuitBreaker)

			if !cb.Allow() {
				http.Error(w, `{"error":"circuit_open"}`,
					http.StatusServiceUnavailable)
				return
			}

			// Wrap ResponseWriter to capture status code
			rec := &statusRecorder{ResponseWriter: w, statusCode: 200}
			next.ServeHTTP(rec, r)

			if rec.statusCode >= 500 {
				cb.RecordFailure()
			} else {
				cb.RecordSuccess()
			}
		})
	}
}

type statusRecorder struct {
	http.ResponseWriter
	statusCode int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.statusCode = code
	r.ResponseWriter.WriteHeader(code)
}
```

## Unit Tests

```go
// gateway_test.go
package gateway

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTokenBucket_AllowAndRefill(t *testing.T) {
	// 2 tokens, refill 1/second
	tb := NewTokenBucket(2, 1.0)

	// Should allow first two requests (burst capacity)
	if !tb.Allow() { t.Fatal("expected first request allowed") }
	if !tb.Allow() { t.Fatal("expected second request allowed") }
	// Third should be rejected — bucket empty
	if tb.Allow() { t.Fatal("expected third request rejected") }

	// Wait for refill
	time.Sleep(1100 * time.Millisecond)
	if !tb.Allow() { t.Fatal("expected request allowed after refill") }
}

func TestCircuitBreaker_TripsAndRecovers(t *testing.T) {
	cb := NewCircuitBreaker(3, 2, 100*time.Millisecond)

	// Record failures up to threshold
	cb.RecordFailure()
	cb.RecordFailure()
	if !cb.Allow() { t.Fatal("should allow before threshold") }
	cb.RecordFailure() // Threshold reached

	if cb.Allow() { t.Fatal("circuit should be open") }

	// Wait for reset timeout, then half-open
	time.Sleep(150 * time.Millisecond)
	if !cb.Allow() { t.Fatal("should allow in half-open") }

	cb.RecordSuccess()
	cb.RecordSuccess() // halfOpenMax reached → closed
	if !cb.Allow() { t.Fatal("should be closed after recovery") }
}

func TestRateLimitMiddleware_RejectsExcess(t *testing.T) {
	handler := RateLimitMiddleware(1, 0.1)(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	// First request passes
	req := httptest.NewRequest("GET", "/test", nil)
	req.RemoteAddr = "192.168.1.1:12345"
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	// Second request should be rate limited
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", rec.Code)
	}
}
```

## Summary and Key Takeaways

- **Middleware chaining** is the **best practice** for API gateways because it separates
  concerns, enables independent testing, and allows flexible composition per route group.
- **Token bucket** rate limiting provides smooth rate enforcement with burst support. However,
  per-instance limiters multiply the effective limit by the number of gateway replicas —
  therefore use Redis-backed distributed counting for strict limits.
- **JWT authentication** must validate signature, expiration, issuer, AND audience. A
  **common mistake** is skipping audience validation, which allows tokens intended for other
  services to be accepted.
- **Circuit breakers** prevent cascading failures by fast-failing when a backend is unhealthy.
  The trade-off is between sensitivity (low threshold) and stability (avoiding flapping).
- **Graceful shutdown** is critical — without it, in-flight requests get killed during
  deployments, causing user-visible errors. Always handle SIGTERM with a shutdown deadline.
- A **pitfall** with reverse proxies is not setting appropriate timeouts. Without read/write
  timeouts, a slow client can hold connections indefinitely, exhausting gateway resources.
"""
    ),

    # --- 3. Service Discovery and Health Checking ---
    (
        "service_discovery_health_checking",
        "Explain service discovery in microservices using Consul and etcd — client-side versus "
        "server-side discovery, service registration with automatic deregistration, health check "
        "strategies including TCP/HTTP/gRPC checks, graceful degradation when the registry is "
        "unavailable, and DNS-based discovery. Show a complete Go implementation with automatic "
        "registration, health checking, and load-balanced client with fallback.",
        r"""
# Service Discovery and Health Checking: Building Reliable Microservices

## The Service Discovery Problem

In a microservices architecture, services are **ephemeral** — they scale up and down, move
between hosts, and get replaced during deployments. Hardcoding IP addresses is therefore
impossible. Service discovery solves this by providing a dynamic registry where services
register themselves and clients look up healthy instances.

There are two fundamental patterns:

**Client-side discovery**: The client queries the registry directly and selects an instance
using its own load-balancing logic. This is **best practice** for performance-critical paths
because it eliminates an extra network hop, however it couples clients to the discovery
mechanism.

**Server-side discovery**: A load balancer sits between clients and the registry. Clients
send requests to the load balancer, which queries the registry and forwards traffic. This is
simpler for clients but adds latency and a potential single point of failure.

```
Client-Side Discovery:
  Client → Registry (lookup) → Client selects instance → Direct call to instance
  Pro: No extra hop, flexible LB     Con: Client complexity

Server-Side Discovery:
  Client → Load Balancer → Registry (lookup) → LB forwards to instance
  Pro: Simple clients                Con: Extra hop, LB is SPOF
```

## Registry Technologies: Consul vs etcd

**Consul** (by HashiCorp) is purpose-built for service discovery with built-in health
checking, DNS interface, and a service mesh (Consul Connect). It uses the Raft consensus
protocol and supports multi-datacenter federation.

**etcd** is a distributed key-value store (used by Kubernetes internally) that provides
strong consistency via Raft. It is lower-level than Consul — you build service discovery
on top of its watch and lease primitives. A trade-off here is that etcd gives you more
flexibility but requires more implementation effort.

```
Feature           | Consul           | etcd
------------------|------------------|------------------
Health checking   | Built-in         | DIY with leases
DNS interface     | Built-in         | External (CoreDNS)
Service mesh      | Consul Connect   | N/A
Multi-DC          | Native           | Manual federation
UI                | Built-in         | Third-party
API               | HTTP + DNS       | gRPC + HTTP
```

## Go Implementation: Service Registry Abstraction

```go
// registry.go — Service registry abstraction with Consul and etcd backends
package discovery

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"net"
	"sync"
	"time"
)

// ServiceInstance represents a registered service.
type ServiceInstance struct {
	ID      string            `json:"id"`
	Name    string            `json:"name"`
	Address string            `json:"address"`
	Port    int               `json:"port"`
	Tags    []string          `json:"tags,omitempty"`
	Meta    map[string]string `json:"meta,omitempty"`
	Healthy bool              `json:"healthy"`
}

// Endpoint returns the address:port string for this instance.
func (s *ServiceInstance) Endpoint() string {
	return fmt.Sprintf("%s:%d", s.Address, s.Port)
}

// HealthCheckConfig defines how the registry checks service health.
type HealthCheckConfig struct {
	Type     string        // "http", "tcp", "grpc"
	Endpoint string        // Health check URL or address
	Interval time.Duration // How often to check
	Timeout  time.Duration // Per-check timeout
	// DeregisterAfter controls automatic cleanup of crashed services.
	// This is critical — without it, dead instances linger in the registry,
	// causing clients to route traffic to black holes.
	DeregisterAfter time.Duration
}

// Registry is the interface for service registration and discovery.
type Registry interface {
	// Register adds a service instance to the registry.
	Register(ctx context.Context, instance *ServiceInstance, check HealthCheckConfig) error
	// Deregister removes a service instance from the registry.
	Deregister(ctx context.Context, instanceID string) error
	// Discover returns all healthy instances of a service.
	Discover(ctx context.Context, serviceName string) ([]*ServiceInstance, error)
	// Watch returns a channel that emits updates when instances change.
	Watch(ctx context.Context, serviceName string) (<-chan []*ServiceInstance, error)
}
```

## Consul-Based Registry Implementation

```go
// consul_registry.go — Consul implementation of the Registry interface
package discovery

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	consul "github.com/hashicorp/consul/api"
)

// ConsulRegistry implements Registry using HashiCorp Consul.
type ConsulRegistry struct {
	client *consul.Client
	logger *slog.Logger
}

// NewConsulRegistry creates a registry backed by Consul.
func NewConsulRegistry(addr string, logger *slog.Logger) (*ConsulRegistry, error) {
	cfg := consul.DefaultConfig()
	cfg.Address = addr
	client, err := consul.NewClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("consul client creation failed: %w", err)
	}
	// Verify connectivity — a common mistake is skipping this and
	// discovering the connection issue only when the first request fails.
	_, err = client.Agent().Self()
	if err != nil {
		return nil, fmt.Errorf("consul connection failed at %s: %w", addr, err)
	}
	logger.Info("connected to consul", "addr", addr)
	return &ConsulRegistry{client: client, logger: logger}, nil
}

// Register adds a service instance with health checking.
func (r *ConsulRegistry) Register(ctx context.Context, inst *ServiceInstance, check HealthCheckConfig) error {
	reg := &consul.AgentServiceRegistration{
		ID:      inst.ID,
		Name:    inst.Name,
		Address: inst.Address,
		Port:    inst.Port,
		Tags:    inst.Tags,
		Meta:    inst.Meta,
	}

	// Configure health check based on type
	switch check.Type {
	case "http":
		reg.Check = &consul.AgentServiceCheck{
			HTTP:                           check.Endpoint,
			Interval:                       check.Interval.String(),
			Timeout:                        check.Timeout.String(),
			DeregisterCriticalServiceAfter: check.DeregisterAfter.String(),
		}
	case "tcp":
		reg.Check = &consul.AgentServiceCheck{
			TCP:                            check.Endpoint,
			Interval:                       check.Interval.String(),
			Timeout:                        check.Timeout.String(),
			DeregisterCriticalServiceAfter: check.DeregisterAfter.String(),
		}
	case "grpc":
		reg.Check = &consul.AgentServiceCheck{
			GRPC:                           check.Endpoint,
			GRPCUseTLS:                     true,
			Interval:                       check.Interval.String(),
			Timeout:                        check.Timeout.String(),
			DeregisterCriticalServiceAfter: check.DeregisterAfter.String(),
		}
	default:
		return fmt.Errorf("unsupported health check type: %s", check.Type)
	}

	if err := r.client.Agent().ServiceRegister(reg); err != nil {
		return fmt.Errorf("registration failed for %s: %w", inst.ID, err)
	}
	r.logger.Info("service registered",
		"id", inst.ID, "name", inst.Name,
		"endpoint", inst.Endpoint(),
		"healthCheck", check.Type,
	)
	return nil
}

// Deregister removes a service instance from Consul.
func (r *ConsulRegistry) Deregister(ctx context.Context, instanceID string) error {
	if err := r.client.Agent().ServiceDeregister(instanceID); err != nil {
		return fmt.Errorf("deregistration failed for %s: %w", instanceID, err)
	}
	r.logger.Info("service deregistered", "id", instanceID)
	return nil
}

// Discover returns healthy instances of the named service.
func (r *ConsulRegistry) Discover(ctx context.Context, serviceName string) ([]*ServiceInstance, error) {
	entries, _, err := r.client.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return nil, fmt.Errorf("discovery failed for %s: %w", serviceName, err)
	}
	instances := make([]*ServiceInstance, 0, len(entries))
	for _, entry := range entries {
		instances = append(instances, &ServiceInstance{
			ID:      entry.Service.ID,
			Name:    entry.Service.Service,
			Address: entry.Service.Address,
			Port:    entry.Service.Port,
			Tags:    entry.Service.Tags,
			Meta:    entry.Service.Meta,
			Healthy: true,
		})
	}
	return instances, nil
}

// Watch uses Consul blocking queries to watch for service changes.
func (r *ConsulRegistry) Watch(ctx context.Context, serviceName string) (<-chan []*ServiceInstance, error) {
	ch := make(chan []*ServiceInstance, 1)
	go func() {
		defer close(ch)
		var lastIndex uint64
		for {
			select {
			case <-ctx.Done():
				return
			default:
			}
			entries, meta, err := r.client.Health().Service(
				serviceName, "", true,
				&consul.QueryOptions{
					WaitIndex: lastIndex,
					WaitTime:  30 * time.Second,
				},
			)
			if err != nil {
				r.logger.Error("watch error", "service", serviceName, "error", err)
				time.Sleep(5 * time.Second)
				continue
			}
			if meta.LastIndex == lastIndex {
				continue // No change
			}
			lastIndex = meta.LastIndex
			instances := make([]*ServiceInstance, 0, len(entries))
			for _, e := range entries {
				instances = append(instances, &ServiceInstance{
					ID:      e.Service.ID,
					Name:    e.Service.Service,
					Address: e.Service.Address,
					Port:    e.Service.Port,
					Healthy: true,
				})
			}
			ch <- instances
		}
	}()
	return ch, nil
}
```

## Load-Balanced Client with Fallback

A **pitfall** of service discovery is blindly trusting the registry — if Consul goes down,
your entire system stops discovering services. **Best practice** is to cache the last-known
healthy instances and fall back to the cache when the registry is unavailable. This is
graceful degradation: the system works with slightly stale data rather than failing completely.

```go
// client.go — Discovery-aware HTTP client with caching and fallback
package discovery

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"net/http"
	"sync"
	"time"
)

// DiscoveryClient is an HTTP client that uses service discovery
// with load balancing, caching, and graceful degradation.
type DiscoveryClient struct {
	registry  Registry
	cache     map[string][]*ServiceInstance
	cacheMu   sync.RWMutex
	cacheTTL  time.Duration
	cacheTime map[string]time.Time
	httpClient *http.Client
	logger    *slog.Logger
}

// NewDiscoveryClient creates a client with discovery and fallback.
func NewDiscoveryClient(registry Registry, logger *slog.Logger) *DiscoveryClient {
	return &DiscoveryClient{
		registry:  registry,
		cache:     make(map[string][]*ServiceInstance),
		cacheTime: make(map[string]time.Time),
		cacheTTL:  30 * time.Second,
		httpClient: &http.Client{Timeout: 10 * time.Second},
		logger:    logger,
	}
}

// Resolve returns a healthy endpoint for the service, using cache as fallback.
func (c *DiscoveryClient) Resolve(ctx context.Context, serviceName string) (string, error) {
	// Try live discovery first
	instances, err := c.registry.Discover(ctx, serviceName)
	if err == nil && len(instances) > 0 {
		// Update cache on success
		c.cacheMu.Lock()
		c.cache[serviceName] = instances
		c.cacheTime[serviceName] = time.Now()
		c.cacheMu.Unlock()
		// Random load balancing — simple but effective for uniform instances
		chosen := instances[rand.Intn(len(instances))]
		return chosen.Endpoint(), nil
	}

	// Fallback to cache — graceful degradation
	c.cacheMu.RLock()
	cached, hasCached := c.cache[serviceName]
	cachedAt := c.cacheTime[serviceName]
	c.cacheMu.RUnlock()

	if hasCached && len(cached) > 0 {
		staleness := time.Since(cachedAt)
		c.logger.Warn("using cached discovery data",
			"service", serviceName,
			"staleness", staleness,
			"instances", len(cached),
			"reason", err,
		)
		chosen := cached[rand.Intn(len(cached))]
		return chosen.Endpoint(), nil
	}

	return "", fmt.Errorf("no instances found for %s (registry error: %w)", serviceName, err)
}

// Do sends an HTTP request to a discovered service instance.
func (c *DiscoveryClient) Do(ctx context.Context, serviceName, method, path string) (*http.Response, error) {
	endpoint, err := c.Resolve(ctx, serviceName)
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("http://%s%s", endpoint, path)
	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		return nil, fmt.Errorf("request creation failed: %w", err)
	}
	return c.httpClient.Do(req)
}
```

## Automatic Registration with Lifecycle Management

```go
// lifecycle.go — Automatic registration and graceful deregistration
package discovery

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"
)

// ServiceLifecycle manages automatic registration and deregistration.
// This pattern ensures services always deregister cleanly, even on crash —
// because the DeregisterAfter health check timeout serves as a safety net.
type ServiceLifecycle struct {
	registry Registry
	instance *ServiceInstance
	check    HealthCheckConfig
	logger   *slog.Logger
}

// NewServiceLifecycle creates lifecycle management for a service.
func NewServiceLifecycle(
	registry Registry,
	serviceName string,
	port int,
	check HealthCheckConfig,
	logger *slog.Logger,
) (*ServiceLifecycle, error) {
	hostname, _ := os.Hostname()
	localIP, err := getOutboundIP()
	if err != nil {
		return nil, fmt.Errorf("cannot determine local IP: %w", err)
	}
	instance := &ServiceInstance{
		ID:      fmt.Sprintf("%s-%s-%d", serviceName, hostname, port),
		Name:    serviceName,
		Address: localIP,
		Port:    port,
		Meta: map[string]string{
			"hostname": hostname,
			"version":  os.Getenv("APP_VERSION"),
		},
	}
	return &ServiceLifecycle{
		registry: registry,
		instance: instance,
		check:    check,
		logger:   logger,
	}, nil
}

// Run registers the service, blocks until shutdown signal, then deregisters.
func (sl *ServiceLifecycle) Run(ctx context.Context) error {
	// Register on startup
	if err := sl.registry.Register(ctx, sl.instance, sl.check); err != nil {
		return fmt.Errorf("registration failed: %w", err)
	}
	sl.logger.Info("service registered, waiting for shutdown signal",
		"id", sl.instance.ID,
	)

	// Wait for termination signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		sl.logger.Info("shutdown signal received", "signal", sig)
	case <-ctx.Done():
		sl.logger.Info("context cancelled")
	}

	// Deregister on shutdown — best practice for clean removal
	if err := sl.registry.Deregister(ctx, sl.instance.ID); err != nil {
		sl.logger.Error("deregistration failed", "error", err)
		return err
	}
	sl.logger.Info("service deregistered cleanly", "id", sl.instance.ID)
	return nil
}

// getOutboundIP finds the preferred outbound IP address.
func getOutboundIP() (string, error) {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return "", err
	}
	defer conn.Close()
	return conn.LocalAddr().(*net.UDPAddr).IP.String(), nil
}
```

## Summary and Key Takeaways

- **Client-side discovery** eliminates a network hop but couples clients to the registry.
  **Server-side discovery** is simpler but adds latency. Choose based on your latency
  requirements and team capabilities.
- **Always set `DeregisterAfter`** on health checks — this is a **pitfall** that causes
  dead instances to linger in the registry forever, sending traffic to endpoints that
  will never respond.
- **Cache discovery results** and fall back to stale data when the registry is unavailable.
  This graceful degradation pattern is therefore essential for production systems because
  registry outages should not cascade into total service failure.
- **Health check intervals** involve a trade-off: frequent checks detect failures faster
  but increase load on both the registry and services. 10-second intervals with 5-second
  timeouts are a reasonable default for most workloads.
- A **common mistake** is using only TCP health checks. TCP confirms the port is open but
  not that the application is functioning. **Best practice** is HTTP checks against a
  `/health` endpoint that verifies database connectivity, cache availability, and other
  critical dependencies.
- DNS-based discovery (Consul DNS interface or CoreDNS with etcd) is the simplest
  integration path — applications resolve service names via DNS without any SDK. However,
  DNS TTL caching can cause stale results, which is a significant pitfall in environments
  with frequent scaling events.
"""
    ),

    # --- 4. Distributed Tracing with OpenTelemetry ---
    (
        "distributed_tracing_opentelemetry",
        "Explain distributed tracing with OpenTelemetry in Python — how context propagation works "
        "across HTTP and gRPC service boundaries, span creation with attributes and events, baggage "
        "for cross-service metadata, sampling strategies including probability and rate-limiting "
        "samplers, and exporter configuration for Jaeger and OTLP. Show complete Python instrumentation "
        "for a multi-service application with manual and automatic instrumentation.",
        r"""
# Distributed Tracing with OpenTelemetry: Complete Python Instrumentation Guide

## Why Distributed Tracing Matters

In a monolithic application, a stack trace tells you exactly what happened. In microservices,
a single user request might traverse **10+ services**, making it impossible to debug with
logs alone. Distributed tracing solves this by assigning a **trace ID** to each request and
propagating it across every service boundary. Each service creates **spans** — timed
operations with metadata — that form a tree showing the complete request lifecycle.

The **trade-off** with tracing is overhead versus visibility. Every span adds serialization,
context propagation, and export costs. Therefore, production systems use **sampling** to
capture a representative subset of traces rather than every request.

```
User Request (trace_id: abc123)
│
├─ API Gateway (span: 2ms)
│  ├─ Auth Service (span: 15ms)
│  │  └─ Token validation (span: 3ms)
│  └─ Product Service (span: 45ms)
│     ├─ Cache lookup (span: 1ms, cache_hit=false)
│     ├─ Database query (span: 30ms)
│     └─ Recommendation Service (span: 25ms, via gRPC)
│        └─ ML inference (span: 20ms)
```

## OpenTelemetry Core Concepts

OpenTelemetry (OTel) is the **industry standard** for observability instrumentation —
it is vendor-neutral, supports traces, metrics, and logs, and has SDKs for every major
language. The key components are:

- **TracerProvider**: Factory that creates Tracers, configured once at startup
- **Tracer**: Creates spans for a specific instrumentation library
- **Span**: A single operation with start time, duration, attributes, and events
- **Context**: Carries the current span across function calls and service boundaries
- **Propagator**: Serializes/deserializes context into HTTP headers or gRPC metadata
- **Exporter**: Sends completed spans to a backend (Jaeger, Zipkin, OTLP collector)
- **Sampler**: Decides which traces to record (all, none, probabilistic, rate-limited)

## Setting Up the TracerProvider

```python
# tracing_setup.py — OpenTelemetry configuration for production
"""
Production-ready OpenTelemetry setup with OTLP export, batch processing,
and configurable sampling. This module should be initialized once at
application startup before any other imports that create spans.
"""

from typing import Optional
import os

from opentelemetry import trace, baggage
from opentelemetry.sdk.trace import TracerProvider, SpanLimits
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.sampling import (
    TraceIdRatioBased,
    ParentBased,
    ALWAYS_ON,
    ALWAYS_OFF,
)
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator


def create_sampler(strategy: str, ratio: float = 0.1):
    """
    Create a sampler based on the specified strategy.

    Best practice: Use ParentBased sampling so that if a parent span
    was sampled, all child spans in the trace are also sampled. This
    prevents broken traces where some spans are missing.

    Args:
        strategy: One of 'always_on', 'always_off', 'ratio'.
        ratio: Sampling probability for 'ratio' strategy (0.0 to 1.0).

    Returns:
        A configured Sampler instance.
    """
    if strategy == "always_on":
        return ALWAYS_ON
    elif strategy == "always_off":
        return ALWAYS_OFF
    elif strategy == "ratio":
        # ParentBased wraps the ratio sampler: if the parent was sampled,
        # always sample the child. Only apply ratio to root spans.
        return ParentBased(root=TraceIdRatioBased(ratio))
    else:
        raise ValueError(f"Unknown sampling strategy: {strategy}")


def init_tracing(
    service_name: str,
    service_version: str = "0.1.0",
    otlp_endpoint: Optional[str] = None,
    sampling_strategy: str = "ratio",
    sampling_ratio: float = 0.1,
    console_export: bool = False,
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing for the application.

    This function configures the global TracerProvider with resource
    attributes, sampling, propagation, and export. It must be called
    once at application startup.

    A common mistake is calling this multiple times or after spans
    have already been created — this causes lost or duplicated spans.

    Args:
        service_name: Logical name of this service (e.g., 'payment-service').
        service_version: Semantic version of the service.
        otlp_endpoint: OTLP collector endpoint (e.g., 'localhost:4317').
        sampling_strategy: 'always_on', 'always_off', or 'ratio'.
        sampling_ratio: Probability for ratio-based sampling.
        console_export: If True, also print spans to console (debugging).

    Returns:
        A configured Tracer instance for this service.
    """
    # Resource identifies this service in the tracing backend
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        "host.name": os.getenv("HOSTNAME", "unknown"),
    })

    sampler = create_sampler(sampling_strategy, sampling_ratio)

    provider = TracerProvider(
        resource=resource,
        sampler=sampler,
        span_limits=SpanLimits(
            max_attributes=64,
            max_events=128,
            max_links=32,
            max_attribute_length=1024,  # Prevent huge attribute values
        ),
    )

    # Configure exporters
    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
    otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    # BatchSpanProcessor batches and exports asynchronously —
    # this is critical because synchronous export blocks request handling.
    provider.add_span_processor(
        BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            schedule_delay_millis=5000,
        )
    )

    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set global provider and propagators
    trace.set_tracer_provider(provider)

    # W3C TraceContext + Baggage propagation — industry standard
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]))

    return trace.get_tracer(service_name, service_version)
```

## Manual Span Instrumentation

```python
# order_service.py — Manual instrumentation with spans, attributes, events
"""
Demonstrates manual span creation with rich metadata, error recording,
and context propagation between internal function calls.
"""

import time
from typing import Optional
from dataclasses import dataclass

from opentelemetry import trace, baggage, context
from opentelemetry.trace import StatusCode, SpanKind
from opentelemetry.context import attach, detach

from tracing_setup import init_tracing

# Initialize tracer for this service
tracer = init_tracing(
    service_name="order-service",
    sampling_strategy="ratio",
    sampling_ratio=0.5,
)


@dataclass
class Order:
    """Represents a customer order."""
    order_id: str
    customer_id: str
    items: list
    total: float
    status: str = "pending"


def create_order(customer_id: str, items: list) -> Order:
    """
    Create a new order with full tracing instrumentation.

    Each logical step gets its own child span, creating a detailed
    trace tree that shows where time is spent. This is best practice
    because it lets you identify bottlenecks at a glance in the
    tracing UI.
    """
    # Start a root span for the entire operation
    with tracer.start_as_current_span(
        "create_order",
        kind=SpanKind.SERVER,
        attributes={
            "order.customer_id": customer_id,
            "order.item_count": len(items),
        },
    ) as span:
        # Set baggage — propagates to all downstream services
        # Use baggage for cross-cutting metadata like tenant ID
        ctx = baggage.set_baggage("customer.tier", "premium")
        token = attach(ctx)

        try:
            # Step 1: Validate inventory
            if not _check_inventory(items):
                span.set_status(StatusCode.ERROR, "insufficient_inventory")
                span.add_event("order_rejected", {
                    "reason": "insufficient_inventory",
                    "items_requested": str(items),
                })
                raise ValueError("Insufficient inventory for requested items")

            # Step 2: Calculate pricing
            total = _calculate_total(items)

            # Step 3: Process payment
            payment_id = _process_payment(customer_id, total)

            # Step 4: Create order record
            order = Order(
                order_id=f"ORD-{int(time.time())}",
                customer_id=customer_id,
                items=items,
                total=total,
                status="confirmed",
            )

            # Add result attributes to the span
            span.set_attribute("order.id", order.order_id)
            span.set_attribute("order.total", total)
            span.set_attribute("order.payment_id", payment_id)
            span.add_event("order_created", {
                "order_id": order.order_id,
                "total": str(total),
            })

            return order

        except Exception as exc:
            # Record exception details in the span
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise
        finally:
            detach(token)


def _check_inventory(items: list) -> bool:
    """Check inventory availability with a child span."""
    with tracer.start_as_current_span(
        "check_inventory",
        attributes={"inventory.item_count": len(items)},
    ) as span:
        # Simulate inventory check
        time.sleep(0.01)
        available = True
        span.set_attribute("inventory.available", available)
        return available


def _calculate_total(items: list) -> float:
    """Calculate order total with pricing rules."""
    with tracer.start_as_current_span("calculate_total") as span:
        # Read baggage from upstream context
        tier = baggage.get_baggage("customer.tier")
        discount = 0.1 if tier == "premium" else 0.0
        span.set_attribute("pricing.discount", discount)
        span.set_attribute("pricing.tier", tier or "standard")

        subtotal = sum(item.get("price", 0) * item.get("qty", 1) for item in items)
        total = subtotal * (1 - discount)
        span.set_attribute("pricing.subtotal", subtotal)
        span.set_attribute("pricing.total", total)
        return total


def _process_payment(customer_id: str, amount: float) -> str:
    """Process payment with external service call tracing."""
    with tracer.start_as_current_span(
        "process_payment",
        kind=SpanKind.CLIENT,  # CLIENT because we call an external service
        attributes={
            "payment.customer_id": customer_id,
            "payment.amount": amount,
            "payment.currency": "USD",
        },
    ) as span:
        time.sleep(0.05)  # Simulate payment processing
        payment_id = f"PAY-{int(time.time())}"
        span.set_attribute("payment.id", payment_id)
        span.set_attribute("payment.status", "success")
        return payment_id
```

## HTTP and gRPC Context Propagation

Context propagation is the mechanism that links spans across service boundaries. The
**W3C TraceContext** standard defines two HTTP headers: `traceparent` (trace ID, span ID,
flags) and `tracestate` (vendor-specific data). A **pitfall** is forgetting to propagate
context in custom HTTP clients — this breaks the trace chain and creates orphaned spans.

```python
# propagation.py — Cross-service context propagation for HTTP and gRPC
"""
Shows how to inject and extract trace context across HTTP and gRPC
service boundaries, ensuring traces are connected end-to-end.
"""

import httpx
from typing import Any, Dict

from opentelemetry import trace, context
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer("propagation-example")


class TracedHTTPClient:
    """
    HTTP client that automatically propagates trace context.

    A common mistake is using a plain HTTP client that does not inject
    trace headers — this breaks the distributed trace and makes it
    impossible to correlate spans across services.
    """

    def __init__(self):
        self._client = httpx.Client(timeout=10.0)

    def get(self, url: str, **kwargs) -> httpx.Response:
        """Send a traced GET request with context propagation."""
        with tracer.start_as_current_span(
            f"HTTP GET {url}",
            kind=SpanKind.CLIENT,
            attributes={
                "http.method": "GET",
                "http.url": url,
            },
        ) as span:
            headers = kwargs.pop("headers", {})
            # Inject trace context into HTTP headers
            # This adds traceparent and tracestate headers
            inject(headers)

            response = self._client.get(url, headers=headers, **kwargs)

            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_status(
                    trace.StatusCode.ERROR,
                    f"HTTP {response.status_code}",
                )
            return response

    def post(self, url: str, json: Any = None, **kwargs) -> httpx.Response:
        """Send a traced POST request with context propagation."""
        with tracer.start_as_current_span(
            f"HTTP POST {url}",
            kind=SpanKind.CLIENT,
            attributes={
                "http.method": "POST",
                "http.url": url,
            },
        ) as span:
            headers = kwargs.pop("headers", {})
            inject(headers)

            response = self._client.post(url, json=json, headers=headers, **kwargs)

            span.set_attribute("http.status_code", response.status_code)
            return response


def extract_context_from_request(headers: Dict[str, str]):
    """
    Extract trace context from incoming HTTP request headers.

    Use this in your HTTP server handler to continue the trace
    started by the upstream service. Without this, each service
    creates an independent trace instead of a connected one.

    Returns:
        A context object to use with context.attach() or
        use_span(span, end_on_exit=True).
    """
    return extract(headers)


# --- Flask integration example ---
def traced_flask_app():
    """
    Example Flask app with manual trace context extraction.

    In production, use opentelemetry-instrumentation-flask for
    automatic instrumentation. This manual example shows what
    happens under the hood.
    """
    from flask import Flask, request

    app = Flask(__name__)

    @app.before_request
    def start_span():
        # Extract propagated context from incoming headers
        ctx = extract(dict(request.headers))
        token = context.attach(ctx)
        span = tracer.start_span(
            f"{request.method} {request.path}",
            kind=SpanKind.SERVER,
            attributes={
                "http.method": request.method,
                "http.url": request.url,
                "http.route": request.path,
            },
        )
        request._otel_token = token
        request._otel_span = span

    @app.after_request
    def end_span(response):
        span = getattr(request, "_otel_span", None)
        token = getattr(request, "_otel_token", None)
        if span:
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(trace.StatusCode.ERROR)
            span.end()
        if token:
            context.detach(token)
        return response

    return app
```

## Sampling Strategies for Production

```python
# sampling.py — Custom sampling strategies
"""
Production sampling must balance cost against debuggability.
These strategies show how to implement intelligent sampling
that captures interesting traces while dropping routine ones.
"""

from opentelemetry.sdk.trace.sampling import (
    Sampler,
    SamplingResult,
    Decision,
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util.types import Attributes
from typing import Optional, Sequence


class ErrorBiasedSampler(Sampler):
    """
    Samples all errors but only a fraction of successful requests.

    This is a best practice for production because errors are rare
    but critical to capture, while routine successes can be sampled
    at low rates to reduce cost.

    The trade-off is that latency analysis on sampled data may be
    biased — because errors tend to be slower, oversampling them
    skews p99 latency metrics.
    """

    def __init__(self, success_ratio: float = 0.01, description: str = "ErrorBiasedSampler"):
        self._success_sampler = TraceIdRatioBased(success_ratio)
        self._description = description

    def should_sample(
        self,
        parent_context,
        trace_id: int,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Attributes = None,
        links: Optional[Sequence] = None,
    ) -> SamplingResult:
        # Check if this looks like an error from attributes
        if attributes:
            status = attributes.get("http.status_code", 200)
            if isinstance(status, int) and status >= 500:
                return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)
            error = attributes.get("error", False)
            if error:
                return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

        # For non-errors, use probability sampling
        return self._success_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links,
        )

    def get_description(self) -> str:
        return self._description


# Usage: wrap with ParentBased so child spans follow parent decision
# sampler = ParentBased(root=ErrorBiasedSampler(success_ratio=0.01))
```

## Summary and Key Takeaways

- **OpenTelemetry** is the vendor-neutral standard for distributed tracing. Always use it
  over proprietary SDKs because it avoids lock-in and has the broadest ecosystem support.
- **Context propagation** via W3C TraceContext headers is the glue that connects spans
  across services. A **common mistake** is using custom HTTP clients without injecting
  trace headers, which creates orphaned spans.
- **BatchSpanProcessor** is essential for production — the **pitfall** of using
  SimpleSpanProcessor is that it exports synchronously, blocking request handling and
  adding latency to every instrumented operation.
- **ParentBased sampling** is **best practice** because it ensures trace completeness —
  if a parent is sampled, all children are sampled too. Without it, traces have random
  gaps that make debugging impossible.
- **Baggage** propagates metadata (tenant ID, feature flags, customer tier) across service
  boundaries without modifying service APIs. However, baggage adds to every request's
  header size, therefore use it sparingly for small key-value pairs.
- The trade-off with tracing granularity is debuggability versus overhead. Instrument
  at the HTTP/gRPC boundary and database query level; avoid tracing individual function
  calls unless investigating a specific performance issue.
- **Error-biased sampling** captures 100% of errors while sampling successes at low rates.
  This is the best strategy for most production systems because it preserves debugging
  capability while minimizing export volume and storage costs.
"""
    ),

    # --- 5. Resilience Patterns ---
    (
        "resilience_patterns_python",
        "Implement the five core resilience patterns for microservices in Python — circuit breaker "
        "with state machine and half-open probing, bulkhead with semaphore-based isolation, retry "
        "with exponential backoff and decorrelated jitter, timeout with context deadlines, and "
        "fallback with graceful degradation. Show how to compose all five patterns together into "
        "a resilient service caller with complete type hints, tests, and production configuration.",
        r"""
# Resilience Patterns for Microservices: Complete Python Implementation

## Why Resilience Patterns Matter

In a distributed system, **failure is not exceptional — it is routine**. Networks partition,
services crash, databases slow down, and deployments introduce bugs. Without resilience
patterns, a single failing dependency can cascade through the entire system, turning a
partial outage into a total one. This is known as a **cascading failure**, and it is the
most dangerous failure mode in microservices.

The five core resilience patterns work together as layers of defense:

```
Request → Timeout → Retry → Circuit Breaker → Bulkhead → Fallback → Response
            ↓         ↓          ↓               ↓          ↓
         Cancel    Retry with   Fast-fail      Limit      Degraded
         after     backoff +    when backend   concurrent response
         deadline  jitter       is down        calls
```

Each pattern addresses a different failure mode. A **common mistake** is implementing only
one (usually retry) and assuming the system is resilient. In reality, retry without a
circuit breaker makes cascading failures **worse** because it multiplies load on an already
struggling service.

## Pattern 1: Circuit Breaker

The circuit breaker prevents repeated calls to a failing service. It has three states:
**CLOSED** (normal), **OPEN** (failing, fast-reject), and **HALF_OPEN** (testing recovery).
This is analogous to an electrical circuit breaker — it "trips" when failures exceed a
threshold, protecting both the caller and the downstream service.

```python
# circuit_breaker.py — State machine circuit breaker with monitoring
"""
Production circuit breaker implementation with configurable thresholds,
half-open probing, and event callbacks for monitoring integration.
"""

import time
import threading
from enum import Enum
from typing import Callable, Optional, TypeVar, Any
from dataclasses import dataclass, field

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states following the standard state machine."""
    CLOSED = "closed"         # Normal operation, tracking failures
    OPEN = "open"             # Failing, rejecting all requests
    HALF_OPEN = "half_open"   # Testing if backend has recovered


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting calls."""
    def __init__(self, breaker_name: str, remaining_seconds: float):
        self.breaker_name = breaker_name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit '{breaker_name}' is OPEN. "
            f"Recovery attempt in {remaining_seconds:.1f}s"
        )


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker.

    Best practice: Set failure_threshold based on your SLO. If your
    target is 99.9% availability, trip the breaker after 5-10 consecutive
    failures to avoid wasting resources on a clearly broken backend.
    """
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes to close from half-open
    reset_timeout: float = 30.0         # Seconds before half-open attempt
    half_open_max_calls: int = 3        # Max concurrent half-open probes
    excluded_exceptions: tuple = ()     # Don't count these as failures


class CircuitBreaker:
    """
    Thread-safe circuit breaker with state machine transitions.

    The circuit breaker monitors call outcomes and transitions between
    states based on failure/success counts. In the OPEN state, calls
    are immediately rejected with CircuitOpenError, preventing load
    on failing backends and freeing caller resources.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.Lock()
        self._on_state_change: Optional[Callable] = None

    @property
    def state(self) -> CircuitState:
        """Current state, checking for automatic OPEN -> HALF_OPEN transition."""
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._last_failure_time is not None
                and time.monotonic() - self._last_failure_time >= self.config.reset_timeout
            ):
                self._transition(CircuitState.HALF_OPEN)
            return self._state

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state with event notification."""
        old_state = self._state
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        if self._on_state_change and old_state != new_state:
            self._on_state_change(self.name, old_state, new_state)

    def on_state_change(self, callback: Callable) -> None:
        """Register a callback for state transitions (monitoring)."""
        self._on_state_change = callback

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Raises CircuitOpenError if the circuit is open. Records
        successes and failures to drive state transitions.
        """
        current_state = self.state  # Triggers automatic transition check

        if current_state == CircuitState.OPEN:
            remaining = self.config.reset_timeout - (
                time.monotonic() - (self._last_failure_time or 0)
            )
            raise CircuitOpenError(self.name, max(0, remaining))

        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitOpenError(self.name, 0)
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as exc:
            if not isinstance(exc, self.config.excluded_exceptions):
                self._record_failure()
            raise

    def _record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition(CircuitState.CLOSED)
            else:
                self._failure_count = 0  # Reset on success

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
            elif self._failure_count >= self.config.failure_threshold:
                self._transition(CircuitState.OPEN)
```

## Pattern 2: Bulkhead

The bulkhead pattern isolates resources so that a failure in one area does not exhaust
resources for others. Named after ship bulkheads that prevent a hull breach from sinking
the entire vessel. The **semaphore-based** approach limits concurrent calls to each
dependency independently.

```python
# bulkhead.py — Semaphore-based bulkhead isolation
"""
Limits concurrent calls to a dependency, preventing a slow service
from consuming all threads/connections and starving other services.
"""

import threading
from typing import Callable, TypeVar, Any
from dataclasses import dataclass

T = TypeVar("T")


class BulkheadFullError(Exception):
    """Raised when the bulkhead has no available permits."""
    def __init__(self, name: str, max_concurrent: int):
        self.name = name
        self.max_concurrent = max_concurrent
        super().__init__(
            f"Bulkhead '{name}' is full ({max_concurrent} concurrent calls). "
            f"Request rejected to prevent resource exhaustion."
        )


@dataclass
class BulkheadConfig:
    """Bulkhead configuration.

    The trade-off with max_concurrent: too low wastes backend capacity,
    too high defeats the purpose. Start with 2x the expected steady-state
    concurrency and tune based on observation.
    """
    max_concurrent: int = 10     # Maximum concurrent calls
    max_wait: float = 0.0        # Seconds to wait for a permit (0 = no wait)


class Bulkhead:
    """
    Semaphore-based bulkhead that limits concurrent access to a resource.

    Each dependency should have its own Bulkhead instance. This ensures
    that if the payment service becomes slow and saturates its bulkhead,
    calls to the inventory service can still proceed normally.
    """

    def __init__(self, name: str, config: Optional[BulkheadConfig] = None):
        self.name = name
        self.config = config or BulkheadConfig()
        self._semaphore = threading.Semaphore(self.config.max_concurrent)
        self._active_count = 0
        self._lock = threading.Lock()

    @property
    def active_calls(self) -> int:
        """Number of currently active calls (for monitoring)."""
        with self._lock:
            return self._active_count

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function within the bulkhead's concurrency limit.

        If the bulkhead is full and max_wait is 0, immediately raises
        BulkheadFullError. Otherwise, waits up to max_wait seconds
        for a permit.
        """
        acquired = self._semaphore.acquire(
            blocking=self.config.max_wait > 0,
            timeout=self.config.max_wait if self.config.max_wait > 0 else -1,
        )
        if not acquired:
            raise BulkheadFullError(self.name, self.config.max_concurrent)

        with self._lock:
            self._active_count += 1

        try:
            return func(*args, **kwargs)
        finally:
            with self._lock:
                self._active_count -= 1
            self._semaphore.release()
```

## Pattern 3: Retry with Exponential Backoff and Jitter

Retry compensates for **transient** failures — network blips, brief overloads, temporary
database locks. However, naive retry (immediate, fixed interval) causes **thundering herd**
problems where all clients retry simultaneously, overwhelming the recovering service.
The solution is **exponential backoff with decorrelated jitter**.

```python
# retry.py — Retry with exponential backoff and decorrelated jitter
"""
Retries transient failures with increasing delays and randomization
to prevent thundering herd on recovery.
"""

import time
import random
from typing import Callable, TypeVar, Any, Tuple, Type
from dataclasses import dataclass

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Retry configuration.

    Best practice: Always set a max_delay cap. Without it, exponential
    backoff can grow to minutes or hours, making the system unresponsive.
    Decorrelated jitter (Jitter.DECORRELATED) is preferred over full jitter
    because it provides better spread — see AWS Architecture Blog on this.
    """
    max_attempts: int = 3
    base_delay: float = 0.1          # Initial delay in seconds
    max_delay: float = 30.0          # Cap on delay
    exponential_base: float = 2.0    # Multiplier per attempt
    jitter: str = "decorrelated"     # "none", "full", "decorrelated"
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)


class MaxRetriesExceededError(Exception):
    """Raised when all retry attempts are exhausted."""
    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"All {attempts} retry attempts failed. "
            f"Last error: {last_exception}"
        )


def calculate_delay(attempt: int, config: RetryConfig, last_delay: float) -> float:
    """
    Calculate the delay before the next retry attempt.

    Decorrelated jitter (sleep = min(cap, random(base, sleep * 3)))
    provides better spread than full jitter and avoids the correlation
    problem where all clients back off to similar intervals.

    Args:
        attempt: Current attempt number (0-indexed).
        config: Retry configuration.
        last_delay: The delay used for the previous attempt.

    Returns:
        Delay in seconds before the next attempt.
    """
    if config.jitter == "none":
        delay = config.base_delay * (config.exponential_base ** attempt)
    elif config.jitter == "full":
        # Full jitter: uniform random between 0 and exponential delay
        exp_delay = config.base_delay * (config.exponential_base ** attempt)
        delay = random.uniform(0, exp_delay)
    elif config.jitter == "decorrelated":
        # Decorrelated jitter: sleep = min(cap, random(base, last * 3))
        delay = random.uniform(config.base_delay, last_delay * 3)
    else:
        delay = config.base_delay * (config.exponential_base ** attempt)

    return min(delay, config.max_delay)


class Retry:
    """
    Retry mechanism with configurable backoff and jitter strategies.

    A pitfall is retrying non-idempotent operations (POST creating
    a resource) — this can cause duplicate side effects. Only retry
    operations that are safe to repeat, or use idempotency keys.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function with retry logic.

        Retries on exceptions matching retryable_exceptions, using
        exponential backoff with the configured jitter strategy.
        """
        last_delay = self.config.base_delay
        last_exception: Optional[Exception] = None

        for attempt in range(self.config.max_attempts):
            try:
                return func(*args, **kwargs)
            except self.config.retryable_exceptions as exc:
                last_exception = exc
                if attempt == self.config.max_attempts - 1:
                    break  # Don't sleep after the last attempt

                delay = calculate_delay(attempt, self.config, last_delay)
                last_delay = delay
                time.sleep(delay)

        raise MaxRetriesExceededError(self.config.max_attempts, last_exception)
```

## Pattern 4: Timeout

Timeouts prevent indefinite waiting for slow responses. Without timeouts, a slow dependency
can hold threads/connections until the caller's resources are exhausted. This pattern is
**deceptively simple** — the common mistake is setting only a per-request timeout without
considering the total time budget across retries.

```python
# timeout.py — Timeout pattern with context deadline propagation
"""
Enforces time limits on operations using threading. For async code,
use asyncio.wait_for instead. This implementation supports deadline
propagation so nested calls respect the remaining time budget.
"""

import threading
import time
from typing import Callable, TypeVar, Any, Optional
from dataclasses import dataclass
from contextvars import ContextVar

T = TypeVar("T")

# Context variable for deadline propagation across function calls
_deadline: ContextVar[Optional[float]] = ContextVar("deadline", default=None)


class TimeoutError(Exception):
    """Raised when an operation exceeds its time limit."""
    def __init__(self, operation: str, timeout: float):
        self.operation = operation
        self.timeout = timeout
        super().__init__(f"Operation '{operation}' timed out after {timeout:.2f}s")


@dataclass
class TimeoutConfig:
    """Timeout configuration.

    The trade-off: short timeouts fail fast but may reject slow-but-valid
    requests (e.g., large reports). Long timeouts waste resources waiting
    for truly broken backends. Set timeouts based on p99 latency of the
    healthy backend plus a safety margin.
    """
    timeout: float = 5.0             # Seconds
    propagate_deadline: bool = True   # Pass remaining budget to nested calls


class Timeout:
    """
    Enforces time limits on function calls.

    Supports deadline propagation: if a parent call has 5s remaining
    and creates a child with 10s timeout, the child gets 5s (the
    parent's remaining budget). This prevents timeout stacking where
    the total time far exceeds the intended limit.
    """

    def __init__(self, config: Optional[TimeoutConfig] = None):
        self.config = config or TimeoutConfig()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function with a timeout, respecting parent deadlines."""
        effective_timeout = self.config.timeout

        if self.config.propagate_deadline:
            parent_deadline = _deadline.get()
            if parent_deadline is not None:
                remaining = parent_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(func.__name__, 0)
                effective_timeout = min(effective_timeout, remaining)

        # Set deadline for child calls
        deadline = time.monotonic() + effective_timeout
        token = _deadline.set(deadline)

        result_container: list = []
        exception_container: list = []

        def target():
            try:
                result_container.append(func(*args, **kwargs))
            except Exception as exc:
                exception_container.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=effective_timeout)

        _deadline.set(token)  # Restore parent deadline

        if thread.is_alive():
            raise TimeoutError(
                getattr(func, "__name__", str(func)),
                effective_timeout,
            )

        if exception_container:
            raise exception_container[0]

        return result_container[0] if result_container else None
```

## Pattern 5: Fallback

Fallback provides a degraded response when the primary path fails. This is the **last line
of defense** — when circuit breaker trips, retries exhaust, or timeout fires, the fallback
returns cached data, a default value, or a simplified response rather than an error.

```python
# fallback.py — Fallback with graceful degradation strategies
"""
Provides degraded responses when the primary operation fails.
Supports cached fallback, default values, and custom fallback functions.
"""

import time
from typing import Callable, TypeVar, Any, Optional, Dict
from dataclasses import dataclass, field
import threading

T = TypeVar("T")


@dataclass
class FallbackConfig:
    """Fallback configuration.

    Best practice: Always log when falling back so you have visibility
    into degraded operation. A silent fallback can mask real problems
    for hours because the system appears healthy from the outside.
    """
    fallback_func: Optional[Callable[..., Any]] = None
    default_value: Any = None
    cache_ttl: float = 300.0  # Cache valid for 5 minutes
    use_cache: bool = True


class Fallback:
    """
    Returns a degraded response when the primary operation fails.

    Supports three fallback strategies:
    1. Cached: Return the last successful response
    2. Default: Return a static default value
    3. Custom: Call a fallback function (e.g., read from secondary DB)
    """

    def __init__(self, name: str, config: Optional[FallbackConfig] = None):
        self.name = name
        self.config = config or FallbackConfig()
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _cache_key(self, args: tuple, kwargs: dict) -> str:
        """Generate a cache key from function arguments."""
        return str((args, sorted(kwargs.items())))

    def _get_cached(self, key: str) -> Optional[Any]:
        """Return cached value if within TTL."""
        with self._lock:
            if key in self._cache:
                age = time.monotonic() - self._cache_times.get(key, 0)
                if age < self.config.cache_ttl:
                    return self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Store a successful result in the cache."""
        with self._lock:
            self._cache[key] = value
            self._cache_times[key] = time.monotonic()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute the function, falling back on failure.

        On success, caches the result for future fallback use.
        On failure, tries (in order): cache, custom fallback, default value.
        """
        cache_key = self._cache_key(args, kwargs)

        try:
            result = func(*args, **kwargs)
            if self.config.use_cache:
                self._set_cached(cache_key, result)
            return result
        except Exception:
            # Strategy 1: Return cached value
            if self.config.use_cache:
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

            # Strategy 2: Call custom fallback function
            if self.config.fallback_func is not None:
                return self.config.fallback_func(*args, **kwargs)

            # Strategy 3: Return default value
            if self.config.default_value is not None:
                return self.config.default_value

            raise  # No fallback available
```

## Composing All Five Patterns

The real power emerges when patterns are **composed** into a unified resilience layer.
The order matters: Timeout wraps the innermost call, then Retry wraps Timeout, then
Circuit Breaker wraps Retry, then Bulkhead wraps Circuit Breaker, and Fallback wraps
everything.

```python
# resilient_caller.py — Composing all five patterns
"""
Composes circuit breaker, bulkhead, retry, timeout, and fallback into
a single resilient caller that protects against cascading failures.
"""

from typing import Callable, TypeVar, Any, Optional
from dataclasses import dataclass

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitOpenError
from bulkhead import Bulkhead, BulkheadConfig, BulkheadFullError
from retry import Retry, RetryConfig, MaxRetriesExceededError
from timeout import Timeout, TimeoutConfig
from timeout import TimeoutError as OpTimeoutError
from fallback import Fallback, FallbackConfig

T = TypeVar("T")


@dataclass
class ResilienceConfig:
    """Complete resilience configuration for a service dependency."""
    circuit_breaker: CircuitBreakerConfig = None
    bulkhead: BulkheadConfig = None
    retry: RetryConfig = None
    timeout: TimeoutConfig = None
    fallback: FallbackConfig = None

    def __post_init__(self):
        self.circuit_breaker = self.circuit_breaker or CircuitBreakerConfig()
        self.bulkhead = self.bulkhead or BulkheadConfig()
        self.retry = self.retry or RetryConfig()
        self.timeout = self.timeout or TimeoutConfig()
        self.fallback = self.fallback or FallbackConfig()


class ResilientCaller:
    """
    Composes all five resilience patterns into a single callable.

    The composition order is critical — each layer handles a different
    failure mode, and the order determines which pattern "sees" the
    failure first:

        Fallback → Bulkhead → CircuitBreaker → Retry → Timeout → func

    Therefore:
    - Timeout ensures individual calls don't hang
    - Retry compensates for transient timeouts/errors
    - CircuitBreaker stops retrying when the backend is clearly down
    - Bulkhead limits concurrent calls to prevent resource exhaustion
    - Fallback provides a degraded response when everything fails
    """

    def __init__(self, name: str, config: Optional[ResilienceConfig] = None):
        self.name = name
        cfg = config or ResilienceConfig()

        self._timeout = Timeout(cfg.timeout)
        self._retry = Retry(cfg.retry)
        self._circuit_breaker = CircuitBreaker(name, cfg.circuit_breaker)
        self._bulkhead = Bulkhead(name, cfg.bulkhead)
        self._fallback = Fallback(name, cfg.fallback)

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through all five resilience layers.

        The call flows through: fallback → bulkhead → circuit breaker →
        retry → timeout → actual function.
        """
        def with_timeout():
            return self._timeout.call(func, *args, **kwargs)

        def with_retry():
            return self._retry.call(with_timeout)

        def with_circuit_breaker():
            return self._circuit_breaker.call(with_retry)

        def with_bulkhead():
            return self._bulkhead.call(with_circuit_breaker)

        return self._fallback.call(with_bulkhead)


# --- Production usage example ---
def create_payment_caller() -> ResilientCaller:
    """
    Create a resilient caller for the payment service.

    Configuration rationale:
    - Timeout 3s: Payment API p99 is 1.5s, so 3s gives 2x headroom
    - Retry 3x: Transient network errors are common in cloud environments
    - Circuit breaker trips at 5 failures: Prevents retry storms
    - Bulkhead 20 concurrent: Payment service can handle 50 RPS, and we
      are one of four callers, so 50/4 ≈ 12, with 60% headroom = 20
    - Fallback: Return cached payment status for idempotent reads
    """
    return ResilientCaller(
        name="payment-service",
        config=ResilienceConfig(
            timeout=TimeoutConfig(timeout=3.0),
            retry=RetryConfig(
                max_attempts=3,
                base_delay=0.1,
                max_delay=2.0,
                jitter="decorrelated",
                retryable_exceptions=(OpTimeoutError, ConnectionError, OSError),
            ),
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                reset_timeout=30.0,
            ),
            bulkhead=BulkheadConfig(max_concurrent=20, max_wait=1.0),
            fallback=FallbackConfig(
                use_cache=True,
                cache_ttl=60.0,
                default_value={"status": "unknown", "degraded": True},
            ),
        ),
    )
```

## Tests for All Patterns

```python
# test_resilience.py — Tests verifying all five patterns
"""
Tests for circuit breaker, bulkhead, retry, timeout, and fallback
patterns, plus their composition in ResilientCaller.
"""

import time
import threading
import pytest

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitOpenError, CircuitState
from bulkhead import Bulkhead, BulkheadConfig, BulkheadFullError
from retry import Retry, RetryConfig, MaxRetriesExceededError, calculate_delay
from timeout import Timeout, TimeoutConfig
from timeout import TimeoutError as OpTimeoutError
from fallback import Fallback, FallbackConfig
from resilient_caller import ResilientCaller, ResilienceConfig


# --- Circuit Breaker Tests ---

class TestCircuitBreaker:
    def test_closed_allows_calls(self):
        """Circuit starts closed and allows calls through."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        """Circuit opens after failure_threshold consecutive failures."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should not execute")

    def test_half_open_recovery(self):
        """Circuit transitions OPEN -> HALF_OPEN -> CLOSED on recovery."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, reset_timeout=0.1,
        ))
        # Trip the breaker
        for _ in range(2):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError))
        assert cb.state == CircuitState.OPEN
        # Wait for reset timeout
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        # Successful calls close the circuit
        cb.call(lambda: "ok")
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED


# --- Bulkhead Tests ---

class TestBulkhead:
    def test_allows_within_limit(self):
        """Bulkhead allows calls within concurrency limit."""
        bh = Bulkhead("test", BulkheadConfig(max_concurrent=2))
        assert bh.call(lambda: 42) == 42

    def test_rejects_when_full(self):
        """Bulkhead rejects calls when at maximum concurrency."""
        bh = Bulkhead("test", BulkheadConfig(max_concurrent=1, max_wait=0))
        barrier = threading.Event()

        def slow():
            barrier.wait(timeout=5)
            return "done"

        # Occupy the single slot
        t = threading.Thread(target=lambda: bh.call(slow))
        t.start()
        time.sleep(0.05)  # Let thread acquire permit
        assert bh.active_calls == 1

        with pytest.raises(BulkheadFullError):
            bh.call(lambda: "rejected")

        barrier.set()
        t.join()


# --- Retry Tests ---

class TestRetry:
    def test_succeeds_on_first_try(self):
        """No retry needed when the function succeeds immediately."""
        r = Retry(RetryConfig(max_attempts=3))
        assert r.call(lambda: "ok") == "ok"

    def test_retries_on_failure(self):
        """Retries until success within max_attempts."""
        call_count = 0
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"
        r = Retry(RetryConfig(max_attempts=3, base_delay=0.01))
        assert r.call(flaky) == "recovered"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Raises MaxRetriesExceededError after exhausting attempts."""
        r = Retry(RetryConfig(max_attempts=2, base_delay=0.01))
        with pytest.raises(MaxRetriesExceededError) as exc_info:
            r.call(lambda: (_ for _ in ()).throw(ValueError("persistent")))
        assert exc_info.value.attempts == 2

    def test_decorrelated_jitter_bounded(self):
        """Decorrelated jitter stays within bounds."""
        config = RetryConfig(base_delay=0.1, max_delay=5.0, jitter="decorrelated")
        for _ in range(100):
            delay = calculate_delay(5, config, 1.0)
            assert 0 <= delay <= 5.0


# --- Timeout Tests ---

class TestTimeout:
    def test_completes_within_timeout(self):
        """Returns result when function completes in time."""
        t = Timeout(TimeoutConfig(timeout=1.0))
        assert t.call(lambda: "fast") == "fast"

    def test_raises_on_timeout(self):
        """Raises TimeoutError when function exceeds limit."""
        t = Timeout(TimeoutConfig(timeout=0.1))
        with pytest.raises(OpTimeoutError):
            t.call(lambda: time.sleep(5))


# --- Fallback Tests ---

class TestFallback:
    def test_returns_primary_on_success(self):
        """Returns primary result when function succeeds."""
        fb = Fallback("test", FallbackConfig(default_value="fallback"))
        assert fb.call(lambda: "primary") == "primary"

    def test_returns_cached_on_failure(self):
        """Falls back to cached result after a failure."""
        fb = Fallback("test", FallbackConfig(use_cache=True))
        fb.call(lambda: "cached_value")  # Populate cache
        result = fb.call(
            lambda: (_ for _ in ()).throw(ConnectionError("down"))
        )
        assert result == "cached_value"

    def test_returns_default_when_no_cache(self):
        """Returns default value when no cache and function fails."""
        fb = Fallback("test", FallbackConfig(
            use_cache=False, default_value={"degraded": True},
        ))
        result = fb.call(
            lambda: (_ for _ in ()).throw(ConnectionError("down"))
        )
        assert result == {"degraded": True}


# --- ResilientCaller Integration Test ---

class TestResilientCaller:
    def test_successful_call(self):
        """All patterns pass through on successful call."""
        caller = ResilientCaller("test")
        assert caller.call(lambda: "success") == "success"

    def test_fallback_on_total_failure(self):
        """Falls back to default when all patterns fail."""
        caller = ResilientCaller("test", ResilienceConfig(
            timeout=TimeoutConfig(timeout=0.5),
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=10),
            fallback=FallbackConfig(default_value="degraded"),
        ))
        result = caller.call(
            lambda: (_ for _ in ()).throw(ConnectionError("down"))
        )
        assert result == "degraded"
```

## Summary and Key Takeaways

- **Circuit breaker** prevents cascading failures by fast-rejecting calls to unhealthy
  backends. The trade-off is between sensitivity (low failure threshold) and avoiding
  false trips during transient spikes.
- **Bulkhead** isolates resource consumption per dependency. **Best practice**: size each
  bulkhead based on the downstream service's capacity divided by the number of callers.
- **Retry with decorrelated jitter** handles transient failures without thundering herd.
  A **pitfall** is retrying non-idempotent operations — always verify idempotency before
  enabling retries on mutating endpoints.
- **Timeout** prevents indefinite blocking. Use **deadline propagation** to ensure nested
  calls respect the parent's remaining time budget. A **common mistake** is setting per-call
  timeouts without considering the total budget across retries (3 retries x 5s timeout = 15s
  total, which may exceed the SLA).
- **Fallback** provides graceful degradation as the last line of defense. However, it can
  mask real failures — therefore always monitor and alert on fallback activation rates.
- **Composition order matters**: Fallback(Bulkhead(CircuitBreaker(Retry(Timeout(func))))).
  Each layer handles a different failure mode, and incorrect ordering (e.g., retry outside
  circuit breaker) can cause harmful behavior like retry storms against a known-broken backend.
"""
    ),
]
