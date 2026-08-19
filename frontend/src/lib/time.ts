/**
 * Time, in the receipt voice: short, lowercase, unpunctuated, machine-like.
 *
 * Two functions rather than one, because the product treats two kinds of time
 * differently. When a job was *posted* is about the student's odds. When its board was last
 * *read* is about whether the posting still exists. Collapsing them into one "updated"
 * figure would hide exactly the thing that makes a feed trustworthy.
 */

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / 86_400_000);
}

/** How long ago a posting went up. Coarse on purpose — nobody needs minutes here. */
export function postedAge(iso: string | null): string {
  const days = daysSince(iso);
  if (days === null) return "posted date unknown";
  if (days <= 0) return "posted today";
  if (days === 1) return "posted 1d ago";
  if (days < 30) return `posted ${days}d ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "posted 1mo ago" : `posted ${months}mo ago`;
}

/** How long ago a board was read. Fine-grained, because staleness is the whole question. */
export function readAge(iso: string | null): string {
  if (!iso) return "never read";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never read";

  const minutes = Math.floor((Date.now() - then) / 60_000);
  if (minutes < 2) return "read just now";
  if (minutes < 60) return `read ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `read ${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "read 1d ago" : `read ${days}d ago`;
}

/** True once a posting is old enough that its date should read as a caution. */
export function isStale(iso: string | null): boolean {
  const days = daysSince(iso);
  return days !== null && days > 30;
}
