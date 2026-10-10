"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { getBrowserTimezone, getSupportedTimezones } from "@/services/timezones";
import { clearOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale } from "@/types";
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { getAuthEntryCopy } from "@/content/auth-entry-copy";

const allowedGenders = ["male", "female", "other", "prefer_not_to_say"] as const;

export default function OnboardingPage() {
    const router = useRouter();
    const { locale, setLocale } = useAuthEntryLocale();
    const copy = getAuthEntryCopy(locale);
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const profileDraft = useSelector((state: RootState) => state.onboarding.profileDraft);
    const dispatch = useDispatch<AppDispatch>();
    const [errorKey, setErrorKey] = useState<"namesRequired" | "genderInvalid" | "inviteRequired" | "inviteInvalid" | "failure" | null>(null);
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
        if (normalizedGender && !allowedGenders.includes(normalizedGender as (typeof allowedGenders)[number])) {
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
            setErrorKey(joiningClinic && typeof submissionError === "object" && submissionError !== null && "status" in submissionError && [400, 404, 422].includes(Number(submissionError.status)) ? "inviteInvalid" : "failure");
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
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-14 pb-10 text-white shadow-sm">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative">
                <p className="text-xs font-black uppercase tracking-[0.24em] text-white">{copy.step} {step} {copy.of} 4</p>
                <h1 className="mt-3 text-[2.35rem] font-black leading-none tracking-[-0.04em]">{copy.completeProfile}</h1>
                <p className="mt-4 text-base leading-7 text-white">{copy.profileIntro}</p>
                <div className="mt-5 flex items-center gap-2">
                    {[1, 2, 3, 4].map((value) => (
                        <span
                            className={`h-2.5 flex-1 rounded-full ${value <= step ? "bg-white" : "bg-white/20"}`}
                            key={value}
                        />
                    ))}
                </div>
                </div>
            </div>

            <div className="patient-stack -mt-5 px-5">
                <Card className="space-y-6 shadow-sm" padding="lg">
                {step === 1 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#5b6b83]">{copy.personal}</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">{copy.aboutYou}</h2>
                        </div>
                        <Input label={copy.firstName} onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label={copy.lastName} onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label={copy.dateOfBirth} disabled onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                    </div>
                ) : null}

                {step === 2 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#5b6b83]">{copy.preferences}</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">{copy.communication}</h2>
                        </div>
                        <label className="block text-[0.95rem] font-semibold text-[#5b6b83]">
                            {copy.preferredLanguage}
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                onChange={(event) => setLocale(normalizeLocale(event.target.value))}
                                value={locale}
                            >
                                {SUPPORTED_LOCALES.map((locale) => (
                                    <option key={locale} value={locale}>
                                        {getLocaleLabel(locale)}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="block text-[0.95rem] font-semibold text-[#5b6b83]">
                            {copy.timezone}
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                onChange={(event) => updateField("timezone", event.target.value)}
                                value={formData.timezone}
                            >
                                {timezones.map((timezone) => (
                                    <option key={timezone} value={timezone}>
                                        {timezone}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="block text-[0.95rem] font-semibold text-[#5b6b83]">
                            {copy.gender}
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                onChange={(event) => updateField("gender", event.target.value)}
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
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#5b6b83]">{copy.medical}</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">{copy.medicalHeading}</h2>
                        </div>
                        <p className="text-sm leading-6 text-[#5b6b83]">{copy.medicalIntro}</p>
                    </div>
                ) : null}

                {step === 4 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#5b6b83]">{copy.joinClinic}</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">{copy.connect}</h2>
                        </div>
                        <Input label={copy.invite} onChange={(event) => updateField("inviteCode", event.target.value)} placeholder="CITY-8832" value={formData.inviteCode} />
                        <p className="rounded-2xl bg-[#e6f4f1] px-4 py-3 text-sm font-medium text-[#147465]">{copy.inviteRequiredIntro}</p>
                    </div>
                ) : null}

                {errorKey ? (
                    <div role="alert" className="rounded-2xl border border-[#d9cbc0] bg-red-100 px-4 py-3 text-sm font-semibold text-red-800">
                        {copy[errorKey]}
                    </div>
                ) : null}

                <div className="flex items-center justify-between gap-3">
                    <Button disabled={step === 1 || submitting} onClick={() => setStep((current) => Math.max(1, current - 1))} variant="secondary">
                        {copy.back}
                    </Button>
                    {step < 4 ? (
                        <Button disabled={submitting} onClick={() => setStep((current) => Math.min(4, current + 1))} size="lg">{copy.next}</Button>
                    ) : (
                        <Button disabled={submitting} onClick={handleFinish} size="lg">
                            {submitting ? copy.saving : copy.finish}
                        </Button>
                    )}
                </div>
                </Card>
            </div>
        </div>
    );
}
