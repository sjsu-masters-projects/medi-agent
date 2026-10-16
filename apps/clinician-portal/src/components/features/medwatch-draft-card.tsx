"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Badge, Button, Card, Input } from "@/components/ui";
import { fieldClass } from "@/components/ui/input";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import { formatReviewTimestamp } from "@/components/features/review-time";
import { Form3500PreviewDialog } from "@/components/features/form-3500-preview";
import {
    Form3500DownloadDialog,
    TemplateSupersededNote,
} from "@/components/features/form-3500-download-dialog";
import { MedWatchApprovalDialog } from "@/components/features/medwatch-approval-dialog";
import {
    DiscardDraftDialog,
    SubmissionRecordDialog,
} from "@/components/features/medwatch-record-dialogs";
import {
    MedWatchRequestError,
    SUBMISSION_METHOD_LABELS,
    type Form3500PdfDownload,
    type MedWatchApprovalInput,
    type MedWatchDiscardInput,
    type MedWatchDraft,
    type MedWatchFormData,
    type MedWatchSubmissionInput,
    type MedWatchSubmissionRecord,
} from "@/services/clinicians";
import {
    FORM_3500_OPTIONS,
    MAX_OTHER_PRODUCTS,
    MAX_TEST_ROWS,
    blankOtherProduct,
    blankProduct,
    blankTestRow,
    gateIssueLabel,
    nameWarningLabel,
    type Form3500Product,
    type MedWatchNameWarning,
    type Option,
} from "@/services/medwatch-form-3500";
import { formatClinicianDate } from "@/utils/dates";

const fieldsetClass = "min-w-0 space-y-3 rounded-xl border border-line p-4";
const legendClass = "px-1 text-[13px] font-semibold text-ink";
const labelTextClass = "mb-1.5 block text-[13px] font-medium text-ink-2";
const wrapClass = "break-words [overflow-wrap:anywhere]";
const checkLabelClass =
    "flex min-h-8 cursor-pointer items-start gap-2.5 rounded-lg px-1 py-1 text-[13px] leading-snug text-ink-2 has-[:disabled]:cursor-not-allowed has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary";
const checkboxClass = "mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-primary)]";
const DATE_HINT = "YYYY-MM-DD, or YYYY-MM for month and year";

