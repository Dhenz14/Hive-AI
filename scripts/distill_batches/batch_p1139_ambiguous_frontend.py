"""
Ambiguous request handling pairs - vague frontend requests
"""

pairs = [
    {
        "instruction": r'''Fix the UI. It looks bad.''',
        "output": r'''<think>
"Fix the UI, it looks bad" -- this is entirely subjective without seeing it. Bad how? Ugly colors? Poor spacing? Broken layout? Inconsistent styling? Looks outdated? Not matching a design mockup? Different on mobile vs desktop? I don't know the framework (React, Vue, plain HTML), what CSS approach they use, or what "good" looks like to them. I need to see the UI or at least understand the specific complaints.
</think>

I'd need to see the UI to give specific advice. A few questions:

1. **What looks bad specifically?** Spacing, colors, typography, layout, inconsistency, or general "dated" feel?
2. **Do you have a design mockup** it should match, or are you looking for general improvement?
3. **What's the frontend stack?** React, Vue, plain HTML? CSS framework (Tailwind, Bootstrap, custom)?

Without seeing the code, here are the most common "looks bad" fixes that apply to almost any UI:

```css
/* The "instant improvement" CSS reset -- fixes 80% of "looks bad" */

/* 1. Consistent spacing with a scale */
:root {
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    --space-xl: 32px;
    --space-2xl: 48px;

    /* 2. Limited, harmonious color palette */
    --color-primary: #2563eb;
    --color-primary-hover: #1d4ed8;
    --color-text: #1f2937;
    --color-text-light: #6b7280;
    --color-bg: #ffffff;
    --color-bg-subtle: #f9fafb;
    --color-border: #e5e7eb;

    /* 3. Clean typography */
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-size-sm: 0.875rem;
    --font-size-base: 1rem;
    --font-size-lg: 1.25rem;
    --font-size-xl: 1.5rem;
}

body {
    font-family: var(--font-sans);
    color: var(--color-text);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}

/* 4. Cards and containers -- add breathing room */
.card {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: var(--space-lg);
    margin-bottom: var(--space-md);
}

/* 5. Buttons that look clickable */
.button {
    display: inline-flex;
    align-items: center;
    padding: var(--space-sm) var(--space-md);
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: var(--font-size-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
}
.button:hover {
    background: var(--color-primary-hover);
}

/* 6. Tables that don't look like spreadsheets */
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-weight: 600; color: var(--color-text-light); font-size: var(--font-size-sm); }
td, th { padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--color-border); }
tr:hover { background: var(--color-bg-subtle); }
```

```text
Quick wins that make any UI look better:
1. More whitespace (increase padding and margins)
2. Fewer colors (pick 1 primary + 2 grays)
3. Consistent border-radius (pick one: 4px, 6px, or 8px)
4. Limit font sizes to 4-5 sizes max
5. Align everything to a grid
6. Subtle borders instead of heavy lines
```

Share a screenshot or the CSS/component code and I'll give you specific fixes.'''
    },
    {
        "instruction": r'''Make the app responsive. It doesn't work on mobile.''',
        "output": r'''<think>
"Doesn't work on mobile" -- is the layout broken? Is it just too wide and requires horizontal scrolling? Are touch targets too small? Is functionality missing on mobile? Are they using fixed pixel widths? I don't know the framework or current CSS approach. "Responsive" could mean anything from adding a viewport meta tag to a complete layout rewrite with media queries or a mobile-first redesign.
</think>

To prioritize the right fixes:

1. **What breaks specifically on mobile?** Layout overflows horizontally? Elements overlap? Text too small? Buttons too small to tap?
2. **What's the current CSS approach?** Fixed pixel widths? No media queries at all?
3. **Framework?** React, Vue, plain HTML? Using any CSS framework?

Here's a systematic approach to making an existing app responsive:

```html
<!-- Step 0: Make sure you have this in your <head> -- without it, nothing works on mobile -->
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```

```css
/* Step 1: Fix the most common layout breakers */

/* Never use fixed widths on containers */
/* BAD: */
.container { width: 1200px; }
/* GOOD: */
.container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 16px; }

/* Make images and media responsive */
img, video, iframe { max-width: 100%; height: auto; }

/* Prevent tables from breaking layout */
.table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; }

/* Step 2: Use flexbox/grid for layouts that adapt */
/* Sidebar + main content layout */
.layout {
    display: flex;
    gap: 24px;
}
.sidebar { width: 250px; flex-shrink: 0; }
.main { flex: 1; min-width: 0; }  /* min-width: 0 prevents flex overflow */

@media (max-width: 768px) {
    .layout {
        flex-direction: column;
    }
    .sidebar {
        width: 100%;
        order: 2;  /* move sidebar below content on mobile */
    }
}

/* Card grid that adapts automatically */
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
}
/* No media query needed -- auto-fill handles it */

/* Step 3: Navigation -- hamburger menu on mobile */
.nav-links {
    display: flex;
    gap: 16px;
}

@media (max-width: 768px) {
    .nav-links {
        display: none;  /* hidden by default on mobile */
        flex-direction: column;
        position: absolute;
        top: 60px;
        left: 0;
        right: 0;
        background: white;
        padding: 16px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .nav-links.open { display: flex; }
    .hamburger { display: block; }
}

/* Step 4: Touch-friendly sizing */
/* Minimum tap target: 44x44px (Apple guideline) */
button, a, input, select {
    min-height: 44px;
    font-size: 16px;  /* prevents iOS zoom on focus */
}

/* Step 5: Typography scaling */
h1 { font-size: clamp(1.5rem, 4vw, 2.5rem); }
h2 { font-size: clamp(1.25rem, 3vw, 2rem); }
body { font-size: clamp(0.875rem, 2vw, 1rem); }
```

```text
Testing checklist:
- Chrome DevTools device toolbar (F12 -> toggle device toolbar)
- Test at: 375px (iPhone SE), 390px (iPhone 14), 768px (iPad), 1024px (laptop)
- Check: horizontal scroll, text readability, tap targets, form usability
```

Share your current layout code or a screenshot on mobile, and I'll fix the specific breakpoints.'''
    },
    {
        "instruction": r'''Improve the UX of our application.''',
        "output": r'''<think>
"Improve the UX" -- this is extremely broad. UX encompasses navigation, information architecture, interaction design, loading states, error states, accessibility, onboarding, form design, feedback mechanisms... I don't know what the app does, who uses it, or what the specific pain points are. Without user research or at least knowing what users struggle with, I'd be guessing. I should ask about the biggest friction points.
</think>

UX improvement is a big topic. To be effective, I'd want to know:

1. **What do users struggle with most?** Where do they get stuck, confused, or abandon a task?
2. **What does the app do?** Different apps have different UX priorities.
3. **Any user feedback or support tickets** that point to specific problems?

Without knowing the specifics, here are the highest-impact UX improvements that apply to almost any web application:

```text
== Universal UX improvements (pick the ones you're missing) ==

1. LOADING STATES -- never leave users staring at nothing
2. ERROR MESSAGES -- tell users what happened AND what to do
3. EMPTY STATES -- guide users when there's no data yet
4. CONFIRMATION -- reassure users their action worked
5. FORM VALIDATION -- instant feedback, not after submission
```

```javascript
// 1. Loading states -- skeleton screens instead of spinners
function UserList() {
    const { data, isLoading, error } = useQuery('users', fetchUsers);

    if (isLoading) {
        return (
            <div className="user-list">
                {[1, 2, 3].map(i => (
                    <div key={i} className="skeleton-row">
                        <div className="skeleton skeleton-avatar" />
                        <div className="skeleton skeleton-text" />
                    </div>
                ))}
            </div>
        );
    }

    if (error) {
        // 2. Helpful error messages
        return (
            <div className="error-state">
                <p>Could not load users. This might be a temporary issue.</p>
                <button onClick={() => refetch()}>Try again</button>
            </div>
        );
    }

    if (data.length === 0) {
        // 3. Helpful empty states
        return (
            <div className="empty-state">
                <h3>No users yet</h3>
                <p>Invite your first team member to get started.</p>
                <button onClick={openInviteModal}>Invite someone</button>
            </div>
        );
    }

    return <ul>{data.map(user => <UserRow key={user.id} user={user} />)}</ul>;
}

// 4. Success feedback -- toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// After saving: showToast('Changes saved successfully');
// After error: showToast('Could not save. Please try again.', 'error');

// 5. Inline form validation
function validateEmail(input) {
    const email = input.value;
    const error = input.nextElementSibling;
    if (!email) {
        error.textContent = 'Email is required';
    } else if (!email.includes('@')) {
        error.textContent = 'Please enter a valid email address';
    } else {
        error.textContent = '';
    }
}
```

```css
/* Skeleton loading animation */
.skeleton {
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
}
@keyframes shimmer { to { background-position: -200% 0; } }
.skeleton-avatar { width: 40px; height: 40px; border-radius: 50%; }
.skeleton-text { height: 16px; width: 60%; }
```

If you can share what your users are actually struggling with (or which screens/flows have the highest drop-off), I can give you targeted UX fixes instead of generic ones.'''
    },
    {
        "instruction": r'''Add dark mode to the app.''',
        "output": r'''<think>
"Add dark mode" -- are they using CSS custom properties already? A CSS framework? What frontend stack -- React, Vue, plain HTML? Do they want system-preference detection, a manual toggle, or both? How complex is the existing theming -- are colors hardcoded everywhere or centralized? Dark mode is straightforward if CSS variables are already in use, but a pain if colors are scattered across hundreds of files.
</think>

A few things to know before implementing:

1. **Are you using CSS custom properties (variables) already?** If colors are hardcoded everywhere (e.g., `color: #333` scattered in 50 files), we need to centralize first.
2. **Toggle or automatic?** Follow system preference, manual toggle button, or both?
3. **What framework?** React, Vue, plain JS? Any CSS framework (Tailwind, etc.)?

Here's a clean dark mode implementation that handles all the edge cases:

```css
/* Step 1: Define theme colors as CSS variables */
:root {
    /* Light theme (default) */
    --bg-primary: #ffffff;
    --bg-secondary: #f9fafb;
    --bg-tertiary: #f3f4f6;
    --text-primary: #111827;
    --text-secondary: #6b7280;
    --border: #e5e7eb;
    --shadow: rgba(0, 0, 0, 0.1);
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --danger: #dc2626;
    --success: #16a34a;
}

/* Dark theme */
[data-theme="dark"] {
    --bg-primary: #111827;
    --bg-secondary: #1f2937;
    --bg-tertiary: #374151;
    --text-primary: #f9fafb;
    --text-secondary: #9ca3af;
    --border: #374151;
    --shadow: rgba(0, 0, 0, 0.4);
    --accent: #3b82f6;
    --accent-hover: #60a5fa;
    --danger: #ef4444;
    --success: #22c55e;
}

/* Auto-detect system preference */
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg-primary: #111827;
        --bg-secondary: #1f2937;
        --bg-tertiary: #374151;
        --text-primary: #f9fafb;
        --text-secondary: #9ca3af;
        --border: #374151;
        --shadow: rgba(0, 0, 0, 0.4);
        --accent: #3b82f6;
        --accent-hover: #60a5fa;
        --danger: #ef4444;
        --success: #22c55e;
    }
}

/* Use variables everywhere instead of hardcoded colors */
body {
    background: var(--bg-primary);
    color: var(--text-primary);
    transition: background 0.2s, color 0.2s;
}

.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    box-shadow: 0 1px 3px var(--shadow);
}

.button-primary {
    background: var(--accent);
    color: white;
}
.button-primary:hover {
    background: var(--accent-hover);
}
```

```javascript
// Step 2: Theme toggle with persistence
function initTheme() {
    // Check saved preference, then system preference
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    }
    // If no saved preference, the CSS @media query handles it
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const isDark = current === 'dark' ||
        (!current && window.matchMedia('(prefers-color-scheme: dark)').matches);

    const newTheme = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Run on page load (put in <head> to prevent flash)
initTheme();

// Listen for system preference changes
window.matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            // Only auto-switch if user hasn't manually chosen
            document.documentElement.setAttribute(
                'data-theme', e.matches ? 'dark' : 'light'
            );
        }
    });
```

The hardest part is migrating existing hardcoded colors to CSS variables. If you have a large codebase, I can help with a search-and-replace strategy. Tell me your stack and I'll adapt the approach.'''
    },
    {
        "instruction": r'''The form is confusing for users. Fix it.''',
        "output": r'''<think>
"The form is confusing" -- which form? What's confusing about it? Too many fields? Unclear labels? Bad validation messages? Poor layout? Required vs optional not clear? Users don't know what to enter? I don't know what the form does, how many fields it has, or what users are getting wrong. I need to see it or at least understand the form's purpose and the specific confusion points.
</think>

I'd need to see the form to give specific advice. Some questions:

1. **Which form and what does it do?** Registration, checkout, settings, data entry?
2. **What's confusing about it?** Users abandoning midway, submitting wrong data, asking support for help, or general feedback that it's hard to use?
3. **How many fields?** 5? 15? 50?

Here's a checklist of common form UX problems and fixes. These apply to almost any form:

```html
<!-- BEFORE: Common form UX mistakes -->
<form>
    <input type="text" name="name" placeholder="Name">
    <input type="text" name="email" placeholder="Email">
    <input type="text" name="phone" placeholder="Phone">
    <input type="text" name="company" placeholder="Company">
    <input type="text" name="address" placeholder="Address">
    <input type="text" name="city" placeholder="City">
    <input type="text" name="zip" placeholder="Zip">
    <textarea placeholder="Message"></textarea>
    <button>Submit</button>
</form>

<!-- Problems: placeholder-only labels disappear, no grouping, no indication
     of required vs optional, no validation, no input types, generic submit button -->


<!-- AFTER: User-friendly form -->
<form novalidate>
    <!-- Group related fields with clear section headers -->
    <fieldset>
        <legend>Contact Information</legend>

        <!-- Always use visible labels (not just placeholders) -->
        <div class="field">
            <label for="name">Full name <span class="required">*</span></label>
            <input type="text" id="name" name="name" required
                   autocomplete="name" placeholder="e.g., Jane Smith">
            <span class="field-error" id="name-error"></span>
        </div>

        <div class="field">
            <label for="email">Email address <span class="required">*</span></label>
            <input type="email" id="email" name="email" required
                   autocomplete="email" placeholder="jane@company.com">
            <span class="field-error" id="email-error"></span>
        </div>

        <div class="field">
            <label for="phone">Phone number <span class="optional">(optional)</span></label>
            <input type="tel" id="phone" name="phone"
                   autocomplete="tel" placeholder="(555) 123-4567">
        </div>
    </fieldset>

    <fieldset>
        <legend>Your Message</legend>
        <div class="field">
            <label for="message">How can we help? <span class="required">*</span></label>
            <textarea id="message" name="message" rows="4" required
                      placeholder="Describe your question or request..."></textarea>
            <span class="field-hint">We typically respond within 1 business day.</span>
        </div>
    </fieldset>

    <!-- Clear, specific button text -->
    <button type="submit">Send message</button>
</form>
```

```css
/* Form styling that guides the user */
.field { margin-bottom: 20px; }
.field label {
    display: block;
    font-weight: 500;
    margin-bottom: 4px;
}
.required { color: #dc2626; }
.optional { color: #9ca3af; font-weight: 400; font-size: 0.875rem; }
.field-hint { color: #6b7280; font-size: 0.875rem; margin-top: 4px; }
.field-error { color: #dc2626; font-size: 0.875rem; margin-top: 4px; display: none; }
.field-error.visible { display: block; }

input:focus, textarea:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
input.invalid { border-color: #dc2626; }
```

```text
Form UX rules:
1. Always use visible labels (never placeholder-only)
2. Mark required vs optional fields clearly
3. Group related fields with fieldset/legend
4. Use correct input types (email, tel, number, date)
5. Validate inline as user types, not only on submit
6. Show specific error messages ("Email must include @") not generic ("Invalid input")
7. Use autocomplete attributes (browsers fill in known data)
8. Put the submit button text as a verb: "Send message" not "Submit"
9. If the form is long (>7 fields), break into steps with a progress indicator
```

Share the form's HTML/component code and I'll give you the specific fixes.'''
    },
]
