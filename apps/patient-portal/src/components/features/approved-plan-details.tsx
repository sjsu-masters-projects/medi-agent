"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { api } from "@/services/api";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { getTodayCopy } from "@/content/today-copy";
import { getCareTeamCopy, ownerLabel } from "@/content/care-team-copy";
import type { Locale, PatientApprovedPlanSummary, PlanOwner } from "@/types";

interface Wording { title: string; instructions: string; frequency: string }
export interface ApprovedPatientPlan {
  id: string;
  status: string;
  version_number: number;
  approved_at: string | null;
  /** PLAN-002: one entry per approved plan; more than one groups the details by care team. */
  plans?: PatientApprovedPlanSummary[];
  items: (Wording & { id: string; is_removed: boolean; plan_owner?: PlanOwner | null; source_locale?: Locale | null; reviewed_locale?: Locale | null; wording?: Partial<Record<Locale, Wording>>; wording_verified?: boolean })[];
}

export function ApprovedPlanDetails({ locale }: { locale: Locale }) {
  const { user, accessToken } = useSelector((state: RootState) => state.auth);
  const [result, setResult] = useState<{ token: string; plan: ApprovedPatientPlan | null } | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const copy = getTodayCopy(locale);
  const spanish = locale === "es-MX";
  useEffect(() => {
    if (!user || !accessToken) return;
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return null;
      setFailed(false); setResult(null);
      return api.get<ApprovedPatientPlan | null>(`/api/v1/care-plans/patients/${encodeURIComponent(user.id)}`, { token: accessToken, signal: controller.signal });
    })
      .then((plan) => {
        if (controller.signal.aborted) return;
        if (plan && (plan.status !== "approved" || !plan.approved_at)) throw new Error("Approved plan unavailable");
        setResult({ token: accessToken, plan });
      }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [user, accessToken, attempt]);
  const current = result?.token === accessToken ? result : null;
  if (failed) return <div className="space-y-3"><p role="alert" className="text-sm text-danger-ink">{spanish ? "No se pudo cargar el plan aprobado." : "The approved plan could not be loaded."}</p><button type="button" className="min-h-11 rounded-xl bg-surface-2 px-4 text-sm font-semibold" onClick={() => setAttempt((value) => value + 1)}>{copy.retry}</button></div>;
  if (!current) return <p role="status" className="text-sm text-muted">{copy.loading}</p>;
  if (!current.plan) return <p className="text-sm text-muted">{spanish ? "No hay un plan aprobado disponible." : "No approved plan is available."}</p>;
  const visible = current.plan.items.filter((item) => !item.is_removed);
  const renderItems = (items: typeof visible) => <ul className="divide-y divide-line">
      {items.map((item) => {
        const wording = item.wording_verified ? item.wording?.[locale] : undefined;
        const content = wording ?? item;
        const sourceLocale = item.source_locale ?? item.reviewed_locale;
        return <li className="space-y-1 py-3" key={item.id} lang={wording ? locale : sourceLocale ?? undefined}>
          <h3 className="break-words text-base font-semibold text-ink">{content.title}</h3>
          {!wording && sourceLocale && sourceLocale !== locale && <p className="text-xs text-muted">{copy.writtenIn(sourceLocale)}</p>}
          <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-ink-2">{content.instructions}</p>
          <p className="text-sm text-muted">{content.frequency}</p>
        </li>;
      })}
    </ul>;
  const groups = groupByCareTeam(current.plan, visible);
  if (groups.length < 2) {
    return <div className="space-y-4">
      <ApprovalSeal>{copy.planDetail(current.plan.version_number)}</ApprovalSeal>
      {renderItems(visible)}
    </div>;
  }
  const careCopy = getCareTeamCopy(locale);
  return <div className="space-y-6">
    {groups.map((group) => <section key={group.owner.care_plan_id} aria-labelledby={`plan-group-${group.owner.care_plan_id}`} className="space-y-2 rounded-2xl border border-line-strong p-4">
      <div className="space-y-1">
        <h3 id={`plan-group-${group.owner.care_plan_id}`} className="break-words text-[15px] font-semibold text-ink [overflow-wrap:anywhere]">{ownerLabel(group.owner)}</h3>
        {group.summary ? <ApprovalSeal>{careCopy.planGroupVersion(group.summary.version_number, group.summary.approved_at ? new Date(group.summary.approved_at).toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" }) : null)}</ApprovalSeal> : null}
        {group.owner.unowned_notice ? <p className="break-words text-[12.5px] leading-snug text-muted">{careCopy.unownedNotice(group.owner.clinician_name)}</p> : null}
      </div>
      {renderItems(group.items)}
    </section>)}
  </div>;
}

/** Items grouped by owning plan; fewer than two groups means the single-plan layout is kept. */
function groupByCareTeam(plan: ApprovedPatientPlan, items: ApprovedPatientPlan["items"]) {
  // Never drop an item: if any lacks an owner, keep the single-plan layout.
  if (items.some((item) => !item.plan_owner)) return [];
  const groups = new Map<string, { owner: PlanOwner; summary?: PatientApprovedPlanSummary; items: ApprovedPatientPlan["items"] }>();
  for (const item of items) {
    const owner = item.plan_owner as PlanOwner;
    const group = groups.get(owner.care_plan_id) ?? { owner, summary: plan.plans?.find((entry) => entry.care_plan_id === owner.care_plan_id), items: [] };
    group.items.push(item);
    groups.set(owner.care_plan_id, group);
  }
  return [...groups.values()];
}
