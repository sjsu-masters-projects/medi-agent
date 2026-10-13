"use client";

import { Suspense, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { BottomNav, ProtectedRoute } from "@/components/layouts";
import { PatientProfileProvider } from "@/hooks/use-patient-profile";
import { PatientLanguageControl } from "@/components/layouts/patient-language-control";
import { PatientShellProvider, usePatientShell } from "@/contexts/patient-shell-context";
import { NotificationProvider } from "@/contexts/notifications-context";

function PatientShell({ children }: { children: ReactNode }) {
    const pathname = usePathname();
    const { conversationOpen } = usePatientShell();
    return (
        <div className="app-shell flex min-h-dvh flex-col">
            <PatientLanguageControl visible={false} />
            <main className={`flex-1 ${conversationOpen ? "pb-0" : "pb-[calc(110px+env(safe-area-inset-bottom))]"}`}>{children}</main>
            {!conversationOpen && <BottomNav currentPath={pathname} />}
        </div>
    );
}

export default function AppLayout({ children }: { children: ReactNode }) {
    return (
        <Suspense fallback={null}>
            <ProtectedRoute>
              <PatientProfileProvider>
                <NotificationProvider><PatientShellProvider><PatientShell>{children}</PatientShell></PatientShellProvider></NotificationProvider>
              </PatientProfileProvider>
            </ProtectedRoute>
        </Suspense>
    );
}
