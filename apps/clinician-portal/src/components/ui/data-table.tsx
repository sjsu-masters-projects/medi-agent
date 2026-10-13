import type { ReactNode } from "react";

interface DataTableProps {
    headers: string[];
    children: ReactNode;
    columns?: string;
}

export function DataTable({ children, columns, headers }: DataTableProps) {
    const gridTemplate = columns ?? `repeat(${headers.length}, minmax(0, 1fr))`;

    return (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" role="region" aria-label="Scrollable data table" tabIndex={0}>
            <div className="min-w-[640px]">
            <div
                className="grid gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted"
                style={{ gridTemplateColumns: gridTemplate }}
            >
                {headers.map((header) => (
                    <span key={header}>{header}</span>
                ))}
            </div>
            <div className="[&>*]:border-b [&>*]:border-line [&>*:last-child]:border-b-0">{children}</div>
            </div>
        </div>
    );
}
