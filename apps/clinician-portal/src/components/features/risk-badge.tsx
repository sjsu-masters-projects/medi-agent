import { FaCircle } from "react-icons/fa6";
import { Badge } from "@/components/ui";

interface RiskBadgeProps {
    level: "low" | "medium" | "high" | "unknown";
}

const riskConfig = {
    high: { iconClassName: "text-red-500", label: "High", variant: "danger" as const },
    low: { iconClassName: "text-green-500", label: "Low", variant: "success" as const },
    medium: { iconClassName: "text-yellow-500", label: "Medium", variant: "warning" as const },
    unknown: { iconClassName: "text-slate-500", label: "Unknown", variant: "neutral" as const },
};

export function RiskBadge({ level }: RiskBadgeProps) {
    const config = riskConfig[level];
    return (
        <Badge variant={config.variant}>
            <FaCircle className={`mr-1 text-[10px] ${config.iconClassName}`} />
            {config.label}
        </Badge>
    );
}
