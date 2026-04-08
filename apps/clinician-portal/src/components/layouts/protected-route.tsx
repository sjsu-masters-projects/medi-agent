"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSelector } from "react-redux";
import { Skeleton } from "@/components/ui";
import type { RootState } from "@/store/store";

function LoadingSkeleton() {
    return (
        <div className="flex h-screen items-center justify-center bg-gray-50">
            <div className="w-96 space-y-4">
                <Skeleton className="h-8 w-48" variant="text" />
                <Skeleton className="h-32 w-full" variant="rect" />
                <Skeleton className="h-24 w-full" variant="rect" />
            </div>
        </div>
    );
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
    const { isAuthenticated, loading } = useSelector((state: RootState) => state.auth);
    const router = useRouter();

    useEffect(() => {
        if (!loading && !isAuthenticated) {
            router.replace("/login");
        }
    }, [isAuthenticated, loading, router]);

    if (loading) {
        return <LoadingSkeleton />;
    }

    if (!isAuthenticated) {
        return null;
    }

    return <>{children}</>;
}
