import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatBubble } from "@/components/features/chat-bubble";
import { ChatResultsCard } from "@/components/features/chat-results-card";
import type { DocumentResult } from "@/services/documents";
import type { ChatDocumentResultsAttachment, Locale } from "@/types";

function lab(overrides: Partial<DocumentResult>): DocumentResult {
  return {
    kind: "lab_result",
    name: "Glucose",
    value: "98",
    unit: "mg/dL",
    reference_range: "70-99",
    flag: null,
    flag_meaning: null,
    range_status: "within",
    panel: "Basic metabolic panel",
    observed_at: "10/01/2026",
    page: 1,
    reviewed: false,
    ...overrides,
  };
}

const BLOOD_PRESSURE: DocumentResult = {
  kind: "vital_sign",
  name: "Blood pressure",
  value: "142/88",
  unit: "mmHg",
  reference_range: null,
  flag: null,
  flag_meaning: null,
  range_status: null,
  panel: null,
  observed_at: "Oct 1, 2026 9:40 AM",
  page: 2,
  reviewed: false,
};

const MIXED: DocumentResult[] = [
  lab({ name: "Sodium", value: "131", unit: "mmol/L", reference_range: "135-145", flag: "L", flag_meaning: "low", range_status: "below" }),
  lab({ name: "Glucose", value: "98" }),
  lab({ name: "Potassium", value: "6.9", unit: "mmol/L", reference_range: "3.5-5.1", flag: "HH", flag_meaning: "critical", range_status: "above" }),
  lab({ name: "eGFR", value: "52", unit: null, reference_range: ">60", range_status: "below" }),
  lab({ name: "Chloride", value: "101", unit: "mmol/L", reference_range: "98-107" }),
  BLOOD_PRESSURE,
];

function attachment(overrides: Partial<ChatDocumentResultsAttachment> = {}): ChatDocumentResultsAttachment {
  return {
    type: "document_results",
    documentId: "doc-1",
    fileName: "labs-2026-10-01.pdf",
    title: { "en-US": "Lab report, October 1", "es-MX": "Reporte de laboratorio, 1 de octubre" },
    results: MIXED,
    ...overrides,
  };
}

function renderCard(props: { attachment?: ChatDocumentResultsAttachment; language?: Locale; locale?: Locale } = {}) {
  return render(
    <ChatResultsCard
      attachment={props.attachment ?? attachment()}
      language={props.language ?? "en-US"}
      locale={props.locale ?? "en-US"}
    />,
  );
}

function names(list: HTMLElement) {
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.querySelector("p")?.textContent);
}

