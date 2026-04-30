import type { ReactNode } from "react";
import { HiOutlineChevronRight } from "react-icons/hi2";
import { Badge, Card } from "@/components/ui";

interface DocumentCardProps {
    id: string;
    name: string;
    type: string;
    date: string;
    provider: string;
    icon: ReactNode;
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
            <Card className="flex items-start gap-4 transition hover:-translate-y-0.5 hover:border-[#b6d9d2] hover:shadow-[0_22px_54px_rgba(20,116,101,0.13)]">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl bg-[#e6f4f1] text-2xl text-[#147465] shadow-sm">
                    {icon}
                </span>
                <div className="min-w-0 flex-1 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <h3 className="truncate text-base font-bold text-[#17233a]">{name}</h3>
                            <p className="mt-1 text-sm text-[#64748b]">{provider}</p>
                        </div>
                        <div className="flex items-center gap-2">
                            {statusLabel ? <Badge variant={statusVariant}>{statusLabel}</Badge> : null}
                            {!statusLabel && hasAiSummary ? <Badge variant="info">AI Summary</Badge> : null}
                            <HiOutlineChevronRight className="text-lg text-[#9aa7b8]" />
                        </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-[#5b6b83]">
                        <Badge variant="neutral">{type}</Badge>
                        <span>{date}</span>
                    </div>
                </div>
            </Card>
        </button>
    );
}
