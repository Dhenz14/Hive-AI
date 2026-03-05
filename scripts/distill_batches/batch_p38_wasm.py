"""WebAssembly — Wasm basics, Rust-to-Wasm, integration with JavaScript, and use cases."""

PAIRS = [
    (
        "webdev/webassembly-basics",
        "Show WebAssembly patterns: compiling Rust to Wasm, JavaScript interop, memory management, and practical use cases.",
        """WebAssembly with Rust and JavaScript:

```rust
// --- Rust library compiled to Wasm ---
// Cargo.toml:
// [lib]
// crate-type = ["cdylib"]
//
// [dependencies]
// wasm-bindgen = "0.2"
// serde = { version = "1", features = ["derive"] }
// serde-wasm-bindgen = "0.6"

use wasm_bindgen::prelude::*;
use serde::{Serialize, Deserialize};

// Simple exported function
#[wasm_bindgen]
pub fn fibonacci(n: u32) -> u64 {
    if n <= 1 { return n as u64; }
    let (mut a, mut b) = (0u64, 1u64);
    for _ in 2..=n {
        let temp = b;
        b = a + b;
        a = temp;
    }
    b
}

// Struct exposed to JavaScript
#[wasm_bindgen]
pub struct ImageProcessor {
    width: u32,
    height: u32,
    pixels: Vec<u8>,
}

#[wasm_bindgen]
impl ImageProcessor {
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32) -> ImageProcessor {
        ImageProcessor {
            width,
            height,
            pixels: vec![0; (width * height * 4) as usize],
        }
    }

    pub fn pixels_ptr(&self) -> *const u8 {
        self.pixels.as_ptr()
    }

    pub fn pixels_len(&self) -> usize {
        self.pixels.len()
    }

    pub fn set_pixels(&mut self, data: &[u8]) {
        self.pixels = data.to_vec();
    }

    pub fn grayscale(&mut self) {
        for chunk in self.pixels.chunks_exact_mut(4) {
            let gray = (0.299 * chunk[0] as f64
                      + 0.587 * chunk[1] as f64
                      + 0.114 * chunk[2] as f64) as u8;
            chunk[0] = gray;
            chunk[1] = gray;
            chunk[2] = gray;
            // chunk[3] (alpha) unchanged
        }
    }

    pub fn blur(&mut self, radius: u32) {
        let w = self.width as usize;
        let h = self.height as usize;
        let r = radius as usize;
        let mut output = self.pixels.clone();

        for y in 0..h {
            for x in 0..w {
                let mut r_sum = 0u32;
                let mut g_sum = 0u32;
                let mut b_sum = 0u32;
                let mut count = 0u32;

                let y_start = y.saturating_sub(r);
                let y_end = (y + r + 1).min(h);
                let x_start = x.saturating_sub(r);
                let x_end = (x + r + 1).min(w);

                for ny in y_start..y_end {
                    for nx in x_start..x_end {
                        let idx = (ny * w + nx) * 4;
                        r_sum += self.pixels[idx] as u32;
                        g_sum += self.pixels[idx + 1] as u32;
                        b_sum += self.pixels[idx + 2] as u32;
                        count += 1;
                    }
                }

                let idx = (y * w + x) * 4;
                output[idx] = (r_sum / count) as u8;
                output[idx + 1] = (g_sum / count) as u8;
                output[idx + 2] = (b_sum / count) as u8;
            }
        }
        self.pixels = output;
    }

    pub fn brightness(&mut self, factor: f64) {
        for chunk in self.pixels.chunks_exact_mut(4) {
            chunk[0] = (chunk[0] as f64 * factor).min(255.0) as u8;
            chunk[1] = (chunk[1] as f64 * factor).min(255.0) as u8;
            chunk[2] = (chunk[2] as f64 * factor).min(255.0) as u8;
        }
    }
}

// Complex data via serde
#[derive(Serialize, Deserialize)]
pub struct SearchResult {
    pub index: usize,
    pub score: f64,
    pub matched: String,
}

#[wasm_bindgen]
pub fn fuzzy_search(query: &str, items: JsValue) -> JsValue {
    let items: Vec<String> = serde_wasm_bindgen::from_value(items).unwrap();
    let query_lower = query.to_lowercase();

    let mut results: Vec<SearchResult> = items.iter()
        .enumerate()
        .filter_map(|(i, item)| {
            let item_lower = item.to_lowercase();
            if item_lower.contains(&query_lower) {
                Some(SearchResult {
                    index: i,
                    score: query_lower.len() as f64 / item_lower.len() as f64,
                    matched: item.clone(),
                })
            } else {
                None
            }
        })
        .collect();

    results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
    serde_wasm_bindgen::to_value(&results).unwrap()
}
```

```javascript
// --- JavaScript integration ---

// Using wasm-pack output
import init, { fibonacci, ImageProcessor, fuzzy_search } from './pkg/my_wasm.js';

async function main() {
  await init();  // Initialize Wasm module

  // Simple function call
  console.log(fibonacci(50));  // 12586269025

  // Image processing
  const canvas = document.getElementById('canvas');
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

  const processor = new ImageProcessor(canvas.width, canvas.height);
  processor.set_pixels(new Uint8Array(imageData.data.buffer));
  processor.grayscale();

  // Read pixels back from Wasm memory
  const wasmMemory = new Uint8Array(
    processor.pixels_ptr(),
    processor.pixels_len()
  );
  imageData.data.set(wasmMemory);
  ctx.putImageData(imageData, 0, 0);

  // Complex data exchange
  const results = fuzzy_search("rust", ["Rust", "JavaScript", "Rusty", "Trust"]);
  console.log(results);  // [{index: 0, score: 1.0, matched: "Rust"}, ...]

  // Clean up (prevent memory leaks)
  processor.free();
}
```

When to use WebAssembly:
1. **CPU-intensive** — image/video processing, physics, compression
2. **Existing native code** — port C/C++/Rust libraries to browser
3. **Consistent performance** — games, simulations, real-time audio
4. **Large dataset processing** — parsing, search, sorting

When NOT to use Wasm:
- DOM manipulation (JS is faster for this)
- Simple CRUD apps (overhead not worth it)
- I/O-bound tasks (async JS is better)"""
    ),
    (
        "webdev/pwa-patterns",
        "Show Progressive Web App patterns: service workers, caching strategies, offline support, and push notifications.",
        """Progressive Web App (PWA) patterns:

```javascript
// --- Service Worker with caching strategies ---
// sw.js

const CACHE_NAME = 'app-v1.2.0';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/manifest.json',
  '/icons/icon-192.png',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// Fetch: apply caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Strategy 1: Cache First (static assets)
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Strategy 2: Network First (API calls)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Strategy 3: Stale While Revalidate (images, fonts)
  if (request.destination === 'image' || request.destination === 'font') {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Default: network with cache fallback
  event.respondWith(networkFirst(request));
});

// --- Caching strategies ---

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(CACHE_NAME);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request, timeout = 3000) {
  try {
    const response = await Promise.race([
      fetch(request),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), timeout)
      ),
    ]);
    // Cache successful GET responses
    if (request.method === 'GET' && response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  // Revalidate in background
  const fetchPromise = fetch(request)
    .then(response => {
      cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);

  // Return cached immediately, or wait for network
  return cached || fetchPromise;
}


// --- Background Sync (offline form submission) ---

self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-forms') {
    event.waitUntil(syncPendingForms());
  }
});

async function syncPendingForms() {
  const db = await openDB();
  const pending = await db.getAll('pending-forms');
  for (const form of pending) {
    try {
      await fetch(form.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form.data),
      });
      await db.delete('pending-forms', form.id);
    } catch {
      break;  // Still offline, try again later
    }
  }
}
```

```json
// manifest.json
{
  "name": "My App",
  "short_name": "MyApp",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#3b82f6",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

Caching strategy selection:
- **Cache First** — static assets that rarely change (CSS, JS, images)
- **Network First** — API data that should be fresh but works offline
- **Stale While Revalidate** — content where slight staleness is OK
- **Network Only** — real-time data, authentication
- **Cache Only** — offline-first content bundled with the app"""
    ),
]
