"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Button, Input, Modal } from "@/components/ui";
import { fieldClass } from "@/components/ui/input";
import { Icon } from "@/components/ui/icons";
import {
    clinicTodayIso,
    SUBMISSION_METHOD_LABELS,
    type MedWatchDiscardInput,
    type MedWatchDraft,
    type MedWatchSubmissionInput,
    type MedWatchSubmissionMethod,
} from "@/services/clinicians";

const MAX_REASON = 2000;
const checkLabelClass =
    "flex min-h-8 cursor-pointer items-start gap-3 rounded-lg border border-line p-3 text-[13px] leading-relaxed text-ink-2 has-[:disabled]:cursor-not-allowed has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary";

function InlineAlert({ children }: { children: ReactNode }) {
    return (
        <p
            className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
            role="alert"
        >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
            <span>{children}</span>
        </p>
    );
}

function TextArea({
    label,
    value,
    disabled,
    onChange,
    hint,
}: {
    label: string;
    value: string;
    disabled: boolean;
    onChange: (value: string) => void;
    hint?: string;
}) {
    const hintId = useId();
    return (
        <div>
            <label className="block">
                <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
                <textarea
                    aria-describedby={hint ? hintId : undefined}
                    className={`${fieldClass} min-h-20 py-2.5 leading-relaxed`}
                    disabled={disabled}
                    maxLength={MAX_REASON}
                    onChange={(event) => onChange(event.target.value)}
                    value={value}
                />
            </label>
            {hint ? (
                <p className="mt-1.5 text-xs text-muted" id={hintId}>
                    {hint}
                </p>
            ) : null}
        </div>
    );
}

function errorText(failure: unknown, fallback: string): string {
    return failure instanceof Error && failure.message ? failure.message : fallback;
}

/** The approval date (clinic calendar day) a submission date may not precede. */
function approvalDay(draft: MedWatchDraft): string | null {
    return draft.approvedAt ? clinicTodayIso(new Date(draft.approvedAt)) : null;
}

/**
 * Record, or amend, the clinician's own submission of the approved report to FDA. Nothing is
 * sent to FDA by MediAgent; this only stores what the clinician did outside it.
 */
