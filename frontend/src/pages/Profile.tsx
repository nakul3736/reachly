/**
 * The student's own page: what they are looking for, and what Reachly read from their resume.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ParsedResumeView } from "../components/ParsedResumeView";
import { Fact, ReceiptLine } from "../components/Receipt";
import { apiUrl } from "../lib/api";
import { ApiError, storedToken } from "../lib/auth";
import {
  UPLOAD_ADVICE,
  fetchParsedResume,
  fetchProfile,
  fetchResumes,
  studentKeys,
  updateProfile,
  uploadResume,
  type StudentProfile,
} from "../lib/student";

/** Human labels for the field names the API reports as missing. */
const FIELD_LABELS: Record<string, string> = {
  target_role: "target role",
  locations: "locations",
  skills: "skills",
  years_experience: "years of experience",
  name: "name",
  resume: "a resume",
};

export default function Profile() {
  const queryClient = useQueryClient();

  const profile = useQuery({ queryKey: studentKeys.profile(), queryFn: fetchProfile });
  const resumes = useQuery({ queryKey: studentKeys.resumes(), queryFn: fetchResumes });
  const parsed = useQuery({
    queryKey: studentKeys.parsed(),
    queryFn: fetchParsedResume,
    // A student with no resume yet gets a 404 here, which is an answer rather than a fault.
    retry: false,
  });

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-8 sm:px-6">
      <h1 className="font-display text-[32px] font-extrabold leading-none tracking-[-0.03em] text-ink">
        Your profile
      </h1>
      <p className="mt-3 max-w-[60ch] text-[15px] text-slate">
        What you are looking for, and what Reachly read out of your resume. Nothing here was
        written by Reachly — every line traces back to the file you uploaded.
      </p>

      <div className="mt-8 grid gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:items-start">
        <div className="flex flex-col gap-4">
          {profile.isPending && <PanelSkeleton />}
          {profile.isError && (
            <Panel title="Profile">
              <p className="text-[15px] text-slate">{(profile.error as Error).message}</p>
            </Panel>
          )}
          {profile.isSuccess && <ProfileForm profile={profile.data} />}

          <ResumePanel
            versions={resumes.data}
            loading={resumes.isPending}
            onUploaded={() => {
              void queryClient.invalidateQueries({ queryKey: studentKeys.resumes() });
              void queryClient.invalidateQueries({ queryKey: studentKeys.parsed() });
              void queryClient.invalidateQueries({ queryKey: studentKeys.profile() });
            }}
          />
        </div>

        <div>
          <h2 className="font-receipt text-[11px] uppercase tracking-[0.08em] text-slate">
            What Reachly read
          </h2>
          <div className="mt-3">
            {parsed.isPending && <PanelSkeleton />}
            {parsed.isError && <NoResumeYet error={parsed.error} />}
            {parsed.isSuccess && <ParsedResumeView parsed={parsed.data} />}
          </div>
        </div>
      </div>
    </main>
  );
}

