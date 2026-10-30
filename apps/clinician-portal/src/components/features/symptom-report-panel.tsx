"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, ErrorState, Modal } from "@/components/ui";
import { CareTeamSelect, useCareTeamChoice } from "@/components/features/care-team-select";
import {
    fetchSymptomReport,
    markSymptomReportReviewed,
    type ClinicianSymptomReport,
} from "@/services/clinicians";

function when(value: string | null, timezone?: string | null) {
    if (!value) return "Not recorded";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not recorded";
    const format = (zone: string) =>
        new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: zone, timeZoneName: "short" }).format(date);
    try {
        return format(timezone || "UTC");
    } catch {
        return format("UTC");
    }
}

const EVENT_LABEL: Record<string, string> = {
    reported: "Patient confirmed the report",
    shared_with_care_team: "Review task and notices sent to the patient's active care teams",
    not_sent_no_care_team: "Not sent: the patient had no active care team at confirmation",
    flagged_urgent: "Urgent-answer alert delivered",
    reviewed: "Marked reviewed",
};

const LANGUAGE_NAMES: Record<string, string> = { "en-US": "English", "es-MX": "Spanish (Mexico)" };
const URGENCY_LABEL: Record<string, string> = { urgent: "Urgent", emergency: "Emergency" };
const DELIVERY_LABEL: Record<string, string> = {
    delivered: "delivered",
    sent: "sent",
    queued: "waiting to send",
    pending: "waiting to send",
    failed: "not delivered",
};

function humanize(code: string) {
    const words = code.replaceAll("_", " ").trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : code;
}

function languageName(locale: string | null | undefined) {
    return locale ? LANGUAGE_NAMES[locale] ?? locale : "Not recorded";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="py-2">
            <dt className="text-xs font-medium text-muted">{label}</dt>
            <dd className="mt-0.5 break-words text-sm text-ink [overflow-wrap:anywhere]">{children}</dd>
        </div>
    );
}

