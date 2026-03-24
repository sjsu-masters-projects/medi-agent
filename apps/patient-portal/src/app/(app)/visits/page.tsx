"use client";

import { useState } from "react";

interface Appointment {
  id: string;
  title: string;
  provider: string;
  date: string;
  time: string;
  location: string;
  type: "In-Person" | "Telehealth";
  status: "upcoming" | "past";
  prepNote?: string;
}

const APPOINTMENTS: Appointment[] = [
  {
    id: "1",
    title: "Follow-up: Blood Pressure",
    provider: "Dr. Patel",
    date: "Mar 25, 2026",
    time: "10:30 AM",
    location: "City Medical Center",
    type: "In-Person",
    status: "upcoming",
    prepNote: "Bring medication list. Dr. Patel wants to review your Spironolactone response.",
  },
  {
    id: "2",
    title: "Diabetes Check-in",
    provider: "Dr. Smith",
    date: "Apr 2, 2026",
    time: "2:00 PM",
    location: "Video Call",
    type: "Telehealth",
    status: "upcoming",
  },
  {
    id: "3",
    title: "Annual Physical",
    provider: "Dr. Smith",
    date: "Jan 10, 2026",
    time: "9:00 AM",
    location: "City Medical Center",
    type: "In-Person",
    status: "past",
  },
];

export default function VisitsPage() {
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const [selected, setSelected] = useState<Appointment | null>(null);

  const filtered = APPOINTMENTS.filter((a) => a.status === tab);

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="px-5 pt-12 pb-4">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>Visits</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-secondary)" }}>Appointments & scheduling</p>
      </div>

      {/* Tab switcher */}
      <div className="px-5 mb-4">
        <div className="flex rounded-xl p-1" style={{ background: "#f1f5f9" }}>
          {(["upcoming", "past"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="flex-1 rounded-lg py-2 text-sm font-semibold capitalize transition-all"
              style={
                tab === t
                  ? { background: "white", color: "var(--text-primary)", boxShadow: "0 1px 4px rgba(0,0,0,0.1)" }
                  : { color: "var(--text-muted)" }
              }
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Schedule button */}
      {tab === "upcoming" && (
        <div className="px-5 mb-4">
          <button
            className="w-full rounded-2xl py-3 text-sm font-semibold text-white flex items-center justify-center gap-2"
            style={{ background: "var(--primary)" }}
          >
            📅 Schedule New Appointment
          </button>
        </div>
      )}

      {/* Appointments list */}
      <div className="px-5 flex flex-col gap-3 pb-24">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center py-12 gap-3">
            <span className="text-5xl">📭</span>
            <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
              No {tab} appointments
            </p>
          </div>
        )}

        {filtered.map((appt) => (
          <button
            key={appt.id}
            onClick={() => setSelected(appt)}
            className="w-full rounded-2xl p-4 flex flex-col gap-2 text-left"
            style={{ background: "#f8fafc", border: "1px solid #e2e8f0" }}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{appt.title}</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>{appt.provider}</p>
              </div>
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0"
                style={
                  appt.type === "Telehealth"
                    ? { background: "#e8f0fb", color: "var(--primary)" }
                    : { background: "#f0fdf4", color: "#16a34a" }
                }
              >
                {appt.type === "Telehealth" ? "📹" : "🏥"} {appt.type}
              </span>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                📅 {appt.date}
              </div>
              <div className="flex items-center gap-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                🕐 {appt.time}
              </div>
            </div>

            <p className="text-xs" style={{ color: "var(--text-muted)" }}>📍 {appt.location}</p>

            {appt.prepNote && (
              <div
                className="flex items-start gap-2 rounded-xl p-3 mt-1"
                style={{ background: "#fef3c7" }}
              >
                <span className="text-sm flex-shrink-0">⚠️</span>
                <p className="text-xs leading-relaxed" style={{ color: "#92400e" }}>{appt.prepNote}</p>
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Appointment detail bottom sheet */}
      {selected && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end" style={{ background: "rgba(0,0,0,0.5)" }}>
          <div className="rounded-t-3xl bg-white p-6 flex flex-col gap-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-bold text-lg" style={{ color: "var(--text-primary)" }}>{selected.title}</p>
                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{selected.provider}</p>
              </div>
              <button onClick={() => setSelected(null)} style={{ color: "var(--text-muted)" }}>✕</button>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-primary)" }}>
                📅 <span>{selected.date} at {selected.time}</span>
              </div>
              <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-primary)" }}>
                📍 <span>{selected.location}</span>
              </div>
            </div>

            {selected.prepNote && (
              <div className="rounded-2xl p-4" style={{ background: "#fef9c3", border: "1px solid #fde047" }}>
                <p className="text-xs font-semibold mb-1" style={{ color: "#854d0e" }}>Pre-Visit Prep Note</p>
                <p className="text-sm" style={{ color: "#713f12" }}>{selected.prepNote}</p>
              </div>
            )}

            <div className="flex gap-3">
              <button
                className="flex-1 rounded-2xl py-3 text-sm font-semibold text-white"
                style={{ background: "var(--primary)" }}
              >
                {selected.type === "Telehealth" ? "📹 Join Call" : "🗺️ Get Directions"}
              </button>
              <button
                className="flex-1 rounded-2xl py-3 text-sm font-semibold border"
                style={{ borderColor: "#e2e8f0", color: "var(--text-secondary)" }}
                onClick={() => setSelected(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
