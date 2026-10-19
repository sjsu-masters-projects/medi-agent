"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { careConversations } from "@/services/care-conversations";
import type { ConversationActivity } from "../../../../../packages/shared/src/types/care-conversations";

type ReviewFailure = "stale" | "revoked" | "draftExists" | "generic";

function failureCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("details" in error)) return null;
  const code = (error.details as { error?: { code?: unknown } } | null)?.error?.code;
  return typeof code === "string" ? code : null;
}

function reviewFailure(error: unknown): ReviewFailure {
  const code = failureCode(error);
  if (code === "ACTIVITY_CONTEXT_STALE") return "stale";
  if (code === "CARE_PLAN_DRAFT_EXISTS") return "draftExists";
  if (code === "AUTHORIZATION_ERROR" || (
    typeof error === "object" && error !== null && "status" in error && error.status === 403
  )) return "revoked";
  return "generic";
}

export function ConversationActivityReview({ activity, token, conversationId, messageId, patientId }: {
  activity: ConversationActivity; token: string; conversationId: string; messageId: string; patientId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ReviewFailure | null>(null);
  const carePlanPath = `/patients/${encodeURIComponent(patientId)}?tab=care-plan`;
  async function openDraft() {
    if (busy) return;
    setBusy(true); setFailure(null);
    try {
      const result = await careConversations.reviewActivity(token, conversationId, messageId);
      router.push(`/patients/${encodeURIComponent(result.patient_id)}?tab=care-plan#care-plan-item-${encodeURIComponent(result.item_id)}`);
    } catch (error) { setFailure(reviewFailure(error)); }
    finally { setBusy(false); }
  }
  return <aside className="max-w-full rounded-xl border border-line-strong bg-surface-2 px-3 py-2 text-[13px] text-ink-2">
    <p className="text-xs text-muted">Patient-linked care-plan activity</p>
    <p className="break-words font-semibold">{activity.wording?.["en-US"]?.title ?? activity.title}</p>
    <p>{activity.wording?.["en-US"]?.frequency ?? activity.frequency}</p>
    <p className="mt-1 text-xs text-muted">A reply does not change the plan or reminders. Changes require draft review and publication.</p>
    <button className="mt-2 min-h-[34px] rounded-lg bg-primary px-3 py-2 font-semibold text-white disabled:opacity-50" type="button" disabled={busy || !activity.current} onClick={() => void openDraft()}>{busy ? "Opening draft…" : "Review activity in draft"}</button>
    <span role="status" aria-live="polite" className="sr-only">{busy ? "Opening the care-plan draft" : ""}</span>
    {!activity.current ? <div className="mt-2 space-y-2 text-xs text-muted">
      <p>This activity is no longer in the approved plan. Open the current care plan instead.</p>
      <button className="font-semibold text-primary underline underline-offset-2" type="button" onClick={() => router.push(carePlanPath)}>Open current care plan</button>
    </div> : null}
    {failure === "stale" ? <div role="alert" className="mt-2 space-y-2 text-risk-ink">
      <p>This activity is no longer in the approved plan. Open the patient’s current care plan.</p>
      <button className="font-semibold underline underline-offset-2" type="button" onClick={() => router.push(carePlanPath)}>Open current care plan</button>
    </div> : null}
    {failure === "draftExists" ? <div role="alert" className="mt-2 space-y-2 text-risk-ink">
      <p>A current care-plan draft already needs review. Open that draft before adding this activity.</p>
      <button className="font-semibold underline underline-offset-2" type="button" onClick={() => router.push(carePlanPath)}>Open current draft</button>
    </div> : null}
    {failure === "revoked" ? <p role="alert" className="mt-2 text-risk-ink">You no longer have access to review this patient’s care plan.</p> : null}
    {failure === "generic" ? <p role="alert" className="mt-2 text-risk-ink">Could not open this activity. Refresh the conversation and try again.</p> : null}
  </aside>;
}
