# 0006 — Tailoring is provenance-checked and cannot invent experience

Status: Accepted · 2026-08-11

## Context

The original specification had a model rewrite the resume summary and "the 3
weakest experience bullets to match the JD's exact keywords and phrasing."

Stated that way, nothing prevents the model from inventing experience. Asked to
make a bullet match a description that requires Kubernetes, the most natural
completion mentions Kubernetes — whether or not the student has touched it. The
output carries the student's name and goes to an employer. That is resume fraud
produced by the tool, and the student may not notice.

This is also the strongest available product differentiator. Resume tailoring is a
crowded category and every competitor instructs the model not to fabricate. That
instruction fails silently and cannot be verified by the user.

## Decision

Tailoring is constrained by construction, not by request.

Every tailored bullet carries a pointer to the span in the master resume it
derives from, stored as `ResumeVersion.provenance_map`. The interface shows the
before-and-after so the student can see exactly what changed.

A validator runs after generation and before the result is ever shown. It extracts
named entities, technologies, and numerals from the source span and from the
generated text, and asserts the generated set is a subset of the source set. Any
bullet introducing a claim absent from the source is rejected, retried once, and
falls back to the original bullet unchanged if it fails again.

The permitted transformation is therefore rephrasing, reordering, and emphasis —
the vocabulary of the description applied to experience the student actually has.
Where a genuine requirement is unmet, that belongs in the skill gap list, not in
the resume.

## Rejected

**Prompt instruction alone.** What every competitor does. Fails silently, and
gives the student no way to check.

**Rewriting the whole resume.** The original specification's instinct to leave
most of the document untouched was right, for a reason worth recording: uniformly
model-rewritten resumes read as machine-written, and the tell is tonal
consistency across sections a human would have written at different times.

**Flagging suspected fabrication as a warning.** Softer and worse. A warning on a
document the student is about to send puts the burden of catching the tool's error
on the person least equipped to notice it.

## Consequences

- The validator is the last thing cut under time pressure. It is the
  differentiator and the correctness guarantee in one piece of code.
- A curated skills vocabulary is needed for entity extraction, shared with
  scoring in [0003](0003-deterministic-scoring-over-llm.md) and with the skill
  gap resource map.
- Skill gap resources come from a hand-curated map for the most common skills, not
  from model-generated URLs, which hallucinate and produce dead links. Estimated
  hours-to-learn is dropped entirely as fabricated precision.
- Rejection is a visible, demonstrable behaviour, which makes it the strongest
  single moment available in the demo video: a bullet that would require invention,
  refused on camera.