export function SubmissionRecordDialog({
    draft,
    open,
    onClose,
    onRecord,
    onAmend,
}: {
    draft: MedWatchDraft;
    open: boolean;
    onClose: () => void;
    onRecord?: (
        draftId: string,
        input: MedWatchSubmissionInput & { expectedRevision: number },
    ) => Promise<void>;
    onAmend?: (
        draftId: string,
        input: MedWatchSubmissionInput & { amendsId: string; reason: string },
    ) => Promise<void>;
}) {
    const current = draft.currentSubmission;
    const amending = current !== null;
    const today = clinicTodayIso();
    const earliest = approvalDay(draft);
    const [submittedOn, setSubmittedOn] = useState(current?.submittedOn ?? "");
    const [method, setMethod] = useState<MedWatchSubmissionMethod | "">(current?.method ?? "");
    const [methodDetail, setMethodDetail] = useState(current?.methodDetail ?? "");
    const [fdaReference, setFdaReference] = useState(current?.fdaReference ?? "");
    const [attested, setAttested] = useState(false);
    const [reason, setReason] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const pending = useRef(false);

    const dateProblem = !submittedOn
        ? null
        : submittedOn > today
          ? "The submission date cannot be in the future."
          : earliest && submittedOn < earliest
            ? "The submission date cannot be before the draft was approved."
            : null;
    const ready =
        Boolean(submittedOn) &&
        !dateProblem &&
        method !== "" &&
        (method !== "other" || methodDetail.trim().length > 0) &&
        (amending ? reason.trim().length > 0 : attested);

    async function submit() {
        if (!ready || pending.current) return;
        pending.current = true;
        setSubmitting(true);
        setError(null);
        const values: MedWatchSubmissionInput = { submittedOn, method, methodDetail, fdaReference };
        try {
            if (amending && current) {
                await onAmend?.(draft.id, { ...values, amendsId: current.id, reason });
            } else {
                await onRecord?.(draft.id, { ...values, expectedRevision: draft.revision });
            }
            onClose();
        } catch (failure) {
            setError(errorText(failure, "Unable to save the submission record. Try again."));
        } finally {
            pending.current = false;
            setSubmitting(false);
        }
    }

    return (
        <Modal
            onClose={onClose}
            open={open}
            title={amending ? "Amend submission record" : "Record FDA submission"}
        >
            <div className="space-y-4 text-sm text-ink-2">
                <p className="leading-relaxed">
                    {amending
                        ? "Correct the date, method or reference. The original record is kept and the amendment is audited."
                        : "Record a submission you made to FDA yourself. MediAgent does not submit reports to FDA, and recording sends nothing to FDA. The draft becomes read-only."}
                </p>
                <Input
                    disabled={submitting}
                    label="Date submitted to FDA"
                    max={today}
                    min={earliest ?? undefined}
                    onChange={(event) => setSubmittedOn(event.target.value)}
                    type="date"
                    value={submittedOn}
                    error={dateProblem ?? undefined}
                />
                <label className="block">
                    <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
                        Submission method
                    </span>
                    <select
                        className={`${fieldClass} h-[42px]`}
                        disabled={submitting}
                        onChange={(event) =>
                            setMethod(event.target.value as MedWatchSubmissionMethod | "")
                        }
                        value={method}
                    >
                        <option value="">Choose a method</option>
                        {(Object.keys(SUBMISSION_METHOD_LABELS) as MedWatchSubmissionMethod[]).map(
                            (value) => (
                                <option key={value} value={value}>
                                    {SUBMISSION_METHOD_LABELS[value]}
                                </option>
                            ),
                        )}
                    </select>
                </label>
                {method === "other" ? (
                    <Input
                        disabled={submitting}
                        label="Describe the method"
                        maxLength={200}
                        onChange={(event) => setMethodDetail(event.target.value)}
                        value={methodDetail}
                    />
                ) : null}
                <Input
                    disabled={submitting}
                    label="FDA confirmation or reference number (optional)"
                    maxLength={100}
                    onChange={(event) => setFdaReference(event.target.value)}
                    value={fdaReference}
                />
                {amending ? (
                    <TextArea
                        disabled={submitting}
                        hint="Required. Explain what was wrong in the original record."
                        label="Reason for amendment"
                        onChange={setReason}
                        value={reason}
                    />
                ) : (
                    <label className={checkLabelClass}>
                        <input
                            checked={attested}
                            className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-ok)]"
                            disabled={submitting}
                            onChange={(event) => setAttested(event.target.checked)}
                            type="checkbox"
                        />
                        <span>
                            I submitted this report to FDA myself, outside MediAgent. MediAgent did
                            not submit it.
                        </span>
                    </label>
                )}
                {error ? <InlineAlert>{error}</InlineAlert> : null}
                <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
                    <Button disabled={submitting} onClick={onClose} variant="secondary">
                        Cancel
                    </Button>
                    <Button disabled={!ready || submitting} onClick={() => void submit()}>
                        {amending ? "Save amendment" : "Record submission"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}

/** Discard a draft with a reason; its ADR assessment returns to review. */
export function DiscardDraftDialog({
    draft,
    open,
    onClose,
    onDiscard,
}: {
    draft: MedWatchDraft;
    open: boolean;
    onClose: () => void;
    onDiscard: (draftId: string, input: MedWatchDiscardInput) => Promise<void>;
}) {
    const [reason, setReason] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const pending = useRef(false);
    const ready = reason.trim().length > 0;

    async function submit() {
        if (!ready || pending.current) return;
        pending.current = true;
        setSubmitting(true);
        setError(null);
        try {
            await onDiscard(draft.id, {
                reason: reason.trim(),
                expectedRevision: draft.revision,
            });
            onClose();
        } catch (failure) {
            setError(errorText(failure, "Unable to discard the draft. Try again."));
        } finally {
            pending.current = false;
            setSubmitting(false);
        }
    }

    return (
        <Modal onClose={onClose} open={open} title="Discard MedWatch draft">
            <div className="space-y-4 text-sm text-ink-2">
                <p className="leading-relaxed">
                    The draft is kept read-only under Discarded, and its ADR assessment returns to
                    review so you can review it again or prepare a new draft.
                </p>
                <TextArea
                    disabled={submitting}
                    hint="Required, up to 2000 characters. Recorded in the audit trail."
                    label="Reason for discarding"
                    onChange={setReason}
                    value={reason}
                />
                {error ? <InlineAlert>{error}</InlineAlert> : null}
                <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
                    <Button disabled={submitting} onClick={onClose} variant="secondary">
                        Cancel
                    </Button>
                    <Button disabled={!ready || submitting} onClick={() => void submit()} variant="danger">
                        Discard draft
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
