"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { ClinicChip, ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { RiskBadge } from "@/components/features/risk-badge";
import { useClinicFilter } from "@/hooks/use-clinic-filter";
import { DataTable, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { useFlip } from "@/components/ui/motion";
import { CompactField, compactSelectClass } from "@/components/ui/toolbar";
import { loadDashboard } from "@/store/slices/dashboard-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type { PatientRiskData } from "@/services/clinicians";

const riskOrder: Record<PatientRiskData["risk_level"], number> = {
    high: 0,
    medium: 1,
    low: 2,
    unknown: 3,
};

function activityRank(lastActivity: string): number {
    const match = lastActivity.match(/(\d+)([mhd]) ago$/i);
    if (!match) return Number.POSITIVE_INFINITY;
    const value = Number(match[1]);
    if (match[2]?.toLowerCase() === "m") return value;
    if (match[2]?.toLowerCase() === "h") return value * 60;
    return value * 60 * 24;
}

export default function PatientsPage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const patients = useSelector((state: RootState) => state.dashboard.patients);
    const loading = useSelector((state: RootState) => state.dashboard.loading);
    const error = useSelector((state: RootState) => state.dashboard.error);
    const [filter, setFilter] = useState<"all" | PatientRiskData["risk_level"]>("all");
    const [sortBy, setSortBy] = useState<"adherence" | "activity" | "risk">("risk");
    const clinicFilter = useClinicFilter();
    const { clinicId, ready } = clinicFilter;

    const reloadPatients = useCallback(() => {
        void dispatch(loadDashboard(clinicId ? { clinicId } : undefined));
    }, [clinicId, dispatch]);

    useEffect(() => {
        if (ready) {
            reloadPatients();
        }
    }, [ready, reloadPatients]);

    const visiblePatients = useMemo(() => {
        const filtered = filter === "all" ? patients : patients.filter((patient) => patient.risk_level === filter);
        return [...filtered].sort((left, right) => {
            if (sortBy === "adherence") {
                return left.adherence_score - right.adherence_score;
            }

            if (sortBy === "activity") {
                return activityRank(left.last_activity) - activityRank(right.last_activity);
            }

            return riskOrder[left.risk_level] - riskOrder[right.risk_level];
        });
    }, [filter, patients, sortBy]);

    const flip = useFlip<HTMLButtonElement>(visiblePatients.map((patient) => patient.patient_id).join(","));
    const columns = "minmax(200px,1.4fr) 120px minmax(150px,1fr) 110px minmax(150px,1fr) 110px";

    return (
        <div className="ma-page space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Patient roster</h1>
                    <p className="mt-1 text-sm text-muted">Sort by risk, adherence, or recent activity.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <CompactField label="Risk">
                        <select aria-label="Filter patients by risk" className={compactSelectClass} onChange={(event) => setFilter(event.target.value as typeof filter)} value={filter}>
                            <option value="all">All risks</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                            <option value="unknown">Unknown</option>
                        </select>
                    </CompactField>
                    <CompactField label="Sort">
                        <select aria-label="Sort patients" className={compactSelectClass} onChange={(event) => setSortBy(event.target.value as typeof sortBy)} value={sortBy}>
                            <option value="risk">Sort by risk</option>
                            <option value="adherence">Sort by adherence</option>
                            <option value="activity">Sort by last activity</option>
                        </select>
                    </CompactField>
                    <ClinicFilterField filter={clinicFilter} />
                </div>
            </div>
            {error && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink" role="alert">
                    <span className="inline-flex items-center gap-2"><Icon name="alert" className="h-4 w-4 shrink-0" />Could not load assigned patients. {error}</span>
                    <button className="ma-press h-8 rounded-lg border border-risk-line bg-surface px-3 text-xs font-semibold hover:bg-risk-tint" onClick={reloadPatients} type="button">Retry</button>
                </div>
            )}
            {loading && patients.length === 0 ? (
                <div aria-label="Loading assigned patients" className="space-y-px overflow-hidden rounded-2xl border border-line bg-surface">
                    {Array.from({ length: 5 }).map((_, index) => <div className="flex h-[66px] items-center gap-3 px-[22px]" key={index}><Skeleton className="h-[34px] w-[34px]" variant="circle" /><Skeleton className="h-4 w-48" variant="text" /></div>)}
                </div>
            ) : (
                <DataTable columns={columns} headers={["Patient", "Risk level", "Adherence", "Active meds", "Last activity", "ADR alerts"]}>
                    {visiblePatients.map((patient) => {
                        const adherence = Math.round(patient.adherence_score * 100);
                        return (
                    <button
                        className="grid w-full items-center gap-4 bg-surface px-[22px] py-4 text-left transition-colors duration-[160ms] hover:bg-[rgba(100,116,139,.05)]"
                        key={patient.patient_id}
                        onClick={() => router.push(`/patients/${patient.patient_id}`)}
                        ref={flip(patient.patient_id)}
                        style={{ gridTemplateColumns: columns }}
                        type="button"
                    >
                        <span className="flex min-w-0 items-center gap-3">
                            <span aria-hidden="true" className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-track text-xs font-semibold text-ink-2">{`${patient.first_name.charAt(0)}${patient.last_name.charAt(0)}`.toUpperCase()}</span>
                            <span className="flex min-w-0 flex-col items-start gap-0.5">
                                <span className="min-w-0 break-words text-[15px] font-semibold text-ink">
                                    {patient.first_name} {patient.last_name}
                                </span>
                                <ClinicChip name={clinicFilter.multi ? patient.clinic_name : null} />
                            </span>
                        </span>
                        <span><RiskBadge level={patient.risk_level} /></span>
                        {patient.risk_level === "unknown" ? <span className="text-[13px] text-muted">Not enough data</span> : <span className="flex items-center gap-2.5">
                            <span aria-hidden="true" className="h-1.5 w-full max-w-[96px] overflow-hidden rounded-[3px] bg-track"><span className={`block h-full rounded-[3px] ${adherence < 60 ? "bg-risk" : "bg-primary"}`} style={{ width: `${adherence}%` }} /></span>
                            <span className="font-mono text-[13px] font-medium text-ink">{adherence}%</span>
                        </span>}
                        <span className="font-mono text-[13px] text-ink-2">{patient.active_med_count}</span>
                        <span className="text-[13px] text-ink-2">{patient.last_activity}</span>
                        <span className={`font-mono text-[13px] ${patient.open_adr_count > 0 ? "font-medium text-risk-ink" : "text-muted"}`}>{patient.open_adr_count}</span>
                    </button>
                        );
                    })}
                    {visiblePatients.length === 0 && (
                        <p className="px-4 py-10 text-center text-sm text-muted">{error ? "The roster is unavailable. Retry to check assigned patients." : clinicFilter.clinicId && patients.length === 0 ? <ClinicFilterEmpty filter={clinicFilter} /> : patients.length ? "No assigned patients match these filters." : "No patients assigned yet."}</p>
                    )}
                </DataTable>
            )}
        </div>
    );
}
