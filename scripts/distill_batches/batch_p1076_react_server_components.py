"""
Batch p1076: TypeScript/React production pairs - React Server Components
Topics: server vs client components, data fetching, streaming, suspense, form actions
"""

PAIRS = [
    ("react/rsc_data_fetching", r'''Build a React Server Component architecture for a dashboard page that fetches data from multiple APIs in parallel, with proper loading states using Suspense boundaries and error handling.''', r'''// app/dashboard/page.tsx - Server Component with parallel data fetching
import { Suspense } from "react";
import { ErrorBoundary } from "./error-boundary";

// These functions run on the server only - no client bundle impact
async function getMetrics(): Promise<DashboardMetrics> {
  const res = await fetch(`${process.env.API_URL}/metrics`, {
    next: { revalidate: 60 }, // ISR: revalidate every 60 seconds
  });
  if (!res.ok) throw new Error("Failed to fetch metrics");
  return res.json();
}

async function getRecentActivity(): Promise<Activity[]> {
  const res = await fetch(`${process.env.API_URL}/activity`, {
    next: { revalidate: 30 },
  });
  if (!res.ok) throw new Error("Failed to fetch activity");
  return res.json();
}

async function getAlerts(): Promise<Alert[]> {
  const res = await fetch(`${process.env.API_URL}/alerts`, {
    cache: "no-store", // Always fresh
  });
  if (!res.ok) throw new Error("Failed to fetch alerts");
  return res.json();
}

// Types
interface DashboardMetrics {
  totalUsers: number;
  activeUsers: number;
  revenue: number;
  conversionRate: number;
}

interface Activity {
  id: string;
  user: string;
  action: string;
  timestamp: string;
}

interface Alert {
  id: string;
  severity: "info" | "warning" | "critical";
  message: string;
  timestamp: string;
}

// Main page - Server Component (no "use client" directive)
export default function DashboardPage() {
  return (
    <div className="dashboard-grid">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <ErrorBoundary fallback={<MetricCardError />}>
          <Suspense fallback={<MetricCardSkeleton />}>
            <MetricsCards />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ErrorBoundary fallback={<SectionError title="Activity" />}>
          <Suspense fallback={<ActivitySkeleton />}>
            <RecentActivitySection />
          </Suspense>
        </ErrorBoundary>

        <ErrorBoundary fallback={<SectionError title="Alerts" />}>
          <Suspense fallback={<AlertsSkeleton />}>
            <AlertsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
    </div>
  );
}

// Async Server Components - data fetching happens at the component level
async function MetricsCards() {
  const metrics = await getMetrics();

  return (
    <>
      <MetricCard title="Total Users" value={metrics.totalUsers.toLocaleString()} />
      <MetricCard title="Active Users" value={metrics.activeUsers.toLocaleString()} />
      <MetricCard
        title="Revenue"
        value={`$${metrics.revenue.toLocaleString()}`}
      />
      <MetricCard
        title="Conversion"
        value={`${(metrics.conversionRate * 100).toFixed(1)}%`}
      />
    </>
  );
}

async function RecentActivitySection() {
  const activities = await getRecentActivity();

  return (
    <section className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
      <ul className="space-y-3">
        {activities.map((activity) => (
          <li key={activity.id} className="flex items-center justify-between">
            <div>
              <span className="font-medium">{activity.user}</span>
              <span className="text-gray-500 ml-2">{activity.action}</span>
            </div>
            <time className="text-sm text-gray-400">
              {new Date(activity.timestamp).toLocaleTimeString()}
            </time>
          </li>
        ))}
      </ul>
    </section>
  );
}

async function AlertsSection() {
  const alerts = await getAlerts();

  const severityColors = {
    info: "bg-blue-50 border-blue-200 text-blue-800",
    warning: "bg-yellow-50 border-yellow-200 text-yellow-800",
    critical: "bg-red-50 border-red-200 text-red-800",
  };

  return (
    <section className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">
        Active Alerts ({alerts.length})
      </h2>
      <div className="space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`p-3 rounded border ${severityColors[alert.severity]}`}
          >
            <div className="flex justify-between items-start">
              <span className="font-medium capitalize">{alert.severity}</span>
              <time className="text-xs">
                {new Date(alert.timestamp).toLocaleString()}
              </time>
            </div>
            <p className="mt-1 text-sm">{alert.message}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Pure presentation components (also server components - no hooks needed)
function MetricCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
    </div>
  );
}

// Skeleton components for loading states
function MetricCardSkeleton() {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-white rounded-lg shadow p-6 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-20 mb-3" />
          <div className="h-8 bg-gray-200 rounded w-32" />
        </div>
      ))}
    </>
  );
}

function ActivitySkeleton() {
  return (
    <section className="bg-white rounded-lg shadow p-6 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-40 mb-4" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-8 bg-gray-100 rounded mb-2" />
      ))}
    </section>
  );
}

function AlertsSkeleton() {
  return (
    <section className="bg-white rounded-lg shadow p-6 animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-32 mb-4" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-16 bg-gray-100 rounded mb-2" />
      ))}
    </section>
  );
}

function MetricCardError() {
  return <div className="col-span-4 text-red-500 p-4">Failed to load metrics</div>;
}

function SectionError({ title }: { title: string }) {
  return (
    <section className="bg-white rounded-lg shadow p-6">
      <p className="text-red-500">Failed to load {title}</p>
    </section>
  );
}
'''),

    ("react/rsc_server_client_boundary", r'''<think>
One of the trickiest parts of React Server Components is understanding the server/client boundary. I need to show how to properly compose server and client components, pass data across the boundary, and use the "use client" directive correctly. Common mistakes include putting "use client" too high in the tree and unnecessarily making things client components.
</think>

Build React Server Component patterns showing proper server/client composition, including passing server data to interactive client components, serialization boundaries, and component composition strategies.''', r'''<think>
The key insight is that server components can import and render client components, passing serializable props across the boundary. Client components cannot import server components but can accept them as children. I will demonstrate several composition patterns.
</think>

// Pattern 1: Server component wrapping client interactivity
// app/products/page.tsx (Server Component)
import { ProductGrid } from "./product-grid"; // Client Component
import { FilterSidebar } from "./filter-sidebar"; // Client Component

async function getProducts(category?: string) {
  const params = category ? `?category=${category}` : "";
  const res = await fetch(`${process.env.API_URL}/products${params}`, {
    next: { revalidate: 300 },
  });
  return res.json() as Promise<Product[]>;
}

async function getCategories() {
  const res = await fetch(`${process.env.API_URL}/categories`, {
    next: { revalidate: 3600 },
  });
  return res.json() as Promise<Category[]>;
}

interface Product {
  id: string;
  name: string;
  price: number;
  image: string;
  category: string;
  rating: number;
}

interface Category {
  id: string;
  name: string;
  count: number;
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: { category?: string; sort?: string };
}) {
  // Parallel fetching on the server
  const [products, categories] = await Promise.all([
    getProducts(searchParams.category),
    getCategories(),
  ]);

  return (
    <div className="flex gap-6">
      {/* Server data passed to client component for interactivity */}
      <FilterSidebar
        categories={categories}
        initialCategory={searchParams.category}
      />
      <ProductGrid
        initialProducts={products}
        initialSort={searchParams.sort || "name"}
      />
    </div>
  );
}

// components/filter-sidebar.tsx (Client Component)
// "use client"
// import { useRouter, useSearchParams } from "next/navigation";
// import { useState, useTransition } from "react";

interface FilterSidebarProps {
  categories: Category[];
  initialCategory?: string;
}

// This is a client component that receives server-fetched data as props
export function FilterSidebar({ categories, initialCategory }: FilterSidebarProps) {
  // In the real file, these would use hooks
  // const router = useRouter();
  // const [isPending, startTransition] = useTransition();
  // const [selected, setSelected] = useState(initialCategory);

  // For demonstration, showing the component structure
  return (
    <aside className="w-64 shrink-0">
      <h2 className="text-lg font-semibold mb-4">Categories</h2>
      <ul className="space-y-2">
        {categories.map((cat) => (
          <li key={cat.id}>
            <button
              className={`w-full text-left px-3 py-2 rounded ${
                cat.id === initialCategory ? "bg-blue-100" : "hover:bg-gray-100"
              }`}
            >
              {cat.name} ({cat.count})
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

// Pattern 2: Composition via children - server content inside client wrapper
// components/accordion.tsx (Client Component)
// "use client"
// import { useState, ReactNode } from "react";

interface AccordionProps {
  title: string;
  children: React.ReactNode; // Can be server components!
  defaultOpen?: boolean;
}

export function Accordion({ title, children, defaultOpen = false }: AccordionProps) {
  // const [isOpen, setIsOpen] = useState(defaultOpen);
  const isOpen = defaultOpen; // simplified

  return (
    <div className="border rounded-lg">
      <button
        className="w-full px-4 py-3 text-left font-medium flex justify-between"
        // onClick={() => setIsOpen(!isOpen)}
      >
        {title}
        <span>{isOpen ? "-" : "+"}</span>
      </button>
      {isOpen && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

// app/faq/page.tsx (Server Component)
// Server component content rendered INSIDE a client component via children
async function getFAQs() {
  const res = await fetch(`${process.env.API_URL}/faqs`);
  return res.json() as Promise<Array<{ question: string; answer: string }>>;
}

export async function FAQPage() {
  const faqs = await getFAQs();

  return (
    <div className="space-y-4">
      {faqs.map((faq, i) => (
        <Accordion key={i} title={faq.question}>
          {/* This server-rendered content is passed as children to client component */}
          <p className="text-gray-600">{faq.answer}</p>
        </Accordion>
      ))}
    </div>
  );
}

// Pattern 3: Serialization boundary - what can cross the boundary
// Only serializable values can be passed from server to client:
// - Primitives: string, number, boolean, null, undefined
// - Plain objects and arrays (of serializable values)
// - Date (serialized as ISO string)
// - NOT: functions, classes, symbols, Maps, Sets

// Pattern to handle non-serializable data:
// app/users/[id]/page.tsx (Server Component)
async function getUserWithActions(id: string) {
  const res = await fetch(`${process.env.API_URL}/users/${id}`);
  const user = await res.json();

  // Transform to serializable shape before passing to client
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    joinedAt: user.joinedAt, // Date will be serialized as string
    role: user.role,
    permissions: user.permissions, // Array of strings - serializable
  };
}

interface UserProfileClientProps {
  user: {
    id: string;
    name: string;
    email: string;
    joinedAt: string;
    role: string;
    permissions: string[];
  };
}

export function UserProfileClient({ user }: UserProfileClientProps) {
  // Client component receives serializable data and adds interactivity
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{user.name}</h1>
      <p className="text-gray-500">{user.email}</p>
      <p className="text-sm">Joined: {new Date(user.joinedAt).toLocaleDateString()}</p>
      <div className="flex gap-2">
        {user.permissions.map((perm) => (
          <span key={perm} className="px-2 py-1 bg-gray-100 rounded text-xs">
            {perm}
          </span>
        ))}
      </div>
    </div>
  );
}
'''),

    ("react/rsc_streaming", r'''Build a React streaming SSR pattern with progressive loading using Suspense boundaries, showing how to stream critical content first while non-critical sections load asynchronously.''', r'''// app/article/[slug]/page.tsx - Streaming SSR with progressive loading

import { Suspense } from "react";

// Critical data - loaded first, blocks initial render
async function getArticle(slug: string) {
  const res = await fetch(`${process.env.API_URL}/articles/${slug}`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error("Article not found");
  return res.json() as Promise<Article>;
}

// Non-critical data - streamed in later
async function getComments(articleId: string) {
  // Simulate slow endpoint
  const res = await fetch(`${process.env.API_URL}/articles/${articleId}/comments`, {
    cache: "no-store",
  });
  return res.json() as Promise<Comment[]>;
}

async function getRelatedArticles(articleId: string) {
  const res = await fetch(
    `${process.env.API_URL}/articles/${articleId}/related`,
    { next: { revalidate: 3600 } }
  );
  return res.json() as Promise<ArticleSummary[]>;
}

async function getAuthorProfile(authorId: string) {
  const res = await fetch(`${process.env.API_URL}/authors/${authorId}`, {
    next: { revalidate: 86400 },
  });
  return res.json() as Promise<Author>;
}

interface Article {
  id: string;
  slug: string;
  title: string;
  content: string;
  authorId: string;
  publishedAt: string;
  tags: string[];
  readingTime: number;
}

interface Comment {
  id: string;
  author: string;
  content: string;
  createdAt: string;
  likes: number;
}

interface ArticleSummary {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  image: string;
}

interface Author {
  id: string;
  name: string;
  avatar: string;
  bio: string;
  articleCount: number;
}

// Page component - article content streams first, then secondary content
export default async function ArticlePage({
  params,
}: {
  params: { slug: string };
}) {
  // This blocks the initial HTML - critical content
  const article = await getArticle(params.slug);

  return (
    <article className="max-w-4xl mx-auto">
      {/* Critical content - rendered immediately in initial HTML */}
      <header className="mb-8">
        <h1 className="text-4xl font-bold mb-4">{article.title}</h1>
        <div className="flex items-center gap-4 text-gray-500">
          <time>{new Date(article.publishedAt).toLocaleDateString()}</time>
          <span>{article.readingTime} min read</span>
          <div className="flex gap-2">
            {article.tags.map((tag) => (
              <span key={tag} className="px-2 py-1 bg-gray-100 rounded-full text-xs">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </header>

      {/* Article body - critical, rendered immediately */}
      <div
        className="prose prose-lg max-w-none mb-12"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />

      {/* Author bio - streams in after article body */}
      <Suspense fallback={<AuthorSkeleton />}>
        <AuthorSection authorId={article.authorId} />
      </Suspense>

      {/* Comments - non-critical, streams in later */}
      <Suspense fallback={<CommentsSkeleton />}>
        <CommentsSection articleId={article.id} />
      </Suspense>

      {/* Related articles - lowest priority, streams in last */}
      <Suspense fallback={<RelatedSkeleton />}>
        <RelatedArticles articleId={article.id} />
      </Suspense>
    </article>
  );
}

// Each of these is an async server component that streams independently
async function AuthorSection({ authorId }: { authorId: string }) {
  const author = await getAuthorProfile(authorId);

  return (
    <div className="border-t border-b py-6 my-8 flex items-start gap-4">
      <img
        src={author.avatar}
        alt={author.name}
        className="w-16 h-16 rounded-full"
      />
      <div>
        <h3 className="font-semibold text-lg">{author.name}</h3>
        <p className="text-gray-600 mt-1">{author.bio}</p>
        <p className="text-sm text-gray-400 mt-2">
          {author.articleCount} articles published
        </p>
      </div>
    </div>
  );
}

async function CommentsSection({ articleId }: { articleId: string }) {
  const comments = await getComments(articleId);

  return (
    <section className="my-12">
      <h2 className="text-2xl font-bold mb-6">
        Comments ({comments.length})
      </h2>
      <div className="space-y-6">
        {comments.map((comment) => (
          <div key={comment.id} className="border-b pb-4">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium">{comment.author}</span>
              <time className="text-sm text-gray-400">
                {new Date(comment.createdAt).toLocaleDateString()}
              </time>
            </div>
            <p className="text-gray-700">{comment.content}</p>
            <button className="text-sm text-gray-500 mt-2 hover:text-blue-500">
              {comment.likes} likes
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

async function RelatedArticles({ articleId }: { articleId: string }) {
  const related = await getRelatedArticles(articleId);

  if (related.length === 0) return null;

  return (
    <section className="my-12">
      <h2 className="text-2xl font-bold mb-6">Related Articles</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {related.map((article) => (
          <a
            key={article.id}
            href={`/article/${article.slug}`}
            className="group block"
          >
            <img
              src={article.image}
              alt={article.title}
              className="w-full h-48 object-cover rounded-lg mb-3"
            />
            <h3 className="font-semibold group-hover:text-blue-600">
              {article.title}
            </h3>
            <p className="text-sm text-gray-500 mt-1 line-clamp-2">
              {article.excerpt}
            </p>
          </a>
        ))}
      </div>
    </section>
  );
}

// Skeleton components
function AuthorSkeleton() {
  return (
    <div className="border-t border-b py-6 my-8 flex gap-4 animate-pulse">
      <div className="w-16 h-16 rounded-full bg-gray-200" />
      <div className="flex-1">
        <div className="h-5 bg-gray-200 rounded w-32 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-full mb-1" />
        <div className="h-4 bg-gray-200 rounded w-3/4" />
      </div>
    </div>
  );
}

function CommentsSkeleton() {
  return (
    <section className="my-12 animate-pulse">
      <div className="h-7 bg-gray-200 rounded w-40 mb-6" />
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="border-b pb-4 mb-4">
          <div className="h-4 bg-gray-200 rounded w-24 mb-2" />
          <div className="h-4 bg-gray-100 rounded w-full mb-1" />
          <div className="h-4 bg-gray-100 rounded w-2/3" />
        </div>
      ))}
    </section>
  );
}

function RelatedSkeleton() {
  return (
    <section className="my-12 animate-pulse">
      <div className="h-7 bg-gray-200 rounded w-48 mb-6" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i}>
            <div className="w-full h-48 bg-gray-200 rounded-lg mb-3" />
            <div className="h-5 bg-gray-200 rounded w-3/4 mb-2" />
            <div className="h-4 bg-gray-100 rounded w-full" />
          </div>
        ))}
      </div>
    </section>
  );
}
'''),

    ("react/rsc_form_actions", r'''Build React Server Actions for a form-heavy application with progressive enhancement, optimistic updates, server-side validation, and proper error handling with revalidation.''', r'''// app/settings/actions.ts - Server Actions
// "use server"

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

// Types
interface ProfileData {
  name: string;
  email: string;
  bio: string;
  website: string;
}

interface ActionResult {
  success: boolean;
  message: string;
  errors?: Record<string, string>;
}

// Server Action: Update profile
export async function updateProfile(
  prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  // Extract and validate
  const data: ProfileData = {
    name: formData.get("name") as string,
    email: formData.get("email") as string,
    bio: formData.get("bio") as string,
    website: formData.get("website") as string,
  };

  // Server-side validation
  const errors: Record<string, string> = {};

  if (!data.name || data.name.trim().length < 2) {
    errors.name = "Name must be at least 2 characters";
  }
  if (!data.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
    errors.email = "Invalid email address";
  }
  if (data.bio && data.bio.length > 500) {
    errors.bio = "Bio must be 500 characters or less";
  }
  if (data.website && !data.website.startsWith("https://")) {
    errors.website = "Website must start with https://";
  }

  if (Object.keys(errors).length > 0) {
    return { success: false, message: "Validation failed", errors };
  }

  // Persist to database
  try {
    const res = await fetch(`${process.env.API_URL}/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    if (!res.ok) {
      const error = await res.json();
      return { success: false, message: error.message || "Update failed" };
    }

    // Revalidate the profile page cache
    revalidatePath("/settings");
    revalidatePath("/profile");

    return { success: true, message: "Profile updated successfully" };
  } catch (error) {
    return { success: false, message: "Server error. Please try again." };
  }
}

// Server Action: Delete account
export async function deleteAccount(formData: FormData): Promise<ActionResult> {
  const confirmation = formData.get("confirmation") as string;

  if (confirmation !== "DELETE") {
    return {
      success: false,
      message: "Please type DELETE to confirm",
      errors: { confirmation: 'Type "DELETE" to confirm' },
    };
  }

  try {
    const res = await fetch(`${process.env.API_URL}/account`, {
      method: "DELETE",
    });

    if (!res.ok) {
      return { success: false, message: "Failed to delete account" };
    }

    redirect("/goodbye");
  } catch (error) {
    if ((error as any)?.digest?.startsWith("NEXT_REDIRECT")) throw error;
    return { success: false, message: "Server error" };
  }
  return { success: true, message: "" };
}

// Server Action: Upload avatar
export async function uploadAvatar(
  prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  const file = formData.get("avatar") as File;

  if (!file || file.size === 0) {
    return { success: false, message: "No file selected" };
  }

  if (file.size > 5 * 1024 * 1024) {
    return { success: false, message: "File must be under 5MB" };
  }

  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
  if (!allowedTypes.includes(file.type)) {
    return { success: false, message: "Only JPEG, PNG, and WebP allowed" };
  }

  try {
    const uploadFormData = new FormData();
    uploadFormData.append("file", file);

    const res = await fetch(`${process.env.API_URL}/avatar`, {
      method: "POST",
      body: uploadFormData,
    });

    if (!res.ok) {
      return { success: false, message: "Upload failed" };
    }

    revalidatePath("/settings");
    revalidatePath("/profile");

    return { success: true, message: "Avatar updated" };
  } catch (error) {
    return { success: false, message: "Upload error. Please try again." };
  }
}

// app/settings/page.tsx - Form with Server Actions
// "use client" for the form component
// import { useFormState, useFormStatus } from "react-dom";

// Form component using Server Actions
export function ProfileForm({
  initialData,
}: {
  initialData: ProfileData;
}) {
  // In real code: const [state, formAction] = useFormState(updateProfile, null);

  return (
    <form className="space-y-6 max-w-lg">
      <div>
        <label htmlFor="name" className="block text-sm font-medium mb-1">
          Name
        </label>
        <input
          id="name"
          name="name"
          type="text"
          defaultValue={initialData.name}
          className="w-full px-3 py-2 border rounded-md"
          required
        />
      </div>

      <div>
        <label htmlFor="email" className="block text-sm font-medium mb-1">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          defaultValue={initialData.email}
          className="w-full px-3 py-2 border rounded-md"
          required
        />
      </div>

      <div>
        <label htmlFor="bio" className="block text-sm font-medium mb-1">
          Bio
        </label>
        <textarea
          id="bio"
          name="bio"
          defaultValue={initialData.bio}
          rows={4}
          maxLength={500}
          className="w-full px-3 py-2 border rounded-md"
        />
      </div>

      <div>
        <label htmlFor="website" className="block text-sm font-medium mb-1">
          Website
        </label>
        <input
          id="website"
          name="website"
          type="url"
          defaultValue={initialData.website}
          placeholder="https://"
          className="w-full px-3 py-2 border rounded-md"
        />
      </div>

      <SubmitButton />
    </form>
  );
}

// Separate component to use useFormStatus for pending state
function SubmitButton() {
  // In real code: const { pending } = useFormStatus();
  const pending = false;

  return (
    <button
      type="submit"
      disabled={pending}
      className={`px-4 py-2 rounded-md text-white ${
        pending ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
      }`}
    >
      {pending ? "Saving..." : "Save Changes"}
    </button>
  );
}

// Avatar upload form with optimistic preview
export function AvatarForm({ currentAvatar }: { currentAvatar: string }) {
  // In real code:
  // const [state, formAction] = useFormState(uploadAvatar, null);
  // const [preview, setPreview] = useState<string | null>(null);

  return (
    <form className="flex items-center gap-4">
      <img
        src={currentAvatar}
        alt="Avatar"
        className="w-20 h-20 rounded-full object-cover"
      />
      <div>
        <label
          htmlFor="avatar"
          className="cursor-pointer px-4 py-2 bg-gray-100 rounded-md hover:bg-gray-200"
        >
          Choose Photo
        </label>
        <input
          id="avatar"
          name="avatar"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
        />
        <p className="text-xs text-gray-500 mt-1">
          JPEG, PNG, or WebP. Max 5MB.
        </p>
      </div>
    </form>
  );
}
'''),

    ("react/rsc_suspense_patterns", r'''Build advanced React Suspense patterns including nested Suspense boundaries with different granularity, SuspenseList for coordinated loading, and a cache-aware data fetching utility.''', r'''// Advanced Suspense patterns for production React applications

// Cache-aware data fetching utility for React Server Components
// This works with React's built-in fetch cache deduplication

// lib/data-fetcher.ts
type FetchOptions = {
  revalidate?: number | false;
  tags?: string[];
  cache?: RequestCache;
};

async function fetchData<T>(
  url: string,
  options: FetchOptions = {}
): Promise<T> {
  const fetchOptions: RequestInit & { next?: { revalidate?: number | false; tags?: string[] } } = {
    headers: { "Content-Type": "application/json" },
  };

  if (options.cache === "no-store") {
    fetchOptions.cache = "no-store";
  } else {
    fetchOptions.next = {
      revalidate: options.revalidate ?? 60,
      tags: options.tags,
    };
  }

  const res = await fetch(url, fetchOptions);

  if (!res.ok) {
    throw new FetchError(
      `Failed to fetch ${url}: ${res.status} ${res.statusText}`,
      res.status
    );
  }

  return res.json();
}

class FetchError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "FetchError";
  }
}

// Preload pattern - start fetching before component renders
function preload<T>(url: string, options?: FetchOptions): void {
  // This call gets deduped by React/Next.js fetch cache
  void fetchData<T>(url, options);
}

// app/shop/page.tsx - Nested Suspense with different granularity
import { Suspense } from "react";

interface ProductCategory {
  id: string;
  name: string;
  slug: string;
  image: string;
}

interface FeaturedProduct {
  id: string;
  name: string;
  price: number;
  image: string;
  badge?: string;
}

interface Banner {
  id: string;
  image: string;
  title: string;
  link: string;
}

interface Promotion {
  id: string;
  title: string;
  discount: string;
  expiresAt: string;
  code: string;
}

// Preload data for components further down the tree
export default function ShopPage() {
  // Start fetching early - these will be deduped when components use them
  preload<ProductCategory[]>(`${process.env.API_URL}/categories`);
  preload<FeaturedProduct[]>(`${process.env.API_URL}/featured`);

  return (
    <div className="space-y-8">
      {/* Level 1: Hero banner - loads fast, shown immediately */}
      <Suspense fallback={<HeroBannerSkeleton />}>
        <HeroBanner />
      </Suspense>

      {/* Level 2: Categories and Featured - can load independently */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <Suspense fallback={<CategoriesSkeleton />}>
            <CategoriesGrid />
          </Suspense>
        </div>
        <div>
          {/* Nested Suspense - promotions inside featured section */}
          <Suspense fallback={<FeaturedSkeleton />}>
            <FeaturedSection />
          </Suspense>
        </div>
      </div>

      {/* Level 3: Product recommendations - lowest priority */}
      <Suspense fallback={<RecommendationsSkeleton />}>
        <PersonalizedRecommendations />
      </Suspense>
    </div>
  );
}

async function HeroBanner() {
  const banners = await fetchData<Banner[]>(
    `${process.env.API_URL}/banners`,
    { revalidate: 300 }
  );

  return (
    <div className="relative h-96 rounded-xl overflow-hidden">
      {banners.length > 0 && (
        <a href={banners[0].link} className="block h-full">
          <img
            src={banners[0].image}
            alt={banners[0].title}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
          <h2 className="absolute bottom-8 left-8 text-4xl font-bold text-white">
            {banners[0].title}
          </h2>
        </a>
      )}
    </div>
  );
}

async function CategoriesGrid() {
  const categories = await fetchData<ProductCategory[]>(
    `${process.env.API_URL}/categories`,
    { revalidate: 3600, tags: ["categories"] }
  );

  return (
    <section>
      <h2 className="text-2xl font-bold mb-4">Shop by Category</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {categories.map((cat) => (
          <a
            key={cat.id}
            href={`/shop/${cat.slug}`}
            className="group relative h-40 rounded-lg overflow-hidden"
          >
            <img
              src={cat.image}
              alt={cat.name}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            />
            <div className="absolute inset-0 bg-black/30 group-hover:bg-black/40 transition-colors" />
            <span className="absolute bottom-3 left-3 text-white font-semibold">
              {cat.name}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

async function FeaturedSection() {
  const featured = await fetchData<FeaturedProduct[]>(
    `${process.env.API_URL}/featured`,
    { revalidate: 300, tags: ["featured"] }
  );

  return (
    <section>
      <h2 className="text-2xl font-bold mb-4">Featured</h2>
      <div className="space-y-4">
        {featured.slice(0, 4).map((product) => (
          <a
            key={product.id}
            href={`/product/${product.id}`}
            className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50"
          >
            <img
              src={product.image}
              alt={product.name}
              className="w-16 h-16 object-cover rounded"
            />
            <div className="flex-1">
              <p className="font-medium">{product.name}</p>
              <p className="text-sm text-gray-500">${product.price}</p>
            </div>
            {product.badge && (
              <span className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded-full">
                {product.badge}
              </span>
            )}
          </a>
        ))}
      </div>

      {/* Nested Suspense for promotions within the featured section */}
      <Suspense fallback={<div className="h-24 bg-gray-100 rounded mt-4 animate-pulse" />}>
        <PromotionsWidget />
      </Suspense>
    </section>
  );
}

async function PromotionsWidget() {
  const promotions = await fetchData<Promotion[]>(
    `${process.env.API_URL}/promotions`,
    { cache: "no-store" } // Always fresh
  );

  if (promotions.length === 0) return null;

  const promo = promotions[0];
  return (
    <div className="mt-4 p-4 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg text-white">
      <p className="font-bold">{promo.title}</p>
      <p className="text-sm opacity-90">{promo.discount} off with code</p>
      <code className="bg-white/20 px-2 py-1 rounded text-sm mt-2 inline-block">
        {promo.code}
      </code>
    </div>
  );
}

async function PersonalizedRecommendations() {
  const products = await fetchData<FeaturedProduct[]>(
    `${process.env.API_URL}/recommendations`,
    { cache: "no-store" }
  );

  return (
    <section>
      <h2 className="text-2xl font-bold mb-4">Recommended for You</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {products.map((product) => (
          <a
            key={product.id}
            href={`/product/${product.id}`}
            className="group"
          >
            <div className="aspect-square rounded-lg overflow-hidden bg-gray-100">
              <img
                src={product.image}
                alt={product.name}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform"
              />
            </div>
            <p className="mt-2 text-sm font-medium truncate">{product.name}</p>
            <p className="text-sm text-gray-500">${product.price}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

// Skeleton components
function HeroBannerSkeleton() {
  return <div className="h-96 rounded-xl bg-gray-200 animate-pulse" />;
}

function CategoriesSkeleton() {
  return (
    <div>
      <div className="h-8 bg-gray-200 rounded w-48 mb-4" />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-40 bg-gray-200 rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  );
}

function FeaturedSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-32 mb-4" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex gap-3 p-3">
          <div className="w-16 h-16 bg-gray-200 rounded" />
          <div className="flex-1">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
            <div className="h-4 bg-gray-200 rounded w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

function RecommendationsSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-56 mb-4" />
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i}>
            <div className="aspect-square bg-gray-200 rounded-lg" />
            <div className="h-4 bg-gray-200 rounded w-3/4 mt-2" />
            <div className="h-4 bg-gray-200 rounded w-1/4 mt-1" />
          </div>
        ))}
      </div>
    </div>
  );
}
'''),
]
