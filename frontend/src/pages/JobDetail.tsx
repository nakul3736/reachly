/**
 * One job, with everything known about it on a single screen — story 20.
 *
 * A closed posting is shown as closed rather than hidden. The student may have applied to it,
 * and a 404 would be a lie about something that existed.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Fact, ReceiptLine, VerificationChip } from "../components/Receipt";
import { ScoreBar } from "../components/ScoreBar";
import {
  STATUSES,
  STATUS_LABEL,
  type ApplicationStatus,
  applicationKeys,
  fetchApplicationForJob,
  trackJob,
} from "../lib/applications";
import { ApiError, storedToken } from "../lib/auth";
import { fetchJob, queryKeys } from "../lib/jobs";
import { isStale, postedAge } from "../lib/time";

export default function JobDetailPage() {
  const { id } = useParams();
  const jobId = Number(id);
  const cache = useQueryClient();
  const signedIn = storedToken() !== null;

  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => fetchJob(jobId),
    enabled: Number.isFinite(jobId),
  });

  // The posting is public, so this must not run for a signed-out visitor — the client throws on a
  // missing token before it ever reaches the network, which would surface as an error on a page that
  // is working perfectly well.
  const tracked = useQuery({
    queryKey: applicationKeys.forJob(jobId),
    queryFn: () => fetchApplicationForJob(jobId),
    enabled: signedIn && Number.isFinite(jobId),
    retry: false,
  });

  const track = useMutation({
    mutationFn: (status: ApplicationStatus) => trackJob(jobId, status),
    onSuccess: (updated) => {
      // Written straight into the cache this component reads, then the pipeline is invalidated. Without
      // the first, the select would snap back to the old status until a refetch landed.
      cache.setQueryData(applicationKeys.forJob(jobId), updated);
      void cache.invalidateQueries({ queryKey: applicationKeys.pipeline });
    },
  });

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-8 sm:px-6">
      <Link
        to="/"
        className="font-receipt text-[11px] tracking-[0.02em] text-slate hover:text-ink"
      >
        &larr; back to the feed
      </Link>

      {job.isPending && (
        <div className="mt-6 rounded-card border border-rule bg-paper p-6" aria-hidden="true">
          <div className="h-[32px] w-2/3 rounded-chip bg-blueprint" />
          <div className="mt-3 h-[18px] w-1/3 rounded-chip bg-blueprint" />
          <div className="mt-6 h-[15px] w-full rounded-chip bg-blueprint" />
          <div className="mt-2 h-[15px] w-11/12 rounded-chip bg-blueprint" />
        </div>
      )}

      {job.isError && (
        <div className="mt-6 rounded-card border border-inferred/40 bg-inferred/5 p-6">
          <h1 className="font-display text-[24px] font-bold text-ink">
            That posting could not be loaded
          </h1>
          <p className="mt-2 text-[15px] text-slate">{(job.error as Error).message}</p>
        </div>
      )}

      {job.isSuccess && (
        <article className="mt-6">
          <header className="rounded-card border border-rule bg-paper">
            <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
              <div className="min-w-0">
                <h1 className="font-display text-[24px] font-extrabold leading-tight tracking-[-0.02em] text-ink sm:text-[32px]">
                  {job.data.title}
                </h1>
                <p className="mt-2 text-[18px] text-slate">
                  <span className="font-medium text-ink">{job.data.company_name}</span>
                  {job.data.location_raw && (
                    <>
                      <span aria-hidden="true" className="px-2 text-rule">
                        /
                      </span>
                      {job.data.location_raw}
                    </>
                  )}
                </p>
              </div>

              <div className="shrink-0">
                {job.data.closed_at ? (
                  <span className="inline-flex items-center rounded-chip border border-closed/40 bg-closed/5 px-2 py-1 font-receipt text-[11px] tracking-[0.02em] text-closed">
                    closed
                  </span>
                ) : (
                  <VerificationChip verified={job.data.is_verified} />
                )}
              </div>
            </div>

            <div className="border-t border-rule px-5 py-3 sm:px-6">
              <ReceiptLine>
                {[
                  <Fact key="src">{`source ${job.data.source}`}</Fact>,
                  <Fact key="posted" tone={isStale(job.data.posted_at) ? "inferred" : "quiet"}>
                    {postedAge(job.data.posted_at)}
                  </Fact>,
                  <Fact key="id">{`id ${job.data.source}:${job.data.id}`}</Fact>,
                  job.data.closed_at ? (
                    <Fact key="closed" tone="closed">
                      {`closed ${new Date(job.data.closed_at).toISOString().slice(0, 10)}`}
                    </Fact>
                  ) : null,
                ]}
              </ReceiptLine>
            </div>
          </header>

          {job.data.closed_at && (
            <p className="mt-4 rounded-card border border-closed/40 bg-closed/5 p-4 text-[15px] text-slate">
              This role is no longer listed on its board, so it has almost certainly been
              filled or withdrawn. It stays here because your application history should not
              develop holes.
            </p>
          )}

          {job.data.score && (
            <section className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
              <h2 className="font-display text-[15px] font-bold text-ink">
                Why this scored {job.data.score.total}
              </h2>

              {/* This panel is a summary: which terms matched, and the sentence the requirement
                  came from. It does not show the arithmetic - the denominators, your own parsed
                  years, the constants - and a student who wants to check the working rather than
                  read a conclusion needs those. */}
              <Link
                to={`/jobs/${job.data.id}/score`}
                className="mt-1 inline-block font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink hover:decoration-ink"
              >
                see the full arithmetic, component by component
              </Link>

              <div className="mt-3">
                <ScoreBar score={job.data.score} />
              </div>

              {/* The score's receipt. Machine voice, because this is evidence rather than
                  prose: the exact terms the posting asked for, and the sentence the
                  experience requirement was read from. */}
              <dl className="mt-5 space-y-3 border-t border-rule pt-4">
                {job.data.score.matched_skills.length > 0 && (
                  <div>
                    <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                      skills you have that it asked for
                    </dt>
                    <dd className="mt-1 flex flex-wrap gap-1.5">
                      {job.data.score.matched_skills.map((skill) => (
                        <span
                          key={skill}
                          className="rounded-chip border border-confirmed/40 bg-confirmed/5 px-1.5 py-0.5 font-receipt text-[11px] text-confirmed"
                        >
                          {skill}
                        </span>
                      ))}
                    </dd>
                  </div>
                )}

                {job.data.score.missing_skills.length > 0 && (
                  <div>
                    <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                      asked for, not on your resume
                    </dt>
                    <dd className="mt-1 flex flex-wrap gap-1.5">
                      {job.data.score.missing_skills.map((skill) => (
                        <span
                          key={skill}
                          className="rounded-chip border border-rule bg-blueprint px-1.5 py-0.5 font-receipt text-[11px] text-slate"
                        >
                          {skill}
                        </span>
                      ))}
                    </dd>
                  </div>
                )}

                <div>
                  <dt className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                    experience
                  </dt>
                  <dd className="mt-1 text-[14px] text-ink">
                    {job.data.score.requirement_phrase ? (
                      <>
                        {job.data.score.requirement_basis === "preferred"
                          ? "Stated as a preference, not a bar: "
                          : "Read from the posting: "}
                        <q className="font-receipt text-[12px] text-slate">
                          {job.data.score.requirement_phrase}
                        </q>
                      </>
                    ) : (
                      <span className="text-inferred">
                        This posting does not state an experience requirement. Reachly has not
                        assumed one either way.
                      </span>
                    )}
                  </dd>
                </div>
              </dl>
            </section>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <a
              href={job.data.apply_url}
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
            >
              Apply on {job.data.company_name}&apos;s site
            </a>
            {/* Placed beside Apply because tailoring is what a student does before applying, not
                a separate errand they have to go looking for. */}
            <Link
              to={`/jobs/${job.data.id}/tailor`}
              className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint"
            >
              Tailor my resume for this job
            </Link>
            <Link
              to={`/jobs/${job.data.id}/outreach`}
              className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint"
            >
              Draft an introduction
            </Link>
          </div>

          {/*
            Two separate acts, deliberately. Clicking Apply opens a tab; Reachly cannot see what
            happens there, and marking the posting applied because a link was clicked would be wrong
            in the direction that hurts — a student who read the form and closed it would find a lie
            in their own tracker. So saying "I applied" is its own button.
          */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {!signedIn ? (
              <Link
                to="/signin"
                className="font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink"
              >
                sign in to track this application
              </Link>
            ) : tracked.data ? (
              // Already in the pipeline, so the question is no longer "track this?" but "where does
              // it stand?". Offering Track this again would invite a second press that appears to do
              // nothing, since the endpoint is idempotent on (student, posting).
              <>
                <label className="flex items-center gap-2">
                  <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                    you marked this
                  </span>
                  <select
                    value={tracked.data.status}
                    disabled={track.isPending}
                    onChange={(event) => track.mutate(event.target.value as ApplicationStatus)}
                    className="rounded-card border border-rule bg-paper px-2 py-1 text-[14px] text-ink focus:border-ink focus:outline-none"
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {STATUS_LABEL[status]}
                      </option>
                    ))}
                  </select>
                </label>
                <Link
                  to="/applications"
                  className="font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink"
                >
                  in my applications
                </Link>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => track.mutate("saved")}
                  disabled={track.isPending}
                  className="rounded-card border border-rule px-4 py-2 text-[15px] text-slate hover:border-ink hover:text-ink disabled:opacity-60"
                >
                  Track this
                </button>
                <button
                  type="button"
                  onClick={() => track.mutate("applied")}
                  disabled={track.isPending}
                  className="rounded-card border border-rule px-4 py-2 text-[15px] text-slate hover:border-ink hover:text-ink disabled:opacity-60"
                >
                  I applied
                </button>
              </>
            )}
            {track.isError && (
              <span className="font-receipt text-[11px] tracking-[0.02em] text-closed">
                {(track.error as ApiError)?.message ?? "That could not be saved."}
              </span>
            )}
          </div>

          <section className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <h2 className="font-receipt text-[11px] uppercase tracking-[0.08em] text-slate">
              Description, as published
            </h2>
            <div className="mt-3 whitespace-pre-line text-[15px] leading-[1.65] text-ink">
              {job.data.description}
            </div>
          </section>

          {job.data.also_seen_on.length > 0 && (
            <section className="mt-4 rounded-card border border-rule bg-paper p-5 sm:p-6">
              <h2 className="font-receipt text-[11px] uppercase tracking-[0.08em] text-slate">
                Also listed on
              </h2>
              <p className="mt-2 text-[15px] text-slate">
                Reachly matched {job.data.also_seen_on.length}{" "}
                {job.data.also_seen_on.length === 1 ? "other listing" : "other listings"} to
                this role and kept the company&apos;s own posting as the record. Apply through
                the link above.
              </p>
              <ul className="mt-3 flex flex-col gap-2">
                {job.data.also_seen_on.map((alias) => (
                  <li key={`${alias.source}-${alias.apply_url}`}>
                    <ReceiptLine>
                      {[
                        <Fact key="src">{alias.source}</Fact>,
                        <Fact key="kind" tone={alias.is_verified ? "confirmed" : "inferred"}>
                          {alias.is_verified ? "company board" : "aggregator copy"}
                        </Fact>,
                        <a
                          key="link"
                          href={alias.apply_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule hover:text-ink"
                        >
                          view listing
                        </a>,
                      ]}
                    </ReceiptLine>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      )}
    </main>
  );
}
