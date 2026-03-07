"""
Code explanation training pairs - React component patterns, hooks, rendering
"""

pairs = [
    {
        "instruction": r'''Walk me through what this React hook does:

```jsx
function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(error);
      return initialValue;
    }
  });

  const setValue = useCallback((value) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(error);
    }
  }, [key, storedValue]);

  return [storedValue, setValue];
}
```''',
        "output": r'''This is a custom React hook that syncs state with `localStorage`, giving you persistent state that survives page refreshes.

**Initialization (useState with lazy initializer):**

The function passed to `useState(() => ...)` runs only on the first render, not on every re-render. It checks if a value already exists in localStorage for the given key. If found, it parses and uses it. If not (or if parsing fails), it falls back to `initialValue`. This means if the user already has saved preferences, they are restored.

**The setter function (setValue):**

Wrapped in `useCallback` to maintain referential stability across renders. It does two things:
1. Updates React state via `setStoredValue`.
2. Writes the new value to localStorage via `setItem`.

The `value instanceof Function` check supports functional updates -- you can call `setValue(prev => prev + 1)` just like a normal setState. It applies the function to the current stored value to compute the new one.

**The try/catch blocks:** localStorage can throw in several scenarios -- private browsing mode in some browsers, storage quota exceeded, or localStorage being disabled. The catches prevent these from crashing the component.

**A subtle issue:** If `key` changes between renders, the hook does not re-read from localStorage. The lazy initializer only runs once. You would need a `useEffect` watching `key` to handle dynamic keys properly.

**Another issue:** `storedValue` in the `useCallback` dependency array means `setValue` gets recreated every time the value changes. This could cause unnecessary re-renders in child components receiving `setValue` as a prop.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a React component that uses render props pattern with a mouse tracker.
</think>

Explain this React pattern to me:

```jsx
function MouseTracker({ render }) {
  const [position, setPosition] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMove = (e) => {
      setPosition({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, []);

  return render(position);
}

// Usage:
<MouseTracker render={({ x, y }) => (
  <div>Mouse is at ({x}, {y})</div>
)} />
```''',
        "output": r'''<think>
This is the render props pattern. I should explain what problem it solves, how the data flows, and the useEffect cleanup.
</think>

This is the "render props" pattern -- a technique for sharing stateful logic between components by passing a function as a prop.

**What MouseTracker does:**

1. Manages mouse position state internally using `useState`.
2. Sets up a `mousemove` event listener on mount (the empty `[]` dependency array means the effect runs once).
3. On every mouse movement, updates state with the new coordinates.
4. Instead of rendering its own UI, it calls `render(position)` -- delegating the rendering decision to the parent.

**The cleanup function:** `return () => window.removeEventListener(...)` runs when the component unmounts. Without this, the event listener would leak -- it would keep firing and trying to update state on an unmounted component, causing a memory leak and a React warning.

**Why this pattern?**

The parent component decides what to display with the mouse data. One parent might show coordinates as text, another might move a tooltip, a third might draw on a canvas. MouseTracker encapsulates the "tracking" behavior without dictating the UI.

**Performance note:** Every mouse move triggers a state update and re-render. For smooth UIs this is fine, but for complex render functions, this could cause jank. Throttling the event handler (e.g., with requestAnimationFrame) would help.

**Modern alternative:** Custom hooks like `useMousePosition()` have largely replaced render props for this kind of logic reuse. They are simpler and avoid the nesting that render props create.'''
    },
    {
        "instruction": r'''What does this component do and how does the useEffect work?

```jsx
function InfiniteScroll({ loadMore, hasMore, children }) {
  const observerRef = useRef(null);
  const sentinelRef = useRef(null);

  useEffect(() => {
    if (!hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (sentinelRef.current) {
      observer.observe(sentinelRef.current);
    }

    observerRef.current = observer;

    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  return (
    <div>
      {children}
      {hasMore && <div ref={sentinelRef} style={{ height: 1 }} />}
    </div>
  );
}
```''',
        "output": r'''This component implements infinite scrolling using the Intersection Observer API instead of scroll event listeners.

**How it works:**

1. It renders its children (the list items) plus a tiny sentinel div (1px tall) at the bottom, but only when there are more items to load.

2. The `useEffect` creates an IntersectionObserver that watches the sentinel div. When 10% or more of that sentinel becomes visible in the viewport (`threshold: 0.1`), it means the user has scrolled near the bottom, and `loadMore()` is called to fetch more data.

3. `observerRef` stores the observer instance (though it is not actually used elsewhere in this code). `sentinelRef` is attached to the sentinel div so the observer knows what DOM element to watch.

**The useEffect dependency array `[hasMore, loadMore]`:**

The effect re-runs when either value changes. This is important because:
- When `hasMore` becomes false, the effect returns early and does not set up an observer (and the sentinel div is not even rendered).
- If `loadMore` changes identity (which happens if the parent does not memoize it), the observer is torn down and recreated.

**The cleanup function `() => observer.disconnect()`** detaches the observer when the effect re-runs or the component unmounts. This prevents stale observers from calling old versions of `loadMore`.

**Why Intersection Observer over scroll events?** Scroll events fire extremely frequently and require manual calculation of element positions. IntersectionObserver is handled by the browser off the main thread and is much more performant.

**Potential issue:** If `loadMore` is not memoized with `useCallback` in the parent, the observer will be recreated on every parent render.'''
    },
    {
        "instruction": r'''Explain this React Context pattern:

```jsx
const ThemeContext = createContext(null);

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState('light');

  const value = useMemo(() => ({
    theme,
    toggleTheme: () => setTheme(t => t === 'light' ? 'dark' : 'light'),
    isDark: theme === 'dark',
  }), [theme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

function useTheme() {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
```''',
        "output": r'''This implements a theme system using React Context, providing a clean API for any component in the tree to read and toggle the theme.

**The three pieces:**

1. **`ThemeContext`**: Created with `createContext(null)`. The `null` default is intentional -- it is used as a sentinel to detect misuse.

2. **`ThemeProvider`**: A wrapper component that holds the theme state and provides it to the entire subtree via `ThemeContext.Provider`.

3. **`useTheme`**: A custom hook that reads the context. The `null` check ensures developers get a clear error if they forget to wrap their app in `ThemeProvider` -- instead of getting cryptic "cannot read property of null" errors later.

**Why `useMemo` on the value object?**

Without it, every time `ThemeProvider` re-renders (even for unrelated reasons), a new object would be created for `value`. Since Context uses reference equality to detect changes, ALL consumers of the context would re-render even if the theme did not change. `useMemo` ensures the object only changes when `theme` actually changes.

**The dependency array `[theme]`:** The `toggleTheme` function and `isDark` both derive from `theme`, so when `theme` changes, all three values need to update. When it does not change, the same memoized object is reused.

**How `toggleTheme` works:** The functional update `setTheme(t => ...)` is used instead of `setTheme(theme === ...)` to avoid a stale closure. Since `toggleTheme` is inside `useMemo`, it would capture the old `theme` value without the functional form.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a React component that uses useReducer for form state management. Let me trace through the reducer logic.
</think>

What is this doing and why use useReducer here instead of useState?

```jsx
const formReducer = (state, action) => {
  switch (action.type) {
    case 'SET_FIELD':
      return {
        ...state,
        values: { ...state.values, [action.field]: action.value },
        errors: { ...state.errors, [action.field]: null },
      };
    case 'SET_ERROR':
      return {
        ...state,
        errors: { ...state.errors, [action.field]: action.error },
      };
    case 'SUBMIT':
      return { ...state, isSubmitting: true };
    case 'SUBMIT_SUCCESS':
      return { ...state, isSubmitting: false, submitCount: state.submitCount + 1 };
    case 'SUBMIT_FAILURE':
      return { ...state, isSubmitting: false, errors: action.errors };
    case 'RESET':
      return action.initialState;
    default:
      return state;
  }
};
```''',
        "output": r'''<think>
This is a form state reducer. I should explain each action, the state shape, and why useReducer is better than useState for this case.
</think>

This is a reducer function for managing complex form state with `useReducer`. It handles field values, validation errors, and submission status in a single state object.

**State shape:**
```
{ values: {...}, errors: {...}, isSubmitting: bool, submitCount: number }
```

**Each action explained:**

- **SET_FIELD**: Updates a single field's value AND clears that field's error. This is a nice UX touch -- when the user starts fixing a field, the error message disappears immediately rather than persisting until the next submit.

- **SET_ERROR**: Sets a validation error for a specific field without changing values.

- **SUBMIT**: Marks the form as submitting (for disabling buttons, showing spinners).

- **SUBMIT_SUCCESS**: Clears the submitting flag and increments `submitCount`. The count can be used to track re-submissions or trigger effects.

- **SUBMIT_FAILURE**: Clears the submitting flag and sets multiple errors at once (e.g., server-side validation errors).

- **RESET**: Replaces the entire state with the initial state passed via the action.

**Why useReducer instead of multiple useState calls?**

1. **Related state transitions**: SET_FIELD updates both values and errors atomically. With separate `useState` calls, you would need two `setState` calls, risking a render between them with inconsistent state.

2. **Predictable transitions**: All state changes are enumerated in one place. You can look at the reducer and understand every possible state change the form can undergo.

3. **Testability**: The reducer is a pure function -- you can unit test it without rendering any components. Pass in a state and action, assert the output.

4. **Complex updates**: SUBMIT_FAILURE replaces the entire errors object, which would be awkward to express with a simple setter.'''
    },
]
