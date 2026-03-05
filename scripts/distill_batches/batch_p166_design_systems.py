"""Design systems and component libraries."""

PAIRS = [
    (
        "frontend/design-system-tokens",
        "Build a design system foundation with design tokens, component architecture, and a systematic approach to scaling a component library.",
        '''A design system provides a shared language of reusable components and design tokens that ensure consistency across products. The foundation is design tokens (colors, spacing, typography) that feed into components through CSS custom properties.

```typescript
// --- Design tokens as a type-safe system ---

// tokens/colors.ts
export const colors = {
  // Semantic palette
  primary: {
    50:  '#eff6ff',
    100: '#dbeafe',
    200: '#bfdbfe',
    300: '#93c5fd',
    400: '#60a5fa',
    500: '#3b82f6',
    600: '#2563eb',
    700: '#1d4ed8',
    800: '#1e40af',
    900: '#1e3a8a',
  },
  neutral: {
    0:   '#ffffff',
    50:  '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
    1000: '#030712',
  },
  success: { light: '#dcfce7', base: '#22c55e', dark: '#15803d' },
  warning: { light: '#fef9c3', base: '#eab308', dark: '#a16207' },
  danger:  { light: '#fee2e2', base: '#ef4444', dark: '#b91c1c' },
  info:    { light: '#dbeafe', base: '#3b82f6', dark: '#1d4ed8' },
} as const;

// tokens/spacing.ts
export const spacing = {
  0:   '0px',
  px:  '1px',
  0.5: '2px',
  1:   '4px',
  1.5: '6px',
  2:   '8px',
  3:   '12px',
  4:   '16px',
  5:   '20px',
  6:   '24px',
  8:   '32px',
  10:  '40px',
  12:  '48px',
  16:  '64px',
  20:  '80px',
  24:  '96px',
} as const;

// tokens/typography.ts
export const typography = {
  fontFamily: {
    sans:  "'Inter', system-ui, -apple-system, sans-serif",
    mono:  "'JetBrains Mono', 'Fira Code', monospace",
    serif: "'Merriweather', Georgia, serif",
  },
  fontSize: {
    xs:   ['0.75rem',  { lineHeight: '1rem' }],
    sm:   ['0.875rem', { lineHeight: '1.25rem' }],
    base: ['1rem',     { lineHeight: '1.5rem' }],
    lg:   ['1.125rem', { lineHeight: '1.75rem' }],
    xl:   ['1.25rem',  { lineHeight: '1.75rem' }],
    '2xl': ['1.5rem',  { lineHeight: '2rem' }],
    '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
    '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
  },
  fontWeight: {
    regular: '400',
    medium:  '500',
    semibold: '600',
    bold:    '700',
  },
} as const;

// tokens/radii.ts
export const radii = {
  none: '0px',
  sm:   '4px',
  md:   '8px',
  lg:   '12px',
  xl:   '16px',
  '2xl': '24px',
  full: '9999px',
} as const;

// tokens/shadows.ts
export const shadows = {
  sm:  '0 1px 2px 0 rgb(0 0 0 / 0.05)',
  md:  '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  lg:  '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  xl:  '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
  inner: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)',
} as const;
```

```css
/* --- CSS custom properties generated from tokens --- */

:root {
  /* Colors */
  --color-primary-50: #eff6ff;
  --color-primary-100: #dbeafe;
  --color-primary-500: #3b82f6;
  --color-primary-600: #2563eb;
  --color-primary-700: #1d4ed8;

  --color-neutral-0: #ffffff;
  --color-neutral-50: #f9fafb;
  --color-neutral-100: #f3f4f6;
  --color-neutral-200: #e5e7eb;
  --color-neutral-700: #374151;
  --color-neutral-800: #1f2937;
  --color-neutral-900: #111827;

  --color-success: #22c55e;
  --color-warning: #eab308;
  --color-danger: #ef4444;

  /* Semantic aliases */
  --color-text-primary: var(--color-neutral-900);
  --color-text-secondary: var(--color-neutral-600);
  --color-text-muted: var(--color-neutral-400);
  --color-text-inverse: var(--color-neutral-0);

  --color-bg-primary: var(--color-neutral-0);
  --color-bg-secondary: var(--color-neutral-50);
  --color-bg-tertiary: var(--color-neutral-100);
  --color-bg-inverse: var(--color-neutral-900);

  --color-border-default: var(--color-neutral-200);
  --color-border-strong: var(--color-neutral-300);
  --color-border-focus: var(--color-primary-500);

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;

  /* Typography */
  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;

  /* Radii */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);

  /* Motion */
  --duration-fast: 100ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
  --easing-default: cubic-bezier(0.4, 0, 0.2, 1);
  --easing-in: cubic-bezier(0.4, 0, 1, 1);
  --easing-out: cubic-bezier(0, 0, 0.2, 1);

  /* Z-index scale */
  --z-dropdown: 1000;
  --z-sticky: 1100;
  --z-modal-backdrop: 1200;
  --z-modal: 1300;
  --z-popover: 1400;
  --z-tooltip: 1500;
  --z-toast: 1600;
}
```

```typescript
// --- Component architecture pattern ---

import React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

// cva (Class Variance Authority) for variant-based styling
const buttonVariants = cva(
  // Base styles
  [
    'inline-flex items-center justify-center gap-2',
    'font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
    'disabled:pointer-events-none disabled:opacity-50',
  ].join(' '),
  {
    variants: {
      variant: {
        primary:
          'bg-primary-600 text-white hover:bg-primary-700 focus-visible:ring-primary-500',
        secondary:
          'bg-neutral-100 text-neutral-900 hover:bg-neutral-200 focus-visible:ring-neutral-400',
        outline:
          'border border-neutral-300 bg-transparent hover:bg-neutral-50 focus-visible:ring-neutral-400',
        ghost:
          'bg-transparent hover:bg-neutral-100 focus-visible:ring-neutral-400',
        danger:
          'bg-danger text-white hover:bg-red-600 focus-visible:ring-red-500',
        link:
          'text-primary-600 underline-offset-4 hover:underline p-0 h-auto',
      },
      size: {
        sm:  'h-8 px-3 text-sm rounded-md',
        md:  'h-10 px-4 text-sm rounded-lg',
        lg:  'h-12 px-6 text-base rounded-lg',
        xl:  'h-14 px-8 text-lg rounded-xl',
        icon: 'h-10 w-10 rounded-lg',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, leftIcon, rightIcon, children, disabled, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <Spinner className="h-4 w-4 animate-spin" />
        ) : leftIcon ? (
          <span className="shrink-0">{leftIcon}</span>
        ) : null}
        {children}
        {rightIcon && <span className="shrink-0">{rightIcon}</span>}
      </button>
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };


// --- Token-to-CSS pipeline (build step) ---

interface TokenConfig {
  colors: Record<string, Record<string, string> | string>;
  spacing: Record<string, string>;
  radii: Record<string, string>;
}

function generateCSSVariables(tokens: TokenConfig): string {
  const lines: string[] = [':root {'];

  // Flatten nested objects to CSS custom properties
  function flatten(obj: Record<string, unknown>, prefix: string): void {
    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'object' && value !== null) {
        flatten(value as Record<string, unknown>, `${prefix}-${key}`);
      } else {
        lines.push(`  --${prefix}-${key}: ${value};`);
      }
    }
  }

  flatten(tokens.colors, 'color');
  flatten(tokens.spacing, 'space');
  flatten(tokens.radii, 'radius');

  lines.push('}');
  return lines.join('\\n');
}
```

| Layer | Examples | Purpose |
|---|---|---|
| Design Tokens | Colors, spacing, typography, shadows | Single source of truth for design values |
| Primitives | Button, Input, Text, Box, Flex | Unstyled or minimally styled building blocks |
| Components | Card, Dialog, Dropdown, Toast | Composed from primitives + tokens |
| Patterns | LoginForm, DataTable, Navigation | Composed from components for specific use cases |
| Pages / Templates | Dashboard, Settings, Profile | Full page layouts using patterns |

| Token Type | Scope | Examples |
|---|---|---|
| Global tokens | Entire system | `--color-blue-500`, `--space-4` |
| Alias tokens | Semantic meaning | `--color-text-primary`, `--color-bg-surface` |
| Component tokens | Single component | `--button-bg`, `--button-radius` |

Key patterns:
1. Design tokens are the foundation: colors, spacing, typography, shadows, motion
2. CSS custom properties bridge tokens to components with runtime theming support
3. Semantic aliases (`--color-text-primary`) decouple components from specific color values
4. Use `cva` (Class Variance Authority) for type-safe component variants
5. Component API: `variant`, `size`, `disabled`, `loading` are the standard props
6. `forwardRef` + `displayName` for all components (composability + DevTools)
7. Build a token-to-CSS pipeline to generate variables from a single source of truth'''
    ),
    (
        "frontend/storybook-development",
        "Demonstrate Storybook for component development including story writing, controls, documentation, interaction testing, and visual regression.",
        '''Storybook provides an isolated environment for developing, testing, and documenting UI components. It enables component-driven development with live previews, interactive controls, and automated testing.

```typescript
// --- Basic story structure (CSF3 format) ---

// Button.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { Button } from './Button';

// Meta: component-level configuration
const meta = {
  title: 'Components/Button',
  component: Button,
  tags: ['autodocs'],    // auto-generate docs page
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component: 'Primary button component with multiple variants and sizes.',
      },
    },
  },
  // Default args for all stories
  args: {
    children: 'Button',
    onClick: fn(),        // Storybook action (tracks calls)
  },
  // Controls configuration
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'outline', 'ghost', 'danger'],
      description: 'Visual style variant',
      table: {
        type: { summary: 'string' },
        defaultValue: { summary: 'primary' },
      },
    },
    size: {
      control: 'radio',
      options: ['sm', 'md', 'lg', 'xl'],
    },
    disabled: { control: 'boolean' },
    loading: { control: 'boolean' },
    children: { control: 'text' },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;


// --- Individual stories ---

// Default story
export const Default: Story = {};

// Variant stories
export const Primary: Story = {
  args: { variant: 'primary', children: 'Primary Button' },
};

export const Secondary: Story = {
  args: { variant: 'secondary', children: 'Secondary Button' },
};

export const Outline: Story = {
  args: { variant: 'outline', children: 'Outline Button' },
};

export const Danger: Story = {
  args: { variant: 'danger', children: 'Delete Item' },
};

// Size stories
export const Small: Story = {
  args: { size: 'sm', children: 'Small' },
};

export const Large: Story = {
  args: { size: 'lg', children: 'Large Button' },
};

// State stories
export const Loading: Story = {
  args: { loading: true, children: 'Saving...' },
};

export const Disabled: Story = {
  args: { disabled: true, children: 'Disabled' },
};

// With icons
export const WithLeftIcon: Story = {
  args: {
    leftIcon: <PlusIcon className="h-4 w-4" />,
    children: 'Add Item',
  },
};

// All variants showcase
export const AllVariants: Story = {
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {(['primary', 'secondary', 'outline', 'ghost', 'danger'] as const).map(
        variant => (
          <div key={variant} style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {(['sm', 'md', 'lg'] as const).map(size => (
              <Button key={size} variant={variant} size={size}>
                {variant} {size}
              </Button>
            ))}
          </div>
        )
      )}
    </div>
  ),
};
```

```typescript
// --- Interaction testing in Storybook ---

import type { Meta, StoryObj } from '@storybook/react';
import { within, userEvent, expect, fn } from '@storybook/test';
import { LoginForm } from './LoginForm';

const meta = {
  title: 'Forms/LoginForm',
  component: LoginForm,
  args: {
    onSubmit: fn(),
  },
} satisfies Meta<typeof LoginForm>;

export default meta;
type Story = StoryObj<typeof meta>;

// Story with interaction test (play function)
export const FilledForm: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);

    // Type in email field
    const emailInput = canvas.getByLabelText('Email');
    await userEvent.clear(emailInput);
    await userEvent.type(emailInput, 'user@example.com');

    // Type in password field
    const passwordInput = canvas.getByLabelText('Password');
    await userEvent.clear(passwordInput);
    await userEvent.type(passwordInput, 'securePassword123');

    // Click submit
    const submitButton = canvas.getByRole('button', { name: /sign in/i });
    await userEvent.click(submitButton);

    // Assert onSubmit was called with correct data
    await expect(args.onSubmit).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'securePassword123',
    });
  },
};

export const ValidationErrors: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    // Submit empty form
    const submitButton = canvas.getByRole('button', { name: /sign in/i });
    await userEvent.click(submitButton);

    // Assert validation messages
    await expect(
      canvas.getByText('Email is required')
    ).toBeInTheDocument();

    await expect(
      canvas.getByText('Password is required')
    ).toBeInTheDocument();
  },
};

export const InvalidEmail: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await userEvent.type(canvas.getByLabelText('Email'), 'not-an-email');
    await userEvent.type(canvas.getByLabelText('Password'), 'password123');
    await userEvent.click(canvas.getByRole('button', { name: /sign in/i }));

    await expect(
      canvas.getByText('Please enter a valid email')
    ).toBeInTheDocument();
  },
};
```

```typescript
// --- Documentation and composition stories ---

// Card.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { Card, CardHeader, CardBody, CardFooter } from './Card';
import { Button } from '../Button/Button';
import { Badge } from '../Badge/Badge';

const meta = {
  title: 'Components/Card',
  component: Card,
  subcomponents: { CardHeader, CardBody, CardFooter },
  parameters: {
    docs: {
      description: {
        component: `
A flexible card component for displaying content in a contained format.

## Usage
\`\`\`tsx
<Card>
  <CardHeader>Title</CardHeader>
  <CardBody>Content</CardBody>
  <CardFooter>Actions</CardFooter>
</Card>
\`\`\`

## Guidelines
- Use cards to group related information
- Cards can be interactive (clickable) or static
- Keep card content concise and scannable
        `,
      },
    },
  },
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ProductCard: Story = {
  render: () => (
    <Card className="w-[350px]">
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <h3 className="text-lg font-semibold">Pro Plan</h3>
            <p className="text-sm text-neutral-500">For growing teams</p>
          </div>
          <Badge variant="success">Popular</Badge>
        </div>
      </CardHeader>
      <CardBody>
        <div className="text-3xl font-bold">$29<span className="text-sm font-normal text-neutral-500">/mo</span></div>
        <ul className="mt-4 space-y-2">
          <li>Unlimited projects</li>
          <li>Priority support</li>
          <li>Advanced analytics</li>
        </ul>
      </CardBody>
      <CardFooter>
        <Button variant="primary" className="w-full">Get Started</Button>
      </CardFooter>
    </Card>
  ),
};


// --- Storybook configuration ---

// .storybook/main.ts
import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',    // controls, docs, actions, viewport
    '@storybook/addon-a11y',          // accessibility checks
    '@storybook/addon-interactions',  // play function debugger
    '@storybook/addon-coverage',      // test coverage
    '@chromatic-com/storybook',       // visual regression testing
  ],
  framework: '@storybook/react-vite',
  docs: {
    autodocs: 'tag',  // generate docs for stories tagged with 'autodocs'
  },
};

export default config;


// .storybook/preview.ts
import type { Preview } from '@storybook/react';
import '../src/styles/globals.css';

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    viewport: {
      viewports: {
        mobile: { name: 'Mobile', styles: { width: '375px', height: '812px' } },
        tablet: { name: 'Tablet', styles: { width: '768px', height: '1024px' } },
        desktop: { name: 'Desktop', styles: { width: '1440px', height: '900px' } },
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ padding: '1rem' }}>
        <Story />
      </div>
    ),
  ],
};

export default preview;
```

| Storybook Feature | Purpose | Addon |
|---|---|---|
| Controls | Interactive prop editing | `@storybook/addon-essentials` |
| Actions | Track event handler calls | `@storybook/addon-essentials` |
| Docs (autodocs) | Auto-generated documentation | `@storybook/addon-essentials` |
| Viewport | Responsive testing | `@storybook/addon-essentials` |
| A11y | Accessibility auditing | `@storybook/addon-a11y` |
| Interactions | Play function debugging | `@storybook/addon-interactions` |
| Visual regression | Screenshot comparison | Chromatic |
| Test coverage | Code coverage from stories | `@storybook/addon-coverage` |

| Story Type | Purpose | Example |
|---|---|---|
| Default | Component with default props | `export const Default: Story = {}` |
| Variant | Each visual variant | `Primary`, `Secondary`, `Outline` |
| State | Loading, disabled, error | `Loading`, `Disabled`, `WithError` |
| Composition | Component combinations | `ProductCard`, `UserProfile` |
| Interaction | Automated user flows | `FilledForm` with `play` function |
| Responsive | Different viewport sizes | Mobile, tablet, desktop layouts |

Key patterns:
1. Use CSF3 (Component Story Format 3) with `satisfies Meta<typeof Component>`
2. `argTypes` configure controls: `select`, `radio`, `boolean`, `text`, `color`
3. `play` functions automate interactions and assertions directly in stories
4. Tag stories with `autodocs` for automatic documentation generation
5. Use `decorators` for wrapping stories with providers, themes, or layout
6. Group stories by atomic design: `Primitives/`, `Components/`, `Patterns/`, `Pages/`
7. Visual regression testing with Chromatic catches unintended UI changes in CI'''
    ),
    (
        "frontend/accessible-components",
        "Build accessible component patterns including ARIA attributes, keyboard navigation, focus management, and screen reader support.",
        '''Accessible components ensure your application works for everyone, including users of screen readers, keyboard-only navigation, and assistive technologies. These patterns follow WAI-ARIA Authoring Practices.

```typescript
// --- Accessible Dialog (Modal) ---

import { useRef, useEffect, useCallback, useId } from 'react';
import { createPortal } from 'react-dom';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}

function Dialog({ open, onClose, title, description, children }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descId = useId();

  // Trap focus inside the dialog
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
      return;
    }

    if (e.key !== 'Tab') return;

    const focusableElements = dialogRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), ' +
      'input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );

    if (!focusableElements || focusableElements.length === 0) return;

    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, [onClose]);

  useEffect(() => {
    if (open) {
      // Store current focus to restore later
      previousFocus.current = document.activeElement as HTMLElement;

      // Focus the dialog
      requestAnimationFrame(() => {
        const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        firstFocusable?.focus();
      });

      // Add keydown listener
      document.addEventListener('keydown', handleKeyDown);

      // Prevent background scrolling
      document.body.style.overflow = 'hidden';

      return () => {
        document.removeEventListener('keydown', handleKeyDown);
        document.body.style.overflow = '';
        // Restore focus to trigger element
        previousFocus.current?.focus();
      };
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className="dialog-backdrop"
        aria-hidden="true"
        onClick={onClose}
      />
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className="dialog"
      >
        <h2 id={titleId}>{title}</h2>
        {description && <p id={descId}>{description}</p>}
        {children}
        <button
          onClick={onClose}
          aria-label="Close dialog"
          className="dialog-close"
        >
          &times;
        </button>
      </div>
    </>,
    document.body,
  );
}
```

```typescript
// --- Accessible Dropdown Menu ---

import { useState, useRef, useCallback, useId } from 'react';

interface MenuItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
}

function DropdownMenu({
  trigger,
  items,
  label,
}: {
  trigger: React.ReactNode;
  items: MenuItem[];
  label: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const menuRef = useRef<HTMLUListElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const enabledItems = items.filter(item => !item.disabled);

  const handleTriggerKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
      case 'Enter':
      case ' ':
        e.preventDefault();
        setIsOpen(true);
        setActiveIndex(0);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setIsOpen(true);
        setActiveIndex(enabledItems.length - 1);
        break;
    }
  }, [enabledItems.length]);

  const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex(prev =>
          prev < enabledItems.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex(prev =>
          prev > 0 ? prev - 1 : enabledItems.length - 1
        );
        break;
      case 'Home':
        e.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        e.preventDefault();
        setActiveIndex(enabledItems.length - 1);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (activeIndex >= 0) {
          enabledItems[activeIndex].onClick();
          setIsOpen(false);
          triggerRef.current?.focus();
        }
        break;
      case 'Escape':
      case 'Tab':
        setIsOpen(false);
        triggerRef.current?.focus();
        break;
    }
  }, [activeIndex, enabledItems]);

  // Focus active item when index changes
  useEffect(() => {
    if (isOpen && activeIndex >= 0) {
      const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]');
      items?.[activeIndex]?.focus();
    }
  }, [isOpen, activeIndex]);

  return (
    <div className="dropdown" onBlur={handleBlur}>
      <button
        ref={triggerRef}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={menuId}
        onClick={() => setIsOpen(prev => !prev)}
        onKeyDown={handleTriggerKeyDown}
      >
        {trigger}
      </button>

      {isOpen && (
        <ul
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={handleMenuKeyDown}
        >
          {items.map((item, index) => (
            <li
              key={item.id}
              role="menuitem"
              tabIndex={index === activeIndex ? 0 : -1}
              aria-disabled={item.disabled || undefined}
              onClick={() => {
                if (!item.disabled) {
                  item.onClick();
                  setIsOpen(false);
                  triggerRef.current?.focus();
                }
              }}
              className={cn(
                'dropdown-item',
                index === activeIndex && 'active',
                item.disabled && 'disabled',
              )}
            >
              {item.icon && <span aria-hidden="true">{item.icon}</span>}
              {item.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

```typescript
// --- Accessible Tabs ---

function Tabs({
  tabs,
  defaultTab,
}: {
  tabs: Array<{ id: string; label: string; content: React.ReactNode }>;
  defaultTab?: string;
}) {
  const [activeTab, setActiveTab] = useState(defaultTab ?? tabs[0]?.id);
  const tabListRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent, currentIndex: number) => {
    let newIndex: number;

    switch (e.key) {
      case 'ArrowRight':
        e.preventDefault();
        newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
        break;
      case 'ArrowLeft':
        e.preventDefault();
        newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
        break;
      case 'Home':
        e.preventDefault();
        newIndex = 0;
        break;
      case 'End':
        e.preventDefault();
        newIndex = tabs.length - 1;
        break;
      default:
        return;
    }

    setActiveTab(tabs[newIndex].id);
    const tabElements = tabListRef.current?.querySelectorAll<HTMLElement>('[role="tab"]');
    tabElements?.[newIndex]?.focus();
  };

  return (
    <div>
      <div
        ref={tabListRef}
        role="tablist"
        aria-label="Content tabs"
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tabs.map(tab => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`panel-${tab.id}`}
          aria-labelledby={`tab-${tab.id}`}
          tabIndex={0}
          hidden={activeTab !== tab.id}
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}


// --- Live region for dynamic announcements ---

function LiveAnnouncer() {
  const [message, setMessage] = useState('');

  // Call this when you need to announce something to screen readers
  function announce(text: string, priority: 'polite' | 'assertive' = 'polite') {
    // Clear and re-set to trigger announcement
    setMessage('');
    requestAnimationFrame(() => setMessage(text));
  }

  return (
    <>
      {/* Visually hidden but read by screen readers */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {message}
      </div>
    </>
  );
}

// Usage: announce('3 items added to cart')
// Usage: announce('Error: form submission failed', 'assertive')


// --- Skip link for keyboard users ---

function SkipLink() {
  return (
    <a
      href="#main-content"
      className="skip-link"
      /*
        CSS:
        .skip-link {
          position: absolute;
          left: -9999px;
          z-index: 9999;
          padding: 1rem;
          background: white;
        }
        .skip-link:focus {
          left: 1rem;
          top: 1rem;
        }
      */
    >
      Skip to main content
    </a>
  );
}
```

| ARIA Role | Keyboard | Focus Management | Announce |
|---|---|---|---|
| `role="dialog"` + `aria-modal` | Escape to close, Tab trapped | Auto-focus first focusable, restore on close | Title via `aria-labelledby` |
| `role="menu"` + `role="menuitem"` | Arrow keys navigate, Enter selects | Roving tabindex (`tabIndex={0/-1}`) | Item label |
| `role="tablist"` + `role="tab"` | Left/Right arrows switch tabs | Roving tabindex | Tab label + panel content |
| `role="alert"` | N/A | N/A | Immediately announced |
| `role="status"` + `aria-live` | N/A | N/A | Announced at next pause |
| `role="combobox"` | Type to filter, arrows to navigate | Input stays focused | Active option via `aria-activedescendant` |

| Principle | Implementation |
|---|---|
| Perceivable | Alt text on images, color contrast >= 4.5:1, captions on video |
| Operable | All interactive elements keyboard-accessible, no keyboard traps |
| Understandable | Clear labels, consistent navigation, input validation messages |
| Robust | Valid HTML, ARIA used correctly, works with assistive tech |

Key patterns:
1. Focus trapping in modals: Tab cycles within, Escape closes, focus restores on close
2. Roving tabindex for composite widgets: active item `tabIndex={0}`, others `tabIndex={-1}`
3. `aria-live="polite"` for status updates, `"assertive"` for critical alerts
4. Always provide `aria-label` or `aria-labelledby` for interactive elements
5. Skip links: hidden anchor that becomes visible on focus for keyboard users
6. Use semantic HTML first (`<button>`, `<nav>`, `<main>`); ARIA is a supplement, not a replacement
7. Test with screen readers (VoiceOver, NVDA) and keyboard-only navigation'''
    ),
    (
        "frontend/theme-system-custom-properties",
        "Build a theme system using CSS custom properties with light/dark modes, user preference detection, and runtime theme switching.",
        '''A robust theme system uses CSS custom properties as a bridge between design tokens and components, supporting light/dark modes, user preferences, and runtime theme switching.

```css
/* --- Theme token architecture --- */

/* 1. Base layer: raw color values (never used directly by components) */
@layer tokens {
  :root {
    /* Light palette */
    --raw-white: #ffffff;
    --raw-gray-50: #f9fafb;
    --raw-gray-100: #f3f4f6;
    --raw-gray-200: #e5e7eb;
    --raw-gray-300: #d1d5db;
    --raw-gray-400: #9ca3af;
    --raw-gray-500: #6b7280;
    --raw-gray-600: #4b5563;
    --raw-gray-700: #374151;
    --raw-gray-800: #1f2937;
    --raw-gray-900: #111827;
    --raw-gray-950: #030712;

    --raw-blue-50: #eff6ff;
    --raw-blue-100: #dbeafe;
    --raw-blue-500: #3b82f6;
    --raw-blue-600: #2563eb;
    --raw-blue-700: #1d4ed8;

    --raw-red-500: #ef4444;
    --raw-red-600: #dc2626;
    --raw-green-500: #22c55e;
    --raw-green-600: #16a34a;
    --raw-amber-500: #f59e0b;
  }
}


/* 2. Semantic layer: theme-aware aliases */
@layer theme {
  /* Light theme (default) */
  :root,
  [data-theme="light"] {
    color-scheme: light;

    /* Surfaces */
    --surface-primary: var(--raw-white);
    --surface-secondary: var(--raw-gray-50);
    --surface-tertiary: var(--raw-gray-100);
    --surface-elevated: var(--raw-white);
    --surface-overlay: rgb(0 0 0 / 0.5);

    /* Text */
    --text-primary: var(--raw-gray-900);
    --text-secondary: var(--raw-gray-600);
    --text-tertiary: var(--raw-gray-400);
    --text-inverse: var(--raw-white);
    --text-link: var(--raw-blue-600);
    --text-link-hover: var(--raw-blue-700);

    /* Borders */
    --border-default: var(--raw-gray-200);
    --border-strong: var(--raw-gray-300);
    --border-focus: var(--raw-blue-500);

    /* Interactive */
    --interactive-primary: var(--raw-blue-600);
    --interactive-primary-hover: var(--raw-blue-700);
    --interactive-secondary: var(--raw-gray-100);
    --interactive-secondary-hover: var(--raw-gray-200);

    /* Status */
    --status-success: var(--raw-green-600);
    --status-warning: var(--raw-amber-500);
    --status-danger: var(--raw-red-600);

    /* Shadows */
    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  }


  /* Dark theme */
  [data-theme="dark"] {
    color-scheme: dark;

    --surface-primary: var(--raw-gray-900);
    --surface-secondary: var(--raw-gray-800);
    --surface-tertiary: var(--raw-gray-700);
    --surface-elevated: var(--raw-gray-800);
    --surface-overlay: rgb(0 0 0 / 0.7);

    --text-primary: var(--raw-gray-50);
    --text-secondary: var(--raw-gray-400);
    --text-tertiary: var(--raw-gray-500);
    --text-inverse: var(--raw-gray-900);
    --text-link: var(--raw-blue-500);
    --text-link-hover: var(--raw-blue-100);

    --border-default: var(--raw-gray-700);
    --border-strong: var(--raw-gray-600);
    --border-focus: var(--raw-blue-500);

    --interactive-primary: var(--raw-blue-500);
    --interactive-primary-hover: var(--raw-blue-600);
    --interactive-secondary: var(--raw-gray-800);
    --interactive-secondary-hover: var(--raw-gray-700);

    --status-success: var(--raw-green-500);
    --status-warning: var(--raw-amber-500);
    --status-danger: var(--raw-red-500);

    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.3);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.4);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.5);
  }
}


/* 3. Components use ONLY semantic tokens */
@layer components {
  .card {
    background: var(--surface-elevated);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md, 8px);
    box-shadow: var(--shadow-sm);
    color: var(--text-primary);
  }

  .btn-primary {
    background: var(--interactive-primary);
    color: var(--text-inverse);
  }
  .btn-primary:hover {
    background: var(--interactive-primary-hover);
  }
}
```

```typescript
// --- Theme provider with system preference detection ---

import { createContext, useContext, useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';
type ResolvedTheme = 'light' | 'dark';

interface ThemeContextValue {
  theme: Theme;                   // user preference
  resolvedTheme: ResolvedTheme;   // actual applied theme
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = 'app-theme';

function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'system';
    return (localStorage.getItem(STORAGE_KEY) as Theme) ?? 'system';
  });

  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => {
    if (typeof window === 'undefined') return 'light';
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  // Listen for system theme changes
  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      setSystemTheme(e.matches ? 'dark' : 'light');
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  const resolvedTheme: ResolvedTheme = theme === 'system' ? systemTheme : theme;

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(STORAGE_KEY, newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(resolvedTheme === 'light' ? 'dark' : 'light');
  }, [resolvedTheme, setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}


// --- Theme switcher component ---

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <div role="radiogroup" aria-label="Theme selection">
      {(['light', 'dark', 'system'] as const).map(option => (
        <button
          key={option}
          role="radio"
          aria-checked={theme === option}
          onClick={() => setTheme(option)}
          className={`theme-option ${theme === option ? 'active' : ''}`}
        >
          {option === 'light' && <SunIcon />}
          {option === 'dark' && <MoonIcon />}
          {option === 'system' && <MonitorIcon />}
          <span>{option.charAt(0).toUpperCase() + option.slice(1)}</span>
        </button>
      ))}
    </div>
  );
}
```

```typescript
// --- Preventing flash of wrong theme (FOWT) ---

// Inline this script in <head> BEFORE any CSS/JS
// to prevent the flash of the wrong theme on page load

const themeScript = `
(function() {
  var stored = localStorage.getItem('app-theme');
  var theme = stored || 'system';
  var resolved = theme;

  if (theme === 'system') {
    resolved = window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }

  document.documentElement.setAttribute('data-theme', resolved);
  document.documentElement.style.colorScheme = resolved;
})();
`;

// In Next.js layout.tsx:
function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}


// --- Multiple brand themes (white-labeling) ---

/* Brand themes extend the base semantic tokens */
/*
[data-brand="acme"] {
  --interactive-primary: #8b5cf6;
  --interactive-primary-hover: #7c3aed;
  --text-link: #8b5cf6;
  --border-focus: #8b5cf6;
}

[data-brand="globex"] {
  --interactive-primary: #059669;
  --interactive-primary-hover: #047857;
  --text-link: #059669;
  --border-focus: #059669;
}
*/

// Apply brand theme alongside light/dark theme
function setBrand(brand: string): void {
  document.documentElement.setAttribute('data-brand', brand);
}

// Components automatically pick up brand colors through
// the semantic tokens — no component changes needed!
```

| Token Layer | Responsibility | Example |
|---|---|---|
| Raw values | Absolute color/size values | `--raw-blue-500: #3b82f6` |
| Semantic tokens | Theme-aware mappings | `--text-primary: var(--raw-gray-900)` |
| Component tokens | Component-specific overrides | `--btn-radius: var(--radius-md)` |

| Theme Strategy | Flash Prevention | SSR Support | Complexity |
|---|---|---|---|
| CSS `prefers-color-scheme` | Yes (media query) | Yes | Low |
| `data-theme` attribute | Needs inline script | Yes | Medium |
| CSS class (`.dark`) | Needs inline script | Yes | Medium |
| Context + localStorage | Risk of flash | Needs hydration | Medium |
| Inline script + attribute | Best (no flash) | Yes | Low |

Key patterns:
1. Three token layers: raw values -> semantic aliases -> component tokens
2. Components reference ONLY semantic tokens (`--text-primary`, not `--raw-gray-900`)
3. `data-theme` attribute on `<html>` scopes the theme; CSS selectors switch values
4. Inline script in `<head>` prevents flash of wrong theme on page load
5. System preference detection with `matchMedia('(prefers-color-scheme: dark)')`
6. `color-scheme: dark` property tells the browser to style form controls appropriately
7. Brand themes override just the interactive/accent tokens for white-label support'''
    ),

    # --- 5. Compound Components with Variant APIs ---
    (
        "frontend/compound-variant-components",
        "Build a production design system component library using compound components with "
        "slot-based composition, variant APIs powered by class-variance-authority (CVA), "
        "and polymorphic as-prop patterns. Show Button, Dialog, and Menu components with "
        "full TypeScript type safety and accessibility.",
        """\
# Compound Components with Variant APIs

## Component Architecture Patterns

```
Simple props:       <Button variant="primary" size="lg" />
Compound slots:     <Dialog><Dialog.Trigger /><Dialog.Content /></Dialog>
Polymorphic:        <Button as="a" href="/home" />
Headless + styled:  useDialog() hook + CVA styling

Best practice in 2026: combine all four patterns.
Compound components for composition, CVA for variants,
polymorphic for semantic HTML, headless hooks for logic.
```

## CVA: Class Variance Authority for Type-Safe Variants

```typescript
// lib/variants.ts
import { cva, type VariantProps } from "class-variance-authority";
import { twMerge } from "tailwind-merge";
import { clsx, type ClassValue } from "clsx";

// Utility: merge Tailwind classes without conflicts
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Button variants
export const buttonVariants = cva(
  // Base classes applied to ALL variants
  [
    "inline-flex items-center justify-center gap-2",
    "rounded-md font-medium transition-all duration-150",
    "focus-visible:outline-none focus-visible:ring-2",
    "focus-visible:ring-offset-2 focus-visible:ring-ring",
    "disabled:pointer-events-none disabled:opacity-50",
    "active:scale-[0.98]",
  ],
  {
    variants: {
      variant: {
        primary: [
          "bg-primary text-primary-foreground shadow-sm",
          "hover:bg-primary/90",
        ],
        secondary: [
          "bg-secondary text-secondary-foreground",
          "hover:bg-secondary/80",
        ],
        outline: [
          "border border-input bg-background",
          "hover:bg-accent hover:text-accent-foreground",
        ],
        ghost: "hover:bg-accent hover:text-accent-foreground",
        destructive: [
          "bg-destructive text-destructive-foreground shadow-sm",
          "hover:bg-destructive/90",
        ],
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    compoundVariants: [
      // Icon buttons get smaller in sm size
      { variant: "ghost", size: "icon", class: "rounded-full" },
    ],
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export type ButtonVariants = VariantProps<typeof buttonVariants>;
```

## Polymorphic Button Component

```tsx
// components/ui/Button.tsx
import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn, buttonVariants, type ButtonVariants } from "../../lib/variants";

// Polymorphic props: allow rendering as any element
type ButtonProps = ButtonVariants & {
  asChild?: boolean;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>;

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      asChild = false,
      isLoading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "button";

    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        {...props}
      >
        {isLoading ? (
          <svg
            className="h-4 w-4 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle
              cx="12" cy="12" r="10"
              stroke="currentColor" strokeWidth="4"
              className="opacity-25"
            />
            <path
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              className="opacity-75"
            />
          </svg>
        ) : leftIcon}
        {children}
        {!isLoading && rightIcon}
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button };
```

## Compound Dialog Component

```tsx
// components/ui/Dialog.tsx
"use client";
import React, {
  createContext, useContext, useState, useCallback, useRef, useEffect,
} from "react";
import { cn } from "../../lib/variants";

// --- Context ---
interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLButtonElement>;
  contentId: string;
}

const DialogContext = createContext<DialogContextValue | null>(null);

function useDialogContext() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("Dialog compound components must be used within <Dialog>");
  return ctx;
}

// --- Root ---
function Dialog({
  children,
  open: controlledOpen,
  onOpenChange,
  defaultOpen = false,
}: {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultOpen?: boolean;
}) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const open = controlledOpen ?? internalOpen;
  const setOpen = useCallback(
    (next: boolean) => {
      setInternalOpen(next);
      onOpenChange?.(next);
    },
    [onOpenChange]
  );
  const triggerRef = useRef<HTMLButtonElement>(null!);
  const contentId = React.useId();

  return (
    <DialogContext.Provider value={{ open, setOpen, triggerRef, contentId }}>
      {children}
    </DialogContext.Provider>
  );
}

// --- Trigger ---
function DialogTrigger({
  children, className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen, triggerRef, contentId } = useDialogContext();
  return (
    <button
      ref={triggerRef}
      className={className}
      onClick={() => setOpen(true)}
      aria-haspopup="dialog"
      aria-expanded={useDialogContext().open}
      aria-controls={contentId}
      {...props}
    >
      {children}
    </button>
  );
}

// --- Content (Portal + Focus trap) ---
function DialogContent({
  children, className, ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { open, setOpen, triggerRef, contentId } = useDialogContext();
  const contentRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, setOpen, triggerRef]);

  // Focus trap
  useEffect(() => {
    if (!open || !contentRef.current) return;
    const focusable = contentRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length > 0) focusable[0].focus();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 animate-in fade-in"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      {/* Content */}
      <div
        ref={contentRef}
        id={contentId}
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative z-50 w-full max-w-lg rounded-xl bg-background p-6 shadow-xl",
          "animate-in fade-in zoom-in-95",
          className
        )}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}

// --- Close ---
function DialogClose({
  children, className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen, triggerRef } = useDialogContext();
  return (
    <button
      className={className}
      onClick={() => {
        setOpen(false);
        triggerRef.current?.focus();
      }}
      {...props}
    >
      {children}
    </button>
  );
}

// Attach compound components
Dialog.Trigger = DialogTrigger;
Dialog.Content = DialogContent;
Dialog.Close = DialogClose;

export { Dialog };
```

| Pattern | When to Use | Example |
|---|---|---|
| CVA variants | Visual variants of one component | Button, Badge, Alert |
| Compound components | Multi-part UI with shared state | Dialog, Tabs, Menu |
| Polymorphic (asChild) | Render as different HTML element | Button as link |
| Headless hooks | Logic without opinions on styling | useDialog, useCombobox |
| Slot pattern | Merge parent props onto child | Radix Slot, asChild |

Key patterns:
1. CVA centralizes variant logic and produces fully type-safe variant props
2. `cn()` = `twMerge(clsx(...))` resolves Tailwind class conflicts intelligently
3. Compound components use React Context so children share state without prop drilling
4. Focus trap and Escape handling are mandatory for accessible dialogs
5. `asChild` with Radix Slot merges Button styles onto any child element (link, div)
6. `React.useId()` generates stable IDs for aria-controls/aria-labelledby
7. Controlled + uncontrolled pattern: accept optional `open` prop, fall back to internal state"""
    ),
]
