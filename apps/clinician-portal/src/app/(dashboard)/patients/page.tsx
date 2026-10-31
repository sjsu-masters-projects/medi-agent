"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useDispatch, useSelector } from "react-redux";
import { ClinicChip, ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { RiskBadge } from "@/components/features/risk-badge";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
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

    const flip = useFlip<HTMLTableRowElement>(visiblePatients.map((patient) => patient.patient_id).join(","));
    const headers = [
        { label: "Patient", width: "27%" },
        { label: "Risk level", width: "14%" },
        { label: "Adherence", width: "18%", align: "right" as const },
        { label: "Active meds", width: "12%", align: "right" as const },
        { label: "Last activity", width: "17%" },
        { label: "ADR alerts", width: "12%", align: "right" as const },
    ];

    return (
        <div className="ma-page space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Patient roster</h1>
                    <p className="mt-1 text-sm text-muted">Sort by risk, adherence, or recent activity.{clinicScopeLabel(clinicFilter) ? ` · ${clinicScopeLabel(clinicFilter)}` : ""}</p>
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
                <DataTable caption="Patient roster" headers={headers}>
                    {visiblePatients.map((patient) => {
                        const adherence = Math.round(patient.adherence_score * 100);
                        return (
                            <tr className="transition-colors duration-[160ms] hover:bg-surface-2 focus-within:bg-surface-2" key={patient.patient_id} ref={flip(patient.patient_id)}>
                                <th scope="row" className="px-4 py-3 text-left font-normal">
                                    <Link href={`/patients/${patient.patient_id}`} className="group flex min-h-10 items-center gap-3 rounded-md">
                                        <span aria-hidden="true" className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-track text-xs font-semibold text-ink-2">{`${patient.first_name.charAt(0)}${patient.last_name.charAt(0)}`.toUpperCase()}</span>
                                        <span className="flex min-w-0 flex-col items-start gap-0.5">
                                            <span className="break-words text-[15px] font-semibold text-primary underline decoration-primary/40 underline-offset-4 group-hover:text-primary-hover group-hover:decoration-primary">
                                                {patient.first_name} {patient.last_name}
                                            </span>
                                            <ClinicChip name={clinicFilter.multi ? patient.clinic_name : null} />
                                        </span>
                                    </Link>
                                </th>
                                <td className="px-4 py-3"><RiskBadge level={patient.risk_level} /></td>
                                <td className="px-4 py-3 text-right">
                                    {patient.risk_level === "unknown" ? <span className="text-sm text-muted">Not enough data</span> : <span className="flex items-center justify-end gap-2.5">
                                        <span aria-hidden="true" className="h-1.5 w-full max-w-[72px] overflow-hidden rounded-[3px] bg-track"><span className={`block h-full rounded-[3px] ${adherence < 60 ? "bg-risk" : "bg-primary"}`} style={{ width: `${adherence}%` }} /></span>
                                        <span className="font-mono text-sm font-medium tabular-nums text-ink">{adherence}%</span>
                                    </span>}
                                </td>
                                <td className="px-4 py-3 text-right font-mono tabular-nums text-ink-2">{patient.active_med_count}</td>
                                <td className="break-words px-4 py-3 text-ink-2">{patient.last_activity}</td>
                                <td className={`px-4 py-3 text-right font-mono tabular-nums ${patient.open_adr_count > 0 ? "font-semibold text-risk-ink" : "text-muted"}`}>{patient.open_adr_count}</td>
                            </tr>
                        );
                    })}
                    {visiblePatients.length === 0 && (
                        <tr><td colSpan={headers.length} className="px-4 py-10 text-center text-sm text-muted">{error ? "The roster is unavailable. Retry to check assigned patients." : clinicFilter.clinicId && patients.length === 0 ? <ClinicFilterEmpty filter={clinicFilter} /> : patients.length ? "No assigned patients match these filters." : "No patients assigned yet."}</td></tr>
                    )}
                </DataTable>
            )}
        </div>
    );
}
