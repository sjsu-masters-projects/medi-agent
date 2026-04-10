"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
    HiOutlineClipboardDocumentList,
    HiOutlineExclamationTriangle,
    HiOutlineMagnifyingGlass,
    HiOutlineUsers,
    HiOutlineArrowPath,
} from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { Card } from "@/components/ui";
import { RiskBadge } from "@/components/features/risk-badge";
import { loadDashboard } from "@/store/slices/dashboard-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { useState } from "react";
import type { PatientRiskData } from "@/services/clinicians";

// ── Risk level configuration ─────────────────────────────────────────────────

const riskConfig = {
    high: {
        accent: "bg-red-100 text-red-700",
        progressBar: "bg-red-500",
        action: "Review",
        actionClass: "border border-red-200 text-red-600 hover:bg-red-50",
    },
    medium: {
        accent: "bg-yellow-100 text-yellow-700",
        progressBar: "bg-amber-500",
        action: "View Profile",
        actionClass: "text-slate-500 hover:bg-slate-50 border border-slate-200",
    },
    low: {
        accent: "bg-green-100 text-green-700",
        progressBar: "bg-green-500",
        action: "View Profile",
        actionClass: "text-slate-500 hover:bg-slate-50 border border-slate-200",
    },
    unknown: {
        accent: "bg-slate-100 text-slate-700",
        progressBar: "bg-slate-400",
        action: "Review",
        actionClass: "text-slate-500 hover:bg-slate-50 border border-slate-200",
    },
} satisfies Record<PatientRiskData["risk_level"], {
    accent: string;
    progressBar: string;
    action: string;
    actionClass: string;
}>;

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
    const [sortBy, setSortBy] = useState<"risk" | "adherence" | "last_activity" | "med_count">("risk");
    const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
    const [minMedCount, setMinMedCount] = useState("0");

    function reloadDashboard() {
        void dispatch(
            loadDashboard({
                sortBy,
                sortOrder,
                riskFilter: riskFilter === "all" ? undefined : riskFilter,
                minMedCount: Number(minMedCount) || 0,
            }),
        );
    }

    // Fetch real data on mount and when sort/filter changes
    useEffect(() => {
        reloadDashboard();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dispatch, sortBy, sortOrder, riskFilter, minMedCount]);

    const visiblePatients = patients
        .filter((p) =>
            `${p.first_name} ${p.last_name}`.toLowerCase().includes(query.toLowerCase()),
        );

    return (
        <div className="mx-auto max-w-7xl space-y-8">
            {/* Error banner */}
            {error && (
                <div
                    className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
                    role="alert"
                >
                    <span>⚠ {error} — showing cached data</span>
                    <button
                        className="rounded px-3 py-1 text-xs font-medium hover:bg-red-100"
                        onClick={reloadDashboard}
                        type="button"
                    >
                        Retry
                    </button>
                </div>
            )}

            {/* Stats cards */}
            <section aria-label="Dashboard statistics" className="grid gap-5 xl:grid-cols-3">
                {loading && stats.length === 0
                    ? Array.from({ length: 3 }).map((_, i) => (
                          <div className="h-24 animate-pulse rounded-2xl bg-slate-100" key={i} />
                      ))
                    : stats.map((stat) => {
                          const emphasis =
                              stat.label.includes("Critical")
                                  ? "bg-red-50 text-red-600"
                                  : stat.label.includes("MedWatch")
                                    ? "bg-amber-100 text-amber-600"
                                    : "bg-slate-100 text-slate-600";
                          const valueColor = stat.label.includes("Critical")
                              ? "text-red-600"
                              : stat.label.includes("MedWatch")
                                ? "text-amber-600"
                                : "text-slate-900";

                          return (
                              <Card
                                  className="flex items-center gap-4 px-6 py-5"
                                  key={stat.label}
                                  padding="sm"
                              >
                                  <div
                                      className={`flex h-14 w-14 items-center justify-center rounded-full text-2xl ${emphasis}`}
                                  >
                                      {stat.label.includes("Monitored") ? (
                                          <HiOutlineUsers className="h-7 w-7" />
                                      ) : stat.label.includes("Critical") ? (
                                          <HiOutlineExclamationTriangle className="h-7 w-7" />
                                      ) : (
                                          <HiOutlineClipboardDocumentList className="h-7 w-7" />
                                      )}
                                  </div>
                                  <div>
                                      <p className="text-sm font-medium text-slate-500">
                                          {stat.label}
                                      </p>
                                      <p className={`text-3xl font-bold ${valueColor}`}>
                                          {stat.value}
                                      </p>
                                  </div>
                              </Card>
                          );
                      })}
            </section>

            {/* Patient alerts table */}
            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-5">
                    <div className="flex items-center gap-3">
                        <h2 className="text-xl font-bold text-slate-900">
                            Active Patient Alerts
                        </h2>
                        {loading && (
                            <HiOutlineArrowPath
                                aria-hidden="true"
                                className="h-4 w-4 animate-spin text-slate-400"
                            />
                        )}
                    </div>

                    <div className="flex items-center gap-3">
                        <label className="sr-only" htmlFor="dashboard-patient-search">
                            Search patients
                        </label>
                        <div className="relative">
                            <HiOutlineMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                            <input
                                className="w-64 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                id="dashboard-patient-search"
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search patients…"
                                value={query}
                            />
                        </div>

                        <button
                            aria-label="Refresh dashboard"
                            className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
                            id="dashboard-refresh-btn"
                            onClick={reloadDashboard}
                            type="button"
                        >
                            <HiOutlineArrowPath aria-hidden="true" className="h-4 w-4" />
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-3 border-b border-slate-200 bg-slate-50 px-6 py-3 md:grid-cols-4">
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                        Risk Filter
                        <select
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-700"
                            onChange={(e) => setRiskFilter(e.target.value as typeof riskFilter)}
                            value={riskFilter}
                        >
                            <option value="all">All</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                            <option value="unknown">Unknown</option>
                        </select>
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                        Sort By
                        <select
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-700"
                            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                            value={sortBy}
                        >
                            <option value="risk">Risk</option>
                            <option value="last_activity">Last Activity</option>
                            <option value="adherence">Adherence</option>
                            <option value="med_count">Medication Count</option>
                        </select>
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                        Sort Order
                        <select
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-700"
                            onChange={(e) => setSortOrder(e.target.value as typeof sortOrder)}
                            value={sortOrder}
                        >
                            <option value="desc">Descending</option>
                            <option value="asc">Ascending</option>
                        </select>
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                        Min Med Count
                        <input
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-700"
                            min={0}
                            onChange={(e) => setMinMedCount(e.target.value)}
                            type="number"
                            value={minMedCount}
                        />
                    </label>
                </div>

                {/* Table header */}
                <div className="grid grid-cols-[1.25fr_0.7fr_1fr_1.4fr_1.4fr_0.8fr] gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                    <span>Patient</span>
                    <span>Risk</span>
                    <span>Adherence</span>
                    <span>Recent Flag</span>
                    <span>ADR / Meds</span>
                    <span className="text-right">Actions</span>
                </div>

                {/* Rows */}
                {loading && patients.length === 0 ? (
                    <div className="space-y-px">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <div
                                className="h-16 animate-pulse border-b border-slate-100 bg-slate-50"
                                key={i}
                            />
                        ))}
                    </div>
                ) : visiblePatients.length === 0 ? (
                    <div className="flex h-40 items-center justify-center text-sm text-slate-400">
                        {patients.length === 0 ? "No patients assigned yet" : "No results found"}
                    </div>
                ) : (
                    visiblePatients.map((patient, index) => {
                        const config = riskConfig[patient.risk_level];
                        const adherencePct = Math.round(patient.adherence_score * 100);

                        return (
                            <div
                                className={`grid grid-cols-[1.25fr_0.7fr_1fr_1.4fr_1.4fr_0.8fr] items-center gap-4 px-6 py-5 ${
                                    index > 0 ? "border-t border-slate-100" : ""
                                } hover:bg-slate-50/60 transition-colors`}
                                key={patient.patient_id}
                            >
                                {/* Name */}
                                <div>
                                    <p className="text-sm font-bold text-slate-900">
                                        {patient.first_name} {patient.last_name}
                                    </p>
                                    <p className="text-xs text-slate-400">
                                        ID: {patient.patient_id.slice(0, 8)}
                                    </p>
                                </div>

                                {/* Risk badge */}
                                <RiskBadge level={patient.risk_level} />

                                {/* Adherence bar */}
                                <div className="flex items-center gap-2">
                                    <div className="h-2 w-16 rounded-full bg-slate-200">
                                        <div
                                            className={`h-2 rounded-full ${config.progressBar}`}
                                            style={{ width: `${adherencePct}%` }}
                                        />
                                    </div>
                                    <span className="text-sm font-semibold text-slate-700">
                                        {adherencePct}%
                                    </span>
                                </div>

                                {/* Recent flag */}
                                <div>
                                    <span
                                        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${config.accent}`}
                                    >
                                        {patient.recent_symptom_severity > 0
                                            ? `Symptom severity ${patient.recent_symptom_severity}/10`
                                            : patient.risk_level === "low"
                                              ? "On Track"
                                              : "Missed Doses"}
                                    </span>
                                    <p className="mt-1.5 truncate text-xs text-slate-400">
                                        {patient.last_activity}
                                    </p>
                                </div>

                                {/* ADR / Meds */}
                                <div className="flex items-center gap-4 text-sm text-slate-600">
                                    {patient.open_adr_count > 0 ? (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                                            ⚠ {patient.open_adr_count} ADR
                                        </span>
                                    ) : (
                                        <span className="text-xs text-slate-400">No ADRs</span>
                                    )}
                                    <span className="text-xs text-slate-400">
                                        {patient.active_med_count} meds
                                    </span>
                                </div>

                                {/* Action button */}
                                <div className="text-right">
                                    <button
                                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${config.actionClass}`}
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
            </Card>
        </div>
    );
}
