# Spike 002 — What a real resume PDF looks like to pdfplumber

**Date:** 2026-08-13
**Question:** is `pdfplumber.extract_text()` enough to structure a resume, and what
does the text actually look like?
**Answer:** yes for text, but line-based bullet splitting is wrong, and that would have
broken provenance silently.

## Method

One real resume, supplied by the developer. Deliberately **not** committed and not
copied into the repository — it carries a name, phone number and email address, and this
repository is public. A public repo plus a real resume is a privacy leak that no
`.gitignore` entry makes safe enough to be worth it. A fictional fixture is generated
for ticket 06 instead.

Structure was inspected via `extract_words(extra_attrs=["size", "fontname"])` grouped by
`top`, with body content redacted in the output.

## What the document is

| Property | Value |
|---|---|
| Producer | `pdfTeX-1.40.27`, `LaTeX with hyperref` |
| Pages | 2 |
| Size | 134 KB |
| Extracted text | 6,207 chars, 80 lines, **0 blank lines** |
| Encrypted | no |
| Font sizes | 6.0, 9.0, 10.0, 10.9, 12.0, 24.8 |
| Body size (mode) | 10.0 |

## Findings that change the design

### 1. Bullets wrap, and continuation lines carry no marker

The single most important observation. Line prefixes from `extract_text()`:

```
14 prefix='• '  len=118     <- bullet begins
15 prefix='an'  len=36      <- SAME bullet, wrapped, no marker
16 prefix='• '  len=116     <- next bullet
17 prefix='fr'  len=99      <- continuation again
```

A parser that treats one line as one bullet would split single bullets in two and
promote the tail to a bullet of its own.

This is not a cosmetic bug. Under ADR 0006 the `provenance_map` references bullet ids,
and the validator checks a generated bullet against its source span. A bullet split in
half has half its evidence, so the validator would reject faithful rewrites as
fabrications — and it would do so for the longest, most detailed bullets, which are
exactly the ones worth tailoring.

**Consequence:** continuation lines must be joined into the preceding bullet *before*
bullet ids are assigned. There must be a test with a genuinely wrapped bullet.

### 2. There are no blank lines to split sections on

`extract_text()` returned 80 lines and zero blank ones. Any section detection that
looks for blank-line separation finds nothing.

### 3. Headings are not upper case

Sections are `Skills`, `Experience`, `Achievements`, `Education` — title case. An
ALLCAPS heuristic, which is the obvious first guess, matches **zero** lines here.

### 4. The date is merged onto the title line

The date is right-aligned in the layout (x≈436–474) but `extract_text()` emits it on the
same line as the job title. Employer follows on the next line, in italic.

```
<Job Title> <Month Year - Month Year>
<Employer>
• bullet
  continuation
• bullet
```

### 5. Bold appears inside bullet text, not only in headings

Some bullets are set in `CMBX10` (bold) because a metric is emphasised, while
neighbouring bullets are `CMR10`. A classifier keying on "bold means heading" would
promote those bullets to headings.

### 6. Bullet glyphs are separate 6pt symbol-font elements

The marker is a `CMSY6` glyph at 6.0pt sitting at x≈36, while bullet text sits at x≈46.
It survives into `extract_text()` as `•`, which is what makes the text-only path viable.

## Decisions

1. **Text-only extraction is sufficient. Do not build a geometry-based parser.** The
   geometry here is clean and tempting, but it is LaTeX-specific — a Word resume has
   different fonts, sizes, and no `CMSY6` markers. A parser tuned to these coordinates
   would overfit to one document and fail on the next.
2. **Join wrapped bullets before assigning ids.** Ticket 05 must test this with a real
   wrapped bullet, not a synthetic one-line-per-bullet fixture.
3. **The `ResumeParser` protocol seam is justified.** Structuring strategy has to vary
   by document; the extraction step does not.
4. **Keep dates as written.** `January 2026 - Present` and `Aug 2023` appear in the same
   document. Normalising them into ranges means inventing precision the document does
   not contain, which is the failure ADR 0006 exists to prevent.
5. **Committed fixtures must include a wrapped bullet, mixed date formats, and a bolded
   mid-bullet metric** — all three are present in real output and all three break a
   naive parser.

## Note on the existing test fixture

`MINIMAL_PDF` in `app/tests/fixtures/pdf_bytes.py` passes the ticket 04 magic-byte
check, opens in pdfplumber, reports one page, and extracts `''`. It is therefore the
fixture for the *unreadable* branch — a structurally valid PDF with no text layer, which
is what a scanned resume looks like.
