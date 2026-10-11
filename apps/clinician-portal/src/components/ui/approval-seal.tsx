import type { ReactNode } from "react";
import { Icon } from "./icons";

/** Render only for a server-backed approval or verification state. */
export function ApprovalSeal({ children, pill = false }: { children: ReactNode; pill?: boolean }) {
  return <span className={`inline-flex items-center gap-2 text-[13px] font-medium text-ok-ink ${pill ? "bg-ok-tint rounded-full px-3 py-1.5" : ""}`}>
    <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] bg-ok text-white"><Icon name="check" className="h-3 w-3" /></span>
    {children}
  </span>;
}
