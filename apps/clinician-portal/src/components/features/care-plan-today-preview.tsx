"use client";

import { useEffect, useRef, useState } from "react";
import { fetchCarePlanTodayPreview, type CarePlanTodayPreview } from "@/services/clinicians";

/** A read-only snapshot, remounted by the parent whenever the saved review changes. */
export function CarePlanTodayPreviewPanel({ patientId, planId, disabled }: {
    patientId: string;
    planId: string;
    disabled: boolean;
}) {
    const [preview, setPreview] = useState<CarePlanTodayPreview | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const request = useRef(0);
    useEffect(() => () => { request.current += 1; }, []);

    async function load() {
        if (disabled || loading) return;
        const current = ++request.current;
        setLoading(true); setError(null); setPreview(null);
        try {
            const result = await fetchCarePlanTodayPreview(patientId, planId);
            if (current === request.current) setPreview(result);
        } catch (cause) {
            if (current === request.current) setError(cause instanceof Error ? cause.message : "Unable to preview Today.");
        } finally {
            if (current === request.current) setLoading(false);
        }
    }

    return <section aria-label="Proposed Today preview" className="rounded-xl border border-gray-200 bg-white p-4">
        <h3 className="font-semibold text-gray-900">Proposed Today preview</h3>
        <p className="mt-1 text-sm text-gray-500">Read-only view using the saved draft, existing activities, and current patient reminder settings. Nothing is published. Changes to records or reminders after this snapshot can change Today.</p>
        {disabled ? <p className="mt-2 text-sm text-yellow-800">Resolve review requirements and save your edits before previewing.</p> : null}
        <button className="mt-3 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-60" type="button" disabled={disabled || loading} onClick={() => void load()}>{loading ? "Loading preview…" : preview ? "Refresh Today preview" : "Preview Today"}</button>
        {error ? <p role="alert" className="mt-3 text-sm text-red-800">{error}</p> : null}
        {preview && !disabled ? <div className="mt-3 space-y-3">
            <p className="text-sm text-gray-700">{preview.feed.date} · {preview.feed.timezone} · proposed version {preview.version_number}</p>
            <p className="text-xs text-gray-500">Snapshot: {new Date(preview.generated_at).toLocaleString("en-US", { timeZone: preview.feed.timezone })}. New activities have preview-only identities; they do not inherit past completion or reminder times.</p>
            {preview.feed.tasks.length ? <ul className="space-y-2">{preview.feed.tasks.map((task) => <li key={task.id} className="rounded-lg border border-gray-200 p-3 text-sm text-gray-700">
                <p className="font-semibold text-gray-900">{task.name}</p>
                <p>{task.description} · {task.frequency}</p>
                <p className="mt-1 text-xs text-gray-500">{task.care_plan ? "Proposed care-plan activity" : "Existing activity"} · {task.status === "pending" ? "Available" : task.status} · {task.scheduled_at ? new Date(task.scheduled_at).toLocaleTimeString("en-US", { timeZone: preview.feed.timezone, hour: "numeric", minute: "2-digit" }) : task.requires_schedule_configuration ? "Patient reminder time needed" : "No automatic reminder"}</p>
            </li>)}</ul> : <p className="text-sm text-gray-500">No activities on this date. Effective dates and chosen reminder days can exclude items.</p>}
        </div> : null}
    </section>;
}
