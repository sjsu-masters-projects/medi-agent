"use client";

import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Card } from "@/components/ui";
import { setPatients, setStats, type DashboardStat } from "@/store/slices/dashboard-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type { PatientSummary } from "@/types";

const dashboardStats: DashboardStat[] = [
    { change: "+12 this week", label: "Total Patients", trend: "up", value: "204" },
    { change: "3 new today", label: "Active Alerts", trend: "up", value: "12" },
    { change: "Awaiting review", label: "Pending MedWatch", trend: "neutral", value: "2" },
    { change: "+4% vs last month", label: "Adherence Avg", trend: "up", value: "82%" },
];

const patients: PatientSummary[] = [
    {
        activeMedCount: 6,
        adherenceScore: 45,
        firstName: "Maria",
        id: "patient-1",
        lastActivity: "2 hours ago",
        lastName: "Garcia",
        openAdrCount: 1,
        riskLevel: "high",
    },
    {
        activeMedCount: 4,
        adherenceScore: 75,
        firstName: "James",
        id: "patient-2",
        lastActivity: "yesterday",
        lastName: "Wilson",
        openAdrCount: 0,
        riskLevel: "medium",
    },
];

export default function DashboardPage() {
    const dispatch = useDispatch<AppDispatch>();
    const stats = useSelector((state: RootState) => state.dashboard.stats);
    const activePatients = useSelector((state: RootState) => state.dashboard.patients);

    useEffect(() => {
        dispatch(setStats(dashboardStats));
        dispatch(setPatients(patients));
    }, [dispatch]);

    return (
        <div className="space-y-6">
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {stats.map((stat) => (
                    <Card className="space-y-3" key={stat.label}>
                        <p className="text-sm font-medium text-gray-500">{stat.label}</p>
                        <p className="text-3xl font-bold text-gray-900">{stat.value}</p>
                        <p className="text-sm text-gray-500">{stat.change}</p>
                    </Card>
                ))}
            </section>

            <section className="grid gap-6 xl:grid-cols-[2fr_1fr]">
                <Card className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-gray-900">Patient Risk Radar</h2>
                        <span className="text-sm text-gray-500">{activePatients.length} active alerts</span>
                    </div>
                    <div className="space-y-3">
                        {activePatients.map((patient) => (
                            <div className="rounded-xl border border-gray-200 p-4" key={patient.id}>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <p className="font-semibold text-gray-900">
                                            {patient.firstName} {patient.lastName}
                                        </p>
                                        <p className="text-sm text-gray-500">
                                            Adherence {patient.adherenceScore}% · {patient.activeMedCount} active medications
                                        </p>
                                    </div>
                                    <span className="text-sm text-gray-500">{patient.lastActivity}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </Card>

                <Card className="space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900">Recent activity</h2>
                    <div className="space-y-3 text-sm text-gray-600">
                        <p>Maria Garcia flagged for severe dizziness via voice report.</p>
                        <p>James Wilson missed three consecutive Metformin doses.</p>
                        <p>Two FDA MedWatch drafts are waiting for clinician review.</p>
                    </div>
                </Card>
            </section>
        </div>
    );
}
