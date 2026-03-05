"""Vue.js — Composition API, reactivity, components, and state management."""

PAIRS = [
    (
        "vue/composition-api",
        "Show Vue 3 Composition API patterns: reactive state, computed, watchers, composables, and lifecycle hooks.",
        """Vue 3 Composition API patterns:

```vue
<script setup lang="ts">
import { ref, reactive, computed, watch, watchEffect,
         onMounted, onUnmounted, provide, inject,
         toRefs, shallowRef } from 'vue'

// --- Reactive state ---

// ref for primitives
const count = ref(0)
const name = ref('Alice')

// reactive for objects (deep reactivity)
const user = reactive({
  name: 'Alice',
  email: 'alice@example.com',
  preferences: { theme: 'dark', language: 'en' },
})

// shallowRef for large objects (only .value triggers updates)
const largeList = shallowRef<Item[]>([])


// --- Computed properties ---

const doubleCount = computed(() => count.value * 2)

// Writable computed
const fullName = computed({
  get: () => `${user.firstName} ${user.lastName}`,
  set: (val: string) => {
    const [first, ...rest] = val.split(' ')
    user.firstName = first
    user.lastName = rest.join(' ')
  },
})


// --- Watchers ---

// Watch specific ref
watch(count, (newVal, oldVal) => {
  console.log(`Count: ${oldVal} -> ${newVal}`)
})

// Watch reactive object property
watch(
  () => user.preferences.theme,
  (theme) => { document.body.className = theme },
)

// Watch multiple sources
watch([count, name], ([newCount, newName]) => {
  console.log(`${newName}: ${newCount}`)
})

// watchEffect (auto-tracks dependencies)
watchEffect(() => {
  document.title = `${name.value} (${count.value})`
})


// --- Lifecycle hooks ---

onMounted(() => {
  console.log('Component mounted')
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})


// --- Event handling ---

const emit = defineEmits<{
  (e: 'update', value: number): void
  (e: 'delete', id: string): void
}>()

function increment() {
  count.value++
  emit('update', count.value)
}


// --- Props with defaults ---

interface Props {
  title: string
  items?: string[]
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  loading: false,
})


// --- Expose (for parent refs) ---

defineExpose({ count, increment })
</script>

<template>
  <div>
    <h1>{{ props.title }}</h1>
    <p>Count: {{ count }} (double: {{ doubleCount }})</p>
    <button @click="increment">+1</button>

    <ul v-if="!props.loading">
      <li v-for="item in props.items" :key="item">{{ item }}</li>
    </ul>
    <p v-else>Loading...</p>
  </div>
</template>
```

Composition API rules:
1. **`ref`** for primitives, **`reactive`** for objects
2. **`computed`** for derived state (cached, only recalculates when deps change)
3. **`watch`** for side effects on specific changes, **`watchEffect`** for auto-tracking
4. **`<script setup>`** — compiler macro that eliminates boilerplate
5. **`shallowRef`** for large data that doesn't need deep reactivity"""
    ),
    (
        "vue/composables",
        "Show Vue 3 composable patterns: reusable logic, async data fetching, and shared state.",
        """Vue 3 composable patterns for reusable logic:

```typescript
// composables/useFetch.ts
import { ref, watchEffect, type Ref } from 'vue'

interface UseFetchReturn<T> {
  data: Ref<T | null>
  error: Ref<string | null>
  loading: Ref<boolean>
  refetch: () => Promise<void>
}

export function useFetch<T>(url: Ref<string> | string): UseFetchReturn<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function fetchData() {
    loading.value = true
    error.value = null
    try {
      const response = await fetch(typeof url === 'string' ? url : url.value)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      data.value = await response.json()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  // Auto-refetch when URL changes (if reactive)
  if (typeof url !== 'string') {
    watchEffect(() => { if (url.value) fetchData() })
  } else {
    fetchData()
  }

  return { data, error, loading, refetch: fetchData }
}


// composables/useLocalStorage.ts
import { ref, watch, type Ref } from 'vue'

export function useLocalStorage<T>(key: string, defaultValue: T): Ref<T> {
  const stored = localStorage.getItem(key)
  const data = ref<T>(stored ? JSON.parse(stored) : defaultValue) as Ref<T>

  watch(data, (val) => {
    localStorage.setItem(key, JSON.stringify(val))
  }, { deep: true })

  return data
}


// composables/useDebounce.ts
import { ref, watch, type Ref } from 'vue'

export function useDebounce<T>(source: Ref<T>, delay: number = 300): Ref<T> {
  const debounced = ref(source.value) as Ref<T>
  let timeout: ReturnType<typeof setTimeout>

  watch(source, (val) => {
    clearTimeout(timeout)
    timeout = setTimeout(() => { debounced.value = val }, delay)
  })

  return debounced
}


// composables/useIntersectionObserver.ts
import { ref, onMounted, onUnmounted, type Ref } from 'vue'

export function useIntersectionObserver(
  target: Ref<HTMLElement | null>,
  options: IntersectionObserverInit = {},
) {
  const isVisible = ref(false)
  let observer: IntersectionObserver | null = null

  onMounted(() => {
    observer = new IntersectionObserver(([entry]) => {
      isVisible.value = entry.isIntersecting
    }, options)

    if (target.value) observer.observe(target.value)
  })

  onUnmounted(() => observer?.disconnect())

  return { isVisible }
}


// composables/useEventListener.ts
import { onMounted, onUnmounted } from 'vue'

export function useEventListener(
  target: EventTarget,
  event: string,
  handler: EventListener,
) {
  onMounted(() => target.addEventListener(event, handler))
  onUnmounted(() => target.removeEventListener(event, handler))
}


// --- Usage in component ---
// <script setup lang="ts">
// import { ref, computed } from 'vue'
// import { useFetch } from '@/composables/useFetch'
// import { useDebounce } from '@/composables/useDebounce'
// import { useLocalStorage } from '@/composables/useLocalStorage'
//
// const search = ref('')
// const debouncedSearch = useDebounce(search, 300)
// const apiUrl = computed(() => `/api/users?q=${debouncedSearch.value}`)
// const { data: users, loading, error } = useFetch<User[]>(apiUrl)
// const theme = useLocalStorage('theme', 'light')
// </script>
```

Composable conventions:
1. **Name with `use` prefix** — `useFetch`, `useAuth`, `useLocalStorage`
2. **Return refs** — callers decide how to use reactive values
3. **Accept refs or plain values** — flexible inputs with `MaybeRef<T>`
4. **Handle cleanup** — use `onUnmounted` to prevent memory leaks
5. **Single responsibility** — one composable per concern, compose together"""
    ),
    (
        "vue/pinia-state",
        "Show Vue 3 Pinia state management: stores, actions, getters, and composing stores.",
        """Pinia state management for Vue 3:

```typescript
// stores/auth.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

// Setup store syntax (Composition API style)
export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))
  const loading = ref(false)

  // Getters (computed)
  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const displayName = computed(() =>
    user.value ? `${user.value.firstName} ${user.value.lastName}` : 'Guest'
  )

  // Actions
  async function login(email: string, password: string) {
    loading.value = true
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!response.ok) throw new Error('Login failed')

      const data = await response.json()
      token.value = data.token
      user.value = data.user
      localStorage.setItem('token', data.token)
    } finally {
      loading.value = false
    }
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('token')
  }

  async function fetchProfile() {
    if (!token.value) return
    const response = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token.value}` },
    })
    if (response.ok) {
      user.value = await response.json()
    } else {
      logout()
    }
  }

  return {
    user, token, loading,
    isAuthenticated, isAdmin, displayName,
    login, logout, fetchProfile,
  }
})


// stores/cart.ts
export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>([])

  const totalItems = computed(() =>
    items.value.reduce((sum, item) => sum + item.quantity, 0)
  )

  const totalPrice = computed(() =>
    items.value.reduce((sum, item) => sum + item.price * item.quantity, 0)
  )

  function addItem(product: Product, quantity: number = 1) {
    const existing = items.value.find(i => i.productId === product.id)
    if (existing) {
      existing.quantity += quantity
    } else {
      items.value.push({
        productId: product.id,
        name: product.name,
        price: product.price,
        quantity,
      })
    }
  }

  function removeItem(productId: string) {
    items.value = items.value.filter(i => i.productId !== productId)
  }

  function updateQuantity(productId: string, quantity: number) {
    const item = items.value.find(i => i.productId === productId)
    if (item) {
      item.quantity = Math.max(0, quantity)
      if (item.quantity === 0) removeItem(productId)
    }
  }

  function clear() { items.value = [] }

  return {
    items, totalItems, totalPrice,
    addItem, removeItem, updateQuantity, clear,
  }
}, {
  // Pinia plugin: persist to localStorage
  persist: true,
})


// stores/notifications.ts — Composing stores
export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<Notification[]>([])
  let nextId = 0

  function add(message: string, type: 'success' | 'error' | 'info' = 'info') {
    const id = nextId++
    items.value.push({ id, message, type, timestamp: Date.now() })
    setTimeout(() => remove(id), 5000)
  }

  function remove(id: number) {
    items.value = items.value.filter(n => n.id !== id)
  }

  return { items, add, remove }
})


// --- Usage in component ---
// <script setup>
// import { useAuthStore } from '@/stores/auth'
// import { useCartStore } from '@/stores/cart'
// import { storeToRefs } from 'pinia'
//
// const auth = useAuthStore()
// const cart = useCartStore()
//
// // Destructure while preserving reactivity
// const { user, isAuthenticated } = storeToRefs(auth)
// const { totalItems, totalPrice } = storeToRefs(cart)
//
// // Actions can be destructured directly
// const { login, logout } = auth
// const { addItem } = cart
// </script>
```

Pinia patterns:
1. **Setup syntax** — use Composition API inside `defineStore` for full TypeScript support
2. **`storeToRefs`** — destructure state/getters without losing reactivity
3. **Actions are just functions** — no mutations needed, direct state modification
4. **Compose stores** — use one store inside another via `useOtherStore()`
5. **Plugins** — add persistence, logging, or devtools integration"""
    ),
]
