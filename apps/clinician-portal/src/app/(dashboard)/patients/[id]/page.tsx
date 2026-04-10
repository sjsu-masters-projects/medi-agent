"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import {
    HiOutlineArrowLeft,
    HiOutlineArrowPath,
    HiOutlineBeaker,
    HiOutlineChatBubbleLeftRight,
    HiOutlineDocumentText,
    HiOutlineExclamationTriangle,
    HiOutlineIdentification,
    HiOutlineSparkles,
} from "react-icons/hi2";
import { Card, Skeleton } from "@/components/ui";
import { RiskBadge } from "@/components/features/risk-badge";
import { AdherenceChart } from "@/components/features/adherence-chart";
import { SymptomTimeline } from "@/components/features/symptom-timeline";
import { ChatTranscript } from "@/components/features/chat-transcript";
import { DocumentSummary } from "@/components/features/document-summary";
import {
    loadPatientDeepDive,
    triggerSoapNote,
    clearPatientDetail,
} from "@/store/slices/patient-detail-slice";
import type { AppDispatch, RootState } from "@/store/store";

// ── Tab types ─────────────────────────────────────────────────────────────────

type TabId = "profile" | "adherence" | "symptoms" | "chat" | "soap" | "documents";

const TABS: Array<{ id: TabId; label: string; icon: typeof HiOutlineIdentification }> = [
    { id: "profile", label: "Profile", icon: HiOutlineIdentification },
    { id: "adherence", label: "Adherence", icon: HiOutlineBeaker },
    { id: "symptoms", label: "Symptoms", icon: HiOutlineExclamationTriangle },
    { id: "chat", label: "Chat Transcript", icon: HiOutlineChatBubbleLeftRight },
    { id: "soap", label: "SOAP Notes", icon: HiOutlineSparkles },
    { id: "documents", label: "Documents", icon: HiOutlineDocumentText },
];

// ── Patient Deep Dive Page ─────────────────────────────────────────────────────

