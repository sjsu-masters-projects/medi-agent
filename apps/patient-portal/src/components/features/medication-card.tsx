import { Badge, Button, Card } from "@/components/ui";
import { getTodayCopy, getTaskStatusLabel } from "@/content/today-copy";
import type { Locale } from "@/types";
import type { TaskCardStatus } from "./task-card.types";

interface MedicationCardProps {
    locale?: Locale;
    id: string;
    name: string;
    dosage: string;
    time: string;
    instructions?: string;
    prescriber?: string;
    approvedBy?: string;
    status: TaskCardStatus;
    submitting?: boolean;
    onMarkComplete: (id: string) => void;
    onReportBarrier?: (id: string) => void;
}

const badgeVariant = {
    active: "info",
    completed: "success",
    missed: "danger",
    upcoming: "neutral",
    skipped: "neutral",
} as const;

const cardClasses = {
    active: "border-[#147465] bg-surface shadow-[0_20px_46px_rgba(20,116,101,0.16)]",
    completed: "border-[#dbe7df] bg-[#f2f8f4]",
    missed: "border-[#efbeb5] bg-[#fff5f2]",
    upcoming: "border-white/70 bg-surface/82",
    skipped: "border-[#edd59a] bg-[#fff7dc]",
} as const;

export function MedicationCard({
    locale,
    dosage,
    id,
    instructions,
    name,
    onMarkComplete,
    onReportBarrier,
    prescriber,
    approvedBy,
    status,
    submitting = false,
    time,
}: MedicationCardProps) {
    const copy = getTodayCopy(locale);
    return (
        <Card className={`space-y-4 ${cardClasses[status]}`} padding="md">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1 basis-44 space-y-1 break-words">
                    <h3 className={`text-lg font-bold leading-snug ${status === "completed" ? "text-[#77869a] line-through" : "text-[#17233a]"}`}>
                        {name} <span className={`font-semibold ${status === "completed" ? "text-[#9aa7b8] line-through" : "text-[#5b6b83]"}`}>{dosage}</span>
                    </h3>
                    <p className={`text-base leading-7 ${status === "completed" ? "text-[#9aa7b8] line-through" : "text-[#5b6b83]"}`}>{instructions ?? copy.prescription}</p>
                    {approvedBy ? <p className="text-sm font-medium text-[#147465]">{copy.approvedBy(approvedBy)}</p> : prescriber ? <p className="text-sm font-medium text-[#147465]">{copy.prescribedBy(prescriber)}</p> : null}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2 text-right">
                    <span className="inline-flex rounded-full bg-[#f4f0ea] px-3 py-1 text-[11px] font-black uppercase tracking-[0.18em] text-[#5b6b83]">
                        Rx
                    </span>
                    <Badge variant={badgeVariant[status]}>
                        {getTaskStatusLabel(status, time, copy)}
                    </Badge>
                </div>
            </div>
            {status === "active" || status === "missed" ? (
                <div className="space-y-2"><Button disabled={submitting} fullWidth onClick={() => onMarkComplete(id)} size="lg" variant={status === "missed" ? "danger" : "primary"}>{copy.taken}</Button>{onReportBarrier ? <button disabled={submitting} className="w-full text-sm font-semibold text-[#5b6b83] underline" onClick={() => onReportBarrier(id)} type="button">{copy.barrier}</button> : null}</div>
            ) : null}
        </Card>
    );
}
