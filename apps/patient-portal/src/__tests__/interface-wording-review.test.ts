import { describe, expect, it } from "vitest";
import { profileCopy } from "@/app/(app)/profile/profile-copy";
import { getCareTeamCopy } from "@/content/care-team-copy";
import { getChatControlsCopy, getChatRecoveryCopy, getChatResultsCopy, getVoiceModeCopy } from "@/content/chat-copy";
import { getSymptomHistoryCopy } from "@/content/symptom-history-copy";
import { getVisitsCopy } from "@/content/visits-copy";

describe("reviewed Mexican Spanish interface wording", () => {
  it("does not attribute an automated urgent mark to a clinician", () => {
    expect(getSymptomHistoryCopy("es-MX").events.flagged_urgent)
      .toBe("Marcado para que tu equipo de atención lo revise con urgencia");
  });

  it("explains how to disable hands-free and preserves voice text fallback", () => {
    expect(getChatControlsCopy("es-MX").handsFreeOn).toContain("Toca para desactivarlo");
    expect(getVoiceModeCopy("es-MX").errors.permission_denied).toContain("usa texto");
    expect(getVoiceModeCopy("es-MX").notices.not_sent).toContain("No se pudo enviar");
  });

  it("scopes an unavailable reply to its message, without inviting a duplicate", () => {
    const copy = getChatRecoveryCopy("es-MX");
    expect(copy.replyUnavailable).toContain("a este mensaje");
    expect(copy.replyUnavailable).toContain("No volveremos a procesarlo");
    expect(copy.uncertain).toContain("No la repetiremos automáticamente");
  });

  it("names the appointment's clinician and describes language as presentation", () => {
    expect(getVisitsCopy("es-MX").offerTitle).toBe("Tu profesional clínico ofreció estos horarios");
    expect(profileCopy("es-MX").languageHelp).toContain("se muestran en ese idioma");
    expect(profileCopy("en-US").languageHelp).toContain("app language");
  });

  it("preserves names, null branches, versions, dates and measurement counts", () => {
    const copy = getCareTeamCopy("es-MX");
    expect(copy.unownedNotice("Dr. Test")).toContain("Dr. Test");
    expect(copy.unownedNotice(null)).not.toContain("null");
    expect(copy.planGroupVersion(7, "22/10/2026")).toBe("Versión 7 · aprobado el 22/10/2026");
    expect(copy.planGroupVersion(7, null)).toBe("Versión 7");
    for (const count of [0, 1, 2]) {
      expect(getChatResultsCopy("es-MX").showMeasurements(count)).toContain(String(count));
    }
    expect(getChatResultsCopy("es-MX").showMeasurements(1)).toBe("Mostrar 1 medición");
    expect(getChatResultsCopy("es-MX").showMeasurements(2)).toBe("Mostrar 2 mediciones");
    expect(getVoiceModeCopy("es-MX").remaining(2, 5)).toContain("2:05");
  });

  it("preserves clinical approval, privacy and emergency boundaries", () => {
    expect(getCareTeamCopy("es-MX").privateConfirmBody).toContain("pero no cuáles");
    expect(getCareTeamCopy("es-MX").contactClinicBody).toContain("Tus recordatorios continúan");
    expect(getChatControlsCopy("es-MX").caution).toContain("No cambies tu tratamiento sin consultar");
    expect(getChatControlsCopy("es-MX").caution).toContain("911");
    expect(getChatResultsCopy("es-MX").notReviewed).toContain("aún no revisado");
  });
});
