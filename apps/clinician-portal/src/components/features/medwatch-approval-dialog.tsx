"use client";

import { useRef, useState } from "react";
import { Button, Modal } from "@/components/ui";
import { fieldClass } from "@/components/ui/input";
import { Icon } from "@/components/ui/icons";
import type { MedWatchApprovalInput, MedWatchDraft } from "@/services/clinicians";
import {
    fieldPathLabel,
    gateIssueLabel,
    isAttestationIssue,
    nameWarningLabel,
} from "@/services/medwatch-form-3500";

const wrapClass = "break-words [overflow-wrap:anywhere]";
const checkLabelClass =
    "flex min-h-8 cursor-pointer items-start gap-3 rounded-lg border p-3 text-[13px] leading-relaxed text-ink-2 has-[:disabled]:cursor-not-allowed has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary";
const checkboxClass = "mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-ok)]";

export function MedWatchApprovalDialog({
    draft,
    open,
    unsaved,
    onClose,
    onApprove,
}: {
    draft: MedWatchDraft;
    open: boolean;
    /** True while the card holds edits that are not saved; approval uses the stored revision. */
    unsaved: boolean;
    onClose: () => void;
    onApprove: (draftId: string, input: MedWatchApprovalInput) => Promise<void>;
}) {
    const [note, setNote] = useState("");
    const [attested, setAttested] = useState(false);
    const [nonSerious, setNonSerious] = useState(false);
    const [warningsAcknowledged, setWarningsAcknowledged] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const pending = useRef(false);

    const blocking = draft.missingForApproval.filter((issue) => !isAttestationIssue(issue));
    const needsNonSerious =
        draft.formData.section_b.outcomes.length === 0 ||
        draft.missingForApproval.some(isAttestationIssue);
    const warnings = draft.nameWarnings;
    const attestation = draft.attestation;
    const ready =
        !unsaved &&
        blocking.length === 0 &&
        attestation !== null &&
        attested &&
        note.trim().length > 0 &&
        (!needsNonSerious || nonSerious) &&
        (warnings.length === 0 || warningsAcknowledged);

    async function submit() {
        if (!ready || !attestation || pending.current) return;
        pending.current = true;
        setSubmitting(true);
        setError(null);
        try {
            await onApprove(draft.id, {
                approvalNote: note.trim(),
                expectedRevision: draft.revision,
                attestationVersion: attestation.version,
                nonSeriousAttested: needsNonSerious && nonSerious,
                acknowledgedWarnings: warnings,
            });
            onClose();
        } catch (failure) {
            setError(
                failure instanceof Error && failure.message
                    ? failure.message
                    : "Unable to approve the draft. Try again.",
            );
        } finally {
            pending.current = false;
            setSubmitting(false);
        }
    }

    return (
        <Modal onClose={onClose} open={open} title="Approve Form 3500 draft">
            <div className="space-y-4 text-sm text-ink-2">
                <p className="leading-relaxed">
                    Approval is checked against the last saved revision (
                    <span className="font-mono">{draft.revision}</span>). It makes the draft
                    exportable; it does not submit anything to FDA.
                </p>

                {unsaved ? (
                    <p
                        className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-warn-ink"
                        role="note"
                    >
                        <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                        Save your changes before approving.
                    </p>
                ) : null}

                {blocking.length > 0 ? (
                    <section
                        aria-label="Missing for approval"
                        className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-warn-ink"
                    >
                        <p className="font-semibold">
                            Complete these items and save the draft before approving:
                        </p>
                        <ul className="mt-2 list-disc space-y-1 pl-6">
                            {blocking.map((issue) => (
                                <li className={wrapClass} key={`${issue.path}-${issue.code}`}>
                                    {gateIssueLabel(issue)}
                                </li>
                            ))}
                        </ul>
                    </section>
                ) : null}

                {warnings.length > 0 ? (
                    <section
                        aria-label="Name warnings"
                        className="space-y-2 rounded-xl border border-warn-line bg-surface px-4 py-3"
                    >
                        <p className="font-semibold text-ink">
                            FDA asks that a report identify no patient, physician or institution by
                            name. These fields may contain a name:
                        </p>
                        <ul className="list-disc space-y-1 pl-6">
                            {warnings.map((warning) => (
                                <li className={wrapClass} key={`${warning.path}-${warning.kind}`}>
                                    {fieldPathLabel(warning.path)}: {nameWarningLabel(warning)}
                                </li>
                            ))}
                        </ul>
                        <label className={`${checkLabelClass} border-warn-line`}>
                            <input
                                checked={warningsAcknowledged}
                                className={checkboxClass}
                                disabled={submitting}
                                onChange={(event) => setWarningsAcknowledged(event.target.checked)}
                                type="checkbox"
                            />
                            <span>I reviewed these name warnings and approve the text as written.</span>
                        </label>
                    </section>
                ) : null}

                {needsNonSerious ? (
                    <label className={`${checkLabelClass} border-line`}>
                        <input
                            checked={nonSerious}
                            className={checkboxClass}
                            disabled={submitting}
                            onChange={(event) => setNonSerious(event.target.checked)}
                            type="checkbox"
                        />
                        <span>
                            No B2 outcome is checked. I attest that this event is not serious and I
                            am reporting it anyway.
                        </span>
                    </label>
                ) : null}

                <label className="block">
                    <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
                        Approval note
                    </span>
                    <textarea
                        className={`${fieldClass} min-h-20 py-2.5 leading-relaxed`}
                        disabled={submitting}
                        maxLength={2000}
                        onChange={(event) => setNote(event.target.value)}
                        value={note}
                    />
                </label>

                {attestation ? (
                    <label className={`${checkLabelClass} border-ok-line bg-ok-soft`}>
                        <input
                            checked={attested}
                            className={checkboxClass}
                            disabled={submitting}
                            onChange={(event) => setAttested(event.target.checked)}
                            type="checkbox"
                        />
                        <span>{attestation.text}</span>
                    </label>
                ) : (
                    <p
                        className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-risk-ink"
                        role="alert"
                    >
                        <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                        The approval attestation could not be loaded. Refresh the queue before
                        approving.
                    </p>
                )}

                {error ? (
                    <p
                        className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-risk-ink"
                        role="alert"
                    >
                        <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                        <span>{error}</span>
                    </p>
                ) : null}

                <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
                    <Button disabled={submitting} onClick={onClose} variant="secondary">
                        Cancel
                    </Button>
                    <Button disabled={!ready || submitting} onClick={() => void submit()} variant="approve">
                        <Icon className="h-4 w-4" name="check" />
                        Confirm approval
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
