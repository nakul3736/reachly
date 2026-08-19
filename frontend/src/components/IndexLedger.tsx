/**
 * The index ledger: a receipt for the whole feed.
 *
 * The signature device applied at page scale. Rather than promoting a count, it states what
 * was read and when — because the claim this product makes is not "we have lots of jobs", it
 * is "we checked these, here is when". Story 18.
 *
 * Deliberately not a statistics band with large display numerals. That version would say
 * "2,571 jobs · 16 companies · updated daily", which is marketing copy: it sounds confident
 * while telling a student nothing about whether today's feed is trustworthy.
 */

import type { BoardStatus } from "../lib/jobs";
import { readAge } from "../lib/time";
import { Fact, ReceiptLine } from "./Receipt";

export function IndexLedger({
  total,
  boards,
  loading,
}: {
  total: number | undefined;
  boards: BoardStatus[] | undefined;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="h-[17px] w-72 rounded-chip bg-paper" aria-hidden="true" />
    );
  }

  const active = boards?.filter((b) => b.active) ?? [];
  const failing = active.filter((b) => b.consecutive_failures > 0);
  const everRead = active.filter((b) => b.last_succeeded_at !== null);

  // The oldest successful read among active boards, not the newest. The feed is only as
  // current as its stalest source, and reporting the newest would flatter it.
  const oldest = everRead.reduce<string | null>((worst, board) => {
    if (!board.last_succeeded_at) return worst;
    if (!worst) return board.last_succeeded_at;
    return board.last_succeeded_at < worst ? board.last_succeeded_at : worst;
  }, null);

  return (
    <ReceiptLine>
      {[
        <Fact key="open" tone="confirmed">
          {`${total ?? 0} open ${total === 1 ? "role" : "roles"}`}
        </Fact>,
        <Fact key="boards">
          {`${active.length} ${active.length === 1 ? "board" : "boards"} registered`}
        </Fact>,
        everRead.length === 0 ? (
          <Fact key="never" tone="inferred">
            never read
          </Fact>
        ) : (
          <Fact key="oldest" tone="quiet" title="The feed is only as current as its stalest source.">
            {`oldest ${readAge(oldest)}`}
          </Fact>
        ),
        failing.length > 0 ? (
          <Fact key="failing" tone="inferred" title={failing.map((b) => b.company_name).join(", ")}>
            {`${failing.length} failing`}
          </Fact>
        ) : null,
      ]}
    </ReceiptLine>
  );
}
