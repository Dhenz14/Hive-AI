"""
Batch p1083: TypeScript/React production pairs - Next.js Data Patterns
Topics: server actions, revalidation, ISR, streaming SSR, data caching
"""

PAIRS = [
    ("react/nextjs_server_actions", r'''Build advanced Next.js Server Actions patterns for a todo application including form actions with useFormState, optimistic updates with useOptimistic, and progressive enhancement.''', r'''// app/todos/actions.ts
// "use server"

import { revalidatePath } from "next/cache";

interface Todo {
  id: string;
  text: string;
  completed: boolean;
  createdAt: string;
}

export async function addTodo(prevState: any, formData: FormData): Promise<{
  error?: string;
  success?: boolean;
}> {
  const text = formData.get("text") as string;

  if (!text || text.trim().length === 0) {
    return { error: "Todo text cannot be empty" };
  }
  if (text.length > 200) {
    return { error: "Todo text must be 200 characters or less" };
  }

  try {
    await fetch(`${process.env.API_URL}/todos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.trim(), completed: false }),
    });

    revalidatePath("/todos");
    return { success: true };
  } catch {
    return { error: "Failed to add todo. Please try again." };
  }
}

export async function toggleTodo(id: string): Promise<void> {
  await fetch(`${process.env.API_URL}/todos/${id}/toggle`, {
    method: "PATCH",
  });
  revalidatePath("/todos");
}

export async function deleteTodo(id: string): Promise<void> {
  await fetch(`${process.env.API_URL}/todos/${id}`, {
    method: "DELETE",
  });
  revalidatePath("/todos");
}

export async function reorderTodos(orderedIds: string[]): Promise<void> {
  await fetch(`${process.env.API_URL}/todos/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: orderedIds }),
  });
  revalidatePath("/todos");
}

// app/todos/page.tsx - Server component
import { Suspense } from "react";

async function getTodos(): Promise<Todo[]> {
  const res = await fetch(`${process.env.API_URL}/todos`, {
    next: { tags: ["todos"], revalidate: 0 },
  });
  return res.json();
}

export default async function TodosPage() {
  const todos = await getTodos();

  return (
    <div className="max-w-lg mx-auto py-8">
      <h1 className="text-2xl font-bold mb-6">Todos</h1>

      {/* Add form - works without JavaScript (progressive enhancement) */}
      <AddTodoForm />

      {/* Todo list with optimistic updates */}
      <TodoList initialTodos={todos} />

      {/* Stats */}
      <div className="mt-4 text-sm text-gray-500">
        {todos.filter((t) => !t.completed).length} remaining |{" "}
        {todos.filter((t) => t.completed).length} completed
      </div>
    </div>
  );
}

// app/todos/add-todo-form.tsx
// "use client"
// import { useFormState, useFormStatus } from "react-dom";

function AddTodoForm() {
  // const [state, formAction] = useFormState(addTodo, null);

  return (
    <form className="flex gap-2 mb-6">
      <input
        name="text"
        type="text"
        placeholder="What needs to be done?"
        className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
        required
        maxLength={200}
        autoComplete="off"
      />
      <SubmitButton />
      {/* {state?.error && (
        <p className="text-red-500 text-sm mt-1" role="alert">{state.error}</p>
      )} */}
    </form>
  );
}

function SubmitButton() {
  // const { pending } = useFormStatus();
  const pending = false;

  return (
    <button
      type="submit"
      disabled={pending}
      className={`px-4 py-2 rounded-lg text-white font-medium ${
        pending ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
      }`}
    >
      {pending ? "Adding..." : "Add"}
    </button>
  );
}

// app/todos/todo-list.tsx
// "use client"
// import { useOptimistic, useTransition } from "react";

interface TodoListProps {
  initialTodos: Todo[];
}

function TodoList({ initialTodos }: TodoListProps) {
  // Optimistic updates for instant UI feedback
  // const [optimisticTodos, setOptimisticTodos] = useOptimistic(
  //   initialTodos,
  //   (state: Todo[], action: { type: string; id?: string; todo?: Todo }) => {
  //     switch (action.type) {
  //       case "toggle":
  //         return state.map((t) =>
  //           t.id === action.id ? { ...t, completed: !t.completed } : t
  //         );
  //       case "delete":
  //         return state.filter((t) => t.id !== action.id);
  //       case "add":
  //         return action.todo ? [...state, action.todo] : state;
  //       default:
  //         return state;
  //     }
  //   }
  // );

  // const [isPending, startTransition] = useTransition();

  // async function handleToggle(id: string) {
  //   setOptimisticTodos({ type: "toggle", id });
  //   await toggleTodo(id);
  // }

  // async function handleDelete(id: string) {
  //   setOptimisticTodos({ type: "delete", id });
  //   await deleteTodo(id);
  // }

  return (
    <ul className="space-y-2">
      {initialTodos.map((todo) => (
        <li
          key={todo.id}
          className="flex items-center gap-3 p-3 bg-white rounded-lg shadow-sm group"
        >
          <button
            // onClick={() => handleToggle(todo.id)}
            className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
              todo.completed
                ? "bg-green-500 border-green-500"
                : "border-gray-300 hover:border-green-400"
            }`}
            aria-label={`Mark "${todo.text}" as ${todo.completed ? "incomplete" : "complete"}`}
          >
            {todo.completed && (
              <span className="text-white text-xs">ok</span>
            )}
          </button>

          <span
            className={`flex-1 ${
              todo.completed ? "line-through text-gray-400" : "text-gray-800"
            }`}
          >
            {todo.text}
          </span>

          <button
            // onClick={() => handleDelete(todo.id)}
            className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all"
            aria-label={`Delete "${todo.text}"`}
          >
            x
          </button>
        </li>
      ))}
    </ul>
  );
}

export { AddTodoForm, TodoList };
'''),

    ("react/nextjs_caching", r'''<think>
Next.js has a complex caching system with multiple layers. I need to explain and demonstrate the different caching behaviors: request memoization, data cache, full route cache, and router cache. Showing how to control each layer is critical for production apps.
</think>

Build Next.js caching strategy patterns showing request memoization, data cache with tags, ISR revalidation, cache control headers, and a cache warming utility.''', r'''<think>
I will demonstrate each caching layer in Next.js with practical examples, showing how to control caching behavior at different levels and implement cache warming for production deployments.
</think>

// lib/cache.ts - Cache utilities for Next.js App Router
import { unstable_cache } from "next/cache";

// 1. Request Memoization - same request in a render pass is deduped
// These functions can be called multiple times across components in the same
// request and only one actual fetch will be made

async function getUser(id: string) {
  // This fetch is automatically deduped within the same request
  const res = await fetch(`${process.env.API_URL}/users/${id}`);
  return res.json();
}

async function getTeam(teamId: string) {
  const res = await fetch(`${process.env.API_URL}/teams/${teamId}`);
  return res.json();
}

// Used in multiple components - only fetched once per request
// Component A calls getUser("1") -> fetches
// Component B calls getUser("1") -> returns cached result from same request

// 2. Data Cache with Tags - fine-grained cache control
async function getProducts(category?: string) {
  const params = category ? `?category=${category}` : "";
  const res = await fetch(`${process.env.API_URL}/products${params}`, {
    next: {
      revalidate: 3600,  // Revalidate every hour (ISR)
      tags: [
        "products",                              // Revalidate all products
        category ? `products-${category}` : "",   // Revalidate by category
      ].filter(Boolean),
    },
  });
  return res.json();
}

async function getProduct(id: string) {
  const res = await fetch(`${process.env.API_URL}/products/${id}`, {
    next: {
      revalidate: 300,
      tags: [`product-${id}`, "products"],
    },
  });
  return res.json();
}

// 3. Dynamic data - opt out of caching
async function getCartItems(userId: string) {
  const res = await fetch(`${process.env.API_URL}/cart/${userId}`, {
    cache: "no-store",  // Always fresh - no caching
  });
  return res.json();
}

async function getNotifications(userId: string) {
  const res = await fetch(`${process.env.API_URL}/notifications/${userId}`, {
    next: { revalidate: 0 },  // Equivalent to no-store
  });
  return res.json();
}

// 4. unstable_cache for non-fetch operations (database queries, computations)
const getCachedAnalytics = unstable_cache(
  async (dateRange: string) => {
    // This could be a database query or expensive computation
    const res = await fetch(`${process.env.API_URL}/analytics?range=${dateRange}`);
    return res.json();
  },
  ["analytics"],                    // Cache key prefix
  {
    revalidate: 3600,               // 1 hour
    tags: ["analytics"],            // On-demand revalidation tag
  }
);

const getCachedUserProfile = unstable_cache(
  async (userId: string) => {
    const res = await fetch(`${process.env.API_URL}/users/${userId}/profile`);
    return res.json();
  },
  ["user-profile"],
  {
    revalidate: 300,
    tags: ["user-profiles"],
  }
);

// 5. Static generation with generateStaticParams
// app/blog/[slug]/page.tsx
export async function generateStaticParams() {
  const posts = await fetch(`${process.env.API_URL}/posts?status=published`).then(
    (r) => r.json()
  );
  return posts.map((post: any) => ({ slug: post.slug }));
}

// ISR: page is statically generated but revalidated on a schedule
async function getBlogPost(slug: string) {
  const res = await fetch(`${process.env.API_URL}/posts/by-slug/${slug}`, {
    next: {
      revalidate: 60,                 // Check for updates every 60 seconds
      tags: [`post-${slug}`, "posts"],
    },
  });
  if (!res.ok) return null;
  return res.json();
}

// 6. Route segment config for full route cache control
// Add these exports to page.tsx or layout.tsx:
export const dynamic = "auto";           // Default: auto-detect
// export const dynamic = "force-dynamic";  // Always dynamic (SSR)
// export const dynamic = "force-static";   // Always static (SSG)
// export const dynamic = "error";          // Error if dynamic features used

export const revalidate = 3600;          // ISR: revalidate every hour
// export const revalidate = 0;           // No caching
// export const revalidate = false;       // Cache indefinitely

export const fetchCache = "default-cache"; // Default fetch behavior
// export const fetchCache = "only-cache";  // All fetches must be cached
// export const fetchCache = "force-no-store";  // No caching for any fetch

// 7. Cache warming utility for deployment
// scripts/warm-cache.ts
interface WarmConfig {
  baseUrl: string;
  paths: string[];
  concurrency: number;
}

async function warmCache(config: WarmConfig): Promise<void> {
  const { baseUrl, paths, concurrency } = config;
  const results: Array<{ path: string; status: number; time: number }> = [];

  // Process in batches
  for (let i = 0; i < paths.length; i += concurrency) {
    const batch = paths.slice(i, i + concurrency);
    const batchResults = await Promise.allSettled(
      batch.map(async (path) => {
        const start = Date.now();
        const res = await fetch(`${baseUrl}${path}`, {
          headers: { "X-Cache-Warm": "true" },
        });
        return {
          path,
          status: res.status,
          time: Date.now() - start,
        };
      })
    );

    for (const result of batchResults) {
      if (result.status === "fulfilled") {
        results.push(result.value);
        console.log(
          `[WARM] ${result.value.path} - ${result.value.status} (${result.value.time}ms)`
        );
      }
    }
  }

  const successful = results.filter((r) => r.status === 200).length;
  const avgTime = results.reduce((sum, r) => sum + r.time, 0) / results.length;
  console.log(`\nWarmed ${successful}/${paths.length} pages (avg ${avgTime.toFixed(0)}ms)`);
}

// 8. On-demand revalidation API route
// app/api/revalidate/route.ts
import { NextRequest, NextResponse } from "next/server";
import { revalidateTag, revalidatePath } from "next/cache";

export async function POST(request: NextRequest) {
  const secret = request.headers.get("x-revalidation-secret");
  if (secret !== process.env.REVALIDATION_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();

  const revalidated: string[] = [];

  // Revalidate specific tags
  if (body.tags && Array.isArray(body.tags)) {
    for (const tag of body.tags) {
      revalidateTag(tag);
      revalidated.push(`tag:${tag}`);
    }
  }

  // Revalidate specific paths
  if (body.paths && Array.isArray(body.paths)) {
    for (const path of body.paths) {
      revalidatePath(path);
      revalidated.push(`path:${path}`);
    }
  }

  return NextResponse.json({
    revalidated,
    now: Date.now(),
  });
}

// Usage: Webhook handler for CMS updates
// POST /api/revalidate
// Headers: { "x-revalidation-secret": "..." }
// Body: { "tags": ["products", "product-123"], "paths": ["/shop", "/shop/widget"] }

export {
  getProducts,
  getProduct,
  getCartItems,
  getCachedAnalytics,
  getCachedUserProfile,
  getBlogPost,
  warmCache,
};
'''),

    ("react/nextjs_streaming_ssr", r'''Build Next.js streaming SSR patterns with React Suspense for a product page that progressively loads critical content, reviews, and recommendations with proper SEO metadata.''', r'''// app/products/[id]/page.tsx - Streaming SSR product page
import { Suspense } from "react";
import type { Metadata } from "next";

interface Product {
  id: string;
  name: string;
  description: string;
  price: number;
  images: string[];
  category: string;
  rating: number;
  reviewCount: number;
  inStock: boolean;
  specifications: Record<string, string>;
}

interface Review {
  id: string;
  author: string;
  rating: number;
  title: string;
  content: string;
  date: string;
  helpful: number;
}

interface ProductSuggestion {
  id: string;
  name: string;
  price: number;
  image: string;
  rating: number;
}

// Critical data - blocks initial render for SEO
async function getProduct(id: string): Promise<Product | null> {
  const res = await fetch(`${process.env.API_URL}/products/${id}`, {
    next: { revalidate: 300, tags: [`product-${id}`] },
  });
  if (!res.ok) return null;
  return res.json();
}

// Non-critical data - streamed in later
async function getReviews(productId: string): Promise<Review[]> {
  const res = await fetch(`${process.env.API_URL}/products/${productId}/reviews`, {
    next: { revalidate: 60, tags: [`reviews-${productId}`] },
  });
  return res.json();
}

async function getRecommendations(productId: string): Promise<ProductSuggestion[]> {
  const res = await fetch(
    `${process.env.API_URL}/products/${productId}/recommendations`,
    { next: { revalidate: 3600 } }
  );
  return res.json();
}

async function getInventory(productId: string): Promise<{ available: number; warehouse: string }> {
  const res = await fetch(`${process.env.API_URL}/inventory/${productId}`, {
    cache: "no-store", // Always check real-time inventory
  });
  return res.json();
}

// Dynamic metadata for SEO
export async function generateMetadata({
  params,
}: {
  params: { id: string };
}): Promise<Metadata> {
  const product = await getProduct(params.id);
  if (!product) {
    return { title: "Product Not Found" };
  }

  return {
    title: product.name,
    description: product.description.slice(0, 160),
    openGraph: {
      title: product.name,
      description: product.description.slice(0, 160),
      images: product.images.map((img) => ({ url: img })),
      type: "website",
    },
    other: {
      "product:price:amount": String(product.price),
      "product:price:currency": "USD",
    },
  };
}

// JSON-LD structured data for SEO
function ProductJsonLd({ product }: { product: Product }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.description,
    image: product.images,
    offers: {
      "@type": "Offer",
      price: product.price,
      priceCurrency: "USD",
      availability: product.inStock
        ? "https://schema.org/InStock"
        : "https://schema.org/OutOfStock",
    },
    aggregateRating: {
      "@type": "AggregateRating",
      ratingValue: product.rating,
      reviewCount: product.reviewCount,
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
  );
}

// Page component with streaming
import { notFound } from "next/navigation";

export default async function ProductPage({
  params,
}: {
  params: { id: string };
}) {
  const product = await getProduct(params.id);
  if (!product) notFound();

  return (
    <>
      <ProductJsonLd product={product} />

      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Critical: Product hero - rendered immediately in initial HTML */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
          {/* Image gallery */}
          <div className="space-y-4">
            <div className="aspect-square rounded-lg overflow-hidden bg-gray-100">
              <img
                src={product.images[0]}
                alt={product.name}
                className="w-full h-full object-cover"
                loading="eager"
              />
            </div>
            <div className="grid grid-cols-4 gap-2">
              {product.images.slice(1, 5).map((img, i) => (
                <div key={i} className="aspect-square rounded overflow-hidden bg-gray-100">
                  <img src={img} alt="" className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
          </div>

          {/* Product info */}
          <div>
            <nav className="text-sm text-gray-500 mb-2">
              <a href="/shop" className="hover:text-gray-700">Shop</a>
              {" / "}
              <a href={`/shop/${product.category}`} className="hover:text-gray-700 capitalize">
                {product.category}
              </a>
            </nav>
            <h1 className="text-3xl font-bold mb-2">{product.name}</h1>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-yellow-500">
                {"*".repeat(Math.round(product.rating))}
              </span>
              <span className="text-sm text-gray-500">
                ({product.reviewCount} reviews)
              </span>
            </div>
            <p className="text-3xl font-bold mb-4">${product.price}</p>
            <p className="text-gray-600 mb-6">{product.description}</p>

            {/* Real-time inventory check - streams independently */}
            <Suspense fallback={<div className="h-8 bg-gray-100 rounded animate-pulse" />}>
              <InventoryStatus productId={params.id} />
            </Suspense>

            <button
              className="w-full mt-4 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              disabled={!product.inStock}
            >
              {product.inStock ? "Add to Cart" : "Out of Stock"}
            </button>
          </div>
        </div>

        {/* Specifications */}
        <section className="mb-12">
          <h2 className="text-xl font-bold mb-4">Specifications</h2>
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
            {Object.entries(product.specifications).map(([key, value]) => (
              <div key={key} className="flex py-2 border-b">
                <dt className="w-1/3 text-gray-500">{key}</dt>
                <dd className="w-2/3 font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* Reviews - streamed in after critical content */}
        <Suspense fallback={<ReviewsSkeleton />}>
          <ReviewsSection productId={params.id} />
        </Suspense>

        {/* Recommendations - lowest priority, streamed last */}
        <Suspense fallback={<RecommendationsSkeleton />}>
          <RecommendationsSection productId={params.id} />
        </Suspense>
      </div>
    </>
  );
}

// Async components that stream in
async function InventoryStatus({ productId }: { productId: string }) {
  const inventory = await getInventory(productId);

  return (
    <div className={`text-sm ${inventory.available > 0 ? "text-green-600" : "text-red-600"}`}>
      {inventory.available > 0
        ? `In stock (${inventory.available} available)`
        : "Currently out of stock"}
    </div>
  );
}

async function ReviewsSection({ productId }: { productId: string }) {
  const reviews = await getReviews(productId);

  return (
    <section className="mb-12">
      <h2 className="text-xl font-bold mb-6">Customer Reviews ({reviews.length})</h2>
      <div className="space-y-6">
        {reviews.slice(0, 10).map((review) => (
          <div key={review.id} className="border-b pb-4">
            <div className="flex justify-between mb-2">
              <div>
                <span className="text-yellow-500">
                  {"*".repeat(review.rating)}
                </span>
                <span className="font-medium ml-2">{review.title}</span>
              </div>
              <time className="text-sm text-gray-400">
                {new Date(review.date).toLocaleDateString()}
              </time>
            </div>
            <p className="text-gray-600 text-sm mb-1">By {review.author}</p>
            <p className="text-gray-700">{review.content}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

async function RecommendationsSection({ productId }: { productId: string }) {
  const recommendations = await getRecommendations(productId);

  return (
    <section>
      <h2 className="text-xl font-bold mb-6">You May Also Like</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {recommendations.map((product) => (
          <a key={product.id} href={`/products/${product.id}`} className="group">
            <div className="aspect-square rounded-lg overflow-hidden bg-gray-100 mb-2">
              <img
                src={product.image}
                alt={product.name}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                loading="lazy"
              />
            </div>
            <p className="font-medium text-sm truncate">{product.name}</p>
            <p className="text-sm text-gray-500">${product.price}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

function ReviewsSkeleton() {
  return (
    <section className="mb-12 animate-pulse">
      <div className="h-7 bg-gray-200 rounded w-48 mb-6" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="border-b pb-4 mb-4">
          <div className="h-5 bg-gray-200 rounded w-64 mb-2" />
          <div className="h-4 bg-gray-100 rounded w-full mb-1" />
          <div className="h-4 bg-gray-100 rounded w-3/4" />
        </div>
      ))}
    </section>
  );
}

function RecommendationsSkeleton() {
  return (
    <section className="animate-pulse">
      <div className="h-7 bg-gray-200 rounded w-48 mb-6" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i}>
            <div className="aspect-square bg-gray-200 rounded-lg mb-2" />
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-1" />
            <div className="h-4 bg-gray-200 rounded w-1/4" />
          </div>
        ))}
      </div>
    </section>
  );
}
'''),

    ("react/nextjs_isr", r'''Build ISR (Incremental Static Regeneration) patterns in Next.js for a blog platform with on-demand revalidation, fallback pages, and cache management strategies.''', r'''// app/blog/[slug]/page.tsx - ISR blog post page
import { notFound } from "next/navigation";
import type { Metadata } from "next";

interface BlogPost {
  id: string;
  slug: string;
  title: string;
  content: string;
  excerpt: string;
  author: { name: string; avatar: string; bio: string };
  publishedAt: string;
  updatedAt: string;
  tags: string[];
  coverImage: string;
  readingTime: number;
}

// ISR: revalidate every 5 minutes
export const revalidate = 300;

// Generate static pages at build time for published posts
export async function generateStaticParams() {
  const res = await fetch(`${process.env.API_URL}/posts?status=published&limit=100`);
  const posts: BlogPost[] = await res.json();

  // Only pre-render the most recent 100 posts
  // Others will be generated on-demand
  return posts.map((post) => ({
    slug: post.slug,
  }));
}

// Fetch with cache tags for targeted revalidation
async function getPost(slug: string): Promise<BlogPost | null> {
  const res = await fetch(`${process.env.API_URL}/posts/by-slug/${slug}`, {
    next: {
      revalidate: 300,
      tags: [`post-${slug}`, "blog-posts"],
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch post");
  return res.json();
}

async function getRelatedPosts(tags: string[], excludeId: string): Promise<BlogPost[]> {
  const tagParam = tags.slice(0, 3).join(",");
  const res = await fetch(
    `${process.env.API_URL}/posts?tags=${tagParam}&exclude=${excludeId}&limit=3`,
    { next: { revalidate: 3600, tags: ["blog-posts"] } }
  );
  return res.json();
}

// Dynamic metadata
export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const post = await getPost(params.slug);
  if (!post) return { title: "Post Not Found" };

  return {
    title: post.title,
    description: post.excerpt,
    authors: [{ name: post.author.name }],
    openGraph: {
      title: post.title,
      description: post.excerpt,
      type: "article",
      publishedTime: post.publishedAt,
      modifiedTime: post.updatedAt,
      authors: [post.author.name],
      images: [{ url: post.coverImage, width: 1200, height: 630 }],
      tags: post.tags,
    },
    twitter: {
      card: "summary_large_image",
      title: post.title,
      description: post.excerpt,
      images: [post.coverImage],
    },
    alternates: {
      canonical: `/blog/${params.slug}`,
    },
  };
}

export default async function BlogPostPage({
  params,
}: {
  params: { slug: string };
}) {
  const post = await getPost(params.slug);
  if (!post) notFound();

  // Structured data for SEO
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description: post.excerpt,
    image: post.coverImage,
    datePublished: post.publishedAt,
    dateModified: post.updatedAt,
    author: {
      "@type": "Person",
      name: post.author.name,
    },
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <article className="max-w-3xl mx-auto px-4 py-8">
        {/* Cover image */}
        <img
          src={post.coverImage}
          alt={post.title}
          className="w-full h-64 md:h-96 object-cover rounded-xl mb-8"
        />

        {/* Header */}
        <header className="mb-8">
          <div className="flex gap-2 mb-4">
            {post.tags.map((tag) => (
              <a
                key={tag}
                href={`/blog/tag/${tag}`}
                className="px-3 py-1 bg-blue-50 text-blue-600 rounded-full text-sm hover:bg-blue-100"
              >
                {tag}
              </a>
            ))}
          </div>
          <h1 className="text-4xl font-bold mb-4">{post.title}</h1>
          <div className="flex items-center gap-4">
            <img
              src={post.author.avatar}
              alt={post.author.name}
              className="w-12 h-12 rounded-full"
            />
            <div>
              <p className="font-medium">{post.author.name}</p>
              <div className="text-sm text-gray-500">
                <time dateTime={post.publishedAt}>
                  {new Date(post.publishedAt).toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </time>
                <span className="mx-2">|</span>
                <span>{post.readingTime} min read</span>
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <div
          className="prose prose-lg max-w-none"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />

        {/* Author bio */}
        <div className="mt-12 p-6 bg-gray-50 rounded-xl flex gap-4">
          <img
            src={post.author.avatar}
            alt={post.author.name}
            className="w-16 h-16 rounded-full"
          />
          <div>
            <p className="font-semibold">{post.author.name}</p>
            <p className="text-gray-600 text-sm mt-1">{post.author.bio}</p>
          </div>
        </div>
      </article>

      {/* Related posts */}
      <RelatedPosts tags={post.tags} excludeId={post.id} />
    </>
  );
}

async function RelatedPosts({ tags, excludeId }: { tags: string[]; excludeId: string }) {
  const related = await getRelatedPosts(tags, excludeId);
  if (related.length === 0) return null;

  return (
    <section className="max-w-5xl mx-auto px-4 py-12">
      <h2 className="text-2xl font-bold mb-6">Related Posts</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {related.map((post) => (
          <a key={post.id} href={`/blog/${post.slug}`} className="group">
            <img
              src={post.coverImage}
              alt={post.title}
              className="w-full h-48 object-cover rounded-lg mb-3 group-hover:opacity-90 transition-opacity"
              loading="lazy"
            />
            <h3 className="font-semibold group-hover:text-blue-600 transition-colors">
              {post.title}
            </h3>
            <p className="text-sm text-gray-500 mt-1 line-clamp-2">{post.excerpt}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

// app/blog/[slug]/not-found.tsx
export function BlogNotFound() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-16 text-center">
      <h1 className="text-3xl font-bold mb-4">Post Not Found</h1>
      <p className="text-gray-500 mb-6">
        The blog post you are looking for may have been removed or does not exist.
      </p>
      <a href="/blog" className="text-blue-600 hover:underline">
        Browse all posts
      </a>
    </div>
  );
}

// app/blog/page.tsx - Blog index with ISR
export async function BlogIndex({
  searchParams,
}: {
  searchParams: { page?: string; tag?: string };
}) {
  const page = parseInt(searchParams.page || "1");
  const tag = searchParams.tag;

  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("limit", "12");
  if (tag) params.set("tag", tag);

  const res = await fetch(`${process.env.API_URL}/posts?${params}`, {
    next: { revalidate: 60, tags: ["blog-posts"] },
  });
  const { posts, total, totalPages } = await res.json();

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">
        {tag ? `Posts tagged "${tag}"` : "Blog"}
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {posts.map((post: BlogPost) => (
          <a key={post.id} href={`/blog/${post.slug}`} className="group">
            <img
              src={post.coverImage}
              alt={post.title}
              className="w-full h-48 object-cover rounded-lg mb-3"
              loading="lazy"
            />
            <h2 className="font-semibold text-lg group-hover:text-blue-600">
              {post.title}
            </h2>
            <p className="text-sm text-gray-500 mt-1">{post.excerpt}</p>
          </a>
        ))}
      </div>
      {totalPages > 1 && (
        <nav className="mt-8 flex justify-center gap-2" aria-label="Pagination">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <a
              key={p}
              href={`/blog?page=${p}${tag ? `&tag=${tag}` : ""}`}
              className={`px-3 py-1 rounded ${
                p === page ? "bg-blue-600 text-white" : "bg-gray-100 hover:bg-gray-200"
              }`}
            >
              {p}
            </a>
          ))}
        </nav>
      )}
    </div>
  );
}
'''),

    ("react/nextjs_data_mutations", r'''Build data mutation patterns in Next.js with server actions including form submissions, API calls with revalidation, optimistic UI updates, and error recovery.''', r'''// app/projects/[id]/settings/actions.ts
// "use server"

import { revalidatePath, revalidateTag } from "next/cache";
import { redirect } from "next/navigation";

// Types
interface ProjectSettings {
  name: string;
  description: string;
  visibility: "public" | "private" | "team";
  defaultBranch: string;
  features: {
    issues: boolean;
    wiki: boolean;
    discussions: boolean;
  };
}

// Action: Update project settings
export async function updateProjectSettings(
  projectId: string,
  prevState: { error?: string; success?: boolean } | null,
  formData: FormData
): Promise<{ error?: string; success?: boolean }> {
  const settings: Partial<ProjectSettings> = {
    name: formData.get("name") as string,
    description: formData.get("description") as string,
    visibility: formData.get("visibility") as ProjectSettings["visibility"],
    defaultBranch: formData.get("defaultBranch") as string,
    features: {
      issues: formData.get("issues") === "on",
      wiki: formData.get("wiki") === "on",
      discussions: formData.get("discussions") === "on",
    },
  };

  // Validation
  if (!settings.name || settings.name.length < 2) {
    return { error: "Project name must be at least 2 characters" };
  }

  if (settings.name.length > 100) {
    return { error: "Project name must be 100 characters or less" };
  }

  const nameRegex = /^[a-zA-Z0-9-_. ]+$/;
  if (!nameRegex.test(settings.name)) {
    return { error: "Project name contains invalid characters" };
  }

  try {
    const res = await fetch(`${process.env.API_URL}/projects/${projectId}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });

    if (!res.ok) {
      const data = await res.json();
      return { error: data.message || "Failed to update settings" };
    }

    // Targeted revalidation
    revalidateTag(`project-${projectId}`);
    revalidatePath(`/projects/${projectId}`);
    revalidatePath(`/projects/${projectId}/settings`);

    return { success: true };
  } catch (error) {
    return { error: "Network error. Please try again." };
  }
}

// Action: Transfer project ownership
export async function transferProject(
  projectId: string,
  formData: FormData
): Promise<{ error?: string }> {
  const newOwner = formData.get("newOwner") as string;
  const confirmation = formData.get("confirmation") as string;

  if (!newOwner) {
    return { error: "New owner is required" };
  }

  // Require typing project name as confirmation
  const projectName = formData.get("projectName") as string;
  if (confirmation !== projectName) {
    return { error: "Please type the project name to confirm" };
  }

  try {
    const res = await fetch(`${process.env.API_URL}/projects/${projectId}/transfer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ newOwner }),
    });

    if (!res.ok) {
      const data = await res.json();
      return { error: data.message || "Transfer failed" };
    }

    revalidateTag("projects");
    redirect("/projects");
  } catch (error) {
    if ((error as any)?.digest?.startsWith("NEXT_REDIRECT")) throw error;
    return { error: "Transfer failed. Please try again." };
  }
  return {};
}

// Action: Delete project
export async function deleteProject(
  projectId: string,
  formData: FormData
): Promise<{ error?: string }> {
  const confirmation = formData.get("confirmation") as string;

  if (confirmation !== "DELETE") {
    return { error: 'Please type "DELETE" to confirm' };
  }

  try {
    const res = await fetch(`${process.env.API_URL}/projects/${projectId}`, {
      method: "DELETE",
    });

    if (!res.ok) {
      return { error: "Failed to delete project" };
    }

    revalidateTag("projects");
    revalidatePath("/projects");
    redirect("/projects");
  } catch (error) {
    if ((error as any)?.digest?.startsWith("NEXT_REDIRECT")) throw error;
    return { error: "Delete failed" };
  }
  return {};
}

// Action: Add team member with role
export async function addTeamMember(
  projectId: string,
  prevState: any,
  formData: FormData
): Promise<{ error?: string; success?: boolean }> {
  const email = formData.get("email") as string;
  const role = formData.get("role") as string;

  if (!email || !email.includes("@")) {
    return { error: "Valid email is required" };
  }

  try {
    const res = await fetch(`${process.env.API_URL}/projects/${projectId}/members`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, role }),
    });

    if (res.status === 404) {
      return { error: "User not found with that email" };
    }
    if (res.status === 409) {
      return { error: "User is already a team member" };
    }
    if (!res.ok) {
      return { error: "Failed to add team member" };
    }

    revalidateTag(`project-${projectId}-members`);
    revalidatePath(`/projects/${projectId}/settings`);

    return { success: true };
  } catch {
    return { error: "Network error" };
  }
}

// Action: Inline mutation (no form, called from client component)
export async function toggleProjectFeature(
  projectId: string,
  feature: string,
  enabled: boolean
): Promise<{ error?: string; success?: boolean }> {
  try {
    const res = await fetch(
      `${process.env.API_URL}/projects/${projectId}/features/${feature}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      }
    );

    if (!res.ok) {
      return { error: `Failed to ${enabled ? "enable" : "disable"} ${feature}` };
    }

    revalidateTag(`project-${projectId}`);
    return { success: true };
  } catch {
    return { error: "Network error" };
  }
}

// app/projects/[id]/settings/page.tsx
export default async function ProjectSettingsPage({
  params,
}: {
  params: { id: string };
}) {
  const res = await fetch(`${process.env.API_URL}/projects/${params.id}`, {
    next: { tags: [`project-${params.id}`] },
  });
  const project = await res.json();

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-8">Project Settings</h1>

      {/* General Settings Form */}
      <section className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">General</h2>
        <form className="space-y-4">
          <input type="hidden" name="projectId" value={params.id} />
          <div>
            <label className="block text-sm font-medium mb-1">Project Name</label>
            <input
              name="name"
              defaultValue={project.name}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              name="description"
              defaultValue={project.description}
              rows={3}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Visibility</label>
            <select
              name="visibility"
              defaultValue={project.visibility}
              className="w-full px-3 py-2 border rounded"
            >
              <option value="public">Public</option>
              <option value="private">Private</option>
              <option value="team">Team only</option>
            </select>
          </div>
          <button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
            Save Changes
          </button>
        </form>
      </section>

      {/* Danger Zone */}
      <section className="bg-white rounded-lg shadow p-6 border-2 border-red-100">
        <h2 className="text-lg font-semibold text-red-600 mb-4">Danger Zone</h2>
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <p className="font-medium">Transfer Project</p>
              <p className="text-sm text-gray-500">Transfer to another user</p>
            </div>
            <button className="px-3 py-1 border border-red-300 text-red-600 rounded hover:bg-red-50">
              Transfer
            </button>
          </div>
          <div className="flex justify-between items-center">
            <div>
              <p className="font-medium">Delete Project</p>
              <p className="text-sm text-gray-500">Permanently delete this project</p>
            </div>
            <button className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700">
              Delete
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
'''),
]
