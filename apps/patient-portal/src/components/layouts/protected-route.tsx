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
