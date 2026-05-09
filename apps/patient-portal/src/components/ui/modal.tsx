"use client";

import type { ReactNode } from "react";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    children: ReactNode;
}

export function Modal({ children, onClose, open, title }: ModalProps) {
    if (!open) {
        return null;
    }

    return (
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-[#17233a]/45 backdrop-blur-sm" onClick={onClose}>
            <div
                className="mx-auto max-h-[88vh] w-full max-w-[480px] overflow-y-auto rounded-t-[34px] border border-white/70 bg-[#fffaf4] p-6 pb-10 shadow-[0_-24px_80px_rgba(23,35,58,0.20)]"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-xl font-bold text-[#17233a]">{title}</h3>
                    <button
                        aria-label="Close modal"
                        className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-[#64748b] shadow-sm transition hover:bg-[#f4f0ea] hover:text-[#17233a]"
                        onClick={onClose}
                        type="button"
                    >
                        ✕
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}
