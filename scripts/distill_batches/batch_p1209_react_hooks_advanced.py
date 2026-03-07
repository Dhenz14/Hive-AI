"""
Batch P1209 -- React hooks advanced: useReducer patterns, custom hooks,
useSyncExternalStore, useTransition, useOptimistic.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: useReducer patterns ---
    {
        "instruction": r'''When should I use useReducer instead of useState in React? Show a complex form example with TypeScript.''',
        "output": r'''<think>
useReducer is better when state transitions depend on previous state or
when multiple values are related. For a form example I will show
discriminated union actions, typed state with validation, and why a
pure reducer is testable without rendering. Also dispatch has stable
identity preventing unnecessary re-renders.
</think>

Use `useReducer` when state transitions are complex or interdependent:

```typescript
import { useReducer, FormEvent } from "react";

interface FormState {
  values: { email: string; password: string };
  errors: Partial<Record<"email" | "password", string>>;
  isSubmitting: boolean;
}

type Action =
  | { type: "SET_FIELD"; field: "email" | "password"; value: string }
  | { type: "SUBMIT_START" }
  | { type: "SUBMIT_SUCCESS" }
  | { type: "SUBMIT_ERROR" };

const init: FormState = { values: { email: "", password: "" }, errors: {}, isSubmitting: false };

function validate(v: FormState["values"]) {
  const e: FormState["errors"] = {};
  if (!v.email.includes("@")) e.email = "Invalid email";
  if (v.password.length < 8) e.password = "Min 8 chars";
  return e;
}

// Pure reducer -- testable without React
function formReducer(state: FormState, action: Action): FormState {
  switch (action.type) {
    case "SET_FIELD": {
      const values = { ...state.values, [action.field]: action.value };
      return { ...state, values, errors: validate(values) };
    }
    case "SUBMIT_START": return { ...state, isSubmitting: true };
    case "SUBMIT_SUCCESS": return init;
    case "SUBMIT_ERROR": return { ...state, isSubmitting: false };
  }
}

function LoginForm() {
  const [s, dispatch] = useReducer(formReducer, init);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    dispatch({ type: "SUBMIT_START" });
    try {
      await fetch("/api/login", { method: "POST", body: JSON.stringify(s.values) });
      dispatch({ type: "SUBMIT_SUCCESS" });
    } catch { dispatch({ type: "SUBMIT_ERROR" }); }
  };
  return (
    <form onSubmit={submit}>
      <input value={s.values.email}
        onChange={(e) => dispatch({ type: "SET_FIELD", field: "email", value: e.target.value })} />
      {s.errors.email && <span>{s.errors.email}</span>}
      <button disabled={s.isSubmitting}>Submit</button>
    </form>
  );
}
```

Benefits: centralized transitions, testable pure reducer, stable `dispatch` identity.'''
    },

    # --- 2. direct: custom hooks ---
    {
        "instruction": r'''Show how to build reusable custom React hooks in TypeScript. Include a useLocalStorage and a useFetch hook.''',
        "output": r'''Custom hooks extract reusable stateful logic:

```typescript
import { useState, useEffect, useCallback, useRef } from "react";

function useLocalStorage<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [stored, setStored] = useState<T>(() => {
    try {
      const item = localStorage.getItem(key);
      return item !== null ? JSON.parse(item) : initial;
    } catch { return initial; }
  });
  const setValue = useCallback((value: T | ((p: T) => T)) => {
    setStored((prev) => {
      const next = value instanceof Function ? value(prev) : value;
      localStorage.setItem(key, JSON.stringify(next));
      return next;
    });
  }, [key]);
  return [stored, setValue];
}

interface FetchState<T> { data: T | null; error: string | null; isLoading: boolean; }

function useFetch<T>(url: string | null): FetchState<T> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<T>>({ data: null, error: null, isLoading: false });
  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    if (!url) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const res = await fetch(url, { signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: T = await res.json();
      setState({ data, error: null, isLoading: false });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setState({ data: null, error: String(err), isLoading: false });
    }
  }, [url]);

  useEffect(() => { fetchData(); return () => abortRef.current?.abort(); }, [fetchData]);
  return { ...state, refetch: fetchData };
}

function UserProfile({ id }: { id: string }) {
  const [theme, setTheme] = useLocalStorage("theme", "light");
  const { data, isLoading } = useFetch<{ name: string }>(`/api/users/${id}`);
  if (isLoading) return <div>Loading...</div>;
  return <div data-theme={theme}><h1>{data?.name}</h1></div>;
}
```

Rules: start with `use`, call hooks unconditionally, use `useCallback`/`useRef` to keep refs stable.'''
    },

    # --- 3. direct: useSyncExternalStore ---
    {
        "instruction": r'''How does React useSyncExternalStore work? Show how to subscribe to an external store like browser localStorage changes.''',
        "output": r'''`useSyncExternalStore` subscribes React to external data sources with tearing-safe reads:

```typescript
import { useSyncExternalStore, useCallback } from "react";

// 1. Subscribe to localStorage across tabs
function useLocalStorageSync(key: string): string | null {
  const subscribe = useCallback((cb: () => void) => {
    const handler = (e: StorageEvent) => { if (e.key === key) cb(); };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [key]);
  const getSnapshot = useCallback(() => localStorage.getItem(key), [key]);
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

// 2. Custom pub-sub store
function createStore<T>(initial: T) {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => value,
    subscribe: (l: () => void) => { listeners.add(l); return () => listeners.delete(l); },
    setState: (next: T | ((p: T) => T)) => {
      value = next instanceof Function ? next(value) : next;
      listeners.forEach((l) => l());
    },
  };
}

const counter = createStore({ count: 0 });

function useCounter() {
  const state = useSyncExternalStore(counter.subscribe, counter.getSnapshot);
  return {
    count: state.count,
    inc: () => counter.setState((s) => ({ count: s.count + 1 })),
  };
}

// 3. Online status
function useOnlineStatus(): boolean {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("online", cb);
      window.addEventListener("offline", cb);
      return () => { window.removeEventListener("online", cb); window.removeEventListener("offline", cb); };
    },
    () => navigator.onLine,
    () => true
  );
}
```

Use it for browser APIs, third-party state, WebSocket data -- anything outside React's state model.'''
    },

    # --- 4. thinking: useTransition ---
    {
        "instruction": r'''How does React useTransition work for keeping the UI responsive during expensive state updates? Show a search filtering example.''',
        "output": r'''<think>
useTransition marks state updates as non-urgent. React can interrupt them
to handle urgent updates like typing first. The canonical example is
filtering a large list while typing. Without it, every keystroke re-renders
the full list causing lag. Different from debouncing -- debouncing delays
the update, useTransition starts immediately but at lower priority.
</think>

`useTransition` marks updates as non-urgent so user input stays responsive:

```typescript
import { useState, useTransition, useMemo } from "react";

const allItems = Array.from({ length: 20_000 }, (_, i) => ({
  id: i, name: `Item ${i}`,
  category: ["electronics", "books", "clothing"][i % 3],
}));

function SearchableList() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [isPending, startTransition] = useTransition();

  const filtered = useMemo(() => {
    if (!filter) return allItems;
    const lower = filter.toLowerCase();
    return allItems.filter((item) =>
      item.name.toLowerCase().includes(lower) || item.category.includes(lower)
    );
  }, [filter]);

  const handleSearch = (value: string) => {
    setQuery(value);                     // urgent: update input
    startTransition(() => setFilter(value)); // non-urgent: filter list
  };

  return (
    <div>
      <input value={query} onChange={(e) => handleSearch(e.target.value)}
        placeholder="Search 20,000 items..." />
      {isPending && <div>Filtering...</div>}
      <div style={{ opacity: isPending ? 0.7 : 1 }}>
        <p>{filtered.length} results</p>
        <ul>
          {filtered.slice(0, 100).map((item) => (
            <li key={item.id}>{item.name} - {item.category}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
```

Unlike debouncing (delays the update), `useTransition` starts immediately at lower priority. If new input arrives, React abandons the in-progress transition and restarts with the latest value.'''
    },

    # --- 5. direct: useOptimistic ---
    {
        "instruction": r'''Show how React useOptimistic works for instant UI updates that revert on server failure.''',
        "output": r'''`useOptimistic` (React 19) shows immediate optimistic state while an async action is pending. On failure it reverts automatically:

```typescript
import { useOptimistic, useState, useTransition } from "react";

interface Message { id: string; text: string; sending?: boolean; }

function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isPending, startTransition] = useTransition();

  const [optimistic, addOptimistic] = useOptimistic(
    messages,
    (current: Message[], text: string) => [
      ...current,
      { id: "temp-" + Date.now(), text, sending: true },
    ]
  );

  async function handleSend(formData: FormData) {
    const text = formData.get("message") as string;
    if (!text?.trim()) return;

    startTransition(async () => {
      addOptimistic(text);
      try {
        const res = await fetch("/api/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const saved: Message = await res.json();
        setMessages((prev) => [...prev, saved]);
      } catch {
        // Optimistic state reverts automatically on failure
        alert("Failed to send");
      }
    });
  }

  return (
    <div>
      <ul>
        {optimistic.map((msg) => (
          <li key={msg.id} style={{ opacity: msg.sending ? 0.6 : 1 }}>
            {msg.text}{msg.sending && " (sending...)"}
          </li>
        ))}
      </ul>
      <form action={handleSend}>
        <input name="message" placeholder="Type a message" />
        <button type="submit" disabled={isPending}>Send</button>
      </form>
    </div>
  );
}
```

When the transition completes or throws, `useOptimistic` switches back to the real `useState` value, eliminating loading spinner delays for mutations.'''
    },
]
