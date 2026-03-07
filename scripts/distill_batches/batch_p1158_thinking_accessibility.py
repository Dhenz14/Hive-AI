"""
Frontend thinking pairs - Accessibility (ARIA, semantic HTML, keyboard navigation)
"""

pairs = [
    {
        "instruction": r'''I built a custom dropdown menu using divs and onClick handlers. It works with a mouse but my QA team says it fails accessibility testing. What am I doing wrong?''',
        "output": r'''<think>
Custom dropdown with divs and onClick -- this is one of the most common accessibility failures in React apps. Let me think about what is broken.

The core problem: a div has no semantic meaning. Screen readers do not announce it as a menu. It has no keyboard interaction built in. A native select element or the button + listbox pattern gives you all of this for free.

What is missing from a div-based dropdown:
1. No keyboard navigation -- cannot Tab to it, cannot use Arrow keys to navigate options, cannot press Enter to select, cannot press Escape to close
2. No ARIA roles -- screen reader does not know it is a menu
3. No focus management -- opening the dropdown does not move focus into it
4. No announcements -- selecting an option does not announce the change

Wait, should I recommend just using a native select element? For simple dropdowns (pick one value from a list), the native select is almost always the right answer. It handles keyboard, screen readers, mobile touch, and accessibility without any custom code.

But the user probably built a custom dropdown because they needed custom styling or complex content (icons, descriptions, multi-select). Native select is hard to style and only supports plain text options.

Hmm, so the real question is: how do I make a custom dropdown accessible? The WAI-ARIA pattern for this is the "combobox" or "listbox" pattern. It requires:
- A button that triggers the dropdown (role="combobox" or just a button)
- A list of options (role="listbox")
- Each option has role="option"
- aria-expanded on the button
- aria-activedescendant for keyboard navigation
- Key handlers for Arrow Up/Down, Enter, Escape, Home, End

I initially thought I should show all of this from scratch, but actually the amount of code needed to get this right is enormous. The better advice might be: use a headless UI library like Radix or Headless UI that handles all the accessibility internals.
</think>

A div-based dropdown is invisible to screen readers and unreachable by keyboard. You need semantic roles, keyboard handlers, and focus management. Here is the accessible pattern:

```tsx
import { useState, useRef, useEffect, useCallback } from 'react';

interface Option {
  value: string;
  label: string;
}

interface AccessibleSelectProps {
  label: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
}

function AccessibleSelect({
  label,
  options,
  value,
  onChange,
}: AccessibleSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = 'select-listbox';

  const selectedOption = options.find(o => o.value === value);

  // Close on Escape or click outside
  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
        buttonRef.current?.focus();
      }
    };
    const handleClickOutside = (e: MouseEvent) => {
      if (!listRef.current?.contains(e.target as Node) &&
          !buttonRef.current?.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('keydown', handleEsc);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          if (!isOpen) {
            setIsOpen(true);
            setActiveIndex(0);
          } else {
            setActiveIndex(i =>
              Math.min(i + 1, options.length - 1)
            );
          }
          break;
        case 'ArrowUp':
          e.preventDefault();
          setActiveIndex(i => Math.max(i - 1, 0));
          break;
        case 'Enter':
        case ' ':
          e.preventDefault();
          if (isOpen && activeIndex >= 0) {
            onChange(options[activeIndex].value);
            setIsOpen(false);
            buttonRef.current?.focus();
          } else {
            setIsOpen(true);
            setActiveIndex(0);
          }
          break;
        case 'Home':
          e.preventDefault();
          setActiveIndex(0);
          break;
        case 'End':
          e.preventDefault();
          setActiveIndex(options.length - 1);
          break;
      }
    },
    [isOpen, activeIndex, options, onChange]
  );

  return (
    <div className="select-wrapper">
      {/* Visible label linked to the button */}
      <label id="select-label">{label}</label>

      <button
        ref={buttonRef}
        type="button"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-labelledby="select-label"
        aria-activedescendant={
          isOpen && activeIndex >= 0
            ? "option-" + activeIndex
            : undefined
        }
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
      >
        {selectedOption ? selectedOption.label : 'Select...'}
      </button>

      {isOpen && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-labelledby="select-label"
        >
          {options.map((opt, i) => (
            <li
              key={opt.value}
              id={"option-" + i}
              role="option"
              aria-selected={opt.value === value}
              data-active={i === activeIndex}
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
                buttonRef.current?.focus();
              }}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

What was missing from your div-based version:
- **role="combobox"** on the trigger so screen readers announce "dropdown"
- **role="listbox" + role="option"** so options are navigable
- **aria-expanded** tells screen readers if the menu is open or closed
- **aria-activedescendant** tracks which option has virtual focus
- **Keyboard handlers** for Arrow keys, Enter, Escape, Home, End
- **Focus management** -- returns focus to trigger on close

For production, consider using **Radix UI** or **Headless UI** which handle all of this correctly out of the box.'''
    },
    {
        "instruction": r'''My designer wants me to use a div with an onClick handler instead of a button element because "buttons are hard to style." How do I push back on this?''',
        "output": r'''<think>
This is a really common conflict between design and accessibility. The designer wants a clickable div because native button styling (borders, padding, browser defaults) is annoying to reset. But using a div as a button breaks accessibility fundamentally.

Let me think about what a native button gives you for free:
1. Focusable via Tab key -- div is not focusable at all
2. Activatable via Enter and Space keys -- div ignores keyboard events
3. Screen readers announce it as "button" -- div is announced as generic text
4. Includes in the tab order automatically
5. Has disabled state that works with screen readers
6. Has type="submit" behavior in forms

To make a div work like a button, you would need to add:
- tabIndex={0}
- role="button"
- onKeyDown handler for Enter and Space
- aria-disabled for disabled state
- cursor: pointer style

That is a lot of work to recreate what button gives you for free. And you will inevitably forget something or get an edge case wrong.

Hmm, but the designer has a point -- button default styles ARE annoying. The counter-argument is not "buttons are easy to style" because they are not. The counter-argument is: "here is a CSS reset that removes all default button styles, making it a blank slate." Once you reset button to appearance: none with no borders, padding, or background, it looks and behaves exactly like a div -- but with all the accessibility built in.

I initially thought I should explain all the accessibility problems, but actually the most persuasive argument is showing the CSS reset. If the button looks identical to a div after the reset, the designer's objection disappears.
</think>

The designer's concern is valid -- native buttons have ugly defaults. But the fix is a CSS reset, not replacing the element. Show them this:

```css
/* Universal button reset -- looks exactly like a div */
.btn-reset {
  appearance: none;
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  text-align: inherit;
  line-height: inherit;
}

/* Now style it however the designer wants */
.fancy-button {
  composes: btn-reset; /* or just apply both classes */
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border-radius: 12px;
  font-weight: 600;
  transition: transform 0.1s ease, box-shadow 0.2s ease;
}

.fancy-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.fancy-button:active {
  transform: translateY(0);
}

/* Focus ring for keyboard users (not mouse users) */
.fancy-button:focus-visible {
  outline: 2px solid #667eea;
  outline-offset: 2px;
}
```

```tsx
// CORRECT: button element with reset CSS
// Gets keyboard, screen reader, and form support for free
function ActionBar() {
  return (
    <div className="action-bar">
      <button className="fancy-button" onClick={handleSave}>
        Save Changes
      </button>
      <button
        className="fancy-button"
        onClick={handleDelete}
        disabled={!canDelete}
      >
        Delete
      </button>
    </div>
  );
}

// WRONG: div pretending to be a button
// Missing: focus, keyboard activation, screen reader role, disabled state
function ActionBarBroken() {
  return (
    <div className="action-bar">
      {/* This is invisible to keyboard users and screen readers */}
      <div className="fancy-button" onClick={handleSave}>
        Save Changes
      </div>
    </div>
  );
}
```

What button gives you for free (that a div does not):
| Feature | button | div |
|---|---|---|
| Tab focus | Automatic | Must add tabIndex={0} |
| Enter/Space activation | Built-in | Must add onKeyDown handler |
| Screen reader announcement | "Save Changes, button" | "Save Changes" (no role) |
| Disabled state | disabled attribute works | Must use aria-disabled + prevent clicks |
| Form submission | type="submit" | Not possible |
| :focus-visible styling | Works | Only with tabIndex hack |

The argument to give the designer: "After the CSS reset, the button element is a completely blank canvas -- identical to a div visually. But it has keyboard and screen reader support built in. Using a div instead means we have to manually recreate all of that, and we will inevitably miss edge cases."'''
    },
    {
        "instruction": r'''How do I make a tab component accessible? I have tabs that switch content panels but I am not sure what ARIA attributes to use.''',
        "output": r'''<think>
Tabs are one of the WAI-ARIA design patterns with a well-defined spec. Let me think through what is needed.

The structure is:
- A tablist container (role="tablist")
- Individual tabs (role="tab") -- these are the clickable labels
- Tab panels (role="tabpanel") -- these are the content areas

The ARIA connections:
- Each tab has aria-controls pointing to its panel's id
- Each panel has aria-labelledby pointing to its tab's id
- The active tab has aria-selected="true"
- Inactive panels are hidden (hidden attribute or display: none)

Keyboard behavior:
- Arrow Left/Right moves between tabs in the tablist
- Home/End jump to first/last tab
- Tab key moves focus FROM the tablist INTO the active panel's content

Wait, there is actually a design decision here: should arrow keys automatically activate the tab (change the panel), or just move focus (and require Enter to activate)? The WAI-ARIA spec recommends automatic activation for most cases because it is faster for users. Manual activation is better when loading the tab content is expensive (like an API call).

Hmm, I initially thought I should show both patterns, but automatic activation is the more common and recommended approach. I will show that and mention manual activation as an alternative.

Another subtlety: roving tabindex. Only the active tab should have tabIndex={0}. Inactive tabs should have tabIndex={-1}. This way, Tab key skips past inactive tabs and goes straight to the panel content. Arrow keys handle navigation between tabs. This is the "roving tabindex" pattern.

I should also make sure the focus moves correctly -- when arrow key moves to a tab, that tab gets focused AND activated (for automatic activation mode).
</think>

Tabs follow a specific WAI-ARIA pattern with roving tabindex for keyboard navigation. Here is the complete accessible implementation:

```tsx
import { useState, useRef, useCallback } from 'react';

interface Tab {
  id: string;
  label: string;
  content: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
  label: string; // Describes the tab group for screen readers
}

function Tabs({ tabs, defaultTab, label }: TabsProps) {
  const [activeId, setActiveId] = useState(
    defaultTab || tabs[0]?.id
  );
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const activeIndex = tabs.findIndex(t => t.id === activeId);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      let nextIndex = activeIndex;

      switch (e.key) {
        case 'ArrowRight':
          e.preventDefault();
          nextIndex = (activeIndex + 1) % tabs.length;
          break;
        case 'ArrowLeft':
          e.preventDefault();
          nextIndex =
            (activeIndex - 1 + tabs.length) % tabs.length;
          break;
        case 'Home':
          e.preventDefault();
          nextIndex = 0;
          break;
        case 'End':
          e.preventDefault();
          nextIndex = tabs.length - 1;
          break;
        default:
          return;
      }

      // Automatic activation: arrow keys change both focus AND active tab
      const nextTab = tabs[nextIndex];
      setActiveId(nextTab.id);
      tabRefs.current.get(nextTab.id)?.focus();
    },
    [activeIndex, tabs]
  );

  return (
    <div>
      {/* The tablist container */}
      <div
        role="tablist"
        aria-label={label}
        onKeyDown={handleKeyDown}
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            ref={el => {
              if (el) tabRefs.current.set(tab.id, el);
            }}
            role="tab"
            id={"tab-" + tab.id}
            aria-selected={tab.id === activeId}
            aria-controls={"panel-" + tab.id}
            tabIndex={tab.id === activeId ? 0 : -1}
            onClick={() => setActiveId(tab.id)}
            className={tab.id === activeId ? 'tab active' : 'tab'}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels -- only active one is visible */}
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={"panel-" + tab.id}
          role="tabpanel"
          aria-labelledby={"tab-" + tab.id}
          tabIndex={0}
          hidden={tab.id !== activeId}
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}

// Usage
function SettingsPage() {
  const tabs: Tab[] = [
    {
      id: 'profile',
      label: 'Profile',
      content: <ProfileSettings />,
    },
    {
      id: 'billing',
      label: 'Billing',
      content: <BillingSettings />,
    },
    {
      id: 'notifications',
      label: 'Notifications',
      content: <NotificationSettings />,
    },
  ];

  return <Tabs tabs={tabs} label="Settings sections" />;
}
```

```css
[role="tablist"] {
  display: flex;
  border-bottom: 2px solid #e2e8f0;
  gap: 0;
}

.tab {
  appearance: none;
  background: none;
  border: none;
  padding: 12px 20px;
  font: inherit;
  cursor: pointer;
  color: #64748b;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}

.tab:hover {
  color: #1e293b;
}

.tab.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
  font-weight: 600;
}

.tab:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: -2px;
}

[role="tabpanel"] {
  padding: 24px 0;
}

[role="tabpanel"]:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 4px;
}
```

Key accessibility features:
- **Roving tabindex**: Only the active tab has tabIndex={0}. Tab key skips past inactive tabs and enters the panel content directly.
- **Arrow keys** navigate between tabs (with wrapping at ends)
- **aria-selected** tells screen readers which tab is active
- **aria-controls / aria-labelledby** link tabs to their panels
- **tabIndex={0} on panels** lets keyboard users Tab into panel content
- **hidden attribute** properly hides inactive panels from screen readers (better than CSS display: none for this purpose)'''
    },
    {
        "instruction": r'''I need to add a loading spinner to my app. How do I make it accessible for screen reader users who cannot see the visual spinner?''',
        "output": r'''<think>
A loading spinner is purely visual -- screen reader users have no idea something is loading unless we tell them. Let me think about the right approach.

The key ARIA attribute here is aria-live. When content in an aria-live region changes, screen readers announce the change. So if I put the loading message in an aria-live region, the screen reader will announce "Loading" when it appears and "Content loaded" (or the actual content) when loading finishes.

But wait, there are details to get right:
- aria-live="polite" vs aria-live="assertive" -- polite waits for the screen reader to finish its current announcement, assertive interrupts. For most loading states, polite is correct. Assertive is for urgent alerts.
- Should I use role="status" or role="alert"? role="status" has implicit aria-live="polite" and is designed for status messages. role="alert" is assertive and for urgent messages. Loading is a status, not an alert.
- Do I need aria-busy? Yes -- aria-busy="true" on the container tells screen readers that the content is being updated and to wait before reading it. This prevents the screen reader from trying to read partially loaded content.

Hmm, another approach: use the aria-label on the spinner itself. But that only works if the spinner is focusable, which it usually is not. The live region approach is better because it announces proactively.

I initially thought a simple aria-label="Loading" on the spinner div would suffice, but that is passive -- the screen reader only reads it if the user navigates to it. The live region approach actively announces when loading starts and ends.

There is also the question of visually hidden text. The spinner SVG/animation is visual, but I need text that screen readers can read. The sr-only / visually-hidden class hides text visually while keeping it accessible.
</think>

Screen reader users cannot see the spinner, so you need to announce the loading state with ARIA live regions. Here is the complete pattern:

```tsx
import { useState, useEffect } from 'react';

// Visually hidden but screen-reader accessible
const srOnly: React.CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  borderWidth: 0,
};

interface LoadingSpinnerProps {
  label?: string;
}

function LoadingSpinner({ label = 'Loading' }: LoadingSpinnerProps) {
  return (
    <div className="spinner-container" role="status">
      {/* Visual spinner -- decorative, hidden from screen readers */}
      <svg
        className="spinner"
        aria-hidden="true"
        viewBox="0 0 24 24"
        width={24}
        height={24}
      >
        <circle
          cx="12" cy="12" r="10"
          stroke="currentColor"
          strokeWidth="3"
          fill="none"
          strokeDasharray="31.4 31.4"
        />
      </svg>
      {/* Screen reader announcement */}
      <span style={srOnly}>{label}</span>
    </div>
  );
}

// Full pattern: async content with loading announcement
function UserDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch('/api/dashboard')
      .then(res => res.json())
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1>Dashboard</h1>

      {/* aria-busy prevents screen readers from reading partial content */}
      <div aria-busy={loading}>
        {loading && <LoadingSpinner label="Loading dashboard data" />}
        {error && (
          <div role="alert" className="error">
            Failed to load dashboard: {error}
          </div>
        )}
        {data && !loading && (
          <div>
            <p>Welcome back, {data.userName}</p>
            {/* Dashboard content */}
          </div>
        )}
      </div>

      {/* Live region for status announcements */}
      <div aria-live="polite" style={srOnly}>
        {loading ? 'Loading dashboard data...' : ''}
        {data && !loading ? 'Dashboard loaded successfully.' : ''}
      </div>
    </div>
  );
}
```

```css
@keyframes spin {
  to { transform: rotate(360deg); }
}

.spinner-container {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.spinner {
  animation: spin 0.8s linear infinite;
  color: #3b82f6;
}
```

Key accessibility details:
- **role="status"** on the spinner -- has implicit aria-live="polite" so screen readers announce it when it appears
- **aria-hidden="true"** on the SVG -- the visual spinner is decorative; the text label is what matters
- **Visually hidden text** provides the actual announcement ("Loading dashboard data")
- **aria-busy={true}** on the content container prevents screen readers from reading half-loaded content
- **aria-live="polite"** region announces both loading start AND completion so users know when content is ready
- **role="alert"** for errors (assertive) vs role="status" for loading (polite) -- errors need immediate attention, loading states do not'''
    },
    {
        "instruction": r'''What is the minimum I need to do to make my React app pass basic WCAG 2.1 AA compliance? I do not have time for a full audit.''',
        "output": r'''<think>
WCAG 2.1 AA compliance is a big spec, but the user wants the minimum viable set. Let me think about what catches the most common violations.

WebAIM's annual survey of the top 1 million websites shows the most common WCAG failures:
1. Low contrast text (86% of sites) -- text does not have enough contrast against its background
2. Missing alt text on images (60%)
3. Missing form labels (54%)
4. Empty links (50%)
5. Missing document language (28%)
6. Empty buttons (27%)

So if I fix these 6 things, I have addressed the vast majority of real-world accessibility failures. That is a pragmatic 80/20 approach.

Hmm, but there are a few more things that are not in the "top failures" list but are critical:
- Keyboard navigation -- can all interactive elements be reached and operated with keyboard alone?
- Focus visible -- can keyboard users see where focus is?
- Heading hierarchy -- do headings follow h1 -> h2 -> h3 order?

Wait, I should also mention tooling. The fastest way to catch obvious issues is to run axe-core or Lighthouse accessibility audit. These automated tools catch about 30-40% of WCAG issues instantly. The rest requires manual testing (keyboard navigation, screen reader testing).

I initially thought I should list all WCAG criteria, but that is overwhelming and the user said they do not have time. The pragmatic approach is: fix the top automated catches, add keyboard support, and test with a screen reader once.

Let me provide a checklist with code examples for the most impactful fixes.
</think>

Here is the 80/20 checklist that catches the most common WCAG AA violations, with code fixes for each:

```tsx
// 1. COLOR CONTRAST -- Most common failure (86% of sites fail this)
// Minimum ratios: 4.5:1 for normal text, 3:1 for large text (18px+ bold or 24px+)

// BAD: light gray on white
// <p style={{ color: '#999', background: '#fff' }}>Hard to read</p>
// ratio: 2.8:1 -- FAIL

// GOOD: dark gray on white
// <p style={{ color: '#4a5568', background: '#fff' }}>Easy to read</p>
// ratio: 7.1:1 -- PASS

// 2. IMAGE ALT TEXT -- Every img needs alt. Decorative images get alt=""
function ProductImage({ product }: { product: Product }) {
  return (
    <div>
      {/* Informative image: describe what it shows */}
      <img
        src={product.imageUrl}
        alt={"Photo of " + product.name}
      />
      {/* Decorative image: empty alt so screen readers skip it */}
      <img src="/decorative-divider.svg" alt="" />
    </div>
  );
}

// 3. FORM LABELS -- Every input needs a visible label
function LoginForm() {
  return (
    <form>
      {/* BAD: placeholder is NOT a label */}
      {/* <input placeholder="Email" /> */}

      {/* GOOD: explicit label linked to input */}
      <label htmlFor="email">Email address</label>
      <input id="email" type="email" autoComplete="email" />

      <label htmlFor="password">Password</label>
      <input id="password" type="password" autoComplete="current-password" />

      <button type="submit">Log in</button>
    </form>
  );
}

// 4. BUTTON AND LINK TEXT -- Never empty, never just an icon
function ActionButtons() {
  return (
    <div>
      {/* BAD: icon-only button with no accessible name */}
      {/* <button><TrashIcon /></button> */}

      {/* GOOD: aria-label provides accessible name */}
      <button aria-label="Delete item">
        <TrashIcon aria-hidden="true" />
      </button>

      {/* GOOD: visually hidden text */}
      <button>
        <TrashIcon aria-hidden="true" />
        <span className="sr-only">Delete item</span>
      </button>

      {/* BAD: link with no text */}
      {/* <a href="/profile"><UserIcon /></a> */}

      {/* GOOD */}
      <a href="/profile" aria-label="View profile">
        <UserIcon aria-hidden="true" />
      </a>
    </div>
  );
}

// 5. FOCUS VISIBILITY -- Never remove focus outlines without replacement
// In your global CSS:
// BAD:  *:focus { outline: none; }
// GOOD: Use :focus-visible so only keyboard focus shows the ring

// 6. HEADING HIERARCHY -- Do not skip levels
function Page() {
  return (
    <main>
      <h1>Dashboard</h1>
      {/* BAD: jumping from h1 to h4 */}
      {/* <h4>Recent Activity</h4> */}
      {/* GOOD: sequential hierarchy */}
      <h2>Recent Activity</h2>
      <h3>Today</h3>
    </main>
  );
}

// 7. DOCUMENT LANGUAGE -- Set in your HTML
// <html lang="en">
```

```css
/* Focus ring that only appears for keyboard navigation */
*:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
}

/* Visually hidden but screen-reader accessible */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

Quick automated audit -- run this in your browser console:

```
// Install axe-core as a dev dependency, then:
// npx axe-core --include body
// Or use Lighthouse: Chrome DevTools -> Lighthouse -> Accessibility
```

Minimum checklist (covers ~80% of WCAG AA):
1. Text contrast ratio >= 4.5:1 (use a contrast checker tool)
2. All images have meaningful alt text (or alt="" for decorative)
3. All form inputs have visible labels (not just placeholders)
4. All buttons and links have accessible text
5. Focus outlines are visible for keyboard users
6. Headings follow h1 -> h2 -> h3 order (no skipping)
7. html element has lang attribute
8. All interactive elements reachable and usable via keyboard alone'''
    },
]
