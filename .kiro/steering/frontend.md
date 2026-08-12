# Frontend steering

React 19 · TypeScript · Vite · Tailwind · dnd-kit · Recharts

`react-beautiful-dnd` from the original spec is deprecated and its repository is
archived. Use `dnd-kit`.

---

## Design direction

### Where it comes from

The subject is a new graduate's job search, and its defining feature is silence.
Applications vanish, rejections arrive unexplained, postings stay up after the role
is filled. Reachly's product thesis is that every claim carries its evidence — score
breakdowns, provenance traces, verification dates, closure detection.

So the interface is built on the idea of a **receipt**: any assertion the product
makes is accompanied by a small, consistent, machine-voiced annotation of where it
came from. That device is the signature, and it is the same device everywhere:

| Assertion | Its receipt |
|---|---|
| Match score 78 | the four weighted components that produced it |
| A tailored bullet | the span of the master resume it derives from |
| A recruiter address | provider, confidence, verification date |
| A posting's freshness | when its board was last read |

Receipts are set in monospace, because they are machine output and should look like
it. Prose is set in a humanist sans. That split — mono for evidence, sans for
speech — is the typographic rule the whole interface hangs on.

**The risk taken deliberately:** a score is never displayed as a bare number. It
always appears with its four-segment decomposition. Refusing to show an unexplained
number is a design position, and it is the same position the product takes.

### Tokens

Colour. Two signal colours are functional, not decorative: confirmed and inferred
must never be mistaken for one another.

```
ink        #101826   primary text, headings
slate      #4A5568   secondary text, labels
blueprint  #EEF2F6   page background (cool, not cream)
paper      #FFFFFF   cards and surfaces
rule       #D7DEE7   hairlines, dividers
confirmed  #0F766E   verified facts, open postings, matched skills
inferred   #B45309   guesses, unverified addresses, stale freshness
closed     #8A94A6   closed postings, completed states
```

No gradients. No glassmorphism. The palette is cool and paper-like so the two
signal colours are the only saturated things on screen and therefore always read as
meaning.

Type.

```
display   Bricolage Grotesque   700/800, tight tracking, used sparingly
body      Instrument Sans       400/500/600
receipt   IBM Plex Mono         400/500, 11–13px, wide tracking
```

Bricolage Grotesque is deliberately not a high-contrast serif — it reads engineered
rather than editorial, which suits a product about instrumentation.

Scale: 48 / 32 / 24 / 18 / 15 / 13 / 11. Body 15. Receipts 11–12.

Layout. The feed is the home screen; there is no dashboard. Content sits in a
single column, max 1100px, with generous vertical rhythm. Job cards are wide and
low: title and company left, the decomposed score bar right, the receipt line along
the bottom edge, separated by a hairline.

Radius is 4px everywhere except receipt chips, which are 2px. Shadows are avoided —
separation comes from hairlines and background contrast.

### What this is not

Not the warm cream plus high-contrast serif plus terracotta look. Not near-black
with an acid accent. Not a hairline-ruled broadsheet. Those are defaults rather than
choices, and none of them says anything about job hunting.

---

## Code conventions

Components are function components with typed props. No default exports except
route-level pages.

```
frontend/src/
  pages/         one per route
  components/    reusable, presentational
  features/      feature-scoped components with logic
  lib/           api client, formatters, hooks
  types/         shared types mirroring backend schemas
```

Server state goes through TanStack Query with query keys as constants — no manual
`useEffect` fetching. Local UI state uses `useState`. No global state library; if
something feels like it needs one, it probably belongs in a query.

The API client is a single typed module. Components never call `fetch` directly.

Tailwind utilities inline. Design tokens are defined in `tailwind.config.ts` and
referenced by name — no arbitrary hex values in components, since the whole point of
the confirmed/inferred distinction is that it is used consistently.

## Quality floor

Not announced, just met: responsive to 375px, visible keyboard focus on every
interactive element, `prefers-reduced-motion` respected, semantic HTML with real
`<button>` and `<label>` elements, ARIA only where semantics fall short.

Kanban drag has a keyboard-accessible equivalent — dnd-kit supports this, and a
drag-only interface excludes keyboard users.

Loading states are skeletons matching final layout, never spinners in place of
content. Empty states say what to do next. Errors say what happened and what to try.

## Motion

Sparingly, and only where it carries meaning: the score bar animates its segments on
first render, and the provenance trace draws its connection when a tailored bullet is
expanded. Nothing else animates. Scattered micro-interactions read as generated.
