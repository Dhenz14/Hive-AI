"""
Code explanation training pairs - JavaScript closures, prototypes, event loop, promises
"""

pairs = [
    {
        "instruction": r'''What does this JavaScript code do?

```javascript
function createCounter(initial = 0) {
  let count = initial;

  return {
    increment() { return ++count; },
    decrement() { return --count; },
    reset() { count = initial; return count; },
    getCount() { return count; }
  };
}

const counter = createCounter(10);
console.log(counter.increment()); // ?
console.log(counter.increment()); // ?
console.log(counter.getCount()); // ?
```''',
        "output": r'''This demonstrates a closure-based module pattern in JavaScript. It creates a counter with private state that cannot be accessed directly from outside.

**How the closure works:**

`createCounter` defines a local variable `count` and returns an object with four methods. Those methods "close over" the `count` variable -- they retain access to it even after `createCounter` has finished executing. The `count` variable lives in the closure scope, not on the returned object.

**The key privacy mechanism:** There is no `counter.count` property. You cannot read or write the count directly -- you must use the provided methods. This is JavaScript's way of achieving encapsulation without classes or private fields.

**The outputs:**
- `counter.increment()` -> 11 (pre-increment: increments then returns)
- `counter.increment()` -> 12
- `counter.getCount()` -> 12

**Subtle detail about `reset`:** The `initial` parameter is also captured by the closure. Calling `counter.reset()` sets `count` back to 10 (the original argument). Since `initial` is a primitive (number), this is safe. If `initial` were an object, mutations to it after creation would affect the reset value.

**Each call creates independent state:** If you called `createCounter(0)` again, you would get a completely separate counter with its own `count` variable. The two closures do not interfere with each other.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain Promise chaining and error handling. I should trace the execution flow carefully and explain how .then and .catch interact.
</think>

Explain the flow of this Promise chain:

```javascript
function fetchUserData(userId) {
  return fetch(`/api/users/${userId}`)
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then(user => {
      return fetch(`/api/posts?author=${user.id}`);
    })
    .then(response => response.json())
    .then(posts => {
      return { user: null, posts };
    })
    .catch(error => {
      console.error('Failed:', error.message);
      return { user: null, posts: [] };
    });
}
```''',
        "output": r'''<think>
I need to trace the promise chain carefully. There is a bug here -- the user object is lost by the time posts are returned. Let me explain the flow and point that out.
</think>

This function fetches a user by ID and then fetches their posts, returning both. However, it has a bug -- let me walk through it.

**Step-by-step flow (happy path):**

1. `fetch()` makes an HTTP request to `/api/users/{userId}` and returns a Promise.

2. First `.then`: Checks if the response was successful. If not (4xx, 5xx), throws an error. If yes, calls `response.json()` which returns another Promise (parsing the body is async).

3. Second `.then`: Receives the parsed user object. Makes a second fetch for that user's posts. Returns the fetch Promise, which the chain waits on.

4. Third `.then`: Parses the posts response body as JSON.

5. Fourth `.then`: Returns the final object -- but here is the bug: it returns `{ user: null, posts }`. The `user` variable from step 3 is not accessible here because each `.then` only receives the return value of the previous `.then`. The user object was consumed two steps back and is gone.

**Error handling flow:**

The single `.catch` at the end handles errors from ANY step in the chain. If the first fetch fails, the network is down, JSON parsing fails, or any `.then` throws -- execution jumps straight to `.catch`. It logs the error and returns a fallback object, which means the Promise returned by `fetchUserData` will always resolve (never reject).

**To fix the bug**, you could either nest the second fetch inside the first `.then` to keep `user` in scope, or use `async/await` where both variables are naturally accessible.'''
    },
    {
        "instruction": r'''Walk me through this JavaScript prototype chain:

```javascript
function Animal(name) {
  this.name = name;
}
Animal.prototype.speak = function() {
  return `${this.name} makes a sound`;
};

function Dog(name, breed) {
  Animal.call(this, name);
  this.breed = breed;
}
Dog.prototype = Object.create(Animal.prototype);
Dog.prototype.constructor = Dog;
Dog.prototype.speak = function() {
  return `${this.name} barks`;
};
```''',
        "output": r'''This is pre-ES6 prototypal inheritance in JavaScript -- setting up `Dog` as a subclass of `Animal`.

**Constructor functions:**

`Animal(name)` and `Dog(name, breed)` are constructor functions. When called with `new`, they initialize properties on the newly created object (`this`).

**`Animal.call(this, name)` in Dog's constructor:** This is the equivalent of `super(name)` in class syntax. It calls `Animal` as a regular function but sets `this` to the Dog instance being created, so `this.name = name` runs in the Dog's context.

**Setting up the prototype chain -- the three critical lines:**

1. `Dog.prototype = Object.create(Animal.prototype)` -- Creates a new object whose `__proto__` is `Animal.prototype` and assigns it as Dog's prototype. This means Dog instances can access methods defined on `Animal.prototype` through the chain.

2. `Dog.prototype.constructor = Dog` -- Fixes the constructor reference. `Object.create` gave us a fresh object, so `constructor` would point to `Animal` without this fix. Some code relies on `instance.constructor` being correct.

3. `Dog.prototype.speak = ...` -- Overrides the inherited `speak` method. When you call `speak()` on a Dog, JavaScript finds it on `Dog.prototype` and stops looking -- it never reaches `Animal.prototype.speak`.

**Lookup chain for a Dog instance `d`:**
`d` -> `Dog.prototype` (has `speak`, `constructor`) -> `Animal.prototype` (has the original `speak`) -> `Object.prototype` -> null

**Why `Object.create` instead of `new Animal()`?** Using `Dog.prototype = new Animal()` would call Animal's constructor, which requires a `name` argument and would add an unwanted `name` property to the prototype itself.'''
    },
    {
        "instruction": r'''What is happening in this event loop example?

```javascript
console.log('1');

setTimeout(() => console.log('2'), 0);

Promise.resolve()
  .then(() => console.log('3'))
  .then(() => console.log('4'));

console.log('5');
```''',
        "output": r'''This demonstrates JavaScript's event loop task prioritization. The output order is: 1, 5, 3, 4, 2.

**Why this order?**

JavaScript has three "queues" with different priorities:

1. **Call stack (synchronous code)** -- runs first, to completion.
2. **Microtask queue** -- Promise callbacks, queueMicrotask, MutationObserver.
3. **Macrotask queue** -- setTimeout, setInterval, I/O, UI rendering.

**Execution trace:**

- `console.log('1')` -- synchronous, runs immediately. Output: **1**

- `setTimeout(..., 0)` -- schedules the callback in the macrotask queue. The 0ms delay does NOT mean "run immediately" -- it means "run after the current synchronous code and all microtasks."

- `Promise.resolve().then(...)` -- The promise is already resolved, so the `.then` callback is queued as a microtask. The second `.then` will be queued after the first microtask runs.

- `console.log('5')` -- synchronous, runs immediately. Output: **5**

- Call stack is now empty. The event loop checks the microtask queue first.

- First microtask runs: `console.log('3')`. Output: **3**. This `.then` resolves, queuing the next `.then` as another microtask.

- Second microtask runs: `console.log('4')`. Output: **4**.

- Microtask queue is empty. Now the event loop processes the macrotask queue.

- setTimeout callback runs: `console.log('2')`. Output: **2**.

**The key takeaway:** Microtasks (Promises) always run before macrotasks (setTimeout), even with a 0ms timeout. This is why Promise-based code feels "faster" than setTimeout-based code.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a JavaScript debounce implementation. I should cover how it uses closures and timer management.
</think>

Explain this debounce function:

```javascript
function debounce(func, wait, immediate = false) {
  let timeout;

  return function executedFunction(...args) {
    const context = this;
    const callNow = immediate && !timeout;

    clearTimeout(timeout);

    timeout = setTimeout(() => {
      timeout = null;
      if (!immediate) func.apply(context, args);
    }, wait);

    if (callNow) func.apply(context, args);
  };
}
```''',
        "output": r'''<think>
This is a debounce function with a leading-edge option. I should explain the timer management, the closure, and the immediate mode.
</think>

This creates a debounced version of a function -- one that waits until calls stop coming in before actually executing. Useful for things like search-as-you-type or window resize handlers.

**Closure state:** The `timeout` variable persists across calls via closure. It holds the ID of the pending setTimeout, allowing it to be canceled and rescheduled.

**Normal mode (immediate = false):**

Each call to the debounced function clears any existing timer and starts a new one. So if you call it 10 times in rapid succession, only the last call matters -- the function fires `wait` milliseconds after the last call. This is "trailing edge" debounce.

**Immediate mode (immediate = true):**

The function fires on the first call (the "leading edge") and then ignores subsequent calls until the wait period expires. `callNow` is true only when `immediate` is set AND there is no existing timer. After firing, the timeout is set but the callback only clears the timer (does not call func again).

**Why `const context = this`?** This captures the calling context so `func.apply(context, args)` preserves the correct `this` binding. Without this, the function called inside `setTimeout` would lose its `this` context (it would default to `undefined` in strict mode or `window` in sloppy mode).

**Why `timeout = null` inside setTimeout?** This resets the state so the next call can fire again in immediate mode. Without it, `callNow` would never be true after the first invocation.

**A subtle issue:** In the non-immediate path, `args` from the last call are captured correctly because `clearTimeout` discards the previous closure over older args.'''
    },
]
