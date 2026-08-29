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
      screen.getByText(/does not overwrite the local record/i),
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

  it("submits explicit review actions as JSON request bodies", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);

    await screen.findByText("Metformin");
    post.mockResolvedValue({});
    fireEvent.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/api/v1/smart/patients/patient-1/facts/fact-1/approve",
        {},
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
