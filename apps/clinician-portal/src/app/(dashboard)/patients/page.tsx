"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { RiskBadge } from "@/components/features/risk-badge";
import { Card, DataTable } from "@/components/ui";
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

    const reloadPatients = useCallback(() => {
        void dispatch(loadDashboard());
    }, [dispatch]);

    useEffect(() => {
        reloadPatients();
    }, [reloadPatients]);

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

    return (
        <Card className="space-y-4" padding="lg">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 className="text-lg font-semibold text-gray-900">Patient roster</h2>
                    <p className="text-sm text-gray-500">Sort by risk, adherence, or recent activity.</p>
                </div>
                <div className="flex gap-2">
                    <select className="rounded-lg border border-gray-300 px-3 py-2 text-sm" onChange={(event) => setFilter(event.target.value as typeof filter)} value={filter}>
                        <option value="all">All risks</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                    </select>
                    <select className="rounded-lg border border-gray-300 px-3 py-2 text-sm" onChange={(event) => setSortBy(event.target.value as typeof sortBy)} value={sortBy}>
                        <option value="risk">Sort by risk</option>
                        <option value="adherence">Sort by adherence</option>
                        <option value="activity">Sort by last activity</option>
                    </select>
                </div>
            </div>
            {error && (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
                    <span>Could not load assigned patients. {error}</span>
                    <button className="font-medium underline" onClick={reloadPatients} type="button">Retry</button>
                </div>
            )}
            {loading && patients.length === 0 ? (
                <div aria-label="Loading assigned patients" className="space-y-3">
                    {Array.from({ length: 5 }).map((_, index) => <div className="h-14 animate-pulse rounded-lg bg-gray-100" key={index} />)}
                </div>
            ) : (
                <DataTable headers={["Patient", "Risk level", "Adherence", "Active meds", "Last activity", "ADR alerts"]}>
                    {visiblePatients.map((patient) => (
                    <button
                        className="grid w-full grid-cols-6 gap-4 border-b border-gray-200 bg-white px-4 py-4 text-left hover:bg-gray-50"
                        key={patient.patient_id}
                        onClick={() => router.push(`/patients/${patient.patient_id}`)}
                        type="button"
                    >
                        <span className="font-medium text-gray-900">
                            {patient.first_name} {patient.last_name}
                        </span>
                        <RiskBadge level={patient.risk_level} />
                        <span className="text-gray-600">{Math.round(patient.adherence_score * 100)}%</span>
                        <span className="text-gray-600">{patient.active_med_count}</span>
                        <span className="text-gray-600">{patient.last_activity}</span>
                        <span className="text-gray-600">{patient.open_adr_count}</span>
                    </button>
                    ))}
                    {visiblePatients.length === 0 && (
                        <p className="px-4 py-8 text-center text-sm text-gray-500">No assigned patients match these filters.</p>
                    )}
                </DataTable>
            )}
        </Card>
    );
}
