"""React Hooks Deep Patterns — data fetching, complex reducers, external stores, optimistic UI, hook composition."""

PAIRS = [
    (
        "typescript/production",
        r'''Build a custom React hook for data fetching with AbortController support, automatic cleanup, retry logic, and proper TypeScript generics. Show production-ready patterns.''',
        r'''# Custom Data Fetching Hook with AbortController

A production fetching hook needs cancellation on unmount/refetch, retry with backoff, proper error typing, and stale-while-revalidate support.

## Core Implementation

```typescript
import { useCallback, useEffect, useRef, useState } from "react";

// Discriminated union for fetch state — no impossible states
type FetchState<T> =
  | { status: "idle" }
  | { status: "loading"; isRevalidating: boolean }
  | { status: "success"; data: T; fetchedAt: number; isRevalidating: boolean }
  | { status: "error"; error: FetchError; retryCount: number };

class FetchError extends Error {
  constructor(
    message: string,
    public statusCode: number | null,
    public isAborted: boolean
  ) {
    super(message);
    this.name = "FetchError";
  }
}

interface UseFetchOptions<T> {
  /** Skip fetching (e.g., when params aren't ready) */
  enabled?: boolean;
  /** Auto-retry count on failure (default: 3) */
  retryCount?: number;
  /** Retry delay in ms — doubles each attempt */
  retryDelay?: number;
  /** Stale time in ms — refetch if data older than this */
  staleTime?: number;
  /** Transform the raw JSON before storing */
  transform?: (raw: unknown) => T;
  /** Called on successful fetch */
  onSuccess?: (data: T) => void;
  /** Called on error */
  onError?: (error: FetchError) => void;
}

function useFetch<T>(
  url: string | null,
  options: UseFetchOptions<T> = {}
): FetchState<T> & { refetch: () => void; abort: () => void } {
  const {
    enabled = true,
    retryCount = 3,
    retryDelay = 1000,
    staleTime = 0,
    transform,
    onSuccess,
    onError,
  } = options;

  const [state, setState] = useState<FetchState<T>>({ status: "idle" });
  const abortControllerRef = useRef<AbortController | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const abort = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const fetchData = useCallback(
    async (attempt: number = 0) => {
      if (!url) return;

      // Abort any in-flight request
      abort();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      // If we have cached data, mark as revalidating instead of loading
      setState((prev) =>
        prev.status === "success"
          ? { ...prev, isRevalidating: true }
          : { status: "loading", isRevalidating: attempt > 0 }
      );

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });

        if (!response.ok) {
          throw new FetchError(
            `HTTP ${response.status}: ${response.statusText}`,
            response.status,
            false
          );
        }

        const raw = await response.json();
        const data = transform ? transform(raw) : (raw as T);

        if (!mountedRef.current) return;

        setState({
          status: "success",
          data,
          fetchedAt: Date.now(),
          isRevalidating: false,
        });
        onSuccess?.(data);
      } catch (err) {
        if (!mountedRef.current) return;

        if (err instanceof DOMException && err.name === "AbortError") {
          // Request was intentionally aborted — do not update state
          return;
        }

        const fetchError =
          err instanceof FetchError
            ? err
            : new FetchError(
                err instanceof Error ? err.message : "Unknown error",
                null,
                false
              );

        // Retry logic with exponential backoff
        if (attempt < retryCount && !fetchError.isAborted) {
          const delay = retryDelay * Math.pow(2, attempt);
          retryTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) fetchData(attempt + 1);
          }, delay);
          return;
        }

        setState({
          status: "error",
          error: fetchError,
          retryCount: attempt,
        });
        onError?.(fetchError);
      }
    },
    [url, abort, retryCount, retryDelay, transform, onSuccess, onError]
  );

  // Fetch on mount and when URL/enabled changes
  useEffect(() => {
    mountedRef.current = true;

    if (!enabled || !url) {
      setState({ status: "idle" });
      return;
    }

    // Check if cached data is still fresh
    if (state.status === "success" && staleTime > 0) {
      const age = Date.now() - state.fetchedAt;
      if (age < staleTime) return; // Data is fresh, skip fetch
    }

    fetchData();

    return () => {
      mountedRef.current = false;
      abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled]);

  return {
    ...state,
    refetch: () => fetchData(0),
    abort,
  };
}
```

## Usage in Components

```typescript
interface User {
  id: string;
  name: string;
  email: string;
}

function UserProfile({ userId }: { userId: string }) {
  const user = useFetch<User>(
    userId ? `/api/users/${userId}` : null,
    {
      enabled: !!userId,
      retryCount: 2,
      staleTime: 30_000, // 30 seconds
      onError: (err) => console.error("Failed to load user:", err),
    }
  );

  switch (user.status) {
    case "idle":
      return null;
    case "loading":
      return <UserSkeleton />;
    case "error":
      return (
        <ErrorPanel>
          <p>{user.error.message}</p>
          <p>Retried {user.retryCount} times</p>
          <button onClick={user.refetch}>Try Again</button>
        </ErrorPanel>
      );
    case "success":
      return (
        <div style={{ opacity: user.isRevalidating ? 0.7 : 1 }}>
          <h2>{user.data.name}</h2>
          <p>{user.data.email}</p>
        </div>
      );
  }
}
```

## Common Pitfalls

1. **Not aborting on unmount**: Without `AbortController`, navigating away triggers state updates on unmounted components. Always abort in the cleanup function.
2. **Race conditions**: Rapid URL changes can cause out-of-order responses. The abort pattern ensures only the latest request's response is applied.
3. **Stale closures in retry**: The `retryTimeoutRef` ensures the timeout is cleaned up. Without it, retries can fire after unmount.
4. **Missing `enabled` flag**: Fetching before params are ready causes 404s. Always gate with `enabled` when URL depends on dynamic values.
''',
    ),
    (
        "typescript/production",
        r'''Show how to use useReducer for complex form state in React, with TypeScript discriminated unions for actions, validation, and multi-step form flows.''',
        r'''# useReducer for Complex Form State

When form state involves validation rules, cross-field dependencies, multi-step flows, or undo/redo, `useState` leads to scattered logic. `useReducer` centralizes transitions and makes state changes predictable and testable.

## Production Multi-Step Form

```typescript
import { useReducer, useCallback } from "react";

// Step-specific data types
interface PersonalInfo {
  firstName: string;
  lastName: string;
  email: string;
}

interface CompanyInfo {
  companyName: string;
  role: string;
  teamSize: "1-10" | "11-50" | "51-200" | "200+";
}

interface Preferences {
  plan: "starter" | "pro" | "enterprise";
  notifications: boolean;
  newsletter: boolean;
}

// Validation errors per field
type FieldErrors<T> = Partial<Record<keyof T, string>>;

// Form state with discriminated step
type FormState =
  | {
      step: "personal";
      data: PersonalInfo;
      errors: FieldErrors<PersonalInfo>;
      touched: Set<keyof PersonalInfo>;
    }
  | {
      step: "company";
      personal: PersonalInfo; // validated and locked
      data: CompanyInfo;
      errors: FieldErrors<CompanyInfo>;
      touched: Set<keyof CompanyInfo>;
    }
  | {
      step: "preferences";
      personal: PersonalInfo;
      company: CompanyInfo;
      data: Preferences;
      errors: FieldErrors<Preferences>;
      touched: Set<keyof Preferences>;
    }
  | {
      step: "submitting";
      personal: PersonalInfo;
      company: CompanyInfo;
      preferences: Preferences;
    }
  | {
      step: "success";
      accountId: string;
    }
  | {
      step: "error";
      message: string;
      personal: PersonalInfo;
      company: CompanyInfo;
      preferences: Preferences;
    };

// All possible actions
type FormAction =
  | { type: "UPDATE_FIELD"; field: string; value: string | boolean }
  | { type: "BLUR_FIELD"; field: string }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "SUBMIT_SUCCESS"; accountId: string }
  | { type: "SUBMIT_ERROR"; message: string }
  | { type: "RETRY" };

// Validators
function validatePersonal(data: PersonalInfo): FieldErrors<PersonalInfo> {
  const errors: FieldErrors<PersonalInfo> = {};
  if (!data.firstName.trim()) errors.firstName = "First name is required";
  if (!data.lastName.trim()) errors.lastName = "Last name is required";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) errors.email = "Valid email required";
  return errors;
}

function validateCompany(data: CompanyInfo): FieldErrors<CompanyInfo> {
  const errors: FieldErrors<CompanyInfo> = {};
  if (!data.companyName.trim()) errors.companyName = "Company name is required";
  if (!data.role.trim()) errors.role = "Role is required";
  return errors;
}

function hasErrors<T>(errors: FieldErrors<T>): boolean {
  return Object.keys(errors).length > 0;
}

// Reducer
function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case "UPDATE_FIELD": {
      if (state.step === "submitting" || state.step === "success") return state;
      return {
        ...state,
        data: { ...state.data, [action.field]: action.value },
        errors: { ...state.errors, [action.field]: undefined },
      } as FormState;
    }

    case "BLUR_FIELD": {
      if (state.step === "personal") {
        const field = action.field as keyof PersonalInfo;
        const newTouched = new Set(state.touched).add(field);
        const allErrors = validatePersonal(state.data);
        return { ...state, touched: newTouched, errors: { [field]: allErrors[field] } as FieldErrors<PersonalInfo> };
      }
      if (state.step === "company") {
        const field = action.field as keyof CompanyInfo;
        const newTouched = new Set(state.touched).add(field);
        const allErrors = validateCompany(state.data);
        return { ...state, touched: newTouched, errors: { [field]: allErrors[field] } as FieldErrors<CompanyInfo> };
      }
      return state;
    }

    case "NEXT_STEP": {
      if (state.step === "personal") {
        const errors = validatePersonal(state.data);
        if (hasErrors(errors)) {
          return { ...state, errors, touched: new Set(Object.keys(state.data) as Array<keyof PersonalInfo>) };
        }
        return {
          step: "company",
          personal: state.data,
          data: { companyName: "", role: "", teamSize: "1-10" },
          errors: {},
          touched: new Set<keyof CompanyInfo>(),
        };
      }
      if (state.step === "company") {
        const errors = validateCompany(state.data);
        if (hasErrors(errors)) {
          return { ...state, errors, touched: new Set(Object.keys(state.data) as Array<keyof CompanyInfo>) };
        }
        return {
          step: "preferences",
          personal: state.personal,
          company: state.data,
          data: { plan: "starter", notifications: true, newsletter: false },
          errors: {},
          touched: new Set<keyof Preferences>(),
        };
      }
      if (state.step === "preferences") {
        return {
          step: "submitting",
          personal: state.personal,
          company: state.company,
          preferences: state.data,
        };
      }
      return state;
    }

    case "PREV_STEP": {
      if (state.step === "company") {
        return {
          step: "personal",
          data: state.personal,
          errors: {},
          touched: new Set<keyof PersonalInfo>(),
        };
      }
      if (state.step === "preferences") {
        return {
          step: "company",
          personal: state.personal,
          data: state.company,
          errors: {},
          touched: new Set<keyof CompanyInfo>(),
        };
      }
      return state;
    }

    case "SUBMIT_SUCCESS":
      return { step: "success", accountId: action.accountId };

    case "SUBMIT_ERROR":
      if (state.step !== "submitting") return state;
      return {
        step: "error",
        message: action.message,
        personal: state.personal,
        company: state.company,
        preferences: state.preferences,
      };

    case "RETRY":
      if (state.step !== "error") return state;
      return {
        step: "submitting",
        personal: state.personal,
        company: state.company,
        preferences: state.preferences,
      };

    default:
      return state;
  }
}

// Initial state
const initialState: FormState = {
  step: "personal",
  data: { firstName: "", lastName: "", email: "" },
  errors: {},
  touched: new Set(),
};
```

## Hook Wrapper

```typescript
function useSignupForm() {
  const [state, dispatch] = useReducer(formReducer, initialState);

  const updateField = useCallback(
    (field: string, value: string | boolean) =>
      dispatch({ type: "UPDATE_FIELD", field, value }),
    []
  );

  const blurField = useCallback(
    (field: string) => dispatch({ type: "BLUR_FIELD", field }),
    []
  );

  const nextStep = useCallback(() => dispatch({ type: "NEXT_STEP" }), []);
  const prevStep = useCallback(() => dispatch({ type: "PREV_STEP" }), []);

  // Handle submission side effect
  useEffect(() => {
    if (state.step !== "submitting") return;

    const controller = new AbortController();
    fetch("/api/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...state.personal,
        ...state.company,
        ...state.preferences,
      }),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => dispatch({ type: "SUBMIT_SUCCESS", accountId: data.id }))
      .catch((err) => {
        if (err.name !== "AbortError") {
          dispatch({ type: "SUBMIT_ERROR", message: err.message });
        }
      });

    return () => controller.abort();
  }, [state.step]);

  return { state, updateField, blurField, nextStep, prevStep };
}
```

## Common Pitfalls

1. **Putting async logic inside the reducer**: Reducers must be pure. Use `useEffect` to trigger side effects when state transitions to a "submitting" step.
2. **Mutating `Set` or `Map` in state**: `new Set(state.touched).add(field)` creates a new Set. Mutating the original will not trigger a re-render.
3. **Over-broad action types**: `{ type: "UPDATE"; payload: Partial<FormState> }` loses all type safety. Use specific actions for specific transitions.
''',
    ),
    (
        "typescript/production",
        r'''Demonstrate useSyncExternalStore for subscribing React components to shared external state. Show a production pattern with a typed store, selectors, and avoiding unnecessary re-renders.''',
        r'''# useSyncExternalStore for Shared External State

`useSyncExternalStore` is React's official API for subscribing to external (non-React) state sources. It handles concurrent rendering edge cases that `useEffect` + `useState` subscriptions cannot, and it works with server rendering via `getServerSnapshot`.

## Building a Typed External Store

```typescript
import { useSyncExternalStore, useCallback, useRef } from "react";

type Listener = () => void;

class Store<T> {
  private state: T;
  private listeners = new Set<Listener>();

  constructor(initialState: T) {
    this.state = initialState;
  }

  getSnapshot = (): T => {
    return this.state;
  };

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setState(updater: T | ((prev: T) => T)): void {
    const nextState =
      typeof updater === "function"
        ? (updater as (prev: T) => T)(this.state)
        : updater;

    if (Object.is(this.state, nextState)) return; // Skip if same reference
    this.state = nextState;
    this.listeners.forEach((listener) => listener());
  }

  // Batch multiple updates into one notification
  batch(fn: () => void): void {
    const prevState = this.state;
    // Temporarily suppress listeners
    const originalListeners = new Set(this.listeners);
    this.listeners.clear();

    fn();

    // Restore and notify once
    this.listeners = originalListeners;
    if (!Object.is(prevState, this.state)) {
      this.listeners.forEach((listener) => listener());
    }
  }
}
```

## Hook with Selector (Avoiding Re-Renders)

```typescript
// Without a selector, every consumer re-renders on ANY state change.
// This selector hook only re-renders when the selected slice changes.
function useStore<T, S>(
  store: Store<T>,
  selector: (state: T) => S
): S {
  // Cache the selector result to enable reference equality checks
  const selectorRef = useRef(selector);
  selectorRef.current = selector;

  const prevResultRef = useRef<S | undefined>(undefined);

  const getSnapshot = useCallback(() => {
    const nextResult = selectorRef.current(store.getSnapshot());

    // If the selector returns the same value, return the cached reference
    // This prevents unnecessary re-renders
    if (prevResultRef.current !== undefined && shallowEqual(prevResultRef.current, nextResult)) {
      return prevResultRef.current;
    }

    prevResultRef.current = nextResult;
    return nextResult;
  }, [store]);

  return useSyncExternalStore(store.subscribe, getSnapshot);
}

function shallowEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;

  const keysA = Object.keys(a as object);
  const keysB = Object.keys(b as object);
  if (keysA.length !== keysB.length) return false;

  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  return keysA.every((key) => Object.is(objA[key], objB[key]));
}
```

## Production Example: Notification System

```typescript
interface Notification {
  id: string;
  type: "info" | "success" | "warning" | "error";
  title: string;
  message: string;
  createdAt: number;
  read: boolean;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isOpen: boolean;
}

// Singleton store — lives outside React
const notificationStore = new Store<NotificationState>({
  notifications: [],
  unreadCount: 0,
  isOpen: false,
});

// Actions — pure functions that call setState
function addNotification(notification: Omit<Notification, "id" | "createdAt" | "read">) {
  notificationStore.setState((prev) => {
    const newNotification: Notification = {
      ...notification,
      id: crypto.randomUUID(),
      createdAt: Date.now(),
      read: false,
    };
    return {
      ...prev,
      notifications: [newNotification, ...prev.notifications].slice(0, 100),
      unreadCount: prev.unreadCount + 1,
    };
  });
}

function markAsRead(id: string) {
  notificationStore.setState((prev) => {
    const notification = prev.notifications.find((n) => n.id === id);
    if (!notification || notification.read) return prev;
    return {
      ...prev,
      notifications: prev.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
      unreadCount: Math.max(0, prev.unreadCount - 1),
    };
  });
}

function markAllAsRead() {
  notificationStore.setState((prev) => ({
    ...prev,
    notifications: prev.notifications.map((n) => ({ ...n, read: true })),
    unreadCount: 0,
  }));
}

function togglePanel() {
  notificationStore.setState((prev) => ({ ...prev, isOpen: !prev.isOpen }));
}

// Components — each subscribes only to the slice it needs
function NotificationBadge() {
  const unreadCount = useStore(notificationStore, (s) => s.unreadCount);

  return (
    <button onClick={togglePanel} aria-label={`${unreadCount} unread notifications`}>
      <BellIcon />
      {unreadCount > 0 && <span className="badge">{unreadCount}</span>}
    </button>
  );
}

function NotificationPanel() {
  const { notifications, isOpen } = useStore(notificationStore, (s) => ({
    notifications: s.notifications,
    isOpen: s.isOpen,
  }));

  if (!isOpen) return null;

  return (
    <aside role="complementary" aria-label="Notifications">
      <header>
        <h2>Notifications</h2>
        <button onClick={markAllAsRead}>Mark all read</button>
      </header>
      <ul>
        {notifications.map((n) => (
          <li key={n.id} data-read={n.read}>
            <strong>{n.title}</strong>
            <p>{n.message}</p>
            {!n.read && <button onClick={() => markAsRead(n.id)}>Mark read</button>}
          </li>
        ))}
      </ul>
    </aside>
  );
}

// Can be called from anywhere — even outside React
// e.g., from a WebSocket handler, service worker, etc.
websocket.on("message", (event) => {
  addNotification({ type: "info", title: "New message", message: event.data });
});
```

## Common Pitfalls

1. **Creating new objects in selectors**: `useStore(store, (s) => ({ a: s.a, b: s.b }))` creates a new object every call. The `shallowEqual` in our implementation handles this, but without it you get infinite re-renders.
2. **Forgetting `getServerSnapshot`**: For SSR, pass a third argument to `useSyncExternalStore` with the server-safe snapshot. Without it, hydration mismatches occur.
3. **Stale listeners**: If `subscribe` does not return an unsubscribe function, listeners accumulate and cause memory leaks.
4. **Mutating state**: Always return a new object from `setState`. Mutations bypass the `Object.is` check and skip notifications.
''',
    ),
    (
        "typescript/production",
        r'''Show how to implement optimistic UI updates in React using useTransition and useOptimistic. Include rollback on failure, with a production example like a todo list or like button.''',
        r'''# Optimistic UI with useTransition and useOptimistic

Optimistic UI updates the interface immediately before the server confirms the change, then rolls back if the server rejects it. React 19 provides `useOptimistic` for this exact pattern.

## Basic Pattern with useOptimistic

```typescript
import { useOptimistic, useTransition, useRef } from "react";

interface Message {
  id: string;
  text: string;
  authorId: string;
  createdAt: string;
  sending?: boolean; // Optimistic flag
}

function MessageThread({
  messages,
  currentUserId,
}: {
  messages: Message[];
  currentUserId: string;
}) {
  const formRef = useRef<HTMLFormElement>(null);

  // useOptimistic takes current state and returns [optimisticState, addOptimistic]
  const [optimisticMessages, addOptimisticMessage] = useOptimistic(
    messages,
    (currentMessages: Message[], newMessage: Message) => [
      ...currentMessages,
      { ...newMessage, sending: true },
    ]
  );

  async function sendMessage(formData: FormData) {
    const text = formData.get("text") as string;
    if (!text.trim()) return;

    const optimisticMessage: Message = {
      id: `temp-${crypto.randomUUID()}`,
      text,
      authorId: currentUserId,
      createdAt: new Date().toISOString(),
      sending: true,
    };

    // Immediately show the message in the UI
    addOptimisticMessage(optimisticMessage);
    formRef.current?.reset();

    try {
      // Server action or API call
      await postMessage({ text });
      // On success, the parent re-fetches and passes updated `messages` prop.
      // useOptimistic automatically replaces optimistic state with real state.
    } catch (error) {
      // On failure, React automatically rolls back — the optimistic message
      // disappears when the parent re-renders with unchanged `messages`.
      toast.error("Failed to send message. Please try again.");
    }
  }

  return (
    <div>
      <ul>
        {optimisticMessages.map((msg) => (
          <li key={msg.id} style={{ opacity: msg.sending ? 0.6 : 1 }}>
            <strong>{msg.authorId}</strong>: {msg.text}
            {msg.sending && <span className="sending-indicator">Sending...</span>}
          </li>
        ))}
      </ul>
      <form ref={formRef} action={sendMessage}>
        <input name="text" placeholder="Type a message..." required />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}
```

## Production Like Button with Rollback

```typescript
interface Post {
  id: string;
  title: string;
  likeCount: number;
  likedByMe: boolean;
}

function LikeButton({ post }: { post: Post }) {
  const [optimisticPost, setOptimisticPost] = useOptimistic(
    post,
    (current: Post, action: "like" | "unlike") => ({
      ...current,
      likedByMe: action === "like",
      likeCount: current.likeCount + (action === "like" ? 1 : -1),
    })
  );

  const [isPending, startTransition] = useTransition();

  async function handleToggleLike() {
    const action = optimisticPost.likedByMe ? "unlike" : "like";

    startTransition(async () => {
      setOptimisticPost(action);

      try {
        await fetch(`/api/posts/${post.id}/like`, {
          method: action === "like" ? "POST" : "DELETE",
        });
        // Revalidate to get server-confirmed count
      } catch {
        // Rollback happens automatically — useOptimistic reverts to `post` prop
        toast.error(action === "like" ? "Failed to like" : "Failed to unlike");
      }
    });
  }

  return (
    <button
      onClick={handleToggleLike}
      disabled={isPending}
      aria-pressed={optimisticPost.likedByMe}
      className={optimisticPost.likedByMe ? "liked" : ""}
    >
      {optimisticPost.likedByMe ? "❤" : "♡"} {optimisticPost.likeCount}
    </button>
  );
}
```

## Complex Optimistic Updates: Todo List with Reorder

```typescript
interface Todo {
  id: string;
  title: string;
  completed: boolean;
  position: number;
}

type OptimisticAction =
  | { type: "add"; todo: Todo }
  | { type: "toggle"; id: string }
  | { type: "delete"; id: string }
  | { type: "reorder"; id: string; newPosition: number };

function TodoList({
  todos,
  listId,
}: {
  todos: Todo[];
  listId: string;
}) {
  const [optimisticTodos, applyOptimistic] = useOptimistic(
    todos,
    (currentTodos: Todo[], action: OptimisticAction): Todo[] => {
      switch (action.type) {
        case "add":
          return [...currentTodos, { ...action.todo, id: `temp-${Date.now()}` }];
        case "toggle":
          return currentTodos.map((t) =>
            t.id === action.id ? { ...t, completed: !t.completed } : t
          );
        case "delete":
          return currentTodos.filter((t) => t.id !== action.id);
        case "reorder": {
          const item = currentTodos.find((t) => t.id === action.id);
          if (!item) return currentTodos;
          const without = currentTodos.filter((t) => t.id !== action.id);
          const updated = { ...item, position: action.newPosition };
          without.splice(action.newPosition, 0, updated);
          return without.map((t, i) => ({ ...t, position: i }));
        }
      }
    }
  );

  const [, startTransition] = useTransition();

  async function addTodo(formData: FormData) {
    const title = formData.get("title") as string;
    if (!title.trim()) return;

    const newTodo: Todo = {
      id: `temp-${Date.now()}`,
      title: title.trim(),
      completed: false,
      position: optimisticTodos.length,
    };

    startTransition(async () => {
      applyOptimistic({ type: "add", todo: newTodo });
      try {
        await createTodo(listId, { title: newTodo.title });
      } catch {
        toast.error("Failed to create todo");
      }
    });
  }

  async function toggleTodo(id: string) {
    startTransition(async () => {
      applyOptimistic({ type: "toggle", id });
      try {
        await updateTodo(id, {
          completed: !todos.find((t) => t.id === id)?.completed,
        });
      } catch {
        toast.error("Failed to update todo");
      }
    });
  }

  async function deleteTodo(id: string) {
    startTransition(async () => {
      applyOptimistic({ type: "delete", id });
      try {
        await removeTodo(id);
      } catch {
        toast.error("Failed to delete todo");
      }
    });
  }

  return (
    <div>
      <form action={addTodo}>
        <input name="title" placeholder="New todo..." required />
        <button type="submit">Add</button>
      </form>
      <ul>
        {optimisticTodos
          .sort((a, b) => a.position - b.position)
          .map((todo) => (
            <li key={todo.id} style={{ opacity: todo.id.startsWith("temp-") ? 0.6 : 1 }}>
              <input
                type="checkbox"
                checked={todo.completed}
                onChange={() => toggleTodo(todo.id)}
              />
              <span style={{ textDecoration: todo.completed ? "line-through" : "none" }}>
                {todo.title}
              </span>
              <button onClick={() => deleteTodo(todo.id)} aria-label={`Delete ${todo.title}`}>
                Delete
              </button>
            </li>
          ))}
      </ul>
    </div>
  );
}
```

## Common Pitfalls

1. **Not revalidating after success**: Optimistic state is a local illusion. After the server confirms, you must revalidate (e.g., via `revalidatePath` in Next.js or refetching the query) so the real data replaces the optimistic data.
2. **Stacking optimistic updates**: If a user clicks "like" twice rapidly, both optimistic updates apply. Debounce or disable the button during the transition.
3. **Temp IDs leaking**: Optimistic items often have temporary IDs. Never persist temp IDs to the server; always let the server assign the real ID.
4. **Missing loading indicators**: Even with optimistic UI, show subtle indicators (reduced opacity, spinner) so users know the action is in flight.
''',
    ),
    (
        "typescript/production",
        r'''Show how to compose multiple React hooks into a feature module hook. Demonstrate encapsulating data fetching, state management, event handlers, and side effects into a single cohesive hook for a feature like a search/filter panel.''',
        r'''# Composing Hooks into Feature Modules

Feature module hooks encapsulate all the logic for a feature — fetching, state, derived data, event handlers, side effects — into a single hook that exposes a clean API to the component. The component becomes a pure rendering shell.

## Production Pattern: Search and Filter Panel

```typescript
import {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
  useDeferredValue,
  useTransition,
} from "react";

// Types
interface Product {
  id: string;
  name: string;
  category: string;
  price: number;
  rating: number;
  inStock: boolean;
}

interface Filters {
  search: string;
  category: string | null;
  priceRange: [number, number];
  inStockOnly: boolean;
  sortBy: "name" | "price-asc" | "price-desc" | "rating";
}

interface Pagination {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
}

// Sub-hooks — each handles one concern

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

function useUrlState<T extends Record<string, string | number | boolean | null>>(
  defaults: T
): [T, (updates: Partial<T>) => void] {
  const [state, setState] = useState<T>(() => {
    if (typeof window === "undefined") return defaults;
    const params = new URLSearchParams(window.location.search);
    const parsed = { ...defaults };
    for (const key of Object.keys(defaults)) {
      const value = params.get(key);
      if (value !== null) {
        const defaultVal = defaults[key];
        if (typeof defaultVal === "number") {
          (parsed as Record<string, unknown>)[key] = Number(value);
        } else if (typeof defaultVal === "boolean") {
          (parsed as Record<string, unknown>)[key] = value === "true";
        } else {
          (parsed as Record<string, unknown>)[key] = value;
        }
      }
    }
    return parsed;
  });

  const updateState = useCallback((updates: Partial<T>) => {
    setState((prev) => {
      const next = { ...prev, ...updates };
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(next)) {
        if (value !== null && value !== undefined && value !== "") {
          params.set(key, String(value));
        }
      }
      window.history.replaceState(null, "", `?${params.toString()}`);
      return next;
    });
  }, []);

  return [state, updateState];
}

// The composed feature hook
interface UseProductSearchReturn {
  // Data
  products: Product[];
  categories: string[];
  pagination: Pagination;
  isLoading: boolean;
  isFiltering: boolean;
  error: string | null;

  // Filter state
  filters: Filters;

  // Actions
  setSearch: (search: string) => void;
  setCategory: (category: string | null) => void;
  setPriceRange: (range: [number, number]) => void;
  toggleInStockOnly: () => void;
  setSortBy: (sortBy: Filters["sortBy"]) => void;
  setPage: (page: number) => void;
  resetFilters: () => void;
  refresh: () => void;
}

const DEFAULT_FILTERS: Filters = {
  search: "",
  category: null,
  priceRange: [0, 10000],
  inStockOnly: false,
  sortBy: "name",
};

function useProductSearch(perPage: number = 20): UseProductSearchReturn {
  // URL-synced state for shareable filter URLs
  const [urlState, setUrlState] = useUrlState({
    search: "",
    category: "",
    minPrice: 0,
    maxPrice: 10000,
    inStockOnly: false,
    sortBy: "name" as string,
    page: 1,
  });

  // Derive filters from URL state
  const filters: Filters = useMemo(
    () => ({
      search: urlState.search,
      category: urlState.category || null,
      priceRange: [urlState.minPrice, urlState.maxPrice] as [number, number],
      inStockOnly: urlState.inStockOnly,
      sortBy: urlState.sortBy as Filters["sortBy"],
    }),
    [urlState]
  );

  // Debounce search to avoid hammering API on every keystroke
  const debouncedSearch = useDebounce(filters.search, 300);
  const [isPending, startTransition] = useTransition();

  // Fetch state
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    page: 1,
    perPage,
    total: 0,
    totalPages: 0,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Abort controller for cleanup
  const abortRef = useRef<AbortController | null>(null);

  // Build query string from filters
  const buildQueryString = useCallback(
    (search: string) => {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (filters.category) params.set("category", filters.category);
      params.set("minPrice", String(filters.priceRange[0]));
      params.set("maxPrice", String(filters.priceRange[1]));
      if (filters.inStockOnly) params.set("inStock", "true");
      params.set("sortBy", filters.sortBy);
      params.set("page", String(urlState.page));
      params.set("perPage", String(perPage));
      return params.toString();
    },
    [filters, urlState.page, perPage]
  );

  // Fetch products when debounced filters change
  const fetchProducts = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    try {
      const qs = buildQueryString(debouncedSearch);
      const response = await fetch(`/api/products?${qs}`, {
        signal: controller.signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      setProducts(data.products);
      setPagination({
        page: data.page,
        perPage: data.perPage,
        total: data.total,
        totalPages: Math.ceil(data.total / data.perPage),
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Failed to load products");
    } finally {
      setIsLoading(false);
    }
  }, [buildQueryString, debouncedSearch]);

  useEffect(() => {
    fetchProducts();
    return () => abortRef.current?.abort();
  }, [fetchProducts]);

  // Fetch categories once on mount
  useEffect(() => {
    fetch("/api/categories")
      .then((res) => res.json())
      .then((data) => setCategories(data.categories))
      .catch(() => {}); // Non-critical
  }, []);

  // Actions
  const setSearch = useCallback(
    (search: string) => {
      startTransition(() => {
        setUrlState({ search, page: 1 });
      });
    },
    [setUrlState]
  );

  const setCategory = useCallback(
    (category: string | null) => setUrlState({ category: category ?? "", page: 1 }),
    [setUrlState]
  );

  const setPriceRange = useCallback(
    (range: [number, number]) =>
      setUrlState({ minPrice: range[0], maxPrice: range[1], page: 1 }),
    [setUrlState]
  );

  const toggleInStockOnly = useCallback(
    () => setUrlState({ inStockOnly: !urlState.inStockOnly, page: 1 }),
    [setUrlState, urlState.inStockOnly]
  );

  const setSortBy = useCallback(
    (sortBy: Filters["sortBy"]) => setUrlState({ sortBy, page: 1 }),
    [setUrlState]
  );

  const setPage = useCallback(
    (page: number) => setUrlState({ page }),
    [setUrlState]
  );

  const resetFilters = useCallback(
    () =>
      setUrlState({
        search: "",
        category: "",
        minPrice: 0,
        maxPrice: 10000,
        inStockOnly: false,
        sortBy: "name",
        page: 1,
      }),
    [setUrlState]
  );

  return {
    products,
    categories,
    pagination,
    isLoading,
    isFiltering: isPending,
    error,
    filters,
    setSearch,
    setCategory,
    setPriceRange,
    toggleInStockOnly,
    setSortBy,
    setPage,
    resetFilters,
    refresh: fetchProducts,
  };
}
```

## Component Becomes a Thin Shell

```typescript
function ProductSearchPage() {
  const search = useProductSearch(20);

  return (
    <div className="product-search">
      <SearchBar value={search.filters.search} onChange={search.setSearch} />
      <FilterSidebar
        categories={search.categories}
        filters={search.filters}
        onCategoryChange={search.setCategory}
        onPriceRangeChange={search.setPriceRange}
        onInStockToggle={search.toggleInStockOnly}
        onReset={search.resetFilters}
      />
      <SortDropdown value={search.filters.sortBy} onChange={search.setSortBy} />

      {search.error && <ErrorBanner message={search.error} onRetry={search.refresh} />}
      {search.isLoading ? (
        <ProductGridSkeleton count={20} />
      ) : (
        <ProductGrid products={search.products} dimmed={search.isFiltering} />
      )}

      <Pagination
        page={search.pagination.page}
        totalPages={search.pagination.totalPages}
        onPageChange={search.setPage}
      />
    </div>
  );
}
```

## Common Pitfalls

1. **Returning unstable references**: If your hook returns `{ products, filters }` as a new object each render, memoized children still re-render. Return individual values or memoize the return object.
2. **Circular dependencies between sub-hooks**: If hook A depends on hook B's output and vice versa, extract shared state into a single `useReducer`.
3. **Testing**: Feature hooks are testable with `renderHook` from `@testing-library/react`. Mock `fetch` and assert state transitions — no component rendering needed.
4. **Over-composition**: Not every feature needs a mega-hook. If a component uses 2 pieces of state and 1 effect, inline them. Compose hooks when logic is reused or has 5+ interconnected pieces.
''',
    ),
]
