"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Input } from "@/components/ui";
import { api } from "@/services/api";
import {
  getBrowserTimezone,
  getSupportedTimezones,
} from "@/services/timezones";
import { clearOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale } from "@/types";
import {
  AuthEntryLanguage,
  useAuthEntryLocale,
} from "@/components/features/auth-entry-language";
import { getAuthEntryCopy } from "@/content/auth-entry-copy";

const allowedGenders = [
  "male",
  "female",
  "other",
  "prefer_not_to_say",
] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const { locale, setLocale } = useAuthEntryLocale();
  const copy = getAuthEntryCopy(locale);
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const profileDraft = useSelector(
    (state: RootState) => state.onboarding.profileDraft,
  );
  const dispatch = useDispatch<AppDispatch>();
  const [errorKey, setErrorKey] = useState<
    | "namesRequired"
    | "genderInvalid"
    | "inviteRequired"
    | "inviteInvalid"
    | "failure"
    | null
  >(null);
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState(() => ({
    dateOfBirth: profileDraft?.dateOfBirth ?? "",
    firstName: profileDraft?.firstName ?? "",
    gender: "",
    inviteCode: "",
    lastName: profileDraft?.lastName ?? "",
    timezone: getBrowserTimezone(),
  }));
  const [timezones] = useState<string[]>(() => getSupportedTimezones());

  async function handleFinish() {
    if (!accessToken) {
      router.replace("/login");
      return;
    }

    if (submitting) return;
    setSubmitting(true);
    setErrorKey(null);

    if (!formData.firstName.trim() || !formData.lastName.trim()) {
      setErrorKey("namesRequired");
      setStep(1);
      setSubmitting(false);
      return;
    }

    const normalizedGender = formData.gender.trim().toLowerCase();
    if (
      normalizedGender &&
      !allowedGenders.includes(
        normalizedGender as (typeof allowedGenders)[number],
      )
    ) {
      setErrorKey("genderInvalid");
      setStep(2);
      setSubmitting(false);
      return;
    }

    if (!formData.inviteCode.trim()) {
      setErrorKey("inviteRequired");
      setSubmitting(false);
      return;
    }

    let joiningClinic = false;
    try {
      await api.put(
        "/api/v1/patients/me",
        {
          first_name: formData.firstName.trim(),
          gender: normalizedGender || undefined,
          last_name: formData.lastName.trim(),
          preferred_language: locale,
          timezone: formData.timezone,
        },
        { token: accessToken },
      );

      joiningClinic = true;
      await api.post<{ clinician_first_name: string }>(
        `/api/v1/patients/me/care-team/join?invite_code=${encodeURIComponent(formData.inviteCode.trim())}`,
        undefined,
        { token: accessToken },
      );
    } catch (submissionError) {
      setErrorKey(
        joiningClinic &&
          typeof submissionError === "object" &&
          submissionError !== null &&
          "status" in submissionError &&
          [400, 404, 422].includes(Number(submissionError.status))
          ? "inviteInvalid"
          : "failure",
      );
      setSubmitting(false);
      return;
    }

    dispatch(clearOnboardingProfile());
    router.replace("/today");
  }
  function updateField(field: keyof typeof formData, value: string) {
    setFormData((current) => ({ ...current, [field]: value }));
    if (errorKey) {
      setErrorKey(null);
    }
  }

  return (
    <div className="app-shell patient-page min-h-dvh pb-10" lang={locale}>
      {step !== 2 && <AuthEntryLanguage locale={locale} onChange={setLocale} />}
      <header className="px-[22px] pt-4 pb-5">
        <p
          className="font-mono text-xs uppercase tracking-[0.08em] text-muted"
          role="status"
        >
          {copy.step} {step} {copy.of} 4
        </p>
        <h1 className="mt-2 text-[32px] font-semibold leading-tight tracking-[-0.02em] text-ink">
          {copy.completeProfile}
        </h1>
        <p className="mt-2 text-[15px] leading-6 text-muted">
          {copy.profileIntro}
        </p>
        <div className="mt-4 flex items-center gap-[5px]" aria-hidden="true">
          {[1, 2, 3, 4].map((value) => (
            <span
              className={`h-1.5 flex-1 rounded-full ${value <= step ? "bg-brand" : "bg-line-strong"}`}
              key={value}
            />
          ))}
        </div>
      </header>

      <div className="patient-stack px-4">
        <section className="space-y-5 rounded-[22px] bg-surface p-4">
          {step === 1 ? (
            <div className="space-y-5">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                  {copy.personal}
                </p>
                <h2 className="mt-1 text-[17px] font-semibold text-ink">
                  {copy.aboutYou}
                </h2>
              </div>
              <Input
                label={copy.firstName}
                onChange={(event) =>
                  updateField("firstName", event.target.value)
                }
                value={formData.firstName}
              />
              <Input
                label={copy.lastName}
                onChange={(event) =>
                  updateField("lastName", event.target.value)
                }
                value={formData.lastName}
              />
              <Input
                label={copy.dateOfBirth}
                disabled
                onChange={(event) =>
                  updateField("dateOfBirth", event.target.value)
                }
                type="date"
                value={formData.dateOfBirth}
              />
            </div>
          ) : null}

          {step === 2 ? (
            <div className="space-y-5">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                  {copy.preferences}
                </p>
                <h2 className="mt-1 text-[17px] font-semibold text-ink">
                  {copy.communication}
                </h2>
              </div>
              <label className="block text-[15px] font-medium text-ink-2">
                {copy.preferredLanguage}
                <select
                  className="mt-2 min-h-11 w-full rounded-2xl border border-line-strong bg-surface px-3 py-2 text-base text-ink"
                  onChange={(event) =>
                    setLocale(normalizeLocale(event.target.value))
                  }
                  value={locale}
                >
                  {SUPPORTED_LOCALES.map((locale) => (
                    <option key={locale} value={locale}>
                      {getLocaleLabel(locale)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[15px] font-medium text-ink-2">
                {copy.timezone}
                <select
                  className="mt-2 min-h-11 w-full rounded-2xl border border-line-strong bg-surface px-3 py-2 text-base text-ink"
                  onChange={(event) =>
                    updateField("timezone", event.target.value)
                  }
                  value={formData.timezone}
                >
                  {timezones.map((timezone) => (
                    <option key={timezone} value={timezone}>
                      {timezone}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[15px] font-medium text-ink-2">
                {copy.gender}
                <select
                  className="mt-2 min-h-11 w-full rounded-2xl border border-line-strong bg-surface px-3 py-2 text-base text-ink"
                  onChange={(event) =>
                    updateField("gender", event.target.value)
                  }
                  value={formData.gender}
                >
                  <option value="">{copy.preferNot}</option>
                  <option value="male">{copy.male}</option>
                  <option value="female">{copy.female}</option>
                  <option value="other">{copy.other}</option>
                  <option value="prefer_not_to_say">{copy.preferNot}</option>
                </select>
              </label>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="space-y-5">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                  {copy.medical}
                </p>
                <h2 className="mt-1 text-[17px] font-semibold text-ink">
                  {copy.medicalHeading}
                </h2>
              </div>
              <p className="text-[15px] leading-6 text-ink-2">
                {copy.medicalIntro}
              </p>
            </div>
          ) : null}

          {step === 4 ? (
            <div className="space-y-5">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                  {copy.joinClinic}
                </p>
                <h2 className="mt-1 text-[17px] font-semibold text-ink">
                  {copy.connect}
                </h2>
              </div>
              <Input
                label={copy.invite}
                onChange={(event) =>
                  updateField("inviteCode", event.target.value)
                }
                placeholder="CITY-8832"
                value={formData.inviteCode}
              />
              <p className="rounded-2xl bg-brand-tint px-4 py-3 text-sm font-medium text-brand-ink">
                {copy.inviteRequiredIntro}
              </p>
            </div>
          ) : null}

          {errorKey ? (
            <div
              role="alert"
              className="rounded-2xl bg-danger-tint px-4 py-3 text-sm font-medium text-danger-ink"
            >
              {copy[errorKey]}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4 [&_button]:min-h-11">
            <Button
              disabled={step === 1 || submitting}
              onClick={() => setStep((current) => Math.max(1, current - 1))}
              variant="secondary"
            >
              {copy.back}
            </Button>
            {step < 4 ? (
              <Button
                disabled={submitting}
                onClick={() => setStep((current) => Math.min(4, current + 1))}
                size="lg"
              >
                {copy.next}
              </Button>
            ) : (
              <Button disabled={submitting} onClick={handleFinish} size="lg">
                {submitting ? copy.saving : copy.finish}
              </Button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
