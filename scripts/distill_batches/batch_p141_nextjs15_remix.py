"""Next.js 15 and Remix/React Router v7 — 2026 React meta-frameworks."""

PAIRS = [
    (
        "frontend/nextjs-15-app-router",
        "Show Next.js 15 App Router patterns: server components, server actions, streaming, PPR, and caching.",
        '''Next.js 15 App Router patterns:

```typescript
// --- Server Components (default in App Router) ---

// app/users/page.tsx — Server Component (no "use client")
import { Suspense } from "react";
import { UserList } from "./user-list";
import { UserListSkeleton } from "./skeleton";

// This runs on the server — can directly access DB, env vars, etc.
export default async function UsersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const { q, page } = await searchParams;

  return (
    <div>
      <h1>Users</h1>
      <SearchBar defaultValue={q} />
      <Suspense fallback={<UserListSkeleton />}>
        <UserList query={q} page={Number(page) || 1} />
      </Suspense>
    </div>
  );
}

// Server component with direct DB access
async function UserList({ query, page }: { query?: string; page: number }) {
  // Direct database call — no API route needed
  const users = await db.user.findMany({
    where: query ? { name: { contains: query } } : undefined,
    skip: (page - 1) * 20,
    take: 20,
  });

  return (
    <ul>
      {users.map((user) => (
        <li key={user.id}>{user.name} — {user.email}</li>
      ))}
    </ul>
  );
}


// --- Server Actions (mutations without API routes) ---

// app/users/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

const CreateUserSchema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
  role: z.enum(["user", "admin"]).default("user"),
});

export async function createUser(formData: FormData) {
  const parsed = CreateUserSchema.safeParse({
    name: formData.get("name"),
    email: formData.get("email"),
    role: formData.get("role"),
  });

  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }

  const user = await db.user.create({ data: parsed.data });
  revalidatePath("/users");
  redirect(`/users/${user.id}`);
}

export async function deleteUser(userId: string) {
  await db.user.delete({ where: { id: userId } });
  revalidatePath("/users");
}


// --- Client Component using Server Action ---

// app/users/create-form.tsx
"use client";

import { useActionState } from "react";
import { createUser } from "./actions";

export function CreateUserForm() {
  const [state, action, pending] = useActionState(createUser, null);

  return (
    <form action={action}>
      <input name="name" placeholder="Name" required />
      {state?.error?.name && <p className="error">{state.error.name}</p>}

      <input name="email" type="email" placeholder="Email" required />
      {state?.error?.email && <p className="error">{state.error.email}</p>}

      <button type="submit" disabled={pending}>
        {pending ? "Creating..." : "Create User"}
      </button>
    </form>
  );
}


// --- Streaming with loading.tsx and Suspense ---

// app/dashboard/loading.tsx — automatic streaming boundary
export default function DashboardLoading() {
  return <DashboardSkeleton />;
}

// app/dashboard/page.tsx
export default async function Dashboard() {
  return (
    <div className="grid grid-cols-3 gap-4">
      <Suspense fallback={<StatCardSkeleton />}>
        <RevenueCard />   {/* Streams in when ready */}
      </Suspense>
      <Suspense fallback={<StatCardSkeleton />}>
        <UsersCard />     {/* Streams independently */}
      </Suspense>
      <Suspense fallback={<StatCardSkeleton />}>
        <OrdersCard />    {/* Streams independently */}
      </Suspense>
    </div>
  );
}

async function RevenueCard() {
  const revenue = await fetchRevenue(); // Slow query
  return <StatCard title="Revenue" value={`$${revenue}`} />;
}


// --- Partial Prerendering (PPR) ---

// next.config.ts
// export default { experimental: { ppr: true } }

// PPR: static shell + dynamic holes
// The page shell is prerendered at build time
// Suspense boundaries mark dynamic content that streams at request time
export default async function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const product = await getProduct(id); // Static (cached at build)

  return (
    <div>
      {/* Static shell — prerendered */}
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <img src={product.image} alt={product.name} />

      {/* Dynamic holes — streamed at request time */}
      <Suspense fallback={<PriceSkeleton />}>
        <LivePrice productId={id} />  {/* Real-time price */}
      </Suspense>
      <Suspense fallback={<ReviewsSkeleton />}>
        <Reviews productId={id} />    {/* User reviews */}
      </Suspense>
    </div>
  );
}


// --- Caching: fetch with revalidation ---

// Cached by default in server components
const data = await fetch("https://api.example.com/data");

// Time-based revalidation
const data = await fetch("https://api.example.com/data", {
  next: { revalidate: 3600 }, // Revalidate every hour
});

// No cache
const data = await fetch("https://api.example.com/data", {
  cache: "no-store",
});

// Tag-based revalidation
const data = await fetch("https://api.example.com/users", {
  next: { tags: ["users"] },
});
// Then in a server action: revalidateTag("users")


// --- Route handlers (API routes in App Router) ---

// app/api/webhooks/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const signature = request.headers.get("x-webhook-signature");

  if (!verifySignature(body, signature)) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  await processWebhook(body);
  return NextResponse.json({ received: true });
}
```

Next.js 15 App Router patterns:
1. **Server Components** — default rendering, direct DB access, no client JS bundle
2. **Server Actions** — `"use server"` functions replace API routes for mutations
3. **`useActionState`** — pending states + validation errors for form submissions
4. **Partial Prerendering (PPR)** — static shell + dynamic Suspense holes streamed at request time
5. **Tag-based revalidation** — `revalidateTag("users")` invalidates all fetches with that tag'''
    ),
    (
        "frontend/remix-react-router-v7",
        "Show React Router v7 (Remix) patterns: loaders, actions, nested routes, and progressive enhancement.",
        '''React Router v7 (Remix) patterns:

```typescript
// --- Route module with loader + action ---

// app/routes/users.tsx
import type { Route } from "./+types/users";
import { Form, useLoaderData, useNavigation, useSearchParams } from "react-router";

// Loader runs on the server (GET requests)
export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const query = url.searchParams.get("q") || "";
  const page = Number(url.searchParams.get("page")) || 1;

  const users = await db.user.findMany({
    where: query ? { name: { contains: query } } : undefined,
    skip: (page - 1) * 20,
    take: 20,
  });

  const total = await db.user.count();
  return { users, total, page, query };
}

// Action handles mutations (POST/PUT/DELETE)
export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const intent = formData.get("intent");

  if (intent === "create") {
    const name = formData.get("name") as string;
    const email = formData.get("email") as string;

    const errors: Record<string, string> = {};
    if (!name) errors.name = "Name is required";
    if (!email?.includes("@")) errors.email = "Valid email required";

    if (Object.keys(errors).length) {
      return { errors };
    }

    await db.user.create({ data: { name, email } });
    return { success: true };
  }

  if (intent === "delete") {
    const id = formData.get("id") as string;
    await db.user.delete({ where: { id } });
    return { success: true };
  }

  return { error: "Unknown intent" };
}

// Component uses loader data (type-safe)
export default function Users({ loaderData }: Route.ComponentProps) {
  const { users, total, page, query } = loaderData;
  const navigation = useNavigation();
  const isSearching = navigation.location?.search.includes("q=");

  return (
    <div>
      {/* Search with progressive enhancement */}
      <Form method="get">
        <input
          name="q"
          defaultValue={query}
          placeholder="Search users..."
        />
        <button type="submit">
          {isSearching ? "Searching..." : "Search"}
        </button>
      </Form>

      {/* Create user form (POST → action) */}
      <CreateUserForm />

      {/* User list */}
      <ul>
        {users.map((user) => (
          <li key={user.id}>
            {user.name}
            <Form method="post" style={{ display: "inline" }}>
              <input type="hidden" name="id" value={user.id} />
              <button name="intent" value="delete">Delete</button>
            </Form>
          </li>
        ))}
      </ul>
    </div>
  );
}


// --- Nested routes with Outlet ---

// app/routes/dashboard.tsx (layout route)
import { Outlet, NavLink } from "react-router";

export default function DashboardLayout() {
  return (
    <div className="flex">
      <nav>
        <NavLink to="overview" className={({ isActive }) =>
          isActive ? "font-bold" : ""
        }>
          Overview
        </NavLink>
        <NavLink to="analytics">Analytics</NavLink>
        <NavLink to="settings">Settings</NavLink>
      </nav>
      <main>
        <Outlet />  {/* Child route renders here */}
      </main>
    </div>
  );
}


// --- Optimistic UI ---

import { useFetcher } from "react-router";

function ToggleFavorite({ itemId, isFavorite }: {
  itemId: string;
  isFavorite: boolean;
}) {
  const fetcher = useFetcher();

  // Optimistic: show intended state immediately
  const optimisticFavorite = fetcher.formData
    ? fetcher.formData.get("favorite") === "true"
    : isFavorite;

  return (
    <fetcher.Form method="post" action="/api/favorites">
      <input type="hidden" name="itemId" value={itemId} />
      <button
        name="favorite"
        value={optimisticFavorite ? "false" : "true"}
      >
        {optimisticFavorite ? "★" : "☆"}
      </button>
    </fetcher.Form>
  );
}


// --- Error boundaries per route ---

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  return (
    <div className="error-container">
      <h1>Something went wrong</h1>
      <p>{error.message}</p>
    </div>
  );
}


// --- Route config (react-router.config.ts) ---

import type { Config } from "@react-router/dev/config";

export default {
  ssr: true,           // Server-side rendering
  future: {
    unstable_optimizeDeps: true,
  },
} satisfies Config;
```

React Router v7 (Remix) patterns:
1. **`loader`/`action`** — server functions for data fetching (GET) and mutations (POST)
2. **`<Form>`** — progressive enhancement: works without JS, upgrades to fetch
3. **`useFetcher`** — non-navigating mutations for optimistic UI without page transitions
4. **Nested routes** — layout routes with `<Outlet>` for shared UI shells
5. **Type-safe `loaderData`** — auto-generated types from `Route.ComponentProps`'''
    ),
    (
        "frontend/server-actions-patterns",
        "Show React Server Actions patterns: form handling, optimistic updates, error handling, and revalidation.",
        '''React Server Actions patterns:

```typescript
// --- Server Action definition ---

// lib/actions.ts
"use server";

import { revalidatePath, revalidateTag } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { cookies } from "next/headers";

// Type-safe server action with Zod validation
const UpdateProfileSchema = z.object({
  name: z.string().min(1, "Name is required").max(100),
  bio: z.string().max(500).optional(),
  website: z.string().url("Invalid URL").optional().or(z.literal("")),
});

type ActionState = {
  success?: boolean;
  errors?: Record<string, string[]>;
  message?: string;
};

export async function updateProfile(
  prevState: ActionState,
  formData: FormData,
): Promise<ActionState> {
  // Auth check
  const session = await getSession(await cookies());
  if (!session) {
    return { message: "Unauthorized" };
  }

  // Validate
  const parsed = UpdateProfileSchema.safeParse({
    name: formData.get("name"),
    bio: formData.get("bio"),
    website: formData.get("website"),
  });

  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  // Mutate
  try {
    await db.user.update({
      where: { id: session.userId },
      data: parsed.data,
    });
  } catch (error) {
    return { message: "Failed to update profile" };
  }

  revalidatePath("/profile");
  return { success: true, message: "Profile updated" };
}


// --- Client component consuming server action ---

// components/profile-form.tsx
"use client";

import { useActionState, useOptimistic } from "react";
import { updateProfile } from "@/lib/actions";

export function ProfileForm({ user }: { user: User }) {
  const [state, action, pending] = useActionState(updateProfile, {});

  return (
    <form action={action}>
      <div>
        <label htmlFor="name">Name</label>
        <input id="name" name="name" defaultValue={user.name} />
        {state.errors?.name?.map((e) => (
          <p key={e} className="text-red-500 text-sm">{e}</p>
        ))}
      </div>

      <div>
        <label htmlFor="bio">Bio</label>
        <textarea id="bio" name="bio" defaultValue={user.bio ?? ""} />
      </div>

      <div>
        <label htmlFor="website">Website</label>
        <input id="website" name="website" defaultValue={user.website ?? ""} />
        {state.errors?.website?.map((e) => (
          <p key={e} className="text-red-500 text-sm">{e}</p>
        ))}
      </div>

      <button type="submit" disabled={pending}>
        {pending ? "Saving..." : "Save"}
      </button>

      {state.success && <p className="text-green-600">{state.message}</p>}
      {state.message && !state.success && (
        <p className="text-red-600">{state.message}</p>
      )}
    </form>
  );
}


// --- Optimistic updates with useOptimistic ---

"use client";

import { useOptimistic } from "react";
import { toggleLike } from "@/lib/actions";

export function LikeButton({
  postId,
  likes,
  isLiked,
}: {
  postId: string;
  likes: number;
  isLiked: boolean;
}) {
  const [optimistic, setOptimistic] = useOptimistic(
    { likes, isLiked },
    (current, _action: void) => ({
      likes: current.isLiked ? current.likes - 1 : current.likes + 1,
      isLiked: !current.isLiked,
    }),
  );

  return (
    <form
      action={async () => {
        setOptimistic(undefined);
        await toggleLike(postId);
      }}
    >
      <button type="submit">
        {optimistic.isLiked ? "❤️" : "🤍"} {optimistic.likes}
      </button>
    </form>
  );
}


// --- Inline server actions (defined in server components) ---

export default async function TodoList() {
  const todos = await db.todo.findMany();

  async function addTodo(formData: FormData) {
    "use server";
    const title = formData.get("title") as string;
    await db.todo.create({ data: { title } });
    revalidatePath("/todos");
  }

  async function toggleTodo(id: string) {
    "use server";
    const todo = await db.todo.findUnique({ where: { id } });
    await db.todo.update({
      where: { id },
      data: { completed: !todo?.completed },
    });
    revalidatePath("/todos");
  }

  return (
    <div>
      <form action={addTodo}>
        <input name="title" placeholder="New todo" required />
        <button type="submit">Add</button>
      </form>
      <ul>
        {todos.map((todo) => (
          <li key={todo.id}>
            <form action={toggleTodo.bind(null, todo.id)}>
              <button type="submit">
                {todo.completed ? "✓" : "○"} {todo.title}
              </button>
            </form>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

Server Actions patterns:
1. **`"use server"`** — marks functions as server-only, callable from client components
2. **`useActionState`** — tracks pending state + returns validation errors from server
3. **`useOptimistic`** — instant UI feedback while server action processes
4. **Zod validation** — type-safe server-side validation with structured error return
5. **`revalidatePath`/`revalidateTag`** — invalidate cached data after mutations'''
    ),
]
"""
