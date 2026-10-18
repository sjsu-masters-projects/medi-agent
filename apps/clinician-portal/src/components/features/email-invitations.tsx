"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { api } from "@/services/api";
import { clinicErrorMessage, withClinic } from "@/services/clinics";

interface Invitation {
  id: string; email: string; role: string; expires_at: string;
  accepted_at: string | null; revoked_at: string | null; delivery_state: string | null;
}
const UNAVAILABLE = "Invitation history is unavailable. Refresh to try again.";
function message(e: unknown): string {
  // Refusals (not an admin of that clinic, clinic required) say why; outages stay generic.
  return [403, 422].includes((e as { status?: number } | null)?.status ?? 0) ? clinicErrorMessage(e, UNAVAILABLE) : UNAVAILABLE;
}
const deliveryLabels: Record<string, string> = {
  queued: "Queued", sending: "Sending", accepted: "Provider accepted — delivery not confirmed",
  delivered: "Provider confirmed delivery", bounced: "Bounced — invite again to send a new link", failed: "Delivery failed — invite again to send a new link", suppressed: "Delivery stopped",
};

export function EmailInvitations({ clinicId = null, token, revision }: { clinicId?: string | null; token: string; revision: string | null }) {
  const [items, setItems] = useState<Invitation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = generation.current;
    setError(null);
    try {
      const result = await api.get<{ items: Invitation[] }>(withClinic("/api/v1/email/invitations", clinicId), { token });
      if (current === generation.current) setItems(result.items);
    } catch (e) { if (current === generation.current) setError(message(e)); }
  }, [clinicId, token]);
  useEffect(() => {
    generation.current += 1; setItems(null); setBusy(null); void load();
    return () => { generation.current += 1; };
  }, [load, revision]);
  async function revoke(id: string) {
    const current = generation.current;
    setBusy(id); setError(null);
    try {
      await api.post(`/api/v1/email/invitations/${id}/revoke`, {}, { token });
      if (current === generation.current) await load();
    } catch (e) { if (current === generation.current) setError(message(e)); }
    finally { if (current === generation.current) setBusy(null); }
  }
  return <section aria-labelledby="email-invitations-title" className="rounded-[20px] border border-line bg-surface p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 id="email-invitations-title" className="text-base font-semibold text-ink">Team email invitations</h3>
      <Button variant="secondary" onClick={() => void load()}>Refresh invitations</Button>
    </div>
    <p className="mt-2 text-sm text-muted">Sending an invitation does not grant access. Acceptance and email delivery are separate.</p>
    {error ? <p role="alert" className="mt-3 text-sm text-muted">{error}</p> : null}
    {!items && !error ? <p role="status" className="mt-3 text-sm text-muted">Loading invitations…</p> : null}
    {items?.length === 0 ? <p className="mt-3 text-sm text-muted">No team email invitations yet.</p> : null}
    <ul className="mt-3 divide-y divide-line">
      {items?.map(item => {
        const expired = new Date(item.expires_at).getTime() <= Date.now();
        const state = item.accepted_at ? "Accepted" : item.revoked_at ? "Revoked" : expired ? "Expired" : "Awaiting acceptance";
        return <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div className="min-w-0 space-y-1">
            <p className="break-all text-sm font-medium text-ink">{item.email}</p>
            <p className="text-sm text-muted">{item.role} · {state}</p>
            <p className="text-xs text-muted">{deliveryLabels[item.delivery_state ?? ""] ?? "Delivery status unavailable"}</p>
            <p className="text-xs text-muted">Expires {new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.expires_at))}</p>
          </div>
          {!item.accepted_at && !item.revoked_at && !expired ? <Button variant="secondary" disabled={busy !== null} onClick={() => void revoke(item.id)}>
            {busy === item.id ? "Revoking…" : "Revoke invitation"}
          </Button> : null}
        </li>;
      })}
    </ul>
  </section>;
}
