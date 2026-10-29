"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/services/api";
import { apiErrorCode } from "@/services/care-team-routing";
import { Button, Skeleton } from "@/components/ui";
import { ProcessingDots } from "@/components/ui/motion";
import type { Document, Locale } from "@/types";

/** Server eligibility is only a hint; the removal transaction rechecks every condition. */
export function RecordActions({
  document,
  locale,
  token,
  actorId,
  onRemoved,
  onRequest,
}: {
  document: Document;
  locale: Locale;
  token: string;
  actorId: string;
  onRemoved: () => void;
  onRequest: () => void;
}) {
  const spanish = locale === "es-MX";
  const [attempt, setAttempt] = useState(0);
  const [eligibility, setEligibility] = useState<{
    attempt: number;
    canRemove: boolean;
    failed: boolean;
  } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<"uncertain" | "review" | "changed" | null>(
    null,
  );
  const [saving, setSaving] = useState(false);
  const alive = useRef(true);
  const busy = useRef(false);
  const root = useRef<HTMLDivElement>(null);
  const returnFocus = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  // The confirmation replaces the button that opened it: move focus in, and back on Cancel.
  useEffect(() => {
    if (confirming) {
      root.current?.querySelector<HTMLElement>("[data-removal-cancel]")?.focus();
    } else if (returnFocus.current) {
      returnFocus.current = false;
      root.current?.querySelector<HTMLElement>("[data-removal-start]")?.focus();
    }
  }, [confirming]);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    void api
      .get<{ can_remove?: boolean }>(
        `/api/v1/documents/${encodeURIComponent(document.id)}/removal`,
        { token, signal: controller.signal },
      )
      .then((result) => {
        if (current)
          setEligibility({
            attempt,
            canRemove: result?.can_remove === true,
            failed: typeof result?.can_remove !== "boolean",
          });
      })
      .catch(() => {
        if (current)
          setEligibility({ attempt, canRemove: false, failed: true });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [attempt, document.id, token]);
  const checked = eligibility?.attempt === attempt;
  const ownPending =
    document.uploadedByRole === "patient" &&
    document.uploadedBy === actorId &&
    document.reviewStatus === "pending";
  const canRemove =
    ownPending && checked && eligibility.canRemove && error !== "review";
  // Until the server answers, neither path is offered: a removable upload must not be
  // sent down the request path, and an ineligible one must not look removable.
  const checking = ownPending && !checked;

  async function remove() {
    if (!canRemove || busy.current) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    try {
      await api.delete<void>(
        `/api/v1/documents/${encodeURIComponent(document.id)}`,
        { token },
      );
      if (alive.current) onRemoved();
    } catch (failure) {
      if (!alive.current) return;
      const reviewRequired =
        apiErrorCode(failure) === "DOCUMENT_REMOVAL_REQUIRES_REVIEW";
      const changed = apiErrorCode(failure) === "DOCUMENT_REMOVAL_CHANGED";
      setError(reviewRequired ? "review" : changed ? "changed" : "uncertain");
      if (reviewRequired) setConfirming(false);
      if (changed) {
        setConfirming(false);
        setAttempt((value) => value + 1);
      }
    } finally {
      busy.current = false;
      if (alive.current) setSaving(false);
    }
  }

  return (
    <div ref={root} className="space-y-3 border-t border-line pt-3">
      {error ? (
        <p role="alert" className="text-sm leading-6 text-danger-ink">
          {error === "changed"
            ? spanish
              ? "El documento cambió. Revisa las opciones actualizadas antes de volver a intentarlo."
              : "The record changed. Check the latest options before trying again."
            : error === "review"
              ? spanish
                ? "Este documento ya no se puede quitar directamente. Pide a tu equipo de atención que lo revise."
                : "This record can no longer be removed directly. Ask your care team to review it."
              : spanish
                ? "No pudimos confirmar si se quitó el archivo. Puedes volver a intentarlo; no se creará otra eliminación."
                : "We could not confirm whether the upload was removed. You can safely retry this removal."}
        </p>
      ) : null}
      {checking ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full !rounded-2xl" />
          <p role="status" className="flex items-center gap-2 text-xs text-muted">
            <ProcessingDots />
            {spanish ? "Revisando opciones…" : "Checking removal options…"}
          </p>
        </div>
      ) : canRemove ? (
        confirming ? (
          <div className="ma-enter rounded-2xl bg-surface-2 p-4">
            <p className="font-semibold text-ink">
              {spanish ? "¿Quitar este archivo?" : "Remove this upload?"}
            </p>
            <p className="mt-1 text-sm leading-6 text-muted">
              {spanish
                ? "Se quitarán el archivo que subiste y los detalles extraídos que aún no se han revisado. Tu plan de atención aprobado no cambia."
                : "This removes your uploaded file and its unreviewed extracted details. Your approved care plan stays unchanged."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                data-removal-cancel
                disabled={saving}
                variant="secondary"
                onClick={() => {
                  returnFocus.current = true;
                  setConfirming(false);
                }}
              >
                {spanish ? "Cancelar" : "Cancel"}
              </Button>
              <Button
                aria-busy={saving || undefined}
                disabled={saving}
                variant="danger"
                onClick={() => void remove()}
              >
                {saving ? (
                  <>
                    <ProcessingDots className="bg-current" />
                    {spanish ? "Quitando…" : "Removing…"}
                  </>
                ) : error === "uncertain"
                    ? spanish
                      ? "Volver a intentar"
                      : "Retry removal"
                    : spanish
                      ? "Quitar archivo"
                      : "Remove upload"}
              </Button>
            </div>
          </div>
        ) : (
          <Button
            data-removal-start
            fullWidth
            variant="secondary"
            onClick={() => setConfirming(true)}
          >
            {spanish ? "Quitar archivo" : "Remove upload"}
          </Button>
        )
      ) : (
        <>
          <Button
            fullWidth
            variant="secondary"
            disabled={saving}
            onClick={onRequest}
          >
            {document.uploadedByRole === "clinician"
              ? spanish
                ? "Reportar un problema"
                : "Report an issue"
              : spanish
                ? "Solicitar corrección o eliminación"
                : "Request removal or correction"}
          </Button>
          <p className="text-xs leading-5 text-muted">
            {spanish
              ? "Elige a un integrante de tu equipo y envíale un mensaje. El documento se conserva mientras se revisa tu solicitud."
              : "Choose a care-team member and send a message. The record stays available while your request is reviewed."}
          </p>
        </>
      )}
      {ownPending && checked && eligibility.failed ? (
        <div>
          <p className="text-xs leading-5 text-muted">
            {spanish
              ? "No pudimos comprobar si puedes quitar este archivo. Vuelve a intentarlo o contacta a tu equipo."
              : "We could not check whether this upload can be removed. Retry or contact your care team."}
          </p>
          <button
            type="button"
            className="min-h-11 text-sm font-semibold text-brand"
            onClick={() => setAttempt((value) => value + 1)}
          >
            {spanish
              ? "Volver a revisar las opciones"
              : "Check removal options again"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
