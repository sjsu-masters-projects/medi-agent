import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecordReviewStatus } from "@/components/features/record-review-status";
import { DocumentReviewStatus } from "@/types";

describe("source review status", () => {
  it.each([
    [
      DocumentReviewStatus.PENDING,
      "Awaiting care-team review",
      "En espera de revisión del equipo de atención",
    ],
    [
      DocumentReviewStatus.APPROVED,
      "Source approved by your care team",
      "Documento aprobado por tu equipo de atención",
    ],
    [
      DocumentReviewStatus.REJECTED,
      "Source not approved by your care team",
      "Documento no aprobado por tu equipo de atención",
    ],
    [
      undefined,
      "Review status unavailable",
      "Estado de revisión no disponible",
    ],
  ] as const)(
    "labels %s in words in both locales",
    (status, english, spanish) => {
      const { rerender } = render(
        <RecordReviewStatus status={status} locale="en-US" />,
      );
      expect(screen.getByText(english)).toBeVisible();
      rerender(<RecordReviewStatus status={status} locale="es-MX" />);
      expect(screen.getByText(spanish)).toBeVisible();
    },
  );
});
