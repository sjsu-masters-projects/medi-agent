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
        <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50" onClick={onClose}>
            <div
                className="max-h-[85vh] overflow-y-auto rounded-t-3xl bg-white p-6"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
                    <button
                        aria-label="Close modal"
                        className="rounded-lg p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
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
