"use client";

import { useCallback, useEffect, useState } from "react";
import {
    HiOutlineArrowPath,
    HiOutlineCheckCircle,
    HiOutlineChevronLeft,
    HiOutlineChevronRight,
    HiOutlineDocumentMagnifyingGlass,
    HiOutlineExclamationCircle,
    HiOutlinePencilSquare,
    HiOutlineXCircle,
} from "react-icons/hi2";
import { useSelector } from "react-redux";
import { Card, Modal, Skeleton } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

type ReviewState = "pending_review" | "approved" | "rejected";

interface ReviewSource {
    issuer: string;
    resource_type: string;
    external_resource_id?: string | null;
    version_id?: string | null;
    mapping_warnings: string[];
    validation_errors: string[];
}

interface ReviewFact {
    id: string;
    fact_type: string;
    subject_type: string;
    value: Record<string, unknown>;
    uncertainty: string[];
    review_state: ReviewState;
    created_at: string;
    source?: ReviewSource | null;
}

interface ReviewResponse {
    patient_id: string;
    review_state: ReviewState;
    facts: ReviewFact[];
    total_count: number;
    state_counts: Record<string, number>;
    fact_type_counts: Record<string, number>;
    offset: number;
    limit: number;
}

interface SourceDetail extends ReviewSource {
    raw_resource: Record<string, unknown>;
}

const PAGE_SIZE = 25;

const FACT_LABELS: Record<string, string> = {
    patient_demographics: "Patient demographics",
    encounter: "Encounter",
    condition: "Condition",
    allergy: "Allergy or intolerance",
    medication: "Medication",
    observation: "Observation",
    diagnostic_report: "Diagnostic report",
    procedure: "Procedure",
    care_plan: "Care plan",
    document_reference: "Document reference",
};

const FACT_FIELDS: Record<string, Array<[string, string]>> = {
    patient_demographics: [["name", "Name"], ["birthDate", "Date of birth"], ["gender", "Administrative gender"]],
    encounter: [["status", "Status"], ["class", "Class"], ["type", "Type"], ["period", "Period"]],
    condition: [["name", "Condition"], ["clinical_status", "Clinical status"], ["onset", "Onset"]],
    allergy: [["allergen", "Allergen"], ["clinical_status", "Clinical status"], ["reactions", "Reactions"]],
    medication: [["name", "Medication"], ["status", "Status"], ["dosage", "Dosage instructions"]],
    observation: [["code", "Observation"], ["value", "Value"], ["effective", "Effective"], ["status", "Status"]],
    diagnostic_report: [["code", "Report"], ["conclusion", "Conclusion"], ["status", "Status"]],
    procedure: [["code", "Procedure"], ["status", "Status"], ["performed", "Performed"]],
    care_plan: [["title", "Title"], ["description", "Description"], ["status", "Status"], ["intent", "Intent"]],
    document_reference: [["type", "Type"], ["description", "Description"], ["date", "Document date"], ["status", "Status"]],
};

function formatValue(value: unknown): string {
    if (value === null || value === undefined || value === "") return "Not supplied";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.length ? value.map(formatValue).join("; ") : "Not supplied";
    if (typeof value === "object") {
        const record = value as Record<string, unknown>;
        if (typeof record.text === "string") return record.text;
        if (typeof record.display === "string") return record.display;
        if (typeof record.code === "string") return record.code;
        if (typeof record.start === "string" || typeof record.end === "string") {
            return [record.start, record.end].filter(Boolean).join(" to ");
        }
        return JSON.stringify(record);
    }
    return String(value);
}

function stateLabel(state: ReviewState): string {
    return state === "pending_review" ? "Pending review" : state === "approved" ? "Approved" : "Rejected";
}

function stateClass(state: ReviewState): string {
    if (state === "approved") return "bg-emerald-100 text-emerald-800";
    if (state === "rejected") return "bg-rose-100 text-rose-800";
    return "bg-amber-100 text-amber-800";
}

