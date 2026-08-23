/**
 * Reading the shared job index.
 *
 * `is_verified` is carried through to the interface rather than flattened away. A posting on
 * a company's own board and one seen only on an aggregator are different claims, and this
 * product's position is that it never presents a guess as a fact.
 */
import { apiUrl } from "./api";
import { storedToken } from "./auth";

export type ComponentState = "scored" | "met" | "short" | "unstated";

/**
 * The score, decomposed. Never rendered as a bare total — ADR 0003 and the design brief both
 * require the four parts to be visible, because a single opaque number is exactly what the
 * student already gets from every job board that ignores them.
 */
export interface ScoreBreakdown {
  total: number;
  skill_points: number;
  experience_points: number;
  keyword_points: number;
  freshness_points: number;
  skill_state: ComponentState;
  experience_state: ComponentState;
  keyword_state: ComponentState;
  freshness_state: ComponentState;
  matched_skills: string[];
  missing_skills: string[];
  required_years: number | null;
  requirement_basis: string | null;
  /** The words the requirement was read from, so the number can be checked against its source. */
  requirement_phrase: string | null;
}

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
  /** Absent for an anonymous request or a student with no parsed resume. */
  score: ScoreBreakdown | null;
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
  /** False for an anonymous request or a student with no parsed resume. */
  scored: boolean;
  /** How many postings the ranking covered, when that is fewer than the total. */
  ranked_within: number | null;
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
  // The token is sent when present, and its absence is not an error. The index is public: an
  // anonymous request gets the feed unscored, a signed-in one gets scores added. Making this a
  // hard requirement would mean browsing the index required an account.
  const token = storedToken();
  const response = await fetch(apiUrl(path), {
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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
