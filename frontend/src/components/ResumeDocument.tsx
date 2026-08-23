/**
 * The resume as a document — what the student would actually send.
 *
 * Rendered as a page rather than as a list of changes, because a student deciding whether to accept a
 * rewrite is deciding how their resume reads, and a diff cannot answer that. The layout is
 * deliberately plain: one column, no colour, ordinary type. A resume that looks designed is a resume
 * an applicant tracking system parses badly.
 *
 * Printing is the export. `window.print()` with print styles produces a real PDF through the
 * browser's own dialog, which avoids putting a PDF renderer, its fonts and its failure modes on a
 * free-tier server for a file the browser can already make. The cost is that page breaks are the
 * browser's decision.
 *
 * Unapproved suggestions are marked on screen and hidden when printing — the marker is a working
 * note, and a printed resume carrying editorial annotations would be worse than no marker at all.
 */

import type { TailoredDocument } from "../lib/tailoring";

function Marker({ bullet }: { bullet: { applied: boolean; pending: boolean; refused: boolean } }) {
  if (bullet.applied) {
    return (
      <span className="ml-1.5 align-middle font-receipt text-[10px] tracking-[0.02em] text-confirmed print:hidden">
        tailored
      </span>
    );
  }
  if (bullet.pending) {
    return (
      <span className="ml-1.5 align-middle font-receipt text-[10px] tracking-[0.02em] text-inferred print:hidden">
        suggestion waiting for you
      </span>
    );
  }
  if (bullet.refused) {
    return (
      <span className="ml-1.5 align-middle font-receipt text-[10px] tracking-[0.02em] text-slate print:hidden">
        yours, a rewrite was refused
      </span>
    );
  }
  return null;
}

export function ResumeDocument({ document: doc }: { document: TailoredDocument }) {
  const links = Object.entries(doc.links ?? {});

  return (
    <article
      // A4-ish measure so what is on screen resembles what comes out of the printer.
      className="mx-auto max-w-[210mm] bg-paper px-8 py-10 text-ink print:max-w-none print:px-0 print:py-0"
      aria-label="Your resume as it would be sent"
    >
      <header className="border-b border-rule pb-4">
        <h2 className="font-display text-[26px] font-extrabold leading-tight tracking-[-0.02em]">
          {doc.name || "Your name"}
        </h2>
        <p className="mt-1 text-[13px] text-slate">
          {doc.email}
          {links.map(([label, url]) => (
            <span key={label}>
              <span aria-hidden="true" className="px-1.5 text-rule">
                /
              </span>
              {url}
            </span>
          ))}
        </p>
      </header>

      {doc.summary && (
        <section className="mt-5">
          <p className="text-[14px] leading-[1.6]">{doc.summary}</p>
        </section>
      )}

      {doc.experience.length > 0 && (
        <section className="mt-6">
          <h3 className="font-receipt text-[11px] uppercase tracking-[0.1em] text-slate">
            Experience
          </h3>
          <div className="mt-3 space-y-4">
            {doc.experience.map((entry, index) => (
              <div key={`${entry.employer}-${index}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="text-[15px] font-semibold">
                    {entry.title}
                    {entry.title && entry.employer ? ", " : ""}
                    {entry.employer}
                  </p>
                  {entry.dates && (
                    <p className="font-receipt text-[12px] text-slate">{entry.dates}</p>
                  )}
                </div>
                <ul className="mt-1.5 space-y-1">
                  {entry.bullets.map((bullet, bulletIndex) => (
                    <li
                      key={bulletIndex}
                      className="relative pl-4 text-[14px] leading-[1.55] before:absolute before:left-0 before:content-['•']"
                    >
                      {bullet.text}
                      <Marker bullet={bullet} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {doc.projects.length > 0 && (
        <section className="mt-6">
          <h3 className="font-receipt text-[11px] uppercase tracking-[0.1em] text-slate">
            Projects
          </h3>
          {/* Its own section, kept out of experience: nobody employed the student to build these,
              and filing a personal project under an employer would put a company on the resume that
              does not exist. For most graduates this is the strongest material in the document, so
              it is tailored on exactly the same terms as paid work. */}
          <div className="mt-3 space-y-4">
            {doc.projects.map((entry, index) => (
              <div key={`${entry.name}-${index}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="text-[15px] font-semibold">{entry.name}</p>
                  {entry.dates && (
                    <p className="font-receipt text-[12px] text-slate">{entry.dates}</p>
                  )}
                </div>
                <ul className="mt-1.5 space-y-1">
                  {entry.bullets.map((bullet, bulletIndex) => (
                    <li
                      key={bulletIndex}
                      className="relative pl-4 text-[14px] leading-[1.55] before:absolute before:left-0 before:content-['•']"
                    >
                      {bullet.text}
                      <Marker bullet={bullet} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {doc.education.length > 0 && (
        <section className="mt-6">
          <h3 className="font-receipt text-[11px] uppercase tracking-[0.1em] text-slate">
            Education
          </h3>
          <div className="mt-3 space-y-2">
            {doc.education.map((entry, index) => (
              <div
                key={`${entry.institution}-${index}`}
                className="flex flex-wrap items-baseline justify-between gap-x-3"
              >
                <p className="text-[14px]">
                  <span className="font-semibold">{entry.credential}</span>
                  {entry.credential && entry.institution ? ", " : ""}
                  {entry.institution}
                </p>
                {entry.dates && (
                  <p className="font-receipt text-[12px] text-slate">{entry.dates}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {doc.skills.length > 0 && (
        <section className="mt-6">
          <h3 className="font-receipt text-[11px] uppercase tracking-[0.1em] text-slate">
            Skills
          </h3>
          {/* The resume's own skills. Nothing the posting asked for is added here - that would be
              the fabrication the whole feature exists to prevent, and this is the easiest place to
              do it by accident. */}
          <p className="mt-2 text-[14px] leading-[1.6]">{doc.skills.join(" · ")}</p>
        </section>
      )}
    </article>
  );
}
