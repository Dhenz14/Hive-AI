"""Frontend — SSR patterns, Svelte, and Astro."""

PAIRS = [
    (
        "frontend/ssr-patterns",
        "Show server-side rendering patterns: Next.js App Router, data fetching, streaming, and caching.",
        """Next.js App Router SSR patterns:

```typescript
// --- Server Components (default in App Router) ---

// app/users/page.tsx — Server Component (runs on server only)
import { Suspense } from 'react';

// Direct database access in Server Components
async function getUsers() {
  const res = await fetch('https://api.example.com/users', {
    next: { revalidate: 60 }, // ISR: revalidate every 60 seconds
  });
  if (!res.ok) throw new Error('Failed to fetch users');
  return res.json();
}

export default async function UsersPage() {
  const users = await getUsers();

  return (
    <div>
      <h1>Users</h1>
      <ul>
        {users.map((user: any) => (
          <li key={user.id}>{user.name}</li>
        ))}
      </ul>

      {/* Stream slow component */}
      <Suspense fallback={<div>Loading stats...</div>}>
        <UserStats />
      </Suspense>
    </div>
  );
}

// Streamed component — renders after initial page load
async function UserStats() {
  const stats = await fetch('https://api.example.com/stats', {
    cache: 'no-store', // Always fresh
  }).then(r => r.json());

  return <div>Total: {stats.total}</div>;
}


// --- Client Components ---

// app/users/search.tsx
'use client'; // Opt into client-side rendering

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

export function SearchUsers() {
  const [query, setQuery] = useState('');
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  function handleSearch(value: string) {
    setQuery(value);
    startTransition(() => {
      router.push(`/users?q=${encodeURIComponent(value)}`);
    });
  }

  return (
    <div>
      <input
        value={query}
        onChange={(e) => handleSearch(e.target.value)}
        placeholder="Search users..."
      />
      {isPending && <span>Searching...</span>}
    </div>
  );
}


// --- Server Actions (form mutations) ---

// app/users/actions.ts
'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createUser(formData: FormData) {
  const name = formData.get('name') as string;
  const email = formData.get('email') as string;

  // Validate
  if (!name || !email) {
    return { error: 'Name and email required' };
  }

  // Create user (direct DB access)
  await db.users.create({ name, email });

  // Revalidate cached data
  revalidatePath('/users');
  redirect('/users');
}

// In component:
// <form action={createUser}>
//   <input name="name" />
//   <input name="email" />
//   <button type="submit">Create</button>
// </form>


// --- Route handlers (API routes) ---

// app/api/users/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const q = searchParams.get('q') || '';

  const users = await db.users.findMany({
    where: { name: { contains: q } },
    take: 20,
  });

  return NextResponse.json(users, {
    headers: {
      'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300',
    },
  });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const user = await db.users.create(body);
  return NextResponse.json(user, { status: 201 });
}


// --- Metadata ---

// app/users/[id]/page.tsx
import { Metadata, ResolvingMetadata } from 'next';

type Props = { params: { id: string } };

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const user = await getUser(params.id);
  return {
    title: `${user.name} | MyApp`,
    description: `Profile of ${user.name}`,
    openGraph: { images: [user.avatar] },
  };
}

export default async function UserPage({ params }: Props) {
  const user = await getUser(params.id);
  return <div>{user.name}</div>;
}
```

Next.js App Router patterns:
1. **Server Components** — default: fetch data on server, zero client JS
2. **`Suspense` streaming** — show page immediately, stream slow parts later
3. **`'use client'`** — opt specific components into client-side interactivity
4. **Server Actions** — `'use server'` functions for form mutations + revalidation
5. **`next: { revalidate: 60 }`** — ISR: cache for 60s, rebuild in background"""
    ),
    (
        "frontend/svelte-patterns",
        "Show Svelte patterns: reactivity, stores, component composition, and SvelteKit routing.",
        """Svelte and SvelteKit patterns:

```svelte
<!-- --- Svelte reactivity --- -->

<script lang="ts">
  // Reactive declarations
  let count = $state(0);            // Svelte 5 runes
  let doubled = $derived(count * 2);

  // Or Svelte 4 style:
  // let count = 0;
  // $: doubled = count * 2;

  function increment() {
    count++;
  }

  // Reactive statements (run when dependencies change)
  $effect(() => {
    console.log('count changed:', count);
    // Cleanup function
    return () => console.log('cleaning up');
  });


  // --- Props ---
  interface Props {
    title: string;
    items?: string[];
    onSelect?: (item: string) => void;
  }

  let { title, items = [], onSelect }: Props = $props();
</script>

<h1>{title}</h1>
<p>Count: {count}, Doubled: {doubled}</p>
<button onclick={increment}>+1</button>

<!-- Conditional rendering -->
{#if count > 10}
  <p>That's a lot!</p>
{:else if count > 5}
  <p>Getting there</p>
{:else}
  <p>Keep clicking</p>
{/if}

<!-- List rendering -->
{#each items as item, index (item)}
  <li>
    <button onclick={() => onSelect?.(item)}>
      {index}: {item}
    </button>
  </li>
{/each}

<!-- Await blocks -->
{#await fetchUsers()}
  <p>Loading...</p>
{:then users}
  {#each users as user}
    <p>{user.name}</p>
  {/each}
{:catch error}
  <p>Error: {error.message}</p>
{/await}

<style>
  /* Scoped by default — only applies to this component */
  h1 { color: #333; }
  button { padding: 0.5rem 1rem; }
</style>
```

```typescript
// --- SvelteKit routing ---

// src/routes/users/+page.server.ts (server load function)
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ fetch, params, url }) => {
  const q = url.searchParams.get('q') || '';
  const res = await fetch(`/api/users?q=${q}`);
  const users = await res.json();
  return { users, query: q };
};

// Form actions (server-side mutations)
export const actions: Actions = {
  create: async ({ request }) => {
    const data = await request.formData();
    const name = data.get('name') as string;
    const email = data.get('email') as string;

    if (!name || !email) {
      return { success: false, error: 'Name and email required' };
    }

    await db.users.create({ name, email });
    return { success: true };
  },

  delete: async ({ request }) => {
    const data = await request.formData();
    const id = data.get('id') as string;
    await db.users.delete(id);
    return { success: true };
  },
};


// src/routes/users/+page.svelte
// <script lang="ts">
//   import type { PageData } from './$types';
//   let { data }: { data: PageData } = $props();
//
//   // data.users available from server load
// </script>
//
// <form method="POST" action="?/create">
//   <input name="name" />
//   <input name="email" />
//   <button>Create User</button>
// </form>


// --- Stores (shared state) ---

// src/lib/stores/auth.ts
import { writable, derived, readable } from 'svelte/store';

export const user = writable<User | null>(null);
export const isLoggedIn = derived(user, $user => $user !== null);

// Time store (readable — no external set)
export const now = readable(new Date(), (set) => {
  const interval = setInterval(() => set(new Date()), 1000);
  return () => clearInterval(interval);
});

// Custom store with methods
function createCart() {
  const { subscribe, update, set } = writable<CartItem[]>([]);

  return {
    subscribe,
    addItem: (item: CartItem) => update(items => [...items, item]),
    removeItem: (id: string) => update(items =>
      items.filter(i => i.id !== id)),
    clear: () => set([]),
  };
}

export const cart = createCart();
```

Svelte patterns:
1. **`$state` / `$derived`** — Svelte 5 runes for reactive declarations
2. **`$effect`** — reactive side effects with automatic cleanup
3. **`{#each ... (key)}`** — keyed list rendering with template syntax
4. **`+page.server.ts`** — server-side data loading and form actions
5. **Custom stores** — `writable` + methods for shared state management"""
    ),
    (
        "frontend/astro-patterns",
        "Show Astro patterns: islands architecture, content collections, and multi-framework components.",
        """Astro islands architecture:

```astro
---
// src/pages/blog/[slug].astro
// Frontmatter (runs on server at build time)

import { getCollection, getEntry } from 'astro:content';
import Layout from '../../layouts/Layout.astro';
import TableOfContents from '../../components/TableOfContents.astro';
import LikeButton from '../../components/LikeButton.tsx';  // React component
import Comments from '../../components/Comments.svelte';    // Svelte component

// Static paths for SSG
export async function getStaticPaths() {
  const posts = await getCollection('blog');
  return posts.map(post => ({
    params: { slug: post.slug },
    props: { post },
  }));
}

const { post } = Astro.props;
const { Content, headings } = await post.render();
---

<Layout title={post.data.title}>
  <article>
    <h1>{post.data.title}</h1>
    <time datetime={post.data.date.toISOString()}>
      {post.data.date.toLocaleDateString()}
    </time>

    <!-- Static component (zero JS) -->
    <TableOfContents headings={headings} />

    <!-- Rendered markdown content -->
    <div class="prose">
      <Content />
    </div>

    <!-- Interactive island: hydrate on visible -->
    <LikeButton client:visible postId={post.slug} />

    <!-- Interactive island: hydrate on idle -->
    <Comments client:idle postId={post.slug} />
  </article>
</Layout>

<style>
  article {
    max-width: 65ch;
    margin: 0 auto;
    padding: 2rem;
  }
  .prose { line-height: 1.7; }
</style>
```

```typescript
// --- Content collections schema ---
// src/content/config.ts

import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  type: 'content',  // Markdown/MDX
  schema: z.object({
    title: z.string(),
    date: z.date(),
    author: z.string(),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
    image: z.string().optional(),
    description: z.string().max(160),
  }),
});

const authors = defineCollection({
  type: 'data',  // JSON/YAML
  schema: z.object({
    name: z.string(),
    bio: z.string(),
    avatar: z.string(),
    social: z.object({
      twitter: z.string().optional(),
      github: z.string().optional(),
    }),
  }),
});

export const collections = { blog, authors };
```

```tsx
// --- React island component ---
// src/components/LikeButton.tsx

import { useState, useEffect } from 'react';

interface Props {
  postId: string;
}

export default function LikeButton({ postId }: Props) {
  const [likes, setLikes] = useState(0);
  const [liked, setLiked] = useState(false);

  useEffect(() => {
    fetch(`/api/likes/${postId}`)
      .then(r => r.json())
      .then(data => setLikes(data.count));
  }, [postId]);

  async function handleLike() {
    const res = await fetch(`/api/likes/${postId}`, { method: 'POST' });
    const data = await res.json();
    setLikes(data.count);
    setLiked(true);
  }

  return (
    <button onClick={handleLike} disabled={liked}>
      {liked ? '❤️' : '🤍'} {likes}
    </button>
  );
}
```

```astro
---
// --- Astro component (zero JS, server-rendered) ---
// src/components/TableOfContents.astro

interface Props {
  headings: { depth: number; slug: string; text: string }[];
}

const { headings } = Astro.props;
const toc = headings.filter(h => h.depth <= 3);
---

<nav class="toc">
  <h2>Contents</h2>
  <ul>
    {toc.map(heading => (
      <li class={`depth-${heading.depth}`}>
        <a href={`#${heading.slug}`}>{heading.text}</a>
      </li>
    ))}
  </ul>
</nav>

<style>
  .toc { border-left: 3px solid #e2e8f0; padding-left: 1rem; }
  .depth-3 { margin-left: 1rem; }
</style>
```

Astro patterns:
1. **Islands architecture** — ship zero JS by default, hydrate only interactive parts
2. **`client:visible`** — hydrate component when it enters viewport (lazy)
3. **Content collections** — type-safe Markdown/MDX with Zod schema validation
4. **Multi-framework** — use React, Svelte, Vue components in same project
5. **`.astro` components** — server-only, no client JS, scoped CSS"""
    ),
]
