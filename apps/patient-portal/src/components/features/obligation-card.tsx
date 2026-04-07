import { Badge, Button, Card } from "@/components/ui";

interface ObligationCardProps {
    id: string;
    description: string;
    type: "diet" | "exercise" | "custom";
    time: string;
    status: "completed" | "active" | "upcoming" | "missed";
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

export function ObligationCard({
    description,
    id,
    onMarkComplete,
    status,
    time,
    type,
}: ObligationCardProps) {
    return (
        <Card className="space-y-4">
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{time}</p>
                    <h3 className="text-sm font-semibold text-gray-900">{description}</h3>
                    <p className="text-sm text-gray-500">{obligationLabel[type]}</p>
                </div>
                <Badge variant={badgeVariant[status]}>
                    {status === "missed" ? "Missed" : status === "active" ? "Due now" : status}
                </Badge>
            </div>
            {status === "active" || status === "missed" ? (
                <Button fullWidth onClick={() => onMarkComplete(id)} variant="secondary">
                    Mark as Done
                </Button>
            ) : null}
        </Card>
    );
}
