"""Thinking-trace pairs: mobile web debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My mobile website layout is broken on iOS Safari. The viewport does not respect the meta tag and the page is zoomed in or elements overflow. My meta tag is:

<meta name="viewport" content="width=device-width, initial-scale=1">

But on iPhone, the page is wider than the screen and users have to scroll horizontally. Some elements extend past the viewport edge. How do I fix this?''',
        r'''<think>
The viewport meta tag looks correct. The issue is likely caused by:
1. Elements with fixed widths wider than the viewport (e.g., a 500px wide element on a 375px wide screen)
2. Elements with overflow not handled (tables, pre, code blocks, images)
3. CSS using vw units without accounting for scrollbar
4. Absolute/fixed positioning pushing elements off-screen
5. iOS Safari has specific quirks with viewport and the address bar

The most common cause is content that is wider than the viewport, which forces Safari to zoom out to fit it.
</think>

The viewport meta tag is correct, but content wider than the screen forces Safari to zoom out. Here is how to diagnose and fix:

```html
<!-- ============================================================ -->
<!-- STEP 1: Ensure proper viewport meta tag -->
<!-- ============================================================ -->

<!-- CORRECT: -->
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">

<!-- viewport-fit=cover is needed for devices with notches (iPhone X+) -->
<!-- to extend content into the safe area -->

<!-- WRONG patterns to avoid: -->
<!-- width=1024 forces desktop width -->
<!-- maximum-scale=1 prevents user zoom (accessibility issue) -->
<!-- user-scalable=no prevents pinch zoom (accessibility violation) -->
```

```css
/* ============================================================ */
/* STEP 2: Find and fix overflow causes */
/* ============================================================ */

/* DIAGNOSTIC: Add this temporarily to find overflowing elements */
* {
    outline: 1px solid red !important;
}

/* Or use this JS snippet in Safari inspector:
   document.querySelectorAll('*').forEach(el => {
       if (el.scrollWidth > document.documentElement.clientWidth) {
           el.style.outline = '3px solid red';
           console.log('Overflow:', el.tagName, el.className, el.scrollWidth);
       }
   });
*/

/* ============================================================ */
/* GLOBAL FIX: Prevent horizontal overflow */
/* ============================================================ */

html, body {
    /* Prevent horizontal scroll */
    overflow-x: hidden;
    /* Do NOT set width: 100vw -- this includes scrollbar width */
    width: 100%;
}

/* FIX 1: Images that overflow */
img, video, iframe, embed, object {
    max-width: 100%;
    height: auto;
}

/* FIX 2: Tables that overflow */
table {
    display: block;
    max-width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch; /* Smooth scroll on iOS */
}

/* FIX 3: Code blocks and pre that overflow */
pre, code {
    max-width: 100%;
    overflow-x: auto;
    word-wrap: break-word;
    white-space: pre-wrap; /* Wrap long lines */
}

/* FIX 4: Flexbox/Grid items that force width */
.container {
    max-width: 100%;
    box-sizing: border-box;
    padding: 0 16px; /* Safe padding for mobile */
}

/* FIX 5: vw units that include scrollbar */
/* BAD: */
/* .full-width { width: 100vw; } */
/* This is wider than the viewport by the scrollbar width */

/* GOOD: */
.full-width {
    width: 100%;
}

/* FIX 6: Fixed/absolute positioned elements */
.sidebar {
    position: fixed;
    /* BAD: left: -300px; -- can cause horizontal scroll */
    /* GOOD: transform to hide off-screen */
    transform: translateX(-100%);
    transition: transform 0.3s ease;
}
.sidebar.open {
    transform: translateX(0);
}

/* ============================================================ */
/* STEP 3: iOS Safari specific fixes */
/* ============================================================ */

/* Safe area insets for notched devices */
.header {
    padding-top: env(safe-area-inset-top);
    padding-left: env(safe-area-inset-left);
    padding-right: env(safe-area-inset-right);
}

.footer {
    padding-bottom: env(safe-area-inset-bottom);
}

/* iOS Safari 100vh includes the address bar height */
/* This causes elements to be taller than visible area */
/* BAD: */
/* .fullscreen { height: 100vh; } */

/* GOOD: Use dvh (dynamic viewport height) */
.fullscreen {
    height: 100dvh; /* Changes as address bar shows/hides */
    /* Fallback for older browsers */
    height: 100vh;
    height: 100dvh;
}

/* Or use CSS custom property with JS: */
/* document.documentElement.style.setProperty(
     '--vh', window.innerHeight * 0.01 + 'px'
   );
*/
.fullscreen-compat {
    height: calc(var(--vh, 1vh) * 100);
}

/* iOS Safari momentum scrolling */
.scroll-container {
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}

/* Prevent iOS zoom on input focus (font-size must be >= 16px) */
input, textarea, select {
    font-size: 16px; /* Prevents auto-zoom on iOS */
}
```

```javascript
// ============================================================
// STEP 4: JavaScript diagnostics for overflow
// ============================================================

function findOverflowingElements() {
    const docWidth = document.documentElement.clientWidth;
    const overflowing = [];

    document.querySelectorAll("*").forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.right > docWidth || rect.left < 0) {
            overflowing.push({
                element: el.tagName + (el.className ? "." + el.className : ""),
                width: rect.width,
                right: rect.right,
                overflow: rect.right - docWidth,
            });
        }
    });

    overflowing.sort((a, b) => b.overflow - a.overflow);
    console.table(overflowing.slice(0, 10));
    return overflowing;
}

// Run this in Safari Web Inspector on the device:
// findOverflowingElements();
```

**Mobile layout debugging checklist:**
1. All images: `max-width: 100%; height: auto;`
2. No `width: 100vw` -- use `width: 100%` instead
3. Input font-size >= 16px to prevent iOS auto-zoom
4. Use `100dvh` instead of `100vh` for full-height layouts
5. Add `viewport-fit=cover` and use `env(safe-area-inset-*)` for notched devices
6. Wrap tables in `overflow-x: auto` containers''',
    ),
    (
        "thinking/debugging",
        r'''Touch events on my mobile web app are causing problems. Scroll is janky, buttons have a 300ms delay, and passive event listener warnings appear in the console. How do I fix touch event handling for mobile?

Console warning: "[Violation] Added non-passive event listener to a scroll-blocking 'touchstart' event. Consider marking event listener as 'passive' to make the page more responsive."''',
        r'''<think>
Several touch event issues here:
1. The 300ms tap delay was historically added by mobile browsers to detect double-tap zoom. Modern browsers have removed this if you have the proper viewport meta tag, but it can still be an issue.
2. Passive event listeners: when you add a touchstart/touchmove listener, the browser cannot know if you will call preventDefault(), so it must wait before scrolling. Marking as passive tells the browser you will not prevent default, allowing immediate scrolling.
3. Janky scroll: caused by non-passive touch listeners or expensive event handlers running on the main thread.

Let me cover all fixes.
</think>

Touch event issues on mobile involve three separate problems: the tap delay, passive listeners, and scroll performance. Here is how to fix each:

```javascript
// ============================================================
// PROBLEM 1: 300ms tap delay
// ============================================================

// The 300ms delay exists because browsers wait to see if a single
// tap is actually a double-tap (for zoom). Modern browsers remove
// this delay IF you have the proper viewport meta tag:
// <meta name="viewport" content="width=device-width">
//
// If you still see delay, you can use touch-action CSS:

// CSS fix:
// button, a, .clickable { touch-action: manipulation; }
// "manipulation" allows pan and pinch-zoom but disables
// double-tap zoom, eliminating the 300ms delay.

// ============================================================
// PROBLEM 2: Passive event listeners
// ============================================================

// BAD: Non-passive listener blocks scrolling
document.addEventListener("touchstart", function(e) {
    // Browser warns because it must wait to see if you
    // call e.preventDefault() before it can scroll
    handleTouch(e);
});

// GOOD: Passive listener (cannot call preventDefault)
document.addEventListener("touchstart", function(e) {
    // e.preventDefault() would throw here -- but scroll is smooth
    handleTouch(e);
}, { passive: true });

// WHEN YOU NEED preventDefault():
// Some cases require preventing default behavior (e.g., custom
// drag-and-drop, pull-to-refresh override). Use passive: false
// only on specific elements, not document-level.

const draggable = document.getElementById("drag-target");
draggable.addEventListener("touchmove", function(e) {
    e.preventDefault(); // Prevent scroll while dragging
    handleDrag(e);
}, { passive: false }); // Explicit non-passive

// ============================================================
// PROBLEM 3: Janky scroll from expensive handlers
// ============================================================

// BAD: Expensive work in touch/scroll handler
document.addEventListener("scroll", function() {
    // This runs on EVERY scroll event (60+ times/sec)
    updateParallax();
    calculatePositions();
    renderOverlay();
}, { passive: true });

// GOOD: Debounce or use requestAnimationFrame
let ticking = false;
document.addEventListener("scroll", function() {
    if (!ticking) {
        requestAnimationFrame(() => {
            updateParallax();
            ticking = false;
        });
        ticking = true;
    }
}, { passive: true });

// BETTER: Use IntersectionObserver instead of scroll events
const observer = new IntersectionObserver(
    (entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add("visible");
            }
        });
    },
    { threshold: 0.1 }
);

document.querySelectorAll(".animate-on-scroll").forEach((el) => {
    observer.observe(el);
});

// ============================================================
// COMPLETE: Proper touch event handling patterns
// ============================================================

class TouchHandler {
    constructor(element) {
        this.element = element;
        this.startX = 0;
        this.startY = 0;
        this.isDragging = false;

        // Use passive for touchstart (just record position)
        element.addEventListener("touchstart", this.onStart.bind(this),
            { passive: true });

        // Non-passive for touchmove ONLY if we need to prevent scroll
        element.addEventListener("touchmove", this.onMove.bind(this),
            { passive: false });

        element.addEventListener("touchend", this.onEnd.bind(this),
            { passive: true });

        // Also handle pointer events (works for mouse + touch + pen)
        element.addEventListener("pointerdown", this.onPointerDown.bind(this));
        element.addEventListener("pointermove", this.onPointerMove.bind(this));
        element.addEventListener("pointerup", this.onPointerUp.bind(this));
    }

    onStart(e) {
        const touch = e.touches[0];
        this.startX = touch.clientX;
        this.startY = touch.clientY;
        this.isDragging = false;
    }

    onMove(e) {
        if (!this.isDragging) {
            const touch = e.touches[0];
            const dx = Math.abs(touch.clientX - this.startX);
            const dy = Math.abs(touch.clientY - this.startY);

            // Determine if this is a horizontal swipe
            if (dx > 10 && dx > dy) {
                this.isDragging = true;
                e.preventDefault(); // Prevent vertical scroll during swipe
            }
        }

        if (this.isDragging) {
            e.preventDefault();
            const touch = e.touches[0];
            this.handleSwipe(touch.clientX - this.startX);
        }
    }

    onEnd(e) {
        if (this.isDragging) {
            this.finishSwipe();
        }
        this.isDragging = false;
    }

    // Pointer events (unified API for touch + mouse)
    onPointerDown(e) {
        this.element.setPointerCapture(e.pointerId);
        this.startX = e.clientX;
        this.startY = e.clientY;
    }

    onPointerMove(e) {
        if (!e.pressure) return; // Not pressed
        const dx = e.clientX - this.startX;
        this.handleSwipe(dx);
    }

    onPointerUp(e) {
        this.element.releasePointerCapture(e.pointerId);
        this.finishSwipe();
    }

    handleSwipe(deltaX) {
        // Apply transform for visual feedback
        this.element.style.transform = "translateX(" + deltaX + "px)";
    }

    finishSwipe() {
        this.element.style.transform = "";
    }
}

// Usage:
// const handler = new TouchHandler(document.getElementById("swipeable"));
```

```css
/* CSS touch optimization */
.swipeable {
    /* Enable hardware acceleration for smooth animations */
    will-change: transform;
    /* Disable text selection during touch */
    user-select: none;
    -webkit-user-select: none;
    /* Remove tap highlight on mobile */
    -webkit-tap-highlight-color: transparent;
    /* Enable touch manipulation without delay */
    touch-action: manipulation;
}

/* For scrollable containers */
.scroll-container {
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch; /* Momentum scrolling on iOS */
    overscroll-behavior: contain; /* Prevent pull-to-refresh */
}

/* For draggable elements - disable scroll in drag direction */
.horizontal-drag {
    touch-action: pan-y; /* Allow vertical scroll, block horizontal */
}
.vertical-drag {
    touch-action: pan-x; /* Allow horizontal scroll, block vertical */
}
```

**Key rules:**
1. Always use `{ passive: true }` for scroll/touch listeners unless you need `preventDefault()`
2. Use `touch-action: manipulation` CSS to remove the 300ms tap delay
3. Prefer Pointer Events API over Touch Events for cross-platform support
4. Use `requestAnimationFrame` to throttle visual updates in scroll handlers
5. Use `IntersectionObserver` instead of scroll event listeners when possible''',
    ),
    (
        "thinking/debugging",
        r'''My web app has several Safari-specific bugs that do not appear in Chrome or Firefox. I am seeing issues with: date parsing, flexbox rendering, local storage in private mode, and CSS backdrop-filter. How do I handle Safari quirks?''',
        r'''<think>
Safari has many known quirks:
1. Date parsing: Safari does not support date strings with dashes (YYYY-MM-DD format with time)
2. Flexbox: Safari has bugs with flex-basis, gap in flexbox, and nested flexbox
3. LocalStorage: In private browsing, it used to throw on setItem (fixed in newer versions but quota is very limited)
4. backdrop-filter: Needs -webkit- prefix
5. CSS features: Some features need -webkit- prefix or have different behavior

Let me provide specific fixes for each.
</think>

Safari has numerous platform-specific behaviors. Here are the most common issues and their fixes:

```javascript
// ============================================================
// QUIRK 1: Date parsing differences
// ============================================================

// Safari does NOT parse these date formats:
new Date("2024-01-15 10:30:00");     // NaN in Safari!
new Date("2024-01-15T10:30:00");     // OK in all browsers
new Date("Jan 15, 2024 10:30:00");   // OK in all browsers

// FIX: Always use ISO 8601 format with T separator
function parseDate(dateString) {
    // Replace space with T for Safari compatibility
    const isoString = dateString.replace(" ", "T");

    // Ensure timezone is specified
    if (!isoString.includes("Z") && !isoString.includes("+") &&
        !isoString.includes("-", 10)) {
        // No timezone -- treat as UTC to avoid inconsistency
        return new Date(isoString + "Z");
    }
    return new Date(isoString);
}

// ALTERNATIVE: Parse manually for full control
function parseDateSafe(str) {
    // Handles "2024-01-15 10:30:00" format
    const parts = str.match(
        /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/
    );
    if (!parts) return new Date(str);
    return new Date(
        Date.UTC(
            parseInt(parts[1]),
            parseInt(parts[2]) - 1,  // Month is 0-indexed
            parseInt(parts[3]),
            parseInt(parts[4]),
            parseInt(parts[5]),
            parseInt(parts[6])
        )
    );
}

// ============================================================
// QUIRK 2: LocalStorage in Private Browsing
// ============================================================

// Old Safari (< 14) throws QuotaExceededError on ANY setItem
// in private browsing. Newer Safari allows it but with
// limited storage that is cleared when the tab closes.

function safeStorage() {
    const storage = {
        _fallback: {},

        getItem(key) {
            try {
                return localStorage.getItem(key);
            } catch (e) {
                return this._fallback[key] || null;
            }
        },

        setItem(key, value) {
            try {
                localStorage.setItem(key, value);
            } catch (e) {
                // QuotaExceededError or SecurityError in private mode
                console.warn("localStorage unavailable, using memory fallback");
                this._fallback[key] = String(value);
            }
        },

        removeItem(key) {
            try {
                localStorage.removeItem(key);
            } catch (e) {
                delete this._fallback[key];
            }
        },

        isAvailable() {
            try {
                const test = "__storage_test__";
                localStorage.setItem(test, "1");
                localStorage.removeItem(test);
                return true;
            } catch (e) {
                return false;
            }
        },
    };

    return storage;
}

const storage = safeStorage();
storage.setItem("user", JSON.stringify({ name: "Alice" }));

// ============================================================
// QUIRK 3: Safari flexbox bugs
// ============================================================
```

```css
/* Safari flexbox issues and fixes */

/* BUG: gap property in flexbox not supported in Safari < 14.1 */
.flex-container {
    display: flex;
    /* gap: 16px; -- not supported in old Safari */

    /* FIX: Use margin instead of gap */
    flex-wrap: wrap;
    margin: -8px; /* Negative margin to offset child margins */
}
.flex-container > * {
    margin: 8px; /* Simulates 16px gap */
}

/* Modern: Use @supports to use gap where available */
@supports (gap: 16px) {
    .flex-container {
        gap: 16px;
        margin: 0;
    }
    .flex-container > * {
        margin: 0;
    }
}

/* BUG: flex-basis with padding collapses in Safari */
.flex-item {
    /* BAD in Safari: */
    /* flex: 1 0 200px; */
    /* padding: 20px; */
    /* Safari may calculate width wrong */

    /* FIX: Use min-width instead of flex-basis */
    flex: 1;
    min-width: 200px;
    padding: 20px;
    box-sizing: border-box;
}

/* BUG: Nested flexbox height calculation */
.outer {
    display: flex;
    flex-direction: column;
    height: 100vh;
}
.inner {
    flex: 1;
    display: flex;
    /* Safari may not stretch inner flex container */
    /* FIX: Add explicit height */
    min-height: 0; /* Allows flex item to shrink below content size */
}

/* ============================================================ */
/* QUIRK 4: backdrop-filter needs prefix */
/* ============================================================ */

.glass-effect {
    /* Standard (Chrome, Firefox) */
    backdrop-filter: blur(10px) saturate(180%);
    /* Safari prefix (required) */
    -webkit-backdrop-filter: blur(10px) saturate(180%);
    background: rgba(255, 255, 255, 0.7);
}

/* ============================================================ */
/* QUIRK 5: CSS features with Safari differences */
/* ============================================================ */

/* Position: sticky in Safari requires -webkit- prefix on older versions */
.sticky-header {
    position: -webkit-sticky; /* Safari */
    position: sticky;
    top: 0;
    z-index: 100;
}

/* Safari 100vh includes address bar (already covered in viewport topic) */
.full-height {
    height: 100vh;
    height: -webkit-fill-available; /* Safari fix */
    height: 100dvh; /* Modern fix */
}

/* Smooth scrolling: Safari supports it but behavior differs */
html {
    scroll-behavior: smooth;
    /* Safari on iOS ignores scroll-behavior for programmatic scrolls */
    /* Use JS scrollIntoView with behavior option instead */
}

/* Input styling: Safari adds default styles */
input, textarea, select {
    -webkit-appearance: none; /* Remove Safari default styling */
    appearance: none;
    border-radius: 0; /* Safari adds rounded corners */
    font-size: 16px; /* Prevent auto-zoom */
}
```

```javascript
// ============================================================
// QUIRK 6: Safari feature detection
// ============================================================

function isSafari() {
    // Feature detection is better than user agent sniffing
    // But sometimes you need to know:
    const ua = navigator.userAgent;
    return /^((?!chrome|android).)*safari/i.test(ua);
}

// Better: Use feature detection
function hasBackdropFilter() {
    return CSS.supports("backdrop-filter", "blur(1px)") ||
           CSS.supports("-webkit-backdrop-filter", "blur(1px)");
}

function hasFlexGap() {
    // Create a test element to check flex gap support
    const el = document.createElement("div");
    el.style.display = "flex";
    el.style.gap = "1px";
    el.appendChild(document.createElement("div"));
    el.appendChild(document.createElement("div"));
    document.body.appendChild(el);
    const hasGap = el.scrollHeight === 1;
    document.body.removeChild(el);
    return hasGap;
}

// Apply polyfills based on feature detection
if (!hasFlexGap()) {
    document.documentElement.classList.add("no-flex-gap");
}
```

**Safari debugging tips:**
1. Use Safari Web Inspector (Develop menu) for debugging on macOS
2. For iOS: Enable Web Inspector in Settings > Safari > Advanced
3. Use `@supports` CSS queries for progressive enhancement
4. Always test date parsing with ISO 8601 format (`T` separator)
5. Add `-webkit-` prefix for `backdrop-filter`, `appearance`, `sticky`
6. Test localStorage in private browsing mode''',
    ),
    (
        "thinking/debugging",
        r'''My Progressive Web App (PWA) is not showing the "Add to Home Screen" install prompt on mobile. The manifest.json is configured and the service worker is registered, but the beforeinstallprompt event never fires. What are the requirements?''',
        r'''<think>
PWA install criteria are strict and browser-specific. The beforeinstallprompt event requires:

For Chrome/Android:
1. Valid web app manifest with required fields
2. Registered service worker with a fetch handler
3. Served over HTTPS (or localhost)
4. Not already installed
5. User engagement heuristic (user has interacted with the domain for some time)
6. Manifest must have: name or short_name, icons (192px and 512px), start_url, display (standalone/fullscreen/minimal-ui)

For Safari/iOS:
- No beforeinstallprompt event at all
- Users must manually use "Add to Home Screen" from share menu
- manifest.json support is limited

Let me provide a comprehensive checklist.
</think>

PWA installation requirements are strict and differ by browser. Here is a complete checklist and implementation:

```json
// ============================================================
// manifest.json - REQUIRED fields for install prompt
// ============================================================
{
    "name": "My Application",
    "short_name": "MyApp",
    "description": "A progressive web application",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#4285f4",
    "orientation": "any",
    "icons": [
        {
            "src": "/icons/icon-192.png",
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any"
        },
        {
            "src": "/icons/icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any"
        },
        {
            "src": "/icons/icon-maskable-192.png",
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "maskable"
        },
        {
            "src": "/icons/icon-maskable-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable"
        }
    ],
    "scope": "/",
    "prefer_related_applications": false
}
```

```html
<!-- ============================================================ -->
<!-- HTML head - Required link tags -->
<!-- ============================================================ -->

<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#4285f4">

<!-- iOS-specific (Safari does not use manifest for everything) -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="MyApp">
<link rel="apple-touch-icon" href="/icons/icon-192.png">

<!-- Splash screens for iOS (optional but recommended) -->
<link rel="apple-touch-startup-image" href="/splash/splash.png">
```

```javascript
// ============================================================
// Service Worker - MUST have a fetch handler
// ============================================================

// service-worker.js
// Chrome requires a service worker with a fetch event listener
self.addEventListener("fetch", (event) => {
    // Even a pass-through handler satisfies the requirement
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request);
        })
    );
});

// ============================================================
// Install prompt handling - main.js
// ============================================================

let deferredPrompt = null;

// Listen for the browser's install prompt
window.addEventListener("beforeinstallprompt", (e) => {
    console.log("Install prompt available!");

    // Prevent the default mini-infobar from appearing
    e.preventDefault();

    // Save the event for later use
    deferredPrompt = e;

    // Show your custom install UI
    showInstallButton();
});

function showInstallButton() {
    const btn = document.getElementById("install-btn");
    if (btn) {
        btn.style.display = "block";
        btn.addEventListener("click", async () => {
            if (!deferredPrompt) return;

            // Show the browser's install prompt
            deferredPrompt.prompt();

            // Wait for user's choice
            const result = await deferredPrompt.userChoice;
            console.log("Install choice:", result.outcome);
            // outcome is "accepted" or "dismissed"

            deferredPrompt = null;
            btn.style.display = "none";
        });
    }
}

// Detect if already installed
window.addEventListener("appinstalled", () => {
    console.log("App was installed");
    deferredPrompt = null;
    // Hide install button
    const btn = document.getElementById("install-btn");
    if (btn) btn.style.display = "none";
});

// Check if running as installed PWA
function isRunningAsPWA() {
    // Check display mode
    if (window.matchMedia("(display-mode: standalone)").matches) {
        return true;
    }
    // iOS Safari
    if (window.navigator.standalone === true) {
        return true;
    }
    return false;
}

// ============================================================
// DIAGNOSTIC: Check why install prompt is not showing
// ============================================================

async function diagnoseInstallability() {
    const issues = [];

    // 1. Check HTTPS
    if (location.protocol !== "https:" && location.hostname !== "localhost") {
        issues.push("Not served over HTTPS");
    }

    // 2. Check manifest
    const manifestLink = document.querySelector('link[rel="manifest"]');
    if (!manifestLink) {
        issues.push("No <link rel='manifest'> found");
    } else {
        try {
            const resp = await fetch(manifestLink.href);
            const manifest = await resp.json();

            if (!manifest.name && !manifest.short_name) {
                issues.push("Manifest missing name or short_name");
            }
            if (!manifest.start_url) {
                issues.push("Manifest missing start_url");
            }
            if (!manifest.display ||
                !["standalone", "fullscreen", "minimal-ui"].includes(manifest.display)) {
                issues.push("Manifest display must be standalone, fullscreen, or minimal-ui");
            }
            if (!manifest.icons || manifest.icons.length === 0) {
                issues.push("Manifest has no icons");
            } else {
                const sizes = manifest.icons.map((i) => i.sizes);
                if (!sizes.some((s) => s === "192x192")) {
                    issues.push("Missing 192x192 icon");
                }
                if (!sizes.some((s) => s === "512x512")) {
                    issues.push("Missing 512x512 icon");
                }
            }
        } catch (e) {
            issues.push("Cannot fetch/parse manifest: " + e.message);
        }
    }

    // 3. Check service worker
    if ("serviceWorker" in navigator) {
        const reg = await navigator.serviceWorker.getRegistration();
        if (!reg) {
            issues.push("No service worker registered");
        } else if (!reg.active) {
            issues.push("Service worker not active yet");
        }
    } else {
        issues.push("Service workers not supported");
    }

    // 4. Check if already installed
    if (isRunningAsPWA()) {
        issues.push("App is already installed (running in standalone mode)");
    }

    if (issues.length === 0) {
        console.log("All install criteria met! The prompt should appear.");
        console.log("Note: Chrome requires user engagement before showing prompt.");
    } else {
        console.log("Install issues found:");
        issues.forEach((issue) => console.log("  - " + issue));
    }

    return issues;
}

// Run: diagnoseInstallability().then(console.log);

// ============================================================
// Chrome DevTools: Application tab > Manifest section
// shows installability status and any errors
// ============================================================
```

**PWA install prompt requirements:**
1. HTTPS (or localhost for development)
2. Web manifest with: name/short_name, start_url, display, 192px + 512px icons
3. Service worker with a `fetch` event handler
4. User engagement (Chrome waits for some interaction before showing prompt)
5. Not already installed
6. Note: Safari/iOS has NO `beforeinstallprompt` -- users must manually "Add to Home Screen"''',
    ),
    (
        "thinking/debugging",
        r'''When I rotate my mobile device from portrait to landscape, the layout breaks. Elements resize incorrectly and there is a flash of wrong layout. The orientationchange event fires but the new dimensions are not yet available. How do I handle orientation changes properly?''',
        r'''<think>
The orientationchange event fires BEFORE the viewport dimensions have actually updated. This means window.innerWidth/innerHeight still reflect the old orientation when the event fires. This is a well-known timing issue.

Fixes:
1. Use the resize event instead (fires after dimensions update)
2. Use matchMedia for orientation detection
3. Use CSS media queries (no JS needed for most cases)
4. If JS is needed, debounce the resize event
</think>

The `orientationchange` event fires before viewport dimensions update. Here is how to handle orientation changes correctly:

```javascript
// ============================================================
// PROBLEM: orientationchange gives stale dimensions
// ============================================================

// BAD: dimensions are wrong when this fires
window.addEventListener("orientationchange", () => {
    console.log(window.innerWidth);  // WRONG -- still old value!
    console.log(window.innerHeight); // WRONG -- still old value!
    resizeLayout();
});

// ============================================================
// FIX 1: Use resize event instead (recommended)
// ============================================================

// The resize event fires AFTER dimensions have updated
let resizeTimer;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        // Dimensions are correct here
        const width = window.innerWidth;
        const height = window.innerHeight;
        const isLandscape = width > height;
        console.log(`${width}x${height} - ${isLandscape ? "landscape" : "portrait"}`);
        adjustLayout(isLandscape);
    }, 100); // Small debounce to avoid rapid-fire during rotation animation
});

// ============================================================
// FIX 2: Use matchMedia (best for orientation detection)
// ============================================================

const landscapeQuery = window.matchMedia("(orientation: landscape)");

// Modern API: addEventListener
landscapeQuery.addEventListener("change", (e) => {
    if (e.matches) {
        console.log("Switched to landscape");
        document.body.classList.add("landscape");
        document.body.classList.remove("portrait");
    } else {
        console.log("Switched to portrait");
        document.body.classList.add("portrait");
        document.body.classList.remove("landscape");
    }
});

// Check initial orientation
if (landscapeQuery.matches) {
    document.body.classList.add("landscape");
} else {
    document.body.classList.add("portrait");
}

// ============================================================
// FIX 3: Use CSS media queries (no JS needed)
// ============================================================
```

```css
/* CSS-only orientation handling (preferred for layout changes) */

/* Portrait layout */
@media (orientation: portrait) {
    .grid {
        grid-template-columns: 1fr;
    }
    .sidebar {
        display: none;
    }
    .main-content {
        width: 100%;
    }
}

/* Landscape layout */
@media (orientation: landscape) {
    .grid {
        grid-template-columns: 250px 1fr;
    }
    .sidebar {
        display: block;
    }
    .main-content {
        width: calc(100% - 250px);
    }
}

/* Combine with width for more specific targeting */
@media (orientation: landscape) and (max-height: 500px) {
    /* Landscape on small phone -- very limited vertical space */
    .header {
        height: 40px; /* Compact header */
    }
    .nav {
        display: none; /* Hide nav to save space */
    }
}

/* Smooth transitions during orientation change */
.layout-container {
    transition: all 0.3s ease;
}

/* Prevent layout flash during rotation */
@media (orientation: portrait), (orientation: landscape) {
    html {
        /* Prevent text size adjustment during orientation change */
        -webkit-text-size-adjust: 100%;
        text-size-adjust: 100%;
    }
}
```

```javascript
// ============================================================
// FIX 4: Screen Orientation API (modern browsers)
// ============================================================

if (screen.orientation) {
    // Read current orientation
    console.log("Type:", screen.orientation.type);
    // "portrait-primary", "portrait-secondary",
    // "landscape-primary", "landscape-secondary"
    console.log("Angle:", screen.orientation.angle);
    // 0, 90, 180, 270

    // Listen for changes
    screen.orientation.addEventListener("change", () => {
        console.log("New orientation:", screen.orientation.type);
        console.log("New angle:", screen.orientation.angle);

        // Dimensions ARE correct here (unlike orientationchange)
        console.log("Width:", window.innerWidth);
        console.log("Height:", window.innerHeight);
    });

    // Lock orientation (requires fullscreen on mobile)
    async function lockLandscape() {
        try {
            await screen.orientation.lock("landscape");
            console.log("Locked to landscape");
        } catch (e) {
            // Requires fullscreen mode on mobile browsers
            console.log("Cannot lock orientation:", e.message);
        }
    }
}

// ============================================================
// FIX 5: Prevent layout flash with transition blocking
// ============================================================

class OrientationHandler {
    constructor() {
        this.isTransitioning = false;
        this.setupListeners();
    }

    setupListeners() {
        // Detect start of orientation change
        window.addEventListener("orientationchange", () => {
            this.startTransition();
        });

        // Detect when dimensions have settled
        window.addEventListener("resize", () => {
            if (this.isTransitioning) {
                this.endTransition();
            }
        });
    }

    startTransition() {
        this.isTransitioning = true;
        // Add a class that hides the flash
        document.body.classList.add("orientation-transitioning");
    }

    endTransition() {
        // Wait a frame for the browser to finish rendering
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this.isTransitioning = false;
                document.body.classList.remove("orientation-transitioning");
                // Now update any JS-dependent layout
                this.updateLayout();
            });
        });
    }

    updateLayout() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        const isLandscape = width > height;

        // Update JS-dependent elements
        const canvas = document.getElementById("game-canvas");
        if (canvas) {
            canvas.width = width;
            canvas.height = height;
        }

        // Dispatch custom event for components
        window.dispatchEvent(
            new CustomEvent("orientationsettled", {
                detail: { width, height, isLandscape },
            })
        );
    }
}

// const handler = new OrientationHandler();
```

```css
/* Hide flash during orientation transition */
.orientation-transitioning * {
    transition: none !important;
}
.orientation-transitioning {
    overflow: hidden;
}
```

**Orientation change best practices:**
1. Use CSS `@media (orientation: ...)` for layout changes (no JS needed)
2. Use `matchMedia("(orientation: landscape)")` for JS detection
3. Use `resize` event instead of `orientationchange` for accurate dimensions
4. Add `-webkit-text-size-adjust: 100%` to prevent text resizing
5. Use `screen.orientation` API for modern browsers
6. Debounce resize handlers to avoid performance issues during rotation animation''',
    ),
]
