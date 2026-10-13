"use client";

import { useEffect, useRef, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import type { MedWatchDraft, MedWatchFormData } from "@/services/clinicians";

const inputClass =
  "mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100";

function TextField({
  label,
  value,
  disabled,
  multiline = false,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  multiline?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-sm font-medium text-gray-700">
      {label}
      {multiline ? (
        <textarea
          className={`${inputClass} min-h-20`}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          value={value}
        />
      ) : (
        <input
          className={inputClass}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          value={value}
        />
      )}
    </label>
  );
}

export function MedWatchDraftCard({
  draft,
  busy,
  onSave,
  onApprove,
  onExport,
}: {
  draft: MedWatchDraft;
  busy: boolean;
  onSave: (
    draftId: string,
    form: MedWatchFormData,
    revision: number,
  ) => Promise<void>;
  onApprove: (draftId: string, note: string, revision: number) => Promise<void>;
  onExport: (draftId: string) => Promise<void>;
}) {
  const [form, setForm] = useState(draft.formData);
  const [approvalNote, setApprovalNote] = useState("");
  const [attested, setAttested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const editable = draft.status === "draft";

  useEffect(() => setForm(draft.formData), [draft.formData]);

  function setField(
    section: keyof MedWatchFormData,
    field: string,
    value: string,
  ) {
    setForm((current) => ({
      ...current,
      [section]: { ...current[section], [field]: value },
    }));
  }

  async function perform(operation: () => Promise<void>) {
    if (busy || pending.current) return;
    pending.current = true;
    setError(null);
    try {
      await operation();
    } catch {
      setError(
        "Unable to complete this action. Your unsaved form values are retained.",
      );
    } finally {
      pending.current = false;
    }
  }

  return (
    <Card className="space-y-5" padding="lg">
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-gray-900">
              MedWatch-compatible draft
            </h2>
            <Badge variant={editable ? "warning" : "success"}>
              {editable ? "Needs approval" : "Approved for export"}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Revision {draft.revision} · Draft ID {draft.id}
          </p>
        </div>
        <p className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
          Not submitted to FDA
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Patient
          </legend>
          <TextField
            disabled={!editable || busy}
            label="Patient identifier"
            onChange={(value) =>
              setField("patient", "patient_identifier", value)
            }
            value={form.patient.patient_identifier}
          />
          <TextField
            disabled={!editable || busy}
            label="Date of birth"
            onChange={(value) => setField("patient", "date_of_birth", value)}
            value={form.patient.date_of_birth}
          />
          <TextField
            disabled={!editable || busy}
            label="Sex"
            onChange={(value) => setField("patient", "sex", value)}
            value={form.patient.sex}
          />
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Adverse event
          </legend>
          <TextField
            disabled={!editable || busy}
            label="Description"
            multiline
            onChange={(value) => setField("event", "description", value)}
            value={form.event.description}
          />
          <TextField
            disabled={!editable || busy}
            label="Onset date or time"
            onChange={(value) => setField("event", "onset_date_or_time", value)}
            value={form.event.onset_date_or_time}
          />
          <TextField
            disabled={!editable || busy}
            label="Outcome (leave empty if unknown)"
            onChange={(value) => setField("event", "outcome", value)}
            value={form.event.outcome}
          />
          <TextField
            disabled={!editable || busy}
            label="Seriousness (leave empty if unknown)"
            onChange={(value) => setField("event", "seriousness", value)}
            value={form.event.seriousness}
          />
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Suspect product
          </legend>
          <TextField
            disabled={!editable || busy}
            label="Product name"
            onChange={(value) => setField("suspect_product", "name", value)}
            value={form.suspect_product.name}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              disabled={!editable || busy}
              label="Dose"
              onChange={(value) => setField("suspect_product", "dose", value)}
              value={form.suspect_product.dose}
            />
            <TextField
              disabled={!editable || busy}
              label="Frequency"
              onChange={(value) =>
                setField("suspect_product", "frequency", value)
              }
              value={form.suspect_product.frequency}
            />
            <TextField
              disabled={!editable || busy}
              label="Route"
              onChange={(value) => setField("suspect_product", "route", value)}
              value={form.suspect_product.route}
            />
            <TextField
              disabled={!editable || busy}
              label="Therapy start"
              onChange={(value) =>
                setField("suspect_product", "therapy_start_date", value)
              }
              value={form.suspect_product.therapy_start_date}
            />
            <TextField
              disabled={!editable || busy}
              label="Therapy end"
              onChange={(value) =>
                setField("suspect_product", "therapy_end_date", value)
              }
              value={form.suspect_product.therapy_end_date}
            />
          </div>
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Other clinical details
          </legend>
          <TextField
            disabled={!editable || busy}
            label="Concomitant products"
            multiline
            onChange={(value) =>
              setField("concomitant_products", "products", value)
            }
            value={form.concomitant_products.products}
          />
          <TextField
            disabled={!editable || busy}
            label="Relevant tests"
            multiline
            onChange={(value) =>
              setField("tests_and_history", "relevant_tests", value)
            }
            value={form.tests_and_history.relevant_tests}
          />
          <TextField
            disabled={!editable || busy}
            label="Other relevant history"
            multiline
            onChange={(value) =>
              setField("tests_and_history", "other_relevant_history", value)
            }
            value={form.tests_and_history.other_relevant_history}
          />
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Reporter
          </legend>
          <TextField
            disabled={!editable || busy}
            label="Name"
            onChange={(value) => setField("reporter", "name", value)}
            value={form.reporter.name}
          />
          <TextField
            disabled={!editable || busy}
            label="Email"
            onChange={(value) => setField("reporter", "email", value)}
            value={form.reporter.email}
          />
          <TextField
            disabled={!editable || busy}
            label="Specialty"
            onChange={(value) => setField("reporter", "specialty", value)}
            value={form.reporter.specialty}
          />
          <TextField
            disabled={!editable || busy}
            label="Clinic"
            onChange={(value) => setField("reporter", "clinic_name", value)}
            value={form.reporter.clinic_name}
          />
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Clinical review
          </legend>
          <p className="text-sm text-gray-700">
            Deterministic Naranjo score:{" "}
            <strong>{form.clinical_review.naranjo_score}</strong> ·{" "}
            {form.clinical_review.causality}
          </p>
          <TextField
            disabled={!editable || busy}
            label="Reportability rationale"
            multiline
            onChange={(value) =>
              setField("clinical_review", "reportability_rationale", value)
            }
            value={form.clinical_review.reportability_rationale}
          />
        </fieldset>
      </div>

      <details className="rounded-lg border border-gray-200 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-gray-900">
          Source evidence and attribution ({draft.sourceEvidence.length})
        </summary>
        <ul className="mt-3 space-y-2">
          {draft.sourceEvidence.map((source, index) => (
            <li
              className="rounded-lg bg-gray-50 p-3 text-sm"
              key={`${source.source_type}-${index}`}
            >
              <p className="font-medium text-gray-900">{source.attribution}</p>
              <p className="mt-1 text-xs text-gray-500">
                {source.field_paths.join(", ")}
              </p>
              {source.excerpt ? (
                <p className="mt-2 text-gray-700">“{source.excerpt}”</p>
              ) : null}
              {source.citation ? (
                <p className="mt-1 text-xs text-blue-700">
                  Source: {source.citation}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </details>

      {error ? (
        <p
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {editable ? (
        <div className="space-y-4 border-t border-gray-200 pt-4">
          <Button
            disabled={busy}
            onClick={() =>
              void perform(() => onSave(draft.id, form, draft.revision))
            }
            size="sm"
            variant="secondary"
          >
            Save draft
          </Button>
          <div className="rounded-lg border border-green-200 bg-green-50 p-4">
            <h3 className="text-sm font-semibold text-green-950">
              Clinician approval
            </h3>
            <TextField
              disabled={busy}
              label="Approval note"
              multiline
              onChange={setApprovalNote}
              value={approvalNote}
            />
            <label className="mt-3 flex items-start gap-2 text-sm text-green-950">
              <input
                checked={attested}
                className="mt-1"
                disabled={busy}
                onChange={(event) => setAttested(event.target.checked)}
                type="checkbox"
              />
              I reviewed the draft and its source evidence. I understand
              approval makes it exportable but does not submit it to the FDA.
            </label>
            <Button
              className="mt-3"
              disabled={busy || !attested || !approvalNote.trim()}
              onClick={() =>
                void perform(() =>
                  onApprove(draft.id, approvalNote.trim(), draft.revision),
                )
              }
              size="sm"
            >
              Approve for export
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col justify-between gap-3 border-t border-gray-200 pt-4 md:flex-row md:items-center">
          <p className="text-sm text-gray-700">
            Approved{" "}
            {draft.approvedAt
              ? new Date(draft.approvedAt).toLocaleString()
              : ""}
            . Exporting records an audit event; it does not submit the draft.
          </p>
          <Button
            disabled={busy}
            onClick={() => void perform(() => onExport(draft.id))}
            size="sm"
          >
            Export approved JSON
          </Button>
        </div>
      )}
    </Card>
  );
}
