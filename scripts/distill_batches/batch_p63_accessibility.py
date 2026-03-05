"""Frontend — accessibility, ARIA patterns, and inclusive design."""

PAIRS = [
    (
        "frontend/accessibility-patterns",
        "Show web accessibility patterns: ARIA roles, keyboard navigation, focus management, and screen reader support.",
        '''Web accessibility (a11y) patterns:

```html
<!-- --- Accessible modal dialog --- -->
<div id="modal-overlay" class="modal-overlay" role="presentation"
     aria-hidden="true">
  <div role="dialog"
       aria-modal="true"
       aria-labelledby="modal-title"
       aria-describedby="modal-desc"
       class="modal">
    <h2 id="modal-title">Confirm Delete</h2>
    <p id="modal-desc">Are you sure you want to delete this item?
       This action cannot be undone.</p>

    <div class="modal-actions">
      <button type="button" class="btn-secondary"
              data-action="cancel">Cancel</button>
      <button type="button" class="btn-danger"
              data-action="confirm" autofocus>Delete</button>
    </div>

    <button type="button" class="modal-close"
            aria-label="Close dialog">
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M6 6l12 12M6 18L18 6" stroke="currentColor"
              stroke-width="2" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
</div>


<!-- --- Accessible form --- -->
<form aria-labelledby="form-title" novalidate>
  <h2 id="form-title">Create Account</h2>

  <div class="field">
    <label for="email">Email address <span aria-hidden="true">*</span></label>
    <input type="email" id="email" name="email"
           required
           autocomplete="email"
           aria-required="true"
           aria-invalid="false"
           aria-describedby="email-hint email-error" />
    <span id="email-hint" class="hint">We'll never share your email.</span>
    <span id="email-error" class="error" role="alert" hidden>
      Please enter a valid email address.
    </span>
  </div>

  <div class="field">
    <label for="password">Password <span aria-hidden="true">*</span></label>
    <input type="password" id="password" name="password"
           required
           minlength="8"
           autocomplete="new-password"
           aria-required="true"
           aria-describedby="password-reqs" />
    <div id="password-reqs" class="hint">
      <p>Password must contain:</p>
      <ul>
        <li id="req-length" aria-live="polite">
          <span aria-hidden="true">✗</span> At least 8 characters
        </li>
        <li id="req-upper" aria-live="polite">
          <span aria-hidden="true">✗</span> One uppercase letter
        </li>
        <li id="req-number" aria-live="polite">
          <span aria-hidden="true">✗</span> One number
        </li>
      </ul>
    </div>
  </div>

  <button type="submit">Create Account</button>
</form>


<!-- --- Accessible tabs --- -->
<div class="tabs">
  <div role="tablist" aria-label="Account settings">
    <button role="tab" id="tab-profile"
            aria-selected="true"
            aria-controls="panel-profile"
            tabindex="0">Profile</button>
    <button role="tab" id="tab-security"
            aria-selected="false"
            aria-controls="panel-security"
            tabindex="-1">Security</button>
    <button role="tab" id="tab-billing"
            aria-selected="false"
            aria-controls="panel-billing"
            tabindex="-1">Billing</button>
  </div>

  <div role="tabpanel" id="panel-profile"
       aria-labelledby="tab-profile"
       tabindex="0">
    <h3>Profile Settings</h3>
    <!-- Panel content -->
  </div>
  <div role="tabpanel" id="panel-security"
       aria-labelledby="tab-security"
       tabindex="0" hidden>
    <h3>Security Settings</h3>
  </div>
  <div role="tabpanel" id="panel-billing"
       aria-labelledby="tab-billing"
       tabindex="0" hidden>
    <h3>Billing Settings</h3>
  </div>
</div>


<!-- --- Skip navigation --- -->
<a href="#main-content" class="skip-link">
  Skip to main content
</a>

<!-- --- Live region for dynamic updates --- -->
<div aria-live="polite" aria-atomic="true" class="sr-only"
     id="status-announcer">
  <!-- JS updates this to announce changes to screen readers -->
</div>
```

```javascript
// --- Focus trap for modals ---

function trapFocus(element) {
  const focusable = element.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  element.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
      return;
    }
    if (e.key !== 'Tab') return;

    if (e.shiftKey) {
      if (document.activeElement === first) {
        last.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  });

  first.focus();
}


// --- Tab keyboard navigation ---

function initTabs(tablist) {
  const tabs = tablist.querySelectorAll('[role="tab"]');

  tablist.addEventListener('keydown', (e) => {
    const current = Array.from(tabs).indexOf(document.activeElement);
    let next;

    switch (e.key) {
      case 'ArrowRight':
        next = (current + 1) % tabs.length;
        break;
      case 'ArrowLeft':
        next = (current - 1 + tabs.length) % tabs.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = tabs.length - 1;
        break;
      default:
        return;
    }

    e.preventDefault();
    activateTab(tabs[next]);
  });
}

function activateTab(tab) {
  const tablist = tab.closest('[role="tablist"]');
  const tabs = tablist.querySelectorAll('[role="tab"]');

  tabs.forEach(t => {
    t.setAttribute('aria-selected', 'false');
    t.setAttribute('tabindex', '-1');
    document.getElementById(t.getAttribute('aria-controls')).hidden = true;
  });

  tab.setAttribute('aria-selected', 'true');
  tab.setAttribute('tabindex', '0');
  tab.focus();
  document.getElementById(tab.getAttribute('aria-controls')).hidden = false;
}


// --- Announce dynamic changes ---

function announce(message, priority = 'polite') {
  const announcer = document.getElementById('status-announcer');
  announcer.setAttribute('aria-live', priority);
  announcer.textContent = '';
  requestAnimationFrame(() => {
    announcer.textContent = message;
  });
}

// announce('Item deleted successfully');
// announce('Error: please fix the form', 'assertive');
```

```css
/* --- Screen reader only (visually hidden) --- */
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

/* --- Skip link --- */
.skip-link {
  position: absolute;
  top: -100%;
  left: 0;
  z-index: 1000;
  padding: 1rem;
  background: #000;
  color: #fff;
}
.skip-link:focus {
  top: 0;
}

/* --- Focus visible --- */
:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

/* --- Reduced motion --- */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Accessibility patterns:
1. **`aria-modal` + focus trap** — modal keeps focus inside until dismissed
2. **`aria-describedby`** — link hints and errors to form inputs
3. **Tab keyboard nav** — Arrow keys move between tabs, Tab moves to panel
4. **`aria-live="polite"`** — announce dynamic changes to screen readers
5. **`prefers-reduced-motion`** — respect user's motion sensitivity preference'''
    ),
    (
        "frontend/web-animations",
        "Show web animation patterns: CSS animations, transitions, Intersection Observer, and GSAP-style patterns.",
        '''Web animation patterns:

```css
/* --- CSS transitions --- */

.card {
  transform: translateY(0);
  opacity: 1;
  transition: transform 0.3s ease-out, opacity 0.3s ease-out,
              box-shadow 0.3s ease-out;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
}

/* Staggered entrance */
.list-item {
  opacity: 0;
  transform: translateY(20px);
  animation: slideUp 0.4s ease-out forwards;
}

.list-item:nth-child(1) { animation-delay: 0.05s; }
.list-item:nth-child(2) { animation-delay: 0.10s; }
.list-item:nth-child(3) { animation-delay: 0.15s; }
.list-item:nth-child(4) { animation-delay: 0.20s; }
.list-item:nth-child(5) { animation-delay: 0.25s; }

@keyframes slideUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}


/* --- Loading spinner --- */

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}


/* --- Skeleton loading --- */

.skeleton {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%, #e0e0e0 37%, #f0f0f0 63%
  );
  background-size: 400% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.skeleton-text {
  height: 1em;
  margin-bottom: 0.5em;
}

.skeleton-text:last-child {
  width: 60%;
}


/* --- Page transition --- */

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideInRight {
  from { transform: translateX(30px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

.page-enter {
  animation: fadeIn 0.3s ease-out, slideInRight 0.3s ease-out;
}
```

```javascript
// --- Intersection Observer for scroll animations ---

function animateOnScroll(selector, animationClass = 'animate-in') {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add(animationClass);
          observer.unobserve(entry.target); // Animate once
        }
      });
    },
    {
      threshold: 0.1,     // Trigger when 10% visible
      rootMargin: '0px 0px -50px 0px', // Slight offset
    }
  );

  document.querySelectorAll(selector).forEach((el) => {
    observer.observe(el);
  });
}

// Usage:
// animateOnScroll('.reveal');


// --- Web Animations API ---

function animateElement(element, keyframes, options = {}) {
  const defaults = {
    duration: 300,
    easing: 'ease-out',
    fill: 'forwards',
  };

  return element.animate(keyframes, { ...defaults, ...options });
}

// Fade in
animateElement(element, [
  { opacity: 0, transform: 'translateY(20px)' },
  { opacity: 1, transform: 'translateY(0)' },
]);

// Shake (error feedback)
function shake(element) {
  return element.animate([
    { transform: 'translateX(0)' },
    { transform: 'translateX(-10px)' },
    { transform: 'translateX(10px)' },
    { transform: 'translateX(-5px)' },
    { transform: 'translateX(5px)' },
    { transform: 'translateX(0)' },
  ], { duration: 400, easing: 'ease-in-out' });
}


// --- Staggered list animation ---

function staggerIn(elements, delay = 50) {
  return Array.from(elements).map((el, i) =>
    el.animate(
      [
        { opacity: 0, transform: 'translateY(20px)' },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      {
        duration: 400,
        delay: i * delay,
        easing: 'ease-out',
        fill: 'forwards',
      }
    )
  );
}


// --- Smooth counter animation ---

function animateCounter(element, target, duration = 1000) {
  const start = parseInt(element.textContent) || 0;
  const startTime = performance.now();

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);

    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(start + (target - start) * eased);

    element.textContent = current.toLocaleString();

    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }

  requestAnimationFrame(update);
}

// animateCounter(document.getElementById('stat'), 12450);


// --- View Transitions API (modern browsers) ---

async function navigateWithTransition(url) {
  if (!document.startViewTransition) {
    window.location.href = url;
    return;
  }

  const response = await fetch(url);
  const html = await response.text();

  document.startViewTransition(() => {
    document.documentElement.innerHTML = html;
  });
}
```

Animation patterns:
1. **`IntersectionObserver`** — trigger animations when elements scroll into view
2. **Web Animations API** — JavaScript-controlled animations with promises
3. **Skeleton loading** — shimmer effect placeholder while content loads
4. **Staggered delays** — offset children animations for cascading effect
5. **View Transitions API** — smooth page-to-page transitions (progressive enhancement)'''
    ),
]
"""
