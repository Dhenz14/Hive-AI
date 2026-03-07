"""
Anti-pattern training pairs - JavaScript anti-patterns
Topics: callback hell, == vs ===, var hoisting, promise anti-patterns, memory leaks
"""

pairs = [
    {
        "instruction": r'''This code works but my team says it's hard to follow. What's wrong with it?

```javascript
function processOrder(orderId) {
    getOrder(orderId, function(err, order) {
        if (err) { console.log(err); return; }
        validateStock(order.items, function(err, stockOk) {
            if (err) { console.log(err); return; }
            if (stockOk) {
                chargePayment(order.total, function(err, receipt) {
                    if (err) { console.log(err); return; }
                    sendConfirmation(order.email, receipt, function(err) {
                        if (err) { console.log(err); return; }
                        updateDatabase(order.id, 'completed', function(err) {
                            if (err) { console.log(err); return; }
                            console.log('Done!');
                        });
                    });
                });
            }
        });
    });
}
```''',
        "output": r'''<think>
Classic callback hell / pyramid of doom. Each async operation is nested inside the previous one's callback. Error handling is duplicated 5 times. Adding a step means adding another nesting level. The user's team flagged it -- they know it's a problem but may not know the modern alternative. This should use async/await.
</think>

This is called "callback hell" or the "pyramid of doom." Each async step nests inside the previous one, creating an ever-growing rightward drift. The problems compound:

- **Error handling is duplicated** 5 times with identical `if (err)` checks
- **Adding a step** means adding another nesting level
- **Inserting a step in the middle** requires re-indenting everything below it
- **Error recovery** (like retrying `chargePayment`) is extremely awkward to add

**The fix -- use async/await:**

```javascript
async function processOrder(orderId) {
    const order = await getOrder(orderId);
    const stockOk = await validateStock(order.items);

    if (!stockOk) {
        throw new Error('Items out of stock');
    }

    const receipt = await chargePayment(order.total);
    await sendConfirmation(order.email, receipt);
    await updateDatabase(order.id, 'completed');

    console.log('Done!');
}

// Call with proper error handling
processOrder('order-123').catch(err => {
    console.error('Order processing failed:', err);
});
```

**What changed:**
- **Flat structure** -- reads top to bottom like synchronous code
- **One error path** -- the `.catch()` or a `try/catch` handles all errors in one place
- **Easy to modify** -- adding a step is just adding a line, no re-indenting

If your callback-based functions don't return promises, wrap them:

```javascript
const { promisify } = require('util');
const getOrderAsync = promisify(getOrder);
```'''
    },
    {
        "instruction": r'''My comparison seems to work fine. Is there a problem here?

```javascript
function checkValue(input) {
    if (input == 0) {
        return 'zero';
    }
    if (input == '') {
        return 'empty string';
    }
    if (input == null) {
        return 'null or undefined';
    }
    if (input == true) {
        return 'truthy';
    }
    return 'other';
}
```''',
        "output": r'''<think>
Using == instead of === in JavaScript. The == operator does type coercion, leading to many surprising results. For example, 0 == '' is true, '' == false is true, null == undefined is true. The user's function has overlapping conditions that produce unexpected results due to coercion. I should demonstrate the specific bugs this creates.
</think>

The `==` operator in JavaScript performs type coercion, which creates bugs that are nearly impossible to spot by reading the code.

**Bugs in your function:**

```javascript
checkValue(0)    // 'zero' -- correct
checkValue('')   // 'zero' -- WRONG! '' == 0 is true due to coercion
checkValue(false) // 'zero' -- WRONG! false == 0 is true
checkValue(null)  // 'null or undefined' -- correct, but by accident
checkValue(1)    // 'truthy' -- WRONG! 1 == true is true
checkValue(2)    // 'other' -- but 2 is truthy too!
```

The empty string never reaches the `== ''` check because `'' == 0` matches first. The `== true` check only matches `1`, not other truthy values.

**The fix -- always use `===` (strict equality):**

```javascript
function checkValue(input) {
    if (input === 0) {
        return 'zero';
    }
    if (input === '') {
        return 'empty string';
    }
    if (input === null || input === undefined) {
        return 'null or undefined';
    }
    if (input === true) {
        return 'boolean true';
    }
    return 'other';
}
```

With `===`, no type coercion happens. `'' === 0` is `false`. `false === 0` is `false`. Each condition matches exactly what you expect.

**The one exception:** `x == null` is the only commonly accepted use of `==` because it checks both `null` and `undefined` in one expression. But even then, being explicit with `x === null || x === undefined` is clearer. Most linters (ESLint's `eqeqeq` rule) will flag `==` usage for good reason.'''
    },
    {
        "instruction": r'''I'm using var in my loops and functions. My code works, is there any reason to switch to let/const?

```javascript
for (var i = 0; i < 5; i++) {
    setTimeout(function() {
        console.log('Button ' + i);
    }, 1000);
}

function example() {
    console.log(x); // undefined, no error
    var x = 10;
    if (true) {
        var y = 20;
    }
    console.log(y); // 20 -- y leaks out of if block
}
```''',
        "output": r'''<think>
var hoisting anti-pattern. var is function-scoped not block-scoped, so it leaks out of for loops and if blocks. The setTimeout loop will print "Button 5" five times because all closures share the same i. The user says "code works" but hasn't tested the setTimeout case carefully. Need to show why let/const fix these issues.
</think>

Your `setTimeout` loop has a bug you may not have noticed. It prints "Button 5" five times, not "Button 0" through "Button 4".

**Why:** `var` is function-scoped, not block-scoped. There is only ONE `i` variable shared by all five closures. By the time the timeouts fire, the loop has finished and `i` is `5`.

**Problem 1 -- loop closure bug:**

```javascript
// With var: prints "Button 5" five times
for (var i = 0; i < 5; i++) {
    setTimeout(function() { console.log('Button ' + i); }, 1000);
}

// With let: prints "Button 0" through "Button 4"
for (let i = 0; i < 5; i++) {
    setTimeout(function() { console.log('Button ' + i); }, 1000);
}
```

`let` creates a new `i` for each loop iteration, so each closure captures its own copy.

**Problem 2 -- hoisting creates confusing code:**

```javascript
console.log(x); // undefined (var x is hoisted, but not its value)
var x = 10;

console.log(z); // ReferenceError (let/const are not hoisted this way)
let z = 10;
```

With `var`, you can use variables before they are declared. This hides bugs -- you get `undefined` instead of a clear error.

**Problem 3 -- block scope leaking:**

```javascript
if (true) { var y = 20; }
console.log(y); // 20 -- leaked out of if block

if (true) { let z = 20; }
console.log(z); // ReferenceError -- properly scoped
```

**Modern rule:** Use `const` by default. Use `let` when you need to reassign. Never use `var`. This is enforced by ESLint's `no-var` rule and is standard practice in all modern JavaScript.'''
    },
    {
        "instruction": r'''I wrapped my async calls in promises. Does this look right?

```javascript
function getUser(id) {
    return new Promise((resolve, reject) => {
        fetch('/api/users/' + id)
            .then(response => response.json())
            .then(data => resolve(data))
            .catch(err => reject(err));
    });
}

async function loadDashboard() {
    const user = await getUser(1);
    const orders = await getOrders(user.id);
    const recommendations = await getRecommendations(user.id);
    return { user, orders, recommendations };
}
```''',
        "output": r'''<think>
Two anti-patterns here. First: the "explicit promise construction" anti-pattern -- wrapping fetch (which already returns a promise) in a new Promise is pointless. Second: sequential awaits for independent operations -- orders and recommendations don't depend on each other but are loaded one after another, doubling the wait time. Should use Promise.all for concurrent requests.
</think>

There are two anti-patterns here.

**Anti-pattern 1: Unnecessary promise wrapping.** `fetch()` already returns a promise. Wrapping it in `new Promise` adds complexity and can swallow errors:

```javascript
// BAD -- redundant promise wrapper
function getUser(id) {
    return new Promise((resolve, reject) => {
        fetch('/api/users/' + id)
            .then(response => response.json())
            .then(data => resolve(data))
            .catch(err => reject(err));
    });
}

// GOOD -- just return the promise chain
function getUser(id) {
    return fetch('/api/users/' + id)
        .then(response => {
            if (!response.ok) throw new Error('User not found');
            return response.json();
        });
}
```

Only use `new Promise()` when wrapping callback-based APIs (like `setTimeout` or Node's `fs.readFile`). If the function already returns a promise, just return it.

**Anti-pattern 2: Sequential awaits for independent operations.** `orders` and `recommendations` do not depend on each other, but you wait for orders to finish before starting recommendations:

```javascript
// BAD -- sequential (2 seconds if each takes 1 second)
const orders = await getOrders(user.id);
const recommendations = await getRecommendations(user.id);

// GOOD -- concurrent (1 second total)
const [orders, recommendations] = await Promise.all([
    getOrders(user.id),
    getRecommendations(user.id),
]);
```

**Fixed version:**

```javascript
async function loadDashboard() {
    const user = await getUser(1);

    // These two are independent -- run concurrently
    const [orders, recommendations] = await Promise.all([
        getOrders(user.id),
        getRecommendations(user.id),
    ]);

    return { user, orders, recommendations };
}
```

This is both simpler and faster.'''
    },
    {
        "instruction": r'''I have a single-page app that creates event listeners. Users report it gets slow after navigating between pages a few times:

```javascript
class PageController {
    init(containerId) {
        this.container = document.getElementById(containerId);
        this.render();

        window.addEventListener('resize', this.handleResize);
        document.addEventListener('keydown', this.handleKeydown);
        this.interval = setInterval(() => this.pollUpdates(), 5000);
    }

    handleResize() { /* update layout */ }
    handleKeydown(e) { /* keyboard shortcuts */ }
    pollUpdates() { /* fetch new data */ }

    render() {
        this.container.innerHTML = '<div>Page content...</div>';
    }
}

// On navigation:
function navigateTo(page) {
    const controller = new PageController();
    controller.init('app');
}
```''',
        "output": r'''<think>
Memory leak from event listeners and intervals not being cleaned up. Each navigation creates new resize/keydown listeners and a new setInterval, but never removes the old ones. After 10 navigations, there are 10 resize handlers, 10 keydown handlers, and 10 intervals all running simultaneously. Classic SPA memory leak. Need a destroy/cleanup method.
</think>

Your app has a memory leak. Every call to `navigateTo()` adds new event listeners and a new interval, but the old ones are never removed. After navigating 10 times, you have:

- 10 resize handlers running on every window resize
- 10 keydown handlers processing every keystroke
- 10 intervals polling your server every 5 seconds

This is why it slows down over time -- the work multiplies with each navigation.

**The fix -- add a cleanup method and call it before re-initializing:**

```javascript
class PageController {
    init(containerId) {
        this.container = document.getElementById(containerId);

        // Bind handlers so we can remove them later
        this._onResize = this.handleResize.bind(this);
        this._onKeydown = this.handleKeydown.bind(this);

        window.addEventListener('resize', this._onResize);
        document.addEventListener('keydown', this._onKeydown);
        this.interval = setInterval(() => this.pollUpdates(), 5000);

        this.render();
    }

    destroy() {
        window.removeEventListener('resize', this._onResize);
        document.removeEventListener('keydown', this._onKeydown);
        clearInterval(this.interval);
        this.container.innerHTML = '';
    }

    handleResize() { /* update layout */ }
    handleKeydown(e) { /* keyboard shortcuts */ }
    pollUpdates() { /* fetch new data */ }
    render() {
        this.container.innerHTML = '<div>Page content...</div>';
    }
}

let currentController = null;

function navigateTo(page) {
    // Clean up the previous page
    if (currentController) {
        currentController.destroy();
    }
    currentController = new PageController();
    currentController.init('app');
}
```

**Key points:**
- You must store bound references (`this._onResize`) because `removeEventListener` requires the exact same function reference that was passed to `addEventListener`
- Always clear intervals and timeouts
- This is why frameworks like React have cleanup returns in `useEffect` -- they solve this problem automatically'''
    },
]
