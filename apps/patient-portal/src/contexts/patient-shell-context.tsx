"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

const PatientShellContext = createContext<{
    conversationOpen: boolean;
    setConversationOpen: (open: boolean) => void;
}>({ conversationOpen: false, setConversationOpen: () => undefined });

/** Presentation state only; conversation ownership remains in the messaging feature. */
export function PatientShellProvider({ children }: { children: ReactNode }) {
    const [conversationOpen, setConversationOpen] = useState(false);
    return <PatientShellContext.Provider value={{ conversationOpen, setConversationOpen }}>{children}</PatientShellContext.Provider>;
}

export function usePatientShell() { return useContext(PatientShellContext); }
