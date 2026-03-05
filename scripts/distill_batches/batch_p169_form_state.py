"""Form management — React Hook Form, Zod, server validation."""

PAIRS = [
    (
        "frontend/react-hook-form-zod",
        "Demonstrate React Hook Form with Zod validation including form setup, nested fields, conditional validation, and error handling.",
        '''React Hook Form provides performant form management with minimal re-renders, and Zod provides type-safe schema validation. Together they create a robust, type-safe form system.

```typescript
// --- Basic form with Zod validation ---

import { useForm, type SubmitHandler } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

// Define validation schema
const signUpSchema = z.object({
  name: z
    .string()
    .min(2, 'Name must be at least 2 characters')
    .max(50, 'Name must be under 50 characters'),
  email: z
    .string()
    .email('Please enter a valid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain an uppercase letter')
    .regex(/[a-z]/, 'Must contain a lowercase letter')
    .regex(/[0-9]/, 'Must contain a number')
    .regex(/[^A-Za-z0-9]/, 'Must contain a special character'),
  confirmPassword: z.string(),
  role: z.enum(['user', 'admin', 'moderator'], {
    errorMap: () => ({ message: 'Please select a role' }),
  }),
  terms: z.literal(true, {
    errorMap: () => ({ message: 'You must accept the terms' }),
  }),
}).refine((data) => data.password === data.confirmPassword, {
  message: 'Passwords do not match',
  path: ['confirmPassword'],
});

// Infer TypeScript type from schema
type SignUpForm = z.infer<typeof signUpSchema>;

function SignUpPage() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid, dirtyFields },
    watch,
    setError,
    reset,
  } = useForm<SignUpForm>({
    resolver: zodResolver(signUpSchema),
    defaultValues: {
      name: '',
      email: '',
      password: '',
      confirmPassword: '',
      role: 'user',
      terms: false as unknown as true,
    },
    mode: 'onBlur',  // validate on blur, re-validate on change
  });

  const onSubmit: SubmitHandler<SignUpForm> = async (data) => {
    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        const errorData = await response.json();

        // Set server-side validation errors
        if (errorData.errors) {
          for (const [field, message] of Object.entries(errorData.errors)) {
            setError(field as keyof SignUpForm, {
              type: 'server',
              message: message as string,
            });
          }
          return;
        }

        throw new Error(errorData.message ?? 'Sign up failed');
      }

      reset();
      // Navigate to success page
    } catch (error) {
      setError('root', {
        type: 'server',
        message: error instanceof Error ? error.message : 'Something went wrong',
      });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      {errors.root && (
        <div role="alert" className="form-error-banner">
          {errors.root.message}
        </div>
      )}

      <FormField label="Name" error={errors.name?.message}>
        <input
          {...register('name')}
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'name-error' : undefined}
        />
      </FormField>

      <FormField label="Email" error={errors.email?.message}>
        <input
          {...register('email')}
          type="email"
          aria-invalid={!!errors.email}
        />
      </FormField>

      <FormField label="Password" error={errors.password?.message}>
        <input {...register('password')} type="password" />
        <PasswordStrength password={watch('password')} />
      </FormField>

      <FormField label="Confirm Password" error={errors.confirmPassword?.message}>
        <input {...register('confirmPassword')} type="password" />
      </FormField>

      <FormField label="Role" error={errors.role?.message}>
        <select {...register('role')}>
          <option value="">Select a role</option>
          <option value="user">User</option>
          <option value="admin">Admin</option>
          <option value="moderator">Moderator</option>
        </select>
      </FormField>

      <label className="checkbox-label">
        <input {...register('terms')} type="checkbox" />
        I accept the terms and conditions
        {errors.terms && <span className="error">{errors.terms.message}</span>}
      </label>

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Creating account...' : 'Sign Up'}
      </button>
    </form>
  );
}


// Reusable FormField component
function FormField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  const id = useId();

  return (
    <div className={`form-field ${error ? 'has-error' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <div className="field-wrapper">
        {React.cloneElement(children as React.ReactElement, { id })}
      </div>
      {error && (
        <p className="field-error" role="alert" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}
```

```typescript
// --- Dynamic and conditional fields ---

import { useForm, useFieldArray, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const orderSchema = z.object({
  customerType: z.enum(['individual', 'business']),
  // Conditional fields based on customerType
  individualName: z.string().optional(),
  companyName: z.string().optional(),
  taxId: z.string().optional(),
  // Dynamic list of order items
  items: z.array(z.object({
    productId: z.string().min(1, 'Select a product'),
    quantity: z.number().min(1, 'Minimum quantity is 1').max(100),
    notes: z.string().max(200).optional(),
  })).min(1, 'Add at least one item'),
  // Conditional discount
  hasDiscount: z.boolean(),
  discountCode: z.string().optional(),
  shippingAddress: z.object({
    street: z.string().min(1, 'Street is required'),
    city: z.string().min(1, 'City is required'),
    state: z.string().min(1, 'State is required'),
    zip: z.string().regex(/^\d{5}(-\d{4})?$/, 'Invalid ZIP code'),
    country: z.string().min(1, 'Country is required'),
  }),
}).superRefine((data, ctx) => {
  // Conditional validation
  if (data.customerType === 'individual' && !data.individualName) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Name is required for individual customers',
      path: ['individualName'],
    });
  }

  if (data.customerType === 'business') {
    if (!data.companyName) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Company name is required',
        path: ['companyName'],
      });
    }
    if (!data.taxId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Tax ID is required for businesses',
        path: ['taxId'],
      });
    }
  }

  if (data.hasDiscount && !data.discountCode) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Enter a discount code',
      path: ['discountCode'],
    });
  }
});

type OrderForm = z.infer<typeof orderSchema>;

function OrderFormPage() {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<OrderForm>({
    resolver: zodResolver(orderSchema),
    defaultValues: {
      customerType: 'individual',
      items: [{ productId: '', quantity: 1, notes: '' }],
      hasDiscount: false,
      shippingAddress: { street: '', city: '', state: '', zip: '', country: 'US' },
    },
  });

  // Dynamic field array
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'items',
  });

  // Watch values for conditional rendering
  const customerType = useWatch({ control, name: 'customerType' });
  const hasDiscount = useWatch({ control, name: 'hasDiscount' });

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      {/* Customer type selection */}
      <fieldset>
        <legend>Customer Type</legend>
        <label>
          <input {...register('customerType')} type="radio" value="individual" />
          Individual
        </label>
        <label>
          <input {...register('customerType')} type="radio" value="business" />
          Business
        </label>
      </fieldset>

      {/* Conditional fields */}
      {customerType === 'individual' && (
        <FormField label="Full Name" error={errors.individualName?.message}>
          <input {...register('individualName')} />
        </FormField>
      )}

      {customerType === 'business' && (
        <>
          <FormField label="Company Name" error={errors.companyName?.message}>
            <input {...register('companyName')} />
          </FormField>
          <FormField label="Tax ID" error={errors.taxId?.message}>
            <input {...register('taxId')} />
          </FormField>
        </>
      )}

      {/* Dynamic item list */}
      <fieldset>
        <legend>Order Items</legend>
        {fields.map((field, index) => (
          <div key={field.id} className="item-row">
            <select {...register(`items.${index}.productId`)}>
              <option value="">Select product</option>
              <option value="prod-1">Widget A</option>
              <option value="prod-2">Widget B</option>
            </select>
            <input
              {...register(`items.${index}.quantity`, { valueAsNumber: true })}
              type="number"
              min={1}
            />
            <input
              {...register(`items.${index}.notes`)}
              placeholder="Notes"
            />
            {fields.length > 1 && (
              <button type="button" onClick={() => remove(index)}>Remove</button>
            )}
            {errors.items?.[index] && (
              <span className="error">
                {errors.items[index]?.productId?.message}
              </span>
            )}
          </div>
        ))}
        <button type="button" onClick={() => append({ productId: '', quantity: 1, notes: '' })}>
          Add Item
        </button>
        {errors.items?.root && (
          <p className="error">{errors.items.root.message}</p>
        )}
      </fieldset>

      {/* Conditional discount */}
      <label>
        <input {...register('hasDiscount')} type="checkbox" />
        I have a discount code
      </label>
      {hasDiscount && (
        <FormField label="Discount Code" error={errors.discountCode?.message}>
          <input {...register('discountCode')} />
        </FormField>
      )}

      <button type="submit">Place Order</button>
    </form>
  );
}
```

```typescript
// --- Reusable form components with Controller ---

import { Controller, type Control, type FieldValues, type Path } from 'react-hook-form';

// Generic controlled input wrapper
function ControlledInput<T extends FieldValues>({
  control,
  name,
  label,
  type = 'text',
  placeholder,
}: {
  control: Control<T>;
  name: Path<T>;
  label: string;
  type?: string;
  placeholder?: string;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState: { error } }) => (
        <div className={`form-field ${error ? 'has-error' : ''}`}>
          <label>{label}</label>
          <input
            {...field}
            type={type}
            placeholder={placeholder}
            aria-invalid={!!error}
          />
          {error && <p className="field-error">{error.message}</p>}
        </div>
      )}
    />
  );
}

// Controlled select with search (e.g., react-select)
function ControlledCombobox<T extends FieldValues>({
  control,
  name,
  label,
  options,
}: {
  control: Control<T>;
  name: Path<T>;
  label: string;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState: { error } }) => (
        <div className={`form-field ${error ? 'has-error' : ''}`}>
          <label>{label}</label>
          <select
            value={field.value}
            onChange={(e) => field.onChange(e.target.value)}
            onBlur={field.onBlur}
            ref={field.ref}
          >
            <option value="">Select...</option>
            {options.map(opt => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {error && <p className="field-error">{error.message}</p>}
        </div>
      )}
    />
  );
}


// --- Password strength indicator ---

function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: '8+ characters', met: password.length >= 8 },
    { label: 'Uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'Lowercase letter', met: /[a-z]/.test(password) },
    { label: 'Number', met: /[0-9]/.test(password) },
    { label: 'Special character', met: /[^A-Za-z0-9]/.test(password) },
  ];

  const strength = checks.filter(c => c.met).length;
  const strengthLabel = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'][strength - 1] ?? '';

  if (!password) return null;

  return (
    <div className="password-strength" aria-label={`Password strength: ${strengthLabel}`}>
      <div className="strength-bar">
        <div
          className={`strength-fill strength-${strength}`}
          style={{ width: `${(strength / 5) * 100}%` }}
        />
      </div>
      <span className="strength-label">{strengthLabel}</span>
      <ul className="strength-checks">
        {checks.map(check => (
          <li key={check.label} className={check.met ? 'met' : ''}>
            {check.met ? '✓' : '○'} {check.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

| Feature | React Hook Form | Formik | Native |
|---|---|---|---|
| Re-renders | Minimal (uncontrolled) | Every keystroke | Every keystroke |
| Validation | Resolver (Zod, Yup) | Yup built-in | Manual |
| Bundle size | ~9 KB | ~15 KB | 0 KB |
| TypeScript | Excellent | Good | Manual |
| Dynamic fields | `useFieldArray` | `<FieldArray>` | Manual |
| Performance | Best (no state per field) | Good | Depends |
| DevTools | RHF DevTools | Formik DevTools | React DevTools |
| Controlled inputs | `Controller` | `<Field>` | Direct |

| Zod Method | Purpose | Example |
|---|---|---|
| `z.string().min(n)` | Min length | `z.string().min(2, 'Too short')` |
| `z.string().email()` | Email format | `z.string().email('Invalid email')` |
| `z.string().regex()` | Pattern match | `z.string().regex(/[A-Z]/, 'Need uppercase')` |
| `z.number().min(n)` | Min value | `z.number().min(1, 'Minimum 1')` |
| `z.enum([...])` | Enum values | `z.enum(['a', 'b', 'c'])` |
| `z.literal(true)` | Exact value | Checkbox must be checked |
| `.refine()` | Custom validation | Cross-field checks |
| `.superRefine()` | Multi-issue validation | Conditional validation |
| `.transform()` | Transform value | `z.string().transform(Number)` |

Key patterns:
1. `zodResolver(schema)` bridges Zod schemas to React Hook Form validation
2. `z.infer<typeof schema>` generates TypeScript types from Zod schemas automatically
3. `useFieldArray` manages dynamic lists with `append`, `remove`, `move`
4. `useWatch` tracks field values for conditional rendering without re-rendering the form
5. `setError` integrates server-side validation errors into the form state
6. `Controller` wraps controlled components (custom selects, date pickers)
7. `mode: 'onBlur'` validates on blur, re-validates on change for optimal UX'''
    ),
    (
        "frontend/multi-step-form-wizard",
        "Build a multi-step form wizard with React Hook Form including step validation, progress tracking, and data persistence across steps.",
        '''A multi-step form wizard breaks complex forms into manageable steps with per-step validation, a progress indicator, and the ability to navigate between steps while preserving data.

```typescript
// --- Multi-step form architecture ---

import { useForm, FormProvider, useFormContext, type SubmitHandler } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useState, useCallback, createContext, useContext } from 'react';

// Step-specific schemas
const personalInfoSchema = z.object({
  firstName: z.string().min(2, 'First name is required'),
  lastName: z.string().min(2, 'Last name is required'),
  email: z.string().email('Valid email is required'),
  phone: z.string().regex(/^\+?[\d\s-()]{10,}$/, 'Valid phone number required'),
});

const addressSchema = z.object({
  street: z.string().min(1, 'Street address is required'),
  apartment: z.string().optional(),
  city: z.string().min(1, 'City is required'),
  state: z.string().min(1, 'State is required'),
  zipCode: z.string().regex(/^\d{5}(-\d{4})?$/, 'Valid ZIP code required'),
  country: z.string().min(1, 'Country is required'),
});

const paymentSchema = z.object({
  cardNumber: z.string().regex(/^\d{16}$/, 'Card number must be 16 digits'),
  expiryMonth: z.string().regex(/^(0[1-9]|1[0-2])$/, 'Valid month required (01-12)'),
  expiryYear: z.string().regex(/^\d{4}$/, 'Valid year required'),
  cvv: z.string().regex(/^\d{3,4}$/, 'CVV must be 3 or 4 digits'),
  cardholderName: z.string().min(2, 'Cardholder name required'),
});

// Combined schema for the entire form
const checkoutSchema = z.object({
  personal: personalInfoSchema,
  address: addressSchema,
  payment: paymentSchema,
});

type CheckoutForm = z.infer<typeof checkoutSchema>;

// Step configuration
interface StepConfig {
  id: string;
  title: string;
  description: string;
  fields: (keyof CheckoutForm)[];
  schema: z.ZodType;
  component: React.ComponentType;
}

const STEPS: StepConfig[] = [
  {
    id: 'personal',
    title: 'Personal Information',
    description: 'Tell us about yourself',
    fields: ['personal'],
    schema: z.object({ personal: personalInfoSchema }),
    component: PersonalInfoStep,
  },
  {
    id: 'address',
    title: 'Shipping Address',
    description: 'Where should we deliver?',
    fields: ['address'],
    schema: z.object({ address: addressSchema }),
    component: AddressStep,
  },
  {
    id: 'payment',
    title: 'Payment',
    description: 'Complete your purchase',
    fields: ['payment'],
    schema: z.object({ payment: paymentSchema }),
    component: PaymentStep,
  },
];
```

```typescript
// --- Wizard container ---

interface WizardContextValue {
  currentStep: number;
  totalSteps: number;
  goToStep: (step: number) => void;
  nextStep: () => Promise<boolean>;
  prevStep: () => void;
  isFirstStep: boolean;
  isLastStep: boolean;
  completedSteps: Set<number>;
}

const WizardContext = createContext<WizardContextValue | null>(null);

function useWizard(): WizardContextValue {
  const ctx = useContext(WizardContext);
  if (!ctx) throw new Error('useWizard must be used within WizardProvider');
  return ctx;
}

function CheckoutWizard() {
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  const methods = useForm<CheckoutForm>({
    resolver: zodResolver(checkoutSchema),
    defaultValues: {
      personal: { firstName: '', lastName: '', email: '', phone: '' },
      address: { street: '', apartment: '', city: '', state: '', zipCode: '', country: 'US' },
      payment: { cardNumber: '', expiryMonth: '', expiryYear: '', cvv: '', cardholderName: '' },
    },
    mode: 'onTouched',
  });

  // Validate current step fields
  const validateCurrentStep = useCallback(async (): Promise<boolean> => {
    const step = STEPS[currentStep];
    const fieldsToValidate = step.fields.flatMap(field => {
      const schema = step.schema;
      // Trigger validation for all fields in this step
      return Object.keys(methods.getValues(field as keyof CheckoutForm) ?? {}).map(
        subField => `${field}.${subField}` as any
      );
    });

    const result = await methods.trigger(fieldsToValidate);
    return result;
  }, [currentStep, methods]);

  const nextStep = useCallback(async (): Promise<boolean> => {
    const isValid = await validateCurrentStep();
    if (isValid) {
      setCompletedSteps(prev => new Set([...prev, currentStep]));
      if (currentStep < STEPS.length - 1) {
        setCurrentStep(prev => prev + 1);
      }
      // Persist to localStorage
      localStorage.setItem('checkout-draft', JSON.stringify(methods.getValues()));
    }
    return isValid;
  }, [currentStep, validateCurrentStep, methods]);

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  }, [currentStep]);

  const goToStep = useCallback((step: number) => {
    // Only allow going to completed steps or the next uncompleted step
    if (step <= currentStep || completedSteps.has(step - 1)) {
      setCurrentStep(step);
    }
  }, [currentStep, completedSteps]);

  const onSubmit: SubmitHandler<CheckoutForm> = async (data) => {
    try {
      const response = await fetch('/api/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!response.ok) throw new Error('Checkout failed');

      localStorage.removeItem('checkout-draft');
      // Navigate to success page
    } catch (error) {
      methods.setError('root', {
        message: error instanceof Error ? error.message : 'Checkout failed',
      });
    }
  };

  const StepComponent = STEPS[currentStep].component;

  return (
    <WizardContext.Provider value={{
      currentStep,
      totalSteps: STEPS.length,
      goToStep,
      nextStep,
      prevStep,
      isFirstStep: currentStep === 0,
      isLastStep: currentStep === STEPS.length - 1,
      completedSteps,
    }}>
      <FormProvider {...methods}>
        <div className="wizard">
          <ProgressBar steps={STEPS} currentStep={currentStep} completedSteps={completedSteps} onStepClick={goToStep} />

          <form onSubmit={methods.handleSubmit(onSubmit)}>
            {methods.formState.errors.root && (
              <div role="alert" className="error-banner">
                {methods.formState.errors.root.message}
              </div>
            )}

            <div className="step-content">
              <h2>{STEPS[currentStep].title}</h2>
              <p className="step-description">{STEPS[currentStep].description}</p>
              <StepComponent />
            </div>

            <WizardNavigation />
          </form>
        </div>
      </FormProvider>
    </WizardContext.Provider>
  );
}
```

```typescript
// --- Step components ---

function PersonalInfoStep() {
  const { register, formState: { errors } } = useFormContext<CheckoutForm>();

  return (
    <div className="step-fields">
      <div className="field-row">
        <FormField label="First Name" error={errors.personal?.firstName?.message}>
          <input {...register('personal.firstName')} />
        </FormField>
        <FormField label="Last Name" error={errors.personal?.lastName?.message}>
          <input {...register('personal.lastName')} />
        </FormField>
      </div>
      <FormField label="Email" error={errors.personal?.email?.message}>
        <input {...register('personal.email')} type="email" />
      </FormField>
      <FormField label="Phone" error={errors.personal?.phone?.message}>
        <input {...register('personal.phone')} type="tel" />
      </FormField>
    </div>
  );
}

function AddressStep() {
  const { register, formState: { errors } } = useFormContext<CheckoutForm>();

  return (
    <div className="step-fields">
      <FormField label="Street Address" error={errors.address?.street?.message}>
        <input {...register('address.street')} />
      </FormField>
      <FormField label="Apartment/Suite (optional)" error={errors.address?.apartment?.message}>
        <input {...register('address.apartment')} />
      </FormField>
      <div className="field-row">
        <FormField label="City" error={errors.address?.city?.message}>
          <input {...register('address.city')} />
        </FormField>
        <FormField label="State" error={errors.address?.state?.message}>
          <input {...register('address.state')} />
        </FormField>
        <FormField label="ZIP Code" error={errors.address?.zipCode?.message}>
          <input {...register('address.zipCode')} />
        </FormField>
      </div>
    </div>
  );
}

function PaymentStep() {
  const { register, formState: { errors } } = useFormContext<CheckoutForm>();

  return (
    <div className="step-fields">
      <FormField label="Card Number" error={errors.payment?.cardNumber?.message}>
        <input {...register('payment.cardNumber')} placeholder="1234 5678 9012 3456" maxLength={16} />
      </FormField>
      <div className="field-row">
        <FormField label="Expiry Month" error={errors.payment?.expiryMonth?.message}>
          <input {...register('payment.expiryMonth')} placeholder="MM" maxLength={2} />
        </FormField>
        <FormField label="Expiry Year" error={errors.payment?.expiryYear?.message}>
          <input {...register('payment.expiryYear')} placeholder="YYYY" maxLength={4} />
        </FormField>
        <FormField label="CVV" error={errors.payment?.cvv?.message}>
          <input {...register('payment.cvv')} type="password" maxLength={4} />
        </FormField>
      </div>
      <FormField label="Cardholder Name" error={errors.payment?.cardholderName?.message}>
        <input {...register('payment.cardholderName')} />
      </FormField>
    </div>
  );
}


// --- Progress bar and navigation ---

function ProgressBar({
  steps,
  currentStep,
  completedSteps,
  onStepClick,
}: {
  steps: StepConfig[];
  currentStep: number;
  completedSteps: Set<number>;
  onStepClick: (step: number) => void;
}) {
  return (
    <nav aria-label="Checkout progress" className="progress-bar">
      <ol>
        {steps.map((step, index) => {
          const isCompleted = completedSteps.has(index);
          const isCurrent = index === currentStep;
          const isClickable = isCompleted || index <= currentStep;

          return (
            <li
              key={step.id}
              className={`progress-step ${isCurrent ? 'current' : ''} ${isCompleted ? 'completed' : ''}`}
              aria-current={isCurrent ? 'step' : undefined}
            >
              <button
                type="button"
                onClick={() => isClickable && onStepClick(index)}
                disabled={!isClickable}
                aria-label={`Step ${index + 1}: ${step.title}${isCompleted ? ' (completed)' : ''}`}
              >
                <span className="step-number">
                  {isCompleted ? '✓' : index + 1}
                </span>
                <span className="step-title">{step.title}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <div
        className="progress-fill"
        style={{ width: `${(currentStep / (steps.length - 1)) * 100}%` }}
        role="progressbar"
        aria-valuenow={currentStep + 1}
        aria-valuemin={1}
        aria-valuemax={steps.length}
      />
    </nav>
  );
}

function WizardNavigation() {
  const { isFirstStep, isLastStep, nextStep, prevStep } = useWizard();
  const { formState: { isSubmitting } } = useFormContext();

  return (
    <div className="wizard-nav">
      {!isFirstStep && (
        <button type="button" onClick={prevStep} className="btn-secondary">
          Back
        </button>
      )}
      {isLastStep ? (
        <button type="submit" disabled={isSubmitting} className="btn-primary">
          {isSubmitting ? 'Processing...' : 'Complete Order'}
        </button>
      ) : (
        <button type="button" onClick={nextStep} className="btn-primary">
          Continue
        </button>
      )}
    </div>
  );
}
```

| Wizard Pattern | Pros | Cons |
|---|---|---|
| Single form, multiple views | Shared validation context, easy submit | Complex conditional validation |
| Separate forms per step | Simple per-step validation | Must manually aggregate data |
| URL-based steps | Bookmarkable, browser back works | Requires routing setup |
| Dialog/modal steps | Focused user attention | Less space for content |

| Feature | Implementation |
|---|---|
| Per-step validation | `methods.trigger(stepFields)` before advancing |
| Data persistence | `localStorage.setItem` on step advance |
| Step navigation | Completed steps are clickable; future steps are disabled |
| Progress indicator | Visual progress bar with step labels |
| Back button | Preserves all form data when going back |
| Submit on last step | `handleSubmit` only fires on the final step |

Key patterns:
1. `FormProvider` shares form context across step components via `useFormContext`
2. Validate only current step fields with `trigger(fieldNames)` before advancing
3. Persist draft to localStorage on each step change for crash recovery
4. `completedSteps` Set tracks which steps passed validation for navigation control
5. Step schemas are subsets of the full schema; full schema validates on final submit
6. Progress bar uses `aria-current="step"` and `role="progressbar"` for accessibility
7. `useWizard` context provides step navigation independent of form state'''
    ),
    (
        "frontend/server-validation-patterns",
        "Demonstrate server-side validation patterns including API validation, error mapping to form fields, and real-time field validation.",
        '''Server-side validation is the last line of defense against invalid data. These patterns show how to validate on the server, map errors to form fields, and provide real-time async validation.

```typescript
// --- Server-side validation with Zod ---

// server/validation/schemas.ts
import { z } from 'zod';

// Reuse the same schema on server and client
export const createUserSchema = z.object({
  email: z
    .string()
    .email('Invalid email format')
    .transform(email => email.toLowerCase().trim()),
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(30, 'Username must be under 30 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Only letters, numbers, hyphens, and underscores'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain an uppercase letter')
    .regex(/[0-9]/, 'Must contain a number'),
  name: z.string().min(1, 'Name is required').max(100),
  bio: z.string().max(500, 'Bio must be under 500 characters').optional(),
});

export type CreateUserInput = z.infer<typeof createUserSchema>;


// server/routes/users.ts
import { Router, type Request, type Response } from 'express';
import { createUserSchema } from '../validation/schemas';
import { db } from '../db';
import { hashPassword } from '../auth';

const router = Router();

interface ValidationErrorResponse {
  error: 'VALIDATION_ERROR';
  message: string;
  fieldErrors: Record<string, string[]>;
}

interface ConflictErrorResponse {
  error: 'CONFLICT';
  message: string;
  field: string;
}

type ErrorResponse = ValidationErrorResponse | ConflictErrorResponse;

router.post('/api/users', async (req: Request, res: Response) => {
  // 1. Parse and validate with Zod
  const result = createUserSchema.safeParse(req.body);

  if (!result.success) {
    // Map Zod errors to field-level errors
    const fieldErrors: Record<string, string[]> = {};

    for (const issue of result.error.issues) {
      const field = issue.path.join('.');
      if (!fieldErrors[field]) fieldErrors[field] = [];
      fieldErrors[field].push(issue.message);
    }

    return res.status(400).json({
      error: 'VALIDATION_ERROR',
      message: 'Please fix the validation errors',
      fieldErrors,
    } satisfies ValidationErrorResponse);
  }

  const data = result.data;

  // 2. Business logic validation (async checks)
  const existingEmail = await db.user.findUnique({
    where: { email: data.email },
  });

  if (existingEmail) {
    return res.status(409).json({
      error: 'CONFLICT',
      message: 'An account with this email already exists',
      field: 'email',
    } satisfies ConflictErrorResponse);
  }

  const existingUsername = await db.user.findUnique({
    where: { username: data.username },
  });

  if (existingUsername) {
    return res.status(409).json({
      error: 'CONFLICT',
      message: 'This username is already taken',
      field: 'username',
    } satisfies ConflictErrorResponse);
  }

  // 3. Create the user
  const user = await db.user.create({
    data: {
      ...data,
      password: await hashPassword(data.password),
    },
  });

  return res.status(201).json({
    id: user.id,
    email: user.email,
    username: user.username,
    name: user.name,
  });
});

export default router;
```

```typescript
// --- Client-side: mapping server errors to form fields ---

import { useForm, type SubmitHandler } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { createUserSchema, type CreateUserInput } from '@/shared/schemas';

function CreateAccountForm() {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<CreateUserInput>({
    resolver: zodResolver(createUserSchema),
    mode: 'onBlur',
  });

  const onSubmit: SubmitHandler<CreateUserInput> = async (data) => {
    try {
      const response = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        const error = await response.json();

        // Map validation errors to form fields
        if (error.error === 'VALIDATION_ERROR') {
          for (const [field, messages] of Object.entries(error.fieldErrors)) {
            setError(field as keyof CreateUserInput, {
              type: 'server',
              message: (messages as string[])[0],
            });
          }
          return;
        }

        // Map conflict errors to the specific field
        if (error.error === 'CONFLICT') {
          setError(error.field as keyof CreateUserInput, {
            type: 'server',
            message: error.message,
          });
          return;
        }

        // Generic error
        setError('root', {
          type: 'server',
          message: error.message ?? 'Something went wrong',
        });
        return;
      }

      // Success — navigate away
    } catch (error) {
      setError('root', {
        type: 'network',
        message: 'Network error. Please check your connection.',
      });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      {errors.root && (
        <div role="alert" className="error-banner">
          {errors.root.message}
        </div>
      )}

      <FormField label="Email" error={errors.email?.message}>
        <input {...register('email')} type="email" autoComplete="email" />
      </FormField>

      <FormField label="Username" error={errors.username?.message}>
        <input {...register('username')} autoComplete="username" />
      </FormField>

      <FormField label="Password" error={errors.password?.message}>
        <input {...register('password')} type="password" autoComplete="new-password" />
      </FormField>

      <FormField label="Name" error={errors.name?.message}>
        <input {...register('name')} autoComplete="name" />
      </FormField>

      <FormField label="Bio (optional)" error={errors.bio?.message}>
        <textarea {...register('bio')} rows={3} />
      </FormField>

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Creating...' : 'Create Account'}
      </button>
    </form>
  );
}
```

```typescript
// --- Real-time async field validation ---

// Validate fields on the server as the user types (debounced)

import { useCallback, useState, useRef, useEffect } from 'react';

// Generic async validation hook
function useAsyncValidation<T>(
  validateFn: (value: T) => Promise<string | null>,
  debounceMs: number = 500,
): {
  validate: (value: T) => void;
  error: string | null;
  isValidating: boolean;
} {
  const [error, setError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();

  const validate = useCallback((value: T) => {
    clearTimeout(timerRef.current);
    abortRef.current?.abort();

    timerRef.current = setTimeout(async () => {
      const controller = new AbortController();
      abortRef.current = controller;

      setIsValidating(true);
      try {
        const result = await validateFn(value);
        if (!controller.signal.aborted) {
          setError(result);
        }
      } catch {
        if (!controller.signal.aborted) {
          setError(null);  // Don\'t show errors for network failures
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsValidating(false);
        }
      }
    }, debounceMs);
  }, [validateFn, debounceMs]);

  useEffect(() => {
    return () => {
      clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, []);

  return { validate, error, isValidating };
}


// Username availability check
function UsernameField() {
  const { register, formState: { errors } } = useFormContext();

  const { validate, error: asyncError, isValidating } = useAsyncValidation(
    async (username: string) => {
      if (username.length < 3) return null;  // Skip if too short

      const response = await fetch(
        `/api/users/check-username?username=${encodeURIComponent(username)}`
      );
      const data = await response.json();

      return data.available ? null : 'This username is already taken';
    },
    500,
  );

  const fieldError = errors.username?.message ?? asyncError;

  return (
    <div className={`form-field ${fieldError ? 'has-error' : ''}`}>
      <label htmlFor="username">Username</label>
      <div className="input-wrapper">
        <input
          {...register('username', {
            onChange: (e) => validate(e.target.value),
          })}
          id="username"
          aria-invalid={!!fieldError}
        />
        {isValidating && <span className="field-spinner" aria-label="Checking availability..." />}
        {!isValidating && !fieldError && (
          <span className="field-check" aria-label="Available">✓</span>
        )}
      </div>
      {fieldError && <p className="field-error" role="alert">{fieldError as string}</p>}
    </div>
  );
}


// --- Server action pattern (Next.js App Router) ---

// app/actions/users.ts
'use server';

import { createUserSchema } from '@/shared/schemas';
import { db } from '@/lib/db';
import { redirect } from 'next/navigation';

interface ActionResult {
  success: boolean;
  errors?: Record<string, string[]>;
  message?: string;
}

export async function createUserAction(
  prevState: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const raw = {
    email: formData.get('email'),
    username: formData.get('username'),
    password: formData.get('password'),
    name: formData.get('name'),
    bio: formData.get('bio') || undefined,
  };

  const result = createUserSchema.safeParse(raw);

  if (!result.success) {
    const errors: Record<string, string[]> = {};
    for (const issue of result.error.issues) {
      const field = issue.path.join('.');
      if (!errors[field]) errors[field] = [];
      errors[field].push(issue.message);
    }
    return { success: false, errors };
  }

  // Check uniqueness
  const existing = await db.user.findFirst({
    where: {
      OR: [
        { email: result.data.email },
        { username: result.data.username },
      ],
    },
  });

  if (existing) {
    const field = existing.email === result.data.email ? 'email' : 'username';
    return {
      success: false,
      errors: { [field]: [`This ${field} is already taken`] },
    };
  }

  await db.user.create({ data: result.data });
  redirect('/welcome');
}
```

| Validation Layer | Purpose | Examples |
|---|---|---|
| HTML attributes | Basic browser validation | `required`, `type="email"`, `minLength` |
| Client-side (Zod) | Instant feedback, UX | Schema validation before submit |
| Async client-side | Uniqueness, availability | Username/email check endpoint |
| Server-side (Zod) | Security, data integrity | Same schema, server-enforced |
| Database constraints | Final safety net | `UNIQUE`, `NOT NULL`, `CHECK` |

| Error Type | HTTP Status | Client Handling |
|---|---|---|
| Validation error | 400 | Map `fieldErrors` to `setError` per field |
| Conflict (duplicate) | 409 | `setError` on the conflicting field |
| Auth error | 401/403 | Redirect to login or show banner |
| Rate limit | 429 | Show "too many attempts" banner |
| Server error | 500 | Show generic error message |

Key patterns:
1. Share Zod schemas between client and server for consistent validation
2. Map server `fieldErrors` to React Hook Form fields via `setError(fieldName, ...)`
3. Debounced async validation (500ms) for uniqueness checks while typing
4. Server validation returns structured errors: `{ error: type, fieldErrors: { field: messages } }`
5. Next.js Server Actions return `ActionResult` with field-level error mapping
6. Always validate on the server even if client validation passes (security)
7. Use `AbortController` to cancel in-flight async validations on new input'''
    ),
    (
        "frontend/file-upload-resumable",
        "Build a file upload system with progress tracking, drag-and-drop, image preview, and resumable uploads using tus protocol.",
        '''A production file upload system needs progress tracking, drag-and-drop, file validation, image previews, and resumable uploads (for large files and unreliable connections).

```typescript
// --- Drag-and-drop file upload component ---

import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from 'react';

interface FileWithPreview {
  file: File;
  id: string;
  preview: string | null;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  error?: string;
}

interface FileUploadProps {
  accept?: string;           // e.g., "image/*,.pdf"
  maxFiles?: number;
  maxSizeBytes?: number;     // per file
  onUploadComplete?: (files: Array<{ id: string; url: string }>) => void;
}

function FileUpload({
  accept = 'image/*,.pdf,.doc,.docx',
  maxFiles = 5,
  maxSizeBytes = 10 * 1024 * 1024,  // 10MB
  onUploadComplete,
}: FileUploadProps) {
  const [files, setFiles] = useState<FileWithPreview[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Validate and add files
  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const fileArray = Array.from(newFiles);
    const validated: FileWithPreview[] = [];

    for (const file of fileArray) {
      // Check max files
      if (files.length + validated.length >= maxFiles) {
        alert(`Maximum ${maxFiles} files allowed`);
        break;
      }

      // Check file size
      if (file.size > maxSizeBytes) {
        alert(`${file.name} is too large. Maximum size is ${formatBytes(maxSizeBytes)}`);
        continue;
      }

      // Check file type
      if (accept && !isFileTypeAccepted(file, accept)) {
        alert(`${file.name} is not an accepted file type`);
        continue;
      }

      // Generate preview for images
      const preview = file.type.startsWith('image/')
        ? URL.createObjectURL(file)
        : null;

      validated.push({
        file,
        id: crypto.randomUUID(),
        preview,
        progress: 0,
        status: 'pending',
      });
    }

    setFiles(prev => [...prev, ...validated]);
  }, [files.length, maxFiles, maxSizeBytes, accept]);

  // Drag handlers
  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addFiles(e.target.files);
      e.target.value = '';  // allow re-selecting same file
    }
  };

  const removeFile = (id: string) => {
    setFiles(prev => {
      const file = prev.find(f => f.id === id);
      if (file?.preview) URL.revokeObjectURL(file.preview);
      return prev.filter(f => f.id !== id);
    });
  };

  // Upload all pending files
  const uploadAll = async () => {
    const pending = files.filter(f => f.status === 'pending');
    const results: Array<{ id: string; url: string }> = [];

    for (const fileEntry of pending) {
      try {
        const url = await uploadFile(fileEntry, (progress) => {
          setFiles(prev => prev.map(f =>
            f.id === fileEntry.id ? { ...f, progress, status: 'uploading' } : f
          ));
        });

        setFiles(prev => prev.map(f =>
          f.id === fileEntry.id ? { ...f, progress: 100, status: 'success' } : f
        ));

        results.push({ id: fileEntry.id, url });
      } catch (error) {
        setFiles(prev => prev.map(f =>
          f.id === fileEntry.id
            ? { ...f, status: 'error', error: error instanceof Error ? error.message : 'Upload failed' }
            : f
        ));
      }
    }

    onUploadComplete?.(results);
  };

  return (
    <div className="file-upload">
      <div
        className={`dropzone ${isDragOver ? 'drag-over' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload files"
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple
          onChange={handleInputChange}
          className="sr-only"
        />
        <p>Drag files here or click to browse</p>
        <p className="hint">Max {maxFiles} files, {formatBytes(maxSizeBytes)} each</p>
      </div>

      {files.length > 0 && (
        <div className="file-list">
          {files.map(f => (
            <FilePreview key={f.id} file={f} onRemove={() => removeFile(f.id)} />
          ))}
          <button onClick={uploadAll} disabled={files.every(f => f.status !== 'pending')}>
            Upload All
          </button>
        </div>
      )}
    </div>
  );
}

function FilePreview({ file, onRemove }: { file: FileWithPreview; onRemove: () => void }) {
  return (
    <div className={`file-preview ${file.status}`}>
      {file.preview ? (
        <img src={file.preview} alt={file.file.name} className="preview-thumb" />
      ) : (
        <div className="preview-icon">{getFileIcon(file.file.type)}</div>
      )}
      <div className="file-info">
        <span className="file-name">{file.file.name}</span>
        <span className="file-size">{formatBytes(file.file.size)}</span>
        {file.status === 'uploading' && (
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${file.progress}%` }} />
          </div>
        )}
        {file.status === 'error' && <span className="error-text">{file.error}</span>}
      </div>
      <button onClick={onRemove} aria-label={`Remove ${file.file.name}`}>
        &times;
      </button>
    </div>
  );
}
```

```typescript
// --- XMLHttpRequest upload with progress ---

async function uploadFile(
  fileEntry: FileWithPreview,
  onProgress: (percent: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', fileEntry.file);
    formData.append('id', fileEntry.id);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        onProgress(percent);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const response = JSON.parse(xhr.responseText);
        resolve(response.url);
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('Authorization', `Bearer ${getAuthToken()}`);
    xhr.send(formData);
  });
}
```

```typescript
// --- Resumable upload with tus protocol ---

// tus is an open protocol for resumable uploads
// If the connection drops, the upload resumes where it left off

import * as tus from 'tus-js-client';

interface ResumableUploadOptions {
  file: File;
  endpoint: string;
  onProgress: (percent: number) => void;
  onSuccess: (url: string) => void;
  onError: (error: Error) => void;
  metadata?: Record<string, string>;
  chunkSize?: number;
}

function createResumableUpload({
  file,
  endpoint,
  onProgress,
  onSuccess,
  onError,
  metadata = {},
  chunkSize = 5 * 1024 * 1024,  // 5MB chunks
}: ResumableUploadOptions): tus.Upload {
  const upload = new tus.Upload(file, {
    endpoint,
    retryDelays: [0, 1000, 3000, 5000, 10000],  // retry with backoff
    chunkSize,
    metadata: {
      filename: file.name,
      filetype: file.type,
      filesize: String(file.size),
      ...metadata,
    },
    // Store upload progress in localStorage for cross-session resume
    storeFingerprintForResuming: true,
    removeFingerprintOnSuccess: true,

    onError(error) {
      console.error('Upload failed:', error);
      onError(error instanceof Error ? error : new Error(String(error)));
    },

    onProgress(bytesUploaded, bytesTotal) {
      const percent = Math.round((bytesUploaded / bytesTotal) * 100);
      onProgress(percent);
    },

    onSuccess() {
      const uploadUrl = upload.url;
      if (uploadUrl) {
        onSuccess(uploadUrl);
      }
    },
  });

  return upload;
}


// React hook for resumable uploads
function useResumableUpload(endpoint: string) {
  const uploadsRef = useRef<Map<string, tus.Upload>>(new Map());
  const [uploadStates, setUploadStates] = useState<
    Map<string, { progress: number; status: string; url?: string; error?: string }>
  >(new Map());

  const startUpload = useCallback((fileId: string, file: File, metadata?: Record<string, string>) => {
    const upload = createResumableUpload({
      file,
      endpoint,
      metadata,
      onProgress: (percent) => {
        setUploadStates(prev => {
          const next = new Map(prev);
          next.set(fileId, { progress: percent, status: 'uploading' });
          return next;
        });
      },
      onSuccess: (url) => {
        setUploadStates(prev => {
          const next = new Map(prev);
          next.set(fileId, { progress: 100, status: 'success', url });
          return next;
        });
        uploadsRef.current.delete(fileId);
      },
      onError: (error) => {
        setUploadStates(prev => {
          const next = new Map(prev);
          next.set(fileId, { progress: 0, status: 'error', error: error.message });
          return next;
        });
      },
    });

    uploadsRef.current.set(fileId, upload);

    // Check for previous upload and resume if found
    upload.findPreviousUploads().then(previousUploads => {
      if (previousUploads.length > 0) {
        upload.resumeFromPreviousUpload(previousUploads[0]);
      }
      upload.start();
    });
  }, [endpoint]);

  const pauseUpload = useCallback((fileId: string) => {
    uploadsRef.current.get(fileId)?.abort();
    setUploadStates(prev => {
      const next = new Map(prev);
      const current = next.get(fileId);
      if (current) {
        next.set(fileId, { ...current, status: 'paused' });
      }
      return next;
    });
  }, []);

  const resumeUpload = useCallback((fileId: string) => {
    uploadsRef.current.get(fileId)?.start();
    setUploadStates(prev => {
      const next = new Map(prev);
      const current = next.get(fileId);
      if (current) {
        next.set(fileId, { ...current, status: 'uploading' });
      }
      return next;
    });
  }, []);

  const cancelUpload = useCallback((fileId: string) => {
    uploadsRef.current.get(fileId)?.abort();
    uploadsRef.current.delete(fileId);
    setUploadStates(prev => {
      const next = new Map(prev);
      next.delete(fileId);
      return next;
    });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      uploadsRef.current.forEach(upload => upload.abort());
    };
  }, []);

  return { startUpload, pauseUpload, resumeUpload, cancelUpload, uploadStates };
}


// Helper functions
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function isFileTypeAccepted(file: File, accept: string): boolean {
  const acceptedTypes = accept.split(',').map(t => t.trim());
  return acceptedTypes.some(type => {
    if (type.startsWith('.')) {
      return file.name.toLowerCase().endsWith(type.toLowerCase());
    }
    if (type.endsWith('/*')) {
      return file.type.startsWith(type.replace('/*', '/'));
    }
    return file.type === type;
  });
}

function getFileIcon(mimeType: string): string {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType === 'application/pdf') return 'pdf';
  if (mimeType.includes('word') || mimeType.includes('document')) return 'doc';
  if (mimeType.includes('sheet') || mimeType.includes('excel')) return 'sheet';
  return 'file';
}
```

| Upload Method | Progress | Resume | Max Size | Complexity |
|---|---|---|---|---|
| `<form>` multipart | No | No | Server limit | Lowest |
| `fetch()` + FormData | No native progress | No | Server limit | Low |
| `XMLHttpRequest` | Yes (`upload.onprogress`) | No | Server limit | Medium |
| tus protocol | Yes | Yes (cross-session) | Unlimited | Medium |
| S3 presigned URL | Yes (XHR) | Via multipart upload | 5 TB | High |
| Chunked upload | Yes | Yes (per chunk) | Unlimited | High |

| Feature | XMLHttpRequest | fetch() | tus |
|---|---|---|---|
| Upload progress | `xhr.upload.onprogress` | No native support | Built-in |
| Download progress | `xhr.onprogress` | `ReadableStream` | N/A |
| Abort | `xhr.abort()` | `AbortController` | `upload.abort()` |
| Retry | Manual | Manual | Built-in backoff |
| Resume | Not possible | Not possible | Automatic |
| Streaming | No | `ReadableStream` | Chunked |

Key patterns:
1. Drag-and-drop: `onDragOver` (prevent default), `onDrop` (read `e.dataTransfer.files`)
2. `URL.createObjectURL(file)` for instant image previews (revoke when done)
3. `XMLHttpRequest.upload.onprogress` for real-time upload progress tracking
4. tus protocol enables resumable uploads that survive connection drops and page reloads
5. Validate file type, size, and count before uploading (both client and server)
6. `storeFingerprintForResuming` in tus stores upload state in localStorage
7. Always clean up: abort uploads on component unmount, revoke object URLs'''
    ),

    # --- 5. Next.js Server Actions with Optimistic Form Updates ---
    (
        "frontend/server-actions-optimistic-forms",
        "Build a production form system using Next.js Server Actions with optimistic updates, "
        "progressive enhancement, Zod validation on both client and server, and useOptimistic "
        "for instant UI feedback. Show a comment system with create, edit, and delete actions "
        "that works without JavaScript enabled.",
        """\
# Next.js Server Actions with Optimistic Form Updates

## Server Actions Overview

```
Traditional form flow:
  Client form -> POST to API route -> parse body -> validate -> DB -> redirect
  Problems: separate API route file, manual fetch, loading state management

Server Actions (Next.js 15+):
  Client form -> action={serverFunction} -> runs on server -> revalidates
  Benefits:
  - No API routes needed; function runs on server directly
  - Progressive enhancement: works without JS (native form submission)
  - Type-safe end-to-end with TypeScript
  - Integrates with useOptimistic for instant UI feedback
  - Automatic revalidation of server components after mutation
```

## Shared Validation Schema

```typescript
// lib/schemas.ts
import { z } from "zod";

export const commentSchema = z.object({
  content: z
    .string()
    .min(1, "Comment cannot be empty")
    .max(2000, "Comment must be under 2000 characters")
    .trim(),
  postId: z.string().uuid(),
  parentId: z.string().uuid().optional(),
});

export const editCommentSchema = z.object({
  commentId: z.string().uuid(),
  content: z
    .string()
    .min(1, "Comment cannot be empty")
    .max(2000, "Comment must be under 2000 characters")
    .trim(),
});

export const deleteCommentSchema = z.object({
  commentId: z.string().uuid(),
});

export type CommentInput = z.infer<typeof commentSchema>;
export type EditCommentInput = z.infer<typeof editCommentSchema>;

// Return type for all form actions
export type ActionResult = {
  success: boolean;
  errors?: Record<string, string[]>;
  message?: string;
};
```

## Server Actions

```typescript
// app/actions/comments.ts
"use server";

import { revalidatePath } from "next/cache";
import { auth } from "@/lib/auth";
import { db } from "@/lib/db";
import {
  commentSchema, editCommentSchema, deleteCommentSchema,
  type ActionResult,
} from "@/lib/schemas";

export async function createComment(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  // 1. Authenticate
  const session = await auth();
  if (!session?.user) {
    return { success: false, message: "You must be signed in" };
  }

  // 2. Validate with Zod
  const parsed = commentSchema.safeParse({
    content: formData.get("content"),
    postId: formData.get("postId"),
    parentId: formData.get("parentId") || undefined,
  });

  if (!parsed.success) {
    return {
      success: false,
      errors: parsed.error.flatten().fieldErrors,
    };
  }

  // 3. Insert into database
  try {
    await db.comment.create({
      data: {
        content: parsed.data.content,
        postId: parsed.data.postId,
        parentId: parsed.data.parentId,
        authorId: session.user.id,
      },
    });
  } catch (error) {
    return { success: false, message: "Failed to create comment" };
  }

  // 4. Revalidate the page to show the new comment
  revalidatePath(`/posts/${parsed.data.postId}`);
  return { success: true, message: "Comment posted" };
}

export async function editComment(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  const session = await auth();
  if (!session?.user)
    return { success: false, message: "Not authenticated" };

  const parsed = editCommentSchema.safeParse({
    commentId: formData.get("commentId"),
    content: formData.get("content"),
  });

  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors };
  }

  // Authorization: only the author can edit
  const existing = await db.comment.findUnique({
    where: { id: parsed.data.commentId },
  });
  if (!existing || existing.authorId !== session.user.id) {
    return { success: false, message: "Not authorized" };
  }

  await db.comment.update({
    where: { id: parsed.data.commentId },
    data: { content: parsed.data.content, editedAt: new Date() },
  });

  revalidatePath(`/posts/${existing.postId}`);
  return { success: true, message: "Comment updated" };
}

export async function deleteComment(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  const session = await auth();
  if (!session?.user)
    return { success: false, message: "Not authenticated" };

  const parsed = deleteCommentSchema.safeParse({
    commentId: formData.get("commentId"),
  });

  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors };
  }

  const existing = await db.comment.findUnique({
    where: { id: parsed.data.commentId },
  });
  if (!existing || existing.authorId !== session.user.id) {
    return { success: false, message: "Not authorized" };
  }

  await db.comment.delete({ where: { id: parsed.data.commentId } });

  revalidatePath(`/posts/${existing.postId}`);
  return { success: true, message: "Comment deleted" };
}
```

## Client Component with useOptimistic

```tsx
// components/CommentSection.tsx
"use client";

import { useOptimistic, useActionState, useRef } from "react";
import { createComment, deleteComment } from "@/app/actions/comments";
import type { ActionResult } from "@/lib/schemas";

interface Comment {
  id: string;
  content: string;
  author: { name: string; avatar: string };
  createdAt: Date;
  editedAt: Date | null;
}

export function CommentSection({
  postId,
  initialComments,
}: {
  postId: string;
  initialComments: Comment[];
}) {
  const formRef = useRef<HTMLFormElement>(null);

  // Optimistic state: show new comments immediately before server confirms
  const [optimisticComments, addOptimistic] = useOptimistic(
    initialComments,
    (
      current: Comment[],
      action: { type: "add"; comment: Comment } | { type: "delete"; id: string }
    ) => {
      switch (action.type) {
        case "add":
          return [action.comment, ...current];
        case "delete":
          return current.filter((c) => c.id !== action.id);
        default:
          return current;
      }
    }
  );

  // Form state via useActionState (progressive enhancement)
  const [createState, createAction, isCreating] = useActionState(
    async (prev: ActionResult | null, formData: FormData) => {
      // Optimistic: add comment to UI immediately
      const content = formData.get("content") as string;
      addOptimistic({
        type: "add",
        comment: {
          id: `optimistic-${Date.now()}`,
          content,
          author: { name: "You", avatar: "" },
          createdAt: new Date(),
          editedAt: null,
        },
      });

      // Actually submit to server
      const result = await createComment(prev, formData);

      if (result.success) {
        formRef.current?.reset();
      }

      return result;
    },
    null
  );

  const handleDelete = async (commentId: string) => {
    // Optimistic removal
    addOptimistic({ type: "delete", id: commentId });

    const formData = new FormData();
    formData.set("commentId", commentId);
    await deleteComment(null, formData);
  };

  return (
    <section className="comment-section">
      {/* Form works without JS via native form submission */}
      <form ref={formRef} action={createAction}>
        <input type="hidden" name="postId" value={postId} />
        <textarea
          name="content"
          placeholder="Write a comment..."
          required
          minLength={1}
          maxLength={2000}
          rows={3}
          className="comment-input"
        />
        {createState?.errors?.content && (
          <p className="error" role="alert">
            {createState.errors.content[0]}
          </p>
        )}
        <button type="submit" disabled={isCreating}>
          {isCreating ? "Posting..." : "Post Comment"}
        </button>
      </form>

      {/* Comment list */}
      <ul className="comment-list">
        {optimisticComments.map((comment) => (
          <li
            key={comment.id}
            className={comment.id.startsWith("optimistic-") ? "opacity-70" : ""}
          >
            <header>
              <strong>{comment.author.name}</strong>
              <time>{comment.createdAt.toLocaleDateString()}</time>
              {comment.editedAt && <span>(edited)</span>}
            </header>
            <p>{comment.content}</p>
            <button
              onClick={() => handleDelete(comment.id)}
              className="delete-btn"
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

| Feature | Server Actions | API Routes | tRPC |
|---|---|---|---|
| Progressive enhancement | Yes (works without JS) | No | No |
| Type safety | Via Zod + TypeScript | Manual | End-to-end |
| Optimistic updates | useOptimistic built-in | Manual | Manual |
| Revalidation | revalidatePath/Tag | Manual cache clear | Manual |
| Bundle size impact | Zero client JS for action | fetch + handler | Client runtime |
| File organization | Colocated with components | Separate /api directory | Separate router |

Key patterns:
1. Server Actions run on the server; `"use server"` directive marks the boundary
2. `useActionState` (React 19) replaces the older `useFormState` with pending support
3. `useOptimistic` shows immediate UI feedback; reverts automatically on server error
4. Zod validation runs on both client (UX) and server (security) with shared schema
5. Forms work without JavaScript via native HTML form submission (progressive enhancement)
6. `revalidatePath` triggers server component re-render after mutation
7. Optimistic items get a temporary ID prefix so they can be styled differently"""
    ),
]
