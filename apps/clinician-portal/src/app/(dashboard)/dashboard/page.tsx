"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { useFlip } from "@/components/ui/motion";
import { CompactField, SegmentedControl, compactSelectClass } from "@/components/ui/toolbar";
import { readStoredClinicContext } from "@/services/clinic-context";
import { ClinicChip, ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { RiskBadge } from "@/components/features/risk-badge";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";
import { fetchPatientRiskSnapshot } from "@/services/clinicians";
import { subscribeDashboardRealtime } from "@/services/dashboard-realtime";
import { loadDashboard, patchPatient } from "@/store/slices/dashboard-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type {
    DashboardSortBy,
    DashboardSortOrder,
    PatientRiskData,
} from "@/services/clinicians";

// ── Risk level configuration ─────────────────────────────────────────────────

const riskConfig = {
    high: {
        accent: "bg-risk-tint text-risk-ink",
        progressBar: "bg-risk",
        action: "Review",
        actionClass: "border border-risk-line text-risk-ink hover:bg-risk-soft",
    },
    medium: {
        accent: "bg-warn-tint text-warn-ink",
        progressBar: "bg-primary",
        action: "View Profile",
        actionClass: "text-muted hover:bg-surface-2 border border-line",
    },
    low: {
        accent: "bg-ok-tint text-ok-ink",
        progressBar: "bg-primary",
        action: "View Profile",
        actionClass: "text-muted hover:bg-surface-2 border border-line",
    },
    unknown: {
        accent: "bg-sunken text-ink-2",
        progressBar: "bg-primary",
        action: "Review",
        actionClass: "text-muted hover:bg-surface-2 border border-line",
    },
} satisfies Record<PatientRiskData["risk_level"], {
    accent: string;
    progressBar: string;
    action: string;
    actionClass: string;
}>;

const riskRank: Record<PatientRiskData["risk_level"], number> = {
    high: 3,
    medium: 2,
    low: 1,
    unknown: 0,
};

function getLastActivityMinutes(lastActivity: string): number {
    const match = lastActivity.match(/(\d+)([mhd]) ago$/i);
    if (!match) {
        return Number.POSITIVE_INFINITY;
    }

    const value = Number(match[1]);
    const unit = match[2]?.toLowerCase();
    if (unit === "m") {
        return value;
    }
    if (unit === "h") {
        return value * 60;
    }
    if (unit === "d") {
        return value * 24 * 60;
    }
    return Number.POSITIVE_INFINITY;
}

function comparePatients(
    left: PatientRiskData,
    right: PatientRiskData,
    sortBy: DashboardSortBy,
    sortOrder: DashboardSortOrder,
): number {
    const direction = sortOrder === "asc" ? 1 : -1;

    switch (sortBy) {
        case "adherence":
            return (left.adherence_score - right.adherence_score) * direction;
        case "last_activity":
            return (getLastActivityMinutes(left.last_activity) - getLastActivityMinutes(right.last_activity)) * direction;
        case "med_count":
            return (left.active_med_count - right.active_med_count) * direction;
        case "risk":
        default:
            return (riskRank[left.risk_level] - riskRank[right.risk_level]) * direction;
    }
}

function noopSubscribe() {
    return () => undefined;
}

function storedClinicName() {
    try { return readStoredClinicContext()?.clinicName ?? null; } catch { return null; }
}

