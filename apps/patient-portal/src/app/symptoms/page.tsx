"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Severity = "SEVERE" | "MODERATE" | "MILD";

interface SymptomEntry {
  id: string;
  label: string;
  quote: string;
  severity: Severity;
  date: string;
  suspectedLink?: { type: "medication" | "recent"; text: string };
}

const SEVERITY_CONFIG: Record<Severity, { color: string; bg: string; dot: string; border: string }> = {
  SEVERE: { color: "#ef4444", bg: "#fef2f2", dot: "#ef4444", border: "#fca5a5" },
  MODERATE: { color: "#d97706", bg: "#fffbeb", dot: "#f59e0b", border: "#fcd34d" },
  MILD: { color: "#6b7280", bg: "#f9fafb", dot: "#9ca3af", border: "#e5e7eb" },
};

const SYMPTOMS: SymptomEntry[] = [
  {
    id: "1",
    label: "Dizziness & Vertigo",
    quote: "The room spins when I stand up.",
    severity: "SEVERE",
    date: "TODAY, 8:15 AM",
    suspectedLink: { type: "medication", text: "Suspected Link · Spironolactone + Lisinopril" },
  },
  {
    id: "2",
    label: "Lightheadedness",
    quote: "Felt a bit woozy after breakfast.",
    severity: "MODERATE",
    date: "YESTERDAY, 9:30 AM",
    suspectedLink: { type: "recent", text: "Recent Med · Took Spironolactone at 8:00 AM" },
  },
  {
    id: "3",
    label: "Mild Nausea",
    quote: "Reported via check-in",
    severity: "MILD",
    date: "FEB 28, 2:00 PM",
  },
];

export default function SymptomsPage() {
  const router = useRouter();
  const [timeFilter] = useState("Past 30 Days");
  const [showLogForm, setShowLogForm] = useState(false);
  const [newSymptom, setNewSymptom] = useState("");
  const [newSeverity, setNewSeverity] = useState<Severity>("MILD");

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-12 pb-4">
        <button onClick={() => router.back()} className="text-xl" style={{ color: "var(--text-primary)" }}>
          ←
        </button>
        <h1 className="font-bold text-base" style={{ color: "var(--text-primary)" }}>Symptom Timeline</h1>
        <button
          onClick={() => setShowLogForm(true)}
          className="w-8 h-8 rounded-full flex items-center justify-center text-white text-lg"
          style={{ background: "var(--primary)" }}
        >
          +
        </button>
      </div>

      <div className="px-5 flex flex-col gap-5">
        {/* AI Pattern Detected card */}
        <div
          className="rounded-2xl p-4 flex flex-col gap-3"
          style={{ background: "#0f172a" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center text-xl flex-shrink-0"
              style={{ background: "#1e40af" }}
            >
              🔵
            </div>
            <p className="font-bold text-white text-sm">AI Pattern Detected</p>
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "#cbd5e1" }}>
            Your reported{" "}
            <span className="font-bold" style={{ color: "#fbbf24" }}>Severe Dizziness</span>{" "}
            correlates closely with the start of your new prescription for{" "}
            <span className="font-bold text-white">Spironolactone</span> combined with your existing{" "}
            <span className="font-bold text-white">Lisinopril</span>.
          </p>
          <button
            className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium w-fit"
            style={{ background: "rgba(255,255,255,0.1)", color: "#cbd5e1" }}
          >
            ↗ This insight has been shared with Dr. Patel.
          </button>
        </div>

        {/* History header */}
        <div className="flex items-center justify-between">
          <h2 className="font-bold" style={{ color: "var(--text-primary)" }}>History</h2>
          <button
            className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium border"
            style={{ borderColor: "#e2e8f0", color: "var(--text-secondary)" }}
          >
            {timeFilter} ▾
          </button>
        </div>

        {/* Timeline */}
        <div className="flex flex-col gap-4 pb-24">
          {SYMPTOMS.map((symptom) => {
            const cfg = SEVERITY_CONFIG[symptom.severity];
            return (
              <div key={symptom.id} className="flex gap-3 items-start">
                {/* Dot */}
                <div className="flex flex-col items-center mt-1" style={{ minWidth: "12px" }}>
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ background: cfg.dot }}
                  />
                </div>

                {/* Card */}
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
                      {symptom.date}
                    </p>
                    <span
                      className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                      style={{ background: cfg.bg, color: cfg.color }}
                    >
                      {symptom.severity}
                    </span>
                  </div>

                  <div
                    className="rounded-2xl p-4 border-l-4"
                    style={{ background: cfg.bg, borderLeftColor: cfg.border }}
                  >
                    <p className="font-bold text-sm mb-1" style={{ color: "var(--text-primary)" }}>
                      {symptom.label}
                    </p>
                    <p className="text-sm italic mb-3" style={{ color: "var(--text-secondary)" }}>
                      &quot;{symptom.quote}&quot;
                    </p>
                    {symptom.suspectedLink && (
                      <div
                        className="flex items-center gap-2 rounded-xl px-3 py-2"
                        style={{ background: "white", border: "1px solid #e2e8f0" }}
                      >
                        <span className="text-sm">💊</span>
                        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                          {symptom.suspectedLink.text}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Log Symptom bottom sheet */}
      {showLogForm && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end" style={{ background: "rgba(0,0,0,0.5)" }}>
          <div className="rounded-t-3xl bg-white p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-lg" style={{ color: "var(--text-primary)" }}>Log a Symptom</h3>
              <button onClick={() => setShowLogForm(false)} style={{ color: "var(--text-muted)" }}>✕</button>
            </div>
            <textarea
              value={newSymptom}
              onChange={(e) => setNewSymptom(e.target.value)}
              placeholder="Describe how you're feeling..."
              rows={3}
              className="rounded-xl p-3 text-sm resize-none outline-none border"
              style={{ borderColor: "#e2e8f0", color: "var(--text-primary)" }}
            />
            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: "var(--text-secondary)" }}>Severity</p>
              <div className="flex gap-2">
                {(["MILD", "MODERATE", "SEVERE"] as Severity[]).map((s) => {
                  const cfg = SEVERITY_CONFIG[s];
                  return (
                    <button
                      key={s}
                      onClick={() => setNewSeverity(s)}
                      className="flex-1 rounded-xl py-2 text-xs font-bold transition-all"
                      style={
                        newSeverity === s
                          ? { background: cfg.color, color: "white" }
                          : { background: cfg.bg, color: cfg.color }
                      }
                    >
                      {s}
                    </button>
                  );
                })}
              </div>
            </div>
            <button
              onClick={() => setShowLogForm(false)}
              className="w-full rounded-2xl py-3 text-sm font-semibold text-white"
              style={{ background: "var(--primary)" }}
            >
              Log Symptom
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
