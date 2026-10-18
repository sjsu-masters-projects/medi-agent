"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { Icon } from "@/components/ui/icons";
import { usePatientProfileState } from "@/hooks/use-patient-profile";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";
import { getLocaleLabel, SUPPORTED_LOCALES, normalizeLocale, type Locale } from "@/types";
import { rememberPatientLocale } from "@/content/patient-locale";
import { useInitialPatientLocale } from "@/contexts/patient-locale-context";

export function PatientLanguageControl({ visible = true }: { visible?: boolean }) {
  const { profile, updateProfile, loading, error, refresh } = usePatientProfileState();
  const token = useSelector((state: RootState) => state.auth.accessToken);
  const currentToken = useRef(token);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const initialLocale = useInitialPatientLocale();
  const locale = normalizeLocale(profile?.preferredLanguage ?? initialLocale);
  const spanish = locale === "es-MX";
  useEffect(() => { currentToken.current = token; setSaving(false); setFailed(false); }, [token]);
  useLayoutEffect(() => { if (profile) rememberPatientLocale(locale); }, [locale, profile]);

  async function changeLanguage(next: Locale) {
    if (!token || !profile || saving || next === locale) return;
    const sentToken = token;
    setSaving(true);
    setFailed(false);
    try {
      const saved = await api.put<{ preferred_language: Locale }>(
        "/api/v1/patients/me", { preferred_language: next }, { token },
      );
      if (currentToken.current === sentToken) {
        updateProfile((current) => ({ ...current, preferredLanguage: normalizeLocale(saved.preferred_language) }));
      }
    } catch {
      if (currentToken.current === sentToken) setFailed(true);
    } finally {
      if (currentToken.current === sentToken) setSaving(false);
    }
  }

  if (!visible) return null;
  return <div className="space-y-3">
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm font-semibold text-ink-2" htmlFor="portal-language"><Icon name="globe" className="h-[18px] w-[18px] text-muted" />{spanish ? "Idioma" : "Language"}</label>
      <select id="portal-language" aria-busy={saving} disabled={!profile || loading || saving}
        className="min-h-[52px] w-full max-w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base font-medium text-ink outline-none transition focus:border-brand focus:ring-4 focus:ring-brand/15 disabled:opacity-60"
        value={locale} onChange={(event) => void changeLanguage(event.target.value as Locale)}>
        {SUPPORTED_LOCALES.map((value) => <option key={value} value={value}>{getLocaleLabel(value)}</option>)}
      </select>
    </div>
    {saving ? <p role="status" className="flex items-center gap-2 text-sm text-muted"><span aria-hidden="true" className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />{spanish ? "Guardando idioma…" : "Saving language…"}</p> : null}
    {failed ? <p role="alert" className="rounded-2xl bg-danger-tint px-4 py-3 text-sm text-danger-ink">{spanish ? "No se pudo guardar el idioma. No cambió tu preferencia; intenta de nuevo." : "Could not save the language. Your preference is unchanged; try again."}</p> : null}
    {error ? <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-danger-tint px-4 py-3 text-sm text-danger-ink"><p>Language preference unavailable / Idioma no disponible.</p><button className="min-h-11 font-semibold underline" type="button" onClick={refresh}>Try again / Reintentar</button></div> : null}
    <p className="flex items-start gap-2.5 rounded-2xl bg-surface-2 px-4 py-3 text-[13px] leading-relaxed text-ink-2"><Icon name="info" className="mt-px h-4 w-4 shrink-0 text-muted" /><span>{spanish ? "El idioma se guarda para todo el portal. Tu plan de atención y tus actividades de hoy cambian también, porque tu equipo de atención los aprueba en inglés y en español. Los mensajes anteriores se muestran en el idioma en que se escribieron." : "This saves the language for the whole portal. Your care plan and Today list switch too, because your care team approves them in English and Spanish. Earlier messages stay in the language they were written in."}</span></p>
  </div>;
}
