import { Badge } from "@/components/ui";

interface RiskBadgeProps {
    level: "low" | "medium" | "high";
}

const riskConfig = {
    high: { icon: "🔴", label: "High", variant: "danger" as const },
    low: { icon: "🟢", label: "Low", variant: "success" as const },
    medium: { icon: "🟡", label: "Medium", variant: "warning" as const },
};

export function RiskBadge({ level }: RiskBadgeProps) {
    const config = riskConfig[level];
    return (
        <Badge variant={config.variant}>
            <span className="mr-1">{config.icon}</span>
            {config.label}
        </Badge>
    );
}
