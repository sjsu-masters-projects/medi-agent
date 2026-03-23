"use client";

import { useState } from "react";
import Link from "next/link";

interface ScheduleItem {
  id: string;
  time: string;
  label: string;
  subtitle: string;
  type: "medication" | "obligation";
  icon: string;
  status: "completed" | "active" | "upcoming";
}

const SCHEDULE: ScheduleItem[] = [
  {
    id: "1",
    time: "8:00 AM",
    label: "Metformin 500mg",
    subtitle: "Take with breakfast · Prescribed by Dr. Smith",
    type: "medication",
    icon: "💊",
    status: "completed",
  },
  {
    id: "2",
    time: "12:00 PM",
    label: "Low-Sodium Lunch",
    subtitle: "Dietary Obligation",
    type: "obligation",
    icon: "🍽️",
    status: "active",
  },
  {
    id: "3",
    time: "3:00 PM",
    label: "30-Min Walk",
    subtitle: "Exercise",
    type: "obligation",
    icon: "🚶",
    status: "upcoming",
  },
  {
    id: "4",
    time: "6:00 PM",
    label: "Lisinopril 10mg",
    subtitle: "Take with dinner",
    type: "medication",
    icon: "💊",
    status: "upcoming",
  },
  {
    id: "5",
    time: "10:00 PM",
    label: "10-Point Sleep",
    subtitle: "Sleep hygiene check-in",
    type: "obligation",
    icon: "😴",
    status: "upcoming",
  },
];

function CircularProgress({ percent }: { percent: number }) {
  const r = 22;
  const circ = 2 * Math.PI * r;
  const offset = circ - (percent / 100) * circ;
  return (
    <div className="relative w-14 h-14 flex items-center justify-center">
      <svg className="absolute inset-0 -rotate-90" width="56" height="56" viewBox="0 0 56 56">
        <circle cx="28" cy="28" r={r} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="4" />
        <circle
          cx="28"
          cy="28"
          r={r}
          fill="none"
          stroke="white"
          strokeWidth="4"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className="text-xs font-bold text-white">{percent}%</span>
    </div>
  );
}

export default function TodayPage() {
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set(["1"]));

  const totalTasks = SCHEDULE.length;
  const completedCount = completedIds.size;
  const progress = Math.round((completedCount / totalTasks) * 100);

  function markComplete(id: string) {
    setCompletedIds((prev) => new Set([...prev, id]));
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--bg-dark)", color: "var(--text-on-dark)" }}>
      {/* Header */}
      <div className="px-5 pt-12 pb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
            style={{ background: "var(--primary)" }}
          >
            S
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Hi, Sarah</h1>
            <p className="text-xs" style={{ color: "var(--text-muted-dark)" }}>
              {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
            </p>
          </div>
        </div>
      </div>

      {/* Daily Progress Card */}
      <div className="px-5 mb-6">
        <div
          className="rounded-2xl p-4 flex items-center justify-between"
          style={{ background: "var(--primary)", boxShadow: "0 4px 24px rgba(51,115,209,0.4)" }}
        >
          <div>
            <p className="text-white/80 text-xs font-medium mb-0.5">Daily Progress</p>
            <p className="text-white font-semibold text-sm">{completedCount} of {totalTasks} tasks completed</p>
          </div>
          <CircularProgress percent={progress} />
        </div>
      </div>

      {/* Today's Schedule */}
      <div className="px-5">
        <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-muted-dark)" }}>
          TODAY'S SCHEDULE
        </h2>

        <div className="flex flex-col gap-0">
          {SCHEDULE.map((item, idx) => {
            const isDone = completedIds.has(item.id);
            const isActive = item.status === "active" && !isDone;
            const dotColor = isDone
              ? "var(--success)"
              : isActive
              ? "var(--primary)"
              : "var(--border-dark)";

            return (
              <div key={item.id} className="flex gap-3">
                {/* Timeline */}
                <div className="flex flex-col items-center" style={{ minWidth: "60px" }}>
                  <span className="text-xs mb-1 font-medium" style={{ color: "var(--text-muted-dark)" }}>
                    {item.time}
                  </span>
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0 z-10"
                    style={{ background: dotColor, border: isActive ? "2px solid var(--primary)" : "none" }}
                  />
                  {idx < SCHEDULE.length - 1 && (
                    <div className="flex-1 w-px mt-1" style={{ background: "var(--border-dark)", minHeight: "32px" }} />
                  )}
                </div>

                {/* Card */}
                <div className="flex-1 pb-4">
                  {isActive ? (
                    <div
                      className="rounded-2xl p-4 border"
                      style={{ background: "var(--bg-card-dark-2)", borderColor: "var(--primary)" }}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <p className="font-semibold text-white text-sm">{item.label}</p>
                          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted-dark)" }}>{item.subtitle}</p>
                        </div>
                        <span className="text-lg">{item.icon}</span>
                      </div>
                      <button
                        onClick={() => markComplete(item.id)}
                        className="w-full rounded-xl py-2.5 text-sm font-semibold text-white"
                        style={{ background: "var(--primary)" }}
                      >
                        Mark as Complete
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between py-1">
                      <div>
                        <p
                          className="text-sm font-medium"
                          style={{
                            color: isDone ? "var(--text-muted-dark)" : "var(--text-on-dark)",
                            textDecoration: isDone ? "line-through" : "none",
                          }}
                        >
                          {item.label}
                        </p>
                        <p className="text-xs" style={{ color: "var(--text-muted-dark)" }}>{item.subtitle}</p>
                      </div>
                      <span className="text-base opacity-60">{item.icon}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Symptom report shortcut */}
      <div className="px-5 mt-2 pb-4">
        <Link
          href="/symptoms"
          className="flex items-center justify-between rounded-2xl p-4"
          style={{ background: "var(--bg-card-dark)" }}
        >
          <div className="flex items-center gap-3">
            <span className="text-xl">🩺</span>
            <div>
              <p className="text-sm font-medium text-white">Log a Symptom</p>
              <p className="text-xs" style={{ color: "var(--text-muted-dark)" }}>Track how you're feeling</p>
            </div>
          </div>
          <span style={{ color: "var(--text-muted-dark)" }}>›</span>
        </Link>
      </div>
    </div>
  );
}
