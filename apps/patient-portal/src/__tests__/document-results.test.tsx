import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentResults, resultChip } from "@/components/features/document-results";
import type { DocumentResult } from "@/services/documents";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get } }));

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
    reviewed: true,
    ...overrides,
  };
}

const PRINTED_RESULTS: DocumentResult[] = [
  lab({ name: "Sodium", value: "131", unit: "mmol/L", reference_range: "135-145", flag: "L", flag_meaning: "low", range_status: "below" }),
  lab({ name: "Hemoglobin A1c", value: "8.1", unit: "%", reference_range: "4.0-5.6", flag: "H", flag_meaning: "high", range_status: "above", panel: "Diabetes", reviewed: false }),
  lab({ name: "Glucose", value: "98" }),
  lab({ name: "Potassium", value: "6.9", unit: "mmol/L", reference_range: "3.5-5.1", flag: "HH", flag_meaning: "critical", range_status: "above" }),
  lab({ name: "eGFR", value: "52", unit: null, reference_range: ">60", flag: null, flag_meaning: null, range_status: "below", panel: "Diabetes" }),
  {
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
  },
];

function renderResults(locale: "en-US" | "es-MX" = "en-US") {
  return render(<DocumentResults documentId="doc-1" locale={locale} token="access-token" />);
}

function rowFor(name: string) {
  const row = screen.getByText(name).closest("li");
  if (!row) throw new Error(`No row for ${name}`);
  return row;
}

