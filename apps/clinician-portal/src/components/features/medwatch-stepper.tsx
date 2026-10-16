import { Icon } from "@/components/ui/icons";

export type ReportStep = "complete" | "preview" | "approve" | "download";

export const REPORT_STEPS: { value: ReportStep; label: string }[] = [
    { value: "complete", label: "Complete" },
    { value: "preview", label: "Preview" },
    { value: "approve", label: "Approve" },
    { value: "download", label: "Download" },
];

export function MedWatchStepper({
    step,
    onSelect,
    disabled = false,
}: {
    step: ReportStep;
    onSelect: (step: ReportStep) => void;
    disabled?: boolean;
}) {
    const current = REPORT_STEPS.findIndex((candidate) => candidate.value === step);
    return (
        <nav aria-label="Report steps">
            {/* Narrow screens: a one-line position, previous/next controls and a progress bar. */}
            <div className="md:hidden">
                <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">
                        Step {current + 1} of {REPORT_STEPS.length}
                        <span aria-hidden="true"> · </span>
                        {REPORT_STEPS[current].label}
                    </p>
                    <div className="flex shrink-0 gap-1">
                        {current > 0 ? (
                            <button
                                className="ma-press rounded-lg border border-line-strong px-2.5 py-1 text-xs font-medium text-ink-2 outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-60"
                                disabled={disabled}
                                aria-label={`Previous step: ${REPORT_STEPS[current - 1].label}`}
                                onClick={() => onSelect(REPORT_STEPS[current - 1].value)}
                                type="button"
                            >
                                <span aria-hidden="true">‹ </span>
                                {REPORT_STEPS[current - 1].label}
                            </button>
                        ) : null}
                        {current < REPORT_STEPS.length - 1 ? (
                            <button
                                className="ma-press rounded-lg border border-line-strong px-2.5 py-1 text-xs font-medium text-ink-2 outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-60"
                                disabled={disabled}
                                aria-label={`Next step: ${REPORT_STEPS[current + 1].label}`}
                                onClick={() => onSelect(REPORT_STEPS[current + 1].value)}
                                type="button"
                            >
                                {REPORT_STEPS[current + 1].label}
                                <span aria-hidden="true"> ›</span>
                            </button>
                        ) : null}
                    </div>
                </div>
                <div aria-hidden="true" className="mt-2 flex gap-1">
                    {REPORT_STEPS.map((candidate, index) => (
                        <span
                            className={`h-1 flex-1 rounded-full ${index <= current ? "bg-primary" : "bg-track"}`}
                            key={candidate.value}
                        />
                    ))}
                </div>
            </div>
            <ol className="hidden items-center gap-2 md:flex">
                {REPORT_STEPS.map((candidate, index) => {
                    const done = index < current;
                    const active = index === current;
                    return (
                        <li className="flex min-w-0 flex-1 items-center gap-2" key={candidate.value}>
                            <button
                                aria-current={active ? "step" : undefined}
                                className={`ma-press flex min-w-0 items-center gap-2.5 rounded-lg px-1.5 py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed ${
                                    active ? "text-ink" : "text-muted hover:text-ink"
                                }`}
                                disabled={disabled}
                                onClick={() => onSelect(candidate.value)}
                                type="button"
                            >
                                <span
                                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                                        active
                                            ? "bg-primary text-white"
                                            : done
                                              ? "bg-ok-tint text-ok-ink"
                                              : "border border-line-strong text-muted"
                                    }`}
                                >
                                    {done ? <Icon aria-hidden="true" className="h-3.5 w-3.5" name="check" /> : index + 1}
                                </span>
                                <span className={`truncate text-[13px] ${active ? "font-semibold" : "font-medium"}`}>
                                    {candidate.label}
                                    {done ? <span className="sr-only"> (done)</span> : null}
                                </span>
                            </button>
                            {index < REPORT_STEPS.length - 1 ? (
                                <span aria-hidden="true" className="h-px flex-1 bg-line-strong" />
                            ) : null}
                        </li>
                    );
                })}
            </ol>
        </nav>
    );
}
