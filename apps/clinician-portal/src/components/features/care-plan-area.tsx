"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import { ClinicChip } from "@/components/features/clinic-chip";
import { PlanReviewItemRow } from "@/components/features/plan-review-items";
import { SharedMedicationList, useSharedSummary } from "@/components/features/shared-clinical-summary";
import { AdoptPlanDialog, RetireItemsDialog } from "@/components/features/unowned-plan-dialogs";
import { Icon } from "@/components/ui/icons";
import { useClinicMemberships } from "@/hooks/use-clinic-filter";
import { fetchPatientPlans, fetchReviewItems } from "@/services/care-team-plans";
import type { ClinicianPlanListEntry, PlanReviewItem } from "@/types";
import { formatClinicianDate } from "@/utils/dates";

type PlansState = { status: "loading" } | { status: "error" } | { status: "ready"; plans: ClinicianPlanListEntry[]; items: PlanReviewItem[] };

function teamLabel(owner: ClinicianPlanListEntry["owner"]): string {
    return [owner.specialty, owner.clinician_name].filter((part): part is string => Boolean(part && part.trim())).join(" · ") || "Care team";
}

function shortDate(value: string | null | undefined): string | null {
    return value ? formatClinicianDate(value, { month: "short", day: "numeric" }) : null;
}

const chip = "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold";

/** Status of one of my plans: Draft, Approved vN on date, or Unowned. */
function PlanStatus({ plan }: { plan: ClinicianPlanListEntry }) {
    const approved = shortDate(plan.approved_at);
    return <div className="flex flex-wrap items-center gap-1.5">
        {plan.draft_version_id ? <span className={`${chip} bg-ai-tint text-ai-ink`}>Draft</span> : null}
        {plan.ownership_state === "unowned" ? <span className={`${chip} bg-warn-tint text-warn-ink`}>Unowned</span> : null}
        {plan.ownership_state === "unassigned_legacy" ? <span className={`${chip} bg-warn-tint text-warn-ink`}>Unassigned</span> : null}
        {approved ? <span className={`${chip} bg-ok-tint text-ok-ink`}>
            {plan.approved_version_number ? `Approved v${plan.approved_version_number} · ${approved}` : `Approved plan live · ${approved}`}
        </span> : null}
        {!approved && !plan.draft_version_id && plan.ownership_state === "owned" ? <span className={`${chip} bg-sunken text-muted`}>No approved plan yet</span> : null}
    </div>;
}

/** The other teams' medicines, read from the shared list. Mounted only when another team has a plan. */
function SharedMedicationsBelow({ patientId }: { patientId: string }) {
    const { status, summary, reload } = useSharedSummary(patientId);
    if (status === "loading") return <p className="text-sm text-muted" role="status">Loading the shared medication list…</p>;
    if (status === "error" || !summary) return <p className="flex flex-wrap items-center gap-3 text-sm text-risk-ink" role="alert">The shared medication list could not be loaded. <button className="font-semibold text-primary hover:underline" onClick={() => void reload()} type="button">Try again</button></p>;
    return <SharedMedicationList summary={summary} />;
}

/**
 * The patient's care plans, grouped by care team: my plans first as full cards (the entry to the
 * draft review below), other teams' plans as compact read-only rows, plans nobody owns with
 * adopt/retire, and the review items for this patient. A patient with one plan of one team gets
 * exactly the draft review and nothing more.
 */
