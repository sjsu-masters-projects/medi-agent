"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, Modal } from "@/components/ui";
import type { SymptomReport } from "@/types";

const symptomReports: SymptomReport[] = [
    {
        aiAssessment: "Pattern suggests blood-pressure medication adjustment may be needed.",
        createdAt: "2026-04-06T08:15:00Z",
        flaggedForAdr: true,
        id: "symptom-1",
        patientId: "demo-patient",
        severity: 8,
        symptom: "Dizziness when standing",
    },
];

export default function SymptomsPage() {
    const [newSymptom, setNewSymptom] = useState("");
    const [open, setOpen] = useState(false);

    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader
                backButton
                rightAction={<Button onClick={() => setOpen(true)} variant="secondary">Log symptom</Button>}
                subtitle="Track patterns and share updates with your clinicians."
                title="Symptom Timeline"
            />
            <div className="patient-stack -mt-4 space-y-4 px-5">
                <Card className="space-y-3 border-[#b9ded6] bg-gradient-to-br from-[#147465] to-[#285d8f] text-white shadow-[0_24px_55px_rgba(20,116,101,0.24)]">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#ccebe5]">AI pattern detected</p>
                    <p className="text-base leading-7 text-[#effaf7]">
                        Your recent dizziness reports overlap with a new blood pressure medication change.
                    </p>
                    <div className="inline-flex w-fit rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white">
                        Care team notified
                    </div>
                </Card>
                {symptomReports.map((report) => (
                    <Card className="space-y-4" key={report.id}>
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Reported symptom</p>
                                <h2 className="mt-1 text-lg font-semibold text-[#17233a]">{report.symptom}</h2>
                                <p className="mt-1 text-base leading-7 text-[#5b6b83]">
                                    {new Date(report.createdAt).toLocaleString(undefined, {
                                        dateStyle: "medium",
                                        timeStyle: "short",
                                    })}
                                </p>
                            </div>
                            <Badge variant={report.severity >= 7 ? "danger" : "warning"}>
                                Severity {report.severity}/10
                            </Badge>
                        </div>
                        <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                            <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Assessment</p>
                            <p className="mt-1 text-base leading-7 text-[#48627c]">{report.aiAssessment}</p>
                        </div>
                    </Card>
                ))}
            </div>
            <Modal onClose={() => setOpen(false)} open={open} title="Log a symptom">
                <div className="space-y-4">
                    <textarea
                        className="min-h-32 w-full rounded-3xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base leading-7 text-[#17233a] shadow-sm outline-none placeholder:text-[#8d9bae] focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                        onChange={(event) => setNewSymptom(event.target.value)}
                        placeholder="Describe what you feel, when it started, and how strong it is."
                        value={newSymptom}
                    />
                    <Button fullWidth onClick={() => setOpen(false)} size="lg">
                        Save symptom
                    </Button>
                </div>
            </Modal>
        </div>
    );
}
