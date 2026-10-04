"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
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
    <div className="mt-3 space-y-2">
      <Button
        variant="secondary"
        disabled={disabled || loading}
        onClick={download}
      >
        {loading ? copy.downloading : copy.download}
      </Button>
      <p className="text-xs text-gray-500">{copy.notice}</p>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {copy.error}
        </p>
      )}
    </div>
  );
}
