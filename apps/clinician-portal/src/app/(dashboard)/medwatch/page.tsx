"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Badge, EmptyState, ErrorState } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
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
import {
    eventSummary,
    patientCode,
    productName,
    reportTabOf,
    type ReportTab,
} from "@/components/features/medwatch-report-meta";
import { fetchMedWatchDrafts, type MedWatchDraft } from "@/services/clinicians";

type ReportSort = "updated" | "oldest";

const TABS: { value: ReportTab; label: string }[] = [
    { value: "drafts", label: "Drafts" },
    { value: "approved", label: "Approved" },
    { value: "submitted", label: "Submitted" },
    { value: "discarded", label: "Discarded" },
];

const SORT_OPTIONS: { value: ReportSort; label: string }[] = [
    { value: "updated", label: "Recently updated" },
    { value: "oldest", label: "Least recently updated" },
];

const EMPTY_COPY: Record<ReportTab, string> = {
    drafts: "Prepare a draft from a reviewed ADR case to start a report.",
    approved: "Approved reports wait here until you download and submit them to FDA.",
    submitted: "Reports you recorded as submitted to FDA appear here.",
    discarded: "Discarded reports are kept here with their reason.",
};

const COLUMNS = "minmax(0,1fr) minmax(0,1.3fr) minmax(0,1.8fr) 150px 80px 20px";

function StatusChip({ draft }: { draft: MedWatchDraft }) {
    const tab = reportTabOf(draft);
    if (tab === "discarded") return <Badge variant="neutral">Discarded</Badge>;
    if (tab === "submitted") return <Badge variant="info">Submitted</Badge>;
    if (tab === "approved") return <Badge variant="success">Approved</Badge>;
    return draft.missingForApproval.length > 0 ? (
        <Badge variant="warning">{draft.missingForApproval.length} to complete</Badge>
    ) : (
        <Badge variant="neutral">Ready to approve</Badge>
    );
}

function ReportRow({ draft, from }: { draft: MedWatchDraft; from: string }) {
    const href = `/medwatch/${draft.id}${from ? `?from=${encodeURIComponent(from)}` : ""}`;
    const code = patientCode(draft);
    const product = productName(draft);
    const event = eventSummary(draft);
    const updated = ageLabel(draft.updatedAt);
    return (
        <div role="listitem">
            <Link className={rowLinkClass} href={href}>
                <div className="hidden items-center gap-4 md:grid" style={{ gridTemplateColumns: COLUMNS }}>
                    <p className="truncate font-mono text-sm font-semibold text-ink">{code}</p>
                    <p className="truncate text-sm text-ink-2">{product}</p>
                    <p className="truncate text-sm text-ink-2">{event}</p>
                    <div>
                        <StatusChip draft={draft} />
                    </div>
                    <p className="font-mono text-xs text-muted">{updated}</p>
                    <Icon aria-hidden="true" className="h-4 w-4 text-muted group-hover:text-ink" name="chevron" />
                </div>
                <div className="space-y-1 md:hidden">
                    <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate font-mono text-sm font-semibold text-ink">{code}</p>
                        <StatusChip draft={draft} />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate text-[13px] text-ink-2">
                            {product} · {event}
                        </p>
                        <p className="shrink-0 font-mono text-xs text-muted">{updated}</p>
                    </div>
                </div>
            </Link>
        </div>
    );
}

/** Old links (`/medwatch?assessment=<id>`) belong to the ADR case page now. */
function useLegacyRedirect() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const assessment = searchParams.get("assessment");
    useEffect(() => {
        if (assessment) router.replace(`/adr-reviews/${encodeURIComponent(assessment)}`);
    }, [assessment, router]);
    return Boolean(assessment);
}

function ReportsContent() {
    const redirecting = useLegacyRedirect();
    const { state, update, query } = useListUrlState({ tab: "drafts", q: "", sort: "updated", page: "1" });
    const tab = (TABS.some((candidate) => candidate.value === state.tab) ? state.tab : "drafts") as ReportTab;
    const sort = (SORT_OPTIONS.some((candidate) => candidate.value === state.sort) ? state.sort : "updated") as ReportSort;
    const [drafts, setDrafts] = useState<MedWatchDraft[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        setError(false);
        try {
            const [active, submitted, discarded] = await Promise.all([
                fetchMedWatchDrafts("active"),
                fetchMedWatchDrafts("submitted"),
                fetchMedWatchDrafts("discarded"),
            ]);
            setDrafts([...active, ...submitted, ...discarded]);
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!redirecting) void load();
    }, [load, redirecting]);

    const counts = useMemo(() => {
        const result: Record<ReportTab, number> = { drafts: 0, approved: 0, submitted: 0, discarded: 0 };
        for (const draft of drafts) result[reportTabOf(draft)] += 1;
        return result;
    }, [drafts]);

    const visible = useMemo(() => {
        const needle = state.q.trim().toLowerCase();
        return drafts
            .filter((draft) => {
                if (reportTabOf(draft) !== tab) return false;
                if (!needle) return true;
                return `${patientCode(draft)} ${productName(draft)} ${eventSummary(draft)}`
                    .toLowerCase()
                    .includes(needle);
            })
            .sort((left, right) =>
                sort === "updated"
                    ? right.updatedAt.localeCompare(left.updatedAt)
                    : left.updatedAt.localeCompare(right.updatedAt),
            );
    }, [drafts, tab, state.q, sort]);

    const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
    const page = Math.min(Math.max(1, Number.parseInt(state.page, 10) || 1), pageCount);
    const rows = visible.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    if (redirecting) return <ListSkeleton label="Opening ADR case" />;

    return (
        <div className="ma-page space-y-5">
            <PageHeader
                subtitle="Form FDA 3500 reports prepared from reviewed ADR cases. MediAgent never submits a report to FDA; you submit it yourself."
                title="MedWatch"
            />
            <StatusTabs
                label="MedWatch report status"
                onChange={(next) => update({ tab: next, page: "1" })}
                tabs={TABS.map((definition) => ({ ...definition, count: loading || error ? undefined : counts[definition.value] }))}
                value={tab}
            />
            <ListToolbar
                onSearch={(value) => update({ q: value, page: "1" })}
                onSort={(value) => update({ sort: value, page: "1" })}
                search={state.q}
                searchLabel="Search reports"
                searchPlaceholder="Search patient code, product or event"
                sort={sort}
                sortLabel="Sort"
                sortOptions={SORT_OPTIONS}
            />
            {loading ? <ListSkeleton label="Loading MedWatch reports" /> : null}
            {!loading && error ? (
                <ErrorState
                    description="Unable to load MedWatch reports. Try again."
                    onRetry={() => void load()}
                    title="Unable to load MedWatch reports"
                />
            ) : null}
            {!loading && !error && visible.length === 0 ? (
                <EmptyState
                    description={state.q.trim() ? "No reports match this search." : EMPTY_COPY[tab]}
                    icon={<Icon name="file" />}
                    title={state.q.trim() ? "No matching reports" : "No reports here"}
                />
            ) : null}
            {!loading && !error && rows.length > 0 ? (
                <>
                    <ListTable
                        columns={COLUMNS}
                        headers={["Patient code", "Product", "Event", "Status", "Updated", ""]}
                        label={`${TABS.find((candidate) => candidate.value === tab)?.label} reports`}
                    >
                        {rows.map((draft) => (
                            <ReportRow draft={draft} from={query} key={draft.id} />
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

export default function MedWatchPage() {
    return (
        <Suspense fallback={<ListSkeleton label="Loading MedWatch reports" />}>
            <ReportsContent />
        </Suspense>
    );
}
