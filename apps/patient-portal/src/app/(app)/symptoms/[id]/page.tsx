"use client";

import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layouts";
import { SymptomReportView } from "@/components/features/symptom-history";
import { getSymptomHistoryCopy } from "@/content/symptom-history-copy";
import { usePatientProfile } from "@/hooks/use-patient-profile";

export default function SymptomReportPage() {
  const profile = usePatientProfile();
  const params = useParams<{ id: string }>();
  const locale = profile?.preferredLanguage ?? "en-US";
  const copy = getSymptomHistoryCopy(locale);
  return (
    <div className="patient-page space-y-4 pb-6">
      <PageHeader backButton title={copy.detailTitle} />
      <div className="patient-stack px-4">
        <SymptomReportView
          id={params.id}
          locale={locale}
          timezone={profile?.timezone ?? "UTC"}
        />
      </div>
    </div>
  );
}
