import type { ReactNode } from "react";
import { Sidebar } from "@/components/layouts/sidebar";
import { TopHeader } from "@/components/layouts/top-header";

export default function DashboardLayout({ children }: { children: ReactNode }) {
    return (
        <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex flex-1 flex-col overflow-hidden">
                <TopHeader />
                <main className="flex-1 overflow-y-auto bg-gray-50 p-6">{children}</main>
            </div>
        </div>
    );
}
