"""
Frontend thinking pairs - Frontend testing strategies
"""

pairs = [
    {
        "instruction": r'''I am new to testing React components. Should I test implementation details like state values and lifecycle methods, or should I test behavior? What does a good test look like?''',
        "output": r'''<think>
This is the fundamental question of React testing philosophy. Let me think about the two approaches.

Implementation testing: check that state has a specific value, that useEffect was called, that a specific handler function exists. This is what Enzyme encouraged -- shallow rendering and inspecting component internals.

Behavior testing: interact with the component the way a user would (click buttons, type text, read visible output) and verify the results. This is what React Testing Library encourages.

The problem with implementation testing is BRITTLENESS. If I refactor the component (change state structure, rename handlers, switch from useState to useReducer), all my tests break even though the component still works perfectly from the user's perspective. The tests are coupled to HOW the code works, not WHAT it does.

Behavior testing is resilient to refactoring. If I rewrite the internals completely but the component still renders the same output and responds to the same interactions, the tests pass. They test the contract, not the implementation.

Wait, should I NEVER test implementation details? Hmm, there are edge cases. Custom hooks that return values (not UI) might need unit tests that check return values. API integration logic might need tests that verify fetch calls. But for component RENDERING, behavior testing is almost always better.

I initially thought I should show both approaches and let the user decide, but actually the React community has strongly converged on behavior testing. Enzyme is essentially dead, React Testing Library is the standard. I should be clear about the recommendation while explaining WHY.

The tradeoff: behavior tests can be harder to write initially (you have to think about what the user sees), but they pay off massively in maintenance -- you can refactor freely without fixing tests.
</think>

Test behavior, not implementation. Write tests that interact with your component the way a user does -- click, type, read. Here is the difference:

```tsx
// The component under test
import { useState } from 'react';

interface Todo {
  id: number;
  text: string;
  done: boolean;
}

function TodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [input, setInput] = useState('');

  const addTodo = () => {
    if (!input.trim()) return;
    setTodos(prev => [
      ...prev,
      { id: Date.now(), text: input, done: false },
    ]);
    setInput('');
  };

  const toggleTodo = (id: number) => {
    setTodos(prev =>
      prev.map(t =>
        t.id === id ? { ...t, done: !t.done } : t
      )
    );
  };

  return (
    <div>
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        placeholder="Add a todo"
        aria-label="New todo"
      />
      <button onClick={addTodo}>Add</button>
      <ul>
        {todos.map(todo => (
          <li key={todo.id}>
            <label>
              <input
                type="checkbox"
                checked={todo.done}
                onChange={() => toggleTodo(todo.id)}
              />
              <span style={
                todo.done ? { textDecoration: 'line-through' } : {}
              }>
                {todo.text}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p>{todos.filter(t => !t.done).length} items remaining</p>
    </div>
  );
}
```

```tsx
// BAD: Testing implementation details
// These tests break when you refactor internals

test('BAD: checks internal state', () => {
  // Do NOT do this -- testing state values directly
  // If you rename 'todos' to 'items', this test breaks
  // even though the component still works
  const { result } = renderHook(() => useState([]));
  // ... inspecting state shape, checking handler names, etc.
});

// GOOD: Testing behavior -- what the user sees and does
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('adds a todo when user types and clicks Add', async () => {
  const user = userEvent.setup();
  render(<TodoList />);

  // Type into the input (the way a user would)
  const input = screen.getByLabelText('New todo');
  await user.type(input, 'Buy groceries');

  // Click the Add button
  await user.click(screen.getByRole('button', { name: 'Add' }));

  // Verify the todo appears in the list
  expect(screen.getByText('Buy groceries')).toBeInTheDocument();
  // Verify the input is cleared
  expect(input).toHaveValue('');
  // Verify the counter updated
  expect(screen.getByText('1 items remaining')).toBeInTheDocument();
});

test('toggles a todo between done and not done', async () => {
  const user = userEvent.setup();
  render(<TodoList />);

  // Add a todo first
  await user.type(screen.getByLabelText('New todo'), 'Walk dog');
  await user.click(screen.getByRole('button', { name: 'Add' }));

  // Check the checkbox
  const checkbox = screen.getByRole('checkbox');
  await user.click(checkbox);

  // Verify it is checked and counter says 0 remaining
  expect(checkbox).toBeChecked();
  expect(screen.getByText('0 items remaining')).toBeInTheDocument();

  // Uncheck it
  await user.click(checkbox);
  expect(checkbox).not.toBeChecked();
  expect(screen.getByText('1 items remaining')).toBeInTheDocument();
});

test('does not add empty todos', async () => {
  const user = userEvent.setup();
  render(<TodoList />);

  // Click Add without typing anything
  await user.click(screen.getByRole('button', { name: 'Add' }));

  // No list items should appear
  expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
  expect(screen.getByText('0 items remaining')).toBeInTheDocument();
});
```

Key principles:
- **Query by role/label**, not by class name or test-id (mirrors how screen readers and users find elements)
- **Use userEvent** instead of fireEvent (simulates real user interactions including focus, typing, clicking)
- **Assert on visible output**, not internal state
- **Each test tells a user story**: "when the user does X, they should see Y"'''
    },
    {
        "instruction": r'''How do I test a component that makes API calls? Should I mock fetch or use something like MSW?''',
        "output": r'''<think>
Testing components with API calls -- there are three main approaches:

1. Mock fetch/axios directly: jest.mock('fetch') or jest.spyOn(global, 'fetch'). Quick but tightly coupled to the HTTP library. If you switch from fetch to axios, all mocks break.

2. Mock the API layer: if you have an api.getUsers() function, mock that. Less coupled to the HTTP library but still requires knowing the exact function being called.

3. MSW (Mock Service Worker): intercepts requests at the network level. Your component code runs exactly as in production -- it calls fetch normally, and MSW intercepts the request before it leaves the browser. This is the most realistic approach.

Hmm, let me think about tradeoffs.

jest.mock is quick for simple cases but has downsides:
- Module mocking is fragile and hard to debug
- Tests do not verify the actual request URL, method, or body
- If you refactor which module makes the request, mocks break

MSW is more setup upfront but:
- Tests run the REAL component code with REAL fetch calls
- You can verify request details (URL, method, headers, body)
- Mocks are reusable across tests
- Same handlers work in tests AND in Storybook/dev mode

I initially thought MSW was overkill for simple tests, but actually the setup cost is about the same as jest.mock once you have a few endpoints. And MSW tests are much more maintainable.

Wait, there is a practical concern: MSW requires a service worker in the browser (for Storybook) and a server mock for Node (for Jest/Vitest). The Node setup uses msw/node, which is straightforward.

The tradeoff: MSW adds a dependency and initial setup time, but produces tests that are more realistic and resilient to refactoring. For a team writing many component tests with API calls, MSW pays for itself quickly.
</think>

Use MSW (Mock Service Worker) for the most realistic and maintainable API mocking. It intercepts network requests so your component runs exactly as in production.

```tsx
// Setup: install msw
// npm install -D msw

// 1. Define mock API handlers (reusable across all tests)
// src/mocks/handlers.ts
import { http, HttpResponse } from 'msw';

interface User {
  id: string;
  name: string;
  email: string;
}

const mockUsers: User[] = [
  { id: '1', name: 'Alice', email: 'alice@test.com' },
  { id: '2', name: 'Bob', email: 'bob@test.com' },
];

export const handlers = [
  http.get('/api/users', () => {
    return HttpResponse.json(mockUsers);
  }),

  http.post('/api/users', async ({ request }) => {
    const body = (await request.json()) as Partial<User>;
    const newUser = {
      id: String(Date.now()),
      name: body.name || '',
      email: body.email || '',
    };
    return HttpResponse.json(newUser, { status: 201 });
  }),

  http.delete('/api/users/:id', ({ params }) => {
    return HttpResponse.json({ deleted: params.id });
  }),
];

// 2. Setup MSW server for tests
// src/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);

// 3. Configure in test setup (vitest.setup.ts or jest.setup.ts)
// import { server } from './mocks/server';
// beforeAll(() => server.listen());
// afterEach(() => server.resetHandlers());
// afterAll(() => server.close());
```

```tsx
// 4. The component under test
function UserList() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/users')
      .then(res => {
        if (!res.ok) throw new Error('Failed to load users');
        return res.json();
      })
      .then(setUsers)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading users...</p>;
  if (error) return <p role="alert">Error: {error}</p>;

  return (
    <ul aria-label="User list">
      {users.map(u => (
        <li key={u.id}>{u.name} ({u.email})</li>
      ))}
    </ul>
  );
}
```

```tsx
// 5. The tests -- component runs REAL fetch, MSW intercepts it
import { render, screen, waitFor } from '@testing-library/react';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';

test('renders users after loading', async () => {
  render(<UserList />);

  // Initially shows loading state
  expect(screen.getByText('Loading users...')).toBeInTheDocument();

  // Wait for users to appear (MSW responds to the real fetch call)
  expect(await screen.findByText('Alice (alice@test.com)')).toBeInTheDocument();
  expect(screen.getByText('Bob (bob@test.com)')).toBeInTheDocument();

  // Loading state is gone
  expect(screen.queryByText('Loading users...')).not.toBeInTheDocument();
});

test('shows error message when API fails', async () => {
  // Override the handler for THIS test only
  server.use(
    http.get('/api/users', () => {
      return HttpResponse.json(
        { message: 'Server error' },
        { status: 500 }
      );
    })
  );

  render(<UserList />);

  // Wait for error message
  expect(
    await screen.findByRole('alert')
  ).toHaveTextContent('Error: Failed to load users');
});

test('shows empty state when no users exist', async () => {
  server.use(
    http.get('/api/users', () => {
      return HttpResponse.json([]);
    })
  );

  render(<UserList />);

  await waitFor(() => {
    expect(screen.queryByText('Loading users...')).not.toBeInTheDocument();
  });

  expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
});
```

Why MSW over jest.mock(fetch):
- **No mocking fetch directly** -- your component runs real fetch calls, making tests more realistic
- **Override per test** -- `server.use()` lets you simulate errors, empty responses, slow responses for specific tests
- **Reusable handlers** -- same mocks work in tests, Storybook, and local development
- **Implementation agnostic** -- switch from fetch to axios and your tests still work because MSW intercepts at the network level'''
    },
    {
        "instruction": r'''How do I decide what to test and what to skip in my React app? I cannot test everything and I need to prioritize.''',
        "output": r'''<think>
Testing prioritization is a crucial skill. Writing tests for everything is impractical -- you need to focus on what gives the most confidence per hour of effort.

Let me think about the testing pyramid/trophy for React apps:

The testing trophy (Kent C. Dodds' model):
- Top: E2E tests (few, slow, high confidence) -- Cypress/Playwright
- Middle: Integration tests (many, medium speed, high confidence) -- RTL
- Bottom: Unit tests (some, fast, lower confidence for UI) -- Jest
- Base: Static analysis (TypeScript, ESLint) -- free, always running

For React specifically, integration tests give the most bang for your buck. An integration test renders a component with its children, makes real interactions, and verifies results. It covers the most code with the least effort.

What should I prioritize testing? Let me think about risk:
1. Revenue-critical flows: checkout, payment, signup -- a bug here loses money
2. Complex logic: filters, sorting, form validation, calculations -- easy to get wrong
3. Edge cases in business logic: empty states, error states, boundary values
4. Shared components used everywhere: Button, Modal, Form -- a bug propagates widely

What should I SKIP?
1. Simple presentational components that just display props -- low risk, low value
2. Third-party library wrappers -- they test their own code
3. CSS/styling -- visual regression testing is a separate concern
4. Implementation details like "useState was called"

Hmm, wait -- I initially thought E2E tests for critical flows were optional, but actually for things like checkout and signup, E2E tests are the ONLY way to verify the full stack works. Integration tests mock the API, so they do not catch backend issues. E2E tests catch everything.

The 80/20 rule: integration tests for most components, E2E tests for the 3-5 most critical user flows, unit tests for complex utility functions, skip the rest.
</think>

Focus testing effort where bugs are most costly. Here is a practical prioritization framework:

```tsx
// PRIORITY 1: Critical user flows (integration tests)
// A bug here = lost revenue, lost users, or broken core experience

// Example: Checkout flow -- test the ENTIRE flow, not individual steps
test('user can complete checkout from cart to confirmation', async () => {
  const user = userEvent.setup();
  render(<CheckoutFlow />);

  // Step 1: Review cart
  expect(screen.getByText('Your Cart (2 items)')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Proceed to Checkout' }));

  // Step 2: Enter shipping info
  await user.type(screen.getByLabelText('Email'), 'test@example.com');
  await user.type(screen.getByLabelText('Address'), '123 Main St');
  await user.click(screen.getByRole('button', { name: 'Continue to Payment' }));

  // Step 3: Verify confirmation
  expect(await screen.findByText('Order Confirmed')).toBeInTheDocument();
  expect(screen.getByText('test@example.com')).toBeInTheDocument();
});


// PRIORITY 2: Complex business logic (unit tests)
// Calculations, validation, data transformations

// Example: Price calculation with discounts, tax, shipping
describe('calculateOrderTotal', () => {
  test('applies percentage discount before tax', () => {
    const result = calculateOrderTotal({
      items: [{ price: 100, quantity: 2 }],
      discount: { type: 'percent', value: 10 },
      taxRate: 0.08,
      shippingCost: 5.99,
    });
    // 200 - 10% = 180, + 8% tax = 194.40, + shipping = 200.39
    expect(result.total).toBeCloseTo(200.39);
  });

  test('free shipping over threshold', () => {
    const result = calculateOrderTotal({
      items: [{ price: 100, quantity: 1 }],
      discount: null,
      taxRate: 0.08,
      shippingCost: 5.99,
      freeShippingThreshold: 50,
    });
    expect(result.shippingCost).toBe(0);
  });
});


// PRIORITY 3: Shared components (integration tests)
// Components used in 10+ places -- a bug here affects everything

test('Modal traps focus and closes on Escape', async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();
  render(
    <Modal open={true} onClose={onClose} title="Settings">
      <input aria-label="Name" />
      <button>Save</button>
    </Modal>
  );

  // Focus is inside the modal
  expect(screen.getByLabelText('Name')).toHaveFocus();

  // Escape closes it
  await user.keyboard('{Escape}');
  expect(onClose).toHaveBeenCalledTimes(1);
});


// PRIORITY 4: Error states and edge cases
test('shows friendly error when API returns 500', async () => {
  server.use(
    http.get('/api/dashboard', () => {
      return HttpResponse.json(null, { status: 500 });
    })
  );
  render(<Dashboard />);
  expect(
    await screen.findByText('Something went wrong. Please try again.')
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
});

test('handles empty search results', async () => {
  const user = userEvent.setup();
  render(<SearchPage />);
  await user.type(screen.getByRole('searchbox'), 'xyznonexistent');
  expect(
    await screen.findByText('No results found')
  ).toBeInTheDocument();
});
```

```
WHAT TO TEST (high value):
  [x] User signup, login, checkout flows
  [x] Form validation (required fields, email format, etc.)
  [x] Data calculations (prices, dates, aggregations)
  [x] Error handling (API failures, empty states, network errors)
  [x] Shared components (Modal, Form, Table, Dropdown)
  [x] Accessibility (keyboard nav, ARIA attributes)

WHAT TO SKIP (low value):
  [ ] Simple presentational components (<Avatar>, <Badge>)
  [ ] Third-party component wrappers
  [ ] CSS/visual styling (use visual regression tools instead)
  [ ] Internal state values
  [ ] Console.log output
  [ ] Implementation of handlers (test their EFFECT, not their existence)
```

Time allocation:
- 50% integration tests (components with user interaction)
- 25% unit tests (business logic, utilities, calculations)
- 15% E2E tests (3-5 critical happy paths end-to-end)
- 10% edge case tests (errors, empty states, boundary values)'''
    },
    {
        "instruction": r'''How do I test a custom React hook? I have a useDebounce hook and I am not sure how to test it since hooks cannot run outside components.''',
        "output": r'''<think>
Testing custom hooks is tricky because hooks can only be called inside React components. You cannot just call useDebounce() in a test file.

The solutions:
1. renderHook from @testing-library/react-hooks (or @testing-library/react in v14+) -- creates a test component that renders the hook
2. Create a test component that uses the hook and test the component's output
3. If the hook has pure logic, extract that into a plain function and test the function

For a useDebounce hook specifically, there is an additional challenge: it uses setTimeout, so tests need to deal with timers. Options:
- jest.useFakeTimers() -- lets you control time advancement
- waitFor with real timers -- slower but more realistic

Hmm, let me think about which approach is best for useDebounce.

The hook probably takes a value and a delay, and returns the debounced value after the delay has passed. Like:
const debouncedSearch = useDebounce(searchTerm, 300);

To test this, I need to:
1. Render the hook with an initial value
2. Update the value (simulating user typing)
3. Verify the debounced value has NOT changed yet
4. Advance time by the delay amount
5. Verify the debounced value HAS changed

I initially thought fake timers would be cleanest, but actually there is a gotcha: fake timers can interfere with React's internal scheduling. In React 18 with concurrent features, fake timers can cause unexpected behavior. The solution is to use jest.useFakeTimers() but advance time using act() to ensure React processes all updates.

Wait, actually the renderHook approach from @testing-library/react (v14+) handles this well. It returns a result ref that always has the current hook return value, and you can call rerender() to update props.

The tradeoff: renderHook is cleaner for testing the hook in isolation. Testing through a component is more realistic but more setup.
</think>

Use `renderHook` from React Testing Library to test hooks in isolation. For debounce, combine it with fake timers to control time.

```tsx
// The hook under test
import { useState, useEffect } from 'react';

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

export { useDebounce };
```

```tsx
// The tests
import { renderHook, act } from '@testing-library/react';
import { useDebounce } from './useDebounce';

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

test('returns initial value immediately', () => {
  const { result } = renderHook(() =>
    useDebounce('hello', 500)
  );

  // Debounced value starts with the initial value
  expect(result.current).toBe('hello');
});

test('does not update value before delay has passed', () => {
  const { result, rerender } = renderHook(
    ({ value, delay }) => useDebounce(value, delay),
    { initialProps: { value: 'hello', delay: 500 } }
  );

  // Change the input value
  rerender({ value: 'hello world', delay: 500 });

  // Advance time but NOT past the delay
  act(() => {
    jest.advanceTimersByTime(300);
  });

  // Debounced value should still be the old value
  expect(result.current).toBe('hello');
});

test('updates value after delay has passed', () => {
  const { result, rerender } = renderHook(
    ({ value, delay }) => useDebounce(value, delay),
    { initialProps: { value: 'hello', delay: 500 } }
  );

  // Change the input value
  rerender({ value: 'hello world', delay: 500 });

  // Advance time past the delay
  act(() => {
    jest.advanceTimersByTime(500);
  });

  // Now the debounced value should be updated
  expect(result.current).toBe('hello world');
});

test('resets timer when value changes rapidly', () => {
  const { result, rerender } = renderHook(
    ({ value, delay }) => useDebounce(value, delay),
    { initialProps: { value: 'a', delay: 500 } }
  );

  // Simulate rapid typing: value changes every 100ms
  rerender({ value: 'ab', delay: 500 });
  act(() => { jest.advanceTimersByTime(100); });

  rerender({ value: 'abc', delay: 500 });
  act(() => { jest.advanceTimersByTime(100); });

  rerender({ value: 'abcd', delay: 500 });
  act(() => { jest.advanceTimersByTime(100); });

  // 300ms total elapsed, but the timer was reset each time
  // so debounced value should still be 'a'
  expect(result.current).toBe('a');

  // Advance past the delay from the last change
  act(() => { jest.advanceTimersByTime(500); });

  // Now it should be the final value
  expect(result.current).toBe('abcd');
});

test('cleans up timer on unmount', () => {
  const { result, unmount, rerender } = renderHook(
    ({ value, delay }) => useDebounce(value, delay),
    { initialProps: { value: 'hello', delay: 500 } }
  );

  rerender({ value: 'changed', delay: 500 });

  // Unmount before timer fires
  unmount();

  // Advancing timers should not cause errors
  // (no setState on unmounted component)
  act(() => {
    jest.advanceTimersByTime(500);
  });

  // No error thrown -- cleanup worked
});
```

Key patterns:
- **renderHook** creates a minimal component wrapper so hooks can run
- **result.current** always has the latest return value
- **rerender** with new props simulates the parent passing new values
- **act()** wraps timer advances so React processes state updates
- **jest.useFakeTimers()** gives you control over setTimeout without waiting
- **Cleanup test** verifies no memory leaks when component unmounts mid-debounce'''
    },
    {
        "instruction": r'''What is the difference between unit tests and integration tests for React components? When should I write each?''',
        "output": r'''<think>
The line between unit and integration tests in React is blurry, and honestly the terminology causes more confusion than clarity. Let me think about what these actually mean in the React context.

Traditional software engineering:
- Unit test: tests one function/class in isolation, mocks all dependencies
- Integration test: tests multiple units working together

In React:
- "Unit test" could mean: testing a single component with all children mocked/stubbed
- "Integration test" could mean: testing a component WITH its real children, testing how they compose together

But here is the thing: React Testing Library does not really support shallow rendering (that was Enzyme's thing). When you render(<UserProfile />), it renders ALL child components too. So almost every RTL test is technically an integration test.

Hmm, I think the more useful distinction for React developers is:
1. Component tests (RTL): render a component tree, interact with it, check visible output. These ARE integration tests but people often call them "unit tests."
2. Hook/utility tests: test a custom hook or utility function in isolation. These are true unit tests.
3. Page/feature tests: render an entire page or feature, mock the API layer, test a complete user flow. These are higher-level integration tests.
4. E2E tests: test the full app including the real backend. Cypress/Playwright.

I initially thought I should define strict boundaries, but actually Kent C. Dodds' advice is good here: "Write tests. Not too many. Mostly integration." Focus on the integration level because it gives the most confidence per test.

The tradeoff: pure unit tests run faster but catch fewer bugs (they miss interaction bugs). Integration tests are slower but catch more real-world issues. E2E tests are slowest but test the full stack.
</think>

In React, the line between unit and integration tests is blurry. Here is a practical framework:

```tsx
// UNIT TEST: Pure logic with no React
// Test utility functions, calculations, transformers in isolation
// Fast, focused, no DOM needed

// utils/formatPrice.ts
export function formatPrice(cents: number, currency: string): string {
  const dollars = cents / 100;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(dollars);
}

// utils/formatPrice.test.ts
describe('formatPrice', () => {
  test('formats cents to dollars', () => {
    expect(formatPrice(1999, 'USD')).toBe('$19.99');
  });
  test('handles zero', () => {
    expect(formatPrice(0, 'USD')).toBe('$0.00');
  });
  test('handles large amounts', () => {
    expect(formatPrice(1000000, 'USD')).toBe('$10,000.00');
  });
});


// INTEGRATION TEST: Component with real children
// Renders the full component tree, mocks external boundaries (API)
// Tests that components WORK TOGETHER correctly

// ProductCard + AddToCartButton + QuantitySelector working together
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('product card lets user select quantity and add to cart', async () => {
  const user = userEvent.setup();
  const onAddToCart = jest.fn();

  // Renders ProductCard AND its children (QuantitySelector, Button)
  // This is NOT mocking children -- they are real components
  render(
    <CartProvider>
      <ProductCard
        product={{
          id: '1',
          name: 'Keyboard',
          price: 7999,
          imageUrl: '/kb.jpg',
        }}
        onAddToCart={onAddToCart}
      />
    </CartProvider>
  );

  // Verify product info renders (ProductCard + PriceDisplay working together)
  expect(screen.getByText('Keyboard')).toBeInTheDocument();
  expect(screen.getByText('$79.99')).toBeInTheDocument();

  // Increase quantity (QuantitySelector component)
  await user.click(screen.getByRole('button', { name: 'Increase quantity' }));
  await user.click(screen.getByRole('button', { name: 'Increase quantity' }));
  expect(screen.getByText('3')).toBeInTheDocument();

  // Add to cart (AddToCartButton component)
  await user.click(screen.getByRole('button', { name: 'Add to Cart' }));
  expect(onAddToCart).toHaveBeenCalledWith('1', 3);
});


// PAGE-LEVEL INTEGRATION TEST: Full feature with API mocking
// Tests an entire user flow across multiple components

test('search page: user searches, filters, and views results', async () => {
  // MSW handles API mocking at the network level
  server.use(
    http.get('/api/search', ({ request }) => {
      const url = new URL(request.url);
      const q = url.searchParams.get('q');
      if (q === 'keyboard') {
        return HttpResponse.json({
          results: [
            { id: '1', name: 'Mechanical Keyboard', price: 7999 },
            { id: '2', name: 'Wireless Keyboard', price: 4999 },
          ],
          total: 2,
        });
      }
      return HttpResponse.json({ results: [], total: 0 });
    })
  );

  const user = userEvent.setup();
  render(<SearchPage />);

  // Type search query
  await user.type(screen.getByRole('searchbox'), 'keyboard');
  await user.click(screen.getByRole('button', { name: 'Search' }));

  // Verify results appeared
  expect(await screen.findByText('Mechanical Keyboard')).toBeInTheDocument();
  expect(screen.getByText('2 results')).toBeInTheDocument();

  // Apply filter
  await user.click(screen.getByLabelText('Under $60'));
  expect(screen.getByText('Wireless Keyboard')).toBeInTheDocument();
  expect(screen.queryByText('Mechanical Keyboard')).not.toBeInTheDocument();
});
```

When to use each:

| Test type | What to test | Speed | Confidence |
|---|---|---|---|
| Unit | Utility functions, calculations, formatters | Fastest | Low (no interaction) |
| Integration | Component trees, user flows within a feature | Medium | High |
| E2E | Critical paths (signup, checkout, payment) | Slow | Highest |

The practical advice: **write mostly integration tests.** They render real component trees with real interactions and give the most confidence that your app actually works. Save unit tests for pure logic and E2E tests for the 3-5 most important user journeys.'''
    },
]
