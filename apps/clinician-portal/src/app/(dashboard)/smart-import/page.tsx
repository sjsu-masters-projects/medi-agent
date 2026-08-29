"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { HiOutlineArrowPath } from "react-icons/hi2";
import { useSelector } from "react-redux";
import { Button, Card, EmptyState } from "@/components/ui";
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

const STANDALONE_SANDBOX_ISSUER = "https://launch.smarthealthit.org/v/r4/sim/eyJsYXVuY2hfdHlwZSI6InBhdGllbnQtc3RhbmRhbG9uZSJ9/fhir";

export default function SmartImportPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [patients, setPatients] = useState<AssignedPatient[]>([]);
    const [patientId, setPatientId] = useState("");
    const [issuer, setIssuer] = useState(STANDALONE_SANDBOX_ISSUER);
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
        if (ehrIssuer) {
            setIssuer(ehrIssuer);
        } else {
            setIssuer(STANDALONE_SANDBOX_ISSUER);
        }
    }, [ehrIssuer]);

    useEffect(() => {
        if (!smartError) return;
        setError("The SMART sandbox did not authorize this import. Start a fresh launch and try again.");
        router.replace("/smart-import");
    }, [router, smartError]);

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
                    issuer,
                    ...(hasEhrLaunch ? { launch_context: ehrLaunchContext } : {}),
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
        return <main className="p-8 text-sm text-gray-600">Loading SMART import…</main>;
    }

    return (
        <main className="mx-auto max-w-4xl space-y-6 p-6 md:p-10">
            <section>
                <p className="text-sm font-medium text-blue-700">Interoperability demo</p>
                <h1 className="mt-1 text-3xl font-bold text-slate-900">Import SMART sandbox records</h1>
                <p className="mt-2 max-w-2xl text-sm text-slate-600">
                    Choose an assigned synthetic patient, then import sandbox records as pending facts.
                    Nothing becomes part of the clinical record until clinician review.
                </p>
            </section>

            <Card className="space-y-5 p-5">
                <div>
                    <label className="mb-1 block text-sm font-medium text-slate-800" htmlFor="smart-patient">
                        Local synthetic patient
                    </label>
                    <select
                        id="smart-patient"
                        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
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
                    <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                        EHR launch context received. Your local clinician session and selected patient still
                        control whether this sandbox import can begin.
                    </div>
                ) : (
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                        <p className="font-medium text-slate-900">SMART Health IT standalone sandbox</p>
                        <p className="mt-1">
                            No EHR launch context is active. This starts a fresh session and does not reuse a
                            previously selected sandbox patient or encounter. Choose one external synthetic
                            patient in the sandbox; the selected local patient remains the review target.
                        </p>
                    </div>
                )}
                {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
                {launchStatus && (
                    <div
                        aria-live="polite"
                        className="flex items-start gap-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950"
                        role="status"
                    >
                        <HiOutlineArrowPath aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-blue-700" />
                        <div>
                            <p className="font-medium">{launchStatus}</p>
                            <p className="mt-1 text-blue-900">This can take a few seconds. Keep this tab open; the SMART sandbox will open automatically.</p>
                        </div>
                    </div>
                )}
                <Button onClick={() => void startLaunch()} disabled={starting || !selectedPatient}>
                    {starting ? "Opening SMART launch…" : "Launch sandbox import"}
                </Button>
            </Card>

            {handoff && (
                <Card className="space-y-4 p-5">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">
                            {handoff.import_record.resource_count === 0
                                ? "No new SMART records to review"
                                : "Import ready for review"}
                        </h2>
                        {handoff.import_record.resource_count === 0 ? (
                            <p className="text-sm text-slate-600">
                                This may be a repeat of a previously imported sandbox record, or the selected
                                sandbox patient has no supported records. No local clinical truth was changed.
                            </p>
                        ) : (
                            <p className="text-sm text-slate-600">
                                {handoff.import_record.resource_count} source resources created {handoff.import_record.candidate_fact_count} pending facts.
                            </p>
                        )}
                    </div>
                    {handoff.import_record.warnings.length > 0 && (
                        <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">
                            {handoff.import_record.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                        </ul>
                    )}
                    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
                        {handoff.resources.map((resource) => (
                            <li key={resource.id} className="px-3 py-2 text-sm text-slate-700">
                                {resource.resource_type}{resource.external_resource_id ? ` · ${resource.external_resource_id}` : ""}
                            </li>
                        ))}
                    </ul>
                    <Button variant="secondary" onClick={() => router.push(`/patients/${handoff.import_record.patient_id}?tab=imports`)}>
                        Open patient review
                    </Button>
                </Card>
            )}

            {patients.length === 0 && (
                <EmptyState title="No assigned patients" description="Assign a synthetic patient before starting a SMART import." />
            )}
        </main>
    );
}