describe("DocumentResults", () => {
  beforeEach(() => {
    get.mockReset();
  });

  it("derives the chip only from the printed flag, else the printed range", () => {
    expect(resultChip({ flag_meaning: "critical", range_status: "above" })).toBe("critical");
    expect(resultChip({ flag_meaning: "high", range_status: "within" })).toBe("high");
    expect(resultChip({ flag_meaning: "low", range_status: null })).toBe("low");
    expect(resultChip({ flag_meaning: "abnormal", range_status: null })).toBe("outside");
    expect(resultChip({ flag_meaning: null, range_status: "above" })).toBe("outside");
    expect(resultChip({ flag_meaning: "unrecognized", range_status: "below" })).toBe("outside");
    expect(resultChip({ flag_meaning: null, range_status: "within" })).toBeNull();
    expect(resultChip({ flag_meaning: "unrecognized", range_status: null })).toBeNull();
  });

  it("groups printed lab results by panel with English chips and separate measurements", async () => {
    get.mockResolvedValue(PRINTED_RESULTS);
    renderResults();

    const section = await screen.findByRole("region", { name: "Test results" });
    expect(get).toHaveBeenCalledWith(
      "/api/v1/documents/doc-1/results",
      expect.objectContaining({ token: "access-token" }),
    );

    const metabolic = within(section).getByRole("list", { name: "Basic metabolic panel" });
    const diabetes = within(section).getByRole("list", { name: "Diabetes" });
    // Panels appear in printed order; rows keep printed order within each panel.
    expect(
      within(metabolic).getAllByRole("listitem").map((item) => item.querySelector("p")?.textContent),
    ).toEqual(["Sodium", "Glucose", "Potassium"]);
    expect(within(diabetes).getAllByRole("listitem")).toHaveLength(2);
    expect(metabolic.compareDocumentPosition(diabetes) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(within(rowFor("Sodium")).getByText("131 mmol/L")).toBeInTheDocument();
    expect(within(rowFor("Sodium")).getByText("Range: 135-145")).toBeInTheDocument();
    expect(within(rowFor("Sodium")).getByText("Low")).toBeInTheDocument();
    expect(within(rowFor("Hemoglobin A1c")).getByText("High")).toBeInTheDocument();
    expect(within(rowFor("eGFR")).getByText("Outside range")).toBeInTheDocument();
    expect(within(rowFor("eGFR")).getByText("52")).toBeInTheDocument();
    // Status is text, not only color, and is announced as a status.
    expect(within(rowFor("Sodium")).getByText(/Result status/)).toHaveClass("sr-only");

    const glucose = rowFor("Glucose");
    expect(within(glucose).queryByText(/Result status/)).not.toBeInTheDocument();
    expect(glucose).not.toHaveTextContent(/high|low|outside|critical|normal|good|bad/i);

    const measurements = within(section).getByRole("list", { name: "Measurements" });
    expect(within(measurements).getByText("Blood pressure")).toBeInTheDocument();
    expect(within(measurements).getByText("142/88 mmHg")).toBeInTheDocument();
    expect(within(measurements).getByText("Oct 1, 2026 9:40 AM")).toBeInTheDocument();
    expect(within(metabolic).queryByText("Blood pressure")).not.toBeInTheDocument();

    expect(section).toHaveTextContent("read automatically from this document");
    expect(section).toHaveTextContent("Your care team will review your results with you.");
  });

  it("renders the same printed values with Mexican Spanish chips and safety copy", async () => {
    get.mockResolvedValue(PRINTED_RESULTS);
    renderResults("es-MX");

    const section = await screen.findByRole("region", { name: "Resultados" });
    expect(within(rowFor("Sodium")).getByText("Rango: 135-145")).toBeInTheDocument();
    expect(within(rowFor("Sodium")).getByText("Bajo")).toBeInTheDocument();
    expect(within(rowFor("Hemoglobin A1c")).getByText("Alto")).toBeInTheDocument();
    expect(within(rowFor("eGFR")).getByText("Fuera de rango")).toBeInTheDocument();
    expect(within(rowFor("Potassium")).getByText("Crítico")).toBeInTheDocument();
    expect(within(rowFor("Potassium")).getByText("Comunícate hoy con tu equipo de atención.")).toBeInTheDocument();
    expect(within(rowFor("Hemoglobin A1c")).getByText("Aún no revisado por tu equipo de atención")).toBeInTheDocument();
    expect(within(section).getByRole("list", { name: "Mediciones" })).toBeInTheDocument();
    expect(section).toHaveTextContent("se leyeron automáticamente de este documento");
    expect(section).toHaveTextContent("Tu equipo de atención revisará tus resultados contigo.");
    // Printed clinical values are never translated.
    expect(within(rowFor("Sodium")).getByText("131 mmol/L")).toBeInTheDocument();
  });

  it("shows contact copy only for a critical result", async () => {
    get.mockResolvedValue(PRINTED_RESULTS);
    renderResults();

    await screen.findByRole("region", { name: "Test results" });
    expect(within(rowFor("Potassium")).getByText("Critical")).toBeInTheDocument();
    expect(within(rowFor("Potassium")).getByText("Contact your care team today.")).toBeInTheDocument();
    expect(screen.getAllByText("Contact your care team today.")).toHaveLength(1);
  });

  it("marks each row that the care team has not yet reviewed", async () => {
    get.mockResolvedValue(PRINTED_RESULTS);
    renderResults();

    await screen.findByRole("region", { name: "Test results" });
    const marker = "Not yet reviewed by your care team";
    expect(within(rowFor("Hemoglobin A1c")).getByText(marker)).toBeInTheDocument();
    expect(within(rowFor("Blood pressure")).getByText(marker)).toBeInTheDocument();
    expect(within(rowFor("Sodium")).queryByText(marker)).not.toBeInTheDocument();
    expect(screen.getAllByText(marker)).toHaveLength(2);
  });

  it("renders no section when the document has no results", async () => {
    get.mockResolvedValue([]);
    const { container } = renderResults();

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
  });

  it("ignores malformed rows rather than showing them", async () => {
    get.mockResolvedValue([{ id: "not-a-result", file_name: "lab.pdf" }, { kind: "lab_result", name: "", value: "1" }]);
    const { container } = renderResults();

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a loading state, then an error with a retry that refetches", async () => {
    get.mockRejectedValueOnce(new Error("network"));
    renderResults();

    expect(screen.getByRole("status")).toHaveTextContent("Loading test results…");
    expect(await screen.findByText("Could not load test results")).toBeInTheDocument();

    get.mockResolvedValueOnce([lab({ name: "Sodium", value: "131" })]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("region", { name: "Test results" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("localizes the error state in Mexican Spanish", async () => {
    get.mockRejectedValueOnce(new Error("network"));
    renderResults("es-MX");

    expect(await screen.findByText("No se pudieron cargar los resultados")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Intentar de nuevo" })).toBeInTheDocument();
  });

  it("does not request results without a session", () => {
    const { container } = render(<DocumentResults documentId="doc-1" locale="en-US" token={null} />);
    expect(get).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });
});
