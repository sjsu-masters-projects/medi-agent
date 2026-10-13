import { AuthShell } from "@/components/features/auth-shell";
import { PasswordRecoveryForm } from "@/components/features/password-recovery-form";

export default function RecoveryPage() {
    return <AuthShell headline="Secure access to your workspace." subcopy="Recover your account, then sign in through your usual clinic and security checks.">
        <PasswordRecoveryForm mode="request" portal="clinician" />
    </AuthShell>;
}
