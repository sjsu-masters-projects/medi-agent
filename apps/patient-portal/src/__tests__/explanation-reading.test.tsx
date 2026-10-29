import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExplanationSections } from "@/components/features/explanation-sections";
import { RecordOrigin } from "@/components/features/record-origin";

describe("readable patient record content", () => {
  it.each(["en-US", "es-MX"] as const)(
    "keeps every supplied detail without visible group headings (%s)",
    (locale) => {
      render(
        <ExplanationSections
          locale={locale}
          sections={[
            { kind: "overview", items: ["A prescription document."] },
            {
              kind: "medicines",
              items: [
                "Metformina 500 mg with dinner.",
                "Another recorded medicine: 10 mg.",
              ],
            },
            {
              kind: "instructions",
              items: ["Walk only if the care team confirms it."],
            },
            {
              kind: "questions",
              items: ["What should I ask about this medicine?"],
            },
          ]}
        />,
      );
      expect(screen.queryByRole("heading")).not.toBeInTheDocument();
      const details = screen.getByRole("list", {
        name:
          locale === "en-US" ? "Document details" : "Detalles del documento",
      });
      expect(within(details).getAllByRole("listitem")).toHaveLength(3);
      expect(details).toHaveTextContent("500 mg with dinner");
      expect(details).toHaveTextContent("10 mg");
      expect(details).toHaveTextContent("only if");
      const questions = screen.getByRole("list", {
        name:
          locale === "en-US"
            ? "Questions for your care team"
            : "Preguntas para tu equipo de atención",
      });
      expect(questions).toHaveTextContent("What should I ask");
      expect(details).not.toHaveTextContent("What should I ask");
    },
  );

  it("labels actual uploader identity without inferring it from filename", () => {
    const { rerender } = render(
      <RecordOrigin
        document={{
          patientId: "p",
          uploadedBy: "p",
          uploadedByRole: "patient",
        }}
        locale="en-US"
      />,
    );
    expect(screen.getByText("Uploaded by you")).toBeVisible();
    rerender(
      <RecordOrigin
        document={{
          patientId: "p",
          uploadedBy: "c",
          uploadedByRole: "clinician",
        }}
        locale="es-MX"
      />,
    );
    expect(screen.getByText("Subido por tu equipo de atención")).toBeVisible();
    rerender(
      <RecordOrigin
        document={{
          patientId: "p",
          uploadedBy: "different",
          uploadedByRole: "patient",
        }}
        locale="en-US"
      />,
    );
    expect(screen.getByText("Uploader unavailable")).toBeVisible();
  });
});
