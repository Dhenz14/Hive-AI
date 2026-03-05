"""Svelte — reactivity, stores, components, and SvelteKit patterns."""

PAIRS = [
    (
        "svelte/fundamentals",
        "Show Svelte patterns: reactive declarations, bindings, events, lifecycle, and component composition.",
        '''Svelte component patterns:

```svelte
<!-- Counter.svelte -->
<script lang="ts">
  // Props
  export let initialCount: number = 0
  export let label: string = 'Count'

  // Reactive state
  let count = initialCount
  let items: string[] = []

  // Reactive declarations (recompute when dependencies change)
  $: doubled = count * 2
  $: isEven = count % 2 === 0
  $: itemCount = items.length

  // Reactive statements (side effects)
  $: if (count > 10) {
    console.log('Count exceeded 10!')
  }

  $: {
    // Multi-line reactive block
    const total = count * 2
    document.title = `${label}: ${total}`
  }

  // Event handlers
  function increment() { count++ }
  function decrement() { count = Math.max(0, count - 1) }
  function addItem() {
    items = [...items, `Item ${items.length + 1}`]  // Must reassign for reactivity
  }
  function removeItem(index: number) {
    items = items.filter((_, i) => i !== index)
  }

  // Event dispatching
  import { createEventDispatcher } from 'svelte'
  const dispatch = createEventDispatcher<{
    change: { count: number }
    reset: void
  }>()

  function reset() {
    count = 0
    dispatch('reset')
  }

  // Lifecycle
  import { onMount, onDestroy } from 'svelte'

  let interval: ReturnType<typeof setInterval>
  onMount(() => {
    interval = setInterval(() => count++, 1000)
    return () => clearInterval(interval)  // Cleanup
  })
</script>

<!-- Template -->
<div class="counter" class:even={isEven}>
  <h2>{label}: {count}</h2>
  <p>Doubled: {doubled}</p>

  <button on:click={increment}>+</button>
  <button on:click={decrement}>-</button>
  <button on:click={reset}>Reset</button>

  <!-- Conditional rendering -->
  {#if count > 5}
    <p class="warning">High count!</p>
  {:else if count > 0}
    <p>Keep going...</p>
  {:else}
    <p>Start counting!</p>
  {/if}

  <!-- List rendering -->
  <ul>
    {#each items as item, index (item)}
      <li>
        {item}
        <button on:click={() => removeItem(index)}>x</button>
      </li>
    {:else}
      <li>No items yet</li>
    {/each}
  </ul>

  <!-- Two-way binding -->
  <input bind:value={label} placeholder="Label" />

  <!-- Slot for composition -->
  <slot name="footer" {count} {doubled}>
    <p>Default footer content</p>
  </slot>
</div>

<style>
  .counter { padding: 1rem; }
  .even { background: #f0f0f0; }
  .warning { color: red; font-weight: bold; }
  /* Styles are scoped by default */
</style>
```

```svelte
<!-- Parent.svelte -->
<script lang="ts">
  import Counter from './Counter.svelte'

  let counterRef: Counter
  let theme = 'light'

  function handleChange(e: CustomEvent<{ count: number }>) {
    console.log('Count changed:', e.detail.count)
  }
</script>

<Counter
  bind:this={counterRef}
  initialCount={5}
  label="Score"
  on:change={handleChange}
  on:reset={() => console.log('Reset!')}
>
  <p slot="footer" let:count let:doubled>
    Custom footer: {count} x 2 = {doubled}
  </p>
</Counter>
```

Svelte rules:
1. **Reactive declarations** (`$:`) — recompute automatically when dependencies change
2. **Reassign for reactivity** — `arr = [...arr, item]` not `arr.push(item)`
3. **Scoped styles** — CSS is component-scoped by default
4. **No virtual DOM** — compiles to direct DOM updates (faster, smaller bundle)
5. **`bind:`** for two-way binding, `on:` for events, `class:` for conditional classes'''
    ),
    (
        "svelte/stores-sveltekit",
        "Show Svelte stores and SvelteKit patterns: writable/derived stores, load functions, form actions, and routing.",
        '''Svelte stores and SvelteKit patterns:

```typescript
// src/lib/stores/auth.ts
import { writable, derived, get } from 'svelte/store'
import type { Writable } from 'svelte/store'

interface User { id: string; name: string; role: string }

// Writable store
function createAuthStore() {
  const { subscribe, set, update }: Writable<User | null> = writable(null)

  return {
    subscribe,
    login: async (email: string, password: string) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (!res.ok) throw new Error('Login failed')
      const user = await res.json()
      set(user)
    },
    logout: () => {
      set(null)
      fetch('/api/auth/logout', { method: 'POST' })
    },
  }
}

export const auth = createAuthStore()

// Derived store (computed from other stores)
export const isAuthenticated = derived(auth, ($auth) => $auth !== null)
export const isAdmin = derived(auth, ($auth) => $auth?.role === 'admin')


// src/lib/stores/cart.ts
interface CartItem { id: string; name: string; price: number; qty: number }

function createCartStore() {
  const { subscribe, update, set } = writable<CartItem[]>([])

  return {
    subscribe,
    add: (item: Omit<CartItem, 'qty'>) => update(items => {
      const existing = items.find(i => i.id === item.id)
      if (existing) {
        return items.map(i => i.id === item.id ? { ...i, qty: i.qty + 1 } : i)
      }
      return [...items, { ...item, qty: 1 }]
    }),
    remove: (id: string) => update(items => items.filter(i => i.id !== id)),
    clear: () => set([]),
  }
}

export const cart = createCartStore()
export const cartTotal = derived(cart, ($cart) =>
  $cart.reduce((sum, item) => sum + item.price * item.qty, 0)
)
```

```typescript
// SvelteKit: src/routes/products/+page.server.ts
import type { PageServerLoad, Actions } from './$types'
import { fail, redirect } from '@sveltejs/kit'

// Load function (runs on server)
export const load: PageServerLoad = async ({ fetch, url, depends }) => {
  const page = Number(url.searchParams.get('page') || '1')
  const search = url.searchParams.get('q') || ''

  const res = await fetch(`/api/products?page=${page}&q=${search}`)
  if (!res.ok) throw new Error('Failed to load products')

  // Mark dependency for invalidation
  depends('app:products')

  const data = await res.json()
  return {
    products: data.items,
    total: data.total,
    page,
  }
}

// Form actions (progressive enhancement)
export const actions: Actions = {
  create: async ({ request, locals }) => {
    if (!locals.user) throw redirect(303, '/login')

    const formData = await request.formData()
    const name = formData.get('name')?.toString()
    const price = Number(formData.get('price'))

    if (!name || name.length < 2) {
      return fail(400, { name, error: 'Name must be at least 2 chars' })
    }

    await db.products.create({ name, price, userId: locals.user.id })
    return { success: true }
  },

  delete: async ({ request, locals }) => {
    const formData = await request.formData()
    const id = formData.get('id')?.toString()
    if (!id) return fail(400, { error: 'Missing ID' })

    await db.products.delete(id)
    return { success: true }
  },
}
```

```svelte
<!-- src/routes/products/+page.svelte -->
<script lang="ts">
  import { enhance } from '$app/forms'
  import { invalidate } from '$app/navigation'
  import { cart, cartTotal } from '$lib/stores/cart'

  export let data  // From load function
  export let form  // From form action response

  // Auto-subscribe with $ prefix
  $: total = $cartTotal
</script>

<h1>Products ({data.total})</h1>

<!-- Form with progressive enhancement -->
<form method="POST" action="?/create" use:enhance>
  <input name="name" value={form?.name ?? ''} />
  <input name="price" type="number" step="0.01" />
  {#if form?.error}
    <p class="error">{form.error}</p>
  {/if}
  <button type="submit">Add Product</button>
</form>

{#each data.products as product (product.id)}
  <div class="product">
    <h3>{product.name} — ${product.price}</h3>
    <button on:click={() => cart.add(product)}>Add to Cart</button>

    <form method="POST" action="?/delete" use:enhance>
      <input type="hidden" name="id" value={product.id} />
      <button type="submit">Delete</button>
    </form>
  </div>
{/each}

<p>Cart total: ${total.toFixed(2)}</p>
```

SvelteKit patterns:
1. **`+page.server.ts`** — server-side load functions and form actions
2. **`use:enhance`** — progressive enhancement (works without JS, enhanced with JS)
3. **`$store` syntax** — auto-subscribe to stores in components
4. **`derived`** — computed stores that update when source stores change
5. **`invalidate`** — trigger re-fetching of load function data'''
    ),
]
"""