/** Structural equality for the plain JSON form payload; key order does not matter. */
function sameValue(left: unknown, right: unknown): boolean {
    if (Object.is(left, right)) return true;
    if (typeof left !== "object" || typeof right !== "object" || left === null || right === null) {
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

function calendarDate(value: string): string {
    return formatClinicianDate(`${value}T12:00:00`, { dateStyle: "medium" });
}

// ── Field primitives (shared `fieldClass` / `Input`) ─────────────────────────────

function NameWarnings({ id, warnings }: { id: string; warnings: MedWatchNameWarning[] }) {
    if (warnings.length === 0) return null;
    return (
        <span className="mt-1.5 flex flex-wrap gap-1.5" id={id}>
            {warnings.map((warning) => (
                <Badge key={`${warning.path}-${warning.kind}`} variant="warning">
                    <Icon className="h-3 w-3" name="alert" />
                    {nameWarningLabel(warning)}
                </Badge>
            ))}
        </span>
    );
}

function TextField({
    label,
    value,
    disabled,
    multiline = false,
    warnings = [],
    hint,
    maxLength,
    onChange,
}: {
    label: string;
    value: string;
    disabled: boolean;
    multiline?: boolean;
    warnings?: MedWatchNameWarning[];
    hint?: string;
    maxLength?: number;
    onChange: (value: string) => void;
}) {
    const warningId = useId();
    const describedBy = warnings.length > 0 ? warningId : undefined;
    return (
        <div className="min-w-0">
            <label className="block">
                <span className={labelTextClass}>{label}</span>
                {multiline ? (
                    <textarea
                        aria-describedby={describedBy}
                        className={`${fieldClass} min-h-24 py-2.5 leading-relaxed`}
                        disabled={disabled}
                        maxLength={maxLength}
                        onChange={(event) => onChange(event.target.value)}
                        value={value}
                    />
                ) : (
                    <input
                        aria-describedby={describedBy}
                        className={`${fieldClass} h-[42px]`}
                        disabled={disabled}
                        maxLength={maxLength}
                        onChange={(event) => onChange(event.target.value)}
                        placeholder={hint}
                        value={value}
                    />
                )}
            </label>
            <NameWarnings id={warningId} warnings={warnings} />
        </div>
    );
}

function DateField({
    label,
    value,
    disabled,
    onChange,
}: {
    label: string;
    value: string | null;
    disabled: boolean;
    onChange: (value: string | null) => void;
}) {
    return (
        <Input
            disabled={disabled}
            inputMode="numeric"
            label={label}
            maxLength={10}
            onChange={(event) => onChange(event.target.value.trim() ? event.target.value.trim() : null)}
            placeholder={DATE_HINT}
            title={DATE_HINT}
            value={value ?? ""}
        />
    );
}

function SelectField<T extends string>({
    label,
    value,
    options,
    disabled,
    onChange,
}: {
    label: string;
    value: T | null;
    options: readonly Option<T>[];
    disabled: boolean;
    onChange: (value: T | null) => void;
}) {
    return (
        <label className="block min-w-0">
            <span className={labelTextClass}>{label}</span>
            <select
                className={`${fieldClass} h-[42px]`}
                disabled={disabled}
                onChange={(event) => onChange(event.target.value ? (event.target.value as T) : null)}
                value={value ?? ""}
            >
                <option value="">Not provided</option>
                {options.map((option) => (
                    <option key={option.value} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
        </label>
    );
}

function CheckboxGroup<T extends string>({
    legend,
    values,
    options,
    disabled,
    onChange,
}: {
    legend: string;
    values: T[];
    options: readonly Option<T>[];
    disabled: boolean;
    onChange: (values: T[]) => void;
}) {
    return (
        <fieldset className="min-w-0">
            <legend className={labelTextClass}>{legend}</legend>
            <div className="grid gap-0.5 sm:grid-cols-2">
                {options.map((option) => (
                    <label className={checkLabelClass} key={option.value}>
                        <input
                            checked={values.includes(option.value)}
                            className={checkboxClass}
                            disabled={disabled}
                            onChange={(event) =>
                                onChange(
                                    event.target.checked
                                        ? [...values, option.value]
                                        : values.filter((value) => value !== option.value),
                                )
                            }
                            type="checkbox"
                        />
                        <span className={wrapClass}>{option.label}</span>
                    </label>
                ))}
            </div>
        </fieldset>
    );
}

function Checkbox({
    label,
    checked,
    disabled,
    onChange,
}: {
    label: ReactNode;
    checked: boolean;
    disabled: boolean;
    onChange: (checked: boolean) => void;
}) {
    return (
        <label className={checkLabelClass}>
            <input
                checked={checked}
                className={checkboxClass}
                disabled={disabled}
                onChange={(event) => onChange(event.target.checked)}
                type="checkbox"
            />
            <span>{label}</span>
        </label>
    );
}

function ProductFields({
    product,
    disabled,
    onChange,
}: {
    product: Form3500Product;
    disabled: boolean;
    onChange: (mutate: (product: Form3500Product) => void) => void;
}) {
    const set =
        <K extends keyof Form3500Product>(key: K) =>
        (value: Form3500Product[K]) =>
            onChange((next) => {
                next[key] = value;
            });
    return (
        <div className="space-y-3">
            <TextField disabled={disabled} label="Product name" maxLength={255} onChange={set("name")} value={product.name} />
            <div className="grid gap-3 sm:grid-cols-2">
                <TextField disabled={disabled} label="Strength" maxLength={50} onChange={set("strength")} value={product.strength} />
                <SelectField disabled={disabled} label="Strength unit" onChange={set("strength_unit")} options={FORM_3500_OPTIONS.doseUnit} value={product.strength_unit} />
                <TextField disabled={disabled} label="Dose or amount" maxLength={50} onChange={set("dose")} value={product.dose} />
                <SelectField disabled={disabled} label="Dose unit" onChange={set("dose_unit")} options={FORM_3500_OPTIONS.doseUnit} value={product.dose_unit} />
                <SelectField
                    disabled={disabled}
                    label="Frequency"
                    onChange={(value) =>
                        onChange((next) => {
                            next.frequency = value;
                            if (value !== "Other") next.frequency_other = "";
                        })
                    }
                    options={FORM_3500_OPTIONS.frequency}
                    value={product.frequency}
                />
                {product.frequency === "Other" ? (
                    <TextField disabled={disabled} label="Other frequency" maxLength={100} onChange={set("frequency_other")} value={product.frequency_other} />
                ) : null}
                <SelectField
                    disabled={disabled}
                    label="Route"
                    onChange={(value) =>
                        onChange((next) => {
                            next.route = value;
                            if (value !== "Other") next.route_other = "";
                        })
                    }
                    options={FORM_3500_OPTIONS.route}
                    value={product.route}
                />
                {product.route === "Other" ? (
                    <TextField disabled={disabled} label="Other route" maxLength={100} onChange={set("route_other")} value={product.route_other} />
                ) : null}
                <DateField disabled={disabled} label="Therapy started on" onChange={set("therapy_start")} value={product.therapy_start} />
                <DateField disabled={disabled} label="Therapy stopped on" onChange={set("therapy_stop")} value={product.therapy_stop} />
                <DateField disabled={disabled} label="Dose reduced on" onChange={set("therapy_reduced")} value={product.therapy_reduced} />
                <SelectField disabled={disabled} label="Therapy ongoing" onChange={set("ongoing")} options={FORM_3500_OPTIONS.yesNo} value={product.ongoing} />
                <TextField disabled={disabled} label="Duration" maxLength={5} onChange={set("duration")} value={product.duration} />
                <SelectField disabled={disabled} label="Duration unit" onChange={set("duration_unit")} options={FORM_3500_OPTIONS.durationUnit} value={product.duration_unit} />
                <TextField disabled={disabled} label="Manufacturer/compounder name" maxLength={255} onChange={set("manufacturer_compounder")} value={product.manufacturer_compounder} />
                <TextField disabled={disabled} label="NDC # or unique ID" maxLength={100} onChange={set("ndc_or_unique_id")} value={product.ndc_or_unique_id} />
                <TextField disabled={disabled} label="Lot #" maxLength={100} onChange={set("lot")} value={product.lot} />
                <DateField disabled={disabled} label="Expiration date" onChange={set("expiration_date")} value={product.expiration_date} />
            </div>
            <TextField disabled={disabled} label="Diagnosis for use (indication)" maxLength={500} onChange={set("diagnosis_for_use")} value={product.diagnosis_for_use} />
            <CheckboxGroup disabled={disabled} legend="Product type" onChange={set("product_types")} options={FORM_3500_OPTIONS.productType} values={product.product_types} />
            <div className="grid gap-3 sm:grid-cols-2">
                <SelectField disabled={disabled} label="Event abated after use stopped or dose reduced" onChange={set("abated")} options={FORM_3500_OPTIONS.yesNoNotApplicable} value={product.abated} />
                <SelectField disabled={disabled} label="Event reappeared after reintroduction" onChange={set("reappeared")} options={FORM_3500_OPTIONS.yesNoNotApplicable} value={product.reappeared} />
            </div>
        </div>
    );
}

function SubmissionLine({ record }: { record: MedWatchSubmissionRecord }) {
    const method =
        record.method === "other" && record.methodDetail
            ? `Other: ${record.methodDetail}`
            : SUBMISSION_METHOD_LABELS[record.method] ?? record.method;
    return (
        <>
            <time className="font-mono" dateTime={record.submittedOn}>
                {calendarDate(record.submittedOn)}
            </time>{" "}
            by {method}
            {record.fdaReference ? (
                <>
                    {" "}
                    · FDA reference <span className={`font-mono ${wrapClass}`}>{record.fdaReference}</span>
                </>
            ) : null}
        </>
    );
}

type DialogKind = "preview" | "approve" | "download" | "submission" | "discard";

export function MedWatchDraftCard({
    draft,
    busy,
    onSave,
    onApprove,
    onExport,
    onDiscard,
    onRecordSubmission,
    onAmendSubmission,
    onPdfDownloaded,
    downloadPdf,
}: {
    draft: MedWatchDraft;
    busy: boolean;
    onSave: (draftId: string, form: MedWatchFormData, revision: number) => Promise<void>;
    onApprove: (draftId: string, input: MedWatchApprovalInput) => Promise<void>;
    onExport: (draftId: string) => Promise<void>;
    onDiscard?: (draftId: string, input: MedWatchDiscardInput) => Promise<void>;
    onRecordSubmission?: (
        draftId: string,
        input: MedWatchSubmissionInput & { expectedRevision: number },
    ) => Promise<void>;
    onAmendSubmission?: (
        draftId: string,
        input: MedWatchSubmissionInput & { amendsId: string; reason: string },
    ) => Promise<void>;
    onPdfDownloaded?: (filename: string) => void;
    downloadPdf?: (draftId: string) => Promise<Form3500PdfDownload>;
}) {
    const [form, setForm] = useState(draft.formData);
    // The server revision and values the form was last synced from.
    const [baseline, setBaseline] = useState({ revision: draft.revision, formData: draft.formData });
    const [error, setError] = useState<string | null>(null);
    const [dialog, setDialog] = useState<DialogKind | null>(null);
    const pending = useRef(false);
    const discarded = draft.discardedAt !== null;
    const submitted = draft.status === "submitted";
    const approved = draft.status === "reviewed" && !discarded;
    const editable = draft.status === "draft" && !discarded;

    // Adjust state when the draft prop changes. A queue refresh replaces the draft object;
    // the form follows it only when it holds no unsaved edits (or already matches the
    // server, as after a successful save). Dirty edits keep their original baseline so a
    // save still sends that revision and a stale save surfaces the revision conflict.
    if (draft.revision !== baseline.revision || draft.formData !== baseline.formData) {
        if (!editable || sameValue(form, baseline.formData) || sameValue(form, draft.formData)) {
            setBaseline({ revision: draft.revision, formData: draft.formData });
            setForm(draft.formData);
        } else if (draft.revision === baseline.revision) {
            setBaseline({ revision: draft.revision, formData: draft.formData });
        }
    }

    const unsaved = editable && !sameValue(form, baseline.formData);
    const disabled = !editable || busy;
    const a = form.section_a;
    const b = form.section_b;
    const d = form.section_d;
    const g = form.section_g;

    function update(mutate: (next: MedWatchFormData) => void) {
        setForm((current) => {
            const next = structuredClone(current);
            mutate(next);
            return next;
        });
    }

    function warningsFor(path: string): MedWatchNameWarning[] {
        return draft.nameWarnings.filter((warning) => warning.path === path);
    }

    async function perform(operation: () => Promise<void>) {
        if (busy || pending.current) return;
        pending.current = true;
        setError(null);
        try {
            await operation();
        } catch (failure) {
            setError(
                failure instanceof MedWatchRequestError
                    ? `${failure.message} Your unsaved form values are retained.`
                    : "Unable to complete this action. Your unsaved form values are retained.",
            );
        } finally {
            pending.current = false;
        }
    }

    const statusBadge = discarded ? (
        <Badge variant="danger">Discarded</Badge>
    ) : submitted ? (
        <>
            <ApprovalSeal pill>Approved for export</ApprovalSeal>
            <Badge variant="info">Submitted outside MediAgent</Badge>
        </>
    ) : approved ? (
        <ApprovalSeal pill>Approved for export</ApprovalSeal>
    ) : (
        <Badge variant="neutral">Needs approval</Badge>
    );

    return (
        <Card className="ma-enter min-w-0" padding="none">
            <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-6 py-4">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">
                            MedWatch Form 3500 draft
                        </h2>
                        {statusBadge}
                        <span aria-live="polite" className="inline-flex">
                            {unsaved ? <Badge variant="warning">Unsaved changes</Badge> : null}
                        </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                        Revision <span className="font-mono">{baseline.revision}</span> · Draft ID{" "}
                        <span className="font-mono break-all">{draft.id}</span>
                    </p>
                </div>
                <Badge variant="warning">
                    {submitted ? "Not submitted to FDA by MediAgent" : "Not submitted to FDA"}
                </Badge>
            </header>

            <div className="space-y-5 p-6">
                {submitted && draft.currentSubmission ? (
                    <section
                        aria-label="FDA submission record"
                        className="space-y-2 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2"
                    >
                        <p className="font-medium text-ink">
                            Submitted by {draft.currentSubmission.recordedByName ?? "a care-team clinician"}{" "}
                            outside MediAgent on{" "}
                            <time className="font-mono" dateTime={draft.currentSubmission.submittedOn}>
                                {calendarDate(draft.currentSubmission.submittedOn)}
                            </time>
                            .
                        </p>
                        <p>
                            Current record: <SubmissionLine record={draft.currentSubmission} />
                        </p>
                        {draft.submissionHistory.length > 1 ? (
                            <details className="ma-disclosure rounded-lg border border-line bg-surface">
                                <summary className="px-3 text-[13px] font-semibold text-ink">
                                    Amendment history (
                                    <span className="font-mono">{draft.submissionHistory.length - 1}</span>)
                                </summary>
                                <ol className="divide-y divide-line border-t border-line">
                                    {draft.submissionHistory.map((record) => (
                                        <li className="space-y-1 px-3 py-2.5" key={record.id}>
                                            <p>
                                                <SubmissionLine record={record} />
                                                {record.amendsId ? null : (
                                                    <span className="text-muted"> · original record</span>
                                                )}
                                            </p>
                                            {record.amendReason ? (
                                                <p className={`text-xs text-muted ${wrapClass}`}>
                                                    Amendment reason: {record.amendReason}
                                                </p>
                                            ) : null}
                                            <p className="text-xs text-muted">
                                                Recorded{" "}
                                                <time className="font-mono" dateTime={record.createdAt}>
                                                    {formatReviewTimestamp(record.createdAt)}
                                                </time>
                                                {record.recordedByName ? ` by ${record.recordedByName}` : ""}
                                            </p>
                                        </li>
                                    ))}
                                </ol>
                            </details>
                        ) : null}
                    </section>
                ) : null}

                {discarded ? (
                    <section
                        aria-label="Discard record"
                        className="space-y-1 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2"
                    >
                        <p className="font-medium text-ink">
                            Discarded on{" "}
                            <time className="font-mono" dateTime={draft.discardedAt ?? undefined}>
                                {formatReviewTimestamp(draft.discardedAt ?? "")}
                            </time>
                            . The ADR assessment returned to review.
                        </p>
                        {draft.discardReason ? (
                            <p className={wrapClass}>Reason: {draft.discardReason}</p>
                        ) : null}
                    </section>
                ) : null}

                {editable && draft.missingForApproval.length > 0 ? (
                    <section
                        aria-label="Missing for approval"
                        className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink"
                    >
                        <p className="flex items-center gap-2 font-semibold">
                            <Icon className="h-4 w-4 shrink-0" name="alert" />
                            Missing for approval (
                            <span className="font-mono">{draft.missingForApproval.length}</span>)
                        </p>
                        <ul className="mt-2 list-disc space-y-1 pl-6">
                            {draft.missingForApproval.map((issue) => (
                                <li className={wrapClass} key={`${issue.path}-${issue.code}`}>
                                    {gateIssueLabel(issue)}
                                </li>
                            ))}
                        </ul>
                        <p className="mt-2 text-xs">Checked against the last saved revision.</p>
                    </section>
                ) : null}

                <div className="grid gap-5 xl:grid-cols-2">
                    <fieldset className={fieldsetClass}>
                        <legend className={legendClass}>A. Patient information</legend>
                        <TextField
                            disabled={disabled}
                            hint="Initials and a reference, never the patient's name"
                            label="A1 Patient identifier"
                            maxLength={50}
                            onChange={(value) => update((next) => { next.section_a.identifier = value; })}
                            value={a.identifier}
                        />
                        <div className="grid gap-3 sm:grid-cols-2">
                            <TextField disabled={disabled} label="A2 Age" maxLength={3} onChange={(value) => update((next) => { next.section_a.age_value = value; })} value={a.age_value} />
                            <SelectField disabled={disabled} label="A2 Age unit" onChange={(value) => update((next) => { next.section_a.age_unit = value; })} options={FORM_3500_OPTIONS.ageUnit} value={a.age_unit} />
                            <DateField disabled={disabled} label="A2 Date of birth" onChange={(value) => update((next) => { next.section_a.date_of_birth = value; })} value={a.date_of_birth} />
                            <SelectField disabled={disabled} label="A3 Sex" onChange={(value) => update((next) => { next.section_a.sex = value; })} options={FORM_3500_OPTIONS.sex} value={a.sex} />
                            <TextField disabled={disabled} label="A4 Weight" maxLength={5} onChange={(value) => update((next) => { next.section_a.weight_value = value; })} value={a.weight_value} />
                            <SelectField disabled={disabled} label="A4 Weight unit" onChange={(value) => update((next) => { next.section_a.weight_unit = value; })} options={FORM_3500_OPTIONS.weightUnit} value={a.weight_unit} />
                        </div>
                        <CheckboxGroup disabled={disabled} legend="A5 Race" onChange={(values) => update((next) => { next.section_a.race = values; })} options={FORM_3500_OPTIONS.race} values={a.race} />
                        <Checkbox checked={a.hispanic_latino} disabled={disabled} label="A5 Hispanic/Latino" onChange={(checked) => update((next) => { next.section_a.hispanic_latino = checked; })} />
                    </fieldset>

                    <fieldset className={fieldsetClass}>
                        <legend className={legendClass}>B. Adverse event or product problem</legend>
                        <CheckboxGroup disabled={disabled} legend="B1 Type of report" onChange={(values) => update((next) => { next.section_b.report_types = values; })} options={FORM_3500_OPTIONS.reportType} values={b.report_types} />
                        <CheckboxGroup
                            disabled={disabled}
                            legend="B2 Outcome (leave all unchecked if not serious)"
                            onChange={(values) =>
                                update((next) => {
                                    next.section_b.outcomes = values;
                                    if (!values.includes("death")) next.section_b.death_date = null;
                                })
                            }
                            options={FORM_3500_OPTIONS.outcome}
                            values={b.outcomes}
                        />
                        {b.outcomes.includes("death") ? (
                            <DateField disabled={disabled} label="B2 Date of death" onChange={(value) => update((next) => { next.section_b.death_date = value; })} value={b.death_date} />
                        ) : null}
                        <div className="grid gap-3 sm:grid-cols-2">
                            <div className="min-w-0">
                                <DateField disabled={disabled} label="B3 Date of event" onChange={(value) => update((next) => { next.section_b.event_date = value; })} value={b.event_date} />
                                {b.event_date && !b.event_date_confirmed ? (
                                    <span className="mt-1.5 inline-flex">
                                        <Badge variant="warning">Best estimate, confirm</Badge>
                                    </span>
                                ) : null}
                                <Checkbox checked={b.event_date_confirmed} disabled={disabled} label="I confirm the date of event" onChange={(checked) => update((next) => { next.section_b.event_date_confirmed = checked; })} />
                            </div>
                            <DateField disabled={disabled} label="B4 Date of this report" onChange={(value) => update((next) => { next.section_b.report_date = value; })} value={b.report_date} />
                        </div>
                        <TextField
                            disabled={disabled}
                            label="B5 Describe event, problem or product use/medication error"
                            maxLength={4000}
                            multiline
                            onChange={(value) => update((next) => { next.section_b.narrative = value; })}
                            value={b.narrative}
                            warnings={warningsFor("section_b.narrative")}
                        />
                        <fieldset className="min-w-0 space-y-3">
                            <legend className={labelTextClass}>B6 Relevant tests/laboratory data</legend>
                            {b.tests.length === 0 ? (
                                <p className="text-[13px] text-muted">No test rows. MediAgent does not prefill tests.</p>
                            ) : null}
                            {b.tests.map((row, index) => (
                                <div className="space-y-3 rounded-lg border border-line p-3" key={index}>
                                    <TextField disabled={disabled} label={`Test ${index + 1}: test and result`} maxLength={500} onChange={(value) => update((next) => { next.section_b.tests[index].test = value; })} value={row.test} warnings={warningsFor(`section_b.tests[${index}].test`)} />
                                    <div className="grid gap-3 sm:grid-cols-3">
                                        <TextField disabled={disabled} label={`Test ${index + 1}: low range`} maxLength={50} onChange={(value) => update((next) => { next.section_b.tests[index].low_range = value; })} value={row.low_range} warnings={warningsFor(`section_b.tests[${index}].low_range`)} />
                                        <TextField disabled={disabled} label={`Test ${index + 1}: high range`} maxLength={50} onChange={(value) => update((next) => { next.section_b.tests[index].high_range = value; })} value={row.high_range} warnings={warningsFor(`section_b.tests[${index}].high_range`)} />
                                        <DateField disabled={disabled} label={`Test ${index + 1}: date`} onChange={(value) => update((next) => { next.section_b.tests[index].date = value; })} value={row.date} />
                                    </div>
                                    {editable ? (
                                        <Button disabled={busy} onClick={() => update((next) => { next.section_b.tests.splice(index, 1); })} size="sm" variant="ghost">
                                            Remove test {index + 1}
                                        </Button>
                                    ) : null}
                                </div>
                            ))}
                            {editable && b.tests.length < MAX_TEST_ROWS ? (
                                <Button disabled={busy} onClick={() => update((next) => { next.section_b.tests.push(blankTestRow()); })} size="sm" variant="secondary">
                                    <Icon className="h-4 w-4" name="plus" />
                                    Add test row
                                </Button>
                            ) : null}
                        </fieldset>
                        <TextField disabled={disabled} label="B6 Additional comments on tests" maxLength={2000} multiline onChange={(value) => update((next) => { next.section_b.tests_comments = value; })} value={b.tests_comments} warnings={warningsFor("section_b.tests_comments")} />
                        <TextField disabled={disabled} label="B7 Other relevant history" maxLength={2000} multiline onChange={(value) => update((next) => { next.section_b.other_history = value; })} value={b.other_history} warnings={warningsFor("section_b.other_history")} />
                    </fieldset>

                    <fieldset className={fieldsetClass}>
                        <legend className={legendClass}>D. Suspect products</legend>
                        <fieldset className="min-w-0 space-y-3 rounded-lg border border-line p-3">
                            <legend className="px-1 text-[13px] font-medium text-ink">Suspect product 1</legend>
                            <ProductFields disabled={disabled} onChange={(mutate) => update((next) => mutate(next.section_d.product_1))} product={d.product_1} />
                        </fieldset>
                        {d.product_2 ? (
                            <fieldset className="min-w-0 space-y-3 rounded-lg border border-line p-3">
                                <legend className="px-1 text-[13px] font-medium text-ink">Suspect product 2</legend>
                                <ProductFields
                                    disabled={disabled}
                                    onChange={(mutate) =>
                                        update((next) => {
                                            if (next.section_d.product_2) mutate(next.section_d.product_2);
                                        })
                                    }
                                    product={d.product_2}
                                />
                                {editable ? (
                                    <Button disabled={busy} onClick={() => update((next) => { next.section_d.product_2 = null; })} size="sm" variant="ghost">
                                        Remove suspect product 2
                                    </Button>
                                ) : null}
                            </fieldset>
                        ) : editable ? (
                            <Button disabled={busy} onClick={() => update((next) => { next.section_d.product_2 = blankProduct(); })} size="sm" variant="secondary">
                                <Icon className="h-4 w-4" name="plus" />
                                Add suspect product 2
                            </Button>
                        ) : null}
                    </fieldset>

                    <div className="min-w-0 space-y-5">
                        <fieldset className={fieldsetClass}>
                            <legend className={legendClass}>F. Other (concomitant) medical products</legend>
                            {form.section_f.others.length === 0 ? (
                                <p className="text-[13px] text-muted">No other products listed.</p>
                            ) : null}
                            {form.section_f.others.map((other, index) => (
                                <div className="space-y-3 rounded-lg border border-line p-3" key={index}>
                                    <TextField disabled={disabled} label={`Other product ${index + 1}: name`} maxLength={255} onChange={(value) => update((next) => { next.section_f.others[index].name = value; })} value={other.name} warnings={warningsFor(`section_f.others[${index}].name`)} />
                                    <div className="grid gap-3 sm:grid-cols-2">
                                        <DateField disabled={disabled} label={`Other product ${index + 1}: start date`} onChange={(value) => update((next) => { next.section_f.others[index].start = value; })} value={other.start} />
                                        <DateField disabled={disabled} label={`Other product ${index + 1}: end date`} onChange={(value) => update((next) => { next.section_f.others[index].end = value; })} value={other.end} />
                                    </div>
                                    {editable ? (
                                        <Button disabled={busy} onClick={() => update((next) => { next.section_f.others.splice(index, 1); })} size="sm" variant="ghost">
                                            Remove other product {index + 1}
                                        </Button>
                                    ) : null}
                                </div>
                            ))}
                            {editable && form.section_f.others.length < MAX_OTHER_PRODUCTS ? (
                                <Button disabled={busy} onClick={() => update((next) => { next.section_f.others.push(blankOtherProduct()); })} size="sm" variant="secondary">
                                    <Icon className="h-4 w-4" name="plus" />
                                    Add other product
                                </Button>
                            ) : null}
                        </fieldset>

                        <fieldset className={fieldsetClass}>
                            <legend className={legendClass}>G. Reporter</legend>
                            <div className="grid gap-3 sm:grid-cols-2">
                                <TextField disabled={disabled} label="G1 First name" maxLength={100} onChange={(value) => update((next) => { next.section_g.first_name = value; })} value={g.first_name} />
                                <TextField disabled={disabled} label="G1 Last name" maxLength={100} onChange={(value) => update((next) => { next.section_g.last_name = value; })} value={g.last_name} />
                                <TextField disabled={disabled} label="G1 Address" maxLength={100} onChange={(value) => update((next) => { next.section_g.address = value; })} value={g.address} />
                                <TextField disabled={disabled} label="G1 City" maxLength={100} onChange={(value) => update((next) => { next.section_g.city = value; })} value={g.city} />
                                <TextField disabled={disabled} label="G1 State/province/region" maxLength={100} onChange={(value) => update((next) => { next.section_g.state = value; })} value={g.state} />
                                <TextField disabled={disabled} label="G1 ZIP/postal code" maxLength={10} onChange={(value) => update((next) => { next.section_g.zip_code = value; })} value={g.zip_code} />
                                <TextField disabled={disabled} hint="As listed on the form, for example UNITED STATES" label="G1 Country" maxLength={100} onChange={(value) => update((next) => { next.section_g.country = value; })} value={g.country} />
                                <TextField disabled={disabled} label="G1 Phone #" maxLength={30} onChange={(value) => update((next) => { next.section_g.phone = value; })} value={g.phone} />
                                <TextField disabled={disabled} label="G1 Email" maxLength={254} onChange={(value) => update((next) => { next.section_g.email = value; })} value={g.email} />
                                <SelectField disabled={disabled} label="G2 Health professional" onChange={(value) => update((next) => { next.section_g.health_professional = value; })} options={FORM_3500_OPTIONS.yesNo} value={g.health_professional} />
                                <SelectField disabled={disabled} label="G3 Occupation" onChange={(value) => update((next) => { next.section_g.occupation = value; })} options={FORM_3500_OPTIONS.occupation} value={g.occupation} />
                            </div>
                            <CheckboxGroup disabled={disabled} legend="G4 Also reported to" onChange={(values) => update((next) => { next.section_g.also_reported_to = values; })} options={FORM_3500_OPTIONS.alsoReportedTo} values={g.also_reported_to} />
                            <Checkbox checked={g.identity_withheld} disabled={disabled} label="G5 Do not disclose reporter identity to the manufacturer" onChange={(checked) => update((next) => { next.section_g.identity_withheld = checked; })} />
                        </fieldset>

                        <fieldset className={fieldsetClass}>
                            <legend className={legendClass}>MediAgent review (not part of Form 3500)</legend>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-line bg-surface-2 px-3.5 py-3 text-sm text-ink-2">
                                <span>
                                    Deterministic Naranjo score:{" "}
                                    <strong className="font-mono font-medium text-ink">
                                        {form.mediagent_review.naranjo_score ?? "—"}
                                    </strong>
                                </span>
                                {form.mediagent_review.causality ? (
                                    <Badge variant="warning">{form.mediagent_review.causality}</Badge>
                                ) : null}
                            </div>
                            <TextField disabled={disabled} label="Reportability rationale" maxLength={2000} multiline onChange={(value) => update((next) => { next.mediagent_review.reportability_rationale = value; })} value={form.mediagent_review.reportability_rationale} />
                        </fieldset>
                    </div>
                </div>

                {Object.keys(form.legacy).length > 0 ? (
                    <details className="ma-disclosure rounded-xl border border-line bg-surface">
                        <summary className="min-h-10 px-4 py-2 text-[13px] font-semibold text-ink">
                            Earlier draft text with no Form 3500 item (
                            <span className="font-mono">{Object.keys(form.legacy).length}</span>)
                        </summary>
                        <dl className="divide-y divide-line border-t border-line">
                            {Object.entries(form.legacy).map(([key, value]) => (
                                <div className="px-4 py-2.5 text-sm" key={key}>
                                    <dt className={`font-mono text-xs text-muted ${wrapClass}`}>{key}</dt>
                                    <dd className={`mt-1 text-ink-2 ${wrapClass}`}>{value}</dd>
                                </div>
                            ))}
                        </dl>
                    </details>
                ) : null}

                <details className="ma-disclosure rounded-xl border border-line bg-surface">
                    <summary className="min-h-10 px-4 py-2 text-[13px] font-semibold text-ink">
                        Source evidence and attribution (
                        <span className="font-mono">{draft.sourceEvidence.length}</span>)
                    </summary>
                    <ul className="divide-y divide-line border-t border-line">
                        {draft.sourceEvidence.map((source, index) => (
                            <li className="min-w-0 space-y-1.5 px-4 py-3 text-sm" key={`${source.source_type}-${index}`}>
                                <p className={`font-medium text-ink ${wrapClass}`}>{source.attribution}</p>
                                <p className={`text-xs text-muted ${wrapClass}`}>{source.field_paths.join(", ")}</p>
                                {source.excerpt ? (
                                    <blockquote className={`max-w-[72ch] border-l-2 border-line-strong pl-3 leading-relaxed text-ink-2 ${wrapClass}`}>
                                        “{source.excerpt}”
                                    </blockquote>
                                ) : null}
                                {source.citation ? (
                                    <p className={`text-xs text-primary ${wrapClass}`}>Source: {source.citation}</p>
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

            <div className="space-y-3 border-t border-line px-6 py-5">
                {approved || submitted ? (
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
                        . Downloading or exporting records an audit event; it does not submit the draft.
                    </p>
                ) : null}
                {(approved || submitted) && !draft.pdfAvailable ? (
                    <p
                        className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink"
                        role="note"
                    >
                        <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                        This earlier draft cannot be downloaded as Form 3500. The preview and JSON
                        export stay available; discard it and prepare a new draft to download the PDF.
                    </p>
                ) : null}
                {(approved || submitted) && draft.pdfAvailable ? (
                    <>
                        <TemplateSupersededNote template={draft.template} />
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                            <Button className="shrink-0" disabled={busy} onClick={() => setDialog("download")}>
                                <Icon className="h-4 w-4" name="download" />
                                Download Form 3500 (PDF)
                            </Button>
                            <span className="text-[13px] font-medium text-warn-ink">
                                MediAgent did not submit this report.
                            </span>
                        </div>
                    </>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                    {editable ? (
                        <>
                            <Button disabled={busy} onClick={() => void perform(() => onSave(draft.id, form, baseline.revision))} variant="secondary">
                                Save draft
                            </Button>
                            <Button disabled={busy} onClick={() => setDialog("approve")} variant="approve">
                                Approve for export
                            </Button>
                        </>
                    ) : null}
                    <Button disabled={busy} onClick={() => setDialog("preview")} variant="secondary">
                        <Icon className="h-4 w-4" name="eye" />
                        Preview Form 3500
                    </Button>
                    {approved || submitted ? (
                        <Button disabled={busy} onClick={() => void perform(() => onExport(draft.id))} variant="secondary">
                            <Icon className="h-4 w-4" name="download" />
                            Export approved JSON
                        </Button>
                    ) : null}
                    {approved && onRecordSubmission ? (
                        <Button disabled={busy} onClick={() => setDialog("submission")} variant="secondary">
                            Record FDA submission
                        </Button>
                    ) : null}
                    {submitted && draft.currentSubmission && onAmendSubmission ? (
                        <Button disabled={busy} onClick={() => setDialog("submission")} variant="secondary">
                            <Icon className="h-4 w-4" name="edit" />
                            Amend record
                        </Button>
                    ) : null}
                    {(editable || approved) && onDiscard ? (
                        <Button disabled={busy} onClick={() => setDialog("discard")} variant="danger">
                            Discard draft
                        </Button>
                    ) : null}
                </div>
            </div>

            {dialog === "preview" ? (
                <Form3500PreviewDialog draftId={draft.id} onClose={() => setDialog(null)} open />
            ) : null}
            {dialog === "approve" ? (
                <MedWatchApprovalDialog
                    draft={draft}
                    onApprove={onApprove}
                    onClose={() => setDialog(null)}
                    open
                    unsaved={unsaved}
                />
            ) : null}
            {dialog === "download" ? (
                <Form3500DownloadDialog
                    download={downloadPdf}
                    draftId={draft.id}
                    onClose={() => setDialog(null)}
                    onDownloaded={onPdfDownloaded}
                    open
                    template={draft.template}
                />
            ) : null}
            {dialog === "submission" ? (
                <SubmissionRecordDialog
                    draft={draft}
                    onAmend={onAmendSubmission}
                    onClose={() => setDialog(null)}
                    onRecord={onRecordSubmission}
                    open
                />
            ) : null}
            {dialog === "discard" && onDiscard ? (
                <DiscardDraftDialog draft={draft} onClose={() => setDialog(null)} onDiscard={onDiscard} open />
            ) : null}
        </Card>
    );
}
