"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/services/api";

export function ClinicalCoreExport({
  patientId,
  token,
}: {
  patientId: string;
  token: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    setBusy(false);
    setError(false);
    return () => {
      generation.current += 1;
    };
  }, [patientId, token]);

  async function download() {
    if (!token || busy) return;
    const request = ++generation.current;
    setBusy(true);
    setError(false);
    try {
      const bundle = await api.get<Record<string, unknown>>(
        `/api/v1/smart/patients/${encodeURIComponent(patientId)}/record-export`,
        { token },
      );
      if (request !== generation.current) return;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(bundle)], { type: "application/fhir+json" }),
      );
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = `clinical-core-${patientId}.fhir.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch {
      if (request === generation.current) setError(true);
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }

  return (
    <section
      aria-label="Clinical record export"
      className="space-y-2 rounded-xl border border-line p-4 text-sm"
    >
      <button
        type="button"
        disabled={busy || !token}
        onClick={() => void download()}
        className="min-h-10 rounded-lg border border-line-strong px-3 py-2 font-medium text-primary disabled:opacity-50"
      >
        {busy
          ? "Preparing FHIR file…"
          : error
            ? "Retry clinical record export"
            : "Download clinical record (FHIR)"}
      </button>
      <p className="text-muted">
        Current active medicines, allergies and conditions you may see. Import
        candidates and private source documents are excluded. This is a
        clinical-core subset, not the complete chart, a prescription or an
        approved handoff summary.
      </p>
      {busy && <p role="status">Preparing the authorized clinical record…</p>}
      {error && (
        <p role="alert">
          The clinical record could not be exported. No partial file was
          downloaded. Retry or refresh your session.
        </p>
      )}
    </section>
  );
}
