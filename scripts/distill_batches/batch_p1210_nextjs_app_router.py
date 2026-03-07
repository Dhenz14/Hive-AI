"""
Batch P1210 -- Next.js App Router: server components, server actions,
route handlers, middleware, parallel routes.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: server components vs client components ---
    {
        "instruction": r'''When should I use React Server Components vs Client Components in Next.js App Router? What are the rules and gotchas?''',
        "output": r'''<think>
Server Components (default) run only on the server -- direct DB access,
zero client JS. Client Components ("use client") run in the browser --
hooks, event handlers, browser APIs. Key rules: "use client" marks the
boundary, server can import client but not vice versa, props crossing
the boundary must be serializable. Push "use client" as deep as possible.
</think>

Components are Server Components by default. Add `"use client"` only for interactivity:

```typescript
// Server Component (default) -- ships ZERO JS to client
import { db } from "@/lib/database";

async function ProductList({ categoryId }: { categoryId: string }) {
  const products = await db.query(
    "SELECT * FROM products WHERE category_id = $1", [categoryId]
  );
  return (
    <ul>
      {products.map((p: any) => (
        <li key={p.id}>
          {p.name} - ${p.price}
          <AddToCartButton productId={p.id} />
        </li>
      ))}
    </ul>
  );
}

// Client Component -- needs interactivity
// AddToCartButton.tsx
"use client";
import { useState } from "react";

function AddToCartButton({ productId }: { productId: string }) {
  const [added, setAdded] = useState(false);
  return (
    <button onClick={() => setAdded(true)}>
      {added ? "Added" : "Add to Cart"}
    </button>
  );
}

// "Donut pattern" -- server children inside client wrapper
// layout.tsx (server component)
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>  {/* "use client" */}
      <Sidebar />      {/* stays server -- passed as children */}
      {children}
    </SidebarProvider>
  );
}
```

Decision checklist: need hooks/events/browser APIs --> `"use client"`. Fetching data or rendering static HTML --> Server Component. Props crossing the boundary must be JSON-serializable (no functions, Date objects, or class instances).'''
    },

    # --- 2. direct: server actions ---
    {
        "instruction": r'''How do Next.js Server Actions work? Show form handling with validation and error handling.''',
        "output": r'''Server Actions are async functions running on the server, called directly from forms:

```typescript
// app/actions/user.ts
"use server";
import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

const Schema = z.object({
  name: z.string().min(1, "Required").max(100),
  email: z.string().email("Invalid email"),
});

interface ActionResult {
  success: boolean;
  errors?: Record<string, string[]>;
  message?: string;
}

export async function createUser(
  prev: ActionResult | null, formData: FormData
): Promise<ActionResult> {
  const parsed = Schema.safeParse({
    name: formData.get("name"),
    email: formData.get("email"),
  });
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors };
  }
  try {
    // await db.insert(parsed.data);
  } catch {
    return { success: false, message: "Email already exists" };
  }
  revalidatePath("/users");
  redirect("/users");
}

// app/users/new/page.tsx
"use client";
import { useActionState } from "react";
import { createUser } from "@/app/actions/user";

export default function NewUserPage() {
  const [state, action, isPending] = useActionState(createUser, null);
  return (
    <form action={action}>
      <input name="name" placeholder="Name" />
      {state?.errors?.name && <p>{state.errors.name[0]}</p>}
      <input name="email" type="email" placeholder="Email" />
      {state?.errors?.email && <p>{state.errors.email[0]}</p>}
      {state?.message && <p>{state.message}</p>}
      <button disabled={isPending}>{isPending ? "Creating..." : "Create"}</button>
    </form>
  );
}
```

Server Actions support progressive enhancement (work without JS), integrate with `revalidatePath`/`revalidateTag`, and are POST requests under the hood.'''
    },

    # --- 3. direct: route handlers ---
    {
        "instruction": r'''Show how to build REST API route handlers in Next.js App Router with TypeScript typing and error handling.''',
        "output": r'''Route handlers use Web standard `Request`/`Response` in `route.ts` files:

```typescript
// app/api/users/route.ts
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

const Body = z.object({ name: z.string().min(1), email: z.string().email() });

export async function GET(request: NextRequest) {
  const role = request.nextUrl.searchParams.get("role");
  const users = [
    { id: "1", name: "Alice", role: "admin" },
    { id: "2", name: "Bob", role: "user" },
  ].filter((u) => !role || u.role === role);
  return NextResponse.json({ users });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = Body.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 }
      );
    }
    const user = { id: crypto.randomUUID(), ...parsed.data };
    return NextResponse.json(user, { status: 201 });
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
}

// app/api/users/[id]/route.ts -- dynamic segment
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  if (!id.match(/^[a-f0-9-]{36}$/)) {
    return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
  }
  return NextResponse.json({ id, name: "Alice" });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return new NextResponse(null, { status: 204 });
}
```

Route handlers support GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS and run on Edge or Node.js runtime.'''
    },

    # --- 4. thinking: middleware ---
    {
        "instruction": r'''How does Next.js middleware work? Show authentication, redirects, and request rewriting patterns.''',
        "output": r'''<think>
Next.js middleware runs before every request at the edge. Single file
middleware.ts at project root. Key constraints: Edge Runtime only (no
fs, no Node APIs), cannot modify response body, only redirect/rewrite/
set headers. Use matcher to skip static assets.
</think>

Middleware (`middleware.ts` at project root) runs on every request before routing:

```typescript
import { NextRequest, NextResponse } from "next/server";

const protectedPaths = ["/dashboard", "/settings", "/api/protected"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("session-token")?.value;

  // Auth: redirect unauthenticated users
  if (protectedPaths.some((p) => pathname.startsWith(p)) && !token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("returnTo", pathname);
    return NextResponse.redirect(login);
  }

  // Already logged in -- redirect away from login
  if (pathname === "/login" && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // A/B test via URL rewrite (invisible to user)
  if (pathname === "/pricing") {
    const bucket = request.cookies.get("ab-bucket")?.value;
    if (bucket === "b") {
      return NextResponse.rewrite(new URL("/pricing-b", request.url));
    }
  }

  // Security headers
  const response = NextResponse.next();
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|webp)$).*)",
  ],
};
```

Constraints: Edge Runtime only (no `fs`). Cannot modify response body -- only redirect, rewrite, or set headers. Use `matcher` to skip static assets.'''
    },

    # --- 5. direct: parallel routes ---
    {
        "instruction": r'''Explain Next.js parallel routes and intercepting routes with practical examples.''',
        "output": r'''Parallel routes render multiple pages in the same layout using named slots (`@slotName` folders):

```
app/
  layout.tsx           # receives slots as props
  @sidebar/page.tsx    # sidebar slot
  @modal/default.tsx   # no modal active
  @modal/(.)photo/[id]/page.tsx  # intercepted modal
  photo/[id]/page.tsx  # full page view
```

```typescript
// app/layout.tsx -- receives named slots
export default function Layout({
  children, sidebar, modal,
}: {
  children: React.ReactNode;
  sidebar: React.ReactNode;
  modal: React.ReactNode;
}) {
  return (
    <div className="flex">
      <aside className="w-64">{sidebar}</aside>
      <main className="flex-1">{children}</main>
      {modal}
    </div>
  );
}

// app/@modal/default.tsx -- no modal
export default function ModalDefault() { return null; }

// app/@modal/(.)photo/[id]/page.tsx -- intercepted (modal view)
import { Modal } from "@/components/modal";
export default async function PhotoModal({
  params,
}: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Modal><img src={`/photos/${id}.jpg`} alt={id} /></Modal>;
}

// app/photo/[id]/page.tsx -- full page (direct URL or refresh)
export default async function PhotoPage({
  params,
}: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div><img src={`/photos/${id}.jpg`} alt={id} /><h1>Photo {id}</h1></div>;
}
```

Parallel routes enable independent loading/error states per slot. Intercepting routes (`(.)`, `(..)`) show modals on soft navigation while preserving the full page for direct URLs.'''
    },
]
