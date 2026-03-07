"""
Code explanation training pairs - TypeScript types, Rust lifetimes, generics
"""

pairs = [
    {
        "instruction": r'''Walk me through these TypeScript types:

```typescript
type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object
    ? T[P] extends Array<infer U>
      ? Array<DeepPartial<U>>
      : DeepPartial<T[P]>
    : T[P];
};

type DeepRequired<T> = {
  [P in keyof T]-?: T[P] extends object
    ? DeepRequired<T[P]>
    : T[P];
};
```''',
        "output": r'''These are recursive utility types that apply optionality (or its inverse) to every level of a nested object type.

**DeepPartial<T>:**

Built-in `Partial<T>` only makes top-level properties optional. `DeepPartial` makes EVERY property at every nesting level optional.

How it works:
- `[P in keyof T]?` iterates over all keys of T and makes each optional (the `?`).
- For each property, it checks: is the type an object?
  - If no (primitives like string, number) -- keep the type as-is.
  - If yes, is it an array? -- `T[P] extends Array<infer U>` extracts the element type `U` using `infer`. The result is `Array<DeepPartial<U>>`, so array elements are also made deeply partial.
  - If it is a non-array object -- recurse with `DeepPartial<T[P]>`.

The array check is important. Without it, arrays would be treated as objects and mapped incorrectly -- you would get `{ 0?: ..., 1?: ..., length?: number }` instead of a proper array type.

**DeepRequired<T>:**

The inverse -- makes all properties required at every level. The `-?` modifier removes optionality (it is the opposite of `?`). This one does not have the array special case, which means it could incorrectly transform array properties into mapped object types. That is likely a bug.

**Practical use case:** DeepPartial is commonly used for configuration objects where you want to provide only the values you want to override, and merge them with defaults:
```
function configure(overrides: DeepPartial<Config>) { ... }
```'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain Rust lifetime annotations and borrowing rules in this code.
</think>

Explain the lifetimes in this Rust code:

```rust
struct Parser<'a> {
    input: &'a str,
    position: usize,
}

impl<'a> Parser<'a> {
    fn new(input: &'a str) -> Self {
        Parser { input, position: 0 }
    }

    fn peek(&self) -> Option<char> {
        self.input[self.position..].chars().next()
    }

    fn take_while<F>(&mut self, predicate: F) -> &'a str
    where
        F: Fn(char) -> bool,
    {
        let start = self.position;
        while let Some(c) = self.peek() {
            if !predicate(c) { break; }
            self.position += c.len_utf8();
        }
        &self.input[start..self.position]
    }
}
```''',
        "output": r'''<think>
The key thing here is that take_while returns a reference with lifetime 'a (tied to the input), not to &self. This is important for how long the returned slice lives.
</think>

This is a string parser that borrows its input and returns slices of it. The lifetime annotations tell the Rust compiler how long references remain valid.

**The lifetime `'a`:**

`Parser<'a>` declares a lifetime parameter. The struct contains `input: &'a str` -- a borrowed string slice that must live at least as long as the parser. The `'a` is a contract: "whoever creates a Parser must ensure the input string outlives it."

**`new` function:**

Takes `input: &'a str` and returns a `Parser<'a>`. The same lifetime `'a` connects the input to the struct, ensuring the parser cannot outlive its input data.

**`peek` function:**

Returns `Option<char>` -- an owned value, not a reference. No lifetime annotations needed. It slices from the current position and gets the first character.

**`take_while` -- the interesting one:**

Returns `&'a str` -- a slice of the ORIGINAL input, not a slice tied to `&self`. This is a crucial design decision. It means the returned slice remains valid even after the parser is dropped, because it borrows from the input string, not from the parser.

If the return type were `&str` (with lifetime elision), Rust would infer it as `&'_ str` tied to `&self`, meaning the slice could not outlive the parser borrow. By explicitly writing `&'a str`, you decouple the returned reference from the parser's borrow.

**`c.len_utf8()`:** Advances position by the character's byte length, not by 1. This correctly handles multi-byte UTF-8 characters (e.g., emoji, CJK characters). Without this, slicing at `self.position` could panic by splitting a multi-byte character.'''
    },
    {
        "instruction": r'''What do these TypeScript generics do?

```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

function map<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => U
): Result<U, E> {
  if (result.ok) {
    return { ok: true, value: fn(result.value) };
  }
  return result;
}

function flatMap<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => Result<U, E>
): Result<U, E> {
  if (result.ok) {
    return fn(result.value);
  }
  return result;
}
```''',
        "output": r'''This implements a Result type (inspired by Rust's Result enum) for type-safe error handling without exceptions.

**The Result type:**

A discriminated union with two variants:
- Success: `{ ok: true, value: T }` -- holds the successful value of type T.
- Failure: `{ ok: false, error: E }` -- holds an error of type E (defaulting to `Error`).

The `ok` field acts as the discriminant. When you check `if (result.ok)`, TypeScript narrows the type -- inside the if-block, `result.value` is available; in the else-block, `result.error` is available. This is type-safe at compile time.

**`map` function:**

Transforms the success value without affecting errors. If the result is ok, it applies `fn` to the value and wraps the output in a new success Result. If the result is an error, it passes through unchanged.

The generics: `T` is the input value type, `U` is the output value type, `E` is the error type (preserved through the transformation). So `map(Result<number, E>, n => n.toString())` produces `Result<string, E>`.

**`flatMap` function:**

Like `map`, but `fn` returns a `Result` instead of a plain value. This is for operations that themselves might fail. Without `flatMap`, mapping with a fallible function would give you `Result<Result<U, E>, E>` -- a nested Result. `flatMap` "flattens" it to `Result<U, E>`.

**Why this pattern?** It makes error handling explicit in the type system. Every function that can fail returns `Result<T, E>`, and callers must handle both cases. Unlike try/catch, errors cannot be silently ignored -- the compiler enforces the check.

**The `E = Error` default** means you can write `Result<string>` instead of `Result<string, Error>` for the common case.'''
    },
    {
        "instruction": r'''Explain this Rust trait and impl:

```rust
trait Summary {
    fn summarize_author(&self) -> String;

    fn summarize(&self) -> String {
        format!("(Read more from {}...)", self.summarize_author())
    }
}

struct Article {
    title: String,
    author: String,
    content: String,
}

impl Summary for Article {
    fn summarize_author(&self) -> String {
        self.author.clone()
    }

    fn summarize(&self) -> String {
        format!("{}, by {} - {}...", self.title, self.author, &self.content[..50])
    }
}

fn notify(item: &(impl Summary + std::fmt::Display)) {
    println!("Breaking: {}", item.summarize());
}
```''',
        "output": r'''This defines a trait (Rust's version of an interface) with a default method implementation, then implements it for a concrete type.

**The `Summary` trait:**

- `summarize_author(&self) -> String` -- a required method. Any type implementing Summary MUST provide this.
- `summarize(&self) -> String` -- a default method. Types CAN override it, but if they do not, this fallback implementation is used. The default calls `summarize_author()`, so even the default behavior is customized per type.

**The `Article` impl:**

- Provides `summarize_author` (required) by cloning the author string.
- Overrides `summarize` (optional) with a custom format that includes the title, author, and first 50 bytes of content.

**The `clone()` call:** `self.author` is a `String`, and the method returns an owned `String`. Since `&self` only borrows, you cannot move `author` out -- you must clone it. Returning `&str` would avoid the clone but would require lifetime annotations.

**The `notify` function:**

`&(impl Summary + std::fmt::Display)` is syntactic sugar for a generic function with trait bounds. It accepts any reference to a type that implements BOTH `Summary` and `Display`. The compiler monomorphizes this -- generating separate compiled versions for each concrete type used.

**The `&self.content[..50]` slice is risky:** It indexes by bytes, not characters. If the content contains multi-byte UTF-8 characters, slicing at byte 50 could split a character and cause a panic. Safe alternatives: `content.chars().take(50).collect::<String>()` or checking `content.is_char_boundary(50)` first.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain TypeScript conditional types and the infer keyword in a complex utility type.
</think>

What does this TypeScript type do?

```typescript
type FunctionParams<T> = T extends (...args: infer P) => any ? P : never;
type FunctionReturn<T> = T extends (...args: any[]) => infer R ? R : never;
type PromiseValue<T> = T extends Promise<infer V> ? PromiseValue<V> : T;

type AsyncFunctionReturn<T> = T extends (...args: any[]) => infer R
  ? R extends Promise<infer V>
    ? V
    : R
  : never;

// Usage:
type Params = FunctionParams<(x: number, y: string) => boolean>;
// Result: [x: number, y: string]

type Unwrapped = PromiseValue<Promise<Promise<string>>>;
// Result: string
```''',
        "output": r'''<think>
These are utility types using conditional types and infer to extract type information from function signatures and promises.
</think>

These are type-level utility types that extract information from function and promise types using conditional types and the `infer` keyword.

**`FunctionParams<T>`:**

Checks if T is a function type. If yes, `infer P` captures the parameter types as a tuple. If no, returns `never` (the "impossible" type). For `(x: number, y: string) => boolean`, P resolves to `[x: number, y: string]` -- a labeled tuple preserving parameter names.

**`FunctionReturn<T>`:**

Same pattern but `infer R` captures the return type. For the same function, R would be `boolean`.

**`PromiseValue<T>`:**

Recursively unwraps nested promises. If T is a `Promise<V>`, it recurses on V. If T is not a Promise, it returns T as-is (base case). So `Promise<Promise<string>>` becomes `PromiseValue<Promise<string>>` which becomes `PromiseValue<string>` which returns `string`.

This handles arbitrary nesting depth -- `Promise<Promise<Promise<number>>>` correctly resolves to `number`.

**`AsyncFunctionReturn<T>`:**

Combines both patterns. First checks if T is a function and captures the return type R. Then checks if R is a Promise and captures the inner value V. This gives you the "unwrapped" return type of an async function.

For `async function foo(): Promise<User>`, the type would be `User`, not `Promise<User>`.

**The `never` type:** Used as the "else" branch because `never` is the bottom type in TypeScript -- it is assignable to everything but nothing is assignable to it. If you accidentally pass a non-function to `FunctionParams`, the result type is `never`, which will cause type errors at usage sites rather than silently succeeding.'''
    },
]
