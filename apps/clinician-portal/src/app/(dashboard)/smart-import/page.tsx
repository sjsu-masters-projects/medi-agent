"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

interface AssignedPatient {
    id: string;
    first_name: string;
    last_name: string;
    email: string;
}

interface ImportResource {
    id: string;
    resource_type: string;
    external_resource_id?: string | null;
    validation_errors: string[];
    mapping_warnings: string[];
}

interface ImportRecord {
    id: string;
    patient_id: string;
    status: string;
    resource_count: number;
    candidate_fact_count: number;
    warnings: string[];
}

interface HandoffResponse {
    import_record: ImportRecord;
    resources: ImportResource[];
}

// The standalone sandbox issuer is server configuration: a standalone launch omits
// the issuer and the backend applies SMART_STANDALONE_ISSUER.
const MAX_SMART_ERROR_DETAIL_LENGTH = 200;

export default function SmartImportPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [patients, setPatients] = useState<AssignedPatient[]>([]);
    const [patientId, setPatientId] = useState("");
    const [loading, setLoading] = useState(true);
    const [starting, setStarting] = useState(false);
    const [launchStatus, setLaunchStatus] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [handoff, setHandoff] = useState<HandoffResponse | null>(null);
    const ehrIssuer = searchParams?.get("iss") ?? null;
    const ehrLaunchContext = searchParams?.get("launch") ?? null;
    const hasEhrLaunch = Boolean(ehrIssuer && ehrLaunchContext);
    const hasIncompleteEhrLaunch = Boolean(ehrIssuer || ehrLaunchContext) && !hasEhrLaunch;
    const smartError = searchParams?.get("smart_error");
    const smartErrorDetail = searchParams?.get("smart_error_detail")?.slice(0, MAX_SMART_ERROR_DETAIL_LENGTH) ?? null;

    const selectedPatient = useMemo(
        () => patients.find((patient) => patient.id === patientId),
        [patientId, patients],
    );

    const loadPatients = useCallback(async () => {
        if (!token) return;
        try {
            const result = await api.get<AssignedPatient[]>("/api/v1/clinicians/me/patients", { token });
            setPatients(result);
            setPatientId((current) => current || result[0]?.id || "");
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : "Unable to load assigned patients.");
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        void loadPatients();
    }, [loadPatients]);

    useEffect(() => {
        if (!smartError) return;
        const message = "The SMART sandbox did not authorize this import. Start a fresh launch and try again.";
        setError(smartErrorDetail ? `${message} Sandbox response: ${smartErrorDetail}` : message);
        router.replace("/smart-import");
    }, [router, smartError, smartErrorDetail]);

    useEffect(() => {
        const ticket = searchParams?.get("ticket");
        if (!ticket || !token) return;
        void (async () => {
            try {
                const result = await api.post<HandoffResponse>("/api/v1/smart/handoff/redeem", { ticket }, { token });
                setHandoff(result);
                setPatientId(result.import_record.patient_id);
                router.replace("/smart-import");
            } catch (redeemError) {
                setError(redeemError instanceof Error ? redeemError.message : "Unable to open SMART import.");
            }
        })();
    }, [router, searchParams, token]);

    const startLaunch = async () => {
        if (!token || !patientId) return;
        if (hasIncompleteEhrLaunch) {
            setError("The EHR launch context is incomplete. Return to the EHR and launch again.");
            return;
        }
        setStarting(true);
        setLaunchStatus("Preparing the secure SMART authorization session…");
        setError(null);
        try {
            const result = await api.post<{ authorization_url: string }>(
                "/api/v1/smart/launch",
                {
                    patient_id: patientId,
                    ...(hasEhrLaunch ? { issuer: ehrIssuer, launch_context: ehrLaunchContext } : {}),
                },
                { token },
            );
            if (!result.authorization_url) {
                throw new Error("The SMART sandbox did not provide an authorization address.");
            }
            setLaunchStatus("Redirecting to the SMART sandbox. Do not refresh this page.");
            if (hasEhrLaunch) {
                // Do not retain the opaque EHR launch handle in local history.
                window.history.replaceState({}, "", "/smart-import");
            }
            window.location.assign(result.authorization_url);
        } catch (launchError) {
            setError(launchError instanceof Error ? launchError.message : "Unable to start SMART launch.");
            setLaunchStatus(null);
            setStarting(false);
        }
    };

    if (loading) {
        return (
            <main className="ma-page space-y-5">
                <p className="text-sm text-muted">Loading SMART import…</p>
                <Skeleton className="h-9 w-72" />
                <Skeleton className="h-64 w-full rounded-2xl" />
            </main>
        );
    }

    const currentStep = handoff ? 3 : starting ? 2 : 1;
    const steps = [
        { label: "Choose a local synthetic patient", detail: "The selected local chart stays the review target." },
        { label: "Authorize in the SMART sandbox", detail: "A fresh, single-use authorization session." },
        { label: "Review pending facts", detail: "Candidates reach the chart only after clinician review." },
    ];

    return (
        <main className="ma-page space-y-5">
            <section>
                <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Interoperability demo</p>
                <h1 className="mt-1.5 text-2xl font-semibold tracking-[-0.02em] text-ink">Import SMART sandbox records</h1>
                <p className="mt-1 max-w-[80ch] text-sm text-muted">
                    Choose an assigned synthetic patient, then import sandbox records as pending facts.
                    Nothing becomes part of the clinical record until clinician review.
                </p>
            </section>

            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
                <Card className="space-y-5 p-0" padding="none">
                    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
                        <div>
                            <p className="text-[15px] font-semibold text-ink">Start a sandbox import</p>
                            <p className="text-[13px] text-muted">Synthetic records only · imported data stays a candidate</p>
                        </div>
                        <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-sunken px-2 py-1 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                            Step {currentStep} / 3
                        </span>
                    </div>
                    <div className="space-y-5 px-5 pb-5">
                        <div>
                            <label className="mb-1.5 block text-[13px] font-medium text-ink-2" htmlFor="smart-patient">
                                Local synthetic patient
                            </label>
                            <select
                                id="smart-patient"
                                className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:bg-surface-2 disabled:text-muted"
                                disabled={starting}
                                value={patientId}
                                onChange={(event) => setPatientId(event.target.value)}
                            >
                                {patients.map((patient) => (
                                    <option key={patient.id} value={patient.id}>
                                        {patient.first_name} {patient.last_name} — {patient.email}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {hasEhrLaunch ? (
                            <div className="flex items-start gap-2.5 rounded-xl border border-primary-line bg-primary-tint px-4 py-3 text-sm text-ai-ink">
                                <Icon name="link" className="mt-0.5 h-4 w-4 shrink-0" />
                                <p>
                                    EHR launch context received. Your local clinician session and selected patient still
                                    control whether this sandbox import can begin.
                                </p>
                            </div>
                        ) : (
                            <div className="flex items-start gap-2.5 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
                                <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                                <div>
                                    <p className="font-medium text-ink">SMART Health IT standalone sandbox</p>
                                    <p className="mt-1">
                                        No EHR launch context is active. This starts a fresh session and does not reuse a
                                        previously selected sandbox patient or encounter. Choose one external synthetic
                                        patient in the sandbox; the selected local patient remains the review target.
                                    </p>
                                </div>
                            </div>
                        )}
                        {error && (
                            <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                                <p>{error}</p>
                            </div>
                        )}
                        {launchStatus && (
                            <div
                                aria-live="polite"
                                className="ma-enter flex items-start gap-2.5 rounded-xl border border-primary-line bg-primary-tint px-4 py-3 text-sm text-ai-ink"
                                role="status"
                            >
                                <span className="mt-2 shrink-0"><ProcessingDots className="bg-primary" /></span>
                                <div>
                                    <p className="font-medium">{launchStatus}</p>
                                    <p className="mt-1 text-ai-ink">This can take a few seconds. Keep this tab open; the SMART sandbox will open automatically.</p>
                                </div>
                            </div>
                        )}
                        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
                            <Button onClick={() => void startLaunch()} disabled={starting || !selectedPatient} size="lg">
                                <Icon name="external" className="h-4 w-4" />
                                {starting ? "Opening SMART launch…" : "Launch sandbox import"}
                            </Button>
                        </div>
                    </div>
                </Card>

                <aside aria-label="Import steps" className="rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Review path</p>
                    <ol className="mt-3 space-y-4">
                        {steps.map((step, index) => {
                            const number = index + 1;
                            const done = number < currentStep;
                            const active = number === currentStep;
                            return (
                                <li className="flex gap-3" key={step.label} aria-current={active ? "step" : undefined}>
                                    <span
                                        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-medium ${
                                            active ? "bg-primary text-white" : done ? "bg-primary-tint text-primary" : "bg-sunken text-muted"
                                        }`}
                                    >
                                        {number}
                                    </span>
                                    <div className="min-w-0">
                                        <p className={`text-[13px] font-medium ${active ? "text-ink" : "text-ink-2"}`}>{step.label}</p>
                                        <p className="mt-0.5 text-xs text-muted">{step.detail}</p>
                                    </div>
                                </li>
                            );
                        })}
                    </ol>
                </aside>
            </div>

            {handoff && (
                <Card className="ma-enter overflow-hidden" padding="none">
                    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
                        <div className="min-w-0">
                            <h2 className="text-[15px] font-semibold text-ink">
                                {handoff.import_record.resource_count === 0
                                    ? "No new SMART records to review"
                                    : "Import ready for review"}
                            </h2>
                            {handoff.import_record.resource_count === 0 ? (
                                <p className="mt-0.5 max-w-[80ch] text-[13px] text-muted">
                                    This may be a repeat of a previously imported sandbox record, or the selected
                                    sandbox patient has no supported records. No local clinical truth was changed.
                                </p>
                            ) : (
                                <p className="mt-0.5 text-[13px] text-muted">
                                    {handoff.import_record.resource_count} source resources created {handoff.import_record.candidate_fact_count} pending facts.
                                </p>
                            )}
                        </div>
                        <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-sunken px-2 py-1 text-xs font-medium capitalize text-ink-2">
                            <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-muted" />
                            {handoff.import_record.status.replaceAll("_", " ")}
                        </span>
                    </div>
                    {handoff.import_record.warnings.length > 0 && (
                        <div className="flex items-start gap-2.5 border-b border-warn-line bg-warn-soft px-5 py-3 text-sm text-warn-ink">
                            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                            <ul className="space-y-1">
                                {handoff.import_record.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                            </ul>
                        </div>
                    )}
                    {handoff.resources.length > 0 && (
                        <div>
                            <div aria-hidden="true" className="hidden grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted sm:grid">
                                <span>Resource type</span>
                                <span>Source identifier</span>
                                <span>Status</span>
                            </div>
                            <ul>
                                {handoff.resources.map((resource) => {
                                    const errors = resource.validation_errors.length;
                                    const warnings = resource.mapping_warnings.length;
                                    return (
                                        <li
                                            key={resource.id}
                                            className="grid gap-2 border-b border-line px-[22px] py-4 text-sm text-ink-2 last:border-b-0 hover:bg-[rgba(100,116,139,.05)] sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-4"
                                        >
                                            <span className="flex items-center gap-2 font-medium text-ink">
                                                <Icon name="file" className="h-4 w-4 shrink-0 text-muted" />
                                                {resource.resource_type}
                                            </span>
                                            <span className="break-all font-mono text-xs text-muted">
                                                {resource.external_resource_id ?? "—"}
                                            </span>
                                            <span className="flex flex-wrap gap-1.5">
                                                {errors > 0 ? (
                                                    <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-risk-tint px-2 py-1 text-xs font-medium text-risk-ink">
                                                        <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-risk" />
                                                        <span className="font-mono">{errors}</span> validation {errors === 1 ? "error" : "errors"}
                                                    </span>
                                                ) : null}
                                                {warnings > 0 ? (
                                                    <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-warn-tint px-2 py-1 text-xs font-medium text-warn-ink">
                                                        <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-warn" />
                                                        <span className="font-mono">{warnings}</span> mapping {warnings === 1 ? "warning" : "warnings"}
                                                    </span>
                                                ) : null}
                                                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-warn-tint px-2 py-1 text-xs font-medium text-warn-ink">
                                                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-warn" />
                                                    Pending review
                                                </span>
                                            </span>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    )}
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-4">
                        <p className="text-[13px] text-muted">Review, correct, or reject each candidate in the patient&apos;s External records tab.</p>
                        <Button variant="secondary" onClick={() => router.push(`/patients/${handoff.import_record.patient_id}?tab=imports`)}>
                            Open patient review
                            <Icon name="arrow" className="h-4 w-4" />
                        </Button>
                    </div>
                </Card>
            )}

            {patients.length === 0 && (
                <EmptyState title="No assigned patients" description="Assign a synthetic patient before starting a SMART import." />
            )}
        </main>
    );
}
