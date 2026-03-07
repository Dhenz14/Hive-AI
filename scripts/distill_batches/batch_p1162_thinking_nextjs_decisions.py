"""
Frontend thinking pairs - Next.js architecture decisions
"""

pairs = [
    {
        "instruction": r'''I am building a blog with Next.js. Should I use SSR (getServerSideProps), SSG (getStaticProps), or the new App Router with Server Components? What are the tradeoffs?''',
        "output": r'''<think>
A blog is a classic use case for static generation because blog posts do not change frequently. But the answer depends on the specifics. Let me think through each option.

SSG with getStaticProps (Pages Router):
- Pages are generated at BUILD time as static HTML
- Served from CDN -- fastest possible response time
- Perfect for content that changes rarely (blog posts)
- Downside: need to rebuild to update content, or use ISR (Incremental Static Regeneration)

SSR with getServerSideProps (Pages Router):
- Pages are generated on EVERY request
- Always fresh data
- Slower than SSG because the server runs on each request
- Good for dashboards, user-specific content
- For a blog? Overkill unless content changes every minute

App Router with Server Components (Next.js 13+):
- Components are rendered on the server by default
- Can use fetch with cache/revalidation options
- More granular control -- mix static and dynamic within one page
- The "modern" approach Next.js is pushing toward

Hmm, for a blog specifically, SSG with ISR is probably the best fit. Posts are written, published, and rarely changed. ISR lets you revalidate every N seconds so new posts appear without a full rebuild.

Wait, but the App Router approach can achieve the same thing with less boilerplate. Instead of getStaticProps + getStaticPaths, you just make the page component async and fetch data directly. You set revalidation with export const revalidate = 3600.

I initially thought Pages Router SSG was the clear winner, but actually App Router with static rendering is just as fast and has a simpler API. The question is whether the team is comfortable with the newer patterns (use client directives, Server vs Client Components).

The tradeoff: Pages Router is more battle-tested and well-documented. App Router is the future direction but has a steeper learning curve and some rough edges.

For a new project, I would recommend App Router. For an existing Pages Router project, no need to migrate.
</think>

For a blog, you want static generation with incremental revalidation. Here is how each approach compares:

```tsx
// OPTION 1: Pages Router + SSG + ISR (battle-tested)
// pages/blog/[slug].tsx
import { GetStaticProps, GetStaticPaths } from 'next';

interface Post {
  slug: string;
  title: string;
  content: string;
  publishedAt: string;
}

export const getStaticPaths: GetStaticPaths = async () => {
  const posts = await fetchAllPosts();
  return {
    paths: posts.map(p => ({ params: { slug: p.slug } })),
    fallback: 'blocking', // New posts SSR on first visit, then cached
  };
};

export const getStaticProps: GetStaticProps = async ({ params }) => {
  const post = await fetchPost(params?.slug as string);
  if (!post) return { notFound: true };
  return {
    props: { post },
    revalidate: 3600, // Regenerate page every hour
  };
};

export default function BlogPost({ post }: { post: Post }) {
  return (
    <article>
      <h1>{post.title}</h1>
      <time>{post.publishedAt}</time>
      <div dangerouslySetInnerHTML={{ __html: post.content }} />
    </article>
  );
}
```

```tsx
// OPTION 2: App Router + Server Components (modern, recommended for new projects)
// app/blog/[slug]/page.tsx

// This tells Next.js to statically generate at build time
export async function generateStaticParams() {
  const posts = await fetchAllPosts();
  return posts.map(p => ({ slug: p.slug }));
}

// Revalidate cached pages every hour
export const revalidate = 3600;

// Server Component -- runs on server, no client JS shipped
export default async function BlogPost({
  params,
}: {
  params: { slug: string };
}) {
  const post = await fetchPost(params.slug);

  if (!post) {
    notFound(); // Built-in 404 handling
  }

  return (
    <article>
      <h1>{post.title}</h1>
      <time dateTime={post.publishedAt}>
        {new Date(post.publishedAt).toLocaleDateString()}
      </time>
      <PostContent content={post.content} />
      {/* Interactive parts are Client Components */}
      <LikeButton postId={post.id} />
      <CommentSection postId={post.id} />
    </article>
  );
}

// Only this component ships JS to the client
// app/blog/[slug]/LikeButton.tsx
'use client';

import { useState } from 'react';

export function LikeButton({ postId }: { postId: string }) {
  const [liked, setLiked] = useState(false);
  return (
    <button onClick={() => setLiked(!liked)}>
      {liked ? 'Liked' : 'Like'}
    </button>
  );
}
```

Decision matrix:

| Factor | SSG (Pages) | SSR (Pages) | App Router |
|---|---|---|---|
| Speed | Fastest (CDN) | Slower (server per request) | Fast (static by default) |
| Freshness | Revalidate interval | Always fresh | Revalidate interval |
| JS shipped to client | Full page component | Full page component | Only interactive parts |
| Best for | Blogs, docs, marketing | Dashboards, real-time data | New projects, mixed content |
| Learning curve | Low | Low | Medium-high |

Recommendation:
- **New blog**: App Router. Less boilerplate, ships less JS, and is where Next.js is heading.
- **Existing Pages Router blog**: Stay with SSG + ISR. No reason to migrate a working setup.
- **Blog with real-time features** (live comments, view counters): App Router with a mix of static pages and client components for interactive parts.'''
    },
    {
        "instruction": r'''I am confused about when to use "use client" vs keeping a component as a Server Component in the Next.js App Router. What is the mental model?''',
        "output": r'''<think>
This is the core mental model question for the App Router. Let me think about it clearly.

Server Components (default in App Router):
- Run ONLY on the server
- Can directly access databases, file system, environment variables
- Ship ZERO JavaScript to the client
- Cannot use useState, useEffect, onClick, or any browser APIs
- Cannot use React context

Client Components ("use client"):
- Run on the server for initial HTML (SSR) AND on the client for interactivity
- Ship JavaScript to the client for hydration
- Can use all React hooks, event handlers, browser APIs
- This is what ALL React components were before Server Components

The mental model: start with Server Components (the default). Only add "use client" when you NEED interactivity. The question is: "Does this component need to respond to user actions or use browser APIs?"

Wait, there is a common misconception. "use client" does NOT mean the component only runs in the browser. It runs on the server first (for SSR), then hydrates on the client. The directive means "include this component's JavaScript in the client bundle."

Hmm, another subtlety: Server Components can IMPORT and RENDER Client Components. The Client Component boundary only affects that component and its children. So you can have a Server Component page that renders a Client Component button -- only the button ships JS.

I initially thought the decision was just "does it have state? --> use client." But there are more nuances:
- Third-party libraries that use hooks internally (like framer-motion) require "use client"
- Components that read cookies/headers at request time are Server Components (they use server-only APIs)
- Context providers must be Client Components
- Forms with state need "use client", but Server Actions can handle form submission on the server

The principle: Server Components are the "render" layer (data fetching, layout, static content). Client Components are the "interaction" layer (forms, buttons, animations, real-time updates). Push "use client" boundaries as LOW as possible in the component tree.
</think>

The mental model: **Server Components are the default. Add "use client" only at the lowest point where you need interactivity.**

```tsx
// Server Component (default) -- NO "use client" directive
// Runs on server only. Ships ZERO JavaScript to browser.
// app/blog/[slug]/page.tsx

import { LikeButton } from './LikeButton';
import { ShareMenu } from './ShareMenu';

// Can directly await async data -- no useEffect needed
export default async function BlogPost({
  params,
}: {
  params: { slug: string };
}) {
  // Direct database/API access on the server
  const post = await db.posts.findBySlug(params.slug);
  const author = await db.users.findById(post.authorId);

  // Server Component renders static content
  // Only LikeButton and ShareMenu ship JS to the client
  return (
    <article>
      <h1>{post.title}</h1>
      <div className="author">
        <img src={author.avatar} alt={author.name} />
        <span>{author.name}</span>
      </div>
      <div>{post.content}</div>

      {/* These are Client Components -- they need interactivity */}
      <LikeButton postId={post.id} initialCount={post.likes} />
      <ShareMenu url={'/blog/' + post.slug} title={post.title} />
    </article>
  );
}
```

```tsx
// Client Component -- has "use client" because it needs useState + onClick
// app/blog/[slug]/LikeButton.tsx
'use client';

import { useState } from 'react';

export function LikeButton({
  postId,
  initialCount,
}: {
  postId: string;
  initialCount: number;
}) {
  const [count, setCount] = useState(initialCount);
  const [liked, setLiked] = useState(false);

  const toggle = async () => {
    setLiked(!liked);
    setCount(c => c + (liked ? -1 : 1));
    await fetch('/api/likes/' + postId, {
      method: liked ? 'DELETE' : 'POST',
    });
  };

  return (
    <button onClick={toggle}>
      {liked ? 'Liked' : 'Like'} ({count})
    </button>
  );
}
```

Decision checklist -- does the component need:

```
Need useState or useReducer?           --> "use client"
Need useEffect?                        --> "use client"
Need onClick, onChange, onSubmit?       --> "use client"
Need browser APIs (window, document)?  --> "use client"
Need React context (useContext)?       --> "use client"
Uses a library that requires hooks?    --> "use client"
  (framer-motion, react-hook-form, etc.)

Just renders data from the server?     --> Server Component
Just does layout/styling?              --> Server Component
Fetches data from DB/API?              --> Server Component
Reads cookies/headers?                 --> Server Component
```

Key insight: push the "use client" boundary DOWN the tree.

```tsx
// BAD: making the entire page a Client Component
// Every child ships JavaScript to the browser
'use client'; // Too high!

export default function Dashboard() {
  const [tab, setTab] = useState('overview');
  return (
    <div>
      <Header /> {/* Static -- should be Server Component */}
      <Sidebar /> {/* Static -- should be Server Component */}
      <TabBar active={tab} onChange={setTab} />
      <TabContent tab={tab} />
    </div>
  );
}

// GOOD: only the interactive parts are Client Components
// app/dashboard/page.tsx (Server Component)
export default async function Dashboard() {
  const stats = await fetchStats(); // Server-side data fetch
  return (
    <div>
      <Header />     {/* Server Component -- no JS shipped */}
      <Sidebar />    {/* Server Component -- no JS shipped */}
      <DashboardTabs stats={stats} /> {/* Client Component -- has tab state */}
    </div>
  );
}
```'''
    },
    {
        "instruction": r'''How do I handle authentication in Next.js App Router? Should auth checks happen in middleware, layout, or each page?''',
        "output": r'''<think>
Authentication in Next.js App Router -- this is a design decision with multiple valid approaches. Let me think through the options.

Option 1: Middleware (middleware.ts at project root)
- Runs BEFORE the page renders on every matching request
- Can check for auth cookies/tokens and redirect to login
- Runs on the edge (Vercel Edge Runtime) so it is fast
- But: limited runtime (no database access, no Node.js APIs in edge)
- Good for: simple token existence checks, redirects

Option 2: Layout (app/dashboard/layout.tsx)
- Auth check in a Server Component layout
- Can access databases, call APIs
- Protects all pages under that layout
- But: the layout renders -- if auth fails, you redirect AFTER rendering starts

Option 3: Each page individually
- Most flexible but most repetitive
- Easy to forget to add auth check to a new page

Option 4: Next-auth / Auth.js integration
- Library handles most of the complexity
- Provides session hooks, middleware helpers, route handlers

Hmm, the best approach in practice is LAYERED:
1. Middleware for fast redirects (check if auth cookie exists -- not if it is valid, just if it exists)
2. Layout for actual session validation (verify token, check permissions)
3. Individual pages for specific authorization (does this user have access to THIS resource?)

Wait, why not just do everything in middleware? Because middleware runs on the edge and cannot access your database to validate sessions. It can check if a cookie EXISTS but cannot verify if the session is still valid or check user permissions.

I initially thought middleware alone was sufficient, but it only does coarse-grained checks. Fine-grained authorization (role-based access, resource ownership) needs server-side code with database access.

The tradeoff: middleware is fast but limited. Server Components have full access but run later. Use both layers for defense in depth.
</think>

Use a layered approach: middleware for fast redirects, layout for session validation, and page-level for authorization.

```tsx
// LAYER 1: Middleware -- fast auth cookie check
// middleware.ts (project root)
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('session-token');

  // No cookie at all? Redirect to login immediately.
  // This is a FAST check -- no database call, no token verification.
  if (!token) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirect', request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Cookie exists -- let the page/layout verify it
  return NextResponse.next();
}

// Only run middleware on protected routes
export const config = {
  matcher: ['/dashboard/:path*', '/settings/:path*', '/admin/:path*'],
};
```

```tsx
// LAYER 2: Layout -- validate session, fetch user data
// app/dashboard/layout.tsx
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifySession } from '@/lib/auth';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = cookies();
  const token = cookieStore.get('session-token')?.value;

  // Verify the token is valid (database call)
  const session = token ? await verifySession(token) : null;

  if (!session) {
    redirect('/login');
  }

  return (
    <div className="dashboard-layout">
      <Sidebar user={session.user} />
      <main>{children}</main>
    </div>
  );
}

// lib/auth.ts
interface Session {
  user: { id: string; name: string; role: 'admin' | 'user' };
  expiresAt: Date;
}

export async function verifySession(
  token: string
): Promise<Session | null> {
  // Check token in database, verify not expired
  const session = await db.sessions.findByToken(token);
  if (!session) return null;
  if (new Date(session.expiresAt) < new Date()) return null;
  return session;
}
```

```tsx
// LAYER 3: Page-level authorization
// app/admin/users/page.tsx
import { cookies } from 'next/headers';
import { verifySession } from '@/lib/auth';
import { redirect } from 'next/navigation';

export default async function AdminUsersPage() {
  const token = cookies().get('session-token')?.value;
  const session = await verifySession(token || '');

  // Role-based access control
  if (!session || session.user.role !== 'admin') {
    redirect('/dashboard'); // Not authorized for admin page
  }

  const users = await db.users.findAll();

  return (
    <div>
      <h1>User Management</h1>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id}>
              <td>{u.name}</td>
              <td>{u.role}</td>
              <td>
                <EditUserButton userId={u.id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

```tsx
// BONUS: Reusable auth helper to avoid repeating session checks
// lib/getSession.ts
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifySession } from './auth';
import { cache } from 'react';

// cache() deduplicates calls within a single request
// so calling getRequiredSession() in layout AND page
// only hits the database once
export const getRequiredSession = cache(async () => {
  const token = cookies().get('session-token')?.value;
  const session = token ? await verifySession(token) : null;
  if (!session) redirect('/login');
  return session;
});

// Usage in any Server Component:
// const session = await getRequiredSession();
// session.user is guaranteed to exist
```

Why three layers:
- **Middleware** (edge): Instant redirect for unauthenticated users -- no page rendering wasted
- **Layout** (server): Validates session once for all child pages, fetches user data for sidebar/header
- **Page** (server): Checks specific permissions (admin-only, resource ownership)
- **React.cache**: Deduplicates session lookups so multiple components calling getRequiredSession() only hit the DB once per request'''
    },
    {
        "instruction": r'''My Next.js page fetches data from 3 different APIs. The page takes 3 seconds to load because each API call takes about 1 second and they run sequentially. How do I fix this?''',
        "output": r'''<think>
Three sequential API calls at 1 second each = 3 seconds total. If these calls are independent (none depends on the result of another), they should run in PARALLEL, bringing the total down to ~1 second.

In a Server Component, the common mistake is:
const users = await fetchUsers();
const products = await fetchProducts();
const analytics = await fetchAnalytics();

Each await blocks until the previous one completes. Sequential.

The fix is Promise.all:
const [users, products, analytics] = await Promise.all([
  fetchUsers(),
  fetchProducts(),
  fetchAnalytics(),
]);

This runs all three concurrently and waits for the slowest one. Total time: ~1 second instead of ~3.

But wait, there is a more interesting Next.js-specific approach: streaming with Suspense. Instead of waiting for ALL data before showing anything, you can show the page skeleton immediately and stream in each section as its data arrives.

With Suspense boundaries, the user sees the page instantly with loading states, and each section fills in as its API call completes. This gives the PERCEPTION of a much faster page even if the actual data loading time is the same.

Hmm, should I recommend Promise.all or Suspense streaming? Actually, they are complementary:
- Use Promise.all when all data is needed before rendering anything
- Use Suspense when you can show partial content while the rest loads
- Or combine: Promise.all for related data, Suspense for independent sections

I initially thought Promise.all was the complete answer, but streaming is actually the more important optimization because it improves perceived performance even more than parallelization.

The tradeoff: Promise.all reduces total wait time. Streaming reduces TIME TO FIRST CONTENT (the user sees something immediately). Both are better than sequential awaits.
</think>

Two fixes: parallelize the API calls with Promise.all, and stream partial content with Suspense.

```tsx
// PROBLEM: Sequential fetching -- 3 seconds total
// app/dashboard/page.tsx (SLOW)
export default async function DashboardSlow() {
  const users = await fetchUsers();        // 1 second
  const products = await fetchProducts();  // 1 second (waits for users)
  const analytics = await fetchAnalytics(); // 1 second (waits for products)
  // Total: 3 seconds before ANYTHING renders

  return (
    <div>
      <UserSection users={users} />
      <ProductSection products={products} />
      <AnalyticsSection analytics={analytics} />
    </div>
  );
}
```

```tsx
// FIX 1: Promise.all -- parallel fetching, ~1 second total
export default async function DashboardParallel() {
  // All three run at the same time
  const [users, products, analytics] = await Promise.all([
    fetchUsers(),      // 1 second \
    fetchProducts(),   // 1 second  > All start simultaneously
    fetchAnalytics(),  // 1 second /
  ]);
  // Total: ~1 second (limited by slowest call)

  return (
    <div>
      <UserSection users={users} />
      <ProductSection products={products} />
      <AnalyticsSection analytics={analytics} />
    </div>
  );
}
```

```tsx
// FIX 2: Suspense streaming -- show content as it arrives
// User sees the page IMMEDIATELY with loading skeletons
// Each section fills in independently as its data arrives

import { Suspense } from 'react';

export default function DashboardStreaming() {
  // No await at the page level -- each section fetches its own data
  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      {/* Each Suspense boundary streams independently */}
      <Suspense fallback={<UserSkeleton />}>
        <UserSection />
      </Suspense>

      <Suspense fallback={<ProductSkeleton />}>
        <ProductSection />
      </Suspense>

      <Suspense fallback={<AnalyticsSkeleton />}>
        <AnalyticsSection />
      </Suspense>
    </div>
  );
}

// Each section is its own async Server Component
async function UserSection() {
  const users = await fetchUsers(); // 1 second
  return (
    <section>
      <h2>Users</h2>
      <ul>
        {users.map(u => (
          <li key={u.id}>{u.name}</li>
        ))}
      </ul>
    </section>
  );
}

async function ProductSection() {
  const products = await fetchProducts(); // 1 second
  return (
    <section>
      <h2>Products</h2>
      {products.map(p => (
        <div key={p.id}>{p.name} - ${p.price}</div>
      ))}
    </section>
  );
}

async function AnalyticsSection() {
  const analytics = await fetchAnalytics(); // 1 second
  return (
    <section>
      <h2>Analytics</h2>
      <p>Revenue: ${analytics.revenue}</p>
      <p>Visitors: {analytics.visitors}</p>
    </section>
  );
}

// Skeleton components for loading state
function UserSkeleton() {
  return (
    <section>
      <h2>Users</h2>
      <div className="skeleton" style={{ height: 200 }} />
    </section>
  );
}
```

Timeline comparison:

```
Sequential (SLOW):
  |--users (1s)--|--products (1s)--|--analytics (1s)--|RENDER|
  Total: 3 seconds to first paint

Promise.all (FASTER):
  |--users (1s)-----|
  |--products (1s)--|
  |--analytics (1s)-|RENDER|
  Total: 1 second to first paint

Suspense Streaming (BEST perceived performance):
  |RENDER skeleton immediately|
  |--users (1s)---> stream in|
  |--products (1s)-> stream in|
  |--analytics (1s)> stream in|
  Total: 0 seconds to first paint, 1 second to full content
```

Use **Promise.all** when all data must be present before rendering (e.g., data that depends on each other for calculations). Use **Suspense streaming** when sections are independent and you can show partial content.'''
    },
    {
        "instruction": r'''Should I use Next.js API routes or Server Actions for form submissions in the App Router?''',
        "output": r'''<think>
This is a design question about the two server-side patterns in Next.js App Router.

API Routes (app/api/*/route.ts):
- Traditional REST endpoints
- Handle GET, POST, PUT, DELETE
- Return JSON responses
- Can be called from any client (not just your Next.js app)
- Good for: public APIs, webhooks, third-party integrations

Server Actions:
- Functions that run on the server, called directly from client components
- No need to create an API endpoint
- Work with forms (progressive enhancement -- forms work without JS)
- Integrated with revalidation (revalidatePath/revalidateTag)
- Good for: form submissions, mutations, data updates

Hmm, let me think about when each makes sense.

For a form that creates a blog post: Server Action. You do not need a REST endpoint for an internal form. The action handles validation, database write, and revalidation in one function.

For a payment webhook from Stripe: API Route. Stripe needs a URL to send POST requests to. It cannot call a Server Action.

For an internal dashboard form: Server Action. Simpler, no endpoint management, built-in error handling.

Wait, there is a nuance with Server Actions and error handling. If a Server Action throws, the error propagates to the nearest error boundary. For API routes, you return a response with a status code. The Server Action pattern is more React-like (error boundaries) while the API route pattern is more REST-like (status codes).

I initially thought Server Actions were just a convenience, but they actually enable progressive enhancement -- forms work even without JavaScript enabled. The form's action attribute points to the Server Action, and the browser submits the form as a regular POST request.

The tradeoff: Server Actions are simpler for internal mutations but cannot be called from external services. API Routes are more flexible but require more boilerplate (fetch calls, JSON parsing, status code handling).
</think>

Use Server Actions for form submissions and data mutations. Use API Routes only when external systems need to call your endpoints.

```tsx
// SERVER ACTION approach (recommended for forms)
// app/blog/new/actions.ts
'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { z } from 'zod';

const PostSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  content: z.string().min(10, 'Content must be at least 10 characters'),
  published: z.boolean().optional(),
});

interface ActionResult {
  errors?: Record<string, string[]>;
  message?: string;
}

export async function createPost(
  prevState: ActionResult,
  formData: FormData
): Promise<ActionResult> {
  // Validate input
  const result = PostSchema.safeParse({
    title: formData.get('title'),
    content: formData.get('content'),
    published: formData.get('published') === 'on',
  });

  if (!result.success) {
    return { errors: result.error.flatten().fieldErrors };
  }

  // Write to database
  try {
    const post = await db.posts.create({
      data: result.data,
    });

    // Revalidate the blog listing page cache
    revalidatePath('/blog');

    // Redirect to the new post
    redirect('/blog/' + post.slug);
  } catch (err) {
    return { message: 'Failed to create post. Please try again.' };
  }
}
```

```tsx
// app/blog/new/page.tsx
'use client';

import { useFormState, useFormStatus } from 'react-dom';
import { createPost } from './actions';

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending}>
      {pending ? 'Creating...' : 'Create Post'}
    </button>
  );
}

export default function NewPostPage() {
  const [state, formAction] = useFormState(createPost, {});

  return (
    <form action={formAction}>
      <div>
        <label htmlFor="title">Title</label>
        <input id="title" name="title" type="text" required />
        {state.errors?.title && (
          <p className="error">{state.errors.title[0]}</p>
        )}
      </div>

      <div>
        <label htmlFor="content">Content</label>
        <textarea id="content" name="content" rows={10} required />
        {state.errors?.content && (
          <p className="error">{state.errors.content[0]}</p>
        )}
      </div>

      <label>
        <input name="published" type="checkbox" />
        Publish immediately
      </label>

      {state.message && <p className="error">{state.message}</p>}

      <SubmitButton />
    </form>
  );
}
```

```tsx
// API ROUTE approach -- use ONLY when external services need the endpoint
// app/api/webhooks/stripe/route.ts
import { NextRequest, NextResponse } from 'next/server';
import Stripe from 'stripe';

export async function POST(request: NextRequest) {
  const body = await request.text();
  const signature = request.headers.get('stripe-signature');

  if (!signature) {
    return NextResponse.json(
      { error: 'Missing signature' },
      { status: 400 }
    );
  }

  try {
    const event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );

    switch (event.type) {
      case 'payment_intent.succeeded':
        await handlePaymentSuccess(event.data.object);
        break;
      case 'payment_intent.failed':
        await handlePaymentFailure(event.data.object);
        break;
    }

    return NextResponse.json({ received: true });
  } catch (err) {
    return NextResponse.json(
      { error: 'Webhook verification failed' },
      { status: 400 }
    );
  }
}
```

When to use each:
| Use case | Server Action | API Route |
|---|---|---|
| Form submission | Yes | No |
| Data mutation (create/update/delete) | Yes | No |
| Stripe/payment webhooks | No | Yes |
| Public REST API for mobile apps | No | Yes |
| Third-party integrations | No | Yes |
| File upload from your app | Yes | Possible |
| Authentication callback (OAuth) | No | Yes |'''
    },
]
