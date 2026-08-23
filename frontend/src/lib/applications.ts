/**
 * Application tracking.
 *
 * Every status is something the student told Reachly. It does not submit the form and does not send the
 * email (ADR 0004), so it has no way to observe an outcome — and a tracker that guessed would be wrong
 * in the direction that costs the student a follow-up.
 */

import { api } from "./auth";

export const STATUSES = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
] as const;

export type ApplicationStatus = (typeof STATUSES)[number];

/** Shown in the interface. Written as the student would say it, not as the database stores it. */
export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export interface Application {
  id: number;
  job_id: number;
  title: string;
  company_name: string;
  apply_url: string;
  status: ApplicationStatus;
  notes: string;
  tailored_resume_id: number | null;
  /** Whether a tailored version was captured at the moment they reported applying. */
  has_tailored_resume: boolean;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  /** The posting has been taken down. Flagged rather than hidden. */
  closed: boolean;
}

export interface Pipeline {
  items: Application[];
  /** Includes zeros, so the columns do not appear and vanish as the pipeline changes shape. */
  counts: Record<ApplicationStatus, number>;
}

export const fetchPipeline = () => api.get<Pipeline>("/api/v1/applications");

export const trackJob = (jobId: number, status: ApplicationStatus = "saved") =>
  api.post<Application>("/api/v1/applications", { job_id: jobId, status });

export const updateApplication = (
  id: number,
  body: { status?: ApplicationStatus; notes?: string },
) => api.patch<Application>(`/api/v1/applications/${id}`, body);

export const untrack = (id: number) => api.del(`/api/v1/applications/${id}`);

export const applicationKeys = {
  pipeline: ["applications"] as const,
};
