"use client";

import { CompactField, compactSelectClass } from "@/components/ui/toolbar";
import type { ClinicFilter } from "@/hooks/use-clinic-filter";

/**
 * The clinic of a patient's link: a small neutral pill, the same tone for every clinic so the
 * meaning comes from the text. It renders only when the clinician belongs to several clinics.
 * It sits on its own line under a name and wraps rather than truncating; `title` keeps the full name.
 */
export function ClinicChip({ className = "", name }: { className?: string; name?: string | null }) {
    if (!name) {
        return null;
    }
    return (
        <span
            className={`inline-block max-w-full break-words rounded-full border border-line bg-surface-2 px-2 py-0.5 align-middle text-[11px] font-medium text-ink-2 ${className}`}
            title={name}
        >
            {name}
        </span>
    );
}

/** A patient header line: "Linked at <clinic>". Hidden for a single-clinic clinician. */
export function LinkedAt({ name }: { name?: string | null }) {
    if (!name) {
        return null;
    }
    return (
        <p className="text-[13px] text-muted">
            Linked at <span className="font-medium text-ink-2">{name}</span>
        </p>
    );
}

/** A labelled "Clinic" select with All clinics first. Hidden with fewer than two clinics. */
export function ClinicFilterField({ filter }: { filter: ClinicFilter }) {
    if (!filter.multi) {
        return null;
    }
    return (
        <CompactField label="Clinic">
            <select
                aria-label="Clinic"
                className={`${compactSelectClass} max-w-[200px] truncate`}
                onChange={(event) => filter.setClinicId(event.target.value || null)}
                value={filter.clinicId ?? ""}
            >
                <option value="">All clinics</option>
                {filter.clinics.map((clinic) => (
                    <option key={clinic.clinic_id} value={clinic.clinic_id}>
                        {clinic.clinic_name}
                    </option>
                ))}
            </select>
        </CompactField>
    );
}

/** The empty state of a clinic-filtered list. */
export function ClinicFilterEmpty({ filter, noun = "patients" }: { filter: ClinicFilter; noun?: string }) {
    return (
        <span>
            No {noun} at {filter.clinicName} match.{" "}
            <button
                className="font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                onClick={() => filter.setClinicId(null)}
                type="button"
            >
                Show all clinics
            </button>
        </span>
    );
}
