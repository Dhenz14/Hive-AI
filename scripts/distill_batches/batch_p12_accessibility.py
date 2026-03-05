'''p12 accessibility'''

PAIRS = [
    (
        "accessibility/web-a11y-patterns",
        "Explain web accessibility implementation including ARIA roles and properties, keyboard navigation patterns, screen reader optimization, color contrast and visual design requirements, and automated accessibility testing integration in CI/CD pipelines.",
        """### ARIA Roles, Properties, and Live Regions

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
                f'id="tab-{tab["id"]}">{tab["label"]}</button>'"""
    ),
    (
        "AAA",
        "} def __init__(self, target_level: str = 'AA'): self.target_level = target_level self.results: list[dict] = [] async def run_axe_scan(self, page_url: str) -> dict:",
        """# Best practice: scan every page in your app, not just the homepage
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(page_url)

            # Inject and run axe-core
            await page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
            results = await page.evaluate('''
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
            ''')
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

        return {"""
    ),
]
