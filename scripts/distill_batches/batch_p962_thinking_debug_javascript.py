PAIRS = [
    ("thinking/debugging", r'''My JavaScript class method loses its `this` binding when passed as a callback:

```javascript
class UserService {
    constructor() {
        this.users = ['Alice', 'Bob', 'Charlie'];
        this.prefix = 'User: ';
    }

    getFormattedUsers() {
        return this.users.map(this.formatUser);
    }

    formatUser(name) {
        return this.prefix + name;
    }
}

const service = new UserService();
console.log(service.getFormattedUsers());
```

Error:
```
TypeError: Cannot read properties of undefined (reading 'prefix')
    at formatUser (user-service.js:11:21)
    at Array.map (<anonymous>)
```

Why is `this` undefined inside formatUser?''', r'''<think>
This is the classic JavaScript `this` binding issue. When you pass `this.formatUser` to `Array.map()`, you are passing just the function reference, not the object context. In JavaScript, `this` is determined by HOW a function is called, not WHERE it is defined.

When `map()` calls `formatUser`, it calls it as a plain function (not as a method on an object), so `this` is `undefined` (in strict mode) or the global object (in sloppy mode). Since class bodies are always in strict mode, `this` is `undefined`.

Solutions:
1. Arrow function in the callback
2. .bind(this)
3. Arrow function class field
4. Pass thisArg to map
</think>

In JavaScript, `this` is determined by how a function is called, not where it is defined. When you write `this.users.map(this.formatUser)`, you extract the `formatUser` function reference and pass it to `map()`. When `map()` later calls it, it calls it as a plain function -- not as a method on `service`. In strict mode (which class bodies always use), `this` becomes `undefined`.

**The call chain:**
```
this.users.map(this.formatUser)
  -> extracts formatUser function (loses 'this' context)
  -> map calls formatUser("Alice") -- no 'this' binding
  -> formatUser: this is undefined
  -> this.prefix throws TypeError
```

**Fix 1: Arrow function wrapper (most common)**

```javascript
getFormattedUsers() {
    return this.users.map(name => this.formatUser(name));
}
```

Arrow functions do not have their own `this` -- they capture `this` from the enclosing scope (the `getFormattedUsers` method, where `this` is the service instance).

**Fix 2: .bind(this)**

```javascript
getFormattedUsers() {
    return this.users.map(this.formatUser.bind(this));
}
```

`.bind(this)` creates a new function with `this` permanently bound to the current object.

**Fix 3: Arrow function class field (best for callbacks)**

```javascript
class UserService {
    constructor() {
        this.users = ['Alice', 'Bob', 'Charlie'];
        this.prefix = 'User: ';
    }

    getFormattedUsers() {
        return this.users.map(this.formatUser);
    }

    // Arrow function as class field -- 'this' is always bound to the instance
    formatUser = (name) => {
        return this.prefix + name;
    }
}
```

Class field arrow functions are created per-instance and automatically bind `this`. This is the cleanest solution when a method is frequently used as a callback.

**Fix 4: Use map's thisArg parameter**

```javascript
getFormattedUsers() {
    return this.users.map(this.formatUser, this);  // second arg is thisArg
}
```

`Array.map()`, `Array.forEach()`, `Array.filter()`, etc. accept an optional `thisArg` as the second parameter.

**Fix 5: Bind in constructor**

```javascript
constructor() {
    this.users = ['Alice', 'Bob', 'Charlie'];
    this.prefix = 'User: ';
    this.formatUser = this.formatUser.bind(this);
}
```

This is the traditional React class component pattern.

**Understanding `this` in different contexts:**

```javascript
const obj = { name: 'test', greet() { return this.name; } };

obj.greet()              // 'test' -- method call, this = obj
const fn = obj.greet;
fn()                     // undefined -- plain call, this = undefined (strict)
setTimeout(obj.greet, 0) // undefined -- callback, this = undefined (strict)
btn.addEventListener('click', obj.greet) // this = the button element
```

**Prevention tips:**
- Use arrow functions for methods that will be passed as callbacks
- In React class components, bind methods in the constructor or use arrow class fields
- Use ESLint rule `no-invalid-this` to catch accidental `this` misuse
- Prefer arrow functions in `map`, `filter`, `forEach`, `setTimeout` callbacks
- When debugging, add `console.log('this is:', this)` at the start of the method'''),

    ("thinking/debugging", r'''My JavaScript loop creates closures that all reference the same variable:

```javascript
function createButtons() {
    const buttons = [];
    for (var i = 0; i < 5; i++) {
        buttons.push({
            label: `Button ${i}`,
            onClick: function() {
                console.log(`Clicked button ${i}`);
            }
        });
    }
    return buttons;
}

const buttons = createButtons();
buttons[0].onClick(); // Expected: "Clicked button 0"
buttons[1].onClick(); // Expected: "Clicked button 1"
buttons[2].onClick(); // Expected: "Clicked button 2"
```

Output:
```
Clicked button 5
Clicked button 5
Clicked button 5
```

All buttons print 5 instead of their index. Why?''', r'''<think>
This is the classic closure-in-loop problem with `var`.

`var` has function scope (not block scope). There is only ONE variable `i` in the entire function. The closures (onClick functions) all capture a reference to the same `i` variable. By the time the buttons are clicked, the loop has finished and `i` is 5.

The fix: use `let` (which has block scope), or use an IIFE to create a new scope per iteration.
</think>

This is the classic "closure over a loop variable" problem. The root cause is that `var` has function scope, not block scope. There is only ONE `i` variable shared by all 5 closures. By the time any onClick is called, the loop has completed and `i` is 5.

**How the loop executes:**

```
Iteration 0: creates closure, closure captures reference to i (not value 0)
Iteration 1: creates closure, closure captures reference to same i
Iteration 2: creates closure, closure captures reference to same i
...
Loop ends: i = 5
All closures read i -> all see 5
```

**Fix 1: Use `let` instead of `var` (modern JS, best solution)**

```javascript
function createButtons() {
    const buttons = [];
    for (let i = 0; i < 5; i++) {  // let creates a new i per iteration
        buttons.push({
            label: `Button ${i}`,
            onClick: function() {
                console.log(`Clicked button ${i}`);
            }
        });
    }
    return buttons;
}
```

`let` has block scope. Each loop iteration gets its own copy of `i`, so each closure captures a different variable.

**Fix 2: IIFE (Immediately Invoked Function Expression)**

For pre-ES6 environments:

```javascript
for (var i = 0; i < 5; i++) {
    (function(index) {
        buttons.push({
            label: `Button ${index}`,
            onClick: function() {
                console.log(`Clicked button ${index}`);
            }
        });
    })(i);  // pass current i as argument, creating a new scope
}
```

**Fix 3: Use forEach with array**

```javascript
[0, 1, 2, 3, 4].forEach(function(i) {
    buttons.push({
        label: `Button ${i}`,
        onClick: function() {
            console.log(`Clicked button ${i}`);
        }
    });
});
```

Each callback to `forEach` creates a new scope with its own `i`.

**Fix 4: Use bind to capture the value**

```javascript
for (var i = 0; i < 5; i++) {
    buttons.push({
        label: `Button ${i}`,
        onClick: function(index) {
            console.log(`Clicked button ${index}`);
        }.bind(null, i)  // bind captures current value of i
    });
}
```

**Why `let` works but `var` does not:**

```javascript
// var: ONE variable for the entire function
for (var i = 0; i < 3; i++) { ... }
// Desugars to:
var i;
i = 0; ... i = 1; ... i = 2; ...

// let: NEW variable per iteration
for (let i = 0; i < 3; i++) { ... }
// Desugars to (conceptually):
{ let i = 0; ... } { let i = 1; ... } { let i = 2; ... }
```

**This same bug occurs in setTimeout:**

```javascript
// BUG:
for (var i = 0; i < 5; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// Prints: 5 5 5 5 5

// FIX:
for (let i = 0; i < 5; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// Prints: 0 1 2 3 4
```

**Prevention tips:**
- Always use `let` or `const` -- never use `var`
- Enable ESLint rule `no-var` to enforce this
- Use `const` by default, `let` only when reassignment is needed
- Be aware of closures in any asynchronous code (setTimeout, event handlers, promises)
- When in doubt, extract the loop body into a separate function that receives the value as a parameter'''),

    ("thinking/debugging", r'''My Promise.all rejects immediately when one promise fails, and I lose the results of promises that did succeed:

```javascript
async function fetchAllData() {
    const urls = [
        'https://api.example.com/users',     // 200 OK
        'https://api.example.com/orders',     // 500 Error
        'https://api.example.com/products',   // 200 OK
    ];

    try {
        const results = await Promise.all(
            urls.map(url => fetch(url).then(r => r.json()))
        );
        return results;
    } catch (error) {
        console.error('Failed:', error.message);
        return [];  // lose ALL results because of ONE failure
    }
}
```

The users and products requests succeed, but because orders fails, I get nothing. How do I get partial results?''', r'''<think>
Promise.all has "fail-fast" behavior: if any promise rejects, the entire Promise.all rejects immediately. The results of successful promises are discarded.

The fix is to use Promise.allSettled (ES2020) which waits for ALL promises to complete regardless of success or failure, or to catch errors per-promise.
</think>

`Promise.all()` has fail-fast behavior: the moment any single promise rejects, the entire `Promise.all()` rejects and all other results are discarded, even if they succeeded.

**Fix 1: Use Promise.allSettled() (best solution, ES2020+)**

```javascript
async function fetchAllData() {
    const urls = [
        'https://api.example.com/users',
        'https://api.example.com/orders',
        'https://api.example.com/products',
    ];

    const results = await Promise.allSettled(
        urls.map(url => fetch(url).then(r => r.json()))
    );

    // results is an array of { status, value } or { status, reason }
    const successes = results
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value);

    const failures = results
        .filter(r => r.status === 'rejected')
        .map(r => r.reason);

    if (failures.length > 0) {
        console.warn(`${failures.length} requests failed:`, failures);
    }

    return { successes, failures };
}
```

`Promise.allSettled()` waits for ALL promises to complete (fulfilled or rejected) and returns an array describing each result:

```javascript
[
    { status: 'fulfilled', value: { users: [...] } },
    { status: 'rejected', reason: Error('500 Internal Server Error') },
    { status: 'fulfilled', value: { products: [...] } },
]
```

**Fix 2: Catch errors per-promise (works in older environments)**

```javascript
async function fetchAllData() {
    const urls = [
        'https://api.example.com/users',
        'https://api.example.com/orders',
        'https://api.example.com/products',
    ];

    const results = await Promise.all(
        urls.map(url =>
            fetch(url)
                .then(r => r.json())
                .then(data => ({ success: true, data, url }))
                .catch(error => ({ success: false, error: error.message, url }))
        )
    );

    // Now Promise.all never rejects because each inner promise always resolves
    const successes = results.filter(r => r.success).map(r => r.data);
    const failures = results.filter(r => !r.success);

    return { successes, failures };
}
```

By adding `.catch()` to each individual promise, they always resolve (never reject). `Promise.all()` then always succeeds.

**Fix 3: Promise.all with timeout and retry**

```javascript
async function fetchWithRetry(url, retries = 2) {
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            if (attempt === retries) throw error;
            await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        }
    }
}

async function fetchAllData() {
    const urls = ['...'];
    const results = await Promise.allSettled(
        urls.map(url => fetchWithRetry(url))
    );
    return results;
}
```

**Comparison of Promise combinators:**

```
Promise.all()        - resolves when ALL succeed, rejects on FIRST failure
Promise.allSettled() - resolves when ALL complete (success or failure)
Promise.race()       - resolves/rejects with the FIRST to complete
Promise.any()        - resolves with FIRST success, rejects only if ALL fail
```

**Prevention tips:**
- Use `Promise.allSettled()` by default when you want all results
- Use `Promise.all()` only when ALL results are required and one failure should abort everything
- Always add per-promise error handling for user-facing operations
- Use `Promise.any()` for redundant requests (e.g., fallback servers)
- Add timeouts to prevent promises from hanging indefinitely'''),

    ("thinking/debugging", r'''My Node.js server becomes unresponsive when processing a large JSON file:

```javascript
const express = require('express');
const app = express();

app.get('/process', (req, res) => {
    const data = require('./large-dataset.json'); // 500MB file
    const result = processData(data);
    res.json(result);
});

function processData(data) {
    // CPU-intensive: sort and filter 10 million records
    return data
        .filter(item => item.score > 50)
        .sort((a, b) => b.score - a.score)
        .slice(0, 100);
}

app.listen(3000);
```

When one request hits /process, ALL other requests hang for 30+ seconds. Health checks time out and the load balancer marks the server as down.''', r'''<think>
Node.js runs on a single-threaded event loop. CPU-intensive operations block the event loop, preventing it from processing any other requests, I/O callbacks, timers, etc.

Loading a 500MB JSON file with `require()` is also blocking and takes significant memory.

Solutions:
1. Use worker_threads for CPU-bound work
2. Use streaming JSON parser
3. Pre-process the data at startup
4. Use a separate microservice for heavy processing
</think>

Node.js uses a single-threaded event loop. When `processData()` runs CPU-intensive sorting and filtering on 10 million records, it blocks the event loop for the entire duration. No other requests can be handled, no I/O callbacks fire, no timers execute. The server is completely frozen.

Additionally, `require('./large-dataset.json')` is synchronous -- it blocks while reading and parsing 500MB of JSON.

**Fix 1: Use Worker Threads for CPU-bound work**

```javascript
const express = require('express');
const { Worker } = require('worker_threads');
const app = express();

app.get('/process', (req, res) => {
    const worker = new Worker('./process-worker.js');

    worker.on('message', (result) => {
        res.json(result);
    });

    worker.on('error', (error) => {
        res.status(500).json({ error: error.message });
    });
});

app.listen(3000);
```

```javascript
// process-worker.js
const { parentPort } = require('worker_threads');
const fs = require('fs');

const raw = fs.readFileSync('./large-dataset.json', 'utf8');
const data = JSON.parse(raw);

const result = data
    .filter(item => item.score > 50)
    .sort((a, b) => b.score - a.score)
    .slice(0, 100);

parentPort.postMessage(result);
```

Worker threads run in a separate thread with their own V8 instance, so they do not block the main event loop.

**Fix 2: Use a worker pool (better for production)**

```javascript
const { StaticPool } = require('node-worker-threads-pool');

const pool = new StaticPool({
    size: 4,  // 4 worker threads
    task: './process-worker.js',
});

app.get('/process', async (req, res) => {
    try {
        const result = await pool.exec();
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});
```

**Fix 3: Stream-process the JSON file**

```javascript
const { pipeline } = require('stream/promises');
const { parser } = require('stream-json');
const { streamArray } = require('stream-json/streamers/StreamArray');
const fs = require('fs');

async function processDataStreaming() {
    const topResults = [];

    const fileStream = fs.createReadStream('./large-dataset.json');
    const jsonStream = fileStream.pipe(parser()).pipe(streamArray());

    for await (const { value: item } of jsonStream) {
        if (item.score > 50) {
            topResults.push(item);
            // Keep only top 100 to bound memory
            if (topResults.length > 200) {
                topResults.sort((a, b) => b.score - a.score);
                topResults.length = 100;
            }
        }
    }

    topResults.sort((a, b) => b.score - a.score);
    return topResults.slice(0, 100);
}
```

**Fix 4: Pre-load and index at startup**

```javascript
let cachedData = null;

async function loadData() {
    const raw = await fs.promises.readFile('./large-dataset.json', 'utf8');
    cachedData = JSON.parse(raw);
    // Pre-sort once at startup
    cachedData.sort((a, b) => b.score - a.score);
    console.log(`Loaded ${cachedData.length} records`);
}

loadData().then(() => {
    app.get('/process', (req, res) => {
        // Fast: data is already sorted, just filter
        const result = cachedData.filter(item => item.score > 50).slice(0, 100);
        res.json(result);
    });

    app.listen(3000);
});
```

**Prevention tips:**
- Never run CPU-intensive operations on the main event loop
- Use `worker_threads` for CPU-bound tasks, `child_process` for external commands
- Stream large files instead of loading them entirely into memory
- Use `--max-old-space-size=4096` to increase V8 heap for large datasets
- Monitor event loop lag with `perf_hooks.monitorEventLoopDelay()` or `clinic.js`
- Set request timeouts to prevent slow requests from accumulating'''),

    ("thinking/debugging", r'''I'm getting unexpected behavior with JavaScript prototype chain:

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

Dog.prototype = Animal.prototype;  // Wrong way to set up inheritance!

Dog.prototype.speak = function() {
    return `${this.name} barks`;
};

const cat = new Animal('Whiskers');
console.log(cat.speak());  // Expected: "Whiskers makes a sound"
                            // Got: "Whiskers barks" !!!
```

Overriding speak on Dog also changed Animal's speak. Why?''', r'''<think>
The issue is `Dog.prototype = Animal.prototype`. This does not create a new object that inherits from Animal.prototype. It makes Dog.prototype point to the SAME object as Animal.prototype. They are the same reference.

So when you modify Dog.prototype.speak, you are modifying Animal.prototype.speak because they are the same object.

The correct way is to create a new object that has Animal.prototype in its prototype chain:
`Dog.prototype = Object.create(Animal.prototype)`

Or use ES6 classes.
</think>

The line `Dog.prototype = Animal.prototype` makes both prototypes point to the **exact same object**. They do not get independent copies -- they share one prototype object. When you modify `Dog.prototype.speak`, you are directly mutating `Animal.prototype.speak` because they are the same reference.

```javascript
Dog.prototype === Animal.prototype  // true! Same object in memory!
```

**The correct way to set up prototypal inheritance:**

```javascript
function Animal(name) {
    this.name = name;
}
Animal.prototype.speak = function() {
    return `${this.name} makes a sound`;
};

function Dog(name, breed) {
    Animal.call(this, name);  // call parent constructor
    this.breed = breed;
}

// Create a NEW object whose prototype is Animal.prototype
Dog.prototype = Object.create(Animal.prototype);
Dog.prototype.constructor = Dog;  // fix the constructor reference

// Now this only affects Dog, not Animal
Dog.prototype.speak = function() {
    return `${this.name} barks`;
};

const cat = new Animal('Whiskers');
const dog = new Dog('Rex', 'Lab');

console.log(cat.speak());  // "Whiskers makes a sound" (correct!)
console.log(dog.speak());  // "Rex barks" (correct!)
console.log(dog instanceof Animal);  // true
console.log(dog instanceof Dog);     // true
```

**How `Object.create()` works:**

```javascript
// Object.create(proto) creates a new empty object
// whose [[Prototype]] is set to proto

Dog.prototype = Object.create(Animal.prototype);
// Creates: Dog.prototype -> Animal.prototype -> Object.prototype

Dog.prototype === Animal.prototype  // false! Different objects!
Object.getPrototypeOf(Dog.prototype) === Animal.prototype  // true!
```

**The modern approach: ES6 classes**

```javascript
class Animal {
    constructor(name) {
        this.name = name;
    }

    speak() {
        return `${this.name} makes a sound`;
    }
}

class Dog extends Animal {
    constructor(name, breed) {
        super(name);
        this.breed = breed;
    }

    speak() {
        return `${this.name} barks`;
    }
}
```

ES6 classes handle the prototype chain correctly behind the scenes. `extends` does the equivalent of `Object.create()` plus sets up the constructor chain.

**Common prototype mistakes:**

```javascript
// WRONG: shared prototype (your bug)
Dog.prototype = Animal.prototype;

// WRONG: creates an instance (calls constructor with no args)
Dog.prototype = new Animal();

// RIGHT: creates a clean prototype link
Dog.prototype = Object.create(Animal.prototype);
Dog.prototype.constructor = Dog;

// RIGHT (ES5 alternative):
Object.setPrototypeOf(Dog.prototype, Animal.prototype);
```

**Prevention tips:**
- Use ES6 classes for inheritance -- they handle prototypes correctly
- Never assign one constructor's prototype directly to another's
- Always reset `constructor` after setting up the prototype chain
- Use `Object.create()` when you need manual prototype setup
- Understand that JavaScript has prototypal inheritance, not classical inheritance -- objects delegate to other objects, they do not copy from classes'''),
]
