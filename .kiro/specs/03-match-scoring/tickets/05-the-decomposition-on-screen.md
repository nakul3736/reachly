# 05 — The decomposition on screen

**What to build:** the four-segment bar the design brief specifies on every card, and the score
receipt on the detail screen.

The brief is explicit that a score is **never shown as a bare number**. A single opaque figure is
the thing this product exists to replace — the student already gets those from every job board that
ignores them.

**Blocked by:** 04.

**Status:** done

- [x] Every card shows the four segments, proportional to their weights, so a card where experience
      is the missing piece is visibly different in shape from one where skills are. The diagnosis is
      readable before any text is
- [x] The total appears with the decomposition, never alone
- [x] The detail screen carries a score receipt in mono: which skills matched, which did not, and
      what experience requirement was found **with the phrase it was read from**
- [x] `unstated` renders as its own state, visually distinct from both full marks and zero, because
      it means neither
- [x] Vocabulary-only extraction is distinguishable from model-enriched, so a student comparing two
      scores knows one posting was read more thoroughly — ADR 0011
- [x] The no-resume state explains what uploading adds, in the interface's voice, and links to the
      upload. An empty state is an invitation to act
- [x] Uses the existing tokens and the `confirmed`/`inferred` signal colours already defined; no new
      palette
- [x] Keyboard reachable, visible focus, and the bar is not the only carrier of meaning — a
      colour-blind or screen-reader user gets the same decomposition in text
- [x] Reduced motion respected if the bar animates at all
- [x] Verified by grepping the built bundle for the strings that must be present, not by trusting a
      successful build — a build-time guard once eliminated the entire application while reporting
      success
