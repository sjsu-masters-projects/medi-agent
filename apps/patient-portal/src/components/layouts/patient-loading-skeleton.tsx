import { Skeleton } from "@/components/ui";

/** Locale-neutral first paint while the browser locale or saved profile resolves. */
export function PatientLoadingSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="MediAgent Care"
      className="mx-auto flex min-h-dvh w-full max-w-[520px] flex-col bg-background px-5 pt-[max(24px,env(safe-area-inset-top))]"
      role="status"
    >
      <div className="flex items-center justify-between gap-4">
        <Skeleton className="h-11 w-11" variant="circle" />
        <Skeleton className="h-4 w-24" variant="text" />
      </div>
      <div className="mt-10 space-y-3">
        <Skeleton className="h-4 w-28" variant="text" />
        <Skeleton className="h-9 w-52" variant="text" />
        <Skeleton className="h-4 w-64 max-w-full" variant="text" />
      </div>
      <div className="mt-8 space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}
