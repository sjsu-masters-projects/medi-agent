"use client";

import { useState } from "react";

interface MedRecord {
  id: string;
  name: string;
  type: "Lab Report" | "Imaging" | "Prescription" | "Visit Summary";
  date: string;
  provider: string;
  icon: string;
  summary?: string;
}

const RECORDS: MedRecord[] = [
  {
    id: "1",
    name: "Blood Panel Results",
    type: "Lab Report",
    date: "Mar 15, 2026",
    provider: "Dr. Smith – City Medical",
    icon: "🩸",
    summary: "HbA1c: 6.8% (within target). LDL: 112 mg/dL (slightly elevated). Blood pressure trending normal. Your diabetes management is improving — keep up the current medication regimen.",
  },
  {
    id: "2",
    name: "Chest X-Ray",
    type: "Imaging",
    date: "Feb 28, 2026",
    provider: "Radiology – City Medical",
    icon: "🫁",
    summary: "No acute cardiopulmonary findings. Lungs clear. Heart size normal.",
  },
  {
    id: "3",
    name: "Spironolactone Rx",
    type: "Prescription",
    date: "Feb 20, 2026",
    provider: "Dr. Patel",
    icon: "💊",
    summary: "New prescription for Spironolactone 25mg. Take once daily in the morning. Monitor blood pressure and potassium levels.",
  },
  {
    id: "4",
    name: "Annual Checkup Summary",
    type: "Visit Summary",
    date: "Jan 10, 2026",
    provider: "Dr. Smith",
    icon: "📋",
  },
];

const TYPE_COLORS: Record<string, string> = {
  "Lab Report": "#3373d1",
  "Imaging": "#7c3aed",
  "Prescription": "#059669",
  "Visit Summary": "#d97706",
};

export default function RecordsPage() {
  const [selected, setSelected] = useState<MedRecord | null>(null);
  const [filter, setFilter] = useState("All");

  const filters = ["All", "Lab Report", "Imaging", "Prescription", "Visit Summary"];
  const filtered = filter === "All" ? RECORDS : RECORDS.filter((r) => r.type === filter);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="px-5 pt-12 pb-4">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>My Records</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>
          {RECORDS.length} documents · AI explanations available
        </p>
      </div>

      {/* Upload button */}
      <div className="px-5 mb-4">
        <button
          className="w-full rounded-2xl border-2 border-dashed py-4 flex items-center justify-center gap-2 text-sm font-medium transition-colors"
          style={{ borderColor: "var(--primary)", color: "var(--primary)" }}
        >
          ➕ Upload Document
        </button>
      </div>

      {/* Filter chips */}
      <div className="px-5 mb-4 flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="flex-shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors"
            style={
              filter === f
                ? { background: "var(--primary)", color: "white" }
                : { background: "#f1f5f9", color: "var(--text-secondary)" }
            }
          >
            {f}
          </button>
        ))}
      </div>

      {/* Record list */}
      <div className="px-5 flex flex-col gap-3">
        {filtered.map((record) => (
          <button
            key={record.id}
            onClick={() => setSelected(record)}
            className="w-full rounded-2xl p-4 flex items-start gap-3 text-left"
            style={{ background: "#f8fafc", border: "1px solid #e2e8f0" }}
          >
            <span className="text-2xl mt-0.5">{record.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <p className="font-semibold text-sm truncate" style={{ color: "var(--text-primary)" }}>
                  {record.name}
                </p>
                {record.summary && (
                  <span
                    className="flex-shrink-0 text-xs font-medium px-2 py-0.5 rounded-full"
                    style={{ background: "#e8f0fb", color: "var(--primary)" }}
                  >
                    AI ✦
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className="text-[10px] font-medium px-2 py-0.5 rounded-full"
                  style={{
                    background: `${TYPE_COLORS[record.type]}15`,
                    color: TYPE_COLORS[record.type],
                  }}
                >
                  {record.type}
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>{record.date}</span>
              </div>
              <p className="text-xs mt-1 truncate" style={{ color: "var(--text-secondary)" }}>{record.provider}</p>
            </div>
          </button>
        ))}
      </div>

      {/* AI Explainer slide-up panel */}
      {selected && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end" style={{ background: "rgba(0,0,0,0.5)" }}>
          <div
            className="rounded-t-3xl p-6 flex flex-col gap-4 max-h-[80vh] overflow-y-auto"
            style={{ background: "white" }}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{selected.icon}</span>
                <div>
                  <p className="font-bold" style={{ color: "var(--text-primary)" }}>{selected.name}</p>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>{selected.date} · {selected.provider}</p>
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-xl"
                style={{ color: "var(--text-muted)" }}
              >
                ✕
              </button>
            </div>

            {selected.summary ? (
              <div className="rounded-2xl p-4" style={{ background: "#f0f7ff", border: "1px solid var(--primary-light)" }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-base">✦</span>
                  <p className="text-xs font-semibold" style={{ color: "var(--primary)" }}>AI Explanation</p>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  {selected.summary}
                </p>
              </div>
            ) : (
              <div
                className="rounded-2xl p-4 flex items-center gap-3"
                style={{ background: "#f8fafc", border: "1px solid #e2e8f0" }}
              >
                <span className="text-2xl">🤖</span>
                <div>
                  <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>Ask AI to explain this</p>
                  <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Get a plain-language summary</p>
                </div>
                <button
                  className="ml-auto rounded-xl px-3 py-1.5 text-xs font-semibold text-white"
                  style={{ background: "var(--primary)" }}
                >
                  Explain
                </button>
              </div>
            )}

            <button
              className="w-full rounded-2xl py-3 text-sm font-semibold border"
              style={{ borderColor: "#e2e8f0", color: "var(--text-secondary)" }}
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