function ProfileForm({ profile }: { profile: StudentProfile }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => ({
    name: profile.name ?? "",
    target_role: profile.target_role ?? "",
    // Empty string means unanswered. "0" means no experience. A graduate with no experience
    // is not a graduate who skipped the question, so the two must not collapse.
    years_experience: profile.years_experience === null ? "" : String(profile.years_experience),
    locations: profile.locations.join(", "),
    skills: profile.skills.join(", "),
  }));

  const save = useMutation({
    mutationFn: () =>
      updateProfile({
        name: form.name.trim() || null,
        target_role: form.target_role.trim() || null,
        years_experience: form.years_experience === "" ? null : Number(form.years_experience),
        locations: splitList(form.locations),
        skills: splitList(form.skills),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(studentKeys.profile(), updated);
    },
  });

  const missing = profile.missing_for_results;

  return (
    <Panel title="What you are looking for">
      <form
        className="flex flex-col gap-3.5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Text label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
        <Text
          label="Target role"
          placeholder="Backend Engineer"
          value={form.target_role}
          onChange={(v) => setForm({ ...form, target_role: v })}
        />
        <Text
          label="Years of experience"
          type="number"
          placeholder="0"
          value={form.years_experience}
          onChange={(v) => setForm({ ...form, years_experience: v })}
        />
        <Text
          label="Locations"
          hint="Comma separated. Location is a hard filter, not a preference."
          placeholder="Toronto, Remote"
          value={form.locations}
          onChange={(v) => setForm({ ...form, locations: v })}
        />
        <Text
          label="Skills"
          hint="Comma separated."
          placeholder="Python, PostgreSQL"
          value={form.skills}
          onChange={(v) => setForm({ ...form, skills: v })}
        />

        {missing.length > 0 && (
          <p className="rounded-card border border-inferred/40 bg-inferred/5 px-3 py-2 text-[13px] text-ink">
            Still needed before Reachly can match you:{" "}
            {missing.map((f) => FIELD_LABELS[f] ?? f).join(", ")}.
          </p>
        )}

        {save.isError && (
          <p role="alert" className="text-[13px] text-inferred">
            {(save.error as Error).message}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-card border border-ink bg-ink px-4 py-2 text-[15px] font-medium text-paper hover:bg-ink/90 disabled:opacity-60"
          >
            {save.isPending ? "Saving…" : "Save changes"}
          </button>
          {save.isSuccess && !save.isPending && (
            <span className="font-receipt text-[11px] tracking-[0.02em] text-confirmed">
              saved
            </span>
          )}
        </div>
      </form>
    </Panel>
  );
}

function ResumePanel({
  versions,
  loading,
  onUploaded,
}: {
  versions: ResumeVersionList;
  loading: boolean;
  onUploaded: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const upload = useMutation({
    mutationFn: (chosen: File) => uploadResume(chosen),
    onSuccess: () => {
      setFile(null);
      if (input.current) input.current.value = "";
      onUploaded();
    },
  });

  useEffect(() => {
    if (file) upload.mutate(file);
    // Uploading immediately on choice: a separate confirm step adds a click and no
    // information, since the file picker already was the decision.
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = versions?.find((v) => v.is_active);
  const advice =
    upload.error instanceof ApiError && upload.error.code
      ? UPLOAD_ADVICE[upload.error.code]
      : undefined;

  return (
    <Panel title="Master resume">
      {loading && <div className="h-[15px] w-2/3 rounded-chip bg-blueprint" aria-hidden="true" />}

      {active && (
        <div className="mb-3">
          <p className="text-[15px] text-ink">{active.filename}</p>
          <div className="mt-1">
            <ReceiptLine>
              {[
                <Fact key="v" tone="confirmed">{`version ${active.version}`}</Fact>,
                <Fact key="size">{`${(active.byte_size / 1024).toFixed(0)} kB`}</Fact>,
                <Fact key="count">
                  {`${versions?.length ?? 1} ${versions?.length === 1 ? "version" : "versions"} kept`}
                </Fact>,
              ]}
            </ReceiptLine>
          </div>
        </div>
      )}

      <label
        htmlFor="resume-file"
        className="block cursor-pointer rounded-card border border-dashed border-rule bg-blueprint/60 px-4 py-5 text-center hover:border-ink/30"
      >
        <span className="text-[15px] font-medium text-ink">
          {active ? "Upload a new version" : "Upload your resume"}
        </span>
        <span className="mt-1 block font-receipt text-[11px] tracking-[0.02em] text-slate">
          PDF with a text layer · up to 5 MB
        </span>
      </label>
      <input
        ref={input}
        id="resume-file"
        type="file"
        accept="application/pdf"
        className="sr-only"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />

      {upload.isPending && (
        <p className="mt-3 font-receipt text-[11px] tracking-[0.02em] text-slate">
          reading the document…
        </p>
      )}

      {upload.isError && (
        <div
          role="alert"
          className="mt-3 rounded-card border border-inferred/40 bg-inferred/5 px-3 py-2"
        >
          <p className="text-[13px] font-medium text-ink">
            {(upload.error as Error).message}
          </p>
          {advice && <p className="mt-1 text-[13px] text-slate">{advice}</p>}
          <p className="mt-1 font-receipt text-[11px] text-slate">
            nothing was stored — your previous version is still active
          </p>
        </div>
      )}

      {active && (
        <p className="mt-3">
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              void downloadResume(active.id, active.filename);
            }}
            className="font-receipt text-[11px] tracking-[0.02em] text-slate underline underline-offset-4 hover:text-ink"
          >
            download the original, byte for byte
          </a>
        </p>
      )}
    </Panel>
  );
}

type ResumeVersionList = Awaited<ReturnType<typeof fetchResumes>> | undefined;

/** Fetched with the token, so it cannot be a plain link. */
async function downloadResume(id: number, filename: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/resumes/${id}/file`), {
    headers: { Authorization: `Bearer ${storedToken() ?? ""}` },
  });
  if (!response.ok) return;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function NoResumeYet({ error }: { error: unknown }) {
  const missing =
    error instanceof ApiError &&
    (error.code === "no_active_resume" || error.code === "resume_not_parsed" || error.status === 404);

  return (
    <div className="rounded-card border border-rule bg-paper p-5">
      <h3 className="font-display text-[18px] font-bold text-ink">
        {missing ? "No resume yet" : "That could not be loaded"}
      </h3>
      <p className="mt-2 max-w-[52ch] text-[15px] text-slate">
        {missing
          ? "Upload a PDF and Reachly will show you exactly what it read — roles, dates as you wrote them, and every bullet with the identifier that keeps a tailored version honest."
          : (error as Error).message}
      </p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-card border border-rule bg-paper p-4 sm:p-5">
      <h2 className="font-receipt text-[11px] uppercase tracking-[0.08em] text-slate">
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function PanelSkeleton() {
  return (
    <div className="rounded-card border border-rule bg-paper p-5" aria-hidden="true">
      <div className="h-[11px] w-24 rounded-chip bg-blueprint" />
      <div className="mt-4 h-[15px] w-full rounded-chip bg-blueprint" />
      <div className="mt-2 h-[15px] w-4/5 rounded-chip bg-blueprint" />
    </div>
  );
}

function Text({
  label,
  value,
  onChange,
  placeholder,
  hint,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  type?: string;
}) {
  const id = `field-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div>
      <label htmlFor={id} className="block text-[13px] font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        type={type}
        min={type === "number" ? 0 : undefined}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-card border border-rule bg-paper px-3 py-2 text-[15px] text-ink placeholder:text-closed"
      />
      {hint && <p className="mt-1 text-[11px] text-slate">{hint}</p>}
    </div>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}
