/**
 * Where the API lives.
 *
 * Development: empty, so requests go to `/api/v1/...` on the Vite dev server and its proxy
 * forwards them to the local backend.
 *
 * Production: the frontend is on Cloudflare Pages and the API is on Render — different
 * origins — so the full base URL is supplied at build time via `VITE_API_BASE_URL`. Vite
 * inlines it at build time, not run time, so changing the variable without redeploying does
 * nothing: the old value is already compiled into the bundle.
 *
 * The missing-variable check is deliberately made at **call time, not module scope.**
 *
 * An earlier version threw while the module was initialising. Because the bundler can prove
 * both `import.meta.env.PROD` and the inlined variable statically, it evaluated the condition,
 * saw an unconditional throw, and eliminated everything after it as unreachable — the entire
 * application. The build reported success and emitted a bundle whose last statement was that
 * throw. A guard against a blank deployed page had become the cause of one.
 *
 * Checking lazily keeps the loud, specific failure while leaving the app intact, so the error
 * surfaces in the interface's own error state instead of as a white screen.
 */
const configured = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

function missingBaseUrl(): boolean {
  return import.meta.env.PROD && configured === "";
}

/** No trailing slash, so `${apiBaseUrl()}/api/v1/...` never doubles up. */
export function apiBaseUrl(): string {
  if (missingBaseUrl()) {
    throw new Error(
      "This build has no API address. VITE_API_BASE_URL was not set when it was compiled — " +
        "set it in the Cloudflare Pages build environment, then redeploy so the value is " +
        "compiled in.",
    );
  }
  return configured;
}

export function apiUrl(path: string): string {
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
