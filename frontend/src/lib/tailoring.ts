/**
 * Tailoring a resume to a posting.
 *
 * The shape mirrors the backend deliberately: every bullet carries its original alongside what is
 * shown, and a refused rewrite carries what was refused and why. The interface's claim is "nothing
 * was invented, and here is the evidence" — a response that only returned final text could not
 * support it.
 */
import { api } from "./auth";

export interface TailoredBullet {
  bullet_id: string;
  original: string;
  tailored: string;
  changed: boolean;
  /** Set only when a rewrite was refused by the validator. */
  rejected_reason: string | null;
  rejected_detail: string;
  rejected_text: string;
}

export interface TailoredResume {
  job_id: number;
  job_title: string;
  company_name: string;
  bullets: TailoredBullet[];
  /** Requirements the posting states that the resume does not support. */
  gaps: string[];
  changed_count: number;
  rejected_count: number;
  /** recorded | live — a fixture is a weaker claim than a model, and it is never presented as one. */
  basis: string;
  created_at: string;
}

export const createTailoring = (jobId: number) =>
  api.post<TailoredResume>(`/api/v1/jobs/${jobId}/tailor`, {});

export const fetchTailoring = (jobId: number) =>
  api.get<TailoredResume>(`/api/v1/jobs/${jobId}/tailor`);

/** Why a rewrite was refused, in the interface's voice rather than the enum's. */
export function refusalWording(reason: string, detail: string): string {
  switch (reason) {
    case "added_technology":
      return `It tried to add ${detail}, which is not in this bullet.`;
    case "added_number":
      return `It tried to add the figure ${detail}, which you never claimed.`;
    case "added_proper_noun":
      return `It tried to add ${detail}, which this bullet does not mention.`;
    case "too_long":
      return `It expanded the bullet well beyond its source (${detail}).`;
    case "empty":
      return "It returned nothing usable.";
    default:
      return "It introduced something absent from this bullet.";
  }
}

/** The whole tailored resume as plain text, for the copy button. */
export function asPlainText(tailored: TailoredResume): string {
  const lines = tailored.bullets.map((b) => `• ${b.tailored}`);
  if (tailored.gaps.length > 0) {
    lines.push("", "Not supported by this resume:", ...tailored.gaps.map((g) => `- ${g}`));
  }
  return lines.join("\n");
}

export const tailoringKeys = {
  tailoring: (jobId: number) => ["tailoring", jobId] as const,
};
