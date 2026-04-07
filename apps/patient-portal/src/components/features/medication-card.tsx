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
        <Card className="space-y-4">
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{time}</p>
                    <h3 className="text-sm font-semibold text-gray-900">
                        {name} <span className="font-medium text-gray-500">{dosage}</span>
                    </h3>
                    <p className="text-sm text-gray-500">{instructions ?? "Take as prescribed."}</p>
                    {prescriber ? <p className="text-xs text-gray-400">Prescribed by {prescriber}</p> : null}
                </div>
                <Badge variant={badgeVariant[status]}>
                    {status === "missed" ? "Missed" : status === "active" ? "Due now" : status}
                </Badge>
            </div>
            {status === "active" || status === "missed" ? (
                <Button fullWidth onClick={() => onMarkComplete(id)} variant="primary">
                    Mark as Taken
                </Button>
            ) : null}
        </Card>
    );
}
