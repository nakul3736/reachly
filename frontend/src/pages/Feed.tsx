/**
 * The feed. The home screen — there is no dashboard.
 *
 * Single column, max 1100px, generous vertical rhythm.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { IndexLedger } from "../components/IndexLedger";
import { JobCard, JobCardSkeleton } from "../components/JobCard";
import { fetchJobs, fetchSources, queryKeys } from "../lib/jobs";

const PAGE_SIZE = 20;

export default function Feed() {
  const [page, setPage] = useState(1);

  const jobs = useQuery({
    queryKey: queryKeys.jobs(page),
    queryFn: () => fetchJobs({ page, pageSize: PAGE_SIZE }),
  });

  const sources = useQuery({
    queryKey: queryKeys.sources(),
    queryFn: fetchSources,
  });

  // When each board was last read, so every card can show it. Verified postings come from a
  // company board; the read time is what makes their posting date mean anything.
  const readByProvider = new Map<string, string>();
  for (const board of sources.data?.boards ?? []) {
    if (!board.last_succeeded_at) continue;
    const current = readByProvider.get(board.provider);
    if (!current || board.last_succeeded_at > current) {
      readByProvider.set(board.provider, board.last_succeeded_at);
    }
  }

  const totalPages = jobs.data ? Math.max(1, Math.ceil(jobs.data.total / PAGE_SIZE)) : 1;

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-10 sm:px-6 sm:pt-14">
      <header>
        <h1 className="font-display text-[32px] font-extrabold leading-none tracking-[-0.03em] text-ink sm:text-[48px]">
          Reachly
        </h1>
        <p className="mt-3 max-w-[52ch] text-[15px] text-slate sm:text-[18px]">
          Graduate openings, checked against the employer&apos;s own board. Every posting
          shows where it came from and when we last looked.
        </p>

        <div className="mt-5 border-t border-rule pt-3">
          <IndexLedger
            total={jobs.data?.total}
            boards={sources.data?.boards}
            loading={jobs.isPending || sources.isPending}
          />
        </div>
      </header>

      <section className="mt-8" aria-label="Open roles">
        {jobs.isPending && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 5 }, (_, i) => (
              <JobCardSkeleton key={i} />
            ))}
          </div>
        )}

        {jobs.isError && <FeedError message={(jobs.error as Error).message} onRetry={() => jobs.refetch()} />}

        {jobs.isSuccess && jobs.data.items.length === 0 && <FeedEmpty />}

        {jobs.isSuccess && jobs.data.items.length > 0 && (
          <>
            <div className="flex flex-col gap-3">
              {jobs.data.items.map((job) => (
                <JobCard
                  key={job.id}
                  job={job}
                  boardReadAt={readByProvider.get(job.source) ?? null}
                />
              ))}
            </div>

            {totalPages > 1 && (
              <nav className="mt-8 flex items-center justify-between border-t border-rule pt-4">
                <PageButton disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Previous
                </PageButton>
                <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                  page {page} of {totalPages}
                </span>
                <PageButton disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  Next
                </PageButton>
              </nav>
            )}
          </>
        )}
      </section>
    </main>
  );
}

function PageButton({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-card border border-rule bg-paper px-3 py-1.5 text-[13px] font-medium text-ink enabled:hover:border-ink/30 disabled:cursor-not-allowed disabled:text-closed"
    >
      {children}
    </button>
  );
}

/**
 * An empty feed is an invitation to act, and it says which condition emptied it.
 *
 * With no filters yet, empty means the index has not been read. Saying "no jobs found" would
 * leave a student assuming the product is broken.
 */
function FeedEmpty() {
  return (
    <div className="rounded-card border border-rule bg-paper p-6">
      <h2 className="font-display text-[18px] font-bold text-ink">
        The index has not been read yet
      </h2>
      <p className="mt-2 max-w-[56ch] text-[15px] text-slate">
        No boards have returned postings so far. Once the daily refresh runs, openings appear
        here with the date each board was last checked.
      </p>
    </div>
  );
}

/** Errors say what happened and what to try. They do not apologise and are never vague. */
function FeedError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-card border border-inferred/40 bg-inferred/5 p-6">
      <h2 className="font-display text-[18px] font-bold text-ink">
        The index could not be read
      </h2>
      <p className="mt-2 max-w-[56ch] text-[15px] text-slate">{message}</p>
      <p className="mt-1 max-w-[56ch] text-[13px] text-slate">
        The API sleeps when idle and can take up to a minute to wake.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-card border border-ink bg-ink px-3 py-1.5 text-[13px] font-medium text-paper hover:bg-ink/90"
      >
        Try again
      </button>
    </div>
  );
}
