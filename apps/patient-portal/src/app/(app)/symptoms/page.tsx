"use client";

import Link from "next/link";
import { Icon } from "@/components/ui/icons";
import { PageHeader } from "@/components/layouts";
import { SymptomHistoryList } from "@/components/features/symptom-history";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { usePatientShell } from "@/contexts/patient-shell-context";

export default function SymptomsPage() {
  const profile = usePatientProfile();
  const { setConversationOpen } = usePatientShell();
  const spanish = profile?.preferredLanguage === "es-MX";

  return (
    <div className="patient-page space-y-4 pb-6">
      <PageHeader
        backButton
        title={spanish ? "Reportar un síntoma" : "Report a symptom"}
        subtitle={
          spanish
            ? "Comparte cómo te sientes y cuándo empezó."
            : "Share how you feel and when it started."
        }
      />
      <div className="patient-stack space-y-4 px-4">
        <section className="space-y-4 rounded-[22px] bg-surface p-[14px]">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-brand-deep text-gold"
            >
              <Icon name="spark" className="h-5 w-5" />
            </span>
            <h2 className="min-w-0 break-words text-[17px] font-semibold text-ink">
              {spanish
                ? "Reportar un síntoma con Nora"
                : "Report a symptom with Nora"}
            </h2>
          </div>
          <p className="text-[15px] leading-6 text-ink-2">
            {spanish
              ? "Nora es una asistente de atención con IA. En el chat, describe lo que sientes, cuándo empezó y qué tan intenso es. Revisa las preguntas y confirma los detalles cuando se te solicite."
              : "Nora is an AI care assistant. In chat, describe what you feel, when it started, and how strong it is. Review the questions and confirm details when asked."}
          </p>
          <Link
            className="ma-press inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-3 text-center text-base font-semibold text-white shadow-[0_12px_24px_-16px_rgba(20,116,101,.9)] hover:bg-brand-hover"
            href="/chat"
            onClick={(event) => {
              if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey)
                setConversationOpen(true);
            }}
          >
            <Icon name="chat" className="h-5 w-5" />
            {spanish ? "Abrir chat con Nora" : "Open chat with Nora"}
          </Link>
          <details className="ma-disclosure border-t border-line pt-2">
            <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-ink-2">
              {spanish
                ? "Qué incluir en tu reporte"
                : "What to include in your report"}
            </summary>
            <p className="text-sm leading-6 text-ink-2">
              {spanish
                ? "Incluye cuándo empezó, con qué frecuencia ocurre y cómo afecta tus actividades. Abrir el chat no guarda un reporte ni notifica a tu equipo de atención."
                : "Include when it started, how often it happens, and how it affects your activities. Opening chat does not save a report or notify your care team."}
            </p>
          </details>
        </section>
        <p
          role="note"
          className="flex items-start gap-2.5 rounded-2xl bg-danger-tint px-3.5 py-3 text-sm leading-6 text-danger-ink"
        >
          <Icon name="alert" className="mt-0.5 h-[18px] w-[18px] shrink-0" />
          {spanish
            ? "Este chat no se monitorea continuamente. En una emergencia, llama al 911."
            : "This chat is not continuously monitored. In an emergency, call 911."}
        </p>
        <SymptomHistoryList
          locale={profile?.preferredLanguage ?? "en-US"}
          timezone={profile?.timezone ?? "UTC"}
        />
      </div>
    </div>
  );
}
