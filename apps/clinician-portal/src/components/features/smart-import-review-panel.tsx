"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { Card, Modal, Skeleton } from "@/components/ui";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

type ReviewState = "pending_review" | "approved" | "rejected";

interface MedicationReferenceResult {
  fact_id: string;
  status: "found" | "not_found" | "unavailable";
  subject: string | null;
  rxcui: string | null;
  retrieved_at: string;
  references: Array<{
    source: "medlineplus" | "dailymed";
    locale: "en-US" | "es-MX";
    title: string;
    url: string;
    summary: string;
    source_version: string | null;
    source_updated: string | null;
    checked_at: string;
    stale: boolean;
  }>;
}

function ReferenceTime({ value }: { value: string | null }) {
  if (!value || !Number.isFinite(Date.parse(value))) return <>Unknown</>;
  return <time dateTime={value}>{value.slice(0, 10).length === value.length ? value : new Date(value).toLocaleString("en-US")}</time>;
}

function MedicationReferencePanel({ patientId, factId, token }: { patientId: string; factId: string; token: string }) {
  const [result, setResult] = useState<MedicationReferenceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);

  async function lookup() {
    const request = ++generation.current;
    setLoading(true);
    setFailed(false);
    setResult(null);
    try {
      const response = await api.get<MedicationReferenceResult>(
        `/api/v1/smart/patients/${encodeURIComponent(patientId)}/facts/${encodeURIComponent(factId)}/medication-reference`, { token },
      );
      if (request !== generation.current) return;
      if (response.fact_id !== factId) throw new Error("Reference scope changed");
      setResult(response);
    } catch {
      if (request === generation.current) setFailed(true);
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }

  return <section aria-label="Medication reference" className="space-y-3 rounded-xl border border-line p-3 text-sm text-ink-2">
    <button type="button" disabled={loading} onClick={() => void lookup()} className="min-h-9 rounded-lg border border-line-strong px-3 py-2 font-medium text-primary disabled:opacity-50">{loading ? "Loading medication reference…" : result || failed ? "Retry medication reference" : "Medication reference"}</button>
    <p className="text-xs text-muted">Optional external public lookup sends only the recorded drug name to the existing reference providers; patient identity and chart details are not sent. A resolved RxNorm ingredient concept is not an exact formulation match or proof of product identity, therapeutic equivalence, interaction safety or clinical approval. This lookup does not apply values or change the chart or imported record.</p>
    {loading && <p role="status">Loading public medication references…</p>}
    {failed && <p role="alert">Medication reference unavailable. Retry to check the public sources; no safety conclusion can be drawn.</p>}
    {result && <>
      <p>Reference subject: {result.subject ?? "Unknown"} · Resolved RxNorm ingredient: {result.rxcui ?? "Unknown"}</p>
      <p className="text-xs text-muted">Lookup returned: <ReferenceTime value={result.retrieved_at} />. Source check dates below are not the last clinical review.</p>
      {result.status === "unavailable" && <p role="alert">Public reference lookup unavailable. Any cached references below retain their own check dates.</p>}
      {result.status === "not_found" && <p role="status">No public reference found for this candidate. This does not mean the product is safe or has no interactions.</p>}
      {result.references.length > 0 && <p className="text-xs text-muted">Up to 3 references; excerpts are limited to 1,200 characters each. Open the official source for the full reference.</p>}
      <ul className="space-y-3">
        {result.references.map((reference) => <li key={`${reference.source}:${reference.locale}:${reference.url}`} className="space-y-1 border-t border-line pt-3">
          <a className="font-medium text-primary underline" href={reference.url} target="_blank" rel="noopener noreferrer">{reference.title || reference.source} ({reference.locale})</a>
          <p className="whitespace-pre-wrap break-words">{reference.summary}</p>
          <p className="text-xs text-muted">Source checked: <ReferenceTime value={reference.checked_at} /> · Source updated: <ReferenceTime value={reference.source_updated} /> · Source version: {reference.source_version ?? "Unknown"}</p>
          <p className={reference.stale ? "text-xs font-medium text-warn-ink" : "text-xs text-muted"}>{reference.stale ? "Stale cached reference — verify the official source before relying on it." : "Within the reference cache age window; this is not proof of clinical currency or review."}</p>
        </li>)}
      </ul>
    </>}
  </section>;
}

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
  review_flags?: string[];
  safety_coverage?: string | null;
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

