import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  cleanRecordTitle,
  groupRecordDates,
  RecordRow,
} from "@/components/features/record-row";
import { DocumentParseStatus, DocumentType, type Document } from "@/types";

describe("Records presentation", () => {
  it.each(["en-US", "es-MX"] as const)(
    "uses a wrapping trailing AI status with its original accessible label in %s",
    (locale) => {
      const spanish = locale === "es-MX";
      render(
        <RecordRow
          document={document}
          locale={locale}
          typeLabel="resumen de alta"
          provider="Clínica con un nombre muy largo"
          date="2 oct"
          statusLabel={spanish ? "Explicación con IA" : "AI Summary"}
          onOpen={() => {}}
        />,
      );
      const status = screen.getByText(spanish ? "Resumen" : "Summary");
      expect(status).toHaveAttribute("aria-hidden", "true");
      expect(
        screen.getByText(spanish ? "Explicación con IA" : "AI Summary"),
      ).toHaveClass("sr-only");
      expect(status.closest(".ml-auto")).toHaveClass("max-w-full", "min-w-0");
      expect(status.closest(".flex-wrap")).toHaveClass("flex-1", "min-w-0");
    },
  );
  it("cleans only display metadata and preserves meaningful case and wording", () => {
    expect(
      cleanRecordTitle(
        "Morgan-Ellis_Metformin-Medication-Order_2026-10-02_es-MX.pdf",
        "Morgan Ellis",
      ),
    ).toBe("Metformin Medication Order");
    expect(
      cleanRecordTitle("Morgan-Ellison_HbA1c_2026-10-02.pdf", "Morgan Ellis"),
    ).toBe("Morgan Ellison HbA1c");
    expect(cleanRecordTitle("A+B_(test)_ECG.pdf", "A+B (test)")).toBe("ECG");
    expect(cleanRecordTitle("2026-10-02_es-MX.pdf")).toBe(
      "2026-10-02_es-MX.pdf",
    );
  });

  it("groups the last seven patient-local dates, sorts newest first, and retains unknown dates", () => {
    const records = [
      { id: "old", createdAt: "2026-10-04T06:59:59Z" },
      { id: "boundary", createdAt: "2026-10-04T07:00:00Z" },
      { id: "today", createdAt: "2026-10-11T06:59:59Z" },
      { id: "unknown", createdAt: "unknown" },
    ];
    const groups = groupRecordDates(
      records,
      new Date("2026-10-11T06:59:59Z"),
      "America/Los_Angeles",
    );
    expect(
      groups.map((group) => [
        group.key,
        group.items.map((record) => record.id),
      ]),
    ).toEqual([
      ["recent", ["today", "boundary"]],
      ["earlier", ["old", "unknown"]],
    ]);
    expect(records[0].id).toBe("old");
  });

  const document = {
    id: "synthetic-record",
    fileName: "Morgan-Ellis_Discharge-Summary_2026-10-02.pdf",
    documentType: DocumentType.DISCHARGE_SUMMARY,
    parseStatus: DocumentParseStatus.COMPLETED,
    uploadedByRole: "patient",
    parsed: true,
    aiSummary: "Exact source wording.",
  } as Document;

  it("keeps the true document type and full source filename accessible with the cleaned title", () => {
    const onOpen = vi.fn();
    render(
      <RecordRow
        document={document}
        patientName="Morgan Ellis"
        locale="en-US"
        typeLabel="discharge summary"
        provider="City Health"
        date="Oct 2"
        statusLabel="AI Summary"
        onOpen={onOpen}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Discharge Summary" }),
    ).toHaveClass("break-words");
    expect(screen.getByText("discharge summary")).toBeInTheDocument();
    expect(screen.queryByText("Visit note")).not.toBeInTheDocument();
    expect(screen.getByText(document.fileName)).toHaveClass("sr-only");
    fireEvent.click(
      screen.getByRole("button", { name: /Morgan-Ellis_Discharge-Summary/ }),
    );
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("keeps Spanish duplicate status readable and suppresses stale AI summary chips", () => {
    render(
      <RecordRow
        document={{ ...document, parseStatus: DocumentParseStatus.DUPLICATE }}
        locale="es-MX"
        typeLabel="resumen de alta"
        provider="Documento subido por usted"
        date="2 oct"
        statusLabel="Archivo duplicado"
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("Archivo duplicado")).toBeInTheDocument();
    expect(screen.queryByText("AI Summary")).not.toBeInTheDocument();
    expect(screen.getByRole("heading")).not.toHaveClass("truncate");
    expect(screen.getByRole("button")).toHaveClass("min-h-11");
  });

  it("shows processing dots only while reading a document", () => {
    const { container } = render(
      <RecordRow
        document={{ ...document, parseStatus: DocumentParseStatus.PROCESSING }}
        locale="es-MX"
        typeLabel="resumen de alta"
        provider="City Health"
        date="2 oct"
        statusLabel="En proceso..."
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText("En proceso...")).toBeInTheDocument();
    expect(screen.getByText("Leyendo")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll(".bg-current")).toHaveLength(3);
  });
});
