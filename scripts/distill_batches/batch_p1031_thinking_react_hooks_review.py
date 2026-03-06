r"""Thinking-trace pairs: React hooks code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this React hooks code and identify issues:

```jsx
import { useState, useEffect, useCallback, useRef } from 'react';

function useApi(url, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const json = await response.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [url, options]);

  return { data, loading, error, refetch: fetchData };
}

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => clearTimeout(timer);
  }, [value]);

  return debouncedValue;
}

function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    const item = window.localStorage.getItem(key);
    return item ? JSON.parse(item) : initialValue;
  });

  const setValue = (value) => {
    setStoredValue(value);
    window.localStorage.setItem(key, JSON.stringify(value));
  };

  return [storedValue, setValue];
}

function useInterval(callback, delay) {
  useEffect(() => {
    const id = setInterval(callback, delay);
    return () => clearInterval(id);
  }, [delay]);
}

function usePrevious(value) {
  const ref = useRef();
  useEffect(() => {
    ref.current = value;
  });
  return ref.current;
}

function SearchPage() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 300);
  const { data, loading, error } = useApi(
    `/api/search?q=${debouncedQuery}`,
    { method: 'GET' }
  );
  const [savedSearches, setSavedSearches] = useLocalStorage('searches', []);
  const previousQuery = usePrevious(debouncedQuery);

  useInterval(() => {
    console.log('Current query:', query);
  }, 5000);

  const handleSearch = (e) => {
    setQuery(e.target.value);
  };

  const saveSearch = () => {
    setSavedSearches([...savedSearches, query]);
  };

  return (
    <div>
      <input value={query} onChange={handleSearch} placeholder="Search..." />
      {previousQuery && <p>Previous search: {previousQuery}</p>}
      {loading && <p>Loading...</p>}
      {error && <p>Error: {error}</p>}
      {data && data.map(item => <div key={item.id}>{item.name}</div>)}
      <button onClick={saveSearch}>Save Search</button>
      <h3>Saved:</h3>
      {savedSearches.map((s, i) => <span key={i}>{s}, </span>)}
    </div>
  );
}
```''', r'''<think>
Let me review these custom hooks for correctness, dependency issues, and design problems.

1. useApi infinite loop:
- `options` is in the dependency array. In SearchPage, `{ method: 'GET' }` is passed as a new object on every render. This causes the useEffect to fire on every render, creating an infinite fetch loop.
- Even if options were memoized, the `url` changes on every render too when query changes (before debouncing stabilizes it). But with debounced query, url changes only when debounced value changes, which is correct.

2. useApi -- no cleanup/abort:
- No AbortController. If the component unmounts or url changes while a request is in-flight, the pending request completes and calls setState on an unmounted component.
- fetchData is recreated on every render but captured in the useEffect closure from the initial render (well, the effect reruns on dependency change, so this is less of an issue).

3. useDebounce missing delay dependency:
- The effect depends on `value` but not `delay`. If delay changes, the timer is not reset with the new delay.

4. useLocalStorage issues:
- The initializer reads from localStorage, but if `key` changes, the stored value is not re-read. The hook always returns the value from the initial key.
- JSON.parse with no try-catch. If localStorage contains invalid JSON (corrupted or manually edited), the hook crashes.
- setValue does not use functional updater pattern. If called with a function (like setCount(prev => prev + 1)), it stores the function itself instead of calling it.
- Does not listen for storage events from other tabs.

5. useInterval:
- callback is NOT in the dependency array. The interval always calls the initial callback from the first render. If the callback uses state values, they are stale. This is the classic Dan Abramov useInterval problem.
- Setting delay to null should stop the interval, but this implementation does not handle that.

6. usePrevious:
- The effect has no dependency array, so it runs after every render. This is intentional and correct -- it always stores the current value after render. The returned ref.current is from before the current render. This hook is correctly implemented.

7. SearchPage:
- useApi fires on every render because `{ method: 'GET' }` is a new object each time (infinite loop!).
- The query is URL-encoded with template literal but not properly escaped. If query contains & or =, the URL breaks.
- savedSearches.map uses index as key.
- saveSearch uses `[...savedSearches, query]` from closure, which could have stale state.

Let me write the review.
</think>

## Code Review: React Custom Hooks

### CRITICAL - Infinite Fetch Loop in useApi

**IL1: Options object causes infinite re-fetch (Severity: CRITICAL)**
```jsx
const { data } = useApi(`/api/search?q=${debouncedQuery}`, { method: 'GET' });
```
The `options` parameter is `{ method: 'GET' }` -- a new object reference on every render. Since `options` is in useEffect's dependency array, the effect runs on every render, triggering a new fetch, which sets state, which causes another render. Infinite loop.

Fix: Remove options from deps or use a serialized comparison:
```jsx
function useApi(url, options = {}) {
  const optionsRef = useRef(options);
  // Or: accept options as individual parameters instead of an object
```
In the consumer, memoize options:
```jsx
const options = useMemo(() => ({ method: 'GET' }), []);
```

### HIGH - useInterval Uses Stale Callback

**SC1: Interval callback captures stale closure (Severity: HIGH)**
```jsx
function useInterval(callback, delay) {
  useEffect(() => {
    const id = setInterval(callback, delay);
    return () => clearInterval(id);
  }, [delay]);
}
```
`callback` is not in the dependency array. The interval always calls the callback from the initial render. If the callback references state, it sees initial state values forever. Use a ref:
```jsx
function useInterval(callback, delay) {
  const savedCallback = useRef(callback);
  useEffect(() => { savedCallback.current = callback; });
  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => savedCallback.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}
```

### HIGH - useLocalStorage Bugs

**LS1: Key change not handled (Severity: HIGH)**
The useState initializer only runs once. If `key` changes, the hook still returns the value from the original key. Add a useEffect to re-read on key change:
```jsx
useEffect(() => {
  const item = window.localStorage.getItem(key);
  setStoredValue(item ? JSON.parse(item) : initialValue);
}, [key]);
```

**LS2: No JSON.parse error handling (Severity: MEDIUM)**
If localStorage contains invalid JSON (user tampering, corruption), `JSON.parse` throws. Wrap in try-catch:
```jsx
try {
  return item ? JSON.parse(item) : initialValue;
} catch {
  return initialValue;
}
```

**LS3: Functional updates not supported (Severity: MEDIUM)**
`setValue(prev => prev + 1)` stores the function itself rather than calling it. Support functional updaters:
```jsx
const setValue = (value) => {
  const valueToStore = value instanceof Function ? value(storedValue) : value;
  setStoredValue(valueToStore);
  window.localStorage.setItem(key, JSON.stringify(valueToStore));
};
```

### HIGH - No Request Cancellation in useApi

**RC1: No AbortController (Severity: HIGH)**
If the URL changes or the component unmounts during a fetch, the old request completes and calls setState. Add cancellation:
```jsx
useEffect(() => {
  const controller = new AbortController();
  const fetchData = async () => {
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      // ...
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    }
  };
  fetchData();
  return () => controller.abort();
}, [url]);
```

### MEDIUM - useDebounce Missing delay Dependency

**DD1: Delay changes do not reset timer (Severity: MEDIUM)**
```jsx
useEffect(() => {
  const timer = setTimeout(...);
  return () => clearTimeout(timer);
}, [value]);  // missing: delay
```
If `delay` changes, the current timer continues with the old delay value. Add `delay` to the dependency array.

### MEDIUM - URL Encoding

**UE1: Query not URL-encoded (Severity: MEDIUM)**
```jsx
`/api/search?q=${debouncedQuery}`
```
If the query contains `&`, `=`, or `#`, the URL is malformed. Use `encodeURIComponent`:
```jsx
`/api/search?q=${encodeURIComponent(debouncedQuery)}`
```'''),

    ("thinking/code-review", r'''Review this React hooks code and identify issues:

```jsx
import { useState, useEffect, useReducer, useContext, createContext, useMemo } from 'react';

const StoreContext = createContext();

function storeReducer(state, action) {
  switch (action.type) {
    case 'SET_PRODUCTS':
      return { ...state, products: action.payload };
    case 'ADD_TO_CART':
      return { ...state, cart: [...state.cart, action.payload] };
    case 'REMOVE_FROM_CART':
      return { ...state, cart: state.cart.filter(i => i.id !== action.payload) };
    case 'SET_USER':
      return { ...state, user: action.payload };
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    case 'SET_FILTERS':
      return { ...state, filters: { ...state.filters, ...action.payload } };
    case 'SET_SORT':
      return { ...state, sort: action.payload };
    case 'SET_PAGE':
      return { ...state, page: action.payload };
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case 'SET_THEME':
      return { ...state, theme: action.payload };
    default:
      return state;
  }
}

const initialState = {
  products: [],
  cart: [],
  user: null,
  loading: false,
  error: null,
  filters: {},
  sort: 'name',
  page: 1,
  sidebarOpen: false,
  theme: 'light',
};

function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(storeReducer, initialState);

  useEffect(() => {
    dispatch({ type: 'SET_LOADING', payload: true });
    fetch('/api/products')
      .then(r => r.json())
      .then(data => {
        dispatch({ type: 'SET_PRODUCTS', payload: data });
        dispatch({ type: 'SET_LOADING', payload: false });
      })
      .catch(err => {
        dispatch({ type: 'SET_ERROR', payload: err.message });
        dispatch({ type: 'SET_LOADING', payload: false });
      });
  }, []);

  return (
    <StoreContext.Provider value={{ state, dispatch }}>
      {children}
    </StoreContext.Provider>
  );
}

function useStore() {
  return useContext(StoreContext);
}

function useProducts() {
  const { state } = useStore();
  return useMemo(() => {
    let products = [...state.products];
    Object.entries(state.filters).forEach(([key, value]) => {
      if (value) {
        products = products.filter(p => p[key] === value);
      }
    });
    products.sort((a, b) => {
      if (typeof a[state.sort] === 'string') {
        return a[state.sort].localeCompare(b[state.sort]);
      }
      return a[state.sort] - b[state.sort];
    });
    const pageSize = 20;
    const start = (state.page - 1) * pageSize;
    return products.slice(start, start + pageSize);
  }, [state]);
}

function useCart() {
  const { state, dispatch } = useStore();

  const addToCart = (product) => {
    dispatch({ type: 'ADD_TO_CART', payload: product });
  };

  const removeFromCart = (productId) => {
    dispatch({ type: 'REMOVE_FROM_CART', payload: productId });
  };

  const total = state.cart.reduce((sum, item) => sum + item.price, 0);

  return { cart: state.cart, addToCart, removeFromCart, total };
}

function useTheme() {
  const { state, dispatch } = useStore();
  const toggleTheme = () => {
    dispatch({ type: 'SET_THEME', payload: state.theme === 'light' ? 'dark' : 'light' });
  };
  return { theme: state.theme, toggleTheme };
}
```''', r'''<think>
Let me review this React state management with useReducer and context.

1. Single monolithic state:
- One reducer handles products, cart, user, filters, sort, page, sidebar, AND theme. These are completely unrelated concerns. Changing the theme causes the entire state reference to change, triggering re-renders in all consumers.
- The reducer is a giant switch statement that will only grow. Hard to test individual concerns.

2. Context value re-renders everything:
- `<StoreContext.Provider value={{ state, dispatch }}>` creates a new object on every render. But since state changes on every dispatch (new object from spread), every consumer re-renders on every state change.
- A component that only needs theme still re-renders when cart changes because it consumes the same context.

3. useProducts memoization issue:
- `useMemo(() => {...}, [state])` depends on the entire state object. Since state is a new object on every dispatch, this memo NEVER caches. It recomputes on every render.
- The filtering, sorting, and pagination logic is computed client-side but should ideally use server-side pagination for large datasets.

4. useCart creates new functions every render:
- addToCart and removeFromCart are new function references on every render. If passed as props to child components, they trigger re-renders. Should use useCallback.
- total is recalculated on every render, not memoized.

5. useTheme stale closure:
- toggleTheme captures state.theme from the render closure. But since dispatch is synchronous and reducer produces new state, this is actually fine for single toggles. However, rapid double-toggles could be an issue.

6. Reducer design:
- Most actions are just "SET_X" with a payload. This is essentially recreating useState with extra boilerplate. The reducer adds no value for simple setters.
- No action creators or constants. Action type strings are scattered throughout the codebase.

7. Cart design:
- ADD_TO_CART appends the product. No duplicate detection or quantity tracking.
- REMOVE_FROM_CART uses id comparison. If duplicate products exist, it removes the first match only... actually filter removes all matches. Ambiguous with duplicates.

Let me write the review.
</think>

## Code Review: React State Management with useReducer

### HIGH - Monolithic State Causes Global Re-renders

**MS1: Single state object for unrelated concerns (Severity: HIGH)**
Products, cart, user, filters, sort, page, sidebar, and theme are all in one state object. Any dispatch creates a new state reference via spread, causing all context consumers to re-render:
- Toggling the sidebar re-renders the product list
- Changing the theme re-renders the cart
- Any filter change triggers the entire tree

Split into separate contexts:
```jsx
const ProductContext = createContext();
const CartContext = createContext();
const UIContext = createContext();  // theme, sidebar
```
Each context only triggers re-renders for its consumers.

### HIGH - useMemo Depends on Entire State

**UM1: Products memo never caches (Severity: HIGH)**
```jsx
return useMemo(() => {
  // ... filtering, sorting, pagination ...
}, [state]);
```
The dependency is the entire `state` object, which is a new reference on every dispatch. The useMemo recomputes on EVERY render, providing zero memoization benefit. Narrow the dependencies:
```jsx
}, [state.products, state.filters, state.sort, state.page]);
```

### HIGH - New Functions on Every Render

**FN1: useCart returns unstable function references (Severity: HIGH)**
```jsx
const addToCart = (product) => {
  dispatch({ type: 'ADD_TO_CART', payload: product });
};
```
New function reference on every render. If `addToCart` is passed to a `React.memo` child, the memo is defeated. Wrap in useCallback:
```jsx
const addToCart = useCallback((product) => {
  dispatch({ type: 'ADD_TO_CART', payload: product });
}, [dispatch]);
```
`dispatch` is stable (from useReducer), so this callback never changes.

### MEDIUM - Reducer Overdesign

**RD1: SET_X actions are useState with extra steps (Severity: MEDIUM)**
Actions like `SET_LOADING`, `SET_ERROR`, `SET_PAGE`, `SET_THEME`, `TOGGLE_SIDEBAR` are simple value setters. Using a reducer for these adds boilerplate without benefit. Consider:
- Separate `useState` for simple values (loading, error, page)
- Reducer only for complex state transitions (cart operations, filter combinations)

### MEDIUM - Context Value Object

**CV1: Provider value creates new object (Severity: MEDIUM)**
```jsx
<StoreContext.Provider value={{ state, dispatch }}>
```
`{ state, dispatch }` is a new object each render. While `dispatch` is stable, `state` changes on every dispatch. Memoize the value or split contexts so stable values (dispatch) do not share a context with changing values (state).

### MEDIUM - Cart Duplicates

**CD1: No duplicate or quantity handling (Severity: MEDIUM)**
ADD_TO_CART appends the product object as-is. Adding the same product twice creates duplicate entries. REMOVE_FROM_CART with `filter` removes ALL entries with that ID. The behavior is inconsistent:
```jsx
case 'ADD_TO_CART': {
  const existing = state.cart.find(i => i.id === action.payload.id);
  if (existing) {
    return {
      ...state,
      cart: state.cart.map(i =>
        i.id === action.payload.id ? { ...i, quantity: i.quantity + 1 } : i
      ),
    };
  }
  return { ...state, cart: [...state.cart, { ...action.payload, quantity: 1 }] };
}
```

### LOW - No Action Constants

**AC1: String action types prone to typos (Severity: LOW)**
Action types like `'SET_PRODUCTS'` are bare strings. A typo silently hits the default case, returning unchanged state with no error. Define constants:
```jsx
const ACTIONS = {
  SET_PRODUCTS: 'SET_PRODUCTS',
  ADD_TO_CART: 'ADD_TO_CART',
  // ...
};
```

### LOW - Cart Total Not Memoized

**CT1: total recalculated every render (Severity: LOW)**
```jsx
const total = state.cart.reduce((sum, item) => sum + item.price, 0);
```
Wrap in useMemo:
```jsx
const total = useMemo(
  () => state.cart.reduce((sum, item) => sum + item.price, 0),
  [state.cart]
);
```'''),

    ("thinking/code-review", r'''Review this React hooks code and identify issues:

```jsx
import { useState, useEffect, useCallback, useRef, useSyncExternalStore } from 'react';

function useWebSocket(url) {
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMessages(prev => [...prev, data]);
    };
    ws.onerror = (error) => console.error('WebSocket error:', error);

    return () => ws.close();
  }, [url]);

  const send = (data) => {
    wsRef.current.send(JSON.stringify(data));
  };

  return { messages, connected, send };
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);

    const handler = (e) => setMatches(e.matches);
    media.addListener(handler);

    return () => media.removeListener(handler);
  }, [query]);

  return matches;
}

function useClickOutside(ref, handler) {
  useEffect(() => {
    const listener = (event) => {
      if (!ref.current || ref.current.contains(event.target)) {
        return;
      }
      handler(event);
    };

    document.addEventListener('mousedown', listener);
    document.addEventListener('touchstart', listener);

    return () => {
      document.removeEventListener('mousedown', listener);
      document.removeEventListener('touchstart', listener);
    };
  }, []);
}

function useForm(initialValues, validate) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setValues({ ...values, [name]: value });
  };

  const handleBlur = (e) => {
    const { name } = e.target;
    setTouched({ ...touched, [name]: true });
    if (validate) {
      const validationErrors = validate(values);
      setErrors(validationErrors);
    }
  };

  const handleSubmit = (onSubmit) => async (e) => {
    e.preventDefault();
    const validationErrors = validate ? validate(values) : {};
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length === 0) {
      setSubmitting(true);
      try {
        await onSubmit(values);
      } finally {
        setSubmitting(false);
      }
    }
  };

  const reset = () => {
    setValues(initialValues);
    setErrors({});
    setTouched({});
  };

  return { values, errors, touched, submitting, handleChange, handleBlur, handleSubmit, reset };
}

function ChatRoom({ roomId }) {
  const { messages, connected, send } = useWebSocket(`wss://chat.example.com/${roomId}`);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const isMobile = useMediaQuery('(max-width: 768px)');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (input.trim()) {
      send({ text: input, timestamp: Date.now() });
      setInput('');
    }
  };

  return (
    <div className={isMobile ? 'chat-mobile' : 'chat-desktop'}>
      <div className="status">{connected ? 'Connected' : 'Disconnected'}</div>
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i}>{msg.text}</div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <input value={input} onChange={e => setInput(e.target.value)}
             onKeyDown={e => e.key === 'Enter' && handleSend()} />
      <button onClick={handleSend} disabled={!connected}>Send</button>
    </div>
  );
}
```''', r'''<think>
Let me review these custom hooks.

1. useWebSocket issues:
- send() calls wsRef.current.send() without checking if the WebSocket is open. If called while disconnected, it throws.
- Messages accumulate unboundedly. Long chat sessions will consume more and more memory.
- No reconnection logic. If the connection drops, it stays disconnected.
- JSON.parse(event.data) has no try-catch. Non-JSON messages crash the handler.
- onclose does not distinguish between intentional close (cleanup) and unexpected disconnect.

2. useMediaQuery:
- Uses the deprecated addListener/removeListener API. Should use addEventListener/removeEventListener.
- Initial state is false regardless of actual match. On first render, the component may flash the wrong layout before the effect runs and updates. Use useSyncExternalStore or initialize with matchMedia result:
  `useState(() => window.matchMedia(query).matches)`

3. useClickOutside:
- Dependency array is empty []. handler and ref are captured from the first render. If handler changes (e.g., it closes different modals based on state), the stale handler is called. Add handler to dependencies.
- ref might not be stable if the parent passes a new ref object.

4. useForm:
- handleChange uses `{ ...values, [name]: value }` from closure. Rapid changes can lose updates. Should use functional updater: `setValues(prev => ({ ...prev, [name]: value }))`.
- handleBlur validates the entire form, not just the field that was blurred. This means errors for untouched fields appear after blurring one field.
- reset() uses `initialValues` from closure. If `initialValues` changes (e.g., editing a different record), reset goes back to the original values, not the current initial values.
- No way to set a specific field programmatically.
- handleSubmit returns a function (curried) which is a nice pattern but may confuse some developers.

5. ChatRoom:
- messages.map with index key. When messages are added at the end, index keys are stable. But if messages were modified or removed, keys would shift.
- scrollIntoView runs on every message update, even when the user has scrolled up to read history. This is annoying -- the view jumps to the bottom while reading.
- handleSend is a new function each render. Not critical but could be memoized.
- No handling of WebSocket reconnection.

Let me write the review.
</think>

## Code Review: React Custom Hooks Suite

### HIGH - useWebSocket Missing Reconnection

**WS1: No auto-reconnection (Severity: HIGH)**
When the WebSocket connection drops (network issue, server restart), `onclose` fires and `connected` becomes false. The connection stays dead. Users must refresh the page. Add reconnection logic:
```jsx
useEffect(() => {
  let ws;
  let retryCount = 0;
  const connect = () => {
    ws = new WebSocket(url);
    ws.onopen = () => { setConnected(true); retryCount = 0; };
    ws.onclose = () => {
      setConnected(false);
      const delay = Math.min(1000 * 2 ** retryCount, 30000);
      setTimeout(connect, delay);
      retryCount++;
    };
    // ...
    wsRef.current = ws;
  };
  connect();
  return () => ws.close();
}, [url]);
```

**WS2: send() crashes when disconnected (Severity: HIGH)**
```jsx
const send = (data) => {
  wsRef.current.send(JSON.stringify(data));
};
```
Calling send when the WebSocket is not open throws `InvalidStateError`. Check ready state:
```jsx
const send = useCallback((data) => {
  if (wsRef.current?.readyState === WebSocket.OPEN) {
    wsRef.current.send(JSON.stringify(data));
  }
}, []);
```

**WS3: No JSON parse error handling (Severity: MEDIUM)**
`JSON.parse(event.data)` crashes on non-JSON messages.

### HIGH - useClickOutside Stale Handler

**CO1: Handler never updates (Severity: HIGH)**
```jsx
useEffect(() => {
  const listener = (event) => {
    // ...
    handler(event);
  };
  // ...
}, []);  // empty deps
```
The `handler` function is captured from the first render. If the parent component passes a different handler based on state, the stale handler is called. Add `handler` to dependencies, or use a ref:
```jsx
const handlerRef = useRef(handler);
handlerRef.current = handler;
useEffect(() => {
  const listener = (event) => {
    if (!ref.current?.contains(event.target)) {
      handlerRef.current(event);
    }
  };
  document.addEventListener('mousedown', listener);
  return () => document.removeEventListener('mousedown', listener);
}, [ref]);
```

### MEDIUM - useMediaQuery Flash

**MQ1: Initial state is always false (Severity: MEDIUM)**
```jsx
const [matches, setMatches] = useState(false);
```
On first render, `matches` is false regardless of actual screen size. Components may flash the wrong layout. Initialize from the query:
```jsx
const [matches, setMatches] = useState(
  () => window.matchMedia(query).matches
);
```

**MQ2: Deprecated API (Severity: LOW)**
`media.addListener` is deprecated. Use `media.addEventListener('change', handler)`.

### MEDIUM - useForm Stale Closures

**FM1: handleChange loses rapid updates (Severity: MEDIUM)**
```jsx
setValues({ ...values, [name]: value });
```
`values` is from the render closure. Rapid changes to different fields can lose the first change. Use the functional updater:
```jsx
setValues(prev => ({ ...prev, [name]: value }));
```

**FM2: handleBlur validates entire form (Severity: MEDIUM)**
After blurring one field, errors for ALL fields appear (including untouched ones). Validate only the blurred field, or filter errors to show only for touched fields in the UI.

**FM3: reset uses stale initialValues (Severity: MEDIUM)**
If the parent passes different `initialValues` (editing a different entity), `reset()` reverts to the original values from mount time. Store current initial values in a ref.

### MEDIUM - Unbounded Message List

**UBM1: Messages grow forever (Severity: MEDIUM)**
```jsx
setMessages(prev => [...prev, data]);
```
In a long chat session, thousands of messages accumulate in state, consuming memory and slowing renders. Limit the stored messages:
```jsx
setMessages(prev => [...prev.slice(-500), data]);
```

### MEDIUM - Auto-Scroll Interrupts Reading

**AS1: scrollIntoView fires on every new message (Severity: MEDIUM)**
```jsx
useEffect(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [messages]);
```
If the user scrolled up to read history, new messages force-scroll to the bottom. Check if the user is near the bottom before auto-scrolling:
```jsx
const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
if (isNearBottom) messagesEndRef.current?.scrollIntoView(...);
```'''),

    ("thinking/code-review", r'''Review this React hooks code and identify issues:

```jsx
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';

function useAsync(asyncFn, immediate = true) {
  const [status, setStatus] = useState('idle');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const execute = useCallback(async (...args) => {
    setStatus('pending');
    setData(null);
    setError(null);
    try {
      const result = await asyncFn(...args);
      setData(result);
      setStatus('success');
      return result;
    } catch (err) {
      setError(err);
      setStatus('error');
      throw err;
    }
  }, [asyncFn]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate]);

  return { execute, status, data, error };
}

function useThrottle(value, interval = 500) {
  const [throttledValue, setThrottledValue] = useState(value);
  const lastUpdated = useRef(Date.now());

  useEffect(() => {
    const now = Date.now();
    if (now >= lastUpdated.current + interval) {
      lastUpdated.current = now;
      setThrottledValue(value);
    } else {
      const timerId = setTimeout(() => {
        lastUpdated.current = Date.now();
        setThrottledValue(value);
      }, interval - (now - lastUpdated.current));
      return () => clearTimeout(timerId);
    }
  }, [value, interval]);

  return throttledValue;
}

function useIntersectionObserver(options = {}) {
  const [entry, setEntry] = useState(null);
  const [node, setNode] = useState(null);
  const observer = useRef(null);

  useEffect(() => {
    if (observer.current) observer.current.disconnect();
    observer.current = new IntersectionObserver(
      ([entry]) => setEntry(entry),
      options
    );
    if (node) observer.current.observe(node);
    return () => observer.current.disconnect();
  }, [node, options]);

  return [setNode, entry];
}

function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef(null);

  const copy = useCallback(async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
    }
  }, []);

  return { copy, copied };
}

function DocumentViewer({ docId }) {
  const fetchDoc = useCallback(
    () => fetch(`/api/docs/${docId}`).then(r => r.json()),
    [docId]
  );
  const { data: doc, status, error } = useAsync(fetchDoc);
  const [searchRef, searchEntry] = useIntersectionObserver({ threshold: 0.5 });
  const { copy, copied } = useCopyToClipboard();
  const isMobile = useThrottle(window.innerWidth < 768, 200);

  if (status === 'pending') return <div>Loading...</div>;
  if (status === 'error') return <div>Error: {error.message}</div>;
  if (!doc) return null;

  return (
    <div>
      <h1>{doc.title}</h1>
      <button onClick={() => copy(doc.content)}>
        {copied ? 'Copied!' : 'Copy'}
      </button>
      <div dangerouslySetInnerHTML={{ __html: doc.content }} />
      <div ref={searchRef}>
        {searchEntry?.isIntersecting && <RelatedDocs docId={docId} />}
      </div>
    </div>
  );
}
```''', r'''<think>
Let me review these hooks.

1. useAsync:
- asyncFn is in the useCallback dependency. If the caller passes an inline async function, it is a new reference every render, causing execute to be recreated, which triggers the useEffect (since execute is a dependency), causing an infinite loop.
- The effect runs execute() when immediate is true. But execute is a new function when asyncFn changes. If asyncFn changes frequently, this triggers repeated fetches.
- setData(null) on execute clears previous data, causing a flash of loading state even for refetches.

2. useThrottle:
- The implementation has a subtle issue. The useEffect runs when value changes. If the value changes rapidly, the first change is applied immediately (if enough time has passed), but subsequent changes create timeouts. However, the cleanup function only clears the timeout when a new effect runs. The effect runs on every value change, so rapid changes keep clearing and resetting the timeout. The last value is eventually set after the interval. This is closer to debounce behavior than true throttle.
- Actually looking more carefully: if now >= lastUpdated + interval, it updates immediately. Otherwise, it schedules a delayed update. This is a leading-edge throttle with a trailing edge -- which is actually a reasonable throttle implementation.

3. useIntersectionObserver:
- `options` is in the dependency array. If the caller passes `{ threshold: 0.5 }` inline, it is a new object on every render, causing the observer to be recreated on every render. Same issue as useMemo with object dependencies.
- Uses callback ref pattern (setNode) which is good for dynamic elements.

4. useCopyToClipboard:
- The fallback using document.execCommand('copy') is deprecated. But it is a reasonable fallback for older browsers.
- The fallback creates a textarea but does not handle the case where setCopied(true) should have a timeout reset like the main path. The timeout is only set in the try block, not the fallback.
- timeoutRef is never cleared on unmount. If the component unmounts before the timeout fires, setCopied is called on an unmounted component.

5. DocumentViewer:
- dangerouslySetInnerHTML with doc.content is an XSS vulnerability. If the API returns unsanitized HTML, malicious scripts can execute.
- isMobile uses useThrottle with window.innerWidth < 768. But this value is computed once on render and passed to useThrottle. It does not update when the window resizes. Need a window resize listener.
- useAsync with fetchDoc: fetchDoc changes when docId changes (correct). This triggers execute which fetches the new doc. But the effect dependency on execute means if anything in the useCallback deps changes, it re-fetches.

Let me write the review.
</think>

## Code Review: React Advanced Hooks

### CRITICAL - XSS Vulnerability

**XSS1: Unsanitized HTML rendering (Severity: CRITICAL)**
```jsx
<div dangerouslySetInnerHTML={{ __html: doc.content }} />
```
If the API returns user-generated or attacker-controlled HTML, scripts execute in the user's browser. Always sanitize HTML before rendering:
```jsx
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(doc.content) }} />
```

### HIGH - useAsync Infinite Loop Risk

**AL1: Inline asyncFn causes infinite re-fetch (Severity: HIGH)**
`useAsync` puts `asyncFn` in `useCallback`'s dependency array, and `execute` is in the `useEffect` dependency array. If a caller passes an inline function:
```jsx
const { data } = useAsync(async () => fetch('/api/data').then(r => r.json()));
```
The inline function is a new reference every render, causing: new asyncFn -> new execute -> effect fires -> fetch -> setState -> re-render -> new asyncFn... infinite loop.

DocumentViewer avoids this by wrapping `fetchDoc` in `useCallback`, but the hook API is fragile. Use a ref for asyncFn:
```jsx
const asyncFnRef = useRef(asyncFn);
asyncFnRef.current = asyncFn;

const execute = useCallback(async (...args) => {
  // ... use asyncFnRef.current instead of asyncFn
}, []); // stable reference
```

### HIGH - isMobile Does Not Update

**IM1: Window width not reactive (Severity: HIGH)**
```jsx
const isMobile = useThrottle(window.innerWidth < 768, 200);
```
`window.innerWidth < 768` is evaluated once per render. It does not update when the window is resized. You need a resize listener:
```jsx
function useWindowWidth() {
  const [width, setWidth] = useState(window.innerWidth);
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  return width;
}
const width = useWindowWidth();
const isMobile = useThrottle(width < 768, 200);
```

### MEDIUM - useIntersectionObserver Options Loop

**IO1: Inline options object recreates observer (Severity: MEDIUM)**
```jsx
const [ref, entry] = useIntersectionObserver({ threshold: 0.5 });
```
The inline `{ threshold: 0.5 }` is a new object reference every render. Since `options` is in the useEffect dependency, the observer is disconnected and recreated every render. Memoize options in the consumer or serialize them for comparison inside the hook.

### MEDIUM - useCopyToClipboard Cleanup

**CC1: Timeout not cleared on unmount (Severity: MEDIUM)**
```jsx
timeoutRef.current = setTimeout(() => setCopied(false), 2000);
```
If the component unmounts before the timeout fires, `setCopied(false)` is called on an unmounted component. Add cleanup:
```jsx
useEffect(() => {
  return () => clearTimeout(timeoutRef.current);
}, []);
```

**CC2: Fallback path missing timeout reset (Severity: LOW)**
The `catch` block sets `setCopied(true)` but does not set the reset timeout. The "Copied!" state persists indefinitely when the fallback is used.

### MEDIUM - useAsync Data Flash

**DF1: Data cleared on re-execute (Severity: MEDIUM)**
```jsx
setData(null);
```
When re-fetching (e.g., docId changes), data is set to null, causing a flash of "Loading..." even though previous data could be shown. Consider keeping stale data until the new data arrives:
```jsx
// Only clear data on initial load, not on refetch
if (status === 'idle') setData(null);
```

### LOW - Deprecated Clipboard API

**CL1: document.execCommand('copy') is deprecated (Severity: LOW)**
The fallback uses `execCommand('copy')` which is deprecated. For modern applications, the Clipboard API (`navigator.clipboard`) has wide support. The fallback may still be needed for HTTP (non-HTTPS) contexts where the Clipboard API is unavailable.'''),

    ("thinking/code-review", r'''Review this React hooks code and identify issues:

```jsx
import { useState, useEffect, useContext, createContext, useCallback, useMemo, useRef } from 'react';

const AuthContext = createContext();
const NotificationContext = createContext();

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      fetch('/api/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(r => r.json())
        .then(data => { setUser(data); setLoading(false); })
        .catch(() => { setToken(null); setLoading(false); });
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email, password) => {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    localStorage.setItem('token', data.token);
    setToken(data.token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

function useAuth() {
  return useContext(AuthContext);
}

function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const { token } = useAuth();

  useEffect(() => {
    if (!token) return;
    const es = new EventSource(`/api/events?token=${token}`);
    es.onmessage = (event) => {
      const notification = JSON.parse(event.data);
      setNotifications(prev => [notification, ...prev]);
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [token]);

  const dismiss = (id) => {
    setNotifications(notifications.filter(n => n.id !== id));
  };

  const dismissAll = () => setNotifications([]);

  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <NotificationContext.Provider value={{ notifications, dismiss, dismissAll, unreadCount }}>
      {children}
    </NotificationContext.Provider>
  );
}

function useNotifications() {
  return useContext(NotificationContext);
}

function usePagination(fetchFn, pageSize = 20) {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);

  const loadMore = async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    const newItems = await fetchFn(page, pageSize);
    setItems([...items, ...newItems]);
    setHasMore(newItems.length === pageSize);
    setPage(page + 1);
    setLoading(false);
  };

  const refresh = async () => {
    setPage(1);
    setItems([]);
    setHasMore(true);
    const newItems = await fetchFn(1, pageSize);
    setItems(newItems);
    setHasMore(newItems.length === pageSize);
    setPage(2);
  };

  return { items, loading, hasMore, loadMore, refresh };
}

function Dashboard() {
  const { user, loading: authLoading } = useAuth();
  const { notifications, unreadCount } = useNotifications();
  const fetchProjects = useCallback(
    (page, size) => fetch(`/api/projects?page=${page}&size=${size}`).then(r => r.json()),
    []
  );
  const { items: projects, loading: projectsLoading, hasMore, loadMore } = usePagination(fetchProjects);

  useEffect(() => {
    loadMore();
  }, []);

  if (authLoading) return <div>Loading...</div>;
  if (!user) return <div>Please log in</div>;

  return (
    <div>
      <h1>Welcome {user.name}</h1>
      <div>Notifications: {unreadCount}</div>
      <ul>
        {projects.map(p => <li key={p.id}>{p.name}</li>)}
      </ul>
      {hasMore && <button onClick={loadMore} disabled={projectsLoading}>Load More</button>}
    </div>
  );
}
```''', r'''<think>
Let me analyze this authentication and notification hooks pattern.

1. AuthProvider issues:
- useEffect dependency array is empty [], but it uses `token` from state. If token changes (after login), the effect does not re-run to validate the new token. However, login already sets the user, so validation only matters on mount. This is arguably fine for the initial fetch, but the empty dependency array means the effect captures the initial token value from state. Since token is read from localStorage.getItem('token') as the initial state, this works on mount. But ESLint would flag the missing dependency.

2. login function:
- Does not check res.ok before parsing JSON. If the server returns 401, res.json() might fail or return an error object, and data.token/data.user would be undefined, storing undefined in localStorage and state.
- login and logout are new function references on every render. The provider value object { user, token, loading, login, logout } is also new on every render, causing all consumers to re-render on every AuthProvider render.

3. Token in URL:
- EventSource passes token as a query parameter: `/api/events?token=${token}`. Tokens in URLs are logged by proxies, CDNs, browser history, and server access logs. This is a security concern.

4. NotificationProvider:
- EventSource onerror closes immediately without reconnect. EventSource normally auto-reconnects, but calling es.close() in onerror prevents that.
- Notifications accumulate without limit. Long-running sessions will consume growing memory.
- dismiss uses `notifications` from closure, not functional updater. Dismissing multiple notifications rapidly can lose updates.

5. usePagination:
- loadMore uses `items`, `page` from closure, not functional updaters. Calling loadMore twice rapidly can lose the first page of results because the second call sees stale `items` and `page`.
- refresh sets page to 1 then fetches, but since setState is batched, the page state may not be 1 when fetchFn runs. Actually, refresh passes 1 directly to fetchFn, so this is fine for the fetch. But setPage(1) followed by setPage(2) at the end is correct.
- No error handling in loadMore or refresh. If fetchFn throws, loading stays true forever.

6. Dashboard:
- loadMore is called in useEffect with empty deps. But loadMore is a new function on every render (not wrapped in useCallback). This works because useEffect with [] only runs once on mount. But ESLint will flag loadMore as a missing dependency. If loadMore were added to deps, it would cause infinite re-renders because loadMore is recreated on each render.

Let me write the review.
</think>

## Code Review: Auth and Notification Context Hooks

### HIGH - Token Exposed in EventSource URL

**TK1: Token passed as query parameter (Severity: HIGH)**
```jsx
const es = new EventSource(`/api/events?token=${token}`);
```
Tokens in URLs are logged by reverse proxies, CDNs, and browser history. They appear in server access logs and can leak through the Referer header. EventSource does not support custom headers natively. Workarounds:
- Use a short-lived ticket exchanged via POST, then pass the ticket in the URL
- Use cookie-based auth for the SSE endpoint
- Use a proxy that adds the Authorization header

### HIGH - usePagination Stale Closure on loadMore

**PG1: loadMore captures stale items and page (Severity: HIGH)**
```jsx
const loadMore = async () => {
  setItems([...items, ...newItems]);
  setPage(page + 1);
};
```
`items` and `page` are captured from the render closure. If loadMore is called twice before the first call finishes, the second call appends to the stale `items` list, losing the first page of new results. Use functional updaters:
```jsx
const loadMore = async () => {
  if (loading || !hasMore) return;
  setLoading(true);
  const currentPage = pageRef.current;
  const newItems = await fetchFn(currentPage, pageSize);
  setItems(prev => [...prev, ...newItems]);
  setHasMore(newItems.length === pageSize);
  setPage(p => p + 1);
  pageRef.current = currentPage + 1;
  setLoading(false);
};
```

### HIGH - No Error Handling in Async Hooks

**EH1: fetchFn failure leaves loading=true (Severity: HIGH)**
Neither `loadMore` nor `refresh` have try/catch blocks. If `fetchFn` rejects, `setLoading(false)` never runs, leaving the UI in a permanent loading state. Wrap in try/finally:
```jsx
const loadMore = async () => {
  if (loading || !hasMore) return;
  setLoading(true);
  try {
    const newItems = await fetchFn(page, pageSize);
    setItems(prev => [...prev, ...newItems]);
    setHasMore(newItems.length === pageSize);
    setPage(p => p + 1);
  } catch (err) {
    console.error('Failed to load:', err);
  } finally {
    setLoading(false);
  }
};
```

### HIGH - login Does Not Check Response Status

**LG1: No error handling on failed login (Severity: HIGH)**
```jsx
const res = await fetch('/api/login', { ... });
const data = await res.json();
localStorage.setItem('token', data.token);
```
If the server returns 401 or 500, `res.json()` may parse an error response, and `data.token` is undefined. `localStorage.setItem('token', undefined)` stores the string "undefined". On next page load, the app sends `Bearer undefined` to `/api/me`. Check status:
```jsx
if (!res.ok) {
  const error = await res.json();
  throw new Error(error.message || 'Login failed');
}
```

### MEDIUM - EventSource Reconnection Disabled

**ES1: onerror kills auto-reconnect (Severity: MEDIUM)**
```jsx
es.onerror = () => es.close();
```
EventSource has built-in reconnection with exponential backoff. Calling `es.close()` in the error handler permanently disconnects. Remove the close call to allow auto-reconnect, or implement custom reconnection logic.

### MEDIUM - Auth Context Value Not Memoized

**AV1: Provider value triggers global re-renders (Severity: MEDIUM)**
```jsx
<AuthContext.Provider value={{ user, token, loading, login, logout }}>
```
A new object is created on every render. Every component using `useAuth()` re-renders whenever AuthProvider re-renders. Memoize the value:
```jsx
const value = useMemo(
  () => ({ user, token, loading, login, logout }),
  [user, token, loading]
);
```
Also wrap `login` and `logout` in `useCallback` so they are stable references.

### MEDIUM - Dismiss Uses Stale Closure

**DM1: Rapid dismissals lose notifications (Severity: MEDIUM)**
```jsx
const dismiss = (id) => {
  setNotifications(notifications.filter(n => n.id !== id));
};
```
`notifications` is from the render closure. Dismissing two notifications rapidly causes the second dismiss to operate on the stale list, restoring the first dismissed notification. Use functional updater:
```jsx
const dismiss = useCallback((id) => {
  setNotifications(prev => prev.filter(n => n.id !== id));
}, []);
```

### MEDIUM - Unbounded Notification List

**UN1: Notifications grow without limit (Severity: MEDIUM)**
New notifications are prepended without pruning old ones. Long-running sessions accumulate thousands of notifications. Cap the list:
```jsx
setNotifications(prev => [notification, ...prev].slice(0, 200));
```

### LOW - ESLint Dependency Warnings

**EL1: Missing deps in multiple useEffect calls (Severity: LOW)**
The AuthProvider useEffect omits `token` from deps. The Dashboard useEffect omits `loadMore`. While functionally acceptable in these specific cases, these trigger ESLint exhaustive-deps warnings and can mask real bugs.'''),
]
