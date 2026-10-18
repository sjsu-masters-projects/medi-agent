"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Input, Modal } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
  cancelVisit,
  completeVisit,
  markVisitNoShow,
  updateVisitDetails,
  type CancelReasonCode,
} from "@/services/appointments";
import type { Appointment } from "@/types";

const BOOKED = ["confirmed", "scheduled"];

export const CANCEL_REASONS: { value: CancelReasonCode; label: string }[] = [
  { value: "clinician_unavailable", label: "I am unavailable" },
  { value: "clinic_closed", label: "The clinic is closed" },
  { value: "patient_request", label: "The patient asked to cancel" },
  { value: "scheduling_error", label: "Scheduled by mistake" },
  { value: "other", label: "Other" },
];

const fieldClass =
  "w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted";

/** The visit has ended: completion and no-show only make sense from then on. */
export function visitHasEnded(visit: Appointment, now: number): boolean {
  return Date.parse(visit.scheduledAt) + visit.durationMinutes * 60_000 <= now;
}

function failureText(failure: unknown, fallback: string): string {
  const code = (failure as { details?: { error?: { code?: string } } } | null)?.details?.error?.code;
  if (code === "APPOINTMENT_UNAVAILABLE") return "This visit changed in the meantime. Refresh and check its status.";
  if (code === "APPOINTMENT_NOT_ENDED") return "This visit has not ended yet.";
  if (code === "APPOINTMENT_TIME_CHANGE_VIA_OFFER") return "Offer new times to change when a booked visit takes place.";
  return fallback;
}

