/**
 * The feed. The home screen — there is no dashboard.
 *
 * Single column, max 1100px.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  FilterBar,
  NO_FILTERS,
  activeCount,
  toQuery,
  type FilterState,
} from "../components/FilterBar";
import { IndexLedger } from "../components/IndexLedger";
import { JobCard, JobCardSkeleton } from "../components/JobCard";
import { fetchJobs, fetchSources } from "../lib/jobs";

const PAGE_SIZE = 20;

export default function Feed() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS);

  const query = toQuery(filters);

  const jobs = useQuery({
    // The filters are part of the key, so each combination is cached separately and going
    // back to a previous set is instant rather than a refetch.
    queryKey: ["jobs", page, query],
    queryFn: () => fetchJobs({ page, pageSize: PAGE_SIZE, ...query }),
  });

  const sources = useQuery({ queryKey: ["sources"], queryFn: fetchSources });

  // When each board was last read, so every card can show it. A verified posting comes from a
  // company board, and the read time is what makes its posting date mean anything.
  const readByProvider = new Map<string, string>();
  for (const board of sources.data?.boards ?? []) {
    if (!board.last_succeeded_at) continue;
    const current = readByProvider.get(board.provider);
    if (!current || board.last_succeeded_at > current) {
      readByProvider.set(board.provider, board.last_succeeded_at);
    }
  }

  const totalPages = jobs.data ? Math.max(1, Math.ceil(jobs.data.total / PAGE_SIZE)) : 1;

  const changeFilters = (next: FilterState) => {
    setFilters(next);
    // Page 3 of the old result set is meaningless against the new one, and landing on an empty
    // page after narrowing a filter reads as "no results" when there are plenty on page 1.
    setPage(1);
  };

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-10 sm:px-6 sm:pt-14">
      <header>
        <h1 className="font-display text-[32px] font-extrabold leading-none tracking-[-0.03em] text-ink sm:text-[48px]">
          Graduate openings, checked
        </h1>
        <p className="mt-3 max-w-[54ch] text-[15px] text-slate sm:text-[18px]">
          Drawn from companies&apos; own job boards. Every posting shows where it came from and
          when we last looked, so a filled role leaves the list instead of wasting your evening.
        </p>

        <div className="mt-5 border-t border-rule pt-3">
          <IndexLedger
            total={jobs.data?.total}
            boards={sources.data?.boards}
            loading={jobs.isPending || sources.isPending}
          />
        </div>
      </header>

      <section className="mt-7" aria-label="Filters">
        <FilterBar
          state={filters}
          onChange={changeFilters}
          total={jobs.data?.total}
          loading={jobs.isFetching}
        />
      </section>

      <section className="mt-6" aria-label="Open roles">
        {jobs.isPending && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 5 }, (_, i) => (
              <JobCardSkeleton key={i} />
            ))}
          </div>
        )}

        {jobs.isError && (
          <FeedError
            message={(jobs.error as Error).message}
            onRetry={() => void jobs.refetch()}
          />
        )}

        {jobs.isSuccess && jobs.data.items.length === 0 && (
          <FeedEmpty
            filtered={activeCount(filters) > 0}
            onClear={() => changeFilters(NO_FILTERS)}
          />
        )}

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
                <PageButton
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
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
 * An empty result is an invitation to act, and says which condition emptied it.
 *
 * The two cases are genuinely different. Filters returning nothing is the student's own
 * narrowing and is fixed by widening. An unfiltered feed being empty means the index has not
 * been read, which the student can do nothing about — and saying "no jobs found" there would
 * leave them assuming the product is broken.
 */
function FeedEmpty({ filtered, onClear }: { filtered: boolean; onClear: () => void }) {
  return (
    <div className="rounded-card border border-rule bg-paper p-6">
      <h2 className="font-display text-[18px] font-bold text-ink">
        {filtered ? "Nothing matches these filters" : "The index has not been read yet"}
      </h2>
      <p className="mt-2 max-w-[56ch] text-[15px] text-slate">
        {filtered
          ? "Your filters are combined, so each one narrows the last. Turning one off usually brings results straight back."
          : "No boards have returned postings yet. Once the daily refresh runs, openings appear here with the date each board was last checked."}
      </p>
      {filtered && (
        <button
          type="button"
          onClick={onClear}
          className="mt-4 rounded-card border border-ink bg-ink px-3 py-1.5 text-[13px] font-medium text-paper hover:bg-ink/90"
        >
          Clear all filters
        </button>
      )}
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
