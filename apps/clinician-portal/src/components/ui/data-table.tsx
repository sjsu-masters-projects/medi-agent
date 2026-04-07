import type { ReactNode } from "react";

interface DataTableProps {
    headers: string[];
    children: ReactNode;
}

export function DataTable({ children, headers }: DataTableProps) {
    return (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="grid border-y border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                <div className={`grid gap-4 ${headers.length === 6 ? "grid-cols-6" : "grid-cols-4"}`}>
                    {headers.map((header) => (
                        <span key={header}>{header}</span>
                    ))}
                </div>
            </div>
            <div>{children}</div>
        </div>
    );
}
