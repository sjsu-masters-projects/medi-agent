"use client";

import { useRef, useState } from "react";
import { Button, Modal } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
    downloadForm3500Pdf,
    type Form3500PdfDownload,
    type Form3500TemplateInfo,
} from "@/services/clinicians";
import { formatClinicianDate } from "@/utils/dates";

export const NOT_SUBMITTED_NOTICE = "MediAgent did not submit this report. You submit it to FDA.";

/** Save a downloaded file locally under the given name. */
export function saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

export function TemplateSupersededNote({ template }: { template: Form3500TemplateInfo }) {
    if (!template.maySuperseded) return null;
    return (
        <p
            className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink"
            role="note"
        >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
            <span>
                This form revision ({template.revision}) passed its expiry date of{" "}
                <time className="font-mono" dateTime={template.expires}>
                    {formatClinicianDate(`${template.expires}T12:00:00`, { dateStyle: "medium" })}
                </time>
                . FDA may have published a newer revision; check before you submit.
            </span>
        </p>
    );
}

export function Form3500DownloadDialog({
    draftId,
    open,
    template,
    onClose,
    onDownloaded,
    download = downloadForm3500Pdf,
}: {
    draftId: string;
    open: boolean;
    template: Form3500TemplateInfo;
    onClose: () => void;
    onDownloaded?: (filename: string) => void;
    download?: (draftId: string) => Promise<Form3500PdfDownload>;
}) {
    const [error, setError] = useState<string | null>(null);
    const [downloading, setDownloading] = useState(false);
    const pending = useRef(false);

    async function confirm() {
        if (pending.current) return;
        pending.current = true;
        setDownloading(true);
        setError(null);
        try {
            const file = await download(draftId);
            saveBlob(file.blob, file.filename);
            onDownloaded?.(file.filename);
            onClose();
        } catch (failure) {
            setError(
                failure instanceof Error && failure.message
                    ? failure.message
                    : "The Form 3500 PDF could not be downloaded. Try again.",
            );
        } finally {
            pending.current = false;
            setDownloading(false);
        }
    }

    return (
        <Modal onClose={onClose} open={open} title="Download Form 3500 (PDF)">
            <div className="space-y-4 text-sm text-ink-2">
                <p className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 font-semibold text-warn-ink">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" name="info" />
                    {NOT_SUBMITTED_NOTICE}
                </p>
                <p className="leading-relaxed">
                    The file is the official fillable Form FDA 3500 (revision{" "}
                    <span className="font-mono">{template.revision}</span>) filled from the approved
                    report. Review it, complete Section C or E in the PDF if they apply, and submit
                    it to FDA yourself. Each download is recorded in the audit trail.
                </p>
                <TemplateSupersededNote template={template} />
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
                    <Button disabled={downloading} onClick={onClose} variant="secondary">
                        Cancel
                    </Button>
                    <Button disabled={downloading} onClick={() => void confirm()}>
                        <Icon className="h-4 w-4" name="download" />
                        {downloading ? "Downloading…" : "Download PDF"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