const EYEBROW = "font-mono text-[11px] uppercase tracking-[0.06em] text-muted";
const CHIP = "inline-flex items-center gap-1.5 rounded-[7px] px-2 py-1 text-xs font-medium";
const BUTTON_BASE = "ma-press inline-flex h-[34px] items-center justify-center gap-1.5 rounded-[9px] px-3.5 text-[13px] disabled:cursor-not-allowed";
const SECONDARY_BUTTON = `${BUTTON_BASE} border border-line-strong bg-surface font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:text-[#94A3B8] disabled:hover:bg-surface`;
const PRIMARY_BUTTON = `${BUTTON_BASE} bg-primary font-semibold text-white hover:bg-primary-hover disabled:bg-track disabled:text-[#94A3B8]`;
const APPROVE_BUTTON = `${BUTTON_BASE} bg-ok font-semibold text-white hover:bg-ok-strong disabled:bg-track disabled:text-[#94A3B8]`;
const DANGER_BUTTON = `${BUTTON_BASE} border border-risk-line bg-surface font-semibold text-risk-ink hover:bg-risk-soft disabled:text-[#94A3B8] disabled:hover:bg-surface`;
const ICON_BUTTON = "ma-press flex h-8 w-8 items-center justify-center rounded-lg border border-line-strong bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface";
const INPUT = "h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm font-normal text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]";
const TEXTAREA = "w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm font-normal text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]";
const FILTER_LABEL = "flex flex-col gap-1 font-mono text-[11px] uppercase tracking-[0.06em] text-muted";
const FILTER_CONTROL = "h-[34px] min-w-[9rem] rounded-[9px] border border-line-strong bg-surface px-3 text-[13px] font-normal normal-case tracking-normal text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]";

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

const DATE_FIELDS = new Set(["birthDate", "birth_date", "date_of_birth", "onset", "recorded", "authored", "effective", "issued", "performed", "period", "date", "start", "end"]);

function formatFhirDateTime(value: string, timezone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return value;

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

function formatValue(value: unknown, timezone: string, field = ""): string {
  if (value === null || value === undefined || value === "")
    return "Not supplied";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  )
    return typeof value === "string" && DATE_FIELDS.has(field)
      ? formatFhirDateTime(value, timezone)
      : String(value);
  if (Array.isArray(value))
    return value.length
      ? value.map((item) => formatValue(item, timezone, field)).join("; ")
      : "Not supplied";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.text === "string") return record.text;
    if (typeof record.display === "string") return record.display;
    if (typeof record.code === "string") return record.code;
    if (DATE_FIELDS.has(field) && (typeof record.start === "string" || typeof record.end === "string")) {
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
  if (state === "approved") return "bg-ok-tint text-ok-ink";
  if (state === "rejected") return "bg-risk-tint text-risk-ink";
  return "bg-warn-tint text-warn-ink";
}

function stateDot(state: ReviewState): string {
  if (state === "approved") return "bg-ok";
  if (state === "rejected") return "bg-risk";
  return "bg-warn";
}

