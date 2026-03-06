"""
Batch p1077: TypeScript/React production pairs - React State Management
Topics: Zustand, Jotai, React Query, optimistic updates, XState
"""

PAIRS = [
    ("react/state_zustand", r'''Build a production Zustand store in TypeScript for an e-commerce cart with persistence, computed values, middleware (logging, devtools), and actions for add/remove/update quantities.''', r'''// store/cart-store.ts
import { create } from "zustand";
import { devtools, persist, subscribeWithSelector } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";

// Types
interface CartItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
  image: string;
  variant?: string;
  maxQuantity: number;
}

interface CartState {
  items: CartItem[];
  couponCode: string | null;
  discountPercent: number;
  isOpen: boolean;
}

interface CartActions {
  addItem: (item: Omit<CartItem, "quantity"> & { quantity?: number }) => void;
  removeItem: (id: string) => void;
  updateQuantity: (id: string, quantity: number) => void;
  incrementQuantity: (id: string) => void;
  decrementQuantity: (id: string) => void;
  clearCart: () => void;
  applyCoupon: (code: string) => Promise<boolean>;
  removeCoupon: () => void;
  toggleCart: () => void;
  setCartOpen: (open: boolean) => void;
}

interface CartComputed {
  totalItems: () => number;
  subtotal: () => number;
  discount: () => number;
  total: () => number;
  isEmpty: () => boolean;
  getItem: (id: string) => CartItem | undefined;
}

type CartStore = CartState & CartActions & CartComputed;

// Coupon validation API
async function validateCoupon(code: string): Promise<{ valid: boolean; discount: number }> {
  const res = await fetch("/api/coupons/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  return res.json();
}

// Logger middleware
const logger = (config: any) => (set: any, get: any, api: any) =>
  config(
    (...args: any[]) => {
      const prevState = get();
      set(...args);
      const nextState = get();
      if (process.env.NODE_ENV === "development") {
        console.groupCollapsed(
          `%c[Cart] State update`,
          "color: #7c3aed; font-weight: bold;"
        );
        console.log("Previous:", prevState);
        console.log("Next:", nextState);
        console.groupEnd();
      }
    },
    get,
    api
  );

export const useCartStore = create<CartStore>()(
  devtools(
    subscribeWithSelector(
      persist(
        immer((set, get) => ({
          // State
          items: [],
          couponCode: null,
          discountPercent: 0,
          isOpen: false,

          // Actions
          addItem: (item) =>
            set((state) => {
              const existing = state.items.find((i) => i.id === item.id);
              if (existing) {
                const newQty = existing.quantity + (item.quantity || 1);
                existing.quantity = Math.min(newQty, existing.maxQuantity);
              } else {
                state.items.push({
                  ...item,
                  quantity: item.quantity || 1,
                } as CartItem);
              }
            }),

          removeItem: (id) =>
            set((state) => {
              state.items = state.items.filter((i) => i.id !== id);
            }),

          updateQuantity: (id, quantity) =>
            set((state) => {
              const item = state.items.find((i) => i.id === id);
              if (item) {
                if (quantity <= 0) {
                  state.items = state.items.filter((i) => i.id !== id);
                } else {
                  item.quantity = Math.min(quantity, item.maxQuantity);
                }
              }
            }),

          incrementQuantity: (id) => {
            const item = get().items.find((i) => i.id === id);
            if (item && item.quantity < item.maxQuantity) {
              get().updateQuantity(id, item.quantity + 1);
            }
          },

          decrementQuantity: (id) => {
            const item = get().items.find((i) => i.id === id);
            if (item) {
              get().updateQuantity(id, item.quantity - 1);
            }
          },

          clearCart: () =>
            set((state) => {
              state.items = [];
              state.couponCode = null;
              state.discountPercent = 0;
            }),

          applyCoupon: async (code) => {
            try {
              const result = await validateCoupon(code);
              if (result.valid) {
                set((state) => {
                  state.couponCode = code;
                  state.discountPercent = result.discount;
                });
                return true;
              }
              return false;
            } catch {
              return false;
            }
          },

          removeCoupon: () =>
            set((state) => {
              state.couponCode = null;
              state.discountPercent = 0;
            }),

          toggleCart: () =>
            set((state) => {
              state.isOpen = !state.isOpen;
            }),

          setCartOpen: (open) =>
            set((state) => {
              state.isOpen = open;
            }),

          // Computed values (as functions for lazy evaluation)
          totalItems: () => get().items.reduce((sum, item) => sum + item.quantity, 0),

          subtotal: () =>
            get().items.reduce((sum, item) => sum + item.price * item.quantity, 0),

          discount: () => {
            const subtotal = get().subtotal();
            return subtotal * (get().discountPercent / 100);
          },

          total: () => {
            const subtotal = get().subtotal();
            const discount = get().discount();
            return Math.max(0, subtotal - discount);
          },

          isEmpty: () => get().items.length === 0,

          getItem: (id) => get().items.find((i) => i.id === id),
        })),
        {
          name: "cart-storage",
          partialize: (state) => ({
            items: state.items,
            couponCode: state.couponCode,
            discountPercent: state.discountPercent,
          }),
        }
      )
    ),
    { name: "CartStore" }
  )
);

// Selector hooks for performance
export const useCartItems = () => useCartStore((s) => s.items);
export const useCartTotal = () => useCartStore((s) => s.total());
export const useCartCount = () => useCartStore((s) => s.totalItems());
export const useCartOpen = () => useCartStore((s) => s.isOpen);

// Subscribe to changes outside React
useCartStore.subscribe(
  (state) => state.items.length,
  (count) => {
    // Update badge in document title
    document.title = count > 0 ? `(${count}) Shop` : "Shop";
  }
);
'''),

    ("react/state_react_query", r'''<think>
React Query (TanStack Query) is the standard for server state management. I could use plain useEffect + useState for data fetching, but wait - that approach has no caching, no deduplication, no background refetching, and requires manual loading/error state management. React Query handles all of that out of the box, which is why it has become the standard.

I need to show practical patterns: queries with caching, mutations with optimistic updates, query invalidation, infinite queries for pagination, and prefetching. I initially thought about showing basic useQuery usage, but actually the advanced patterns are more valuable since basic usage is well-covered in the docs.

Key patterns to demonstrate:
1. Custom query hooks with proper typing - hmm, I considered returning the full query result, but wrapping it in a custom hook with a cleaner API is better because it encapsulates the query key and fetcher
2. Mutations with optimistic updates and rollback - this is tricky because you need to snapshot the cache, update it optimistically, and restore on error
3. Query invalidation strategies - granular invalidation vs broad invalidation, and when to use each
4. Infinite scroll with useInfiniteQuery - the getNextPageParam callback is where most people get confused
5. Prefetching for navigation - start loading data before the user clicks
</think>

Build production React Query patterns in TypeScript including typed custom hooks, optimistic mutations with rollback, query invalidation strategies, infinite scroll, and prefetching.''', r'''<think>
I will create a complete set of React Query patterns centered around a todo/task management API. I considered using a generic CRUD example, but actually a task management API is better because it naturally requires optimistic updates (toggling task status should feel instant) and list invalidation (adding a task should update the list immediately).

For the optimistic mutation pattern, I need to use onMutate to snapshot and update the cache, onError to rollback, and onSettled to refetch the authoritative data. I initially forgot about onSettled, but wait - without it, if the mutation succeeds but the server returns slightly different data (e.g., a server-generated timestamp), the cache would be stale. The refetch in onSettled ensures consistency.

For query keys, I will use a factory pattern like `taskKeys.list(filters)` and `taskKeys.detail(id)`. This avoids key string duplication and makes invalidation precise - you can invalidate all task lists without touching individual task detail caches.
</think>

// lib/query-client.ts
import { QueryClient, QueryClientConfig } from "@tanstack/react-query";

const queryClientConfig: QueryClientConfig = {
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
};

export const queryClient = new QueryClient(queryClientConfig);

// Types
interface Task {
  id: string;
  title: string;
  description: string;
  status: "todo" | "in_progress" | "done";
  priority: "low" | "medium" | "high";
  assigneeId: string | null;
  createdAt: string;
  updatedAt: string;
}

interface TasksResponse {
  tasks: Task[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

interface CreateTaskDto {
  title: string;
  description: string;
  priority: Task["priority"];
  assigneeId?: string;
}

interface UpdateTaskDto {
  title?: string;
  description?: string;
  status?: Task["status"];
  priority?: Task["priority"];
  assigneeId?: string | null;
}

// API client
const api = {
  getTasks: async (params: {
    page?: number;
    status?: string;
    search?: string;
  }): Promise<TasksResponse> => {
    const qs = new URLSearchParams();
    if (params.page) qs.set("page", String(params.page));
    if (params.status) qs.set("status", params.status);
    if (params.search) qs.set("search", params.search);
    const res = await fetch(`/api/tasks?${qs}`);
    if (!res.ok) throw new Error("Failed to fetch tasks");
    return res.json();
  },

  getTask: async (id: string): Promise<Task> => {
    const res = await fetch(`/api/tasks/${id}`);
    if (!res.ok) throw new Error("Task not found");
    return res.json();
  },

  createTask: async (data: CreateTaskDto): Promise<Task> => {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create task");
    return res.json();
  },

  updateTask: async (id: string, data: UpdateTaskDto): Promise<Task> => {
    const res = await fetch(`/api/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update task");
    return res.json();
  },

  deleteTask: async (id: string): Promise<void> => {
    const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete task");
  },
};

// Query key factory for consistency
export const taskKeys = {
  all: ["tasks"] as const,
  lists: () => [...taskKeys.all, "list"] as const,
  list: (filters: Record<string, string | undefined>) =>
    [...taskKeys.lists(), filters] as const,
  details: () => [...taskKeys.all, "detail"] as const,
  detail: (id: string) => [...taskKeys.details(), id] as const,
};

// hooks/useTasks.ts
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";

export function useTasks(filters: { status?: string; search?: string } = {}) {
  return useQuery({
    queryKey: taskKeys.list(filters),
    queryFn: () => api.getTasks({ ...filters, page: 1 }),
    placeholderData: (previousData) => previousData, // Keep previous data while refetching
  });
}

export function useTask(id: string) {
  return useQuery({
    queryKey: taskKeys.detail(id),
    queryFn: () => api.getTask(id),
    enabled: !!id, // Only fetch when id is provided
  });
}

// Infinite scroll query
export function useInfiniteTasks(filters: { status?: string; search?: string } = {}) {
  return useInfiniteQuery({
    queryKey: [...taskKeys.list(filters), "infinite"],
    queryFn: ({ pageParam }) => api.getTasks({ ...filters, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.page + 1 : undefined,
    select: (data) => ({
      pages: data.pages,
      pageParams: data.pageParams,
      tasks: data.pages.flatMap((page) => page.tasks),
      total: data.pages[0]?.total ?? 0,
    }),
  });
}

// Create mutation
export function useCreateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createTask,
    onSuccess: (newTask) => {
      // Invalidate all task lists to refetch
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
      // Pre-populate the detail cache
      queryClient.setQueryData(taskKeys.detail(newTask.id), newTask);
    },
  });
}

// Optimistic update mutation
export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTaskDto }) =>
      api.updateTask(id, data),

    onMutate: async ({ id, data }) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: taskKeys.detail(id) });
      await queryClient.cancelQueries({ queryKey: taskKeys.lists() });

      // Snapshot current state for rollback
      const previousTask = queryClient.getQueryData<Task>(taskKeys.detail(id));
      const previousLists = queryClient.getQueriesData({ queryKey: taskKeys.lists() });

      // Optimistically update the detail cache
      if (previousTask) {
        queryClient.setQueryData<Task>(taskKeys.detail(id), {
          ...previousTask,
          ...data,
          updatedAt: new Date().toISOString(),
        });
      }

      // Optimistically update list caches
      queryClient.setQueriesData<TasksResponse>(
        { queryKey: taskKeys.lists() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            tasks: old.tasks.map((task) =>
              task.id === id ? { ...task, ...data, updatedAt: new Date().toISOString() } : task
            ),
          };
        }
      );

      return { previousTask, previousLists };
    },

    onError: (_err, { id }, context) => {
      // Rollback on error
      if (context?.previousTask) {
        queryClient.setQueryData(taskKeys.detail(id), context.previousTask);
      }
      if (context?.previousLists) {
        for (const [key, data] of context.previousLists) {
          queryClient.setQueryData(key, data);
        }
      }
    },

    onSettled: (_data, _err, { id }) => {
      // Always refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
    },
  });
}

// Delete with optimistic removal
export function useDeleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.deleteTask,

    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: taskKeys.lists() });
      const previousLists = queryClient.getQueriesData({ queryKey: taskKeys.lists() });

      queryClient.setQueriesData<TasksResponse>(
        { queryKey: taskKeys.lists() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            tasks: old.tasks.filter((t) => t.id !== id),
            total: old.total - 1,
          };
        }
      );

      return { previousLists };
    },

    onError: (_err, _id, context) => {
      if (context?.previousLists) {
        for (const [key, data] of context.previousLists) {
          queryClient.setQueryData(key, data);
        }
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
    },
  });
}

// Prefetching for navigation
export function usePrefetchTask(id: string) {
  const queryClient = useQueryClient();

  return () => {
    queryClient.prefetchQuery({
      queryKey: taskKeys.detail(id),
      queryFn: () => api.getTask(id),
      staleTime: 60 * 1000,
    });
  };
}
'''),

    ("react/state_jotai", r'''Build a Jotai-based state management solution in TypeScript for a multi-step form wizard with derived atoms, async atoms for API validation, persistence, and undo/redo support.''', r'''// store/form-atoms.ts
import { atom, useAtom, useAtomValue, useSetAtom } from "jotai";
import { atomWithStorage, RESET } from "jotai/utils";
import { focusAtom } from "jotai-optics";

// Step definitions
type FormStep = "personal" | "address" | "payment" | "review";

const STEP_ORDER: FormStep[] = ["personal", "address", "payment", "review"];

// Form data types
interface PersonalInfo {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
}

interface AddressInfo {
  street: string;
  city: string;
  state: string;
  zip: string;
  country: string;
}

interface PaymentInfo {
  cardNumber: string;
  expiry: string;
  cvv: string;
  nameOnCard: string;
}

interface FormData {
  personal: PersonalInfo;
  address: AddressInfo;
  payment: PaymentInfo;
}

interface FormState {
  data: FormData;
  currentStep: FormStep;
  completedSteps: FormStep[];
  errors: Partial<Record<string, string>>;
}

// Initial state
const initialFormData: FormData = {
  personal: { firstName: "", lastName: "", email: "", phone: "" },
  address: { street: "", city: "", state: "", zip: "", country: "" },
  payment: { cardNumber: "", expiry: "", cvv: "", nameOnCard: "" },
};

const initialFormState: FormState = {
  data: initialFormData,
  currentStep: "personal",
  completedSteps: [],
  errors: {},
};

// Base atom with persistence
const formStateAtom = atomWithStorage<FormState>("checkout-form", initialFormState);

// Undo/redo history
interface HistoryEntry {
  state: FormState;
  timestamp: number;
}

const historyAtom = atom<HistoryEntry[]>([]);
const historyIndexAtom = atom<number>(-1);

// Derived atoms for each section (using optics for focused updates)
const currentStepAtom = atom(
  (get) => get(formStateAtom).currentStep,
  (get, set, step: FormStep) => {
    const state = get(formStateAtom);
    set(formStateAtom, { ...state, currentStep: step });
  }
);

const personalAtom = atom(
  (get) => get(formStateAtom).data.personal,
  (get, set, update: Partial<PersonalInfo>) => {
    const state = get(formStateAtom);
    const newState = {
      ...state,
      data: {
        ...state.data,
        personal: { ...state.data.personal, ...update },
      },
    };
    pushHistory(get, set, state);
    set(formStateAtom, newState);
  }
);

const addressAtom = atom(
  (get) => get(formStateAtom).data.address,
  (get, set, update: Partial<AddressInfo>) => {
    const state = get(formStateAtom);
    const newState = {
      ...state,
      data: {
        ...state.data,
        address: { ...state.data.address, ...update },
      },
    };
    pushHistory(get, set, state);
    set(formStateAtom, newState);
  }
);

const paymentAtom = atom(
  (get) => get(formStateAtom).data.payment,
  (get, set, update: Partial<PaymentInfo>) => {
    const state = get(formStateAtom);
    const newState = {
      ...state,
      data: {
        ...state.data,
        payment: { ...state.data.payment, ...update },
      },
    };
    pushHistory(get, set, state);
    set(formStateAtom, newState);
  }
);

const errorsAtom = atom(
  (get) => get(formStateAtom).errors,
  (get, set, errors: Partial<Record<string, string>>) => {
    const state = get(formStateAtom);
    set(formStateAtom, { ...state, errors });
  }
);

// Computed atoms
const stepIndexAtom = atom((get) => {
  const step = get(currentStepAtom);
  return STEP_ORDER.indexOf(step);
});

const progressAtom = atom((get) => {
  const index = get(stepIndexAtom);
  return ((index + 1) / STEP_ORDER.length) * 100;
});

const isFirstStepAtom = atom((get) => get(stepIndexAtom) === 0);
const isLastStepAtom = atom((get) => get(stepIndexAtom) === STEP_ORDER.length - 1);

const canProceedAtom = atom((get) => {
  const errors = get(errorsAtom);
  return Object.keys(errors).length === 0;
});

const formSummaryAtom = atom((get) => {
  const data = get(formStateAtom).data;
  return {
    fullName: `${data.personal.firstName} ${data.personal.lastName}`.trim(),
    email: data.personal.email,
    fullAddress: [data.address.street, data.address.city, data.address.state, data.address.zip]
      .filter(Boolean)
      .join(", "),
    cardLast4: data.payment.cardNumber.slice(-4),
  };
});

// Async validation atom
const emailValidationAtom = atom(async (get) => {
  const email = get(personalAtom).email;
  if (!email || !email.includes("@")) return null;

  try {
    const res = await fetch(`/api/validate-email?email=${encodeURIComponent(email)}`);
    const data = await res.json();
    return data.valid ? null : "Email is already registered";
  } catch {
    return null; // Don't block on validation errors
  }
});

// Address autocomplete atom
const addressSuggestionsAtom = atom(async (get) => {
  const address = get(addressAtom);
  const query = address.street;
  if (!query || query.length < 3) return [];

  try {
    const res = await fetch(`/api/address-suggest?q=${encodeURIComponent(query)}`);
    return res.json() as Promise<Array<{ formatted: string; components: AddressInfo }>>;
  } catch {
    return [];
  }
});

// History management
function pushHistory(get: any, set: any, state: FormState) {
  const history = get(historyAtom);
  const index = get(historyIndexAtom);
  const newHistory = history.slice(0, index + 1);
  newHistory.push({ state, timestamp: Date.now() });
  if (newHistory.length > 50) newHistory.shift(); // Limit history size
  set(historyAtom, newHistory);
  set(historyIndexAtom, newHistory.length - 1);
}

const undoAtom = atom(null, (get, set) => {
  const index = get(historyIndexAtom);
  const history = get(historyAtom);
  if (index >= 0) {
    set(formStateAtom, history[index].state);
    set(historyIndexAtom, index - 1);
  }
});

const redoAtom = atom(null, (get, set) => {
  const index = get(historyIndexAtom);
  const history = get(historyAtom);
  if (index < history.length - 1) {
    const newIndex = index + 1;
    set(formStateAtom, history[newIndex].state);
    set(historyIndexAtom, newIndex);
  }
});

const canUndoAtom = atom((get) => get(historyIndexAtom) >= 0);
const canRedoAtom = atom((get) => {
  const index = get(historyIndexAtom);
  const history = get(historyAtom);
  return index < history.length - 1;
});

// Action atoms
const nextStepAtom = atom(null, (get, set) => {
  const index = get(stepIndexAtom);
  if (index < STEP_ORDER.length - 1) {
    const current = get(currentStepAtom);
    const completed = get(formStateAtom).completedSteps;
    if (!completed.includes(current)) {
      const state = get(formStateAtom);
      set(formStateAtom, {
        ...state,
        completedSteps: [...completed, current],
      });
    }
    set(currentStepAtom, STEP_ORDER[index + 1]);
  }
});

const prevStepAtom = atom(null, (get, set) => {
  const index = get(stepIndexAtom);
  if (index > 0) {
    set(currentStepAtom, STEP_ORDER[index - 1]);
  }
});

const resetFormAtom = atom(null, (_get, set) => {
  set(formStateAtom, initialFormState);
  set(historyAtom, []);
  set(historyIndexAtom, -1);
});

// Validation
function validateStep(step: FormStep, data: FormData): Record<string, string> {
  const errors: Record<string, string> = {};

  if (step === "personal") {
    if (!data.personal.firstName) errors.firstName = "First name is required";
    if (!data.personal.lastName) errors.lastName = "Last name is required";
    if (!data.personal.email.includes("@")) errors.email = "Valid email required";
  } else if (step === "address") {
    if (!data.address.street) errors.street = "Street is required";
    if (!data.address.city) errors.city = "City is required";
    if (!data.address.zip) errors.zip = "ZIP code is required";
  } else if (step === "payment") {
    if (data.payment.cardNumber.replace(/\s/g, "").length !== 16) {
      errors.cardNumber = "Valid card number required";
    }
    if (!data.payment.expiry.match(/^\d{2}\/\d{2}$/)) {
      errors.expiry = "Format: MM/YY";
    }
    if (data.payment.cvv.length < 3) errors.cvv = "Valid CVV required";
  }

  return errors;
}

const validateCurrentStepAtom = atom(null, (get, set) => {
  const step = get(currentStepAtom);
  const data = get(formStateAtom).data;
  const errors = validateStep(step, data);
  set(errorsAtom, errors);
  return Object.keys(errors).length === 0;
});

// Export all atoms
export {
  formStateAtom, currentStepAtom, personalAtom, addressAtom, paymentAtom,
  errorsAtom, stepIndexAtom, progressAtom, isFirstStepAtom, isLastStepAtom,
  canProceedAtom, formSummaryAtom, emailValidationAtom, addressSuggestionsAtom,
  undoAtom, redoAtom, canUndoAtom, canRedoAtom,
  nextStepAtom, prevStepAtom, resetFormAtom, validateCurrentStepAtom,
};
'''),

    ("react/state_optimistic", r'''Build optimistic update patterns in React with TypeScript for a social media feed including like/unlike, comment adding, and post deletion with proper rollback on failure and conflict resolution.''', r'''// hooks/useOptimisticMutation.ts
import { useState, useCallback, useRef } from "react";

interface OptimisticState<T> {
  data: T;
  pending: Map<string, PendingOperation>;
  errors: Map<string, Error>;
}

interface PendingOperation {
  id: string;
  type: string;
  timestamp: number;
  rollback: () => void;
}

// Generic optimistic mutation hook
function useOptimisticMutation<T, TVariables>(options: {
  mutationFn: (variables: TVariables) => Promise<T>;
  onOptimistic: (variables: TVariables) => { apply: () => void; rollback: () => void };
  onSuccess?: (data: T, variables: TVariables) => void;
  onError?: (error: Error, variables: TVariables) => void;
  onSettled?: () => void;
}) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pendingOps = useRef(new Map<string, PendingOperation>());

  const mutate = useCallback(
    async (variables: TVariables, operationId?: string) => {
      const opId = operationId || crypto.randomUUID();
      setIsPending(true);
      setError(null);

      // Apply optimistic update immediately
      const { apply, rollback } = options.onOptimistic(variables);
      apply();

      pendingOps.current.set(opId, {
        id: opId,
        type: "mutation",
        timestamp: Date.now(),
        rollback,
      });

      try {
        const result = await options.mutationFn(variables);
        pendingOps.current.delete(opId);
        options.onSuccess?.(result, variables);
        return result;
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));

        // Rollback optimistic update
        rollback();
        pendingOps.current.delete(opId);

        setError(error);
        options.onError?.(error, variables);
        throw error;
      } finally {
        setIsPending(pendingOps.current.size > 0);
        options.onSettled?.();
      }
    },
    [options]
  );

  return { mutate, isPending, error };
}

// Social feed types
interface Post {
  id: string;
  author: { id: string; name: string; avatar: string };
  content: string;
  likes: number;
  isLiked: boolean;
  comments: Comment[];
  createdAt: string;
}

interface Comment {
  id: string;
  author: { id: string; name: string; avatar: string };
  content: string;
  createdAt: string;
}

// Feed state with optimistic capabilities
function useFeedState(initialPosts: Post[]) {
  const [posts, setPosts] = useState<Post[]>(initialPosts);
  const snapshotRef = useRef<Map<string, Post>>(new Map());

  // Snapshot a post before mutation
  const snapshot = (postId: string) => {
    const post = posts.find((p) => p.id === postId);
    if (post) {
      snapshotRef.current.set(postId, structuredClone(post));
    }
  };

  // Restore a post from snapshot
  const restore = (postId: string) => {
    const saved = snapshotRef.current.get(postId);
    if (saved) {
      setPosts((prev) =>
        prev.map((p) => (p.id === postId ? saved : p))
      );
      snapshotRef.current.delete(postId);
    }
  };

  return { posts, setPosts, snapshot, restore };
}

// Hook: Optimistic like/unlike
function useLikePost(
  setPosts: React.Dispatch<React.SetStateAction<Post[]>>,
  snapshot: (id: string) => void,
  restore: (id: string) => void
) {
  return useOptimisticMutation<void, { postId: string; isLiked: boolean }>({
    mutationFn: async ({ postId, isLiked }) => {
      const res = await fetch(`/api/posts/${postId}/like`, {
        method: isLiked ? "DELETE" : "POST",
      });
      if (!res.ok) throw new Error("Like failed");
    },

    onOptimistic: ({ postId, isLiked }) => ({
      apply: () => {
        snapshot(postId);
        setPosts((prev) =>
          prev.map((post) =>
            post.id === postId
              ? {
                  ...post,
                  isLiked: !isLiked,
                  likes: isLiked ? post.likes - 1 : post.likes + 1,
                }
              : post
          )
        );
      },
      rollback: () => restore(postId),
    }),

    onError: (error) => {
      console.error("Like failed:", error.message);
    },
  });
}

// Hook: Optimistic comment
function useAddComment(
  setPosts: React.Dispatch<React.SetStateAction<Post[]>>,
  snapshot: (id: string) => void,
  restore: (id: string) => void,
  currentUser: { id: string; name: string; avatar: string }
) {
  return useOptimisticMutation<
    Comment,
    { postId: string; content: string }
  >({
    mutationFn: async ({ postId, content }) => {
      const res = await fetch(`/api/posts/${postId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error("Comment failed");
      return res.json();
    },

    onOptimistic: ({ postId, content }) => {
      const tempId = `temp-${Date.now()}`;

      return {
        apply: () => {
          snapshot(postId);
          setPosts((prev) =>
            prev.map((post) =>
              post.id === postId
                ? {
                    ...post,
                    comments: [
                      ...post.comments,
                      {
                        id: tempId,
                        author: currentUser,
                        content,
                        createdAt: new Date().toISOString(),
                      },
                    ],
                  }
                : post
            )
          );
        },
        rollback: () => restore(postId),
      };
    },

    onSuccess: (serverComment, { postId }) => {
      // Replace temp comment with server response
      setPosts((prev) =>
        prev.map((post) =>
          post.id === postId
            ? {
                ...post,
                comments: post.comments.map((c) =>
                  c.id.startsWith("temp-") ? serverComment : c
                ),
              }
            : post
        )
      );
    },
  });
}

// Hook: Optimistic delete with confirmation
function useDeletePost(
  setPosts: React.Dispatch<React.SetStateAction<Post[]>>,
  snapshot: (id: string) => void,
  restore: (id: string) => void
) {
  const [deletedPosts, setDeletedPosts] = useState<Map<string, Post>>(new Map());
  const undoTimeouts = useRef<Map<string, NodeJS.Timeout>>(new Map());

  const softDelete = useCallback(
    (postId: string) => {
      const post = undefined; // would find from posts
      snapshot(postId);

      // Immediately hide from UI
      setPosts((prev) => prev.filter((p) => p.id !== postId));

      // Set undo timeout - actually delete after 5 seconds
      const timeout = setTimeout(async () => {
        try {
          const res = await fetch(`/api/posts/${postId}`, { method: "DELETE" });
          if (!res.ok) throw new Error("Delete failed");
          undoTimeouts.current.delete(postId);
          setDeletedPosts((prev) => {
            const next = new Map(prev);
            next.delete(postId);
            return next;
          });
        } catch (error) {
          // Restore on failure
          restore(postId);
        }
      }, 5000);

      undoTimeouts.current.set(postId, timeout);
    },
    [setPosts, snapshot, restore]
  );

  const undoDelete = useCallback(
    (postId: string) => {
      const timeout = undoTimeouts.current.get(postId);
      if (timeout) {
        clearTimeout(timeout);
        undoTimeouts.current.delete(postId);
      }
      restore(postId);
    },
    [restore]
  );

  return { softDelete, undoDelete };
}

// Conflict resolution for concurrent edits
interface ConflictResolver<T> {
  detect: (local: T, server: T) => boolean;
  resolve: (local: T, server: T) => T;
}

const postConflictResolver: ConflictResolver<Post> = {
  detect: (local, server) => {
    return local.likes !== server.likes || local.comments.length !== server.comments.length;
  },
  resolve: (local, server) => {
    // Server wins for likes, merge comments
    const localCommentIds = new Set(local.comments.map((c) => c.id));
    const mergedComments = [
      ...server.comments,
      ...local.comments.filter(
        (c) => c.id.startsWith("temp-") && !localCommentIds.has(c.id)
      ),
    ];
    return {
      ...server,
      comments: mergedComments,
      isLiked: local.isLiked, // Keep local like state if pending
    };
  },
};

export {
  useOptimisticMutation,
  useFeedState,
  useLikePost,
  useAddComment,
  useDeletePost,
};
'''),

    ("react/state_xstate", r'''Build an XState state machine in TypeScript for a multi-step checkout flow with parallel states for form validation and payment processing, including guards, actions, and service invocations.''', r'''// machines/checkout-machine.ts
import { createMachine, assign, fromPromise } from "xstate";

// Context types
interface CheckoutContext {
  cart: CartItem[];
  shipping: ShippingInfo | null;
  payment: PaymentInfo | null;
  order: OrderResult | null;
  errors: Record<string, string>;
  retryCount: number;
}

interface CartItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
}

interface ShippingInfo {
  name: string;
  street: string;
  city: string;
  state: string;
  zip: string;
  country: string;
  method: "standard" | "express" | "overnight";
}

interface PaymentInfo {
  cardNumber: string;
  expiry: string;
  cvv: string;
  nameOnCard: string;
}

interface OrderResult {
  orderId: string;
  total: number;
  estimatedDelivery: string;
}

// Events
type CheckoutEvent =
  | { type: "NEXT" }
  | { type: "BACK" }
  | { type: "SET_SHIPPING"; data: ShippingInfo }
  | { type: "SET_PAYMENT"; data: PaymentInfo }
  | { type: "SUBMIT_ORDER" }
  | { type: "RETRY" }
  | { type: "RESET" }
  | { type: "EDIT_SHIPPING" }
  | { type: "EDIT_PAYMENT" }
  | { type: "APPLY_COUPON"; code: string };

// Services (async operations)
const validateAddress = fromPromise(async ({ input }: { input: ShippingInfo }) => {
  const res = await fetch("/api/validate-address", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.message || "Address validation failed");
  }
  return res.json() as Promise<{ valid: boolean; normalized: ShippingInfo }>;
});

const processPayment = fromPromise(
  async ({ input }: { input: { payment: PaymentInfo; amount: number } }) => {
    const res = await fetch("/api/payment/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.message || "Payment processing failed");
    }
    return res.json() as Promise<{ transactionId: string; status: string }>;
  }
);

const createOrder = fromPromise(
  async ({
    input,
  }: {
    input: {
      cart: CartItem[];
      shipping: ShippingInfo;
      transactionId: string;
    };
  }) => {
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!res.ok) throw new Error("Order creation failed");
    return res.json() as Promise<OrderResult>;
  }
);

// Machine definition
export const checkoutMachine = createMachine({
  id: "checkout",
  initial: "cart",
  context: {
    cart: [],
    shipping: null,
    payment: null,
    order: null,
    errors: {},
    retryCount: 0,
  } satisfies CheckoutContext,
  types: {} as {
    context: CheckoutContext;
    events: CheckoutEvent;
  },

  states: {
    cart: {
      on: {
        NEXT: {
          target: "shipping",
          guard: ({ context }) => context.cart.length > 0,
        },
      },
    },

    shipping: {
      initial: "form",
      states: {
        form: {
          on: {
            SET_SHIPPING: {
              actions: assign({
                shipping: ({ event }) => event.data,
                errors: () => ({}),
              }),
            },
            NEXT: {
              target: "validating",
              guard: ({ context }) => context.shipping !== null,
            },
            BACK: { target: "#checkout.cart" },
          },
        },
        validating: {
          invoke: {
            src: validateAddress,
            input: ({ context }) => context.shipping!,
            onDone: {
              target: "#checkout.payment",
              actions: assign({
                shipping: ({ event }) => event.output.normalized,
              }),
            },
            onError: {
              target: "form",
              actions: assign({
                errors: ({ event }) => ({
                  address: (event.error as Error).message,
                }),
              }),
            },
          },
        },
      },
    },

    payment: {
      initial: "form",
      states: {
        form: {
          on: {
            SET_PAYMENT: {
              actions: assign({
                payment: ({ event }) => event.data,
                errors: () => ({}),
              }),
            },
            NEXT: {
              target: "#checkout.review",
              guard: ({ context }) => context.payment !== null,
            },
            BACK: { target: "#checkout.shipping" },
          },
        },
      },
    },

    review: {
      on: {
        SUBMIT_ORDER: { target: "processing" },
        EDIT_SHIPPING: { target: "shipping" },
        EDIT_PAYMENT: { target: "payment" },
        BACK: { target: "payment" },
      },
    },

    processing: {
      initial: "charging",
      states: {
        charging: {
          invoke: {
            src: processPayment,
            input: ({ context }) => ({
              payment: context.payment!,
              amount: context.cart.reduce(
                (sum, item) => sum + item.price * item.quantity,
                0
              ),
            }),
            onDone: {
              target: "creatingOrder",
              actions: assign({
                // Store transactionId temporarily
                errors: ({ event }) => ({
                  _transactionId: event.output.transactionId,
                }),
              }),
            },
            onError: {
              target: "#checkout.paymentError",
              actions: assign({
                errors: ({ event }) => ({
                  payment: (event.error as Error).message,
                }),
              }),
            },
          },
        },
        creatingOrder: {
          invoke: {
            src: createOrder,
            input: ({ context }) => ({
              cart: context.cart,
              shipping: context.shipping!,
              transactionId: context.errors._transactionId || "",
            }),
            onDone: {
              target: "#checkout.success",
              actions: assign({
                order: ({ event }) => event.output,
                errors: () => ({}),
              }),
            },
            onError: {
              target: "#checkout.orderError",
              actions: assign({
                errors: ({ event }) => ({
                  order: (event.error as Error).message,
                }),
              }),
            },
          },
        },
      },
    },

    paymentError: {
      on: {
        RETRY: {
          target: "processing",
          guard: ({ context }) => context.retryCount < 3,
          actions: assign({
            retryCount: ({ context }) => context.retryCount + 1,
          }),
        },
        EDIT_PAYMENT: {
          target: "payment",
          actions: assign({ retryCount: () => 0 }),
        },
        RESET: { target: "cart" },
      },
    },

    orderError: {
      on: {
        RETRY: {
          target: "processing.creatingOrder",
          guard: ({ context }) => context.retryCount < 3,
          actions: assign({
            retryCount: ({ context }) => context.retryCount + 1,
          }),
        },
        RESET: { target: "cart" },
      },
    },

    success: {
      type: "final",
      entry: assign({
        retryCount: () => 0,
      }),
    },
  },
});

// React hook for the checkout machine
// import { useMachine } from "@xstate/react";
//
// function useCheckout(initialCart: CartItem[]) {
//   const [state, send] = useMachine(checkoutMachine, {
//     context: { ...checkoutMachine.context, cart: initialCart },
//   });
//
//   return {
//     state: state.value,
//     context: state.context,
//     isProcessing: state.matches("processing"),
//     isSuccess: state.matches("success"),
//     hasError: state.matches("paymentError") || state.matches("orderError"),
//     next: () => send({ type: "NEXT" }),
//     back: () => send({ type: "BACK" }),
//     setShipping: (data: ShippingInfo) => send({ type: "SET_SHIPPING", data }),
//     setPayment: (data: PaymentInfo) => send({ type: "SET_PAYMENT", data }),
//     submit: () => send({ type: "SUBMIT_ORDER" }),
//     retry: () => send({ type: "RETRY" }),
//     reset: () => send({ type: "RESET" }),
//   };
// }

export type { CheckoutContext, CheckoutEvent, ShippingInfo, PaymentInfo, OrderResult };
'''),
]
