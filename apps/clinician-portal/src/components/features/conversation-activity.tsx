"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { careConversations } from "@/services/care-conversations";
import type { ConversationActivity } from "../../../../../packages/shared/src/types/care-conversations";

export function ConversationActivityReview({ activity, token, conversationId, messageId }: {
  activity: ConversationActivity; token: string; conversationId: string; messageId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  async function openDraft() {
    if (busy) return;
    setBusy(true); setFailed(false);
    try {
      const result = await careConversations.reviewActivity(token, conversationId, messageId);
      router.push(`/patients/${encodeURIComponent(result.patient_id)}?tab=care-plan#care-plan-item-${encodeURIComponent(result.item_id)}`);
    } catch { setFailed(true); }
    finally { setBusy(false); }
  }
  return <aside className="max-w-full rounded-xl border border-line-strong bg-surface-2 px-3 py-2 text-[13px] text-ink-2">
    <p className="text-xs text-muted">Patient-linked care-plan activity</p>
    <p className="break-words font-semibold">{activity.wording?.["en-US"]?.title ?? activity.title}</p>
    <p>{activity.wording?.["en-US"]?.frequency ?? activity.frequency}</p>
    <p className="mt-1 text-xs text-muted">A reply does not change the plan or reminders. Changes require draft review and publication.</p>
    <button className="mt-2 min-h-[34px] rounded-lg bg-primary px-3 py-2 font-semibold text-white disabled:opacity-50" type="button" disabled={busy || !activity.current} onClick={() => void openDraft()}>{busy ? "Opening draft…" : "Review activity in draft"}</button>
    {!activity.current ? <p className="mt-1 text-xs text-muted">This activity is no longer in the approved plan. Open the current care plan instead.</p> : null}
    {failed ? <p role="alert" className="mt-2 text-risk-ink">Could not open this activity. It may have changed or an existing draft needs review. Refresh the conversation or open the patient’s current care plan.</p> : null}
  </aside>;
}
