"use client";

import { Suspense, type ReactNode } from "react";
import { ProtectedRoute } from "@/components/layouts/protected-route";
import { Sidebar } from "@/components/layouts/sidebar";
import { TopHeader } from "@/components/layouts/top-header";

export default function DashboardLayout({ children }: { children: ReactNode }) {
    return (
        <Suspense fallback={null}>
            <ProtectedRoute>
                <div className="flex h-dvh flex-col overflow-hidden md:flex-row">
                    <Sidebar />
                    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                        <TopHeader />
                        <main className="min-h-0 flex-1 overflow-y-auto bg-gray-50 p-4 sm:p-6">{children}</main>
                    </div>
                </div>
            </ProtectedRoute>
        </Suspense>
    );
}
