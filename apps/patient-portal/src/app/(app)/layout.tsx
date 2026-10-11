"use client";

import { Suspense, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { BottomNav, ProtectedRoute } from "@/components/layouts";
import { PatientProfileProvider } from "@/hooks/use-patient-profile";
import { PatientLanguageControl } from "@/components/layouts/patient-language-control";

export default function AppLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    return (
        <Suspense fallback={null}>
            <ProtectedRoute>
              <PatientProfileProvider>
                <div className="app-shell flex min-h-dvh flex-col">
                    <PatientLanguageControl visible={false} />
                    <main className="flex-1 overflow-y-auto pb-32">{children}</main>
                    <BottomNav currentPath={pathname} />
                </div>
              </PatientProfileProvider>
            </ProtectedRoute>
        </Suspense>
    );
}
