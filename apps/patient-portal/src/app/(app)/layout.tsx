"use client";

import { Suspense, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { BottomNav, ProtectedRoute } from "@/components/layouts";

export default function AppLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    return (
        <Suspense fallback={null}>
            <ProtectedRoute>
                <div className="app-shell app-shell--responsive flex min-h-dvh flex-col">
                    <main className="flex-1 overflow-y-auto pb-32">{children}</main>
                    <BottomNav currentPath={pathname} />
                </div>
            </ProtectedRoute>
        </Suspense>
    );
}
