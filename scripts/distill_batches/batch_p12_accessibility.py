PAIRS = [
    (
        "accessibility/web-a11y-patterns",
        r"""Explain web accessibility implementation including ARIA roles and properties, keyboard navigation patterns, screen reader optimization, color contrast and visual design requirements, and automated accessibility testing integration in CI/CD pipelines.""",
        r"""## Web Accessibility: ARIA, Keyboard Navigation, Screen Readers, and Automated Testing

**Web accessibility (a11y)** ensures that applications are usable by people with diverse abilities — visual, motor, auditory, and cognitive. **Because** 15-20% of the global population has some form of disability, accessibility is both an ethical imperative and a legal requirement (ADA, WCAG 2.1, EAA). The **trade-off** between rapid development and thorough accessibility is a false dichotomy — when accessibility patterns are integrated from the start, they add minimal overhead.

### ARIA Roles, Properties, and Live Regions

**ARIA (Accessible Rich Internet Applications)** bridges the gap between complex interactive widgets and assistive technology. **However**, the first rule of ARIA is: don't use ARIA if a native HTML element provides the same semantics. **Best practice**: use semantic HTML first, then enhance with ARIA where native elements are insufficient.

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class AriaRole(Enum):
    # Landmark roles for page structure
    BANNER = "banner"
    NAVIGATION = "navigation"
    MAIN = "main"
    COMPLEMENTARY = "complementary"
    CONTENTINFO = "contentinfo"
    # Widget roles for interactive elements
    DIALOG = "dialog"
    ALERTDIALOG = "alertdialog"
    TAB = "tab"
    TABPANEL = "tabpanel"
    TABLIST = "tablist"
    MENU = "menu"
    MENUITEM = "menuitem"
    TREE = "tree"
    TREEITEM = "treeitem"
    # Live region roles
    ALERT = "alert"
    STATUS = "status"
    LOG = "log"
    TIMER = "timer"

@dataclass
class AccessibleComponent:
    # Generates accessible HTML attributes for components
    role: Optional[AriaRole] = None
    label: Optional[str] = None
    described_by: Optional[str] = None
    expanded: Optional[bool] = None
    selected: Optional[bool] = None
    hidden: bool = False
    live: Optional[str] = None  # "polite", "assertive", "off"
    controls: Optional[str] = None
    owns: Optional[str] = None

    def to_attrs(self) -> dict[str, str]:
        attrs = {}
        if self.role:
            attrs["role"] = self.role.value
        if self.label:
            attrs["aria-label"] = self.label
        if self.described_by:
            attrs["aria-describedby"] = self.described_by
        if self.expanded is not None:
            attrs["aria-expanded"] = str(self.expanded).lower()
        if self.selected is not None:
            attrs["aria-selected"] = str(self.selected).lower()
        if self.hidden:
            attrs["aria-hidden"] = "true"
        if self.live:
            attrs["aria-live"] = self.live
        if self.controls:
            attrs["aria-controls"] = self.controls
        if self.owns:
            attrs["aria-owns"] = self.owns
        return attrs

class TabsComponentA11y:
    # Accessible tab component pattern
    # Common mistake: using divs with click handlers instead of proper tab semantics
    # because screen readers cannot identify the component's purpose

    def __init__(self, tabs: list[dict]):
        self.tabs = tabs

    def render_tablist(self) -> str:
        # The tablist contains tab buttons with proper roles
        # Keyboard: Left/Right arrows navigate tabs, Home/End jump to first/last
        tab_items = []
        for i, tab in enumerate(self.tabs):
            is_active = tab.get("active", False)
            panel_id = f"panel-{tab['id']}"
            attrs = AccessibleComponent(
                role=AriaRole.TAB,
                selected=is_active,
                controls=panel_id,
            ).to_attrs()
            attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
            # tabindex: active tab = 0, inactive = -1
            # Therefore, only the active tab is in the tab order
            # Arrow keys handle navigation between tabs (roving tabindex)
            tabindex = "0" if is_active else "-1"
            tab_items.append(
                f'<button {attr_str} tabindex="{tabindex}" '
                f'id="tab-{tab["id"]}">{tab["label"]}</button>'
            )

        tabs_html = "\n    ".join(tab_items)
        return f'<div role="tablist" aria-label="Settings">\n    {tabs_html}\n</div>'

    def render_panels(self) -> str:
        panels = []
        for tab in self.tabs:
            is_active = tab.get("active", False)
            hidden = "" if is_active else ' hidden'
            # tabpanel is labeled by its associated tab
            panels.append(
                f'<div role="tabpanel" id="panel-{tab["id"]}" '
                f'aria-labelledby="tab-{tab["id"]}"{hidden} tabindex="0">'
                f'\n    {tab.get("content", "")}\n</div>'
            )
        return "\n".join(panels)
```

### Keyboard Navigation and Focus Management

**Keyboard accessibility** is the foundation of all accessibility — if a component can't be operated with a keyboard, it fails for users of screen readers, switch devices, and voice control. **Pitfall**: relying on mouse-only interactions (hover, click, drag) without keyboard equivalents.

```python
class FocusManager:
    # Manages focus for complex interactive patterns
    # Best practice: trap focus within modal dialogs
    # because users should not be able to tab to background content

    # Roving tabindex pattern for composite widgets
    # (tabs, toolbars, menus, grids)
    @staticmethod
    def roving_tabindex_js() -> str:
        return """
class RovingTabindex {
    // Manages keyboard navigation within a composite widget
    // Therefore, only one item is tabbable at a time
    constructor(container, itemSelector, orientation = 'horizontal') {
        this.container = container;
        this.items = Array.from(container.querySelectorAll(itemSelector));
        this.orientation = orientation;
        this.currentIndex = 0;
        this.setup();
    }

    setup() {
        // Set initial tabindex values
        this.items.forEach((item, i) => {
            item.setAttribute('tabindex', i === 0 ? '0' : '-1');
        });
        this.container.addEventListener('keydown', (e) => this.handleKeydown(e));
    }

    handleKeydown(event) {
        const key = event.key;
        let newIndex = this.currentIndex;

        // Arrow key navigation based on orientation
        // Trade-off: horizontal uses Left/Right, vertical uses Up/Down
        // However, some widgets (grids) use both
        if (this.orientation === 'horizontal') {
            if (key === 'ArrowRight') newIndex = this.currentIndex + 1;
            else if (key === 'ArrowLeft') newIndex = this.currentIndex - 1;
        } else {
            if (key === 'ArrowDown') newIndex = this.currentIndex + 1;
            else if (key === 'ArrowUp') newIndex = this.currentIndex - 1;
        }

        if (key === 'Home') newIndex = 0;
        if (key === 'End') newIndex = this.items.length - 1;

        // Wrap around
        if (newIndex < 0) newIndex = this.items.length - 1;
        if (newIndex >= this.items.length) newIndex = 0;

        if (newIndex !== this.currentIndex) {
            event.preventDefault();
            this.moveFocus(newIndex);
        }
    }

    moveFocus(newIndex) {
        this.items[this.currentIndex].setAttribute('tabindex', '-1');
        this.items[newIndex].setAttribute('tabindex', '0');
        this.items[newIndex].focus();
        this.currentIndex = newIndex;
    }
}

// Focus trap for modal dialogs
// Pitfall: not trapping focus allows users to interact with background
class FocusTrap {
    constructor(element) {
        this.element = element;
        this.focusableSelector = [
            'a[href]', 'button:not([disabled])', 'input:not([disabled])',
            'select:not([disabled])', 'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])', '[contenteditable]'
        ].join(', ');
        this.previousFocus = document.activeElement;
    }

    activate() {
        const focusable = this.element.querySelectorAll(this.focusableSelector);
        if (focusable.length > 0) focusable[0].focus();
        document.addEventListener('keydown', this.handleTab);
    }

    handleTab = (event) => {
        if (event.key !== 'Tab') return;
        const focusable = Array.from(
            this.element.querySelectorAll(this.focusableSelector)
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    deactivate() {
        document.removeEventListener('keydown', this.handleTab);
        if (this.previousFocus) this.previousFocus.focus();
    }
}
"""
```

### Automated Accessibility Testing

**Best practice**: integrate accessibility testing into CI/CD pipelines to catch regressions early. **However**, automated tools only catch ~30-40% of accessibility issues — manual testing with screen readers is still essential.

```python
import json
from typing import Optional

class A11yTestRunner:
    # Integrates axe-core accessibility testing into CI/CD
    # Common mistake: relying solely on automated tests
    # because they miss many interaction and context-dependent issues
    # Therefore, use automated tests as a baseline, not a replacement

    WCAG_LEVELS = {
        "A": ["area-alt", "button-name", "image-alt", "label"],
        "AA": ["color-contrast", "heading-order", "link-name", "landmark-one-main"],
        "AAA": ["link-purpose", "target-size", "focus-visible"],
    }

    def __init__(self, target_level: str = "AA"):
        self.target_level = target_level
        self.results: list[dict] = []

    async def run_axe_scan(self, page_url: str) -> dict:
        # Runs axe-core via Playwright for comprehensive a11y scanning
        # Best practice: scan every page in your app, not just the homepage
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(page_url)

            # Inject and run axe-core
            await page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
            results = await page.evaluate("""
                async () => {
                    // Configure axe to test against our target WCAG level
                    const results = await axe.run(document, {
                        runOnly: {
                            type: 'tag',
                            values: ['wcag2a', 'wcag2aa', 'best-practice']
                        }
                    });
                    return {
                        violations: results.violations.map(v => ({
                            id: v.id,
                            impact: v.impact,
                            description: v.description,
                            help: v.help,
                            helpUrl: v.helpUrl,
                            nodes: v.nodes.length,
                            tags: v.tags,
                        })),
                        passes: results.passes.length,
                        incomplete: results.incomplete.length,
                    };
                }
            """)
            await browser.close()

        self.results.append({"url": page_url, **results})
        return results

    def generate_report(self) -> dict:
        total_violations = 0
        critical = 0
        serious = 0

        for result in self.results:
            for violation in result.get("violations", []):
                total_violations += violation["nodes"]
                if violation["impact"] == "critical":
                    critical += violation["nodes"]
                elif violation["impact"] == "serious":
                    serious += violation["nodes"]

        return {
            "pages_scanned": len(self.results),
            "total_violations": total_violations,
            "critical": critical,
            "serious": serious,
            "pass": critical == 0 and serious == 0,
            # Pitfall: setting the bar too low initially
            # Trade-off: start strict and maintain, vs permissive and gradually tighten
        }

    def should_fail_ci(self, report: dict) -> bool:
        # Fail CI on critical or serious violations
        # However, allow incomplete checks (need manual review)
        return report["critical"] > 0 or report["serious"] > 0
```

### Key Takeaways

- **Semantic HTML first, ARIA second** — a **common mistake** is adding ARIA roles to elements that already have native semantics (e.g., `role="button"` on a `<button>`)
- **Roving tabindex** is the **best practice** for composite widgets — **because** only one item should be in the tab order at a time
- **Focus trapping** in modals is essential — **pitfall**: forgetting to return focus to the trigger element when the modal closes
- **Automated testing catches ~30-40%** of issues — **therefore** complement with manual screen reader testing (NVDA, VoiceOver, JAWS)
- **Color contrast** must meet WCAG AA (4.5:1 for normal text, 3:1 for large text) — **however** many design systems still fail this basic requirement
- The **trade-off** between custom widgets and native elements: custom widgets require extensive ARIA and keyboard handling, while native elements get accessibility for free
"""
    ),
]
