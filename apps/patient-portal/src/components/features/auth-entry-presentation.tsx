import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

// Entry-only primitives keep the reference composition independent of app cards.
export function AuthEntryInput({ label, trailingAction, ...props }: InputHTMLAttributes<HTMLInputElement> & {
    label: string;
    trailingAction?: ReactNode;
}) {
    return (
        <label className="block text-sm font-medium text-ink-2">
            <span className="mb-2 block">{label}</span>
            <span className="relative block">
                <input {...props} className={`h-[52px] w-full min-w-0 rounded-2xl border border-line-strong bg-surface px-4 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15 ${trailingAction ? "pr-14" : ""}`} />
                {trailingAction ? <span className="absolute inset-y-0 right-1 flex items-center">{trailingAction}</span> : null}
            </span>
        </label>
    );
}

export function AuthEntryButton(props: ButtonHTMLAttributes<HTMLButtonElement>) {
    return <button {...props} className="ma-press inline-flex min-h-[54px] w-full items-center justify-center rounded-btn bg-brand px-5 py-3 text-[17px] font-semibold text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50" />;
}
