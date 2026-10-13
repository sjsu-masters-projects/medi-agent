"use client";

import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import type { AdherenceDataPoint } from "@/services/clinicians";

interface AdherenceChartProps {
    data: AdherenceDataPoint[];
}

/** Format axis tick: "Mar 15" */
function formatDate(dateStr: string): string {
    const date = new Date(`${dateStr}T12:00:00Z`);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** Custom tooltip content */
function CustomTooltip({
    active,
    payload,
    label,
}: {
    active?: boolean;
    payload?: Array<{ value: number; payload: AdherenceDataPoint }>;
    label?: string;
}) {
    if (!active || !payload?.length) return null;
    const point = payload[0];
    return (
        <div className="rounded-xl border border-line bg-surface px-3.5 py-2.5 shadow-[var(--shadow-pop)]">
            <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{formatDate(label ?? "")}</p>
            <p className={`text-sm font-semibold ${(point?.value ?? 0) < LOW_COMPLETION ? "text-risk-ink" : "text-primary"}`}>
                <span className="font-mono">{Math.round((point?.value ?? 0) * 100)}%</span> adherence
            </p>
            <p className="mt-0.5 text-xs text-muted">
                {point?.payload?.completed ?? 0} of {point?.payload?.expected ?? 0} recorded responses completed
            </p>
        </div>
    );
}

/** Days below this recorded completion are drawn in the risk color, matching the roster bars. */
const LOW_COMPLETION = 0.6;
const AXIS_TICK = { fontSize: 12, fill: "var(--color-muted)" };

function CompletionDot(props: { cx?: number; cy?: number; payload?: { score: number | null }; active?: boolean }) {
    const { cx, cy, payload, active = false } = props;
    if (cx === undefined || cy === undefined || payload?.score === null || payload?.score === undefined) return null;
    const low = payload.score < LOW_COMPLETION;
    return (
        <circle
            cx={cx}
            cy={cy}
            fill={low ? "var(--color-risk)" : "var(--color-primary)"}
            r={active ? 5 : 3}
            stroke="var(--color-surface)"
            strokeWidth={active ? 2 : 1.5}
        />
    );
}

export function toAdherenceChartData(data: AdherenceDataPoint[]) {
    return data.map((point) => ({ ...point, score: point.expected > 0 ? point.score : null }));
}

export function AdherenceChart({ data }: AdherenceChartProps) {
    if (!data.some((point) => point.expected > 0)) {
        return (
            <div
                aria-label="30-day adherence chart"
                className="flex h-40 items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface-2 text-sm text-muted"
            >
                No adherence data available for this period.
            </div>
        );
    }

    // Use the axis tick value itself, not array indexing, so labels stay correct.
    const tickFormatter = (value: string) => {
        const date = new Date(`${value}T12:00:00Z`);
        if (Number.isNaN(date.getTime())) return "";
        return date.getUTCDate() % 5 === 0 ? formatDate(value) : "";
    };

    return (
        <div className="w-full" aria-label="30-day adherence chart">
            <ResponsiveContainer height={220} width="100%">
                <LineChart
                    data={toAdherenceChartData(data)}
                    margin={{ top: 4, right: 16, bottom: 4, left: -16 }}
                >
                    <CartesianGrid stroke="var(--color-line-strong)" strokeDasharray="3 4" vertical={false} />
                    <XAxis
                        dataKey="date"
                        tick={AXIS_TICK}
                        tickFormatter={tickFormatter}
                        tickLine={false}
                        axisLine={false}
                    />
                    <YAxis
                        domain={[0, 1]}
                        tick={AXIS_TICK}
                        tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ stroke: "var(--color-line-strong)", strokeWidth: 1 }} />
                    <Line
                        dataKey="score"
                        dot={<CompletionDot />}
                        connectNulls={false}
                        name="Adherence"
                        stroke="var(--color-primary)"
                        strokeWidth={2}
                        type="linear"
                        activeDot={<CompletionDot active />}
                        isAnimationActive={false}
                    />
                </LineChart>
            </ResponsiveContainer>
            <div className="mt-2 flex flex-wrap gap-2 pl-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1">
                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-primary" /> Recorded completion
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-surface-2 px-2 py-1">
                    <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-risk" /> Below <span className="font-mono">60%</span>
                </span>
            </div>
        </div>
    );
}
