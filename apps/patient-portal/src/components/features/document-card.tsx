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
    <button
      className="w-full rounded-xl text-left focus-visible:outline-2 focus-visible:outline-blue-600"
      onClick={onClick}
      type="button"
    >
      <Card className="flex items-start gap-4 transition hover:border-blue-600 hover:shadow-sm">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-100 text-2xl text-gray-700 shadow-sm">
          {icon}
        </span>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 w-full">
              <h3 className="break-words text-base font-bold text-gray-700">
                {name}
              </h3>
              <p className="mt-1 text-sm text-gray-700">{provider}</p>
            </div>
            <div className="flex items-center gap-2">
              {statusLabel ? (
                <Badge variant={statusVariant}>{statusLabel}</Badge>
              ) : null}
              {!statusLabel && hasAiSummary ? (
                <Badge variant="info">AI Summary</Badge>
              ) : null}
              <HiOutlineChevronRight className="text-lg text-gray-700" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-700">
            <Badge variant="neutral">{type}</Badge>
            <span>{date}</span>
          </div>
        </div>
      </Card>
    </button>
  );
}
