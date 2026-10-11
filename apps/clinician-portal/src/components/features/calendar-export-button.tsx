"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { api } from "@/services/api";
import type { Locale } from "@/types";
import {
  getAppointmentCalendarCopy,
  saveAppointmentCalendar,
  type AppointmentCalendarExport,
} from "../../../../../packages/shared/src/utils/appointment-calendar";

interface Props {
  token?: string | null;
  appointmentId: string;
  locale: Locale;
  disabled?: boolean;
}

export function CalendarExportButton(props: Props) {
  return props.token ? (
    <CalendarDownload
      key={`${props.token}:${props.appointmentId}:${props.locale}`}
      {...props}
      token={props.token}
    />
  ) : null;
}

function CalendarDownload({
  token,
  appointmentId,
  locale,
  disabled,
}: Props & { token: string }) {
  const copy = getAppointmentCalendarCopy(locale);
  const active = useRef(true);
  const pending = useRef(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  async function download() {
    if (disabled || pending.current) return;
    pending.current = true;
    setLoading(true);
    setError(false);
    try {
      const file = await api.get<AppointmentCalendarExport>(
        `/api/v1/appointments/${encodeURIComponent(appointmentId)}/calendar?locale=${locale}`,
        { token, cache: "no-store" },
      );
      if (active.current) saveAppointmentCalendar(file);
    } catch {
      if (active.current) setError(true);
    } finally {
      if (active.current) {
        pending.current = false;
        setLoading(false);
      }
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Button
        variant="secondary"
        size="sm"
        disabled={disabled || loading}
        onClick={download}
      >
        <Icon name="download" className="h-3.5 w-3.5" />
        {loading ? copy.downloading : copy.download}
      </Button>
      <p className="min-w-0 flex-1 text-xs text-muted">{copy.notice}</p>
      {error && (
        <p
          role="alert"
          className="flex w-full items-start gap-2 rounded-[10px] border border-risk-line bg-risk-soft px-3 py-2 text-[13px] text-risk-ink"
        >
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{copy.error}</span>
        </p>
      )}
    </div>
  );
}
