"""
Batch p1082: TypeScript/React production pairs - Next.js Patterns
Topics: App Router, parallel routes, intercepting routes, route handlers, middleware
"""

PAIRS = [
    ("react/nextjs_app_router", r'''Build Next.js App Router patterns showing route groups, layouts, loading states, error boundaries, and not-found handling with proper TypeScript types.''', r'''// app/layout.tsx - Root layout
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { template: "%s | MyApp", default: "MyApp" },
  description: "Production Next.js application",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <div className="flex">
          <aside className="w-64 bg-white border-r min-h-screen p-4">
            <nav aria-label="Main navigation">
              <ul className="space-y-2">
                <li><a href="/dashboard" className="block px-3 py-2 rounded hover:bg-gray-100">Dashboard</a></li>
                <li><a href="/projects" className="block px-3 py-2 rounded hover:bg-gray-100">Projects</a></li>
                <li><a href="/settings" className="block px-3 py-2 rounded hover:bg-gray-100">Settings</a></li>
              </ul>
            </nav>
          </aside>
          <main className="flex-1 p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}

// app/(auth)/layout.tsx - Route group for auth pages (no sidebar)
export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
        <div className="w-full max-w-md bg-white rounded-xl shadow-xl p-8">
          {children}
        </div>
      </body>
    </html>
  );
}

// app/dashboard/layout.tsx - Dashboard-specific layout with nested navigation
export function DashboardLayout({
  children,
  metrics,
  activity,
}: {
  children: React.ReactNode;
  metrics: React.ReactNode; // Parallel route slot
  activity: React.ReactNode; // Parallel route slot
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">{children}</div>
        <div className="space-y-6">
          {metrics}
          {activity}
        </div>
      </div>
    </div>
  );
}

// app/dashboard/loading.tsx - Loading state
export function DashboardLoading() {
  return (
    <div className="animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-48 mb-6" />
      <div className="grid grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-gray-200 rounded-lg" />
        ))}
      </div>
      <div className="h-64 bg-gray-200 rounded-lg" />
    </div>
  );
}

// app/dashboard/error.tsx - Error boundary (must be client component)
// "use client"
export function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="p-8 text-center">
      <h2 className="text-xl font-bold text-red-600 mb-2">Something went wrong</h2>
      <p className="text-gray-600 mb-4">{error.message}</p>
      <button
        onClick={reset}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Try again
      </button>
    </div>
  );
}

// app/not-found.tsx - Global 404 page
export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh]">
      <h1 className="text-6xl font-bold text-gray-300 mb-4">404</h1>
      <p className="text-xl text-gray-600 mb-6">Page not found</p>
      <a href="/" className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
        Go Home
      </a>
    </div>
  );
}

// app/projects/[projectId]/not-found.tsx - Scoped 404
export function ProjectNotFound() {
  return (
    <div className="text-center py-12">
      <h2 className="text-2xl font-bold mb-2">Project Not Found</h2>
      <p className="text-gray-500 mb-4">The project you are looking for does not exist or has been deleted.</p>
      <a href="/projects" className="text-blue-600 hover:underline">
        Back to Projects
      </a>
    </div>
  );
}

// app/projects/[projectId]/page.tsx - Dynamic route with params
import { notFound } from "next/navigation";

interface ProjectPageProps {
  params: { projectId: string };
  searchParams: { tab?: string; page?: string };
}

async function getProject(id: string) {
  const res = await fetch(`${process.env.API_URL}/projects/${id}`, {
    next: { tags: [`project-${id}`] },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch project");
  return res.json();
}

export default async function ProjectPage({ params, searchParams }: ProjectPageProps) {
  const project = await getProject(params.projectId);
  if (!project) notFound();

  const tab = searchParams.tab || "overview";

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-bold">{project.name}</h1>
        <p className="text-gray-500">{project.description}</p>
      </header>

      <nav className="flex gap-4 border-b mb-6">
        {["overview", "tasks", "files", "settings"].map((t) => (
          <a
            key={t}
            href={`/projects/${params.projectId}?tab=${t}`}
            className={`pb-2 px-1 capitalize ${
              tab === t
                ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </a>
        ))}
      </nav>

      <div>{/* Tab content based on searchParams.tab */}</div>
    </div>
  );
}

// Generate static params for pre-rendering
export async function generateStaticParams() {
  const res = await fetch(`${process.env.API_URL}/projects`);
  const projects = await res.json();
  return projects.map((p: any) => ({ projectId: p.id }));
}

// Metadata generation
export async function generateMetadata({ params }: ProjectPageProps) {
  const project = await getProject(params.projectId);
  if (!project) return { title: "Not Found" };
  return {
    title: project.name,
    description: project.description,
  };
}
'''),

    ("react/nextjs_parallel_routes", r'''<think>
Parallel routes in Next.js are one of the most powerful App Router features. They allow rendering multiple pages in the same layout simultaneously. I need to show the folder structure conventions (@slot), default.tsx files, and how to conditionally render based on authentication or modal states.
</think>

Build Next.js parallel route patterns for a dashboard with simultaneously rendered slots for metrics, activity feed, and modal overlays using intercepted routes.''', r'''<think>
Parallel routes use the @folder convention to create named slots. I need to show the file structure, how default.tsx works as a fallback, and a practical example combining parallel routes with intercepted routes for a modal pattern.
</think>

// File structure for parallel routes:
// app/dashboard/
//   layout.tsx          - Receives named slots as props
//   page.tsx            - Main dashboard content
//   @metrics/
//     page.tsx          - Metrics panel
//     loading.tsx       - Metrics loading state
//     default.tsx       - Fallback when slot has no match
//   @activity/
//     page.tsx          - Activity feed
//     loading.tsx       - Activity loading state
//     default.tsx       - Fallback
//   @modal/
//     default.tsx       - No modal by default
//     (..)tasks/[id]/
//       page.tsx        - Intercepted task modal

// app/dashboard/layout.tsx
interface DashboardLayoutProps {
  children: React.ReactNode;
  metrics: React.ReactNode;
  activity: React.ReactNode;
  modal: React.ReactNode;
}

export default function DashboardLayout({
  children,
  metrics,
  activity,
  modal,
}: DashboardLayoutProps) {
  return (
    <div className="space-y-6">
      {/* Modal overlay - renders on top when active */}
      {modal}

      {/* Main content area */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Primary content - takes 3 columns */}
        <div className="xl:col-span-3">{children}</div>

        {/* Sidebar slots - stacked in 1 column */}
        <div className="space-y-6">
          {metrics}
          {activity}
        </div>
      </div>
    </div>
  );
}

// app/dashboard/page.tsx - Main dashboard content
export default async function DashboardPage() {
  const overview = await fetch(`${process.env.API_URL}/dashboard/overview`, {
    next: { revalidate: 60 },
  }).then((r) => r.json());

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {overview.stats.map((stat: any) => (
          <div key={stat.label} className="bg-white p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500">{stat.label}</p>
            <p className="text-2xl font-bold">{stat.value}</p>
            <p className={`text-xs ${stat.change >= 0 ? "text-green-600" : "text-red-600"}`}>
              {stat.change >= 0 ? "+" : ""}{stat.change}%
            </p>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Tasks</h2>
        {/* Task list with links that trigger intercepted route modals */}
        <ul className="divide-y">
          {overview.recentTasks.map((task: any) => (
            <li key={task.id}>
              <a
                href={`/tasks/${task.id}`}
                className="block py-3 px-2 hover:bg-gray-50 rounded"
              >
                <span className="font-medium">{task.title}</span>
                <span className="text-sm text-gray-500 ml-2">{task.status}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// app/dashboard/@metrics/page.tsx
export default async function MetricsSlot() {
  const metrics = await fetch(`${process.env.API_URL}/dashboard/metrics`, {
    next: { revalidate: 30 },
  }).then((r) => r.json());

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="font-semibold mb-3">Key Metrics</h3>
      <div className="space-y-3">
        {metrics.map((metric: any) => (
          <div key={metric.name}>
            <div className="flex justify-between text-sm mb-1">
              <span>{metric.name}</span>
              <span className="font-medium">{metric.value}%</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${metric.value}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// app/dashboard/@metrics/loading.tsx
export default function MetricsLoading() {
  return (
    <div className="bg-white rounded-lg shadow p-4 animate-pulse">
      <div className="h-5 bg-gray-200 rounded w-24 mb-3" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="mb-3">
          <div className="h-3 bg-gray-200 rounded w-full mb-1" />
          <div className="h-2 bg-gray-100 rounded-full" />
        </div>
      ))}
    </div>
  );
}

// app/dashboard/@metrics/default.tsx
export default function MetricsDefault() {
  return null; // Show nothing when navigated to a sub-route without metrics
}

// app/dashboard/@activity/page.tsx
export default async function ActivitySlot() {
  const activities = await fetch(`${process.env.API_URL}/dashboard/activity`, {
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="font-semibold mb-3">Recent Activity</h3>
      <ul className="space-y-3">
        {activities.slice(0, 8).map((activity: any) => (
          <li key={activity.id} className="flex gap-3 text-sm">
            <img
              src={activity.user.avatar}
              alt=""
              className="w-6 h-6 rounded-full mt-0.5"
            />
            <div>
              <p>
                <span className="font-medium">{activity.user.name}</span>{" "}
                {activity.action}
              </p>
              <time className="text-xs text-gray-400">{activity.timeAgo}</time>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// app/dashboard/@modal/default.tsx
export default function ModalDefault() {
  return null; // No modal by default
}

// app/dashboard/@modal/(..)tasks/[id]/page.tsx
// This intercepts /tasks/[id] when navigated from the dashboard
// "use client"
import { useRouter } from "next/navigation";

interface TaskModalProps {
  params: { id: string };
}

export default function TaskModal({ params }: TaskModalProps) {
  // const router = useRouter();

  // In real implementation, fetch task data
  return (
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/50"
        // onClick={() => router.back()}
      />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-auto">
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold">Task Details</h2>
            <button
              // onClick={() => router.back()}
              className="text-gray-400 hover:text-gray-600"
            >
              Close
            </button>
          </div>
          <p className="text-gray-600">Task ID: {params.id}</p>
          {/* Full task details would render here */}
        </div>
      </div>
    </div>
  );
}

// app/tasks/[id]/page.tsx - Full page version (when navigated directly)
export default async function TaskPage({ params }: { params: { id: string } }) {
  const task = await fetch(`${process.env.API_URL}/tasks/${params.id}`).then((r) =>
    r.json()
  );

  return (
    <div className="max-w-2xl mx-auto">
      <a href="/dashboard" className="text-blue-600 hover:underline mb-4 inline-block">
        Back to Dashboard
      </a>
      <h1 className="text-2xl font-bold mb-4">{task.title}</h1>
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-gray-600">{task.description}</p>
        {/* Full task page content */}
      </div>
    </div>
  );
}
'''),

    ("react/nextjs_route_handlers", r'''Build Next.js Route Handlers (API routes) in TypeScript with request validation, authentication middleware, rate limiting, and proper error handling patterns.''', r'''// app/api/tasks/route.ts - RESTful route handler
import { NextRequest, NextResponse } from "next/server";

// Types
interface Task {
  id: string;
  title: string;
  status: "todo" | "in_progress" | "done";
  priority: "low" | "medium" | "high";
  assigneeId: string | null;
  createdAt: string;
}

interface CreateTaskBody {
  title: string;
  priority?: Task["priority"];
  assigneeId?: string;
}

// Helper: Parse and validate JSON body
async function parseBody<T>(request: NextRequest, validator: (data: unknown) => T | null): Promise<T> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    throw new ApiError(400, "Invalid JSON body");
  }

  const validated = validator(body);
  if (!validated) {
    throw new ApiError(422, "Validation failed");
  }
  return validated;
}

// Helper: API error class
class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

// Helper: Error response
function errorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    return NextResponse.json(
      { error: { message: error.message, code: error.code } },
      { status: error.status }
    );
  }
  console.error("Unhandled error:", error);
  return NextResponse.json(
    { error: { message: "Internal server error", code: "INTERNAL_ERROR" } },
    { status: 500 }
  );
}

// Helper: Authenticate request
async function authenticate(request: NextRequest): Promise<{ userId: string; role: string }> {
  const authHeader = request.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    throw new ApiError(401, "Missing or invalid authorization header", "UNAUTHORIZED");
  }

  const token = authHeader.slice(7);
  // In production, verify JWT token
  try {
    // const payload = await verifyJWT(token);
    const payload = { userId: "user-1", role: "admin" }; // placeholder
    return payload;
  } catch {
    throw new ApiError(401, "Invalid or expired token", "TOKEN_EXPIRED");
  }
}

// Simple rate limiter using Map (use Redis in production)
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function rateLimit(key: string, limit: number = 100, windowMs: number = 60000): void {
  const now = Date.now();
  const record = rateLimitMap.get(key);

  if (!record || now > record.resetAt) {
    rateLimitMap.set(key, { count: 1, resetAt: now + windowMs });
    return;
  }

  if (record.count >= limit) {
    throw new ApiError(429, "Too many requests", "RATE_LIMITED");
  }

  record.count++;
}

// Validator
function validateCreateTask(data: unknown): CreateTaskBody | null {
  if (typeof data !== "object" || data === null) return null;
  const obj = data as Record<string, unknown>;

  if (typeof obj.title !== "string" || obj.title.trim().length === 0) return null;
  if (obj.title.length > 200) return null;

  const priority = obj.priority as string | undefined;
  if (priority && !["low", "medium", "high"].includes(priority)) return null;

  return {
    title: obj.title.trim(),
    priority: (priority as Task["priority"]) || "medium",
    assigneeId: typeof obj.assigneeId === "string" ? obj.assigneeId : undefined,
  };
}

// GET /api/tasks - List tasks
export async function GET(request: NextRequest) {
  try {
    const user = await authenticate(request);
    const ip = request.headers.get("x-forwarded-for") || "unknown";
    rateLimit(`tasks-list-${ip}`, 60);

    const { searchParams } = new URL(request.url);
    const status = searchParams.get("status");
    const page = parseInt(searchParams.get("page") || "1");
    const limit = Math.min(parseInt(searchParams.get("limit") || "20"), 100);
    const search = searchParams.get("search");

    // Build query (would use database in production)
    const queryParams = new URLSearchParams();
    if (status) queryParams.set("status", status);
    if (search) queryParams.set("search", search);
    queryParams.set("page", String(page));
    queryParams.set("limit", String(limit));
    queryParams.set("userId", user.userId);

    const res = await fetch(
      `${process.env.DATABASE_URL}/tasks?${queryParams}`,
      { cache: "no-store" }
    );

    const data = await res.json();

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "private, max-age=10",
        "X-Total-Count": String(data.total),
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}

// POST /api/tasks - Create task
export async function POST(request: NextRequest) {
  try {
    const user = await authenticate(request);
    rateLimit(`tasks-create-${user.userId}`, 30);

    const body = await parseBody(request, validateCreateTask);

    const task: Task = {
      id: crypto.randomUUID(),
      title: body.title,
      status: "todo",
      priority: body.priority || "medium",
      assigneeId: body.assigneeId || null,
      createdAt: new Date().toISOString(),
    };

    // Save to database
    // await db.tasks.create(task);

    return NextResponse.json(task, {
      status: 201,
      headers: { "Location": `/api/tasks/${task.id}` },
    });
  } catch (error) {
    return errorResponse(error);
  }
}

// app/api/tasks/[id]/route.ts - Individual task operations
export async function GET_TASK(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    await authenticate(request);

    // const task = await db.tasks.findById(params.id);
    const task = null; // placeholder

    if (!task) {
      throw new ApiError(404, "Task not found", "NOT_FOUND");
    }

    return NextResponse.json(task);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const user = await authenticate(request);
    const body = await request.json();

    // Validate update fields
    const allowedFields = ["title", "status", "priority", "assigneeId"];
    const updates: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
      if (allowedFields.includes(key)) {
        updates[key] = value;
      }
    }

    if (Object.keys(updates).length === 0) {
      throw new ApiError(400, "No valid fields to update");
    }

    // const updated = await db.tasks.update(params.id, updates);
    const updated = { id: params.id, ...updates };

    return NextResponse.json(updated);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const user = await authenticate(request);

    if (user.role !== "admin") {
      throw new ApiError(403, "Only admins can delete tasks", "FORBIDDEN");
    }

    // await db.tasks.delete(params.id);

    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return errorResponse(error);
  }
}
'''),

    ("react/nextjs_middleware", r'''Build Next.js middleware for authentication, internationalization, A/B testing, and request logging with proper response handling and header manipulation.''', r'''// middleware.ts - Next.js Edge Middleware
import { NextRequest, NextResponse } from "next/server";

// Configuration: which paths the middleware runs on
export const config = {
  matcher: [
    // Match all paths except static files and API health check
    "/((?!_next/static|_next/image|favicon.ico|api/health).*)",
  ],
};

// Auth: paths that require authentication
const PROTECTED_PATHS = ["/dashboard", "/settings", "/projects", "/api/tasks"];
const AUTH_PATHS = ["/login", "/register", "/forgot-password"];
const PUBLIC_PATHS = ["/", "/about", "/pricing", "/blog"];

// i18n: supported locales
const SUPPORTED_LOCALES = ["en", "es", "fr", "de", "ja"];
const DEFAULT_LOCALE = "en";

// A/B test: experiment configuration
interface Experiment {
  name: string;
  variants: string[];
  paths: string[];
}

const EXPERIMENTS: Experiment[] = [
  {
    name: "new-pricing",
    variants: ["control", "variant-a", "variant-b"],
    paths: ["/pricing"],
  },
  {
    name: "dashboard-v2",
    variants: ["control", "variant"],
    paths: ["/dashboard"],
  },
];

export default async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const response = NextResponse.next();

  // 1. Request logging
  const requestId = crypto.randomUUID();
  response.headers.set("X-Request-Id", requestId);
  response.headers.set("X-Response-Time", String(Date.now()));

  // 2. Security headers
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
  );

  // 3. Locale detection and redirect
  const localeResult = handleLocale(request, pathname);
  if (localeResult) return localeResult;

  // 4. Authentication check
  const authResult = await handleAuth(request, pathname);
  if (authResult) return authResult;

  // 5. A/B testing
  const abResponse = handleABTest(request, response, pathname);

  // 6. Rate limiting for API routes
  if (pathname.startsWith("/api/")) {
    const rateLimitResult = handleRateLimit(request);
    if (rateLimitResult) return rateLimitResult;
  }

  return abResponse || response;
}

// Locale detection
function handleLocale(request: NextRequest, pathname: string): NextResponse | null {
  // Check if path already has a locale prefix
  const pathnameLocale = SUPPORTED_LOCALES.find(
    (locale) => pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`
  );

  if (pathnameLocale) return null; // Already localized

  // Skip locale redirect for API routes and static files
  if (pathname.startsWith("/api/") || pathname.startsWith("/_next/")) {
    return null;
  }

  // Detect preferred locale
  const acceptLanguage = request.headers.get("accept-language") || "";
  const preferredLocale = detectLocale(acceptLanguage);

  // Check cookie for previously selected locale
  const cookieLocale = request.cookies.get("locale")?.value;
  const locale = cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale)
    ? cookieLocale
    : preferredLocale;

  // Only redirect if not default locale (to keep clean URLs for default)
  if (locale !== DEFAULT_LOCALE) {
    const url = request.nextUrl.clone();
    url.pathname = `/${locale}${pathname}`;
    return NextResponse.redirect(url);
  }

  return null;
}

function detectLocale(acceptLanguage: string): string {
  const languages = acceptLanguage
    .split(",")
    .map((lang) => {
      const [code, priority] = lang.trim().split(";q=");
      return { code: code.split("-")[0].toLowerCase(), priority: priority ? parseFloat(priority) : 1 };
    })
    .sort((a, b) => b.priority - a.priority);

  for (const { code } of languages) {
    if (SUPPORTED_LOCALES.includes(code)) return code;
  }
  return DEFAULT_LOCALE;
}

// Authentication
async function handleAuth(request: NextRequest, pathname: string): Promise<NextResponse | null> {
  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PATHS.some((p) => pathname.startsWith(p));

  // Get session token from cookie
  const sessionToken = request.cookies.get("session-token")?.value;

  if (isProtected && !sessionToken) {
    // Redirect to login with return URL
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("returnTo", pathname);
    return NextResponse.redirect(url);
  }

  if (isAuthPage && sessionToken) {
    // Already logged in, redirect to dashboard
    const returnTo = request.nextUrl.searchParams.get("returnTo") || "/dashboard";
    const url = request.nextUrl.clone();
    url.pathname = returnTo;
    url.searchParams.delete("returnTo");
    return NextResponse.redirect(url);
  }

  // Verify token for protected routes
  if (isProtected && sessionToken) {
    try {
      // In production: verify JWT or check session store
      const isValid = sessionToken.length > 10; // simplified
      if (!isValid) {
        const url = request.nextUrl.clone();
        url.pathname = "/login";
        const response = NextResponse.redirect(url);
        response.cookies.delete("session-token");
        return response;
      }
    } catch {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }
  }

  return null;
}

// A/B Testing
function handleABTest(
  request: NextRequest,
  response: NextResponse,
  pathname: string
): NextResponse | null {
  for (const experiment of EXPERIMENTS) {
    const matchesPath = experiment.paths.some((p) => pathname.startsWith(p));
    if (!matchesPath) continue;

    const cookieName = `exp-${experiment.name}`;
    let variant = request.cookies.get(cookieName)?.value;

    if (!variant || !experiment.variants.includes(variant)) {
      // Assign random variant
      const index = Math.floor(Math.random() * experiment.variants.length);
      variant = experiment.variants[index];
      response.cookies.set(cookieName, variant, {
        maxAge: 60 * 60 * 24 * 30, // 30 days
        httpOnly: false, // Readable by client for analytics
        sameSite: "lax",
      });
    }

    // Set header for the app to read
    response.headers.set(`X-Experiment-${experiment.name}`, variant);

    // Optionally rewrite to variant-specific page
    if (variant !== "control") {
      const url = request.nextUrl.clone();
      url.pathname = `${pathname}/__variants/${variant}`;
      return NextResponse.rewrite(url, {
        headers: response.headers,
      });
    }
  }

  return null;
}

// Rate limiting
const ipRequestCounts = new Map<string, { count: number; windowStart: number }>();

function handleRateLimit(request: NextRequest): NextResponse | null {
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0] || "unknown";
  const windowMs = 60 * 1000; // 1 minute window
  const maxRequests = 100;
  const now = Date.now();

  const record = ipRequestCounts.get(ip);

  if (!record || now - record.windowStart > windowMs) {
    ipRequestCounts.set(ip, { count: 1, windowStart: now });
    return null;
  }

  record.count++;

  if (record.count > maxRequests) {
    return NextResponse.json(
      { error: { message: "Too many requests", code: "RATE_LIMITED" } },
      {
        status: 429,
        headers: {
          "Retry-After": String(Math.ceil((record.windowStart + windowMs - now) / 1000)),
          "X-RateLimit-Limit": String(maxRequests),
          "X-RateLimit-Remaining": "0",
        },
      }
    );
  }

  return null;
}
'''),

    ("react/nextjs_data_patterns", r'''Build Next.js data fetching patterns including server actions with revalidation, ISR with on-demand revalidation, and streaming with loading UI for a content management dashboard.''', r'''// app/posts/actions.ts - Server Actions for CMS
// "use server"

import { revalidatePath, revalidateTag } from "next/cache";
import { redirect } from "next/navigation";

interface Post {
  id: string;
  title: string;
  slug: string;
  content: string;
  status: "draft" | "published" | "archived";
  authorId: string;
  publishedAt: string | null;
  updatedAt: string;
}

// Server Action: Create post
export async function createPost(formData: FormData) {
  const title = formData.get("title") as string;
  const content = formData.get("content") as string;
  const status = formData.get("status") as Post["status"];

  // Validate
  if (!title || title.length < 3) {
    return { error: "Title must be at least 3 characters" };
  }

  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

  const res = await fetch(`${process.env.API_URL}/posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      slug,
      content,
      status,
      publishedAt: status === "published" ? new Date().toISOString() : null,
    }),
  });

  if (!res.ok) {
    const error = await res.json();
    return { error: error.message || "Failed to create post" };
  }

  const post = await res.json();

  // Revalidate affected caches
  revalidateTag("posts");
  revalidatePath("/posts");

  if (status === "published") {
    revalidatePath(`/blog/${slug}`);
    revalidatePath("/blog");
  }

  redirect(`/posts/${post.id}`);
}

// Server Action: Update post
export async function updatePost(id: string, formData: FormData) {
  const title = formData.get("title") as string;
  const content = formData.get("content") as string;
  const status = formData.get("status") as Post["status"];

  const res = await fetch(`${process.env.API_URL}/posts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      content,
      status,
      publishedAt: status === "published" ? new Date().toISOString() : null,
    }),
  });

  if (!res.ok) {
    return { error: "Failed to update post" };
  }

  const post = await res.json();

  // Targeted revalidation
  revalidateTag(`post-${id}`);
  revalidateTag("posts");
  revalidatePath(`/posts/${id}`);
  revalidatePath("/posts");

  if (post.slug) {
    revalidatePath(`/blog/${post.slug}`);
  }

  return { success: true };
}

// Server Action: Publish post
export async function publishPost(id: string) {
  const res = await fetch(`${process.env.API_URL}/posts/${id}/publish`, {
    method: "POST",
  });

  if (!res.ok) {
    return { error: "Failed to publish" };
  }

  revalidateTag(`post-${id}`);
  revalidateTag("posts");
  revalidatePath("/posts");
  revalidatePath("/blog");

  return { success: true };
}

// Server Action: Delete post
export async function deletePost(id: string) {
  const res = await fetch(`${process.env.API_URL}/posts/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    return { error: "Failed to delete" };
  }

  revalidateTag("posts");
  revalidatePath("/posts");
  revalidatePath("/blog");

  redirect("/posts");
}

// app/posts/page.tsx - Posts list with ISR
import { Suspense } from "react";

// Fetch with ISR - revalidate every 60 seconds
async function getPosts(status?: string) {
  const params = status ? `?status=${status}` : "";
  const res = await fetch(`${process.env.API_URL}/posts${params}`, {
    next: {
      revalidate: 60, // ISR: regenerate at most every 60 seconds
      tags: ["posts"], // Can be revalidated on-demand with revalidateTag
    },
  });
  return res.json() as Promise<{ posts: Post[]; total: number }>;
}

export default function PostsPage({
  searchParams,
}: {
  searchParams: { status?: string; page?: string };
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Posts</h1>
        <a
          href="/posts/new"
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          New Post
        </a>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-4 mb-6 border-b">
        {[
          { label: "All", value: undefined },
          { label: "Published", value: "published" },
          { label: "Drafts", value: "draft" },
          { label: "Archived", value: "archived" },
        ].map((tab) => (
          <a
            key={tab.label}
            href={tab.value ? `/posts?status=${tab.value}` : "/posts"}
            className={`pb-2 px-1 border-b-2 ${
              searchParams.status === tab.value
                ? "border-blue-600 text-blue-600 font-medium"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </a>
        ))}
      </div>

      {/* Posts list with streaming */}
      <Suspense fallback={<PostsListSkeleton />}>
        <PostsList status={searchParams.status} />
      </Suspense>
    </div>
  );
}

async function PostsList({ status }: { status?: string }) {
  const { posts, total } = await getPosts(status);

  if (posts.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg">No posts found</p>
        <a href="/posts/new" className="text-blue-600 hover:underline mt-2 inline-block">
          Create your first post
        </a>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm text-gray-500 mb-4">{total} posts</p>
      <div className="space-y-3">
        {posts.map((post) => (
          <a
            key={post.id}
            href={`/posts/${post.id}`}
            className="block bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex justify-between items-start">
              <div>
                <h2 className="font-semibold text-lg">{post.title}</h2>
                <p className="text-gray-500 text-sm mt-1 line-clamp-2">
                  {post.content.slice(0, 150)}...
                </p>
              </div>
              <span
                className={`px-2 py-1 rounded text-xs font-medium ${
                  post.status === "published"
                    ? "bg-green-100 text-green-700"
                    : post.status === "draft"
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-gray-100 text-gray-700"
                }`}
              >
                {post.status}
              </span>
            </div>
            <div className="mt-3 text-xs text-gray-400">
              Updated {new Date(post.updatedAt).toLocaleDateString()}
              {post.publishedAt && (
                <span className="ml-4">
                  Published {new Date(post.publishedAt).toLocaleDateString()}
                </span>
              )}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function PostsListSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="bg-white rounded-lg shadow p-4">
          <div className="h-5 bg-gray-200 rounded w-2/3 mb-2" />
          <div className="h-4 bg-gray-100 rounded w-full mb-1" />
          <div className="h-4 bg-gray-100 rounded w-3/4" />
        </div>
      ))}
    </div>
  );
}

// app/api/revalidate/route.ts - On-demand revalidation webhook
export async function POST_REVALIDATE(request: NextRequest) {
  const secret = request.headers.get("x-revalidation-secret");
  if (secret !== process.env.REVALIDATION_SECRET) {
    return NextResponse.json({ error: "Invalid secret" }, { status: 401 });
  }

  const body = await request.json();
  const { tag, path } = body;

  if (tag) {
    revalidateTag(tag);
  }
  if (path) {
    revalidatePath(path);
  }

  return NextResponse.json({ revalidated: true, now: Date.now() });
}
'''),
]
