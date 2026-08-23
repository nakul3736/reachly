/**
 * Outreach: a draft to send yourself.
 *
 * The screen is built around a refusal. Reachly will not send this message and will not guess who to
 * send it to, and both are stated on the page rather than hidden — a bounced email costs the student a
 * real opportunity, and they would never learn it happened.
 *
 * What it does instead is make the message true. Every specific sentence rests on something in the
 * database, and the evidence panel says which: the role from the posting, the skills from the match
 * score, the company's other openings from the index. That is also why there is no "make it more
 * enthusiastic" button. A graduate who tells a company they have long admired its work in distributed
 * systems, having met it ninety seconds ago, is worse off than one who sends four plain true
 * sentences.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../lib/auth";
import { fetchJob, queryKeys } from "../lib/jobs";
import { fetchOutreach, mailtoLink, outreachKeys } from "../lib/outreach";

export function OutreachPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);

  const [recipient, setRecipient] = useState("");
  const [copied, setCopied] = useState<"none" | "body" | "subject">("none");

  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => fetchJob(jobId),
    enabled: Number.isFinite(jobId),
  });

  const draft = useQuery({
    queryKey: outreachKeys.outreach(jobId),
    queryFn: () => fetchOutreach(jobId),
    retry: false,
    enabled: Number.isFinite(jobId),
  });

  const copy = async (what: "body" | "subject", text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(what);
    window.setTimeout(() => setCopied("none"), 2000);
  };

  return (
    <main className="mx-auto max-w-[820px] px-4 py-8 sm:px-6">
      <Link
        to={`/jobs/${jobId}`}
        className="font-receipt text-[11px] tracking-[0.02em] text-slate underline-offset-4 hover:underline"
      >
        &larr; back to the posting
      </Link>

      <h1 className="mt-3 font-display text-[24px] font-extrabold leading-tight tracking-[-0.02em] text-ink sm:text-[32px]">
        Introduce yourself
      </h1>

      {job.data && (
        <p className="mt-2 text-[15px] text-slate">
          about <span className="font-medium text-ink">{job.data.title}</span> at{" "}
          {job.data.company_name}
        </p>
      )}

      {draft.isError && (
        <div className="mt-6 rounded-card border border-rule bg-paper p-5">
          <p className="text-[15px] text-ink">
            {(draft.error as ApiError)?.message ?? "That draft could not be prepared."}
          </p>
        </div>
      )}

      {draft.data && (
        <>
          <div className="mt-6 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <label className="block">
              <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                who you are writing to
              </span>
              <input
                type="email"
                value={recipient}
                onChange={(event) => setRecipient(event.target.value)}
                placeholder="name@company.com"
                className="mt-1 w-full rounded-card border border-rule bg-paper px-3 py-2 text-[15px] text-ink placeholder:text-slate/60 focus:border-ink focus:outline-none"
              />
            </label>
            {/* Stated plainly rather than papered over with a guessed address. A pattern-matched
                address that bounces costs the student the opportunity and tells them nothing. */}
            <p className="mt-2 text-[14px] leading-[1.6] text-slate">
              Reachly does not guess email addresses. Look for a name on{" "}
              {draft.data.company_name}&apos;s careers or team page, or leave this empty and fill it
              in from your mail client. The application form below always works.
            </p>
            <a
              href={draft.data.apply_url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-2 inline-block font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink"
            >
              open the official application form
            </a>
          </div>

          <div className="mt-4 rounded-card border border-rule bg-paper p-5 sm:p-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-receipt text-[11px] tracking-[0.02em] text-slate">subject</p>
              <button
                type="button"
                onClick={() => copy("subject", draft.data.subject)}
                className="font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink"
              >
                {copied === "subject" ? "copied" : "copy"}
              </button>
            </div>
            <p className="mt-1 text-[15px] text-ink">{draft.data.subject}</p>

            <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2 border-t border-rule pt-4">
              <p className="font-receipt text-[11px] tracking-[0.02em] text-slate">message</p>
              <button
                type="button"
                onClick={() => copy("body", draft.data.body)}
                className="font-receipt text-[11px] tracking-[0.02em] text-slate underline decoration-rule underline-offset-2 hover:text-ink"
              >
                {copied === "body" ? "copied" : "copy"}
              </button>
            </div>
            <p className="mt-2 whitespace-pre-line text-[15px] leading-[1.6] text-ink">
              {draft.data.body}
            </p>

            <div className="mt-5 flex flex-wrap gap-2 border-t border-rule pt-4">
              <a
                href={mailtoLink(draft.data, recipient)}
                className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90"
              >
                Open in my email
              </a>
              <button
                type="button"
                onClick={() => copy("body", `${draft.data.subject}\n\n${draft.data.body}`)}
                className="rounded-card border border-ink px-4 py-2 text-[15px] font-medium text-ink hover:bg-blueprint"
              >
                Copy the whole thing
              </button>
            </div>
            <p className="mt-2 font-receipt text-[11px] leading-[1.6] text-slate">
              Reachly never sends this. It opens in your own mail client, from your own address, and
              you send it after reading it — so nothing goes out under your name that you have not
              seen.
            </p>
          </div>

          <div className="mt-4 rounded-card border border-rule bg-blueprint p-5 sm:p-6">
            <h2 className="font-display text-[15px] font-bold text-ink">
              Why it says what it says
            </h2>
            <ul className="mt-3 space-y-2">
              {draft.data.evidence.map((line) => (
                <li key={line} className="text-[14px] leading-[1.6] text-slate">
                  {line}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[14px] leading-[1.6] text-slate">
              There is no &quot;make it warmer&quot; button, on purpose. Every sentence here is
              something Reachly can point at, and enthusiasm a tool invented for you is the part a
              recruiter has read fifty times today. Add your own if you want it — it will be yours.
            </p>
          </div>
        </>
      )}
    </main>
  );
}
