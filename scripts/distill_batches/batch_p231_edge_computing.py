"""Edge computing patterns — Cloudflare Workers, Vercel Edge, edge caching, edge AI inference."""

PAIRS = [
    (
        "edge/cloudflare-workers",
        "Show Cloudflare Workers patterns including KV storage, Durable Objects for stateful coordination, and D1 SQL database, with proper error handling and TypeScript types.",
        '''Cloudflare Workers with KV, Durable Objects, and D1:

```typescript
// src/index.ts — Main Worker entry point
import { Env, RequestContext } from './types';

export interface Env {
    // KV namespace binding
    CACHE_KV: KVNamespace;
    // Durable Object binding
    RATE_LIMITER: DurableObjectNamespace;
    // D1 database binding
    DB: D1Database;
    // Environment variables
    API_KEY: string;
    ENVIRONMENT: string;
}

interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
    meta: {
        colo: string;
        country: string;
        cached: boolean;
        latency_ms: number;
    };
}

export default {
    async fetch(
        request: Request,
        env: Env,
        ctx: ExecutionContext
    ): Promise<Response> {
        const start = Date.now();
        const url = new URL(request.url);
        const cf = request.cf;

        try {
            // Rate limiting via Durable Object
            const rateLimiterId = env.RATE_LIMITER.idFromName(
                cf?.country as string || 'unknown'
            );
            const rateLimiter = env.RATE_LIMITER.get(rateLimiterId);
            const rateLimitResp = await rateLimiter.fetch(
                new Request('https://internal/check', {
                    method: 'POST',
                    body: JSON.stringify({
                        ip: request.headers.get('cf-connecting-ip'),
                        limit: 100,
                        window_seconds: 60,
                    }),
                })
            );

            if (rateLimitResp.status === 429) {
                return jsonResponse<never>(
                    { success: false, error: 'Rate limit exceeded', meta: buildMeta(cf, false, start) },
                    429,
                    { 'Retry-After': '60' }
                );
            }

            // Route handling
            if (url.pathname.startsWith('/api/products')) {
                return handleProducts(request, env, ctx, cf, start);
            }
            if (url.pathname.startsWith('/api/users')) {
                return handleUsers(request, env, ctx, cf, start);
            }

            return jsonResponse<never>(
                { success: false, error: 'Not found', meta: buildMeta(cf, false, start) },
                404
            );
        } catch (err) {
            console.error('Worker error:', err);
            return jsonResponse<never>(
                {
                    success: false,
                    error: env.ENVIRONMENT === 'production' ? 'Internal error' : String(err),
                    meta: buildMeta(cf, false, start),
                },
                500
            );
        }
    },
};

// ---------- KV-backed caching ----------

async function handleProducts(
    request: Request,
    env: Env,
    ctx: ExecutionContext,
    cf: IncomingRequestCfProperties | undefined,
    start: number
): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.pathname.split('/')[3];

    if (request.method === 'GET' && productId) {
        // Check KV cache first
        const cacheKey = `product:${productId}`;
        const cached = await env.CACHE_KV.get(cacheKey, { type: 'json' });

        if (cached) {
            return jsonResponse<unknown>({
                success: true,
                data: cached,
                meta: buildMeta(cf, true, start),
            });
        }

        // Cache miss — query D1
        const row = await env.DB
            .prepare('SELECT * FROM products WHERE id = ?')
            .bind(productId)
            .first();

        if (!row) {
            return jsonResponse<never>(
                { success: false, error: 'Product not found', meta: buildMeta(cf, false, start) },
                404
            );
        }

        // Write to KV with TTL (non-blocking via waitUntil)
        ctx.waitUntil(
            env.CACHE_KV.put(cacheKey, JSON.stringify(row), {
                expirationTtl: 300,  // 5 minutes
                metadata: { updated: Date.now() },
            })
        );

        return jsonResponse<unknown>({
            success: true,
            data: row,
            meta: buildMeta(cf, false, start),
        });
    }

    if (request.method === 'POST') {
        const body = await request.json() as Record<string, unknown>;

        const result = await env.DB
            .prepare(
                'INSERT INTO products (name, price, category) VALUES (?, ?, ?) RETURNING *'
            )
            .bind(body.name, body.price, body.category)
            .first();

        // Invalidate cache
        ctx.waitUntil(env.CACHE_KV.delete(`product:${(result as any).id}`));

        return jsonResponse<unknown>({
            success: true,
            data: result,
            meta: buildMeta(cf, false, start),
        }, 201);
    }

    return jsonResponse<never>(
        { success: false, error: 'Method not allowed', meta: buildMeta(cf, false, start) },
        405
    );
}

function buildMeta(
    cf: IncomingRequestCfProperties | undefined,
    cached: boolean,
    start: number
) {
    return {
        colo: cf?.colo as string || 'unknown',
        country: cf?.country as string || 'unknown',
        cached,
        latency_ms: Date.now() - start,
    };
}

function jsonResponse<T>(body: ApiResponse<T>, status = 200, headers: Record<string, string> = {}) {
    return new Response(JSON.stringify(body), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-store',
            ...headers,
        },
    });
}
```

```typescript
// src/rate-limiter.ts — Durable Object for distributed rate limiting
export class RateLimiter implements DurableObject {
    private state: DurableObjectState;
    private requests: Map<string, number[]> = new Map();

    constructor(state: DurableObjectState, env: Env) {
        this.state = state;

        // Restore state from storage on wake-up
        this.state.blockConcurrencyWhile(async () => {
            const stored = await this.state.storage.get<Map<string, number[]>>('requests');
            if (stored) this.requests = stored;
        });
    }

    async fetch(request: Request): Promise<Response> {
        const body = await request.json() as {
            ip: string;
            limit: number;
            window_seconds: number;
        };

        const { ip, limit, window_seconds } = body;
        const now = Date.now();
        const windowMs = window_seconds * 1000;

        // Get existing requests for this IP
        let timestamps = this.requests.get(ip) || [];

        // Remove expired entries
        timestamps = timestamps.filter(ts => now - ts < windowMs);

        if (timestamps.length >= limit) {
            return new Response('Rate limited', { status: 429 });
        }

        // Record new request
        timestamps.push(now);
        this.requests.set(ip, timestamps);

        // Persist (Durable Objects have transactional storage)
        await this.state.storage.put('requests', this.requests);

        // Set alarm to clean up old entries
        const currentAlarm = await this.state.storage.getAlarm();
        if (!currentAlarm) {
            await this.state.storage.setAlarm(now + windowMs);
        }

        return new Response(JSON.stringify({
            remaining: limit - timestamps.length,
            reset_at: timestamps[0] + windowMs,
        }), {
            status: 200,
            headers: {
                'X-RateLimit-Remaining': String(limit - timestamps.length),
                'X-RateLimit-Reset': String(Math.ceil((timestamps[0] + windowMs) / 1000)),
            },
        });
    }

    async alarm(): Promise<void> {
        // Periodic cleanup of expired entries
        const now = Date.now();
        for (const [ip, timestamps] of this.requests) {
            const valid = timestamps.filter(ts => now - ts < 60_000);
            if (valid.length === 0) {
                this.requests.delete(ip);
            } else {
                this.requests.set(ip, valid);
            }
        }
        await this.state.storage.put('requests', this.requests);
    }
}
```

```sql
-- D1 schema migration: migrations/0001_init.sql
-- D1 is SQLite at the edge — supports most SQLite features

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL CHECK (price >= 0),
    category TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_price ON products(price);

-- Full-text search
CREATE VIRTUAL TABLE products_fts USING fts5(
    name, category,
    content='products',
    content_rowid='id'
);

-- Trigger to keep FTS in sync
CREATE TRIGGER products_ai AFTER INSERT ON products BEGIN
    INSERT INTO products_fts(rowid, name, category)
    VALUES (new.id, new.name, new.category);
END;

CREATE TRIGGER products_ad AFTER DELETE ON products BEGIN
    INSERT INTO products_fts(products_fts, rowid, name, category)
    VALUES ('delete', old.id, old.name, old.category);
END;
```

```toml
# wrangler.toml — Worker configuration
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
ENVIRONMENT = "production"

[[kv_namespaces]]
binding = "CACHE_KV"
id = "abc123"

[[d1_databases]]
binding = "DB"
database_name = "products-db"
database_id = "def456"

[[durable_objects.bindings]]
name = "RATE_LIMITER"
class_name = "RateLimiter"

[[migrations]]
tag = "v1"
new_classes = ["RateLimiter"]

[build]
command = "npm run build"

# Routes
[[routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
```

| CF Feature | Consistency | Latency | Storage Limit | Best For |
|---|---|---|---|---|
| KV | Eventually consistent | <10ms reads | 25MB/value | Cache, config, static |
| Durable Objects | Strong consistency | Single-region | 128KB/key | Coordination, counters |
| D1 | Strong consistency | <5ms reads | 2GB/db | Structured queries |
| R2 | Strong consistency | ~50ms | 5TB/bucket | Large objects, files |
| Queues | At-least-once | ~100ms | 128KB/msg | Async processing |
| Hyperdrive | Conn pooling | Varies | N/A | External Postgres |

Key patterns:
1. Use `ctx.waitUntil()` for non-blocking background work (cache writes, analytics)
2. Durable Objects provide single-threaded, strongly consistent state per ID
3. KV is eventually consistent (60s propagation) — use for cache, not source of truth
4. D1 is SQLite-based — supports FTS5, JSON functions, and window functions
5. Durable Object alarms replace cron for per-object scheduled work
6. Always return responses quickly — move heavy work to `waitUntil` or Queues'''
    ),
    (
        "edge/vercel-deno-deploy",
        "Show edge function patterns for Vercel Edge Functions and Deno Deploy, including streaming responses, middleware, and geolocation-based routing.",
        '''Edge functions on Vercel and Deno Deploy with streaming and geo-routing:

```typescript
// app/api/stream/route.ts — Vercel Edge Function with streaming
import { NextRequest } from 'next/server';

export const runtime = 'edge';   // Run at the edge, not Node.js
export const preferredRegion = ['iad1', 'sfo1', 'cdg1'];  // Multi-region

interface StreamChunk {
    id: string;
    text: string;
    done: boolean;
}

export async function GET(request: NextRequest): Promise<Response> {
    const geo = request.geo;
    const searchParams = request.nextUrl.searchParams;
    const query = searchParams.get('q') || '';

    // Geo-based content customization
    const locale = getLocaleFromGeo(geo);
    const currency = getCurrencyFromGeo(geo);

    // Create a TransformStream for server-sent events
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
        async start(controller) {
            try {
                // Simulate streaming from an upstream API
                const upstream = await fetch('https://api.internal.com/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, locale, currency }),
                });

                if (!upstream.ok) {
                    controller.enqueue(
                        encoder.encode(`data: ${JSON.stringify({ error: 'Upstream failed' })}\n\n`)
                    );
                    controller.close();
                    return;
                }

                const reader = upstream.body?.getReader();
                if (!reader) {
                    controller.close();
                    return;
                }

                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });

                    // Parse newline-delimited JSON
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.trim()) {
                            const chunk: StreamChunk = {
                                id: crypto.randomUUID(),
                                text: line,
                                done: false,
                            };
                            controller.enqueue(
                                encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`)
                            );
                        }
                    }
                }

                // Final chunk
                controller.enqueue(
                    encoder.encode(`data: ${JSON.stringify({ id: 'end', text: '', done: true })}\n\n`)
                );
            } catch (err) {
                controller.enqueue(
                    encoder.encode(`data: ${JSON.stringify({ error: String(err) })}\n\n`)
                );
            } finally {
                controller.close();
            }
        },
    });

    return new Response(stream, {
        headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'X-Edge-Region': geo?.region || 'unknown',
            'X-Edge-Country': geo?.country || 'unknown',
        },
    });
}

function getLocaleFromGeo(geo?: { country?: string }): string {
    const countryLocales: Record<string, string> = {
        US: 'en-US', GB: 'en-GB', DE: 'de-DE',
        FR: 'fr-FR', JP: 'ja-JP', BR: 'pt-BR',
    };
    return countryLocales[geo?.country || ''] || 'en-US';
}

function getCurrencyFromGeo(geo?: { country?: string }): string {
    const countryCurrencies: Record<string, string> = {
        US: 'USD', GB: 'GBP', DE: 'EUR',
        FR: 'EUR', JP: 'JPY', BR: 'BRL',
    };
    return countryCurrencies[geo?.country || ''] || 'USD';
}
```

```typescript
// middleware.ts — Vercel Edge Middleware (runs before all routes)
import { NextRequest, NextResponse } from 'next/server';

export const config = {
    matcher: [
        // Match all API routes and pages, skip static files
        '/((?!_next/static|_next/image|favicon.ico).*)',
    ],
};

export function middleware(request: NextRequest): NextResponse {
    const response = NextResponse.next();
    const { geo, ip, nextUrl } = request;

    // 1. Bot detection
    const ua = request.headers.get('user-agent') || '';
    if (isBot(ua) && nextUrl.pathname.startsWith('/api/')) {
        return NextResponse.json(
            { error: 'Forbidden' },
            { status: 403 }
        );
    }

    // 2. Geo-based redirects
    if (geo?.country === 'CN' && !nextUrl.pathname.startsWith('/cn/')) {
        return NextResponse.redirect(new URL(`/cn${nextUrl.pathname}`, request.url));
    }

    // 3. A/B testing with edge cookies
    let bucket = request.cookies.get('ab-bucket')?.value;
    if (!bucket) {
        bucket = Math.random() < 0.5 ? 'control' : 'variant';
        response.cookies.set('ab-bucket', bucket, {
            maxAge: 60 * 60 * 24 * 30,  // 30 days
            httpOnly: true,
            sameSite: 'lax',
        });
    }
    response.headers.set('x-ab-bucket', bucket);

    // 4. Security headers
    response.headers.set('X-Frame-Options', 'DENY');
    response.headers.set('X-Content-Type-Options', 'nosniff');
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    // 5. Request timing
    response.headers.set('X-Edge-Start', String(Date.now()));

    return response;
}

function isBot(ua: string): boolean {
    const bots = [/bot/i, /crawl/i, /spider/i, /scrape/i];
    return bots.some(re => re.test(ua));
}
```

```typescript
// main.ts — Deno Deploy edge function
import { serve } from "https://deno.land/std@0.220.0/http/server.ts";

interface GeoInfo {
    city: string;
    country: string;
    continent: string;
    latitude: number;
    longitude: number;
}

// In-memory LRU cache (per-isolate)
const cache = new Map<string, { data: unknown; expires: number }>();
const MAX_CACHE_SIZE = 1000;

function getCached<T>(key: string): T | null {
    const entry = cache.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expires) {
        cache.delete(key);
        return null;
    }
    return entry.data as T;
}

function setCache(key: string, data: unknown, ttlMs: number): void {
    if (cache.size >= MAX_CACHE_SIZE) {
        // Evict oldest entry
        const firstKey = cache.keys().next().value;
        if (firstKey) cache.delete(firstKey);
    }
    cache.set(key, { data, expires: Date.now() + ttlMs });
}

serve(async (request: Request): Promise<Response> => {
    const url = new URL(request.url);

    // Deno Deploy provides geographic info
    // Access via Deno.env or headers depending on platform
    const connInfo: GeoInfo = {
        city: request.headers.get('x-forwarded-city') || 'unknown',
        country: request.headers.get('x-forwarded-country') || 'unknown',
        continent: request.headers.get('x-forwarded-continent') || 'unknown',
        latitude: parseFloat(request.headers.get('x-forwarded-lat') || '0'),
        longitude: parseFloat(request.headers.get('x-forwarded-lon') || '0'),
    };

    // Route: nearest data center selection
    if (url.pathname === '/api/nearest-dc') {
        const datacenters = [
            { name: 'us-east', lat: 39.0, lon: -77.5 },
            { name: 'eu-west', lat: 53.3, lon: -6.3 },
            { name: 'ap-southeast', lat: 1.3, lon: 103.8 },
        ];

        const nearest = datacenters
            .map(dc => ({
                ...dc,
                distance: haversine(
                    connInfo.latitude, connInfo.longitude,
                    dc.lat, dc.lon
                ),
            }))
            .sort((a, b) => a.distance - b.distance)[0];

        return Response.json({
            client: connInfo,
            nearest_dc: nearest.name,
            distance_km: Math.round(nearest.distance),
        });
    }

    // Route: cached proxy with stale-while-revalidate
    if (url.pathname.startsWith('/api/proxy/')) {
        const upstream = url.pathname.replace('/api/proxy/', '');
        const cacheKey = `proxy:${upstream}`;

        const cached = getCached<unknown>(cacheKey);
        if (cached) {
            return Response.json(cached, {
                headers: { 'X-Cache': 'HIT' },
            });
        }

        const resp = await fetch(`https://api.upstream.com/${upstream}`);
        const data = await resp.json();
        setCache(cacheKey, data, 30_000);  // 30s TTL

        return Response.json(data, {
            headers: { 'X-Cache': 'MISS' },
        });
    }

    return Response.json({ error: 'Not found' }, { status: 404 });
}, { port: 8000 });

function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
```

| Platform | Runtime | Cold Start | Max Exec Time | Regions | Storage |
|---|---|---|---|---|---|
| Vercel Edge | V8 Isolates | <5ms | 30s (free), 5min (pro) | 30+ | KV (beta) |
| CF Workers | V8 Isolates | <5ms | 30s (free), 15min (paid) | 300+ | KV, D1, R2, DO |
| Deno Deploy | Deno (V8) | <10ms | 10min | 35+ | Deno KV |
| Fastly C@E | WASM | <1ms | 120s | 90+ | KV Store |
| AWS Lambda@Edge | Node.js | ~50ms | 30s (viewer), 60s (origin) | CloudFront PoPs | DynamoDB |

Key patterns:
1. Edge functions use V8 isolates, not containers -- no cold start penalty
2. Use `TransformStream` and `ReadableStream` for SSE/streaming responses
3. Edge middleware runs before page render -- ideal for auth, A/B, geo-redirect
4. Per-isolate memory caches are fast but ephemeral -- combine with distributed KV
5. Limit edge function size: avoid large npm dependencies (they inflate cold start)
6. Use `waitUntil()` or `ctx.waitUntil()` for fire-and-forget background tasks'''
    ),
    (
        "edge/caching-strategies",
        "Explain edge caching strategies including stale-while-revalidate, cache tags, tiered caching, and cache invalidation patterns for dynamic content at the edge.",
        '''Edge caching strategies for dynamic content:

```typescript
// edge-cache.ts — Comprehensive edge caching layer
interface CacheConfig {
    defaultTtl: number;
    staleTtl: number;
    maxSize: number;
    tieredEnabled: boolean;
}

interface CacheEntry<T> {
    data: T;
    etag: string;
    created: number;
    expires: number;
    staleUntil: number;
    tags: string[];
    revalidating: boolean;
}

interface CacheStats {
    hits: number;
    misses: number;
    staleHits: number;
    revalidations: number;
    evictions: number;
}

class EdgeCacheManager<T> {
    private l1: Map<string, CacheEntry<T>> = new Map();  // In-memory (per-isolate)
    private config: CacheConfig;
    private stats: CacheStats = {
        hits: 0, misses: 0, staleHits: 0, revalidations: 0, evictions: 0,
    };

    constructor(
        private kvStore: KVNamespace,  // L2: distributed KV
        config: Partial<CacheConfig> = {},
    ) {
        this.config = {
            defaultTtl: 60_000,       // 1 minute
            staleTtl: 300_000,        // 5 minutes stale grace
            maxSize: 500,             // L1 entries
            tieredEnabled: true,
            ...config,
        };
    }

    /**
     * Stale-while-revalidate pattern:
     * 1. Return cached data immediately (even if stale)
     * 2. Revalidate in background if stale
     * 3. Fetch fresh if completely expired
     */
    async get(
        key: string,
        fetcher: () => Promise<T>,
        options: { ttl?: number; tags?: string[]; ctx?: ExecutionContext } = {},
    ): Promise<{ data: T; status: 'hit' | 'stale' | 'miss' }> {
        const ttl = options.ttl ?? this.config.defaultTtl;

        // L1: Check in-memory cache
        const l1Entry = this.l1.get(key);
        if (l1Entry) {
            const now = Date.now();

            // Fresh hit
            if (now < l1Entry.expires) {
                this.stats.hits++;
                return { data: l1Entry.data, status: 'hit' };
            }

            // Stale but within grace period
            if (now < l1Entry.staleUntil && !l1Entry.revalidating) {
                this.stats.staleHits++;
                l1Entry.revalidating = true;

                // Background revalidation (non-blocking)
                const revalidate = async () => {
                    try {
                        const fresh = await fetcher();
                        await this.set(key, fresh, { ttl, tags: l1Entry.tags });
                        this.stats.revalidations++;
                    } catch {
                        // Keep stale data on revalidation failure
                        l1Entry.revalidating = false;
                    }
                };

                if (options.ctx) {
                    options.ctx.waitUntil(revalidate());
                } else {
                    revalidate();  // Fire and forget
                }

                return { data: l1Entry.data, status: 'stale' };
            }
        }

        // L2: Check distributed KV (if tiered caching enabled)
        if (this.config.tieredEnabled) {
            const l2Data = await this.kvStore.get<CacheEntry<T>>(
                `cache:${key}`, { type: 'json' }
            );

            if (l2Data && Date.now() < l2Data.staleUntil) {
                // Promote to L1
                this.l1Set(key, l2Data);

                if (Date.now() < l2Data.expires) {
                    this.stats.hits++;
                    return { data: l2Data.data, status: 'hit' };
                }

                // Stale in L2 — revalidate
                this.stats.staleHits++;
                if (options.ctx) {
                    options.ctx.waitUntil(
                        fetcher().then(d => this.set(key, d, { ttl, tags: l2Data.tags }))
                    );
                }
                return { data: l2Data.data, status: 'stale' };
            }
        }

        // Cache miss — fetch fresh data
        this.stats.misses++;
        const data = await fetcher();
        await this.set(key, data, { ttl, tags: options.tags });
        return { data, status: 'miss' };
    }

    async set(
        key: string,
        data: T,
        options: { ttl?: number; tags?: string[] } = {},
    ): Promise<void> {
        const ttl = options.ttl ?? this.config.defaultTtl;
        const now = Date.now();

        const entry: CacheEntry<T> = {
            data,
            etag: await this.generateEtag(data),
            created: now,
            expires: now + ttl,
            staleUntil: now + ttl + this.config.staleTtl,
            tags: options.tags || [],
            revalidating: false,
        };

        // L1: In-memory
        this.l1Set(key, entry);

        // L2: Distributed KV
        if (this.config.tieredEnabled) {
            await this.kvStore.put(`cache:${key}`, JSON.stringify(entry), {
                expirationTtl: Math.ceil((ttl + this.config.staleTtl) / 1000),
                metadata: { tags: entry.tags },
            });

            // Update tag index for invalidation
            for (const tag of entry.tags) {
                const tagKeys = await this.kvStore.get<string[]>(`tag:${tag}`, { type: 'json' }) || [];
                if (!tagKeys.includes(key)) {
                    tagKeys.push(key);
                    await this.kvStore.put(`tag:${tag}`, JSON.stringify(tagKeys), {
                        expirationTtl: Math.ceil((ttl + this.config.staleTtl) / 1000),
                    });
                }
            }
        }
    }

    /**
     * Tag-based cache invalidation.
     * Invalidate all entries matching any of the given tags.
     */
    async invalidateByTag(tags: string[]): Promise<number> {
        let invalidated = 0;

        // L1: scan and remove
        for (const [key, entry] of this.l1) {
            if (entry.tags.some(t => tags.includes(t))) {
                this.l1.delete(key);
                invalidated++;
            }
        }

        // L2: use tag index
        for (const tag of tags) {
            const keys = await this.kvStore.get<string[]>(`tag:${tag}`, { type: 'json' }) || [];
            for (const key of keys) {
                await this.kvStore.delete(`cache:${key}`);
                invalidated++;
            }
            await this.kvStore.delete(`tag:${tag}`);
        }

        return invalidated;
    }

    getStats(): CacheStats {
        return { ...this.stats };
    }

    private l1Set(key: string, entry: CacheEntry<T>): void {
        if (this.l1.size >= this.config.maxSize) {
            // LRU eviction
            const firstKey = this.l1.keys().next().value;
            if (firstKey) {
                this.l1.delete(firstKey);
                this.stats.evictions++;
            }
        }
        this.l1.set(key, entry);
    }

    private async generateEtag(data: T): Promise<string> {
        const text = JSON.stringify(data);
        const buffer = await crypto.subtle.digest(
            'SHA-256',
            new TextEncoder().encode(text),
        );
        return Array.from(new Uint8Array(buffer).slice(0, 8))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
}
```

```typescript
// usage.ts — Using the cache manager in a Worker
export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        const cache = new EdgeCacheManager<unknown>(env.CACHE_KV, {
            defaultTtl: 60_000,
            staleTtl: 300_000,
            tieredEnabled: true,
        });

        const url = new URL(request.url);

        // Cache-Control negotiation with conditional requests
        if (request.method === 'GET') {
            const ifNoneMatch = request.headers.get('If-None-Match');

            const { data, status } = await cache.get(
                url.pathname,
                async () => {
                    const resp = await fetch(`https://origin.example.com${url.pathname}`);
                    return resp.json();
                },
                {
                    ttl: 120_000,
                    tags: ['api', `path:${url.pathname}`],
                    ctx,
                },
            );

            return new Response(JSON.stringify(data), {
                headers: {
                    'Content-Type': 'application/json',
                    'X-Cache': status.toUpperCase(),
                    'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
                    'CDN-Cache-Control': 'public, max-age=300',
                    'Surrogate-Control': 'max-age=600',
                },
            });
        }

        // POST/PUT/DELETE: invalidate by tags
        if (['POST', 'PUT', 'DELETE'].includes(request.method)) {
            const invalidated = await cache.invalidateByTag([
                `path:${url.pathname}`,
                'api',
            ]);

            // Forward to origin
            const resp = await fetch(request);
            const data = await resp.json();

            return new Response(JSON.stringify({
                ...data as object,
                _cache: { invalidated },
            }), {
                status: resp.status,
                headers: { 'Content-Type': 'application/json' },
            });
        }

        return new Response('Method not allowed', { status: 405 });
    },
};
```

```text
Cache Header Hierarchy (highest to lowest priority):

Request Flow:
  Client -> CDN Edge -> Origin Shield -> Origin Server

Cache-Control headers:
  Cache-Control:         Browser + CDN (standard)
  CDN-Cache-Control:     CDN only (Cloudflare, Fastly)
  Surrogate-Control:     CDN only (Akamai, Varnish)

Stale-While-Revalidate flow:
  t=0    -> Cache SET (fresh for 60s, stale until 360s)
  t=30   -> HIT (fresh)
  t=90   -> STALE HIT + background revalidate
  t=91   -> HIT (refreshed cache)
  t=400  -> MISS (fully expired) -> fetch from origin

Tiered cache architecture:
  L1 (in-memory)  : ~0.01ms, per-isolate, 500 entries
  L2 (KV store)   : ~10ms, globally distributed
  L3 (origin)     : ~100ms, source of truth
```

| Strategy | Use Case | TTL | Invalidation |
|---|---|---|---|
| Stale-while-revalidate | API responses, feeds | 60s fresh / 5min stale | Background fetch |
| Cache tags | CMS content, products | 5-30min | Purge by tag on update |
| Tiered (L1+L2) | High-traffic APIs | L1: 10s, L2: 5min | Cascade invalidation |
| Conditional (ETag) | Large responses | Long-lived | 304 Not Modified |
| Micro-cache | Dynamic personalized | 1-5s | TTL expiry only |
| Edge-side includes | Partial page caching | Per-fragment | Fragment-level purge |

Key patterns:
1. Stale-while-revalidate returns fast (stale data) and refreshes in background
2. Tag-based invalidation scales better than key-by-key purging
3. Two-tier cache (L1 memory + L2 KV) handles isolate restarts gracefully
4. Use `CDN-Cache-Control` for CDN-specific TTLs separate from browser cache
5. Micro-caching (1-5s TTL) protects origin from traffic spikes without stale data
6. Always set both `max-age` and `stale-while-revalidate` in Cache-Control headers'''
    ),
    (
        "edge/ai-inference",
        "Show patterns for running AI inference at the edge using ONNX Runtime Web and TensorFlow Lite, including model loading, preprocessing, and latency optimization.",
        '''Edge AI inference with ONNX Runtime and TensorFlow Lite:

```typescript
// onnx-edge.ts — ONNX Runtime Web for edge inference
import * as ort from 'onnxruntime-web';

interface ClassificationResult {
    label: string;
    confidence: number;
}

interface ModelConfig {
    modelPath: string;
    labels: string[];
    inputSize: [number, number];  // [height, width]
    inputName: string;
    outputName: string;
    normalize: boolean;
    meanValues?: [number, number, number];
    stdValues?: [number, number, number];
}

class ONNXEdgeClassifier {
    private session: ort.InferenceSession | null = null;
    private config: ModelConfig;
    private warmUpComplete = false;

    constructor(config: ModelConfig) {
        this.config = config;
    }

    async initialize(): Promise<void> {
        // Configure execution providers in priority order
        const options: ort.InferenceSession.SessionOptions = {
            executionProviders: [
                {
                    name: 'webgpu',    // Fastest: GPU compute shaders
                },
                {
                    name: 'webgl',     // Fallback: GPU via WebGL
                },
                {
                    name: 'wasm',      // CPU fallback: WASM SIMD
                    wasmPaths: '/onnx-wasm/',
                },
            ],
            graphOptimizationLevel: 'all',
            enableCpuMemArena: true,
            enableMemPattern: true,
        };

        this.session = await ort.InferenceSession.create(
            this.config.modelPath,
            options
        );

        // Warm-up inference to compile GPU shaders
        await this.warmUp();
    }

    private async warmUp(): Promise<void> {
        const [h, w] = this.config.inputSize;
        const dummyInput = new Float32Array(1 * 3 * h * w);
        const tensor = new ort.Tensor('float32', dummyInput, [1, 3, h, w]);
        await this.session!.run({ [this.config.inputName]: tensor });
        this.warmUpComplete = true;
    }

    /**
     * Classify an image from various input sources.
     */
    async classify(
        input: HTMLImageElement | HTMLCanvasElement | ImageBitmap | Uint8Array,
        topK: number = 5,
    ): Promise<ClassificationResult[]> {
        if (!this.session) throw new Error('Model not initialized');

        const tensor = await this.preprocess(input);
        const start = performance.now();

        const results = await this.session.run({
            [this.config.inputName]: tensor,
        });

        const inferenceMs = performance.now() - start;
        console.log(`Inference: ${inferenceMs.toFixed(1)}ms`);

        const outputTensor = results[this.config.outputName];
        return this.postprocess(outputTensor, topK);
    }

    private async preprocess(
        input: HTMLImageElement | HTMLCanvasElement | ImageBitmap | Uint8Array,
    ): Promise<ort.Tensor> {
        const [targetH, targetW] = this.config.inputSize;

        // Get pixel data via OffscreenCanvas (works in Workers)
        let canvas: OffscreenCanvas;
        let ctx: OffscreenCanvasRenderingContext2D;

        if (input instanceof Uint8Array) {
            // Raw RGBA bytes
            const imgData = new ImageData(
                new Uint8ClampedArray(input),
                targetW,
                targetH
            );
            canvas = new OffscreenCanvas(targetW, targetH);
            ctx = canvas.getContext('2d')!;
            ctx.putImageData(imgData, 0, 0);
        } else {
            canvas = new OffscreenCanvas(targetW, targetH);
            ctx = canvas.getContext('2d')!;
            ctx.drawImage(input, 0, 0, targetW, targetH);
        }

        const imageData = ctx.getImageData(0, 0, targetW, targetH);
        const { data } = imageData;

        // Convert RGBA -> CHW float32 with normalization
        const float32Data = new Float32Array(3 * targetH * targetW);
        const mean = this.config.meanValues || [0.485, 0.456, 0.406];
        const std = this.config.stdValues || [0.229, 0.224, 0.225];

        for (let i = 0; i < targetH * targetW; i++) {
            const rgbaIdx = i * 4;
            // Channel-first layout: [1, 3, H, W]
            float32Data[i] = (data[rgbaIdx] / 255.0 - mean[0]) / std[0];                        // R
            float32Data[targetH * targetW + i] = (data[rgbaIdx + 1] / 255.0 - mean[1]) / std[1]; // G
            float32Data[2 * targetH * targetW + i] = (data[rgbaIdx + 2] / 255.0 - mean[2]) / std[2]; // B
        }

        return new ort.Tensor('float32', float32Data, [1, 3, targetH, targetW]);
    }

    private postprocess(output: ort.Tensor, topK: number): ClassificationResult[] {
        const scores = Array.from(output.data as Float32Array);

        // Softmax
        const maxScore = Math.max(...scores);
        const expScores = scores.map(s => Math.exp(s - maxScore));
        const sumExp = expScores.reduce((a, b) => a + b, 0);
        const probabilities = expScores.map(s => s / sumExp);

        // Top-K
        return probabilities
            .map((confidence, idx) => ({
                label: this.config.labels[idx] || `class_${idx}`,
                confidence,
            }))
            .sort((a, b) => b.confidence - a.confidence)
            .slice(0, topK);
    }

    async dispose(): Promise<void> {
        await this.session?.release();
        this.session = null;
    }
}

// Usage
const classifier = new ONNXEdgeClassifier({
    modelPath: '/models/mobilenet_v3_small.onnx',
    labels: ['cat', 'dog', 'bird', /* ... */],
    inputSize: [224, 224],
    inputName: 'input',
    outputName: 'output',
    normalize: true,
    meanValues: [0.485, 0.456, 0.406],
    stdValues: [0.229, 0.224, 0.225],
});

await classifier.initialize();
const results = await classifier.classify(imageElement, 5);
console.log('Top prediction:', results[0].label, results[0].confidence);
```

```typescript
// tflite-edge.ts — TensorFlow Lite for edge/mobile inference
import * as tflite from '@tensorflow/tfjs-tflite';
import * as tf from '@tensorflow/tfjs';

interface DetectionBox {
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
    score: number;
}

class TFLiteEdgeDetector {
    private model: tflite.TFLiteModel | null = null;
    private labels: string[];
    private inputSize: number;
    private confidenceThreshold: number;
    private iouThreshold: number;

    constructor(
        labels: string[],
        inputSize: number = 320,
        confidenceThreshold: number = 0.5,
        iouThreshold: number = 0.45,
    ) {
        this.labels = labels;
        this.inputSize = inputSize;
        this.confidenceThreshold = confidenceThreshold;
        this.iouThreshold = iouThreshold;
    }

    async initialize(modelUrl: string): Promise<void> {
        // Load TFLite model (quantized, ~5MB)
        tflite.setWasmPath('/tflite-wasm/');
        this.model = await tflite.loadTFLiteModel(modelUrl);

        // Warm up
        const dummy = tf.zeros([1, this.inputSize, this.inputSize, 3], 'float32');
        this.model.predict(dummy);
        dummy.dispose();
    }

    async detect(imageSource: HTMLImageElement | HTMLVideoElement): Promise<DetectionBox[]> {
        if (!this.model) throw new Error('Model not loaded');

        // Preprocess: resize and normalize to [0, 1]
        const tensor = tf.tidy(() => {
            const img = tf.browser.fromPixels(imageSource);
            const resized = tf.image.resizeBilinear(img, [this.inputSize, this.inputSize]);
            const normalized = resized.div(255.0);
            return normalized.expandDims(0);  // [1, H, W, 3]
        });

        const start = performance.now();
        const predictions = this.model.predict(tensor) as tf.Tensor[];
        const inferenceMs = performance.now() - start;

        // Parse SSD output tensors
        const [boxes, classes, scores, numDetections] = await Promise.all(
            predictions.map(t => t.data())
        );

        tensor.dispose();
        predictions.forEach(t => t.dispose());

        // Post-process detections
        const detections: DetectionBox[] = [];
        const count = numDetections[0];

        for (let i = 0; i < count; i++) {
            const score = scores[i] as number;
            if (score < this.confidenceThreshold) continue;

            const classIdx = Math.round(classes[i] as number);
            const [y1, x1, y2, x2] = [
                boxes[i * 4],
                boxes[i * 4 + 1],
                boxes[i * 4 + 2],
                boxes[i * 4 + 3],
            ];

            detections.push({
                x: x1 as number,
                y: y1 as number,
                width: (x2 as number) - (x1 as number),
                height: (y2 as number) - (y1 as number),
                label: this.labels[classIdx] || `unknown_${classIdx}`,
                score,
            });
        }

        // NMS (Non-Maximum Suppression) in case model doesn't include it
        return this.nms(detections);
    }

    private nms(detections: DetectionBox[]): DetectionBox[] {
        detections.sort((a, b) => b.score - a.score);
        const kept: DetectionBox[] = [];

        for (const det of detections) {
            let dominated = false;
            for (const existing of kept) {
                if (this.iou(det, existing) > this.iouThreshold) {
                    dominated = true;
                    break;
                }
            }
            if (!dominated) kept.push(det);
        }

        return kept;
    }

    private iou(a: DetectionBox, b: DetectionBox): number {
        const x1 = Math.max(a.x, b.x);
        const y1 = Math.max(a.y, b.y);
        const x2 = Math.min(a.x + a.width, b.x + b.width);
        const y2 = Math.min(a.y + a.height, b.y + b.height);

        const intersection = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
        const areaA = a.width * a.height;
        const areaB = b.width * b.height;

        return intersection / (areaA + areaB - intersection);
    }

    dispose(): void {
        this.model = null;
    }
}
```

```python
# edge_model_optimization.py — Prepare models for edge deployment
import onnx
from onnxruntime.quantization import (
    quantize_dynamic,
    quantize_static,
    QuantType,
    CalibrationDataReader,
)
import numpy as np
from pathlib import Path
from typing import Iterator


class ImageCalibrationReader(CalibrationDataReader):
    """Calibration data for static quantization."""

    def __init__(self, calibration_dir: str, input_name: str, input_shape: tuple):
        self.input_name = input_name
        self.input_shape = input_shape
        self.image_files = list(Path(calibration_dir).glob("*.jpg"))
        self.idx = 0

    def get_next(self) -> dict | None:
        if self.idx >= len(self.image_files):
            return None
        # Generate calibration tensor (simplified)
        data = np.random.randn(*self.input_shape).astype(np.float32)
        self.idx += 1
        return {self.input_name: data}


def optimize_for_edge(
    model_path: str,
    output_dir: str,
    calibration_dir: str | None = None,
) -> dict[str, str]:
    """Produce optimized model variants for edge deployment."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    results = {}

    base = Path(model_path).stem

    # 1. Dynamic quantization (INT8 weights, no calibration needed)
    dynamic_path = str(output / f"{base}_dynamic_int8.onnx")
    quantize_dynamic(
        model_path,
        dynamic_path,
        weight_type=QuantType.QInt8,
    )
    results["dynamic_int8"] = dynamic_path

    # 2. Static quantization (INT8 weights + activations, needs calibration)
    if calibration_dir:
        model = onnx.load(model_path)
        input_name = model.graph.input[0].name
        input_shape = [d.dim_value for d in model.graph.input[0].type.tensor_type.shape.dim]

        static_path = str(output / f"{base}_static_int8.onnx")
        calibrator = ImageCalibrationReader(calibration_dir, input_name, tuple(input_shape))

        quantize_static(
            model_path,
            static_path,
            calibration_data_reader=calibrator,
            quant_format=QuantType.QInt8,
        )
        results["static_int8"] = static_path

    # Print size comparison
    original_size = Path(model_path).stat().st_size / (1024 * 1024)
    for name, path in results.items():
        opt_size = Path(path).stat().st_size / (1024 * 1024)
        ratio = opt_size / original_size * 100
        print(f"{name}: {opt_size:.1f}MB ({ratio:.0f}% of original {original_size:.1f}MB)")

    return results
```

| Runtime | Platform | GPU Support | Model Format | Latency (MobileNet) | Size |
|---|---|---|---|---|---|
| ONNX Runtime Web | Browser | WebGPU, WebGL, WASM | .onnx | ~15ms (WebGPU) | ~2MB runtime |
| TF.js + TFLite | Browser | WebGL, WASM | .tflite | ~20ms (WebGL) | ~1.5MB runtime |
| MediaPipe | Browser/Mobile | GPU delegate | .tflite | ~10ms | ~3MB runtime |
| CF Workers AI | Edge (server) | Cloudflare GPUs | ONNX/PyTorch | ~20ms | N/A (managed) |
| ONNX Runtime (native) | Server edge | CUDA, DirectML | .onnx | ~5ms (CUDA) | ~50MB |

| Optimization | Size Reduction | Accuracy Loss | Speedup |
|---|---|---|---|
| FP32 (baseline) | 1x | 0% | 1x |
| FP16 | ~50% | <0.1% | 1.5-2x |
| Dynamic INT8 | ~75% | 0.5-1% | 2-3x |
| Static INT8 | ~75% | 0.2-0.5% | 3-4x |
| INT4 (GPTQ/AWQ) | ~87% | 1-3% | 3-5x |
| Pruning + INT8 | ~90% | 1-2% | 4-6x |

Key patterns:
1. Use WebGPU execution provider first, fall back to WebGL, then WASM SIMD
2. Warm up models with a dummy inference to compile GPU shaders before real use
3. Use OffscreenCanvas for preprocessing in Web Workers (non-blocking)
4. Static INT8 quantization gives best size/accuracy tradeoff for edge
5. NMS (Non-Maximum Suppression) must be done in JS if not baked into the model
6. Keep edge models under 10MB for acceptable load times on mobile networks
7. Use `tf.tidy()` to prevent memory leaks from intermediate tensor allocations'''
    ),
]
"""
