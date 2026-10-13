"use client";

import { useRef, useState } from "react";
import { Badge, Button, Card, Input } from "@/components/ui";
import { fieldClass } from "@/components/ui/input";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import { formatReviewTimestamp } from "@/components/features/review-time";
import type { MedWatchDraft, MedWatchFormData } from "@/services/clinicians";

const fieldsetClass = "min-w-0 space-y-3 rounded-xl border border-line p-4";
const legendClass = "px-1 text-[13px] font-semibold text-ink";
const wrapClass = "break-words [overflow-wrap:anywhere]";

/** Structural equality for the plain JSON form payload; key order does not matter. */
function sameValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (
    typeof left !== "object" ||
    typeof right !== "object" ||
    left === null ||
    right === null
  ) {
    return false;
  }
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord);
  if (leftKeys.length !== Object.keys(rightRecord).length) return false;
  return leftKeys.every(
    (key) =>
      Object.prototype.hasOwnProperty.call(rightRecord, key) &&
      sameValue(leftRecord[key], rightRecord[key]),
  );
}

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
  if (!multiline) {
    return (
      <Input
        disabled={disabled}
        label={label}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    );
  }
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
        {label}
      </span>
      <textarea
        className={`${fieldClass} min-h-24 py-2.5 leading-relaxed`}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

