/**
 * Tailoring a resume to a posting.
 *
 * The shape mirrors the backend deliberately: every bullet carries its original alongside what is
 * shown, and a refused rewrite carries what was refused and why. The interface's claim is "nothing
 * was invented, and here is the evidence" — a response that only returned final text could not
 * support it.
 *
 * The response also carries the assembled document, which is what the student prints. It is built on
 * the server so the browser never has to stitch bullets back into a resume it fetched separately —
 * two payloads that can disagree about which bullet belongs to which job, with a student sending an
 * employer a line filed under the wrong employer.
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
  /** No rewrite was attempted: no answer came back for this line. Not a verdict on the sentence. */
  unavailable: boolean;
}

export interface DocumentBullet {
  text: string;
  /** The student approved a rewrite and it is in the text above. */
  applied: boolean;
  /** A rewrite exists and has not been approved, so the text above is still the original. */
  pending: boolean;
  /** A rewrite was attempted and the validator refused it. */
  refused: boolean;
}

export interface DocumentExperience {
  employer: string;
  title: string;
  dates: string;
  bullets: DocumentBullet[];
}

export interface DocumentProject {
  name: string;
  dates: string;
  bullets: DocumentBullet[];
}

export interface DocumentEducation {
  institution: string;
  credential: string;
  dates: string;
}

export interface TailoredDocument {
  name: string;
  email: string;
  links: Record<string, string>;
  summary: string;
  skills: string[];
  experience: DocumentExperience[];
  /** Often the strongest part of a graduate resume, and tailored on the same terms. */
  projects: DocumentProject[];
  education: DocumentEducation[];
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
  /** Empty means the document below is entirely the student's own writing. */
  approved_bullet_ids: string[];
  document: TailoredDocument;
}

export interface BulletFeedback {
  bullet_id: string;
  instruction: string;
}

export const createTailoring = (jobId: number) =>
  api.post<TailoredResume>(`/api/v1/jobs/${jobId}/tailor`, {});

export const fetchTailoring = (jobId: number) =>
  api.get<TailoredResume>(`/api/v1/jobs/${jobId}/tailor`);

/** Replace the set of approved rewrites. The whole set, so two screens cannot disagree. */
export const setApprovals = (jobId: number, approved: string[]) =>
  api.patch<TailoredResume>(`/api/v1/jobs/${jobId}/tailor/approvals`, { approved });

/**
 * Send feedback on several bullets at once.
 *
 * One request, answered with one model call, so revising six bullets costs what revising one costs.
 * The instructions cannot authorise a new fact — each result is validated against that bullet's own
 * original, and a refusal comes back naming what it tried to add.
 *
 * `approved` carries the ticks currently on screen. Feedback and approval happen together on the same
 * screen, so without sending them the server would answer with whatever it last stored and silently
 * drop approvals the student had made but not yet applied.
 */
export const reviseBullets = (
  jobId: number,
  revisions: BulletFeedback[],
  approved: string[],
) => api.post<TailoredResume>(`/api/v1/jobs/${jobId}/tailor/revise`, { revisions, approved });

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

/**
 * The document as plain text, for pasting into an application form.
 *
 * Built from the document rather than from the bullets, so it contains exactly what the student
 * approved — the same words the printed page shows. A copy button that emitted every proposed rewrite
 * regardless of approval would hand over text the student had declined.
 */
export function asPlainText(tailored: TailoredResume): string {
  const doc = tailored.document;
  const lines: string[] = [];

  if (doc.name) lines.push(doc.name);
  if (doc.email) lines.push(doc.email);
  if (doc.summary) lines.push("", doc.summary);

  if (doc.experience.length > 0) {
    lines.push("", "EXPERIENCE");
    for (const entry of doc.experience) {
      lines.push("", `${entry.title}, ${entry.employer}${entry.dates ? ` (${entry.dates})` : ""}`);
      for (const bullet of entry.bullets) lines.push(`• ${bullet.text}`);
    }
  }

  if (doc.projects.length > 0) {
    lines.push("", "PROJECTS");
    for (const entry of doc.projects) {
      lines.push("", `${entry.name}${entry.dates ? ` (${entry.dates})` : ""}`);
      for (const bullet of entry.bullets) lines.push(`• ${bullet.text}`);
    }
  }

  if (doc.education.length > 0) {
    lines.push("", "EDUCATION");
    for (const entry of doc.education) {
      lines.push(
        `${entry.credential}${entry.credential && entry.institution ? ", " : ""}${entry.institution}${entry.dates ? ` (${entry.dates})` : ""}`,
      );
    }
  }

  if (doc.skills.length > 0) lines.push("", "SKILLS", doc.skills.join(", "));

  return lines.join("\n");
}

export const tailoringKeys = {
  tailoring: (jobId: number) => ["tailoring", jobId] as const,
};
