/**
 * How this score was calculated — the whole arithmetic, component by component.
 *
 * This page exists because a bar is a summary, not an explanation. A student looking at "58" and
 * four coloured segments can see that the experience component is weak and still have no idea what
 * sentence in the posting made it weak, how many skills were asked for, or what their own resume
 * was read as saying. Every number here is one the server sent, laid out so the total can be
 * recomputed on paper and Reachly can be caught being wrong.
 *
 * ADR 0003 chose deterministic scoring over asking a model, and this page is what that decision
 * buys. A model-assigned number can be displayed; it cannot be audited.
 */

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../lib/auth";
import { fetchJob, queryKeys } from "../lib/jobs";
import {
  componentTitles,
  derivationOf,
  fetchScoreExplanation,
  scoreKeys,
  type ScoreComponent,
} from "../lib/score";

/** A component's points as a proportion of its own weight, for the inline bar. */
function shareOf(component: ScoreComponent): number {
  return component.weight === 0 ? 0 : component.points / component.weight;
}

function StateChip({ state }: { state: ScoreComponent["state"] }) {
  const wording: Record<ScoreComponent["state"], string> = {
    scored: "scored",
    met: "you meet it",
    short: "you are short",
    unstated: "posting did not say",
  };

  // An unstated component is drawn differently from a low one throughout the product. Reusing the
  // same grey for "we do not know" and "you scored badly" would be the one confusion this whole
  // page exists to prevent.
  const tone =
    state === "unstated"
      ? "border-inferred/40 bg-inferred/5 text-inferred"
      : state === "short"
        ? "border-closed/40 bg-closed/5 text-closed"
        : "border-confirmed/40 bg-confirmed/5 text-confirmed";

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-chip border px-1.5 py-0.5 font-receipt text-[11px] tracking-[0.02em] ${tone}`}
    >
      {wording[state]}
    </span>
  );
}

function SkillChips({ terms, tone }: { terms: string[]; tone: "have" | "missing" }) {
  if (terms.length === 0) return null;
  const className =
    tone === "have"
      ? "rounded-chip border border-confirmed/40 bg-confirmed/5 px-1.5 py-0.5 font-receipt text-[11px] text-confirmed"
      : "rounded-chip border border-rule bg-blueprint px-1.5 py-0.5 font-receipt text-[11px] text-slate";

  return (
    <dd className="mt-1 flex flex-wrap gap-1.5">
      {terms.map((term) => (
        <span key={term} className={className}>
          {term}
        </span>
      ))}
    </dd>
  );
}

function ComponentRow({
  component,
  neutralShare,
  children,
}: {
  component: ScoreComponent;
  neutralShare: number;
  children?: React.ReactNode;
}) {
  const share = shareOf(component);

  return (
    <section className="border-t border-rule py-5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-[16px] font-bold text-ink">
          {componentTitles[component.name]}
        </h2>
        <div className="flex items-center gap-2">
          <StateChip state={component.state} />
          <span className="font-receipt text-[13px] text-ink">
            {component.points}
            <span className="text-slate"> of {component.weight}</span>
          </span>
        </div>
      </div>

      {/* The component's own bar, filled against its own weight rather than against 100. Sizing
          every component to the same width would make 9 of 10 look worse than 24 of 40. */}
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-blueprint"
        role="img"
        aria-label={`${component.points} of ${component.weight} points`}
      >
        <div
          className={component.state === "unstated" ? "h-full bg-inferred/40" : "h-full bg-ink"}
          style={{ width: `${Math.max(share * 100, 1)}%` }}
        />
      </div>

      <p className="mt-3 text-[15px] leading-[1.6] text-slate">
        {derivationOf(component, neutralShare)}
      </p>

      {children}
    </section>
  );
}

export function ScoreReportPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);

  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => fetchJob(jobId),
    enabled: Number.isFinite(jobId),
  });

  const report = useQuery({
    queryKey: scoreKeys.explanation(jobId),
    queryFn: () => fetchScoreExplanation(jobId),
    retry: false,
    enabled: Number.isFinite(jobId),
  });

  const unavailable =
    report.isError && (report.error as ApiError)?.code === "score_unavailable";

  return (
    <main className="mx-auto max-w-[820px] px-4 py-8 sm:px-6">
      <Link
        to={`/jobs/${jobId}`}
        className="font-receipt text-[11px] tracking-[0.02em] text-slate underline-offset-4 hover:underline"
      >
        &larr; back to the posting
      </Link>

      <h1 className="mt-3 font-display text-[24px] font-extrabold leading-tight tracking-[-0.02em] text-ink sm:text-[32px]">
        How this score was calculated
      </h1>

      {job.data && (
        <p className="mt-2 text-[15px] text-slate">
          <span className="font-medium text-ink">{job.data.title}</span> at {job.data.company_name}
        </p>
      )}

      {unavailable && (
        <div className="mt-6 rounded-card border border-rule bg-paper p-5">
          <p className="text-[15px] text-ink">{(report.error as ApiError).message}</p>
          <Link
            to="/profile"
            className="mt-3 inline-block font-receipt text-[11px] tracking-[0.02em] text-slate underline underline-offset-2 hover:text-ink"
          >
            upload a resume
          </Link>
        </div>
      )}

      {report.isLoading && (
        <p className="mt-6 font-receipt text-[13px] text-slate">Reading the posting…</p>
      )}

      {report.data && (
        <>
          {/* The total first, and stated as a sum, because the rest of the page is the addends. */}
          <div className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <div className="flex items-baseline gap-3">
              <span className="font-display text-[40px] font-extrabold leading-none tracking-[-0.03em] text-ink">
                {report.data.total}
              </span>
              <span className="font-receipt text-[13px] text-slate">out of 100</span>
            </div>
            <p className="mt-3 font-receipt text-[12px] leading-[1.6] text-slate">
              {report.data.components
                .map((c) => `${c.points}`)
                .join(" + ")}{" "}
              = {report.data.total}. Four weighted components, summed. Each is a whole number within
              its own weight, so what you add up is exactly what you were shown.
            </p>
            <p className="mt-3 text-[14px] leading-[1.6] text-slate">
              Nothing here is a model&apos;s opinion. The same posting and the same resume produce
              the same number every time, which is why it can be shown to you at all.
            </p>
          </div>

          <div className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
            {report.data.components.map((component) => (
              <ComponentRow
                key={component.name}
                component={component}
                neutralShare={report.data.neutral_share}
              >
                {component.name === "skills" && (
                  <dl className="mt-3 space-y-3">
                    {report.data.matched_skills.length > 0 && (
                      <div>
                        <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                          you have these
                        </dt>
                        <SkillChips terms={report.data.matched_skills} tone="have" />
                      </div>
                    )}
                    {report.data.missing_skills.length > 0 && (
                      <div>
                        <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                          it asked for these and your resume does not show them
                        </dt>
                        <SkillChips terms={report.data.missing_skills} tone="missing" />
                        <p className="mt-2 text-[14px] leading-[1.6] text-slate">
                          These are the terms to go and learn, or to add to your resume if you have
                          them and left them out. Reachly will not write them in for you — see the
                          tailoring page for why.
                        </p>
                      </div>
                    )}
                  </dl>
                )}

                {component.name === "experience" && report.data.requirement_phrase && (
                  <div className="mt-3 rounded-card border border-rule bg-blueprint p-3">
                    <p className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                      read from this sentence in the posting
                    </p>
                    <q className="mt-1 block font-receipt text-[12px] leading-[1.6] text-ink">
                      {report.data.requirement_phrase}
                    </q>
                    <p className="mt-2 text-[13px] leading-[1.6] text-slate">
                      If that sentence is not really a requirement, the score is wrong and this is
                      where you can see it. Reading &quot;18 years&quot; out of &quot;18 years of
                      age&quot; is a mistake Reachly used to make on the most accessible jobs in the
                      index.
                    </p>
                  </div>
                )}

                {component.name === "keywords" && report.data.shared_keywords.length > 0 && (
                  <div className="mt-3">
                    <p className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                      words in both your resume and this posting
                    </p>
                    <p className="mt-1 font-receipt text-[12px] leading-[1.7] text-slate">
                      {report.data.shared_keywords.join(" · ")}
                    </p>
                  </div>
                )}
              </ComponentRow>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={`/jobs/${jobId}/tailor`}
              className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
            >
              Tailor my resume for this job
            </Link>
            <Link
              to={`/jobs/${jobId}`}
              className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint"
            >
              Read the full posting
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
