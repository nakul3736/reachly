/**
 * Tailoring: review every proposed change, push back on any of them, approve what you want to keep.
 *
 * This screen is the product's argument. Other tools that offer to tailor a resume ask the student to
 * trust the output. This one shows the source of every sentence, shows what was refused and why, and
 * changes nothing until the student says so.
 *
 * Three decisions worth stating.
 *
 * **Nothing is applied by default.** A rewrite is a proposal. The resume on the right is the
 * student's own writing until they tick a box, because silence is not consent for words somebody
 * sends an employer under their own name.
 *
 * **Feedback is batched.** Comments on six bullets go in one request and cost one model call, so
 * iterating on a whole resume costs what iterating on one bullet costs. On a free tier that is the
 * difference between a loop a student can actually use and being rate-limited half way through.
 *
 * **The loop has no limit, and cannot drift.** Every revision is validated against the student's
 * original sentence, never against the previous rewrite — so a claim cannot arrive by degrees over
 * five rounds of "make it stronger", and the student can keep going until they are satisfied.
 *
 * The refusals are not hidden behind a disclosure. A student who reads "it tried to add Kubernetes,
 * which is not in this bullet" learns two things at once: that the fabrication was attempted, and
 * that something stopped it. Neither is available from a tool that silently succeeds.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ResumeDocument } from "../components/ResumeDocument";
import { ApiError } from "../lib/auth";
import {
  asPlainText,
  createTailoring,
  fetchTailoring,
  refusalWording,
  reviseBullets,
  setApprovals,
  tailoringKeys,
  type TailoredBullet,
  type TailoredResume,
} from "../lib/tailoring";

type View = "review" | "resume";

function BulletRow({
  bullet,
  approved,
  onToggle,
  feedback,
  onFeedback,
}: {
  bullet: TailoredBullet;
  approved: boolean;
  onToggle: (next: boolean) => void;
  feedback: string;
  onFeedback: (value: string) => void;
}) {
  const refused = Boolean(bullet.rejected_reason);
  const offered = bullet.changed && !refused;

  return (
    <li className="border-t border-rule py-4 first:border-t-0 first:pt-0">
      <p className="font-receipt text-[11px] tracking-[0.02em] text-slate">what you wrote</p>
      <p className="mt-1 text-[14px] leading-[1.55] text-slate">{bullet.original}</p>

      {offered && (
        <>
          <p className="mt-3 font-receipt text-[11px] tracking-[0.02em] text-slate">
            what Reachly suggests
          </p>
          <p className="mt-1 text-[15px] leading-[1.55] text-ink">{bullet.tailored}</p>

          <label className="mt-2 inline-flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={approved}
              onChange={(event) => onToggle(event.target.checked)}
              className="h-4 w-4 rounded border-rule accent-ink"
            />
            <span className="text-[14px] text-ink">
              {approved ? "Using the suggestion" : "Use this suggestion"}
            </span>
          </label>
        </>
      )}

      {refused && (
        <div className="mt-3 rounded-card border border-closed/30 bg-closed/5 p-3">
          <p className="font-receipt text-[11px] tracking-[0.02em] text-closed">rewrite refused</p>
          <p className="mt-1 text-[14px] leading-[1.55] text-ink">
            {refusalWording(bullet.rejected_reason ?? "", bullet.rejected_detail)} Your own sentence
            is being kept.
          </p>
          {bullet.rejected_text && (
            <details className="mt-2">
              <summary className="cursor-pointer font-receipt text-[11px] tracking-[0.02em] text-slate">
                what it wanted to write
              </summary>
              <p className="mt-1 text-[13px] leading-[1.55] text-slate">{bullet.rejected_text}</p>
            </details>
          )}
        </div>
      )}

      {!offered && !refused && (
        <p className="mt-2 font-receipt text-[11px] tracking-[0.02em] text-slate">
          left as you wrote it
        </p>
      )}

      <label className="mt-3 block">
        <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
          tell Reachly what to change about this line
        </span>
        <textarea
          value={feedback}
          onChange={(event) => onFeedback(event.target.value)}
          rows={2}
          placeholder="lead with the database work / make it shorter / say less about the tooling"
          className="mt-1 w-full rounded-card border border-rule bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-slate/60 focus:border-ink focus:outline-none"
        />
      </label>
    </li>
  );
}

export function TailorPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const queryClient = useQueryClient();

  const [view, setView] = useState<View>("review");
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  /** Ticked boxes, held locally so several can be changed before one request is sent. */
  const [selection, setSelection] = useState<Set<string> | null>(null);

  const existing = useQuery({
    queryKey: tailoringKeys.tailoring(jobId),
    queryFn: () => fetchTailoring(jobId),
    // A 404 means "not tailored yet", which is a normal state rather than a failure.
    retry: false,
    enabled: Number.isFinite(jobId),
  });

  const store = (data: TailoredResume) => {
    queryClient.setQueryData(tailoringKeys.tailoring(jobId), data);
    setSelection(new Set(data.approved_bullet_ids));
  };

  const tailor = useMutation({
    mutationFn: () => createTailoring(jobId),
    onSuccess: (data) => {
      store(data);
      setFeedback({});
    },
  });

  const approve = useMutation({
    mutationFn: (ids: string[]) => setApprovals(jobId, ids),
    onSuccess: store,
  });

  const revise = useMutation({
    mutationFn: (entries: { bullet_id: string; instruction: string }[]) =>
      // The ticks go with the feedback. Both happen on this screen at the same time, and sending
      // only the comments meant the server answered with its last stored approvals and wiped ticks
      // the student had made but not yet applied.
      reviseBullets(jobId, entries, [...approvedIdsRef.current]),
    onSuccess: (data) => {
      store(data);
      // The comments have been answered; leaving them in the boxes would invite sending them twice.
      setFeedback({});
    },
  });

  /**
   * The cache is the single source of truth, not the most recent mutation.
   *
   * This read used to be `revise.data ?? approve.data ?? tailor.data ?? existing.data`, which ranks
   * by which mutation happened to run, not by which is current. Once a revision had been made,
   * `revise.data` outranked everything for the rest of the session — so approving afterwards updated
   * the server and the screen carried on showing the pre-approval document, still labelling applied
   * suggestions as waiting. Every mutation writes to the cache, so reading the cache is both simpler
   * and correct.
   */
  const result = existing.data;
  const notFound = existing.isError && (existing.error as ApiError)?.status === 404;
  const blocked = existing.isError && (existing.error as ApiError)?.status === 409;

  /**
   * First arrival tailors immediately rather than asking.
   *
   * Producing the first draft is the application's job, not a favour the student requests: they
   * pressed "tailor my resume for this job" on the posting, and being met by a second button asking
   * the same question is a step that exists only because the code was built inside-out. What the
   * student is here to do is read the suggestions and push back on them, so the page starts with
   * suggestions to read.
   *
   * Guarded by a ref rather than by mutation state. Both are only true *after* the request starts, so
   * a re-render in the gap between the 404 arriving and the mutation registering would fire a second
   * model call — and the first thing this page does would be to spend twice the quota.
   */
  const autoStarted = useRef(false);
  useEffect(() => {
    if (notFound && !result && !autoStarted.current) {
      autoStarted.current = true;
      tailor.mutate();
    }
    // `tailor` is stable for the life of the component; listing it would re-run this on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notFound, result]);

  const approvedIds = selection ?? new Set(result?.approved_bullet_ids ?? []);

  // The mutation closure would otherwise capture whichever set existed when it was created, and send
  // a stale list of ticks. A ref is read at call time.
  const approvedIdsRef = useRef(approvedIds);
  useEffect(() => {
    approvedIdsRef.current = approvedIds;
  }, [approvedIds]);

  const pendingFeedback = Object.entries(feedback)
    .filter(([, instruction]) => instruction.trim().length > 0)
    .map(([bullet_id, instruction]) => ({ bullet_id, instruction }));

  const suggestions = (result?.bullets ?? []).filter((b) => b.changed && !b.rejected_reason);
  const unsavedApprovals =
    result != null &&
    (approvedIds.size !== result.approved_bullet_ids.length ||
      result.approved_bullet_ids.some((approvedId) => !approvedIds.has(approvedId)));

  const toggle = (bulletId: string, next: boolean) => {
    const current = new Set(approvedIds);
    if (next) current.add(bulletId);
    else current.delete(bulletId);
    setSelection(current);
  };

  const copy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(asPlainText(result));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="mx-auto max-w-[1100px] px-4 py-8 sm:px-6">
      <div className="print:hidden">
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
          <p className="mt-2 text-[15px] text-slate">
            for <span className="font-medium text-ink">{result.job_title}</span> at{" "}
            {result.company_name}
          </p>
        )}

        {blocked && (
          <div className="mt-6 rounded-card border border-rule bg-paper p-5">
            <p className="text-[15px] text-ink">{(existing.error as ApiError).message}</p>
            <Link
              to="/profile"
              className="mt-3 inline-block font-receipt text-[11px] tracking-[0.02em] text-slate underline underline-offset-2 hover:text-ink"
            >
              upload a resume
            </Link>
          </div>
        )}

        {notFound && !result && (
          <div className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <h2 className="font-display text-[16px] font-bold text-ink">
              {tailor.isError ? "That did not work" : "Rewriting your bullets for this posting…"}
            </h2>
            <p className="mt-2 text-[15px] leading-[1.6] text-slate">
              Reachly rewrites your own bullets to use this posting&apos;s language. It cannot add a
              skill, a number, a tool or an employer that is not already in your resume — every
              rewrite is checked against the sentence it came from, and anything that introduces a
              new claim is refused and shown to you. Nothing is applied until you approve it.
            </p>
            {tailor.isError && (
              <>
                <p className="mt-3 text-[14px] text-closed">
                  {(tailor.error as ApiError)?.message ??
                    "The model could not be reached just now."}
                </p>
                <button
                  type="button"
                  onClick={() => tailor.mutate()}
                  disabled={tailor.isPending}
                  className="mt-3 rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90 disabled:opacity-60"
                >
                  Try again
                </button>
              </>
            )}
          </div>
        )}

        {result && (
          <>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-card border border-rule p-0.5">
                {(["review", "resume"] as View[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setView(option)}
                    className={`rounded-[10px] px-3 py-1.5 text-[14px] font-medium ${
                      view === option ? "bg-ink text-paper" : "text-slate hover:text-ink"
                    }`}
                  >
                    {option === "review"
                      ? `Review changes (${suggestions.length})`
                      : "Your resume"}
                  </button>
                ))}
              </div>

              <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                {approvedIds.size} of {suggestions.length} suggestions in use
                {result.rejected_count > 0 && ` · ${result.rejected_count} refused`}
                {result.basis === "recorded" && " · recorded response"}
              </span>
            </div>

            {view === "review" && (
              <>
                <ul className="mt-4 rounded-card border border-rule bg-paper p-5 sm:p-6">
                  {result.bullets.map((bullet) => (
                    <BulletRow
                      key={bullet.bullet_id}
                      bullet={bullet}
                      approved={approvedIds.has(bullet.bullet_id)}
                      onToggle={(next) => toggle(bullet.bullet_id, next)}
                      feedback={feedback[bullet.bullet_id] ?? ""}
                      onFeedback={(value) =>
                        setFeedback((current) => ({ ...current, [bullet.bullet_id]: value }))
                      }
                    />
                  ))}
                </ul>

                {result.gaps.length > 0 && (
                  <div className="mt-4 rounded-card border border-rule bg-blueprint p-5">
                    <h2 className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                      Asked for, and not supported by your resume
                    </h2>
                    <p className="mt-2 flex flex-wrap gap-1.5">
                      {result.gaps.map((gap) => (
                        <span
                          key={gap}
                          className="rounded-chip border border-rule bg-paper px-1.5 py-0.5 font-receipt text-[11px] text-slate"
                        >
                          {gap}
                        </span>
                      ))}
                    </p>
                    <p className="mt-2 text-[14px] leading-[1.6] text-slate">
                      These stay out of your resume. If you have one of them and left it off, add it
                      to your master resume and tailor again — then it is your claim, made once,
                      rather than a sentence a model wrote on your behalf.
                    </p>
                  </div>
                )}

                {/* The action bar. Both actions are explicit and batched: approvals in one request,
                    all feedback in one model call. */}
                <div className="sticky bottom-4 mt-4 flex flex-wrap items-center gap-2 rounded-card border border-ink/15 bg-paper/95 p-3 backdrop-blur">
                  <button
                    type="button"
                    onClick={() => approve.mutate([...approvedIds])}
                    disabled={approve.isPending || !unsavedApprovals}
                    className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90 disabled:opacity-40"
                  >
                    {approve.isPending
                      ? "Saving…"
                      : unsavedApprovals
                        ? `Apply ${approvedIds.size} to my resume`
                        : "Approvals saved"}
                  </button>

                  <button
                    type="button"
                    onClick={() => revise.mutate(pendingFeedback)}
                    disabled={revise.isPending || pendingFeedback.length === 0}
                    className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint disabled:opacity-40"
                  >
                    {revise.isPending
                      ? "Rewriting…"
                      : `Send feedback on ${pendingFeedback.length} ${
                          pendingFeedback.length === 1 ? "line" : "lines"
                        }`}
                  </button>

                  <button
                    type="button"
                    onClick={() => setView("resume")}
                    className="rounded-card border border-rule px-3 py-2 text-[14px] font-medium text-ink hover:bg-blueprint"
                  >
                    Done — see my resume
                  </button>

                  {/* Destructive, so it says so. Re-tailoring discards every suggestion currently on
                      screen, including approved ones, and asks the model again from the student's
                      original bullets. Worth having - a first attempt can come back weak - but not
                      worth doing by accident after twenty minutes of review. */}
                  <button
                    type="button"
                    onClick={() => {
                      const approvedCount = approvedIds.size;
                      const warning =
                        approvedCount > 0
                          ? `Start again from your original resume? This discards all ${suggestions.length} suggestions, including the ${approvedCount} you approved.`
                          : "Start again from your original resume? This discards the current suggestions and asks again.";
                      if (window.confirm(warning)) tailor.mutate();
                    }}
                    disabled={tailor.isPending}
                    className="rounded-card border border-rule px-3 py-2 font-receipt text-[12px] text-slate hover:text-ink disabled:opacity-40"
                  >
                    {tailor.isPending ? "asking again…" : "start over"}
                  </button>

                  <span className="ml-auto font-receipt text-[11px] leading-[1.5] text-slate">
                    {pendingFeedback.length > 1
                      ? "all your comments go in one request"
                      : "keep going until you are happy with it"}
                  </span>
                </div>

                {revise.isError && (
                  <p className="mt-2 text-[14px] text-closed">
                    {(revise.error as ApiError)?.message ?? "That revision could not be made."}
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>

      {result && view === "resume" && (
        <>
          <div className="mt-4 flex flex-wrap gap-2 print:hidden">
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
            >
              Save as PDF or print
            </button>
            <button
              type="button"
              onClick={copy}
              className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint"
            >
              {copied ? "Copied" : "Copy as text"}
            </button>
            <p className="w-full font-receipt text-[11px] leading-[1.6] text-slate">
              This is your resume with the {approvedIds.size} suggestions you approved. Lines you
              have not approved are still your own words — the notes beside them do not print.
            </p>
          </div>

          <div className="mt-3 rounded-card border border-rule print:border-0">
            <ResumeDocument document={result.document} />
          </div>
        </>
      )}
    </main>
  );
}
