"""
Batch p1088: React accessibility patterns.
ARIA patterns, keyboard navigation, screen reader support, focus management, color contrast utilities.
"""

PAIRS = [
    (
        "react/accessibility",
        r'''Build a comprehensive ARIA-compliant combobox (autocomplete) component in React with TypeScript. Include proper roles, states, keyboard navigation (arrow keys, enter, escape), screen reader announcements, and support for async option loading.''',
        r'''A fully ARIA-compliant combobox with keyboard navigation and live announcements:

```typescript
import React, { useCallback, useEffect, useId, useRef, useState } from "react";

interface ComboboxOption {
  id: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

interface ComboboxProps {
  label: string;
  options: ComboboxOption[];
  value?: string;
  onChange: (value: string | null, option: ComboboxOption | null) => void;
  onInputChange?: (query: string) => void;
  placeholder?: string;
  loading?: boolean;
  disabled?: boolean;
  required?: boolean;
  error?: string;
  noResultsMessage?: string;
}

export function Combobox({
  label,
  options,
  value,
  onChange,
  onInputChange,
  placeholder = "Type to search...",
  loading = false,
  disabled = false,
  required = false,
  error,
  noResultsMessage = "No results found",
}: ComboboxProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [announcement, setAnnouncement] = useState("");

  const listboxId = `${id}-listbox`;
  const labelId = `${id}-label`;
  const errorId = `${id}-error`;
  const statusId = `${id}-status`;

  // Find the selected option
  const selectedOption = options.find((o) => o.id === value);

  // Sync input value with selection
  useEffect(() => {
    if (selectedOption && !isOpen) {
      setInputValue(selectedOption.label);
    }
  }, [selectedOption, isOpen]);

  // Get enabled options for navigation
  const enabledOptions = options.filter((o) => !o.disabled);

  function announce(message: string) {
    // Clear first to ensure repeat announcements are read
    setAnnouncement("");
    requestAnimationFrame(() => setAnnouncement(message));
  }

  function openListbox() {
    if (disabled) return;
    setIsOpen(true);
    setActiveIndex(-1);
    announce(`${options.length} results available. Use arrow keys to navigate.`);
  }

  function closeListbox() {
    setIsOpen(false);
    setActiveIndex(-1);
  }

  function selectOption(option: ComboboxOption) {
    if (option.disabled) return;
    setInputValue(option.label);
    onChange(option.id, option);
    closeListbox();
    announce(`${option.label} selected`);
    inputRef.current?.focus();
  }

  function clearSelection() {
    setInputValue("");
    onChange(null, null);
    onInputChange?.("");
    announce("Selection cleared");
  }

  // Scroll active option into view
  useEffect(() => {
    if (activeIndex < 0 || !listboxRef.current) return;
    const activeElement = listboxRef.current.children[activeIndex] as HTMLElement;
    if (activeElement) {
      activeElement.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setInputValue(query);
    onInputChange?.(query);

    if (!isOpen) openListbox();
    setActiveIndex(-1);
  }, [isOpen, onInputChange]);

  function handleKeyDown(e: React.KeyboardEvent) {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!isOpen) {
          openListbox();
          return;
        }
        setActiveIndex((prev) => {
          const next = prev < enabledOptions.length - 1 ? prev + 1 : 0;
          const opt = enabledOptions[next];
          if (opt) announce(`${opt.label}${opt.description ? `, ${opt.description}` : ""}, ${next + 1} of ${enabledOptions.length}`);
          return options.indexOf(enabledOptions[next]);
        });
        break;

      case "ArrowUp":
        e.preventDefault();
        if (!isOpen) {
          openListbox();
          return;
        }
        setActiveIndex((prev) => {
          const currentEnabledIdx = enabledOptions.indexOf(options[prev]);
          const nextIdx = currentEnabledIdx > 0 ? currentEnabledIdx - 1 : enabledOptions.length - 1;
          const opt = enabledOptions[nextIdx];
          if (opt) announce(`${opt.label}, ${nextIdx + 1} of ${enabledOptions.length}`);
          return options.indexOf(enabledOptions[nextIdx]);
        });
        break;

      case "Enter":
        e.preventDefault();
        if (isOpen && activeIndex >= 0) {
          const option = options[activeIndex];
          if (option && !option.disabled) selectOption(option);
        }
        break;

      case "Escape":
        e.preventDefault();
        if (isOpen) {
          closeListbox();
          // Restore previous selection
          if (selectedOption) {
            setInputValue(selectedOption.label);
          }
          announce("Listbox closed");
        }
        break;

      case "Home":
        if (isOpen) {
          e.preventDefault();
          const firstEnabled = options.indexOf(enabledOptions[0]);
          setActiveIndex(firstEnabled);
        }
        break;

      case "End":
        if (isOpen) {
          e.preventDefault();
          const lastEnabled = options.indexOf(enabledOptions[enabledOptions.length - 1]);
          setActiveIndex(lastEnabled);
        }
        break;
    }
  }

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!inputRef.current?.parentElement?.contains(target)) {
        closeListbox();
        if (selectedOption) setInputValue(selectedOption.label);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen, selectedOption]);

  const activeDescendantId = activeIndex >= 0 ? `${id}-option-${options[activeIndex]?.id}` : undefined;

  return (
    <div style={{ position: "relative" }}>
      {/* Label */}
      <label id={labelId} htmlFor={`${id}-input`} style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
        {label}
        {required && <span aria-hidden="true" style={{ color: "#dc2626" }}> *</span>}
      </label>

      {/* Input wrapper */}
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <input
          ref={inputRef}
          id={`${id}-input`}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-activedescendant={activeDescendantId}
          aria-labelledby={labelId}
          aria-describedby={error ? errorId : undefined}
          aria-required={required}
          aria-invalid={!!error}
          value={inputValue}
          placeholder={placeholder}
          disabled={disabled}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (options.length > 0) openListbox(); }}
          style={{
            width: "100%", padding: "8px 32px 8px 12px",
            border: `1px solid ${error ? "#dc2626" : "#d1d5db"}`,
            borderRadius: "6px", fontSize: "14px",
            outline: "none",
          }}
        />

        {/* Clear button */}
        {inputValue && !disabled && (
          <button
            type="button"
            onClick={clearSelection}
            aria-label="Clear selection"
            style={{
              position: "absolute", right: "8px",
              background: "none", border: "none", cursor: "pointer",
              fontSize: "16px", color: "#6b7280", padding: "4px",
            }}
          >
            x
          </button>
        )}
      </div>

      {/* Error message */}
      {error && (
        <p id={errorId} role="alert" style={{ color: "#dc2626", fontSize: "12px", marginTop: "4px" }}>
          {error}
        </p>
      )}

      {/* Listbox */}
      {isOpen && (
        <ul
          ref={listboxRef}
          id={listboxId}
          role="listbox"
          aria-labelledby={labelId}
          style={{
            position: "absolute", top: "100%", left: 0, right: 0,
            maxHeight: "240px", overflowY: "auto",
            background: "white", border: "1px solid #d1d5db",
            borderRadius: "6px", marginTop: "4px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
            listStyle: "none", padding: 0, margin: 0, zIndex: 50,
          }}
        >
          {loading && (
            <li role="option" aria-disabled="true" aria-selected={false} style={{ padding: "12px", color: "#6b7280" }}>
              Loading...
            </li>
          )}

          {!loading && options.length === 0 && (
            <li role="option" aria-disabled="true" aria-selected={false} style={{ padding: "12px", color: "#6b7280" }}>
              {noResultsMessage}
            </li>
          )}

          {!loading && options.map((option, index) => (
            <li
              key={option.id}
              id={`${id}-option-${option.id}`}
              role="option"
              aria-selected={option.id === value}
              aria-disabled={option.disabled}
              onClick={() => { if (!option.disabled) selectOption(option); }}
              onMouseEnter={() => setActiveIndex(index)}
              style={{
                padding: "8px 12px",
                cursor: option.disabled ? "not-allowed" : "pointer",
                backgroundColor: index === activeIndex ? "#eff6ff" : option.id === value ? "#f0fdf4" : "transparent",
                opacity: option.disabled ? 0.5 : 1,
                borderBottom: index < options.length - 1 ? "1px solid #f3f4f6" : "none",
              }}
            >
              <div style={{ fontWeight: option.id === value ? 600 : 400 }}>
                {option.label}
              </div>
              {option.description && (
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "2px" }}>
                  {option.description}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Live region for screen reader announcements */}
      <div
        id={statusId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        style={{
          position: "absolute", width: "1px", height: "1px",
          overflow: "hidden", clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap", border: 0,
        }}
      >
        {announcement}
      </div>
    </div>
  );
}
```

The combobox follows WAI-ARIA 1.2 combobox pattern: `role="combobox"` on the input with `aria-expanded`, `aria-controls`, and `aria-activedescendant` tracking the focused option. Screen reader users hear option counts on open, individual options during navigation, and selection confirmations. Keyboard support covers all required keys including Home/End for jumping to first/last options.'''
    ),
    (
        "react/accessibility",
        r'''<think>
Keyboard navigation is one of the most important accessibility features. I need to build a system that goes beyond individual components - a focus management system that handles:
1. Roving tabindex for component groups (toolbars, tab lists, menus)
2. Focus trapping for modals/dialogs
3. Skip navigation links
4. Focus restoration when dialogs close
5. Arrow key navigation patterns

I should make these composable hooks that work together.
</think>
Create a React keyboard navigation system with hooks for roving tabindex, focus trapping, skip navigation, and focus restoration. Support arrow key navigation patterns for toolbars, menus, and tab lists with proper ARIA integration.''',
        r'''A composable keyboard navigation system with focus management hooks:

```typescript
import React, { useCallback, useEffect, useRef, useState } from "react";

// ============================================
// Roving Tabindex Hook
// ============================================

type Orientation = "horizontal" | "vertical" | "both";

interface UseRovingTabindexOptions {
  orientation?: Orientation;
  loop?: boolean;
  onActivate?: (index: number) => void;
}

function useRovingTabindex<T extends HTMLElement>(
  itemCount: number,
  options: UseRovingTabindexOptions = {}
) {
  const { orientation = "horizontal", loop = true, onActivate } = options;
  const [activeIndex, setActiveIndex] = useState(0);
  const itemRefs = useRef<(T | null)[]>([]);

  // Ensure refs array matches item count
  useEffect(() => {
    itemRefs.current = itemRefs.current.slice(0, itemCount);
    while (itemRefs.current.length < itemCount) {
      itemRefs.current.push(null);
    }
  }, [itemCount]);

  const focusItem = useCallback((index: number) => {
    const clamped = loop
      ? ((index % itemCount) + itemCount) % itemCount
      : Math.max(0, Math.min(index, itemCount - 1));
    setActiveIndex(clamped);
    itemRefs.current[clamped]?.focus();
    onActivate?.(clamped);
  }, [itemCount, loop, onActivate]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    let handled = true;

    switch (e.key) {
      case "ArrowRight":
        if (orientation === "horizontal" || orientation === "both") {
          focusItem(activeIndex + 1);
        } else handled = false;
        break;

      case "ArrowLeft":
        if (orientation === "horizontal" || orientation === "both") {
          focusItem(activeIndex - 1);
        } else handled = false;
        break;

      case "ArrowDown":
        if (orientation === "vertical" || orientation === "both") {
          focusItem(activeIndex + 1);
        } else handled = false;
        break;

      case "ArrowUp":
        if (orientation === "vertical" || orientation === "both") {
          focusItem(activeIndex - 1);
        } else handled = false;
        break;

      case "Home":
        focusItem(0);
        break;

      case "End":
        focusItem(itemCount - 1);
        break;

      default:
        handled = false;
    }

    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, [activeIndex, focusItem, itemCount, orientation]);

  function getItemProps(index: number) {
    return {
      ref: (el: T | null) => { itemRefs.current[index] = el; },
      tabIndex: index === activeIndex ? 0 : -1,
      onKeyDown: handleKeyDown,
      onFocus: () => setActiveIndex(index),
    };
  }

  return { activeIndex, focusItem, getItemProps };
}

// ============================================
// Focus Trap Hook
// ============================================

interface UseFocusTrapOptions {
  enabled?: boolean;
  autoFocus?: boolean;
  restoreFocus?: boolean;
  initialFocusRef?: React.RefObject<HTMLElement>;
}

function useFocusTrap(options: UseFocusTrapOptions = {}) {
  const { enabled = true, autoFocus = true, restoreFocus = true, initialFocusRef } = options;
  const containerRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  function getFocusableElements(): HTMLElement[] {
    if (!containerRef.current) return [];

    const selector = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
      '[contenteditable="true"]',
    ].join(", ");

    const elements = containerRef.current.querySelectorAll<HTMLElement>(selector);
    return Array.from(elements).filter(
      (el) => el.offsetParent !== null // Visible elements only
    );
  }

  useEffect(() => {
    if (!enabled) return;

    // Store currently focused element for restoration
    previouslyFocusedRef.current = document.activeElement as HTMLElement;

    // Auto-focus first element or specified element
    if (autoFocus) {
      requestAnimationFrame(() => {
        if (initialFocusRef?.current) {
          initialFocusRef.current.focus();
        } else {
          const focusable = getFocusableElements();
          if (focusable.length > 0) focusable[0].focus();
        }
      });
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Tab") return;

      const focusable = getFocusableElements();
      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }

      const firstEl = focusable[0];
      const lastEl = focusable[focusable.length - 1];

      if (e.shiftKey) {
        // Shift+Tab: if on first element, wrap to last
        if (document.activeElement === firstEl) {
          e.preventDefault();
          lastEl.focus();
        }
      } else {
        // Tab: if on last element, wrap to first
        if (document.activeElement === lastEl) {
          e.preventDefault();
          firstEl.focus();
        }
      }
    }

    // Prevent focus from leaving the container
    function handleFocusIn(e: FocusEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        const focusable = getFocusableElements();
        if (focusable.length > 0) focusable[0].focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", handleFocusIn);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", handleFocusIn);

      // Restore focus
      if (restoreFocus && previouslyFocusedRef.current) {
        previouslyFocusedRef.current.focus();
      }
    };
  }, [enabled, autoFocus, restoreFocus, initialFocusRef]);

  return containerRef;
}

// ============================================
// Skip Navigation
// ============================================

function SkipNavigation({ links }: { links: { href: string; label: string }[] }) {
  return (
    <nav aria-label="Skip navigation" style={{ position: "absolute" }}>
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          style={{
            position: "absolute",
            left: "-9999px",
            top: "auto",
            width: "1px",
            height: "1px",
            overflow: "hidden",
            // When focused, show on screen
          }}
          onFocus={(e) => {
            const el = e.currentTarget;
            Object.assign(el.style, {
              position: "fixed", left: "8px", top: "8px",
              width: "auto", height: "auto", overflow: "visible",
              zIndex: "10000", padding: "8px 16px",
              background: "#1e40af", color: "white",
              borderRadius: "4px", fontSize: "14px",
              textDecoration: "none",
            });
          }}
          onBlur={(e) => {
            const el = e.currentTarget;
            Object.assign(el.style, {
              position: "absolute", left: "-9999px",
              width: "1px", height: "1px", overflow: "hidden",
            });
          }}
        >
          {link.label}
        </a>
      ))}
    </nav>
  );
}

// ============================================
// Focus Restoration Hook
// ============================================

function useFocusRestoration() {
  const triggerRef = useRef<HTMLElement | null>(null);

  const saveFocus = useCallback(() => {
    triggerRef.current = document.activeElement as HTMLElement;
  }, []);

  const restoreFocus = useCallback(() => {
    if (triggerRef.current && document.body.contains(triggerRef.current)) {
      triggerRef.current.focus();
      triggerRef.current = null;
    }
  }, []);

  return { saveFocus, restoreFocus };
}

// ============================================
// Accessible Dialog with Focus Trap
// ============================================

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  initialFocusRef?: React.RefObject<HTMLElement>;
}

function Dialog({ isOpen, onClose, title, description, children, initialFocusRef }: DialogProps) {
  const containerRef = useFocusTrap({
    enabled: isOpen,
    initialFocusRef,
    restoreFocus: true,
  });

  useEffect(() => {
    if (!isOpen) return;

    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        aria-hidden="true"
        style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.5)" }}
      />

      {/* Dialog */}
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby={description ? "dialog-desc" : undefined}
        style={{
          position: "relative", background: "white", borderRadius: "8px",
          padding: "24px", maxWidth: "500px", width: "90%",
          boxShadow: "0 8px 30px rgba(0,0,0,0.2)",
        }}
      >
        <h2 id="dialog-title" style={{ margin: "0 0 8px" }}>{title}</h2>
        {description && <p id="dialog-desc" style={{ color: "#6b7280", marginBottom: "16px" }}>{description}</p>}
        {children}
      </div>
    </div>
  );
}

// ============================================
// Toolbar with Roving Tabindex
// ============================================

interface ToolbarProps {
  label: string;
  children: React.ReactElement[];
}

function Toolbar({ label, children }: ToolbarProps) {
  const { getItemProps, activeIndex } = useRovingTabindex<HTMLButtonElement>(
    children.length,
    { orientation: "horizontal", loop: true }
  );

  return (
    <div role="toolbar" aria-label={label} style={{ display: "flex", gap: "4px" }}>
      {React.Children.map(children, (child, index) => {
        const itemProps = getItemProps(index);
        return React.cloneElement(child, {
          ...itemProps,
          "aria-pressed": child.props["aria-pressed"],
          style: {
            ...child.props.style,
            outline: index === activeIndex ? "2px solid #3b82f6" : "none",
            outlineOffset: "2px",
          },
        });
      })}
    </div>
  );
}

// ============================================
// Tab List with Roving Tabindex
// ============================================

interface Tab {
  id: string;
  label: string;
  panelContent: React.ReactNode;
  disabled?: boolean;
}

function TabGroup({ tabs, label }: { tabs: Tab[]; label: string }) {
  const [selectedId, setSelectedId] = useState(tabs[0]?.id || "");
  const enabledTabs = tabs.filter((t) => !t.disabled);

  const { getItemProps } = useRovingTabindex<HTMLButtonElement>(
    tabs.length,
    {
      orientation: "horizontal",
      onActivate: (index) => {
        if (!tabs[index].disabled) {
          setSelectedId(tabs[index].id);
        }
      },
    }
  );

  const selectedTab = tabs.find((t) => t.id === selectedId);

  return (
    <div>
      <div role="tablist" aria-label={label} style={{ display: "flex", borderBottom: "2px solid #e5e7eb" }}>
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            {...getItemProps(index)}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={tab.id === selectedId}
            aria-controls={`panel-${tab.id}`}
            aria-disabled={tab.disabled}
            onClick={() => { if (!tab.disabled) setSelectedId(tab.id); }}
            style={{
              padding: "8px 16px", border: "none", background: "none",
              cursor: tab.disabled ? "not-allowed" : "pointer",
              borderBottom: tab.id === selectedId ? "2px solid #3b82f6" : "2px solid transparent",
              color: tab.disabled ? "#9ca3af" : tab.id === selectedId ? "#1d4ed8" : "#374151",
              fontWeight: tab.id === selectedId ? 600 : 400,
              marginBottom: "-2px",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab.id}`}
          hidden={tab.id !== selectedId}
          tabIndex={0}
          style={{ padding: "16px" }}
        >
          {tab.panelContent}
        </div>
      ))}
    </div>
  );
}

// ============================================
// App Integration
// ============================================

function App() {
  const [isDialogOpen, setDialogOpen] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  return (
    <div>
      <SkipNavigation
        links={[
          { href: "#main-content", label: "Skip to main content" },
          { href: "#navigation", label: "Skip to navigation" },
        ]}
      />

      <nav id="navigation">
        <Toolbar label="Formatting toolbar">
          <button aria-label="Bold">B</button>
          <button aria-label="Italic">I</button>
          <button aria-label="Underline">U</button>
        </Toolbar>
      </nav>

      <main id="main-content">
        <TabGroup
          label="Content sections"
          tabs={[
            { id: "overview", label: "Overview", panelContent: <p>Overview content</p> },
            { id: "details", label: "Details", panelContent: <p>Details content</p> },
            { id: "settings", label: "Settings", panelContent: <p>Settings content</p>, disabled: true },
          ]}
        />

        <button onClick={() => setDialogOpen(true)}>Open Dialog</button>

        <Dialog
          isOpen={isDialogOpen}
          onClose={() => setDialogOpen(false)}
          title="Confirm Action"
          description="This action cannot be undone."
          initialFocusRef={confirmRef}
        >
          <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
            <button onClick={() => setDialogOpen(false)}>Cancel</button>
            <button ref={confirmRef} onClick={() => setDialogOpen(false)}>Confirm</button>
          </div>
        </Dialog>
      </main>
    </div>
  );
}
```

This system implements four composable patterns: roving tabindex (only the active item in a group has `tabIndex=0`), focus trapping (Tab/Shift+Tab cycle within a container), skip navigation (visually hidden links that appear on focus), and focus restoration (return focus to the trigger element when a dialog closes). Each hook follows WAI-ARIA authoring practices for its respective widget pattern.'''
    ),
    (
        "react/accessibility",
        r'''Build a React screen reader announcement system with a live region manager, announcement queue with priority levels, and utilities for announcing dynamic content changes like route transitions, form validation, and data updates.''',
        r'''A screen reader announcement system with priority queuing:

```typescript
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// ============================================
// Announcement types
// ============================================

type AnnouncementPriority = "polite" | "assertive";

interface Announcement {
  id: string;
  message: string;
  priority: AnnouncementPriority;
  timestamp: number;
  clearAfterMs?: number;
}

interface AnnouncerContextType {
  announce: (message: string, priority?: AnnouncementPriority) => void;
  announcePolite: (message: string) => void;
  announceAssertive: (message: string) => void;
  clearAnnouncements: () => void;
}

const AnnouncerContext = createContext<AnnouncerContextType | null>(null);

// ============================================
// Announcer Provider
// ============================================

const DEFAULT_CLEAR_DELAY = 7000;
const DEBOUNCE_MS = 100;

export function AnnouncerProvider({ children }: { children: React.ReactNode }) {
  const [politeMessage, setPoliteMessage] = useState("");
  const [assertiveMessage, setAssertiveMessage] = useState("");
  const queueRef = useRef<Announcement[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const counterRef = useRef(0);

  function processQueue() {
    const queue = queueRef.current;
    if (queue.length === 0) return;

    // Process assertive messages first
    const assertive = queue.filter((a) => a.priority === "assertive");
    const polite = queue.filter((a) => a.priority === "polite");

    if (assertive.length > 0) {
      // Use the most recent assertive message
      const latest = assertive[assertive.length - 1];
      setAssertiveMessage("");
      // Clear then set to trigger re-announcement of same message
      requestAnimationFrame(() => {
        setAssertiveMessage(latest.message);
      });
    }

    if (polite.length > 0) {
      const combined = polite.map((a) => a.message).join(". ");
      setPoliteMessage("");
      requestAnimationFrame(() => {
        setPoliteMessage(combined);
      });
    }

    // Schedule cleanup
    const clearDelay = Math.max(
      ...queue.map((a) => a.clearAfterMs || DEFAULT_CLEAR_DELAY)
    );
    setTimeout(() => {
      setPoliteMessage("");
      setAssertiveMessage("");
    }, clearDelay);

    queueRef.current = [];
  }

  const announce = useCallback((message: string, priority: AnnouncementPriority = "polite") => {
    if (!message.trim()) return;

    const announcement: Announcement = {
      id: `ann_${++counterRef.current}`,
      message: message.trim(),
      priority,
      timestamp: Date.now(),
    };

    queueRef.current.push(announcement);

    // Debounce processing to batch rapid announcements
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(processQueue, DEBOUNCE_MS);
  }, []);

  const announcePolite = useCallback((message: string) => announce(message, "polite"), [announce]);
  const announceAssertive = useCallback((message: string) => announce(message, "assertive"), [announce]);

  const clearAnnouncements = useCallback(() => {
    queueRef.current = [];
    setPoliteMessage("");
    setAssertiveMessage("");
  }, []);

  return (
    <AnnouncerContext.Provider value={{ announce, announcePolite, announceAssertive, clearAnnouncements }}>
      {children}

      {/* Polite live region */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        style={{
          position: "absolute", width: "1px", height: "1px",
          overflow: "hidden", clip: "rect(0, 0, 0, 0)",
          whiteSpace: "nowrap", border: 0, padding: 0, margin: "-1px",
        }}
      >
        {politeMessage}
      </div>

      {/* Assertive live region */}
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        style={{
          position: "absolute", width: "1px", height: "1px",
          overflow: "hidden", clip: "rect(0, 0, 0, 0)",
          whiteSpace: "nowrap", border: 0, padding: 0, margin: "-1px",
        }}
      >
        {assertiveMessage}
      </div>
    </AnnouncerContext.Provider>
  );
}

export function useAnnouncer(): AnnouncerContextType {
  const ctx = useContext(AnnouncerContext);
  if (!ctx) throw new Error("useAnnouncer must be used within AnnouncerProvider");
  return ctx;
}

// ============================================
// Route change announcer
// ============================================

interface RouteAnnouncerProps {
  pathname: string;
  pageTitle?: string;
}

export function RouteAnnouncer({ pathname, pageTitle }: RouteAnnouncerProps) {
  const { announcePolite } = useAnnouncer();
  const prevPathRef = useRef(pathname);

  useEffect(() => {
    if (pathname !== prevPathRef.current) {
      prevPathRef.current = pathname;
      const title = pageTitle || document.title || "New page";
      announcePolite(`Navigated to ${title}`);
    }
  }, [pathname, pageTitle, announcePolite]);

  return null;
}

// ============================================
// Form validation announcer
// ============================================

interface FormError {
  field: string;
  message: string;
}

export function useFormAnnouncer() {
  const { announceAssertive, announcePolite } = useAnnouncer();
  const prevErrorCountRef = useRef(0);

  const announceErrors = useCallback((errors: FormError[]) => {
    if (errors.length === 0) {
      if (prevErrorCountRef.current > 0) {
        announcePolite("All errors resolved");
      }
      prevErrorCountRef.current = 0;
      return;
    }

    prevErrorCountRef.current = errors.length;

    if (errors.length === 1) {
      announceAssertive(`Error: ${errors[0].message}`);
    } else {
      const summary = `${errors.length} errors found. `;
      const details = errors.map((e) => `${e.field}: ${e.message}`).join(". ");
      announceAssertive(summary + details);
    }
  }, [announceAssertive, announcePolite]);

  const announceFieldError = useCallback((field: string, message: string) => {
    announceAssertive(`${field}: ${message}`);
  }, [announceAssertive]);

  const announceSuccess = useCallback((message: string) => {
    announcePolite(message);
  }, [announcePolite]);

  return { announceErrors, announceFieldError, announceSuccess };
}

// ============================================
// Data update announcer
// ============================================

export function useDataAnnouncer() {
  const { announcePolite, announceAssertive } = useAnnouncer();

  const announceListUpdate = useCallback((params: {
    itemType: string;
    previousCount: number;
    currentCount: number;
    action?: "added" | "removed" | "updated" | "loaded";
  }) => {
    const { itemType, previousCount, currentCount, action } = params;
    const diff = currentCount - previousCount;

    if (action === "loaded") {
      announcePolite(`${currentCount} ${itemType} loaded`);
    } else if (diff > 0) {
      announcePolite(`${diff} ${itemType} added. ${currentCount} total.`);
    } else if (diff < 0) {
      announcePolite(`${Math.abs(diff)} ${itemType} removed. ${currentCount} total.`);
    } else if (action === "updated") {
      announcePolite(`${itemType} list updated. ${currentCount} items.`);
    }
  }, [announcePolite]);

  const announceLoadingState = useCallback((params: {
    isLoading: boolean;
    resourceName: string;
    error?: string;
  }) => {
    const { isLoading, resourceName, error } = params;

    if (error) {
      announceAssertive(`Failed to load ${resourceName}: ${error}`);
    } else if (isLoading) {
      announcePolite(`Loading ${resourceName}...`);
    } else {
      announcePolite(`${resourceName} loaded`);
    }
  }, [announcePolite, announceAssertive]);

  const announceSortChange = useCallback((column: string, direction: "ascending" | "descending") => {
    announcePolite(`Table sorted by ${column}, ${direction}`);
  }, [announcePolite]);

  const announceFilterChange = useCallback((filterDesc: string, resultCount: number) => {
    announcePolite(`Filter applied: ${filterDesc}. ${resultCount} results.`);
  }, [announcePolite]);

  return { announceListUpdate, announceLoadingState, announceSortChange, announceFilterChange };
}

// ============================================
// Usage example
// ============================================

function TodoApp() {
  const [todos, setTodos] = useState<{ id: string; text: string }[]>([]);
  const [errors, setErrors] = useState<FormError[]>([]);
  const { announceErrors, announceSuccess } = useFormAnnouncer();
  const { announceListUpdate } = useDataAnnouncer();

  function addTodo(text: string) {
    if (!text.trim()) {
      const newErrors = [{ field: "Todo text", message: "Cannot be empty" }];
      setErrors(newErrors);
      announceErrors(newErrors);
      return;
    }

    const prevCount = todos.length;
    const newTodos = [...todos, { id: crypto.randomUUID(), text }];
    setTodos(newTodos);
    setErrors([]);

    announceListUpdate({
      itemType: "todos",
      previousCount: prevCount,
      currentCount: newTodos.length,
      action: "added",
    });
    announceSuccess(`Todo "${text}" added`);
  }

  function removeTodo(id: string) {
    const prevCount = todos.length;
    const removed = todos.find((t) => t.id === id);
    setTodos(todos.filter((t) => t.id !== id));

    announceListUpdate({
      itemType: "todos",
      previousCount: prevCount,
      currentCount: prevCount - 1,
      action: "removed",
    });
    if (removed) announceSuccess(`Todo "${removed.text}" removed`);
  }

  return (
    <div>
      <h1>Todos</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const input = (e.target as HTMLFormElement).elements.namedItem("todoInput") as HTMLInputElement;
          addTodo(input.value);
          input.value = "";
        }}
      >
        <label htmlFor="todoInput">New todo</label>
        <input id="todoInput" name="todoInput" type="text" aria-describedby={errors.length ? "todo-error" : undefined} />
        {errors.length > 0 && <p id="todo-error" role="alert" style={{ color: "#dc2626" }}>{errors[0].message}</p>}
        <button type="submit">Add</button>
      </form>
      <ul aria-label={`Todo list, ${todos.length} items`}>
        {todos.map((todo) => (
          <li key={todo.id}>
            {todo.text}
            <button onClick={() => removeTodo(todo.id)} aria-label={`Remove ${todo.text}`}>Remove</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function App() {
  return (
    <AnnouncerProvider>
      <RouteAnnouncer pathname={window.location.pathname} />
      <TodoApp />
    </AnnouncerProvider>
  );
}
```

The announcement system uses separate live regions for polite (non-interrupting) and assertive (immediate) announcements. Messages are debounced and batched - multiple polite announcements within 100ms are combined into a single announcement to avoid overwhelming screen readers. The clear-then-set pattern via `requestAnimationFrame` ensures that repeated identical messages are re-announced.'''
    ),
    (
        "react/accessibility",
        r'''Create a React focus management system for complex multi-step forms and wizard interfaces. Handle focus movement between steps, error focus on validation failure, section landmark announcements, and progress indicator accessibility.''',
        r'''A focus management system for accessible multi-step wizards:

```typescript
import React, { useCallback, useEffect, useId, useRef, useState } from "react";

// ============================================
// Step definitions
// ============================================

interface WizardStep {
  id: string;
  title: string;
  description?: string;
  validate?: () => ValidationResult;
}

interface ValidationResult {
  valid: boolean;
  errors: { fieldId: string; message: string }[];
}

interface WizardFocusConfig {
  focusHeadingOnStep?: boolean;
  focusFirstFieldOnStep?: boolean;
  focusFirstErrorOnValidation?: boolean;
  announceStepChange?: boolean;
}

const DEFAULT_CONFIG: WizardFocusConfig = {
  focusHeadingOnStep: true,
  focusFirstFieldOnStep: false,
  focusFirstErrorOnValidation: true,
  announceStepChange: true,
};

// ============================================
// Wizard Focus Manager Hook
// ============================================

function useWizardFocus(
  steps: WizardStep[],
  config: WizardFocusConfig = DEFAULT_CONFIG
) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [announcement, setAnnouncement] = useState("");
  const stepHeadingRefs = useRef<Map<number, HTMLElement>>(new Map());
  const stepContentRefs = useRef<Map<number, HTMLElement>>(new Map());

  const currentStep = steps[currentStepIndex];

  function announce(message: string) {
    setAnnouncement("");
    requestAnimationFrame(() => setAnnouncement(message));
  }

  // Focus management for step transitions
  const focusStep = useCallback((stepIndex: number) => {
    requestAnimationFrame(() => {
      if (config.focusHeadingOnStep) {
        const heading = stepHeadingRefs.current.get(stepIndex);
        if (heading) {
          heading.focus();
          return;
        }
      }

      if (config.focusFirstFieldOnStep) {
        const content = stepContentRefs.current.get(stepIndex);
        if (content) {
          const firstInput = content.querySelector<HTMLElement>(
            'input:not([disabled]), select:not([disabled]), textarea:not([disabled])'
          );
          if (firstInput) {
            firstInput.focus();
            return;
          }
        }
      }
    });
  }, [config]);

  // Focus first error field after validation
  const focusFirstError = useCallback((errors: { fieldId: string; message: string }[]) => {
    if (!config.focusFirstErrorOnValidation || errors.length === 0) return;

    requestAnimationFrame(() => {
      const firstError = errors[0];
      const errorField = document.getElementById(firstError.fieldId);
      if (errorField) {
        errorField.focus();
        // Also scroll into view
        errorField.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }, [config]);

  // Navigate to a step
  const goToStep = useCallback((targetIndex: number, skipValidation = false): boolean => {
    if (targetIndex < 0 || targetIndex >= steps.length) return false;

    // Validate current step when moving forward
    if (targetIndex > currentStepIndex && !skipValidation) {
      const step = steps[currentStepIndex];
      if (step.validate) {
        const result = step.validate();
        if (!result.valid) {
          focusFirstError(result.errors);

          const errorCount = result.errors.length;
          announce(
            `Cannot proceed. ${errorCount} ${errorCount === 1 ? "error" : "errors"} found. ` +
            `${result.errors[0].message}`
          );
          return false;
        }
      }
    }

    // Mark current step as completed when moving forward
    if (targetIndex > currentStepIndex) {
      setCompletedSteps((prev) => new Set([...prev, currentStepIndex]));
    }

    setCurrentStepIndex(targetIndex);

    if (config.announceStepChange) {
      announce(
        `Step ${targetIndex + 1} of ${steps.length}: ${steps[targetIndex].title}`
      );
    }

    focusStep(targetIndex);
    return true;
  }, [currentStepIndex, steps, config, focusStep, focusFirstError]);

  const nextStep = useCallback(() => goToStep(currentStepIndex + 1), [goToStep, currentStepIndex]);
  const prevStep = useCallback(() => goToStep(currentStepIndex - 1, true), [goToStep, currentStepIndex]);

  // Register refs
  const registerHeading = useCallback((index: number, el: HTMLElement | null) => {
    if (el) {
      stepHeadingRefs.current.set(index, el);
    } else {
      stepHeadingRefs.current.delete(index);
    }
  }, []);

  const registerContent = useCallback((index: number, el: HTMLElement | null) => {
    if (el) {
      stepContentRefs.current.set(index, el);
    } else {
      stepContentRefs.current.delete(index);
    }
  }, []);

  return {
    currentStepIndex,
    currentStep,
    completedSteps,
    announcement,
    goToStep,
    nextStep,
    prevStep,
    registerHeading,
    registerContent,
    isFirstStep: currentStepIndex === 0,
    isLastStep: currentStepIndex === steps.length - 1,
  };
}

// ============================================
// Progress Indicator
// ============================================

interface ProgressProps {
  steps: WizardStep[];
  currentIndex: number;
  completedSteps: Set<number>;
  onStepClick?: (index: number) => void;
}

function WizardProgress({ steps, currentIndex, completedSteps, onStepClick }: ProgressProps) {
  return (
    <nav aria-label="Wizard progress">
      <ol
        style={{
          display: "flex", listStyle: "none", padding: 0, margin: 0,
          gap: "4px", alignItems: "center",
        }}
      >
        {steps.map((step, index) => {
          const isCompleted = completedSteps.has(index);
          const isCurrent = index === currentIndex;
          const isAccessible = isCompleted || isCurrent || index <= currentIndex;

          return (
            <li key={step.id} style={{ display: "flex", alignItems: "center" }}>
              {index > 0 && (
                <div
                  aria-hidden="true"
                  style={{
                    width: "40px", height: "2px", marginRight: "4px",
                    background: isCompleted ? "#22c55e" : "#e5e7eb",
                  }}
                />
              )}
              <button
                onClick={() => isAccessible && onStepClick?.(index)}
                disabled={!isAccessible}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={`Step ${index + 1}: ${step.title}${isCompleted ? ", completed" : isCurrent ? ", current" : ""}`}
                style={{
                  width: "32px", height: "32px", borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "14px", fontWeight: 600,
                  border: isCurrent ? "2px solid #3b82f6" : "2px solid transparent",
                  background: isCompleted ? "#22c55e" : isCurrent ? "#eff6ff" : "#f3f4f6",
                  color: isCompleted ? "white" : isCurrent ? "#1d4ed8" : "#6b7280",
                  cursor: isAccessible ? "pointer" : "not-allowed",
                }}
              >
                {isCompleted ? (
                  <span aria-hidden="true">&#10003;</span>
                ) : (
                  index + 1
                )}
              </button>
            </li>
          );
        })}
      </ol>

      {/* Text indicator for screen readers */}
      <p
        style={{
          position: "absolute", width: "1px", height: "1px",
          overflow: "hidden", clip: "rect(0,0,0,0)",
        }}
      >
        Step {currentIndex + 1} of {steps.length}: {steps[currentIndex].title}
      </p>
    </nav>
  );
}

// ============================================
// Wizard Component
// ============================================

interface WizardProps {
  steps: WizardStep[];
  onComplete: () => void;
  children: (params: {
    currentStepIndex: number;
    registerContent: (index: number, el: HTMLElement | null) => void;
  }) => React.ReactNode;
}

function Wizard({ steps, onComplete, children }: WizardProps) {
  const wizardId = useId();
  const {
    currentStepIndex,
    currentStep,
    completedSteps,
    announcement,
    goToStep,
    nextStep,
    prevStep,
    registerHeading,
    registerContent,
    isFirstStep,
    isLastStep,
  } = useWizardFocus(steps);

  function handleNext() {
    if (isLastStep) {
      // Validate last step before completing
      if (currentStep.validate) {
        const result = currentStep.validate();
        if (!result.valid) return;
      }
      onComplete();
    } else {
      nextStep();
    }
  }

  return (
    <div
      role="group"
      aria-label={`Multi-step form: ${currentStep.title}`}
      aria-roledescription="wizard"
    >
      {/* Progress indicator */}
      <WizardProgress
        steps={steps}
        currentIndex={currentStepIndex}
        completedSteps={completedSteps}
        onStepClick={(index) => goToStep(index)}
      />

      {/* Step content */}
      <section
        aria-labelledby={`${wizardId}-heading`}
        style={{ marginTop: "24px" }}
      >
        <h2
          id={`${wizardId}-heading`}
          ref={(el) => registerHeading(currentStepIndex, el)}
          tabIndex={-1}
          style={{ outline: "none", margin: "0 0 8px" }}
        >
          {currentStep.title}
        </h2>

        {currentStep.description && (
          <p style={{ color: "#6b7280", marginBottom: "16px" }}>
            {currentStep.description}
          </p>
        )}

        {/* Render step content */}
        {children({ currentStepIndex, registerContent })}
      </section>

      {/* Navigation buttons */}
      <div
        style={{
          display: "flex", justifyContent: "space-between",
          marginTop: "24px", paddingTop: "16px",
          borderTop: "1px solid #e5e7eb",
        }}
      >
        <button
          onClick={prevStep}
          disabled={isFirstStep}
          aria-label={isFirstStep ? "No previous step" : `Back to ${steps[currentStepIndex - 1]?.title}`}
          style={{
            padding: "8px 24px", borderRadius: "6px",
            border: "1px solid #d1d5db", background: "white",
            cursor: isFirstStep ? "not-allowed" : "pointer",
            opacity: isFirstStep ? 0.5 : 1,
          }}
        >
          Back
        </button>

        <button
          onClick={handleNext}
          aria-label={isLastStep ? "Complete wizard" : `Continue to ${steps[currentStepIndex + 1]?.title}`}
          style={{
            padding: "8px 24px", borderRadius: "6px",
            border: "none", background: "#2563eb", color: "white",
            cursor: "pointer", fontWeight: 600,
          }}
        >
          {isLastStep ? "Complete" : "Continue"}
        </button>
      </div>

      {/* Live region for announcements */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        style={{
          position: "absolute", width: "1px", height: "1px",
          overflow: "hidden", clip: "rect(0,0,0,0)",
        }}
      >
        {announcement}
      </div>
    </div>
  );
}

// ============================================
// Example usage
// ============================================

function RegistrationWizard() {
  const [formData, setFormData] = useState({
    name: "", email: "", password: "",
    street: "", city: "", zip: "",
  });

  const steps: WizardStep[] = [
    {
      id: "personal",
      title: "Personal Information",
      description: "Enter your name and email address",
      validate: () => {
        const errors: { fieldId: string; message: string }[] = [];
        if (!formData.name) errors.push({ fieldId: "field-name", message: "Name is required" });
        if (!formData.email) errors.push({ fieldId: "field-email", message: "Email is required" });
        return { valid: errors.length === 0, errors };
      },
    },
    {
      id: "address",
      title: "Address Details",
      description: "Enter your mailing address",
      validate: () => {
        const errors: { fieldId: string; message: string }[] = [];
        if (!formData.city) errors.push({ fieldId: "field-city", message: "City is required" });
        return { valid: errors.length === 0, errors };
      },
    },
    {
      id: "review",
      title: "Review & Submit",
      description: "Review your information before submitting",
    },
  ];

  return (
    <Wizard steps={steps} onComplete={() => console.log("Wizard completed", formData)}>
      {({ currentStepIndex, registerContent }) => (
        <div>
          {currentStepIndex === 0 && (
            <fieldset ref={(el) => registerContent(0, el)} style={{ border: "none", padding: 0 }}>
              <legend style={{ position: "absolute", clip: "rect(0,0,0,0)" }}>Personal Information</legend>
              <div style={{ marginBottom: "12px" }}>
                <label htmlFor="field-name" style={{ display: "block", marginBottom: "4px" }}>Name *</label>
                <input
                  id="field-name"
                  value={formData.name}
                  onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                  aria-required="true"
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid #d1d5db" }}
                />
              </div>
              <div style={{ marginBottom: "12px" }}>
                <label htmlFor="field-email" style={{ display: "block", marginBottom: "4px" }}>Email *</label>
                <input
                  id="field-email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData((p) => ({ ...p, email: e.target.value }))}
                  aria-required="true"
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid #d1d5db" }}
                />
              </div>
            </fieldset>
          )}

          {currentStepIndex === 1 && (
            <fieldset ref={(el) => registerContent(1, el)} style={{ border: "none", padding: 0 }}>
              <legend style={{ position: "absolute", clip: "rect(0,0,0,0)" }}>Address Details</legend>
              <div style={{ marginBottom: "12px" }}>
                <label htmlFor="field-city" style={{ display: "block", marginBottom: "4px" }}>City *</label>
                <input
                  id="field-city"
                  value={formData.city}
                  onChange={(e) => setFormData((p) => ({ ...p, city: e.target.value }))}
                  aria-required="true"
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid #d1d5db" }}
                />
              </div>
            </fieldset>
          )}

          {currentStepIndex === 2 && (
            <div ref={(el) => registerContent(2, el)}>
              <dl>
                <dt style={{ fontWeight: 600 }}>Name</dt>
                <dd>{formData.name}</dd>
                <dt style={{ fontWeight: 600 }}>Email</dt>
                <dd>{formData.email}</dd>
                <dt style={{ fontWeight: 600 }}>City</dt>
                <dd>{formData.city}</dd>
              </dl>
            </div>
          )}
        </div>
      )}
    </Wizard>
  );
}
```

The wizard manages focus by moving it to the step heading (with `tabIndex={-1}`) on step transitions, to the first error field on validation failure, and announcing step changes via a live region. The progress indicator uses `aria-current="step"` for the active step and descriptive labels indicating completion state. Each step content is wrapped in a `fieldset` with a visually-hidden `legend` for screen reader context.'''
    ),
    (
        "react/accessibility",
        r'''Build a TypeScript color contrast utility for React that checks WCAG 2.1 compliance, suggests accessible color alternatives, provides a useColorContrast hook for dynamic checks, and includes a contrast checker component for design systems.''',
        r'''A WCAG color contrast utility with suggestions and React integration:

```typescript
import React, { useMemo, useState, useCallback } from "react";

// ============================================
// Color conversion utilities
// ============================================

interface RGB { r: number; g: number; b: number }
interface HSL { h: number; s: number; l: number }

function hexToRgb(hex: string): RGB {
  const cleaned = hex.replace("#", "");
  const num = parseInt(cleaned.length === 3
    ? cleaned.split("").map((c) => c + c).join("")
    : cleaned, 16);
  return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
}

function rgbToHex(rgb: RGB): string {
  const toHex = (n: number) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, "0");
  return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
}

function rgbToHsl(rgb: RGB): HSL {
  const r = rgb.r / 255;
  const g = rgb.g / 255;
  const b = rgb.b / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;

  if (max === min) return { h: 0, s: 0, l };

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

  let h: number;
  switch (max) {
    case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
    case g: h = ((b - r) / d + 2) / 6; break;
    default: h = ((r - g) / d + 4) / 6;
  }

  return { h: h * 360, s, l };
}

function hslToRgb(hsl: HSL): RGB {
  const { h: hDeg, s, l } = hsl;
  const h = hDeg / 360;

  if (s === 0) {
    const v = Math.round(l * 255);
    return { r: v, g: v, b: v };
  }

  function hue2rgb(p: number, q: number, t: number): number {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  }

  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;

  return {
    r: Math.round(hue2rgb(p, q, h + 1/3) * 255),
    g: Math.round(hue2rgb(p, q, h) * 255),
    b: Math.round(hue2rgb(p, q, h - 1/3) * 255),
  };
}

// ============================================
// WCAG Contrast Calculation
// ============================================

function relativeLuminance(rgb: RGB): number {
  const [rs, gs, bs] = [rgb.r, rgb.g, rgb.b].map((c) => {
    const srgb = c / 255;
    return srgb <= 0.03928
      ? srgb / 12.92
      : Math.pow((srgb + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function contrastRatio(color1: string, color2: string): number {
  const l1 = relativeLuminance(hexToRgb(color1));
  const l2 = relativeLuminance(hexToRgb(color2));
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

type WCAGLevel = "AAA" | "AA" | "AA-large" | "fail";

interface ContrastResult {
  ratio: number;
  level: WCAGLevel;
  passesAA: boolean;
  passesAAA: boolean;
  passesAALarge: boolean;
  passesAAALarge: boolean;
}

function checkContrast(foreground: string, background: string): ContrastResult {
  const ratio = contrastRatio(foreground, background);

  const passesAALarge = ratio >= 3;     // AA for large text (18pt+ or 14pt+ bold)
  const passesAA = ratio >= 4.5;        // AA for normal text
  const passesAAALarge = ratio >= 4.5;  // AAA for large text
  const passesAAA = ratio >= 7;         // AAA for normal text

  let level: WCAGLevel = "fail";
  if (passesAAA) level = "AAA";
  else if (passesAA) level = "AA";
  else if (passesAALarge) level = "AA-large";

  return { ratio, level, passesAA, passesAAA, passesAALarge, passesAAALarge };
}

// ============================================
// Color suggestion engine
// ============================================

interface ColorSuggestion {
  color: string;
  ratio: number;
  level: WCAGLevel;
  adjustment: string;
}

function suggestAccessibleColors(
  foreground: string,
  background: string,
  targetLevel: "AA" | "AAA" = "AA"
): ColorSuggestion[] {
  const targetRatio = targetLevel === "AAA" ? 7 : 4.5;
  const currentResult = checkContrast(foreground, background);

  if (currentResult.ratio >= targetRatio) {
    return [{ color: foreground, ratio: currentResult.ratio, level: currentResult.level, adjustment: "No change needed" }];
  }

  const suggestions: ColorSuggestion[] = [];
  const fgHsl = rgbToHsl(hexToRgb(foreground));
  const bgLuminance = relativeLuminance(hexToRgb(background));

  // Try adjusting lightness of foreground
  const shouldDarken = bgLuminance > 0.5;
  const step = shouldDarken ? -0.02 : 0.02;
  let testL = fgHsl.l;

  for (let i = 0; i < 50; i++) {
    testL += step;
    if (testL < 0 || testL > 1) break;

    const testRgb = hslToRgb({ ...fgHsl, l: testL });
    const testHex = rgbToHex(testRgb);
    const result = checkContrast(testHex, background);

    if (result.ratio >= targetRatio) {
      suggestions.push({
        color: testHex,
        ratio: result.ratio,
        level: result.level,
        adjustment: `${shouldDarken ? "Darken" : "Lighten"} foreground`,
      });
      break;
    }
  }

  // Try adjusting saturation
  for (const sDelta of [-0.2, -0.4, 0.2, 0.4]) {
    const testS = Math.max(0, Math.min(1, fgHsl.s + sDelta));
    for (let lDelta = -0.3; lDelta <= 0.3; lDelta += 0.05) {
      const testL2 = Math.max(0, Math.min(1, fgHsl.l + lDelta));
      const testRgb = hslToRgb({ h: fgHsl.h, s: testS, l: testL2 });
      const testHex = rgbToHex(testRgb);
      const result = checkContrast(testHex, background);

      if (result.ratio >= targetRatio && result.ratio < targetRatio + 2) {
        suggestions.push({
          color: testHex,
          ratio: result.ratio,
          level: result.level,
          adjustment: "Adjusted saturation and lightness",
        });
      }
    }
  }

  // Deduplicate and sort by closest ratio to target
  const seen = new Set<string>();
  return suggestions
    .filter((s) => {
      if (seen.has(s.color)) return false;
      seen.add(s.color);
      return true;
    })
    .sort((a, b) => Math.abs(a.ratio - targetRatio) - Math.abs(b.ratio - targetRatio))
    .slice(0, 5);
}

// ============================================
// React hook
// ============================================

function useColorContrast(foreground: string, background: string) {
  const result = useMemo(
    () => checkContrast(foreground, background),
    [foreground, background]
  );

  const suggestions = useMemo(
    () => result.passesAA ? [] : suggestAccessibleColors(foreground, background),
    [foreground, background, result.passesAA]
  );

  return { ...result, suggestions };
}

// ============================================
// Contrast Checker Component
// ============================================

function ContrastChecker() {
  const [fg, setFg] = useState("#595959");
  const [bg, setBg] = useState("#ffffff");

  const { ratio, level, passesAA, passesAAA, passesAALarge, suggestions } = useColorContrast(fg, bg);

  const levelColors: Record<WCAGLevel, string> = {
    AAA: "#16a34a",
    AA: "#2563eb",
    "AA-large": "#d97706",
    fail: "#dc2626",
  };

  return (
    <div style={{ maxWidth: "600px", margin: "2rem auto", fontFamily: "system-ui" }}>
      <h2>Color Contrast Checker</h2>

      {/* Color inputs */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "24px" }}>
        <div>
          <label htmlFor="fg-color" style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
            Foreground
          </label>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="color"
              id="fg-color"
              value={fg}
              onChange={(e) => setFg(e.target.value)}
              aria-label="Foreground color picker"
            />
            <input
              type="text"
              value={fg}
              onChange={(e) => { if (/^#[0-9a-f]{6}$/i.test(e.target.value)) setFg(e.target.value); }}
              aria-label="Foreground hex value"
              style={{ width: "100px", padding: "4px 8px", fontFamily: "monospace" }}
            />
          </div>
        </div>

        <div>
          <label htmlFor="bg-color" style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
            Background
          </label>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <input
              type="color"
              id="bg-color"
              value={bg}
              onChange={(e) => setBg(e.target.value)}
              aria-label="Background color picker"
            />
            <input
              type="text"
              value={bg}
              onChange={(e) => { if (/^#[0-9a-f]{6}$/i.test(e.target.value)) setBg(e.target.value); }}
              aria-label="Background hex value"
              style={{ width: "100px", padding: "4px 8px", fontFamily: "monospace" }}
            />
          </div>
        </div>
      </div>

      {/* Preview */}
      <div
        style={{ background: bg, color: fg, padding: "24px", borderRadius: "8px", marginBottom: "16px" }}
        aria-label="Color contrast preview"
      >
        <p style={{ fontSize: "24px", margin: "0 0 8px" }}>Large text preview (24px)</p>
        <p style={{ fontSize: "16px", margin: 0 }}>Normal text preview (16px). The quick brown fox jumps over the lazy dog.</p>
      </div>

      {/* Results */}
      <div
        role="region"
        aria-label="Contrast check results"
        style={{ padding: "16px", background: "#f9fafb", borderRadius: "8px", marginBottom: "16px" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <span style={{ fontSize: "14px", color: "#6b7280" }}>Contrast Ratio</span>
          <span style={{ fontSize: "24px", fontWeight: 700 }}>{ratio.toFixed(2)}:1</span>
        </div>

        <div style={{ fontSize: "18px", fontWeight: 600, color: levelColors[level], marginBottom: "12px" }}>
          WCAG Level: {level === "fail" ? "Does not pass" : level}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
          {([
            ["AA Normal (4.5:1)", passesAA],
            ["AA Large (3:1)", passesAALarge],
            ["AAA Normal (7:1)", passesAAA],
            ["AAA Large (4.5:1)", passesAAA || passesAA],
          ] as [string, boolean][]).map(([label, passes]) => (
            <div
              key={label}
              style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "8px", borderRadius: "4px",
                background: passes ? "#f0fdf4" : "#fef2f2",
              }}
            >
              <span aria-hidden="true" style={{ color: passes ? "#16a34a" : "#dc2626" }}>
                {passes ? "PASS" : "FAIL"}
              </span>
              <span style={{ fontSize: "13px" }}>{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div role="region" aria-label="Accessible color suggestions">
          <h3 style={{ marginBottom: "8px" }}>Suggested Alternatives</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => setFg(s.color)}
                style={{
                  display: "flex", alignItems: "center", gap: "12px",
                  padding: "12px", border: "1px solid #e5e7eb",
                  borderRadius: "6px", background: "white", cursor: "pointer",
                  textAlign: "left",
                }}
                aria-label={`Use ${s.color}, contrast ratio ${s.ratio.toFixed(2)} to 1, WCAG ${s.level}`}
              >
                <div style={{ width: "32px", height: "32px", borderRadius: "4px", background: s.color, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "monospace", fontWeight: 600 }}>{s.color}</div>
                  <div style={{ fontSize: "12px", color: "#6b7280" }}>{s.adjustment}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontWeight: 600 }}>{s.ratio.toFixed(2)}:1</div>
                  <div style={{ fontSize: "12px", color: levelColors[s.level] }}>{s.level}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { checkContrast, contrastRatio, suggestAccessibleColors, useColorContrast, ContrastChecker };
```

The utility implements the WCAG 2.1 relative luminance formula and contrast ratio calculation. It checks all four compliance levels (AA/AAA for normal and large text). The suggestion engine adjusts the foreground color's HSL lightness and saturation to find the nearest accessible alternative that preserves the original hue. The React hook memoizes calculations and the checker component provides real-time preview with live region updates for screen readers.'''
    ),
]
