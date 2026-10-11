import type { ReactNode } from "react";
import { Icon } from "./icons";

/** The only way to mark content produced by AI. Never pair it with the approval check. */
export function AiChip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-brand-tint px-2.5 py-1 text-xs font-medium text-brand-ink ${className}`}><Icon name="spark" className="h-3 w-3" />{children}</span>;
}
