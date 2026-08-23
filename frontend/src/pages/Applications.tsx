/**
 * The pipeline: every posting the student is pursuing, and what has happened to it.
 *
 * A list rather than a drag-and-drop board. Kanban columns look impressive in a demo and are hostile on
 * the phone a student actually checks this on between classes, and dragging is a poor fit for a change
 * that happens once a fortnight per row. A status control on each row does the same work and can be
 * operated with one thumb.
 *
 * Nothing here is inferred. Reachly does not submit the form and does not send the email, so every
 * status is the student's own report — which is why the empty state explains that saving a posting is
 * something they do, rather than implying Reachly will notice on their behalf.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  STATUSES,
  STATUS_LABEL,
  type Application,
  type ApplicationStatus,
  applicationKeys,
  fetchPipeline,
  untrack,
  updateApplication,
} from "../lib/applications";

/** A date a person can read, without a time — the hour they pressed the button is noise. */
function readableDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Whole days since a date. The number that answers "should I follow up?". */
function daysSince(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));
}

export function Applications() {
  const cache = useQueryClient();

  const pipeline = useQuery({
    queryKey: applicationKeys.pipeline,
    queryFn: fetchPipeline,
  });

  const move = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      updateApplication(id, { status }),
    onSuccess: () => cache.invalidateQueries({ queryKey: applicationKeys.pipeline }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => untrack(id),
    onSuccess: () => cache.invalidateQueries({ queryKey: applicationKeys.pipeline }),
  });

  const items = pipeline.data?.items ?? [];
  const counts = pipeline.data?.counts;

  return (
    <main className="mx-auto max-w-[1100px] px-4 py-8 sm:px-6">
      <h1 className="font-display text-[24px] font-extrabold leading-tight tracking-[-0.02em] text-ink sm:text-[32px]">
        My applications
      </h1>
      <p className="mt-2 max-w-[62ch] text-[15px] leading-[1.6] text-slate">
        Everything you are pursuing, with the resume you actually sent attached to it. Reachly does
        not submit forms or send email, so these statuses are yours to set — nothing here changes
        unless you say it did.
      </p>

      {counts && (
        <ul className="mt-6 flex flex-wrap gap-2">
          {STATUSES.map((status) => (
            <li
              key={status}
              className="rounded-card border border-rule bg-paper px-3 py-2"
              aria-label={`${counts[status]} ${STATUS_LABEL[status]}`}
            >
              <span className="font-display text-[18px] font-bold text-ink">{counts[status]}</span>{" "}
              <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                {STATUS_LABEL[status].toLowerCase()}
              </span>
            </li>
          ))}
        </ul>
      )}

      {pipeline.isLoading && (
        <p className="mt-6 font-receipt text-[11px] tracking-[0.02em] text-slate">loading…</p>
      )}

      {!pipeline.isLoading && items.length === 0 && (
        <div className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
          <h2 className="font-display text-[16px] font-bold text-ink">Nothing tracked yet</h2>
          <p className="mt-2 max-w-[62ch] text-[15px] leading-[1.6] text-slate">
            Open a posting and press <span className="text-ink">Track this</span> to put it here.
            Saving is not applying — the point of the two being separate is that you can hold twelve
            postings you are still deciding between without pretending you have sent anything.
          </p>
          <Link
            to="/"
            className="mt-3 inline-block rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
          >
            Find postings
          </Link>
        </div>
      )}

      {items.length > 0 && (
        <ul className="mt-6 flex flex-col gap-3">
          {items.map((application) => (
            <Row
              key={application.id}
              application={application}
              onMove={(status) => move.mutate({ id: application.id, status })}
              onRemove={() => remove.mutate(application.id)}
              busy={move.isPending || remove.isPending}
            />
          ))}
        </ul>
      )}
    </main>
  );
}

function Row({
  application,
  onMove,
  onRemove,
  busy,
}: {
  application: Application;
  onMove: (status: ApplicationStatus) => void;
  onRemove: () => void;
  busy: boolean;
}) {
  const waiting =
    application.status === "applied" && application.applied_at
      ? daysSince(application.applied_at)
      : null;

  return (
    <li className="rounded-card border border-rule bg-paper p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <Link
            to={`/jobs/${application.job_id}`}
            className="font-display text-[18px] font-bold tracking-[-0.01em] text-ink underline-offset-4 hover:underline"
          >
            {application.title}
          </Link>
          <p className="mt-0.5 text-[15px] text-slate">{application.company_name}</p>
        </div>

        <label className="flex items-center gap-2">
          <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">status</span>
          <select
            value={application.status}
            disabled={busy}
            onChange={(event) => onMove(event.target.value as ApplicationStatus)}
            className="rounded-card border border-rule bg-paper px-2 py-1 text-[14px] text-ink focus:border-ink focus:outline-none"
          >
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABEL[status]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-receipt text-[11px] tracking-[0.02em] text-slate">
        {application.applied_at ? (
          <span>applied {readableDate(application.applied_at)}</span>
        ) : (
          <span>saved {readableDate(application.created_at)}</span>
        )}

        {/* The number that answers "should I follow up?", which a date alone does not. */}
        {waiting !== null && waiting >= 7 && (
          <span className="text-closed">
            {waiting} days with no reply — worth following up
          </span>
        )}

        {application.has_tailored_resume ? (
          <Link
            to={`/jobs/${application.job_id}/tailor`}
            className="underline decoration-rule underline-offset-2 hover:text-ink"
          >
            see the resume you sent
          </Link>
        ) : (
          <span title="You applied with your master resume rather than a tailored one.">
            master resume
          </span>
        )}

        <Link
          to={`/jobs/${application.job_id}/outreach`}
          className="underline decoration-rule underline-offset-2 hover:text-ink"
        >
          introduction
        </Link>

        <a
          href={application.apply_url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline decoration-rule underline-offset-2 hover:text-ink"
        >
          posting
        </a>

        <button
          type="button"
          onClick={onRemove}
          disabled={busy}
          className="underline decoration-rule underline-offset-2 hover:text-closed disabled:opacity-60"
        >
          stop tracking
        </button>
      </div>

      {/*
        Flagged, never hidden. An application outstanding against a posting that has been taken down is
        worth knowing — and a row disappearing from a tracker reads as data loss.
      */}
      {application.closed && (
        <p className="mt-2 font-receipt text-[11px] tracking-[0.02em] text-closed">
          this posting has been taken down
        </p>
      )}

      {application.notes && (
        <p className="mt-2 whitespace-pre-line text-[14px] leading-[1.55] text-slate">
          {application.notes}
        </p>
      )}
    </li>
  );
}
