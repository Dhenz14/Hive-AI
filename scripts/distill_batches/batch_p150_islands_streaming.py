"""Islands architecture and streaming SSR — modern rendering patterns."""

PAIRS = [
    (
        "frontend/islands-architecture",
        "Show islands architecture patterns: partial hydration, selective interactivity, and implementation with Astro and Fresh (Deno).",
        """Islands architecture — partial hydration for fast pages:

```typescript
// === Astro Islands ===
// Only interactive components ship JavaScript.
// Static HTML loads instantly; islands hydrate independently.

// --- src/pages/product/[id].astro ---
---
import Layout from "../../layouts/Layout.astro";
import ProductGallery from "../../components/ProductGallery";   // React
import AddToCart from "../../components/AddToCart.svelte";       // Svelte
import Reviews from "../../components/Reviews.tsx";             // React
import { getProduct, getReviews } from "../../lib/api";

const { id } = Astro.params;
const product = await getProduct(id!);
const reviews = await getReviews(id!);
---

<Layout title={product.name}>
  <!-- Static HTML: zero JS, renders instantly -->
  <header>
    <h1>{product.name}</h1>
    <p class="price">${product.price.toFixed(2)}</p>
    <p class="description">{product.description}</p>
  </header>

  <!-- Island 1: client:load — hydrate immediately (above the fold) -->
  <ProductGallery
    client:load
    images={product.images}
  />

  <!-- Island 2: client:visible — hydrate when scrolled into view -->
  <AddToCart
    client:visible
    productId={product.id}
    price={product.price}
  />

  <!-- Static section: no JS needed -->
  <section class="specs">
    <h2>Specifications</h2>
    <dl>
      {product.specs.map(([key, val]) => (
        <>
          <dt>{key}</dt>
          <dd>{val}</dd>
        </>
      ))}
    </dl>
  </section>

  <!-- Island 3: client:idle — hydrate when browser is idle -->
  <Reviews
    client:idle
    reviews={reviews}
    productId={product.id}
  />

  <!-- Island 4: client:media — hydrate only on desktop -->
  <!-- <DesktopEditor client:media="(min-width: 768px)" /> -->
</Layout>


// === Astro component mixing frameworks ===

// components/ProductGallery.tsx (React island)
import { useState } from "react";

interface Props {
  images: { url: string; alt: string }[];
}

export default function ProductGallery({ images }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <div className="gallery">
      <img
        src={images[activeIndex].url}
        alt={images[activeIndex].alt}
        className="main-image"
      />
      <div className="thumbnails">
        {images.map((img, i) => (
          <button
            key={img.url}
            onClick={() => setActiveIndex(i)}
            className={i === activeIndex ? "active" : ""}
          >
            <img src={img.url} alt={img.alt} width={80} height={80} />
          </button>
        ))}
      </div>
    </div>
  );
}


// === Fresh (Deno) Islands ===

// routes/product/[id].tsx — server-rendered page
import { Handlers, PageProps } from "$fresh/server.ts";
import AddToCartIsland from "../../islands/AddToCart.tsx";

interface Product {
  id: string;
  name: string;
  price: number;
}

export const handler: Handlers<Product> = {
  async GET(_req, ctx) {
    const product = await fetchProduct(ctx.params.id);
    if (!product) return ctx.renderNotFound();
    return ctx.render(product);
  },
};

export default function ProductPage({ data: product }: PageProps<Product>) {
  return (
    <main>
      {/* Static HTML — no JS */}
      <h1>{product.name}</h1>
      <p>${product.price.toFixed(2)}</p>

      {/* Island — only this component ships JS */}
      <AddToCartIsland productId={product.id} price={product.price} />
    </main>
  );
}

// islands/AddToCart.tsx — auto-detected as island by Fresh
import { useState } from "preact/hooks";

export default function AddToCart(props: { productId: string; price: number }) {
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);

  async function handleAdd() {
    await fetch("/api/cart", {
      method: "POST",
      body: JSON.stringify({ productId: props.productId, quantity: qty }),
    });
    setAdded(true);
    setTimeout(() => setAdded(false), 2000);
  }

  return (
    <div class="add-to-cart">
      <select value={qty} onChange={(e) => setQty(Number(e.currentTarget.value))}>
        {[1, 2, 3, 4, 5].map((n) => <option value={n}>{n}</option>)}
      </select>
      <button onClick={handleAdd} disabled={added}>
        {added ? "Added!" : `Add to Cart — $${(props.price * qty).toFixed(2)}`}
      </button>
    </div>
  );
}
```

Islands architecture patterns:

| Hydration directive | When | Use case |
|-------------------|------|----------|
| `client:load` | Immediately | Above-fold interactive (gallery, nav) |
| `client:idle` | Browser idle | Below-fold interactive (comments, chat) |
| `client:visible` | In viewport | Lazy interactive (infinite scroll, forms) |
| `client:media` | Media query match | Desktop-only features |
| `client:only` | Client render only | No SSR (canvas, WebGL) |

Key patterns:
1. **Zero JS by default** — static HTML ships no JavaScript; only islands opt into interactivity
2. **Independent hydration** — each island loads its own JS bundle; one slow island doesn't block others
3. **Mixed frameworks** — Astro islands can be React, Svelte, Vue, or Solid in the same page
4. **Progressive enhancement** — page is usable before any JS loads; islands add interactivity on top
5. **Fresh convention** — files in `islands/` directory are automatically client-side components"""
    ),
    (
        "frontend/streaming-ssr-suspense",
        "Show streaming SSR patterns: React Suspense boundaries, out-of-order streaming, progressive rendering, and selective hydration.",
        """Streaming SSR with React Suspense:

```typescript
// === Streaming SSR: send HTML progressively as data resolves ===

// --- Server entry point (Node.js / Edge) ---

import { renderToPipeableStream } from "react-dom/server";
import { createServer } from "http";
import App from "./App";

createServer((req, res) => {
  res.setHeader("Content-Type", "text/html; charset=utf-8");

  const { pipe, abort } = renderToPipeableStream(<App url={req.url!} />, {
    // Shell: content outside Suspense boundaries
    // Sent immediately — user sees layout + loading states
    bootstrapScripts: ["/static/client.js"],

    onShellReady() {
      // Shell rendered — start streaming
      res.statusCode = 200;
      pipe(res);
    },

    onShellError(error) {
      // Shell failed — send error page
      res.statusCode = 500;
      res.end("<!DOCTYPE html><html><body><h1>Server Error</h1></body></html>");
    },

    onAllReady() {
      // All Suspense boundaries resolved (useful for crawlers)
      // For bots, you might wait for this instead of onShellReady
    },

    onError(error) {
      console.error("Streaming error:", error);
    },
  });

  // Timeout: abort if streaming takes too long
  setTimeout(() => abort(), 10000);
}).listen(3000);


// === App with Suspense boundaries ===

// --- App.tsx ---

import { Suspense } from "react";

function App({ url }: { url: string }) {
  return (
    <html>
      <head>
        <title>Streaming SSR</title>
        <link rel="stylesheet" href="/static/styles.css" />
      </head>
      <body>
        {/* Shell: renders immediately */}
        <Header />
        <Nav />

        <main>
          {/* Suspense boundary 1: product data */}
          <Suspense fallback={<ProductSkeleton />}>
            <ProductDetails productId={extractId(url)} />
          </Suspense>

          <div className="grid">
            {/* Suspense boundary 2: recommendations (slow API) */}
            <Suspense fallback={<RecommendationsSkeleton />}>
              <Recommendations productId={extractId(url)} />
            </Suspense>

            {/* Suspense boundary 3: reviews (independent) */}
            <Suspense fallback={<ReviewsSkeleton />}>
              <Reviews productId={extractId(url)} />
            </Suspense>
          </div>
        </main>

        <Footer />
      </body>
    </html>
  );
}


// === Async server components (data fetching) ===

// React Server Components fetch data directly — no useEffect, no API routes

async function ProductDetails({ productId }: { productId: string }) {
  // This fetch happens on the server during SSR
  const product = await fetch(`https://api.example.com/products/${productId}`)
    .then(r => r.json());

  return (
    <section className="product-details">
      <h1>{product.name}</h1>
      <p className="price">${product.price.toFixed(2)}</p>
      <p>{product.description}</p>

      {/* Nested Suspense: independent loading for stock check */}
      <Suspense fallback={<span>Checking availability...</span>}>
        <StockStatus productId={productId} />
      </Suspense>
    </section>
  );
}

async function Recommendations({ productId }: { productId: string }) {
  // Slow API call — streams in when ready, doesn't block product details
  const recs = await fetch(`https://api.example.com/recommendations/${productId}`)
    .then(r => r.json());

  return (
    <aside className="recommendations">
      <h2>You might also like</h2>
      <ul>
        {recs.map((item: any) => (
          <li key={item.id}>
            <a href={`/product/${item.id}`}>{item.name}</a>
          </li>
        ))}
      </ul>
    </aside>
  );
}

async function Reviews({ productId }: { productId: string }) {
  const reviews = await fetch(`https://api.example.com/reviews/${productId}`)
    .then(r => r.json());

  return (
    <section className="reviews">
      <h2>Reviews ({reviews.length})</h2>
      {reviews.map((review: any) => (
        <article key={review.id} className="review">
          <div className="rating">{"★".repeat(review.rating)}</div>
          <p>{review.text}</p>
          <span className="author">{review.author}</span>
        </article>
      ))}
    </section>
  );
}


// === Selective Hydration ===

// React 18+ selectively hydrates Suspense boundaries based on user interaction.
// If a user clicks on a not-yet-hydrated Suspense boundary,
// React prioritizes hydrating THAT boundary first.

// --- Client entry point ---
import { hydrateRoot } from "react-dom/client";

// Selective hydration: React hydrates Suspense boundaries independently
// and prioritizes boundaries the user interacts with
hydrateRoot(document.getElementById("root")!, <App url={window.location.pathname} />);


// === Streaming with Next.js App Router ===

// --- app/product/[id]/page.tsx ---

import { Suspense } from "react";

// This page uses streaming automatically with Suspense
export default async function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <main>
      {/* Streamed immediately */}
      <Suspense fallback={<div className="skeleton h-96" />}>
        <ProductDetails id={id} />
      </Suspense>

      {/* Streamed independently when data resolves */}
      <Suspense fallback={<div className="skeleton h-48" />}>
        <Reviews id={id} />
      </Suspense>
    </main>
  );
}

// loading.tsx — automatic Suspense boundary for the route segment
export default function Loading() {
  return <div className="page-skeleton">Loading...</div>;
}
```

Streaming SSR timeline:
```
Time →
0ms     Shell sent: <html><head>...</head><body><Header/><Nav/><ProductSkeleton/>...
100ms   Product data resolves → <script>swap ProductSkeleton with ProductDetails</script>
300ms   Reviews resolve → <script>swap ReviewsSkeleton with Reviews</script>
800ms   Recommendations resolve → <script>swap RecommendationsSkeleton with Recommendations</script>
1000ms  All hydrated — page fully interactive
```

Key patterns:
1. **Shell-first streaming** — send HTML layout + skeletons immediately; replace with real content as data resolves
2. **Out-of-order streaming** — Suspense boundaries resolve independently; fast data appears first regardless of DOM order
3. **Selective hydration** — React prioritizes hydrating the Suspense boundary the user interacts with first
4. **Nested Suspense** — fine-grained loading states; each boundary can show its own skeleton
5. **Next.js `loading.tsx`** — automatic Suspense boundary per route segment; no manual Suspense wrapping needed"""
    ),
]
