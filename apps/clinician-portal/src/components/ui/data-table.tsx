import type { ReactNode } from "react";

interface DataTableColumn {
    label: string;
    width?: string;
    align?: "left" | "right";
}

interface DataTableProps {
    caption: string;
    headers: readonly DataTableColumn[];
    children: ReactNode;
}

/** Native table relationships stay available when the viewport requires horizontal scrolling. */
export function DataTable({ children, caption, headers }: DataTableProps) {
    return (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" role="region" aria-label={`${caption} table`} tabIndex={0}>
            <table className="w-full min-w-[840px] table-fixed text-sm">
                <caption className="sr-only">{caption}</caption>
                <colgroup>{headers.map((header) => <col key={header.label} style={{ width: header.width }} />)}</colgroup>
                <thead className="border-b border-line-strong bg-surface-2">
                    <tr>{headers.map((header) => (
                        <th className={`ma-table-heading px-4 py-3 ${header.align === "right" ? "text-right" : "text-left"}`} scope="col" key={header.label}>{header.label}</th>
                    ))}</tr>
                </thead>
                <tbody className="divide-y divide-line">{children}</tbody>
            </table>
        </div>
    );
}
