# 08 — The screens feature 01 never got

**What to build:** a student can reach everything the first seven tickets built. They sign in,
say what they are looking for, upload a resume, and see what Reachly read out of it — with
every claim carrying the receipt that shows it came from their own document.

**Blocked by:** None. Tickets 01–07 are done; this is the interface over them.

**Status:** done

## Why this ticket exists at all

It is a correction. Tickets 01–07 were all backend, which was a deviation from the
tracer-bullet rule, and nothing was ever written down that owned their interface. The result
is that seven tickets of work — authentication, profile, upload, Gemini structuring, the
evidence check — are unreachable from the deployed application. A judge opening Reachly today
sees a job board and cannot sign in.

It also blocks more than itself. Feature 03 scores a resume against jobs and feature 04
tailors one, so without a way to sign in and upload, both would be built invisible too.

## Acceptance criteria

- [x] A visitor can register with an email and password, and is signed in afterwards
- [x] A returning student can sign in, and stays signed in across a page reload
- [x] **The demo credentials are offered on the sign-in screen as a one-click fill.** Rule 17
      requires judges be given working credentials, and a judge who has to find them in a
      README first has already formed an impression
- [x] Sign-in failure says what to do next, and never reveals whether the email exists —
      the enumeration guard in ticket 02 is worth nothing if the interface leaks it
- [x] A student can set name, target role, years of experience, locations and skills, and see
      what is still missing before results can be produced
- [x] Years of experience distinguishes zero from unanswered, because a graduate with no
      experience is not a graduate who skipped the question
- [x] A student can upload a resume PDF, and sees the version number, filename and size
- [x] Upload rejections are distinguishable and actionable: too large, wrong format, no text
      layer, parse failed. A scanned resume and a corrupt file need different advice
- [x] The parsed resume is shown: summary, roles with dates as written, bullets, skills
- [x] **Dates appear exactly as the resume wrote them.** Normalising them is the invention
      ADR 0006 exists to prevent, and the interface must not undo it
- [x] **Every bullet carries its content-derived identifier as a receipt.** This is the
      provenance feature 04 resolves against; showing it now means a student can see the
      mechanism before it matters
- [x] Skills are shown as the atomic skills they are, not as the grouped category lines the
      model first returned
- [x] The original PDF can be downloaded back, so the student can confirm nothing was altered
- [x] Signing out clears the token, and a signed-out visitor sent to a student page is
      returned to sign-in rather than shown an error
- [x] The feed stays reachable without an account — browsing jobs never requires signing in
- [x] Quality floor: responsive to 375px, visible keyboard focus, real `<button>` and
      `<label>` elements, skeletons matching final layout, `prefers-reduced-motion` respected

## Notes from implementation

**A build-time guard deleted the entire application, and the build reported success.**

`lib/api.ts` threw at module scope when `VITE_API_BASE_URL` was unset on a production build,
to prevent a deployed site that quietly requests the wrong origin. Rolldown can prove both
`import.meta.env.PROD` and the inlined variable statically, so it evaluated the condition, saw
an unconditional throw, and eliminated everything after it as unreachable � every component in
the app. The emitted bundle's final statement was that throw.

It was invisible from outside. `tsc -b` passed, `vite build` printed a successful summary with
84 modules transformed, and `index.html` returned 200. The bundle was 225 kB, which looks
entirely reasonable, because React and the router are imported before the throw and survived.
Only my own code was missing. Confirmed by searching the bundle for strings that had to be in
it: `Previous` from the feed pagination was absent. After moving the check to call time the
bundle is 297 kB � the missing 72 kB was the application.

Two lessons kept. A guard against a blank deployed page had become the cause of one, so
fail-fast at module scope is not safe in code a bundler constant-folds. And "the build
succeeded" is not evidence the build contains anything: the check now is to grep the artifact
for strings that must be present.

**Upload failures are advised separately per error code.** `resume_too_large`,
`unsupported_resume_format`, `resume_unreadable`, `resume_parse_failed` and `llm_unavailable`
each get their own sentence, because the student's fix differs completely � a scan needs
re-exporting, a renamed `.docx` needs converting, a large file needs compressing. Telling all
of them "upload failed" leaves the student guessing, and ticket 05 went to real trouble to keep
those cases distinguishable in the API.

**Years of experience keeps empty distinct from zero.** A graduate with no experience is not a
graduate who skipped the question, and the API already models that difference.

**Verified against the running app:** login issues a token, the profile returns Alex Rivera /
Backend Engineer / 1 year / 3 locations / 0 missing fields, and the parsed resume returns 2
roles and 11 atomic skills with dates reading `January 2026 - Present` and `Aug 2023` � `Aug`
not tidied into `August`, which is the ADR 0006 promise surviving all the way to the screen.