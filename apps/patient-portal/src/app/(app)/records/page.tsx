"use client";

import { useRef, useState } from "react";
import { DocumentCard } from "@/components/features";
import { PageHeader } from "@/components/layouts";
import { Button, EmptyState, Modal, ProgressBar } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";
import { DocumentType, type Document } from "@/types";
import { useSelector } from "react-redux";

type PortalDocument = Document & { icon: string; provider: string };

const initialDocuments: PortalDocument[] = [
    {
        aiSummary: "Your blood pressure is stable. LDL is slightly elevated, so keep taking your medication as directed.",
        createdAt: "2026-03-15T00:00:00Z",
        documentType: DocumentType.LAB_REPORT,
        fileName: "Blood Panel Results",
        fileSizeBytes: 120000,
        fileUrl: "#",
        icon: "🩸",
        id: "doc-1",
        mimeType: "application/pdf",
        parsed: true,
        patientId: "demo-patient",
        provider: "Dr. Smith",
        uploadedBy: "demo-patient",
        uploadedByRole: "patient",
        visibility: "all_providers",
    },
];

export default function RecordsPage() {
    const [documents, setDocuments] = useState(initialDocuments);
    const [selectedDocument, setSelectedDocument] = useState<PortalDocument | null>(null);
    const [explanationLang, setExplanationLang] = useState<"en" | "es">("en");
    const [explanationText, setExplanationText] = useState<string | null>(null);
    const [explanationLoading, setExplanationLoading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const token = useSelector((state: RootState) => state.auth.token);

    async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }

        setUploading(true);
        for (const value of [20, 45, 70, 100]) {
            setUploadProgress(value);
            await new Promise((resolve) => window.setTimeout(resolve, 150));
        }

        try {
            await api.post(
                "/api/v1/documents/",
                {
                    document_type: "other",
                    file_name: file.name,
                    file_path: `uploads/${file.name}`,
                    file_size_bytes: file.size,
                    mime_type: file.type || "application/octet-stream",
                },
                { token: token ?? undefined },
            );
        } catch {
            // Allow local-only demo uploads while backend/storage wiring is incomplete.
        }

        setDocuments((current) => [
            {
                createdAt: new Date().toISOString(),
                documentType: DocumentType.OTHER,
                fileName: file.name,
                fileSizeBytes: file.size,
                fileUrl: "#",
                icon: "📄",
                id: `${Date.now()}`,
                mimeType: file.type || "application/octet-stream",
                parsed: false,
                patientId: "demo-patient",
                provider: "Recently uploaded",
                uploadedBy: "demo-patient",
                uploadedByRole: "patient",
                visibility: "all_providers",
            },
            ...current,
        ]);
        setUploading(false);
        setUploadProgress(0);
    }

    async function handleLanguageChange(lang: "en" | "es") {
        setExplanationLang(lang);
        if (!selectedDocument) {
            return;
        }

        if (lang === "en") {
            setExplanationText(selectedDocument.aiSummary ?? null);
            return;
        }

        setExplanationLoading(true);
        try {
            const result = await api.post<{ summary: string }>(
                `/api/v1/documents/${selectedDocument.id}/explain`,
                { language: lang },
                { token: token ?? undefined },
            );
            setExplanationText(result.summary);
        } catch {
            setExplanationText("Translation is currently unavailable. Please try again later.");
        } finally {
            setExplanationLoading(false);
        }
    }

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader
                rightAction={<Button onClick={() => fileInputRef.current?.click()} variant="secondary">Upload</Button>}
                subtitle="View clinical records and plain-language explanations."
                title="My Records"
            />
            <input className="hidden" onChange={handleFileChange} ref={fileInputRef} type="file" />
            <div className="-mt-4 space-y-4 px-5">
                <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-2xl bg-white px-4 py-3 shadow-sm ring-1 ring-slate-100">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Stored</p>
                        <p className="mt-1 text-2xl font-bold text-slate-900">{documents.length}</p>
                        <p className="text-xs text-slate-500">Secure records</p>
                    </div>
                    <div className="rounded-2xl bg-sky-50 px-4 py-3 shadow-sm ring-1 ring-sky-100">
                        <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">AI Ready</p>
                        <p className="mt-1 text-2xl font-bold text-slate-900">{documents.filter((document) => document.aiSummary).length}</p>
                        <p className="text-xs text-slate-500">Summaries available</p>
                    </div>
                </div>
                {uploading ? <ProgressBar value={uploadProgress} /> : null}
                {documents.length === 0 ? (
                    <EmptyState description="Upload PDFs or images from your clinic visits." icon="📁" title="No records yet" />
                ) : null}
                {documents.map((document) => (
                    <DocumentCard
                        date={new Date(document.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                        hasAiSummary={Boolean(document.aiSummary)}
                        icon={document.icon}
                        id={document.id}
                        key={document.id}
                        name={document.fileName}
                        onClick={() => {
                            setSelectedDocument(document);
                            setExplanationLang("en");
                            setExplanationLoading(false);
                            setExplanationText(document.aiSummary ?? null);
                        }}
                        provider={document.provider}
                        type={document.documentType.replaceAll("_", " ")}
                    />
                ))}
            </div>
            <Modal onClose={() => setSelectedDocument(null)} open={Boolean(selectedDocument)} title={selectedDocument?.fileName ?? "Record details"}>
                <div className="space-y-4">
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Source</p>
                        <p className="mt-1 text-sm font-medium text-slate-700">{selectedDocument?.provider}</p>
                    </div>
                    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                        <div className="flex items-center justify-between gap-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">Explain this to me</p>
                            <select
                                className="rounded-lg border border-blue-200 bg-white px-2 py-1 text-xs text-blue-700"
                                onChange={(event) => handleLanguageChange(event.target.value as "en" | "es")}
                                value={explanationLang}
                            >
                                <option value="en">English</option>
                                <option value="es">Español</option>
                            </select>
                        </div>
                        <p className="mt-2 text-sm text-gray-700">
                            {explanationLoading
                                ? "Translating..."
                                : explanationText ?? "AI summary will appear here after parsing completes."}
                        </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <Button fullWidth onClick={() => setSelectedDocument(null)} variant="secondary">
                            Close
                        </Button>
                        <Button fullWidth onClick={() => fileInputRef.current?.click()}>
                            Upload another
                        </Button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
