"""
Anti-pattern training pairs - TypeScript anti-patterns
Topics: any everywhere, assertion overuse, enum misuse, ignoring strictNullChecks, bad generics
"""

pairs = [
    {
        "instruction": r'''I keep getting TypeScript errors so I added `any` to make them go away:

```typescript
async function fetchUser(id: any): Promise<any> {
    const response: any = await fetch(`/api/users/${id}`);
    const data: any = await response.json();
    return data;
}

function processUsers(users: any[]) {
    return users.map((user: any) => ({
        name: user.name,
        email: user.emial,  // typo -- no error!
        age: user.age + "years",  // wrong concat -- no error!
    }));
}

const config: any = loadConfig();
startServer(config.potr);  // typo -- no error!
```''',
        "output": r'''<think>
Using "any" everywhere defeats the entire purpose of TypeScript. The user has a typo "emial" instead of "email" and "potr" instead of "port" that TypeScript would catch with proper types. They also have "years" concatenated to a number without a space. By using any, they turned TypeScript into JavaScript with extra syntax. Need to show how proper types catch these bugs at compile time.
</think>

You have turned TypeScript into JavaScript with extra typing. The `any` type disables all type checking, so TypeScript cannot catch any of the bugs in your code:

- `user.emial` -- typo for `email`, no error
- `user.age + "years"` -- produces "25years" not "25 years", no warning
- `config.potr` -- typo for `port`, no error

These bugs would all be caught at compile time with proper types.

**The fix -- define types for your data:**

```typescript
interface User {
    id: number;
    name: string;
    email: string;
    age: number;
}

interface AppConfig {
    port: number;
    host: string;
    database: string;
}

async function fetchUser(id: number): Promise<User> {
    const response = await fetch(`/api/users/${id}`);
    const data: User = await response.json();
    return data;
}

function processUsers(users: User[]) {
    return users.map((user) => ({
        name: user.name,
        email: user.emial,  // ERROR: Property 'emial' does not exist
        age: `${user.age} years`,
    }));
}

const config: AppConfig = loadConfig();
startServer(config.potr);  // ERROR: Property 'potr' does not exist
```

Now TypeScript catches both typos instantly.

**When you genuinely don't know the type**, use `unknown` instead of `any`:

```typescript
function handleApiResponse(data: unknown) {
    // Must narrow the type before using it
    if (typeof data === 'object' && data !== null && 'name' in data) {
        console.log((data as { name: string }).name);
    }
}
```

`unknown` is the type-safe version of `any` -- it forces you to check the type before using the value. Reserve `any` for genuine escape hatches (e.g., migrating a JS codebase), never as a first resort.'''
    },
    {
        "instruction": r'''I use type assertions to fix type errors quickly:

```typescript
interface User {
    id: number;
    name: string;
    email: string;
    role: 'admin' | 'user';
}

// "I know this is a User"
const user = {} as User;
user.id = 1;
user.name = 'Alice';
// forgot email and role -- no error!

function getElement() {
    const el = document.getElementById('submit-btn') as HTMLButtonElement;
    el.disabled = true;  // crashes if element doesn't exist!
}

const response = await fetch('/api/data');
const data = (await response.json()) as User[];
// If API returns something else, no error at compile OR runtime
```''',
        "output": r'''<think>
Type assertion (as) overuse. The user uses "as" to tell TypeScript "trust me, I know the type" but is wrong in multiple cases: empty object asserted as User (missing required fields), potentially null DOM element asserted as HTMLButtonElement (crashes if not found), and API response asserted without validation (runtime type mismatch). Assertions bypass the type checker -- they are lies you tell the compiler.
</think>

Type assertions (`as`) tell TypeScript: "I know better than you -- stop checking." But in all three cases, you are wrong, and TypeScript cannot protect you.

**Problem 1: Empty object as User**

```typescript
const user = {} as User;
// TypeScript thinks this has id, name, email, role
// It actually has nothing. Any code using user.email gets undefined.
```

Fix -- let TypeScript enforce required fields:

```typescript
const user: User = {
    id: 1,
    name: 'Alice',
    email: 'alice@example.com',
    role: 'user',
};
// ERROR if you forget any required field
```

**Problem 2: DOM element might not exist**

```typescript
// Crashes with "Cannot set property 'disabled' of null"
const el = document.getElementById('submit-btn') as HTMLButtonElement;
el.disabled = true;
```

Fix -- handle the null case:

```typescript
const el = document.getElementById('submit-btn');
if (el instanceof HTMLButtonElement) {
    el.disabled = true;
}
// Or with optional chaining for simple cases:
const el = document.querySelector<HTMLButtonElement>('#submit-btn');
el?.disabled = true;
```

**Problem 3: Unvalidated API response**

```typescript
// API could return an error, different format, or empty array
const data = (await response.json()) as User[];
```

Fix -- validate at runtime:

```typescript
import { z } from 'zod';

const UserSchema = z.object({
    id: z.number(),
    name: z.string(),
    email: z.string().email(),
    role: z.enum(['admin', 'user']),
});

const data = await response.json();
const users = z.array(UserSchema).parse(data);
// Throws with a clear error if the data doesn't match
```

**Rule:** Use `as` only when you have information TypeScript genuinely cannot infer (e.g., after a custom type guard). If you find yourself using `as` frequently, your types are wrong.'''
    },
    {
        "instruction": r'''I'm using TypeScript enums for my app's constants:

```typescript
enum Direction {
    Up,
    Down,
    Left,
    Right,
}

enum Status {
    Active = 'ACTIVE',
    Inactive = 'INACTIVE',
    Pending = 'PENDING',
}

enum Color {
    Red = 0,
    Green = 1,
    Blue = 2,
}

function move(direction: Direction) {
    console.log(direction);
}

// Weird behavior:
move(Direction.Up);    // logs 0
move(42);              // no error! Any number is accepted
console.log(Color[0]); // "Red" -- reverse mapping
```''',
        "output": r'''<think>
TypeScript numeric enum pitfalls. Numeric enums accept any number, not just valid enum values -- so move(42) compiles fine even though 42 is not a valid Direction. They also generate runtime code with reverse mappings, increasing bundle size. String enums are better but still have issues. The modern alternative is union types or const objects. Need to explain the specific gotchas.
</think>

TypeScript numeric enums have several surprising behaviors that cause bugs.

**Problem 1: Any number is accepted.** `Direction` is a numeric enum, so TypeScript accepts ANY number where `Direction` is expected:

```typescript
move(42);        // compiles fine -- 42 is not a valid direction
move(-999);      // also compiles fine
move(Direction.Up); // this is just move(0)
```

This defeats the purpose of having an enum for type safety.

**Problem 2: Runtime code bloat.** Enums compile to JavaScript objects with reverse mappings:

```javascript
// Generated JS for enum Direction
var Direction;
(function (Direction) {
    Direction[Direction["Up"] = 0] = "Up";
    Direction[Direction["Down"] = 1] = "Down";
    // ...
})(Direction || (Direction = {}));
```

This adds bundle size for every enum.

**Problem 3: Reverse mappings are confusing.** `Color[0]` returns `"Red"`. This is rarely useful and often leads to bugs when someone passes a number thinking it's a color.

**The fix -- use union types or const objects:**

```typescript
// Option 1: Union type (simplest, zero runtime cost)
type Direction = 'up' | 'down' | 'left' | 'right';

function move(direction: Direction) {
    console.log(direction);
}

move('up');    // works
move('sideways'); // ERROR: not assignable to type Direction
move(42);      // ERROR: not assignable to type Direction

// Option 2: Const object (when you need runtime values)
const Status = {
    Active: 'ACTIVE',
    Inactive: 'INACTIVE',
    Pending: 'PENDING',
} as const;

type Status = typeof Status[keyof typeof Status];
// type Status = 'ACTIVE' | 'INACTIVE' | 'PENDING'
```

**When enums are acceptable:** String enums (`Status` in your example) are safer than numeric ones since they don't accept arbitrary strings. But union types are simpler, have zero runtime cost, and work better with tree-shaking.'''
    },
    {
        "instruction": r'''I turned off strict null checks because I was getting too many errors. Now my app crashes in production with "Cannot read properties of undefined":

```typescript
// tsconfig.json: "strictNullChecks": false

interface Order {
    id: number;
    customer?: {
        name: string;
        address?: {
            city: string;
        };
    };
}

function getShippingCity(order: Order): string {
    return order.customer.address.city;
    // Runtime: Cannot read properties of undefined (reading 'address')
}

function findUser(users: User[], id: number): User {
    return users.find(u => u.id === id);
    // Runtime: result might be undefined
}
```''',
        "output": r'''<think>
Disabling strictNullChecks. With strict null checks off, TypeScript pretends that null and undefined don't exist. Optional fields like customer? and address? are treated as always present. Array.find() returns T instead of T | undefined. The code compiles without errors but crashes at runtime when any optional field is missing. The user disabled it because of "too many errors" -- those errors were real bugs.
</think>

Those "too many errors" you silenced were real bugs that now crash in production. With `strictNullChecks: false`, TypeScript pretends `null` and `undefined` do not exist. Every optional field is treated as always present.

**What TypeScript would have told you with strict checks on:**

```typescript
function getShippingCity(order: Order): string {
    return order.customer.address.city;
    //          ^^^^^^^^ ERROR: Object is possibly undefined
    //                   ^^^^^^^ ERROR: Object is possibly undefined
}

function findUser(users: User[], id: number): User {
    return users.find(u => u.id === id);
    // ERROR: Type 'User | undefined' is not assignable to type 'User'
}
```

These are not false positives -- they are genuine bugs.

**The fix -- enable strict checks and handle nullability:**

```json
{ "compilerOptions": { "strictNullChecks": true } }
```

Then fix the code to handle the null cases:

```typescript
function getShippingCity(order: Order): string | null {
    // Optional chaining -- safe access
    return order.customer?.address?.city ?? null;
}

// Or throw a clear error if city is required:
function getRequiredShippingCity(order: Order): string {
    const city = order.customer?.address?.city;
    if (!city) {
        throw new Error(
            `Order ${order.id} has no shipping city`
        );
    }
    return city;  // TypeScript narrows this to string
}

function findUser(users: User[], id: number): User | undefined {
    return users.find(u => u.id === id);
}

// Or throw if not found:
function getUser(users: User[], id: number): User {
    const user = users.find(u => u.id === id);
    if (!user) {
        throw new Error(`User ${id} not found`);
    }
    return user;  // narrowed to User
}
```

**Do not disable strict checks to "fix" errors.** The errors are telling you where your code will crash. Fix them with optional chaining (`?.`), nullish coalescing (`??`), or explicit null checks. Enable `strict: true` in tsconfig for all new projects.'''
    },
    {
        "instruction": r'''I'm learning generics and wrote some utility types. They work but feel over-complicated:

```typescript
function getProperty<T extends object, K extends keyof T, V extends T[K]>(
    obj: T, key: K
): V {
    return obj[key] as V;
}

function merge<
    T extends Record<string, unknown>,
    U extends Record<string, unknown>,
    R extends T & U
>(a: T, b: U): R {
    return { ...a, ...b } as R;
}

type DeepReadonly<T> = T extends Function
    ? T
    : T extends object
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;

type DeepPartial<T> = T extends Function
    ? T
    : T extends object
    ? { [K in keyof T]?: DeepPartial<T[K]> }
    : T;

// Usage:
const name = getProperty(user, 'name');
const merged = merge(defaults, overrides);
```''',
        "output": r'''<think>
Over-engineered generics. getProperty has an unnecessary V generic (T[K] is already the return type), merge has an unnecessary R generic (T & U is the return type), and the deep utility types are reinventing what libraries like ts-toolbelt provide. The user is adding generic parameters that don't add type safety. Simpler versions work identically or better. Bad generics make code unreadable and unmaintainable.
</think>

Your generics are over-specified. Extra type parameters that don't add safety make the code harder to read and maintain.

**Problem 1: `getProperty` has a useless third generic.**

The `V extends T[K]` parameter adds nothing -- `T[K]` already IS the return type. And the `as V` cast actually makes it less safe:

```typescript
// Your version -- 3 generics, needs a cast
function getProperty<T extends object, K extends keyof T, V extends T[K]>(
    obj: T, key: K
): V {
    return obj[key] as V;
}

// Correct version -- 2 generics, no cast needed
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
    return obj[key];
}

// But this already exists in TypeScript:
const name = user.name;  // just access the property directly
// or use: user['name'] for dynamic keys
```

**Problem 2: `merge` has a useless third generic.**

```typescript
// Your version -- 3 generics, needs a cast
function merge<T extends Record<string, unknown>, U extends Record<string, unknown>, R extends T & U>(a: T, b: U): R { ... }

// Correct version -- 2 generics, no cast
function merge<T, U>(a: T, b: U): T & U {
    return { ...a, ...b };
}

// But this already exists:
const merged = { ...defaults, ...overrides };
// TypeScript infers the correct intersection type automatically
```

**Problem 3: Deep utility types already exist.**

Don't reinvent these. Use proven libraries:

```typescript
// Use ts-toolbelt or type-fest
import { DeepReadonly, DeepPartial } from 'type-fest';
```

**Rules for generics:**
- Each generic parameter should be USED at least twice (input and output). If it appears once, you probably don't need it.
- If TypeScript can infer it, don't make it a generic.
- If the built-in syntax works (property access, spread), don't wrap it in a function.
- Start with the simplest signature and add generics only when the compiler demands them.'''
    },
]
