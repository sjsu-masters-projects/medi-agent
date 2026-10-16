"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui";
import { fieldClass } from "@/components/ui/input";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";

const PREPARE_ERROR =
  "Unable to prepare the MedWatch draft. Your rationale is retained. Try again.";

export function MedWatchPreparationAction({
  disabled,
  onPrepare,
}: {
  disabled: boolean;
  onPrepare: (rationale: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  const titleId = useId();
  const hintId = useId();
  const errorId = useId();
  const blocked = disabled || submitting;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (disabled || pending.current || !rationale.trim()) return;
    pending.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await onPrepare(rationale.trim());
      setOpen(false);
      setRationale("");
    } catch {
      // Shown only here (the page does not repeat it); the rationale is kept for a retry.
      setError(PREPARE_ERROR);
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  function cancel() {
    setOpen(false);
    setError(null);
  }

  if (!open) {
    return (
      <Button
        disabled={disabled}
        onClick={() => setOpen(true)}
        size="sm"
        variant="secondary"
      >
        <Icon aria-hidden="true" className="h-4 w-4" name="file" />
        Prepare MedWatch draft
      </Button>
    );
  }

  return (
    <form
      aria-busy={submitting || undefined}
      aria-labelledby={titleId}
      className="ma-enter space-y-4 rounded-xl border border-line-strong bg-surface-2 p-4"
      onSubmit={submit}
    >
      <div className="space-y-1.5">
        <h3 className="text-sm font-semibold text-ink" id={titleId}>
          Record reportability decision
        </h3>
        <p className="text-xs leading-relaxed text-muted" id={hintId}>
          This prepares an editable draft only. It will not submit a report to
          the FDA.
        </p>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
          Clinical rationale (required)
        </span>
        <textarea
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          className={`${fieldClass} min-h-24 py-2.5 leading-relaxed placeholder:text-muted!`}
          disabled={blocked}
          maxLength={2000}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Explain why this event should be prepared for MedWatch review."
          required
          value={rationale}
        />
      </label>
      {error ? (
        <p
          className="ma-enter flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
          id={errorId}
          role="alert"
        >
          <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
          <span>{error}</span>
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <Button
          disabled={blocked || !rationale.trim()}
          size="sm"
          type="submit"
        >
          {submitting ? <ProcessingDots className="bg-current" /> : null}
          Create editable draft
        </Button>
        <Button disabled={blocked} onClick={cancel} size="sm" variant="ghost">
          Cancel
        </Button>
      </div>
    </form>
  );
}
