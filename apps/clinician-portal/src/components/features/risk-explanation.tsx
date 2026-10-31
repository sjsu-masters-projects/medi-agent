"use client";

import { Modal } from "@/components/ui/modal";
import type { PatientRiskData } from "@/services/clinicians";
import { formatClinicianDateTime } from "@/utils/dates";

const SOURCE_LABELS: Record<string, string> = {
    adherence_logs: "Latest adherence response (30-day window)",
    symptom_reports: "Latest confirmed, rated symptom (7-day window)",
    adr_assessments: "Latest open ADR case update",
    medications: "Latest active medication recorded",
};

function When({ value }: { value: string }) {
    return <time dateTime={value}>{formatClinicianDateTime(value, { dateStyle: "medium", timeStyle: "short" })}</time>;
}

function humanize(code: string) {
    const words = code.replaceAll("_", " ").trim();
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : code;
}

export function RiskExplanationDialog({ patient, onClose }: { patient: PatientRiskData | null; onClose: () => void }) {
    const explanation = patient?.risk_explanation;
    const calculated = explanation ? Date.parse(explanation.calculated_at) : NaN;
    return <Modal open={!!patient} onClose={onClose} title="Why this review priority?">
        <p className="text-sm font-semibold text-ink">{patient?.first_name} {patient?.last_name}</p>
        <p className="mt-2 text-sm text-ink-2">Rule-based review priority, not a diagnosis or a validated prediction. ADR cases still require clinician review.</p>
        {explanation ? <>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink-2">
                {explanation.factors.map((factor) => <li key={factor}>{factor}</li>)}
            </ul>
            <dl className="mt-4 space-y-2 border-t border-line pt-3 text-xs text-muted">
                <div><dt className="font-medium">Calculated</dt><dd>{Number.isFinite(calculated) ? <When value={explanation.calculated_at} /> : "Calculation time unavailable"}</dd></div>
                {explanation.source_freshness?.map((source) => {
                    const timestamp = source.latest_at ? Date.parse(source.latest_at) : NaN;
                    return <div key={source.source}>
                        <dt className="font-medium">{SOURCE_LABELS[source.source] ?? humanize(source.source)}</dt>
                        <dd>{source.status === "unavailable" ? "Couldn't be read — refresh the dashboard" : source.status === "available" && Number.isFinite(timestamp) ? <When value={source.latest_at!} /> : "No dated record available"}</dd>
                    </div>;
                })}
            </dl>
            {!explanation.source_freshness?.length && <p className="mt-3 text-xs text-muted">Source dates aren&apos;t available for this calculation.</p>}
            <p className="mt-3 text-xs text-muted">Calculated from available records; this time is not the last clinical review. Each date above is a separate read, so together they are not a single point-in-time view. A date shows a record was found, not that it is current or reviewed. A medication&apos;s recorded date is not its last review or dose change, and adherence covers recorded responses, not every expected dose.</p>
            {/* Audit value only: which rule set produced this priority. */}
            <details className="ma-disclosure mt-3 text-xs text-muted">
                <summary className="min-h-9 py-1.5 text-[13px] font-medium">Technical details</summary>
                <p className="pb-1">Rule version: <span className="font-mono">{explanation.rule_version}</span></p>
            </details>
        </> : <p className="mt-4 text-sm text-muted">The explanation for this priority isn&apos;t available. Refresh the dashboard, and don&apos;t draw a clinical conclusion from its absence.</p>}
    </Modal>;
}
