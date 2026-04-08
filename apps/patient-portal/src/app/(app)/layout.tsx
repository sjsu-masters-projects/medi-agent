"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { BottomNav, ProtectedRoute } from "@/components/layouts";

export default function AppLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    return (
        <ProtectedRoute>
            <div className="app-shell flex min-h-dvh flex-col bg-gray-50">
                <main className="flex-1 overflow-y-auto pb-24">{children}</main>
                <BottomNav currentPath={pathname} />
            </div>
        </ProtectedRoute>
    );
}
