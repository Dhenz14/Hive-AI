r"""Thinking-trace pairs: Next.js code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Next.js code and identify issues:

```jsx
// app/products/page.jsx
import { prisma } from '@/lib/prisma';

export default async function ProductsPage({ searchParams }) {
  const category = searchParams.category;
  const sort = searchParams.sort || 'name';
  const page = parseInt(searchParams.page) || 1;

  const products = await prisma.product.findMany({
    where: category ? { category } : {},
    orderBy: { [sort]: 'asc' },
    skip: (page - 1) * 20,
    take: 20,
    include: {
      reviews: true,
      seller: true,
      categories: true,
    },
  });

  const totalProducts = await prisma.product.count({
    where: category ? { category } : {},
  });

  return (
    <div>
      <h1>Products</h1>
      <ProductFilter category={category} />
      <div className="grid">
        {products.map(product => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
      <Pagination total={totalProducts} page={page} pageSize={20} />
    </div>
  );
}

// app/products/[id]/page.jsx
export default async function ProductPage({ params }) {
  const product = await prisma.product.findUnique({
    where: { id: params.id },
    include: {
      reviews: { include: { user: true } },
      seller: true,
      categories: true,
      relatedProducts: true,
    },
  });

  const user = await getCurrentUser();
  const viewCount = await prisma.product.update({
    where: { id: params.id },
    data: { viewCount: { increment: 1 } },
  });

  return (
    <div>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <p>Price: ${product.price}</p>
      <AddToCartButton product={product} />
      <ReviewList reviews={product.reviews} />
      {user && <ReviewForm productId={product.id} />}
    </div>
  );
}

// app/api/products/route.js
import { NextResponse } from 'next/server';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('q');

  const products = await prisma.product.findMany({
    where: {
      OR: [
        { name: { contains: query } },
        { description: { contains: query } },
      ],
    },
  });

  return NextResponse.json(products);
}

export async function POST(request) {
  const data = await request.json();
  const product = await prisma.product.create({ data });
  return NextResponse.json(product, { status: 201 });
}
```''', r'''<think>
Let me review this Next.js App Router code.

1. SSR data fetching issues:
- ProductsPage: The `sort` parameter from searchParams is passed directly to Prisma's orderBy. An attacker can set sort=password or any other column, potentially exposing data order based on sensitive fields. Also, invalid column names will cause a Prisma error.
- page parameter: parseInt(searchParams.page) could be negative or very large. No bounds checking.

2. Over-fetching:
- ProductsPage includes reviews, seller, and categories for every product on the listing page. The product card probably only needs name, price, and image. Including reviews for 20 products (each with potentially hundreds of reviews) is a massive over-fetch.
- ProductPage includes relatedProducts which may recursively include their own relations.

3. Sequential queries:
- ProductsPage makes two sequential queries (findMany then count). These could run in parallel with Promise.all.
- ProductPage has three sequential queries: findUnique, getCurrentUser, and update. All independent and can be parallelized.

4. Write operation in SSR:
- ProductPage does a Prisma update (increment viewCount) during server-side rendering. This means:
  - Every crawler bot increments the view count
  - If the page is cached/static, the view count is not actually updated on every visit
  - Write operations during rendering can cause issues with caching and revalidation

5. API route issues:
- GET handler: No pagination on the search query. Returns ALL matching products.
- POST handler: No authentication. Anyone can create products. No validation on the data.
- POST uses `data` directly from request body, passing it straight to Prisma create. This is mass assignment -- attacker can set any field including id, createdAt, or admin flags.

6. No error handling:
- No try-catch on any database query. A Prisma error (invalid column, connection issue) returns a 500 error page.
- No null check on product in ProductPage. If the product does not exist, product.name crashes.

7. Caching:
- No caching configuration. ProductsPage runs a database query on every request. For high-traffic pages, this creates unnecessary database load.

Let me write the review.
</think>

## Code Review: Next.js App Router Product Pages

### CRITICAL - Security

**SEC1: Unvalidated sort parameter (Severity: CRITICAL)**
```jsx
orderBy: { [sort]: 'asc' }
```
The `sort` parameter from searchParams is used directly as a Prisma column name. An attacker can pass `sort=password` or `sort=internalNotes` to order results by sensitive fields, leaking information through the ordering. Validate against an allowlist:
```jsx
const ALLOWED_SORTS = ['name', 'price', 'createdAt'];
const sortField = ALLOWED_SORTS.includes(sort) ? sort : 'name';
```

**SEC2: API POST has no auth or validation (Severity: CRITICAL)**
```jsx
export async function POST(request) {
  const data = await request.json();
  const product = await prisma.product.create({ data });
}
```
No authentication check and no input validation. Anyone can create products with arbitrary data including setting `id`, `createdAt`, or any other field. Validate input with a schema (e.g., Zod) and require authentication.

### HIGH - Over-Fetching

**OF1: Full review data loaded on listing page (Severity: HIGH)**
```jsx
include: {
  reviews: true,
  seller: true,
  categories: true,
}
```
For 20 products on the listing page, this loads ALL reviews, ALL seller data, and ALL categories. If each product has 100 reviews, that is 2000 review objects loaded just for a product card that likely shows only name, price, and image. Select only needed fields:
```jsx
select: {
  id: true, name: true, price: true, image: true,
  seller: { select: { name: true } },
  _count: { select: { reviews: true } },
}
```

### HIGH - Write During SSR

**WR1: View count incremented during render (Severity: HIGH)**
```jsx
const viewCount = await prisma.product.update({
  where: { id: params.id },
  data: { viewCount: { increment: 1 } },
});
```
Write operations during server-side rendering cause issues:
- Search engine crawlers inflate view counts
- Cached or prerendered pages skip the increment
- Makes the page uncacheable
Move view counting to a client-side API call or a separate analytics endpoint.

### HIGH - No Error Handling

**EH1: Missing null check on product (Severity: HIGH)**
If `params.id` does not match any product, `findUnique` returns null. `product.name` throws TypeError. Add a not-found check:
```jsx
if (!product) notFound();  // from 'next/navigation'
```

**EH2: No try-catch on database queries (Severity: MEDIUM)**
Invalid sort columns, connection timeouts, or Prisma errors return generic 500 pages with no useful feedback.

### MEDIUM - Sequential Queries

**SQ1: Parallelizable queries run sequentially (Severity: MEDIUM)**
ProductsPage:
```jsx
const products = await prisma.product.findMany(...);
const totalProducts = await prisma.product.count(...);
```
These are independent queries. Run in parallel:
```jsx
const [products, totalProducts] = await Promise.all([
  prisma.product.findMany(...),
  prisma.product.count(...),
]);
```
Same for ProductPage: findUnique, getCurrentUser, and update can all run in parallel.

### MEDIUM - No Caching

**NC1: Database hit on every request (Severity: MEDIUM)**
High-traffic product listing pages query the database on every request. Use Next.js caching:
```jsx
export const revalidate = 60; // revalidate every 60 seconds
```
Or use `unstable_cache` for granular control.

### LOW - Missing Pagination on API Search

**PG1: Search returns all results (Severity: LOW)**
The GET API handler returns all matching products with no limit. A broad search could return thousands of results. Add pagination parameters.'''),

    ("thinking/code-review", r'''Review this Next.js code and identify issues:

```jsx
// middleware.ts
import { NextResponse } from 'next/server';

export function middleware(request) {
  const token = request.cookies.get('auth-token')?.value;
  const path = request.nextUrl.pathname;

  if (path.startsWith('/admin') && !token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  if (path.startsWith('/api/admin') && !token) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const response = NextResponse.next();
  response.headers.set('X-Custom-Header', 'value');
  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};

// app/admin/layout.jsx
import { cookies } from 'next/headers';
import jwt from 'jsonwebtoken';

export default async function AdminLayout({ children }) {
  const cookieStore = cookies();
  const token = cookieStore.get('auth-token')?.value;

  let user = null;
  if (token) {
    user = jwt.verify(token, process.env.JWT_SECRET);
  }

  if (!user || user.role !== 'admin') {
    redirect('/login');
  }

  return (
    <div className="admin-layout">
      <AdminSidebar user={user} />
      <main>{children}</main>
    </div>
  );
}

// app/admin/users/page.jsx
export default async function AdminUsersPage() {
  const users = await prisma.user.findMany({
    select: {
      id: true,
      name: true,
      email: true,
      role: true,
      password: true,
      createdAt: true,
    },
  });

  return (
    <div>
      <h1>Users</h1>
      <UserTable users={users} />
    </div>
  );
}

// components/UserTable.jsx
'use client';
import { useState } from 'react';

export default function UserTable({ users }) {
  const [sortedUsers, setSortedUsers] = useState(users);

  const deleteUser = async (userId) => {
    await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
    setSortedUsers(sortedUsers.filter(u => u.id !== userId));
  };

  return (
    <table>
      <thead>
        <tr>
          <th>Name</th><th>Email</th><th>Role</th><th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {sortedUsers.map(user => (
          <tr key={user.id}>
            <td>{user.name}</td>
            <td>{user.email}</td>
            <td>{user.role}</td>
            <td>
              <button onClick={() => deleteUser(user.id)}>Delete</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```''', r'''<think>
Let me review this Next.js admin panel code.

1. Password in user data:
- AdminUsersPage selects `password: true` from the database. This sends hashed passwords to the client component UserTable via server component props. Even though UserTable does not display the password, the data is serialized to the client in the RSC payload, visible in the network tab.

2. Middleware authentication is weak:
- The middleware only checks if the auth-token cookie EXISTS, not if it is valid. An attacker can set any value for auth-token and pass the middleware check.
- The actual JWT verification happens in the layout. But middleware lets requests through with invalid tokens, potentially allowing access to API routes that do not have their own auth checks.

3. JWT verification without error handling:
- jwt.verify(token, process.env.JWT_SECRET) throws if the token is expired, malformed, or the signature is invalid. This error is not caught, causing the admin layout to crash with a 500 error instead of redirecting to login.

4. Security headers:
- The middleware sets a custom header on ALL requests (the matcher is very broad). But it does not set security headers like CSP, X-Frame-Options, etc.

5. Client-side delete without server revalidation:
- deleteUser makes a DELETE request but only updates local state. The server-side data (from the server component) is now stale. On page refresh, the deleted user may reappear if the server data is cached.
- No confirmation before delete. No error handling.

6. Middleware and layout auth duplication:
- Auth is checked in both middleware (cookie exists) and layout (JWT verification). This is redundant but incomplete -- middleware does not verify, layout does. If middleware is bypassed (misconfigured matcher), unauthenticated requests reach the layout.

7. Missing redirect import:
- AdminLayout uses redirect('/login') but does not import it from 'next/navigation'.

Let me write the review.
</think>

## Code Review: Next.js Admin Panel

### CRITICAL - Password Leaked to Client

**PW1: Hashed passwords sent to browser (Severity: CRITICAL)**
```jsx
select: {
  password: true,  // hashed passwords selected
}
```
AdminUsersPage selects passwords from the database. This data is passed as props to the client component UserTable. Even though the password column is not rendered, it is included in the React Server Components payload visible in the browser's network tab. Remove it:
```jsx
select: {
  id: true, name: true, email: true, role: true, createdAt: true,
  // DO NOT include password
}
```

### HIGH - Middleware Auth is Token-Existence Only

**MW1: No token validation in middleware (Severity: HIGH)**
```jsx
if (path.startsWith('/admin') && !token) {
  return NextResponse.redirect(new URL('/login', request.url));
}
```
The middleware only checks if the cookie exists, not if its value is a valid JWT. An attacker can set `auth-token=anything` and pass the middleware check. Validate the token in middleware or remove the false sense of security:
```jsx
try {
  jwt.verify(token, process.env.JWT_SECRET);
} catch {
  return NextResponse.redirect(new URL('/login', request.url));
}
```

### HIGH - JWT Verify Crashes on Invalid Token

**JWT1: Uncaught exception in layout (Severity: HIGH)**
```jsx
user = jwt.verify(token, process.env.JWT_SECRET);
```
If the token is expired, malformed, or tampered with, `jwt.verify` throws. The admin layout crashes with a 500 error instead of redirecting to login. Wrap in try-catch:
```jsx
try {
  user = jwt.verify(token, process.env.JWT_SECRET);
} catch {
  user = null;
}
if (!user || user.role !== 'admin') {
  redirect('/login');
}
```

### HIGH - Client-Side Delete Without Revalidation

**RV1: Server data becomes stale after delete (Severity: HIGH)**
```jsx
const deleteUser = async (userId) => {
  await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
  setSortedUsers(sortedUsers.filter(u => u.id !== userId));
};
```
The client removes the user from local state, but the server component's data is cached. On page refresh or navigation, the deleted user may reappear. Use `router.refresh()` to revalidate server data, or use `revalidatePath` in the API route.

Also, no error handling or confirmation dialog before deleting a user.

### MEDIUM - Missing Import

**MI1: redirect not imported (Severity: MEDIUM)**
`redirect('/login')` is used but not imported. This will throw a ReferenceError. Add:
```jsx
import { redirect } from 'next/navigation';
```

### MEDIUM - Duplicate Auth Logic

**DA1: Auth checked in middleware and layout separately (Severity: MEDIUM)**
Authentication is partially checked in middleware (cookie exists) and fully checked in the layout (JWT verified). This split creates confusion about where auth is enforced. If a new admin page forgets to use AdminLayout, it has only the weak middleware check. Centralize JWT verification in middleware for all admin routes.

### LOW - Missing Security Headers

**SH1: No security headers set (Severity: LOW)**
The middleware sets a custom header but misses standard security headers. Add at minimum:
```jsx
response.headers.set('X-Frame-Options', 'DENY');
response.headers.set('X-Content-Type-Options', 'nosniff');
response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
```

### LOW - Delete Stale Closure

**SC1: sortedUsers may be stale (Severity: LOW)**
```jsx
setSortedUsers(sortedUsers.filter(u => u.id !== userId));
```
If multiple deletes happen rapidly, the `sortedUsers` reference is stale. Use functional updater:
```jsx
setSortedUsers(prev => prev.filter(u => u.id !== userId));
```'''),

    ("thinking/code-review", r'''Review this Next.js code and identify issues:

```jsx
// app/api/upload/route.js
import { writeFile } from 'fs/promises';
import { join } from 'path';

export async function POST(request) {
  const formData = await request.formData();
  const file = formData.get('file');
  const buffer = Buffer.from(await file.arrayBuffer());
  const filename = file.name;
  const filepath = join(process.cwd(), 'public', 'uploads', filename);
  await writeFile(filepath, buffer);
  return Response.json({ url: `/uploads/${filename}` });
}

// app/api/data/route.js
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const callback = searchParams.get('callback');
  const data = await fetchData();

  if (callback) {
    return new Response(`${callback}(${JSON.stringify(data)})`, {
      headers: { 'Content-Type': 'application/javascript' },
    });
  }

  return Response.json(data);
}

// app/api/proxy/route.js
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const targetUrl = searchParams.get('url');
  const response = await fetch(targetUrl);
  const data = await response.text();
  return new Response(data, {
    headers: { 'Content-Type': response.headers.get('Content-Type') },
  });
}

// app/api/webhook/route.js
export async function POST(request) {
  const payload = await request.json();
  await prisma.event.create({ data: payload });
  // Process in background
  processWebhook(payload);
  return Response.json({ received: true });
}

// app/api/export/route.js
export async function GET(request) {
  const users = await prisma.user.findMany();
  const csv = users.map(u => `${u.name},${u.email},${u.phone}`).join('\n');
  return new Response(csv, {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': 'attachment; filename=users.csv',
    },
  });
}
```''', r'''<think>
Let me review these Next.js API routes for security issues.

1. Upload route - multiple critical issues:
- Path traversal: filename comes from the client. A filename like "../../../etc/cron.d/backdoor" writes outside the uploads directory. Must sanitize the filename.
- No file type validation. Any file type can be uploaded including executables, HTML files (XSS), or server-side scripts.
- No file size limit. A single request can upload arbitrarily large files.
- Filename collision: if two users upload "photo.jpg", the second overwrites the first.
- Writing to public/ means the file is immediately served statically. An uploaded HTML file with JavaScript can execute XSS.

2. Data route - JSONP XSS:
- The callback parameter is injected directly into a JavaScript response. If callback contains malicious code like `alert(1)//`, the response becomes `alert(1)//({"data":...})` which executes arbitrary JavaScript. This is a reflected XSS vulnerability via JSONP injection.

3. Proxy route - SSRF:
- targetUrl comes from the client with no validation. An attacker can make the server fetch internal services: `?url=http://169.254.169.254/latest/meta-data/` (AWS metadata), `?url=http://localhost:6379/` (Redis), etc. This is Server-Side Request Forgery.
- Also proxies the response directly, including potentially malicious content.

4. Webhook route:
- No signature verification. Anyone can send fake webhook events. Most webhook providers (Stripe, GitHub) include a signature header that must be verified.
- processWebhook runs "in the background" but in a serverless environment (Vercel), the function execution ends after the response is sent. processWebhook may be killed mid-execution.
- `data: payload` passes raw webhook data directly to Prisma create -- mass assignment.

5. Export route:
- No authentication. Anyone can download all user data (names, emails, phones).
- No CSV escaping. If a user's name contains a comma or newline, the CSV is malformed. If it contains `=`, `+`, or `@`, it is a CSV injection vulnerability that can execute formulas in Excel.
- Loads ALL users into memory. For large databases, this causes OOM.

Let me write the review.
</think>

## Code Review: Next.js API Routes

### CRITICAL - Path Traversal in Upload

**PT1: Filename from client used directly (Severity: CRITICAL)**
```jsx
const filename = file.name;
const filepath = join(process.cwd(), 'public', 'uploads', filename);
```
An attacker can upload with filename `../../../.env` to overwrite the environment file, or `../../pages/evil.html` to inject an XSS page. Sanitize the filename:
```jsx
import { randomUUID } from 'crypto';
import path from 'path';

const ext = path.extname(file.name).toLowerCase();
const ALLOWED_EXTENSIONS = ['.jpg', '.png', '.gif', '.pdf'];
if (!ALLOWED_EXTENSIONS.includes(ext)) {
  return Response.json({ error: 'Invalid file type' }, { status: 400 });
}
const filename = `${randomUUID()}${ext}`;
```

### CRITICAL - SSRF in Proxy Route

**SSRF1: Unrestricted URL fetch (Severity: CRITICAL)**
```jsx
const targetUrl = searchParams.get('url');
const response = await fetch(targetUrl);
```
An attacker can make the server fetch internal resources:
- `?url=http://169.254.169.254/latest/meta-data/` -- AWS instance credentials
- `?url=http://localhost:6379/INFO` -- Redis server info
- `?url=file:///etc/passwd` -- local files (depending on fetch implementation)

Either remove this endpoint or implement strict URL validation:
```jsx
const parsed = new URL(targetUrl);
if (!['http:', 'https:'].includes(parsed.protocol)) {
  return Response.json({ error: 'Invalid protocol' }, { status: 400 });
}
const BLOCKED = ['localhost', '127.0.0.1', '169.254.169.254', '10.', '172.16.', '192.168.'];
if (BLOCKED.some(b => parsed.hostname.startsWith(b))) {
  return Response.json({ error: 'Blocked host' }, { status: 403 });
}
```

### CRITICAL - JSONP XSS

**XSS1: Unsanitized callback parameter (Severity: CRITICAL)**
```jsx
return new Response(`${callback}(${JSON.stringify(data)})`, {
  headers: { 'Content-Type': 'application/javascript' },
});
```
If `callback=alert(document.cookie)//`, the response executes arbitrary JavaScript. Validate the callback name:
```jsx
if (!/^[a-zA-Z_$][a-zA-Z0-9_$]*$/.test(callback)) {
  return Response.json({ error: 'Invalid callback' }, { status: 400 });
}
```
Better yet, remove JSONP support entirely and use CORS headers instead.

### HIGH - Unauthenticated Data Export

**EX1: User data downloadable by anyone (Severity: HIGH)**
The export endpoint returns all user names, emails, and phone numbers with no authentication. This is a data breach waiting to happen. Add authentication and authorization checks.

**EX2: CSV injection (Severity: HIGH)**
```jsx
const csv = users.map(u => `${u.name},${u.email},${u.phone}`).join('\n');
```
If a user's name is `=HYPERLINK("http://evil.com","Click")`, this executes as a formula when opened in Excel. Escape fields:
```jsx
const escapeCSV = (value) => {
  const str = String(value ?? '');
  if (/[,"\n\r=+\-@]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};
```

### HIGH - Unverified Webhook

**WH1: No signature verification (Severity: HIGH)**
```jsx
const payload = await request.json();
await prisma.event.create({ data: payload });
```
Anyone can send fake webhook events. Verify the signature:
```jsx
const signature = request.headers.get('x-webhook-signature');
const isValid = verifySignature(payload, signature, WEBHOOK_SECRET);
if (!isValid) return Response.json({ error: 'Invalid signature' }, { status: 401 });
```

**WH2: Background processing killed in serverless (Severity: HIGH)**
`processWebhook(payload)` runs after the response is sent. In serverless environments (Vercel, AWS Lambda), the function is frozen after the response, potentially killing the background work. Use a queue or `waitUntil` in edge runtime.

### MEDIUM - No Upload Limits

**UL1: No file size or type restrictions (Severity: MEDIUM)**
The upload accepts files of any size and type. An attacker can exhaust disk space or upload executable content. Set limits in Next.js config:
```jsx
export const config = { api: { bodyParser: { sizeLimit: '5mb' } } };
```'''),

    ("thinking/code-review", r'''Review this Next.js code and identify issues:

```jsx
// app/layout.jsx
import { Inter } from 'next/font/google';
import { headers } from 'next/headers';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'My App',
  description: 'A Next.js application',
};

export default async function RootLayout({ children }) {
  const headersList = headers();
  const userAgent = headersList.get('user-agent');
  const isMobile = /mobile/i.test(userAgent);

  return (
    <html lang="en">
      <body className={inter.className}>
        <script dangerouslySetInnerHTML={{
          __html: `window.__ENV__ = ${JSON.stringify({
            API_URL: process.env.API_URL,
            STRIPE_KEY: process.env.STRIPE_SECRET_KEY,
            DB_URL: process.env.DATABASE_URL,
          })}`
        }} />
        <Navbar isMobile={isMobile} />
        {children}
      </body>
    </html>
  );
}

// app/dashboard/page.jsx
import { unstable_cache } from 'next/cache';

const getStats = unstable_cache(
  async () => {
    const stats = await prisma.order.aggregate({
      _sum: { total: true },
      _count: true,
    });
    return stats;
  },
  ['dashboard-stats'],
  { revalidate: 3600 }
);

export default async function DashboardPage() {
  const stats = await getStats();
  const recentOrders = await prisma.order.findMany({
    orderBy: { createdAt: 'desc' },
    take: 10,
    include: { user: true, items: { include: { product: true } } },
  });

  return (
    <div>
      <h1>Dashboard</h1>
      <StatsCards stats={stats} />
      <RecentOrders orders={recentOrders} />
    </div>
  );
}

// app/dashboard/loading.jsx
export default function Loading() {
  return <div>Loading dashboard...</div>;
}

// app/dashboard/error.jsx
'use client';
export default function Error({ error, reset }) {
  return (
    <div>
      <h2>Something went wrong!</h2>
      <p>{error.message}</p>
      <p>{error.stack}</p>
      <button onClick={() => reset()}>Try again</button>
    </div>
  );
}
```''', r'''<think>
Let me review this Next.js code.

1. Critical secret exposure:
- The script tag in RootLayout serializes environment variables to the client:
  - STRIPE_SECRET_KEY -- this is the SECRET key, not the publishable key. Exposing this gives full access to the Stripe account.
  - DATABASE_URL -- the database connection string with credentials is exposed to every user.
  - API_URL is probably fine if it is a public URL.
- This is a catastrophic security vulnerability. Server-side secrets must NEVER be sent to the client.

2. Error page leaks stack trace:
- error.jsx displays error.message AND error.stack. In production, this can expose internal file paths, code structure, and sensitive information. Only show generic error messages.

3. User-agent detection in root layout:
- Calling headers() in the root layout makes the ENTIRE application dynamic (opt out of static generation). This affects every page under this layout, even pages that could be statically generated. User-agent detection should be done client-side or in specific pages that need it.

4. Caching inconsistency:
- getStats is cached for 1 hour. But recentOrders is NOT cached -- it runs a fresh query on every request. The dashboard shows stale stats (up to 1 hour old) next to fresh recent orders. This inconsistency can be confusing.
- recentOrders includes user and items with products. This is a lot of data for 10 orders.

5. dangerouslySetInnerHTML for env vars:
- Beyond the secret exposure, using JSON.stringify with user-controllable data in a script tag can enable XSS if any env var contains `</script>`. Should use proper escaping.

6. Loading and error boundaries:
- loading.jsx is very basic -- no skeleton UI or meaningful feedback.
- error.jsx has no logging. Errors are only shown to the user.

Let me write the review.
</think>

## Code Review: Next.js Layout, Caching, and Error Handling

### CRITICAL - Server Secrets Exposed to Client

**SEC1: Secret keys in client-side JavaScript (Severity: CRITICAL)**
```jsx
<script dangerouslySetInnerHTML={{
  __html: `window.__ENV__ = ${JSON.stringify({
    STRIPE_KEY: process.env.STRIPE_SECRET_KEY,
    DB_URL: process.env.DATABASE_URL,
  })}`
}} />
```
**STRIPE_SECRET_KEY** and **DATABASE_URL** (with database credentials) are serialized into the HTML sent to every user. Anyone viewing page source can:
- Access the Stripe account (create charges, refund orders, read customer data)
- Connect directly to the database with full credentials

Remove immediately. Only expose public keys prefixed with `NEXT_PUBLIC_`:
```jsx
// Only safe for client:
window.__ENV__ = {
  API_URL: process.env.NEXT_PUBLIC_API_URL,
  STRIPE_KEY: process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
}
```

### CRITICAL - Stack Trace in Error Page

**ERR1: Full stack trace shown to users (Severity: HIGH)**
```jsx
<p>{error.message}</p>
<p>{error.stack}</p>
```
The error page displays the full stack trace, exposing internal file paths, code structure, and potentially sensitive information. Show only a generic message:
```jsx
export default function Error({ error, reset }) {
  // Log the error server-side
  useEffect(() => {
    reportError(error);
  }, [error]);

  return (
    <div>
      <h2>Something went wrong</h2>
      <p>We have been notified and are looking into it.</p>
      <button onClick={() => reset()}>Try again</button>
    </div>
  );
}
```

### HIGH - Root Layout Forces Dynamic Rendering

**DYN1: headers() call makes entire app dynamic (Severity: HIGH)**
```jsx
export default async function RootLayout({ children }) {
  const headersList = headers();
```
Calling `headers()` in the root layout opts the entire application out of static generation. Every page becomes dynamically rendered, even those that could be fully static. Move user-agent detection to:
- A client component using `navigator.userAgent`
- A middleware that sets a cookie or header
- Individual pages that need the information

### MEDIUM - Caching Inconsistency

**CC1: Stats cached, orders not cached (Severity: MEDIUM)**
`getStats` is cached for 1 hour. `recentOrders` queries fresh on every request. Users see stale aggregate stats alongside fresh order data. Either:
- Cache both with the same revalidation interval
- Do not cache stats (if freshness matters)
- Clearly label stats as "last updated X minutes ago"

### MEDIUM - Script Tag XSS Risk

**XSS1: JSON.stringify in script tag (Severity: MEDIUM)**
```jsx
__html: `window.__ENV__ = ${JSON.stringify({...})}`
```
If any environment variable contains `</script>`, the script tag is closed prematurely, enabling XSS. Even after removing secrets, properly escape the JSON:
```jsx
const json = JSON.stringify(env).replace(/</g, '\\u003c');
```

### LOW - Loading State

**LS1: Basic loading component (Severity: LOW)**
`Loading dashboard...` as plain text provides poor UX. Use skeleton components that match the dashboard layout to reduce perceived loading time.'''),

    ("thinking/code-review", r'''Review this Next.js code and identify issues:

```jsx
// next.config.js
const nextConfig = {
  images: {
    domains: ['*'],
  },
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: '*' },
          { key: 'Access-Control-Allow-Headers', value: '*' },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/v2/:path*',
        destination: `${process.env.BACKEND_URL}/api/:path*`,
      },
    ];
  },
  webpack: (config) => {
    config.resolve.fallback = { fs: false, net: false, tls: false };
    return config;
  },
  output: 'standalone',
  experimental: {
    serverActions: true,
  },
};

module.exports = nextConfig;

// app/actions.js
'use server';
import { prisma } from '@/lib/prisma';
import { revalidatePath } from 'next/cache';

export async function createProduct(formData) {
  const name = formData.get('name');
  const price = parseFloat(formData.get('price'));
  const description = formData.get('description');
  const category = formData.get('category');

  await prisma.product.create({
    data: { name, price, description, category },
  });

  revalidatePath('/products');
}

export async function deleteProduct(productId) {
  await prisma.product.delete({ where: { id: productId } });
  revalidatePath('/products');
}

export async function updateUserProfile(formData) {
  const userId = formData.get('userId');
  const name = formData.get('name');
  const email = formData.get('email');
  const role = formData.get('role');

  await prisma.user.update({
    where: { id: userId },
    data: { name, email, role },
  });

  revalidatePath('/profile');
}

export async function searchProducts(query) {
  const products = await prisma.product.findMany({
    where: {
      OR: [
        { name: { contains: query, mode: 'insensitive' } },
        { description: { contains: query, mode: 'insensitive' } },
      ],
    },
    take: 20,
  });
  return products;
}
```''', r'''<think>
Let me review this Next.js config and server actions.

1. CORS configuration:
- Access-Control-Allow-Origin: '*' allows any website to make requests to the API. Combined with Allow-Methods: '*' and Allow-Headers: '*', this completely disables CORS protection. Any malicious website can call these API endpoints.
- This is especially dangerous if the API uses cookies for authentication -- the browser will include cookies in cross-origin requests.

2. Image domains:
- `domains: ['*']` allows loading images from ANY domain. This can be exploited for SSRF (the Next.js image optimization proxy fetches from attacker-controlled URLs) and can consume server resources optimizing malicious images.

3. Server Actions -- no authentication:
- createProduct has no auth check. Anyone can create products.
- deleteProduct has no auth check. Anyone can delete any product.
- updateUserProfile accepts userId from the form data! A user can change another user's profile by submitting a different userId. The role field is also editable from the form, allowing privilege escalation.

4. Input validation:
- createProduct: no validation on name, description. parseFloat('abc') returns NaN.
- updateUserProfile: userId from form data is not verified against the authenticated user.
- searchProducts: query is user-provided. While Prisma parameterizes queries (no SQL injection), there's no length limit or sanitization.

5. Rewrite proxy:
- The /api/v2/ rewrite proxies to BACKEND_URL. If BACKEND_URL is not set, this could proxy to undefined or empty, causing errors. The rewrite also does not forward authentication headers.

6. Webpack config:
- Setting fs, net, tls to false suppresses build errors but may cause runtime crashes if server-side code tries to use these modules.

7. Server actions returning data:
- searchProducts returns Prisma objects directly. These may contain internal fields or be larger than necessary for the client.

Let me write the review.
</think>

## Code Review: Next.js Config and Server Actions

### CRITICAL - Privilege Escalation in Server Actions

**PE1: updateUserProfile trusts client-supplied userId (Severity: CRITICAL)**
```jsx
export async function updateUserProfile(formData) {
  const userId = formData.get('userId');
  const role = formData.get('role');
  await prisma.user.update({
    where: { id: userId },
    data: { name, email, role },
  });
}
```
The userId comes from the form, so any user can modify any other user's profile. The `role` field is also updatable, allowing a regular user to set `role: 'admin'`. Fix: Get userId from the authenticated session and disallow role updates:
```jsx
export async function updateUserProfile(formData) {
  const session = await getServerSession();
  if (!session) throw new Error('Unauthorized');
  await prisma.user.update({
    where: { id: session.user.id },
    data: {
      name: formData.get('name'),
      email: formData.get('email'),
      // DO NOT allow role changes from user form
    },
  });
}
```

**PE2: deleteProduct has no auth check (Severity: CRITICAL)**
Anyone can call `deleteProduct(anyId)` from the client. Server actions are accessible as HTTP endpoints. Add authentication and authorization.

### CRITICAL - CORS Allows Everything

**CORS1: Wildcard CORS on all API routes (Severity: CRITICAL)**
```jsx
{ key: 'Access-Control-Allow-Origin', value: '*' },
{ key: 'Access-Control-Allow-Methods', value: '*' },
{ key: 'Access-Control-Allow-Headers', value: '*' },
```
Any website can call your API endpoints with any method and headers. If the API uses cookie-based auth, this enables cross-site request attacks. Restrict to known origins:
```jsx
{ key: 'Access-Control-Allow-Origin', value: process.env.FRONTEND_URL },
```

### HIGH - Image Domain Wildcard

**IMG1: Any domain allowed for image optimization (Severity: HIGH)**
```jsx
images: { domains: ['*'] }
```
The Next.js image optimization endpoint (`/_next/image`) acts as a proxy. With wildcard domains, an attacker can use your server to:
- Fetch from internal IP addresses (SSRF)
- Consume server CPU/memory with malicious images
- Proxy content through your domain

Specify exact allowed domains:
```jsx
images: { domains: ['cdn.example.com', 'images.example.com'] }
```

### HIGH - No Server Action Authentication

**SA1: createProduct accessible to everyone (Severity: HIGH)**
Server actions are exposed as POST endpoints. Without authentication, anyone can create products. Add session checks to all mutation server actions:
```jsx
export async function createProduct(formData) {
  const session = await getServerSession();
  if (!session || session.user.role !== 'admin') {
    throw new Error('Forbidden');
  }
  // ... validation and creation
}
```

### MEDIUM - Input Validation

**IV1: No validation on server action inputs (Severity: MEDIUM)**
`parseFloat(formData.get('price'))` returns NaN for invalid input. No minimum/maximum bounds, no name length check. Use Zod:
```jsx
import { z } from 'zod';
const schema = z.object({
  name: z.string().min(1).max(200),
  price: z.number().positive().max(999999),
  description: z.string().max(5000),
  category: z.string(),
});
const validated = schema.parse({
  name, price, description, category,
});
```

### LOW - Backend Proxy

**BP1: Rewrite may fail if BACKEND_URL unset (Severity: LOW)**
The rewrite destination uses `process.env.BACKEND_URL`. If this is undefined at build time, the rewrite produces invalid URLs. Add validation or a fallback in the config.'''),
]