function sourceHost(issuer: string): string {
  try {
    return new URL(issuer).host || issuer;
  } catch {
    return issuer;
  }
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
    <dl className="grid gap-x-6 gap-y-3 rounded-[14px] border border-line bg-surface-2 p-4 sm:grid-cols-2 xl:grid-cols-3">
      {fields.map(([key, label]) => {
        const text = formatValue(fact.value[key], patientTimezone, key);
        const dated = DATE_FIELDS.has(key) && /\d{4}/.test(text);
        return (
          <div className="min-w-0" key={key}>
            <dt className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
              {label}
            </dt>
            <dd className={`mt-1 break-words ${dated ? "font-mono text-[13px]" : "text-sm"} ${text === "Not supplied" ? "text-muted" : "text-ink"}`}>
              {text}
            </dd>
          </div>
        );
      })}
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
  const reconciliationTrigger = useRef<HTMLButtonElement | null>(null);
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

  async function openReconciliation(fact: ReviewFact, trigger: HTMLButtonElement) {
    if (!token) return;
    reconciliationTrigger.current = trigger;
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className={EYEBROW}>
            External-record reconciliation
          </p>
          <h2
            className="mt-1.5 text-lg font-semibold tracking-[-0.01em] text-ink"
            id="smart-import-review-heading"
          >
            External records review
          </h2>
          <p className="mt-1 max-w-[80ch] text-sm text-muted">
            Review SMART and document candidates with source-level provenance.
            Only a field-by-field reconciliation decision can change an existing
            medication, condition, or allergy; evidence-only records remain
            read-only.
          </p>
        </div>
        <button
          disabled={loading || busyFactId !== null}
          className={`${SECONDARY_BUTTON} shrink-0 self-start sm:self-auto`}
          onClick={() => void load()}
          type="button"
        >
          <Icon name="refresh" aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <ol aria-label="Review steps" className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[13px] text-muted">
        {["Inspect provenance", "Compare with the local chart", "Record a clinician decision"].map((step, index) => (
          <li className="flex items-center gap-2" key={step}>
            {index > 0 ? <Icon name="chevron" className="h-3.5 w-3.5 text-[#94A3B8]" /> : null}
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-sunken font-mono text-[11px] text-ink-2">{index + 1}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className="grid gap-3 sm:grid-cols-3">
        {(["pending_review", "approved", "rejected"] as ReviewState[]).map(
          (state) => (
            <button
              aria-pressed={reviewState === state}
              className={`ma-press rounded-2xl border px-5 py-4 text-left ${reviewState === state ? "border-primary bg-primary-tint shadow-[0_0_0_3px_rgba(37,99,235,.10)]" : "border-line bg-surface shadow-[var(--shadow-card)] hover:border-line-strong hover:bg-surface-2"}`}
              key={state}
              onClick={() => {
                setReviewState(state);
                setOffset(0);
              }}
              type="button"
            >
              <p className="flex items-center gap-2 text-[13px] text-muted">
                <span aria-hidden="true" className={`h-[7px] w-[7px] rounded-full ${stateDot(state)}`} />
                {stateLabel(state)}
              </p>
              <p className="mt-1.5 font-mono text-[28px] font-medium leading-none text-ink">
                {loading || error ? "—" : review?.state_counts[state] ?? 0}
              </p>
            </button>
          ),
        )}
      </div>

      {error && (
        <div
          className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
          role="alert"
        >
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <Card className="overflow-hidden" padding="none">
        <div className="border-b border-line px-5 py-4">
          <h3 className="text-[15px] font-semibold text-ink">
            {stateLabel(reviewState)} imported facts
          </h3>
          <p className="text-[13px] text-muted">
            {loading ? (
              "Loading imported fact count…"
            ) : error ? (
              "Imported fact count unavailable."
            ) : (
              <><span className="font-mono">{total}</span> {total === 1 ? "fact" : "facts"} in this review state.</>
            )} Source data remains synthetic and read-only.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3 border-b border-line bg-surface-2 px-5 py-3">
          {review && Object.keys(review.fact_type_counts).length > 0 && (
            <label className={FILTER_LABEL}>
              Mapped type
              <select
                aria-label="Filter imported facts by mapped type"
                className={FILTER_CONTROL}
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
          <label className={FILTER_LABEL}>
            Source
            <select
              aria-label="Filter imported facts by source"
              className={FILTER_CONTROL}
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
          <label className={FILTER_LABEL}>
            Reconciliation
            <select
              aria-label="Filter imported facts by reconciliation state"
              className={FILTER_CONTROL}
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
          <label className={FILTER_LABEL}>
            From
            <input
              aria-label="Filter imported facts from date"
              className={`${FILTER_CONTROL} font-mono`}
              onChange={(event) => {
                setFromDate(event.target.value);
                setOffset(0);
              }}
              type="date"
              value={fromDate}
            />
          </label>
          <label className={FILTER_LABEL}>
            To
            <input
              aria-label="Filter imported facts to date"
              className={`${FILTER_CONTROL} font-mono`}
              onChange={(event) => {
                setToDate(event.target.value);
                setOffset(0);
              }}
              type="date"
              value={toDate}
            />
          </label>
        </div>

        {loading ? (
          <div className="space-y-4 p-5">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton className="h-44 w-full" key={index} />
            ))}
          </div>
        ) : review?.facts.length === 0 ? (
          <div className="flex min-h-48 flex-col items-center justify-center gap-3 px-5 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
              <Icon name="inbox" className="h-6 w-6" />
            </span>
            <p className="text-[15px] font-semibold text-ink">
              No {stateLabel(reviewState).toLowerCase()} imported facts
            </p>
            <p className="max-w-[48ch] text-sm text-muted">
              New SMART and document imports appear here as clinician-review
              candidates.
            </p>
          </div>
        ) : (
          <div>
            {review?.facts.map((fact) => (
              <article className="space-y-4 border-b border-line px-5 py-5 last:border-b-0" key={fact.id}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-[15px] font-semibold text-ink">
                        {FACT_LABELS[fact.fact_type] ?? fact.fact_type}
                      </h4>
                      {fact.review_state === "approved" ? (
                        <ApprovalSeal pill>
                          {stateLabel(fact.review_state)}
                        </ApprovalSeal>
                      ) : (
                        <span
                          className={`${CHIP} ${stateClass(fact.review_state)}`}
                        >
                          <span aria-hidden="true" className={`h-[7px] w-[7px] rounded-full ${stateDot(fact.review_state)}`} />
                          {stateLabel(fact.review_state)}
                        </span>
                      )}
                      {fact.reconciliation_state &&
                        fact.reconciliation_state !== "not_started" && (
                          <span className={`${CHIP} bg-sunken capitalize text-ink-2`}>
                            {fact.reconciliation_state.replaceAll("_", " ")}
                          </span>
                        )}
                    </div>
                    <dl className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
                      <div className="flex items-center gap-1.5">
                        <dt className="sr-only">Source system</dt>
                        <dd className="flex items-center gap-1.5">
                          <Icon name={fact.source?.source_kind === "document" ? "file" : "link"} className="h-3.5 w-3.5" />
                          {fact.source
                            ? fact.source.source_kind === "document"
                              ? "Document"
                              : fact.source.source_kind === "smart"
                                ? `SMART · ${sourceHost(fact.source.issuer)}`
                                : sourceHost(fact.source.issuer)
                            : "Unknown source"}
                        </dd>
                      </div>
                      {fact.source && (
                        <div className="flex items-center gap-1.5">
                          <dt className="sr-only">Resource type</dt>
                          <dd className="rounded-[5px] bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
                            {fact.source.resource_type}
                          </dd>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        <dt>Imported</dt>
                        <dd className="font-mono text-ink-2">
                          {formatFhirDateTime(fact.created_at, patientTimezone ?? "UTC")}
                        </dd>
                      </div>
                    </dl>
                    <details className="ma-disclosure mt-1 text-xs text-muted"><summary className="min-h-9 py-1.5 text-[13px] font-medium">Source identifiers</summary><p className="break-words pb-1 pl-[1.375rem] font-mono text-[11px]">
                      {fact.source
                        ? `${fact.source.resource_type}${fact.source.external_resource_id ? ` · ${fact.source.external_resource_id}` : ""}${fact.source.version_id ? ` · version ${fact.source.version_id}` : ""}`
                        : "Source metadata unavailable"}
                    </p></details>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <button
                      className={SECONDARY_BUTTON}
                      disabled={busyFactId === fact.id || !fact.source}
                      onClick={() => void inspectSource(fact)}
                      type="button"
                    >
                      <Icon name="eye" className="h-4 w-4" />{" "}
                      Source
                    </button>
                    {fact.review_state === "pending_review" && (
                      <>
                        {PROJECTABLE_TYPES.has(fact.fact_type) ? (
                          <button
                            className={PRIMARY_BUTTON}
                            disabled={busyFactId === fact.id}
                            onClick={(event) => void openReconciliation(fact, event.currentTarget)}
                            type="button"
                          >
                            <Icon name="history" className="h-4 w-4" /> Review
                            changes
                          </button>
                        ) : (
                          <button
                            className={APPROVE_BUTTON}
                            disabled={busyFactId === fact.id}
                            onClick={() => void approve(fact)}
                            type="button"
                          >
                            <Icon name="check" className="h-4 w-4" /> Mark
                            reviewed
                          </button>
                        )}
                        {PROJECTABLE_TYPES.has(fact.fact_type) &&
                          fact.source?.source_kind === "smart" &&
                          fact.source.import_id && (
                            <button
                              className={`${SECONDARY_BUTTON} text-primary hover:text-primary-hover`}
                              disabled={busyFactId === fact.id}
                              onClick={() =>
                                void openIdentityBinding(
                                  String(fact.source?.import_id),
                                )
                              }
                              type="button"
                            >
                              <Icon name="user" className="h-4 w-4" />
                              Confirm patient
                            </button>
                          )}
                        <button
                          className={SECONDARY_BUTTON}
                          disabled={busyFactId === fact.id}
                          onClick={() => {
                            setCorrecting(fact);
                            setCorrectionDraft(buildCorrectionDraft(fact));
                            setNote("");
                          }}
                          type="button"
                        >
                          <Icon name="edit" className="h-4 w-4" /> Correct
                        </button>
                        <button
                          className={DANGER_BUTTON}
                          disabled={busyFactId === fact.id}
                          onClick={() => {
                            setRejecting(fact);
                            setNote("");
                          }}
                          type="button"
                        >
                          <Icon name="close" className="h-4 w-4" /> Reject
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
                  <div className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                    <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>{fact.uncertainty.join(" ")}</p>
                  </div>
                )}
                {fact.reconciliation_state === "source_withdrawn" && (
                  <div className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                    <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>
                      The supporting source was withdrawn after local
                      reconciliation. Review the preserved local record and audit
                      history before further use.
                    </p>
                  </div>
                )}
                {fact.reconciliation_state === "applied" &&
                  fact.reconciliation_target_id && (
                    <a
                      className="inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:text-primary-hover hover:underline"
                      href={`/patients/${patientId}`}
                    >
                      View applied local{" "}
                      {fact.reconciliation_target_type ?? "record"}
                      <Icon name="arrow" className="h-3.5 w-3.5" />
                    </a>
                  )}
                {fact.source &&
                  (fact.source.mapping_warnings.length > 0 ||
                    fact.source.validation_errors.length > 0) && (
                    <div className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                      <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
                      <p>
                        {[
                          ...fact.source.mapping_warnings,
                          ...fact.source.validation_errors,
                        ].join(" ")}
                      </p>
                    </div>
                  )}
              </article>
            ))}
          </div>
        )}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3 text-[13px] text-muted">
            <span className="font-mono">
              {start}–{end} of {total}
            </span>
            <div className="flex gap-2">
              <button
                aria-label="Previous imported facts"
                className={ICON_BUTTON}
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                type="button"
              >
                <Icon name="chevron" className="h-4 w-4 rotate-180" />
              </button>
              <button
                aria-label="Next imported facts"
                className={ICON_BUTTON}
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                type="button"
              >
                <Icon name="chevron" className="h-4 w-4" />
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
        returnFocusRef={reconciliationTrigger}
      >
        {reconciling && (
          <div className="space-y-5">
            <p className="text-sm text-ink-2">
              Select exactly which imported values may be applied. Missing
              values never clear the local chart; this action is recorded with
              the original source version.
            </p>
            {reconciling.preview.safety_coverage && <section aria-label="Medication comparison coverage" className="rounded-xl border border-warn-line bg-warn-soft p-3 text-sm text-ink-2">
              <p>{reconciling.preview.safety_coverage}</p>
              {!!reconciling.preview.review_flags?.length && <ul className="mt-2 list-disc space-y-1 pl-5">{reconciling.preview.review_flags.map((flag) => <li key={flag}>{flag}</li>)}</ul>}
            </section>}
            {reconciling.fact.fact_type === "medication" && token && <MedicationReferencePanel key={`${patientId}:${reconciling.fact.id}:${token}`} patientId={patientId} factId={reconciling.fact.id} token={token} />}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[14px] border border-line bg-surface-2 p-4">
                <h3 className="text-[13px] font-semibold text-ink">
                  Imported candidate
                </h3>
                <dl className="mt-3 space-y-2.5 text-sm">
                  {Object.entries(reconciling.preview.candidate_fields).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className={EYEBROW}>
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd className="mt-0.5 break-words text-ink">
                          {formatValue(value, patientTimezone ?? "UTC", field)}
                        </dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
              <div className="rounded-[14px] border border-line bg-surface p-4">
                <h3 className="text-[13px] font-semibold text-ink">
                  Matched local record
                </h3>
                {reconciling.preview.matches.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">
                    No conservative match was found. You may add a new local
                    record after checking the candidate fields.
                  </p>
                ) : (
                  <>
                    <label className="mt-3 block text-[13px] font-medium text-ink-2">
                      {reconciling.preview.matches.length > 1
                        ? "Choose a local record"
                        : "Matched local record"}
                      <select
                        className={`mt-1.5 ${INPUT}`}
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
                            <dl className="mt-3 space-y-2.5 text-sm">
                              {Object.entries(match.record)
                                .filter(([field]) =>
                                  reconciling.preview.available_fields.includes(
                                    field,
                                  ),
                                )
                                .map(([field, value]) => (
                                  <div key={field}>
                                    <dt className={EYEBROW}>
                                      {field.replaceAll("_", " ")}
                                    </dt>
                                    <dd className="mt-0.5 break-words text-ink">
                                      {formatValue(
                                        value,
                                        patientTimezone ?? "UTC",
                                        field,
                                      )}
                                    </dd>
                                  </div>
                                ))}
                            </dl>
                            <div className="mt-4 rounded-xl border border-primary-line bg-primary-tint p-3 text-sm text-ink">
                              <h4 className="text-[13px] font-semibold">
                                Selected-field preview
                              </h4>
                              <dl className="mt-2 space-y-2">
                                {reconciling.preview.available_fields
                                  .filter((field) =>
                                    selectedFields.includes(field),
                                  )
                                  .map((field) => (
                                    <div key={field}>
                                      <dt className={EYEBROW}>
                                        {field.replaceAll("_", " ")}
                                      </dt>
                                      <dd className="mt-0.5">
                                        <span className="text-muted line-through decoration-line-strong">
                                          {formatValue(
                                            match.record[field],
                                            patientTimezone ?? "UTC",
                                            field,
                                          )}
                                        </span>{" "}
                                        <span aria-hidden="true" className="text-primary">→</span>{" "}
                                        <span className="font-medium">
                                          {formatValue(
                                            reconciling.preview
                                              .candidate_fields[field],
                                            patientTimezone ?? "UTC",
                                            field,
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
              <legend className="text-[13px] font-semibold text-ink">
                Fields to apply
              </legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {reconciling.preview.available_fields.map((field) => (
                  <label
                    className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-[9px] border border-line px-3 text-sm capitalize text-ink-2 hover:bg-surface-2"
                    key={field}
                  >
                    <input
                      checked={selectedFields.includes(field)}
                      className="h-4 w-4 accent-[var(--color-primary)]"
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
            <label className="block text-[13px] font-medium text-ink-2">
              Decision note (required for defer or reject)
              <textarea
                className={`mt-1.5 min-h-20 ${TEXTAREA}`}
                onChange={(event) => setNote(event.target.value)}
                value={note}
              />
            </label>
            <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
              <button
                className={SECONDARY_BUTTON}
                onClick={() => setReconciling(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className={SECONDARY_BUTTON}
                disabled={busyFactId !== null}
                onClick={() => void reconcile("defer")}
                type="button"
              >
                Defer
              </button>
              {reconciling.preview.matches.length > 0 && (
                <>
                  <button
                    className={SECONDARY_BUTTON}
                    disabled={busyFactId !== null}
                    onClick={() => void reconcile("keep_existing")}
                    type="button"
                  >
                    Keep existing
                  </button>
                  <button
                    className={APPROVE_BUTTON}
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
                  className={APPROVE_BUTTON}
                  disabled={busyFactId !== null || selectedFields.length === 0}
                  onClick={() => void reconcile("add")}
                  type="button"
                >
                  Add local record
                </button>
              )}
              <button
                className={DANGER_BUTTON}
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
            <p className="text-sm text-ink-2">
              This comparison confirms that this external SMART patient belongs
              to this local chart. It never updates local demographics.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[14px] border border-line bg-surface-2 p-4">
                <h3 className="text-[13px] font-semibold text-ink">
                  External SMART patient
                </h3>
                <dl className="mt-3 space-y-2.5 text-sm text-ink-2">
                  {Object.entries(binding.external_identity).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className={EYEBROW}>
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd className="mt-0.5">{formatValue(value, patientTimezone ?? "UTC", field)}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
              <div className="rounded-[14px] border border-line bg-surface p-4">
                <h3 className="text-[13px] font-semibold text-ink">
                  Local chart
                </h3>
                <dl className="mt-3 space-y-2.5 text-sm text-ink-2">
                  {Object.entries(binding.local_identity).map(
                    ([field, value]) => (
                      <div key={field}>
                        <dt className={EYEBROW}>
                          {field.replaceAll("_", " ")}
                        </dt>
                        <dd className="mt-0.5">{formatValue(value, patientTimezone ?? "UTC", field)}</dd>
                      </div>
                    ),
                  )}
                </dl>
              </div>
            </div>
            <div
              className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${binding.identity_matches ? "border-ok-line bg-ok-soft text-ok-ink" : "border-warn-line bg-warn-soft text-warn-ink"}`}
            >
              <Icon name={binding.identity_matches ? "info" : "alert"} className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                {binding.identity_matches
                  ? "The available identity details match."
                  : "The available identity details differ or are incomplete. A clinician reason is required before binding synthetic records."}
              </p>
            </div>
            {!binding.identity_matches && (
              <label className="block text-[13px] font-medium text-ink-2">
                Confirmation reason
                <textarea
                  className={`mt-1.5 min-h-20 ${TEXTAREA}`}
                  onChange={(event) => setBindingNote(event.target.value)}
                  value={bindingNote}
                />
              </label>
            )}
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <button
                className={SECONDARY_BUTTON}
                onClick={() => setBinding(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className={PRIMARY_BUTTON}
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
          <p className="text-sm text-ink-2">
            Record why this imported candidate should not be used. The original
            source remains in the audit trail.
          </p>
          <label className="block text-[13px] font-medium text-ink-2">
            Rejection note
            <textarea
              className={`mt-1.5 min-h-28 ${TEXTAREA}`}
              onChange={(event) => setNote(event.target.value)}
              value={note}
            />
          </label>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <button
              className={SECONDARY_BUTTON}
              onClick={() => setRejecting(null)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="ma-press inline-flex h-[34px] items-center justify-center gap-2 rounded-[9px] bg-risk px-4 text-[13px] font-semibold text-white hover:bg-risk-strong disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
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
          <p className="text-sm text-ink-2">
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
                    className="block text-[13px] font-medium text-ink-2"
                    key={key}
                  >
                    {label}
                    {structured ? (
                      <textarea
                        className={`mt-1.5 min-h-28 ${TEXTAREA} font-mono text-xs`}
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
                        className={`mt-1.5 ${INPUT}`}
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
          <label className="block text-[13px] font-medium text-ink-2">
            Correction note
            <textarea
              className={`mt-1.5 min-h-24 ${TEXTAREA}`}
              onChange={(event) => setNote(event.target.value)}
              value={note}
            />
          </label>
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <button
              className={SECONDARY_BUTTON}
              onClick={() => setCorrecting(null)}
              type="button"
            >
              Cancel
            </button>
            <button
              className={PRIMARY_BUTTON}
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
            <p className="font-mono text-xs text-muted">
              {source.detail.resource_type}
              {source.detail.external_resource_id
                ? ` · ${source.detail.external_resource_id}`
                : ""}
              {source.detail.version_id
                ? ` · version ${source.detail.version_id}`
                : ""}
            </p>
            <pre className="max-h-[60vh] overflow-auto rounded-xl bg-rail p-4 font-mono text-xs leading-relaxed text-rail-ink">
              {JSON.stringify(source.detail.raw_resource, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </section>
  );
}
