import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("react-redux", () => ({
  useSelector: () => "local-clinician-token",
}));

vi.mock("@/services/api", () => ({
  api: { get, post },
}));

import { SmartImportReviewPanel } from "@/components/features/smart-import-review-panel";

const reviewResponse = {
  patient_id: "patient-1",
  review_state: "pending_review" as const,
  facts: [
    {
      id: "fact-1",
      fact_type: "medication",
      subject_type: "medication",
      value: { name: "Metformin", status: "active", dosage: "500 mg daily" },
      uncertainty: ["Dose form was not supplied."],
      review_state: "pending_review" as const,
      created_at: "2026-08-28T00:00:00Z",
      source: {
        issuer: "https://sandbox.example/fhir",
        resource_type: "MedicationRequest",
        external_resource_id: "med-1",
        version_id: "2",
        mapping_warnings: ["Frequency was not supplied."],
        validation_errors: [],
      },
    },
  ],
  total_count: 1,
  state_counts: { pending_review: 1, approved: 0, rejected: 0 },
  fact_type_counts: { medication: 1 },
  offset: 0,
  limit: 25,
};

describe("SMART import review panel", () => {
  it("does not invent a zero count while loading or after an initial failure", async () => {
    let reject!: (reason: Error) => void;
    get.mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    expect(screen.getByText(/Loading imported fact count/)).toBeInTheDocument();
    expect(screen.queryByText((_, element) => element?.tagName === "P" && /0 facts in this review state/.test(element.textContent ?? ""))).not.toBeInTheDocument();
    reject(new Error("Unavailable"));
    expect(await screen.findByText(/Imported fact count unavailable/)).toBeInTheDocument();
    expect(screen.queryByText((_, element) => element?.tagName === "P" && /0 facts in this review state/.test(element.textContent ?? ""))).not.toBeInTheDocument();
  });

  it("shows a genuine empty count only after a successful response", async () => {
    get.mockResolvedValue({ ...reviewResponse, total_count: 0, facts: [] });
    render(<SmartImportReviewPanel patientId="patient-1" />);
    expect(await screen.findByText((_, element) => element?.tagName === "P" && /0 facts in this review state/.test(element.textContent ?? ""))).toBeInTheDocument();
  });

  it("hides the old count while a different review-state filter loads", async () => {
    get.mockResolvedValueOnce(reviewResponse).mockImplementation(() => new Promise(() => {}));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    await screen.findByText("Metformin");
    fireEvent.click(screen.getByRole("button", { name: /Approved/ }));
    expect(screen.getByText(/Loading imported fact count/)).toBeInTheDocument();
    expect(screen.queryByText((_, element) => element?.tagName === "P" && /1 fact in this review state/.test(element.textContent ?? ""))).not.toBeInTheDocument();
  });
  it.each([
    ["condition", "Diabetes mellitus tipo 2"],
    ["medication", "Metformin 500"],
    ["condition", "2026-10-10T10:00:00Z"],
  ])("preserves %s names verbatim even when numbers resemble dates", async (factType, name) => {
    get.mockResolvedValue({ ...reviewResponse, facts: [{ ...reviewResponse.facts[0],
      fact_type: factType, value: { name, onset: "since age 2", dosage: "500 mg daily" },
    }] });
    render(<SmartImportReviewPanel patientId="patient-1" />);
    expect(await screen.findByText(name)).toBeInTheDocument();
    expect(screen.queryByText(/Feb 1, 2001/)).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    if (factType === "condition") expect(screen.getByText("since age 2")).toBeInTheDocument();
    else expect(screen.getByText("500 mg daily")).toBeInTheDocument();
  });

  it("keeps source identifiers in expandable audit details while source review stays available", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const metadata = await screen.findByText("MedicationRequest · med-1 · version 2");
    expect(metadata.closest("details")).not.toHaveAttribute("open");
    expect(metadata).not.toBeVisible();
    expect(screen.getByRole("button", { name: /source/i })).toBeEnabled();
    expect(post).not.toHaveBeenCalled();
  });
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue(reviewResponse);
  });

  it("shows mapped candidate fields and keeps the original source behind an explicit action", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);

    expect(await screen.findByText("Metformin")).toBeInTheDocument();
    expect(
      screen.getByText("MedicationRequest · med-1 · version 2"),
    ).toBeInTheDocument();
    expect(screen.getByText(/frequency was not supplied/i)).toBeInTheDocument();
    expect(
      screen.getByText(/field-by-field reconciliation decision/i),
    ).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      "/api/v1/smart/patients/patient-1/facts?review_state=pending_review&offset=0&limit=25",
      { token: "local-clinician-token" },
    );

    get.mockResolvedValueOnce({
      ...reviewResponse.facts[0].source,
      raw_resource: { resourceType: "MedicationRequest", id: "med-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /source/i }));

    await waitFor(() => {
      expect(get).toHaveBeenLastCalledWith(
        "/api/v1/smart/patients/patient-1/facts/fact-1/source",
        { token: "local-clinician-token" },
      );
    });
    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "PRE" &&
          element.textContent?.includes(
            '"resourceType": "MedicationRequest"',
          ) === true,
      ),
    ).toBeInTheDocument();
  });

  it("submits a clinician-selected reconciliation decision as JSON", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);

    await screen.findByText("Metformin");
    get.mockResolvedValueOnce({
      fact_id: "fact-1",
      fact_type: "medication",
      projectable: true,
      candidate_fields: { name: "Metformin", dosage: "500 mg daily" },
      available_fields: ["name", "dosage"],
      matches: [],
      safety_coverage: "Source text/name comparisons only. Drug interactions are not checked.",
      review_flags: ["No matching local medication was found. The approved list is unchanged."],
    });
    post.mockResolvedValue({});
    fireEvent.click(screen.getByRole("button", { name: /review changes/i }));

    await screen.findByText(/no conservative match was found/i);
    expect(screen.getByRole("region", { name: "Medication comparison coverage" })).toHaveTextContent("Drug interactions are not checked");
    expect(screen.getByRole("region", { name: "Medication comparison coverage" })).toHaveTextContent("approved list is unchanged");
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /add local record/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/api/v1/smart/patients/patient-1/facts/fact-1/reconcile",
        expect.objectContaining({
          decision: "add",
          selected_fields: ["name", "dosage"],
        }),
        { token: "local-clinician-token" },
      );
    });
  });

  it("filters candidates by mapped type and presents field-level correction", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);

    await screen.findByText("Metformin");
    fireEvent.change(
      screen.getByRole("combobox", {
        name: /filter imported facts by mapped type/i,
      }),
      {
        target: { value: "medication" },
      },
    );
    await waitFor(() => {
      expect(get).toHaveBeenLastCalledWith(
        "/api/v1/smart/patients/patient-1/facts?review_state=pending_review&offset=0&limit=25&fact_type=medication",
        { token: "local-clinician-token" },
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /^correct$/i }));
    expect(screen.getByRole("textbox", { name: "Medication" })).toHaveValue(
      "Metformin",
    );
    expect(
      screen.getByRole("textbox", { name: "Dosage instructions" }),
    ).toHaveValue("500 mg daily");
    expect(
      screen.queryByText(/corrected value \(json\)/i),
    ).not.toBeInTheDocument();
  });

  it("renders FHIR instants in the selected patient's timezone while preserving date-only values", async () => {
    get.mockResolvedValueOnce({
      ...reviewResponse,
      facts: [
        {
          ...reviewResponse.facts[0],
          fact_type: "procedure",
          value: {
            code: "Pelvis X-ray",
            performed: {
              start: "2012-10-02T11:40:58+00:00",
              end: "2012-10-02T12:34:58+00:00",
            },
          },
        },
      ],
    });

    render(
      <SmartImportReviewPanel
        patientId="patient-1"
        patientTimezone="America/Los_Angeles"
      />,
    );

    expect(await screen.findByText("Pelvis X-ray")).toBeInTheDocument();
    expect(screen.getByText(/Oct 2, 2012, 4:40 AM/)).toBeInTheDocument();
    expect(screen.getByText(/Oct 2, 2012, 5:34 AM/)).toBeInTheDocument();
  });
});
