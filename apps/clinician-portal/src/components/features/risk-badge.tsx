interface RiskBadgeProps {
    level: "low" | "medium" | "high" | "unknown";
}

const riskConfig = {
    high: { chip: "bg-risk-tint text-risk-ink", dot: "bg-risk", label: "High" },
    medium: { chip: "bg-warn-tint text-warn-ink", dot: "bg-warn", label: "Medium" },
    low: { chip: "bg-ok-tint text-ok-ink", dot: "bg-ok", label: "Low" },
    unknown: { chip: "bg-[rgba(100,116,139,.1)] text-ink-2", dot: "bg-[#64748B]", label: "Unknown" },
};

export function RiskBadge({ level }: RiskBadgeProps) {
    const config = riskConfig[level];
    return (
        <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[7px] px-2 py-1 text-[13px] font-medium ${config.chip}`}>
            <span aria-hidden="true" className={`h-[7px] w-[7px] rounded-full ${config.dot}`} />
            {config.label}
        </span>
    );
}
