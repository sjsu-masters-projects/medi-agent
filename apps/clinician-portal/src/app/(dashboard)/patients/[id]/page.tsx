"use client";

import { LinkedAt } from "@/components/features/clinic-chip";
import { useClinicMemberships } from "@/hooks/use-clinic-filter";
import { Suspense, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { Skeleton } from "@/components/ui";
import { Icon, type IconName } from "@/components/ui/icons";
import { AiChip } from "@/components/ui/ai-chip";
import { ProcessingDots } from "@/components/ui/motion";
import { RiskBadge } from "@/components/features/risk-badge";
import { PatientAdherencePanel } from "@/components/features/patient-adherence-panel";
import { SymptomTimeline } from "@/components/features/symptom-timeline";
import { ChatTranscript } from "@/components/features/chat-transcript";
import { PatientDocumentsPanel } from "@/components/features/patient-documents-panel";
import { PatientAppointmentsPanel } from "@/components/features/patient-appointments-panel";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import { SmartImportReviewPanel } from "@/components/features/smart-import-review-panel";
import Link from "next/link";
import { usePatientDetail } from "@/hooks/use-patient-detail";
import type { RootState } from "@/store/store";
import { PatientADRPanel } from "@/components/features/patient-adr-panel";
import { formatClinicianDateTime } from "@/utils/dates";

// ── Tab types ─────────────────────────────────────────────────────────────────

type TabId = "profile" | "imports" | "adherence" | "symptoms" | "chat" | "soap" | "documents" | "care-plan" | "adr" | "appointments";

const TABS: Array<{ id: TabId; label: string; icon: IconName }> = [
    { id: "profile", label: "Profile", icon: "user" },
    { id: "imports", label: "External Records", icon: "link" },
    { id: "adherence", label: "Adherence", icon: "gauge" },
    { id: "symptoms", label: "Symptoms", icon: "alert" },
    { id: "adr", label: "ADR", icon: "pill" },
    { id: "chat", label: "Chat", icon: "chat" },
    { id: "soap", label: "SOAP Notes", icon: "spark" },
    { id: "documents", label: "Documents", icon: "note" },
    { id: "care-plan", label: "Care Plan", icon: "check" },
    { id: "appointments", label: "Appointments", icon: "cal" },
];

function PatientTabs({ activeTab, onChange }: { activeTab: TabId; onChange: (tab: TabId) => void }) {
    const bar = useRef<HTMLDivElement>(null);
    const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);
    useLayoutEffect(() => {
        function measure() {
            const button = bar.current?.querySelector<HTMLElement>(`#tab-btn-${activeTab}`);
            if (button) setIndicator({ left: button.offsetLeft, width: button.offsetWidth });
            // On narrow windows the bar scrolls; keep the active tab in view without moving the page.
            const container = bar.current;
            if (button && container) {
                const overflowRight = button.offsetLeft + button.offsetWidth - (container.scrollLeft + container.clientWidth);
                if (overflowRight > 0) container.scrollLeft += overflowRight + 24;
                else if (button.offsetLeft < container.scrollLeft) container.scrollLeft = Math.max(0, button.offsetLeft - 24);
            }
        }
        measure();
        window.addEventListener("resize", measure);
        return () => window.removeEventListener("resize", measure);
    }, [activeTab]);
    return (
        <div
            aria-label="Patient data tabs"
            className="ma-tabbar relative flex h-11 shrink-0 gap-0.5 overflow-x-auto border-b border-line-strong xl:gap-1"
            ref={bar}
            role="tablist"
        >
            {TABS.map(({ id, label, icon }) => (
                <button
                    aria-controls={`tab-panel-${id}`}
                    aria-selected={activeTab === id}
                    className={`flex h-full shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-t-lg px-2.5 text-[13px] xl:px-3 transition-colors duration-[160ms] ${
                        activeTab === id
                            ? "font-medium text-ink"
                            : "text-muted hover:bg-[rgba(100,116,139,.06)] hover:text-ink-2"
                    }`}
                    id={`tab-btn-${id}`}
                    key={id}
                    onClick={() => onChange(id)}
                    tabIndex={activeTab === id ? 0 : -1}
                    onKeyDown={(event) => {
                        const index = TABS.findIndex((tab) => tab.id === id);
                        const nextIndex = event.key === "ArrowRight" ? (index + 1) % TABS.length
                            : event.key === "ArrowLeft" ? (index - 1 + TABS.length) % TABS.length
                            : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : null;
                        if (nextIndex === null) return;
                        event.preventDefault();
                        const nextTab = TABS[nextIndex];
                        onChange(nextTab.id);
                        document.getElementById(`tab-btn-${nextTab.id}`)?.focus();
                    }}
                    role="tab"
                    type="button"
                >
                    <Icon name={icon} className={`hidden h-4 w-4 shrink-0 xl:block ${activeTab === id ? "text-primary" : ""}`} />
                    <span>{label}</span>
                </button>
            ))}
            {indicator ? <span aria-hidden="true" className="pointer-events-none absolute bottom-0 left-0 h-0.5 rounded-full bg-primary transition-[transform,width] duration-[240ms] ease-[cubic-bezier(.2,.8,.2,1)]" style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }} /> : null}
        </div>
    );
}

