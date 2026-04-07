import { Badge, Card } from "@/components/ui";

interface DocumentCardProps {
    id: string;
    name: string;
    type: string;
    date: string;
    provider: string;
    icon: string;
    hasAiSummary: boolean;
    onClick: () => void;
}

export function DocumentCard({
    date,
    hasAiSummary,
    icon,
    name,
    onClick,
    provider,
    type,
}: DocumentCardProps) {
    return (
        <button className="w-full text-left" onClick={onClick} type="button">
            <Card className="flex items-start gap-4 transition hover:border-blue-200 hover:shadow-md">
                <span className="text-2xl">{icon}</span>
                <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <h3 className="truncate text-sm font-semibold text-gray-900">{name}</h3>
                            <p className="text-xs text-gray-400">{provider}</p>
                        </div>
                        {hasAiSummary ? <Badge variant="info">AI Summary</Badge> : null}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Badge variant="neutral">{type}</Badge>
                        <span>{date}</span>
                    </div>
                </div>
            </Card>
        </button>
    );
}
