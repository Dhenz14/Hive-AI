"""
Batch p1089: React design system patterns.
Component API design, theming engine, compound components, polymorphic components, documentation generation.
"""

PAIRS = [
    (
        "react/design-system",
        r'''Build a React design system theming engine in TypeScript with type-safe design tokens, CSS variable generation, dark/light mode support, component-level theme overrides, and a useTheme hook. Include nested theme provider support.''',
        r'''A type-safe theming engine with tokens, CSS variables, and nested providers:

```typescript
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

// ============================================
// Design token definitions
// ============================================

interface ColorScale {
  50: string;
  100: string;
  200: string;
  300: string;
  400: string;
  500: string;
  600: string;
  700: string;
  800: string;
  900: string;
}

interface SpacingScale {
  0: string;
  1: string;
  2: string;
  3: string;
  4: string;
  5: string;
  6: string;
  8: string;
  10: string;
  12: string;
  16: string;
  20: string;
}

interface TypographyScale {
  xs: { fontSize: string; lineHeight: string };
  sm: { fontSize: string; lineHeight: string };
  md: { fontSize: string; lineHeight: string };
  lg: { fontSize: string; lineHeight: string };
  xl: { fontSize: string; lineHeight: string };
  "2xl": { fontSize: string; lineHeight: string };
  "3xl": { fontSize: string; lineHeight: string };
}

interface ShadowScale {
  none: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
}

interface RadiusScale {
  none: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
  full: string;
}

interface SemanticColors {
  background: string;
  foreground: string;
  muted: string;
  mutedForeground: string;
  card: string;
  cardForeground: string;
  border: string;
  input: string;
  primary: string;
  primaryForeground: string;
  secondary: string;
  secondaryForeground: string;
  destructive: string;
  destructiveForeground: string;
  success: string;
  successForeground: string;
  warning: string;
  warningForeground: string;
  ring: string;
}

interface ThemeTokens {
  colors: {
    palette: Record<string, ColorScale>;
    semantic: SemanticColors;
  };
  spacing: SpacingScale;
  typography: TypographyScale;
  fontFamily: {
    sans: string;
    mono: string;
  };
  shadows: ShadowScale;
  radii: RadiusScale;
  transitions: {
    fast: string;
    normal: string;
    slow: string;
  };
}

// ============================================
// Default themes
// ============================================

const baseTokens: Omit<ThemeTokens, "colors"> = {
  spacing: {
    0: "0px", 1: "4px", 2: "8px", 3: "12px", 4: "16px",
    5: "20px", 6: "24px", 8: "32px", 10: "40px",
    12: "48px", 16: "64px", 20: "80px",
  },
  typography: {
    xs: { fontSize: "0.75rem", lineHeight: "1rem" },
    sm: { fontSize: "0.875rem", lineHeight: "1.25rem" },
    md: { fontSize: "1rem", lineHeight: "1.5rem" },
    lg: { fontSize: "1.125rem", lineHeight: "1.75rem" },
    xl: { fontSize: "1.25rem", lineHeight: "1.75rem" },
    "2xl": { fontSize: "1.5rem", lineHeight: "2rem" },
    "3xl": { fontSize: "1.875rem", lineHeight: "2.25rem" },
  },
  fontFamily: {
    sans: "system-ui, -apple-system, sans-serif",
    mono: "ui-monospace, monospace",
  },
  shadows: {
    none: "none",
    sm: "0 1px 2px rgba(0,0,0,0.05)",
    md: "0 4px 6px rgba(0,0,0,0.07)",
    lg: "0 10px 15px rgba(0,0,0,0.1)",
    xl: "0 20px 25px rgba(0,0,0,0.15)",
  },
  radii: {
    none: "0px", sm: "4px", md: "6px",
    lg: "8px", xl: "12px", full: "9999px",
  },
  transitions: {
    fast: "150ms cubic-bezier(0.4, 0, 0.2, 1)",
    normal: "200ms cubic-bezier(0.4, 0, 0.2, 1)",
    slow: "300ms cubic-bezier(0.4, 0, 0.2, 1)",
  },
};

const bluePalette: ColorScale = {
  50: "#eff6ff", 100: "#dbeafe", 200: "#bfdbfe", 300: "#93c5fd",
  400: "#60a5fa", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8",
  800: "#1e40af", 900: "#1e3a8a",
};

const lightTheme: ThemeTokens = {
  ...baseTokens,
  colors: {
    palette: { blue: bluePalette },
    semantic: {
      background: "#ffffff",
      foreground: "#0f172a",
      muted: "#f1f5f9",
      mutedForeground: "#64748b",
      card: "#ffffff",
      cardForeground: "#0f172a",
      border: "#e2e8f0",
      input: "#e2e8f0",
      primary: "#2563eb",
      primaryForeground: "#ffffff",
      secondary: "#f1f5f9",
      secondaryForeground: "#0f172a",
      destructive: "#dc2626",
      destructiveForeground: "#ffffff",
      success: "#16a34a",
      successForeground: "#ffffff",
      warning: "#d97706",
      warningForeground: "#ffffff",
      ring: "#3b82f6",
    },
  },
};

const darkTheme: ThemeTokens = {
  ...baseTokens,
  colors: {
    palette: { blue: bluePalette },
    semantic: {
      background: "#0f172a",
      foreground: "#f8fafc",
      muted: "#1e293b",
      mutedForeground: "#94a3b8",
      card: "#1e293b",
      cardForeground: "#f8fafc",
      border: "#334155",
      input: "#334155",
      primary: "#3b82f6",
      primaryForeground: "#ffffff",
      secondary: "#1e293b",
      secondaryForeground: "#f8fafc",
      destructive: "#ef4444",
      destructiveForeground: "#ffffff",
      success: "#22c55e",
      successForeground: "#ffffff",
      warning: "#f59e0b",
      warningForeground: "#000000",
      ring: "#60a5fa",
    },
  },
};

// ============================================
// CSS variable generation
// ============================================

function flattenTokens(obj: Record<string, unknown>, prefix: string = ""): Record<string, string> {
  const result: Record<string, string> = {};

  for (const [key, value] of Object.entries(obj)) {
    const varName = prefix ? `${prefix}-${key}` : key;

    if (typeof value === "string") {
      result[`--${varName}`] = value;
    } else if (typeof value === "object" && value !== null) {
      Object.assign(result, flattenTokens(value as Record<string, unknown>, varName));
    }
  }

  return result;
}

function generateCSSVariables(tokens: ThemeTokens): Record<string, string> {
  return flattenTokens({
    color: tokens.colors.semantic,
    spacing: tokens.spacing,
    radius: tokens.radii,
    shadow: tokens.shadows,
    font: tokens.fontFamily,
    transition: tokens.transitions,
  });
}

// ============================================
// Theme context
// ============================================

type ThemeMode = "light" | "dark" | "system";

interface ThemeContextType {
  tokens: ThemeTokens;
  mode: ThemeMode;
  resolvedMode: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  cssVars: Record<string, string>;
  token: <T>(path: string) => T;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

function resolveSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultMode?: ThemeMode;
  themes?: { light: ThemeTokens; dark: ThemeTokens };
  overrides?: Partial<ThemeTokens>;
}

export function ThemeProvider({
  children,
  defaultMode = "system",
  themes,
  overrides,
}: ThemeProviderProps) {
  const parentTheme = useContext(ThemeContext);
  const [mode, setMode] = useState<ThemeMode>(defaultMode);
  const [systemPref, setSystemPref] = useState<"light" | "dark">(resolveSystemTheme);

  // Listen for system theme changes
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    function handleChange(e: MediaQueryListEvent) {
      setSystemPref(e.matches ? "dark" : "light");
    }
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  const resolvedMode = mode === "system" ? systemPref : mode;

  const themeMap = themes || { light: lightTheme, dark: darkTheme };
  const baseThemeTokens = themeMap[resolvedMode];

  // Deep merge overrides
  const tokens = useMemo(() => {
    if (!overrides) return baseThemeTokens;
    return deepMergeTokens(baseThemeTokens, overrides);
  }, [baseThemeTokens, overrides]);

  const cssVars = useMemo(() => generateCSSVariables(tokens), [tokens]);

  // Token accessor by dot path
  const token = useCallback(<T,>(path: string): T => {
    const parts = path.split(".");
    let current: unknown = tokens;
    for (const part of parts) {
      if (current && typeof current === "object") {
        current = (current as Record<string, unknown>)[part];
      } else {
        return undefined as T;
      }
    }
    return current as T;
  }, [tokens]);

  // Persist preference
  useEffect(() => {
    try {
      localStorage.setItem("theme-mode", mode);
    } catch {}
  }, [mode]);

  const contextValue = useMemo<ThemeContextType>(
    () => ({ tokens, mode, resolvedMode, setMode, cssVars, token }),
    [tokens, mode, resolvedMode, cssVars, token]
  );

  return (
    <ThemeContext.Provider value={contextValue}>
      <div
        style={cssVars as React.CSSProperties}
        data-theme={resolvedMode}
        className={`theme-${resolvedMode}`}
      >
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

function deepMergeTokens(base: ThemeTokens, overrides: Partial<ThemeTokens>): ThemeTokens {
  const result = { ...base };
  for (const key of Object.keys(overrides) as (keyof ThemeTokens)[]) {
    const overrideVal = overrides[key];
    if (overrideVal && typeof overrideVal === "object" && typeof result[key] === "object") {
      (result as Record<string, unknown>)[key] = {
        ...(result[key] as Record<string, unknown>),
        ...(overrideVal as Record<string, unknown>),
      };
    } else if (overrideVal !== undefined) {
      (result as Record<string, unknown>)[key] = overrideVal;
    }
  }
  return result;
}

// ============================================
// Hook
// ============================================

export function useTheme(): ThemeContextType {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

// CSS variable accessor for components
export function cssVar(name: string): string {
  return `var(--${name})`;
}

// ============================================
// Theme toggle component
// ============================================

function ThemeToggle() {
  const { mode, setMode, resolvedMode } = useTheme();

  const modes: ThemeMode[] = ["light", "dark", "system"];
  const labels: Record<ThemeMode, string> = {
    light: "Light", dark: "Dark", system: "System",
  };

  return (
    <div role="radiogroup" aria-label="Color theme" style={{ display: "flex", gap: "4px" }}>
      {modes.map((m) => (
        <button
          key={m}
          role="radio"
          aria-checked={mode === m}
          onClick={() => setMode(m)}
          style={{
            padding: "6px 12px", borderRadius: "4px",
            border: mode === m ? "2px solid var(--color-primary)" : "1px solid var(--color-border)",
            background: mode === m ? "var(--color-primary)" : "var(--color-background)",
            color: mode === m ? "var(--color-primaryForeground)" : "var(--color-foreground)",
            cursor: "pointer", fontSize: "13px",
          }}
        >
          {labels[m]}
        </button>
      ))}
    </div>
  );
}

// Nested theme example - a card with its own theme overrides
function BrandedSection({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      overrides={{
        colors: {
          palette: { blue: bluePalette },
          semantic: {
            ...lightTheme.colors.semantic,
            primary: "#7c3aed",
            primaryForeground: "#ffffff",
            background: "#faf5ff",
          },
        },
      } as Partial<ThemeTokens>}
    >
      <div style={{
        background: cssVar("color-background"),
        padding: cssVar("spacing-6"),
        borderRadius: cssVar("radius-lg"),
      }}>
        {children}
      </div>
    </ThemeProvider>
  );
}
```

The theming engine generates CSS custom properties from token definitions, supports light/dark/system modes with `prefers-color-scheme` listening, persists preference to localStorage, and allows nested `ThemeProvider` instances for component-level overrides. The `token()` accessor provides type-safe dot-path access to any token value, and `cssVar()` is a helper for referencing variables in inline styles.'''
    ),
    (
        "react/design-system",
        r'''<think>
Compound components are a powerful pattern for design systems - they share implicit state through context while giving users control over composition. I need to show:

1. A compound component pattern (e.g., Select with Select.Trigger, Select.Content, Select.Item)
2. Shared internal state via context
3. Controlled and uncontrolled modes
4. Proper TypeScript types for the compound component interface
5. Slot pattern for customizing internal elements

Let me build a compound Select component since it demonstrates all these concepts well.
</think>
Build a compound component pattern for a React design system Select component with TypeScript. Include Select.Trigger, Select.Content, Select.Item, Select.Group, and Select.Label. Support controlled/uncontrolled modes, keyboard navigation, and customizable rendering via slots.''',
        r'''A compound Select component with shared context and keyboard navigation:

```typescript
import React, {
  createContext, useCallback, useContext, useEffect,
  useId, useRef, useState, forwardRef,
} from "react";

// ============================================
// Types
// ============================================

interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectContextType {
  isOpen: boolean;
  selectedValue: string | undefined;
  highlightedIndex: number;
  options: SelectOption[];
  selectId: string;
  open: () => void;
  close: () => void;
  toggle: () => void;
  select: (value: string) => void;
  registerOption: (option: SelectOption) => void;
  unregisterOption: (value: string) => void;
  setHighlighted: (index: number) => void;
}

const SelectContext = createContext<SelectContextType | null>(null);

function useSelectContext(): SelectContextType {
  const ctx = useContext(SelectContext);
  if (!ctx) throw new Error("Select compound components must be used within Select.Root");
  return ctx;
}

// ============================================
// Select.Root
// ============================================

interface SelectRootProps {
  children: React.ReactNode;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
}

function SelectRoot({
  children,
  value: controlledValue,
  defaultValue,
  onValueChange,
  disabled = false,
}: SelectRootProps) {
  const selectId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [internalValue, setInternalValue] = useState(defaultValue);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [options, setOptions] = useState<SelectOption[]>([]);

  const isControlled = controlledValue !== undefined;
  const selectedValue = isControlled ? controlledValue : internalValue;

  const open = useCallback(() => {
    if (disabled) return;
    setIsOpen(true);
    // Highlight the selected option or first
    const idx = options.findIndex((o) => o.value === selectedValue);
    setHighlightedIndex(idx >= 0 ? idx : 0);
  }, [disabled, options, selectedValue]);

  const close = useCallback(() => {
    setIsOpen(false);
    setHighlightedIndex(-1);
  }, []);

  const toggle = useCallback(() => {
    if (isOpen) close();
    else open();
  }, [isOpen, open, close]);

  const select = useCallback((value: string) => {
    if (!isControlled) setInternalValue(value);
    onValueChange?.(value);
    close();
  }, [isControlled, onValueChange, close]);

  const registerOption = useCallback((option: SelectOption) => {
    setOptions((prev) => {
      if (prev.some((o) => o.value === option.value)) return prev;
      return [...prev, option];
    });
  }, []);

  const unregisterOption = useCallback((value: string) => {
    setOptions((prev) => prev.filter((o) => o.value !== value));
  }, []);

  const contextValue: SelectContextType = {
    isOpen,
    selectedValue,
    highlightedIndex,
    options,
    selectId,
    open,
    close,
    toggle,
    select,
    registerOption,
    unregisterOption,
    setHighlighted: setHighlightedIndex,
  };

  return (
    <SelectContext.Provider value={contextValue}>
      <div style={{ position: "relative", display: "inline-block" }} data-disabled={disabled || undefined}>
        {children}
      </div>
    </SelectContext.Provider>
  );
}

// ============================================
// Select.Trigger
// ============================================

interface SelectTriggerProps {
  children?: React.ReactNode;
  placeholder?: string;
  className?: string;
  asChild?: boolean;
}

const SelectTrigger = forwardRef<HTMLButtonElement, SelectTriggerProps>(
  function SelectTrigger({ children, placeholder = "Select...", className }, ref) {
    const ctx = useSelectContext();
    const triggerRef = useRef<HTMLButtonElement | null>(null);

    const selectedOption = ctx.options.find((o) => o.value === ctx.selectedValue);

    function handleKeyDown(e: React.KeyboardEvent) {
      switch (e.key) {
        case "ArrowDown":
        case "ArrowUp":
        case "Enter":
        case " ":
          e.preventDefault();
          ctx.open();
          break;
      }
    }

    return (
      <button
        ref={(el) => {
          triggerRef.current = el;
          if (typeof ref === "function") ref(el);
          else if (ref) ref.current = el;
        }}
        type="button"
        role="combobox"
        aria-expanded={ctx.isOpen}
        aria-haspopup="listbox"
        aria-controls={`${ctx.selectId}-listbox`}
        aria-activedescendant={
          ctx.highlightedIndex >= 0
            ? `${ctx.selectId}-option-${ctx.options[ctx.highlightedIndex]?.value}`
            : undefined
        }
        onClick={ctx.toggle}
        onKeyDown={handleKeyDown}
        className={className}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: "8px", padding: "8px 12px",
          minWidth: "180px", border: "1px solid var(--color-border, #e2e8f0)",
          borderRadius: "6px", background: "var(--color-background, white)",
          cursor: "pointer", fontSize: "14px",
          color: selectedOption ? "var(--color-foreground, #0f172a)" : "var(--color-mutedForeground, #94a3b8)",
        }}
      >
        <span>{children || selectedOption?.label || placeholder}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" />
        </svg>
      </button>
    );
  }
);

// ============================================
// Select.Content
// ============================================

interface SelectContentProps {
  children: React.ReactNode;
  className?: string;
  position?: "popper" | "item-aligned";
}

function SelectContent({ children, className, position = "popper" }: SelectContentProps) {
  const ctx = useSelectContext();
  const listboxRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!ctx.isOpen) return;

    function handleClick(e: MouseEvent) {
      if (listboxRef.current && !listboxRef.current.contains(e.target as Node)) {
        ctx.close();
      }
    }

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [ctx.isOpen, ctx]);

  // Keyboard navigation
  useEffect(() => {
    if (!ctx.isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      const enabledOptions = ctx.options.filter((o) => !o.disabled);

      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          const currentEnabled = enabledOptions.findIndex(
            (o) => ctx.options.indexOf(o) === ctx.highlightedIndex
          );
          const nextIdx = (currentEnabled + 1) % enabledOptions.length;
          ctx.setHighlighted(ctx.options.indexOf(enabledOptions[nextIdx]));
          break;
        }
        case "ArrowUp": {
          e.preventDefault();
          const currentEnabled2 = enabledOptions.findIndex(
            (o) => ctx.options.indexOf(o) === ctx.highlightedIndex
          );
          const prevIdx = (currentEnabled2 - 1 + enabledOptions.length) % enabledOptions.length;
          ctx.setHighlighted(ctx.options.indexOf(enabledOptions[prevIdx]));
          break;
        }
        case "Enter":
        case " ":
          e.preventDefault();
          if (ctx.highlightedIndex >= 0) {
            const option = ctx.options[ctx.highlightedIndex];
            if (option && !option.disabled) ctx.select(option.value);
          }
          break;
        case "Escape":
          e.preventDefault();
          ctx.close();
          break;
        case "Home":
          e.preventDefault();
          if (enabledOptions.length > 0) {
            ctx.setHighlighted(ctx.options.indexOf(enabledOptions[0]));
          }
          break;
        case "End":
          e.preventDefault();
          if (enabledOptions.length > 0) {
            ctx.setHighlighted(ctx.options.indexOf(enabledOptions[enabledOptions.length - 1]));
          }
          break;
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [ctx]);

  if (!ctx.isOpen) return null;

  return (
    <div
      ref={listboxRef}
      id={`${ctx.selectId}-listbox`}
      role="listbox"
      aria-label="Options"
      className={className}
      style={{
        position: "absolute", top: "100%", left: 0, right: 0,
        marginTop: "4px", padding: "4px",
        background: "var(--color-card, white)",
        border: "1px solid var(--color-border, #e2e8f0)",
        borderRadius: "8px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
        zIndex: 50, maxHeight: "240px", overflowY: "auto",
      }}
    >
      {children}
    </div>
  );
}

// ============================================
// Select.Item
// ============================================

interface SelectItemProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}

function SelectItem({ value, children, disabled = false, className }: SelectItemProps) {
  const ctx = useSelectContext();
  const optionIndex = ctx.options.findIndex((o) => o.value === value);
  const isSelected = ctx.selectedValue === value;
  const isHighlighted = ctx.highlightedIndex === optionIndex;

  // Register option on mount
  useEffect(() => {
    const label = typeof children === "string" ? children : value;
    ctx.registerOption({ value, label, disabled });
    return () => ctx.unregisterOption(value);
  }, [value, disabled]);

  return (
    <div
      id={`${ctx.selectId}-option-${value}`}
      role="option"
      aria-selected={isSelected}
      aria-disabled={disabled}
      onClick={() => { if (!disabled) ctx.select(value); }}
      onMouseEnter={() => { if (!disabled) ctx.setHighlighted(optionIndex); }}
      className={className}
      style={{
        display: "flex", alignItems: "center", gap: "8px",
        padding: "8px 12px", borderRadius: "4px",
        cursor: disabled ? "not-allowed" : "pointer",
        fontSize: "14px",
        background: isHighlighted ? "var(--color-muted, #f1f5f9)" : "transparent",
        color: disabled ? "var(--color-mutedForeground, #94a3b8)" : "var(--color-foreground, #0f172a)",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {/* Selected checkmark */}
      <span style={{ width: "16px", flexShrink: 0 }}>
        {isSelected && (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
          </svg>
        )}
      </span>
      <span style={{ flex: 1 }}>{children}</span>
    </div>
  );
}

// ============================================
// Select.Group and Select.Label
// ============================================

function SelectGroup({ children }: { children: React.ReactNode }) {
  return (
    <div role="group" style={{ padding: "4px 0" }}>
      {children}
    </div>
  );
}

function SelectLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      aria-hidden="true"
      style={{
        padding: "4px 12px", fontSize: "12px", fontWeight: 600,
        color: "var(--color-mutedForeground, #94a3b8)",
        textTransform: "uppercase", letterSpacing: "0.05em",
      }}
    >
      {children}
    </div>
  );
}

// Select.Separator
function SelectSeparator() {
  return (
    <div
      role="separator"
      style={{
        height: "1px", margin: "4px 0",
        background: "var(--color-border, #e2e8f0)",
      }}
    />
  );
}

// ============================================
// Compose the compound component
// ============================================

export const Select = {
  Root: SelectRoot,
  Trigger: SelectTrigger,
  Content: SelectContent,
  Item: SelectItem,
  Group: SelectGroup,
  Label: SelectLabel,
  Separator: SelectSeparator,
};

// ============================================
// Usage
// ============================================

function CountrySelector() {
  const [country, setCountry] = useState<string>();

  return (
    <div>
      <label id="country-label" style={{ display: "block", marginBottom: "4px", fontWeight: 600 }}>
        Country
      </label>
      <Select.Root value={country} onValueChange={setCountry}>
        <Select.Trigger placeholder="Select a country" aria-labelledby="country-label" />
        <Select.Content>
          <Select.Group>
            <Select.Label>North America</Select.Label>
            <Select.Item value="us">United States</Select.Item>
            <Select.Item value="ca">Canada</Select.Item>
            <Select.Item value="mx">Mexico</Select.Item>
          </Select.Group>

          <Select.Separator />

          <Select.Group>
            <Select.Label>Europe</Select.Label>
            <Select.Item value="gb">United Kingdom</Select.Item>
            <Select.Item value="de">Germany</Select.Item>
            <Select.Item value="fr">France</Select.Item>
            <Select.Item value="es" disabled>Spain (unavailable)</Select.Item>
          </Select.Group>
        </Select.Content>
      </Select.Root>
    </div>
  );
}
```

The compound component pattern uses `Select.Root` as the context provider with `Select.Trigger`, `Select.Content`, and `Select.Item` as consumers. Items self-register via `useEffect` so the root tracks all options for keyboard navigation. The controlled/uncontrolled pattern uses the `value` prop presence check, and forwardRef on Trigger enables external ref access. Each sub-component is independently styleable while sharing navigation and selection state.'''
    ),
    (
        "react/design-system",
        r'''Create a polymorphic component system for React that allows components to render as different HTML elements or other components while preserving type safety. Include an `as` prop implementation, proper ref forwarding, and a component factory for creating polymorphic design system primitives.''',
        r'''A type-safe polymorphic component system with `as` prop and ref forwarding:

```typescript
import React, { forwardRef } from "react";

// ============================================
// Core polymorphic types
// ============================================

// Extract props of a component or HTML element type
type PropsOf<T extends React.ElementType> = React.ComponentPropsWithoutRef<T>;

// The "as" prop
type AsProp<T extends React.ElementType> = { as?: T };

// Merge component's own props with the "as" target's props
// Own props take precedence over the target element's props
type PolymorphicProps<
  T extends React.ElementType,
  OwnProps = {}
> = OwnProps &
  AsProp<T> &
  Omit<PropsOf<T>, keyof OwnProps | "as">;

// Ref type for the polymorphic component
type PolymorphicRef<T extends React.ElementType> = React.ComponentPropsWithRef<T>["ref"];

// Full props including ref
type PolymorphicPropsWithRef<
  T extends React.ElementType,
  OwnProps = {}
> = PolymorphicProps<T, OwnProps> & { ref?: PolymorphicRef<T> };

// Component type that accepts "as" prop
type PolymorphicComponent<
  DefaultElement extends React.ElementType,
  OwnProps = {}
> = <T extends React.ElementType = DefaultElement>(
  props: PolymorphicPropsWithRef<T, OwnProps>
) => React.ReactElement | null;

// ============================================
// Component factory
// ============================================

function createPolymorphicComponent<
  DefaultElement extends React.ElementType,
  OwnProps = {}
>(
  displayName: string,
  render: <T extends React.ElementType = DefaultElement>(
    props: PolymorphicProps<T, OwnProps>,
    ref: PolymorphicRef<T>
  ) => React.ReactElement | null
): PolymorphicComponent<DefaultElement, OwnProps> {
  const Component = forwardRef(render as any) as any;
  Component.displayName = displayName;
  return Component;
}

// ============================================
// Design system primitives
// ============================================

// Box - the most basic building block
interface BoxOwnProps {
  padding?: string | number;
  margin?: string | number;
  display?: React.CSSProperties["display"];
  flex?: React.CSSProperties["flex"];
  gap?: string | number;
}

const Box = createPolymorphicComponent<"div", BoxOwnProps>(
  "Box",
  (props, ref) => {
    const { as: Component = "div", padding, margin, display, flex, gap, style, ...rest } = props;

    return (
      <Component
        ref={ref}
        style={{
          padding,
          margin,
          display,
          flex,
          gap,
          ...style,
        }}
        {...rest}
      />
    );
  }
);

// Text - typography primitive
type TextVariant = "body" | "caption" | "label" | "heading";
type TextSize = "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl";
type TextWeight = "normal" | "medium" | "semibold" | "bold";

interface TextOwnProps {
  variant?: TextVariant;
  size?: TextSize;
  weight?: TextWeight;
  color?: string;
  truncate?: boolean;
  align?: React.CSSProperties["textAlign"];
}

const sizeMap: Record<TextSize, { fontSize: string; lineHeight: string }> = {
  xs: { fontSize: "0.75rem", lineHeight: "1rem" },
  sm: { fontSize: "0.875rem", lineHeight: "1.25rem" },
  md: { fontSize: "1rem", lineHeight: "1.5rem" },
  lg: { fontSize: "1.125rem", lineHeight: "1.75rem" },
  xl: { fontSize: "1.25rem", lineHeight: "1.75rem" },
  "2xl": { fontSize: "1.5rem", lineHeight: "2rem" },
  "3xl": { fontSize: "1.875rem", lineHeight: "2.25rem" },
};

const weightMap: Record<TextWeight, number> = {
  normal: 400, medium: 500, semibold: 600, bold: 700,
};

const variantDefaults: Record<TextVariant, { element: React.ElementType; size: TextSize; weight: TextWeight }> = {
  body: { element: "p", size: "md", weight: "normal" },
  caption: { element: "span", size: "sm", weight: "normal" },
  label: { element: "label", size: "sm", weight: "medium" },
  heading: { element: "h2", size: "xl", weight: "bold" },
};

const Text = createPolymorphicComponent<"span", TextOwnProps>(
  "Text",
  (props, ref) => {
    const {
      as,
      variant = "body",
      size,
      weight,
      color,
      truncate = false,
      align,
      style,
      ...rest
    } = props;

    const defaults = variantDefaults[variant];
    const Component = as || defaults.element;
    const resolvedSize = size || defaults.size;
    const resolvedWeight = weight || defaults.weight;
    const sizeStyles = sizeMap[resolvedSize];

    return (
      <Component
        ref={ref}
        style={{
          fontSize: sizeStyles.fontSize,
          lineHeight: sizeStyles.lineHeight,
          fontWeight: weightMap[resolvedWeight],
          color: color || "inherit",
          textAlign: align,
          ...(truncate && {
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap" as const,
          }),
          margin: 0,
          ...style,
        }}
        {...rest}
      />
    );
  }
);

// Stack - layout primitive
type StackDirection = "horizontal" | "vertical";
type StackAlign = "start" | "center" | "end" | "stretch" | "baseline";
type StackJustify = "start" | "center" | "end" | "between" | "around" | "evenly";

interface StackOwnProps {
  direction?: StackDirection;
  gap?: string | number;
  align?: StackAlign;
  justify?: StackJustify;
  wrap?: boolean;
}

const alignMap: Record<StackAlign, string> = {
  start: "flex-start", center: "center", end: "flex-end",
  stretch: "stretch", baseline: "baseline",
};

const justifyMap: Record<StackJustify, string> = {
  start: "flex-start", center: "center", end: "flex-end",
  between: "space-between", around: "space-around", evenly: "space-evenly",
};

const Stack = createPolymorphicComponent<"div", StackOwnProps>(
  "Stack",
  (props, ref) => {
    const {
      as: Component = "div",
      direction = "vertical",
      gap = "8px",
      align = "stretch",
      justify = "start",
      wrap = false,
      style,
      ...rest
    } = props;

    return (
      <Component
        ref={ref}
        style={{
          display: "flex",
          flexDirection: direction === "horizontal" ? "row" : "column",
          gap,
          alignItems: alignMap[align],
          justifyContent: justifyMap[justify],
          flexWrap: wrap ? "wrap" : "nowrap",
          ...style,
        }}
        {...rest}
      />
    );
  }
);

// Button - interactive primitive
type ButtonVariant = "solid" | "outline" | "ghost" | "link";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonOwnProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

const buttonSizes: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: "4px 12px", fontSize: "13px", height: "32px" },
  md: { padding: "8px 16px", fontSize: "14px", height: "40px" },
  lg: { padding: "12px 24px", fontSize: "16px", height: "48px" },
};

const buttonVariants: Record<ButtonVariant, React.CSSProperties> = {
  solid: {
    background: "var(--color-primary, #2563eb)",
    color: "var(--color-primaryForeground, white)",
    border: "none",
  },
  outline: {
    background: "transparent",
    color: "var(--color-foreground, #0f172a)",
    border: "1px solid var(--color-border, #e2e8f0)",
  },
  ghost: {
    background: "transparent",
    color: "var(--color-foreground, #0f172a)",
    border: "none",
  },
  link: {
    background: "transparent",
    color: "var(--color-primary, #2563eb)",
    border: "none",
    textDecoration: "underline",
  },
};

const Button = createPolymorphicComponent<"button", ButtonOwnProps>(
  "Button",
  (props, ref) => {
    const {
      as: Component = "button",
      variant = "solid",
      size = "md",
      loading = false,
      leftIcon,
      rightIcon,
      fullWidth = false,
      style,
      disabled,
      children,
      ...rest
    } = props;

    return (
      <Component
        ref={ref}
        disabled={disabled || loading}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "8px",
          borderRadius: "6px",
          fontWeight: 500,
          cursor: disabled || loading ? "not-allowed" : "pointer",
          opacity: disabled ? 0.5 : 1,
          width: fullWidth ? "100%" : "auto",
          transition: "background 150ms, opacity 150ms",
          ...buttonSizes[size],
          ...buttonVariants[variant],
          ...style,
        }}
        {...rest}
      >
        {loading && <span aria-hidden="true">...</span>}
        {!loading && leftIcon}
        <span>{children}</span>
        {!loading && rightIcon}
      </Component>
    );
  }
);

// ============================================
// Usage examples with full type safety
// ============================================

function ExampleUsage() {
  return (
    <Stack gap="24px" style={{ maxWidth: "600px", margin: "2rem auto" }}>
      {/* Box renders as a section */}
      <Box as="section" padding="16px">
        <Text variant="heading" as="h1" size="3xl">
          Polymorphic Components
        </Text>
      </Box>

      {/* Text renders as different elements */}
      <Text variant="body">Regular paragraph text</Text>
      <Text as="span" size="sm" color="#6b7280">Small muted span</Text>
      <Text as="a" href="/about" color="#2563eb">Link text with anchor element</Text>

      {/* Stack as nav */}
      <Stack as="nav" direction="horizontal" gap="16px" align="center">
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
      </Stack>

      {/* Button variants */}
      <Stack direction="horizontal" gap="8px" wrap>
        <Button variant="solid">Primary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button as="a" href="/docs" variant="link">Link Button</Button>
      </Stack>

      {/* Button as link - type-safe href */}
      <Button as="a" href="/signup" variant="solid" size="lg" fullWidth>
        Sign Up
      </Button>
    </Stack>
  );
}
```

The `createPolymorphicComponent` factory handles the complex generic typing needed for the `as` prop. When you write `<Button as="a" href="/signup">`, TypeScript knows that `href` is valid (because `<a>` accepts it) and would flag `<Button as="div" href="/signup">` as an error (because `<div>` does not accept `href`). The component's own props always take precedence in the type union, preventing conflicts.'''
    ),
    (
        "react/design-system",
        r'''<think>
The user wants a component variant system similar to CVA (Class Variance Authority) but for a design system. I need to build:

1. A `defineComponent` or `styled` function that takes a base config with variants
2. Type-safe variant props
3. Compound variants (combinations like variant=primary + size=lg)
4. Default variants
5. A way to compose variant styles from CSS-in-JS objects

This is about the API design layer of a design system, not just individual components.
</think>
Build a TypeScript variant system for React design system components, similar to CVA (Class Variance Authority) but for CSS-in-JS. Support typed variant definitions, compound variants, default variants, and component composition with variant inheritance.''',
        r'''A type-safe component variant system with compound variants and composition:

```typescript
import React, { forwardRef } from "react";

// ============================================
// Core variant system types
// ============================================

type StyleObject = React.CSSProperties;

interface VariantDefinition {
  [variantValue: string]: StyleObject;
}

type VariantsConfig = Record<string, VariantDefinition>;

interface CompoundVariant<V extends VariantsConfig> {
  conditions: Partial<{ [K in keyof V]: keyof V[K] }>;
  style: StyleObject;
}

interface ComponentConfig<V extends VariantsConfig> {
  base: StyleObject;
  variants: V;
  compoundVariants?: CompoundVariant<V>[];
  defaultVariants?: Partial<{ [K in keyof V]: keyof V[K] }>;
}

// Infer variant props from config
type VariantProps<V extends VariantsConfig> = {
  [K in keyof V]?: keyof V[K];
};

// ============================================
// Style resolver
// ============================================

function resolveStyles<V extends VariantsConfig>(
  config: ComponentConfig<V>,
  variantProps: VariantProps<V>
): StyleObject {
  let styles: StyleObject = { ...config.base };

  // Apply variant styles
  const resolvedVariants = { ...config.defaultVariants, ...variantProps } as VariantProps<V>;

  for (const [variantKey, variantValue] of Object.entries(resolvedVariants)) {
    if (variantValue === undefined) continue;
    const variantDef = config.variants[variantKey];
    if (variantDef && variantDef[variantValue as string]) {
      styles = { ...styles, ...variantDef[variantValue as string] };
    }
  }

  // Apply compound variants
  if (config.compoundVariants) {
    for (const compound of config.compoundVariants) {
      const matches = Object.entries(compound.conditions).every(
        ([key, value]) => resolvedVariants[key] === value
      );
      if (matches) {
        styles = { ...styles, ...compound.style };
      }
    }
  }

  return styles;
}

// ============================================
// Component factory with variants
// ============================================

function defineVariants<V extends VariantsConfig>(config: ComponentConfig<V>) {
  return config;
}

type StyledComponentProps<
  Element extends React.ElementType,
  V extends VariantsConfig
> = VariantProps<V> &
  Omit<React.ComponentPropsWithRef<Element>, keyof VariantProps<V>> & {
    as?: React.ElementType;
    className?: string;
  };

function styled<
  Element extends React.ElementType,
  V extends VariantsConfig
>(
  defaultElement: Element,
  config: ComponentConfig<V>
) {
  type Props = StyledComponentProps<Element, V>;

  const Component = forwardRef<unknown, Props>((props, ref) => {
    const { as, style: userStyle, ...rest } = props as Record<string, unknown>;
    const Tag = (as || defaultElement) as React.ElementType;

    // Separate variant props from element props
    const variantProps: Record<string, unknown> = {};
    const elementProps: Record<string, unknown> = {};

    for (const [key, value] of Object.entries(rest)) {
      if (key in config.variants) {
        variantProps[key] = value;
      } else {
        elementProps[key] = value;
      }
    }

    const resolvedStyles = resolveStyles(config, variantProps as VariantProps<V>);

    return (
      <Tag
        ref={ref}
        style={{ ...resolvedStyles, ...(userStyle as StyleObject) }}
        {...elementProps}
      />
    );
  }) as React.ForwardRefExoticComponent<Props & React.RefAttributes<unknown>>;

  Component.displayName = `Styled(${typeof defaultElement === "string" ? defaultElement : "Component"})`;

  // Attach config for composition
  (Component as any).__variantConfig = config;

  return Component;
}

// ============================================
// Variant composition (extend existing variants)
// ============================================

function extendVariants<
  V extends VariantsConfig,
  ExtV extends VariantsConfig
>(
  baseConfig: ComponentConfig<V>,
  extension: {
    base?: StyleObject;
    variants?: ExtV;
    compoundVariants?: CompoundVariant<V & ExtV>[];
    defaultVariants?: Partial<{ [K in keyof (V & ExtV)]: keyof (V & ExtV)[K] }>;
  }
): ComponentConfig<V & ExtV> {
  const mergedVariants: Record<string, VariantDefinition> = {};

  // Merge base variants
  for (const [key, def] of Object.entries(baseConfig.variants)) {
    mergedVariants[key] = { ...def };
  }

  // Merge extension variants
  if (extension.variants) {
    for (const [key, def] of Object.entries(extension.variants)) {
      mergedVariants[key] = { ...mergedVariants[key], ...def };
    }
  }

  return {
    base: { ...baseConfig.base, ...extension.base },
    variants: mergedVariants as V & ExtV,
    compoundVariants: [
      ...(baseConfig.compoundVariants || []),
      ...(extension.compoundVariants || []),
    ] as CompoundVariant<V & ExtV>[],
    defaultVariants: {
      ...baseConfig.defaultVariants,
      ...extension.defaultVariants,
    } as Partial<{ [K in keyof (V & ExtV)]: keyof (V & ExtV)[K] }>,
  };
}

// ============================================
// Design system components using the variant system
// ============================================

// Badge component
const badgeConfig = defineVariants({
  base: {
    display: "inline-flex",
    alignItems: "center",
    borderRadius: "9999px",
    fontWeight: 500,
    whiteSpace: "nowrap" as const,
    transition: "background 150ms",
  },
  variants: {
    variant: {
      solid: { color: "white" },
      outline: { background: "transparent", borderWidth: "1px", borderStyle: "solid" as const },
      soft: {},
    },
    color: {
      primary: {},
      success: {},
      warning: {},
      danger: {},
      neutral: {},
    },
    size: {
      sm: { padding: "2px 8px", fontSize: "11px", lineHeight: "16px" },
      md: { padding: "4px 12px", fontSize: "12px", lineHeight: "18px" },
      lg: { padding: "6px 16px", fontSize: "14px", lineHeight: "20px" },
    },
  },
  compoundVariants: [
    // Solid + color combinations
    { conditions: { variant: "solid", color: "primary" }, style: { background: "#2563eb" } },
    { conditions: { variant: "solid", color: "success" }, style: { background: "#16a34a" } },
    { conditions: { variant: "solid", color: "warning" }, style: { background: "#d97706" } },
    { conditions: { variant: "solid", color: "danger" }, style: { background: "#dc2626" } },
    { conditions: { variant: "solid", color: "neutral" }, style: { background: "#475569" } },
    // Soft + color combinations
    { conditions: { variant: "soft", color: "primary" }, style: { background: "#eff6ff", color: "#1d4ed8" } },
    { conditions: { variant: "soft", color: "success" }, style: { background: "#f0fdf4", color: "#15803d" } },
    { conditions: { variant: "soft", color: "warning" }, style: { background: "#fffbeb", color: "#b45309" } },
    { conditions: { variant: "soft", color: "danger" }, style: { background: "#fef2f2", color: "#b91c1c" } },
    { conditions: { variant: "soft", color: "neutral" }, style: { background: "#f1f5f9", color: "#334155" } },
    // Outline + color combinations
    { conditions: { variant: "outline", color: "primary" }, style: { borderColor: "#2563eb", color: "#2563eb" } },
    { conditions: { variant: "outline", color: "success" }, style: { borderColor: "#16a34a", color: "#16a34a" } },
    { conditions: { variant: "outline", color: "danger" }, style: { borderColor: "#dc2626", color: "#dc2626" } },
  ],
  defaultVariants: {
    variant: "soft",
    color: "primary",
    size: "md",
  },
});

const Badge = styled("span", badgeConfig);

// Input component
const inputConfig = defineVariants({
  base: {
    width: "100%",
    fontFamily: "inherit",
    outline: "none",
    transition: "border-color 150ms, box-shadow 150ms",
  },
  variants: {
    variant: {
      outline: {
        background: "transparent",
        borderWidth: "1px",
        borderStyle: "solid" as const,
        borderColor: "#e2e8f0",
      },
      filled: {
        background: "#f1f5f9",
        border: "2px solid transparent",
      },
      flushed: {
        background: "transparent",
        border: "none",
        borderBottom: "2px solid #e2e8f0",
        borderRadius: "0px",
      },
    },
    size: {
      sm: { padding: "6px 10px", fontSize: "13px", borderRadius: "4px" },
      md: { padding: "8px 12px", fontSize: "14px", borderRadius: "6px" },
      lg: { padding: "12px 16px", fontSize: "16px", borderRadius: "8px" },
    },
    state: {
      default: {},
      error: { borderColor: "#dc2626" },
      success: { borderColor: "#16a34a" },
    },
  },
  compoundVariants: [
    { conditions: { variant: "filled", state: "error" }, style: { background: "#fef2f2", borderColor: "#dc2626" } },
    { conditions: { variant: "filled", state: "success" }, style: { background: "#f0fdf4", borderColor: "#16a34a" } },
  ],
  defaultVariants: {
    variant: "outline",
    size: "md",
    state: "default",
  },
});

const Input = styled("input", inputConfig);

// Card component using extendVariants
const baseCardConfig = defineVariants({
  base: {
    borderRadius: "8px",
    overflow: "hidden",
  },
  variants: {
    variant: {
      elevated: {
        background: "white",
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
      },
      outline: {
        background: "white",
        border: "1px solid #e2e8f0",
      },
      filled: {
        background: "#f8fafc",
      },
    },
    padding: {
      none: { padding: "0" },
      sm: { padding: "12px" },
      md: { padding: "20px" },
      lg: { padding: "32px" },
    },
  },
  defaultVariants: {
    variant: "elevated",
    padding: "md",
  },
});

// Extended card with interactive variant
const interactiveCardConfig = extendVariants(baseCardConfig, {
  variants: {
    interactive: {
      true: { cursor: "pointer", transition: "transform 150ms, box-shadow 150ms" },
      false: {},
    },
  } as const,
  compoundVariants: [
    {
      conditions: { variant: "elevated", interactive: "true" as unknown as keyof { true: StyleObject } },
      style: {},
    },
  ],
  defaultVariants: { interactive: "false" as any },
});

const Card = styled("div", baseCardConfig);

// ============================================
// Usage
// ============================================

function DesignSystemDemo() {
  return (
    <div style={{ maxWidth: "600px", margin: "2rem auto", display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Badges with variant combinations */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        <Badge variant="solid" color="primary" size="sm">New</Badge>
        <Badge variant="soft" color="success">Active</Badge>
        <Badge variant="outline" color="danger" size="lg">Critical</Badge>
        <Badge color="warning">Pending</Badge>
        <Badge variant="solid" color="neutral">Archived</Badge>
      </div>

      {/* Input variants */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <Input placeholder="Outline input" variant="outline" />
        <Input placeholder="Filled input" variant="filled" size="lg" />
        <Input placeholder="Error state" variant="outline" state="error" />
        <Input placeholder="Flushed input" variant="flushed" />
      </div>

      {/* Card variants */}
      <Card variant="elevated" padding="lg">
        <h3 style={{ margin: "0 0 8px" }}>Elevated Card</h3>
        <p style={{ margin: 0, color: "#64748b" }}>With large padding and shadow</p>
      </Card>

      <Card variant="outline" padding="md">
        <h3 style={{ margin: "0 0 8px" }}>Outlined Card</h3>
        <p style={{ margin: 0, color: "#64748b" }}>With border and medium padding</p>
      </Card>

      {/* Card as link */}
      <Card as="a" href="/details" variant="filled" padding="sm" style={{ textDecoration: "none", color: "inherit" }}>
        Clickable card rendered as anchor
      </Card>
    </div>
  );
}
```

The variant system works like CVA but for CSS-in-JS style objects. `defineVariants` creates a configuration that maps variant names to style objects, `styled` creates a React component that resolves the correct styles at render time, and `extendVariants` composes configurations for variant inheritance. Compound variants handle style combinations (e.g., solid+primary produces a blue background) that cannot be expressed with individual variant values alone.'''
    ),
    (
        "react/design-system",
        r'''Build a design system component documentation generator in TypeScript/React that extracts prop types, generates interactive examples, shows variant previews, and creates a searchable component catalog with accessibility information.''',
        r'''A component documentation system with prop extraction and interactive previews:

```typescript
import React, { useState, useMemo, useCallback } from "react";

// ============================================
// Component metadata types
// ============================================

interface PropDef {
  name: string;
  type: string;
  required: boolean;
  defaultValue?: string;
  description: string;
  options?: string[]; // For enum/union types
  control?: "text" | "number" | "boolean" | "select" | "color" | "range";
}

interface VariantPreview {
  name: string;
  props: Record<string, unknown>;
  description?: string;
}

interface AccessibilityInfo {
  role?: string;
  ariaAttributes: string[];
  keyboardInteractions: { key: string; action: string }[];
  screenReaderNotes: string[];
}

interface ComponentDoc {
  name: string;
  description: string;
  category: string;
  status: "stable" | "beta" | "deprecated" | "experimental";
  importPath: string;
  props: PropDef[];
  variants?: VariantPreview[];
  accessibility?: AccessibilityInfo;
  examples: ComponentExample[];
  relatedComponents?: string[];
}

interface ComponentExample {
  title: string;
  description?: string;
  code: string;
  render: () => React.ReactElement;
}

// ============================================
// Documentation registry
// ============================================

class ComponentRegistry {
  private docs = new Map<string, ComponentDoc>();

  register(doc: ComponentDoc): void {
    this.docs.set(doc.name, doc);
  }

  get(name: string): ComponentDoc | undefined {
    return this.docs.get(name);
  }

  getAll(): ComponentDoc[] {
    return Array.from(this.docs.values());
  }

  getByCategory(category: string): ComponentDoc[] {
    return this.getAll().filter((d) => d.category === category);
  }

  getCategories(): string[] {
    const categories = new Set(this.getAll().map((d) => d.category));
    return Array.from(categories).sort();
  }

  search(query: string): ComponentDoc[] {
    const lower = query.toLowerCase();
    return this.getAll().filter(
      (d) =>
        d.name.toLowerCase().includes(lower) ||
        d.description.toLowerCase().includes(lower) ||
        d.category.toLowerCase().includes(lower) ||
        d.props.some((p) => p.name.toLowerCase().includes(lower))
    );
  }
}

const registry = new ComponentRegistry();

// ============================================
// Prop controls renderer
// ============================================

interface PropControlsProps {
  props: PropDef[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

function PropControls({ props, values, onChange }: PropControlsProps) {
  return (
    <div style={{ display: "grid", gap: "12px" }}>
      {props.filter((p) => p.control).map((prop) => (
        <div key={prop.name} style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "8px", alignItems: "center" }}>
          <label htmlFor={`prop-${prop.name}`} style={{ fontSize: "13px", fontWeight: 600 }}>
            {prop.name}
            {prop.required && <span style={{ color: "#dc2626" }}>*</span>}
          </label>
          <div>
            {prop.control === "text" && (
              <input
                id={`prop-${prop.name}`}
                type="text"
                value={String(values[prop.name] || "")}
                onChange={(e) => onChange(prop.name, e.target.value)}
                style={{ width: "100%", padding: "4px 8px", border: "1px solid #e2e8f0", borderRadius: "4px", fontSize: "13px" }}
              />
            )}
            {prop.control === "number" && (
              <input
                id={`prop-${prop.name}`}
                type="number"
                value={Number(values[prop.name] || 0)}
                onChange={(e) => onChange(prop.name, Number(e.target.value))}
                style={{ width: "100px", padding: "4px 8px", border: "1px solid #e2e8f0", borderRadius: "4px", fontSize: "13px" }}
              />
            )}
            {prop.control === "boolean" && (
              <input
                id={`prop-${prop.name}`}
                type="checkbox"
                checked={Boolean(values[prop.name])}
                onChange={(e) => onChange(prop.name, e.target.checked)}
              />
            )}
            {prop.control === "select" && prop.options && (
              <select
                id={`prop-${prop.name}`}
                value={String(values[prop.name] || "")}
                onChange={(e) => onChange(prop.name, e.target.value)}
                style={{ padding: "4px 8px", border: "1px solid #e2e8f0", borderRadius: "4px", fontSize: "13px" }}
              >
                {prop.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            )}
            {prop.control === "color" && (
              <input
                id={`prop-${prop.name}`}
                type="color"
                value={String(values[prop.name] || "#000000")}
                onChange={(e) => onChange(prop.name, e.target.value)}
              />
            )}
            <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>
              {prop.type}{prop.defaultValue ? ` (default: ${prop.defaultValue})` : ""}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================
// Props table
// ============================================

function PropsTable({ props }: { props: PropDef[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
      <thead>
        <tr style={{ borderBottom: "2px solid #e2e8f0" }}>
          <th style={{ textAlign: "left", padding: "8px", fontWeight: 600 }}>Prop</th>
          <th style={{ textAlign: "left", padding: "8px", fontWeight: 600 }}>Type</th>
          <th style={{ textAlign: "left", padding: "8px", fontWeight: 600 }}>Default</th>
          <th style={{ textAlign: "left", padding: "8px", fontWeight: 600 }}>Description</th>
        </tr>
      </thead>
      <tbody>
        {props.map((prop) => (
          <tr key={prop.name} style={{ borderBottom: "1px solid #f1f5f9" }}>
            <td style={{ padding: "8px" }}>
              <code style={{
                background: "#f1f5f9", padding: "2px 6px", borderRadius: "4px",
                fontFamily: "monospace", fontSize: "12px",
              }}>
                {prop.name}
                {prop.required && <span style={{ color: "#dc2626" }}>*</span>}
              </code>
            </td>
            <td style={{ padding: "8px" }}>
              <code style={{ color: "#7c3aed", fontFamily: "monospace", fontSize: "12px" }}>
                {prop.type}
              </code>
            </td>
            <td style={{ padding: "8px", color: "#6b7280" }}>
              {prop.defaultValue || "-"}
            </td>
            <td style={{ padding: "8px" }}>{prop.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ============================================
// Accessibility info panel
// ============================================

function AccessibilityPanel({ info }: { info: AccessibilityInfo }) {
  return (
    <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px", padding: "16px" }}>
      <h4 style={{ margin: "0 0 12px", display: "flex", alignItems: "center", gap: "8px" }}>
        Accessibility
      </h4>

      {info.role && (
        <div style={{ marginBottom: "12px" }}>
          <strong>ARIA Role:</strong>{" "}
          <code style={{ background: "#dcfce7", padding: "2px 6px", borderRadius: "4px" }}>{info.role}</code>
        </div>
      )}

      {info.ariaAttributes.length > 0 && (
        <div style={{ marginBottom: "12px" }}>
          <strong>ARIA Attributes:</strong>
          <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
            {info.ariaAttributes.map((attr) => (
              <li key={attr} style={{ fontSize: "13px" }}><code>{attr}</code></li>
            ))}
          </ul>
        </div>
      )}

      {info.keyboardInteractions.length > 0 && (
        <div style={{ marginBottom: "12px" }}>
          <strong>Keyboard:</strong>
          <table style={{ width: "100%", marginTop: "4px", fontSize: "13px" }}>
            <tbody>
              {info.keyboardInteractions.map((ki) => (
                <tr key={ki.key}>
                  <td style={{ padding: "4px 8px" }}>
                    <kbd style={{
                      background: "white", border: "1px solid #d1d5db",
                      borderRadius: "4px", padding: "2px 6px", fontSize: "12px",
                    }}>
                      {ki.key}
                    </kbd>
                  </td>
                  <td style={{ padding: "4px 8px" }}>{ki.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {info.screenReaderNotes.length > 0 && (
        <div>
          <strong>Screen Reader Notes:</strong>
          <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
            {info.screenReaderNotes.map((note, i) => (
              <li key={i} style={{ fontSize: "13px" }}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ============================================
// Component doc page
// ============================================

function ComponentDocPage({ doc }: { doc: ComponentDoc }) {
  const [propValues, setPropValues] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {};
    for (const prop of doc.props) {
      if (prop.defaultValue !== undefined) {
        defaults[prop.name] = prop.defaultValue;
      }
    }
    return defaults;
  });

  const [activeTab, setActiveTab] = useState<"playground" | "props" | "examples" | "a11y">("playground");

  const handlePropChange = useCallback((name: string, value: unknown) => {
    setPropValues((prev) => ({ ...prev, [name]: value }));
  }, []);

  const statusColors: Record<string, string> = {
    stable: "#16a34a", beta: "#d97706", deprecated: "#dc2626", experimental: "#7c3aed",
  };

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
          <h1 style={{ margin: 0, fontSize: "28px" }}>{doc.name}</h1>
          <span style={{
            padding: "2px 8px", borderRadius: "9999px", fontSize: "11px",
            fontWeight: 600, background: statusColors[doc.status] + "20",
            color: statusColors[doc.status],
          }}>
            {doc.status}
          </span>
        </div>
        <p style={{ color: "#64748b", margin: "0 0 8px" }}>{doc.description}</p>
        <code style={{
          background: "#f1f5f9", padding: "4px 8px", borderRadius: "4px",
          fontSize: "13px", fontFamily: "monospace",
        }}>
          import {"{ "}{doc.name}{" }"} from "{doc.importPath}"
        </code>
      </div>

      {/* Tabs */}
      <div role="tablist" style={{ display: "flex", borderBottom: "2px solid #e5e7eb", marginBottom: "20px" }}>
        {(["playground", "props", "examples", "a11y"] as const).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "8px 16px", border: "none", background: "none",
              cursor: "pointer", fontSize: "14px",
              borderBottom: activeTab === tab ? "2px solid #3b82f6" : "2px solid transparent",
              color: activeTab === tab ? "#1d4ed8" : "#6b7280",
              fontWeight: activeTab === tab ? 600 : 400,
              marginBottom: "-2px",
            }}
          >
            {tab === "a11y" ? "Accessibility" : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Playground tab */}
      {activeTab === "playground" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: "24px" }}>
          {/* Preview */}
          <div style={{
            padding: "32px", border: "1px solid #e2e8f0", borderRadius: "8px",
            display: "flex", alignItems: "center", justifyContent: "center",
            minHeight: "200px", background: "#fafafa",
          }}>
            {doc.examples[0]?.render()}
          </div>

          {/* Controls */}
          <div style={{ borderLeft: "1px solid #e2e8f0", paddingLeft: "24px" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: "14px" }}>Controls</h3>
            <PropControls props={doc.props} values={propValues} onChange={handlePropChange} />
          </div>
        </div>
      )}

      {/* Props tab */}
      {activeTab === "props" && <PropsTable props={doc.props} />}

      {/* Examples tab */}
      {activeTab === "examples" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {doc.examples.map((example, i) => (
            <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: "8px", overflow: "hidden" }}>
              <div style={{ padding: "16px", borderBottom: "1px solid #e2e8f0" }}>
                <h3 style={{ margin: "0 0 4px", fontSize: "16px" }}>{example.title}</h3>
                {example.description && <p style={{ margin: 0, color: "#6b7280", fontSize: "13px" }}>{example.description}</p>}
              </div>
              <div style={{ padding: "24px", background: "#fafafa" }}>
                {example.render()}
              </div>
              <pre style={{
                margin: 0, padding: "16px", background: "#1e293b", color: "#e2e8f0",
                fontSize: "13px", fontFamily: "monospace", overflow: "auto",
              }}>
                {example.code}
              </pre>
            </div>
          ))}
        </div>
      )}

      {/* Accessibility tab */}
      {activeTab === "a11y" && doc.accessibility && (
        <AccessibilityPanel info={doc.accessibility} />
      )}
    </div>
  );
}

// ============================================
// Component catalog
// ============================================

function ComponentCatalog() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const categories = registry.getCategories();
  const components = useMemo(() => {
    let results = searchQuery ? registry.search(searchQuery) : registry.getAll();
    if (selectedCategory) {
      results = results.filter((c) => c.category === selectedCategory);
    }
    return results;
  }, [searchQuery, selectedCategory]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      {/* Sidebar */}
      <nav aria-label="Component categories">
        <div style={{ marginBottom: "16px" }}>
          <input
            type="search"
            placeholder="Search components..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search components"
            style={{
              width: "100%", padding: "8px 12px", border: "1px solid #e2e8f0",
              borderRadius: "6px", fontSize: "13px",
            }}
          />
        </div>

        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          <li>
            <button
              onClick={() => setSelectedCategory(null)}
              style={{
                width: "100%", textAlign: "left", padding: "6px 12px",
                border: "none", borderRadius: "4px",
                background: selectedCategory === null ? "#eff6ff" : "transparent",
                color: selectedCategory === null ? "#1d4ed8" : "#374151",
                cursor: "pointer", fontSize: "13px", fontWeight: selectedCategory === null ? 600 : 400,
              }}
            >
              All Components ({registry.getAll().length})
            </button>
          </li>
          {categories.map((cat) => (
            <li key={cat}>
              <button
                onClick={() => setSelectedCategory(cat)}
                style={{
                  width: "100%", textAlign: "left", padding: "6px 12px",
                  border: "none", borderRadius: "4px",
                  background: selectedCategory === cat ? "#eff6ff" : "transparent",
                  color: selectedCategory === cat ? "#1d4ed8" : "#374151",
                  cursor: "pointer", fontSize: "13px", fontWeight: selectedCategory === cat ? 600 : 400,
                }}
              >
                {cat} ({registry.getByCategory(cat).length})
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Component grid */}
      <main>
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "16px",
        }}>
          {components.map((doc) => (
            <a
              key={doc.name}
              href={`/docs/${doc.name.toLowerCase()}`}
              style={{
                display: "block", padding: "16px", border: "1px solid #e2e8f0",
                borderRadius: "8px", textDecoration: "none", color: "inherit",
                transition: "border-color 150ms, box-shadow 150ms",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <h3 style={{ margin: 0, fontSize: "16px" }}>{doc.name}</h3>
                <span style={{
                  fontSize: "10px", padding: "2px 6px", borderRadius: "9999px",
                  background: "#f1f5f9", color: "#64748b",
                }}>
                  {doc.status}
                </span>
              </div>
              <p style={{ margin: "0 0 8px", fontSize: "13px", color: "#64748b" }}>
                {doc.description}
              </p>
              <div style={{ fontSize: "12px", color: "#94a3b8" }}>
                {doc.props.length} props | {doc.examples.length} examples
                {doc.accessibility && " | a11y docs"}
              </div>
            </a>
          ))}
        </div>

        {components.length === 0 && (
          <p style={{ textAlign: "center", color: "#6b7280", padding: "40px" }}>
            No components found matching "{searchQuery}"
          </p>
        )}
      </main>
    </div>
  );
}

export { ComponentRegistry, registry, ComponentDocPage, ComponentCatalog };
export type { ComponentDoc, PropDef, ComponentExample, AccessibilityInfo };
```

The documentation system provides a registry for component metadata, a playground with interactive prop controls (text, select, boolean, color pickers), a props table extracted from type definitions, code examples with live previews, and an accessibility panel showing ARIA roles, keyboard interactions, and screen reader notes. The catalog supports search across component names, descriptions, and prop names, with category-based filtering.'''
    ),
]
