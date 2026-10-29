"use client";

import { useEffect, useState } from "react";
import { api } from "@/services/api";
import type { DocumentApiRecord } from "@/services/documents";
import type { ConversationDraft } from "@/types/care-conversations";
import type { Locale } from "@/types";
import { recordTitle } from "./record-row";

/** Prepare an ordinary private message; no chart write or automatic send occurs here. */
export function RecordRequestComposer({
  documentId,
  patientId,
  locale,
  token,
  draft,
  disabled,
  onDraft,
}: {
  documentId: string;
  patientId: string;
  locale: Locale;
  token: string;
  draft: ConversationDraft;
  disabled: boolean;
  onDraft: (draft: ConversationDraft) => void;
}) {
  const spanish = locale === "es-MX";
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([documentId, patientId, locale, token, attempt]);
  const [source, setSource] = useState<{
    key: string;
    document: DocumentApiRecord | null;
  } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    void api
      .get<DocumentApiRecord>(
        `/api/v1/documents/${encodeURIComponent(documentId)}`,
        { token, signal: controller.signal },
      )
      .then((document) => {
        if (current)
          setSource({
            key,
            document:
              document?.id === documentId &&
              document.patient_id === patientId &&
              typeof document.file_name === "string"
                ? document
                : null,
          });
      })
      .catch(() => {
        if (current) setSource({ key, document: null });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [documentId, patientId, locale, token, attempt, key]);
  const settled = source?.key === key;
  const document = settled ? source.document : null;
  const occupied = Boolean(
    draft.body.trim() || draft.clientMessageId || draft.carePlanItemId,
  );
  function prepare() {
    if (!document || disabled || occupied) return;
    const title = recordTitle(
      {
        fileName: document.file_name,
        displayTitle: document.display_title ?? undefined,
      },
      locale,
    );
    const body = spanish
      ? `Me gustaría solicitar una corrección o la eliminación de este documento.\n\nDocumento: ${title}\nArchivo original: ${document.file_name}\nReferencia del documento: ${document.id}\n\nMi solicitud: `
      : `I would like to request a correction or removal of this record.\n\nDocument: ${title}\nOriginal file: ${document.file_name}\nRecord reference: ${document.id}\n\nMy request: `;
    onDraft({ body });
  }
  return (
    <aside className="rounded-2xl border border-line-strong bg-surface p-3 text-sm leading-6">
      {!settled ? (
        <p role="status">
          {spanish
            ? "Cargando el documento de tu solicitud…"
            : "Loading the record for your request…"}
        </p>
      ) : document ? (
        <>
          <p className="break-words font-medium text-ink">
            {recordTitle(
              {
                fileName: document.file_name,
                displayTitle: document.display_title ?? undefined,
              },
              locale,
            )}
          </p>
          <p className="text-muted">
            {spanish
              ? "Prepara un mensaje, explica lo que necesitas y selecciona Enviar. Esto no cambia ni elimina el documento."
              : "Prepare a message, explain what you need, then select Send. This does not change or remove the record."}
          </p>
          {occupied ? (
            <p className="mt-1 text-muted">
              {spanish
                ? "Envía o borra tu borrador actual antes de preparar esta solicitud."
                : "Send or clear your current draft before preparing this request."}
            </p>
          ) : null}
          <button
            type="button"
            className="mt-2 min-h-11 rounded-xl bg-brand-tint px-3 font-semibold text-brand-ink disabled:opacity-50"
            disabled={disabled || occupied}
            onClick={prepare}
          >
            {spanish ? "Preparar solicitud" : "Prepare request"}
          </button>
        </>
      ) : (
        <>
          <p role="alert">
            {spanish
              ? "Este documento no está disponible. No se preparó ninguna solicitud."
              : "This record is unavailable. No request was prepared."}
          </p>
          <button
            type="button"
            className="min-h-11 font-semibold text-brand"
            onClick={() => setAttempt((value) => value + 1)}
          >
            {spanish ? "Volver a cargar el documento" : "Reload record"}
          </button>
        </>
      )}
    </aside>
  );
}
