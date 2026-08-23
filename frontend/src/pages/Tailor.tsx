/**
 * The tailored resume: every bullet with its original beside it.
 *
 * This screen is the product's argument. Every other tool that offers to tailor a resume asks the
 * student to trust the output; this one shows the source of every sentence and, when a rewrite was
 * refused, shows what was refused and why.
 *
 * The refusals are the point, so they are not hidden behind a disclosure. A student who sees "it
 * tried to add Kubernetes, which is not in this bullet" learns two things at once: that the
 * fabrication was attempted, and that something stopped it. Neither is available from a tool that
 * silently succeeds.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Fact, ReceiptLine } from "../components/Receipt";
import { ApiError } from "../lib/auth";
import {
  asPlainText,
  createTailoring,
  fetchTailoring,
  refusalWording,
  tailoringKeys,
  type TailoredBullet,
} from "../lib/tailoring";

export function TailorPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);

  const existing = useQuery({
    queryKey: tailoringKeys.tailoring(jobId),
    queryFn: () => fetchTailoring(jobId),
    // A 404 means "not tailored yet", which is a normal state rather than a failure.
    retry: false,
    enabled: Number.isFinite(jobId),
  });

  const tailor = useMutation({
    mutationFn: () => createTailoring(jobId),
    onSuccess: (data) => queryClient.setQueryData(tailoringKeys.tailoring(jobId), data),
  });

  const result = tailor.data ?? existing.data;
  const notFound = existing.isError && (existing.error as ApiError)?.status === 404;

  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="mx-auto max-w-[1100px] px-4 py-8 sm:px-6">
      <Link
        to={`/jobs/${jobId}`}
        className="font-receipt text-[11px] tracking-[0.02em] text-slate underline-offset-4 hover:underline"
      >
        &larr; back to the posting
      </Link>

      <h1 className="mt-3 font-display text-[24px] font-extrabold leading-tight tracking-[-0.02em] text-ink sm:text-[32px]">
        Tailored resume
      </h1>

      {result && (
        <p className="mt-1 text-[15px] text-slate">
          for <span className="font-medium text-ink">{result.job_title}</span> at{" "}
          {result.company_name}
        </p>
      )}

      {/* The claim, stated before the output rather than after it. */}
      <section className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
        <h2 className="font-display text-[15px] font-bold text-ink">
          What this does, and what it will not do
        </h2>
        <p className="mt-2 max-w-[68ch] text-[15px] text-slate">
          Reachly rewrites your bullets using this posting&apos;s vocabulary. It cannot add a
          technology, employer, number or claim that is not already in the bullet it is rewriting —
          each rewrite is checked against its own source, and a rewrite that fails the check is
          discarded in favour of your original sentence.
        </p>
        <p className="mt-2 max-w-[68ch] text-[15px] text-slate">
          Requirements your resume does not support are listed as gaps below, never written into
          your experience.
        </p>

        {!result && (
          <button
            type="button"
            onClick={() => tailor.mutate()}
            disabled={tailor.isPending}
            className="mt-4 rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90 disabled:opacity-60"
          >
            {tailor.isPending ? "Tailoring…" : "Tailor my resume for this job"}
          </button>
        )}

        {tailor.isError && (
          <p className="mt-4 rounded-card border border-inferred/45 bg-inferred/5 p-3 text-[14px] text-ink">
            {(tailor.error as ApiError)?.message ?? "That did not work."}
          </p>
        )}

        {existing.isLoading && !notFound && (
          <p className="mt-4 font-receipt text-[11px] text-slate">checking for an earlier version…</p>
        )}
      </section>

      {result && (
        <>
          <section className="mt-4 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <ReceiptLine>
              {[
                <Fact key="changed" tone="confirmed">
                  {`${result.changed_count} rewritten`}
                </Fact>,
                <Fact
                  key="rejected"
                  tone={result.rejected_count > 0 ? "inferred" : "quiet"}
                  title="Rewrites the validator refused because they added something not in your resume."
                >
                  {`${result.rejected_count} refused`}
                </Fact>,
                <Fact key="kept" tone="quiet">
                  {`${result.bullets.length - result.changed_count} kept as written`}
                </Fact>,
                <Fact key="basis" tone={result.basis === "live" ? "quiet" : "inferred"}>
                  {result.basis === "live" ? "model" : "recorded response"}
                </Fact>,
              ]}
            </ReceiptLine>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => copy(asPlainText(result))}
                className="rounded-card border border-ink px-3 py-1.5 text-[14px] font-medium text-ink hover:bg-blueprint"
              >
                {copied ? "Copied" : "Copy tailored bullets"}
              </button>
              <button
                type="button"
                onClick={() => tailor.mutate()}
                disabled={tailor.isPending}
                className="rounded-card border border-rule px-3 py-1.5 text-[14px] text-slate hover:border-ink/25 disabled:opacity-60"
              >
                {tailor.isPending ? "Tailoring…" : "Tailor again"}
              </button>
            </div>
          </section>

          <ol className="mt-4 flex flex-col gap-3">
            {result.bullets.map((bullet) => (
              <BulletRow key={bullet.bullet_id} bullet={bullet} />
            ))}
          </ol>

          <GapList gaps={result.gaps} />
        </>
      )}
    </main>
  );
}

