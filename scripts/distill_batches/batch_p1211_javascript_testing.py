"""
Batch P1211 -- JavaScript testing: Vitest, Testing Library, MSW mocking,
snapshot testing, E2E with Playwright.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Vitest setup and patterns ---
    {
        "instruction": r'''How do I set up Vitest for a TypeScript project and what are the best testing patterns? Show unit and integration test examples.''',
        "output": r'''<think>
Vitest is the modern Jest replacement for Vite projects. Key advantages:
native ESM, built-in TypeScript, same Vite config, Jest-compatible API,
faster startup. I should show config, a practical test (not "add 1+1"),
and mocking patterns.
</think>

Vitest provides Jest-compatible API with native TypeScript and ESM support:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.ts"],
    coverage: { provider: "v8", reporter: ["text", "html"] },
  },
});

// src/cart.ts
export class Cart {
  private items = new Map<string, { name: string; price: number; qty: number }>();

  add(id: string, name: string, price: number, qty = 1) {
    const existing = this.items.get(id);
    if (existing) existing.qty += qty;
    else this.items.set(id, { name, price, qty });
  }

  remove(id: string) { return this.items.delete(id); }

  get total() {
    let sum = 0;
    for (const item of this.items.values()) sum += item.price * item.qty;
    return Math.round(sum * 100) / 100;
  }

  get count() {
    let n = 0;
    for (const item of this.items.values()) n += item.qty;
    return n;
  }
}

// src/cart.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { Cart } from "./cart";

describe("Cart", () => {
  let cart: Cart;
  beforeEach(() => { cart = new Cart(); });

  it("starts empty", () => {
    expect(cart.total).toBe(0);
    expect(cart.count).toBe(0);
  });

  it("calculates total with quantities", () => {
    cart.add("1", "Widget", 9.99);
    cart.add("2", "Gadget", 24.99, 2);
    expect(cart.count).toBe(3);
    expect(cart.total).toBe(59.97);
  });

  it("merges duplicates", () => {
    cart.add("1", "Widget", 9.99);
    cart.add("1", "Widget", 9.99, 3);
    expect(cart.count).toBe(4);
  });

  it("removes items", () => {
    cart.add("1", "Widget", 9.99);
    expect(cart.remove("1")).toBe(true);
    expect(cart.remove("nope")).toBe(false);
  });
});
```

Run `npx vitest` (watch) or `npx vitest run` (CI). Vitest reuses Vite config for path aliases and transforms.'''
    },

    # --- 2. direct: Testing Library ---
    {
        "instruction": r'''Show how to test React components with Testing Library and Vitest, including user interactions and async rendering.''',
        "output": r'''Testing Library tests components the way users interact -- by role, label, and text:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LoginForm } from "./LoginForm";

describe("LoginForm", () => {
  it("renders fields and button", () => {
    render(<LoginForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows validation errors on empty submit", async () => {
    const user = userEvent.setup();
    render(<LoginForm onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
  });

  it("calls onSubmit with form data", async () => {
    const handleSubmit = vi.fn();
    const user = userEvent.setup();
    render(<LoginForm onSubmit={handleSubmit} />);
    await user.type(screen.getByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => {
      expect(handleSubmit).toHaveBeenCalledWith({
        email: "a@b.com", password: "secret123",
      });
    });
  });

  it("shows server error", async () => {
    const user = userEvent.setup();
    const fail = vi.fn().mockRejectedValue(new Error("Invalid credentials"));
    render(<LoginForm onSubmit={fail} />);
    await user.type(screen.getByLabelText(/email/i), "a@b.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/i);
  });
});
```

Key: query by role/label not test IDs, use `userEvent` not `fireEvent`, use `findBy` for async elements.'''
    },

    # --- 3. thinking: MSW mocking ---
    {
        "instruction": r'''How do I use MSW (Mock Service Worker) to mock API calls in tests and during development?''',
        "output": r'''<think>
MSW intercepts network requests at the service worker (browser) or
request interception (Node) level. Better than mocking fetch because
your code uses the real fetch, tests exercise the full cycle, and same
mocks work in tests and Storybook. I will use MSW v2 syntax.
</think>

MSW intercepts network requests so your code uses real `fetch` -- no mock wiring:

```typescript
// src/mocks/handlers.ts
import { http, HttpResponse, delay } from "msw";

export const handlers = [
  http.get("/api/users", async () => {
    await delay(100);
    return HttpResponse.json([
      { id: "1", name: "Alice" },
      { id: "2", name: "Bob" },
    ]);
  }),

  http.post("/api/users", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json(
      { id: "3", ...body }, { status: 201 }
    );
  }),
];

// src/mocks/server.ts -- for Vitest (Node)
import { setupServer } from "msw/node";
import { handlers } from "./handlers";
export const server = setupServer(...handlers);

// src/setupTests.ts
import { beforeAll, afterEach, afterAll } from "vitest";
import { server } from "./mocks/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Override for error scenarios in a single test
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

it("shows error when API fails", async () => {
  server.use(
    http.get("/api/users", () =>
      HttpResponse.json({ error: "Server error" }, { status: 500 })
    )
  );
  render(<UserList />);
  expect(await screen.findByText(/server error/i)).toBeInTheDocument();
  // Override resets after each test via afterEach()
});
```

Same handlers work in Vitest (Node), Storybook (browser), and development (service worker via `setupWorker`).'''
    },

    # --- 4. direct: Playwright E2E ---
    {
        "instruction": r'''Show how to write E2E tests with Playwright for a web application, including page objects and assertions.''',
        "output": r'''Playwright runs real browsers for end-to-end testing. Use page objects for structure:

```typescript
// e2e/pages/LoginPage.ts
import { type Page, type Locator } from "@playwright/test";

export class LoginPage {
  readonly email: Locator;
  readonly password: Locator;
  readonly submit: Locator;
  readonly error: Locator;

  constructor(readonly page: Page) {
    this.email = page.getByLabel("Email");
    this.password = page.getByLabel("Password");
    this.submit = page.getByRole("button", { name: "Sign In" });
    this.error = page.getByRole("alert");
  }

  async goto() { await this.page.goto("/login"); }

  async login(email: string, password: string) {
    await this.email.fill(email);
    await this.password.fill(password);
    await this.submit.click();
  }
}

// e2e/login.spec.ts
import { test, expect } from "@playwright/test";
import { LoginPage } from "./pages/LoginPage";

test("successful login redirects to dashboard", async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.login("alice@example.com", "password123");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page).toHaveURL("/dashboard");
});

test("invalid credentials show error", async ({ page }) => {
  const login = new LoginPage(page);
  await login.goto();
  await login.login("wrong@example.com", "bad");
  await expect(login.error).toHaveText("Invalid credentials");
  await expect(page).toHaveURL("/login");
});

// playwright.config.ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: "http://localhost:3000", trace: "on-first-retry" },
  webServer: { command: "npm run dev", port: 3000 },
});
```

Use `npx playwright test --ui` for interactive mode, `npx playwright codegen` to record tests by clicking.'''
    },

    # --- 5. direct: snapshot testing ---
    {
        "instruction": r'''When should I use snapshot testing in Vitest, and how do I handle snapshot updates?''',
        "output": r'''Snapshot testing captures output and compares against stored reference. Use for serializable outputs:

```typescript
import { describe, it, expect } from "vitest";

function formatError(err: { code: string; message: string; details?: Record<string, unknown> }): string {
  const lines = [`Error [${err.code}]: ${err.message}`];
  if (err.details) {
    for (const [k, v] of Object.entries(err.details)) {
      lines.push(`  ${k}: ${JSON.stringify(v)}`);
    }
  }
  return lines.join("\n");
}

describe("formatError", () => {
  it("formats basic error", () => {
    expect(formatError({ code: "AUTH", message: "Invalid token" }))
      .toMatchSnapshot();
  });

  // Inline snapshot -- stored in the test file itself
  it("formats inline", () => {
    expect(formatError({ code: "NOT_FOUND", message: "Missing" }))
      .toMatchInlineSnapshot('"Error [NOT_FOUND]: Missing"');
  });

  // Property matchers for dynamic values
  it("handles dynamic fields", () => {
    expect({
      id: crypto.randomUUID(),
      name: "Alice",
      createdAt: new Date().toISOString(),
    }).toMatchSnapshot({
      id: expect.any(String),
      createdAt: expect.any(String),
    });
  });
});

// Update when output intentionally changes:
// npx vitest run --update (or press 'u' in watch mode)

// GOOD for: formatters, serializers, component HTML
// BAD for: large objects, objects with timestamps, logic tests
// Always review snapshot diffs in code review
```

Use snapshots for pure formatters and component HTML. Avoid for logic tests. Never blindly update snapshots -- review diffs in PRs.'''
    },
]
