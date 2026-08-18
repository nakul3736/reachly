/**
 * Where the API lives.
 *
 * Development: empty, so requests go to `/api/v1/...` on the Vite dev server and its
 * proxy forwards them to the local backend.
 *
 * Production: the frontend is on Cloudflare Pages and the API is on Render — different
 * origins — so the full base URL is supplied at build time via `VITE_API_BASE_URL`.
 *
 * Vite inlines this at build time, not run time. Changing the variable without
 * redeploying does nothing, because the old value is already compiled into the bundle.
 *
 * Failing loudly on a production build with no base URL is deliberate: the alternative
 * is a deployed site that looks fine and quietly requests paths on its own origin,
 * which reads as "the app is broken" rather than "one variable is missing".
 */
const configured = import.meta.env.VITE_API_BASE_URL ?? "";

if (import.meta.env.PROD && !configured) {
  throw new Error(
    "VITE_API_BASE_URL is not set. Set it in the Cloudflare Pages build environment, " +
      "for example https://reachly-api-82u2.onrender.com, then redeploy.",
  );
}

/** No trailing slash, so `${API_BASE_URL}/api/v1/...` never doubles up. */
export const API_BASE_URL = configured.replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
