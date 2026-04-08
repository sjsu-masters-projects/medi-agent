import { Badge, Button, Card } from "@/components/ui";

interface MedicationCardProps {
    id: string;
    name: string;
    dosage: string;
    time: string;
    instructions?: string;
    prescriber?: string;
    status: "completed" | "active" | "upcoming" | "missed";
    onMarkComplete: (id: string) => void;
}

const badgeVariant = {
    active: "info",
    completed: "success",
    missed: "danger",
    upcoming: "neutral",
} as const;

const cardClasses = {
    active: "border-blue-700 shadow-md shadow-blue-100",
    completed: "border-slate-100 bg-slate-50 opacity-70",
    missed: "border-red-200 bg-red-50/60",
    upcoming: "border-slate-100 bg-white",
} as const;

export function MedicationCard({
    dosage,
    id,
    instructions,
    name,
    onMarkComplete,
    prescriber,
    status,
    time,
}: MedicationCardProps) {
    return (
        <Card className={`space-y-4 ${cardClasses[status]}`} padding="sm">
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                    {time ? <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{time}</p> : null}
                    <h3 className={`text-sm font-semibold ${status === "completed" ? "text-slate-400 line-through" : "text-slate-800"}`}>
                        {name} <span className={`font-medium ${status === "completed" ? "text-slate-300 line-through" : "text-slate-500"}`}>{dosage}</span>
                    </h3>
                    <p className={`text-sm ${status === "completed" ? "text-slate-400 line-through" : "text-slate-500"}`}>{instructions ?? "Take as prescribed."}</p>
                    {prescriber ? <p className="text-xs text-sky-700">Prescribed by {prescriber}</p> : null}
                </div>
                <div className="space-y-2 text-right">
                    <span className="inline-flex rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">
                        Rx
                    </span>
                    <Badge variant={badgeVariant[status]}>
                        {status === "missed" ? "Missed" : status === "active" ? "Due now" : status}
                    </Badge>
                </div>
            </div>
            {status === "active" || status === "missed" ? (
                <Button fullWidth onClick={() => onMarkComplete(id)} variant={status === "missed" ? "danger" : "primary"}>
                    Mark as Taken
                </Button>
            ) : null}
        </Card>
    );
}
