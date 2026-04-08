import type { ReactNode } from "react";

interface DataTableProps {
    headers: string[];
    children: ReactNode;
    columns?: string;
}

export function DataTable({ children, columns, headers }: DataTableProps) {
    const gridTemplate = columns ?? `repeat(${headers.length}, minmax(0, 1fr))`;

    return (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div
                className="grid gap-4 border-y border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500"
                style={{ gridTemplateColumns: gridTemplate }}
            >
                {headers.map((header) => (
                    <span key={header}>{header}</span>
                ))}
            </div>
            <div>{children}</div>
        </div>
    );
}
