/**
 * The score, decomposed into four segments.
 *
 * The brief is explicit that a score is never a bare number. This is the reason: a single figure
 * out of 100 is what every job board already gives the student, and it explains nothing. Four
 * segments sized by their weights mean the *shape* of the bar carries the diagnosis — a card whose
 * experience segment is empty looks different at a glance from one whose skills segment is, and
 * those two cards call for different decisions.
 *
 * Segment widths are proportional to the component weights (40/30/20/10), so the bar is a fixed
 * frame that fills rather than a chart that rescales. A student comparing two cards is comparing
 * the same geometry.
 *
 * `unstated` is drawn as a hatch, not as fill and not as emptiness, because it means neither. A
 * posting that never named its requirements has not said the student qualifies and has not said
 * they fail — and rendering that as full marks would be the product lying about what it knows.
 */

import type { ComponentState, ScoreBreakdown } from "../lib/jobs";

const WEIGHTS = { skill: 40, experience: 30, keyword: 20, freshness: 10 } as const;

type SegmentKey = keyof typeof WEIGHTS;

const LABELS: Record<SegmentKey, string> = {
  skill: "skills",
  experience: "experience",
  keyword: "wording",
  freshness: "freshness",
};

interface Segment {
  key: SegmentKey;
  label: string;
  points: number;
  weight: number;
  state: ComponentState;
}

function segmentsOf(score: ScoreBreakdown): Segment[] {
  return [
    {
      key: "skill",
      label: LABELS.skill,
      points: score.skill_points,
      weight: WEIGHTS.skill,
      state: score.skill_state,
    },
    {
      key: "experience",
      label: LABELS.experience,
      points: score.experience_points,
      weight: WEIGHTS.experience,
      state: score.experience_state,
    },
    {
      key: "keyword",
      label: LABELS.keyword,
      points: score.keyword_points,
      weight: WEIGHTS.keyword,
      state: score.keyword_state,
    },
    {
      key: "freshness",
      label: LABELS.freshness,
      points: score.freshness_points,
      weight: WEIGHTS.freshness,
      state: score.freshness_state,
    },
  ];
}

/** Hatched fill for `unstated`, so it reads as "not known" rather than as a quantity. */
const HATCH =
  "repeating-linear-gradient(45deg, var(--color-inferred) 0 2px, transparent 2px 4px)";

function fillFor(segment: Segment): string {
  if (segment.state === "unstated") return HATCH;
  if (segment.key === "experience" && segment.state === "short") {
    return "var(--color-inferred)";
  }
  return "var(--color-confirmed)";
}

function describe(segment: Segment): string {
  if (segment.state === "unstated") {
    return `${segment.label}: not stated in the posting`;
  }
  return `${segment.label}: ${segment.points} of ${segment.weight}`;
}

/**
 * The bar plus its total.
 *
 * `role="img"` with a full text label rather than four decorative divs: the decomposition has to
 * reach a screen reader and a colour-blind reader intact, so colour is never the only carrier.
 * The same sentence is what a hover reveals, so nobody gets a lesser version of the explanation.
 */
export function ScoreBar({ score, compact = false }: { score: ScoreBreakdown; compact?: boolean }) {
  const segments = segmentsOf(score);
  const summary = `Match ${score.total} of 100. ${segments.map(describe).join(". ")}.`;

  return (
    <div className={compact ? "w-full sm:w-[168px]" : "w-full"}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">match</span>
        {/* The total always appears with the decomposition, never alone. */}
        <span className="font-display text-[15px] font-bold tabular-nums text-ink">
          {score.total}
          <span className="font-receipt text-[11px] font-normal text-slate">/100</span>
        </span>
      </div>

      <div
        role="img"
        aria-label={summary}
        title={summary}
        className="mt-1 flex h-[6px] w-full gap-[2px] overflow-hidden rounded-chip"
      >
        {segments.map((segment) => {
          const filled = Math.max(0, Math.min(1, segment.points / segment.weight));
          return (
            <div
              key={segment.key}
              // Flex-grow by weight, so the frame is fixed and only the fill varies.
              style={{ flexGrow: segment.weight }}
              className="relative h-full bg-blueprint"
            >
              <div
                className="absolute inset-y-0 left-0"
                style={{
                  width: `${filled * 100}%`,
                  background: fillFor(segment),
                }}
              />
            </div>
          );
        })}
      </div>

      {!compact && (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
          {segments.map((segment) => (
            <div key={segment.key} className="flex items-baseline justify-between gap-2">
              <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                {segment.label}
              </dt>
              <dd
                className={`font-receipt text-[11px] tabular-nums ${
                  segment.state === "unstated" ? "text-inferred" : "text-ink"
                }`}
              >
                {segment.state === "unstated"
                  ? "not stated"
                  : `${segment.points}/${segment.weight}`}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/**
 * What stands in for the bar when there is no score.
 *
 * An empty state that says what to do next, per the voice rules — not four grey bars, which would
 * read as a score of zero and tell the student they are a bad candidate rather than that they have
 * not uploaded anything.
 */
export function ScoreAbsent({ reason }: { reason: "anonymous" | "no-resume" }) {
  return (
    <div className="w-full sm:w-[168px]">
      <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">match</span>
      <p className="mt-1 text-[13px] leading-snug text-slate">
        {reason === "anonymous" ? (
          <>
            <a href="/signin" className="text-ink underline underline-offset-4">
              Sign in
            </a>{" "}
            to score this against your resume.
          </>
        ) : (
          <>
            <a href="/profile" className="text-ink underline underline-offset-4">
              Upload a resume
            </a>{" "}
            to see which of these skills you already have.
          </>
        )}
      </p>
    </div>
  );
}
