/**
 * Signing in, and staying signed in.
 *
 * The token goes in localStorage rather than a cookie because the API is on a different
 * origin to the site — Render and Cloudflare Pages — so a same-site cookie would not be sent
 * and a cross-site one needs a shared parent domain we do not have. The tradeoff is honest:
 * localStorage is readable by any script on the page, so this is only acceptable while the
 * app ships no third-party scripts. Worth revisiting if that ever changes.
 */

import { apiUrl } from "./api";

const TOKEN_KEY = "reachly.token";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function storedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private browsing modes can refuse storage entirely. Better to behave as signed out
    // than to crash the whole application on a getter.
    return null;
  }
}

function storeToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Nothing to do. The session lasts until reload, which is worse but still usable.
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Ignored for the same reason.
  }
}

/** Thrown when the API rejects a request. Carries the backend's own code so callers can act. */
export class ApiError extends Error {
  readonly code: string | null;
  readonly status: number;

  constructor(message: string, code: string | null, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { authenticated = false }: { authenticated?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (authenticated) {
    const token = storedToken();
    if (!token) throw new ApiError("Sign in to continue.", "not_authenticated", 401);
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(apiUrl(path), { ...init, headers });

  if (!response.ok) {
    let message = `The request failed (${response.status}).`;
    let code: string | null = null;
    try {
      const body = await response.json();
      if (body?.error?.message) message = body.error.message;
      if (body?.error?.code) code = body.error.code;
    } catch {
      // A cold start or proxy error will not return the envelope.
    }
    throw new ApiError(message, code, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, {}, { authenticated: true }),
  getPublic: <T>(path: string) => request<T>(path),
  patch: <T>(path: string, body: unknown) =>
    request<T>(
      path,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      { authenticated: true },
    ),
  post: <T>(path: string, body: unknown) =>
    request<T>(
      path,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      { authenticated: true },
    ),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }, { authenticated: true }),
  // Returns 204 with no body, which `request` already handles by resolving undefined.
  del: (path: string) => request<void>(path, { method: "DELETE" }, { authenticated: true }),
};

async function authenticate(path: string, email: string, password: string): Promise<void> {
  const token = await request<TokenResponse>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  storeToken(token.access_token);
}

export const signIn = (email: string, password: string) =>
  authenticate("/api/v1/auth/login", email, password);

export const register = (email: string, password: string) =>
  authenticate("/api/v1/auth/register", email, password);

/** Published in the README, and offered on the sign-in screen so a judge never hunts. */
export const DEMO_CREDENTIALS = {
  email: "demo@reachly.app",
  password: "reachly-demo-2026",
};

/** The minimum the API enforces. Stated up front rather than discovered by being rejected. */
export const MIN_PASSWORD_LENGTH = 10;
