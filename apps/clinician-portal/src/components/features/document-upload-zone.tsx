"use client";

import { useState, useCallback } from "react";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { Icon } from "@/components/ui/icons";
import { LiveDot, ProcessingDots } from "@/components/ui/motion";
import { DocumentType } from "@/types";
import { readStoredSession } from "@/services/auth-session";

const UploadStatus = {
  PENDING: "pending",
  UPLOADING: "uploading",
  DONE: "done",
  ERROR: "error",
} as const;
type UploadStatus = (typeof UploadStatus)[keyof typeof UploadStatus];

interface QueuedFile {
  id: string;
  file: File;
  status: UploadStatus;
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
  "image/tiff",
]);
const MAX_SIZE_MB = 20;
const MAX_FILE_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
const ACCEPTED_FILE_EXTENSIONS = ".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff";
const ACCEPTED_FILE_MESSAGE =
  "Choose a PDF, JPG, PNG, WebP, or TIFF file up to 20 MB.";
const DOCUMENT_TYPES = [
  { label: "Clinical Note", value: DocumentType.OTHER },
  { label: "Lab Report", value: DocumentType.LAB_REPORT },
  { label: "Prescription", value: DocumentType.PRESCRIPTION },
  { label: "Discharge Summary", value: DocumentType.DISCHARGE_SUMMARY },
  { label: "Diagnostic Report", value: DocumentType.DIAGNOSTIC_REPORT },
  { label: "Referral", value: DocumentType.REFERRAL },
] as const;

function parseDocumentType(value: string): DocumentType {
  return (
    DOCUMENT_TYPES.find((type) => type.value === value)?.value ??
    DocumentType.OTHER
  );
}

function makeId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function getFileValidationError(file: File): string | null {
  if (!ALLOWED_TYPES.has(file.type)) {
    return ACCEPTED_FILE_MESSAGE;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `Each file must be ${MAX_SIZE_MB} MB or smaller.`;
  }
  return null;
}

function sanitizeFileName(fileName: string) {
  return fileName
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9._-]/g, "");
}

function createStorageClient(token: string): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "Supabase Storage is not configured for the clinician portal.",
    );
  }
  return createClient(url, anonKey, {
    accessToken: async () => token,
    auth: {
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: false,
    },
  });
}

