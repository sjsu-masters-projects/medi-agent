"use client";

import { combinedOwnerLabel, getCareTeamCopy, ownerLabel } from "@/content/care-team-copy";
import { Icon } from "@/components/ui/icons";
import type { CareTeamFilterOption, FeedTask, Locale, PlanOwner } from "@/types";

/** The owners of a Today entry: several when identical activities of different plans are combined. */
export function taskOwners(task: FeedTask): PlanOwner[] {
    if (task.planOwners && task.planOwners.length > 0) return task.planOwners;
    return task.planOwner ? [task.planOwner] : [];
}

export function isUnownedOwner(owner: PlanOwner): boolean {
    return owner.unowned_notice || owner.ownership_state !== "owned";
}

/** Owner chrome is only shown when the feed has two or more owners; a single-team patient sees today's screen. */
export function hasMultipleOwners(tasks: FeedTask[], filters: CareTeamFilterOption[]): boolean {
    if (filters.length >= 2) return true;
    const ids = new Set<string>();
    for (const task of tasks) for (const owner of taskOwners(task)) ids.add(owner.care_plan_id);
    return ids.size >= 2;
}

export const UNOWNED_FILTER = "unowned";

export function taskMatchesFilter(task: FeedTask, filter: string): boolean {
    if (filter === "all") return true;
    return taskOwners(task).some((owner) => (filter === UNOWNED_FILTER ? isUnownedOwner(owner) : owner.care_team_id === filter));
}

/**
 * "Cardiology · Dr. Park · Cedar Grove" under the title, naming every owner of a combined
 * entry, plus the muted unowned caption. Wraps; never truncates.
 */
export function TaskOwnerLine({ task, locale, showOwner }: { task: FeedTask; locale: Locale; showOwner: boolean }) {
    const owners = taskOwners(task);
    if (owners.length === 0) return null;
    const copy = getCareTeamCopy(locale);
    const unowned = owners.filter(isUnownedOwner);
    const label = showOwner ? combinedOwnerLabel(owners, copy) : "";
    if (!label && unowned.length === 0) return null;
    // Spans: this line also sits inside the row's button, where block elements are not valid.
    return <span className="mt-0.5 block space-y-0.5" data-testid="task-owner">
        {label ? <span className="block break-words text-[13px] font-medium leading-snug text-ink-2 [overflow-wrap:anywhere]">{label}</span> : null}
        {unowned.length > 0 ? <span className="block break-words text-[12.5px] leading-snug text-muted [overflow-wrap:anywhere]">{copy.unownedNotice(unowned[0].clinician_name)}</span> : null}
    </span>;
}

export function filterChipLabel(option: CareTeamFilterOption, locale: Locale): string {
    const copy = getCareTeamCopy(locale);
    if (option.care_team_id === null) return copy.filterUnowned;
    return [option.specialty, option.clinician_name].filter(Boolean).join(" · ") || ownerLabel(option);
}

/** Horizontal chip filter; scrolls inside itself so the page never overflows at 360px. */
export function CareTeamFilterChips({ filters, value, onChange, locale }: {
    filters: CareTeamFilterOption[]; value: string; onChange: (value: string) => void; locale: Locale;
}) {
    const copy = getCareTeamCopy(locale);
    const options = [{ key: "all", label: copy.filterAll, count: null as number | null }, ...filters.map((option) => ({
        key: option.care_team_id ?? UNOWNED_FILTER, label: filterChipLabel(option, locale), count: option.count,
    }))];
    return <div role="group" aria-label={copy.filterLabel} data-testid="care-team-filter" className="min-w-0 max-w-full overflow-x-auto overscroll-x-contain px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex w-max gap-2">
            {options.map((option) => {
                const active = value === option.key;
                return <button key={option.key} type="button" aria-pressed={active} onClick={() => onChange(option.key)} className={`ma-press inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-2 text-[14px] font-semibold ${active ? "border-brand bg-brand text-white" : "border-line-strong bg-surface text-ink-2 hover:border-brand/40 hover:bg-brand-tint/50"}`}>
                    <span>{option.label}</span>
                    {option.count !== null ? <span className={`font-mono text-[12px] font-medium ${active ? "text-white/85" : "text-muted"}`}>{option.count}</span> : null}
                </button>;
            })}
        </div>
    </div>;
}

/** The patient has no active care team: tell them to contact the clinic. */
export function ContactClinicCard({ locale }: { locale: Locale }) {
    const copy = getCareTeamCopy(locale);
    return <section role="region" aria-labelledby="contact-clinic-title" className="mx-4 flex items-start gap-3 rounded-[22px] bg-note-tint p-4">
        <Icon name="info" className="mt-0.5 h-5 w-5 shrink-0 text-note-ink" />
        <div className="min-w-0 space-y-1">
            <h2 id="contact-clinic-title" className="text-[15px] font-semibold text-ink">{copy.contactClinicTitle}</h2>
            <p className="break-words text-[14px] leading-relaxed text-ink-2">{copy.contactClinicBody}</p>
        </div>
    </section>;
}
