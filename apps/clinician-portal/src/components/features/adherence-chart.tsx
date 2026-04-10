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
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
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
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-lg">
            <p className="mb-1 text-xs font-semibold text-gray-500">{formatDate(label ?? "")}</p>
            <p className="text-sm font-bold text-blue-600">
                {Math.round((point?.value ?? 0) * 100)}% adherence
            </p>
            <p className="text-xs text-gray-400">
                {point?.payload?.completed ?? 0} of {point?.payload?.expected ?? 0} completed
            </p>
        </div>
    );
}

export function AdherenceChart({ data }: AdherenceChartProps) {
    if (data.length === 0) {
        return (
            <div
                aria-label="30-day adherence chart"
                className="flex h-40 items-center justify-center rounded-xl border border-dashed border-gray-200 text-sm text-gray-400"
            >
                No adherence data available for this period.
            </div>
        );
    }

    // Use the axis tick value itself, not array indexing, so labels stay correct.
    const tickFormatter = (value: string) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.getDate() % 5 === 0 ? formatDate(value) : "";
    };

    return (
        <div className="w-full" aria-label="30-day adherence chart">
            <ResponsiveContainer height={220} width="100%">
                <LineChart
                    data={data}
                    margin={{ top: 4, right: 16, bottom: 4, left: -16 }}
                >
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="4 4" vertical={false} />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 11, fill: "#94a3b8" }}
                        tickFormatter={tickFormatter}
                        tickLine={false}
                        axisLine={false}
                    />
                    <YAxis
                        domain={[0, 1]}
                        tick={{ fontSize: 11, fill: "#94a3b8" }}
                        tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                        dataKey="score"
                        dot={false}
                        name="Adherence"
                        stroke="#2563eb"
                        strokeWidth={2}
                        type="monotone"
                        activeDot={{ r: 5, fill: "#2563eb", strokeWidth: 0 }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
