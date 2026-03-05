"""E2E testing — Playwright, visual regression, and accessibility testing."""

PAIRS = [
    (
        "testing/playwright",
        "Show Playwright E2E testing patterns: page interactions, assertions, fixtures, and API testing.",
        """Playwright E2E testing patterns:

```typescript
import { test, expect, type Page } from '@playwright/test';


// --- Basic page interaction and assertions ---

test('user can log in and see dashboard', async ({ page }) => {
  await page.goto('/login');

  // Fill form
  await page.getByLabel('Email').fill('user@example.com');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign In' }).click();

  // Wait for navigation
  await page.waitForURL('/dashboard');

  // Assert content
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('Welcome, User')).toBeVisible();
});


// --- Page Object Model ---

class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login');
  }

  async login(email: string, password: string) {
    await this.page.getByLabel('Email').fill(email);
    await this.page.getByLabel('Password').fill(password);
    await this.page.getByRole('button', { name: 'Sign In' }).click();
  }

  async expectError(message: string) {
    await expect(this.page.getByRole('alert')).toContainText(message);
  }
}

class DashboardPage {
  constructor(private page: Page) {}

  async expectVisible() {
    await expect(this.page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  }

  async getStatCount(label: string): Promise<string> {
    return this.page.getByTestId(`stat-${label}`).innerText();
  }
}

test('login with page objects', async ({ page }) => {
  const loginPage = new LoginPage(page);
  const dashboard = new DashboardPage(page);

  await loginPage.goto();
  await loginPage.login('admin@test.com', 'admin123');
  await dashboard.expectVisible();
});


// --- Fixtures for shared setup ---

type TestFixtures = {
  authenticatedPage: Page;
};

const authTest = test.extend<TestFixtures>({
  authenticatedPage: async ({ page }, use) => {
    // Login via API (faster than UI login)
    const response = await page.request.post('/api/auth/login', {
      data: { email: 'test@example.com', password: 'pass123' },
    });
    const { token } = await response.json();

    // Set auth cookie/header
    await page.context().addCookies([{
      name: 'auth_token',
      value: token,
      domain: 'localhost',
      path: '/',
    }]);

    await use(page);
  },
});

authTest('authenticated user sees profile', async ({ authenticatedPage }) => {
  await authenticatedPage.goto('/profile');
  await expect(authenticatedPage.getByText('test@example.com')).toBeVisible();
});


// --- Network interception ---

test('handles API errors gracefully', async ({ page }) => {
  // Mock failed API response
  await page.route('/api/users', (route) =>
    route.fulfill({
      status: 500,
      body: JSON.stringify({ error: 'Internal Server Error' }),
    })
  );

  await page.goto('/users');
  await expect(page.getByText('Failed to load users')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('intercept and modify response', async ({ page }) => {
  await page.route('/api/users', async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    // Inject test data
    json.push({ id: 999, name: 'Test User' });
    await route.fulfill({ json });
  });

  await page.goto('/users');
  await expect(page.getByText('Test User')).toBeVisible();
});


// --- Wait patterns ---

test('wait for specific conditions', async ({ page }) => {
  await page.goto('/dashboard');

  // Wait for network idle
  await page.waitForLoadState('networkidle');

  // Wait for specific request
  const responsePromise = page.waitForResponse('/api/stats');
  await page.getByRole('button', { name: 'Refresh' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);

  // Wait for element state
  await page.getByTestId('loading-spinner').waitFor({ state: 'hidden' });
  await expect(page.getByTestId('data-table')).toBeVisible();
});


// --- Screenshot testing ---

test('visual regression', async ({ page }) => {
  await page.goto('/components');
  await expect(page).toHaveScreenshot('components-page.png', {
    maxDiffPixelRatio: 0.01,
  });

  // Screenshot specific element
  const card = page.getByTestId('user-card');
  await expect(card).toHaveScreenshot('user-card.png');
});
```

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'] } },
  ],

  webServer: {
    command: 'npm run dev',
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
```

Playwright patterns:
1. **`getByRole()` / `getByLabel()`** — accessible locators are more resilient than CSS selectors
2. **Page Object Model** — encapsulate page interactions for reuse across tests
3. **API-based auth fixture** — login via API is faster than UI flow for test setup
4. **`page.route()`** — intercept network requests to test error states and edge cases
5. **`toHaveScreenshot()`** — visual regression testing with configurable diff threshold"""
    ),
    (
        "testing/accessibility",
        "Show accessibility testing patterns: axe-core integration, ARIA testing, keyboard navigation, and screen reader testing.",
        """Accessibility testing patterns:

```typescript
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';


// --- Automated accessibility scanning with axe ---

test('homepage has no accessibility violations', async ({ page }) => {
  await page.goto('/');

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();

  expect(results.violations).toEqual([]);
});

test('form page meets WCAG AA', async ({ page }) => {
  await page.goto('/contact');

  const results = await new AxeBuilder({ page })
    .include('.contact-form')   // Scan specific section
    .exclude('.third-party-widget')  // Skip known issues
    .analyze();

  // Log violations for debugging
  for (const violation of results.violations) {
    console.log(`${violation.id}: ${violation.description}`);
    for (const node of violation.nodes) {
      console.log(`  - ${node.html}`);
      console.log(`    Fix: ${node.failureSummary}`);
    }
  }

  expect(results.violations).toHaveLength(0);
});


// --- Keyboard navigation testing ---

test('modal can be used with keyboard only', async ({ page }) => {
  await page.goto('/dashboard');

  // Open modal with keyboard
  await page.getByRole('button', { name: 'Add Item' }).focus();
  await page.keyboard.press('Enter');

  // Verify focus is trapped in modal
  const modal = page.getByRole('dialog');
  await expect(modal).toBeVisible();

  // First focusable element should be focused
  const closeButton = modal.getByRole('button', { name: 'Close' });
  await expect(closeButton).toBeFocused();

  // Tab through all focusable elements
  await page.keyboard.press('Tab');
  await expect(modal.getByLabel('Item Name')).toBeFocused();

  await page.keyboard.press('Tab');
  await expect(modal.getByLabel('Description')).toBeFocused();

  await page.keyboard.press('Tab');
  await expect(modal.getByRole('button', { name: 'Save' })).toBeFocused();

  // Tab should cycle back to close button (focus trap)
  await page.keyboard.press('Tab');
  await expect(closeButton).toBeFocused();

  // Escape closes modal
  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden();

  // Focus returns to trigger button
  await expect(page.getByRole('button', { name: 'Add Item' })).toBeFocused();
});


// --- ARIA attributes testing ---

test('dropdown has correct ARIA attributes', async ({ page }) => {
  await page.goto('/components');

  const trigger = page.getByRole('button', { name: 'Options' });
  const menu = page.getByRole('menu');

  // Closed state
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
  await expect(menu).toBeHidden();

  // Open
  await trigger.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(menu).toBeVisible();

  // Menu items
  const items = menu.getByRole('menuitem');
  await expect(items).toHaveCount(3);

  // Arrow key navigation
  await page.keyboard.press('ArrowDown');
  await expect(items.first()).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(items.nth(1)).toBeFocused();
});


test('form validation announces errors to screen readers', async ({ page }) => {
  await page.goto('/register');

  // Submit empty form
  await page.getByRole('button', { name: 'Submit' }).click();

  // Error messages linked via aria-describedby
  const emailInput = page.getByLabel('Email');
  const errorId = await emailInput.getAttribute('aria-describedby');
  expect(errorId).toBeTruthy();

  const errorMsg = page.locator(`#${errorId}`);
  await expect(errorMsg).toHaveText('Email is required');

  // Input marked as invalid
  await expect(emailInput).toHaveAttribute('aria-invalid', 'true');

  // Live region announces error
  const liveRegion = page.locator('[role="alert"]');
  await expect(liveRegion).toContainText('Please fix the errors');
});


// --- Color contrast and visual checks ---

test('text meets contrast requirements', async ({ page }) => {
  await page.goto('/');

  const results = await new AxeBuilder({ page })
    .withRules(['color-contrast'])
    .analyze();

  expect(results.violations).toEqual([]);
});
```

Accessibility testing patterns:
1. **axe-core** — automated WCAG scanning catches ~57% of a11y issues
2. **`withTags(['wcag2aa'])`** — test against specific WCAG conformance levels
3. **Focus trap testing** — verify Tab cycles within modals, Escape closes them
4. **`aria-expanded`/`aria-haspopup`** — assert correct ARIA states on interactive widgets
5. **`aria-describedby` + `role="alert"`** — verify form errors are screen-reader accessible"""
    ),
    (
        "testing/load-testing",
        "Show load testing patterns: k6 scripts, performance metrics, ramp-up scenarios, and threshold checking.",
        """Load testing patterns with k6:

```javascript
// load-test.js — k6 load test script
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const loginDuration = new Trend('login_duration');
const apiCalls = new Counter('api_calls');


// --- Test configuration ---

export const options = {
  // Ramp-up scenario
  stages: [
    { duration: '1m',  target: 50 },   // Ramp up to 50 users
    { duration: '3m',  target: 50 },   // Stay at 50 users
    { duration: '1m',  target: 200 },  // Spike to 200 users
    { duration: '3m',  target: 200 },  // Stay at 200
    { duration: '2m',  target: 0 },    // Ramp down
  ],

  // Performance thresholds (fail CI if exceeded)
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],  // 95th < 500ms
    errors: ['rate<0.01'],                             // Error rate < 1%
    login_duration: ['p(95)<1000'],                    // Login < 1s at p95
  },
};


// --- Setup (runs once before test) ---

export function setup() {
  const loginRes = http.post(`${__ENV.BASE_URL}/api/auth/login`, JSON.stringify({
    email: 'loadtest@example.com',
    password: 'testpass123',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  const token = loginRes.json('token');
  return { token };
}


// --- Main test function (runs per virtual user) ---

export default function (data) {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:3000';
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  group('API endpoints', () => {
    // GET users list
    const usersRes = http.get(`${baseUrl}/api/users`, { headers });
    apiCalls.add(1);
    check(usersRes, {
      'users: status 200': (r) => r.status === 200,
      'users: has data': (r) => r.json('data').length > 0,
    }) || errorRate.add(1);

    sleep(1);  // Think time between requests

    // GET single user
    const userRes = http.get(`${baseUrl}/api/users/1`, { headers });
    apiCalls.add(1);
    check(userRes, {
      'user: status 200': (r) => r.status === 200,
      'user: has name': (r) => r.json('name') !== '',
    }) || errorRate.add(1);

    sleep(0.5);

    // POST create item
    const createRes = http.post(`${baseUrl}/api/items`, JSON.stringify({
      name: `Item ${Date.now()}`,
      price: Math.random() * 100,
    }), { headers });
    apiCalls.add(1);
    check(createRes, {
      'create: status 201': (r) => r.status === 201,
    }) || errorRate.add(1);
  });

  group('Login flow', () => {
    const start = Date.now();
    const loginRes = http.post(`${baseUrl}/api/auth/login`, JSON.stringify({
      email: `user${__VU}@example.com`,
      password: 'password123',
    }), {
      headers: { 'Content-Type': 'application/json' },
    });

    loginDuration.add(Date.now() - start);
    check(loginRes, {
      'login: status 200': (r) => r.status === 200,
      'login: has token': (r) => r.json('token') !== '',
    }) || errorRate.add(1);
  });

  sleep(Math.random() * 3 + 1);  // Random think time 1-4s
}


// --- Teardown (runs once after test) ---

export function teardown(data) {
  // Clean up test data
  http.del(`${__ENV.BASE_URL}/api/test/cleanup`, null, {
    headers: { 'Authorization': `Bearer ${data.token}` },
  });
}
```

```bash
# Run load test
k6 run --env BASE_URL=http://localhost:3000 load-test.js

# Run with output to InfluxDB/Grafana
k6 run --out influxdb=http://localhost:8086/k6 load-test.js

# Run specific scenario with more VUs
k6 run --vus 100 --duration 5m load-test.js
```

Load testing patterns:
1. **`stages`** — ramp-up/spike/ramp-down simulates realistic traffic patterns
2. **`thresholds`** — auto-fail CI if p95 latency or error rate exceeds limits
3. **`check()`** — assert response status and body per request
4. **Custom metrics** — `Trend` for latency distributions, `Rate` for error rates
5. **`sleep()`** — think time between requests simulates real user behavior"""
    ),
]
