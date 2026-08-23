# 03 — The four components and their arithmetic

**What to build:** `score_job(profile, posting) -> MatchBreakdown` — the four weighted components,
summing to 0–100, each an integer within its own weight.

**Blocked by:** 01 and 02. Skills and experience are two of the four components.

**Status:** done

- [x] Skill overlap scores 0–40 from profile skills against the posting's extracted skills
- [x] Experience fit scores 0–30, full marks when the requirement is met, tapering as the gap grows
- [x] Keyword similarity scores 0–20 from BM25 over the description against the resume text
- [x] Freshness scores 0–10, full marks today, tapering to zero across a month
- [x] **Location is not a component.** ADR 0003: the wrong country is not a weak match, and it is
      already excluded by a filter
- [x] Components are integers **within their own weight**, so the parts sum to the total exactly. A
      student who reads the segments and the total must not find them a point apart
- [x] **An unstated requirement scores the neutral share and is labelled `unstated`**, never zero.
      Zero would rank a description that omitted its requirements below one stating requirements the
      student fails, which is backwards
- [x] **A posting listing no skills scores the neutral share on skills**, for the same reason, and
      the breakdown says so
- [x] A student with no resume gets a breakdown that is explicitly incomplete rather than zeros, so
      the interface can explain what uploading would add — story 34
- [x] The breakdown carries **which skills matched and which did not**, so the score is inspectable
      term by term rather than only as a number
- [x] Deterministic: the same profile and posting produce the same score every time, with no clock
      dependency beyond freshness, which takes an injected reference time
- [x] Totals are stable under reordering of the profile's skills
- [x] No model calls anywhere in this module — ADR 0003, non-negotiable 5
