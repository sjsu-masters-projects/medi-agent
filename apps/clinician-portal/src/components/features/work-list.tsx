"use client";

import { useCallback, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { Badge, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { CompactField, compactSelectClass } from "@/components/ui/toolbar";

/** Rows per page for both work lists (one screen at 56px a row). */
export const PAGE_SIZE = 10;

type Params = Record<string, string>;

/**
 * List state (tab, search, sort, page) kept in the URL query so Back from a case or report
 * restores it. Writes use `replaceState`, so the history stack is not filled with filters.
 */
export function useListUrlState<T extends Params>(defaults: T) {
    const searchParams = useSearchParams();
    const [state, setState] = useState<T>(() => {
        const initial: Params = { ...defaults };
        for (const key of Object.keys(defaults)) {
            const value = searchParams.get(key);
            if (value !== null) initial[key] = value;
        }
        return initial as T;
    });

    const update = useCallback(
        (patch: Partial<T>) => {
            setState((current) => {
                const next = { ...current, ...patch } as T;
                if (typeof window !== "undefined") {
                    const params = new URLSearchParams(window.location.search);
                    for (const key of Object.keys(defaults)) {
                        if (next[key] === defaults[key] || next[key] === "") params.delete(key);
                        else params.set(key, next[key]);
                    }
                    const search = params.toString();
                    window.history.replaceState(
                        window.history.state,
                        "",
                        `${window.location.pathname}${search ? `?${search}` : ""}`,
                    );
                }
                return next;
            });
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [],
    );

    /** The query string that restores this list, for a link out to a detail page. */
    const query = new URLSearchParams(
        Object.keys(defaults)
            .filter((key) => state[key] !== defaults[key] && state[key] !== "")
            .map((key) => [key, state[key]] as [string, string]),
    ).toString();

    return { state, update, query };
}

/** A relative age such as "3 d", "5 h" or "just now". */
export function ageLabel(iso: string, now: Date = new Date()): string {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const minutes = Math.max(0, Math.floor((now.getTime() - then) / 60_000));
    if (minutes < 60) return minutes < 2 ? "just now" : `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours} h`;
    return `${Math.floor(hours / 24)} d`;
}

export interface TabDefinition<T extends string> {
    value: T;
    label: string;
    count?: number;
}

export function StatusTabs<T extends string>({
    label,
    tabs,
    value,
    onChange,
}: {
    label: string;
    tabs: TabDefinition<T>[];
    value: T;
    onChange: (value: T) => void;
}) {
    return (
        <div
            aria-label={label}
            className="flex gap-1 overflow-x-auto border-b border-line-strong"
            role="tablist"
        >
            {tabs.map((tab) => {
                const active = tab.value === value;
                return (
                    <button
                        aria-selected={active}
                        className={`ma-press -mb-px flex h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-[13px] font-medium transition-colors ${
                            active
                                ? "border-primary text-ink"
                                : "border-transparent text-muted hover:text-ink"
                        }`}
                        key={tab.value}
                        onClick={() => onChange(tab.value)}
                        role="tab"
                        type="button"
                    >
                        {tab.label}
                        {tab.count !== undefined ? (
                            <span className="rounded-md bg-[rgba(100,116,139,.1)] px-1.5 font-mono text-xs text-ink-2">
                                {tab.count}
                            </span>
                        ) : null}
                    </button>
                );
            })}
        </div>
    );
}

export function ListToolbar({
    searchLabel,
    searchPlaceholder,
    search,
    onSearch,
    sortLabel,
    sort,
    sortOptions,
    onSort,
    extra,
}: {
    extra?: ReactNode;
    searchLabel: string;
    searchPlaceholder: string;
    search: string;
    onSearch: (value: string) => void;
    sortLabel: string;
    sort: string;
    sortOptions: { value: string; label: string }[];
    onSort: (value: string) => void;
}) {
    return (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="relative block sm:w-80">
                <span className="sr-only">{searchLabel}</span>
                <Icon
                    aria-hidden="true"
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                    name="search"
                />
                <input
                    className="h-[34px] w-full rounded-[9px] border border-line-strong bg-surface pl-9 pr-3 text-[13px] text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
                    onChange={(event) => onSearch(event.target.value)}
                    placeholder={searchPlaceholder}
                    type="search"
                    value={search}
                />
            </label>
            <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
                {extra}
                <CompactField label={sortLabel}>
                    <select
                        className={compactSelectClass}
                        onChange={(event) => onSort(event.target.value)}
                        value={sort}
                    >
                        {sortOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </CompactField>
            </div>
        </div>
    );
}

export function Pagination({
    page,
    pageCount,
    total,
    onChange,
}: {
    page: number;
    pageCount: number;
    total: number;
    onChange: (page: number) => void;
}) {
    if (pageCount <= 1) return null;
    const first = (page - 1) * PAGE_SIZE + 1;
    const last = Math.min(total, page * PAGE_SIZE);
    const buttonClass =
        "ma-press h-8 rounded-lg border border-line-strong bg-surface px-3 text-xs font-semibold text-ink-2 hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface";
    return (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-[13px] text-muted">
            <p>
                <span className="font-mono">{first}–{last}</span> of <span className="font-mono">{total}</span>
            </p>
            <div className="flex items-center gap-2">
                <button className={buttonClass} disabled={page <= 1} onClick={() => onChange(page - 1)} type="button">
                    Previous
                </button>
                <span aria-current="page" className="font-mono text-ink-2">
                    {page} / {pageCount}
                </span>
                <button className={buttonClass} disabled={page >= pageCount} onClick={() => onChange(page + 1)} type="button">
                    Next
                </button>
            </div>
        </nav>
    );
}

export const rowLinkClass =
    "group block bg-surface px-4 py-3 outline-none transition-colors hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary sm:px-[22px]";

/** The shared frame: header labels on wide screens, stacked rows on narrow ones. */
export function ListTable({
    label,
    columns,
    headers,
    children,
}: {
    label: string;
    columns: string;
    headers: string[];
    children: ReactNode;
}) {
    return (
        <div
            aria-label={label}
            className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]"
            role="list"
        >
            <div
                aria-hidden="true"
                className="hidden gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted md:grid"
                style={{ gridTemplateColumns: columns }}
            >
                {headers.map((header, index) => (
                    <span key={`${header}-${index}`}>{header}</span>
                ))}
            </div>
            <div className="divide-y divide-line">{children}</div>
        </div>
    );
}

export function ListSkeleton({ label }: { label: string }) {
    return (
        <div
            aria-label={label}
            className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface"
            role="status"
        >
            {Array.from({ length: 5 }).map((_, index) => (
                <div className="flex h-14 items-center gap-4 px-5" key={index}>
                    <Skeleton className="h-4 w-1/4" variant="text" />
                    <Skeleton className="h-4 w-1/3" variant="text" />
                    <Skeleton className="ml-auto h-5 w-16" />
                </div>
            ))}
        </div>
    );
}

export function PageHeader({
    title,
    subtitle,
    action,
}: {
    title: string;
    subtitle: string;
    action?: ReactNode;
}) {
    return (
        <header className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0 max-w-[72ch]">
                <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
                <p className="mt-1 text-sm leading-relaxed text-ink-2">{subtitle}</p>
            </div>
            {action}
        </header>
    );
}

export function CausalityPill({ score, band }: { score: number; band: string }) {
    const variant =
        band === "Definite" || band === "Probable" ? "info" : band === "Possible" ? "warning" : "neutral";
    return (
        <Badge className="font-mono" variant={variant}>
            {score} <span className="font-sans">{band}</span>
        </Badge>
    );
}