export function CarePlanArea({ patientId, onPublished, reviewId }: { patientId: string; onPublished?: () => void; reviewId?: string | null }) {
    const { clinics } = useClinicMemberships();
    const multiClinic = clinics.length >= 2;
    const [state, setState] = useState<PlansState>({ status: "loading" });
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [unowned, setUnowned] = useState<{ plan: ClinicianPlanListEntry; dialog: "adopt" | "retire" } | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const load = useCallback(async () => {
        const [plans, items] = await Promise.all([
            fetchPatientPlans(patientId),
            fetchReviewItems("open").catch(() => null),
        ]);
        return { plans: plans.plans ?? [], items: (items?.items ?? []).filter((item) => item.patient_id === patientId) };
    }, [patientId]);

    useEffect(() => {
        let active = true;
        void (async () => {
            try {
                const next = await load();
                if (active) setState({ status: "ready", ...next });
            } catch {
                // Without the list the draft review still works for a patient with one plan.
                if (active) setState({ status: "error" });
            }
        })();
        return () => { active = false; };
    }, [load]);

    const reload = useCallback(async () => {
        try {
            const next = await load();
            setState({ status: "ready", ...next });
        } catch { /* keep what is shown; a failed refresh must not erase the plans */ }
    }, [load]);

    if (state.status === "loading") {
        return <div aria-label="Loading care plan…" className="grid gap-4 rounded-2xl border border-line bg-surface p-5 xl:grid-cols-[300px_minmax(0,1fr)_400px]" role="status"><span className="sr-only">Loading care plan…</span>{[0, 1, 2].map((key) => <div className="space-y-3" key={key}><div className="ma-skeleton h-5 w-40 rounded" /><div className="ma-skeleton h-24 rounded-xl" /></div>)}</div>;
    }
    if (state.status === "error") return <CarePlanPanel onPublished={onPublished} patientId={patientId} />;

    const { plans, items } = state;
    const mine = plans.filter((plan) => plan.is_mine);
    const others = plans.filter((plan) => !plan.is_mine && plan.ownership_state === "owned");
    const orphaned = plans.filter((plan) => !plan.is_mine && plan.ownership_state !== "owned");
    const showOverview = plans.length >= 2 || others.length > 0 || orphaned.length > 0 || items.length > 0;
    const selected = mine.find((plan) => plan.care_plan_id === selectedId) ?? mine.find((plan) => plan.draft_version_id) ?? mine[0] ?? null;
    // A scope is only needed (and only sent) when I hold several plans for this patient.
    const scope = mine.length >= 2 && selected ? { careTeamId: selected.care_team_id ?? undefined, carePlanId: selected.care_plan_id } : undefined;
    const panel = <CarePlanPanel key={scope?.carePlanId ?? "single"} onPublished={() => { onPublished?.(); void reload(); }} patientId={patientId} scope={scope} />;
    // A notification link names one review item; it may be resolved, or not addressed to me.
    const missingReview = reviewId && !items.some((item) => item.id === reviewId)
        ? <p className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink" role="status"><Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />That review item is no longer open, or it is not addressed to your care team. Its outcome, if any, is in the plan below.</p>
        : null;
    if (!showOverview) return missingReview ? <div className="flex flex-col gap-4">{missingReview}{panel}</div> : panel;

    const adoptTeam = (plan: ClinicianPlanListEntry) => plan.adoptable_by_care_team_ids?.[0] ?? null;

    return <div className="flex flex-col gap-4">
        {missingReview}
        <section aria-labelledby="care-plans-heading" className="rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink" id="care-plans-heading">Care plans</h2>
                    <p className="text-[13px] text-muted">{plans.length} plan{plans.length === 1 ? "" : "s"} across {new Set(plans.map((plan) => plan.care_team_id ?? plan.care_plan_id)).size} care team{plans.length === 1 ? "" : "s"}. You can change and approve only your own.</p>
                </div>
                {items.length > 0 ? <a className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 text-[13px] font-semibold text-warn-ink hover:bg-warn-tint" href="#review-items">
                    <span aria-hidden="true" className="rounded-md bg-warn px-1.5 font-mono text-[11px] text-white">{items.length}</span>Care plan review item{items.length === 1 ? "" : "s"}
                </a> : null}
            </div>

            {notice ? <p className="mt-3 flex items-start gap-2 rounded-lg border border-ok-line bg-ok-soft px-3 py-2 text-sm text-ok-ink" role="status"><Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />{notice}</p> : null}

            {mine.length > 0 ? <ul aria-label="Your care plans" className="mt-4 grid gap-3 md:grid-cols-2">
                {mine.map((plan) => {
                    const isSelected = selected?.care_plan_id === plan.care_plan_id;
                    return <li className={`rounded-xl border p-4 ${isSelected ? "border-primary-line bg-primary-tint" : "border-line-strong bg-surface"}`} key={plan.care_plan_id}>
                        <p className="break-words text-[15px] font-semibold text-ink">{teamLabel(plan.owner)}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                            <span className="text-xs text-ink-2">Your plan</span>
                            <ClinicChip name={multiClinic ? plan.owner.clinic_name : null} />
                        </div>
                        <div className="mt-2.5"><PlanStatus plan={plan} /></div>
                        {mine.length >= 2 ? <button aria-pressed={isSelected} className={`ma-press mt-3 inline-flex min-h-9 items-center rounded-[9px] border px-3 text-[13px] font-semibold ${isSelected ? "border-primary bg-primary text-white" : "border-line-strong bg-surface text-ink-2 hover:bg-surface-2"}`} onClick={() => setSelectedId(plan.care_plan_id)} type="button">
                            {isSelected ? "Reviewing below" : plan.draft_version_id ? "Review draft" : "Open plan"}
                        </button> : <p className="mt-3 text-xs text-muted">{plan.draft_version_id ? "Review the draft below." : "Shown below."}</p>}
                    </li>;
                })}
            </ul> : <p className="mt-4 text-sm text-muted">You have no plan for this patient yet.</p>}

            {orphaned.length > 0 ? <div className="mt-5 space-y-2">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Needs an owner</h3>
                <ul className="divide-y divide-line rounded-xl border border-warn-line bg-warn-soft">
                    {orphaned.map((plan) => <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3" key={plan.care_plan_id}>
                        <div className="min-w-0 flex-1 basis-56">
                            <p className="break-words text-sm font-semibold text-ink">{teamLabel(plan.owner)}{plan.owner.clinic_name ? ` · ${plan.owner.clinic_name}` : ""}</p>
                            <div className="mt-1"><PlanStatus plan={plan} /></div>
                        </div>
                        {adoptTeam(plan) ? <div className="flex flex-wrap gap-2">
                            <button className="ma-press inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover" onClick={() => setUnowned({ plan, dialog: "adopt" })} type="button">Adopt this plan</button>
                            <button className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" onClick={() => setUnowned({ plan, dialog: "retire" })} type="button">Retire items</button>
                        </div> : null}
                    </li>)}
                </ul>
            </div> : null}

            {others.length > 0 ? <div className="mt-5 space-y-2">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Other care teams&apos; plans</h3>
                <ul aria-label="Other care teams' plans" className="divide-y divide-line rounded-xl border border-line bg-surface-2/60">
                    {others.map((plan) => <li className="px-4 py-2.5 text-[13px] text-ink-2" key={plan.care_plan_id}>
                        <span className="break-words font-semibold text-ink">{[plan.owner.specialty, plan.owner.clinician_name, plan.owner.clinic_name].filter(Boolean).join(" · ") || "Care team"}</span>
                        <span className="text-muted">{shortDate(plan.approved_at) ? ` · approved ${shortDate(plan.approved_at)}` : " · no approved plan"} · Medications shared below</span>
                    </li>)}
                </ul>
                <SharedMedicationsBelow patientId={patientId} />
            </div> : null}
        </section>

        {items.length > 0 ? <section aria-labelledby="review-items-heading" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" id="review-items">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-[22px] py-3.5">
                <h2 className="text-[15px] font-semibold text-ink" id="review-items-heading">Care plan review items</h2>
                <Link className="text-[13px] font-medium text-primary hover:underline" href={`/care-plan-reviews?patient=${encodeURIComponent(patientId)}`}>Open in review list</Link>
            </div>
            <ul>{items.map((item) => <PlanReviewItemRow highlighted={reviewId === item.id} item={item} key={item.id} onChanged={() => void reload()} />)}</ul>
        </section> : null}

        {panel}

        {unowned && adoptTeam(unowned.plan) ? <>
            <AdoptPlanDialog carePlanId={unowned.plan.care_plan_id} careTeamId={adoptTeam(unowned.plan) as string}
                onClose={() => setUnowned(null)}
                onDone={({ adopted, lost }) => { setUnowned(null); setNotice(adopted ? "You adopted this plan. It is yours to review and approve." : lost ? "Another clinician adopted this plan." : null); void reload(); }}
                open={unowned.dialog === "adopt"} patientId={patientId} />
            <RetireItemsDialog carePlanId={unowned.plan.care_plan_id} careTeamId={adoptTeam(unowned.plan) as string}
                onClose={() => setUnowned(null)}
                onDone={() => { setUnowned(null); setNotice("The selected items were retired from this plan."); void reload(); }}
                open={unowned.dialog === "retire"} patientId={patientId} />
        </> : null}
    </div>;
}