function Problem({ children }: { children: string }) {
  return (
    <p role="alert" className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-3.5 py-2.5 text-[13px] text-risk-ink">
      <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

interface DialogProps {
  token: string;
  visit: Appointment;
  onClose: () => void;
  onChanged: (visit: Appointment) => void;
}

export function EditDetailsDialog({ token, visit, onClose, onChanged }: DialogProps) {
  const [type, setType] = useState(visit.appointmentType);
  const [location, setLocation] = useState(visit.location ?? "");
  const [reason, setReason] = useState(visit.reason ?? "");
  const [notes, setNotes] = useState(visit.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      onChanged(
        await updateVisitDetails(token, visit.id, {
          appointment_type: type,
          location: location.trim(),
          reason: reason.trim(),
          notes: notes.trim(),
        }),
      );
    } catch (failure) {
      setError(failureText(failure, "Could not save the details. Your edits are kept; try again."));
      setSaving(false);
    }
  }
  return (
    <Modal onClose={() => !saving && onClose()} open title="Edit details">
      <form aria-label="Edit visit details" className="space-y-4" onSubmit={(event) => void save(event)}>
        <p className="text-[13px] text-muted">
          The time is not editable here. To move a booked visit, offer new times so the patient can agree.
        </p>
        <label className="block">
          <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Appointment type</span>
          <select
            className={`${fieldClass} h-[42px]`}
            disabled={saving}
            onChange={(event) => setType(event.target.value as Appointment["appointmentType"])}
            value={type}
          >
            <option value="follow_up">Follow-up</option>
            <option value="initial">Initial</option>
            <option value="routine">Routine</option>
            <option value="urgent">Urgent</option>
            <option value="pre_op">Pre-op</option>
          </select>
        </label>
        <Input disabled={saving} label="Location" onChange={(event) => setLocation(event.target.value)} value={location} />
        <Input disabled={saving} label="Reason" onChange={(event) => setReason(event.target.value)} value={reason} />
        <label className="block">
          <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Notes for the patient</span>
          <textarea
            className={`${fieldClass} min-h-[84px] py-2.5`}
            disabled={saving}
            onChange={(event) => setNotes(event.target.value)}
            value={notes}
          />
        </label>
        {error && <Problem>{error}</Problem>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button disabled={saving} onClick={onClose} variant="secondary">Close</Button>
          <Button disabled={saving} type="submit">{saving ? "Saving…" : "Save details"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function CancelVisitDialog({ token, visit, onClose, onChanged }: DialogProps) {
  const [code, setCode] = useState<CancelReasonCode | "">("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ready = code !== "" && (code !== "other" || text.trim().length > 0);
  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!ready || saving) return;
    setSaving(true);
    setError("");
    try {
      onChanged(
        await cancelVisit(token, visit.id, {
          reason_code: code as CancelReasonCode,
          reason: text.trim() || undefined,
        }),
      );
    } catch (failure) {
      setError(failureText(failure, "Could not cancel the visit. Nothing changed; try again."));
      setSaving(false);
    }
  }
  return (
    <Modal onClose={() => !saving && onClose()} open title="Cancel this visit?">
      <form aria-label="Cancel visit" className="space-y-4" onSubmit={(event) => void confirm(event)}>
        <p className="text-[13px] text-ink-2">
          The visit is cancelled, its time is freed, and the patient is told in the app and by email,
          with the reason you give. This cannot be undone.
        </p>
        <label className="block">
          <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Reason (required)</span>
          <select
            className={`${fieldClass} h-[42px]`}
            disabled={saving}
            onChange={(event) => setCode(event.target.value as CancelReasonCode | "")}
            value={code}
          >
            <option value="">Choose a reason</option>
            {CANCEL_REASONS.map((reason) => (
              <option key={reason.value} value={reason.value}>{reason.label}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
            {code === "other" ? "Say why (required)" : "More detail (optional, shown to the patient)"}
          </span>
          <textarea
            className={`${fieldClass} min-h-[72px] py-2.5`}
            disabled={saving}
            maxLength={500}
            onChange={(event) => setText(event.target.value)}
            value={text}
          />
        </label>
        {error && <Problem>{error}</Problem>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button disabled={saving} onClick={onClose} variant="secondary">Keep visit</Button>
          <Button disabled={!ready || saving} type="submit" variant="danger">
            {saving ? "Cancelling…" : "Cancel visit"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function NoShowDialog({ token, visit, onClose, onChanged }: DialogProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function confirm() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      onChanged(await markVisitNoShow(token, visit.id));
    } catch (failure) {
      setError(failureText(failure, "Could not record the no-show. Nothing changed; try again."));
      setSaving(false);
    }
  }
  return (
    <Modal onClose={() => !saving && onClose()} open title="Mark as no-show?">
      <div className="space-y-4">
        <p className="text-[13px] text-ink-2">This records that the patient did not attend. The patient is not notified.</p>
        {error && <Problem>{error}</Problem>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button disabled={saving} onClick={onClose} variant="secondary">Keep as is</Button>
          <Button disabled={saving} onClick={() => void confirm()} variant="danger">
            {saving ? "Saving…" : "Mark no-show"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

type Dialog = "edit" | "cancel" | "no_show" | null;

/**
 * The action row of a visit: one primary action that fits its status, and a small menu for the
 * rest. Cancel is destructive and needs a reason; complete and no-show wait for the end of the visit.
 */
export function VisitActions({
  token,
  visit,
  now,
  onRepropose,
  onChanged,
}: {
  token: string;
  visit: Appointment;
  now: number;
  onRepropose: (visit: Appointment) => void;
  onChanged: (visit: Appointment) => void;
}) {
  const [menu, setMenu] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setMenu(false);
      } else if (!wrapper.current?.contains(event.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menu]);

  const booked = BOOKED.includes(visit.status);
  const editable = booked || visit.status === "proposed";
  const ended = visitHasEnded(visit, now);
  if (!editable) return null;

  async function complete() {
    setCompleting(true);
    setError("");
    try {
      onChanged(await completeVisit(token, visit.id));
    } catch (failure) {
      setError(failureText(failure, "Could not mark the visit completed. Nothing changed; try again."));
      setCompleting(false);
    }
  }
  const items: { key: Dialog; label: string; danger?: boolean }[] = [
    { key: "edit", label: "Edit details" },
    ...(booked && ended ? [{ key: "no_show" as const, label: "Mark no-show" }] : []),
    ...(booked ? [{ key: "cancel" as const, label: "Cancel visit", danger: true }] : []),
  ];
  return (
    <div className="space-y-2 border-t border-line px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        {booked && ended ? (
          <Button disabled={completing} onClick={() => void complete()}>
            <Icon name="check" className="h-4 w-4" />
            {completing ? "Saving…" : "Mark completed"}
          </Button>
        ) : booked ? (
          <Button onClick={() => onRepropose(visit)}>Offer new times</Button>
        ) : null}
        <div className="relative" ref={wrapper}>
          <Button
            aria-expanded={menu}
            aria-haspopup="menu"
            onClick={() => setMenu((open) => !open)}
            variant="secondary"
          >
            More actions
            <Icon name="chevron" className={`h-4 w-4 transition-transform ${menu ? "-rotate-90" : "rotate-90"}`} />
          </Button>
          {menu && (
            <ul
              aria-label="More actions"
              className="absolute left-0 z-20 mt-1 min-w-[190px] overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-[var(--shadow-pop)]"
              role="menu"
            >
              {items.map((item) => (
                <li key={item.key} role="none">
                  <button
                    className={`flex min-h-10 w-full items-center px-4 text-left text-[13px] hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:outline-none ${item.danger ? "font-medium text-risk-ink" : "text-ink"}`}
                    onClick={() => {
                      setMenu(false);
                      setDialog(item.key);
                    }}
                    role="menuitem"
                    type="button"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {error && <Problem>{error}</Problem>}
      {dialog === "edit" && (
        <EditDetailsDialog onChanged={(row) => { setDialog(null); onChanged(row); }} onClose={() => setDialog(null)} token={token} visit={visit} />
      )}
      {dialog === "cancel" && (
        <CancelVisitDialog onChanged={(row) => { setDialog(null); onChanged(row); }} onClose={() => setDialog(null)} token={token} visit={visit} />
      )}
      {dialog === "no_show" && (
        <NoShowDialog onChanged={(row) => { setDialog(null); onChanged(row); }} onClose={() => setDialog(null)} token={token} visit={visit} />
      )}
    </div>
  );
}
