"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSelector } from "react-redux";
import { Skeleton } from "@/components/ui";
import type { RootState } from "@/store/store";

function LoadingSkeleton() {
    return (
        <div className="space-y-4 px-5 py-10">
            <Skeleton className="h-8 w-40" variant="text" />
            <Skeleton className="h-28 w-full" variant="rect" />
            <Skeleton className="h-24 w-full" variant="rect" />
            <Skeleton className="h-24 w-full" variant="rect" />
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
