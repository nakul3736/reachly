/**
 * The receipt: a machine-voiced annotation of where an assertion came from.
 *
 * The interface's signature device. Receipts are monospace because they are machine output
 * and should look like it; prose is sans. That split is the typographic rule the product
 * hangs on.
 *
 * `confirmed` and `inferred` are functional, never interchangeable. Confirmed means the
 * company's own board carries this posting. Inferred means an aggregator claimed it and
 * nobody has checked. Styling them alike would break the product's central promise.
 */

import type { ReactNode } from "react";

export type Tone = "confirmed" | "inferred" | "closed" | "quiet";

const TONE: Record<Tone, string> = {
  confirmed: "text-confirmed",
  inferred: "text-inferred",
  closed: "text-closed",
  quiet: "text-slate",
};

/** A single segment of a receipt line. */
export function Fact({
  children,
  tone = "quiet",
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  title?: string;
}) {
  return (
    <span className={`font-receipt text-[11px] tracking-[0.02em] ${TONE[tone]}`} title={title}>
      {children}
    </span>
  );
}

/**
 * A row of facts, separated by middots.
 *
 * The separator is drawn rather than typed into each fact so that segments can be added and
 * removed — filters in ticket 04, score components in feature 03 — without anyone having to
 * remember where the dots go.
 */
export function ReceiptLine({ children }: { children: ReactNode[] }) {
  const facts = children.filter(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {facts.map((fact, index) => (
        <span key={index} className="flex items-center gap-x-2">
          {index > 0 && (
            <span aria-hidden="true" className="font-receipt text-[11px] text-rule">
              ·
            </span>
          )}
          {fact}
        </span>
      ))}
    </div>
  );
}

/**
 * The verification state, as a bordered chip rather than plain text.
 *
 * Given a border because it is the one claim on the card a student should be able to find
 * without reading: is this posting confirmed by the employer, or only reported by somebody
 * else.
 */
export function VerificationChip({ verified }: { verified: boolean }) {
  return verified ? (
    <span
      className="inline-flex items-center rounded-chip border border-confirmed/40 bg-confirmed/5 px-1.5 py-0.5 font-receipt text-[11px] tracking-[0.02em] text-confirmed"
      title="This posting is on the company's own job board."
    >
      confirmed
    </span>
  ) : (
    <span
      className="inline-flex items-center rounded-chip border border-inferred/45 bg-inferred/5 px-1.5 py-0.5 font-receipt text-[11px] tracking-[0.02em] text-inferred"
      title="Seen on an aggregator, not on the company's own board. It may already be filled."
    >
      inferred
    </span>
  );
}
