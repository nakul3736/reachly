"""
Job source spike — validates coverage BEFORE any code depends on these sources.

Answers four questions per source:
  1. Does the endpoint respond without a key?
  2. Does it return FULL job description text? (tailoring needs this)
  3. How many roles are genuinely entry-level (0-1 years)?
  4. Are US/Canada locations represented?

Run:  python scripts/spike_sources.py
Uses only the standard library so it works before any dependency install.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

TIMEOUT = 25
UA = {"User-Agent": "reachly-spike/0.1 (hackathon source validation)"}
CTX = ssl.create_default_context()

# --- entry-level detection -------------------------------------------------

SENIOR_MARKERS = re.compile(
    r"\b(senior|staff|principal|lead|director|head of|manager|vp|architect|"
    r"sr\.?|iii|iv|expert)\b",
    re.I,
)
GRAD_MARKERS = re.compile(
    r"\b(new grad(uate)?s?|entry[- ]level|junior|intern(ship)?|early career|"
    r"campus|university grad|graduate program|associate|apprentice|"
    r"0-2 years|0-1 years|no experience required)\b",
    re.I,
)
YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus|or more)?\s*(?:-|to|–)?\s*(\d{1,2})?\s*"
    r"years?(?:\s+of)?(?:\s+\w+){0,3}?\s*experience",
    re.I,
)


def min_years(text: str) -> int | None:
    """Lowest years-of-experience requirement stated anywhere in the text."""
    found = [int(m.group(1)) for m in YEARS.finditer(text or "")]
    return min(found) if found else None


def classify(title: str, body: str) -> str:
    """entry | senior | unclear — biased toward what a new grad could apply to."""
    if SENIOR_MARKERS.search(title):
        return "senior"
    if GRAD_MARKERS.search(title):
        return "entry"
    yrs = min_years(body)
    if yrs is not None:
        return "entry" if yrs <= 1 else "senior"
    if GRAD_MARKERS.search(body or ""):
        return "entry"
    return "unclear"


def strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (
        s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    )
    return re.sub(r"\s+", " ", s).strip()


NA_HINT = re.compile(
    r"\b(united states|usa|u\.s\.|canada|remote|toronto|vancouver|montreal|"
    r"ottawa|calgary|waterloo|new york|nyc|san francisco|seattle|austin|boston|"
    r"chicago|los angeles|denver|atlanta|ca|ny|wa|tx|ma|on|bc)\b",
    re.I,
)


def get(url: str) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, {"_raw_len": len(raw)}
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001 - spike: report, never crash
        return -1, {"_error": type(e).__name__}


# --- per-source adapters --------------------------------------------------

GREENHOUSE = ["stripe", "airbnb", "dropbox", "coinbase", "figma", "databricks",
              "gitlab", "robinhood", "instacart", "affirm"]
LEVER = ["netflix", "brex", "plaid", "ramp", "attentive", "kickstarter"]
ASHBY = ["openai", "linear", "vanta", "notion", "cohere", "posthog"]


def probe_greenhouse(tok: str):
    st, d = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true")
    if st != 200 or not isinstance(d, dict):
        return st, []
    out = []
    for j in d.get("jobs", []):
        body = strip_html(j.get("content", ""))
        out.append({
            "title": j.get("title", ""),
            "loc": (j.get("location") or {}).get("name", ""),
            "body": body,
        })
    return st, out


def probe_lever(tok: str):
    st, d = get(f"https://api.lever.co/v0/postings/{tok}?mode=json")
    if st != 200 or not isinstance(d, list):
        return st, []
    out = []
    for j in d:
        body = " ".join(filter(None, [
            j.get("descriptionPlain", ""),
            " ".join(strip_html(l.get("content", "")) for l in j.get("lists", []) or []),
            j.get("additionalPlain", ""),
        ]))
        out.append({
            "title": j.get("text", ""),
            "loc": (j.get("categories") or {}).get("location", "") or "",
            "body": strip_html(body),
        })
    return st, out


def probe_ashby(tok: str):
    st, d = get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}")
    if st != 200 or not isinstance(d, dict):
        return st, []
    out = []
    for j in d.get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "loc": j.get("location", "") or "",
            "body": strip_html(j.get("descriptionPlain") or j.get("descriptionHtml") or ""),
        })
    return st, out


def probe_muse(pages: int = 3):
    rows, statuses = [], []
    for p in range(pages):
        st, d = get(
            "https://www.themuse.com/api/public/jobs"
            f"?page={p}&level=Entry%20Level&category=Software%20Engineering"
        )
        statuses.append(st)
        if st != 200 or not isinstance(d, dict):
            continue
        for j in d.get("results", []):
            locs = ", ".join(l.get("name", "") for l in j.get("locations", []) or [])
            rows.append({
                "title": j.get("name", ""),
                "loc": locs,
                "body": strip_html(j.get("contents", "")),
            })
    return statuses, rows


# --- reporting ------------------------------------------------------------

def summarise(label: str, rows: list[dict]) -> dict:
    if not rows:
        return {"source": label, "jobs": 0}
    kinds = Counter(classify(r["title"], r["body"]) for r in rows)
    bodies = [len(r["body"]) for r in rows]
    na = sum(1 for r in rows if NA_HINT.search(r["loc"] or ""))
    return {
        "source": label,
        "jobs": len(rows),
        "entry": kinds["entry"],
        "senior": kinds["senior"],
        "unclear": kinds["unclear"],
        "entry_pct": round(100 * kinds["entry"] / len(rows), 1),
        "median_body_chars": sorted(bodies)[len(bodies) // 2],
        "empty_bodies": sum(1 for b in bodies if b < 200),
        "na_locations_pct": round(100 * na / len(rows), 1),
    }


def main() -> None:
    print("=" * 74)
    print("REACHLY SOURCE SPIKE")
    print("=" * 74)

    results, all_rows = [], {}

    for label, toks, fn in [
        ("greenhouse", GREENHOUSE, probe_greenhouse),
        ("lever", LEVER, probe_lever),
        ("ashby", ASHBY, probe_ashby),
    ]:
        print(f"\n--- {label} ---")
        rows, ok, bad = [], [], []
        for t in toks:
            st, js = fn(t)
            (ok if st == 200 else bad).append(f"{t}:{st}")
            print(f"  {t:<14} status={st:<5} jobs={len(js)}")
            rows.extend(js)
        all_rows[label] = rows
        results.append(summarise(label, rows))
        print(f"  reachable {len(ok)}/{len(toks)}   failed: {bad or 'none'}")

    print("\n--- themuse (entry-level, software engineering) ---")
    st, rows = probe_muse()
    print(f"  page statuses={st}  jobs={len(rows)}")
    all_rows["themuse"] = rows
    results.append(summarise("themuse", rows))

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    hdr = ["source", "jobs", "entry", "entry_pct", "median_body_chars",
           "empty_bodies", "na_locations_pct"]
    print(" | ".join(h.rjust(17 if h == "median_body_chars" else 12) for h in hdr))
    for r in results:
        print(" | ".join(
            str(r.get(h, "-")).rjust(17 if h == "median_body_chars" else 12)
            for h in hdr
        ))

    print("\nSample entry-level titles found:")
    for label, rows in all_rows.items():
        ents = [r for r in rows if classify(r["title"], r["body"]) == "entry"]
        print(f"\n  [{label}] {len(ents)} entry-level")
        for r in ents[:6]:
            print(f"    - {r['title'][:58]:<58} | {(r['loc'] or '?')[:30]}")

    with open("scripts/spike_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nWrote scripts/spike_results.json")


if __name__ == "__main__":
    main()
