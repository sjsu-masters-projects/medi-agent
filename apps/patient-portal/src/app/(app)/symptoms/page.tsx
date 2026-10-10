"use client";

import Link from "next/link";
import { HiOutlineChatBubbleLeftRight } from "react-icons/hi2";
import { PageHeader } from "@/components/layouts";
import { Card } from "@/components/ui";
import { usePatientProfile } from "@/hooks/use-patient-profile";

export default function SymptomsPage() {
  const profile = usePatientProfile();
  const spanish = profile?.preferredLanguage === "es-MX";

  return (
    <div className="patient-page space-y-4 pb-8">
      <PageHeader
        backButton
        title={spanish ? "Reportar un síntoma" : "Report a symptom"}
        subtitle={
          spanish
            ? "Comparta cómo se siente y cuándo empezó."
            : "Share how you feel and when it started."
        }
      />
      <div className="patient-stack -mt-4 space-y-4 px-5">
        <Card className="space-y-4">
          <div aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e6f4f1] text-[#147465]">
            <HiOutlineChatBubbleLeftRight className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold text-[#17233a]">
            {spanish
              ? "Reportar un síntoma con Nora"
              : "Report a symptom with Nora"}
          </h2>
          <p className="text-sm leading-6 text-gray-700">
            {spanish
              ? "Nora es una asistente de atención con IA. En el chat, describa lo que siente, cuándo empezó y qué tan intenso es. Revise las preguntas y confirme los detalles cuando se le solicite."
              : "Nora is an AI care assistant. In chat, describe what you feel, when it started, and how strong it is. Review the questions and confirm details when asked."}
          </p>
          <Link
            className="inline-flex min-h-12 w-full items-center justify-center rounded-2xl bg-[#147465] px-4 py-3 text-center font-semibold text-white hover:bg-[#0f5f53] focus-visible:outline-2 focus-visible:outline-[#147465] focus-visible:outline-offset-2"
            href="/chat"
          >
            {spanish ? "Abrir chat con Nora" : "Open chat with Nora"}
          </Link>
          <details className="border-t border-gray-200 pt-2">
            <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-gray-900">
              {spanish
                ? "Qué incluir en su reporte"
                : "What to include in your report"}
            </summary>
            <p className="text-sm leading-6 text-gray-700">
              {spanish
                ? "Incluya cuándo empezó, con qué frecuencia ocurre y cómo afecta sus actividades. Abrir el chat no guarda un reporte ni notifica a su equipo de atención."
                : "Include when it started, how often it happens, and how it affects your activities. Opening chat does not save a report or notify your care team."}
            </p>
          </details>
        </Card>
        <p
          role="note"
          className="rounded-xl border border-yellow-100 bg-yellow-100 p-4 text-sm leading-6 text-yellow-800"
        >
          {spanish
            ? "Este chat no se monitorea continuamente. En una emergencia, llame al 911."
            : "This chat is not continuously monitored. In an emergency, call 911."}
        </p>
        <details className="rounded-2xl border border-[#eadfd4] bg-white/80 px-4">
          <summary className="min-h-12 cursor-pointer py-3 text-sm font-semibold text-[#30415f]">
            {
            spanish
              ? "Historial de síntomas no disponible aquí"
              : "Symptom history is not available here"
            }
          </summary>
          <p className="pb-4 text-sm leading-6 text-[#5b6b83]">
            {
            spanish
              ? "Esta pantalla aún no está conectada a sus reportes guardados. Puede usar el chat para reportar un síntoma o consultar a su equipo de atención."
              : "This screen is not yet connected to your saved reports. You can use chat to report a symptom or ask your care team."
            }
          </p>
        </details>
      </div>
    </div>
  );
}
