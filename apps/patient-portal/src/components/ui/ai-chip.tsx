import type { ReactNode } from "react";
import { Icon } from "./icons";

export function AiChip({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-tint text-brand-ink px-2 py-1 text-xs font-medium"><Icon name="spark" className="h-3.5 w-3.5" />{children}</span>;
}
