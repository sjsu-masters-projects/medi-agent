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

interface SymptomReport {
    id: string;
    symptom: string;
    severity: number;
    created_at: string;
    flagged_for_adr?: boolean;
}

interface SymptomTimelineProps {
    data: SymptomReport[];
}

interface ChartPoint {
    date: string;
    severity: number;
    symptom: string;
    flagged: boolean;
}

function buildChartData(reports: SymptomReport[]): ChartPoint[] {
    return [...reports]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .map((r) => ({
            date: r.created_at.slice(0, 10),
            severity: r.severity,
            symptom: r.symptom,
            flagged: r.flagged_for_adr ?? false,
        }));
}

function severityColor(severity: number): string {
    if (severity >= 8) return "#ef4444"; // red-500
    if (severity >= 5) return "#f59e0b"; // amber-500
    return "#22c55e"; // green-500
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
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-lg">
            <p className="mb-1 text-xs font-semibold text-gray-500">{point.date}</p>
            <p className="text-sm font-bold text-gray-900 capitalize">{point.symptom}</p>
            <p
                className="text-sm font-semibold"
                style={{ color: severityColor(point.severity) }}
            >
                Severity: {point.severity}/10
            </p>
            {point.flagged && (
                <p className="mt-1 text-xs font-medium text-red-600">⚠ ADR flagged</p>
            )}
        </div>
    );
}

export function SymptomTimeline({ data }: SymptomTimelineProps) {
    const chartData = buildChartData(data);

    if (chartData.length === 0) {
        return (
            <div className="flex h-40 items-center justify-center text-sm text-gray-400">
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
                            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} />
                            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="4 4" vertical={false} />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 11, fill: "#94a3b8" }}
                        tickLine={false}
                        axisLine={false}
                    />
                    <YAxis
                        domain={[0, 10]}
                        tick={{ fontSize: 11, fill: "#94a3b8" }}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                        dataKey="severity"
                        fill="url(#symptomGradient)"
                        name="Severity"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        type="monotone"
                        dot={{ r: 4, fill: "#f59e0b", strokeWidth: 0 }}
                    />
                </AreaChart>
            </ResponsiveContainer>

            {/* Legend */}
            <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-green-500" /> Mild (1–4)
                </span>
                <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> Moderate (5–7)
                </span>
                <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> Severe (8–10)
                </span>
            </div>
        </div>
    );
}