function todayLabel() {
    return new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const stats = useSelector((state: RootState) => state.dashboard.stats);
    const patients = useSelector((state: RootState) => state.dashboard.patients);
    const loading = useSelector((state: RootState) => state.dashboard.loading);
    const error = useSelector((state: RootState) => state.dashboard.error);
    const [query, setQuery] = useState("");
    const [riskFilter, setRiskFilter] = useState<"all" | PatientRiskData["risk_level"]>("all");
    const [sortBy, setSortBy] = useState<DashboardSortBy>("risk");
    const [sortOrder, setSortOrder] = useState<DashboardSortOrder>("desc");
    const [minMedCount, setMinMedCount] = useState("0");
    const clinicFilter = useClinicFilter();
    const { clinicId, ready } = clinicFilter;

    const reloadDashboard = useCallback(() => {
        void dispatch(
            loadDashboard({
                sortBy,
                sortOrder,
                riskFilter: riskFilter === "all" ? undefined : riskFilter,
                minMedCount: Number(minMedCount) || 0,
                clinicId,
            }),
        );
    }, [clinicId, dispatch, minMedCount, riskFilter, sortBy, sortOrder]);

    // Fetch real data on mount and when sort/filter changes
    useEffect(() => {
        if (ready) {
            reloadDashboard();
        }
    }, [ready, reloadDashboard]);

    useEffect(() => {
        const pendingPatientIds = new Set<string>();
        let flushTimer: ReturnType<typeof setTimeout> | null = null;
        let cancelled = false;

        const flushQueue = () => {
            flushTimer = null;
            const patientIds = Array.from(pendingPatientIds);
            pendingPatientIds.clear();

            for (const patientId of patientIds) {
                void fetchPatientRiskSnapshot(patientId)
                    .then((patient) => {
                        if (cancelled) {
                            return;
                        }
                        dispatch(patchPatient(patient));
                    })
                    .catch(() => {
                        // Best-effort sync only; hard failures are recovered by manual refresh.
                    });
            }
        };

        const queuePatientRefresh = (patientId: string) => {
            pendingPatientIds.add(patientId);

            if (flushTimer) {
                return;
            }

            flushTimer = setTimeout(flushQueue, 350);
        };

        const unsubscribe = subscribeDashboardRealtime({
            onPatientChanged: (patientId) => {
                queuePatientRefresh(patientId);
            },
        });

        return () => {
            cancelled = true;
            if (flushTimer) {
                clearTimeout(flushTimer);
            }
            unsubscribe();
        };
    }, [dispatch]);

    const visiblePatients = useMemo(() => {
        const loweredQuery = query.trim().toLowerCase();

        return [...patients]
            .filter((patient) => {
                if (
                    riskFilter !== "all"
                    && patient.risk_level !== riskFilter
                ) {
                    return false;
                }

                if (patient.active_med_count < (Number(minMedCount) || 0)) {
                    return false;
                }

                if (!loweredQuery) {
                    return true;
                }

                return `${patient.first_name} ${patient.last_name}`
                    .toLowerCase()
                    .includes(loweredQuery);
            })
            .sort((left, right) => comparePatients(left, right, sortBy, sortOrder));
    }, [minMedCount, patients, query, riskFilter, sortBy, sortOrder]);

    const flip = useFlip(visiblePatients.map((patient) => patient.patient_id).join(","));
    const storedClinic = useSyncExternalStore(noopSubscribe, storedClinicName, () => null);
    const scopeLabel = clinicScopeLabel(clinicFilter, storedClinic);
    const today = useSyncExternalStore(noopSubscribe, todayLabel, () => "");
    const statTone = (label: string) => label.includes("Critical") ? "text-risk" : label.includes("ADR") || label.includes("MedWatch") ? "text-warn-ink" : "text-ink";
    const columns = "grid-cols-[minmax(200px,1.3fr)_112px_minmax(170px,1fr)_minmax(200px,1.4fr)_minmax(150px,1fr)_112px]";

    return (
        <div className="ma-page flex flex-col gap-[22px]">
            {/* Error banner */}
            {error && (
                <div
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-5 py-3.5 text-sm text-risk-ink"
                    role="alert"
                >
                    <span className="inline-flex items-center gap-2"><Icon name="alert" className="h-4 w-4 shrink-0" />{error}{patients.length > 0 ? " — showing cached data" : ""}</span>
                    <button
                        className="ma-press h-8 rounded-lg border border-risk-line bg-surface px-3 text-xs font-semibold hover:bg-risk-tint"
                        onClick={reloadDashboard}
                        type="button"
                    >
                        Retry
                    </button>
                </div>
            )}

            {/* Header band: same three metrics, laid over a static perspective floor */}
            <section aria-label="Dashboard statistics" className="relative flex flex-wrap items-end justify-between gap-x-10 gap-y-6 overflow-hidden rounded-[20px] border border-line bg-surface px-7 py-[26px] shadow-[var(--shadow-card)]">
                <div className="radar-floor" aria-hidden="true" />
                <div className="radar-glow" aria-hidden="true" />
                <div className="relative flex min-w-0 flex-col gap-1.5">
                    <p className="text-sm text-muted">{today}{scopeLabel ? ` · ${scopeLabel}` : ""}</p>
                    <h1 className="text-[34px] font-semibold leading-[1.05] tracking-[-0.025em] text-ink">Risk Radar</h1>
                    <p className="text-[15px] text-ink-2">Assigned patient overview</p>
                </div>
                <dl className="relative flex flex-wrap gap-x-9 gap-y-4">
                    {loading && stats.length === 0
                        ? Array.from({ length: 3 }).map((_, i) => (
                              <div className="flex flex-col gap-2" key={i}>
                                  <Skeleton className="h-8 w-14" />
                                  <Skeleton className="h-3.5 w-28" variant="text" />
                              </div>
                          ))
                        : stats.map((stat) => (
                              <div className="flex flex-col-reverse gap-0.5" key={stat.label}>
                                  <dt className="text-[13px] text-muted">
                                      {stat.label.replace(/\s+Pending$/i, "")}
                                  </dt>
                                  <dd className={`font-mono text-[28px] font-medium leading-tight ${statTone(stat.label)}`}>
                                      {String(stat.value).replace(/\s+Pending$/i, "")}
                                  </dd>
                              </div>
                          ))}
                </dl>
            </section>

            {/* Patient table */}
            <section aria-labelledby="dashboard-overview-title" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
                <h2 id="dashboard-overview-title" className="sr-only">Assigned patient overview</h2>
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-[22px] py-3.5">
                    <SegmentedControl
                        label="Risk filter"
                        onChange={(value) => setRiskFilter(value)}
                        options={[
                            { value: "all", label: "All" },
                            { value: "high", label: "High" },
                            { value: "medium", label: "Medium" },
                            { value: "low", label: "Low" },
                            { value: "unknown", label: "Unknown" },
                        ]}
                        value={riskFilter}
                    />
                    <div className="flex flex-wrap items-center gap-2">
                        <ClinicFilterField filter={clinicFilter} />
                        <CompactField label="Sort">
                            <select
                                aria-label="Sort by"
                                className={compactSelectClass}
                                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                                value={sortBy}
                            >
                                <option value="risk">Risk</option>
                                <option value="last_activity">Last Activity</option>
                                <option value="adherence">Adherence</option>
                                <option value="med_count">Medication Count</option>
                            </select>
                        </CompactField>
                        <CompactField label="Order">
                            <select
                                aria-label="Sort order"
                                className={compactSelectClass}
                                onChange={(e) => setSortOrder(e.target.value as typeof sortOrder)}
                                value={sortOrder}
                            >
                                <option value="desc">Descending</option>
                                <option value="asc">Ascending</option>
                            </select>
                        </CompactField>
                        <CompactField label="Min. meds" className="pr-1">
                            <input
                                aria-label="Minimum medications"
                                className="h-full w-12 bg-transparent font-mono font-medium text-ink outline-none"
                                min={0}
                                onChange={(e) => setMinMedCount(e.target.value)}
                                type="number"
                                value={minMedCount}
                            />
                        </CompactField>
                        <label className="sr-only" htmlFor="dashboard-patient-search">
                            Search patients
                        </label>
                        <div className="relative">
                            <Icon name="search" className="pointer-events-none absolute left-2.5 top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-muted" />
                            <input
                                className={`h-[34px] rounded-[9px] border border-line-strong bg-surface pl-8 pr-3 text-[13px] text-ink outline-none transition-[width,box-shadow,border-color] duration-[240ms] placeholder:text-[#94A3B8] focus:w-[240px] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] ${query ? "w-[240px]" : "w-[160px]"}`}
                                id="dashboard-patient-search"
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search patients…"
                                value={query}
                            />
                        </div>
                        <button
                            aria-label="Refresh dashboard"
                            disabled={loading}
                            className="ma-press flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line-strong text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-60"
                            id="dashboard-refresh-btn"
                            onClick={reloadDashboard}
                            type="button"
                        >
                            <Icon name="refresh" className={`h-[15px] w-[15px] ${loading ? "animate-spin" : ""}`} />
                        </button>
                    </div>
                </div>

                <div role="region" aria-label="Scrollable patient overview" tabIndex={0} className="overflow-x-auto">
                <div className="min-w-[960px]">
                {/* Table header */}
                <div className={`grid ${columns} gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted`}>
                    <span>Patient</span>
                    <span>Risk</span>
                    <span>Adherence</span>
                    <span>Recent Flag</span>
                    <span>ADR / Meds</span>
                    <span className="text-right">Actions</span>
                </div>

                {/* Rows */}
                {loading && patients.length === 0 ? (
                    <div>
                        {Array.from({ length: 4 }).map((_, i) => (
                            <div className={`grid ${columns} items-center gap-4 border-b border-line px-[22px] py-4`} key={i}>
                                <div className="flex items-center gap-3"><Skeleton className="h-[34px] w-[34px]" variant="circle" /><Skeleton className="h-4 w-32" variant="text" /></div>
                                <Skeleton className="h-6 w-16" />
                                <Skeleton className="h-2 w-28" />
                                <Skeleton className="h-6 w-40" />
                                <Skeleton className="h-4 w-24" variant="text" />
                                <Skeleton className="ml-auto h-[34px] w-20" />
                            </div>
                        ))}
                    </div>
                ) : visiblePatients.length === 0 ? (
                    <div className="flex h-44 flex-col items-center justify-center gap-2 text-sm text-muted">
                        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sunken"><Icon name={query ? "search" : "users"} className="h-5 w-5" /></span>
                        {error && patients.length === 0 ? "Patient overview is unavailable. Retry to check assigned patients." : clinicId && patients.length === 0 ? <ClinicFilterEmpty filter={clinicFilter} /> : patients.length === 0 ? "No patients assigned yet" : "No results found"}
                    </div>
                ) : (
                    visiblePatients.map((patient) => {
                        const config = riskConfig[patient.risk_level];
                        const adherencePct = Math.round(patient.adherence_score * 100);
                        const strong = patient.risk_level === "high" || patient.open_adr_count > 0;
                        const initials = `${patient.first_name.charAt(0)}${patient.last_name.charAt(0)}`.toUpperCase();

                        return (
                            <div
                                className={`grid ${columns} items-center gap-4 border-b border-line px-[22px] py-4 transition-colors duration-[160ms] last:border-b-0 hover:bg-[rgba(100,116,139,.05)]`}
                                key={patient.patient_id}
                                ref={flip(patient.patient_id)}
                            >
                                {/* Name */}
                                <div className="flex min-w-0 items-center gap-3">
                                    <span aria-hidden="true" className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-track text-xs font-semibold text-ink-2">{initials}</span>
                                    <div className="flex min-w-0 flex-col items-start gap-0.5">
                                        <p className="min-w-0 break-words text-[15px] font-semibold text-ink">
                                            {patient.first_name} {patient.last_name}
                                        </p>
                                        <ClinicChip name={clinicFilter.multi ? patient.clinic_name : null} />
                                    </div>
                                </div>

                                {/* Risk badge */}
                                <div><RiskBadge level={patient.risk_level} /></div>

                                {/* Adherence bar */}
                                {patient.risk_level === "unknown" ? <span className="text-[13px] text-muted">Not enough data</span> : <div className="flex items-center gap-2.5">
                                    <div className="h-1.5 w-full max-w-[120px] overflow-hidden rounded-[3px] bg-track">
                                        <div
                                            className={`h-full rounded-[3px] ${adherencePct < 60 ? "bg-risk" : config.progressBar}`}
                                            style={{ width: `${adherencePct}%` }}
                                        />
                                    </div>
                                    <span className="font-mono text-[13px] font-medium text-ink">
                                        {adherencePct}%
                                    </span>
                                </div>}

                                {/* Recent flag */}
                                <div className="flex min-w-0 flex-col items-start gap-1">
                                    <span
                                        className={`inline-flex max-w-full items-center rounded-md px-2 py-[3px] text-xs font-medium ${patient.recent_symptom_severity > 0 ? config.accent : "bg-[rgba(100,116,139,.1)] text-ink-2"}`}
                                    >
                                        {patient.recent_symptom_severity > 0
                                            ? `Symptom severity ${patient.recent_symptom_severity}/10`
                                            : "No recent symptom report"}
                                    </span>
                                    <p className="max-w-full truncate text-xs text-muted">
                                        {patient.last_activity}
                                    </p>
                                </div>

                                {/* ADR / Meds */}
                                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px]">
                                    {patient.open_adr_count > 0 ? (
                                        <span className="inline-flex items-center gap-1 font-medium text-risk-ink">
                                            <Icon name="alert" className="h-[13px] w-[13px]" />{patient.open_adr_count} ADR
                                        </span>
                                    ) : (
                                        <span className="text-muted">No open ADR flags</span>
                                    )}
                                    <span className="text-muted">
                                        {patient.active_med_count} meds
                                    </span>
                                </div>

                                {/* Action button */}
                                <div className="flex justify-end">
                                    <button
                                        className={`ma-press h-[34px] rounded-[9px] px-4 text-[13px] font-semibold ${strong ? "bg-primary text-white shadow-[0_1px_2px_rgba(37,99,235,.25)] hover:bg-primary-hover" : "border border-line-strong bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"}`}
                                        id={`patient-action-btn-${patient.patient_id}`}
                                        onClick={() =>
                                            router.push(`/patients/${patient.patient_id}`)
                                        }
                                        type="button"
                                    >
                                        {config.action}
                                    </button>
                                </div>
                            </div>
                        );
                    })
                )}
                </div>
                </div>
                <details className="ma-disclosure border-t border-line px-[22px] text-[13px] text-muted">
                    <summary className="min-h-11 py-2 font-medium hover:text-ink">How to read these metrics</summary>
                    <p className="max-w-[80ch] pb-4 pl-[22px] leading-relaxed text-ink-2">Adherence is the share of recorded responses marked taken or completed in the last 30 days. It does not measure all expected doses. Unknown risk means there is not enough information to classify risk; an absent response does not establish a missed dose. ADR flags need clinician review.</p>
                </details>
            </section>
        </div>
    );
}
