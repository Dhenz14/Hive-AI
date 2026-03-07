"""
Proactive alternatives training pairs - JavaScript patterns and idioms
"""

pairs = [
    {
        "instruction": r'''I'm fetching data from an API and then processing it. I'm using callbacks to handle the async flow:

```javascript
function getData(url, callback) {
    fetch(url).then(response => response.json()).then(data => {
        callback(null, data);
    }).catch(err => {
        callback(err, null);
    });
}

getData('/api/users', function(err, users) {
    if (err) { console.log(err); return; }
    getData('/api/users/' + users[0].id + '/posts', function(err, posts) {
        if (err) { console.log(err); return; }
        console.log(posts);
    });
});
```

This works but I need to chain more API calls. Any tips for keeping it manageable?''',
        "output": r'''<think>
Classic callback nesting problem. Since they are already using fetch (which returns Promises), wrapping it in callbacks is adding unnecessary complexity. async/await would flatten the chain completely and make error handling cleaner with try/catch. They are clearly feeling the pain already since they asked about manageability.
</think>

You are already using `fetch`, which returns Promises natively -- so you can skip the callback wrapper entirely and use async/await. This flattens the chain no matter how many calls you add:

```javascript
async function getUserPosts(baseUrl) {
    try {
        const usersRes = await fetch(baseUrl + '/api/users');
        const users = await usersRes.json();

        const postsRes = await fetch(baseUrl + '/api/users/' + users[0].id + '/posts');
        const posts = await postsRes.json();

        // Easy to add more calls -- they just read top to bottom
        const commentsRes = await fetch(baseUrl + '/api/posts/' + posts[0].id + '/comments');
        const comments = await commentsRes.json();

        return { users, posts, comments };
    } catch (err) {
        console.error('API call failed:', err);
        throw err;
    }
}

// Usage
getUserPosts('https://example.com')
    .then(data => console.log(data))
    .catch(err => console.error(err));
```

If some calls are independent and can run in parallel:

```javascript
async function getDashboardData() {
    // These three calls run simultaneously
    const [users, stats, alerts] = await Promise.all([
        fetch('/api/users').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/alerts').then(r => r.json())
    ]);

    return { users, stats, alerts };
}
```

async/await works in all modern browsers and Node 8+. The code reads like synchronous code but runs asynchronously -- no nesting, no callback arguments, and try/catch handles errors for the entire chain.'''
    },
    {
        "instruction": r'''I'm building a to-do list app. I'm using plain JavaScript to manipulate the DOM directly:

```javascript
function addTodo(text) {
    var li = document.createElement('li');
    li.textContent = text;
    var btn = document.createElement('button');
    btn.textContent = 'Delete';
    btn.onclick = function() { li.remove(); };
    li.appendChild(btn);
    document.getElementById('todo-list').appendChild(li);
}
```

I need to add filtering (all/active/completed), editing, drag-to-reorder, and syncing with a backend. How should I structure this as it grows?''',
        "output": r'''<think>
Manual DOM manipulation works for simple cases but becomes spaghetti once you add state management (filtering means re-rendering based on state), editing (toggling between display and input), and syncing (keeping DOM in sync with server data). A lightweight framework like Alpine.js or a full one like Vue/React would help. Given the feature list, even something minimal like Preact or Alpine would be a huge improvement. I should suggest a lightweight option, not jump straight to React.
</think>

Your current approach works for a simple list, but the features you described -- filtering, editing, reorder, backend sync -- mean you will be manually keeping DOM state and data state in sync, which gets tangled fast.

You do not need a heavy framework. Alpine.js (15KB, no build step) gives you reactivity with a single script tag:

```html
<div x-data="todoApp()">
    <input x-model="newTodo" @keydown.enter="addTodo()">
    <button @click="addTodo()">Add</button>

    <div>
        <button @click="filter = 'all'">All</button>
        <button @click="filter = 'active'">Active</button>
        <button @click="filter = 'completed'">Completed</button>
    </div>

    <ul>
        <template x-for="todo in filteredTodos" :key="todo.id">
            <li>
                <input type="checkbox" x-model="todo.completed" @change="sync(todo)">
                <span @dblclick="startEdit(todo)" x-text="todo.text"></span>
                <button @click="removeTodo(todo)">Delete</button>
            </li>
        </template>
    </ul>
</div>
```

```javascript
function todoApp() {
    return {
        todos: [],
        newTodo: '',
        filter: 'all',

        get filteredTodos() {
            if (this.filter === 'active') return this.todos.filter(t => !t.completed);
            if (this.filter === 'completed') return this.todos.filter(t => t.completed);
            return this.todos;
        },

        async addTodo() {
            if (!this.newTodo.trim()) return;
            var todo = { id: Date.now(), text: this.newTodo, completed: false };
            this.todos.push(todo);
            this.newTodo = '';
            await fetch('/api/todos', { method: 'POST', body: JSON.stringify(todo) });
        },

        async removeTodo(todo) {
            this.todos = this.todos.filter(t => t.id !== todo.id);
            await fetch('/api/todos/' + todo.id, { method: 'DELETE' });
        },

        async sync(todo) {
            await fetch('/api/todos/' + todo.id, { method: 'PUT', body: JSON.stringify(todo) });
        }
    };
}
```

The data drives the DOM automatically -- when `this.todos` changes, the list re-renders. Filtering is a computed property instead of manually hiding/showing elements. Backend sync is just an `await fetch()` inside each method.

If the app grows further (routing, complex state), stepping up to Vue or React makes sense. For a single interactive widget, Alpine.js is the sweet spot.'''
    },
    {
        "instruction": r'''I need to remove duplicates from an array and find the intersection of two arrays. I'm using lodash:

```javascript
const _ = require('lodash');

const unique = _.uniq(myArray);
const common = _.intersection(arrayA, arrayB);
const grouped = _.groupBy(users, 'role');
```

Should I keep using lodash or are there better alternatives?''',
        "output": r'''<think>
For uniq and intersection, native JavaScript has Set which handles these cleanly. groupBy was added as Object.groupBy in ES2024. For a few operations like these, adding lodash (70KB) is overkill. But lodash still has value for deep cloning, complex object manipulation, and debounce/throttle. I should show the native equivalents and mention where lodash is still worth it.
</think>

For those specific operations, native JavaScript handles them well now -- no need for the lodash dependency:

```javascript
// _.uniq --> Set
const unique = [...new Set(myArray)];

// _.intersection --> Set + filter
const setB = new Set(arrayB);
const common = arrayA.filter(x => setB.has(x));

// _.groupBy --> Object.groupBy (ES2024, Node 21+)
const grouped = Object.groupBy(users, user => user.role);

// If you need groupBy in older environments, it is a short helper:
function groupBy(arr, key) {
    return arr.reduce((groups, item) => {
        const val = typeof key === 'function' ? key(item) : item[key];
        (groups[val] = groups[val] || []).push(item);
        return groups;
    }, {});
}
```

A few more common lodash operations that have native equivalents:

```javascript
// _.flatten --> Array.flat
[1, [2, [3]]].flat(Infinity);  // [1, 2, 3]

// _.compact --> filter(Boolean)
[0, 1, false, 2, '', 3].filter(Boolean);  // [1, 2, 3]

// _.get(obj, 'a.b.c') --> optional chaining
obj?.a?.b?.c;

// _.cloneDeep --> structuredClone (Node 17+, modern browsers)
const copy = structuredClone(original);

// _.debounce -- still worth importing individually
import { debounce } from 'lodash-es/debounce';
```

Lodash is still valuable for `debounce`, `throttle`, `merge` (deep object merge), and complex collection operations. But if you are only using `uniq`, `intersection`, and `groupBy`, dropping lodash saves about 70KB from your bundle.

If you do keep lodash, import individual functions instead of the whole library:

```javascript
// BAD -- imports everything
const _ = require('lodash');

// GOOD -- tree-shakeable
import uniq from 'lodash-es/uniq';
```'''
    },
    {
        "instruction": r'''I'm writing some JavaScript and using `var` for my variables. A colleague mentioned I should use something else but I'm not sure why. Here's my code:

```javascript
for (var i = 0; i < 5; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// Prints 5, 5, 5, 5, 5 -- not what I wanted

var config = { debug: true };
// ... 200 lines later ...
var config = loadConfig(); // accidentally redeclared, no error
```

What's the issue here?''',
        "output": r'''<think>
Classic var pitfalls: function scoping (not block scoping) causes the loop bug, and var allows redeclaration without error. let and const fix both issues. let is block-scoped so the loop works correctly, and const prevents reassignment of things that should not change. I should explain why not just what.
</think>

The issue is that `var` is function-scoped, not block-scoped. In your loop, there is only one `i` variable shared across all iterations -- by the time the timeouts fire, `i` is already 5.

`let` and `const` (introduced in ES6) fix this:

```javascript
// let is block-scoped -- each iteration gets its own i
for (let i = 0; i < 5; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// Prints 0, 1, 2, 3, 4 -- correct!

// const prevents accidental reassignment
const config = { debug: true };
// ... 200 lines later ...
const config = loadConfig(); // SyntaxError: already declared
```

The rules are simple:

```javascript
// Use const by default -- signals "this binding will not change"
const API_URL = 'https://api.example.com';
const users = [];        // The array is const, but you can still push to it
users.push('Alice');     // This is fine
// users = [];           // This would error -- cannot reassign

// Use let when you need to reassign
let count = 0;
count += 1;              // Fine

let retries = 3;
while (retries > 0) {
    retries--;
}

// Never use var -- there is no case where var is better
```

One more `var` gotcha -- hoisting:

```javascript
// var hoists the declaration but not the value
console.log(x);  // undefined (not an error!)
var x = 5;

// let/const throw a clear error
console.log(y);  // ReferenceError: cannot access 'y' before initialization
let y = 5;
```

Start with `const` everywhere. Switch to `let` only when you need reassignment. You will never need `var` in modern JavaScript.'''
    },
    {
        "instruction": r'''I'm creating objects in JavaScript using prototype-based inheritance:

```javascript
function Animal(name) {
    this.name = name;
}
Animal.prototype.speak = function() {
    return this.name + ' makes a noise';
};

function Dog(name, breed) {
    Animal.call(this, name);
    this.breed = breed;
}
Dog.prototype = Object.create(Animal.prototype);
Dog.prototype.constructor = Dog;
Dog.prototype.speak = function() {
    return this.name + ' barks';
};
```

This is getting verbose as I add more types. Is there a cleaner pattern?''',
        "output": r'''<think>
ES6 classes are syntactic sugar over prototypes but much more readable. For the user's case with multiple animal types, classes make the hierarchy clear. I could also mention composition as an alternative if the hierarchy gets deep, but since they have a clear is-a relationship (Dog is an Animal), classes are the right suggestion here.
</think>

ES6 classes do exactly the same thing under the hood but with cleaner syntax:

```javascript
class Animal {
    constructor(name) {
        this.name = name;
    }

    speak() {
        return this.name + ' makes a noise';
    }
}

class Dog extends Animal {
    constructor(name, breed) {
        super(name);
        this.breed = breed;
    }

    speak() {
        return this.name + ' barks';
    }
}

const rex = new Dog('Rex', 'German Shepherd');
console.log(rex.speak());  // "Rex barks"
```

This is the same prototypal inheritance -- `class` is syntactic sugar, not a new mechanism. But it removes all the boilerplate around `Object.create`, `prototype.constructor`, and `Function.call`.

Classes also give you some nice features:

```javascript
class Animal {
    // Private fields (Node 12+, modern browsers)
    #health = 100;

    constructor(name) {
        this.name = name;
    }

    get isAlive() {
        return this.#health > 0;
    }

    // Static methods
    static create(name) {
        return new Animal(name);
    }

    speak() {
        return this.name + ' makes a noise';
    }
}
```

If your hierarchy gets deeper than 2-3 levels, consider composition instead -- where objects have behaviors rather than inheriting them:

```javascript
// Composition approach for complex cases
const canSwim = (state) => ({
    swim: () => state.name + ' is swimming'
});

const canBark = (state) => ({
    bark: () => state.name + ' barks'
});

function createDog(name) {
    const state = { name };
    return Object.assign(
        { name },
        canBark(state),
        canSwim(state)  // Labs can swim!
    );
}

const dog = createDog('Rex');
dog.bark();  // "Rex barks"
dog.swim();  // "Rex is swimming"
```

For your current use case with clear parent-child relationships, ES6 classes are the way to go. Reach for composition when you need to mix capabilities that do not fit a strict hierarchy.'''
    },
]
