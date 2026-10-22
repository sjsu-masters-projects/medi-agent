"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { ClinicReviewItemRow, PlanReviewItemsList } from "@/components/features/plan-review-items";
import { Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";
import { fetchReviewItems } from "@/services/care-team-plans";
import { fetchDashboard } from "@/services/clinicians";
import type { ReviewItemList } from "@/types";

interface RosterEntry { label: string; clinicId: string | null; clinicName: string | null }

const ROSTER_PAGE_SIZE = 100;
const ROSTER_MAX_PAGES = 20;

/** Every page of the (clinic-filtered) roster, so a patient on a later page still gets a name and a clinic. */
async function loadRoster(clinicId: string | null): Promise<Map<string, RosterEntry> | null> {
    const entries = new Map<string, RosterEntry>();
    try {
        for (let page = 1; page <= ROSTER_MAX_PAGES; page += 1) {
            const dashboard = await fetchDashboard({ clinicId: clinicId ?? undefined, page, pageSize: ROSTER_PAGE_SIZE });
            for (const patient of dashboard.patients) {
                if (!entries.has(patient.patient_id)) {
                    entries.set(patient.patient_id, { label: `${patient.first_name} ${patient.last_name}`.trim(), clinicId: patient.clinic_id ?? null, clinicName: patient.clinic_name ?? null });
                }
            }
            if (dashboard.patients.length < ROSTER_PAGE_SIZE || entries.size >= dashboard.total) break;
        }
        return entries;
    } catch {
        return null;
    }
}

/**
 * Care plan review items: cross-plan asks and decisions, plans nobody owns, and legacy plans
 * that could not be assigned. This is where the notification-centre links for these items land
 * (`/care-plan-reviews?item=<id>`); the same items also show on the patient's Care Plan tab.
 */
function CarePlanReviewsContent() {
    const clinicFilter = useClinicFilter();
    const { clinicId, ready } = clinicFilter;
    const params = useSearchParams();
    const highlightId = params?.get("item") ?? null;
    const patientId = params?.get("patient") ?? null;
    const [list, setList] = useState<ReviewItemList | null>(null);
    const [roster, setRoster] = useState<Map<string, RosterEntry> | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const sequence = useRef(0);

    const load = useCallback(async () => {
        const request = ++sequence.current;
        setLoading(true); setError(null);
        try {
            // Names and clinics come from the roster: review items carry ids only.
            const [items, nextRoster] = await Promise.all([fetchReviewItems("open"), loadRoster(clinicId)]);
            if (request !== sequence.current) return;
            setList(items);
            setRoster(nextRoster);
        } catch (cause) {
            if (request !== sequence.current) return;
            setError(cause instanceof Error ? cause.message : "Unable to load care plan review items.");
        } finally {
            if (request === sequence.current) setLoading(false);
        }
    }, [clinicId]);

    useEffect(() => {
        if (!ready) return;
        void load();
        return () => { sequence.current += 1; };
    }, [ready, load]);

    const items = useMemo(() => (list?.items ?? []).filter((item) => {
        if (patientId && item.patient_id !== patientId) return false;
        // A clinic filter keeps the patients of that clinic (the roster is already filtered).
        return !clinicId || (roster ? roster.has(item.patient_id) : false);
    }), [list, patientId, clinicId, roster]);
    const clinicItems = useMemo(() => (list?.clinic_items ?? []).filter((item) => !clinicId || item.target_clinic_id === clinicId), [list, clinicId]);
    const clinicName = (id: string) => clinicFilter.clinics.find((clinic) => clinic.clinic_id === id)?.clinic_name ?? null;
    const lookup = useCallback((id: string) => {
        const entry = roster?.get(id);
        return { label: entry?.label ?? null, clinicName: clinicFilter.multi ? (entry?.clinicName ?? null) : null };
    }, [roster, clinicFilter.multi]);
    const total = items.length + clinicItems.length;

    return <div className="ma-page space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Care plan review items</h1>
                <p className="mt-1 max-w-[80ch] text-sm text-muted">Conflicts other care teams raised with your plans, decisions you were told about, and plans that need an owner. Answering an item never changes another team&apos;s plan.{clinicScopeLabel(clinicFilter) ? ` · ${clinicScopeLabel(clinicFilter)}` : ""}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
                <Link className="inline-flex min-h-9 items-center rounded-lg border border-line-strong bg-surface px-3 text-sm font-medium text-ink-2 hover:bg-surface-2" href={clinicId ? `/alerts?clinic=${encodeURIComponent(clinicId)}` : "/alerts"}>All clinical actions</Link>
                <ClinicFilterField filter={clinicFilter} />
                <button className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]" disabled={loading} onClick={() => void load()} type="button">
                    <Icon name="refresh" aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />{loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>
        </div>

        {patientId ? <p className="text-sm text-ink-2">Showing items for one patient. <Link className="font-medium text-primary hover:underline" href="/care-plan-reviews">Show all</Link></p> : null}
        {!loading && !error && roster === null && list ? <p className="rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-sm text-warn-ink" role="status">Patient names could not be loaded. Items are still listed and each opens its patient&apos;s care plan.</p> : null}

        {error ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink" role="alert">
            <span className="inline-flex items-center gap-2"><Icon name="alert" className="h-4 w-4 shrink-0" />{error}</span>
            <button className="ma-press h-8 rounded-lg border border-risk-line bg-surface px-3 text-xs font-semibold hover:bg-risk-tint" onClick={() => void load()} type="button">Retry</button>
        </div> : null}

        {loading && !list ? <div aria-busy="true" className="space-y-3"><p className="sr-only" role="status">Loading care plan review items…</p>{[0, 1].map((key) => <Skeleton className="h-32 w-full" key={key} />)}</div> : null}

        {!loading && !error && total === 0 ? <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-surface px-6 py-12 text-center">
            <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted"><Icon name="inbox" className="h-6 w-6" /></span>
            <p className="text-[15px] font-semibold text-ink">{clinicId ? <ClinicFilterEmpty filter={clinicFilter} noun="care plan review items" /> : "No open care plan review items"}</p>
            {clinicId ? null : <p className="text-sm text-muted">New conflicts and unowned plans appear here and in your alerts.</p>}
        </div> : null}

        {items.length > 0 ? <PlanReviewItemsList highlightId={highlightId} items={items} onChanged={() => void load()} patientLookup={lookup} /> : null}

        {clinicItems.length > 0 ? <section aria-labelledby="review-clinic-work" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
            <div className="border-b border-line px-[22px] py-3.5">
                <h2 className="text-[15px] font-semibold text-ink" id="review-clinic-work">Clinic work</h2>
                <p className="mt-0.5 text-xs text-muted">You are an administrator here. This shows that work exists, not which patient or activity.</p>
            </div>
            <ul>{clinicItems.map((item) => <ClinicReviewItemRow clinicName={clinicFilter.multi ? clinicName(item.target_clinic_id) : null} item={item} key={item.id} />)}</ul>
        </section> : null}
    </div>;
}

export default function CarePlanReviewsPage() {
    return <Suspense fallback={<p role="status">Loading care plan review items…</p>}><CarePlanReviewsContent /></Suspense>;
}