describe("ChatResultsCard", () => {
  it("leads with the critical banner and lists out-of-range results, critical first", () => {
    renderCard();
    const card = screen.getByRole("region", { name: "Lab report, October 1" });
    expect(within(card).getByText("Results from this report")).toBeInTheDocument();
    expect(within(card).getByText("Contact your care team today.")).toBeInTheDocument();
    expect(
      within(card).getByText("Call 911 if you have chest pain, palpitations or trouble breathing."),
    ).toBeInTheDocument();

    const flagged = within(card).getByRole("list", { name: "Outside the report's range" });
    expect(names(flagged)).toEqual(["Potassium", "Sodium", "eGFR"]);
    const potassium = within(flagged).getAllByRole("listitem")[0];
    expect(potassium).toHaveTextContent("6.9 mmol/L");
    expect(potassium).toHaveTextContent("Result status: Critical");
    expect(potassium).toHaveTextContent("Range: 3.5-5.1");
    expect(within(flagged).getAllByRole("listitem")[1]).toHaveTextContent("Result status: Low");
    expect(within(flagged).getAllByRole("listitem")[2]).toHaveTextContent("Result status: Outside range");
    expect(within(card).queryByText("All results are within the report's ranges.")).not.toBeInTheDocument();
  });

  it("keeps in-range results and measurements collapsed behind an accessible toggle", () => {
    renderCard();
    const toggle = screen.getByRole("button", { name: "Show 2 results in range" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "In range" })).not.toBeInTheDocument();
    expect(screen.queryByText("Blood pressure")).not.toBeVisible();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName("Hide results in range");
    expect(names(screen.getByRole("list", { name: "In range" }))).toEqual(["Glucose", "Chloride"]);
    const measurements = screen.getByRole("list", { name: "Measurements" });
    expect(within(measurements).getByText("Blood pressure")).toBeVisible();
    expect(within(measurements).getByText("142/88 mmHg")).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("says everything is within range and shows no banner when nothing is flagged", () => {
    renderCard({
      attachment: attachment({ results: [lab({ name: "Glucose" }), lab({ name: "Chloride", value: "101" })] }),
    });
    expect(screen.getByText("All results are within the report's ranges.")).toBeInTheDocument();
    expect(screen.queryByText("Contact your care team today.")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Outside the report's range" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Show 2 results in range" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(names(screen.getByRole("list", { name: "In range" }))).toEqual(["Glucose", "Chloride"]);
  });

  it("states review status and links to the document in Records", () => {
    const { unmount } = renderCard();
    expect(screen.getByText("Read automatically · not yet reviewed by your care team")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See in Records" })).toHaveAttribute("href", "/records?document=doc-1");
    unmount();

    renderCard({ attachment: attachment({ results: MIXED.map((result) => ({ ...result, reviewed: true })) }) });
    expect(screen.getByText("Reviewed by your care team")).toBeInTheDocument();
    expect(screen.queryByText(/not yet reviewed/)).not.toBeInTheDocument();
  });

  it("uses Mexican Spanish copy with the Spanish title and printed values unchanged", () => {
    renderCard({ language: "es-MX", locale: "es-MX" });
    const card = screen.getByRole("region", { name: "Reporte de laboratorio, 1 de octubre" });
    expect(within(card).getByText("Resultados de este reporte")).toBeInTheDocument();
    expect(within(card).getByText("Comunícate hoy con tu equipo de atención.")).toBeInTheDocument();
    expect(
      within(card).getByText("Llama al 911 si tienes dolor de pecho, palpitaciones o dificultad para respirar."),
    ).toBeInTheDocument();
    const flagged = within(card).getByRole("list", { name: "Fuera del rango del reporte" });
    const potassium = within(flagged).getAllByRole("listitem")[0];
    expect(potassium).toHaveTextContent("Potassium");
    expect(potassium).toHaveTextContent("Estado del resultado: Crítico");
    expect(potassium).toHaveTextContent("Rango: 3.5-5.1");
    const toggle = within(card).getByRole("button", { name: "Mostrar 2 resultados dentro del rango" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAccessibleName("Ocultar resultados dentro del rango");
    expect(within(card).getByRole("list", { name: "Mediciones" })).toBeInTheDocument();
    expect(
      within(card).getByText("Leído automáticamente · aún no revisado por tu equipo de atención"),
    ).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver en Registros" })).toHaveAttribute(
      "href",
      "/records?document=doc-1",
    );
  });

  it("falls back to the cleaned file name when the message's language has no title", () => {
    renderCard({ attachment: attachment({ title: { "es-MX": "Reporte" } }), language: "en-US" });
    expect(screen.getByRole("region", { name: "Labs" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "labs-2026-10-01.pdf" })).not.toBeInTheDocument();
  });

  it("offers only measurements when a report has no lab results in range", () => {
    renderCard({ attachment: attachment({ results: [BLOOD_PRESSURE] }) });
    expect(screen.queryByText("All results are within the report's ranges.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show 1 measurement" }));
    expect(screen.getByRole("list", { name: "Measurements" })).toBeInTheDocument();
  });
});

describe("ChatBubble attachments", () => {
  const base = {
    content: "Your potassium was printed as critical.\n\nSource: labs-2026-10-01.pdf, page 1",
    language: "en-US" as Locale,
    locale: "en-US" as Locale,
    role: "assistant" as const,
    timestamp: "2026-10-13T10:00:00Z",
  };

  it("renders a message without attachments exactly as before", () => {
    const plain = render(<ChatBubble {...base} />);
    const plainMarkup = plain.container.innerHTML;
    plain.unmount();
    const empty = render(<ChatBubble {...base} attachments={[]} />);
    expect(empty.container.innerHTML).toBe(plainMarkup);
    const bubble = empty.container.querySelector(".ma-bubble > div");
    expect(bubble?.className.startsWith("max-w-[88%] ")).toBe(true);
    expect(bubble?.children).toHaveLength(2);
    expect(screen.queryByText("Results from this report")).not.toBeInTheDocument();
  });

  it("places the card under the reply text, which is unchanged", () => {
    const { container } = render(<ChatBubble {...base} attachments={[attachment()]} />);
    const text = screen.getByText(/Your potassium was printed as critical\./);
    expect(text.textContent).toBe(base.content);
    const card = screen.getByRole("region", { name: "Lab report, October 1" });
    expect(text.nextElementSibling).toBe(card);
    expect(container.querySelector(".ma-bubble > div")?.className).toContain("w-full");
  });
});
