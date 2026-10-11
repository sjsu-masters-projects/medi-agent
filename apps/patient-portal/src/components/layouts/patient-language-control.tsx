"use client";

import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { HiOutlineInformationCircle, HiOutlineLanguage } from "react-icons/hi2";
import { usePatientProfileState } from "@/hooks/use-patient-profile";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";
import { normalizeLocale, type Locale } from "@/types";

export function PatientLanguageControl({ visible = true }: { visible?: boolean }) {
  const { profile, updateProfile, loading, error, refresh } = usePatientProfileState();
  const token = useSelector((state: RootState) => state.auth.accessToken);
  const currentToken = useRef(token);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const locale = normalizeLocale(profile?.preferredLanguage);
  const spanish = locale === "es-MX";
  useEffect(() => { currentToken.current = token; setSaving(false); setFailed(false); }, [token]);
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);

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
  return <div className="border-b border-line bg-surface px-5 py-2">
    <div className="flex items-center justify-end gap-2">
      <HiOutlineLanguage aria-hidden="true" className="h-5 w-5 shrink-0 text-gray-500" />
      <label className="text-sm font-medium text-gray-700" htmlFor="portal-language">{spanish ? "Idioma" : "Language"}</label>
      <select id="portal-language" aria-busy={saving} disabled={!profile || loading || saving}
        className="min-h-11 max-w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 disabled:opacity-60"
        value={locale} onChange={(event) => void changeLanguage(event.target.value as Locale)}>
        <option value="en-US">English</option><option value="es-MX">Español</option>
      </select>
    </div>
    <details className="mt-1 text-xs text-gray-500">
      <summary className="flex min-h-8 cursor-pointer items-center justify-end gap-1"><HiOutlineInformationCircle aria-hidden="true" className="h-4 w-4" />{spanish ? "Sobre el idioma" : "About language"}</summary>
      <p className="mt-1">{spanish ? "El idioma se guarda para todo el portal. Las indicaciones médicas y los mensajes anteriores conservan su texto original. Pide a tu equipo de atención indicaciones revisadas en otro idioma." : "This saves the language for the whole portal. Medical instructions and previous messages keep their original wording. Ask your care team for reviewed instructions in another language."}</p>
    </details>
    {saving ? <p role="status" className="mt-1 text-right text-xs text-gray-500">{spanish ? "Guardando idioma…" : "Saving language…"}</p> : null}
    {failed ? <p role="alert" className="mt-1 text-sm text-red-800">{spanish ? "No se pudo guardar el idioma. No cambió tu preferencia; intenta de nuevo." : "Could not save the language. Your preference is unchanged; try again."}</p> : null}
    {error ? <div role="alert" className="mt-1 text-sm text-red-800"><p>Language preference unavailable / Idioma no disponible.</p><button className="min-h-11 underline" type="button" onClick={refresh}>Try again / Reintentar</button></div> : null}
  </div>;
}
