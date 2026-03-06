"""Next.js App Router — server components, parallel routes, server actions, middleware, ISR."""

PAIRS = [
    (
        "typescript/production",
        r'''Show how to use Next.js App Router server components with streaming and Suspense. Include data fetching patterns, loading states, and how to combine server and client components.''',
        r'''# Next.js Server Components with Streaming

Server Components render on the server and stream HTML to the client progressively. Combined with Suspense boundaries, each section of the page loads independently — fast initial paint with granular loading states.

## Basic Server Component with Data Fetching

```typescript
// app/dashboard/page.tsx — this is a Server Component by default
import { Suspense } from "react";
import { RevenueChart } from "./revenue-chart";
import { RecentOrders } from "./recent-orders";
import { StatsCards } from "./stats-cards";
import { DashboardSkeleton, ChartSkeleton, TableSkeleton, CardsSkeleton } from "./skeletons";

// Server Components can be async — no useEffect needed
export default async function DashboardPage() {
  // This fetch runs on the server, never hits the client bundle
  const user = await getUser();

  return (
    <main>
      <h1>Welcome back, {user.name}</h1>

      {/* Each Suspense boundary streams independently */}
      <Suspense fallback={<CardsSkeleton />}>
        <StatsCards />
      </Suspense>

      <div className="grid grid-cols-2 gap-6">
        <Suspense fallback={<ChartSkeleton />}>
          <RevenueChart />
        </Suspense>

        <Suspense fallback={<TableSkeleton />}>
          <RecentOrders />
        </Suspense>
      </div>
    </main>
  );
}
```

## Async Server Components

```typescript
// app/dashboard/stats-cards.tsx
import { db } from "@/lib/db";

interface Stats {
  totalRevenue: number;
  activeUsers: number;
  conversionRate: number;
  avgOrderValue: number;
}

// This component fetches its own data — runs entirely on the server
export async function StatsCards() {
  const stats = await getStats(); // Direct DB query, no API route needed

  return (
    <div className="grid grid-cols-4 gap-4">
      <StatCard label="Revenue" value={formatCurrency(stats.totalRevenue)} />
      <StatCard label="Active Users" value={stats.activeUsers.toLocaleString()} />
      <StatCard label="Conversion" value={`${stats.conversionRate}%`} />
      <StatCard label="Avg Order" value={formatCurrency(stats.avgOrderValue)} />
    </div>
  );
}

async function getStats(): Promise<Stats> {
  // Direct database access — this code NEVER ships to the client
  const [revenue, users, orders] = await Promise.all([
    db.query<{ total: number }>`SELECT SUM(amount) as total FROM orders WHERE created_at > NOW() - INTERVAL '30 days'`,
    db.query<{ count: number }>`SELECT COUNT(DISTINCT user_id) as count FROM sessions WHERE last_seen > NOW() - INTERVAL '7 days'`,
    db.query<{ count: number; total: number }>`SELECT COUNT(*) as count, SUM(amount) as total FROM orders WHERE created_at > NOW() - INTERVAL '30 days'`,
  ]);

  return {
    totalRevenue: revenue.rows[0].total,
    activeUsers: users.rows[0].count,
    conversionRate: Number(((orders.rows[0].count / users.rows[0].count) * 100).toFixed(1)),
    avgOrderValue: orders.rows[0].total / orders.rows[0].count,
  };
}
```

## Mixing Server and Client Components

```typescript
// app/dashboard/revenue-chart.tsx — Server Component fetches data
import { ChartClient } from "./chart-client";

export async function RevenueChart() {
  // Heavy data processing on the server
  const rawData = await db.query`
    SELECT DATE_TRUNC('day', created_at) as day, SUM(amount) as revenue
    FROM orders
    WHERE created_at > NOW() - INTERVAL '30 days'
    GROUP BY day ORDER BY day
  `;

  const chartData = rawData.rows.map((row) => ({
    date: row.day.toISOString().split("T")[0],
    revenue: Number(row.revenue),
  }));

  // Pass serializable data to the Client Component
  return <ChartClient data={chartData} />;
}

// app/dashboard/chart-client.tsx — Client Component for interactivity
"use client";

import { useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface ChartData {
  date: string;
  revenue: number;
}

export function ChartClient({ data }: { data: ChartData[] }) {
  const [range, setRange] = useState<"7d" | "14d" | "30d">("30d");

  const filtered = data.slice(
    range === "7d" ? -7 : range === "14d" ? -14 : 0
  );

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {(["7d", "14d", "30d"] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={range === r ? "btn-active" : "btn-default"}
          >
            {r}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={filtered}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip formatter={(v: number) => `$${v.toLocaleString()}`} />
          <Area type="monotone" dataKey="revenue" fill="#3b82f6" stroke="#2563eb" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

## Error Boundaries with Streaming

```typescript
// app/dashboard/error.tsx — catches errors in this route segment
"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div role="alert" className="error-panel">
      <h2>Something went wrong loading the dashboard</h2>
      <p>{error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}

// app/dashboard/loading.tsx — shown while the page-level Suspense resolves
export default function DashboardLoading() {
  return <DashboardSkeleton />;
}
```

## Common Pitfalls

1. **Importing client-only code in Server Components**: Using `useState`, `useEffect`, or browser APIs in a Server Component causes a build error. Extract interactive parts into `"use client"` files.
2. **Passing non-serializable props**: Server Components pass props to Client Components via serialization. Functions, Dates, Maps, and class instances cannot be passed. Convert to plain objects.
3. **Waterfall fetches**: If `RecentOrders` depends on `StatsCards` data, they serialize. Fetch data in parallel at the page level and pass down, or use independent Suspense boundaries so they stream independently.
4. **Over-clientizing**: Adding `"use client"` to a parent makes all children client components. Push `"use client"` to the leaves — keep data-fetching wrappers as Server Components.
''',
    ),
    (
        "typescript/production",
        r'''Explain Next.js App Router parallel routes and intercepting routes. Show production patterns for modals, split layouts, and conditional rendering based on auth state.''',
        r'''# Parallel Routes and Intercepting Routes

Parallel routes render multiple page segments simultaneously in the same layout. Intercepting routes let you show a route in a different context (e.g., a modal) while preserving the full-page version for direct navigation.

## Parallel Routes: Split Dashboard Layout

```
app/
  dashboard/
    layout.tsx
    page.tsx
    @analytics/
      page.tsx
      loading.tsx
    @activity/
      page.tsx
      loading.tsx
      default.tsx
```

```typescript
// app/dashboard/layout.tsx
// Named slots (@analytics, @activity) are passed as props to the layout
export default function DashboardLayout({
  children,
  analytics,
  activity,
}: {
  children: React.ReactNode;
  analytics: React.ReactNode;
  activity: React.ReactNode;
}) {
  return (
    <div className="dashboard-grid">
      {/* Main content from page.tsx */}
      <main className="col-span-2">{children}</main>

      {/* These render in parallel — independent loading states */}
      <aside className="col-span-1">
        {analytics}
        {activity}
      </aside>
    </div>
  );
}

// app/dashboard/@analytics/page.tsx
export default async function AnalyticsPanel() {
  const metrics = await getAnalytics(); // Fetches independently

  return (
    <section>
      <h3>Analytics</h3>
      <MetricsGrid metrics={metrics} />
    </section>
  );
}

// app/dashboard/@analytics/loading.tsx
export default function AnalyticsLoading() {
  return <MetricsGridSkeleton />;
}

// app/dashboard/@activity/default.tsx
// Required: default.tsx renders when the slot has no matching route
// (e.g., when navigating to a sub-route that only @analytics defines)
export default function ActivityDefault() {
  return null;
}
```

## Conditional Parallel Routes for Auth

```
app/
  @auth/
    login/
      page.tsx
    default.tsx
  @dashboard/
    page.tsx
    settings/
      page.tsx
    default.tsx
  layout.tsx
```

```typescript
// app/layout.tsx
import { getSession } from "@/lib/auth";

export default async function RootLayout({
  auth,
  dashboard,
}: {
  auth: React.ReactNode;
  dashboard: React.ReactNode;
}) {
  const session = await getSession();

  // Show auth flow or dashboard based on session
  return (
    <html lang="en">
      <body>
        {session ? dashboard : auth}
      </body>
    </html>
  );
}

// app/@auth/login/page.tsx
"use client";

import { useActionState } from "react";
import { loginAction } from "./actions";

export default function LoginPage() {
  const [state, formAction, isPending] = useActionState(loginAction, {
    error: null,
  });

  return (
    <div className="login-container">
      <form action={formAction}>
        <input name="email" type="email" required placeholder="Email" />
        <input name="password" type="password" required placeholder="Password" />
        {state.error && <p className="error">{state.error}</p>}
        <button type="submit" disabled={isPending}>
          {isPending ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
```

## Intercepting Routes: Modal Pattern

```
app/
  photos/
    page.tsx              # Gallery grid
    [id]/
      page.tsx            # Full photo page (direct navigation)
  @modal/
    (.)photos/[id]/
      page.tsx            # Photo modal (intercepted soft navigation)
    default.tsx
  layout.tsx
```

The `(.)` prefix means "intercept from the same level." When a user clicks a photo link in the gallery, Next.js shows the modal version. On direct URL access or hard refresh, the full page renders.

```typescript
// app/layout.tsx
export default function RootLayout({
  children,
  modal,
}: {
  children: React.ReactNode;
  modal: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}
        {modal}
      </body>
    </html>
  );
}

// app/@modal/default.tsx — no modal by default
export default function ModalDefault() {
  return null;
}

// app/@modal/(.)photos/[id]/page.tsx — the intercepted modal
import { getPhoto } from "@/lib/photos";
import { Modal } from "@/components/modal";

export default async function PhotoModal({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const photo = await getPhoto(id);

  return (
    <Modal>
      <img src={photo.url} alt={photo.alt} className="max-h-[80vh] object-contain" />
      <div className="p-4">
        <h2>{photo.title}</h2>
        <p>{photo.description}</p>
        <p className="text-sm text-gray-500">By {photo.author}</p>
      </div>
    </Modal>
  );
}

// components/modal.tsx
"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";

export function Modal({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const overlayRef = useRef<HTMLDivElement>(null);

  const onDismiss = useCallback(() => {
    router.back();
  }, [router]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onDismiss();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onDismiss]);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === overlayRef.current) onDismiss();
      }}
    >
      <div className="bg-white rounded-lg max-w-3xl w-full max-h-[90vh] overflow-auto">
        {children}
      </div>
    </div>
  );
}

// app/photos/[id]/page.tsx — full page version (direct navigation / hard refresh)
import { getPhoto } from "@/lib/photos";
import { notFound } from "next/navigation";

export default async function PhotoPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const photo = await getPhoto(id);
  if (!photo) notFound();

  return (
    <article className="max-w-4xl mx-auto py-8">
      <img src={photo.url} alt={photo.alt} className="w-full rounded-lg" />
      <h1 className="text-3xl mt-4">{photo.title}</h1>
      <p className="mt-2">{photo.description}</p>
      <p className="text-gray-500 mt-1">By {photo.author}</p>
    </article>
  );
}
```

## Common Pitfalls

1. **Missing `default.tsx`**: Every parallel route slot MUST have a `default.tsx`. Without it, Next.js throws a 404 when navigating to a route that does not have a matching segment in that slot.
2. **Intercepting route depth**: `(.)` intercepts same level, `(..)` one level up, `(...)` from root. Getting the level wrong silently fails — the interception does not trigger.
3. **Hard refresh kills modals**: Intercepting routes only work on soft (client-side) navigation. On hard refresh, the full page version renders. Design both versions.
4. **Slot naming**: Parallel route folders must start with `@`. The `@` folder name becomes the prop name in the parent layout (minus the `@`).
''',
    ),
    (
        "typescript/production",
        r'''Show how to use Next.js server actions with form handling, revalidation, and error handling. Include optimistic updates and progressive enhancement patterns.''',
        r'''# Next.js Server Actions with Revalidation

Server actions are async functions that run on the server, callable directly from Client Components via form actions or event handlers. They replace API routes for mutations and integrate with Next.js caching and revalidation.

## Basic Server Action with Validation

```typescript
// app/actions/posts.ts
"use server";

import { z } from "zod";
import { revalidatePath, revalidateTag } from "next/cache";
import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { getSession } from "@/lib/auth";

const createPostSchema = z.object({
  title: z.string().min(1, "Title is required").max(200),
  content: z.string().min(10, "Content must be at least 10 characters"),
  categoryId: z.string().uuid("Invalid category"),
  published: z.coerce.boolean().default(false),
});

// Return type for form state
interface ActionState {
  success: boolean;
  errors?: Record<string, string[]>;
  message?: string;
}

export async function createPost(
  prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  // Auth check
  const session = await getSession();
  if (!session) {
    return { success: false, message: "You must be signed in" };
  }

  // Validate
  const parsed = createPostSchema.safeParse({
    title: formData.get("title"),
    content: formData.get("content"),
    categoryId: formData.get("categoryId"),
    published: formData.get("published"),
  });

  if (!parsed.success) {
    return {
      success: false,
      errors: parsed.error.flatten().fieldErrors,
    };
  }

  try {
    const post = await db.post.create({
      data: {
        ...parsed.data,
        authorId: session.userId,
      },
    });

    // Revalidate cached data
    revalidatePath("/posts");
    revalidateTag("posts");

    // Redirect on success (throws internally, must be outside try/catch for redirects)
  } catch (error) {
    return {
      success: false,
      message: "Failed to create post. Please try again.",
    };
  }

  redirect("/posts"); // Must be outside try-catch
}

export async function deletePost(postId: string): Promise<ActionState> {
  const session = await getSession();
  if (!session) {
    return { success: false, message: "Unauthorized" };
  }

  const post = await db.post.findUnique({ where: { id: postId } });
  if (!post || post.authorId !== session.userId) {
    return { success: false, message: "Not found or unauthorized" };
  }

  await db.post.delete({ where: { id: postId } });

  revalidatePath("/posts");
  revalidateTag("posts");

  return { success: true };
}

export async function togglePublished(postId: string): Promise<void> {
  const session = await getSession();
  if (!session) throw new Error("Unauthorized");

  const post = await db.post.findUniqueOrThrow({ where: { id: postId } });
  if (post.authorId !== session.userId) throw new Error("Forbidden");

  await db.post.update({
    where: { id: postId },
    data: { published: !post.published },
  });

  revalidatePath("/posts");
  revalidateTag(`post-${postId}`);
}
```

## Client Form with useActionState

```typescript
// app/posts/new/page.tsx
"use client";

import { useActionState } from "react";
import { createPost } from "@/app/actions/posts";

const initialState = { success: false };

export default function NewPostPage() {
  const [state, formAction, isPending] = useActionState(createPost, initialState);

  return (
    <form action={formAction} className="space-y-4 max-w-2xl">
      <div>
        <label htmlFor="title">Title</label>
        <input
          id="title"
          name="title"
          required
          className="input"
          aria-describedby={state.errors?.title ? "title-error" : undefined}
        />
        {state.errors?.title && (
          <p id="title-error" className="text-red-500 text-sm">
            {state.errors.title[0]}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="content">Content</label>
        <textarea
          id="content"
          name="content"
          required
          rows={10}
          className="textarea"
          aria-describedby={state.errors?.content ? "content-error" : undefined}
        />
        {state.errors?.content && (
          <p id="content-error" className="text-red-500 text-sm">
            {state.errors.content[0]}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="categoryId">Category</label>
        <CategorySelect name="categoryId" />
        {state.errors?.categoryId && (
          <p className="text-red-500 text-sm">{state.errors.categoryId[0]}</p>
        )}
      </div>

      <label className="flex items-center gap-2">
        <input type="checkbox" name="published" value="true" />
        Publish immediately
      </label>

      {state.message && !state.success && (
        <div role="alert" className="text-red-500">{state.message}</div>
      )}

      <button type="submit" disabled={isPending} className="btn-primary">
        {isPending ? "Creating..." : "Create Post"}
      </button>
    </form>
  );
}
```

## Optimistic Delete with Server Action

```typescript
// app/posts/post-list.tsx
"use client";

import { useOptimistic, useTransition } from "react";
import { deletePost, togglePublished } from "@/app/actions/posts";

interface Post {
  id: string;
  title: string;
  published: boolean;
}

export function PostList({ posts }: { posts: Post[] }) {
  const [optimisticPosts, setOptimisticPosts] = useOptimistic(
    posts,
    (current: Post[], action: { type: "delete"; id: string } | { type: "toggle"; id: string }) => {
      if (action.type === "delete") {
        return current.filter((p) => p.id !== action.id);
      }
      return current.map((p) =>
        p.id === action.id ? { ...p, published: !p.published } : p
      );
    }
  );

  const [, startTransition] = useTransition();

  function handleDelete(id: string) {
    startTransition(async () => {
      setOptimisticPosts({ type: "delete", id });
      const result = await deletePost(id);
      if (!result.success) {
        // Optimistic state reverts automatically when posts prop updates
        alert(result.message);
      }
    });
  }

  function handleToggle(id: string) {
    startTransition(async () => {
      setOptimisticPosts({ type: "toggle", id });
      await togglePublished(id);
    });
  }

  return (
    <ul>
      {optimisticPosts.map((post) => (
        <li key={post.id} className="flex items-center justify-between py-2">
          <span>{post.title}</span>
          <div className="flex gap-2">
            <button onClick={() => handleToggle(post.id)}>
              {post.published ? "Unpublish" : "Publish"}
            </button>
            <button onClick={() => handleDelete(post.id)} className="text-red-500">
              Delete
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
```

## Progressive Enhancement

```typescript
// This form works WITHOUT JavaScript enabled
// The server action processes the FormData directly
// With JS, useActionState enhances it with pending state and client validation

// The key principle: server actions bound to <form action={...}> work as
// standard HTML form submissions when JS is disabled. The server processes
// the POST, runs the action, and returns the new page.

// For non-form mutations (like the delete button above), provide a
// fallback form for no-JS:
function DeleteButton({ postId }: { postId: string }) {
  return (
    <form action={async () => {
      "use server";
      await deletePost(postId);
    }}>
      <button type="submit" className="text-red-500">Delete</button>
    </form>
  );
}
```

## Common Pitfalls

1. **`redirect()` inside try/catch**: `redirect()` throws a special error internally. Calling it inside a catch block swallows the redirect. Always call it after the try/catch.
2. **Forgetting revalidation**: Server actions mutate data but Next.js serves cached pages. Always call `revalidatePath` or `revalidateTag` after mutations.
3. **Large FormData**: Server actions have a 1MB default body limit. For file uploads, use a presigned URL pattern instead.
4. **Closure over sensitive data**: Inline server actions (`async () => { "use server"; ... }`) capture variables from the outer scope. These values are encrypted but still sent to the client as part of the action reference. Never close over secrets.
''',
    ),
    (
        "typescript/production",
        r'''Show how to use Next.js middleware for authentication and internationalization (i18n). Include patterns for protecting routes, redirecting unauthenticated users, and locale detection.''',
        r'''# Next.js Middleware for Auth and i18n

Middleware runs at the edge before every request, making it ideal for auth checks, locale detection, and redirects. It executes before any rendering, so protected pages never even begin to load for unauthorized users.

## Auth Middleware

```typescript
// middleware.ts (root of the project)
import { NextRequest, NextResponse } from "next/server";
import { verifyToken } from "@/lib/auth-edge"; // Edge-compatible JWT verification

// Routes that don't require authentication
const publicPaths = new Set([
  "/",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/api/auth/callback",
  "/api/health",
]);

// Routes that require specific roles
const roleProtectedPaths: Record<string, string[]> = {
  "/admin": ["admin"],
  "/admin/users": ["admin"],
  "/admin/settings": ["admin", "manager"],
};

function isPublicPath(pathname: string): boolean {
  if (publicPaths.has(pathname)) return true;
  // Allow all static assets and Next.js internals
  if (pathname.startsWith("/_next/") || pathname.startsWith("/static/")) return true;
  if (/\.(ico|png|jpg|svg|css|js|woff2?)$/.test(pathname)) return true;
  return false;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip public routes
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Check for auth token
  const token = request.cookies.get("auth-token")?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(loginUrl);
  }

  try {
    const session = await verifyToken(token);

    // Check role-based access
    for (const [protectedPath, allowedRoles] of Object.entries(roleProtectedPaths)) {
      if (pathname.startsWith(protectedPath)) {
        if (!allowedRoles.includes(session.role)) {
          return NextResponse.redirect(new URL("/unauthorized", request.url));
        }
        break;
      }
    }

    // Attach user info to headers for downstream use
    const response = NextResponse.next();
    response.headers.set("x-user-id", session.userId);
    response.headers.set("x-user-role", session.role);
    return response;
  } catch {
    // Invalid or expired token — clear cookie and redirect
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("callbackUrl", pathname);
    const response = NextResponse.redirect(loginUrl);
    response.cookies.delete("auth-token");
    return response;
  }
}

export const config = {
  // Match all paths except static files
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

## i18n Middleware with Locale Detection

```typescript
// middleware.ts — combined auth + i18n
import { NextRequest, NextResponse } from "next/server";
import { match } from "@formatjs/intl-localematcher";
import Negotiator from "negotiator";

const SUPPORTED_LOCALES = ["en", "es", "fr", "de", "ja"] as const;
type Locale = (typeof SUPPORTED_LOCALES)[number];
const DEFAULT_LOCALE: Locale = "en";

function getPreferredLocale(request: NextRequest): Locale {
  // 1. Check cookie (user's explicit choice)
  const cookieLocale = request.cookies.get("locale")?.value;
  if (cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale as Locale)) {
    return cookieLocale as Locale;
  }

  // 2. Check Accept-Language header
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    headers[key] = value;
  });

  try {
    const negotiator = new Negotiator({ headers });
    const languages = negotiator.languages();
    return match(languages, [...SUPPORTED_LOCALES], DEFAULT_LOCALE) as Locale;
  } catch {
    return DEFAULT_LOCALE;
  }
}

function pathnameHasLocale(pathname: string): boolean {
  return SUPPORTED_LOCALES.some(
    (locale) => pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`
  );
}

function extractLocale(pathname: string): Locale | null {
  const segment = pathname.split("/")[1];
  if (SUPPORTED_LOCALES.includes(segment as Locale)) {
    return segment as Locale;
  }
  return null;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip Next.js internals and static files
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    /\.(ico|png|jpg|svg|css|js)$/.test(pathname)
  ) {
    return NextResponse.next();
  }

  // i18n: Redirect if no locale prefix
  if (!pathnameHasLocale(pathname)) {
    const locale = getPreferredLocale(request);
    const url = new URL(`/${locale}${pathname}`, request.url);
    url.search = request.nextUrl.search;
    return NextResponse.redirect(url);
  }

  const locale = extractLocale(pathname)!;

  // Auth: Check protected routes (after locale prefix)
  const pathWithoutLocale = pathname.replace(`/${locale}`, "") || "/";

  if (!isPublicPath(pathWithoutLocale)) {
    const token = request.cookies.get("auth-token")?.value;
    if (!token) {
      const loginUrl = new URL(`/${locale}/login`, request.url);
      loginUrl.searchParams.set("callbackUrl", pathname);
      return NextResponse.redirect(loginUrl);
    }

    try {
      await verifyToken(token);
    } catch {
      const loginUrl = new URL(`/${locale}/login`, request.url);
      loginUrl.searchParams.set("callbackUrl", pathname);
      const response = NextResponse.redirect(loginUrl);
      response.cookies.delete("auth-token");
      return response;
    }
  }

  // Set locale header for server components to read
  const response = NextResponse.next();
  response.headers.set("x-locale", locale);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

## Using Locale in Server Components

```typescript
// app/[locale]/layout.tsx
import { headers } from "next/headers";
import { getDictionary } from "@/lib/dictionaries";

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const dict = await getDictionary(locale);

  return (
    <html lang={locale}>
      <body>
        <nav>
          <a href={`/${locale}`}>{dict.nav.home}</a>
          <a href={`/${locale}/about`}>{dict.nav.about}</a>
          <LocaleSwitcher currentLocale={locale} />
        </nav>
        {children}
      </body>
    </html>
  );
}

// lib/dictionaries.ts
const dictionaries = {
  en: () => import("@/dictionaries/en.json").then((m) => m.default),
  es: () => import("@/dictionaries/es.json").then((m) => m.default),
  fr: () => import("@/dictionaries/fr.json").then((m) => m.default),
  de: () => import("@/dictionaries/de.json").then((m) => m.default),
  ja: () => import("@/dictionaries/ja.json").then((m) => m.default),
};

export async function getDictionary(locale: string) {
  const loader = dictionaries[locale as keyof typeof dictionaries] ?? dictionaries.en;
  return loader();
}
```

## Common Pitfalls

1. **Middleware runs on EVERY request**: Including images, fonts, and API calls. Use the `matcher` config to exclude static paths, or performance suffers.
2. **Edge runtime limitations**: Middleware runs in the Edge Runtime. No Node.js APIs (`fs`, `crypto.subtle` is OK, `node:crypto` is not). Use edge-compatible JWT libraries.
3. **Infinite redirect loops**: If middleware redirects to `/login` and `/login` is not in `publicPaths`, you get an infinite loop. Always verify your public path list includes all redirect targets.
4. **Locale in API routes**: Do NOT prefix API routes with locale (`/en/api/...`). Exclude `/api` from the locale middleware.
''',
    ),
    (
        "typescript/production",
        r'''Show how to implement ISR (Incremental Static Regeneration) with on-demand revalidation in Next.js App Router. Include time-based ISR, on-demand revalidation via API routes, and tag-based cache invalidation.''',
        r'''# ISR with On-Demand Revalidation

ISR lets you statically generate pages at build time and regenerate them in the background — either on a time interval or on-demand when data changes. In the App Router, this is controlled via `fetch` options and the `revalidatePath`/`revalidateTag` APIs.

## Time-Based ISR

```typescript
// app/blog/page.tsx — regenerates every 60 seconds
import { db } from "@/lib/db";

export const revalidate = 60; // Seconds — page-level ISR config

export default async function BlogIndex() {
  const posts = await db.post.findMany({
    where: { published: true },
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  return (
    <main>
      <h1>Blog</h1>
      <ul>
        {posts.map((post) => (
          <li key={post.id}>
            <a href={`/blog/${post.slug}`}>{post.title}</a>
            <time dateTime={post.createdAt.toISOString()}>
              {post.createdAt.toLocaleDateString()}
            </time>
          </li>
        ))}
      </ul>
    </main>
  );
}

// app/blog/[slug]/page.tsx — per-page ISR with static params
import { notFound } from "next/navigation";

// Generate static pages at build time for known slugs
export async function generateStaticParams() {
  const posts = await db.post.findMany({
    where: { published: true },
    select: { slug: true },
  });
  return posts.map((post) => ({ slug: post.slug }));
}

export const revalidate = 3600; // 1 hour for individual posts

export default async function BlogPost({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  const post = await db.post.findUnique({
    where: { slug, published: true },
    include: { author: true },
  });

  if (!post) notFound();

  return (
    <article>
      <h1>{post.title}</h1>
      <p>By {post.author.name}</p>
      <div dangerouslySetInnerHTML={{ __html: post.contentHtml }} />
    </article>
  );
}
```

## Fetch-Level Cache Tags

```typescript
// lib/data.ts — tagged fetches for granular cache control
export async function getProducts(categoryId?: string): Promise<Product[]> {
  const url = categoryId
    ? `${process.env.API_URL}/products?category=${categoryId}`
    : `${process.env.API_URL}/products`;

  const response = await fetch(url, {
    next: {
      tags: ["products", ...(categoryId ? [`category-${categoryId}`] : [])],
      revalidate: 300, // 5 minutes fallback
    },
  });

  if (!response.ok) throw new Error("Failed to fetch products");
  return response.json();
}

export async function getProduct(id: string): Promise<Product> {
  const response = await fetch(`${process.env.API_URL}/products/${id}`, {
    next: {
      tags: ["products", `product-${id}`],
      revalidate: 600, // 10 minutes fallback
    },
  });

  if (!response.ok) throw new Error("Failed to fetch product");
  return response.json();
}
```

## On-Demand Revalidation via Webhook

```typescript
// app/api/revalidate/route.ts
import { revalidatePath, revalidateTag } from "next/cache";
import { NextRequest, NextResponse } from "next/server";

const WEBHOOK_SECRET = process.env.REVALIDATION_SECRET!;

interface WebhookPayload {
  event: "post.created" | "post.updated" | "post.deleted" | "product.updated";
  data: {
    id: string;
    slug?: string;
    categoryId?: string;
  };
}

export async function POST(request: NextRequest) {
  // Verify webhook authenticity
  const authHeader = request.headers.get("authorization");
  if (authHeader !== `Bearer ${WEBHOOK_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const payload: WebhookPayload = await request.json();

  try {
    switch (payload.event) {
      case "post.created":
      case "post.deleted":
        // Revalidate the blog index
        revalidateTag("posts");
        revalidatePath("/blog");
        break;

      case "post.updated":
        // Revalidate the specific post AND the index
        revalidateTag("posts");
        if (payload.data.slug) {
          revalidatePath(`/blog/${payload.data.slug}`);
        }
        break;

      case "product.updated":
        // Revalidate the specific product page
        revalidateTag(`product-${payload.data.id}`);
        // Also revalidate the category page if category changed
        if (payload.data.categoryId) {
          revalidateTag(`category-${payload.data.categoryId}`);
        }
        break;
    }

    return NextResponse.json({
      revalidated: true,
      event: payload.event,
      timestamp: Date.now(),
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Revalidation failed" },
      { status: 500 }
    );
  }
}
```

## Revalidation from Server Actions

```typescript
// app/actions/products.ts
"use server";

import { revalidateTag, revalidatePath } from "next/cache";
import { db } from "@/lib/db";
import { z } from "zod";

const updateProductSchema = z.object({
  name: z.string().min(1),
  price: z.number().positive(),
  description: z.string(),
  categoryId: z.string().uuid(),
});

export async function updateProduct(
  productId: string,
  formData: FormData
): Promise<{ success: boolean; error?: string }> {
  const parsed = updateProductSchema.safeParse({
    name: formData.get("name"),
    price: Number(formData.get("price")),
    description: formData.get("description"),
    categoryId: formData.get("categoryId"),
  });

  if (!parsed.success) {
    return { success: false, error: "Validation failed" };
  }

  const product = await db.product.update({
    where: { id: productId },
    data: parsed.data,
  });

  // Surgical cache invalidation
  revalidateTag(`product-${productId}`);          // This product's detail page
  revalidateTag(`category-${product.categoryId}`); // The category listing
  revalidateTag("products");                        // The main products page
  // Note: other pages that fetched with these tags will also revalidate

  return { success: true };
}
```

## Advanced: Stale-While-Revalidate with Streaming

```typescript
// app/products/page.tsx
import { Suspense } from "react";
import { getProducts } from "@/lib/data";

// Page shell loads instantly (static), product grid streams in
export default function ProductsPage() {
  return (
    <main>
      <h1>Products</h1>
      <Suspense fallback={<ProductGridSkeleton />}>
        <ProductGrid />
      </Suspense>
    </main>
  );
}

async function ProductGrid() {
  const products = await getProducts(); // Uses cached data, revalidates in background

  return (
    <div className="grid grid-cols-3 gap-6">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}

// Dynamic generation for unknown slugs
export const dynamicParams = true; // Allow pages not in generateStaticParams

// If false, unknown slugs return 404 instead of generating on-demand
```

## Cache Debugging

```typescript
// During development, verify cache behavior
// next.config.ts
import type { NextConfig } from "next";

const config: NextConfig = {
  logging: {
    fetches: {
      fullUrl: true, // Logs all fetch calls with cache status (HIT/MISS/STALE)
    },
  },
};

export default config;
```

## Common Pitfalls

1. **`revalidate = 0` vs `dynamic = "force-dynamic"`**: Setting `revalidate = 0` means "never cache" — every request hits the server. Use `force-dynamic` when you also need to access headers/cookies. For ISR, use a positive number.
2. **Tag propagation**: `revalidateTag("products")` invalidates ALL fetches tagged with "products" across all pages. Be specific with tags to avoid over-invalidating.
3. **Build-time vs runtime**: `generateStaticParams` runs at build time. If you add new blog posts after deployment, set `dynamicParams = true` so new slugs are generated on first request.
4. **Serverless function cold starts**: ISR regeneration runs in serverless functions. If regeneration is slow (heavy DB queries), the first visitor after expiry gets a stale page while the function regenerates. Combine with webhook-based on-demand revalidation for instant updates.
''',
    ),
]
