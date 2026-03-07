"""
Rust language training pairs - trait objects, blanket impls, associated types, From/Into, Deref
"""

pairs = [
    {
        "instruction": r'''<thinking>
The user wants to understand trait objects and dynamic dispatch in Rust. I should explain the difference between static and dynamic dispatch, show dyn Trait usage, and cover object safety rules.
</thinking>

Explain trait objects and dynamic dispatch in Rust. When should I use dyn Trait vs generics?''',
        "output": r'''Static dispatch (generics) monomorphizes at compile time -- the compiler generates specialized code for each concrete type. Dynamic dispatch (`dyn Trait`) uses a vtable at runtime, allowing heterogeneous collections at the cost of a small indirection overhead.

```rust
use std::fmt;

trait Shape: fmt::Display {
    fn area(&self) -> f64;
    fn perimeter(&self) -> f64;
}

struct Circle { radius: f64 }
struct Rect { w: f64, h: f64 }

impl Shape for Circle {
    fn area(&self) -> f64 { std::f64::consts::PI * self.radius * self.radius }
    fn perimeter(&self) -> f64 { 2.0 * std::f64::consts::PI * self.radius }
}
impl fmt::Display for Circle {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Circle(r={})", self.radius)
    }
}

impl Shape for Rect {
    fn area(&self) -> f64 { self.w * self.h }
    fn perimeter(&self) -> f64 { 2.0 * (self.w + self.h) }
}
impl fmt::Display for Rect {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Rect({}x{})", self.w, self.h)
    }
}

// Static dispatch -- fast, but one type at a time
fn print_area<S: Shape>(shape: &S) {
    println!("{}: area = {:.2}", shape, shape.area());
}

// Dynamic dispatch -- allows mixed types in a collection
fn total_area(shapes: &[Box<dyn Shape>]) -> f64 {
    shapes.iter().map(|s| s.area()).sum()
}

fn main() {
    // Heterogeneous collection requires dyn Trait
    let shapes: Vec<Box<dyn Shape>> = vec![
        Box::new(Circle { radius: 5.0 }),
        Box::new(Rect { w: 4.0, h: 6.0 }),
        Box::new(Circle { radius: 1.0 }),
    ];

    for s in &shapes {
        print_area(s.as_ref());
    }
    println!("Total area: {:.2}", total_area(&shapes));
}
```

Use generics when:
- All values are the same type
- You want maximum performance (no vtable indirection)
- You need to return the concrete type

Use `dyn Trait` when:
- You need heterogeneous collections
- You want to erase the concrete type (plugin systems, callbacks)
- You want smaller binary size (no monomorphization bloat)

Object safety rules: a trait is object-safe if its methods do not use `Self` by value and do not have generic type parameters.'''
    },
    {
        "instruction": r'''Show how blanket implementations work in Rust with a practical example.''',
        "output": r'''A blanket implementation implements a trait for all types that satisfy a bound. The standard library uses this pattern extensively -- for example, `impl<T: Display> ToString for T`.

```rust
use std::fmt;

// A trait for serializing values to a log-friendly string
trait LogFormat {
    fn log_format(&self) -> String;
}

// Blanket impl: any type that implements Display gets LogFormat for free
impl<T: fmt::Display> LogFormat for T {
    fn log_format(&self) -> String {
        format!("[LOG] {self}")
    }
}

// A trait for types that can be validated
trait Validate {
    fn is_valid(&self) -> bool;
}

// A trait for types that can be validated and then saved
trait SaveIfValid: Validate + fmt::Debug {
    fn save(&self) -> Result<(), String>;
}

// Blanket impl: anything Validate + Debug gets SaveIfValid
impl<T: Validate + fmt::Debug> SaveIfValid for T {
    fn save(&self) -> Result<(), String> {
        if self.is_valid() {
            println!("Saving: {self:?}");
            Ok(())
        } else {
            Err(format!("Invalid: {self:?}"))
        }
    }
}

#[derive(Debug)]
struct Email(String);

impl fmt::Display for Email {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Validate for Email {
    fn is_valid(&self) -> bool {
        self.0.contains('@') && self.0.contains('.')
    }
}

fn main() {
    // LogFormat works on anything with Display
    println!("{}", 42.log_format());
    println!("{}", "hello".log_format());
    println!("{}", 3.14f64.log_format());

    let good = Email("user@example.com".into());
    let bad = Email("not-an-email".into());

    // SaveIfValid works on anything with Validate + Debug
    println!("{:?}", good.save()); // Ok(())
    println!("{:?}", bad.save());  // Err(...)
}
```

Blanket impls are powerful because adding a single trait impl on your type can unlock many derived behaviors. However, they can cause conflicts -- you cannot write two blanket impls that might overlap, and adding a blanket impl to a published crate is a breaking change.'''
    },
    {
        "instruction": r'''Explain associated types vs generic type parameters in Rust traits. When should I use each?''',
        "output": r'''Associated types define a single type per implementation, while generic parameters allow multiple implementations for the same type.

```rust
// Associated type: each type has ONE output type for Iterator
// You cannot impl Iterator<Output=u32> AND Iterator<Output=String>
// for the same struct
trait MyIterator {
    type Item;
    fn next(&mut self) -> Option<Self::Item>;
}

struct Counter {
    count: u32,
    max: u32,
}

impl MyIterator for Counter {
    type Item = u32; // fixed for this type
    fn next(&mut self) -> Option<u32> {
        if self.count < self.max {
            self.count += 1;
            Some(self.count)
        } else {
            None
        }
    }
}

// Generic parameter: a type can impl From<T> for MANY different T
// String impls From<&str>, From<Vec<u8>>, From<char>, etc.
trait Convert<From> {
    fn convert(value: From) -> Self;
}

struct Celsius(f64);
struct Fahrenheit(f64);
struct Kelvin(f64);

// Multiple impls of Convert for Celsius, one per source type
impl Convert<Fahrenheit> for Celsius {
    fn convert(f: Fahrenheit) -> Self {
        Celsius((f.0 - 32.0) * 5.0 / 9.0)
    }
}

impl Convert<Kelvin> for Celsius {
    fn convert(k: Kelvin) -> Self {
        Celsius(k.0 - 273.15)
    }
}

// Using associated types in trait bounds
fn sum_first_n<I>(iter: &mut I, n: usize) -> i64
where
    I: MyIterator<Item = u32>,
{
    let mut total: i64 = 0;
    for _ in 0..n {
        match iter.next() {
            Some(val) => total += val as i64,
            None => break,
        }
    }
    total
}

fn main() {
    let mut counter = Counter { count: 0, max: 10 };
    println!("Sum of first 5: {}", sum_first_n(&mut counter, 5));

    let c1 = Celsius::convert(Fahrenheit(212.0));
    let c2 = Celsius::convert(Kelvin(373.15));
    println!("212F = {:.1}C", c1.0);
    println!("373.15K = {:.1}C", c2.0);
}
```

Use associated types when:
- Each implementing type has exactly one logical output (Iterator::Item)
- You want simpler trait bounds (no extra generic params)

Use generic parameters when:
- A type can implement the trait multiple times with different types
- From<T>, Add<Rhs>, PartialEq<Rhs> are classic examples'''
    },
    {
        "instruction": r'''<thinking>
The user wants to understand the From and Into traits in Rust. I should show how to implement From for custom types and how Into is automatically derived. I will include practical conversion patterns used in real Rust code.
</thinking>

How do From and Into work in Rust? Show practical conversion patterns for custom types.''',
        "output": r'''`From<T>` defines how to create a type from `T`. Implementing `From<T>` automatically gives you `Into<T>` for free (blanket impl). These traits are the idiomatic way to do type conversions in Rust.

```rust
#[derive(Debug, Clone)]
struct UserId(u64);

#[derive(Debug, Clone)]
struct Email(String);

#[derive(Debug)]
struct User {
    id: UserId,
    email: Email,
    display_name: String,
}

// From<u64> for UserId
impl From<u64> for UserId {
    fn from(id: u64) -> Self {
        UserId(id)
    }
}

// From<&str> and From<String> for Email
impl From<&str> for Email {
    fn from(s: &str) -> Self {
        Email(s.to_lowercase())
    }
}

impl From<String> for Email {
    fn from(s: String) -> Self {
        Email(s.to_lowercase())
    }
}

// Accept anything convertible to UserId and Email
fn create_user(
    id: impl Into<UserId>,
    email: impl Into<Email>,
    name: impl Into<String>,
) -> User {
    User {
        id: id.into(),
        email: email.into(),
        display_name: name.into(),
    }
}

// TryFrom for fallible conversions
impl TryFrom<&str> for UserId {
    type Error = String;
    fn try_from(s: &str) -> Result<Self, Self::Error> {
        s.parse::<u64>()
            .map(UserId)
            .map_err(|e| format!("invalid user id '{s}': {e}"))
    }
}

fn main() {
    // From conversions -- explicit
    let id = UserId::from(42u64);
    let email = Email::from("Alice@Example.COM");

    // Into conversions -- implicit via type inference
    let user = create_user(123u64, "bob@test.com", "Bob");
    println!("{user:?}");

    // TryFrom for validation
    let parsed: Result<UserId, _> = "9999".try_into();
    println!("Parsed: {parsed:?}");

    let bad: Result<UserId, _> = UserId::try_from("not_a_number");
    println!("Bad: {bad:?}");

    // Common pattern: String conversions
    let s: String = "hello".into(); // &str -> String via From
    let path: std::path::PathBuf = "/tmp/file.txt".into(); // &str -> PathBuf
    println!("{s}, {}", path.display());
}
```

Rules of thumb:
- Implement `From`, not `Into` -- you get `Into` for free
- Use `TryFrom`/`TryInto` when conversion can fail
- Use `impl Into<T>` in function parameters for ergonomic APIs
- `From` conversions should be cheap and infallible'''
    },
    {
        "instruction": r'''Explain the Deref trait in Rust and how it enables smart pointer patterns. Show custom Deref implementation.''',
        "output": r'''`Deref` lets a type behave like a reference to its inner value. The compiler automatically calls `deref()` when you use the `*` operator or when a method/function expects a reference to the inner type (deref coercion).

```rust
use std::ops::{Deref, DerefMut};
use std::fmt;

// A smart pointer that logs access to its inner value
struct Tracked<T: fmt::Debug> {
    value: T,
    access_count: std::cell::Cell<u32>,
}

impl<T: fmt::Debug> Tracked<T> {
    fn new(value: T) -> Self {
        Tracked {
            value,
            access_count: std::cell::Cell::new(0),
        }
    }

    fn accesses(&self) -> u32 {
        self.access_count.get()
    }
}

impl<T: fmt::Debug> Deref for Tracked<T> {
    type Target = T;

    fn deref(&self) -> &T {
        self.access_count.set(self.access_count.get() + 1);
        &self.value
    }
}

impl<T: fmt::Debug> DerefMut for Tracked<T> {
    fn deref_mut(&mut self) -> &mut T {
        self.access_count.set(self.access_count.get() + 1);
        &mut self.value
    }
}

fn print_len(s: &str) {
    println!("Length: {}", s.len());
}

fn main() {
    // Tracked<String> auto-derefs to &String, then to &str
    let name = Tracked::new(String::from("Rust"));

    // Deref coercion: Tracked<String> -> &String -> &str
    print_len(&name); // works because of deref coercion chain
    println!("First char: {}", name.chars().next().unwrap());
    println!("Access count: {}", name.accesses());

    // Standard library examples of Deref:
    // Box<T> -> T
    let boxed = Box::new(vec![1, 2, 3]);
    println!("Sum: {}", boxed.iter().sum::<i32>()); // Box<Vec> -> &Vec -> slice

    // String -> str
    let s = String::from("hello");
    print_len(&s); // &String coerces to &str

    // Vec<T> -> [T]
    let v = vec![10, 20, 30];
    let slice: &[i32] = &v; // Vec<i32> coerces to &[i32]
    println!("Slice: {slice:?}");

    // Mutable deref
    let mut tracked_vec = Tracked::new(vec![1, 2]);
    tracked_vec.push(3); // DerefMut gives &mut Vec, then push()
    println!("Vec: {:?}, accesses: {}", *tracked_vec, tracked_vec.accesses());
}
```

Deref coercion chain: `&Tracked<String>` -> `&String` -> `&str`. The compiler applies these automatically, which is why you can pass a `&String` to a function expecting `&str`.

Warning: do not abuse Deref for general "inheritance." Use it only for smart-pointer-like wrappers where the inner type is the primary interface.'''
    },
]
