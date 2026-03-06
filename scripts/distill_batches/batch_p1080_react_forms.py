"""
Batch p1080: TypeScript/React production pairs - React Forms
Topics: React Hook Form, Zod, dynamic fields, file uploads, multi-step forms
"""

PAIRS = [
    ("react/forms_hook_form_zod", r'''Build a production form in React with React Hook Form and Zod validation, including typed form values, custom error messages, conditional fields, and submission handling.''', r'''// components/RegistrationForm.tsx
import { useForm, Controller, SubmitHandler } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// Zod schema with custom validation messages
const registrationSchema = z.object({
  accountType: z.enum(["personal", "business"], {
    errorMap: () => ({ message: "Please select an account type" }),
  }),
  firstName: z
    .string()
    .min(2, "First name must be at least 2 characters")
    .max(50, "First name is too long"),
  lastName: z
    .string()
    .min(2, "Last name must be at least 2 characters")
    .max(50, "Last name is too long"),
  email: z
    .string()
    .email("Please enter a valid email address")
    .toLowerCase(),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain an uppercase letter")
    .regex(/[0-9]/, "Password must contain a number")
    .regex(/[^A-Za-z0-9]/, "Password must contain a special character"),
  confirmPassword: z.string(),
  companyName: z.string().optional(),
  companySize: z.enum(["1-10", "11-50", "51-200", "201+"]).optional(),
  taxId: z.string().optional(),
  acceptTerms: z.literal(true, {
    errorMap: () => ({ message: "You must accept the terms and conditions" }),
  }),
  newsletter: z.boolean().default(false),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords do not match",
  path: ["confirmPassword"],
}).refine(
  (data) => {
    if (data.accountType === "business") {
      return !!data.companyName && data.companyName.length > 0;
    }
    return true;
  },
  {
    message: "Company name is required for business accounts",
    path: ["companyName"],
  }
);

// Infer TypeScript type from Zod schema
type RegistrationFormData = z.infer<typeof registrationSchema>;

// Reusable form field component
function FormField({
  label,
  error,
  children,
  required,
  hint,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
  required?: boolean;
  hint?: string;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="mb-4">
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="mt-1 text-sm text-gray-500">{hint}</p>
      )}
      {error && (
        <p className="mt-1 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function RegistrationForm() {
  const {
    register,
    handleSubmit,
    watch,
    control,
    formState: { errors, isSubmitting, isValid, dirtyFields },
    reset,
    setError,
  } = useForm<RegistrationFormData>({
    resolver: zodResolver(registrationSchema),
    mode: "onBlur", // Validate on blur
    defaultValues: {
      accountType: "personal",
      newsletter: false,
      acceptTerms: false as any,
    },
  });

  const accountType = watch("accountType");
  const password = watch("password");

  // Password strength indicator
  const passwordStrength = getPasswordStrength(password || "");

  const onSubmit: SubmitHandler<RegistrationFormData> = async (data) => {
    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        const error = await response.json();
        if (error.field) {
          setError(error.field as keyof RegistrationFormData, {
            message: error.message,
          });
          return;
        }
        throw new Error(error.message);
      }

      reset();
      // Show success message or redirect
    } catch (error) {
      setError("root", {
        message: error instanceof Error ? error.message : "Registration failed",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-md mx-auto">
      <h2 className="text-2xl font-bold mb-6">Create Account</h2>

      {errors.root && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded" role="alert">
          {errors.root.message}
        </div>
      )}

      {/* Account Type Selection */}
      <FormField label="Account Type" error={errors.accountType?.message} required>
        <div className="flex gap-4">
          {(["personal", "business"] as const).map((type) => (
            <label key={type} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                value={type}
                {...register("accountType")}
                className="text-blue-600"
              />
              <span className="capitalize">{type}</span>
            </label>
          ))}
        </div>
      </FormField>

      {/* Name Fields */}
      <div className="grid grid-cols-2 gap-4">
        <FormField label="First Name" error={errors.firstName?.message} required>
          <input
            id="first-name"
            {...register("firstName")}
            className={`w-full px-3 py-2 border rounded ${
              errors.firstName ? "border-red-500" : "border-gray-300"
            }`}
            aria-invalid={!!errors.firstName}
          />
        </FormField>
        <FormField label="Last Name" error={errors.lastName?.message} required>
          <input
            id="last-name"
            {...register("lastName")}
            className={`w-full px-3 py-2 border rounded ${
              errors.lastName ? "border-red-500" : "border-gray-300"
            }`}
          />
        </FormField>
      </div>

      {/* Email */}
      <FormField label="Email" error={errors.email?.message} required>
        <input
          id="email"
          type="email"
          {...register("email")}
          className="w-full px-3 py-2 border rounded border-gray-300"
        />
      </FormField>

      {/* Password with strength indicator */}
      <FormField
        label="Password"
        error={errors.password?.message}
        required
        hint="8+ characters with uppercase, number, and special character"
      >
        <input
          id="password"
          type="password"
          {...register("password")}
          className="w-full px-3 py-2 border rounded border-gray-300"
        />
        {password && (
          <div className="mt-2">
            <div className="flex gap-1">
              {[1, 2, 3, 4].map((level) => (
                <div
                  key={level}
                  className={`h-1 flex-1 rounded ${
                    passwordStrength >= level
                      ? level <= 1 ? "bg-red-400"
                        : level <= 2 ? "bg-yellow-400"
                        : level <= 3 ? "bg-blue-400"
                        : "bg-green-400"
                      : "bg-gray-200"
                  }`}
                />
              ))}
            </div>
          </div>
        )}
      </FormField>

      {/* Confirm Password */}
      <FormField label="Confirm Password" error={errors.confirmPassword?.message} required>
        <input
          id="confirm-password"
          type="password"
          {...register("confirmPassword")}
          className="w-full px-3 py-2 border rounded border-gray-300"
        />
      </FormField>

      {/* Conditional Business Fields */}
      {accountType === "business" && (
        <div className="p-4 bg-gray-50 rounded-lg mb-4">
          <h3 className="font-medium mb-3">Business Information</h3>
          <FormField label="Company Name" error={errors.companyName?.message} required>
            <input
              id="company-name"
              {...register("companyName")}
              className="w-full px-3 py-2 border rounded border-gray-300"
            />
          </FormField>
          <FormField label="Company Size" error={errors.companySize?.message}>
            <select
              id="company-size"
              {...register("companySize")}
              className="w-full px-3 py-2 border rounded border-gray-300"
            >
              <option value="">Select size</option>
              <option value="1-10">1-10 employees</option>
              <option value="11-50">11-50 employees</option>
              <option value="51-200">51-200 employees</option>
              <option value="201+">201+ employees</option>
            </select>
          </FormField>
          <FormField label="Tax ID" error={errors.taxId?.message}>
            <input
              id="tax-id"
              {...register("taxId")}
              className="w-full px-3 py-2 border rounded border-gray-300"
              placeholder="XX-XXXXXXX"
            />
          </FormField>
        </div>
      )}

      {/* Terms and Newsletter */}
      <div className="space-y-3 mb-6">
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            {...register("acceptTerms")}
            className="mt-1"
          />
          <span className="text-sm">
            I accept the terms and conditions
            {errors.acceptTerms && (
              <span className="block text-red-600" role="alert">
                {errors.acceptTerms.message}
              </span>
            )}
          </span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" {...register("newsletter")} />
          <span className="text-sm">Subscribe to newsletter</span>
        </label>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isSubmitting}
        className={`w-full py-2 px-4 rounded font-medium text-white ${
          isSubmitting ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
        }`}
      >
        {isSubmitting ? "Creating Account..." : "Create Account"}
      </button>
    </form>
  );
}

function getPasswordStrength(password: string): number {
  let strength = 0;
  if (password.length >= 8) strength++;
  if (/[A-Z]/.test(password)) strength++;
  if (/[0-9]/.test(password)) strength++;
  if (/[^A-Za-z0-9]/.test(password)) strength++;
  return strength;
}
'''),

    ("react/forms_dynamic_fields", r'''Build a React form with dynamic field arrays using React Hook Form, supporting add/remove/reorder of repeating field groups with validation on each item.''', r'''// components/InvoiceForm.tsx
import { useForm, useFieldArray, Controller, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// Schema with array validation
const lineItemSchema = z.object({
  description: z.string().min(1, "Description is required"),
  quantity: z.number().min(1, "Minimum quantity is 1").max(9999),
  unitPrice: z.number().min(0.01, "Price must be greater than 0"),
  taxRate: z.number().min(0).max(100).default(0),
});

const invoiceSchema = z.object({
  invoiceNumber: z.string().min(1, "Invoice number is required"),
  clientName: z.string().min(1, "Client name is required"),
  clientEmail: z.string().email("Invalid email"),
  dueDate: z.string().min(1, "Due date is required"),
  notes: z.string().max(500).optional(),
  lineItems: z
    .array(lineItemSchema)
    .min(1, "At least one line item is required")
    .max(50, "Maximum 50 line items"),
});

type InvoiceFormData = z.infer<typeof invoiceSchema>;
type LineItem = z.infer<typeof lineItemSchema>;

// Line item totals watcher
function LineItemTotal({ control, index }: { control: any; index: number }) {
  const quantity = useWatch({ control, name: `lineItems.${index}.quantity` });
  const unitPrice = useWatch({ control, name: `lineItems.${index}.unitPrice` });
  const taxRate = useWatch({ control, name: `lineItems.${index}.taxRate` });

  const subtotal = (quantity || 0) * (unitPrice || 0);
  const tax = subtotal * ((taxRate || 0) / 100);
  const total = subtotal + tax;

  return (
    <div className="text-right">
      <span className="text-sm text-gray-500">
        ${subtotal.toFixed(2)} + ${tax.toFixed(2)} tax
      </span>
      <p className="font-semibold">${total.toFixed(2)}</p>
    </div>
  );
}

// Invoice totals watcher
function InvoiceTotals({ control }: { control: any }) {
  const lineItems = useWatch({ control, name: "lineItems" });

  const { subtotal, totalTax, total } = (lineItems || []).reduce(
    (acc: any, item: LineItem) => {
      const lineSubtotal = (item.quantity || 0) * (item.unitPrice || 0);
      const lineTax = lineSubtotal * ((item.taxRate || 0) / 100);
      return {
        subtotal: acc.subtotal + lineSubtotal,
        totalTax: acc.totalTax + lineTax,
        total: acc.total + lineSubtotal + lineTax,
      };
    },
    { subtotal: 0, totalTax: 0, total: 0 }
  );

  return (
    <div className="border-t pt-4 space-y-2">
      <div className="flex justify-between text-sm">
        <span>Subtotal</span>
        <span>${subtotal.toFixed(2)}</span>
      </div>
      <div className="flex justify-between text-sm text-gray-500">
        <span>Tax</span>
        <span>${totalTax.toFixed(2)}</span>
      </div>
      <div className="flex justify-between text-lg font-bold border-t pt-2">
        <span>Total</span>
        <span>${total.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function InvoiceForm() {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<InvoiceFormData>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {
      invoiceNumber: `INV-${Date.now()}`,
      lineItems: [{ description: "", quantity: 1, unitPrice: 0, taxRate: 0 }],
    },
  });

  const { fields, append, remove, move, insert } = useFieldArray({
    control,
    name: "lineItems",
  });

  const onSubmit = async (data: InvoiceFormData) => {
    console.log("Invoice data:", data);
    // Submit to API
  };

  const handleMoveUp = (index: number) => {
    if (index > 0) move(index, index - 1);
  };

  const handleMoveDown = (index: number) => {
    if (index < fields.length - 1) move(index, index + 1);
  };

  const handleDuplicate = (index: number) => {
    const item = fields[index];
    insert(index + 1, {
      description: item.description || "",
      quantity: item.quantity || 1,
      unitPrice: item.unitPrice || 0,
      taxRate: item.taxRate || 0,
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="max-w-4xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6">Create Invoice</h2>

      {/* Header fields */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div>
          <label className="block text-sm font-medium mb-1">Invoice Number</label>
          <input
            {...register("invoiceNumber")}
            className="w-full px-3 py-2 border rounded"
            readOnly
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Due Date *</label>
          <input
            type="date"
            {...register("dueDate")}
            className="w-full px-3 py-2 border rounded"
          />
          {errors.dueDate && (
            <p className="text-red-600 text-sm mt-1">{errors.dueDate.message}</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Client Name *</label>
          <input
            {...register("clientName")}
            className="w-full px-3 py-2 border rounded"
          />
          {errors.clientName && (
            <p className="text-red-600 text-sm mt-1">{errors.clientName.message}</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Client Email *</label>
          <input
            type="email"
            {...register("clientEmail")}
            className="w-full px-3 py-2 border rounded"
          />
          {errors.clientEmail && (
            <p className="text-red-600 text-sm mt-1">{errors.clientEmail.message}</p>
          )}
        </div>
      </div>

      {/* Line Items */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-lg font-semibold">Line Items</h3>
          <button
            type="button"
            onClick={() => append({ description: "", quantity: 1, unitPrice: 0, taxRate: 0 })}
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            + Add Item
          </button>
        </div>

        {errors.lineItems?.root && (
          <p className="text-red-600 text-sm mb-2" role="alert">
            {errors.lineItems.root.message}
          </p>
        )}

        <div className="space-y-3">
          {fields.map((field, index) => (
            <div
              key={field.id}
              className="grid grid-cols-12 gap-2 items-start p-3 bg-gray-50 rounded"
            >
              {/* Reorder buttons */}
              <div className="col-span-1 flex flex-col gap-1">
                <button
                  type="button"
                  onClick={() => handleMoveUp(index)}
                  disabled={index === 0}
                  className="text-gray-400 hover:text-gray-600 disabled:opacity-30"
                  aria-label="Move up"
                >
                  ^
                </button>
                <button
                  type="button"
                  onClick={() => handleMoveDown(index)}
                  disabled={index === fields.length - 1}
                  className="text-gray-400 hover:text-gray-600 disabled:opacity-30"
                  aria-label="Move down"
                >
                  v
                </button>
              </div>

              {/* Description */}
              <div className="col-span-4">
                <input
                  {...register(`lineItems.${index}.description`)}
                  placeholder="Description"
                  className="w-full px-2 py-1 border rounded text-sm"
                  aria-label={`Item ${index + 1} description`}
                />
                {errors.lineItems?.[index]?.description && (
                  <p className="text-red-600 text-xs mt-1">
                    {errors.lineItems[index]?.description?.message}
                  </p>
                )}
              </div>

              {/* Quantity */}
              <div className="col-span-1">
                <Controller
                  name={`lineItems.${index}.quantity`}
                  control={control}
                  render={({ field }) => (
                    <input
                      type="number"
                      min={1}
                      {...field}
                      onChange={(e) => field.onChange(Number(e.target.value))}
                      className="w-full px-2 py-1 border rounded text-sm"
                      aria-label={`Item ${index + 1} quantity`}
                    />
                  )}
                />
              </div>

              {/* Unit Price */}
              <div className="col-span-2">
                <Controller
                  name={`lineItems.${index}.unitPrice`}
                  control={control}
                  render={({ field }) => (
                    <input
                      type="number"
                      step="0.01"
                      min={0}
                      {...field}
                      onChange={(e) => field.onChange(Number(e.target.value))}
                      className="w-full px-2 py-1 border rounded text-sm"
                      aria-label={`Item ${index + 1} price`}
                    />
                  )}
                />
              </div>

              {/* Tax Rate */}
              <div className="col-span-1">
                <Controller
                  name={`lineItems.${index}.taxRate`}
                  control={control}
                  render={({ field }) => (
                    <input
                      type="number"
                      step="0.1"
                      min={0}
                      max={100}
                      {...field}
                      onChange={(e) => field.onChange(Number(e.target.value))}
                      className="w-full px-2 py-1 border rounded text-sm"
                      aria-label={`Item ${index + 1} tax rate`}
                    />
                  )}
                />
              </div>

              {/* Total */}
              <div className="col-span-2">
                <LineItemTotal control={control} index={index} />
              </div>

              {/* Actions */}
              <div className="col-span-1 flex gap-1">
                <button
                  type="button"
                  onClick={() => handleDuplicate(index)}
                  className="text-gray-400 hover:text-blue-600 text-sm"
                  aria-label={`Duplicate item ${index + 1}`}
                >
                  copy
                </button>
                <button
                  type="button"
                  onClick={() => remove(index)}
                  disabled={fields.length <= 1}
                  className="text-gray-400 hover:text-red-600 text-sm disabled:opacity-30"
                  aria-label={`Remove item ${index + 1}`}
                >
                  x
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Totals */}
      <InvoiceTotals control={control} />

      {/* Notes */}
      <div className="mt-6">
        <label className="block text-sm font-medium mb-1">Notes</label>
        <textarea
          {...register("notes")}
          rows={3}
          className="w-full px-3 py-2 border rounded"
          placeholder="Additional notes..."
        />
      </div>

      {/* Submit */}
      <div className="mt-6 flex gap-3">
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
        >
          {isSubmitting ? "Saving..." : "Create Invoice"}
        </button>
        <button type="button" className="px-6 py-2 border rounded hover:bg-gray-50">
          Save Draft
        </button>
      </div>
    </form>
  );
}
'''),

    ("react/forms_file_upload", r'''<think>
File upload forms need special handling compared to regular form inputs. I initially thought about using a simple input[type=file] with onChange, but wait - that misses drag and drop support, which is the expected UX for modern file uploads. The component needs to handle dragenter, dragover, dragleave, and drop events on a dropzone area.

For preview generation, I could use FileReader.readAsDataURL, but hmm - that creates a base64 data URL which can be very large for high-resolution images. URL.createObjectURL is more efficient since it creates a blob URL that references the file in memory without encoding it. But I need to remember to revoke the object URL on cleanup to avoid memory leaks.

For upload progress, fetch API does not support upload progress tracking (only download progress via ReadableStream). Therefore I need to use XMLHttpRequest, which provides an upload.onprogress event. This is one of the few cases where XHR is still preferable to fetch.
</think>

Build a React file upload component with drag-and-drop, file type/size validation, image preview, upload progress tracking, and retry support for failed uploads.''', r'''<think>
I will create a comprehensive file upload component. For the drag and drop implementation, I need to be careful about the dragenter/dragleave counter trick - browsers fire dragleave when entering a child element, which causes the dropzone highlight to flicker. I considered using pointer-events: none on children, but actually a counter (increment on dragenter, decrement on dragleave, show highlight when counter > 0) is the standard solution.

For file validation, I should validate BEFORE uploading to avoid wasting bandwidth. I initially planned to check only file.type, but wait - file extensions can be spoofed and some browsers report empty MIME types. Checking both the extension and the MIME type gives better coverage, though server-side validation is still essential.

For retry support, each file needs its own upload state (pending, uploading, success, error) so that retrying one file does not re-upload successfully completed files. I will use a Map keyed by a generated file ID to track individual upload states.
</think>

// components/FileUpload.tsx
import React, { useState, useRef, useCallback, useEffect } from "react";

interface UploadedFile {
  id: string;
  file: File;
  preview: string | null;
  progress: number;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
  url?: string;
}

interface FileUploadProps {
  accept?: string;
  maxSize?: number; // bytes
  maxFiles?: number;
  multiple?: boolean;
  uploadUrl: string;
  onUploadComplete?: (files: Array<{ name: string; url: string }>) => void;
  onError?: (error: string) => void;
}

export function FileUpload({
  accept = "image/*,.pdf,.doc,.docx",
  maxSize = 10 * 1024 * 1024, // 10MB
  maxFiles = 5,
  multiple = true,
  uploadUrl,
  onUploadComplete,
  onError,
}: FileUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  // Validate files before adding
  const validateFile = (file: File): string | null => {
    if (file.size > maxSize) {
      return `File too large. Max size is ${formatBytes(maxSize)}`;
    }

    if (accept !== "*") {
      const acceptedTypes = accept.split(",").map((t) => t.trim());
      const fileExt = `.${file.name.split(".").pop()?.toLowerCase()}`;
      const fileType = file.type;

      const isAccepted = acceptedTypes.some((accepted) => {
        if (accepted.startsWith(".")) {
          return fileExt === accepted.toLowerCase();
        }
        if (accepted.endsWith("/*")) {
          return fileType.startsWith(accepted.replace("/*", "/"));
        }
        return fileType === accepted;
      });

      if (!isAccepted) {
        return `File type not allowed. Accepted: ${accept}`;
      }
    }

    return null;
  };

  // Generate preview for image files
  const generatePreview = (file: File): Promise<string | null> => {
    if (!file.type.startsWith("image/")) return Promise.resolve(null);

    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target?.result as string);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  };

  // Add files to the queue
  const addFiles = useCallback(
    async (newFiles: FileList | File[]) => {
      const fileArray = Array.from(newFiles);
      const currentCount = files.length;
      const availableSlots = maxFiles - currentCount;

      if (availableSlots <= 0) {
        onError?.(`Maximum ${maxFiles} files allowed`);
        return;
      }

      const filesToAdd = fileArray.slice(0, availableSlots);
      const uploadFiles: UploadedFile[] = [];

      for (const file of filesToAdd) {
        const error = validateFile(file);
        if (error) {
          onError?.(error);
          continue;
        }

        const preview = await generatePreview(file);
        uploadFiles.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          file,
          preview,
          progress: 0,
          status: "pending",
        });
      }

      setFiles((prev) => [...prev, ...uploadFiles]);
    },
    [files.length, maxFiles, maxSize, accept, onError]
  );

  // Upload a single file
  const uploadFile = useCallback(
    (uploadedFile: UploadedFile) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", uploadedFile.file);

      // Track progress
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 100);
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadedFile.id
                ? { ...f, progress, status: "uploading" as const }
                : f
            )
          );
        }
      });

      // Handle completion
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            setFiles((prev) =>
              prev.map((f) =>
                f.id === uploadedFile.id
                  ? { ...f, progress: 100, status: "success" as const, url: response.url }
                  : f
              )
            );
          } catch {
            setFiles((prev) =>
              prev.map((f) =>
                f.id === uploadedFile.id
                  ? { ...f, progress: 100, status: "success" as const }
                  : f
              )
            );
          }
        } else {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === uploadedFile.id
                ? { ...f, status: "error" as const, error: `Upload failed (${xhr.status})` }
                : f
            )
          );
        }
      });

      xhr.addEventListener("error", () => {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === uploadedFile.id
              ? { ...f, status: "error" as const, error: "Network error" }
              : f
          )
        );
      });

      xhr.open("POST", uploadUrl);
      xhr.send(formData);

      // Update status to uploading
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadedFile.id ? { ...f, status: "uploading" as const } : f
        )
      );
    },
    [uploadUrl]
  );

  // Auto-upload pending files
  useEffect(() => {
    const pendingFiles = files.filter((f) => f.status === "pending");
    for (const file of pendingFiles) {
      uploadFile(file);
    }
  }, [files, uploadFile]);

  // Notify parent when all uploads complete
  useEffect(() => {
    const allDone = files.length > 0 && files.every((f) => f.status === "success" || f.status === "error");
    if (allDone) {
      const successful = files
        .filter((f) => f.status === "success")
        .map((f) => ({ name: f.file.name, url: f.url || "" }));
      if (successful.length > 0) {
        onUploadComplete?.(successful);
      }
    }
  }, [files, onUploadComplete]);

  // Retry a failed upload
  const retryUpload = (fileId: string) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, status: "pending" as const, progress: 0, error: undefined } : f
      )
    );
  };

  // Remove a file
  const removeFile = (fileId: string) => {
    setFiles((prev) => {
      const file = prev.find((f) => f.id === fileId);
      if (file?.preview) {
        URL.revokeObjectURL(file.preview);
      }
      return prev.filter((f) => f.id !== fileId);
    });
  };

  // Drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items.length > 0) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDragOver(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    dragCounter.current = 0;
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        }`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload files by clicking or dragging"
      >
        <div className="text-gray-500">
          <p className="text-lg font-medium">
            {isDragOver ? "Drop files here" : "Drag & drop files here"}
          </p>
          <p className="text-sm mt-1">or click to browse</p>
          <p className="text-xs mt-2">
            Max {formatBytes(maxSize)} per file | Up to {maxFiles} files
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={(e) => e.target.files && addFiles(e.target.files)}
          className="hidden"
          aria-hidden="true"
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file) => (
            <li
              key={file.id}
              className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg"
            >
              {/* Preview */}
              {file.preview ? (
                <img src={file.preview} alt="" className="w-12 h-12 rounded object-cover" />
              ) : (
                <div className="w-12 h-12 rounded bg-gray-200 flex items-center justify-center text-xs text-gray-500">
                  {file.file.name.split(".").pop()?.toUpperCase()}
                </div>
              )}

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{file.file.name}</p>
                <p className="text-xs text-gray-500">{formatBytes(file.file.size)}</p>

                {/* Progress bar */}
                {file.status === "uploading" && (
                  <div className="mt-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${file.progress}%` }}
                    />
                  </div>
                )}

                {/* Error message */}
                {file.status === "error" && (
                  <p className="text-xs text-red-600 mt-1">{file.error}</p>
                )}
              </div>

              {/* Status and actions */}
              <div className="flex items-center gap-2">
                {file.status === "uploading" && (
                  <span className="text-xs text-blue-600">{file.progress}%</span>
                )}
                {file.status === "success" && (
                  <span className="text-green-600 text-sm">Done</span>
                )}
                {file.status === "error" && (
                  <button
                    onClick={() => retryUpload(file.id)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Retry
                  </button>
                )}
                <button
                  onClick={() => removeFile(file.id)}
                  className="text-gray-400 hover:text-red-600"
                  aria-label={`Remove ${file.file.name}`}
                >
                  x
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
'''),

    ("react/forms_multi_step", r'''Build a multi-step form wizard in React with step validation, navigation between steps, progress tracking, data persistence across steps, and review before submission.''', r'''// components/MultiStepForm.tsx
import React, { useState, useCallback, useMemo, createContext, useContext } from "react";

// Form context for sharing state across steps
interface FormWizardContextValue<T> {
  data: Partial<T>;
  updateData: (step: string, values: Partial<T>) => void;
  currentStep: number;
  totalSteps: number;
  goToStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  isFirstStep: boolean;
  isLastStep: boolean;
  stepErrors: Record<string, string[]>;
  setStepErrors: (step: string, errors: string[]) => void;
  completedSteps: Set<number>;
}

const FormWizardContext = createContext<FormWizardContextValue<any>>(null!);

function useFormWizard<T>() {
  return useContext(FormWizardContext) as FormWizardContextValue<T>;
}

// Step definition
interface StepConfig {
  id: string;
  title: string;
  description?: string;
  component: React.ComponentType;
  validate?: (data: any) => string[];
  optional?: boolean;
}

// Wizard component
interface FormWizardProps<T> {
  steps: StepConfig[];
  initialData?: Partial<T>;
  onSubmit: (data: T) => Promise<void>;
  onStepChange?: (step: number, direction: "forward" | "backward") => void;
  persistKey?: string; // localStorage key for persistence
}

function FormWizard<T extends Record<string, any>>({
  steps,
  initialData = {},
  onSubmit,
  onStepChange,
  persistKey,
}: FormWizardProps<T>) {
  // Load persisted data
  const loadPersistedData = (): Partial<T> => {
    if (!persistKey) return {};
    try {
      const saved = localStorage.getItem(persistKey);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  };

  const [data, setData] = useState<Partial<T>>({
    ...loadPersistedData(),
    ...initialData,
  });
  const [currentStep, setCurrentStep] = useState(0);
  const [stepErrors, setStepErrorsState] = useState<Record<string, string[]>>({});
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Persist data on change
  const persistData = useCallback(
    (newData: Partial<T>) => {
      if (persistKey) {
        try {
          localStorage.setItem(persistKey, JSON.stringify(newData));
        } catch {
          // Storage full or unavailable
        }
      }
    },
    [persistKey]
  );

  const updateData = useCallback(
    (step: string, values: Partial<T>) => {
      setData((prev) => {
        const updated = { ...prev, ...values };
        persistData(updated);
        return updated;
      });
    },
    [persistData]
  );

  const setStepErrors = useCallback((step: string, errors: string[]) => {
    setStepErrorsState((prev) => ({ ...prev, [step]: errors }));
  }, []);

  // Validate current step before proceeding
  const validateCurrentStep = useCallback((): boolean => {
    const step = steps[currentStep];
    if (!step.validate) return true;

    const errors = step.validate(data);
    setStepErrors(step.id, errors);
    return errors.length === 0;
  }, [currentStep, steps, data, setStepErrors]);

  const goToStep = useCallback(
    (step: number) => {
      if (step < 0 || step >= steps.length) return;

      // Can always go backward
      if (step < currentStep) {
        onStepChange?.(step, "backward");
        setCurrentStep(step);
        return;
      }

      // Going forward requires validation
      if (validateCurrentStep()) {
        setCompletedSteps((prev) => new Set([...prev, currentStep]));
        onStepChange?.(step, "forward");
        setCurrentStep(step);
      }
    },
    [currentStep, steps.length, validateCurrentStep, onStepChange]
  );

  const nextStep = useCallback(() => goToStep(currentStep + 1), [currentStep, goToStep]);
  const prevStep = useCallback(() => goToStep(currentStep - 1), [currentStep, goToStep]);

  const handleSubmit = useCallback(async () => {
    // Validate all steps before submitting
    let hasErrors = false;
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      if (step.validate) {
        const errors = step.validate(data);
        if (errors.length > 0) {
          setStepErrors(step.id, errors);
          if (!hasErrors) {
            setCurrentStep(i); // Go to first step with errors
            hasErrors = true;
          }
        }
      }
    }

    if (hasErrors) return;

    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit(data as T);
      // Clear persisted data on success
      if (persistKey) localStorage.removeItem(persistKey);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Submission failed");
    } finally {
      setIsSubmitting(false);
    }
  }, [data, steps, onSubmit, persistKey, setStepErrors]);

  const contextValue = useMemo<FormWizardContextValue<T>>(
    () => ({
      data,
      updateData,
      currentStep,
      totalSteps: steps.length,
      goToStep,
      nextStep,
      prevStep,
      isFirstStep: currentStep === 0,
      isLastStep: currentStep === steps.length - 1,
      stepErrors,
      setStepErrors,
      completedSteps,
    }),
    [data, updateData, currentStep, steps.length, goToStep, nextStep, prevStep, stepErrors, setStepErrors, completedSteps]
  );

  const CurrentStepComponent = steps[currentStep].component;

  return (
    <FormWizardContext.Provider value={contextValue}>
      <div className="max-w-2xl mx-auto">
        {/* Progress indicator */}
        <nav aria-label="Form progress" className="mb-8">
          <ol className="flex items-center">
            {steps.map((step, index) => {
              const isActive = index === currentStep;
              const isCompleted = completedSteps.has(index);
              const hasError = stepErrors[step.id]?.length > 0;

              return (
                <li key={step.id} className="flex-1 flex items-center">
                  <button
                    onClick={() => goToStep(index)}
                    disabled={index > currentStep && !isCompleted}
                    className={`flex items-center gap-2 ${
                      isActive
                        ? "text-blue-600 font-medium"
                        : isCompleted
                        ? "text-green-600"
                        : "text-gray-400"
                    }`}
                    aria-current={isActive ? "step" : undefined}
                  >
                    <span
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-sm border-2 ${
                        isActive
                          ? "border-blue-600 bg-blue-600 text-white"
                          : isCompleted
                          ? "border-green-600 bg-green-600 text-white"
                          : hasError
                          ? "border-red-500 bg-red-50 text-red-500"
                          : "border-gray-300"
                      }`}
                    >
                      {isCompleted ? "ok" : index + 1}
                    </span>
                    <span className="text-sm hidden md:inline">{step.title}</span>
                  </button>
                  {index < steps.length - 1 && (
                    <div
                      className={`flex-1 h-0.5 mx-2 ${
                        isCompleted ? "bg-green-600" : "bg-gray-200"
                      }`}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        {/* Step header */}
        <div className="mb-6">
          <h2 className="text-xl font-bold">{steps[currentStep].title}</h2>
          {steps[currentStep].description && (
            <p className="text-gray-500 mt-1">{steps[currentStep].description}</p>
          )}
        </div>

        {/* Step errors */}
        {stepErrors[steps[currentStep].id]?.length > 0 && (
          <div className="mb-4 p-3 bg-red-50 rounded border border-red-200" role="alert">
            <ul className="text-sm text-red-700 space-y-1">
              {stepErrors[steps[currentStep].id].map((error, i) => (
                <li key={i}>{error}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Submit error */}
        {submitError && (
          <div className="mb-4 p-3 bg-red-50 rounded border border-red-200" role="alert">
            <p className="text-red-700">{submitError}</p>
          </div>
        )}

        {/* Step content */}
        <div className="mb-8">
          <CurrentStepComponent />
        </div>

        {/* Navigation buttons */}
        <div className="flex justify-between border-t pt-4">
          <button
            type="button"
            onClick={prevStep}
            disabled={currentStep === 0}
            className="px-4 py-2 border rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Back
          </button>

          {currentStep < steps.length - 1 ? (
            <button
              type="button"
              onClick={nextStep}
              className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Continue
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
            >
              {isSubmitting ? "Submitting..." : "Submit"}
            </button>
          )}
        </div>
      </div>
    </FormWizardContext.Provider>
  );
}

export { FormWizard, useFormWizard };
export type { StepConfig, FormWizardProps };
'''),

    ("react/forms_async_validation", r'''Build async form validation patterns in React with debounced server-side checks, inline validation status indicators, and coordinated multi-field validation with proper UX.''', r'''// hooks/useAsyncValidation.ts
import { useState, useEffect, useRef, useCallback } from "react";

interface AsyncValidationResult {
  isValidating: boolean;
  error: string | null;
  isValid: boolean | null;
}

// Debounced async validator hook
function useAsyncValidation(
  value: string,
  validator: (value: string) => Promise<string | null>,
  options: {
    debounceMs?: number;
    minLength?: number;
    validateOnMount?: boolean;
  } = {}
): AsyncValidationResult {
  const { debounceMs = 500, minLength = 1, validateOnMount = false } = options;
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isValid, setIsValid] = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const initialRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    // Skip initial mount validation unless explicitly requested
    if (initialRef.current && !validateOnMount) {
      initialRef.current = false;
      return;
    }
    initialRef.current = false;

    // Skip validation for short values
    if (value.length < minLength) {
      setError(null);
      setIsValid(null);
      setIsValidating(false);
      return;
    }

    // Cancel previous validation
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsValidating(true);

    const timer = setTimeout(async () => {
      try {
        const result = await validator(value);
        if (!controller.signal.aborted && mountedRef.current) {
          setError(result);
          setIsValid(result === null);
          setIsValidating(false);
        }
      } catch (err) {
        if (!controller.signal.aborted && mountedRef.current) {
          setError("Validation failed");
          setIsValid(false);
          setIsValidating(false);
        }
      }
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value, validator, debounceMs, minLength, validateOnMount]);

  return { isValidating, error, isValid };
}

// Validation status indicator component
function ValidationIndicator({
  isValidating,
  isValid,
  error,
}: AsyncValidationResult) {
  if (isValidating) {
    return (
      <span className="inline-flex items-center text-sm text-gray-400">
        <span className="animate-spin mr-1 h-3 w-3 border-2 border-gray-400 border-t-transparent rounded-full" />
        Checking...
      </span>
    );
  }

  if (isValid === true) {
    return <span className="text-sm text-green-600">Available</span>;
  }

  if (isValid === false && error) {
    return <span className="text-sm text-red-600">{error}</span>;
  }

  return null;
}

// Async validators
const validators = {
  username: async (username: string): Promise<string | null> => {
    const res = await fetch(
      `/api/check-username?username=${encodeURIComponent(username)}`
    );
    const data = await res.json();
    if (!data.available) return "Username is already taken";
    return null;
  },

  email: async (email: string): Promise<string | null> => {
    // Basic format check first (sync)
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return "Invalid email format";
    }
    const res = await fetch(`/api/check-email?email=${encodeURIComponent(email)}`);
    const data = await res.json();
    if (data.exists) return "An account with this email already exists";
    return null;
  },

  domain: async (domain: string): Promise<string | null> => {
    const res = await fetch(`/api/check-domain?domain=${encodeURIComponent(domain)}`);
    const data = await res.json();
    if (!data.available) return "Domain is already registered";
    if (!data.valid) return "Invalid domain name";
    return null;
  },
};

// Multi-field coordinated validation
interface MultiFieldValidation<T extends Record<string, string>> {
  values: T;
  errors: Partial<Record<keyof T, string>>;
  isValidating: Partial<Record<keyof T, boolean>>;
  isAllValid: boolean;
  isAnyValidating: boolean;
}

function useMultiFieldValidation<T extends Record<string, string>>(
  values: T,
  fieldValidators: Partial<Record<keyof T, (value: string) => Promise<string | null>>>,
  options?: { debounceMs?: number }
): MultiFieldValidation<T> {
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
  const [validating, setValidating] = useState<Partial<Record<keyof T, boolean>>>({});
  const abortControllers = useRef<Map<string, AbortController>>(new Map());

  useEffect(() => {
    return () => {
      for (const controller of abortControllers.current.values()) {
        controller.abort();
      }
    };
  }, []);

  useEffect(() => {
    for (const [field, validator] of Object.entries(fieldValidators) as Array<
      [keyof T & string, (value: string) => Promise<string | null>]
    >) {
      const value = values[field];
      if (!value) continue;

      // Cancel previous validation for this field
      abortControllers.current.get(field)?.abort();
      const controller = new AbortController();
      abortControllers.current.set(field, controller);

      setValidating((prev) => ({ ...prev, [field]: true }));

      const timer = setTimeout(async () => {
        try {
          const error = await validator(value);
          if (!controller.signal.aborted) {
            setErrors((prev) => {
              const next = { ...prev };
              if (error) {
                next[field] = error;
              } else {
                delete next[field];
              }
              return next;
            });
            setValidating((prev) => ({ ...prev, [field]: false }));
          }
        } catch {
          if (!controller.signal.aborted) {
            setValidating((prev) => ({ ...prev, [field]: false }));
          }
        }
      }, options?.debounceMs ?? 500);

      return () => clearTimeout(timer);
    }
  }, [values, fieldValidators, options?.debounceMs]);

  const isAnyValidating = Object.values(validating).some(Boolean);
  const isAllValid =
    !isAnyValidating &&
    Object.keys(fieldValidators).every((field) => !errors[field as keyof T]);

  return { values, errors, isValidating: validating, isAllValid, isAnyValidating };
}

// Usage example: Registration form with async validation
function RegistrationFormWithAsync() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");

  const usernameValidation = useAsyncValidation(username, validators.username, {
    debounceMs: 300,
    minLength: 3,
  });

  const emailValidation = useAsyncValidation(email, validators.email, {
    debounceMs: 500,
    minLength: 5,
  });

  const canSubmit =
    usernameValidation.isValid === true &&
    emailValidation.isValid === true &&
    !usernameValidation.isValidating &&
    !emailValidation.isValidating;

  return (
    <form className="max-w-md mx-auto space-y-4">
      <div>
        <label htmlFor="username" className="block text-sm font-medium mb-1">
          Username
        </label>
        <div className="relative">
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={`w-full px-3 py-2 border rounded pr-24 ${
              usernameValidation.isValid === false
                ? "border-red-300"
                : usernameValidation.isValid === true
                ? "border-green-300"
                : "border-gray-300"
            }`}
            aria-describedby="username-status"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2" id="username-status">
            <ValidationIndicator {...usernameValidation} />
          </div>
        </div>
      </div>

      <div>
        <label htmlFor="email" className="block text-sm font-medium mb-1">
          Email
        </label>
        <div className="relative">
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`w-full px-3 py-2 border rounded pr-24 ${
              emailValidation.isValid === false
                ? "border-red-300"
                : emailValidation.isValid === true
                ? "border-green-300"
                : "border-gray-300"
            }`}
            aria-describedby="email-status"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2" id="email-status">
            <ValidationIndicator {...emailValidation} />
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full py-2 bg-blue-600 text-white rounded disabled:bg-gray-400"
      >
        Register
      </button>
    </form>
  );
}

export {
  useAsyncValidation,
  useMultiFieldValidation,
  ValidationIndicator,
  validators,
  RegistrationFormWithAsync,
};
'''),
]