/**
 * One bullet, before and after.
 *
 * Three visually distinct states, because they mean three different things: rewritten and verified,
 * kept because nothing needed changing, and kept because a rewrite was caught adding something.
 */
function BulletRow({ bullet }: { bullet: TailoredBullet }) {
  const refused = bullet.rejected_reason !== null;

  return (
    <li className="rounded-card border border-rule bg-paper">
      <div className="p-4 sm:p-5">
        <p className="text-[15px] leading-relaxed text-ink">{bullet.tailored}</p>

        {bullet.changed && (
          <details className="mt-3">
            <summary className="cursor-pointer font-receipt text-[11px] tracking-[0.02em] text-slate underline-offset-4 hover:underline">
              what changed
            </summary>
            <p className="mt-2 border-l-2 border-rule pl-3 font-receipt text-[12px] leading-relaxed text-slate">
              {bullet.original}
            </p>
          </details>
        )}
      </div>

      <div className="border-t border-rule px-4 py-2.5 sm:px-5">
        {refused ? (
          <div>
            <ReceiptLine>
              {[
                <Fact key="state" tone="inferred">
                  rewrite refused — your sentence kept
                </Fact>,
              ]}
            </ReceiptLine>
            <p className="mt-1.5 text-[13px] leading-snug text-ink">
              {refusalWording(bullet.rejected_reason ?? "", bullet.rejected_detail)}
            </p>
            {bullet.rejected_text && (
              <details className="mt-1.5">
                <summary className="cursor-pointer font-receipt text-[11px] text-slate underline-offset-4 hover:underline">
                  what it wanted to write
                </summary>
                <p className="mt-1 border-l-2 border-inferred/40 pl-3 font-receipt text-[12px] leading-relaxed text-slate">
                  {bullet.rejected_text}
                </p>
              </details>
            )}
          </div>
        ) : (
          <ReceiptLine>
            {[
              bullet.changed ? (
                <Fact key="state" tone="confirmed">
                  rewritten, every claim checked against your original
                </Fact>
              ) : (
                <Fact key="state" tone="quiet">
                  unchanged
                </Fact>
              ),
            ]}
          </ReceiptLine>
        )}
      </div>
    </li>
  );
}

/** Where unmet requirements go, so they never end up in the experience section. */
function GapList({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) return null;

  return (
    <section className="mt-4 rounded-card border border-rule bg-paper p-5 sm:p-6">
      <h2 className="font-display text-[15px] font-bold text-ink">
        Asked for, and not supported by your resume
      </h2>
      <p className="mt-2 max-w-[68ch] text-[15px] text-slate">
        These stay here rather than being written into your experience. If you have used any of them
        somewhere your resume does not mention, adding it there is the honest fix.
      </p>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {gaps.map((gap) => (
          <li
            key={gap}
            className="rounded-chip border border-rule bg-blueprint px-1.5 py-0.5 font-receipt text-[11px] text-slate"
          >
            {gap}
          </li>
        ))}
      </ul>
    </section>
  );
}
