"""
Frontend thinking pairs - TypeScript with React patterns
"""

pairs = [
    {
        "instruction": r'''How do I type a React component that accepts either a "link" variant (with href) or a "button" variant (with onClick) but never both? I want TypeScript to enforce this.''',
        "output": r'''<think>
This is a discriminated union problem. The user wants a component that can be used as either a link or a button, but the props should be mutually exclusive -- you cannot pass both href and onClick.

Option 1: Optional props for both href and onClick. But then TypeScript allows passing both, or neither. No enforcement.

Option 2: Discriminated union with a "variant" or "as" prop. Something like:
type Props = { as: 'link'; href: string } | { as: 'button'; onClick: () => void }

This works but forces the user to pass an explicit "as" prop, which is redundant -- if they pass href, it is obviously a link.

Option 3: Discriminated union based on the presence of href vs onClick:
type Props = { href: string; onClick?: never } | { onClick: () => void; href?: never }

The `never` type prevents the other prop from being passed. This is the cleanest approach because TypeScript infers the variant from which prop is provided.

Wait, I should also consider: should this render an <a> tag for links and a <button> tag for buttons? Yes, absolutely -- using the right semantic element matters for accessibility. So the component needs to render different elements based on the variant.

Hmm, there is a subtlety. The link variant might also want target, rel, and other anchor attributes. The button variant might want type="submit" or disabled. Should I extend HTML attributes?

I initially thought extending HTMLAttributes would be cleanest, but discriminated unions with spread HTML attributes get messy. Let me keep it focused on the core pattern with the most common props, and show how to extend it.

The tradeoff: full HTML attribute forwarding is more flexible but makes the type definition complex. A focused prop set is simpler but less reusable.
</think>

Use a discriminated union with `never` types to make the props mutually exclusive. TypeScript will error if someone passes both href and onClick.

```tsx
import { ReactNode } from 'react';

// Core shared props
interface BaseProps {
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
}

// Link variant -- has href, cannot have onClick
interface LinkProps extends BaseProps {
  href: string;
  target?: '_blank' | '_self';
  onClick?: never; // <-- Prevents passing onClick
}

// Button variant -- has onClick, cannot have href
interface ButtonProps extends BaseProps {
  onClick: () => void;
  type?: 'button' | 'submit' | 'reset';
  href?: never; // <-- Prevents passing href
}

type ActionProps = LinkProps | ButtonProps;

function Action(props: ActionProps) {
  const { children, className, size = 'md', disabled } = props;

  const sizeClass = {
    sm: 'action-sm',
    md: 'action-md',
    lg: 'action-lg',
  }[size];

  const classes = ['action', sizeClass, className]
    .filter(Boolean)
    .join(' ');

  // TypeScript narrows the type based on which prop exists
  if ('href' in props && props.href) {
    return (
      <a
        href={props.href}
        target={props.target}
        className={classes}
        rel={props.target === '_blank' ? 'noopener noreferrer' : undefined}
        aria-disabled={disabled || undefined}
      >
        {children}
      </a>
    );
  }

  return (
    <button
      onClick={(props as ButtonProps).onClick}
      type={(props as ButtonProps).type || 'button'}
      className={classes}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

// USAGE -- TypeScript enforces the constraints:

// Valid: link with href
<Action href="/settings" size="md">Settings</Action>

// Valid: button with onClick
<Action onClick={() => save()} size="lg">Save</Action>

// ERROR: both href and onClick
// <Action href="/foo" onClick={() => {}}>Bad</Action>
// Type error: Type 'string' is not assignable to type 'undefined'

// ERROR: neither href nor onClick
// <Action size="md">Nothing</Action>
// Type error: missing required property
```

The `never` trick explained:
- `onClick?: never` means "this prop can exist but must be `undefined`"
- If you pass `onClick={() => {}}` on a LinkProps, TypeScript errors because `() => void` is not assignable to `never`
- This gives you compile-time enforcement of mutual exclusivity without runtime checks'''
    },
    {
        "instruction": r'''How do I write a generic custom hook that works with any data type? I want a useFetch hook that returns typed data.''',
        "output": r'''<think>
Generic hooks are a common TypeScript + React pattern. The user wants useFetch<T> where T is the response data type.

The basic shape is:
function useFetch<T>(url: string): { data: T | null; loading: boolean; error: Error | null }

But there are some design decisions:
1. Should T have a constraint? Like T extends Record<string, unknown>? Hmm, no -- the response could be an array, a string, any JSON-serializable type. Keep T unconstrained.

2. How does the caller specify T? Two ways:
   - Explicit: useFetch<User>('/api/user')
   - Inferred: useFetch('/api/user', parseUser) where parseUser returns User

The explicit generic approach is simpler but relies on trust -- TypeScript does not verify that the API actually returns a User. The parser approach is safer because the parser validates the shape at runtime.

Wait, should I include a Zod schema for runtime validation? That would be the most robust approach: useFetch('/api/user', userSchema) where userSchema is a Zod schema that both validates AND infers the TypeScript type. But that introduces a dependency and adds complexity.

I initially thought the simple generic approach is enough for a training example, but I should show both the basic generic version AND the Zod version since runtime validation is important in production.

The tradeoff: simple generics are trust-based (you declare the type and hope the API matches). Schema validation is verified at runtime but requires Zod or similar.

Let me also handle: abort on unmount (prevent state updates after unmount), refetch function, dependency array for re-fetching.
</think>

Here is a generic useFetch hook with proper TypeScript, abort handling, and an optional runtime validation pattern.

```tsx
import { useState, useEffect, useCallback, useRef } from 'react';

// Return type is fully typed based on the generic parameter T
interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

function useFetch<T>(
  url: string | null, // null = skip fetching
  options?: RequestInit,
): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Ref to track if component is still mounted
  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async () => {
    if (!url) return;

    // Abort previous request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error('HTTP ' + response.status + ': ' + response.statusText);
      }

      const json = (await response.json()) as T;
      setData(json);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        return; // Ignore aborted requests
      }
      setError(
        err instanceof Error ? err.message : 'Unknown error'
      );
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    fetchData();
    return () => {
      abortRef.current?.abort();
    };
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// USAGE with explicit generic type:

interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user';
}

interface Product {
  id: string;
  name: string;
  price: number;
}

function UserProfile({ userId }: { userId: string }) {
  // TypeScript knows data is User | null
  const { data: user, loading, error } = useFetch<User>(
    '/api/users/' + userId
  );

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!user) return null;

  // user is fully typed -- autocomplete works
  return (
    <div>
      <h1>{user.name}</h1>
      <p>{user.email}</p>
      <span>Role: {user.role}</span>
    </div>
  );
}

function ProductList() {
  // TypeScript knows data is Product[] | null
  const { data: products, loading, refetch } = useFetch<Product[]>(
    '/api/products'
  );

  if (loading || !products) return <div>Loading...</div>;

  return (
    <div>
      <button onClick={refetch}>Refresh</button>
      {products.map(p => (
        <div key={p.id}>
          {p.name} - ${p.price.toFixed(2)}
        </div>
      ))}
    </div>
  );
}

// Conditional fetching -- pass null to skip
function ConditionalFetch({ userId }: { userId: string | null }) {
  // Does not fetch until userId is provided
  const { data } = useFetch<User>(
    userId ? '/api/users/' + userId : null
  );
  return <div>{data?.name || 'No user selected'}</div>;
}
```

Key TypeScript patterns used:
- **Generic parameter T** flows through the entire return type -- `data` is `T | null`, not `any`
- **Caller specifies T** explicitly: `useFetch<User>(url)` -- TypeScript trusts this matches the API response
- **Null URL pattern** for conditional fetching -- avoids awkward `if` statements around the hook call (hooks cannot be called conditionally)
- **AbortController** cleanup prevents state updates on unmounted components'''
    },
    {
        "instruction": r'''I keep getting the TypeScript error "Type X is not assignable to type Y" when passing props to child components. How do I debug and fix these prop typing issues?''',
        "output": r'''<think>
"Type X is not assignable to type Y" is the most common TypeScript error in React codebases. Let me think about the typical causes and how to debug them.

Common causes in React:
1. Missing optional modifier -- component expects { name: string } but parent passes { name: string | undefined } because the value comes from state that might not be set yet
2. String literal vs string -- component expects variant: 'primary' | 'secondary' but parent passes a variable typed as string
3. Event handler types -- passing (e: React.ChangeEvent<HTMLInputElement>) to something expecting (e: React.FormEvent)
4. Children type mismatch -- component expects string children but gets JSX
5. Object shape mismatch -- extra properties, missing properties, or nested type differences

Hmm, the debugging approach matters more than listing all causes. When you see this error, the steps are:
1. Read the error carefully -- TypeScript tells you exactly what X and Y are
2. Hover over the prop in the parent to see what type TypeScript inferred
3. Hover over the prop definition in the child to see what it expects
4. Compare the two and find the mismatch

Wait, one of the most confusing cases is when TypeScript shows a HUGE type in the error. Like "Type '{ name: string; age: number; address: { street: string; city: string; zip: number; } }' is not assignable to type '{ name: string; age: number; address: { street: string; city: string; zip: string; } }'." The actual mismatch is zip: number vs zip: string, buried in a nested object.

I initially thought I should just list solutions, but actually teaching the debugging PROCESS is more valuable. The user will encounter new type errors constantly -- they need to know how to read and fix them, not just memorize specific fixes.
</think>

This error means the type of what you are passing does not match what the component expects. Here is how to systematically debug and fix it.

```tsx
// SCENARIO 1: Optional vs required props
// Error: Type 'string | undefined' is not assignable to type 'string'

interface UserCardProps {
  name: string; // Required!
  email: string;
}

function UserCard({ name, email }: UserCardProps) {
  return <div>{name} ({email})</div>;
}

// Parent has optional data from an API call
function ParentBroken() {
  const [user, setUser] = useState<{
    name?: string;
    email?: string;
  }>({});

  // ERROR: user.name is string | undefined, but UserCard needs string
  return <UserCard name={user.name} email={user.email} />;
}

// FIX 1: Guard with a conditional
function ParentFixed1() {
  const [user, setUser] = useState<{
    name?: string;
    email?: string;
  }>({});

  if (!user.name || !user.email) return <div>Loading...</div>;
  // TypeScript narrows: user.name is now string (not undefined)
  return <UserCard name={user.name} email={user.email} />;
}

// FIX 2: Make the child props optional with defaults
interface UserCardPropsV2 {
  name?: string;
  email?: string;
}

function UserCardV2({ name = 'Unknown', email = '' }: UserCardPropsV2) {
  return <div>{name} ({email})</div>;
}


// SCENARIO 2: String literal narrowing
// Error: Type 'string' is not assignable to type '"primary" | "secondary"'

interface ButtonProps {
  variant: 'primary' | 'secondary' | 'danger';
  children: React.ReactNode;
}

function StyledButton({ variant, children }: ButtonProps) {
  return <button className={variant}>{children}</button>;
}

function ParentLiteralBroken() {
  // 'primary' is widened to type 'string' when assigned to a variable
  const myVariant = 'primary';
  // This actually works because const inference keeps it as 'primary'
  // But this breaks:
  let dynamicVariant = 'primary'; // type is 'string', not 'primary'
  // return <StyledButton variant={dynamicVariant}>Click</StyledButton>;
  // ERROR: Type 'string' is not assignable to type '"primary" | "secondary" | "danger"'

  // FIX: Use 'as const' or type the variable
  const variant1 = 'primary' as const; // type: 'primary'
  const variant2: ButtonProps['variant'] = 'primary'; // type: 'primary' | 'secondary' | 'danger'

  return <StyledButton variant={variant1}>Click</StyledButton>;
}


// SCENARIO 3: Event handler type mismatch
// Error: Type '(e: ChangeEvent<HTMLInputElement>) => void' is not assignable to...

interface SearchProps {
  onSearch: (query: string) => void;
}

function SearchBox({ onSearch }: SearchProps) {
  return (
    <input onChange={e => onSearch(e.target.value)} />
  );
}

function ParentEventBroken() {
  // BAD: passing the wrong function signature
  // onSearch expects (query: string) => void
  // but you are passing (e: ChangeEvent) => void
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    console.log(e.target.value);
  };
  // return <SearchBox onSearch={handleChange} />; // ERROR

  // FIX: Match the expected signature
  const handleSearch = (query: string) => {
    console.log(query);
  };
  return <SearchBox onSearch={handleSearch} />; // OK
}


// SCENARIO 4: Debugging technique -- hover and compare
// When the error is confusing, extract the types explicitly:

type Actual = typeof someValue;
// Hover over 'Actual' in your IDE to see the inferred type

type Expected = ComponentProps<typeof SomeComponent>['propName'];
// Hover over 'Expected' to see what the component wants

// Compare the two visually. The mismatch becomes obvious.
// For nested objects, TypeScript highlights the exact field that differs.
```

Debugging checklist for "not assignable" errors:
1. **Hover** over the prop where the error occurs -- IDE shows the inferred type
2. **Hover** over the component's prop definition -- see what it expects
3. **Compare** the two types -- find the specific field that mismatches
4. **Common fixes**: add a null guard, use `as const`, adjust the interface, or add a default value
5. **Nuclear option**: If you truly know the type is correct, use `as` assertion -- but this is a last resort that hides real bugs'''
    },
    {
        "instruction": r'''How do I type a polymorphic component in React? I want a Box component that can render as any HTML element -- div, section, article, span -- and have the correct props for that element.''',
        "output": r'''<think>
Polymorphic components are one of the hardest TypeScript + React patterns. The user wants something like <Box as="a" href="/foo"> where TypeScript knows that href is valid because as="a" makes it an anchor element.

The naive approach:
interface BoxProps { as?: string; children: ReactNode; [key: string]: any; }
But this throws away all type safety -- any prop is accepted regardless of the element.

The correct approach uses generics:
- The `as` prop determines the element type
- TypeScript infers the valid HTML attributes from the element type
- Invalid attributes for the chosen element cause a type error

The key type is React.ElementType which accepts any valid element ('div', 'span', 'a') or component type. Then React.ComponentPropsWithoutRef<T> gives you the HTML attributes for that element.

Wait, there is a complexity with ref forwarding. If I want the component to accept refs, I need ComponentPropsWithRef<T> and forwardRef. Let me start without refs for clarity.

Hmm, I initially thought this was straightforward, but the generic constraint gets tricky. The component needs:
1. A generic parameter C that extends React.ElementType
2. The `as` prop typed as C
3. The remaining props typed as ComponentPropsWithoutRef<C>
4. Omit the `as` key from the HTML props to avoid conflicts

The implementation requires some advanced TypeScript: conditional types, generic constraints, and Omit utility type. Let me build it step by step.

The tradeoff: full polymorphic typing is complex code that can be hard for junior developers to understand. But it provides excellent DX for consumers of the component. Libraries like Chakra UI and Radix use this pattern extensively.
</think>

Polymorphic components need generics so TypeScript can infer the correct props based on the `as` prop. Here is the pattern:

```tsx
import {
  ElementType,
  ComponentPropsWithoutRef,
  ReactNode,
  forwardRef,
} from 'react';

// Step 1: Define the polymorphic type helper
type BoxOwnProps<C extends ElementType> = {
  as?: C;
  children?: ReactNode;
  padding?: 'sm' | 'md' | 'lg';
  bg?: string;
};

// Step 2: Combine own props with the HTML element's props
// Omit prevents conflicts between our props and HTML attributes
type BoxProps<C extends ElementType> = BoxOwnProps<C> &
  Omit<ComponentPropsWithoutRef<C>, keyof BoxOwnProps<C>>;

// Step 3: The component with a generic default
function Box<C extends ElementType = 'div'>({
  as,
  children,
  padding = 'md',
  bg,
  ...rest
}: BoxProps<C>) {
  const Component = as || 'div';

  const paddingMap = { sm: 8, md: 16, lg: 24 };

  return (
    <Component
      style={{
        padding: paddingMap[padding],
        background: bg,
      }}
      {...rest}
    >
      {children}
    </Component>
  );
}

// USAGE -- TypeScript enforces correct props for each element:

// Renders a <div> -- accepts div attributes
<Box padding="lg" bg="#f1f5f9" id="main-content">
  Default div
</Box>

// Renders an <a> tag -- href is valid
<Box as="a" href="/about" target="_blank" padding="sm">
  This is a link
</Box>

// Renders a <section> -- accepts section attributes
<Box as="section" aria-label="Features" padding="lg">
  Section content
</Box>

// Renders a <button> -- onClick and type are valid
<Box as="button" onClick={() => alert('hi')} type="submit">
  Click me
</Box>

// TYPE ERRORS -- these are caught at compile time:

// Error: 'href' does not exist on type 'IntrinsicAttributes & BoxProps<"div">'
// <Box href="/foo">Bad</Box>

// Error: 'type' does not exist on type 'IntrinsicAttributes & BoxProps<"a">'
// <Box as="a" type="submit">Bad</Box>
// (type="submit" is a button attribute, not an anchor attribute)
```

```tsx
// BONUS: Polymorphic component that also works with custom components

interface CardProps {
  title: string;
  elevated?: boolean;
}

function Card({ title, elevated }: CardProps) {
  return (
    <div className={elevated ? 'card elevated' : 'card'}>
      <h3>{title}</h3>
    </div>
  );
}

// Box can render as Card too -- it picks up CardProps
<Box as={Card} title="My Card" elevated padding="lg">
  Card content
</Box>

// Error: 'title' is required when using as={Card}
// <Box as={Card} padding="lg">Missing title</Box>
```

Why this pattern matters:
- **Design system components** (Box, Stack, Flex) need to render as different elements depending on context -- a Flex might be a `nav`, `ul`, or `div`
- **Type safety scales** -- adding a new `as` value automatically brings the correct prop types
- **No runtime overhead** -- all the checking happens at compile time
- Used by **Chakra UI, Radix, Mantine**, and other major component libraries'''
    },
    {
        "instruction": r'''What is the difference between React.FC and just typing the props parameter? I see both patterns in codebases and I am confused about which to use.''',
        "output": r'''<think>
This is a long-running debate in the React TypeScript community. Let me think about the actual differences.

React.FC<Props> (or React.FunctionComponent<Props>):
- Automatically includes children in the props type (in React 17 and earlier, NOT in React 18+)
- Provides a displayName property
- Returns ReactElement | null (enforced)
- Does not support generics easily

Plain function with typed props:
function MyComponent(props: MyProps): JSX.Element { ... }
- You explicitly add children if needed
- Supports generics naturally
- Simpler, more flexible

Wait, an important change happened in React 18. React.FC no longer implicitly includes children. So the main historical reason to avoid React.FC ("it adds implicit children") is no longer relevant in React 18+.

Hmm, but there is still the generics issue. If I want a generic component:
function List<T>(props: ListProps<T>) { ... } -- works fine
const List: React.FC<ListProps<T>> = ... -- cannot use generics with FC

I initially thought FC was just fine in React 18, but the generics limitation is still a real problem. Also, the React TypeScript cheatsheet recommends plain functions, and most modern codebases I have seen have moved away from FC.

The tradeoff: FC is slightly more explicit about the return type (prevents returning undefined or a string accidentally). But plain functions are more flexible and the community consensus has shifted toward them.

Let me show both and explain the practical differences so the user can make an informed choice.
</think>

In modern React (18+), plain function declarations are preferred over React.FC. Here is why:

```tsx
// APPROACH 1: React.FC (older pattern)
import { FC } from 'react';

interface GreetingProps {
  name: string;
  greeting?: string;
}

const Greeting: FC<GreetingProps> = ({ name, greeting = 'Hello' }) => {
  return <p>{greeting}, {name}!</p>;
};

// APPROACH 2: Plain function (recommended)
function Greeting({ name, greeting = 'Hello' }: GreetingProps) {
  return <p>{greeting}, {name}!</p>;
}

// Both work. Here is why plain functions are better:


// REASON 1: Generics work naturally
// Plain function -- generics just work
function List<T extends { id: string }>({
  items,
  renderItem,
}: {
  items: T[];
  renderItem: (item: T) => React.ReactNode;
}) {
  return (
    <ul>
      {items.map(item => (
        <li key={item.id}>{renderItem(item)}</li>
      ))}
    </ul>
  );
}

// Usage -- T is inferred from the items prop
<List
  items={[{ id: '1', name: 'Alice' }]}
  renderItem={item => <span>{item.name}</span>}
/>

// FC -- generics are awkward/impossible
// const List: FC<ListProps<???>> = ... // How do you parameterize this?


// REASON 2: Children must be explicit (React 18+)
// React.FC no longer includes children automatically in React 18
// Both approaches now require explicit children:

interface CardProps {
  title: string;
  children: React.ReactNode; // Must be explicit either way
}

function Card({ title, children }: CardProps) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {children}
    </div>
  );
}


// REASON 3: Default exports are cleaner
// Plain function
export default function Dashboard() {
  return <div>Dashboard</div>;
}

// FC requires a separate line
// const Dashboard: FC = () => { return <div>Dashboard</div>; };
// export default Dashboard;


// REASON 4: Overloaded signatures (advanced)
// Plain functions support multiple call signatures:
function Input(props: { type: 'text'; maxLength?: number }): JSX.Element;
function Input(props: { type: 'number'; min?: number; max?: number }): JSX.Element;
function Input(props: any) {
  return <input {...props} />;
}

// FC cannot do this at all
```

Summary:
| Feature | React.FC | Plain function |
|---|---|---|
| Generic components | Awkward / impossible | Natural |
| Children typing | Explicit (React 18+) | Explicit |
| Default props | Works | Works |
| Return type enforcement | Built-in | Add `: JSX.Element` if desired |
| Overloaded signatures | No | Yes |
| Community preference | Legacy | Recommended |

Use plain function declarations. The only thing React.FC gives you is an enforced return type, which you can add manually with `: JSX.Element` if you want that safety.'''
    },
]
