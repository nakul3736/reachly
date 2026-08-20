/**
 * One job, with everything known about it on a single screen — story 20.
 *
 * A closed posting is shown as closed rather than hidden. The student may have applied to it,
 * and a 404 would be a lie about something that existed.
 */

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { Fact, ReceiptLine, VerificationChip } from "../components/Receipt";
import { fetchJob, queryKeys } from "../lib/jobs";
import { isStale, postedAge } from "../lib/time";

export default function JobDetailPage() {
  const { id } = useParams();
  const jobId = Number(id);

  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => fetchJob(jobId),
    enabled: Number.isFinite(jobId),
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

          <div className="mt-4 flex flex-wrap gap-2">
            <a
              href={job.data.apply_url}
              target="_blank"
              rel="noreferrer noopener"
              className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
            >
              Apply on {job.data.company_name}&apos;s site
            </a>
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
