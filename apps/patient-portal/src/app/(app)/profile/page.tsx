"use client";

import { useRouter } from "next/navigation";

const PROFILE = {
  name: "Sarah Johnson",
  email: "sarah@example.com",
  dob: "March 15, 1985",
  language: "English (US)",
  providers: [
    { name: "Dr. Emily Smith", specialty: "Primary Care", clinic: "City Medical Center" },
    { name: "Dr. Raj Patel", specialty: "Cardiology", clinic: "City Medical Center" },
  ],
  conditions: ["Type 2 Diabetes", "Hypertension"],
  allergies: ["Penicillin (Severe)", "Sulfa drugs (Moderate)"],
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-5">
      <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>
        {title}
      </p>
      <div className="rounded-2xl overflow-hidden border" style={{ borderColor: "#e2e8f0" }}>
        {children}
      </div>
    </div>
  );
}

function Row({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b last:border-0" style={{ borderColor: "#f1f5f9" }}>
      <span className="text-lg w-7 text-center flex-shrink-0">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</p>
        <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{value}</p>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const router = useRouter();

  return (
    <div className="min-h-screen" style={{ background: "#f8fafc" }}>
      {/* Header */}
      <div
        className="flex flex-col items-center pt-12 pb-6 px-5"
        style={{ background: "white", borderBottom: "1px solid #f1f5f9" }}
      >
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center text-3xl font-bold text-white mb-3"
          style={{ background: "var(--primary)" }}
        >
          S
        </div>
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>{PROFILE.name}</h1>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{PROFILE.email}</p>
      </div>

      <div className="flex flex-col gap-5 py-5 pb-24">
        {/* Personal Info */}
        <Section title="Personal Info">
          <Row icon="🎂" label="Date of Birth" value={PROFILE.dob} />
          <Row icon="🌐" label="Language" value={PROFILE.language} />
        </Section>

        {/* Care Team */}
        <Section title="Care Team">
          {PROFILE.providers.map((p) => (
            <div key={p.name} className="flex items-center gap-3 px-4 py-3 border-b last:border-0" style={{ borderColor: "#f1f5f9" }}>
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                style={{ background: "var(--primary)" }}
              >
                {p.name.split(" ").pop()![0]}
              </div>
              <div>
                <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{p.name}</p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{p.specialty} · {p.clinic}</p>
              </div>
            </div>
          ))}
        </Section>

        {/* Conditions */}
        <Section title="Conditions">
          {PROFILE.conditions.map((c) => (
            <div key={c} className="flex items-center gap-3 px-4 py-3 border-b last:border-0" style={{ borderColor: "#f1f5f9" }}>
              <span className="text-lg">🩺</span>
              <p className="text-sm" style={{ color: "var(--text-primary)" }}>{c}</p>
            </div>
          ))}
        </Section>

        {/* Allergies */}
        <Section title="Allergies">
          {PROFILE.allergies.map((a) => (
            <div key={a} className="flex items-center gap-3 px-4 py-3 border-b last:border-0" style={{ borderColor: "#f1f5f9" }}>
              <span className="text-lg">⚠️</span>
              <p className="text-sm" style={{ color: "var(--text-primary)" }}>{a}</p>
            </div>
          ))}
        </Section>

        {/* Sign out */}
        <div className="px-5">
          <button
            onClick={() => router.push("/login")}
            className="w-full rounded-2xl py-3 text-sm font-semibold border"
            style={{ borderColor: "#fca5a5", color: "#ef4444", background: "#fef2f2" }}
          >
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}
