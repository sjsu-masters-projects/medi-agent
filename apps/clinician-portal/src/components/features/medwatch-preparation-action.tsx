"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui";

export function MedWatchPreparationAction({
  disabled,
  onPrepare,
}: {
  disabled: boolean;
  onPrepare: (rationale: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [rationale, setRationale] = useState("");
  const pending = useRef(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (disabled || pending.current || !rationale.trim()) return;
    pending.current = true;
    try {
      await onPrepare(rationale.trim());
      setOpen(false);
      setRationale("");
    } finally {
      pending.current = false;
    }
  }

  if (!open) {
    return (
      <Button disabled={disabled} onClick={() => setOpen(true)} size="sm">
        Prepare MedWatch draft
      </Button>
    );
  }

  return (
    <form
      className="space-y-3 rounded-lg border border-indigo-200 bg-indigo-50 p-4"
      onSubmit={submit}
    >
      <div>
        <h3 className="text-sm font-semibold text-gray-900">
          Record reportability decision
        </h3>
        <p className="mt-1 text-xs text-gray-600">
          This prepares an editable draft only. It will not submit a report to
          the FDA.
        </p>
      </div>
      <label className="block text-sm font-medium text-gray-700">
        Clinical rationale (required)
        <textarea
          className="mt-1 min-h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
          disabled={disabled}
          maxLength={2000}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Explain why this event should be prepared for MedWatch review."
          value={rationale}
        />
      </label>
      <div className="flex gap-2">
        <Button
          disabled={disabled || !rationale.trim()}
          size="sm"
          type="submit"
        >
          Create editable draft
        </Button>
        <Button
          disabled={disabled}
          onClick={() => setOpen(false)}
          size="sm"
          variant="ghost"
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
