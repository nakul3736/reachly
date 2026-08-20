/**
 * Reading the shared job index.
 *
 * `is_verified` is carried through to the interface rather than flattened away. A posting on
 * a company's own board and one seen only on an aggregator are different claims, and this
 * product's position is that it never presents a guess as a fact.
 */
import { apiUrl } from "./api";

export interface JobSummary {
  id: number;
  source: string;
  company_name: string;
  title: string;
  location_raw: string | null;
  country: string | null;
  is_remote: boolean | null;
  role_family: string | null;
  seniority: string | null;
  posted_at: string | null;
  first_seen_at: string;
  closed_at: string | null;
  is_verified: boolean;
}

export interface JobAlias {
  source: string;
  apply_url: string;
  is_verified: boolean;
}

export interface JobDetail extends JobSummary {
  description: string;
  apply_url: string;
  /** Other listings collapsed into this one, so the match is visible rather than assumed. */
  also_seen_on: JobAlias[];
}

export interface JobFeed {
  items: JobSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface BoardStatus {
  provider: string;
  token: string;
  company_name: string;
  active: boolean;
  last_fetched_at: string | null;
  last_succeeded_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    // The backend envelope is {error: {code, message}}. Preferring its message means the
    // interface explains the actual problem rather than showing a status code.
    let message = `The request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (body?.error?.message) message = body.error.message;
    } catch {
      // Not every failure returns JSON. A cold start or a proxy error will not.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export interface JobQuery {
  seniority?: string[];
  roleFamily?: string[];
  country?: string[];
  remote?: boolean;
  q?: string;
}

export function fetchJobs(
  params: { page?: number; pageSize?: number } & JobQuery = {},
) {
  const query = new URLSearchParams();
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));
  if (params.seniority?.length) query.set("seniority", params.seniority.join(","));
  if (params.roleFamily?.length) query.set("role_family", params.roleFamily.join(","));
  if (params.country?.length) query.set("country", params.country.join(","));
  if (params.remote !== undefined) query.set("remote", String(params.remote));
  if (params.q) query.set("q", params.q);
  return getJson<JobFeed>(`/api/v1/jobs?${query.toString()}`);
}

export function fetchJob(id: number) {
  return getJson<JobDetail>(`/api/v1/jobs/${id}`);
}

export function fetchSources() {
  return getJson<{ boards: BoardStatus[] }>("/api/v1/sources");
}

export const queryKeys = {
  jobs: (page: number) => ["jobs", page] as const,
  job: (id: number) => ["job", id] as const,
  sources: () => ["sources"] as const,
};
