import type { ReactNode } from "react";
import { Icon } from "./icons";

/** The only way to say "AI produced this". Never pair it with the approval check. */
export function AiChip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-ai-tint px-2.5 py-1.5 text-xs font-medium text-ai-ink ${className}`}><Icon name="spark" className="h-3 w-3" />{children}</span>;
}
