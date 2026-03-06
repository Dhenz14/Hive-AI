PAIRS = [
    ("thinking/debugging", r'''My React useEffect has a stale closure bug. The counter shows in the console but the displayed value is always 0:

```jsx
function Timer() {
    const [count, setCount] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            console.log('Current count:', count);  // always logs 0!
            setCount(count + 1);  // always sets to 1!
        }, 1000);

        return () => clearInterval(interval);
    }, []);  // empty dependency array

    return <div>Count: {count}</div>;
}
```

The component shows "Count: 1" and never increments further. Console keeps logging "Current count: 0". Why?''', r'''<think>
The counter shows "Count: 1" and never increments further. This could be a setInterval issue where the interval is being cleared prematurely... but wait, the cleanup function only runs on unmount since the dependency array is empty, so the interval should keep running.

Hmm, actually this is the classic stale closure problem in React hooks. The useEffect has an empty dependency array `[]`, so it runs only once on mount. The callback function created at that time closes over the `count` variable from that render, which is `0`.

Even though `setCount(count + 1)` is called repeatedly, `count` in the closure is always `0` (the initial value). So it always does `setCount(0 + 1)` = `setCount(1)`. After the first tick, count becomes 1 in the component, but the closure still has the old count of 0. Because each React render creates a new snapshot of state, therefore the old closure is permanently stuck with the initial snapshot.

I considered suggesting they add `count` to the dependency array, but that creates a different tradeoff: the interval would be cleared and recreated on every state change, which is less efficient. The better fix is the functional updater form `setCount(prev => prev + 1)` which does not depend on the closed-over value at all.
</think>

This is a stale closure bug. The `useEffect` callback is created once (because of the empty dependency array `[]`) and closes over the `count` value from the initial render, which is `0`. This closure never sees updated values of `count`.

**What happens each second:**
```
Tick 1: closure reads count = 0, calls setCount(0 + 1) -> count becomes 1
Tick 2: closure reads count = 0 (stale!), calls setCount(0 + 1) -> count stays 1
Tick 3: closure reads count = 0 (stale!), calls setCount(0 + 1) -> count stays 1
```

The `setInterval` callback was created during the first render and permanently captured `count = 0`. React re-renders the component with `count = 1`, but the old closure still exists in the interval and still sees `count = 0`.

**Fix 1: Use functional updater (best for this case)**

```jsx
function Timer() {
    const [count, setCount] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setCount(prevCount => prevCount + 1);  // uses latest value
        }, 1000);

        return () => clearInterval(interval);
    }, []);

    return <div>Count: {count}</div>;
}
```

The functional form `setCount(prev => prev + 1)` does not depend on the closed-over `count`. React provides the current state value as `prev`, so it always increments correctly.

**Fix 2: Add count to dependency array**

```jsx
function Timer() {
    const [count, setCount] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setCount(count + 1);
        }, 1000);

        return () => clearInterval(interval);
    }, [count]);  // re-run when count changes

    return <div>Count: {count}</div>;
}
```

This works but creates/destroys the interval on every render, which is less efficient. The interval is cleared and recreated each time count changes.

**Fix 3: Use useRef for mutable values**

```jsx
function Timer() {
    const [count, setCount] = useState(0);
    const countRef = useRef(count);

    useEffect(() => {
        countRef.current = count;  // keep ref in sync with state
    }, [count]);

    useEffect(() => {
        const interval = setInterval(() => {
            console.log('Current count:', countRef.current);  // always fresh
            setCount(prev => prev + 1);
        }, 1000);

        return () => clearInterval(interval);
    }, []);

    return <div>Count: {count}</div>;
}
```

`useRef` creates a mutable object that persists across renders. Unlike state, reading `countRef.current` always gives the latest value because it is a mutable reference, not a closed-over value.

**When to use each fix:**

- **Functional updater**: when the new state depends only on the previous state
- **Dependency array**: when the effect should re-run when a value changes
- **useRef**: when you need to read the latest value in a long-lived callback without re-running the effect

**Prevention tips:**
- Use the `react-hooks/exhaustive-deps` ESLint rule to catch missing dependencies
- Prefer functional updaters (`setState(prev => ...)`) in intervals and timeouts
- If you reference a value from state inside `setInterval` or `setTimeout`, it is likely stale
- Think of each render as a "snapshot" -- closures capture the snapshot, not live values'''),

    ("thinking/debugging", r'''My React component enters an infinite render loop:

```jsx
function UserProfile({ userId }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        fetchUser(userId).then(data => {
            setUser(data);
            setLoading(false);
        });
    }, [userId, user]);  // user in deps causes infinite loop!

    const displayName = user ? `${user.firstName} ${user.lastName}` : 'Loading...';

    return <div>{loading ? 'Loading...' : displayName}</div>;
}
```

The browser tab freezes and React DevTools shows hundreds of renders per second. What's causing the loop?''', r'''<think>
The browser tab freezes with hundreds of renders. This could be a rendering bug or missing memo... but wait, the useEffect dependency array includes `user`, which is set inside the effect itself. That is a circular dependency.

Let me trace the cycle:
1. Component mounts, user is null
2. useEffect runs, fetches data
3. setUser(data) triggers re-render with new user object
4. useEffect dependency check: user has changed (null -> object), so effect runs again
5. setUser(data) creates a NEW object (even if same data), triggers re-render
6. useEffect dependency check: user has changed (different object reference!), effect runs again
7. Infinite loop

I considered whether using deep comparison in the deps would fix it, but that won't work because React always uses Object.is() (reference equality), and each fetch creates a new object. Even if the data is identical, a new object is always "different" by reference.

Hmm, actually, the fundamental issue is a logical one: the effect's output (user) is listed as its own trigger. Because the effect depends on userId (the input) not user (the output), therefore removing `user` from the dependency array breaks the cycle. The ESLint exhaustive-deps rule might complain, but in this case the override is correct since `user` is not a true dependency of the fetching logic.
</think>

The infinite loop is caused by `user` being in the `useEffect` dependency array. Here is the cycle:

```
1. Effect runs -> fetches user -> setUser(newObject) -> re-render
2. React checks deps: user changed (new object reference) -> effect runs again
3. Fetches user again -> setUser(anotherNewObject) -> re-render
4. React checks deps: user changed again -> effect runs again
5. ... infinite loop
```

Each `fetchUser()` call returns a new object. Even if the data is identical, `{name: "Alice"} !== {name: "Alice"}` in JavaScript because React uses `Object.is()` for comparison (reference equality, not deep equality).

**Fix: Remove `user` from the dependency array**

```jsx
function UserProfile({ userId }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        fetchUser(userId).then(data => {
            setUser(data);
            setLoading(false);
        });
    }, [userId]);  // only re-fetch when userId changes

    const displayName = user ? `${user.firstName} ${user.lastName}` : 'Loading...';

    return <div>{loading ? 'Loading...' : displayName}</div>;
}
```

The effect should re-run when `userId` changes (to fetch new data), not when `user` changes (which is the result of the fetch). Including `user` creates a circular dependency: effect -> setUser -> user changes -> effect runs again.

**Additional fix: Handle race conditions with cleanup**

```jsx
function UserProfile({ userId }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;  // race condition guard

        setLoading(true);
        fetchUser(userId).then(data => {
            if (!cancelled) {
                setUser(data);
                setLoading(false);
            }
        });

        return () => {
            cancelled = true;  // cleanup: ignore stale response
        };
    }, [userId]);

    const displayName = user
        ? `${user.firstName} ${user.lastName}`
        : 'Loading...';

    return <div>{loading ? 'Loading...' : displayName}</div>;
}
```

If `userId` changes rapidly, the cleanup function marks old requests as cancelled so stale data does not overwrite newer data.

**Common infinite loop patterns:**

```jsx
// BAD: object in deps (new object every render)
useEffect(() => { ... }, [{ key: 'value' }]);

// BAD: array in deps (new array every render)
useEffect(() => { ... }, [[1, 2, 3]]);

// BAD: function created inline in deps
useEffect(() => { ... }, [() => doSomething()]);

// BAD: setting state that is also a dependency
useEffect(() => {
    setItems(items.filter(i => i.active));  // items changes -> loop!
}, [items]);

// GOOD: use functional updater to avoid the dependency
useEffect(() => {
    setItems(prev => prev.filter(i => i.active));
}, []);
```

**Prevention tips:**
- Never include state that is SET inside the effect as a dependency
- Use the `react-hooks/exhaustive-deps` ESLint rule, but understand when to override it
- Memoize objects and functions with `useMemo` and `useCallback` before putting them in deps
- If an effect runs too often, add a `console.log` inside to trace the trigger
- Think about the data flow: effects should respond to inputs (props, URL params), not to their own outputs'''),

    ("thinking/debugging", r'''My React list re-renders every item when I add one new item, because I'm using array index as the key:

```jsx
function TodoList() {
    const [todos, setTodos] = useState([
        'Buy groceries',
        'Walk the dog',
        'Write code',
    ]);

    const addTodo = () => {
        setTodos(['New todo', ...todos]);  // prepend
    };

    return (
        <div>
            <button onClick={addTodo}>Add Todo</button>
            {todos.map((todo, index) => (
                <TodoItem key={index} text={todo} />
            ))}
        </div>
    );
}

const TodoItem = React.memo(({ text }) => {
    console.log(`Rendering: ${text}`);
    return <div>{text}</div>;
});
```

Console after clicking "Add Todo":
```
Rendering: New todo
Rendering: Buy groceries
Rendering: Walk the dog
Rendering: Write code
```

All 4 items re-render even though only 1 was added. React.memo should prevent unchanged items from re-rendering.''', r'''<think>
All 4 items re-render even though React.memo should prevent it. This could be a React.memo configuration problem... but wait, the issue is in the key prop, not React.memo itself. Using array index as the key when prepending items causes every key to map to different data.

When you prepend "New todo" to the front:
- Before: index 0 = "Buy groceries", index 1 = "Walk the dog", index 2 = "Write code"
- After: index 0 = "New todo", index 1 = "Buy groceries", index 2 = "Walk the dog", index 3 = "Write code"

From React's perspective (using key={index}):
- key=0 had text="Buy groceries", now has text="New todo" -> prop changed, re-render!
- key=1 had text="Walk the dog", now has text="Buy groceries" -> prop changed, re-render!
- key=2 had text="Write code", now has text="Walk the dog" -> prop changed, re-render!
- key=3 is new -> render

I considered whether appending instead of prepending would avoid the problem, but that is only a partial fix -- deletions and reordering would still cause the same issue. Because the fundamental problem is that index keys are unstable when the list changes, therefore stable unique keys are needed.

Hmm, actually, the tradeoff matters: index keys are fine for static lists that never change order. But for dynamic lists with insertions, deletions, or reordering, unique IDs are essential. With stable unique keys, React.memo correctly skips unchanged items, dropping from 4 renders to just 1.
</think>

Using array index as `key` causes every item to re-render when you prepend an item. Here is why:

**Before adding:**
```
key=0 -> text="Buy groceries"
key=1 -> text="Walk the dog"
key=2 -> text="Write code"
```

**After prepending "New todo":**
```
key=0 -> text="New todo"       (was "Buy groceries" -- prop changed!)
key=1 -> text="Buy groceries"  (was "Walk the dog" -- prop changed!)
key=2 -> text="Walk the dog"   (was "Write code" -- prop changed!)
key=3 -> text="Write code"     (new key)
```

React uses `key` to match elements across renders. Since indices shifted, every existing key now has a different `text` prop. `React.memo` sees the prop change and re-renders each item. The optimization is completely defeated.

**Fix: Use stable, unique keys**

```jsx
function TodoList() {
    const [todos, setTodos] = useState([
        { id: 1, text: 'Buy groceries' },
        { id: 2, text: 'Walk the dog' },
        { id: 3, text: 'Write code' },
    ]);

    const nextId = useRef(4);

    const addTodo = () => {
        setTodos([
            { id: nextId.current++, text: 'New todo' },
            ...todos,
        ]);
    };

    return (
        <div>
            <button onClick={addTodo}>Add Todo</button>
            {todos.map(todo => (
                <TodoItem key={todo.id} text={todo.text} />
            ))}
        </div>
    );
}
```

Now after prepending:
```
key=4 -> text="New todo"       (new -- renders)
key=1 -> text="Buy groceries"  (unchanged -- React.memo skips)
key=2 -> text="Walk the dog"   (unchanged -- React.memo skips)
key=3 -> text="Write code"     (unchanged -- React.memo skips)
```

Only 1 render instead of 4.

**Other problems caused by index keys:**

1. **Form inputs lose their state**: If items have input fields, the value of one item's input "moves" to another item when the list changes.

2. **Animations break**: CSS transitions fire on the wrong items because React reuses DOM nodes for different data.

3. **Component state mixes up**: If TodoItem has internal state (e.g., "expanded"), prepending an item shifts all state to the wrong items.

**When index keys are acceptable:**

- The list is static (never reordered, inserted, or deleted)
- Items have no internal state or controlled inputs
- The list is purely for display and performance does not matter

**Generating unique keys:**

```jsx
// Option 1: Use data from the backend (preferred)
items.map(item => <Item key={item.id} />)

// Option 2: Generate at creation time (not at render time!)
const addItem = (text) => {
    setItems(prev => [...prev, { id: crypto.randomUUID(), text }]);
};

// WRONG: generating key at render time
items.map(item => <Item key={Math.random()} />)  // forces re-render EVERY time!
```

**Prevention tips:**
- Never use array index as key for dynamic lists
- Never use Math.random() or Date.now() as key at render time
- Use database IDs, UUIDs, or incrementing counters created at data creation time
- Enable the React ESLint rule `react/no-array-index-key`
- Test list performance with React DevTools Profiler after adding/removing items'''),

    ("thinking/debugging", r'''My React Context is causing every consumer to re-render even when only part of the context changes:

```jsx
const AppContext = React.createContext();

function AppProvider({ children }) {
    const [user, setUser] = useState(null);
    const [theme, setTheme] = useState('light');
    const [notifications, setNotifications] = useState([]);

    const value = {
        user, setUser,
        theme, setTheme,
        notifications, setNotifications,
    };

    return (
        <AppContext.Provider value={value}>
            {children}
        </AppContext.Provider>
    );
}

// This component only uses theme but re-renders when notifications change
function ThemeToggle() {
    const { theme, setTheme } = useContext(AppContext);
    console.log('ThemeToggle rendered');
    return <button onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}>{theme}</button>;
}
```

Every time a notification is added, ThemeToggle re-renders even though it only uses theme. How do I fix this?''', r'''<think>
ThemeToggle re-renders when notifications change even though it only uses theme. This could be a missing React.memo... but wait, React.memo would not help here because useContext bypasses memo -- when context changes, the consumer always re-renders.

The deeper issue is that the context value is a new object on every render of AppProvider. Even if only `notifications` changes, the `value` object `{ user, setUser, theme, setTheme, notifications, setNotifications }` is recreated, which is a new reference. Because React's context uses Object.is() to compare values and a new object always fails reference equality, therefore ALL consumers re-render on ANY state change.

I considered just wrapping the value in useMemo, but that only prevents re-renders when the parent re-renders without state changes -- consumers still re-render when any context value changes. Hmm, actually the real fix requires splitting the context so that unrelated state changes do not trigger unrelated consumers.

The tradeoff between approaches:
1. Split contexts -- most effective but adds nesting complexity
2. Memoize context value -- simple but still couples all consumers
3. Selector pattern -- flexible but requires a library
4. Separate state from dispatch -- good for action-heavy components
</think>

The problem is that the `value` object is recreated on every render of `AppProvider`. Even when only `notifications` changes, a new `{ user, theme, notifications, ... }` object is created. React's Context uses `Object.is()` to compare the previous and next value. Since it is always a new object reference, ALL consumers re-render on ANY state change in the provider.

**Fix 1: Split into separate contexts (recommended)**

```jsx
const UserContext = React.createContext();
const ThemeContext = React.createContext();
const NotificationContext = React.createContext();

function AppProvider({ children }) {
    const [user, setUser] = useState(null);
    const [theme, setTheme] = useState('light');
    const [notifications, setNotifications] = useState([]);

    return (
        <UserContext.Provider value={useMemo(() => ({ user, setUser }), [user])}>
            <ThemeContext.Provider value={useMemo(() => ({ theme, setTheme }), [theme])}>
                <NotificationContext.Provider value={useMemo(() => ({
                    notifications, setNotifications
                }), [notifications])}>
                    {children}
                </NotificationContext.Provider>
            </ThemeContext.Provider>
        </UserContext.Provider>
    );
}

// Now ThemeToggle only re-renders when theme changes
function ThemeToggle() {
    const { theme, setTheme } = useContext(ThemeContext);
    return <button onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}>{theme}</button>;
}
```

**Fix 2: Memoize the context value**

If splitting is not practical, memoize the value to prevent new objects:

```jsx
function AppProvider({ children }) {
    const [user, setUser] = useState(null);
    const [theme, setTheme] = useState('light');
    const [notifications, setNotifications] = useState([]);

    const value = useMemo(() => ({
        user, setUser,
        theme, setTheme,
        notifications, setNotifications,
    }), [user, theme, notifications]);

    return (
        <AppContext.Provider value={value}>
            {children}
        </AppContext.Provider>
    );
}
```

This prevents re-renders when the parent re-renders WITHOUT state changes, but consumers still re-render when ANY context value changes.

**Fix 3: Separate state from dispatch**

```jsx
const StateContext = React.createContext();
const DispatchContext = React.createContext();

function AppProvider({ children }) {
    const [state, dispatch] = useReducer(reducer, initialState);

    return (
        <StateContext.Provider value={state}>
            <DispatchContext.Provider value={dispatch}>
                {children}
            </DispatchContext.Provider>
        </StateContext.Provider>
    );
}

// Components that only dispatch actions never re-render from state changes
function AddNotificationButton() {
    const dispatch = useContext(DispatchContext);  // dispatch is stable
    return <button onClick={() => dispatch({ type: 'ADD_NOTIFICATION' })}>Notify</button>;
}
```

`dispatch` from `useReducer` is stable across renders, so DispatchContext consumers never re-render due to state changes.

**Fix 4: Use an intermediate memo component**

```jsx
function ThemeToggle() {
    return (
        <AppContext.Consumer>
            {(value) => <MemoizedThemeButton theme={value.theme} setTheme={value.setTheme} />}
        </AppContext.Consumer>
    );
}

const MemoizedThemeButton = React.memo(({ theme, setTheme }) => {
    console.log('ThemeButton rendered');
    return <button onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}>{theme}</button>;
});
```

**Prevention tips:**
- Split contexts by update frequency: things that change often (notifications) should be separate from things that change rarely (theme, user)
- Always memoize context values with `useMemo`
- Separate state from dispatch for contexts with useReducer
- Consider using a state management library (Zustand, Jotai) for complex state that many components consume
- Profile with React DevTools to identify unnecessary re-renders'''),

    ("thinking/debugging", r'''React.memo is not preventing re-renders of my component:

```jsx
const ExpensiveList = React.memo(({ items, onItemClick }) => {
    console.log('ExpensiveList rendered');
    return (
        <ul>
            {items.map(item => (
                <li key={item.id} onClick={() => onItemClick(item.id)}>
                    {item.name}
                </li>
            ))}
        </ul>
    );
});

function Parent() {
    const [count, setCount] = useState(0);
    const [items] = useState([
        { id: 1, name: 'Item 1' },
        { id: 2, name: 'Item 2' },
    ]);

    const handleItemClick = (id) => {
        console.log('Clicked:', id);
    };

    return (
        <div>
            <button onClick={() => setCount(c => c + 1)}>Count: {count}</button>
            <ExpensiveList items={items} onItemClick={handleItemClick} />
        </div>
    );
}
```

Every time I click the count button, ExpensiveList re-renders even though items haven't changed. React.memo should prevent this!''', r'''<think>
React.memo should prevent re-renders when props are unchanged. The `items` array is stable (created with useState, same reference on each render). This could be an issue with React.memo itself... but wait, let me check the other prop. The `handleItemClick` function is defined inline in the Parent component body, which means it is a new function on every render.

React.memo does a shallow comparison of props. Because `handleItemClick` is recreated each render, therefore `onItemClick` is a different reference every time, and React.memo sees a prop change.

I considered whether passing the function directly without wrapping would help, but that won't work because the function creation happens in the component body regardless. The fix is to memoize the callback with useCallback so it maintains the same reference across renders. The tradeoff: useCallback has a small overhead from dependency checking, so it is only worth using when the child component is expensive to re-render (which it is here, given React.memo is applied).
</think>

`React.memo` performs a shallow comparison of props. The `items` prop is stable (same reference from useState). However, `handleItemClick` is a **new function on every render** of Parent. Each render creates a new function object, and `React.memo` sees that `onItemClick` has changed (different reference), so it re-renders `ExpensiveList`.

```javascript
// On each Parent render:
const handleItemClick = (id) => { ... };
// This creates a brand-new function object every time
// Previous onItemClick !== current onItemClick (different references)
// React.memo: "prop changed, must re-render!"
```

**Fix: Memoize the callback with useCallback**

```jsx
function Parent() {
    const [count, setCount] = useState(0);
    const [items] = useState([
        { id: 1, name: 'Item 1' },
        { id: 2, name: 'Item 2' },
    ]);

    const handleItemClick = useCallback((id) => {
        console.log('Clicked:', id);
    }, []);  // empty deps: function never changes

    return (
        <div>
            <button onClick={() => setCount(c => c + 1)}>Count: {count}</button>
            <ExpensiveList items={items} onItemClick={handleItemClick} />
        </div>
    );
}
```

`useCallback` returns the same function reference across renders (as long as its dependencies have not changed). Now `React.memo` sees that both `items` and `onItemClick` are the same references, and skips re-rendering.

**If the callback depends on state:**

```jsx
const handleItemClick = useCallback((id) => {
    console.log('Clicked:', id, 'count:', count);
}, [count]);  // new function when count changes -- which is expected
```

When `count` changes, a new function is created and `ExpensiveList` re-renders. If you want to avoid this, use a ref:

```jsx
const countRef = useRef(count);
countRef.current = count;

const handleItemClick = useCallback((id) => {
    console.log('Clicked:', id, 'count:', countRef.current);
}, []);  // stable function, reads current count via ref
```

**Also memoize computed values with useMemo:**

```jsx
const filteredItems = useMemo(() => {
    return items.filter(item => item.active);
}, [items]);

<ExpensiveList items={filteredItems} onItemClick={handleItemClick} />
```

Without `useMemo`, `filteredItems` would be a new array on every render even if `items` has not changed.

**The three tools for preventing re-renders:**

```
React.memo    - skips re-render if props are unchanged (component level)
useCallback   - returns stable function reference (function prop)
useMemo       - returns stable computed value (object/array prop)
```

All three use shallow comparison. For deep equality, provide a custom comparator:

```jsx
const ExpensiveList = React.memo(({ items, onItemClick }) => {
    // ...
}, (prevProps, nextProps) => {
    // Custom comparison: return true to skip re-render
    return JSON.stringify(prevProps.items) === JSON.stringify(nextProps.items);
});
```

**Prevention tips:**
- Wrap callbacks passed to memoized children with `useCallback`
- Wrap computed objects/arrays with `useMemo`
- Use React DevTools Profiler to verify memo is working
- Do not over-memoize: memo has overhead too, only use it for expensive components
- Consider using the React Compiler (React 19) which auto-memoizes'''),
]