async function hashFile(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

async function uploadToStorage(
  file: File,
  patientId: string,
  token: string,
): Promise<string> {
  const safeName = sanitizeFileName(file.name) || `document-${Date.now()}`;
  const path = `${patientId}/${Date.now()}-${safeName}`;
  const { data, error } = await createStorageClient(token)
    .storage.from("documents")
    .upload(path, file, {
      cacheControl: "3600",
      contentType: file.type || "application/octet-stream",
      upsert: false,
    });
  if (error) throw new Error(error.message);
  return data.path;
}

export function DocumentUploadZone({
  patientId,
  onComplete,
}: DocumentUploadZoneProps) {
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>(
    DocumentType.OTHER,
  );

  // ── File validation ──────────────────────────────────────────────────────

  const validateFiles = useCallback((files: File[]): File[] => {
    return files.filter((file) => !getFileValidationError(file));
  }, []);

  const addToQueue = useCallback(
    (files: File[]) => {
      const valid = validateFiles(files);
      const firstInvalid = files.find((file) => getFileValidationError(file));
      setValidationError(
        firstInvalid ? getFileValidationError(firstInvalid) : null,
      );
      const newItems: QueuedFile[] = valid.map((f) => ({
        id: makeId(),
        file: f,
        status: UploadStatus.PENDING,
      }));
      setQueue((prev) => [...prev, ...newItems]);
    },
    [validateFiles],
  );

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
    const pendingItems = queue.filter(
      (item) => item.status === UploadStatus.PENDING,
    );
    if (pendingItems.length === 0) return;

    setUploading(true);
    const completedIds: string[] = [];
    const token =
      typeof window !== "undefined"
        ? (readStoredSession()?.accessToken ??
          localStorage.getItem("access_token") ??
          "")
        : "";
    const apiBase =
      process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

    for (const item of pendingItems) {
      // Mark as uploading
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id ? { ...q, status: UploadStatus.UPLOADING } : q,
        ),
      );

      try {
        if (!token)
          throw new Error("Your session has expired. Please sign in again.");
        const [filePath, contentHash] = await Promise.all([
          uploadToStorage(item.file, patientId, token),
          hashFile(item.file),
        ]);

        const response = await fetch(
          `${apiBase}/api/v1/documents/patients/${patientId}`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              document_type: documentType,
              file_name: item.file.name,
              file_path: filePath,
              file_size_bytes: item.file.size,
              mime_type: item.file.type || "application/octet-stream",
              source_clinic: "Clinician uploaded document",
              content_hash: contentHash,
              start_ingestion: true,
            }),
          },
        );

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.status}`);
        }

        const data = (await response.json()) as { id?: string };
        if (data.id) completedIds.push(data.id);

        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id ? { ...q, status: UploadStatus.DONE } : q,
          ),
        );
      } catch (err) {
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  status: UploadStatus.ERROR,
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
        <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
          Document type
        </span>
        <select
          className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
          id="upload-document-type"
          onChange={(e) => setDocumentType(parseDocumentType(e.target.value))}
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
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-[1.5px] border-dashed px-6 py-10 transition-colors duration-[160ms] ${
          dragging
            ? "border-primary bg-primary-tint"
            : "border-line-strong bg-surface-2 hover:border-primary-line hover:bg-primary-tint/40"
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
        <span
          aria-hidden="true"
          className={`flex h-12 w-12 items-center justify-center rounded-2xl border transition-colors duration-[160ms] ${
            dragging
              ? "border-primary-line bg-surface text-primary"
              : "border-line bg-surface text-muted"
          }`}
        >
          <Icon name="up" className="h-6 w-6" />
        </span>
        <div className="text-center">
          <p className="text-sm font-medium text-ink">
            Drop files here or{" "}
            <span className="font-semibold text-primary underline underline-offset-2">browse</span>
          </p>
          <p className="mt-1 text-xs text-muted">
            PDF, JPG, PNG, WebP, or TIFF — max {MAX_SIZE_MB}MB per file
          </p>
        </div>

        <input
          accept={ACCEPTED_FILE_EXTENSIONS}
          aria-hidden="true"
          className="hidden"
          id="clinician-file-input"
          multiple
          onChange={handleFileInput}
          tabIndex={-1}
          type="file"
        />
      </div>

      {validationError && (
        <p
          className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
          role="alert"
        >
          <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{validationError}</span>
        </p>
      )}

      {/* File queue */}
      {queue.length > 0 && (
        <ul
          aria-label="Files queued for upload"
          className="overflow-hidden rounded-xl border border-line bg-surface"
        >
          {queue.map((item) => (
            <li
              className="ma-enter flex items-center justify-between gap-3 border-b border-line px-4 py-3 last:border-b-0"
              key={item.id}
            >
              <div className="flex min-w-0 items-center gap-3">
                <span
                  aria-hidden="true"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-primary-tint text-primary"
                >
                  <Icon name="file" className="h-[18px] w-[18px]" />
                </span>
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium text-ink">
                    {item.file.name}
                  </p>
                  <p className="font-mono text-xs text-muted">
                    {(item.file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                {/* Status pill */}
                {item.status === UploadStatus.UPLOADING && (
                  <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-primary-tint px-2 py-1 text-xs font-medium text-primary">
                    <LiveDot color="#2563EB" /> Uploading
                  </span>
                )}
                {item.status === UploadStatus.DONE && (
                  <span className="inline-flex items-center rounded-[7px] bg-ok-soft px-2 py-1 text-xs font-medium text-ok-ink">
                    ✓ Done
                  </span>
                )}
                {item.status === UploadStatus.ERROR && (
                  <div className="text-right">
                    <span className="inline-flex items-center rounded-[7px] bg-risk-soft px-2 py-1 text-xs font-medium text-risk-ink">
                      ✕ Failed
                    </span>
                    <p className="mt-1 max-w-56 text-xs text-risk-ink" role="alert">
                      {item.error ?? "Upload failed. Please try again."}
                    </p>
                  </div>
                )}

                {/* Remove button */}
                {item.status !== UploadStatus.UPLOADING && (
                  <button
                    aria-label={`Remove ${item.file.name}`}
                    className="ma-press inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink"
                    onClick={() => removeFromQueue(item.id)}
                    type="button"
                  >
                    <Icon name="close" aria-hidden="true" className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Upload button */}
      {queue.some((item) => item.status === UploadStatus.PENDING) && (
        <button
          className="ma-press inline-flex h-[42px] w-full items-center justify-center gap-2 rounded-[10px] bg-primary px-[18px] text-sm font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
          disabled={uploading}
          id="clinician-upload-submit"
          onClick={handleUpload}
          type="button"
        >
          {uploading ? <ProcessingDots className="bg-[#94A3B8]" /> : null}
          {uploading
            ? "Uploading..."
            : `Upload ${queue.filter((q) => q.status === UploadStatus.PENDING).length} file(s)`}
        </button>
      )}
    </div>
  );
}
