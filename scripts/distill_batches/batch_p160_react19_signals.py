"""React 19 and signals-based reactivity."""

PAIRS = [
    (
        "frontend/react19-use-hook-actions",
        "Explain React 19's use() hook and Actions pattern with practical examples including data fetching, form submissions, and optimistic updates.",
        '''React 19 introduces the `use()` hook for reading resources (promises, contexts) during render, and Actions for handling async mutations with built-in pending/error states.

```typescript
// --- use() hook for data fetching ---

import {
  use, Suspense, startTransition, useOptimistic,
  useActionState, useTransition, cache,
} from 'react';

// 1. use() reads a promise during render (must be inside Suspense)
interface User {
  id: string;
  name: string;
  email: string;
  avatar: string;
}

// Cache the fetch so multiple components reading the same
// resource share a single network request
const fetchUser = cache(async (id: string): Promise<User> => {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch user ${id}`);
  return res.json();
});

function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  // use() suspends until the promise resolves
  const user = use(userPromise);

  return (
    <div className="profile">
      <img src={user.avatar} alt={user.name} />
      <h2>{user.name}</h2>
      <p>{user.email}</p>
    </div>
  );
}

function UserPage({ userId }: { userId: string }) {
  // Create promise at the parent, pass down
  const userPromise = fetchUser(userId);

  return (
    <Suspense fallback={<UserSkeleton />}>
      <UserProfile userPromise={userPromise} />
    </Suspense>
  );
}
```

```typescript
// --- Actions with useActionState ---

interface FormState {
  error: string | null;
  success: boolean;
  data: { id: string; title: string } | null;
}

// Server action (or client-side async function)
async function createPost(
  prevState: FormState,
  formData: FormData
): Promise<FormState> {
  const title = formData.get('title') as string;
  const body = formData.get('body') as string;

  // Validation
  if (!title || title.length < 3) {
    return { error: 'Title must be at least 3 characters', success: false, data: null };
  }

  try {
    const res = await fetch('/api/posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body }),
    });

    if (!res.ok) {
      const err = await res.json();
      return { error: err.message, success: false, data: null };
    }

    const post = await res.json();
    return { error: null, success: true, data: post };
  } catch {
    return { error: 'Network error, please try again', success: false, data: null };
  }
}

function CreatePostForm() {
  const [state, formAction, isPending] = useActionState(createPost, {
    error: null,
    success: false,
    data: null,
  });

  return (
    <form action={formAction}>
      <input name="title" placeholder="Post title" disabled={isPending} />
      <textarea name="body" placeholder="Write something..." disabled={isPending} />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Creating...' : 'Create Post'}
      </button>
      {state.error && <p className="error">{state.error}</p>}
      {state.success && <p className="success">Post created: {state.data?.title}</p>}
    </form>
  );
}
```

```typescript
// --- useOptimistic for instant UI feedback ---

interface Message {
  id: string;
  text: string;
  sending?: boolean;
}

async function sendMessage(text: string): Promise<Message> {
  const res = await fetch('/api/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('Failed to send');
  return res.json();
}

function Chat({ messages }: { messages: Message[] }) {
  const [optimisticMessages, addOptimistic] = useOptimistic(
    messages,
    (current: Message[], newMsg: string) => [
      ...current,
      { id: `temp-${Date.now()}`, text: newMsg, sending: true },
    ]
  );

  async function handleSend(formData: FormData) {
    const text = formData.get('message') as string;
    addOptimistic(text);          // instant UI update
    await sendMessage(text);      // actual network call
  }

  return (
    <div>
      <ul>
        {optimisticMessages.map(msg => (
          <li key={msg.id} style={{ opacity: msg.sending ? 0.6 : 1 }}>
            {msg.text}
          </li>
        ))}
      </ul>
      <form action={handleSend}>
        <input name="message" placeholder="Type a message..." />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}
```

```typescript
// --- use() with Context (replaces useContext) ---

import { createContext, use } from 'react';

interface Theme {
  mode: 'light' | 'dark';
  primary: string;
  radius: number;
}

const ThemeContext = createContext<Theme>({
  mode: 'light',
  primary: '#3b82f6',
  radius: 8,
});

function ThemedButton({ children }: { children: React.ReactNode }) {
  // use() can read context — supports conditional reads
  const theme = use(ThemeContext);

  return (
    <button
      style={{
        backgroundColor: theme.primary,
        borderRadius: theme.radius,
        color: theme.mode === 'dark' ? '#fff' : '#000',
      }}
    >
      {children}
    </button>
  );
}

// Conditional context read (impossible with useContext)
function MaybeThemed({ useTheme, children }: { useTheme: boolean; children: React.ReactNode }) {
  if (useTheme) {
    const theme = use(ThemeContext);  // OK — use() works in conditionals
    return <div style={{ color: theme.primary }}>{children}</div>;
  }
  return <div>{children}</div>;
}
```

| Feature | React 18 | React 19 |
|---|---|---|
| Data fetching in render | Not built-in (Relay, SWR) | `use(promise)` natively |
| Form actions | Manual `onSubmit` + state | `<form action={fn}>` + `useActionState` |
| Optimistic updates | Manual state management | `useOptimistic` built-in |
| Context reading | `useContext` (no conditionals) | `use(context)` (conditionals OK) |
| Pending states | `useTransition` only | `isPending` from `useActionState` |
| Ref as prop | `forwardRef` required | `ref` is a regular prop |
| Metadata | `react-helmet` | `<title>`, `<meta>` in components |

Key patterns:
1. Always wrap `use(promise)` consumers in `<Suspense>` boundaries
2. Create promises at parent level, pass them down (don\'t create in render)
3. `useActionState` replaces manual loading/error/data state for forms
4. `useOptimistic` reverts automatically if the action throws
5. `use()` replaces `useContext` and allows conditional context reads
6. Actions automatically batch state updates and handle transitions
7. Use `cache()` to deduplicate identical fetches across components'''
    ),
    (
        "frontend/react-server-components",
        "Demonstrate React Server Components (RSC) patterns including server/client boundaries, data fetching, streaming, and composition.",
        '''React Server Components (RSC) let you render components on the server with zero client-side JavaScript, fetching data directly in async components.

```typescript
// --- Server Components (default in Next.js App Router) ---

// app/posts/page.tsx — Server Component (no "use client")
import { Suspense } from 'react';
import { db } from '@/lib/db';
import { PostList } from './post-list';
import { PostFilter } from './post-filter';   // client component

interface Post {
  id: string;
  title: string;
  body: string;
  authorId: string;
  createdAt: Date;
  tags: string[];
}

interface Author {
  id: string;
  name: string;
  avatar: string;
}

// Async server component — fetches data directly
async function PostsPage({
  searchParams,
}: {
  searchParams: Promise<{ tag?: string; page?: string }>;
}) {
  const params = await searchParams;
  const tag = params.tag ?? 'all';
  const page = parseInt(params.page ?? '1', 10);

  // Direct database access — no API layer needed
  const posts = await db.post.findMany({
    where: tag !== 'all' ? { tags: { has: tag } } : {},
    orderBy: { createdAt: 'desc' },
    take: 20,
    skip: (page - 1) * 20,
    include: { author: true },
  });

  const tags = await db.post.findMany({
    select: { tags: true },
    distinct: ['tags'],
  });

  const allTags = [...new Set(tags.flatMap(t => t.tags))];

  return (
    <div className="posts-page">
      <h1>Posts</h1>
      {/* Client component for interactivity */}
      <PostFilter tags={allTags} currentTag={tag} />

      {/* Server-rendered list with streaming */}
      <Suspense fallback={<PostsSkeleton />}>
        <PostList posts={posts} />
      </Suspense>
    </div>
  );
}

export default PostsPage;
```

```typescript
// --- Client / Server boundary and composition ---

// components/post-card.tsx — Server Component
import { formatDate } from '@/lib/utils';
import { LikeButton } from './like-button'; // client component

interface PostCardProps {
  post: {
    id: string;
    title: string;
    body: string;
    createdAt: Date;
    author: { name: string; avatar: string };
  };
}

// Server component can import and render client components
// but NOT the other way around (client can only receive
// server components as children/props)
function PostCard({ post }: PostCardProps) {
  return (
    <article className="post-card">
      <header>
        <img src={post.author.avatar} alt="" width={32} height={32} />
        <span>{post.author.name}</span>
        <time>{formatDate(post.createdAt)}</time>
      </header>
      <h2>{post.title}</h2>
      <p>{post.body.slice(0, 200)}...</p>
      {/* Client island for interactivity */}
      <LikeButton postId={post.id} />
    </article>
  );
}

// components/like-button.tsx — Client Component
'use client';

import { useState, useTransition } from 'react';
import { likePost } from '@/actions/posts';

export function LikeButton({ postId }: { postId: string }) {
  const [liked, setLiked] = useState(false);
  const [isPending, startTransition] = useTransition();

  function handleLike() {
    startTransition(async () => {
      await likePost(postId);
      setLiked(prev => !prev);
    });
  }

  return (
    <button onClick={handleLike} disabled={isPending}>
      {liked ? '❤️' : '🤍'} {isPending ? '...' : 'Like'}
    </button>
  );
}
```

```typescript
// --- Server Actions ---

// actions/posts.ts
'use server';

import { db } from '@/lib/db';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { z } from 'zod';

const CreatePostSchema = z.object({
  title: z.string().min(3).max(200),
  body: z.string().min(10).max(10000),
  tags: z.array(z.string()).max(5),
});

export async function createPost(formData: FormData) {
  const raw = {
    title: formData.get('title'),
    body: formData.get('body'),
    tags: formData.getAll('tags'),
  };

  const parsed = CreatePostSchema.safeParse(raw);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }

  const post = await db.post.create({
    data: {
      ...parsed.data,
      authorId: await getCurrentUserId(),
    },
  });

  revalidatePath('/posts');
  redirect(`/posts/${post.id}`);
}

export async function likePost(postId: string) {
  const userId = await getCurrentUserId();

  await db.like.upsert({
    where: { postId_userId: { postId, userId } },
    create: { postId, userId },
    update: {},
  });

  revalidatePath(`/posts/${postId}`);
}


// --- Streaming with nested Suspense ---

// app/dashboard/page.tsx
import { Suspense } from 'react';

async function RevenueChart() {
  const data = await fetchRevenue(); // slow query
  return <Chart data={data} />;
}

async function RecentOrders() {
  const orders = await fetchRecentOrders(); // medium query
  return <OrderTable orders={orders} />;
}

async function QuickStats() {
  const stats = await fetchStats(); // fast query
  return <StatsGrid stats={stats} />;
}

export default function Dashboard() {
  return (
    <div className="dashboard">
      {/* Fast — renders first */}
      <Suspense fallback={<StatsSkeleton />}>
        <QuickStats />
      </Suspense>

      {/* Medium — streams in second */}
      <Suspense fallback={<OrdersSkeleton />}>
        <RecentOrders />
      </Suspense>

      {/* Slow — streams in last */}
      <Suspense fallback={<ChartSkeleton />}>
        <RevenueChart />
      </Suspense>
    </div>
  );
}
```

```typescript
// --- Parallel data fetching pattern ---

// Avoid sequential waterfalls by initiating fetches in parallel

async function ParallelPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // Start all fetches simultaneously
  const [user, posts, followers] = await Promise.all([
    fetchUser(id),
    fetchUserPosts(id),
    fetchFollowers(id),
  ]);

  return (
    <div>
      <UserHeader user={user} followerCount={followers.length} />
      <PostList posts={posts} />
    </div>
  );
}


// --- Preloading data ---

import { preload } from 'react-dom';

function preloadUserData(userId: string) {
  // Preload while navigating
  preload(`/api/users/${userId}/avatar.jpg`, { as: 'image' });
  // Warm the cache
  void fetchUser(userId);
}
```

| Pattern | Server Component | Client Component |
|---|---|---|
| Data fetching | Direct DB/API access | `useEffect` / SWR / React Query |
| JavaScript shipped | Zero JS | Full component JS |
| State / effects | Not available | `useState`, `useEffect` |
| Event handlers | Not available | `onClick`, `onChange`, etc. |
| Re-renders | Never (static HTML) | On state change |
| Import restriction | Can import client components | Cannot import server components |
| Best for | Static content, data display | Interactivity, forms, animations |

Key patterns:
1. Default to server components; add "use client" only when needed
2. Keep client components as leaf nodes (small interactive islands)
3. Pass server components as `children` to client components for composition
4. Use `Suspense` boundaries to stream slow data independently
5. Parallel data fetching with `Promise.all` to avoid waterfalls
6. Server Actions with `"use server"` for mutations + `revalidatePath`
7. Serialize only plain objects across the server/client boundary'''
    ),
    (
        "frontend/preact-signals",
        "Show Preact Signals for fine-grained reactivity including signal creation, computed values, effects, and React integration.",
        '''Preact Signals provide fine-grained reactivity where only the DOM nodes that read a signal update — no virtual DOM diffing needed.

```typescript
// --- Core Signals API ---

import {
  signal, computed, effect, batch,
  Signal, ReadonlySignal,
} from '@preact/signals';
// For React: import from '@preact/signals-react'

// 1. signal() — reactive primitive
const count = signal(0);
console.log(count.value);   // 0
count.value = 5;             // triggers subscribers

// 2. computed() — derived reactive value (lazy, cached)
const doubled = computed(() => count.value * 2);
console.log(doubled.value); // 10

// 3. effect() — side effect that auto-tracks dependencies
const dispose = effect(() => {
  console.log(`Count is now: ${count.value}`);
  // Runs immediately, then re-runs when count changes
});

// 4. batch() — group multiple updates into one flush
batch(() => {
  count.value = 10;
  // doubled doesn't recompute until batch ends
});

dispose(); // cleanup the effect


// --- Building a reactive store ---

interface Todo {
  id: string;
  text: string;
  done: boolean;
}

function createTodoStore() {
  const todos = signal<Todo[]>([]);
  const filter = signal<'all' | 'active' | 'done'>('all');

  const filtered = computed(() => {
    switch (filter.value) {
      case 'active': return todos.value.filter(t => !t.done);
      case 'done':   return todos.value.filter(t => t.done);
      default:       return todos.value;
    }
  });

  const stats = computed(() => ({
    total: todos.value.length,
    active: todos.value.filter(t => !t.done).length,
    done: todos.value.filter(t => t.done).length,
  }));

  function addTodo(text: string) {
    todos.value = [
      ...todos.value,
      { id: crypto.randomUUID(), text, done: false },
    ];
  }

  function toggleTodo(id: string) {
    todos.value = todos.value.map(t =>
      t.id === id ? { ...t, done: !t.done } : t
    );
  }

  function removeTodo(id: string) {
    todos.value = todos.value.filter(t => t.id !== id);
  }

  return { todos, filter, filtered, stats, addTodo, toggleTodo, removeTodo };
}

const store = createTodoStore();
```

```typescript
// --- React integration ---

// With @preact/signals-react, signals work directly in JSX
// The component itself doesn't re-render — only the text node updates!

import { signal, computed } from '@preact/signals-react';
import { useSignal, useComputed, useSignalEffect } from '@preact/signals-react/runtime';

// Global signals (shared state — no context needed)
const darkMode = signal(false);
const user = signal<{ name: string; email: string } | null>(null);

// Component-scoped signals
function Counter() {
  // useSignal creates a signal scoped to this component instance
  const count = useSignal(0);
  const doubled = useComputed(() => count.value * 2);

  // Effect scoped to component lifecycle
  useSignalEffect(() => {
    document.title = `Count: ${count.value}`;
  });

  return (
    <div>
      {/* Only this text node updates, not the whole component */}
      <p>Count: {count}</p>
      <p>Doubled: {doubled}</p>
      <button onClick={() => count.value++}>Increment</button>
    </div>
  );
}

// No re-render of Header when darkMode changes — only the
// className text node is surgically updated
function Header() {
  return (
    <header className={darkMode.value ? 'dark' : 'light'}>
      <h1>My App</h1>
      <span>{user.value?.name ?? 'Guest'}</span>
      <button onClick={() => { darkMode.value = !darkMode.value; }}>
        Toggle Theme
      </button>
    </header>
  );
}
```

```typescript
// --- Advanced patterns ---

// 1. Async data with signals
function createAsyncSignal<T>(fetcher: () => Promise<T>) {
  const data = signal<T | undefined>(undefined);
  const error = signal<Error | null>(null);
  const loading = signal(false);

  async function execute() {
    loading.value = true;
    error.value = null;
    try {
      data.value = await fetcher();
    } catch (e) {
      error.value = e instanceof Error ? e : new Error(String(e));
    } finally {
      loading.value = false;
    }
  }

  return { data, error, loading, execute };
}

const users = createAsyncSignal(() =>
  fetch('/api/users').then(r => r.json())
);

// 2. Undo/redo with signal history
function createHistory<T>(initial: T) {
  const past = signal<T[]>([]);
  const present = signal<T>(initial);
  const future = signal<T[]>([]);

  const canUndo = computed(() => past.value.length > 0);
  const canRedo = computed(() => future.value.length > 0);

  function set(value: T) {
    batch(() => {
      past.value = [...past.value, present.value];
      present.value = value;
      future.value = [];
    });
  }

  function undo() {
    if (!canUndo.value) return;
    batch(() => {
      const prev = past.value.at(-1)!;
      past.value = past.value.slice(0, -1);
      future.value = [present.value, ...future.value];
      present.value = prev;
    });
  }

  function redo() {
    if (!canRedo.value) return;
    batch(() => {
      const next = future.value[0];
      future.value = future.value.slice(1);
      past.value = [...past.value, present.value];
      present.value = next;
    });
  }

  return { present, canUndo, canRedo, set, undo, redo };
}


// 3. Derived signal with debounce
function debouncedSignal<T>(source: Signal<T>, ms: number): ReadonlySignal<T> {
  const debounced = signal(source.value);
  let timer: ReturnType<typeof setTimeout>;

  effect(() => {
    const val = source.value;
    clearTimeout(timer);
    timer = setTimeout(() => { debounced.value = val; }, ms);
  });

  return debounced;
}

const searchInput = signal('');
const debouncedSearch = debouncedSignal(searchInput, 300);
```

| Feature | Signals | useState | Redux | Zustand |
|---|---|---|---|---|
| Granularity | DOM node | Component | Component (selector) | Component (selector) |
| Boilerplate | Minimal | Minimal | High | Low |
| Re-renders | None (bypasses VDOM) | Full component | Selected slice | Selected slice |
| DevTools | Limited | React DevTools | Redux DevTools | Basic |
| SSR support | Full | Full | Full | Full |
| Bundle size | ~1 KB | 0 (built-in) | ~7 KB | ~1 KB |
| Learning curve | Low | Low | High | Low |

Key patterns:
1. `signal()` for primitive state, `computed()` for derived values
2. Signals update at the DOM node level — no component re-renders
3. `useSignal` for component-scoped signals, top-level `signal()` for global state
4. `batch()` groups multiple updates to avoid intermediate computations
5. `effect()` auto-tracks dependencies; returns a dispose function
6. Signals work as JSX children directly: `<p>{count}</p>` (not `.value`)
7. No context providers needed — signals are inherently shareable'''
    ),
    (
        "frontend/solidjs-reactivity",
        "Demonstrate Solid.js fine-grained reactivity including createSignal, createEffect, createMemo, stores, and component patterns.",
        '''Solid.js uses fine-grained reactivity where signals are tracked at the access site, not the component level. Components run once (no re-execution), and only the specific DOM expressions that read signals update.

```typescript
// --- Core reactivity primitives ---

import {
  createSignal, createEffect, createMemo,
  createResource, onMount, onCleanup, batch,
  Show, For, Switch, Match, Index,
  type Component, type Accessor, type Setter,
} from 'solid-js';
import { createStore, produce } from 'solid-js/store';

// 1. createSignal — returns [getter, setter] (not a value!)
const [count, setCount] = createSignal(0);
console.log(count());    // 0  — call the getter
setCount(5);             // set directly
setCount(prev => prev + 1); // functional update

// 2. createMemo — memoized derived value
const doubled = createMemo(() => count() * 2);

// 3. createEffect — runs side effects when dependencies change
createEffect(() => {
  // Auto-tracks: re-runs when count() changes
  console.log('Count changed:', count());
});


// --- Component that runs once ---

const Counter: Component = () => {
  const [count, setCount] = createSignal(0);
  const doubled = createMemo(() => count() * 2);

  // This log runs ONCE — the component function is a setup function
  console.log('Counter setup (runs once)');

  // Only the {count()} text node in the DOM updates
  return (
    <div>
      <p>Count: {count()}</p>
      <p>Doubled: {doubled()}</p>
      <button onClick={() => setCount(c => c + 1)}>+1</button>
    </div>
  );
};
```

```typescript
// --- Stores for nested/complex state ---

interface AppState {
  user: {
    name: string;
    preferences: { theme: 'light' | 'dark'; lang: string };
  };
  todos: Array<{ id: string; text: string; done: boolean }>;
  ui: { sidebarOpen: boolean; modal: string | null };
}

const [state, setState] = createStore<AppState>({
  user: {
    name: 'Alice',
    preferences: { theme: 'light', lang: 'en' },
  },
  todos: [],
  ui: { sidebarOpen: true, modal: null },
});

// Path-based updates — only affected parts of the DOM update
setState('user', 'preferences', 'theme', 'dark');
setState('ui', 'sidebarOpen', open => !open);

// Array operations with produce (Immer-like)
setState(
  produce((draft) => {
    draft.todos.push({
      id: crypto.randomUUID(),
      text: 'New task',
      done: false,
    });
  })
);

// Toggle specific todo — only that <li> updates
setState('todos', todo => todo.id === targetId, 'done', d => !d);


// --- createResource for async data ---

interface Post {
  id: string;
  title: string;
  body: string;
}

const [selectedId, setSelectedId] = createSignal<string>('1');

// Automatically re-fetches when selectedId() changes
const [post, { refetch, mutate }] = createResource(
  selectedId,  // source signal
  async (id: string): Promise<Post> => {
    const res = await fetch(`/api/posts/${id}`);
    if (!res.ok) throw new Error('Failed to fetch');
    return res.json();
  }
);

const PostView: Component = () => {
  return (
    <Switch>
      <Match when={post.loading}>
        <p>Loading...</p>
      </Match>
      <Match when={post.error}>
        <p>Error: {(post.error as Error).message}</p>
        <button onClick={refetch}>Retry</button>
      </Match>
      <Match when={post()}>
        {(p) => (
          <article>
            <h2>{p().title}</h2>
            <p>{p().body}</p>
          </article>
        )}
      </Match>
    </Switch>
  );
};
```

```typescript
// --- Control flow components ---

const TodoApp: Component = () => {
  const [todos, setTodos] = createStore<{ id: string; text: string; done: boolean }[]>([]);
  const [filter, setFilter] = createSignal<'all' | 'active' | 'done'>('all');

  const filtered = createMemo(() => {
    switch (filter()) {
      case 'active': return todos.filter(t => !t.done);
      case 'done':   return todos.filter(t => t.done);
      default:       return [...todos];
    }
  });

  function addTodo(text: string) {
    setTodos(todos.length, { id: crypto.randomUUID(), text, done: false });
  }

  return (
    <div>
      {/* Show — conditional rendering */}
      <Show
        when={todos.length > 0}
        fallback={<p>No todos yet!</p>}
      >
        {/* For — keyed list (each item tracked by key) */}
        <For each={filtered()}>
          {(todo, index) => (
            <div>
              <span>{index() + 1}. </span>
              <input
                type="checkbox"
                checked={todo.done}
                onChange={() =>
                  setTodos(t => t.id === todo.id, 'done', d => !d)
                }
              />
              <span style={{
                'text-decoration': todo.done ? 'line-through' : 'none',
              }}>
                {todo.text}
              </span>
            </div>
          )}
        </For>
      </Show>

      {/* Index — for lists where items don't move, only values change */}
      <Index each={todos}>
        {(todo, i) => <span>{todo().text}</span>}
      </Index>
    </div>
  );
};


// --- Custom reactive primitives ---

function createLocalSignal<T>(key: string, initial: T) {
  const stored = localStorage.getItem(key);
  const [value, setValue] = createSignal<T>(
    stored ? JSON.parse(stored) : initial
  );

  createEffect(() => {
    localStorage.setItem(key, JSON.stringify(value()));
  });

  return [value, setValue] as const;
}

function createMediaQuery(query: string): Accessor<boolean> {
  const mql = window.matchMedia(query);
  const [matches, setMatches] = createSignal(mql.matches);

  onMount(() => {
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    onCleanup(() => mql.removeEventListener('change', handler));
  });

  return matches;
}

const isMobile = createMediaQuery('(max-width: 768px)');
```

| Feature | Solid.js | React | Svelte 5 | Vue 3 |
|---|---|---|---|---|
| Reactivity model | Fine-grained signals | VDOM diffing | Runes (signals) | Proxy-based refs |
| Component re-runs | Never (setup once) | Every state change | Compiled away | Template only |
| Bundle size | ~7 KB | ~40 KB | ~2 KB (compiled) | ~33 KB |
| JSX | Yes (compiled away) | Yes (runtime VDOM) | No (template) | Optional |
| Performance | Near-vanilla JS | Good with memoization | Excellent | Very good |
| Learning from React | Very similar API | N/A | Different model | Somewhat similar |

Key patterns:
1. Components are setup functions that run once — no re-execution
2. `createSignal` returns `[getter, setter]` — always call the getter: `count()`
3. `<For>` for keyed lists, `<Index>` when items are positional
4. Stores with path-based updates for surgical DOM updates on nested objects
5. `createResource` auto-refetches when its source signal changes
6. Effects auto-track dependencies at the getter call site
7. No need for `useMemo`/`useCallback` — closures are stable since components run once'''
    ),
    (
        "frontend/signals-comparison",
        "Compare signal-based state management across frameworks: Preact Signals, Solid.js, Angular Signals, Vue refs, and Svelte 5 runes.",
        '''Signal-based reactivity is converging across frameworks. Each implementation shares the core idea — reactive primitives that track dependencies and update only what changed — but with different APIs and trade-offs.

```typescript
// --- Signal creation across frameworks ---

// Preact Signals
import { signal, computed, effect } from '@preact/signals';
const count_preact = signal(0);
const doubled_preact = computed(() => count_preact.value * 2);
effect(() => console.log(count_preact.value));
count_preact.value = 5;

// Solid.js
import { createSignal, createMemo, createEffect } from 'solid-js';
const [countSolid, setCountSolid] = createSignal(0);
const doubledSolid = createMemo(() => countSolid() * 2);
createEffect(() => console.log(countSolid()));
setCountSolid(5);

// Angular Signals (Angular 16+)
import { signal as angularSignal, computed as angularComputed, effect as angularEffect } from '@angular/core';
const countAngular = angularSignal(0);
const doubledAngular = angularComputed(() => countAngular() * 2);
angularEffect(() => console.log(countAngular()));
countAngular.set(5);        // or countAngular.update(v => v + 1)

// Vue 3 Composition API (ref/computed are signal-like)
import { ref, computed as vueComputed, watchEffect } from 'vue';
const countVue = ref(0);
const doubledVue = vueComputed(() => countVue.value * 2);
watchEffect(() => console.log(countVue.value));
countVue.value = 5;

// Svelte 5 Runes
// let count = $state(0);                   // signal
// let doubled = $derived(count * 2);       // computed
// $effect(() => console.log(count));       // effect
// count = 5;                               // plain assignment
```

```typescript
// --- Building a shared counter store in each framework ---

// === Preact Signals store ===
function createCounterStore() {
  const count = signal(0);
  const doubled = computed(() => count.value * 2);
  const isEven = computed(() => count.value % 2 === 0);

  return {
    count,       // Signal<number>
    doubled,     // ReadonlySignal<number>
    isEven,      // ReadonlySignal<boolean>
    increment: () => { count.value++; },
    decrement: () => { count.value--; },
    reset: ()    => { count.value = 0; },
  };
}
// Usage in any component: const store = createCounterStore();
// JSX: <p>{store.count}</p>  (no .value needed in JSX)


// === Solid.js store ===
function createCounterStoreSolid() {
  const [count, setCount] = createSignal(0);
  const doubled = createMemo(() => count() * 2);
  const isEven = createMemo(() => count() % 2 === 0);

  return {
    count,      // Accessor<number>
    doubled,    // Accessor<number>
    isEven,     // Accessor<boolean>
    increment: () => setCount(c => c + 1),
    decrement: () => setCount(c => c - 1),
    reset: ()   => setCount(0),
  };
}
// Usage: const store = createCounterStoreSolid();
// JSX: <p>{store.count()}</p>  (must call getter)


// === Angular Signals store ===
import { Injectable, signal, computed } from '@angular/core';

@Injectable({ providedIn: 'root' })
class CounterStore {
  readonly count = signal(0);
  readonly doubled = computed(() => this.count() * 2);
  readonly isEven = computed(() => this.count() % 2 === 0);

  increment() { this.count.update(c => c + 1); }
  decrement() { this.count.update(c => c - 1); }
  reset()     { this.count.set(0); }
}
// Usage: inject(CounterStore) in component
// Template: <p>{{ store.count() }}</p>


// === Vue 3 composable ===
import { ref, computed } from 'vue';

function useCounter() {
  const count = ref(0);
  const doubled = computed(() => count.value * 2);
  const isEven = computed(() => count.value % 2 === 0);

  return {
    count,
    doubled,
    isEven,
    increment: () => { count.value++; },
    decrement: () => { count.value--; },
    reset: ()    => { count.value = 0; },
  };
}
// Usage: const { count, doubled } = useCounter();
// Template: <p>{{ count }}</p>  (auto-unwrapped in template)
```

```typescript
// --- Batching behavior comparison ---

// Preact Signals — explicit batch()
import { signal, computed, batch } from '@preact/signals';
const a = signal(1);
const b = signal(2);
const sum = computed(() => a.value + b.value);

// Without batch: sum recomputes twice (once per .value set)
// With batch: sum recomputes once
batch(() => {
  a.value = 10;
  b.value = 20;
});
// sum.value === 30 (computed once)


// Solid.js — implicit batching in event handlers, explicit batch()
import { createSignal, createMemo, batch as solidBatch } from 'solid-js';
const [a2, setA] = createSignal(1);
const [b2, setB] = createSignal(2);
const sum2 = createMemo(() => a2() + b2());

// Inside event handlers: automatically batched
// Outside: use batch()
solidBatch(() => {
  setA(10);
  setB(20);
});


// Angular — auto-batched via change detection (no manual batch needed)
// Signal updates are always batched within the same synchronous block

// Vue — auto-batched via nextTick (DOM updates deferred)
// Multiple ref updates in same tick = single DOM update

// Svelte 5 — auto-batched via microtask (similar to Vue)
```

```typescript
// --- Interop: signals with React (adapter patterns) ---

// Pattern: use Preact Signals as a framework-agnostic store
// consumed by React, Vue, or vanilla JS

// store.ts — framework-agnostic
import { signal, computed, effect } from '@preact/signals-core';

export const authStore = (() => {
  const token = signal<string | null>(null);
  const user = signal<{ id: string; name: string } | null>(null);
  const isAuthenticated = computed(() => token.value !== null);

  async function login(email: string, password: string) {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    token.value = data.token;
    user.value = data.user;
  }

  function logout() {
    token.value = null;
    user.value = null;
  }

  // Persist to localStorage
  effect(() => {
    if (token.value) {
      localStorage.setItem('auth_token', token.value);
    } else {
      localStorage.removeItem('auth_token');
    }
  });

  return { token, user, isAuthenticated, login, logout };
})();


// React adapter — subscribe to signals via useSyncExternalStore
import { useSyncExternalStore } from 'react';
import type { ReadonlySignal } from '@preact/signals-core';

function useSignalValue<T>(sig: ReadonlySignal<T>): T {
  return useSyncExternalStore(
    (callback) => {
      const dispose = effect(() => {
        sig.value;  // track
        callback();
      });
      return dispose;
    },
    () => sig.value,
    () => sig.value,  // server snapshot
  );
}

// React component consuming the framework-agnostic store
function AuthStatus() {
  const isAuth = useSignalValue(authStore.isAuthenticated);
  const user = useSignalValue(authStore.user);

  if (!isAuth) return <button onClick={() => authStore.login('a@b.com', 'pw')}>Login</button>;
  return <span>Welcome, {user?.name}</span>;
}
```

| Aspect | Preact Signals | Solid.js | Angular Signals | Vue refs | Svelte 5 Runes |
|---|---|---|---|---|---|
| Read syntax | `sig.value` | `sig()` | `sig()` | `ref.value` | `variable` (plain) |
| Write syntax | `sig.value = x` | `setSig(x)` | `sig.set(x)` | `ref.value = x` | `variable = x` |
| Computed | `computed(fn)` | `createMemo(fn)` | `computed(fn)` | `computed(fn)` | `$derived(expr)` |
| Effect | `effect(fn)` | `createEffect(fn)` | `effect(fn)` | `watchEffect(fn)` | `$effect(fn)` |
| Batching | Explicit `batch()` | Auto in handlers | Automatic | Automatic (nextTick) | Automatic |
| Granularity | DOM node | DOM expression | Component (zoneless) | Component | DOM expression |
| Framework-agnostic | Yes (`signals-core`) | No | No | No | No |
| SSR | Yes | Yes | Yes | Yes | Yes |
| Bundle overhead | ~1 KB | ~7 KB | Part of Angular | Part of Vue | Compiled away |

Key patterns:
1. All signal systems share: reactive atom, derived/computed, side effect
2. Preact Signals is the only framework-agnostic option (`@preact/signals-core`)
3. Solid and Svelte achieve finest granularity — DOM expression level updates
4. Angular signals integrate with the existing DI and change detection system
5. Vue `ref` is essentially a signal with Proxy-based tracking
6. Batching is automatic in most frameworks; Preact Signals needs explicit `batch()`
7. For cross-framework stores, use `@preact/signals-core` + framework adapters'''
    ),
]
