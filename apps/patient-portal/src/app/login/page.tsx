"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [language, setLanguage] = useState("English (US)");

  function handleSendMagicLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setEmailSent(true);
    // TODO: call POST /api/v1/auth/magic-link
  }

  function handleJoinClinic(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteCode) return;
    // TODO: call POST /api/v1/patients/join-clinic
    router.push("/today");
  }

  return (
    <div className="app-shell flex flex-col min-h-dvh" style={{ background: "var(--bg-auth)" }}>
      {/* Blue header */}
      <div
        className="flex flex-col items-center justify-center gap-3 px-8 py-10"
        style={{
          background: "linear-gradient(160deg, #3373d1 0%, #2b62b8 100%)",
          borderBottomLeftRadius: "2rem",
          borderBottomRightRadius: "2rem",
        }}
      >
        {/* Robot icon */}
        <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-white/20 text-4xl shadow-inner">
          🤖
        </div>
        <h1 className="text-3xl font-bold text-white tracking-tight">MediAgent</h1>
        <p className="text-white/80 text-sm">Your intelligent health companion</p>
      </div>

      {/* Card */}
      <div className="flex-1 flex flex-col px-5 py-6 gap-6">
        <div className="bg-white rounded-3xl shadow-lg p-6 flex flex-col gap-5">
          {emailSent ? (
            <div className="flex flex-col items-center gap-4 py-4 text-center">
              <div className="text-5xl">✉️</div>
              <h2 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>Check your email</h2>
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                We sent a magic link to <strong>{email}</strong>. Click it to sign in.
              </p>
              <button
                onClick={() => setEmailSent(false)}
                className="text-sm font-medium"
                style={{ color: "var(--primary)" }}
              >
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <div>
                <h2 className="text-xl font-bold text-center mb-1" style={{ color: "var(--text-primary)" }}>Welcome</h2>
                <p className="text-sm text-center" style={{ color: "var(--text-secondary)" }}>Sign in instantly via magic link.</p>
              </div>

              <form onSubmit={handleSendMagicLink} className="flex flex-col gap-3">
                <label className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                  Email Address
                </label>
                <div className="flex items-center gap-2 rounded-xl border px-3 py-3" style={{ borderColor: "#e2e8f0", background: "#f8fafc" }}>
                  <span className="text-base" style={{ color: "var(--text-muted)" }}>✉️</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="sarah@example.com"
                    className="flex-1 bg-transparent text-sm outline-none"
                    style={{ color: "var(--text-primary)" }}
                  />
                </div>
                <button
                  type="submit"
                  className="w-full rounded-xl py-3 text-sm font-semibold text-white flex items-center justify-center gap-2 transition-opacity hover:opacity-90"
                  style={{ background: "var(--primary)" }}
                >
                  <span>✨</span> Send Magic Link
                </button>
              </form>

              <div className="flex items-center gap-3">
                <div className="flex-1 h-px" style={{ background: "#e2e8f0" }} />
                <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>OR</span>
                <div className="flex-1 h-px" style={{ background: "#e2e8f0" }} />
              </div>

              <form onSubmit={handleJoinClinic} className="flex flex-col gap-3">
                <div className="rounded-2xl border p-4 flex flex-col gap-3" style={{ borderColor: "#e2e8f0" }}>
                  <div>
                    <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Have a clinic invite code?</p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                      Enter the code provided by your doctor to link your records.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={inviteCode}
                      onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                      placeholder="E.G. CITY-8832"
                      className="flex-1 rounded-xl border px-3 py-2.5 text-sm outline-none"
                      style={{ borderColor: "#e2e8f0", background: "#f8fafc", color: "var(--text-primary)" }}
                    />
                    <button
                      type="submit"
                      className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white"
                      style={{ background: "#0f172a" }}
                    >
                      Join
                    </button>
                  </div>
                </div>
              </form>
            </>
          )}
        </div>

        {/* Dev shortcut */}
        <button
          onClick={() => router.push("/today")}
          className="text-xs text-center"
          style={{ color: "var(--text-muted)" }}
        >
          Continue as guest →
        </button>
      </div>

      {/* Language selector */}
      <div className="flex justify-center pb-6">
        <button
          className="flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-medium"
          style={{ background: "#f1f5f9", color: "var(--text-secondary)" }}
          onClick={() => setLanguage(language === "English (US)" ? "Español" : "English (US)")}
        >
          🌐 {language} ▾
        </button>
      </div>
    </div>
  );
}
