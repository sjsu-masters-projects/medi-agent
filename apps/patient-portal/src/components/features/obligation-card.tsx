import { Badge, Button, Card } from "@/components/ui";
import type { TaskCardStatus } from "./task-card.types";

interface ObligationCardProps {
    id: string;
    description: string;
    type: "diet" | "exercise" | "custom";
    time: string;
    status: TaskCardStatus;
    onMarkComplete: (id: string) => void;
}

const badgeVariant = {
    active: "info",
    completed: "success",
    missed: "danger",
    upcoming: "neutral",
} as const;

const obligationLabel = {
    custom: "Custom task",
    diet: "Diet obligation",
    exercise: "Exercise obligation",
} as const;

const typeLabel = {
    custom: "Task",
    diet: "Diet",
    exercise: "Move",
} as const;

const cardClasses = {
    active: "border-[#147465] bg-white shadow-[0_20px_46px_rgba(20,116,101,0.16)]",
    completed: "border-[#dbe7df] bg-[#f2f8f4]",
    missed: "border-[#efbeb5] bg-[#fff5f2]",
    upcoming: "border-white/70 bg-white/82",
} as const;

export function ObligationCard({
    description,
    id,
    onMarkComplete,
    status,
    time,
    type,
}: ObligationCardProps) {
    return (
        <Card className={`space-y-4 ${cardClasses[status]}`} padding="md">
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                    {time ? <p className="text-sm font-bold text-[#147465]">{time}</p> : null}
                    <h3 className={`text-lg font-bold leading-snug ${status === "completed" ? "text-[#77869a] line-through" : "text-[#17233a]"}`}>{description}</h3>
                    <p className={`text-base leading-7 ${status === "completed" ? "text-[#9aa7b8] line-through" : "text-[#5b6b83]"}`}>{obligationLabel[type]}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2 text-right">
                    <span className="inline-flex rounded-full bg-[#f4f0ea] px-3 py-1 text-[11px] font-black uppercase tracking-[0.18em] text-[#5b6b83]">
                        {typeLabel[type]}
                    </span>
                    <Badge variant={badgeVariant[status]}>
                        {status === "missed" ? "Missed" : status === "active" ? "Due now" : status}
                    </Badge>
                </div>
            </div>
            {status === "active" || status === "missed" ? (
                <Button fullWidth onClick={() => onMarkComplete(id)} size="lg" variant={status === "missed" ? "danger" : "primary"}>
                    Mark as Done
                </Button>
            ) : null}
        </Card>
    );
}
