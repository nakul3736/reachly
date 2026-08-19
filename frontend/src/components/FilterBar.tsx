/**
 * Feed filters.
 *
 * Offered as intents rather than as a form over the schema. A student does not think "seniority
 * in (entry, unknown)", they think "roles I could actually get".
 *
 * That particular preset is the important one, and the numbers are why. Of 2,586 real postings
 * indexed, 1,886 carry an explicit senior marker and only 14 carry an explicit entry-level one.
 * A control offering "entry level" alone would return almost nothing and read as broken; what
 * works is excluding what is definitely too senior and keeping the 686 unmarked postings, which
 * is where a graduate's real opportunities are.
 */

import type { JobQuery } from "../lib/jobs";

const SOFTWARE_FAMILIES = ["software_engineering", "data_ml", "infrastructure", "quality"];

export interface FilterState {
  graduateFriendly: boolean;
  technicalOnly: boolean;
  remoteOnly: boolean;
  countries: string[];
  q: string;
}

export const NO_FILTERS: FilterState = {
  graduateFriendly: false,
  technicalOnly: false,
  remoteOnly: false,
  countries: [],
  q: "",
};

/** Translate intents into the query the API understands. */
export function toQuery(state: FilterState): JobQuery {
  return {
    seniority: state.graduateFriendly ? ["entry", "unknown"] : [],
    roleFamily: state.technicalOnly ? SOFTWARE_FAMILIES : [],
    country: state.countries,
    remote: state.remoteOnly ? true : undefined,
    q: state.q.trim() || undefined,
  };
}

export function activeCount(state: FilterState): number {
  return (
    (state.graduateFriendly ? 1 : 0) +
    (state.technicalOnly ? 1 : 0) +
    (state.remoteOnly ? 1 : 0) +
    (state.countries.length > 0 ? 1 : 0) +
    (state.q.trim() ? 1 : 0)
  );
}

export function FilterBar({
  state,
  onChange,
  total,
  loading,
}: {
  state: FilterState;
  onChange: (next: FilterState) => void;
  total: number | undefined;
  loading: boolean;
}) {
  const active = activeCount(state);

  const toggleCountry = (code: string) => {
    const next = state.countries.includes(code)
      ? state.countries.filter((c) => c !== code)
      : [...state.countries, code];
    onChange({ ...state, countries: next });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <label htmlFor="job-search" className="sr-only">
          Search titles and descriptions
        </label>
        <input
          id="job-search"
          type="search"
          value={state.q}
          onChange={(e) => onChange({ ...state, q: e.target.value })}
          placeholder="Search titles and descriptions"
          className="w-full rounded-card border border-rule bg-paper px-3 py-2 text-[15px] text-ink placeholder:text-closed sm:max-w-[320px]"
        />
        <p className="font-receipt text-[11px] tracking-[0.02em] text-slate sm:ml-1">
          {loading ? "counting…" : `${total ?? 0} matching`}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Toggle
          on={state.graduateFriendly}
          onClick={() => onChange({ ...state, graduateFriendly: !state.graduateFriendly })}
          title="Excludes titles marked senior, staff, principal, lead, manager, director and level II and above. Keeps unmarked postings, which is where most graduate openings are."
        >
          open to graduates
        </Toggle>
        <Toggle
          on={state.technicalOnly}
          onClick={() => onChange({ ...state, technicalOnly: !state.technicalOnly })}
          title="Engineering, data, infrastructure and quality. Excludes commercial roles such as Solutions Engineer."
        >
          technical roles
        </Toggle>
        <Toggle on={state.countries.includes("US")} onClick={() => toggleCountry("US")}>
          united states
        </Toggle>
        <Toggle on={state.countries.includes("CA")} onClick={() => toggleCountry("CA")}>
          canada
        </Toggle>
        <Toggle
          on={state.remoteOnly}
          onClick={() => onChange({ ...state, remoteOnly: !state.remoteOnly })}
        >
          remote
        </Toggle>

        {active > 0 && (
          <button
            type="button"
            onClick={() => onChange(NO_FILTERS)}
            className="ml-1 font-receipt text-[11px] tracking-[0.02em] text-slate underline underline-offset-4 hover:text-ink"
          >
            clear {active}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * A filter toggle.
 *
 * A real `<button>` with `aria-pressed` rather than a styled div, so it is reachable and
 * announced. Set in the receipt face because a filter is machine instruction, not prose.
 */
function Toggle({
  on,
  onClick,
  title,
  children,
}: {
  on: boolean;
  onClick: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      title={title}
      onClick={onClick}
      className={`rounded-chip border px-2 py-1 font-receipt text-[11px] tracking-[0.02em] transition-colors ${
        on
          ? "border-ink bg-ink text-paper"
          : "border-rule bg-paper text-slate hover:border-ink/30 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
