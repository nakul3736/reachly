/**
 * The outreach draft.
 *
 * Reachly does not send it (ADR 0004). The student is the sender, from their own address, having read
 * what goes out under their name — so this module's job ends at producing a `mailto:` link and text
 * on the clipboard.
 */

import { api } from "./auth";

export interface Outreach {
  job_id: number;
  company_name: string;
  subject: string;
  body: string;
  /** Why the message says what it says. Every specific claim in it has a line here. */
  evidence: string[];
  /**
   * True when a model wrote it from the resume and the posting and the result passed the fabrication
   * check. False when it is the assembled fallback — surfaced, because presenting a template as
   * writing is a small lie the student discovers by reading it.
   */
  written: boolean;
  apply_url: string;
  other_open_roles: number;
}

export const fetchOutreach = (jobId: number) =>
  api.get<Outreach>(`/api/v1/jobs/${jobId}/outreach`);

/** Generation is not deterministic, so this is a genuinely different email, not a retry. */
export const rewriteOutreach = (jobId: number) =>
  api.post<Outreach>(`/api/v1/jobs/${jobId}/outreach/rewrite`, {});

export const outreachKeys = {
  outreach: (jobId: number) => ["outreach", jobId] as const,
};

/**
 * A `mailto:` link the student's own mail client opens.
 *
 * `encodeURIComponent` rather than `encodeURI`: the body contains newlines and `&`, and encodeURI
 * leaves both alone, which truncates the message at the first ampersand and silently drops everything
 * after it. An email that arrives half-written is worse than one that fails to open.
 *
 * The recipient may be empty. That is a usable state — the mail client opens with the message ready
 * and the To field waiting — and it is the honest default, because Reachly is not guessing addresses.
 */
export function mailtoLink(outreach: Outreach, recipient: string): string {
  const to = encodeURIComponent(recipient.trim());
  const subject = encodeURIComponent(outreach.subject);
  const body = encodeURIComponent(outreach.body);
  return `mailto:${to}?subject=${subject}&body=${body}`;
}
