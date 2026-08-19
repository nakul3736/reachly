/**
 * The student's own record: what they are looking for, and what Reachly read from their
 * resume.
 */

import { api } from "./auth";

export interface StudentProfile {
  name: string | null;
  target_role: string | null;
  years_experience: number | null;
  locations: string[];
  skills: string[];
  links: Record<string, string>;
  /** Field names the API says are still needed before results can be produced. */
  missing_for_results: string[];
}

export interface ResumeVersion {
  id: number;
  version: number;
  filename: string;
  byte_size: number;
  is_active: boolean;
  uploaded_at: string;
}

export interface Bullet {
  /** Content-derived, never positional. What feature 04 resolves provenance against. */
  id: string;
  text: string;
}

export interface ExperienceEntry {
  id: string;
  employer: string;
  title: string;
  /** Exactly as the resume wrote it. Normalising is the invention ADR 0006 prevents. */
  dates: string;
  bullets: Bullet[];
}

export interface EducationEntry {
  id: string;
  institution: string;
  credential: string;
  dates: string;
}

export interface ParsedResume {
  summary: string;
  experience: ExperienceEntry[];
  education: EducationEntry[];
  skills: string[];
  raw_text: string;
}

export const fetchProfile = () => api.get<StudentProfile>("/api/v1/students/me");

export const updateProfile = (changes: Partial<StudentProfile>) =>
  api.patch<StudentProfile>("/api/v1/students/me", changes);

export const fetchResumes = () => api.get<ResumeVersion[]>("/api/v1/resumes");

export const fetchParsedResume = () => api.get<ParsedResume>("/api/v1/resumes/parsed");

export function uploadResume(file: File) {
  const form = new FormData();
  form.append("file", file);
  return api.postForm<ResumeVersion>("/api/v1/resumes", form);
}

export const studentKeys = {
  profile: () => ["profile"] as const,
  resumes: () => ["resumes"] as const,
  parsed: () => ["parsed-resume"] as const,
};

/**
 * Advice for each way an upload can be refused.
 *
 * Written per code rather than shown as one generic failure, because the student's fix is
 * completely different in each case. A scanned resume needs re-exporting; a corrupt file
 * needs replacing; a too-large file needs compressing. Telling all three "upload failed"
 * leaves the student guessing.
 */
export const UPLOAD_ADVICE: Record<string, string> = {
  resume_too_large:
    "That file is over the 5 MB limit. Export it again at a lower quality, or remove images.",
  unsupported_resume_format:
    "Reachly reads PDFs. If that file came from Word, use File then Save as PDF rather than renaming it.",
  resume_unreadable:
    "That PDF has no text layer, which usually means it is a scan or a photo. Export a PDF directly from your editor instead of scanning a printout.",
  resume_parse_failed:
    "Reachly could read the text but could not identify roles and dates in it. An unusual layout can cause this — a single-column resume with clear section headings works best.",
  llm_unavailable:
    "The service that structures resumes is busy. Your file was not stored, so try again in a moment.",
};