function isTabId(value: string | null): value is TabId {
    return value !== null && TABS.some((entry) => entry.id === value);
}

function formatReminderSchedule(
    schedule:
        | {
              timesOfDay?: string[];
              daysOfWeek?: string[];
          }
        | null
        | undefined,
) {
    if (!schedule?.timesOfDay?.length) {
        return "Reminders not configured";
    }

    const timeLabel = schedule.timesOfDay
        .map((value) => value.slice(0, 5))
        .join(", ");
    if (!schedule.daysOfWeek?.length || schedule.daysOfWeek.length === 7) {
        return timeLabel;
    }
    const dayLabel = schedule.daysOfWeek
        .map((value) => value.slice(0, 3))
        .join(", ");
    return `${dayLabel} · ${timeLabel}`;
}

// ── Patient Deep Dive Page ─────────────────────────────────────────────────────

function PatientDeepDivePageContent({ patientId, enabled }: { patientId: string; enabled: boolean }) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { clinics } = useClinicMemberships();
    const hasMounted = useSyncExternalStore(
        () => () => undefined,
        () => true,
        () => false,
    );
    const [activeTab, setActiveTab] = useState<TabId>(() => {
        const requestedTab = searchParams.get("tab");
        return isTabId(requestedTab) ? requestedTab : "profile";
    });
    const requestedTab = searchParams.get("tab");
    const [previousRequestedTab, setPreviousRequestedTab] = useState(requestedTab);
    if (previousRequestedTab !== requestedTab) {
        setPreviousRequestedTab(requestedTab);
        setActiveTab(isTabId(requestedTab) ? requestedTab : "profile");
    }

    const { patient, loadingProfile, generatingSoap, error, loadFailure, reload, generateSoap } = usePatientDetail(patientId, enabled);

    function handleGenerateSoap() {
        void generateSoap();
    }


    // Patient detail includes charts and locale-aware dates. Keep the server and
    // initial client render identical; render the interactive data only after mount.
    if (!hasMounted || loadingProfile) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-10 w-48" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-96 w-full" />
            </div>
        );
    }

    if (loadFailure && !patient) {
        if (loadFailure !== "transient") {
            return (
                <div className="rounded-2xl border border-line bg-surface px-6 py-8 text-center" role="status">
                    <h1 className="mb-2 text-lg font-semibold text-ink">
                        {loadFailure === "denied" ? "Access denied" : "Patient not found"}
                    </h1>
                    <p className="mb-4 text-sm text-ink-2">
                        {loadFailure === "denied"
                            ? "You do not have access to this patient. Only assigned care-team members can view this record."
                            : "This patient record could not be found."}
                    </p>
                    <button className="rounded-lg border border-line-strong bg-surface px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2" onClick={() => router.push("/patients")} type="button">
                        Return to patient roster
                    </button>
                </div>
            );
        }
        return (
            <div>
                <div className="rounded-xl border border-risk-line bg-risk-soft px-6 py-8 text-center">
                    <p className="mb-4 text-sm font-semibold text-risk-ink">
                        Unable to load patient data. Please try again.
                    </p>
                    <button
                        className="rounded-lg border border-risk-line px-4 py-2 text-sm text-risk-ink hover:bg-risk-tint"
                        onClick={() => void reload()}
                        type="button"
                    >
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    if (!patient) return null;

    const adherencePct = Math.round(patient.adherence_score * 100);

    const adrFlags = patient.symptom_reports.filter((s) => s.flaggedForAdr).length;
    const hasCompletionData = patient.adherence_series.some((day) => day.expected > 0);

    return (
        <div className="ma-page flex min-h-full flex-col gap-4">
            {/* Patient strip */}
            <section className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-2xl border border-line bg-surface px-5 py-4 shadow-[var(--shadow-card)]">
                <div className="flex min-w-0 items-center gap-3.5">
                    <button
                        aria-label="Back to patients"
                        className="ma-press flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink"
                        id="back-to-patients-btn"
                        onClick={() => router.push("/patients")}
                        type="button"
                    >
                        <Icon name="back" className="h-4 w-4" />
                    </button>
                    <div aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-track text-sm font-semibold text-ink-2">
                        {patient.first_name[0]}{patient.last_name[0]}
                    </div>
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2.5">
                            <h1 className="break-words text-lg font-semibold tracking-[-0.01em] text-ink">
                                {patient.first_name} {patient.last_name}
                            </h1>
                            <RiskBadge level={patient.risk_level} />
                        </div>
                        <LinkedAt name={clinics.length >= 2 ? patient.clinic_name : null} />
                        <p className="mt-0.5 flex flex-wrap gap-x-1.5 text-[13px] text-muted">
                            {patient.date_of_birth ? <span>DOB {patient.date_of_birth}</span> : null}
                            {patient.date_of_birth ? <span aria-hidden="true">·</span> : null}
                            <span className="break-all">{patient.email}</span>
                        </p>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-x-7 gap-y-2">
                    <dl className="flex flex-wrap items-center gap-x-7 gap-y-2">
                        <div className="flex flex-col-reverse">
                            <dt className="text-xs text-muted">Recorded completion</dt>
                            <dd className="font-mono text-lg font-medium text-ink">{hasCompletionData ? `${adherencePct}%` : "—"}</dd>
                        </div>
                        <div className="flex flex-col-reverse">
                            <dt className="text-xs text-muted">Active Meds</dt>
                            <dd className="font-mono text-lg font-medium text-ink">{patient.medications.length}</dd>
                        </div>
                        <div className="flex flex-col-reverse">
                            <dt className="text-xs text-muted">ADR Flags</dt>
                            <dd className={`font-mono text-lg font-medium ${adrFlags > 0 ? "text-risk" : "text-ink"}`}>{adrFlags}</dd>
                        </div>
                    </dl>
                    <button
                        aria-label="Refresh patient data"
                        className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
                        onClick={() => void reload()}
                        type="button"
                    >
                        <Icon name="refresh" className="h-[15px] w-[15px]" />
                        Refresh
                    </button>
                </div>
            </section>

            {/* Tab navigation: underline bar with one sliding indicator */}
            <PatientTabs activeTab={activeTab} onChange={setActiveTab} />

            {/* Tab panels */}
            <div className={activeTab === "care-plan" ? "flex min-h-0 flex-1 flex-col" : "rounded-2xl border border-line bg-surface p-6 shadow-[var(--shadow-card)]"}>
                {activeTab === "adr" && <PatientADRPanel patientId={patientId} />}
                {activeTab === "imports" && (
                    <SmartImportReviewPanel
                        patientId={patientId}
                        patientTimezone={patient.timezone}
                    />
                )}

                {/* ── Profile ── */}
                {activeTab === "profile" && (
                    <div
                        aria-labelledby="tab-btn-profile"
                        id="tab-panel-profile"
                        role="tabpanel"
                    >
                        <h2 className="mb-4 text-lg font-semibold tracking-[-0.01em] text-ink">
                            Demographics &amp; Clinical Profile
                        </h2>

                        <div className="grid gap-4 md:grid-cols-2">
                            {/* Conditions */}
                            <section className="rounded-[14px] border border-line bg-surface p-5">
                                <h3 className="mb-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                    Active Conditions
                                </h3>
                                {patient.conditions.length === 0 ? (
                                    <p className="text-sm text-muted">None documented</p>
                                ) : (
                                    <ul className="flex flex-wrap gap-2">
                                        {patient.conditions.map((c, i) => (
                                            <li
                                                className="inline-flex items-center gap-1.5 rounded-[7px] border border-line bg-surface-2 px-2.5 py-1.5 text-[13px] font-medium text-ink"
                                                key={i}
                                            >
                                                <span aria-hidden="true" className="h-[7px] w-[7px] shrink-0 rounded-full bg-primary" />
                                                {c.name ?? c.icd10_code ?? "Unknown condition"}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>

                            {/* Allergies */}
                            <section className="rounded-[14px] border border-line bg-surface p-5">
                                <h3 className="mb-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                    Allergies
                                </h3>
                                {patient.allergies.length === 0 ? (
                                    <p className="text-sm text-muted">Not documented</p>
                                ) : (
                                    <ul className="flex flex-wrap gap-2">
                                        {patient.allergies.map((a, i) => (
                                            <li
                                                className="inline-flex items-center gap-1.5 rounded-[7px] border border-risk-line bg-risk-soft px-2.5 py-1.5 text-[13px] font-medium text-risk-ink"
                                                key={i}
                                            >
                                                <Icon name="alert" className="h-3.5 w-3.5 shrink-0" />
                                                <span>{a.allergen}</span>
                                                {a.severity && (
                                                    <span className="rounded-[5px] bg-risk-tint px-1.5 py-0.5 text-[11px] font-medium capitalize text-risk-ink">
                                                        {a.severity}
                                                    </span>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>

                            {/* Active Medications */}
                            <section className="overflow-hidden rounded-[14px] border border-line bg-surface md:col-span-2">
                                <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-5">
                                    <h3 className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                        Active Medications
                                    </h3>
                                    <p className="text-[13px] text-muted">
                                        Patient timezone: {patient.timezone ?? "UTC"}
                                    </p>
                                </div>
                                {patient.medications.length === 0 ? (
                                    <p className="px-5 pb-5 text-sm text-muted">No active medications</p>
                                ) : (
                                    <div className="overflow-x-auto">
                                        <table className="w-full min-w-[720px] text-sm">
                                            <thead>
                                                <tr className="border-y border-line font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                                    <th className="px-5 py-3 text-left font-normal">Name</th>
                                                    <th className="px-3 py-3 text-left font-normal">Dosage</th>
                                                    <th className="px-3 py-3 text-left font-normal">Frequency</th>
                                                    <th className="px-3 py-3 text-left font-normal">Route</th>
                                                    <th className="px-3 py-3 text-left font-normal">Source Provider</th>
                                                    <th className="px-5 py-3 text-left font-normal">Reminders</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {patient.medications.map((med) => (
                                                    <tr
                                                        className="border-b border-line last:border-b-0 hover:bg-[rgba(100,116,139,.05)]"
                                                        key={med.id}
                                                    >
                                                        <td className="px-5 py-4 align-top font-medium text-ink">
                                                            <span className="inline-flex items-center gap-2">
                                                                <Icon name="pill" className="h-4 w-4 shrink-0 text-muted" />
                                                                {med.name}
                                                            </span>
                                                            {med.genericName && (
                                                                <span className="ml-1 text-xs font-normal text-muted">
                                                                    ({med.genericName})
                                                                </span>
                                                            )}
                                                        </td>
                                                        <td className="px-3 py-4 align-top font-mono text-[13px] text-ink-2">
                                                            {med.dosage}
                                                        </td>
                                                        <td className="px-3 py-4 align-top text-ink-2">
                                                            {med.frequency}
                                                        </td>
                                                        <td className="px-3 py-4 align-top capitalize text-ink-2">
                                                            {med.route}
                                                        </td>
                                                        <td className="px-3 py-4 align-top text-ink-2">
                                                            {med.prescribedByName ?? "Unknown"}
                                                        </td>
                                                        <td className={`px-5 py-4 align-top ${med.reminderSchedule?.timesOfDay?.length ? "font-mono text-[13px] text-ink-2" : "text-muted"}`}>
                                                            {formatReminderSchedule(med.reminderSchedule)}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </section>

                            <section className="overflow-hidden rounded-[14px] border border-line bg-surface md:col-span-2">
                                <h3 className="px-5 pb-3 pt-5 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                    Active care activities
                                </h3>
                                {patient.obligations?.length ? (
                                    <div className="border-t border-line">
                                        {patient.obligations.map((obligation) => (
                                            <div
                                                className="border-b border-line px-5 py-4 last:border-b-0 hover:bg-[rgba(100,116,139,.05)]"
                                                key={obligation.id}
                                            >
                                                <div className="flex flex-wrap items-start justify-between gap-3">
                                                    <div className="flex min-w-0 flex-1 basis-48 items-start gap-2.5 break-words">
                                                        <Icon name="walk" className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-medium text-ink">
                                                                {obligation.description}
                                                            </p>
                                                            <p className="mt-0.5 text-[13px] text-muted">
                                                                {obligation.frequency}
                                                                {obligation.notes && obligation.notes.trim().replace(/\s+/g, " ") !== obligation.description.trim().replace(/\s+/g, " ")
                                                                    ? ` · ${obligation.notes}`
                                                                    : ""}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <p className={`inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1 text-xs ${obligation.reminder_schedule?.timesOfDay?.length ? "font-mono text-ink-2" : "text-muted"}`}>
                                                        <span className="sr-only">Reminders: </span>
                                                        {formatReminderSchedule(
                                                            obligation.reminder_schedule,
                                                        )}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="px-5 pb-5 text-sm text-muted">No active care activities</p>
                                )}
                            </section>
                        </div>
                    </div>
                )}

                {/* ── Adherence ── */}
                {activeTab === "adherence" && (
                    <div
                        aria-labelledby="tab-btn-adherence"
                        id="tab-panel-adherence"
                        role="tabpanel"
                    >
                        <PatientAdherencePanel patient={patient} activityId={searchParams.get("activity")} />
                    </div>
                )}

                {/* ── Symptoms ── */}
                {activeTab === "symptoms" && (
                    <div
                        aria-labelledby="tab-btn-symptoms"
                        id="tab-panel-symptoms"
                        role="tabpanel"
                    >
                        <h2 className="mb-1 text-lg font-semibold tracking-[-0.01em] text-ink">
                            Symptom Timeline
                        </h2>
                        <p className="mb-5 max-w-[80ch] text-sm text-muted">
                            Patient-reported symptoms with severity ratings. ADR flags require clinician review and do not establish an adverse drug reaction.
                        </p>
                        <SymptomTimeline data={patient.symptom_reports} />

                        {/* Symptom list */}
                        {patient.symptom_reports.length > 0 && (
                            <div className="mt-6">
                                <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                    Recent Symptoms
                                </h3>
                                <div className="overflow-hidden rounded-[14px] border border-line">
                                    {patient.symptom_reports.slice(0, 10).map((s) => (
                                        <div
                                            className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-[22px] py-4 last:border-b-0 hover:bg-[rgba(100,116,139,.05)]"
                                            key={s.id}
                                        >
                                            <div className="flex min-w-0 items-center gap-3">
                                                <span
                                                    aria-hidden="true"
                                                    className={`h-2 w-2 shrink-0 rounded-full ${
                                                        s.severity === null ? "bg-line-strong" : s.severity >= 8 ? "bg-risk" : s.severity !== null && s.severity >= 5 ? "bg-warn" : "bg-ok"
                                                    }`}
                                                />
                                                <div className="min-w-0">
                                                    <p className="text-sm font-medium capitalize text-ink">
                                                        {s.symptom}
                                                    </p>
                                                    <p className="mt-0.5 text-xs text-muted">{s.confirmationState === "patient_confirmed"
                                                        ? `Patient-confirmed${s.confirmedAt ? ` · ${s.confirmedAt}` : ""}`
                                                        : "Historical report — patient confirmation not recorded"}</p>
                                                    {s.confirmedSummary && <details className="mt-2 text-sm"><summary className="min-h-11 cursor-pointer py-2">Confirmed patient summary</summary><p className="whitespace-pre-wrap">{s.confirmedSummary}</p></details>}
                                                    {s.reportedProduct && <div className="mt-2 max-w-prose break-words rounded-lg bg-surface-2 p-2 text-xs text-ink-2">
                                                        <p className="font-medium">Patient-reported product: {s.reportedProduct.name}</p>
                                                        {!s.relatedMedicationId && <p>Not linked to a recorded medication. Review before linking or adding; this does not approve a medication.</p>}
                                                        {s.reportedProduct.concern === true && <p>A reported concern is not a confirmed adverse reaction.</p>}
                                                    </div>}
                                                    {s.onset && (
                                                        <p className="mt-0.5 text-xs text-muted">
                                                            Onset: {s.onset}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                {s.flaggedForAdr && (
                                                    <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-risk-tint px-2 py-1 text-xs font-medium text-risk-ink">
                                                        <Icon name="alert" className="h-3 w-3" />
                                                        ADR Flagged
                                                    </span>
                                                )}
                                                <span
                                                    className={`min-w-[3.25rem] text-right font-mono text-sm font-medium ${
                                                        s.severity === null ? "text-muted" : s.severity >= 8
                                                            ? "text-risk-ink"
                                                            : s.severity !== null && s.severity >= 5
                                                              ? "text-warn-ink"
                                                              : "text-ok-ink"
                                                    }`}
                                                >
                                                    {s.severity === null ? "Unknown / not provided" : `${s.severity}/10`}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Chat ── */}
                {activeTab === "chat" && (
                    <div
                        aria-labelledby="tab-btn-chat"
                        id="tab-panel-chat"
                        role="tabpanel"
                    >
                        <h2 className="mb-4 text-lg font-semibold text-ink">
                            Chat Transcript
                        </h2>
                        <p className="mb-4 text-sm text-muted">Patient conversations with Nora, the AI care assistant. Messages retain their original language. Care-team conversations are in Messages.</p>
                        <ChatTranscript messages={patient.chat_messages} />

                        <Link href="/messages" className="mt-6 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover">
                            Open Messages to contact this patient
                        </Link>
                    </div>
                )}

                {/* ── SOAP Notes ── */}
                {activeTab === "soap" && (
                    <div
                        aria-labelledby="tab-btn-soap"
                        id="tab-panel-soap"
                        role="tabpanel"
                    >
                        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2.5">
                                    <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">
                                        AI SOAP draft
                                    </h2>
                                    <AiChip>AI draft</AiChip>
                                </div>
                                <p className="mt-1 text-sm text-muted">
                                    AI-assisted draft based on available recent records · clinician review required.
                                </p>
                            </div>
                            <button
                                className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-wait disabled:bg-track disabled:text-[#94A3B8]"
                                disabled={generatingSoap}
                                id="generate-soap-btn"
                                onClick={handleGenerateSoap}
                                type="button"
                            >
                                <Icon name="spark" className="h-4 w-4" />
                                {generatingSoap ? "Generating…" : patient.latest_soap_note ? "Regenerate" : "Generate SOAP Note"}
                            </button>
                        </div>

                        {generatingSoap && (
                            <div className="ma-enter space-y-3">
                                <p className="flex items-center gap-2 text-xs text-muted">
                                    <ProcessingDots className="bg-ai-ink" />
                                    AI is analyzing patient data… this may take 15–30 seconds.
                                </p>
                                <Skeleton className="h-20 w-full" />
                                <Skeleton className="h-20 w-full" />
                                <Skeleton className="h-20 w-full" />
                            </div>
                        )}

                        {error && !generatingSoap && (
                            <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                                <p>Failed to generate SOAP note: {error}</p>
                            </div>
                        )}

                        {patient.latest_soap_note && !generatingSoap && (
                            <div className="ma-enter space-y-3">
                                <div className="grid gap-3 lg:grid-cols-2">
                                    {(["subjective", "objective", "assessment", "plan"] as const).map(
                                        (section) => (
                                            <div
                                                key={section}
                                                className="overflow-hidden rounded-[14px] border border-line bg-surface"
                                            >
                                                <div className="flex items-center gap-2.5 border-b border-line bg-surface-2 px-5 py-3">
                                                    <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-ai-tint font-mono text-[11px] font-medium uppercase text-ai-ink">
                                                        {section[0]}
                                                    </span>
                                                    <h3 className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                                                        {section}
                                                    </h3>
                                                </div>
                                                <div className="max-w-[80ch] whitespace-pre-wrap px-5 py-4 text-sm leading-relaxed text-ink">
                                                    {patient.latest_soap_note![section]}
                                                </div>
                                            </div>
                                        ),
                                    )}
                                </div>

                                <details className="ma-disclosure text-xs text-muted"><summary className="min-h-9 py-1.5 text-[13px] font-medium">Generation details</summary><p className="pl-[1.375rem]">
                                    Generated{" "}
                                    <span className="font-mono">
                                        {patient.latest_soap_note?.generated_at
                                            ? formatClinicianDateTime(patient.latest_soap_note.generated_at)
                                            : "recently"}
                                    </span>
                                </p></details>
                            </div>
                        )}

                        {!patient.latest_soap_note && !generatingSoap && (
                            <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
                                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ai-tint text-ai-ink"><Icon name="spark" className="h-6 w-6" /></span>
                                <p className="text-[15px] font-semibold text-ink">No SOAP note generated yet.</p>
                                <p className="text-sm text-muted">Click &ldquo;Generate SOAP Note&rdquo; to create one.</p>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Documents ── */}
                {activeTab === "documents" && (
                    <PatientDocumentsPanel
                        documents={patient.documents}
                        onRefresh={() => void reload()}
                        patientId={patientId}
                    />
                )}
                {activeTab === "appointments" && <PatientAppointmentsPanel patientId={patientId} />}
                {activeTab === "care-plan" && <CarePlanPanel patientId={patientId} onPublished={() => void reload()} />}
            </div>
        </div>
    );
}

export default function PatientDeepDivePage() {
    const params = useParams();
    const patientId = params["id"] as string;
    const userId = useSelector((state: RootState) => state.auth.user?.id);
    return (
        <Suspense fallback={null}>
            <PatientDeepDivePageContent key={`${patientId}:${userId ?? "signed-out"}`} patientId={patientId} enabled={Boolean(patientId && userId)} />
        </Suspense>
    );
}
