"""Edge computing — CDN patterns, edge functions, and caching strategies."""

PAIRS = [
    (
        "devops/cdn-caching",
        "Show CDN and HTTP caching patterns: Cache-Control headers, cache invalidation, stale-while-revalidate, and CDN configuration.",
        '''CDN and HTTP caching patterns:

```python
# --- Cache-Control header patterns ---

from fastapi import FastAPI, Response
from datetime import datetime, timezone

app = FastAPI()


# Immutable static assets (hashed filenames like app.abc123.js)
@app.get("/static/{filename}")
async def static_asset(filename: str, response: Response):
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # CDN and browser cache for 1 year, never revalidate
    return serve_file(filename)


# API responses: short cache with revalidation
@app.get("/api/products")
async def list_products(response: Response):
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    # Fresh for 60s, serve stale for 5 min while revalidating in background
    response.headers["Vary"] = "Accept-Encoding, Accept-Language"
    return get_products()


# Private data: cache in browser only, not CDN
@app.get("/api/profile")
async def get_profile(response: Response):
    response.headers["Cache-Control"] = "private, max-age=300"
    # Browser can cache for 5 min, CDN must not cache
    return get_user_profile()


# Never cache (sensitive data, real-time)
@app.get("/api/account/balance")
async def get_balance(response: Response):
    response.headers["Cache-Control"] = "no-store"
    # No caching anywhere
    return get_account_balance()


# ETag-based conditional caching
@app.get("/api/config")
async def get_config(response: Response):
    config = load_config()
    import hashlib
    etag = hashlib.md5(str(config).encode()).hexdigest()

    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "no-cache"  # Always revalidate
    # Client sends If-None-Match, server returns 304 if unchanged
    return config


# --- Cache invalidation patterns ---

class CacheInvalidator:
    """Invalidate CDN cache via API."""

    def __init__(self, cdn_api_url: str, api_key: str):
        self.cdn_api_url = cdn_api_url
        self.api_key = api_key

    async def purge_url(self, url: str):
        """Purge specific URL from CDN cache."""
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.cdn_api_url}/purge",
                json={"files": [url]},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

    async def purge_tag(self, tag: str):
        """Purge all URLs with a cache tag."""
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.cdn_api_url}/purge_tag",
                json={"tags": [tag]},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

    async def purge_prefix(self, prefix: str):
        """Purge all URLs matching prefix."""
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.cdn_api_url}/purge_prefix",
                json={"prefixes": [prefix]},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )


# --- Surrogate keys (cache tags) ---

@app.get("/api/products/{product_id}")
async def get_product(product_id: str, response: Response):
    product = load_product(product_id)

    response.headers["Cache-Control"] = "public, max-age=3600"
    # Surrogate keys enable targeted purging
    response.headers["Surrogate-Key"] = f"product-{product_id} products category-{product['category']}"
    # Can purge: all products, specific product, or entire category

    return product


@app.put("/api/products/{product_id}")
async def update_product(product_id: str):
    product = save_product(product_id)

    # Purge this product and its category from CDN
    invalidator = CacheInvalidator(CDN_API, CDN_KEY)
    await invalidator.purge_tag(f"product-{product_id}")
    await invalidator.purge_tag(f"category-{product['category']}")

    return product
```

```nginx
# --- nginx CDN/caching config ---

# Cache zone
proxy_cache_path /var/cache/nginx/cdn levels=1:2
                 keys_zone=cdn:50m max_size=10g
                 inactive=24h use_temp_path=off;

server {
    # Static assets: long cache
    location ~* \.(js|css|png|jpg|svg|woff2)$ {
        proxy_cache cdn;
        proxy_cache_valid 200 365d;
        proxy_cache_key "$scheme$request_uri";
        add_header X-Cache-Status $upstream_cache_status;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # API: short cache with stale serving
    location /api/ {
        proxy_cache cdn;
        proxy_cache_valid 200 60s;
        proxy_cache_use_stale error timeout updating http_500 http_502;
        proxy_cache_background_update on;
        proxy_cache_lock on;

        # Vary by auth (don't serve cached private data to wrong user)
        proxy_cache_key "$scheme$request_uri$http_authorization";
    }
}
```

CDN caching patterns:
1. **`immutable`** — hashed filenames never change, cache forever
2. **`stale-while-revalidate`** — serve stale content while fetching fresh in background
3. **Surrogate keys** — tag cached responses for targeted invalidation
4. **`Vary` header** — cache different versions per encoding/language/auth
5. **`proxy_cache_use_stale`** — nginx serves stale on origin error (resilience)'''
    ),
    (
        "devops/edge-functions",
        "Show edge function patterns: request routing, A/B testing, geolocation, and authentication at the edge.",
        '''Edge function patterns (Cloudflare Workers / Vercel Edge):

```typescript
// --- Cloudflare Worker: request routing and middleware ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Middleware chain
    const middlewares = [
      addSecurityHeaders,
      handleCORS,
      rateLimit,
      routeRequest,
    ];

    let response: Response | null = null;
    for (const middleware of middlewares) {
      response = await middleware(request, env, url);
      if (response) return response;
    }

    return new Response("Not Found", { status: 404 });
  },
};


// --- Security headers middleware ---

async function addSecurityHeaders(
  request: Request, env: Env, url: URL,
): Promise<Response | null> {
  // Continue to next middleware (return null = pass through)
  return null;
}


// --- CORS at the edge ---

async function handleCORS(
  request: Request, env: Env, url: URL,
): Promise<Response | null> {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "86400",
      },
    });
  }
  return null;
}


// --- A/B testing at the edge ---

async function routeRequest(
  request: Request, env: Env, url: URL,
): Promise<Response | null> {
  if (url.pathname === "/" || url.pathname.startsWith("/landing")) {
    return handleABTest(request, env);
  }

  // Proxy to origin
  return fetch(request);
}

async function handleABTest(request: Request, env: Env): Promise<Response> {
  // Deterministic bucket from cookie or IP
  const cookie = request.headers.get("cookie") || "";
  const abCookie = cookie.match(/ab_variant=(\w+)/)?.[1];

  let variant: string;
  if (abCookie) {
    variant = abCookie;
  } else {
    // Hash-based assignment (stable per user)
    const ip = request.headers.get("cf-connecting-ip") || "unknown";
    const hash = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(ip + env.AB_SALT),
    );
    const hashArray = new Uint8Array(hash);
    variant = hashArray[0] < 128 ? "control" : "experiment";
  }

  // Route to different origins
  const origins: Record<string, string> = {
    control: "https://v1.myapp.com",
    experiment: "https://v2.myapp.com",
  };

  const originUrl = new URL(request.url);
  originUrl.hostname = new URL(origins[variant]).hostname;

  const response = await fetch(originUrl.toString(), request);
  const newResponse = new Response(response.body, response);

  // Set cookie for consistent experience
  if (!abCookie) {
    newResponse.headers.append(
      "Set-Cookie",
      `ab_variant=${variant}; Path=/; Max-Age=2592000; SameSite=Lax`,
    );
  }

  // Track assignment for analytics
  newResponse.headers.set("X-AB-Variant", variant);
  return newResponse;
}


// --- Geolocation-based routing ---

async function geoRoute(request: Request, env: Env): Promise<Response> {
  // Cloudflare provides geo data
  const country = request.headers.get("cf-ipcountry") || "US";
  const city = (request as any).cf?.city || "Unknown";

  const regionOrigins: Record<string, string> = {
    US: "https://us.api.myapp.com",
    EU: "https://eu.api.myapp.com",
    AP: "https://ap.api.myapp.com",
  };

  // Map country to region
  const euCountries = new Set(["DE", "FR", "IT", "ES", "NL", "PL", "SE"]);
  const apCountries = new Set(["JP", "KR", "AU", "SG", "IN"]);

  let region = "US";
  if (euCountries.has(country)) region = "EU";
  if (apCountries.has(country)) region = "AP";

  const origin = regionOrigins[region];
  const url = new URL(request.url);
  url.hostname = new URL(origin).hostname;

  return fetch(url.toString(), {
    ...request,
    headers: {
      ...Object.fromEntries(request.headers),
      "X-User-Country": country,
      "X-User-City": city,
    },
  });
}


// --- Edge-side JWT validation ---

async function validateJWT(request: Request, env: Env): Promise<Response | null> {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 });
  }

  const token = auth.slice(7);
  const [headerB64, payloadB64, signatureB64] = token.split(".");

  // Verify signature using Web Crypto API
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.JWT_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );

  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = Uint8Array.from(atob(signatureB64.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));

  const valid = await crypto.subtle.verify("HMAC", key, signature, data);
  if (!valid) {
    return new Response("Invalid token", { status: 401 });
  }

  // Check expiry
  const payload = JSON.parse(atob(payloadB64));
  if (payload.exp && payload.exp < Date.now() / 1000) {
    return new Response("Token expired", { status: 401 });
  }

  // Pass through (null = continue to origin)
  return null;
}

interface Env {
  ALLOWED_ORIGIN: string;
  AB_SALT: string;
  JWT_SECRET: string;
}
```

Edge function patterns:
1. **Middleware chain** — sequential handlers; returning `null` passes to next
2. **A/B testing** — deterministic hash-based bucketing with cookie persistence
3. **Geo-routing** — route to nearest regional origin using `cf-ipcountry` header
4. **Edge JWT validation** — reject invalid tokens before hitting origin server
5. **`crypto.subtle`** — Web Crypto API for HMAC/SHA operations at the edge'''
    ),
]
