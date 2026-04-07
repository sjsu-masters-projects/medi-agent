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
                rightAction={<Button onClick={() => setOpen(true)}>Log symptom</Button>}
                subtitle="Track patterns and share updates with your clinicians."
                title="Symptom Timeline"
            />
            <div className="space-y-4 px-5">
                <Card className="space-y-2 border-blue-200 bg-blue-50">
                    <p className="text-sm font-semibold text-blue-700">AI pattern detected</p>
                    <p className="text-sm text-gray-700">
                        Your recent dizziness reports overlap with a new blood pressure medication change.
                    </p>
                </Card>
                {symptomReports.map((report) => (
                    <Card className="space-y-3" key={report.id}>
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <h2 className="text-sm font-semibold text-gray-900">{report.symptom}</h2>
                                <p className="text-sm text-gray-500">
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
                        <p className="text-sm text-gray-600">{report.aiAssessment}</p>
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
