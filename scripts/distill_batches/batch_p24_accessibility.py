"""Web accessibility — ARIA, semantic HTML, screen readers, testing, WCAG compliance."""

PAIRS = [
    (
        "web/accessibility-fundamentals",
        "Explain web accessibility best practices: semantic HTML, ARIA roles, keyboard navigation, and WCAG 2.1 compliance with practical examples.",
        '''Building accessible web applications:

```html
<!-- --- Semantic HTML (the foundation) --- -->

<!-- BAD: div soup -->
<div class="header">
    <div class="nav">
        <div class="nav-item" onclick="goHome()">Home</div>
    </div>
</div>
<div class="content">
    <div class="title">Article Title</div>
    <div class="text">Content here...</div>
</div>

<!-- GOOD: semantic elements -->
<header>
    <nav aria-label="Main navigation">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/about">About</a></li>
        </ul>
    </nav>
</header>
<main>
    <article>
        <h1>Article Title</h1>
        <p>Content here...</p>
    </article>
</main>
<footer>
    <p>&copy; 2024 Company</p>
</footer>
```

```javascript
// --- Accessible Components ---

// 1. Accessible Modal Dialog
class AccessibleModal {
    constructor(dialogEl) {
        this.dialog = dialogEl;
        this.previousFocus = null;
        this.focusableSelector =
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    }

    open() {
        this.previousFocus = document.activeElement;
        this.dialog.setAttribute('role', 'dialog');
        this.dialog.setAttribute('aria-modal', 'true');
        this.dialog.removeAttribute('hidden');

        // Trap focus inside modal
        const focusable = this.dialog.querySelectorAll(this.focusableSelector);
        if (focusable.length) focusable[0].focus();

        // Handle keyboard
        this.dialog.addEventListener('keydown', this._handleKeydown.bind(this));

        // Announce to screen readers
        this.dialog.setAttribute('aria-live', 'assertive');
    }

    close() {
        this.dialog.setAttribute('hidden', '');
        this.dialog.removeEventListener('keydown', this._handleKeydown);
        // Restore focus to trigger element
        if (this.previousFocus) this.previousFocus.focus();
    }

    _handleKeydown(e) {
        if (e.key === 'Escape') {
            this.close();
            return;
        }
        if (e.key === 'Tab') {
            const focusable = [...this.dialog.querySelectorAll(this.focusableSelector)];
            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    }
}

// 2. Accessible Dropdown Menu
// HTML:
// <div role="combobox" aria-expanded="false" aria-haspopup="listbox">
//     <input type="text" aria-autocomplete="list" aria-controls="options-list">
//     <ul id="options-list" role="listbox" hidden>
//         <li role="option" id="opt-1">Option 1</li>
//         <li role="option" id="opt-2">Option 2</li>
//     </ul>
// </div>

class AccessibleCombobox {
    constructor(container) {
        this.container = container;
        this.input = container.querySelector('input');
        this.listbox = container.querySelector('[role="listbox"]');
        this.options = [...this.listbox.querySelectorAll('[role="option"]')];
        this.activeIndex = -1;

        this.input.addEventListener('keydown', this._onKeydown.bind(this));
        this.options.forEach((opt, i) => {
            opt.addEventListener('click', () => this._select(i));
        });
    }

    _onKeydown(e) {
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this._navigate(1);
                break;
            case 'ArrowUp':
                e.preventDefault();
                this._navigate(-1);
                break;
            case 'Enter':
                if (this.activeIndex >= 0) this._select(this.activeIndex);
                break;
            case 'Escape':
                this._close();
                break;
        }
    }

    _navigate(direction) {
        this._open();
        this.activeIndex = Math.max(0,
            Math.min(this.options.length - 1, this.activeIndex + direction));
        this.options.forEach(o => o.removeAttribute('aria-selected'));
        this.options[this.activeIndex].setAttribute('aria-selected', 'true');
        this.input.setAttribute('aria-activedescendant',
            this.options[this.activeIndex].id);
    }

    _select(index) {
        this.input.value = this.options[index].textContent;
        this._close();
    }

    _open() {
        this.listbox.removeAttribute('hidden');
        this.container.setAttribute('aria-expanded', 'true');
    }

    _close() {
        this.listbox.setAttribute('hidden', '');
        this.container.setAttribute('aria-expanded', 'false');
        this.activeIndex = -1;
    }
}

// --- Live Regions for Dynamic Content ---

// Polite: announced after current speech finishes
// <div aria-live="polite" aria-atomic="true" id="status">
//     5 results found
// </div>

// Assertive: interrupts current speech (use sparingly)
// <div aria-live="assertive" role="alert" id="error">
//     Error: Invalid email address
// </div>

function announceToScreenReader(message, priority = 'polite') {
    const el = document.getElementById(
        priority === 'assertive' ? 'error' : 'status'
    );
    el.textContent = '';  // Clear first to trigger re-announcement
    requestAnimationFrame(() => {
        el.textContent = message;
    });
}

// --- Color and Contrast ---

function checkContrast(foreground, background) {
    // WCAG 2.1 contrast ratios:
    // Normal text: 4.5:1 (AA), 7:1 (AAA)
    // Large text (18pt+): 3:1 (AA), 4.5:1 (AAA)
    // Non-text (icons, borders): 3:1 (AA)

    const lumFg = relativeLuminance(foreground);
    const lumBg = relativeLuminance(background);
    const lighter = Math.max(lumFg, lumBg);
    const darker = Math.min(lumFg, lumBg);
    return (lighter + 0.05) / (darker + 0.05);
}
```

WCAG 2.1 quick checklist:
- **Perceivable**: alt text, captions, sufficient contrast (4.5:1)
- **Operable**: keyboard navigable, no time limits, skip links
- **Understandable**: consistent navigation, error identification, labels
- **Robust**: valid HTML, ARIA when needed, works with assistive tech

Testing tools:
- **axe-core** — automated accessibility testing
- **Lighthouse** — Chrome accessibility audit
- **NVDA/VoiceOver** — manual screen reader testing
- **Tab through entire page** — verify keyboard accessibility'''
    ),
    (
        "web/accessibility-testing-automation",
        "Show how to automate accessibility testing with axe-core, Playwright, and CI integration.",
        '''Automated accessibility testing in CI/CD:

```python
# --- Playwright + axe-core accessibility tests ---
# test_accessibility.py

import pytest
from playwright.sync_api import sync_playwright
from axe_playwright_python.sync_playwright import Axe

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()

@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()

def run_axe(page, url: str, rules_to_check: list[str] = None) -> dict:
    """Run axe-core accessibility audit on a page."""
    page.goto(url)
    page.wait_for_load_state("networkidle")

    axe = Axe()
    results = axe.run(page)

    violations = results.response.get("violations", [])
    return {
        "url": url,
        "violations": violations,
        "violation_count": len(violations),
        "critical": [v for v in violations if v["impact"] == "critical"],
        "serious": [v for v in violations if v["impact"] == "serious"],
    }

class TestAccessibility:
    BASE_URL = "http://localhost:3000"

    def test_homepage_no_critical_violations(self, page):
        results = run_axe(page, f"{self.BASE_URL}/")
        critical = results["critical"]
        assert len(critical) == 0, (
            f"Critical violations: {format_violations(critical)}"
        )

    def test_login_page_accessible(self, page):
        results = run_axe(page, f"{self.BASE_URL}/login")
        assert results["violation_count"] == 0

    def test_dashboard_keyboard_navigation(self, page):
        page.goto(f"{self.BASE_URL}/dashboard")

        # Tab through interactive elements
        tab_order = []
        for _ in range(20):
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.tagName + '#' + document.activeElement.id")
            tab_order.append(focused)

        # Verify skip link is first
        assert "skip" in tab_order[0].lower()

        # Verify all interactive elements are reachable
        buttons = page.query_selector_all("button:not([disabled])")
        links = page.query_selector_all("a[href]")
        assert len(tab_order) >= len(buttons) + len(links)

    def test_form_labels_and_errors(self, page):
        page.goto(f"{self.BASE_URL}/register")

        # Check all inputs have labels
        inputs = page.query_selector_all("input:not([type=hidden])")
        for inp in inputs:
            input_id = inp.get_attribute("id")
            label = page.query_selector(f'label[for="{input_id}"]')
            aria_label = inp.get_attribute("aria-label")
            aria_labelledby = inp.get_attribute("aria-labelledby")
            assert label or aria_label or aria_labelledby, (
                f"Input #{input_id} has no accessible label"
            )

        # Submit empty form and check error announcements
        page.click("button[type=submit]")
        page.wait_for_selector("[role=alert]")

        # Verify errors are associated with inputs
        errors = page.query_selector_all("[role=alert]")
        assert len(errors) > 0

    def test_color_contrast(self, page):
        """Check text elements meet WCAG AA contrast."""
        results = run_axe(page, f"{self.BASE_URL}/")
        contrast_violations = [
            v for v in results["violations"]
            if v["id"] == "color-contrast"
        ]
        assert len(contrast_violations) == 0, (
            f"Contrast failures: {format_violations(contrast_violations)}"
        )

    def test_images_have_alt_text(self, page):
        page.goto(f"{self.BASE_URL}/")
        images = page.query_selector_all("img")
        for img in images:
            alt = img.get_attribute("alt")
            role = img.get_attribute("role")
            # Images must have alt text OR role="presentation" for decorative
            assert alt is not None or role == "presentation", (
                f"Image missing alt text: {img.get_attribute('src')}"
            )

def format_violations(violations: list) -> str:
    lines = []
    for v in violations:
        lines.append(f"  [{v['impact']}] {v['id']}: {v['description']}")
        for node in v.get("nodes", [])[:3]:
            lines.append(f"    Element: {node.get('html', '')[:100]}")
    return "\\n".join(lines)
```

```yaml
# CI integration — .github/workflows/a11y.yml
name: Accessibility Tests
on: [pull_request]
jobs:
  a11y:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci && npm run build
      - run: npm start &
      - name: Wait for server
        run: npx wait-on http://localhost:3000 --timeout 30000
      - run: pip install playwright axe-playwright-python pytest
      - run: playwright install chromium
      - run: pytest test_accessibility.py -v --tb=long
```

Testing strategy:
- **Automated (axe-core)** — catches ~30-40% of issues (contrast, labels, ARIA)
- **Semi-automated** — tab order, focus management, screen reader output
- **Manual** — actual screen reader testing (NVDA/VoiceOver), cognitive load review'''
    ),
]
