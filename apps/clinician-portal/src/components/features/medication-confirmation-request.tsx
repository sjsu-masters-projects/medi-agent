"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/services/api";

/**
 * MED-002: ask the patient to confirm one imported medication, and read their answer.
 *
 * The answer is the patient's own statement. It is shown as evidence next to the candidate and
 * is never applied to the chart; the reconciliation decision below it stays the clinician's.
 */

export type ConfirmationAnswer = "yes" | "stopped" | "changed" | "unsure";

export interface MedicationConfirmation {
  id: string;
  fact_id: string;
  care_team_id: string;
  subject_kind: "imported" | "approved";
  medication_name: string;
  dosage: string | null;
  frequency: string | null;
  status: "open" | "answered" | "expired";
  answer: ConfirmationAnswer | null;
  answer_note: string | null;
  created_at: string;
  expires_at: string;
  answered_at: string | null;
  replayed?: boolean;
}

interface Match {
  target_id: string;
  match_reason: string;
  record: Record<string, unknown>;
}

const ANSWER_LABEL: Record<ConfirmationAnswer, string> = {
  yes: "Yes, still taking it",
  stopped: "No, stopped taking it",
  changed: "It changed",
  unsure: "Not sure",
};

const EYEBROW = "font-mono text-[11px] uppercase tracking-[0.06em] text-muted";
const SECONDARY_BUTTON = "ma-press inline-flex h-[34px] items-center justify-center gap-1.5 rounded-[9px] border border-line-strong bg-surface px-3.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface";

function describe(name: unknown, dosage: unknown, frequency: unknown): string {
  return [name, dosage, frequency]
    .map((part) => (typeof part === "string" ? part.trim() : ""))
    .filter(Boolean)
    .join(" ");
}

function when(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return "";
  return new Date(value).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

export function MedicationConfirmationRequest({
  patientId,
  factId,
  token,
  candidate,
  matches,
}: {
  patientId: string;
  factId: string;
  token: string;
  candidate: Record<string, unknown>;
  matches: Match[];
}) {
  const [items, setItems] = useState<MedicationConfirmation[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [subject, setSubject] = useState("imported");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attempt = useRef<{ key: string; subject: string } | null>(null);
  const generation = useRef(0);
  const base = `/api/v1/smart/patients/${encodeURIComponent(patientId)}/facts/${encodeURIComponent(factId)}/confirmations`;

  const load = useCallback(async () => {
    const request = ++generation.current;
    try {
      const rows = await api.get<MedicationConfirmation[]>(base, { token });
      if (request !== generation.current) return;
      setItems(Array.isArray(rows) ? rows : []);
      setLoadFailed(false);
    } catch {
      if (request === generation.current) setLoadFailed(true);
    }
  }, [base, token]);

  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);

  const open = items?.find((item) => item.status === "open") ?? null;
  const answered = (items ?? []).filter((item) => item.status === "answered");
  const lastExpired = !open && items?.[0]?.status === "expired" ? items[0] : null;

  async function ask() {
    setBusy(true);
    setError(null);
    // A retry of the same choice reuses its key, so a lost response never asks twice.
    if (!attempt.current || attempt.current.subject !== subject) {
      attempt.current = { key: crypto.randomUUID(), subject };
    }
    try {
      await api.post(
        base,
        subject === "imported"
          ? { subject: "imported", client_request_id: attempt.current.key }
          : { subject: "approved", medication_id: subject, client_request_id: attempt.current.key },
        { token },
      );
      attempt.current = null;
      await load();
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : "Unable to send the question.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Patient confirmation" className="rounded-[14px] border border-line bg-surface p-4">
      <h3 className="text-[13px] font-semibold text-ink">Ask the patient to confirm</h3>
      <p className="mt-1 text-sm text-ink-2">
        The patient gets one plain question about this medicine. Their answer is their own statement:
        it is shown here as evidence and is never applied to the chart. You still decide below.
      </p>

      {loadFailed && (
        <p role="status" className="mt-3 text-sm text-muted">
          Patient answers could not be loaded. Reopen this review to try again.
        </p>
      )}

      {answered.map((item) => (
        <div key={item.id} className="mt-3 rounded-xl border border-ok-line bg-ok-soft p-3 text-sm" data-testid="patient-answer">
          <p className={EYEBROW}>Patient answered{item.answered_at ? ` · ${when(item.answered_at)}` : ""}</p>
          <p className="mt-1 break-words text-ink">
            About {item.subject_kind === "approved" ? "the approved list entry" : "the imported record"}:{" "}
            <span className="font-medium">{describe(item.medication_name, item.dosage, item.frequency)}</span>
          </p>
          <p className="mt-1 font-semibold text-ink">{item.answer ? ANSWER_LABEL[item.answer] : ""}</p>
          {item.answer_note && <p className="mt-1 break-words text-ink-2">&ldquo;{item.answer_note}&rdquo;</p>}
          <p className="mt-1 text-xs text-muted">Patient testimony. Not verified and not applied to the chart.</p>
        </div>
      ))}

      {open ? (
        <p className="mt-3 text-sm text-ink-2" role="status">
          Waiting for the patient&rsquo;s answer about{" "}
          <span className="font-medium">{describe(open.medication_name, open.dosage, open.frequency)}</span>
          . Asked {when(open.created_at)}; expires {when(open.expires_at)}.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {lastExpired && (
            <p className="text-sm text-muted" role="status">
              The last question expired {when(lastExpired.expires_at)} without an answer.
            </p>
          )}
          <fieldset className="space-y-2">
            <legend className={EYEBROW}>Ask about</legend>
            <label className="flex min-h-11 cursor-pointer items-start gap-2.5 text-sm text-ink">
              <input
                checked={subject === "imported"}
                className="mt-1 h-4 w-4"
                name={`ask-about-${factId}`}
                onChange={() => setSubject("imported")}
                type="radio"
              />
              <span className="min-w-0 break-words">
                The imported record: <strong>{describe(candidate.name, candidate.dosage, candidate.frequency) || "Unnamed medicine"}</strong>
              </span>
            </label>
            {matches.map((match) => (
              <label key={match.target_id} className="flex min-h-11 cursor-pointer items-start gap-2.5 text-sm text-ink">
                <input
                  checked={subject === match.target_id}
                  className="mt-1 h-4 w-4"
                  name={`ask-about-${factId}`}
                  onChange={() => setSubject(match.target_id)}
                  type="radio"
                />
                <span className="min-w-0 break-words">
                  On the approved list: <strong>{describe(match.record.name, match.record.dosage, match.record.frequency)}</strong>
                </span>
              </label>
            ))}
          </fieldset>
          {error && <p role="alert" className="text-sm text-risk-ink">{error}</p>}
          <button className={SECONDARY_BUTTON} disabled={busy || !describe(candidate.name, null, null)} onClick={() => void ask()} type="button">
            {busy ? "Sending…" : "Ask the patient to confirm"}
          </button>
        </div>
      )}
    </section>
  );
}
