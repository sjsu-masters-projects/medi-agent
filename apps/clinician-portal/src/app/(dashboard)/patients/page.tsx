"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { RiskBadge } from "@/components/features/risk-badge";
import { Card } from "@/components/ui";
import { setPatients } from "@/store/slices/patients-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type { PatientSummary } from "@/types";

const mockPatients: PatientSummary[] = [
    { activeMedCount: 6, adherenceScore: 45, firstName: "Maria", id: "patient-1", lastActivity: "2 hours ago", lastName: "Garcia", openAdrCount: 1, riskLevel: "high" },
    { activeMedCount: 4, adherenceScore: 75, firstName: "James", id: "patient-2", lastActivity: "1 day ago", lastName: "Wilson", openAdrCount: 0, riskLevel: "medium" },
    { activeMedCount: 5, adherenceScore: 92, firstName: "Robert", id: "patient-3", lastActivity: "3 hours ago", lastName: "Chen", openAdrCount: 0, riskLevel: "low" },
    { activeMedCount: 3, adherenceScore: 68, firstName: "Angela", id: "patient-4", lastActivity: "5 hours ago", lastName: "Brooks", openAdrCount: 2, riskLevel: "high" },
    { activeMedCount: 7, adherenceScore: 81, firstName: "Sanjay", id: "patient-5", lastActivity: "2 days ago", lastName: "Patel", openAdrCount: 0, riskLevel: "medium" },
];

export default function PatientsPage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const patients = useSelector((state: RootState) => state.patients.list);
    const [filter, setFilter] = useState<"all" | "high" | "low" | "medium">("all");
    const [sortBy, setSortBy] = useState<"adherence" | "activity" | "risk">("risk");

    useEffect(() => {
        dispatch(setPatients(mockPatients));
    }, [dispatch]);

    const visiblePatients = useMemo(() => {
        const filtered = filter === "all" ? patients : patients.filter((patient) => patient.riskLevel === filter);
        return [...filtered].sort((left, right) => {
            if (sortBy === "adherence") {
                return left.adherenceScore - right.adherenceScore;
            }

            if (sortBy === "activity") {
                return left.lastActivity.localeCompare(right.lastActivity);
            }

            const riskOrder = { high: 0, medium: 1, low: 2 };
            return riskOrder[left.riskLevel] - riskOrder[right.riskLevel];
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

            <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <div className="grid grid-cols-6 gap-4 border-y border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    <span>Patient</span>
                    <span>Risk level</span>
                    <span>Adherence</span>
                    <span>Active meds</span>
                    <span>Last activity</span>
                    <span>ADR alerts</span>
                </div>
                {visiblePatients.map((patient) => (
                    <button
                        className="grid w-full grid-cols-6 gap-4 border-b border-gray-200 bg-white px-4 py-4 text-left hover:bg-gray-50"
                        key={patient.id}
                        onClick={() => router.push(`/patients/${patient.id}`)}
                        type="button"
                    >
                        <span className="font-medium text-gray-900">
                            {patient.firstName} {patient.lastName}
                        </span>
                        <RiskBadge level={patient.riskLevel} />
                        <span className="text-gray-600">{patient.adherenceScore}%</span>
                        <span className="text-gray-600">{patient.activeMedCount}</span>
                        <span className="text-gray-600">{patient.lastActivity}</span>
                        <span className="text-gray-600">{patient.openAdrCount}</span>
                    </button>
                ))}
            </div>
        </Card>
    );
}
