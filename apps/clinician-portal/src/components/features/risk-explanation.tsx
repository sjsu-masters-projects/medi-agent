"use client";

import { Modal } from "@/components/ui/modal";
import type { PatientRiskData } from "@/services/clinicians";

const SOURCE_LABELS: Record<string, string> = {
    adherence_logs: "Latest adherence response (30-day window)",
    symptom_reports: "Latest confirmed, rated symptom (7-day window)",
    adr_assessments: "Latest open ADR candidate update",
    medications: "Latest active medication recorded",
};

export function RiskExplanationDialog({ patient, onClose }: { patient: PatientRiskData | null; onClose: () => void }) {
    const explanation = patient?.risk_explanation;
    const calculated = explanation ? Date.parse(explanation.calculated_at) : NaN;
    return <Modal open={!!patient} onClose={onClose} title="Why this review priority?">
        <p className="text-sm font-semibold text-ink">{patient?.first_name} {patient?.last_name}</p>
        <p className="mt-2 text-sm text-ink-2">Rule-based review priority, not a diagnosis or a validated prediction. ADR candidates still require clinician review.</p>
        {explanation ? <>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink-2">
                {explanation.factors.map((factor) => <li key={factor}>{factor}</li>)}
            </ul>
            <dl className="mt-4 space-y-2 border-t border-line pt-3 text-xs text-muted">
                <div><dt className="font-medium">Rule version</dt><dd>{explanation.rule_version}</dd></div>
                <div><dt className="font-medium">Calculated</dt><dd>{Number.isFinite(calculated) ? <time dateTime={explanation.calculated_at}>{new Date(calculated).toLocaleString("en-US")}</time> : "Calculation time unavailable"}</dd></div>
                {explanation.source_freshness?.map((source) => {
                    const timestamp = source.latest_at ? Date.parse(source.latest_at) : NaN;
                    return <div key={source.source}>
                        <dt className="font-medium">{SOURCE_LABELS[source.source] ?? source.source}</dt>
                        <dd>{source.status === "unavailable" ? "Source freshness unavailable — read failed" : source.status === "available" && Number.isFinite(timestamp) ? <time dateTime={source.latest_at!}>{new Date(timestamp).toLocaleString("en-US")}</time> : "Unknown — no dated source available"}</dd>
                    </div>;
                })}
            </dl>
            {!explanation.source_freshness?.length && <p className="mt-3 text-xs text-muted">Source freshness unknown for this snapshot.</p>}
            <p className="mt-3 text-xs text-muted">Source dates are separate reads of the available rule inputs, not an atomic snapshot or proof of clinical currency. An available date means a dated source was read, not that it is clinically fresh or reviewed. Medication recording time is not its last review or dose change.</p>
            <p className="mt-3 text-xs text-muted">Calculated from available records. This time is not the last clinical review or proof that every source is current. Adherence describes recorded responses, not all expected doses.</p>
        </> : <p className="mt-4 text-sm text-muted">Versioned explanation is unavailable for this snapshot. Refresh the dashboard; no clinical conclusion should be inferred from missing metadata.</p>}
    </Modal>;
}
