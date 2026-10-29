"use client";

import { useEffect, useState } from "react";
import { api } from "@/services/api";
import {
  readDocumentExplanation,
  type DocumentExplanation,
} from "@/services/documents";
import type { Locale } from "@/types";

/** Responses belong to one actor, source and locale, including before effects run. */
export function useDocumentExplanation({
  documentId,
  source,
  locale,
  token,
  actorId,
}: {
  documentId: string | null;
  source: string | undefined;
  locale: Locale;
  token: string | null;
  actorId: string | undefined;
}) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    data: DocumentExplanation | null;
  } | null>(null);
  const key = JSON.stringify([
    documentId,
    source,
    locale,
    token,
    actorId,
    attempt,
  ]);
  const enabled = Boolean(documentId && source && token && actorId);

  useEffect(() => {
    if (!enabled || !documentId || !token) return;
    const endpoint = `/api/v1/documents/${encodeURIComponent(documentId)}/explain`;
    const requestToken = token;
    const controller = new AbortController();
    let current = true;
    async function load() {
      try {
        const response = await api.post<unknown>(
          endpoint,
          { language: locale, structured: true },
          { token: requestToken, signal: controller.signal },
        );
        if (current)
          setResult({ key, data: readDocumentExplanation(response, locale) });
      } catch {
        if (current) setResult({ key, data: null });
      }
    }
    void load();
    return () => {
      current = false;
      controller.abort();
    };
  }, [documentId, enabled, key, locale, token]);

  const settled = enabled && result?.key === key;
  return {
    data: settled ? result.data : null,
    loading: enabled && !settled,
    failed: settled && result.data === null,
    retry: () => setAttempt((value) => value + 1),
  };
}
