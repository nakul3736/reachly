/**
 * The score's working, fetched separately from the posting.
 *
 * The API returns facts, not sentences: denominators, the student's own parsed years, the words
 * that overlapped, and the constants the arithmetic used. Wording lives here because the interface
 * knows how much room it has, and because an API that returns English cannot be translated.
 *
 * Points are never recomputed in this file. Where a derivation is shown as arithmetic it is shown
 * using the numbers the server sent, next to the points the server assigned — so if the two ever
 * disagree the student sees the disagreement rather than a plausible-looking invention.
 */

import { api } from "./auth";

export type ComponentName = "skills" | "experience" | "keywords" | "freshness";

export type ComponentState = "scored" | "met" | "short" | "unstated";

export interface ScoreComponent {
  name: ComponentName;
  points: number;
  weight: number;
  state: ComponentState;
  facts: {
    asked?: number;
    matched?: number;
    required_years?: number | null;
    your_years?: number;
    basis?: string;
    phrase?: string | null;
    gap_cap_years?: number;
    preference_scale?: number;
    shared_terms?: number;
    age_days?: number | null;
    horizon_days?: number;
  };
}

export interface ScoreExplanation {
  job_id: number;
  total: number;
  components: ScoreComponent[];
  matched_skills: string[];
  missing_skills: string[];
  shared_keywords: string[];
  requirement_phrase: string | null;
  neutral_share: number;
}

export function fetchScoreExplanation(jobId: number) {
  return api.get<ScoreExplanation>(`/api/v1/jobs/${jobId}/score`);
}

export const scoreKeys = {
  explanation: (jobId: number) => ["score-explanation", jobId] as const,
};

/** What the component is called on screen, in the student's terms rather than the schema's. */
export const componentTitles: Record<ComponentName, string> = {
  skills: "Skills this posting names",
  experience: "Experience it asks for",
  keywords: "Vocabulary you share with it",
  freshness: "How recently it was posted",
};

/**
 * The derivation as a sentence, using only numbers the server sent.
 *
 * Returns the arithmetic where there is arithmetic a student can follow, and says plainly when
 * there is not. An unstated component is the case most worth wording carefully: half marks looks
 * arbitrary until you are told that the posting was silent and that silence is not scored as
 * failure.
 */
export function derivationOf(component: ScoreComponent, neutralShare: number): string {
  const { facts, points, weight, state } = component;

  if (state === "unstated") {
    const share = Math.round(neutralShare * 100);
    switch (component.name) {
      case "skills":
        return `This posting does not name any specific skills, so there is nothing to match against. An unknown scores ${share}% of ${weight} rather than zero, because you can act on a stated mismatch and cannot act on silence.`;
      case "experience":
        return `This posting never states how much experience it wants. An unknown scores ${share}% of ${weight} rather than zero — Reachly will not invent a requirement in order to fail you against it.`;
      case "freshness":
        return `This posting carries no date. Providers omit it constantly and that is not your fault, so it scores ${share}% of ${weight} rather than nothing.`;
      default:
        return `Not stated, so this scores ${share}% of ${weight} rather than zero.`;
    }
  }

  switch (component.name) {
    case "skills": {
      const asked = facts.asked ?? 0;
      const matched = facts.matched ?? 0;
      return `You have ${matched} of the ${asked} ${asked === 1 ? "skill" : "skills"} this posting names. ${matched} ÷ ${asked} of ${weight} is ${points}. The denominator is what the posting asked for, never how many skills you have — the question is whether the job's needs are met.`;
    }

    case "experience": {
      const required = facts.required_years;
      const yours = facts.your_years ?? 0;
      const cap = facts.gap_cap_years ?? 10;

      if (required === null || required === undefined) {
        return `No requirement was read from this posting.`;
      }
      if (state === "met") {
        return `It asks for ${required} ${required === 1 ? "year" : "years"} and your resume shows about ${yours}. You meet it, so this component is full marks: ${points} of ${weight}.`;
      }
      const gap = Math.round((required - yours) * 10) / 10;
      const softened =
        facts.basis === "preferred"
          ? ` Because it is written as a preference rather than a bar, the shortfall costs only ${Math.round((facts.preference_scale ?? 0.4) * 100)}% of what the same gap would cost as a requirement.`
          : "";
      return `It asks for ${required} ${required === 1 ? "year" : "years"} and your resume shows about ${yours}, so you are ${gap} short. A shortfall counts against this component in proportion to its size, up to ${cap} years — past that, one impossibility is not usefully distinguished from another.${softened} That leaves ${points} of ${weight}.`;
    }

    case "keywords": {
      const shared = facts.shared_terms ?? 0;
      return `Your resume and this posting share ${shared} ${shared === 1 ? "word" : "words"}, counted so that a word the posting uses throughout is worth more than one it mentions once, and normalised against your own vocabulary so a longer resume is not penalised. That comes to ${points} of ${weight}.`;
    }

    case "freshness": {
      const age = facts.age_days ?? 0;
      const horizon = facts.horizon_days ?? 30;
      return `Posted about ${age} ${age === 1 ? "day" : "days"} ago, against a ${horizon}-day horizon: ${points} of ${weight}. A graduate applying to something four weeks old is usually applying after the shortlist already exists.`;
    }

    default:
      return "";
  }
}
