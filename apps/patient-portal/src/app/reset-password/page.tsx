"use client";

import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { PasswordRecoveryForm } from "@/components/features/password-recovery-form";

export default function RecoveryPage() {
    const { locale, setLocale } = useAuthEntryLocale();
    return <main className="patient-entry mx-auto min-h-dvh w-full max-w-[480px] bg-background pb-8">
        <AuthEntryLanguage locale={locale} onChange={setLocale} />
        <div className="px-6 py-10">
            <PasswordRecoveryForm mode="reset" locale={locale} portal="patient" />
        </div>
    </main>;
}
