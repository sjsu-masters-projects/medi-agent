"use client";

import { useEffect, useState } from "react";
import { HiOutlineClipboardDocumentList, HiOutlineExclamationTriangle, HiOutlineMagnifyingGlass, HiOutlineUsers } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { Card } from "@/components/ui";
import { setPatients, setStats, type DashboardStat } from "@/store/slices/dashboard-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type { PatientSummary } from "@/types";

const dashboardStats: DashboardStat[] = [
    { change: "", label: "Monitored Patients", trend: "neutral", value: "204" },
    { change: "", label: "Critical Risk (< 70% or ADR)", trend: "up", value: "12" },
    { change: "", label: "FDA MedWatch Drafts", trend: "neutral", value: "2 Pending" },
];

const patients: PatientSummary[] = [
    { activeMedCount: 6, adherenceScore: 45, firstName: "Maria", id: "8832", lastActivity: "Reported via Voice Agent (2h ago)", lastName: "Garcia", openAdrCount: 1, riskLevel: "high" },
    { activeMedCount: 4, adherenceScore: 75, firstName: "James", id: "9104", lastActivity: "Missed Metformin 3 days in a row", lastName: "Wilson", openAdrCount: 0, riskLevel: "medium" },
    { activeMedCount: 5, adherenceScore: 98, firstName: "Robert", id: "7721", lastActivity: "Stable vitals reported", lastName: "Chen", openAdrCount: 0, riskLevel: "low" },
];

const alertMeta = {
    high: {
        accent: "bg-red-100 text-red-600",
        action: "Review",
        progress: "bg-red-600",
        sharedCare: "Dr. Patel (Cardiology)",
        sharedCareDetail: "Lisinopril conflict detected",
        summary: "Severe Dizziness",
        text: "text-red-600",
    },
    low: {
        accent: "bg-green-100 text-green-600",
        action: "View Profile",
        progress: "bg-green-600",
        sharedCare: "Dr. Lee (Endocrinology)",
        sharedCareDetail: "",
        summary: "On Track",
        text: "text-green-600",
    },
    medium: {
        accent: "bg-yellow-100 text-yellow-700",
        action: "View Profile",
        progress: "bg-amber-600",
        sharedCare: "No other active providers",
        sharedCareDetail: "",
        summary: "Missed Doses",
        text: "text-amber-600",
    },
} satisfies Record<
    PatientSummary["riskLevel"],
    {
        accent: string;
        action: string;
        progress: string;
        sharedCare: string;
        sharedCareDetail: string;
        summary: string;
        text: string;
    }
>;

export default function DashboardPage() {
    const dispatch = useDispatch<AppDispatch>();
    const stats = useSelector((state: RootState) => state.dashboard.stats);
    const activePatients = useSelector((state: RootState) => state.dashboard.patients);
    const [query, setQuery] = useState("");

    useEffect(() => {
        dispatch(setStats(dashboardStats));
        dispatch(setPatients(patients));
    }, [dispatch]);

    const visiblePatients = activePatients.filter((patient) =>
        `${patient.firstName} ${patient.lastName}`.toLowerCase().includes(query.toLowerCase()),
    );

    return (
        <div className="mx-auto max-w-7xl space-y-8">
            <section className="grid gap-5 xl:grid-cols-3">
                {stats.map((stat) => {
                    const emphasis =
                        stat.label === "Critical Risk (< 70% or ADR)"
                            ? "bg-red-50 text-red-600"
                            : stat.label === "FDA MedWatch Drafts"
                              ? "bg-amber-100 text-amber-600"
                              : "bg-slate-100 text-slate-600";
                    const valueColor =
                        stat.label === "Critical Risk (< 70% or ADR)"
                            ? "text-red-600"
                            : stat.label === "FDA MedWatch Drafts"
                              ? "text-amber-600"
                              : "text-slate-900";

                    return (
                        <Card className="flex items-center gap-4 px-6 py-5" key={stat.label} padding="sm">
                            <div className={`flex h-14 w-14 items-center justify-center rounded-full text-2xl ${emphasis}`}>
                                {stat.label === "Monitored Patients" ? (
                                    <HiOutlineUsers className="h-7 w-7" />
                                ) : stat.label === "Critical Risk (< 70% or ADR)" ? (
                                    <HiOutlineExclamationTriangle className="h-7 w-7" />
                                ) : (
                                    <HiOutlineClipboardDocumentList className="h-7 w-7" />
                                )}
                            </div>
                            <div>
                                <p className="text-sm font-medium text-slate-500">{stat.label}</p>
                                <p className={`text-3xl font-bold ${valueColor}`}>{stat.value}</p>
                            </div>
                        </Card>
                    );
                })}
            </section>

            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-5">
                    <h2 className="text-xl font-bold text-slate-900">Active Patient Alerts</h2>
                    <label className="relative block">
                        <HiOutlineMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <input
                            className="w-64 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                            onChange={(event) => setQuery(event.target.value)}
                            placeholder="Search patients..."
                            value={query}
                        />
                    </label>
                </div>

                <div className="grid grid-cols-[1.25fr_1fr_1.6fr_1.6fr_0.8fr] gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <span>Patient</span>
                    <span>Adherence</span>
                    <span>Recent Flag / Symptom</span>
                    <span>Shared Care</span>
                    <span className="text-right">Actions</span>
                </div>

                {visiblePatients.map((patient, index) => {
                    const meta = alertMeta[patient.riskLevel];

                    return (
                        <div
                            className={`grid grid-cols-[1.25fr_1fr_1.6fr_1.6fr_0.8fr] gap-4 px-6 py-5 ${index > 0 ? "border-t border-slate-100" : ""}`}
                            key={patient.id}
                        >
                            <div>
                                <p className="text-sm font-bold text-slate-900">
                                    {patient.firstName} {patient.lastName}
                                </p>
                                <p className="text-xs text-slate-500">ID: P-{patient.id}</p>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="h-2 w-16 rounded-full bg-slate-200">
                                    <div className={`h-2 rounded-full ${meta.progress}`} style={{ width: `${patient.adherenceScore}%` }} />
                                </div>
                                <span className={`text-sm font-bold ${meta.text}`}>{patient.adherenceScore}%</span>
                            </div>
                            <div>
                                <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${meta.accent}`}>
                                    {meta.summary}
                                </span>
                                <p className="mt-2 text-xs text-slate-500">{patient.lastActivity}</p>
                            </div>
                            <div>
                                <p className="text-xs font-medium text-slate-700">{meta.sharedCare}</p>
                                {meta.sharedCareDetail ? <p className="mt-1 text-xs text-slate-500">{meta.sharedCareDetail}</p> : null}
                            </div>
                            <div className="text-right">
                                <button
                                    className={`rounded-md px-3 py-1.5 text-xs font-medium ${meta.action === "Review" ? "border border-blue-200 text-blue-600" : "text-slate-500"}`}
                                    type="button"
                                >
                                    {meta.action}
                                </button>
                            </div>
                        </div>
                    );
                })}
            </Card>
        </div>
    );
}