export default function PatientDeepDivePage() {
    const params = useParams();
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const patientId = params["id"] as string;
    const [activeTab, setActiveTab] = useState<TabId>("profile");

    const { data: patient, loadingProfile, generatingSoap, error } = useSelector(
        (state: RootState) => state.patientDetail,
    );

    useEffect(() => {
        if (patientId) {
            void dispatch(loadPatientDeepDive(patientId));
        }
        return () => {
            dispatch(clearPatientDetail());
        };
    }, [dispatch, patientId]);

    function handleGenerateSoap() {
        void dispatch(triggerSoapNote({ patientId, lookbackDays: 30 }));
    }

    if (loadingProfile) {
        return (
            <div className="mx-auto max-w-6xl space-y-6">
                <Skeleton className="h-10 w-48" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-96 w-full" />
            </div>
        );
    }

    if (error && !patient) {
        return (
            <div className="mx-auto max-w-6xl">
                <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center">
                    <p className="mb-4 text-sm font-semibold text-red-700">
                        Failed to load patient: {error}
                    </p>
                    <button
                        className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700 hover:bg-red-100"
                        onClick={() => void dispatch(loadPatientDeepDive(patientId))}
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
    const obligationCount = patient.obligations?.length ?? 0;
    const obligationCompletionPct = Math.round((patient.obligation_completion_rate ?? 0) * 100);

    return (
        <div className="mx-auto max-w-6xl space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <button
                    aria-label="Back to patients"
                    className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900"
                    id="back-to-patients-btn"
                    onClick={() => router.back()}
                    type="button"
                >
                    <HiOutlineArrowLeft aria-hidden="true" className="h-4 w-4" />
                    Back to Dashboard
                </button>

                <button
                    aria-label="Refresh patient data"
                    className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
                    onClick={() => void dispatch(loadPatientDeepDive(patientId))}
                    type="button"
                >
                    <HiOutlineArrowPath aria-hidden="true" className="h-4 w-4" />
                    Refresh
                </button>
            </div>

            {/* Patient hero card */}
            <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between" padding="lg">
                <div className="flex items-center gap-5">
                    {/* Avatar */}
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-xl font-bold text-white">
                        {patient.first_name[0]}{patient.last_name[0]}
                    </div>

                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">
                            {patient.first_name} {patient.last_name}
                        </h1>
                        <p className="text-sm text-gray-500">{patient.email}</p>
                        {patient.date_of_birth && (
                            <p className="text-xs text-gray-400">DOB: {patient.date_of_birth}</p>
                        )}
                    </div>
                </div>

                {/* Risk + adherence summary */}
                <div className="flex items-center gap-6">
                    <RiskBadge level={patient.risk_level} />

                    <div className="text-center">
                        <p className="text-2xl font-bold text-gray-900">{adherencePct}%</p>
                        <p className="text-xs text-gray-400">Adherence</p>
                    </div>

                    <div className="text-center">
                        <p className="text-2xl font-bold text-gray-900">
                            {patient.medications.length}
                        </p>
                        <p className="text-xs text-gray-400">Active Meds</p>
                    </div>

                    <div className="text-center">
                        <p className="text-2xl font-bold text-gray-900">
                            {patient.symptom_reports.filter((s) => s.flaggedForAdr).length}
                        </p>
                        <p className="text-xs text-gray-400">ADR Flags</p>
                    </div>
                </div>
            </Card>

            {/* Tab navigation */}
            <div
                aria-label="Patient data tabs"
                className="flex gap-1 rounded-xl border border-gray-200 bg-gray-50 p-1"
                role="tablist"
            >
                {TABS.map(({ id, label, icon: Icon }) => (
                    <button
                        aria-controls={`tab-panel-${id}`}
                        aria-selected={activeTab === id}
                        className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
                            activeTab === id
                                ? "bg-white text-blue-600 shadow-sm"
                                : "text-gray-500 hover:bg-white/60 hover:text-gray-700"
                        }`}
                        id={`tab-btn-${id}`}
                        key={id}
                        onClick={() => setActiveTab(id)}
                        role="tab"
                        type="button"
                    >
                        <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                        <span className="hidden sm:inline">{label}</span>
                    </button>
                ))}
            </div>

            {/* Tab panels */}
            <Card padding="lg">
                {/* ── Profile ── */}
                {activeTab === "profile" && (
                    <div
                        aria-labelledby="tab-btn-profile"
                        id="tab-panel-profile"
                        role="tabpanel"
                    >
                        <h2 className="mb-4 text-lg font-semibold text-gray-900">
                            Demographics &amp; Clinical Profile
                        </h2>

                        <div className="grid gap-6 md:grid-cols-2">
                            {/* Conditions */}
                            <div>
                                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-400">
                                    Active Conditions
                                </h3>
                                {patient.conditions.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic">None documented</p>
                                ) : (
                                    <ul className="space-y-1.5">
                                        {patient.conditions.map((c, i) => (
                                            <li
                                                className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800"
                                                key={i}
                                            >
                                                <span className="h-2 w-2 rounded-full bg-blue-500" />
                                                {c.name ?? c.icd10_code ?? "Unknown condition"}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>

                            {/* Allergies */}
                            <div>
                                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-400">
                                    Allergies
                                </h3>
                                {patient.allergies.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic">NKDA</p>
                                ) : (
                                    <ul className="space-y-1.5">
                                        {patient.allergies.map((a, i) => (
                                            <li
                                                className="flex items-center justify-between rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-gray-800"
                                                key={i}
                                            >
                                                <span>{a.allergen}</span>
                                                {a.severity && (
                                                    <span className="text-xs text-red-600 font-medium">
                                                        {a.severity}
                                                    </span>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>

                            {/* Active Medications */}
                            <div className="md:col-span-2">
                                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-400">
                                    Active Medications
                                </h3>
                                {patient.medications.length === 0 ? (
                                    <p className="text-sm text-gray-400 italic">No active medications</p>
                                ) : (
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b border-gray-200 text-xs font-semibold uppercase tracking-wider text-gray-400">
                                                    <th className="py-2 pr-4 text-left">Name</th>
                                                    <th className="py-2 pr-4 text-left">Dosage</th>
                                                    <th className="py-2 pr-4 text-left">Frequency</th>
                                                    <th className="py-2 text-left">Route</th>
                                                    <th className="py-2 text-left">Source Provider</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {patient.medications.map((med) => (
                                                    <tr
                                                        className="border-b border-gray-100 hover:bg-gray-50"
                                                        key={med.id}
                                                    >
                                                        <td className="py-2.5 pr-4 font-medium text-gray-900">
                                                            {med.name}
                                                            {med.genericName && (
                                                                <span className="ml-1 text-xs text-gray-400">
                                                                    ({med.genericName})
                                                                </span>
                                                            )}
                                                        </td>
                                                        <td className="py-2.5 pr-4 text-gray-600">
                                                            {med.dosage}
                                                        </td>
                                                        <td className="py-2.5 pr-4 text-gray-600">
                                                            {med.frequency}
                                                        </td>
                                                        <td className="py-2.5 text-gray-600 capitalize">
                                                            {med.route}
                                                        </td>
                                                        <td className="py-2.5 text-gray-600">
                                                            {med.prescribedByName ?? "Unknown"}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
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
                        <h2 className="mb-1 text-lg font-semibold text-gray-900">
                            30-Day Adherence Trend
                        </h2>
                        <p className="mb-6 text-sm text-gray-500">
                            Daily completion rate for medications and obligations
                        </p>
                        <AdherenceChart data={patient.adherence_series} />

                        {/* Summary stats */}
                        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
                            {[
                                {
                                    label: "Overall Score",
                                    value: `${adherencePct}%`,
                                    color:
                                        adherencePct >= 80
                                            ? "text-green-600"
                                            : adherencePct >= 60
                                              ? "text-amber-600"
                                              : "text-red-600",
                                },
                                {
                                    label: "Days Tracked",
                                    value: patient.adherence_series.filter(
                                        (d) => d.expected > 0,
                                    ).length,
                                    color: "text-gray-900",
                                },
                                {
                                    label: "Active Obligations",
                                    value: obligationCount,
                                    color: "text-gray-900",
                                },
                                {
                                    label: "Obligation Completion",
                                    value: `${obligationCompletionPct}%`,
                                    color: "text-gray-900",
                                },
                            ].map(({ label, value, color }) => (
                                <div
                                    className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-center"
                                    key={label}
                                >
                                    <p className={`text-2xl font-bold ${color}`}>{value}</p>
                                    <p className="mt-1 text-xs text-gray-500">{label}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Symptoms ── */}
                {activeTab === "symptoms" && (
                    <div
                        aria-labelledby="tab-btn-symptoms"
                        id="tab-panel-symptoms"
                        role="tabpanel"
                    >
                        <h2 className="mb-1 text-lg font-semibold text-gray-900">
                            Symptom Timeline
                        </h2>
                        <p className="mb-6 text-sm text-gray-500">
                            Patient-reported symptoms with severity ratings
                        </p>
                        <SymptomTimeline data={patient.symptom_reports} />

                        {/* Symptom list */}
                        {patient.symptom_reports.length > 0 && (
                            <div className="mt-6 space-y-2">
                                <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
                                    Recent Symptoms
                                </h3>
                                {patient.symptom_reports.slice(0, 10).map((s) => (
                                    <div
                                        className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3"
                                        key={s.id}
                                    >
                                        <div>
                                            <p className="text-sm font-medium text-gray-900 capitalize">
                                                {s.symptom}
                                            </p>
                                            {s.onset && (
                                                <p className="text-xs text-gray-400">
                                                    Onset: {s.onset}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3">
                                            {s.flaggedForAdr && (
                                                <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                                                    ADR Flagged
                                                </span>
                                            )}
                                            <span
                                                className={`text-sm font-bold ${
                                                    s.severity >= 8
                                                        ? "text-red-600"
                                                        : s.severity >= 5
                                                          ? "text-amber-600"
                                                          : "text-green-600"
                                                }`}
                                            >
                                                {s.severity}/10
                                            </span>
                                        </div>
                                    </div>
                                ))}
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
                        <h2 className="mb-4 text-lg font-semibold text-gray-900">
                            Chat Transcript
                        </h2>
                        <ChatTranscript messages={patient.chat_messages} />
                    </div>
                )}

                {/* ── SOAP Notes ── */}
                {activeTab === "soap" && (
                    <div
                        aria-labelledby="tab-btn-soap"
                        id="tab-panel-soap"
                        role="tabpanel"
                    >
                        <div className="mb-6 flex items-center justify-between">
                            <div>
                                <h2 className="text-lg font-semibold text-gray-900">
                                    AI SOAP Note
                                </h2>
                                <p className="text-sm text-gray-500">
                                    Generated by Gemini 3.1 Pro Preview from last 30 days of data
                                </p>
                            </div>
                            <button
                                className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-wait disabled:opacity-60"
                                disabled={generatingSoap}
                                id="generate-soap-btn"
                                onClick={handleGenerateSoap}
                                type="button"
                            >
                                <HiOutlineSparkles
                                    aria-hidden="true"
                                    className={`h-4 w-4 ${generatingSoap ? "animate-pulse" : ""}`}
                                />
                                {generatingSoap ? "Generating…" : patient.latest_soap_note ? "Regenerate" : "Generate SOAP Note"}
                            </button>
                        </div>

                        {generatingSoap && (
                            <div className="space-y-3">
                                <p className="text-xs text-gray-400">
                                    AI is analyzing patient data… this may take 15–30 seconds.
                                </p>
                                <Skeleton className="h-20 w-full" />
                                <Skeleton className="h-20 w-full" />
                                <Skeleton className="h-20 w-full" />
                            </div>
                        )}

                        {error && !generatingSoap && (
                            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                                Failed to generate SOAP note: {error}
                            </div>
                        )}

                        {patient.latest_soap_note && !generatingSoap && (
                            <div className="space-y-4">
                                {(["subjective", "objective", "assessment", "plan"] as const).map(
                                    (section) => (
                                        <div
                                            key={section}
                                            className="rounded-xl border border-gray-200"
                                        >
                                            <div className="border-b border-gray-100 bg-gray-50 px-5 py-3">
                                                <h3 className="text-sm font-semibold capitalize text-gray-700">
                                                    {section}
                                                </h3>
                                            </div>
                                            <div className="whitespace-pre-wrap px-5 py-4 text-sm leading-relaxed text-gray-800">
                                                {patient.latest_soap_note![section]}
                                            </div>
                                        </div>
                                    ),
                                )}

                                <p className="text-right text-xs text-gray-400">
                                    Generated{" "}
                                    {patient.latest_soap_note?.generated_at
                                        ? new Date(patient.latest_soap_note.generated_at).toLocaleString()
                                        : "recently"}{" "}
                                    · Model: {patient.latest_soap_note?.model_used}
                                </p>
                            </div>
                        )}

                        {!patient.latest_soap_note && !generatingSoap && (
                            <div className="flex h-40 flex-col items-center justify-center gap-3 text-gray-400">
                                <HiOutlineSparkles aria-hidden="true" className="h-10 w-10" />
                                <p className="text-sm">No SOAP note generated yet.</p>
                                <p className="text-xs">Click &ldquo;Generate SOAP Note&rdquo; to create one.</p>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Documents ── */}
                {activeTab === "documents" && (
                    <div
                        aria-labelledby="tab-btn-documents"
                        id="tab-panel-documents"
                        role="tabpanel"
                    >
                        <div className="mb-6 flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-gray-900">Documents</h2>
                            <a
                                className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                                href={`/patients/${patientId}/upload`}
                                id="clinician-upload-link"
                            >
                                + Upload Document
                            </a>
                        </div>

                        {patient.documents.length === 0 ? (
                            <div className="flex h-40 items-center justify-center text-sm text-gray-400">
                                No documents on file
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {patient.documents.map((doc) => (
                                    <div
                                        className="rounded-xl border border-gray-200 bg-white"
                                        key={doc.id}
                                    >
                                        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
                                            <div className="flex items-center gap-3">
                                                <HiOutlineDocumentText
                                                    aria-hidden="true"
                                                    className="h-5 w-5 text-blue-500"
                                                />
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900">
                                                        {doc.file_name}
                                                    </p>
                                                    <p className="text-xs text-gray-400">
                                                        {doc.document_type} ·{" "}
                                                        {new Date(doc.created_at).toLocaleDateString()} ·
                                                        uploaded by {doc.uploaded_by_role}
                                                    </p>
                                                </div>
                                            </div>
                                            <span
                                                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                                                    doc.parse_status === "done"
                                                        ? "bg-green-100 text-green-700"
                                                        : doc.parse_status === "error"
                                                          ? "bg-red-100 text-red-700"
                                                          : "bg-amber-100 text-amber-700"
                                                }`}
                                            >
                                                {doc.parse_status}
                                            </span>
                                        </div>

                                        {doc.ai_summary && (
                                            <div className="px-5 py-4">
                                                <DocumentSummary
                                                    documentId={doc.id}
                                                    existingAnnotation={doc.clinician_annotation}
                                                    patientId={patientId}
                                                    summaryText={doc.ai_summary}
                                                />
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </Card>
        </div>
    );
}
