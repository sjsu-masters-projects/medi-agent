"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { Skeleton } from "@/components/ui";
import type { RootState } from "@/store/store";
import { buildLoginRedirectUrl } from "../../../../../packages/shared/src/utils/return-path";

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
    const pathname = usePathname();
    const searchParams = useSearchParams();

    useEffect(() => {
        if (!loading && !isAuthenticated) {
            const returnPath = `${pathname}${searchParams?.toString() ? `?${searchParams.toString()}` : ""}`;
            router.replace(
                buildLoginRedirectUrl({
                    loginPath: "/login",
                    returnPath,
                }),
            );
        }
    }, [isAuthenticated, loading, pathname, router, searchParams]);

    if (loading) {
        return <LoadingSkeleton />;
    }

    if (!isAuthenticated) {
        return null;
    }

    return <>{children}</>;
}
