"use client";

import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import { Icon } from "@/components/ui/icons";
import type { SymptomReport } from "@/types";

interface SymptomTimelineProps {
    data: SymptomReport[];
}

interface ChartPoint {
    date: string;
    severity: number | null;
    symptom: string;
    flagged: boolean;
}

function buildChartData(reports: SymptomReport[]): ChartPoint[] {
    return [...reports]
        .sort((a, b) => {
            const aCreated = (a as SymptomReport & { created_at?: string }).createdAt ??
                (a as SymptomReport & { created_at?: string }).created_at ??
                "";
            const bCreated = (b as SymptomReport & { created_at?: string }).createdAt ??
                (b as SymptomReport & { created_at?: string }).created_at ??
                "";
            return aCreated.localeCompare(bCreated);
        })
        .map((r) => ({
            date: (
                (r as SymptomReport & { created_at?: string }).createdAt ??
                (r as SymptomReport & { created_at?: string }).created_at ??
                ""
            ).slice(0, 10),
            severity: r.severity,
            symptom: r.symptom,
            flagged:
                (r as SymptomReport & { flagged_for_adr?: boolean }).flaggedForAdr ??
                (r as SymptomReport & { flagged_for_adr?: boolean }).flagged_for_adr ??
                false,
        }));
}

function severityColor(severity: number | null): string {
    if (severity === null) return "var(--color-muted)";
    if (severity >= 8) return "var(--color-risk)";
    if (severity >= 5) return "var(--color-warn)";
    return "var(--color-ok)";
}

function severityText(severity: number | null): string {
    if (severity === null) return "text-muted";
    if (severity >= 8) return "text-risk-ink";
    if (severity >= 5) return "text-warn-ink";
    return "text-ok-ink";
}

const AXIS_TICK = { fontSize: 12, fill: "var(--color-muted)" };

function SeverityDot(props: { cx?: number; cy?: number; payload?: ChartPoint; active?: boolean }) {
    const { cx, cy, payload, active = false } = props;
    if (cx === undefined || cy === undefined || !payload || payload.severity === null) return null;
    return (
        <circle
            cx={cx}
            cy={cy}
            fill={severityColor(payload.severity)}
            r={active ? 6 : 4}
            stroke="var(--color-surface)"
            strokeWidth={active ? 2 : 1.5}
        />
    );
}

function CustomTooltip({
    active,
    payload,
}: {
    active?: boolean;
    payload?: Array<{ payload: ChartPoint }>;
}) {
    if (!active || !payload?.length) return null;
    const point = payload[0]?.payload;
    if (!point) return null;

    return (
        <div className="rounded-xl border border-line bg-surface px-3.5 py-2.5 shadow-[var(--shadow-pop)]">
            <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{point.date}</p>
            <p className="text-sm font-semibold capitalize text-ink">{point.symptom}</p>
            <p className={`text-sm font-medium ${severityText(point.severity)}`}>
                Severity: <span className="font-mono">{point.severity === null ? "Unknown / not provided" : `${point.severity}/10`}</span>
            </p>
            {point.flagged && (
                <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-[7px] bg-risk-tint px-2 py-1 text-xs font-medium text-risk-ink">
                    <Icon name="alert" className="h-3 w-3" /> ADR flagged
                </p>
            )}
        </div>
    );
}

export function SymptomTimeline({ data }: SymptomTimelineProps) {
    const chartData = buildChartData(data);

    if (chartData.length === 0) {
        return (
            <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface-2 text-sm text-muted">
                No symptom reports recorded
            </div>
        );
    }

    return (
        <div className="w-full" aria-label="Symptom severity timeline">
            <ResponsiveContainer height={200} width="100%">
                <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: -16 }}>
                    <defs>
                        <linearGradient id="symptomGradient" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-warn)" stopOpacity={0.18} />
                            <stop offset="95%" stopColor="var(--color-warn)" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--color-line-strong)" strokeDasharray="3 4" vertical={false} />
                    <XAxis
                        dataKey="date"
                        tick={AXIS_TICK}
                        tickLine={false}
                        axisLine={false}
                    />
                    <YAxis
                        domain={[0, 10]}
                        tick={AXIS_TICK}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ stroke: "var(--color-line-strong)", strokeWidth: 1 }} />
                    <Area
                        connectNulls={false}
                        dataKey="severity"
                        fill="url(#symptomGradient)"
                        name="Severity"
                        stroke="var(--color-warn)"
                        strokeWidth={2}
                        type="monotone"
                        dot={<SeverityDot />}
                        activeDot={<SeverityDot active />}
                        isAnimationActive={false}
                    />
                </AreaChart>
            </ResponsiveContainer>

            {data.some((report) => report.severity === null) && <p className="mt-2 text-xs text-muted">Unknown ratings are not plotted.</p>}
            {/* Legend */}
            <div className="mt-2 flex flex-wrap gap-2 pl-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1">
                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-ok" /> Mild (1–4)
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1">
                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-warn" /> Moderate (5–7)
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1">
                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-risk" /> Severe (8–10)
                </span>
            </div>
        </div>
    );
}
