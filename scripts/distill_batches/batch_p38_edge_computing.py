"""Edge computing — CDN workers, edge functions, and distributed computing patterns."""

PAIRS = [
    (
        "architecture/edge-computing",
        "Show edge computing patterns: CDN workers, edge middleware, geo-routing, and A/B testing at the edge.",
        """Edge computing patterns for low-latency applications:

```javascript
// --- Cloudflare Worker: API Gateway at the Edge ---

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Rate limiting at the edge (using Durable Objects)
    const rateLimiter = env.RATE_LIMITER.get(
      env.RATE_LIMITER.idFromName(request.headers.get('CF-Connecting-IP'))
    );
    const allowed = await rateLimiter.fetch(request.url);
    if (!allowed.ok) {
      return new Response('Rate limited', { status: 429 });
    }

    // Geo-based routing
    const country = request.cf?.country || 'US';
    const origins = {
      US: 'https://us-api.example.com',
      EU: 'https://eu-api.example.com',
      APAC: 'https://apac-api.example.com',
    };
    const region = ['DE', 'FR', 'GB', 'NL', 'IT'].includes(country) ? 'EU'
                 : ['JP', 'KR', 'AU', 'SG', 'IN'].includes(country) ? 'APAC'
                 : 'US';
    const origin = origins[region];

    // A/B testing at edge
    const variant = getVariant(request, env);

    // Forward request to origin with edge-computed headers
    const response = await fetch(`${origin}${url.pathname}${url.search}`, {
      method: request.method,
      headers: {
        ...Object.fromEntries(request.headers),
        'X-Edge-Region': region,
        'X-Edge-Country': country,
        'X-AB-Variant': variant,
        'X-Request-ID': crypto.randomUUID(),
      },
      body: request.method !== 'GET' ? request.body : undefined,
    });

    // Cache at edge for GET requests
    const cacheableResponse = new Response(response.body, response);
    if (request.method === 'GET' && response.ok) {
      cacheableResponse.headers.set('Cache-Control', 'public, s-maxage=60');
    }
    cacheableResponse.headers.set('X-Served-By', 'edge');

    return cacheableResponse;
  }
};

function getVariant(request, env) {
  // Sticky variant based on cookie
  const cookie = request.headers.get('Cookie') || '';
  const match = cookie.match(/ab_variant=(\w+)/);
  if (match) return match[1];

  // New user: assign variant based on hash
  const ip = request.headers.get('CF-Connecting-IP') || '';
  const hash = simpleHash(ip);
  return hash % 100 < 10 ? 'B' : 'A';
}

function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash = hash & hash;
  }
  return Math.abs(hash);
}


// --- Edge KV for configuration ---

async function getConfig(env, key) {
  const cached = await env.CONFIG_KV.get(key, { type: 'json' });
  if (cached) return cached;

  // Fallback to origin
  const response = await fetch(`https://api.internal/config/${key}`);
  const data = await response.json();

  // Cache at edge for 5 minutes
  await env.CONFIG_KV.put(key, JSON.stringify(data), { expirationTtl: 300 });
  return data;
}


// --- Edge authentication (JWT verification) ---

async function verifyJWT(token, env) {
  try {
    const [headerB64, payloadB64, signatureB64] = token.split('.');

    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(env.JWT_SECRET),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );

    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const signature = Uint8Array.from(
      atob(signatureB64.replace(/-/g, '+').replace(/_/g, '/')),
      c => c.charCodeAt(0),
    );

    const valid = await crypto.subtle.verify('HMAC', key, signature, data);
    if (!valid) return null;

    const payload = JSON.parse(atob(payloadB64));
    if (payload.exp && payload.exp < Date.now() / 1000) return null;

    return payload;
  } catch {
    return null;
  }
}
```

```python
# --- Edge function use cases ---

EDGE_USE_CASES = {
    "authentication": "Verify JWT at edge, reject 401s before hitting origin",
    "rate_limiting": "Per-IP limits at edge with Durable Objects or KV",
    "geo_routing": "Route to nearest region based on CF-IPCountry header",
    "ab_testing": "Assign variants at edge, no origin round-trip",
    "image_optimization": "Resize/compress images on-the-fly at edge",
    "bot_detection": "Block scrapers before they reach origin",
    "header_injection": "Add security headers, request IDs at edge",
    "redirects": "Handle redirects at edge (marketing URLs, legacy paths)",
    "feature_flags": "Read flags from KV, route to different origins",
    "caching": "Smart cache with vary headers, stale-while-revalidate",
}
```

Edge computing patterns:
1. **Auth at edge** — verify tokens before requests hit origin
2. **Geo-routing** — route to nearest datacenter automatically
3. **Edge KV** — distributed config/cache with eventual consistency
4. **A/B testing** — assign variants without origin round-trip
5. **Image optimization** — resize/format on-the-fly at CDN edge"""
    ),
    (
        "architecture/micro-frontends",
        "Show micro-frontend patterns: module federation, single-spa, shared state, and deployment strategies.",
        """Micro-frontend architecture patterns:

```javascript
// --- Module Federation (Webpack 5) ---

// Host application: webpack.config.js
const { ModuleFederationPlugin } = require('webpack').container;

module.exports = {
  plugins: [
    new ModuleFederationPlugin({
      name: 'host',
      remotes: {
        // Load micro-frontends at runtime
        auth: 'auth@https://auth.cdn.example.com/remoteEntry.js',
        dashboard: 'dashboard@https://dash.cdn.example.com/remoteEntry.js',
        settings: 'settings@https://settings.cdn.example.com/remoteEntry.js',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.0.0' },
        'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
        'react-router-dom': { singleton: true },
      },
    }),
  ],
};

// Remote (auth micro-frontend): webpack.config.js
module.exports = {
  plugins: [
    new ModuleFederationPlugin({
      name: 'auth',
      filename: 'remoteEntry.js',
      exposes: {
        './LoginPage': './src/pages/LoginPage',
        './AuthProvider': './src/providers/AuthProvider',
        './useAuth': './src/hooks/useAuth',
      },
      shared: {
        react: { singleton: true },
        'react-dom': { singleton: true },
      },
    }),
  ],
};


// --- Host application loading remotes ---

// Lazy load micro-frontends
const LoginPage = React.lazy(() => import('auth/LoginPage'));
const Dashboard = React.lazy(() => import('dashboard/DashboardPage'));
const Settings = React.lazy(() => import('settings/SettingsPage'));

function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary fallback={<FallbackUI />}>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard/*" element={<Dashboard />} />
            <Route path="/settings/*" element={<Settings />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}


// --- Shared state via custom events ---

// Event bus for cross-micro-frontend communication
class MicroFrontendBus {
  static emit(event, data) {
    window.dispatchEvent(
      new CustomEvent(`mfe:${event}`, { detail: data })
    );
  }

  static on(event, callback) {
    const handler = (e) => callback(e.detail);
    window.addEventListener(`mfe:${event}`, handler);
    return () => window.removeEventListener(`mfe:${event}`, handler);
  }
}

// Auth MFE emits user change
MicroFrontendBus.emit('auth:user-changed', { user: currentUser });

// Dashboard MFE listens
useEffect(() => {
  return MicroFrontendBus.on('auth:user-changed', ({ user }) => {
    setUser(user);
  });
}, []);


// --- Error boundary for resilient loading ---

class MFEErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error('Micro-frontend failed to load:', error);
    // Report to monitoring
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="mfe-error">
          <p>This section is temporarily unavailable.</p>
          <button onClick={() => this.setState({ hasError: false })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Architecture patterns:
1. **Module Federation** — share modules at runtime, independent deployment
2. **Shared singletons** — React, router shared to avoid duplication
3. **Event bus** — cross-MFE communication via custom events
4. **Error boundaries** — graceful degradation when one MFE fails
5. **Independent deploys** — each team deploys their MFE independently"""
    ),
]
