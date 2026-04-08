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
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader
                backButton
                rightAction={<Button onClick={() => setOpen(true)} variant="secondary">Log symptom</Button>}
                subtitle="Track patterns and share updates with your clinicians."
                title="Symptom Timeline"
            />
            <div className="-mt-4 space-y-4 px-5">
                <Card className="space-y-3 border-sky-100 bg-gradient-to-br from-sky-600 to-sky-700 text-white shadow-lg shadow-sky-100">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">AI pattern detected</p>
                    <p className="text-sm text-sky-50">
                        Your recent dizziness reports overlap with a new blood pressure medication change.
                    </p>
                    <div className="inline-flex w-fit rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white">
                        Care team notified
                    </div>
                </Card>
                {symptomReports.map((report) => (
                    <Card className="space-y-4 border-slate-100" key={report.id}>
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Reported symptom</p>
                                <h2 className="mt-1 text-base font-semibold text-slate-900">{report.symptom}</h2>
                                <p className="mt-1 text-sm text-slate-500">
                                    {new Date(report.createdAt).toLocaleString("en-US", {
                                        dateStyle: "medium",
                                        timeStyle: "short",
                                    })}
                                </p>
                            </div>
                            <Badge variant={report.severity >= 7 ? "danger" : "warning"}>
                                Severity {report.severity}/10
                            </Badge>
                        </div>
                        <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Assessment</p>
                            <p className="mt-1 text-sm text-slate-600">{report.aiAssessment}</p>
                        </div>
                    </Card>
                ))}
            </div>
            <Modal onClose={() => setOpen(false)} open={open} title="Log a symptom">
                <div className="space-y-4">
                    <textarea
                        className="min-h-28 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                        onChange={(event) => setNewSymptom(event.target.value)}
                        placeholder="Describe how you feel..."
                        value={newSymptom}
                    />
                    <Button fullWidth onClick={() => setOpen(false)}>
                        Save symptom
                    </Button>
                </div>
            </Modal>
        </div>
    );
}