/** Structured detail of one patient-confirmed symptom report, with an audited "Mark reviewed". */
export function SymptomReportPanel({ patientId, reportId, onClose, onReviewed }: {
    patientId: string;
    reportId: string;
    onClose: () => void;
    onReviewed?: () => void;
}) {
    const [report, setReport] = useState<ClinicianSymptomReport | null>(null);
    const [failed, setFailed] = useState<"load" | "review" | null>(null);
    const [saving, setSaving] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const team = useCareTeamChoice(patientId);

    useEffect(() => {
        let active = true;
        fetchSymptomReport(patientId, reportId).then(
            (result) => { if (active) { setReport(result); setFailed(null); } },
            () => { if (active) setFailed("load"); },
        );
        return () => { active = false; };
    }, [patientId, reportId, attempt]);

    const review = useCallback(async () => {
        if (saving) return;
        setSaving(true);
        setFailed(null);
        try {
            setReport(await markSymptomReportReviewed(patientId, reportId, team.careTeamId));
            onReviewed?.();
        } catch (error) {
            // A clinician with several links must choose one; the select then appears.
            if (!team.handleError(error)) setFailed("review");
        } finally {
            setSaving(false);
        }
    }, [patientId, reportId, saving, onReviewed, team]);

    const reviewed = Boolean(report?.reviewed_by_your_team);
    const others = report?.reviews.filter((item) => !item.mine) ?? [];
    return (
        <Modal open onClose={onClose} placement="side" title="Patient-confirmed symptom report">
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
                {failed === "load" ? (
                    <ErrorState title="Unable to load this report" description="No conclusion can be drawn from a failed load." onRetry={() => { setFailed(null); setAttempt((n) => n + 1); }} />
                ) : !report ? (
                    <p role="status" className="text-sm text-muted">Loading report…</p>
                ) : (
                    <>
                        <header className="space-y-2">
                            <h3 className="break-words text-base font-semibold text-ink" lang={report.locale}>{report.symptom}</h3>
                            <div className="flex flex-wrap items-center gap-2">
                                <Badge variant={report.severity === null ? "neutral" : report.severity >= 8 ? "danger" : report.severity >= 5 ? "warning" : "success"}>
                                    {report.severity === null ? "Severity unknown / not provided" : `Severity ${report.severity}/10`}
                                </Badge>
                                <Badge variant={reviewed ? "success" : "warning"}>{reviewed ? "Reviewed by you" : "Not reviewed by your team"}</Badge>
                                {report.flagged_for_adr && <Badge variant="danger">ADR flagged</Badge>}
                            </div>
                            <p className="text-xs text-muted">Confirmed by the patient {when(report.confirmed_at, report.timezone)}. Patient testimony, not a diagnosis; a cause has not been established.</p>
                        </header>

                        <section aria-labelledby="report-answers">
                            <h4 id="report-answers" className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Confirmed answers · {languageName(report.locale)}</h4>
                            {report.answers.length === 0 ? <p className="mt-2 text-sm text-muted">No answers were saved with this report.</p> : (
                                <dl lang={report.locale} className="divide-y divide-line">
                                    {report.answers.map((answer) => (
                                        <Row key={answer.question_id} label={answer.label}>{answer.display}</Row>
                                    ))}
                                </dl>
                            )}
                            {report.related_medication_name && <p className="mt-2 text-xs text-muted">Patient-named product: {report.related_medication_name}. Unverified until a clinician links it.</p>}
                        </section>

                        <section aria-labelledby="report-triage">
                            <h4 id="report-triage" className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Safety outcome</h4>
                            <dl className="divide-y divide-line">
                                <Row label="Emergency rule check at confirmation">
                                    {report.triage.safety_result === "no_existing_rule_matched"
                                        ? "No existing emergency rule matched. This is not a clinical triage."
                                        : report.triage.safety_result
                                          ? humanize(report.triage.safety_result)
                                          : "Not recorded"}
                                </Row>
                                <Row label="Urgent-answer alert">
                                    {report.triage.escalation_urgency
                                        ? `${URGENCY_LABEL[report.triage.escalation_urgency] ?? humanize(report.triage.escalation_urgency)}, ${
                                              report.triage.escalation_delivery
                                                  ? DELIVERY_LABEL[report.triage.escalation_delivery] ?? humanize(report.triage.escalation_delivery).toLowerCase()
                                                  : "delivery not recorded"
                                          }, ${when(report.triage.escalation_at, report.timezone)}`
                                        : "None recorded"}
                                </Row>
                            </dl>
                        </section>

                        <section aria-labelledby="report-provenance">
                            <h4 id="report-provenance" className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Report details</h4>
                            <dl className="divide-y divide-line">
                                <Row label="Confirmed">{when(report.provenance.confirmed_at, report.provenance.timezone)}</Row>
                                <Row label="Patient language">{languageName(report.provenance.language)}</Row>
                                <Row label="Patient consent to share">{report.provenance.consent_recorded ? "Explicit consent recorded at confirmation" : "Not recorded"}</Row>
                            </dl>
                            {/* Audit and support identifiers; not needed to review the report. */}
                            <details className="ma-disclosure mt-2 rounded-lg bg-surface-2 px-3 py-1 text-xs text-muted">
                                <summary className="min-h-9 py-1.5 text-[13px] font-medium">Technical details</summary>
                                <dl className="space-y-1.5 pb-2 [overflow-wrap:anywhere]">
                                    <div><dt className="font-medium text-ink-2">Report ID</dt><dd className="font-mono">{report.provenance.report_id}</dd></div>
                                    <div><dt className="font-medium text-ink-2">Source chat message ID</dt><dd className="font-mono">{report.provenance.source_message_id ?? "Not recorded"}</dd></div>
                                    <div><dt className="font-medium text-ink-2">Question set version</dt><dd className="font-mono">{[report.provenance.schema_version, report.provenance.library_version].filter(Boolean).join(" · ") || "Not recorded"}</dd></div>
                                    <div><dt className="font-medium text-ink-2">Emergency rule version</dt><dd className="font-mono">{report.triage.safety_rule_version ?? "Not recorded"}</dd></div>
                                </dl>
                            </details>
                        </section>

                        <section aria-labelledby="report-events">
                            <h4 id="report-events" className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Recorded events</h4>
                            <ol className="mt-2 space-y-2">
                                {report.events.map((event) => (
                                    <li key={`${event.kind}-${event.at}`} className="text-sm text-ink-2">
                                        {EVENT_LABEL[event.kind] ?? humanize(event.kind)}{event.actor_name ? ` by ${event.actor_name}` : ""}{event.team_label ? ` (${event.team_label})` : ""}
                                        <span className="block text-xs text-muted"><time dateTime={event.at}>{when(event.at, report.timezone)}</time></span>
                                    </li>
                                ))}
                            </ol>
                        </section>
                    </>
                )}
            </div>
            {report && (
                <footer className="shrink-0 space-y-2 border-t border-line px-5 py-3">
                    {others.map((item) => (
                        <p key={item.care_team_id} className="text-sm text-ink-2">
                            Also reviewed by {[item.team_label, item.reviewed_by_name].filter(Boolean).join(" · ") || "another care team"} <span className="text-xs text-muted">{when(item.reviewed_at, report.timezone)}</span>
                        </p>
                    ))}
                    {failed === "review" && <p role="alert" className="text-sm text-risk-ink">Could not mark this report reviewed. Nothing was changed; try again.</p>}
                    {report.your_care_team_ids.length > 1 && <CareTeamSelect onChange={team.setValue} options={team.options} required={team.required} value={team.value} />}
                    {reviewed && report.your_care_team_ids.length <= 1 ? (
                        <p role="status" className="text-sm text-ok-ink">
                            {report.already_reviewed ? "Already reviewed by you" : "Reviewed by you"} {when(report.reviews.find((item) => item.mine)?.reviewed_at ?? null, report.timezone)}. Review records your team&apos;s follow-up only; it does not approve a diagnosis or medication change.
                        </p>
                    ) : (
                        <Button fullWidth disabled={saving || team.missing} onClick={() => void review()}>{saving ? "Saving…" : "Mark reviewed"}</Button>
                    )}
                </footer>
            )}
        </Modal>
    );
}
