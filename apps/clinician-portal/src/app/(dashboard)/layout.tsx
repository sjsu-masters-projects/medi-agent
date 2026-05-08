"use client";

import { Suspense, type ReactNode } from "react";
import { ProtectedRoute } from "@/components/layouts/protected-route";
import { Sidebar } from "@/components/layouts/sidebar";
import { TopHeader } from "@/components/layouts/top-header";

export default function DashboardLayout({ children }: { children: ReactNode }) {
    return (
        <Suspense fallback={null}>
            <ProtectedRoute>
                <div className="flex h-screen overflow-hidden">
                    <Sidebar />
                    <div className="flex flex-1 flex-col overflow-hidden">
                        <TopHeader />
                        <main className="flex-1 overflow-y-auto bg-gray-50 p-6">{children}</main>
                    </div>
                </div>
            </ProtectedRoute>
        </Suspense>
    );
}
