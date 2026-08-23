/**
 * A job card: wide and low, title and company left, verification right, receipt line along
 * the bottom edge behind a hairline. Separation comes from hairlines and background
 * contrast, never shadow.
 *
 * The right-hand slot holds verification rather than the decomposed score bar the brief
 * describes, because scoring is feature 03. When it lands, the score decomposition joins
 * this column. For this ticket verification is genuinely the headline claim.
 */

import { Link } from "react-router-dom";

import { Fact, ReceiptLine, VerificationChip } from "./Receipt";
import { ScoreAbsent, ScoreBar } from "./ScoreBar";
import type { JobSummary } from "../lib/jobs";
import { isStale, postedAge, readAge } from "../lib/time";

export function JobCard({
  job,
  boardReadAt,
  scoreAbsentReason,
}: {
  job: JobSummary;
  boardReadAt: string | null;
  /** Why there is no score, when there is none. Absent means say nothing. */
  scoreAbsentReason?: "anonymous" | "no-resume" | null;
}) {
  const closed = job.closed_at !== null;

  return (
    <article
      className={`rounded-card border border-rule bg-paper transition-colors ${
        closed ? "opacity-70" : "hover:border-ink/25"
      }`}
    >
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6 sm:p-5">
        <div className="min-w-0">
          <h2 className="font-display text-[18px] font-bold leading-snug tracking-[-0.01em] text-ink">
            <Link
              to={`/jobs/${job.id}`}
              className="rounded-chip underline-offset-4 hover:underline"
            >
              {job.title}
            </Link>
          </h2>

          <p className="mt-1 text-[15px] text-slate">
            <span className="font-medium text-ink">{job.company_name}</span>
            {job.location_raw && (
              <>
                <span aria-hidden="true" className="px-1.5 text-rule">
                  /
                </span>
                {job.location_raw}
              </>
            )}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          {closed ? (
            <span className="inline-flex items-center rounded-chip border border-closed/40 bg-closed/5 px-1.5 py-0.5 font-receipt text-[11px] tracking-[0.02em] text-closed">
              closed
            </span>
          ) : (
            <VerificationChip verified={job.is_verified} />
          )}

          {/* The decomposed score joins this column, as the card's original note anticipated. */}
          {job.score ? (
            <ScoreBar score={job.score} compact />
          ) : (
            scoreAbsentReason && <ScoreAbsent reason={scoreAbsentReason} />
          )}
        </div>
      </div>

      {/* The receipt: every claim above, with its origin. */}
      <div className="border-t border-rule px-4 py-2.5 sm:px-5">
        <ReceiptLine>
          {[
            <Fact key="source">{job.source}</Fact>,
            <Fact key="posted" tone={isStale(job.posted_at) ? "inferred" : "quiet"}>
              {postedAge(job.posted_at)}
            </Fact>,
            // Both timestamps, always. A posting date alone cannot tell you whether the
            // role still exists; the board read date is what makes the first one mean
            // something.
            job.is_verified ? (
              <Fact key="read" tone={boardReadAt ? "quiet" : "inferred"}>
                {`board ${readAge(boardReadAt)}`}
              </Fact>
            ) : (
              <Fact key="unverified" tone="inferred" title="Not checked against the employer.">
                not on the employer&apos;s board
              </Fact>
            ),
          ]}
        </ReceiptLine>
      </div>
    </article>
  );
}

/** Skeleton matching the card's real geometry, so nothing shifts when data arrives. */
export function JobCardSkeleton() {
  return (
    <div className="rounded-card border border-rule bg-paper" aria-hidden="true">
      <div className="flex items-start justify-between gap-6 p-4 sm:p-5">
        <div className="w-full">
          <div className="h-[18px] w-2/3 rounded-chip bg-blueprint" />
          <div className="mt-2 h-[15px] w-1/3 rounded-chip bg-blueprint" />
        </div>
        <div className="h-[20px] w-20 shrink-0 rounded-chip bg-blueprint" />
      </div>
      <div className="border-t border-rule px-4 py-2.5 sm:px-5">
        <div className="h-[11px] w-1/2 rounded-chip bg-blueprint" />
      </div>
    </div>
  );
}
