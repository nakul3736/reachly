/**
 * What Reachly read out of the resume.
 *
 * This is where the receipt device earns itself. Every bullet shows the content-derived
 * identifier that feature 04 will resolve tailored text against, and every date appears
 * exactly as the resume wrote it. A student can see the mechanism before it matters, which is
 * the point: the product's claim is that tailoring cannot invent experience, and that claim is
 * only believable if the evidence is visible beforehand.
 */

import { Fact, ReceiptLine } from "./Receipt";
import type { ParsedResume } from "../lib/student";

export function ParsedResumeView({ parsed }: { parsed: ParsedResume }) {
  // Projects may be absent entirely: every resume parsed before Reachly read them has no such key.
  const projects = parsed.projects ?? [];
  const experienceBullets = parsed.experience.reduce((n, role) => n + role.bullets.length, 0);
  const projectBullets = projects.reduce((n, project) => n + project.bullets.length, 0);
  const bulletCount = experienceBullets + projectBullets;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-card border border-rule bg-paper px-4 py-3">
        <ReceiptLine>
          {[
            <Fact key="roles" tone="confirmed">
              {`${parsed.experience.length} ${parsed.experience.length === 1 ? "role" : "roles"}`}
            </Fact>,
            <Fact key="projects" tone={projects.length > 0 ? "confirmed" : undefined}>
              {`${projects.length} ${projects.length === 1 ? "project" : "projects"}`}
            </Fact>,
            <Fact key="bullets">{`${bulletCount} bullets`}</Fact>,
            <Fact key="skills">{`${parsed.skills.length} skills`}</Fact>,
            <Fact key="chars" title="Characters of text extracted from your PDF.">
              {`${parsed.raw_text.length} chars read`}
            </Fact>,
            <Fact key="verbatim" tone="confirmed" title="Nothing here is absent from your document.">
              every line traced to your file
            </Fact>,
          ]}
        </ReceiptLine>
      </div>

      {parsed.summary && (
        <Section title="Summary">
          <p className="text-[15px] leading-[1.6] text-ink">{parsed.summary}</p>
        </Section>
      )}

      {parsed.experience.length > 0 && (
        <Section title="Experience">
          <ol className="flex flex-col gap-5">
            {parsed.experience.map((role) => (
              <li key={role.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h4 className="font-display text-[18px] font-bold tracking-[-0.01em] text-ink">
                    {role.title}
                  </h4>
                  {/*
                    Monospace, because the date is machine-read evidence rather than prose,
                    and shown byte-for-byte as written. "Aug 2023" is not tidied into
                    "August 2023" — that tidying is exactly the invention ADR 0006 prevents.
                  */}
                  <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                    {role.dates || "no dates given"}
                  </span>
                </div>
                <p className="mt-0.5 text-[15px] text-slate">{role.employer}</p>

                {role.bullets.length > 0 && (
                  <ul className="mt-3 flex flex-col gap-3">
                    {role.bullets.map((bullet) => (
                      <li key={bullet.id} className="border-l-2 border-rule pl-3">
                        <p className="text-[15px] leading-[1.6] text-ink">{bullet.text}</p>
                        <span
                          className="mt-1 inline-block font-receipt text-[11px] tracking-[0.02em] text-closed"
                          title="Derived from this bullet's own text. Tailored versions resolve back to this identifier, so a rewrite can always be traced to the line it came from."
                        >
                          {bullet.id}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </Section>
      )}

      {(parsed.projects ?? []).length > 0 && (
        <Section title="Projects">
          {/*
            Its own section, never folded into experience. Nobody employed the student to build
            these, and filing one under an employer would put a company on the resume that does not
            exist. For most graduates this is the strongest material in the document, so the bullets
            carry the same traceable ids as paid work and are tailored on the same terms.
          */}
          <ol className="flex flex-col gap-5">
            {parsed.projects.map((project) => (
              <li key={project.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h4 className="font-display text-[18px] font-bold tracking-[-0.01em] text-ink">
                    {project.name}
                  </h4>
                  <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                    {project.dates || "no dates given"}
                  </span>
                </div>

                {project.bullets.length > 0 && (
                  <ul className="mt-3 flex flex-col gap-3">
                    {project.bullets.map((bullet) => (
                      <li key={bullet.id} className="border-l-2 border-rule pl-3">
                        <p className="text-[15px] leading-[1.6] text-ink">{bullet.text}</p>
                        <span
                          className="mt-1 inline-block font-receipt text-[11px] tracking-[0.02em] text-closed"
                          title="Derived from this bullet's own text. Tailored versions resolve back to this identifier, so a rewrite can always be traced to the line it came from."
                        >
                          {bullet.id}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </Section>
      )}

      {parsed.education.length > 0 && (
        <Section title="Education">
          <ul className="flex flex-col gap-3">
            {parsed.education.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-x-4">
                <div>
                  <p className="text-[15px] font-medium text-ink">{entry.institution}</p>
                  {entry.credential && (
                    <p className="text-[15px] text-slate">{entry.credential}</p>
                  )}
                </div>
                <span className="font-receipt text-[11px] tracking-[0.02em] text-slate">
                  {entry.dates || "no dates given"}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {parsed.skills.length > 0 && (
        <Section title="Skills">
          {/*
            One chip per skill, which is the visible proof of a fix worth seeing. The model
            first returned seven "skills" for a resume containing forty-six, each one a whole
            category line such as "Languages: Java, Python, SQL". Skill overlap is 40% of the
            match score, so those blobs would have matched nothing and every score would have
            been wrong while looking fine.
          */}
          <ul className="flex flex-wrap gap-1.5">
            {parsed.skills.map((skill) => (
              <li
                key={skill}
                className="rounded-chip border border-confirmed/30 bg-confirmed/5 px-2 py-0.5 font-receipt text-[11px] tracking-[0.02em] text-confirmed"
              >
                {skill}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-card border border-rule bg-paper p-4 sm:p-5">
      <h3 className="font-receipt text-[11px] uppercase tracking-[0.08em] text-slate">
        {title}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}
