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
  source_kind?: "smart" | "document";
  import_id?: string | null;
}

interface ReviewFact {
  id: string;
  fact_type: string;
  subject_type: string;
  value: Record<string, unknown>;
  uncertainty: string[];
  review_state: ReviewState;
  reconciliation_state?: string;
  reconciliation_target_type?: string | null;
  reconciliation_target_id?: string | null;
  created_at: string;
  source?: ReviewSource | null;
}

interface ReconciliationMatch {
  target_type: "medication" | "condition" | "allergy";
  target_id: string;
  match_reason: string;
  record: Record<string, unknown>;
}

interface ReconciliationPreview {
  fact_id: string;
  fact_type: string;
  projectable: boolean;
  candidate_fields: Record<string, unknown>;
  available_fields: string[];
  matches: ReconciliationMatch[];
}

interface IdentityBindingPreview {
  import_id: string;
  patient_id: string;
  issuer: string;
  external_patient_id: string;
  external_identity: Record<string, unknown>;
  local_identity: Record<string, unknown>;
  identity_matches: boolean;
  binding_id?: string | null;
  confirmed_at?: string | null;
}

interface ReviewResponse {
  patient_id: string;
  review_state: ReviewState;
  fact_type?: string | null;
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
const PROJECTABLE_TYPES = new Set(["medication", "condition", "allergy"]);

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
  patient_demographics: [
    ["name", "Name"],
    ["birthDate", "Date of birth"],
    ["gender", "Administrative gender"],
  ],
  encounter: [
    ["status", "Status"],
    ["class", "Class"],
    ["type", "Type"],
    ["period", "Period"],
  ],
  condition: [
    ["name", "Condition"],
    ["clinical_status", "Clinical status"],
    ["verification_status", "Verification status"],
    ["onset", "Onset"],
    ["recorded", "Recorded"],
  ],
  allergy: [
    ["allergen", "Allergen"],
    ["clinical_status", "Clinical status"],
    ["criticality", "Criticality"],
    ["reactions", "Reactions"],
  ],
  medication: [
    ["name", "Medication"],
    ["status", "Status"],
    ["intent", "Intent"],
    ["dosage", "Dosage instructions"],
    ["authored", "Authored or effective"],
  ],
  observation: [
    ["code", "Observation"],
    ["value", "Value"],
    ["effective", "Effective"],
    ["status", "Status"],
    ["interpretation", "Interpretation"],
    ["reference_range", "Reference range"],
  ],
  diagnostic_report: [
    ["code", "Report"],
    ["conclusion", "Conclusion"],
    ["status", "Status"],
    ["effective", "Effective"],
    ["issued", "Issued"],
    ["result_count", "Linked results"],
  ],
  procedure: [
    ["code", "Procedure"],
    ["status", "Status"],
    ["performed", "Performed"],
    ["reason", "Reason"],
    ["body_site", "Body site"],
  ],
  care_plan: [
    ["title", "Title"],
    ["description", "Description"],
    ["status", "Status"],
    ["intent", "Intent"],
    ["period", "Period"],
    ["category", "Category"],
    ["activities", "Activities"],
    ["addresses", "Addresses"],
  ],
  document_reference: [
    ["type", "Type"],
    ["description", "Description"],
    ["date", "Document date"],
    ["status", "Status"],
    ["authors", "Authors"],
    ["content_types", "Content types"],
  ],
};

function formatFhirDateTime(value: string, timezone: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;

  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return value;

  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      dateStyle: "medium",
      timeStyle: "short",
    }).format(timestamp);
  } catch {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "UTC",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(timestamp);
  }
}

function formatValue(value: unknown, timezone: string): string {
  if (value === null || value === undefined || value === "")
    return "Not supplied";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  )
    return typeof value === "string"
      ? formatFhirDateTime(value, timezone)
      : String(value);
  if (Array.isArray(value))
    return value.length
      ? value.map((item) => formatValue(item, timezone)).join("; ")
      : "Not supplied";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.text === "string") return record.text;
    if (typeof record.display === "string") return record.display;
    if (typeof record.code === "string") return record.code;
    if (typeof record.start === "string" || typeof record.end === "string") {
      return [record.start, record.end]
        .filter((item): item is string => typeof item === "string")
        .map((item) => formatFhirDateTime(item, timezone))
        .join(" to ");
    }
    return JSON.stringify(record);
  }
  return String(value);
}

