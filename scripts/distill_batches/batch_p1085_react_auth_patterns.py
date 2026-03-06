"""
Batch p1085: React authentication UI patterns.
Protected routes, auth context with token refresh, session management, social login, role-based access control.
"""

PAIRS = [
    (
        "react/auth-patterns",
        r'''Build a complete React authentication context with TypeScript that handles JWT token storage, automatic refresh before expiry, and provides login/logout/signup methods. Include proper error handling and loading states.''',
        r'''A production-grade auth context with automatic token refresh:

```typescript
import React, { createContext, useContext, useCallback, useEffect, useRef, useState } from "react";

interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "moderator";
  avatarUrl?: string;
}

interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // Unix timestamp in ms
}

interface AuthState {
  user: User | null;
  tokens: AuthTokens | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (data: SignupData) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  getAccessToken: () => Promise<string>;
}

interface SignupData {
  name: string;
  email: string;
  password: string;
}

interface AuthResponse {
  user: User;
  accessToken: string;
  refreshToken: string;
  expiresIn: number; // seconds
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_STORAGE_KEY = "auth_tokens";
const REFRESH_BUFFER_MS = 60_000; // Refresh 1 minute before expiry

function storeTokens(tokens: AuthTokens): void {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
  } catch {
    // Storage full or unavailable - proceed without persistence
  }
}

function loadTokens(): AuthTokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!raw) return null;
    const tokens = JSON.parse(raw) as AuthTokens;
    if (tokens.expiresAt < Date.now()) {
      // Access token expired, but refresh token might still work
      return tokens;
    }
    return tokens;
  } catch {
    return null;
  }
}

function clearTokens(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(`/api/auth${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ message: "Request failed" }));
    throw new AuthError(body.message || resp.statusText, resp.status);
  }

  return resp.json() as Promise<T>;
}

class AuthError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "AuthError";
  }
}

function parseAuthResponse(resp: AuthResponse): { user: User; tokens: AuthTokens } {
  return {
    user: resp.user,
    tokens: {
      accessToken: resp.accessToken,
      refreshToken: resp.refreshToken,
      expiresAt: Date.now() + resp.expiresIn * 1000,
    },
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    tokens: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const refreshTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const refreshPromiseRef = useRef<Promise<AuthTokens> | null>(null);

  const setAuthenticated = useCallback((user: User, tokens: AuthTokens) => {
    storeTokens(tokens);
    setState({ user, tokens, isLoading: false, isAuthenticated: true });
    scheduleRefresh(tokens);
  }, []);

  const setUnauthenticated = useCallback(() => {
    clearTokens();
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    setState({ user: null, tokens: null, isLoading: false, isAuthenticated: false });
  }, []);

  function scheduleRefresh(tokens: AuthTokens) {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    const msUntilExpiry = tokens.expiresAt - Date.now();
    const refreshIn = Math.max(msUntilExpiry - REFRESH_BUFFER_MS, 0);
    refreshTimerRef.current = setTimeout(() => {
      refreshSession().catch(() => setUnauthenticated());
    }, refreshIn);
  }

  async function performRefresh(refreshToken: string): Promise<{ user: User; tokens: AuthTokens }> {
    const resp = await apiCall<AuthResponse>("/refresh", {
      method: "POST",
      body: JSON.stringify({ refreshToken }),
    });
    return parseAuthResponse(resp);
  }

  const refreshSession = useCallback(async () => {
    const currentTokens = state.tokens || loadTokens();
    if (!currentTokens?.refreshToken) {
      setUnauthenticated();
      throw new AuthError("No refresh token", 401);
    }

    // Deduplicate concurrent refresh calls
    if (!refreshPromiseRef.current) {
      refreshPromiseRef.current = (async () => {
        try {
          const { user, tokens } = await performRefresh(currentTokens.refreshToken);
          setAuthenticated(user, tokens);
          return tokens;
        } finally {
          refreshPromiseRef.current = null;
        }
      })();
    }

    return refreshPromiseRef.current;
  }, [state.tokens, setAuthenticated, setUnauthenticated]);

  const getAccessToken = useCallback(async (): Promise<string> => {
    const tokens = state.tokens || loadTokens();
    if (!tokens) throw new AuthError("Not authenticated", 401);

    // If token expires within the buffer window, refresh first
    if (tokens.expiresAt - Date.now() < REFRESH_BUFFER_MS) {
      const newTokens = await refreshSession();
      return newTokens.accessToken;
    }

    return tokens.accessToken;
  }, [state.tokens, refreshSession]);

  const login = useCallback(async (email: string, password: string) => {
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const resp = await apiCall<AuthResponse>("/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const { user, tokens } = parseAuthResponse(resp);
      setAuthenticated(user, tokens);
    } catch (err) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw err;
    }
  }, [setAuthenticated]);

  const signup = useCallback(async (data: SignupData) => {
    setState((prev) => ({ ...prev, isLoading: true }));
    try {
      const resp = await apiCall<AuthResponse>("/signup", {
        method: "POST",
        body: JSON.stringify(data),
      });
      const { user, tokens } = parseAuthResponse(resp);
      setAuthenticated(user, tokens);
    } catch (err) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw err;
    }
  }, [setAuthenticated]);

  const logout = useCallback(async () => {
    try {
      const tokens = state.tokens || loadTokens();
      if (tokens?.refreshToken) {
        await apiCall("/logout", {
          method: "POST",
          body: JSON.stringify({ refreshToken: tokens.refreshToken }),
        }).catch(() => {});
      }
    } finally {
      setUnauthenticated();
    }
  }, [state.tokens, setUnauthenticated]);

  // Initialize from stored tokens
  useEffect(() => {
    const tokens = loadTokens();
    if (!tokens) {
      setState((prev) => ({ ...prev, isLoading: false }));
      return;
    }

    performRefresh(tokens.refreshToken)
      .then(({ user, tokens: newTokens }) => setAuthenticated(user, newTokens))
      .catch(() => setUnauthenticated());
  }, []);

  return (
    <AuthContext.Provider
      value={{ ...state, login, signup, logout, refreshSession, getAccessToken }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// Authenticated fetch helper
export function useAuthFetch() {
  const { getAccessToken } = useAuth();

  return useCallback(
    async (url: string, init: RequestInit = {}): Promise<Response> => {
      const token = await getAccessToken();
      return fetch(url, {
        ...init,
        headers: {
          ...init.headers,
          Authorization: `Bearer ${token}`,
        },
      });
    },
    [getAccessToken]
  );
}
```

The context handles the full auth lifecycle: initialization from localStorage, automatic token refresh scheduled before expiry, deduplication of concurrent refresh calls via a shared promise ref, and a `getAccessToken` helper that components and fetch wrappers can call to always get a valid token.'''
    ),
    (
        "react/auth-patterns",
        r'''<think>
Protected routes need to handle several cases: loading state during auth check, redirect to login for unauthenticated users, redirect away from login for authenticated users, and role-based route guards. I should show a pattern that works with React Router v6 and handles the loading/redirect edge cases cleanly.
</think>
Implement protected route components for React Router v6 that handle authentication guards, role-based access control, and redirect logic. Include loading states, redirect preservation, and nested route support.''',
        r'''Protected route guards with role-based access and redirect handling:

```typescript
import React, { Suspense } from "react";
import {
  Navigate,
  Outlet,
  useLocation,
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";
import { useAuth } from "./auth-context";

// Loading fallback
function AuthLoadingScreen() {
  return (
    <div role="status" aria-label="Checking authentication" style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100vh",
    }}>
      <div>
        <div className="spinner" aria-hidden="true" />
        <p>Verifying your session...</p>
      </div>
    </div>
  );
}

// Access denied page
function AccessDenied() {
  return (
    <div role="alert" style={{ padding: "2rem", textAlign: "center" }}>
      <h1>Access Denied</h1>
      <p>You do not have permission to view this page.</p>
      <a href="/">Return to home</a>
    </div>
  );
}

// Core protected route - requires authentication
interface ProtectedRouteProps {
  children?: React.ReactNode;
  fallback?: React.ReactNode;
}

function RequireAuth({ children, fallback }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <>{fallback || <AuthLoadingScreen />}</>;
  }

  if (!isAuthenticated) {
    // Preserve the attempted URL for post-login redirect
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }

  return <>{children || <Outlet />}</>;
}

// Role-based route guard
type UserRole = "admin" | "user" | "moderator";

interface RequireRoleProps extends ProtectedRouteProps {
  roles: UserRole[];
  deniedComponent?: React.ReactNode;
}

function RequireRole({ roles, children, fallback, deniedComponent }: RequireRoleProps) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <>{fallback || <AuthLoadingScreen />}</>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }

  if (!user || !roles.includes(user.role)) {
    return <>{deniedComponent || <AccessDenied />}</>;
  }

  return <>{children || <Outlet />}</>;
}

// Redirect authenticated users away from login/signup pages
function RedirectAuthenticated({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <AuthLoadingScreen />;
  }

  if (isAuthenticated) {
    // Redirect to the page they came from, or default to dashboard
    const from = (location.state as { from?: string })?.from || "/dashboard";
    return <Navigate to={from} replace />;
  }

  return <>{children}</>;
}

// Permission-based guard (more granular than roles)
type Permission = "users:read" | "users:write" | "posts:read" | "posts:write" | "admin:settings";

const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  admin: ["users:read", "users:write", "posts:read", "posts:write", "admin:settings"],
  moderator: ["users:read", "posts:read", "posts:write"],
  user: ["posts:read"],
};

function usePermissions(): { hasPermission: (p: Permission) => boolean; hasAny: (ps: Permission[]) => boolean } {
  const { user } = useAuth();

  const permissions = user ? ROLE_PERMISSIONS[user.role] : [];

  return {
    hasPermission: (p: Permission) => permissions.includes(p),
    hasAny: (ps: Permission[]) => ps.some((p) => permissions.includes(p)),
  };
}

interface RequirePermissionProps extends ProtectedRouteProps {
  permissions: Permission[];
  requireAll?: boolean;
  deniedComponent?: React.ReactNode;
}

function RequirePermission({
  permissions: required,
  requireAll = false,
  children,
  deniedComponent,
}: RequirePermissionProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const { hasPermission, hasAny } = usePermissions();
  const location = useLocation();

  if (isLoading) return <AuthLoadingScreen />;
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  const hasAccess = requireAll
    ? required.every((p) => hasPermission(p))
    : hasAny(required);

  if (!hasAccess) return <>{deniedComponent || <AccessDenied />}</>;

  return <>{children || <Outlet />}</>;
}

// Lazy-loaded page components
const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const AdminPanel = React.lazy(() => import("./pages/AdminPanel"));
const UserManagement = React.lazy(() => import("./pages/UserManagement"));
const LoginPage = React.lazy(() => import("./pages/LoginPage"));
const SignupPage = React.lazy(() => import("./pages/SignupPage"));
const ProfilePage = React.lazy(() => import("./pages/ProfilePage"));
const PostsPage = React.lazy(() => import("./pages/PostsPage"));

// Router definition with all guard types
const router = createBrowserRouter([
  {
    path: "/",
    children: [
      // Public routes that redirect if already logged in
      {
        path: "login",
        element: (
          <RedirectAuthenticated>
            <Suspense fallback={<AuthLoadingScreen />}>
              <LoginPage />
            </Suspense>
          </RedirectAuthenticated>
        ),
      },
      {
        path: "signup",
        element: (
          <RedirectAuthenticated>
            <Suspense fallback={<AuthLoadingScreen />}>
              <SignupPage />
            </Suspense>
          </RedirectAuthenticated>
        ),
      },

      // Authenticated routes
      {
        element: <RequireAuth />,
        children: [
          {
            path: "dashboard",
            element: (
              <Suspense fallback={null}>
                <Dashboard />
              </Suspense>
            ),
          },
          {
            path: "profile",
            element: (
              <Suspense fallback={null}>
                <ProfilePage />
              </Suspense>
            ),
          },
          {
            path: "posts",
            element: (
              <RequirePermission permissions={["posts:read"]}>
                <Suspense fallback={null}>
                  <PostsPage />
                </Suspense>
              </RequirePermission>
            ),
          },
        ],
      },

      // Admin-only routes
      {
        element: <RequireRole roles={["admin"]} />,
        children: [
          {
            path: "admin",
            element: (
              <Suspense fallback={null}>
                <AdminPanel />
              </Suspense>
            ),
          },
          {
            path: "admin/users",
            element: (
              <RequirePermission permissions={["users:read", "users:write"]} requireAll>
                <Suspense fallback={null}>
                  <UserManagement />
                </Suspense>
              </RequirePermission>
            ),
          },
        ],
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

The guards compose at multiple levels: `RequireAuth` for basic authentication, `RequireRole` for role-based access, and `RequirePermission` for fine-grained permission checks. Each guard preserves the original URL in location state so the login page can redirect back after successful authentication. The `RedirectAuthenticated` wrapper prevents logged-in users from seeing auth pages.'''
    ),
    (
        "react/auth-patterns",
        r'''Implement a React session management system with idle timeout detection, multi-tab synchronization, and session extension prompts. The system should log users out after inactivity across all tabs and show a warning dialog before timeout.''',
        r'''Session management with idle detection, cross-tab sync, and timeout warning:

```typescript
import React, { createContext, useContext, useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./auth-context";

interface SessionConfig {
  idleTimeoutMs: number;      // Total idle timeout (e.g., 15 minutes)
  warningBeforeMs: number;    // Show warning this long before timeout (e.g., 2 minutes)
  checkIntervalMs: number;    // How often to check idle state (e.g., 30 seconds)
  activityEvents: string[];   // DOM events that reset idle timer
}

const DEFAULT_CONFIG: SessionConfig = {
  idleTimeoutMs: 15 * 60 * 1000,
  warningBeforeMs: 2 * 60 * 1000,
  checkIntervalMs: 30 * 1000,
  activityEvents: ["mousedown", "keydown", "scroll", "touchstart", "pointermove"],
};

interface SessionContextType {
  isIdle: boolean;
  showWarning: boolean;
  remainingMs: number;
  extendSession: () => void;
}

const SessionContext = createContext<SessionContextType | null>(null);

const LAST_ACTIVITY_KEY = "session_last_activity";
const SESSION_LOGOUT_KEY = "session_logout_signal";

function getLastActivity(): number {
  const stored = localStorage.getItem(LAST_ACTIVITY_KEY);
  return stored ? parseInt(stored, 10) : Date.now();
}

function setLastActivity(time: number): void {
  localStorage.setItem(LAST_ACTIVITY_KEY, String(time));
}

export function SessionProvider({
  children,
  config = DEFAULT_CONFIG,
}: {
  children: React.ReactNode;
  config?: Partial<SessionConfig>;
}) {
  const mergedConfig = { ...DEFAULT_CONFIG, ...config };
  const { isAuthenticated, logout } = useAuth();
  const [showWarning, setShowWarning] = useState(false);
  const [remainingMs, setRemainingMs] = useState(mergedConfig.idleTimeoutMs);
  const [isIdle, setIsIdle] = useState(false);
  const checkIntervalRef = useRef<ReturnType<typeof setInterval>>();
  const countdownRef = useRef<ReturnType<typeof setInterval>>();

  // Record activity
  const recordActivity = useCallback(() => {
    const now = Date.now();
    setLastActivity(now);
    setShowWarning(false);
    setIsIdle(false);
    setRemainingMs(mergedConfig.idleTimeoutMs);
  }, [mergedConfig.idleTimeoutMs]);

  // Extend session explicitly (from warning dialog)
  const extendSession = useCallback(() => {
    recordActivity();
  }, [recordActivity]);

  // Check idle state periodically
  const checkIdleState = useCallback(() => {
    if (!isAuthenticated) return;

    const lastActivity = getLastActivity();
    const elapsed = Date.now() - lastActivity;
    const remaining = mergedConfig.idleTimeoutMs - elapsed;

    if (remaining <= 0) {
      // Session expired - log out
      setIsIdle(true);
      setShowWarning(false);
      logout();
      // Signal other tabs
      localStorage.setItem(SESSION_LOGOUT_KEY, String(Date.now()));
      return;
    }

    setRemainingMs(remaining);

    if (remaining <= mergedConfig.warningBeforeMs) {
      setShowWarning(true);
    }
  }, [isAuthenticated, mergedConfig, logout]);

  // Set up activity listeners
  useEffect(() => {
    if (!isAuthenticated) return;

    // Throttled activity handler
    let lastRecorded = 0;
    const throttleMs = 5000;

    function handleActivity() {
      const now = Date.now();
      if (now - lastRecorded > throttleMs) {
        lastRecorded = now;
        recordActivity();
      }
    }

    for (const event of mergedConfig.activityEvents) {
      document.addEventListener(event, handleActivity, { passive: true });
    }

    // Initialize last activity
    recordActivity();

    return () => {
      for (const event of mergedConfig.activityEvents) {
        document.removeEventListener(event, handleActivity);
      }
    };
  }, [isAuthenticated, mergedConfig.activityEvents, recordActivity]);

  // Periodic idle check
  useEffect(() => {
    if (!isAuthenticated) {
      if (checkIntervalRef.current) clearInterval(checkIntervalRef.current);
      return;
    }

    checkIntervalRef.current = setInterval(checkIdleState, mergedConfig.checkIntervalMs);
    return () => {
      if (checkIntervalRef.current) clearInterval(checkIntervalRef.current);
    };
  }, [isAuthenticated, checkIdleState, mergedConfig.checkIntervalMs]);

  // Countdown timer when warning is shown
  useEffect(() => {
    if (!showWarning) {
      if (countdownRef.current) clearInterval(countdownRef.current);
      return;
    }

    countdownRef.current = setInterval(() => {
      const lastActivity = getLastActivity();
      const remaining = mergedConfig.idleTimeoutMs - (Date.now() - lastActivity);
      setRemainingMs(Math.max(0, remaining));

      if (remaining <= 0) {
        logout();
        localStorage.setItem(SESSION_LOGOUT_KEY, String(Date.now()));
      }
    }, 1000);

    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [showWarning, mergedConfig.idleTimeoutMs, logout]);

  // Cross-tab synchronization via storage events
  useEffect(() => {
    function handleStorageChange(e: StorageEvent) {
      if (e.key === SESSION_LOGOUT_KEY && e.newValue) {
        // Another tab triggered logout
        logout();
      }
      if (e.key === LAST_ACTIVITY_KEY && e.newValue) {
        // Another tab recorded activity - update local state
        const remaining = mergedConfig.idleTimeoutMs - (Date.now() - parseInt(e.newValue, 10));
        if (remaining > mergedConfig.warningBeforeMs) {
          setShowWarning(false);
        }
        setRemainingMs(Math.max(0, remaining));
      }
    }

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [mergedConfig, logout]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (checkIntervalRef.current) clearInterval(checkIntervalRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, []);

  return (
    <SessionContext.Provider value={{ isIdle, showWarning, remainingMs, extendSession }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextType {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}

// Session warning dialog component
export function SessionTimeoutWarning() {
  const { showWarning, remainingMs, extendSession } = useSession();
  const { logout } = useAuth();

  if (!showWarning) return null;

  const minutes = Math.floor(remainingMs / 60000);
  const seconds = Math.floor((remainingMs % 60000) / 1000);
  const timeDisplay = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="session-timeout-title"
      aria-describedby="session-timeout-desc"
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        backgroundColor: "rgba(0,0,0,0.5)",
      }}
    >
      <div style={{
        background: "white", borderRadius: "8px", padding: "2rem",
        maxWidth: "400px", width: "90%", boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
      }}>
        <h2 id="session-timeout-title" style={{ margin: "0 0 0.5rem" }}>
          Session Expiring
        </h2>
        <p id="session-timeout-desc" style={{ marginBottom: "1.5rem" }}>
          Your session will expire in <strong>{timeDisplay}</strong> due to inactivity.
          Would you like to stay signed in?
        </p>
        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button
            onClick={logout}
            style={{
              padding: "0.5rem 1rem", border: "1px solid #ccc",
              borderRadius: "4px", background: "white", cursor: "pointer",
            }}
          >
            Sign Out
          </button>
          <button
            onClick={extendSession}
            autoFocus
            style={{
              padding: "0.5rem 1rem", border: "none", borderRadius: "4px",
              background: "#2563eb", color: "white", cursor: "pointer",
            }}
          >
            Stay Signed In
          </button>
        </div>
      </div>
    </div>
  );
}

// App integration
function App() {
  return (
    <SessionProvider config={{ idleTimeoutMs: 15 * 60 * 1000, warningBeforeMs: 2 * 60 * 1000 }}>
      <SessionTimeoutWarning />
      <main>{/* App routes */}</main>
    </SessionProvider>
  );
}
```

The session system uses `localStorage` for cross-tab communication: all tabs share the same `lastActivity` timestamp, and a `storage` event listener ensures that activity in one tab resets the timer in all others. The logout signal also propagates across tabs. Activity detection is throttled to avoid excessive writes.'''
    ),
    (
        "react/auth-patterns",
        r'''<think>
Social login integration in React. I need to show OAuth flow handling - the redirect-based flow with PKCE for security. Key pieces:
1. OAuth configuration for multiple providers
2. PKCE challenge generation
3. Redirect flow with state parameter for CSRF protection
4. Callback handler that exchanges code for tokens
5. Provider-specific button components

I should show Google and GitHub as examples since they're the most common.
</think>
Build a React social login system supporting Google and GitHub OAuth with PKCE flow. Include provider configuration, secure state management, callback handling, and reusable social login button components.''',
        r'''Social OAuth login with PKCE, state verification, and multi-provider support:

```typescript
import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "./auth-context";

// Provider configuration
interface OAuthProvider {
  name: string;
  clientId: string;
  authUrl: string;
  tokenUrl: string;
  scopes: string[];
  icon: string;
}

const providers: Record<string, OAuthProvider> = {
  google: {
    name: "Google",
    clientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || "",
    authUrl: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenUrl: "/api/auth/oauth/google/callback",
    scopes: ["openid", "email", "profile"],
    icon: "G",
  },
  github: {
    name: "GitHub",
    clientId: import.meta.env.VITE_GITHUB_CLIENT_ID || "",
    authUrl: "https://github.com/login/oauth/authorize",
    tokenUrl: "/api/auth/oauth/github/callback",
    scopes: ["read:user", "user:email"],
    icon: "GH",
  },
};

// PKCE helpers
async function generateCodeVerifier(): Promise<string> {
  const buffer = new Uint8Array(32);
  crypto.getRandomValues(buffer);
  return base64UrlEncode(buffer);
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return base64UrlEncode(new Uint8Array(digest));
}

function base64UrlEncode(buffer: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < buffer.byteLength; i++) {
    binary += String.fromCharCode(buffer[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function generateState(): string {
  const buffer = new Uint8Array(16);
  crypto.getRandomValues(buffer);
  return base64UrlEncode(buffer);
}

// Storage for OAuth flow state
const OAUTH_STATE_KEY = "oauth_state";
const OAUTH_VERIFIER_KEY = "oauth_verifier";
const OAUTH_PROVIDER_KEY = "oauth_provider";
const OAUTH_REDIRECT_KEY = "oauth_redirect_to";

interface OAuthFlowState {
  state: string;
  codeVerifier: string;
  provider: string;
  redirectTo: string;
}

function storeFlowState(flow: OAuthFlowState): void {
  sessionStorage.setItem(OAUTH_STATE_KEY, flow.state);
  sessionStorage.setItem(OAUTH_VERIFIER_KEY, flow.codeVerifier);
  sessionStorage.setItem(OAUTH_PROVIDER_KEY, flow.provider);
  sessionStorage.setItem(OAUTH_REDIRECT_KEY, flow.redirectTo);
}

function loadFlowState(): OAuthFlowState | null {
  const state = sessionStorage.getItem(OAUTH_STATE_KEY);
  const codeVerifier = sessionStorage.getItem(OAUTH_VERIFIER_KEY);
  const provider = sessionStorage.getItem(OAUTH_PROVIDER_KEY);
  const redirectTo = sessionStorage.getItem(OAUTH_REDIRECT_KEY);

  if (!state || !codeVerifier || !provider) return null;
  return { state, codeVerifier, provider, redirectTo: redirectTo || "/dashboard" };
}

function clearFlowState(): void {
  sessionStorage.removeItem(OAUTH_STATE_KEY);
  sessionStorage.removeItem(OAUTH_VERIFIER_KEY);
  sessionStorage.removeItem(OAUTH_PROVIDER_KEY);
  sessionStorage.removeItem(OAUTH_REDIRECT_KEY);
}

// Initiate OAuth flow
async function initiateOAuth(providerKey: string, redirectTo: string = "/dashboard"): Promise<void> {
  const provider = providers[providerKey];
  if (!provider) throw new Error(`Unknown OAuth provider: ${providerKey}`);

  const state = generateState();
  const codeVerifier = await generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);

  storeFlowState({ state, codeVerifier, provider: providerKey, redirectTo });

  const params = new URLSearchParams({
    client_id: provider.clientId,
    redirect_uri: `${window.location.origin}/auth/callback`,
    response_type: "code",
    scope: provider.scopes.join(" "),
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });

  // Provider-specific params
  if (providerKey === "google") {
    params.set("access_type", "offline");
    params.set("prompt", "consent");
  }

  window.location.href = `${provider.authUrl}?${params.toString()}`;
}

// Social login button component
interface SocialButtonProps {
  provider: string;
  redirectTo?: string;
  className?: string;
}

export function SocialLoginButton({ provider: providerKey, redirectTo, className }: SocialButtonProps) {
  const provider = providers[providerKey];
  const [isLoading, setIsLoading] = useState(false);

  if (!provider) return null;

  async function handleClick() {
    setIsLoading(true);
    try {
      await initiateOAuth(providerKey, redirectTo);
    } catch (err) {
      setIsLoading(false);
      console.error("OAuth initiation failed:", err);
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={isLoading}
      className={className}
      style={{
        display: "flex", alignItems: "center", gap: "0.75rem",
        padding: "0.75rem 1.5rem", border: "1px solid #d1d5db",
        borderRadius: "6px", background: "white", cursor: "pointer",
        fontSize: "0.875rem", fontWeight: 500, width: "100%",
        justifyContent: "center", opacity: isLoading ? 0.6 : 1,
      }}
      aria-label={`Sign in with ${provider.name}`}
    >
      <span style={{ fontWeight: 700, fontSize: "1rem" }}>{provider.icon}</span>
      <span>{isLoading ? "Redirecting..." : `Continue with ${provider.name}`}</span>
    </button>
  );
}

// OAuth callback page
export function OAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      const code = searchParams.get("code");
      const returnedState = searchParams.get("state");
      const oauthError = searchParams.get("error");

      if (oauthError) {
        setError(`OAuth error: ${searchParams.get("error_description") || oauthError}`);
        clearFlowState();
        return;
      }

      if (!code || !returnedState) {
        setError("Missing authorization code or state parameter");
        clearFlowState();
        return;
      }

      const flow = loadFlowState();
      if (!flow) {
        setError("OAuth session expired. Please try signing in again.");
        return;
      }

      // Verify state to prevent CSRF
      if (returnedState !== flow.state) {
        setError("Invalid OAuth state. This may be a CSRF attack.");
        clearFlowState();
        return;
      }

      const provider = providers[flow.provider];
      if (!provider) {
        setError("Unknown OAuth provider");
        clearFlowState();
        return;
      }

      try {
        // Exchange code for tokens via backend
        const resp = await fetch(provider.tokenUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code,
            codeVerifier: flow.codeVerifier,
            redirectUri: `${window.location.origin}/auth/callback`,
          }),
        });

        if (!resp.ok) {
          const body = await resp.json().catch(() => ({ message: "Token exchange failed" }));
          throw new Error(body.message);
        }

        const data = await resp.json();
        // The backend returns our own JWT tokens after verifying with the provider
        await login(data.email, data.accessToken);

        clearFlowState();
        navigate(flow.redirectTo, { replace: true });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Authentication failed");
        clearFlowState();
      }
    }

    handleCallback();
  }, [searchParams, navigate, login]);

  if (error) {
    return (
      <div role="alert" style={{ padding: "2rem", maxWidth: "400px", margin: "4rem auto" }}>
        <h2>Authentication Failed</h2>
        <p style={{ color: "#dc2626" }}>{error}</p>
        <a href="/login">Back to login</a>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <p>Completing sign in...</p>
    </div>
  );
}

// Login page with social buttons
export function LoginPage() {
  return (
    <div style={{ maxWidth: "400px", margin: "4rem auto", padding: "2rem" }}>
      <h1>Sign In</h1>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1.5rem" }}>
        <SocialLoginButton provider="google" />
        <SocialLoginButton provider="github" />
      </div>
      <div style={{ textAlign: "center", margin: "1.5rem 0", color: "#6b7280" }}>
        or sign in with email
      </div>
      {/* Email/password form here */}
    </div>
  );
}
```

The PKCE flow generates a random code verifier stored in `sessionStorage` (tab-scoped, not shared), creates a SHA-256 challenge sent to the provider, and verifies the state parameter on callback to prevent CSRF. The code exchange happens server-side to keep client secrets secure, and the backend returns application JWT tokens after validating with the OAuth provider.'''
    ),
    (
        "react/auth-patterns",
        r'''Create a React role-based access control (RBAC) system with a permission hook, conditional UI rendering based on permissions, and an admin panel for managing roles and permissions. Include TypeScript types for the permission hierarchy.''',
        r'''A complete RBAC system with permission hierarchy, hooks, and admin UI:

```typescript
import React, { createContext, useContext, useMemo, useState, useCallback } from "react";
import { useAuth } from "./auth-context";

// Permission and role type definitions
type Resource = "users" | "posts" | "comments" | "settings" | "analytics" | "billing";
type Action = "create" | "read" | "update" | "delete" | "manage";
type Permission = `${Resource}:${Action}`;

interface Role {
  id: string;
  name: string;
  description: string;
  permissions: Permission[];
  inherits?: string[]; // Role IDs this role inherits from
}

interface RBACConfig {
  roles: Record<string, Role>;
}

// Default role configuration
const defaultConfig: RBACConfig = {
  roles: {
    viewer: {
      id: "viewer",
      name: "Viewer",
      description: "Read-only access to public resources",
      permissions: ["posts:read", "comments:read", "analytics:read"],
    },
    editor: {
      id: "editor",
      name: "Editor",
      description: "Can create and edit content",
      permissions: ["posts:create", "posts:update", "comments:create", "comments:update", "comments:delete"],
      inherits: ["viewer"],
    },
    moderator: {
      id: "moderator",
      name: "Moderator",
      description: "Can manage content and users",
      permissions: ["posts:delete", "comments:delete", "users:read", "users:update"],
      inherits: ["editor"],
    },
    admin: {
      id: "admin",
      name: "Administrator",
      description: "Full system access",
      permissions: [
        "users:manage", "posts:manage", "comments:manage",
        "settings:manage", "analytics:manage", "billing:manage",
      ],
    },
  },
};

// Resolve all permissions including inherited ones
function resolvePermissions(roleId: string, config: RBACConfig, visited = new Set<string>()): Set<Permission> {
  if (visited.has(roleId)) return new Set(); // Prevent circular inheritance
  visited.add(roleId);

  const role = config.roles[roleId];
  if (!role) return new Set();

  const perms = new Set<Permission>(role.permissions);

  // Expand "manage" into all CRUD actions
  for (const perm of role.permissions) {
    if (perm.endsWith(":manage")) {
      const resource = perm.split(":")[0] as Resource;
      const actions: Action[] = ["create", "read", "update", "delete", "manage"];
      for (const action of actions) {
        perms.add(`${resource}:${action}` as Permission);
      }
    }
  }

  // Inherit permissions from parent roles
  if (role.inherits) {
    for (const parentId of role.inherits) {
      const parentPerms = resolvePermissions(parentId, config, visited);
      for (const p of parentPerms) {
        perms.add(p);
      }
    }
  }

  return perms;
}

// RBAC Context
interface RBACContextType {
  permissions: Set<Permission>;
  userRole: string;
  can: (permission: Permission) => boolean;
  canAll: (permissions: Permission[]) => boolean;
  canAny: (permissions: Permission[]) => boolean;
  config: RBACConfig;
}

const RBACContext = createContext<RBACContextType | null>(null);

export function RBACProvider({
  children,
  config = defaultConfig,
}: {
  children: React.ReactNode;
  config?: RBACConfig;
}) {
  const { user } = useAuth();
  const userRole = user?.role || "viewer";

  const permissions = useMemo(
    () => resolvePermissions(userRole, config),
    [userRole, config]
  );

  const can = useCallback(
    (permission: Permission) => permissions.has(permission),
    [permissions]
  );

  const canAll = useCallback(
    (perms: Permission[]) => perms.every((p) => permissions.has(p)),
    [permissions]
  );

  const canAny = useCallback(
    (perms: Permission[]) => perms.some((p) => permissions.has(p)),
    [permissions]
  );

  return (
    <RBACContext.Provider value={{ permissions, userRole, can, canAll, canAny, config }}>
      {children}
    </RBACContext.Provider>
  );
}

// Hooks
export function useRBAC(): RBACContextType {
  const ctx = useContext(RBACContext);
  if (!ctx) throw new Error("useRBAC must be used within RBACProvider");
  return ctx;
}

export function usePermission(permission: Permission): boolean {
  const { can } = useRBAC();
  return can(permission);
}

// Conditional rendering components
interface CanProps {
  permission?: Permission;
  permissions?: Permission[];
  requireAll?: boolean;
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export function Can({ permission, permissions, requireAll = false, fallback = null, children }: CanProps) {
  const { can, canAll, canAny } = useRBAC();

  let hasAccess = false;
  if (permission) {
    hasAccess = can(permission);
  } else if (permissions) {
    hasAccess = requireAll ? canAll(permissions) : canAny(permissions);
  }

  return <>{hasAccess ? children : fallback}</>;
}

// Higher-order component for permission gating
function withPermission<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  permission: Permission,
  FallbackComponent?: React.ComponentType
) {
  return function PermissionGated(props: P) {
    const allowed = usePermission(permission);
    if (!allowed) {
      return FallbackComponent ? <FallbackComponent /> : null;
    }
    return <WrappedComponent {...props} />;
  };
}

// Admin panel for managing roles
interface RoleEditorProps {
  role: Role;
  allResources: Resource[];
  allActions: Action[];
  onChange: (roleId: string, permissions: Permission[]) => void;
}

function RolePermissionEditor({ role, allResources, allActions, onChange }: RoleEditorProps) {
  const currentPerms = new Set(role.permissions);

  function togglePermission(perm: Permission) {
    const updated = new Set(currentPerms);
    if (updated.has(perm)) {
      updated.delete(perm);
    } else {
      updated.add(perm);
    }
    onChange(role.id, Array.from(updated));
  }

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h3>{role.name}</h3>
      <p style={{ color: "#6b7280", fontSize: "0.875rem" }}>{role.description}</p>
      {role.inherits && (
        <p style={{ fontSize: "0.75rem", color: "#9ca3af" }}>
          Inherits from: {role.inherits.join(", ")}
        </p>
      )}
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.5rem" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #e5e7eb" }}>Resource</th>
            {allActions.map((action) => (
              <th key={action} style={{ padding: "0.5rem", borderBottom: "1px solid #e5e7eb", textAlign: "center" }}>
                {action}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allResources.map((resource) => (
            <tr key={resource}>
              <td style={{ padding: "0.5rem", borderBottom: "1px solid #f3f4f6", fontWeight: 500 }}>
                {resource}
              </td>
              {allActions.map((action) => {
                const perm = `${resource}:${action}` as Permission;
                const isChecked = currentPerms.has(perm);
                const isManaged = currentPerms.has(`${resource}:manage` as Permission) && action !== "manage";
                return (
                  <td key={action} style={{ padding: "0.5rem", borderBottom: "1px solid #f3f4f6", textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={isChecked || isManaged}
                      disabled={isManaged}
                      onChange={() => togglePermission(perm)}
                      aria-label={`${role.name} ${resource} ${action}`}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RBACAdminPanel() {
  const { config } = useRBAC();
  const [roles, setRoles] = useState<Record<string, Role>>(config.roles);

  const allResources: Resource[] = ["users", "posts", "comments", "settings", "analytics", "billing"];
  const allActions: Action[] = ["create", "read", "update", "delete", "manage"];

  function handlePermissionChange(roleId: string, permissions: Permission[]) {
    setRoles((prev) => ({
      ...prev,
      [roleId]: { ...prev[roleId], permissions },
    }));
  }

  async function saveChanges() {
    await fetch("/api/admin/roles", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roles }),
    });
  }

  return (
    <Can permission="settings:manage" fallback={<p>You do not have permission to manage roles.</p>}>
      <div style={{ maxWidth: "900px", margin: "2rem auto", padding: "1rem" }}>
        <h2>Role & Permission Management</h2>
        {Object.values(roles).map((role) => (
          <RolePermissionEditor
            key={role.id}
            role={role}
            allResources={allResources}
            allActions={allActions}
            onChange={handlePermissionChange}
          />
        ))}
        <button
          onClick={saveChanges}
          style={{
            padding: "0.75rem 1.5rem", background: "#2563eb", color: "white",
            border: "none", borderRadius: "6px", cursor: "pointer", marginTop: "1rem",
          }}
        >
          Save Changes
        </button>
      </div>
    </Can>
  );
}

// Usage in app components
function PostActions({ postId }: { postId: string }) {
  return (
    <div>
      <Can permission="posts:update">
        <button>Edit Post</button>
      </Can>
      <Can permission="posts:delete" fallback={null}>
        <button style={{ color: "red" }}>Delete Post</button>
      </Can>
    </div>
  );
}

function Sidebar() {
  return (
    <nav>
      <a href="/posts">Posts</a>
      <Can permission="analytics:read">
        <a href="/analytics">Analytics</a>
      </Can>
      <Can permission="settings:manage">
        <a href="/admin">Admin Panel</a>
      </Can>
      <Can permission="billing:manage">
        <a href="/billing">Billing</a>
      </Can>
    </nav>
  );
}
```

The RBAC system supports role inheritance (editor inherits viewer permissions), a `manage` wildcard that expands to all CRUD actions, and both declarative (`<Can>`) and imperative (`usePermission`, `useRBAC`) APIs. The admin panel renders a permission matrix grid for each role, and the entire system is protected by its own permission check.'''
    ),
]
