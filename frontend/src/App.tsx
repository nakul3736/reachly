import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { clearToken, storedToken } from "./lib/auth";
import Feed from "./pages/Feed";
import JobDetailPage from "./pages/JobDetail";
import Profile from "./pages/Profile";
import SignIn from "./pages/SignIn";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The index refreshes daily from an external trigger, so refetching on window focus
      // would spend requests to learn nothing.
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      // The API sleeps when idle on the free tier and the first request after that can fail
      // while the container wakes. One retry turns a cold start into a slow load rather than
      // an error screen.
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Chrome>
          <Routes>
            <Route path="/" element={<Feed />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/signin" element={<SignIn />} />
            <Route
              path="/profile"
              element={
                <RequireAccount>
                  <Profile />
                </RequireAccount>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Chrome>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

/**
 * A signed-out visitor is sent to sign in, not shown an error.
 *
 * `replace` so the back button does not bounce them straight back into a page they cannot
 * see, and the intended path is remembered so signing in continues where they were going.
 */
function RequireAccount({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  if (!storedToken()) {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/** Shared header. The feed is home, so the wordmark points there. */
function Chrome({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const signedIn = storedToken() !== null;

  // The sign-in screen carries its own back link and needs no header competing with it.
  if (location.pathname === "/signin") return <>{children}</>;

  return (
    <>
      <header className="border-b border-rule bg-paper">
        <div className="mx-auto flex w-full max-w-[1100px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link
            to="/"
            className="font-display text-[18px] font-extrabold tracking-[-0.02em] text-ink"
          >
            Reachly
          </Link>

          <nav className="flex items-center gap-1">
            <NavLink to="/" current={location.pathname === "/"}>
              Jobs
            </NavLink>
            {signedIn ? (
              <>
                <NavLink to="/profile" current={location.pathname === "/profile"}>
                  Profile
                </NavLink>
                <button
                  type="button"
                  onClick={() => {
                    clearToken();
                    queryClient.clear();
                    navigate("/");
                  }}
                  className="rounded-card px-2.5 py-1.5 text-[13px] text-slate hover:text-ink"
                >
                  Sign out
                </button>
              </>
            ) : (
              <Link
                to="/signin"
                className="rounded-card border border-ink bg-ink px-3 py-1.5 text-[13px] font-medium text-paper hover:bg-ink/90"
              >
                Sign in
              </Link>
            )}
          </nav>
        </div>
      </header>
      {children}
    </>
  );
}

function NavLink({
  to,
  current,
  children,
}: {
  to: string;
  current: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      aria-current={current ? "page" : undefined}
      className={`rounded-card px-2.5 py-1.5 text-[13px] ${
        current ? "font-medium text-ink" : "text-slate hover:text-ink"
      }`}
    >
      {children}
    </Link>
  );
}

function NotFound() {
  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pt-16 sm:px-6">
      <h1 className="font-display text-[32px] font-extrabold tracking-[-0.02em] text-ink">
        There is nothing at this address
      </h1>
      <p className="mt-3 text-[15px] text-slate">
        <Link to="/" className="underline underline-offset-4">
          Go back to the jobs
        </Link>
      </p>
    </main>
  );
}