function stateLabel(state: ReviewState): string {
  return state === "pending_review"
    ? "Pending review"
    : state === "approved"
      ? "Approved"
      : "Rejected";
}

function stateClass(state: ReviewState): string {
  if (state === "approved") return "bg-emerald-100 text-emerald-800";
  if (state === "rejected") return "bg-rose-100 text-rose-800";
  return "bg-amber-100 text-amber-800";
}

function FactDetails({
  fact,
  patientTimezone,
}: {
  fact: ReviewFact;
  patientTimezone: string;
}) {
  const fields =
    FACT_FIELDS[fact.fact_type] ??
    Object.keys(fact.value).map((key) => [key, key] as [string, string]);
  return (
    <dl className="grid gap-x-5 gap-y-2 sm:grid-cols-2">
      {fields.map(([key, label]) => (
        <div key={key}>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {label}
          </dt>
          <dd className="mt-0.5 break-words text-sm text-slate-800">
            {formatValue(fact.value[key], patientTimezone)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function editValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "object"
    ? JSON.stringify(value, null, 2)
    : String(value);
}

function correctionFields(fact: ReviewFact): Array<[string, string]> {
  const preferred = FACT_FIELDS[fact.fact_type] ?? [];
  const known = new Set(preferred.map(([key]) => key));
  return [
    ...preferred,
    ...Object.keys(fact.value)
      .filter((key) => !known.has(key))
      .map((key) => [key, key] as [string, string]),
  ];
}

function buildCorrectionDraft(fact: ReviewFact): Record<string, string> {
  return Object.fromEntries(
    Object.entries(fact.value).map(([key, value]) => [key, editValue(value)]),
  );
}

function parseCorrection(
  fact: ReviewFact,
  draft: Record<string, string>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(fact.value).map(([key, original]) => {
      const edited = draft[key] ?? editValue(original);
      if (original !== null && typeof original === "object")
        return [key, JSON.parse(edited || "null")];
      if (typeof original === "number")
        return [key, edited === "" ? null : Number(edited)];
      if (typeof original === "boolean") return [key, edited === "true"];
      return [key, edited || null];
    }),
  );
}

export function SmartImportReviewPanel({
  patientId,
  patientTimezone = "UTC",
}: {
  patientId: string;
  patientTimezone?: string | null;
}) {
  const token = useSelector((state: RootState) => state.auth.accessToken);
  const [reviewState, setReviewState] = useState<ReviewState>("pending_review");
  const [factType, setFactType] = useState("");
  const [sourceKind, setSourceKind] = useState("");
  const [reconciliationState, setReconciliationState] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [offset, setOffset] = useState(0);
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyFactId, setBusyFactId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<ReviewFact | null>(null);
  const [correcting, setCorrecting] = useState<ReviewFact | null>(null);
  const [reconciling, setReconciling] = useState<{
    fact: ReviewFact;
    preview: ReconciliationPreview;
  } | null>(null);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [binding, setBinding] = useState<IdentityBindingPreview | null>(null);
  const [bindingNote, setBindingNote] = useState("");
  const [note, setNote] = useState("");
  const [correctionDraft, setCorrectionDraft] = useState<
    Record<string, string>
  >({});
  const [source, setSource] = useState<{
    factId: string;
    detail: SourceDetail;
  } | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const filters = new URLSearchParams({
        review_state: reviewState,
        offset: String(offset),
        limit: String(PAGE_SIZE),
      });
      if (factType) filters.set("fact_type", factType);
      if (sourceKind) filters.set("source_kind", sourceKind);
      if (reconciliationState)
        filters.set("reconciliation_state", reconciliationState);
      if (fromDate) filters.set("from_date", fromDate);
      if (toDate) filters.set("to_date", toDate);
      const response = await api.get<ReviewResponse>(
        `/api/v1/smart/patients/${patientId}/facts?${filters.toString()}`,
        { token },
      );
      setReview(response);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load imported records.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    factType,
    fromDate,
    offset,
    patientId,
    reconciliationState,
    reviewState,
    sourceKind,
    toDate,
    token,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  async function approve(fact: ReviewFact) {
    if (!token) return;
    setBusyFactId(fact.id);
    setError(null);
    try {
      await api.post(
        `/api/v1/smart/patients/${patientId}/facts/${fact.id}/approve`,
        {},
        { token },
      );
      await load();
    } catch (reviewError) {
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to approve imported fact.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  async function openReconciliation(fact: ReviewFact) {
    if (!token) return;
    setBusyFactId(fact.id);
    setError(null);
    try {
      if (fact.source?.source_kind === "smart" && fact.source.import_id) {
        const identityBinding = await api.get<IdentityBindingPreview>(
          `/api/v1/smart/patients/${patientId}/imports/${fact.source.import_id}/identity-binding`,
          { token },
        );
        if (!identityBinding.confirmed_at) {
          setBinding(identityBinding);
          setBindingNote("");
          return;
        }
      }
      const preview = await api.get<ReconciliationPreview>(
        `/api/v1/smart/patients/${patientId}/facts/${fact.id}/reconciliation-preview`,
        { token },
      );
      setReconciling({ fact, preview });
      setSelectedFields(preview.available_fields);
      setSelectedTargetId(
        preview.matches.length === 1 ? preview.matches[0].target_id : "",
      );
      setNote("");
    } catch (reviewError) {
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to prepare record reconciliation.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  async function openIdentityBinding(importId: string) {
    if (!token) return;
    setBusyFactId(importId);
    setError(null);
    try {
      const preview = await api.get<IdentityBindingPreview>(
        `/api/v1/smart/patients/${patientId}/imports/${importId}/identity-binding`,
        { token },
      );
      setBinding(preview);
      setBindingNote("");
    } catch (bindingError) {
      setError(
        bindingError instanceof Error
          ? bindingError.message
          : "Unable to load the external-patient comparison.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  async function confirmIdentityBinding() {
    if (!token || !binding) return;
    if (!binding.identity_matches && !bindingNote.trim()) {
      setError(
        "Provide a reason before confirming a synthetic identity mismatch.",
      );
      return;
    }
    setBusyFactId(binding.import_id);
    setError(null);
    try {
      await api.post(
        `/api/v1/smart/patients/${patientId}/imports/${binding.import_id}/identity-binding`,
        { confirmation_note: bindingNote.trim() || undefined },
        { token },
      );
      setBinding(null);
      setBindingNote("");
    } catch (bindingError) {
      setError(
        bindingError instanceof Error
          ? bindingError.message
          : "Unable to confirm the external patient binding.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  async function reconcile(
    decision:
      | "add"
      | "update"
      | "keep_existing"
      | "defer"
      | "reject"
      | "mark_reviewed",
  ) {
    if (!token || !reconciling) return;
    if (decision === "update" && !selectedTargetId) {
      setError("Choose the local record to update.");
      return;
    }
    if ((decision === "defer" || decision === "reject") && !note.trim()) {
      setError("A note is required for this decision.");
      return;
    }
    setBusyFactId(reconciling.fact.id);
    setError(null);
    try {
      await api.post(
        `/api/v1/smart/patients/${patientId}/facts/${reconciling.fact.id}/reconcile`,
        {
          decision,
          target_id: decision === "update" ? selectedTargetId : undefined,
          selected_fields:
            decision === "add" || decision === "update" ? selectedFields : [],
          note: note.trim() || undefined,
          idempotency_key: crypto.randomUUID(),
        },
        { token },
      );
      setReconciling(null);
      setSelectedFields([]);
      setSelectedTargetId("");
      setNote("");
      await load();
    } catch (reviewError) {
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to record reconciliation decision.",
      );
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
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to reject imported fact.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  async function correct() {
    if (!token || !correcting || !note.trim()) return;
    let value: Record<string, unknown>;
    try {
      value = parseCorrection(correcting, correctionDraft);
    } catch {
      setError("Structured fields must contain valid JSON.");
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
      setCorrectionDraft({});
      setNote("");
      await load();
    } catch (reviewError) {
      setError(
        reviewError instanceof Error
          ? reviewError.message
          : "Unable to correct imported fact.",
      );
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
      setError(
        sourceError instanceof Error
          ? sourceError.message
          : "Unable to load source FHIR resource.",
      );
    } finally {
      setBusyFactId(null);
    }
  }

  const total = review?.total_count ?? 0;
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + PAGE_SIZE, total);

  return (
    <section
      className="space-y-5"
      aria-labelledby="smart-import-review-heading"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">
            External-record reconciliation
          </p>
          <h2
            className="mt-1 text-xl font-bold text-slate-900"
            id="smart-import-review-heading"
          >
            External records review
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Review SMART and document candidates with source-level provenance.
            Only a field-by-field reconciliation decision can change an existing
            medication, condition, or allergy; evidence-only records remain
            read-only.
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          onClick={() => void load()}
          type="button"
        >
          <HiOutlineArrowPath className="h-4 w-4" /> Refresh
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {(["pending_review", "approved", "rejected"] as ReviewState[]).map(
          (state) => (
            <button
              aria-pressed={reviewState === state}
              className={`rounded-xl border p-4 text-left transition ${reviewState === state ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white hover:border-slate-300"}`}
              key={state}
              onClick={() => {
                setReviewState(state);
                setOffset(0);
              }}
              type="button"
            >
              <p className="text-sm text-slate-600">{stateLabel(state)}</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {review?.state_counts[state] ?? 0}
              </p>
            </button>
          ),
        )}
      </div>

      {error && (
        <div
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
          role="alert"
        >
          {error}
        </div>
      )}

      <Card className="overflow-hidden px-0 py-0" padding="sm">
        <div className="flex flex-col gap-2 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="font-semibold text-slate-900">
              {stateLabel(reviewState)} imported facts
            </h3>
            <p className="text-sm text-slate-500">
              {total} facts in this review state. Source data remains synthetic
              and read-only.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {review && Object.keys(review.fact_type_counts).length > 0 && (
              <label className="text-sm font-medium text-slate-700">
                Mapped type
                <select
                  aria-label="Filter imported facts by mapped type"
                  className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-800"
                  onChange={(event) => {
                    setFactType(event.target.value);
                    setOffset(0);
                  }}
                  value={factType}
                >
                  <option value="">All mapped types</option>
                  {Object.entries(review.fact_type_counts)
                    .sort(([left], [right]) =>
                      (FACT_LABELS[left] ?? left).localeCompare(
                        FACT_LABELS[right] ?? right,
                      ),
                    )
                    .map(([value, count]) => (
                      <option key={value} value={value}>
                        {FACT_LABELS[value] ?? value} ({count})
                      </option>
                    ))}
                </select>
              </label>
            )}
            <label className="text-sm font-medium text-slate-700">
              Source
              <select
                aria-label="Filter imported facts by source"
                className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-800"
                onChange={(event) => {
                  setSourceKind(event.target.value);
                  setOffset(0);
                }}
                value={sourceKind}
              >
                <option value="">All sources</option>
                <option value="smart">SMART</option>
                <option value="document">Document</option>
              </select>
            </label>
            <label className="text-sm font-medium text-slate-700">
              Reconciliation
              <select
                aria-label="Filter imported facts by reconciliation state"
                className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-800"
                onChange={(event) => {
                  setReconciliationState(event.target.value);
                  setOffset(0);
                }}
                value={reconciliationState}
              >
                <option value="">All states</option>
                <option value="not_started">Not started</option>
                <option value="applied">Applied</option>
                <option value="kept_existing">Kept existing</option>
                <option value="deferred">Deferred</option>
                <option value="rejected">Rejected</option>
                <option value="reviewed_evidence">Reviewed evidence</option>
                <option value="source_withdrawn">Source withdrawn</option>
              </select>
            </label>
            <label className="text-sm font-medium text-slate-700">
              From
              <input
                aria-label="Filter imported facts from date"
                className="ml-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm font-normal"
                onChange={(event) => {
                  setFromDate(event.target.value);
                  setOffset(0);
                }}
                type="date"
                value={fromDate}
              />
            </label>
            <label className="text-sm font-medium text-slate-700">
              To
              <input
                aria-label="Filter imported facts to date"
                className="ml-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm font-normal"
                onChange={(event) => {
                  setToDate(event.target.value);
                  setOffset(0);
                }}
                type="date"
                value={toDate}
              />
            </label>
          </div>
        </div>

        {loading ? (
          <div className="space-y-4 p-5">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton className="h-44 w-full" key={index} />
            ))}
          </div>
        ) : review?.facts.length === 0 ? (
          <div className="flex min-h-48 flex-col items-center justify-center px-5 py-10 text-center">
            <HiOutlineCheckCircle className="h-10 w-10 text-emerald-500" />
            <p className="mt-3 font-semibold text-slate-900">
              No {stateLabel(reviewState).toLowerCase()} imported facts
            </p>
            <p className="mt-1 text-sm text-slate-600">
              New SMART and document imports appear here as clinician-review
              candidates.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-200">
            {review?.facts.map((fact) => (
              <article className="space-y-4 px-5 py-5" key={fact.id}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="font-semibold text-slate-900">
                        {FACT_LABELS[fact.fact_type] ?? fact.fact_type}
                      </h4>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${stateClass(fact.review_state)}`}
                      >
                        {stateLabel(fact.review_state)}
                      </span>
                      {fact.reconciliation_state &&
                        fact.reconciliation_state !== "not_started" && (
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                            {fact.reconciliation_state.replaceAll("_", " ")}
                          </span>
                        )}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {fact.source
                        ? `${fact.source.resource_type}${fact.source.external_resource_id ? ` · ${fact.source.external_resource_id}` : ""}${fact.source.version_id ? ` · version ${fact.source.version_id}` : ""}`
                        : "Source metadata unavailable"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      disabled={busyFactId === fact.id || !fact.source}
                      onClick={() => void inspectSource(fact)}
                      type="button"
                    >
                      <HiOutlineDocumentMagnifyingGlass className="h-4 w-4" />{" "}
                      Source
                    </button>
                    {fact.review_state === "pending_review" && (
                      <>
                        {PROJECTABLE_TYPES.has(fact.fact_type) ? (
                          <button
                            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
                            disabled={busyFactId === fact.id}
                            onClick={() => void openReconciliation(fact)}
                            type="button"
                          >
                            <HiOutlineCheckCircle className="h-4 w-4" /> Review
                            changes
                          </button>
                        ) : (
                          <button
                            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
                            disabled={busyFactId === fact.id}
                            onClick={() => void approve(fact)}
                            type="button"
                          >
                            <HiOutlineCheckCircle className="h-4 w-4" /> Mark
                            reviewed
                          </button>
                        )}
                        {PROJECTABLE_TYPES.has(fact.fact_type) &&
                          fact.source?.source_kind === "smart" &&
                          fact.source.import_id && (
                            <button
                              className="inline-flex items-center gap-1 rounded-lg border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-60"
                              disabled={busyFactId === fact.id}
                              onClick={() =>
                                void openIdentityBinding(
                                  String(fact.source?.import_id),
                                )
                              }
                              type="button"
                            >
                              Confirm patient
                            </button>
                          )}
                        <button
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                          disabled={busyFactId === fact.id}
                          onClick={() => {
                            setCorrecting(fact);
                            setCorrectionDraft(buildCorrectionDraft(fact));
                            setNote("");
                          }}
                          type="button"
                        >
                          <HiOutlinePencilSquare className="h-4 w-4" /> Correct
                        </button>
                        <button
                          className="inline-flex items-center gap-1 rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                          disabled={busyFactId === fact.id}
                          onClick={() => {
                            setRejecting(fact);
                            setNote("");
                          }}
                          type="button"
                        >
                          <HiOutlineXCircle className="h-4 w-4" /> Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <FactDetails
                  fact={fact}
                  patientTimezone={patientTimezone ?? "UTC"}
                />
                {fact.uncertainty.length > 0 && (
                  <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    <HiOutlineExclamationCircle className="mr-1 inline h-4 w-4" />
                    {fact.uncertainty.join(" ")}
                  </div>
                )}
                {fact.reconciliation_state === "source_withdrawn" && (
                  <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">
                    <HiOutlineExclamationCircle className="mr-1 inline h-4 w-4" />
                    The supporting source was withdrawn after local
                    reconciliation. Review the preserved local record and audit
                    history before further use.
                  </div>
                )}
                {fact.reconciliation_state === "applied" &&
                  fact.reconciliation_target_id && (
                    <a
                      className="inline-flex text-sm font-medium text-blue-700 underline hover:text-blue-800"
                      href={`/patients/${patientId}`}
                    >
                      View applied local{" "}
                      {fact.reconciliation_target_type ?? "record"}
                    </a>
                  )}
                {fact.source &&
                  (fact.source.mapping_warnings.length > 0 ||
                    fact.source.validation_errors.length > 0) && (
                    <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      {[
                        ...fact.source.mapping_warnings,
                        ...fact.source.validation_errors,
                      ].join(" ")}
                    </div>
                  )}
              </article>
            ))}
          </div>
        )}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-slate-200 px-5 py-4 text-sm text-slate-600">
            <span>
              {start}–{end} of {total}
            </span>
            <div className="flex gap-2">
              <button
                aria-label="Previous imported facts"
                className="rounded-lg border border-slate-200 p-2 disabled:opacity-40"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                type="button"
              >
                <HiOutlineChevronLeft className="h-4 w-4" />
              </button>
              <button
                aria-label="Next imported facts"
                className="rounded-lg border border-slate-200 p-2 disabled:opacity-40"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                type="button"
              >
                <HiOutlineChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </Card>

      <Modal
        onClose={() => {
          if (!busyFactId) {
            setReconciling(null);
            setSelectedFields([]);
            setSelectedTargetId("");
            setNote("");
          }
        }}
        open={Boolean(reconciling)}
        title="Reconcile imported record"
      >
        {reconciling && (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              Select exactly which imported values may be applied. Missing
              values never clear the local chart; this action is recorded with
              the original source version.
            </p>
            <div className="grid gap-4 rounded-xl border border-slate-200 p-4 sm:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  Imported candidate
                </h3>
                <dl className="mt-2 space-y-2 text-sm">
                  {Object.entries(reconciling.preview.candidate_fields).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd className="break-words text-slate-800">
                          {formatValue(value, patientTimezone ?? "UTC")}
                        </dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  Matched local record
                </h3>
                {reconciling.preview.matches.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-600">
                    No conservative match was found. You may add a new local
                    record after checking the candidate fields.
                  </p>
                ) : (
                  <>
                    <label className="mt-2 block text-sm font-medium text-slate-700">
                      {reconciling.preview.matches.length > 1
                        ? "Choose a local record"
                        : "Matched local record"}
                      <select
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal"
                        onChange={(event) =>
                          setSelectedTargetId(event.target.value)
                        }
                        value={selectedTargetId}
                      >
                        <option value="">Choose a record</option>
                        {reconciling.preview.matches.map((match) => (
                          <option key={match.target_id} value={match.target_id}>
                            {match.match_reason}
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedTargetId &&
                      (() => {
                        const match = reconciling.preview.matches.find(
                          (item) => item.target_id === selectedTargetId,
                        );
                        return match ? (
                          <>
                            <dl className="mt-3 space-y-2 text-sm">
                              {Object.entries(match.record)
                                .filter(([field]) =>
                                  reconciling.preview.available_fields.includes(
                                    field,
                                  ),
                                )
                                .map(([field, value]) => (
                                  <div key={field}>
                                    <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                      {field.replaceAll("_", " ")}
                                    </dt>
                                    <dd className="break-words text-slate-800">
                                      {formatValue(
                                        value,
                                        patientTimezone ?? "UTC",
                                      )}
                                    </dd>
                                  </div>
                                ))}
                            </dl>
                            <div className="mt-4 rounded-lg bg-blue-50 p-3 text-sm text-slate-800">
                              <h4 className="font-semibold">
                                Selected-field preview
                              </h4>
                              <dl className="mt-2 space-y-2">
                                {reconciling.preview.available_fields
                                  .filter((field) =>
                                    selectedFields.includes(field),
                                  )
                                  .map((field) => (
                                    <div key={field}>
                                      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                        {field.replaceAll("_", " ")}
                                      </dt>
                                      <dd>
                                        <span className="text-slate-500">
                                          {formatValue(
                                            match.record[field],
                                            patientTimezone ?? "UTC",
                                          )}
                                        </span>{" "}
                                        <span aria-hidden="true">→</span>{" "}
                                        <span className="font-medium">
                                          {formatValue(
                                            reconciling.preview
                                              .candidate_fields[field],
                                            patientTimezone ?? "UTC",
                                          )}
                                        </span>
                                      </dd>
                                    </div>
                                  ))}
                              </dl>
                            </div>
                          </>
                        ) : null;
                      })()}
                  </>
                )}
              </div>
            </div>
            <fieldset>
              <legend className="text-sm font-semibold text-slate-900">
                Fields to apply
              </legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {reconciling.preview.available_fields.map((field) => (
                  <label
                    className="flex items-center gap-2 text-sm text-slate-700"
                    key={field}
                  >
                    <input
                      checked={selectedFields.includes(field)}
                      onChange={(event) =>
                        setSelectedFields((current) =>
                          event.target.checked
                            ? [...current, field]
                            : current.filter((item) => item !== field),
                        )
                      }
                      type="checkbox"
                    />
                    {field.replaceAll("_", " ")}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="block text-sm font-medium text-slate-700">
              Decision note (required for defer or reject)
              <textarea
                className="mt-2 min-h-20 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                onChange={(event) => setNote(event.target.value)}
                value={note}
              />
            </label>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm"
                onClick={() => setReconciling(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
                disabled={busyFactId !== null}
                onClick={() => void reconcile("defer")}
                type="button"
              >
                Defer
              </button>
              {reconciling.preview.matches.length > 0 && (
                <>
                  <button
                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
                    disabled={busyFactId !== null}
                    onClick={() => void reconcile("keep_existing")}
                    type="button"
                  >
                    Keep existing
                  </button>
                  <button
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                    disabled={
                      busyFactId !== null ||
                      !selectedTargetId ||
                      selectedFields.length === 0
                    }
                    onClick={() => void reconcile("update")}
                    type="button"
                  >
                    Update selected fields
                  </button>
                </>
              )}
              {reconciling.preview.matches.length === 0 && (
                <button
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  disabled={busyFactId !== null || selectedFields.length === 0}
                  onClick={() => void reconcile("add")}
                  type="button"
                >
                  Add local record
                </button>
              )}
              <button
                className="rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700"
                disabled={busyFactId !== null}
                onClick={() => void reconcile("reject")}
                type="button"
              >
                Reject
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        onClose={() => {
          if (!busyFactId) {
            setBinding(null);
            setBindingNote("");
          }
        }}
        open={Boolean(binding)}
        title="Confirm external patient binding"
      >
        {binding && (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              This comparison confirms that this external SMART patient belongs
              to this local chart. It never updates local demographics.
            </p>
            <div className="grid gap-4 rounded-xl border border-slate-200 p-4 sm:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  External SMART patient
                </h3>
                <dl className="mt-2 space-y-2 text-sm text-slate-700">
                  {Object.entries(binding.external_identity).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd>{formatValue(value, patientTimezone ?? "UTC")}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  Local chart
                </h3>
                <dl className="mt-2 space-y-2 text-sm text-slate-700">
                  {Object.entries(binding.local_identity).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd>{formatValue(value, patientTimezone ?? "UTC")}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
            </div>
            <div
              className={`rounded-lg px-3 py-2 text-sm ${binding.identity_matches ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}
            >
              {binding.identity_matches
                ? "The available identity details match."
                : "The available identity details differ or are incomplete. A clinician reason is required before binding synthetic records."}
            </div>
            {!binding.identity_matches && (
              <label className="block text-sm font-medium text-slate-700">
                Confirmation reason
                <textarea
                  className="mt-2 min-h-20 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                  onChange={(event) => setBindingNote(event.target.value)}
                  value={bindingNote}
                />
              </label>
            )}
            <div className="flex justify-end gap-3">
              <button
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm"
                onClick={() => setBinding(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                disabled={
                  busyFactId !== null ||
                  (!binding.identity_matches && !bindingNote.trim())
                }
                onClick={() => void confirmIdentityBinding()}
                type="button"
              >
                {busyFactId ? "Confirming…" : "Confirm binding"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        onClose={() => {
          if (!busyFactId) {
            setRejecting(null);
            setNote("");
          }
        }}
        open={Boolean(rejecting)}
        title="Reject imported fact"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Record why this imported candidate should not be used. The original
            source remains in the audit trail.
          </p>
          <label className="block text-sm font-medium text-slate-700">
            Rejection note
            <textarea
              className="mt-2 min-h-28 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
              onChange={(event) => setNote(event.target.value)}
              value={note}
            />
          </label>
          <div className="flex justify-end gap-3">
            <button
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm"
              onClick={() => setRejecting(null)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
              disabled={!note.trim() || busyFactId !== null}
              onClick={() => void reject()}
              type="button"
            >
              {busyFactId ? "Saving…" : "Confirm rejection"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        onClose={() => {
          if (!busyFactId) {
            setCorrecting(null);
            setNote("");
          }
        }}
        open={Boolean(correcting)}
        title="Correct imported fact"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Edit mapped fields, not the original FHIR source. The change remains
            pending review and is audited. Structured fields keep JSON only when
            their clinical structure must be preserved.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {correcting &&
              correctionFields(correcting).map(([key, label]) => {
                const original = correcting.value[key];
                const structured =
                  original !== null && typeof original === "object";
                return (
                  <label
                    className="block text-sm font-medium text-slate-700"
                    key={key}
                  >
                    {label}
                    {structured ? (
                      <textarea
                        className="mt-2 min-h-28 w-full rounded-xl border border-slate-300 px-3 py-2 font-mono text-xs"
                        onChange={(event) =>
                          setCorrectionDraft((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))
                        }
                        value={correctionDraft[key] ?? ""}
                      />
                    ) : (
                      <input
                        className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                        onChange={(event) =>
                          setCorrectionDraft((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))
                        }
                        value={correctionDraft[key] ?? ""}
                      />
                    )}
                  </label>
                );
              })}
          </div>
          <label className="block text-sm font-medium text-slate-700">
            Correction note
            <textarea
              className="mt-2 min-h-24 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
              onChange={(event) => setNote(event.target.value)}
              value={note}
            />
          </label>
          <div className="flex justify-end gap-3">
            <button
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm"
              onClick={() => setCorrecting(null)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
              disabled={!note.trim() || busyFactId !== null}
              onClick={() => void correct()}
              type="button"
            >
              {busyFactId ? "Saving…" : "Save corrected candidate"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        onClose={() => setSource(null)}
        open={Boolean(source)}
        title={
          source?.detail.source_kind === "document"
            ? "Original document evidence"
            : "Original SMART FHIR source"
        }
      >
        {source && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              {source.detail.resource_type}
              {source.detail.external_resource_id
                ? ` · ${source.detail.external_resource_id}`
                : ""}
              {source.detail.version_id
                ? ` · version ${source.detail.version_id}`
                : ""}
            </p>
            <pre className="max-h-[60vh] overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">
              {JSON.stringify(source.detail.raw_resource, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </section>
  );
}
