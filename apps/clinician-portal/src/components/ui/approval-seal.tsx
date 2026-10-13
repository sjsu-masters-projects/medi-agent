import type { ReactNode } from "react";
import { Icon } from "./icons";

/** The only way to say "a clinician approved or verified this". Render only for server-backed state. */
export function ApprovalSeal({ children, pill = false, className = "" }: { children: ReactNode; pill?: boolean; className?: string }) {
  return <span className={`inline-flex items-center gap-2 whitespace-nowrap text-[13px] font-medium text-ok-ink ${pill ? "rounded-lg bg-ok-tint py-1.5 pl-1.5 pr-2.5" : ""} ${className}`}>
    <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] bg-ok text-white"><Icon name="check" className="h-3 w-3" strokeWidth={2.6} /></span>
    {children}
  </span>;
}
