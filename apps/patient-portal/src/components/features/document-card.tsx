import { Badge, Card } from "@/components/ui";

interface DocumentCardProps {
    id: string;
    name: string;
    type: string;
    date: string;
    provider: string;
    icon: string;
    hasAiSummary: boolean;
    statusLabel?: string;
    statusVariant?: "success" | "warning" | "danger" | "info" | "neutral";
    onClick: () => void;
}

export function DocumentCard({
    date,
    hasAiSummary,
    icon,
    name,
    onClick,
    provider,
    statusLabel,
    statusVariant = "neutral",
    type,
}: DocumentCardProps) {
    return (
        <button className="w-full text-left" onClick={onClick} type="button">
            <Card className="flex items-start gap-4 border-slate-100 transition hover:border-sky-200 hover:shadow-md">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-50 text-2xl text-sky-700 shadow-sm">
                    {icon}
                </span>
                <div className="min-w-0 flex-1 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold text-slate-900">{name}</h3>
                            <p className="mt-1 text-xs text-slate-400">{provider}</p>
                        </div>
                        <div className="flex items-center gap-2">
                            {statusLabel ? <Badge variant={statusVariant}>{statusLabel}</Badge> : null}
                            {!statusLabel && hasAiSummary ? <Badge variant="info">AI Summary</Badge> : null}
                            <span className="text-sm text-slate-300">→</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Badge variant="neutral">{type}</Badge>
                        <span>{date}</span>
                    </div>
                </div>
            </Card>
        </button>
    );
}
