"use client";

import type { ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    children: ReactNode;
    size?: "default" | "wide";
}

const sizeClasses: Record<NonNullable<ModalProps["size"]>, string> = {
    default: "max-w-[480px] rounded-t-[34px] pb-32",
    wide: "max-w-[480px] rounded-t-[34px] pb-32 md:max-w-[960px] md:rounded-[34px] md:pb-6 xl:max-w-[1080px]",
};

const overlayClasses: Record<NonNullable<ModalProps["size"]>, string> = {
    default: "justify-end",
    wide: "justify-end md:items-center md:justify-center md:p-6",
};

export function Modal({ children, onClose, open, size = "default", title }: ModalProps) {
    if (!open || typeof document === "undefined") {
        return null;
    }

    return createPortal(
        <div className={`fixed inset-0 z-60 flex flex-col bg-[#17233a]/45 backdrop-blur-sm ${overlayClasses[size]}`} onClick={onClose}>
            <div
                className={`mx-auto max-h-[88vh] w-full ${sizeClasses[size]} overflow-y-auto border border-white/70 bg-[#fffaf4] p-6 shadow-[0_-24px_80px_rgba(23,35,58,0.20)]`}
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
        </div>,
        document.body,
    );
}
