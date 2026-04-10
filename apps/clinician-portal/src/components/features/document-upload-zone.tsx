"use client";

import { useState, useCallback } from "react";
import { HiOutlineCloudArrowUp, HiOutlineDocumentText, HiOutlineXMark } from "react-icons/hi2";

interface QueuedFile {
    id: string;
    file: File;
    status: "pending" | "uploading" | "done" | "error";
    error?: string;
}

interface DocumentUploadZoneProps {
    patientId: string;
    /** Called with the registered document IDs after successful upload */
    onComplete?: (documentIds: string[]) => void;
}

const ALLOWED_TYPES = new Set([
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
]);
const MAX_SIZE_MB = 20;
const DOCUMENT_TYPES = [
    { label: "Clinical Note", value: "clinical_note" },
    { label: "Lab Result", value: "lab_result" },
    { label: "Prescription", value: "prescription" },
    { label: "Discharge Summary", value: "discharge_summary" },
    { label: "Other", value: "other" },
] as const;

function makeId(): string {
    return Math.random().toString(36).slice(2, 10);
}

export function DocumentUploadZone({ patientId, onComplete }: DocumentUploadZoneProps) {
    const [queue, setQueue] = useState<QueuedFile[]>([]);
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [documentType, setDocumentType] = useState<string>("clinical_note");

    // ── File validation ──────────────────────────────────────────────────────

    const validateFiles = useCallback((files: File[]): File[] => {
        return files.filter((file) => {
            if (!ALLOWED_TYPES.has(file.type)) return false;
            if (file.size > MAX_SIZE_MB * 1024 * 1024) return false;
            return true;
        });
    }, []);

    const addToQueue = useCallback((files: File[]) => {
        const valid = validateFiles(files);
        const newItems: QueuedFile[] = valid.map((f) => ({
            id: makeId(),
            file: f,
            status: "pending",
        }));
        setQueue((prev) => [...prev, ...newItems]);
    }, [validateFiles]);

    // ── Drag-and-drop handlers ───────────────────────────────────────────────

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragging(true);
    }, []);

    const handleDragLeave = useCallback(() => setDragging(false), []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setDragging(false);
            const files = Array.from(e.dataTransfer.files);
            addToQueue(files);
        },
        [addToQueue],
    );

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files ?? []);
        addToQueue(files);
        // Reset input so re-selecting same file triggers onChange
        e.target.value = "";
    };

    function removeFromQueue(id: string) {
        setQueue((prev) => prev.filter((item) => item.id !== id));
    }

    // ── Upload handler ───────────────────────────────────────────────────────

    async function handleUpload() {
        const pendingItems = queue.filter((item) => item.status === "pending");
        if (pendingItems.length === 0) return;

        setUploading(true);
        const completedIds: string[] = [];
        const token =
            typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : "";
        const apiBase = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

        for (const item of pendingItems) {
            // Mark as uploading
            setQueue((prev) =>
                prev.map((q) => (q.id === item.id ? { ...q, status: "uploading" } : q)),
            );

            try {
                const formData = new FormData();
                formData.append("file", item.file);
                formData.append("patient_id", patientId);
                formData.append("document_type", documentType);
                formData.append("uploaded_by_role", "clinician");

                const response = await fetch(`${apiBase}/api/v1/documents/`, {
                    method: "POST",
                    headers: { Authorization: `Bearer ${token}` },
                    body: formData,
                });

                if (!response.ok) {
                    throw new Error(`Upload failed: ${response.status}`);
                }

                const data = (await response.json()) as { id?: string };
                if (data.id) completedIds.push(data.id);

                setQueue((prev) =>
                    prev.map((q) => (q.id === item.id ? { ...q, status: "done" } : q)),
                );
            } catch (err) {
                setQueue((prev) =>
                    prev.map((q) =>
                        q.id === item.id
                            ? {
                                  ...q,
                                  status: "error",
                                  error: err instanceof Error ? err.message : "Upload failed",
                              }
                            : q,
                    ),
                );
            }
        }

        setUploading(false);
        if (completedIds.length > 0) {
            onComplete?.(completedIds);
        }
    }

    // ── Render ───────────────────────────────────────────────────────────────

    return (
        <div className="space-y-4">
            <label className="block" htmlFor="upload-document-type">
                <span className="mb-1 block text-sm font-medium text-gray-700">Document type</span>
                <select
                    className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    id="upload-document-type"
                    onChange={(e) => setDocumentType(e.target.value)}
                    value={documentType}
                >
                    {DOCUMENT_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>
                            {type.label}
                        </option>
                    ))}
                </select>
            </label>

            {/* Drop zone */}
            <div
                className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 transition-colors ${
                    dragging
                        ? "border-blue-400 bg-blue-50"
                        : "border-gray-300 bg-gray-50 hover:border-blue-300 hover:bg-blue-50/30"
                }`}
                id="clinician-upload-zone"
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => document.getElementById("clinician-file-input")?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ")
                        document.getElementById("clinician-file-input")?.click();
                }}
                aria-label="Upload patient documents"
            >
                <HiOutlineCloudArrowUp
                    aria-hidden="true"
                    className={`h-10 w-10 ${dragging ? "text-blue-500" : "text-gray-400"}`}
                />
                <div className="text-center">
                    <p className="text-sm font-medium text-gray-700">
                        Drop files here or{" "}
                        <span className="text-blue-600 underline">browse</span>
                    </p>
                    <p className="mt-1 text-xs text-gray-400">
                        PDF, JPG, PNG, TXT — max {MAX_SIZE_MB}MB per file
                    </p>
                </div>

                <input
                    accept=".pdf,.jpg,.jpeg,.png,.webp,.txt"
                    aria-hidden="true"
                    className="hidden"
                    id="clinician-file-input"
                    multiple
                    onChange={handleFileInput}
                    tabIndex={-1}
                    type="file"
                />
            </div>

            {/* File queue */}
            {queue.length > 0 && (
                <ul aria-label="Files queued for upload" className="space-y-2">
                    {queue.map((item) => (
                        <li
                            className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-4 py-3"
                            key={item.id}
                        >
                            <div className="flex items-center gap-3">
                                <HiOutlineDocumentText
                                    aria-hidden="true"
                                    className="h-5 w-5 shrink-0 text-blue-500"
                                />
                                <div>
                                    <p className="text-sm font-medium text-gray-800">
                                        {item.file.name}
                                    </p>
                                    <p className="text-xs text-gray-400">
                                        {(item.file.size / 1024).toFixed(1)} KB
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                {/* Status pill */}
                                {item.status === "uploading" && (
                                    <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                                        <span className="animate-pulse">●</span> Uploading
                                    </span>
                                )}
                                {item.status === "done" && (
                                    <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">
                                        ✓ Done
                                    </span>
                                )}
                                {item.status === "error" && (
                                    <span
                                        className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700"
                                        title={item.error}
                                    >
                                        ✕ Failed
                                    </span>
                                )}

                                {/* Remove button */}
                                {item.status !== "uploading" && (
                                    <button
                                        aria-label={`Remove ${item.file.name}`}
                                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                                        onClick={() => removeFromQueue(item.id)}
                                        type="button"
                                    >
                                        <HiOutlineXMark aria-hidden="true" className="h-4 w-4" />
                                    </button>
                                )}
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            {/* Upload button */}
            {queue.some((item) => item.status === "pending") && (
                <button
                    className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={uploading}
                    id="clinician-upload-submit"
                    onClick={handleUpload}
                    type="button"
                >
                    {uploading
                        ? "Uploading..."
                        : `Upload ${queue.filter((q) => q.status === "pending").length} file(s)`}
                </button>
            )}
        </div>
    );
}
