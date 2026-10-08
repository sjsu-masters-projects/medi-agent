"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPatientDeepDive, generateSoapNote, type PatientDeepDive } from "@/services/clinicians";

export function patientLoadFailure(error: unknown): "denied" | "not-found" | "transient" {
    const status = typeof error === "object" && error !== null && "status" in error
        ? error.status : undefined;
    if (status === 403) return "denied";
    if (status === 404) return "not-found";
    return "transient";
}

// The page keys this hook's owner by patient and account, so new identities
// start empty before effects run. Request generations also guard refresh races.
export function usePatientDetail(patientId: string, enabled: boolean) {
    const [patient, setPatient] = useState<PatientDeepDive | null>(null);
    const [loadingProfile, setLoading] = useState(true);
    const [loadFailure, setLoadFailure] = useState<ReturnType<typeof patientLoadFailure> | null>(null);
    const [generatingSoap, setGeneratingSoap] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const generation = useRef(0);

    const reload = useCallback(async () => {
        const request = ++generation.current;
        setPatient(null);
        setLoading(true);
        setLoadFailure(null);
        setError(null);
        setGeneratingSoap(false);
        if (!enabled) return;
        try {
            const data = await fetchPatientDeepDive(patientId);
            if (request === generation.current) setPatient(data);
        } catch (failure) {
            if (request === generation.current) setLoadFailure(patientLoadFailure(failure));
        } finally {
            if (request === generation.current) setLoading(false);
        }
    }, [patientId, enabled]);

    useEffect(() => {
        void reload();
        return () => { generation.current += 1; };
    }, [reload]);

    async function generateSoap() {
        const request = generation.current;
        setGeneratingSoap(true);
        setError(null);
        try {
            const result = await generateSoapNote(patientId, 30);
            if (request === generation.current) {
                setPatient((current) => current ? { ...current, latest_soap_note: result.soap_note } : null);
            }
        } catch (failure) {
            if (request === generation.current) {
                setError(failure instanceof Error ? failure.message : "Failed to generate SOAP note");
            }
        } finally {
            if (request === generation.current) setGeneratingSoap(false);
        }
    }

    return { patient, loadingProfile, loadFailure, generatingSoap, error, reload, generateSoap };
}