function FactDetails({ fact }: { fact: ReviewFact }) {
    const fields = FACT_FIELDS[fact.fact_type] ?? Object.keys(fact.value).map((key) => [key, key] as [string, string]);
    return (
        <dl className="grid gap-x-5 gap-y-2 sm:grid-cols-2">
            {fields.map(([key, label]) => (
                <div key={key}>
                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
                    <dd className="mt-0.5 break-words text-sm text-slate-800">{formatValue(fact.value[key])}</dd>
                </div>
            ))}
        </dl>
    );
}

export function SmartImportReviewPanel({ patientId }: { patientId: string }) {
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [reviewState, setReviewState] = useState<ReviewState>("pending_review");
    const [offset, setOffset] = useState(0);
    const [review, setReview] = useState<ReviewResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [busyFactId, setBusyFactId] = useState<string | null>(null);
    const [rejecting, setRejecting] = useState<ReviewFact | null>(null);
    const [correcting, setCorrecting] = useState<ReviewFact | null>(null);
    const [note, setNote] = useState("");
    const [correctedValue, setCorrectedValue] = useState("");
    const [source, setSource] = useState<{ factId: string; detail: SourceDetail } | null>(null);

    const load = useCallback(async () => {
        if (!token) return;
        setLoading(true);
        setError(null);
        try {
            const response = await api.get<ReviewResponse>(
                `/api/v1/smart/patients/${patientId}/facts?review_state=${reviewState}&offset=${offset}&limit=${PAGE_SIZE}`,
                { token },
            );
            setReview(response);
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : "Unable to load imported records.");
        } finally {
            setLoading(false);
        }
    }, [offset, patientId, reviewState, token]);

    useEffect(() => {
        void load();
    }, [load]);

    async function approve(fact: ReviewFact) {
        if (!token) return;
        setBusyFactId(fact.id);
        setError(null);
        try {
            await api.post(`/api/v1/smart/patients/${patientId}/facts/${fact.id}/approve`, {}, { token });
            await load();
        } catch (reviewError) {
            setError(reviewError instanceof Error ? reviewError.message : "Unable to approve imported fact.");
        } finally {
            setBusyFactId(null);
        }
    }

    async function reject() {
        if (!token || !rejecting || !note.trim()) return;
        setBusyFactId(rejecting.id);
        setError(null);
        try {
            await api.post(
                `/api/v1/smart/patients/${patientId}/facts/${rejecting.id}/reject`,
                { note: note.trim() },
                { token },
            );
            setRejecting(null);
            setNote("");
            await load();
        } catch (reviewError) {
            setError(reviewError instanceof Error ? reviewError.message : "Unable to reject imported fact.");
        } finally {
            setBusyFactId(null);
        }
    }

    async function correct() {
        if (!token || !correcting || !note.trim()) return;
        let value: Record<string, unknown>;
        try {
            value = JSON.parse(correctedValue) as Record<string, unknown>;
        } catch {
            setError("Corrected value must be valid JSON.");
            return;
        }
        if (!value || Array.isArray(value)) {
            setError("Corrected value must be a JSON object.");
            return;
        }
        setBusyFactId(correcting.id);
        setError(null);
        try {
            await api.post(
                `/api/v1/smart/patients/${patientId}/facts/${correcting.id}/correct`,
                { value, note: note.trim() },
                { token },
            );
            setCorrecting(null);
            setCorrectedValue("");
            setNote("");
            await load();
        } catch (reviewError) {
            setError(reviewError instanceof Error ? reviewError.message : "Unable to correct imported fact.");
        } finally {
            setBusyFactId(null);
        }
    }

    async function inspectSource(fact: ReviewFact) {
        if (!token) return;
        setBusyFactId(fact.id);
        setError(null);
        try {
            const detail = await api.get<SourceDetail>(
                `/api/v1/smart/patients/${patientId}/facts/${fact.id}/source`,
                { token },
            );
            setSource({ factId: fact.id, detail });
        } catch (sourceError) {
            setError(sourceError instanceof Error ? sourceError.message : "Unable to load source FHIR resource.");
        } finally {
            setBusyFactId(null);
        }
    }

    const total = review?.total_count ?? 0;
    const start = total ? offset + 1 : 0;
    const end = Math.min(offset + PAGE_SIZE, total);

    return (
        <section className="space-y-5" aria-labelledby="smart-import-review-heading">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                    <p className="text-sm font-medium text-blue-700">External-record reconciliation</p>
                    <h2 className="mt-1 text-xl font-bold text-slate-900" id="smart-import-review-heading">SMART import review</h2>
                    <p className="mt-1 max-w-3xl text-sm text-slate-600">
                        Review mapped sandbox facts with resource-level provenance. Approval records a clinician decision; it does not overwrite the local record.
                    </p>
                </div>
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => void load()} type="button">
                    <HiOutlineArrowPath className="h-4 w-4" /> Refresh
                </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
                {(["pending_review", "approved", "rejected"] as ReviewState[]).map((state) => (
                    <button
                        aria-pressed={reviewState === state}
                        className={`rounded-xl border p-4 text-left transition ${reviewState === state ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white hover:border-slate-300"}`}
                        key={state}
                        onClick={() => { setReviewState(state); setOffset(0); }}
                        type="button"
                    >
                        <p className="text-sm text-slate-600">{stateLabel(state)}</p>
                        <p className="mt-1 text-2xl font-bold text-slate-900">{review?.state_counts[state] ?? 0}</p>
                    </button>
                ))}
            </div>

            {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">{error}</div>}

            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="flex flex-col gap-2 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h3 className="font-semibold text-slate-900">{stateLabel(reviewState)} imported facts</h3>
                        <p className="text-sm text-slate-500">{total} facts in this review state. Source data remains synthetic and read-only.</p>
                    </div>
                    {review && Object.keys(review.fact_type_counts).length > 0 && <p className="text-xs text-slate-500">Mapped types: {Object.keys(review.fact_type_counts).map((value) => FACT_LABELS[value] ?? value).join(", ")}</p>}
                </div>

                {loading ? (
                    <div className="space-y-4 p-5">{Array.from({ length: 3 }).map((_, index) => <Skeleton className="h-44 w-full" key={index} />)}</div>
                ) : review?.facts.length === 0 ? (
                    <div className="flex min-h-48 flex-col items-center justify-center px-5 py-10 text-center">
                        <HiOutlineCheckCircle className="h-10 w-10 text-emerald-500" />
                        <p className="mt-3 font-semibold text-slate-900">No {stateLabel(reviewState).toLowerCase()} imported facts</p>
                        <p className="mt-1 text-sm text-slate-600">A new SMART import will appear here as clinician-review candidates.</p>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-200">
                        {review?.facts.map((fact) => (
                            <article className="space-y-4 px-5 py-5" key={fact.id}>
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                    <div>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <h4 className="font-semibold text-slate-900">{FACT_LABELS[fact.fact_type] ?? fact.fact_type}</h4>
                                            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${stateClass(fact.review_state)}`}>{stateLabel(fact.review_state)}</span>
                                        </div>
                                        <p className="mt-1 text-xs text-slate-500">
                                            {fact.source ? `${fact.source.resource_type}${fact.source.external_resource_id ? ` · ${fact.source.external_resource_id}` : ""}${fact.source.version_id ? ` · version ${fact.source.version_id}` : ""}` : "Source metadata unavailable"}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        <button className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60" disabled={busyFactId === fact.id || !fact.source} onClick={() => void inspectSource(fact)} type="button"><HiOutlineDocumentMagnifyingGlass className="h-4 w-4" /> Source</button>
                                        {fact.review_state === "pending_review" && <>
                                            <button className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60" disabled={busyFactId === fact.id} onClick={() => void approve(fact)} type="button"><HiOutlineCheckCircle className="h-4 w-4" /> Approve</button>
                                            <button className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60" disabled={busyFactId === fact.id} onClick={() => { setCorrecting(fact); setCorrectedValue(JSON.stringify(fact.value, null, 2)); setNote(""); }} type="button"><HiOutlinePencilSquare className="h-4 w-4" /> Correct</button>
                                            <button className="inline-flex items-center gap-1 rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-60" disabled={busyFactId === fact.id} onClick={() => { setRejecting(fact); setNote(""); }} type="button"><HiOutlineXCircle className="h-4 w-4" /> Reject</button>
                                        </>}
                                    </div>
                                </div>
                                <FactDetails fact={fact} />
                                {fact.uncertainty.length > 0 && <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"><HiOutlineExclamationCircle className="mr-1 inline h-4 w-4" />{fact.uncertainty.join(" ")}</div>}
                                {fact.source && (fact.source.mapping_warnings.length > 0 || fact.source.validation_errors.length > 0) && <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{[...fact.source.mapping_warnings, ...fact.source.validation_errors].join(" ")}</div>}
                            </article>
                        ))}
                    </div>
                )}
                {total > PAGE_SIZE && <div className="flex items-center justify-between border-t border-slate-200 px-5 py-4 text-sm text-slate-600"><span>{start}–{end} of {total}</span><div className="flex gap-2"><button aria-label="Previous imported facts" className="rounded-lg border border-slate-200 p-2 disabled:opacity-40" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} type="button"><HiOutlineChevronLeft className="h-4 w-4" /></button><button aria-label="Next imported facts" className="rounded-lg border border-slate-200 p-2 disabled:opacity-40" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)} type="button"><HiOutlineChevronRight className="h-4 w-4" /></button></div></div>}
            </Card>

            <Modal onClose={() => { if (!busyFactId) { setRejecting(null); setNote(""); } }} open={Boolean(rejecting)} title="Reject imported fact">
                <div className="space-y-4"><p className="text-sm text-slate-600">Record why this imported candidate should not be used. The original source remains in the audit trail.</p><label className="block text-sm font-medium text-slate-700">Rejection note<textarea className="mt-2 min-h-28 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" onChange={(event) => setNote(event.target.value)} value={note} /></label><div className="flex justify-end gap-3"><button className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={() => setRejecting(null)} type="button">Cancel</button><button className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={!note.trim() || busyFactId !== null} onClick={() => void reject()} type="button">{busyFactId ? "Saving…" : "Confirm rejection"}</button></div></div>
            </Modal>

            <Modal onClose={() => { if (!busyFactId) { setCorrecting(null); setNote(""); } }} open={Boolean(correcting)} title="Correct imported fact">
                <div className="space-y-4"><p className="text-sm text-slate-600">Edit the mapped candidate, not the original FHIR source. The change remains pending review and is audited.</p><label className="block text-sm font-medium text-slate-700">Corrected value (JSON)<textarea className="mt-2 min-h-48 w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-xs" onChange={(event) => setCorrectedValue(event.target.value)} value={correctedValue} /></label><label className="block text-sm font-medium text-slate-700">Correction note<textarea className="mt-2 min-h-24 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" onChange={(event) => setNote(event.target.value)} value={note} /></label><div className="flex justify-end gap-3"><button className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={() => setCorrecting(null)} type="button">Cancel</button><button className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={!note.trim() || busyFactId !== null} onClick={() => void correct()} type="button">{busyFactId ? "Saving…" : "Save corrected candidate"}</button></div></div>
            </Modal>

            <Modal onClose={() => setSource(null)} open={Boolean(source)} title="Original SMART FHIR source">
                {source && <div className="space-y-3"><p className="text-sm text-slate-600">{source.detail.resource_type}{source.detail.external_resource_id ? ` · ${source.detail.external_resource_id}` : ""}{source.detail.version_id ? ` · version ${source.detail.version_id}` : ""}</p><pre className="max-h-[60vh] overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(source.detail.raw_resource, null, 2)}</pre></div>}
            </Modal>
        </section>
    );
}
