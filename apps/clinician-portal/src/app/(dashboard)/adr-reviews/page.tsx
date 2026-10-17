"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { EmptyState, ErrorState } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
    CausalityPill,
    ListSkeleton,
    ListTable,
    ListToolbar,
    PAGE_SIZE,
    PageHeader,
    Pagination,
    StatusTabs,
    ageLabel,
    rowLinkClass,
    useListUrlState,
} from "@/components/features/work-list";
import { ClinicChip, ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { useResolvedClinicFilter } from "@/hooks/use-clinic-filter";
import { missingCount, queueTabOf, type QueueTab } from "@/components/features/adr-queue";
import { fetchADRReviewQueue, type ADRReviewQueueItem } from "@/services/clinicians";

type QueueSort = "score" | "oldest" | "newest";

const TABS: { value: QueueTab; label: string }[] = [
    { value: "awaiting", label: "Awaiting review" },
    { value: "information", label: "Information requested" },
    { value: "reviewed", label: "Reviewed" },
    { value: "dismissed", label: "Dismissed" },
];

const SORT_OPTIONS: { value: QueueSort; label: string }[] = [
    { value: "score", label: "Score, high to low" },
    { value: "oldest", label: "Oldest first" },
    { value: "newest", label: "Newest first" },
];

const EMPTY_COPY: Record<QueueTab, string> = {
    awaiting: "No assessments are waiting for your review.",
    information: "No assessments are waiting on a patient's answers.",
    reviewed: "Assessments you have reviewed appear here.",
    dismissed: "Assessments you have dismissed appear here.",
};

const COLUMNS =
    "minmax(0,1.3fr) minmax(0,1.4fr) minmax(0,1.2fr) 150px 90px 56px 20px";

function QueueRow({ item, from, showClinic }: { item: ADRReviewQueueItem; from: string; showClinic: boolean }) {
    const name = `${item.patientFirstName} ${item.patientLastName}`.trim();
    const missing = missingCount(item);
    const href = `/adr-reviews/${item.id}${from ? `?from=${encodeURIComponent(from)}` : ""}`;
    const age = ageLabel(item.createdAt);
    return (
        <div role="listitem">
            <Link className={rowLinkClass} href={href}>
                {/* Wide: one grid row. Narrow: patient and score on line one, reaction and age below. */}
                <div
                    className="hidden items-center gap-4 md:grid"
                    style={{ gridTemplateColumns: COLUMNS }}
                >
                    <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink" title={name}>{name}</p>
                        <p className="truncate text-xs text-muted">Severity {item.severity}/10</p>
                        {showClinic ? <ClinicChip className="mt-0.5" name={item.clinicName} /> : null}
                    </div>
                    <p className="truncate text-sm text-ink-2" title={item.symptom}>{item.symptom}</p>
                    <p className="truncate text-sm text-ink-2" title={item.suspectMedicationName}>{item.suspectMedicationName}</p>
                    <div>
                        <CausalityPill band={item.causality} score={item.naranjoScore} />
                    </div>
                    <p className={`text-sm ${missing ? "font-medium text-warn-ink" : "text-muted"}`}>
                        {missing ? `${missing} ${missing === 1 ? "item" : "items"}` : "—"}
                    </p>
                    <p className="font-mono text-xs text-muted">{age}</p>
                    <Icon aria-hidden="true" className="h-4 w-4 text-muted group-hover:text-ink" name="chevron" />
                </div>
                <div className="space-y-1 md:hidden">
                    <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate text-sm font-semibold text-ink" title={name}>{name}</p>
                        <CausalityPill band={item.causality} score={item.naranjoScore} />
                    </div>
                    {showClinic ? <ClinicChip name={item.clinicName} /> : null}
                    <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate text-[13px] text-ink-2" title={`${item.symptom} · ${item.suspectMedicationName}`}>
                            {item.symptom} · {item.suspectMedicationName}
                        </p>
                        <p className="shrink-0 font-mono text-xs text-muted">
                            {missing ? <span className="mr-2 font-sans font-medium text-warn-ink">{missing} missing</span> : null}
                            {age}
                        </p>
                    </div>
                </div>
            </Link>
        </div>
    );
}

function QueueContent() {
    const { state, update, query } = useListUrlState({
        tab: "awaiting",
        q: "",
        sort: "score",
        page: "1",
        clinic: "",
    });
    const clinicFilter = useResolvedClinicFilter(state.clinic || null, (clinic) =>
        update({ clinic: clinic ?? "", page: "1" }),
    );
    const { clinicId, ready } = clinicFilter;
    const tab = (TABS.some((candidate) => candidate.value === state.tab) ? state.tab : "awaiting") as QueueTab;
    const sort = (SORT_OPTIONS.some((candidate) => candidate.value === state.sort) ? state.sort : "score") as QueueSort;
    const [items, setItems] = useState<ADRReviewQueueItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        setError(false);
        try {
            setItems(await fetchADRReviewQueue({ status: "all", clinicId }));
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }, [clinicId]);

    useEffect(() => {
        if (ready) {
            void load();
        }
    }, [load, ready]);

    const counts = useMemo(() => {
        const result: Record<QueueTab, number> = { awaiting: 0, information: 0, reviewed: 0, dismissed: 0 };
        for (const item of items) result[queueTabOf(item)] += 1;
        return result;
    }, [items]);

    const visible = useMemo(() => {
        const needle = state.q.trim().toLowerCase();
        const matches = items.filter((item) => {
            if (queueTabOf(item) !== tab) return false;
            if (!needle) return true;
            return `${item.patientFirstName} ${item.patientLastName} ${item.suspectMedicationName} ${item.symptom}`
                .toLowerCase()
                .includes(needle);
        });
        return matches.sort((left, right) => {
            if (sort === "score") return right.naranjoScore - left.naranjoScore || left.createdAt.localeCompare(right.createdAt);
            return sort === "oldest"
                ? left.createdAt.localeCompare(right.createdAt)
                : right.createdAt.localeCompare(left.createdAt);
        });
    }, [items, tab, state.q, sort]);

    const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
    const page = Math.min(Math.max(1, Number.parseInt(state.page, 10) || 1), pageCount);
    const rows = visible.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    return (
        <div className="ma-page space-y-5">
            <PageHeader
                subtitle="Suspected adverse drug reactions awaiting clinician review. Scores are decision support, not a verdict."
                title="ADR Reviews"
            />
            <StatusTabs
                label="ADR review status"
                onChange={(next) => update({ tab: next, page: "1" })}
                tabs={TABS.map((definition) => ({ ...definition, count: loading || error ? undefined : counts[definition.value] }))}
                value={tab}
            />
            <ListToolbar
                onSearch={(value) => update({ q: value, page: "1" })}
                onSort={(value) => update({ sort: value, page: "1" })}
                search={state.q}
                searchLabel="Search by patient or medicine"
                searchPlaceholder="Search patient or medicine"
                extra={<ClinicFilterField filter={clinicFilter} />}
                sort={sort}
                sortLabel="Sort"
                sortOptions={SORT_OPTIONS}
            />
            {loading ? <ListSkeleton label="Loading ADR reviews" /> : null}
            {!loading && error ? (
                <ErrorState
                    description="Unable to load ADR reviews. Try again."
                    onRetry={() => void load()}
                    title="Unable to load ADR reviews"
                />
            ) : null}
            {!loading && !error && visible.length === 0 ? (
                clinicId && items.length === 0 ? (
                    <p className="rounded-2xl border border-line bg-surface px-6 py-12 text-center text-sm text-ink-2">
                        <ClinicFilterEmpty filter={clinicFilter} noun="cases" />
                    </p>
                ) : (
                    <EmptyState
                        description={state.q.trim() ? "No cases match this search." : EMPTY_COPY[tab]}
                        icon={<Icon name="inbox" />}
                        title={state.q.trim() ? "No matching cases" : "Nothing here"}
                    />
                )
            ) : null}
            {!loading && !error && rows.length > 0 ? (
                <>
                    <ListTable
                        columns={COLUMNS}
                        headers={["Patient", "Suspected reaction", "Suspect medicine", "Score", "Missing", "Age", ""]}
                        label={`${TABS.find((candidate) => candidate.value === tab)?.label} cases`}
                    >
                        {rows.map((item) => (
                            <QueueRow from={query} item={item} key={item.id} showClinic={clinicFilter.multi} />
                        ))}
                    </ListTable>
                    <Pagination
                        onChange={(next) => update({ page: String(next) })}
                        page={page}
                        pageCount={pageCount}
                        total={visible.length}
                    />
                </>
            ) : null}
        </div>
    );
}

export default function ADRReviewsPage() {
    return (
        <Suspense fallback={<ListSkeleton label="Loading ADR reviews" />}>
            <QueueContent />
        </Suspense>
    );
}