interface SyncedDraft {
  revision: number;
  formData: MedWatchFormData;
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
  // The server revision and values the form was last synced from.
  const [baseline, setBaseline] = useState<SyncedDraft>({
    revision: draft.revision,
    formData: draft.formData,
  });
  const [approvalNote, setApprovalNote] = useState("");
  const [attested, setAttested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const editable = draft.status === "draft";

  // Adjust state when the draft prop changes. A queue refresh replaces the draft object;
  // the form follows it only when it holds no unsaved edits (or already matches the
  // server, as after a successful save). Dirty edits keep their original baseline so a
  // save still sends that revision and a stale save surfaces the revision conflict.
  if (
    draft.revision !== baseline.revision ||
    draft.formData !== baseline.formData
  ) {
    if (
      !editable ||
      sameValue(form, baseline.formData) ||
      sameValue(form, draft.formData)
    ) {
      setBaseline({ revision: draft.revision, formData: draft.formData });
      setForm(draft.formData);
    } else if (draft.revision === baseline.revision) {
      setBaseline({ revision: draft.revision, formData: draft.formData });
    }
  }

  const unsaved = editable && !sameValue(form, baseline.formData);
  const fieldsDisabled = !editable || busy;

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
    <Card className="ma-enter min-w-0" padding="none">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-6 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">
              MedWatch-compatible draft
            </h2>
            {editable ? (
              <Badge variant="neutral">Needs approval</Badge>
            ) : (
              <ApprovalSeal pill>Approved for export</ApprovalSeal>
            )}
            <span aria-live="polite" className="inline-flex">
              {unsaved ? (
                <Badge variant="warning">Unsaved changes</Badge>
              ) : null}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            Revision <span className="font-mono">{baseline.revision}</span> ·
            Draft ID <span className="font-mono break-all">{draft.id}</span>
          </p>
        </div>
        <Badge variant="warning">Not submitted to FDA</Badge>
      </header>

      <div className="space-y-5 p-6">
        <div className="grid gap-5 lg:grid-cols-2">
          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Patient</legend>
            <TextField
              disabled={fieldsDisabled}
              label="Patient identifier"
              onChange={(value) =>
                setField("patient", "patient_identifier", value)
              }
              value={form.patient.patient_identifier}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Date of birth"
              onChange={(value) => setField("patient", "date_of_birth", value)}
              value={form.patient.date_of_birth}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Sex"
              onChange={(value) => setField("patient", "sex", value)}
              value={form.patient.sex}
            />
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Adverse event</legend>
            <TextField
              disabled={fieldsDisabled}
              label="Description"
              multiline
              onChange={(value) => setField("event", "description", value)}
              value={form.event.description}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Onset date or time"
              onChange={(value) =>
                setField("event", "onset_date_or_time", value)
              }
              value={form.event.onset_date_or_time}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Outcome (leave empty if unknown)"
              onChange={(value) => setField("event", "outcome", value)}
              value={form.event.outcome}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Seriousness (leave empty if unknown)"
              onChange={(value) => setField("event", "seriousness", value)}
              value={form.event.seriousness}
            />
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Suspect product</legend>
            <TextField
              disabled={fieldsDisabled}
              label="Product name"
              onChange={(value) => setField("suspect_product", "name", value)}
              value={form.suspect_product.name}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                disabled={fieldsDisabled}
                label="Dose"
                onChange={(value) => setField("suspect_product", "dose", value)}
                value={form.suspect_product.dose}
              />
              <TextField
                disabled={fieldsDisabled}
                label="Frequency"
                onChange={(value) =>
                  setField("suspect_product", "frequency", value)
                }
                value={form.suspect_product.frequency}
              />
              <TextField
                disabled={fieldsDisabled}
                label="Route"
                onChange={(value) =>
                  setField("suspect_product", "route", value)
                }
                value={form.suspect_product.route}
              />
              <TextField
                disabled={fieldsDisabled}
                label="Therapy start"
                onChange={(value) =>
                  setField("suspect_product", "therapy_start_date", value)
                }
                value={form.suspect_product.therapy_start_date}
              />
              <TextField
                disabled={fieldsDisabled}
                label="Therapy end"
                onChange={(value) =>
                  setField("suspect_product", "therapy_end_date", value)
                }
                value={form.suspect_product.therapy_end_date}
              />
            </div>
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Other clinical details</legend>
            <TextField
              disabled={fieldsDisabled}
              label="Concomitant products"
              multiline
              onChange={(value) =>
                setField("concomitant_products", "products", value)
              }
              value={form.concomitant_products.products}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Relevant tests"
              multiline
              onChange={(value) =>
                setField("tests_and_history", "relevant_tests", value)
              }
              value={form.tests_and_history.relevant_tests}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Other relevant history"
              multiline
              onChange={(value) =>
                setField("tests_and_history", "other_relevant_history", value)
              }
              value={form.tests_and_history.other_relevant_history}
            />
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Reporter</legend>
            <TextField
              disabled={fieldsDisabled}
              label="Name"
              onChange={(value) => setField("reporter", "name", value)}
              value={form.reporter.name}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Email"
              onChange={(value) => setField("reporter", "email", value)}
              value={form.reporter.email}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Specialty"
              onChange={(value) => setField("reporter", "specialty", value)}
              value={form.reporter.specialty}
            />
            <TextField
              disabled={fieldsDisabled}
              label="Clinic"
              onChange={(value) => setField("reporter", "clinic_name", value)}
              value={form.reporter.clinic_name}
            />
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Clinical review</legend>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-line bg-surface-2 px-3.5 py-3 text-sm text-ink-2">
              <span>
                Deterministic Naranjo score:{" "}
                <strong className="font-mono font-medium text-ink">
                  {form.clinical_review.naranjo_score}
                </strong>
              </span>
              <Badge variant="warning">{form.clinical_review.causality}</Badge>
            </div>
            <TextField
              disabled={fieldsDisabled}
              label="Reportability rationale"
              multiline
              onChange={(value) =>
                setField("clinical_review", "reportability_rationale", value)
              }
              value={form.clinical_review.reportability_rationale}
            />
          </fieldset>
        </div>

        <details className="ma-disclosure rounded-xl border border-line bg-surface">
          <summary className="min-h-10 px-4 py-2 text-[13px] font-semibold text-ink">
            Source evidence and attribution (
            <span className="font-mono">{draft.sourceEvidence.length}</span>)
          </summary>
          <ul className="divide-y divide-line border-t border-line">
            {draft.sourceEvidence.map((source, index) => (
              <li
                className="min-w-0 space-y-1.5 px-4 py-3 text-sm"
                key={`${source.source_type}-${index}`}
              >
                <p className={`font-medium text-ink ${wrapClass}`}>
                  {source.attribution}
                </p>
                <p className={`text-xs text-muted ${wrapClass}`}>
                  {source.field_paths.join(", ")}
                </p>
                {source.excerpt ? (
                  <blockquote
                    className={`max-w-[72ch] border-l-2 border-line-strong pl-3 leading-relaxed text-ink-2 ${wrapClass}`}
                  >
                    “{source.excerpt}”
                  </blockquote>
                ) : null}
                {source.citation ? (
                  <p className={`text-xs text-primary ${wrapClass}`}>
                    Source: {source.citation}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </details>

        {error ? (
          <p
            className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
            role="alert"
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
            <span>{error}</span>
          </p>
        ) : null}
      </div>

      {editable ? (
        <div className="space-y-4 border-t border-line px-6 py-5">
          <Button
            disabled={busy}
            onClick={() =>
              void perform(() => onSave(draft.id, form, baseline.revision))
            }
            variant="secondary"
          >
            Save draft
          </Button>
          <section className="space-y-3 rounded-xl border border-ok-line bg-ok-soft p-4">
            <h3 className="text-sm font-semibold text-ink">
              Clinician approval
            </h3>
            <TextField
              disabled={busy}
              label="Approval note"
              multiline
              onChange={setApprovalNote}
              value={approvalNote}
            />
            <label className="flex min-h-8 cursor-pointer items-start gap-3 rounded-lg border border-ok-line bg-surface p-3 text-[13px] leading-relaxed text-ink-2 has-[:disabled]:cursor-not-allowed has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary">
              <input
                checked={attested}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-ok)]"
                disabled={busy}
                onChange={(event) => setAttested(event.target.checked)}
                type="checkbox"
              />
              <span>
                I reviewed the draft and its source evidence. I understand
                approval makes it exportable but does not submit it to the FDA.
              </span>
            </label>
            <Button
              disabled={busy || !attested || !approvalNote.trim()}
              onClick={() =>
                void perform(() =>
                  onApprove(draft.id, approvalNote.trim(), baseline.revision),
                )
              }
              variant="approve"
            >
              Approve for export
            </Button>
          </section>
        </div>
      ) : (
        <div className="flex flex-col justify-between gap-3 border-t border-line px-6 py-4 md:flex-row md:items-center">
          <p className="max-w-[80ch] text-sm text-ink-2">
            Approved
            {draft.approvedAt ? (
              <>
                {" "}
                <time className="font-mono" dateTime={draft.approvedAt}>
                  {formatReviewTimestamp(draft.approvedAt)}
                </time>
              </>
            ) : null}
            . Exporting records an audit event; it does not submit the draft.
          </p>
          <Button
            className="shrink-0"
            disabled={busy}
            onClick={() => void perform(() => onExport(draft.id))}
          >
            <Icon className="h-4 w-4" name="download" />
            Export approved JSON
          </Button>
        </div>
      )}
    </Card>
  );
}
